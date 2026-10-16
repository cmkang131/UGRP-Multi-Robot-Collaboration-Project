"""Opt-in MJWarp kinematic RGB feasibility recording; never a driving result.

The recorder owns fixture poses. The separate estimator sees own.json only;
eval-only.json contains labels. No pose/segmentation is embedded in own records.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

RENDERER_SHA = '3c598b816b823ef93d064b2f30ffd07cf5493816'
PROFILE = 'walls_floor_contrast_v5_indigo110_s80'


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(a):
    if platform.system() != 'Linux' or not platform.node().startswith('ugrp-act-l4-gcp2'):
        raise ValueError('GCP2_L4_ONLY')
    queue = json.loads(a.queue.read_text())
    table = Path(queue['rejection_table'])
    if not table.is_absolute() or not table.is_file():
        raise ValueError('ABSOLUTE_EXISTING_REJECTION_TABLE_REQUIRED')
    if queue['toggle'] != 'mapbuild1_v1' or queue['enabled'] is not True:
        raise ValueError('EXPLICIT_MAPBUILD1_V1_REQUIRED')
    source = Path(__file__).resolve().parents[1]
    current = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if current != queue['source_sha'] or subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source):
        raise ValueError('CLEAN_PINNED_MAPBUILD_SOURCE_REQUIRED')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=a.renderer_source, text=True).strip() != RENDERER_SHA:
        raise ValueError('PINNED_RENDERER_SOURCE_REQUIRED')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=a.renderer_source):
        raise ValueError('CLEAN_RENDERER_SOURCE_REQUIRED')
    base = Path('/home/ugrp/ugrp-sim')
    leases = [json.loads(p.read_text()) for p in (base/'leases').glob('*.json')]
    if not any(p.get('task') == 'mapbuild1' for p in leases):
        raise ValueError('OWN_LEASE_REQUIRED')
    # Six kinematic worlds, not six physics workers; count them conservatively.
    if sum(int(p.get('concurrency', 0)) for p in leases if p.get('task') != 'mapbuild1') + 6 > 40:
        raise ValueError('SHARED_WORLD_LIMIT')
    # Reuse warp5's host admission floors; these are resource watchdogs,
    # never action-selection or visual-acceptance constants.
    free = os.statvfs(base).f_bavail*os.statvfs(base).f_frsize
    available = int(next(s for s in Path('/proc/meminfo').read_text().splitlines()
                         if s.startswith('MemAvailable:')).split()[1])*1024
    if free < 15*1024**3 or available < 6*1024**3:
        raise ValueError('WARP5_RESOURCE_FLOOR_NOT_MET')
    a.output.mkdir(parents=True, exist_ok=False)
    dump(a.output/'queue.json', queue)
    dump(a.output/'resources.json', dict(leases=leases, free_bytes=os.statvfs(base).f_bavail*os.statvfs(base).f_frsize,
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],text=True)))
    sys.path.insert(0, str(a.renderer_source))
    sys.path.insert(1, str(a.renderer_source/'scripts'))
    # Compiled XML keeps the pinned renderer's relative texture asset paths.
    # The sparse recorder checkout intentionally contains no duplicate assets.
    os.chdir(a.renderer_source)
    import cv2
    import numpy as np
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from scripts import probe_scene_tex2 as old
    from scripts.generate_scene_textures import MAPS
    from scripts.simalt_physics_compare import unused_efm
    from scripts.warp5_render import Renderer
    from sim import camera_render_quality as quality
    from sim.masterpi_camera_profile import raw_fisheye_remap
    wp.init(); cv2.setNumThreads(1)
    map_path = MAPS[0]
    model, scene, hardware, xml, audit = old.build_model(map_path, PROFILE)
    quality.configure_model(model, 'no_mip_v1')
    data = mujoco.MjData(model)
    view = old.wall_views(json.loads(map_path.read_text()))[0]
    fixtures = []
    for pose in ('drive', 'high'):
        pwm, setup = old.fixture(model, data, scene, view, pose, hardware)
        for motion in ('forward', 'lateral', 'turn'):
            fixtures.append(dict(name=pose+'-'+motion, motion=motion, pwm=pwm, qpos=data.qpos.copy()))
    wm = mjw.put_model(model)
    ncon = 1 << (max(32, int(data.ncon))-1).bit_length()
    njmax = 1 << (max(256, int(data.nefc))-1).bit_length()
    with unused_efm(model, data):
        wd = mjw.put_data(model, data, nworld=len(fixtures), nconmax=ncon, njmax=njmax)
    rc = Renderer(model, wm, wd, [('r1','r1__robot_cam',(640,480))],
                  enabled=True, texture_after_lighting=True)
    mx, my = raw_fisheye_remap(640,480)
    bid = model.body('r1__robot').id
    adr = int(model.jnt_qposadr[int(model.body_jntadr[bid])])
    base_q = np.stack([f['qpos'] for f in fixtures])
    own, labels = [], []
    start = time.monotonic()
    error = None
    try:
        # 4 seconds/10Hz is finite acquisition coverage. 0.2m/15deg is the
        # preregistered excitation range, never an acceptance threshold.
        for tick in range(41):
            t = tick/10
            phase = min(t/2, (4-t)/2)
            poses = base_q.copy()
            for i, f in enumerate(fixtures):
                q = poses[i]; w, _, _, z = q[adr+3:adr+7]
                yaw = 2*math.atan2(z,w)
                dx = .2*phase if f['motion']=='forward' else 0.
                dy = .2*phase if f['motion']=='lateral' else 0.
                da = math.radians(15)*phase if f['motion']=='turn' else 0.
                q[adr] += math.cos(yaw)*dx-math.sin(yaw)*dy
                q[adr+1] += math.sin(yaw)*dx+math.cos(yaw)*dy
                q[adr+3:adr+7] = [math.cos((yaw+da)/2),0,0,math.sin((yaw+da)/2)]
                labels.append(dict(sequence=f['name'], frame_id=tick, t=t, pose=[dx,dy,da]))
            wp.copy(wd.qpos, wp.array(poses,dtype=wd.qpos.dtype))
            images = np.clip(rc.render()['r1'][0],0,255).astype(np.uint8)
            for f, image in zip(fixtures, images):
                folder = a.output/f['name']; folder.mkdir(exist_ok=True)
                image = cv2.remap(image,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                path = folder/f'{tick:04d}.jpg'
                ok, jpeg = cv2.imencode('.jpg',cv2.cvtColor(image,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82])
                if not ok: raise ValueError('JPEG_ENCODE_FAILED')
                path.write_bytes(jpeg.tobytes())
                own.append(dict(sequence=f['name'], robot_id='r1', frame_id=tick,t=t,
                    rgb=str(path.relative_to(a.output)),sha256=sha(path),
                    servo={str(k):int(v) for k,v in f['pwm'].items()},
                    command_delta=[0.,0.,0.],command_covariance=np.zeros((3,3)).tolist()))
            print('recorded', tick, flush=True)
    except BaseException as exc:
        error = dict(category='HOST_ERROR',reason=repr(exc),blocked_object='kinematic_recorder',
                     minimum_gap_m=None,gap_status='not_applicable_to_render_fixture')
        raise
    finally:
        dump(a.output/'own.json',dict(schema='ugrp.mapbuild1.own.v1',frames=own,
            source_sha=current, renderer_sha=RENDERER_SHA, backend='mjwarp_render',
            scene=PROFILE,quality='no_mip_v1',scope='kinematic_render_only',
            command_scope='zero wheel prior; fixture PWM specification, no actual drive'))
        dump(a.output/'eval-only.json',dict(frames=labels,map=str(map_path),map_sha256=sha(map_path)))
        dump(a.output/'summary.json',dict(status='HOST_ERROR' if error else 'cap_end',frames=len(own),
            sequences=len(fixtures),physics_steps=0,wall_s=time.monotonic()-start,error=error,
            renderer_audit=rc.audit,scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
            jpeg_bytes=sum(p.stat().st_size for p in a.output.rglob('*.jpg')),
            recording='all frames10Hz; entire4s is within terminal10s buffer'))
        dump(a.output/'rejection-table.json',dict(raw=str(a.output),reproduction=sys.argv,
            stages=[dict(stage='requested_frames',cumulative_pass_n=246,rejected_n=0),
                    dict(stage='rendered_frames',cumulative_pass_n=len(own),rejected_n=246-len(own))],
            reasons=[] if error is None else [error]))
        dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue',type=Path,required=True)
    p.add_argument('--renderer-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not a.execute: p.error('explicit --execute required; default off')
    existed = a.output.exists()
    try:
        run(a)
    except BaseException as exc:
        # Preserve initialization errors too, before a renderer or frame exists.
        if not existed and a.output.is_dir() and not (a.output/'summary.json').exists():
            import traceback
            error=dict(category='HOST_ERROR',reason=repr(exc),blocked_object='recorder_initialization',
                minimum_gap_m=None,gap_status='not_measured',traceback=traceback.format_exc())
            dump(a.output/'summary.json',dict(status='HOST_ERROR',frames=0,physics_steps=0,error=error))
            dump(a.output/'rejection-table.json',dict(stages=[
                dict(stage='requested_frames',cumulative_pass_n=246,rejected_n=0),
                dict(stage='rendered_frames',cumulative_pass_n=0,rejected_n=246)],
                reasons=[error],raw=str(a.output),reproduction=sys.argv))
        raise


if __name__=='__main__': main()
