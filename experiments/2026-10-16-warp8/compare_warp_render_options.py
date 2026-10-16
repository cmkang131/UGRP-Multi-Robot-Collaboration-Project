"""Isolated gcp3 render-only comparison of explicit shadows vs MJWarp default.

Same saved states and frozen perception; mjw.step is disabled. This is not a
teacher trial and never authorizes a changed renderer for a gate.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def read(path):
    return json.loads(path.read_text() if path.exists() else
                      subprocess.check_output(['zstd', '-qdc', str(path) + '.zst'], text=True))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--world', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    assert not a.out.exists()
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', LP_NUM_THREADS='1')
    sys.path.insert(0, str(a.source))
    os.chdir(a.source)
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp
    from PIL import Image
    from sim.grasp_act_scene import make_scene
    from sim.lookaround_localization import LookaroundLocalizer
    from sim.masterpi_camera_profile import raw_fisheye_remap

    def forbidden_step(*args, **kwargs):
        raise RuntimeError('physics forbidden in render-only comparison')
    mjw.step = forbidden_step
    raw = a.run / f'world-{a.world:03d}/raw'
    result, plan = read(raw / 'result.json'), read(raw / 'plan.json')
    static = make_scene(plan).config['static_map']
    saved = np.load(a.run / f'world-{a.world:03d}-states.npz')
    indices = {int(t): i for i, t in enumerate(saved['ticks'])}
    model = mujoco.MjModel.from_xml_string((raw / 'scene.xml').read_text())
    # Reuse the gate's exact compiled-geometry and sleep-import adapters.
    # Neither adapter changes the render option under comparison.
    backend = Path('/home/ugrp/ugrp-sim/src') / read(a.run / 'summary.json')['source_sha']
    sys.path.insert(0, str(backend / 'scripts'))
    from simalt_compiled_compat import apply_geometry, apply_reference
    from warp_act_core import runtime_sleep_policy
    command = read(a.run.with_suffix('.command.json'))['command']
    references = read(Path(command[command.index('--per-world-model-references-v1')+1]))
    xml = raw / 'scene.xml'
    reference = references[hashlib.sha256(xml.read_bytes()).hexdigest()]
    apply_geometry(model, xml, Path(reference['geometry']))
    apply_reference(model, xml, Path(reference['actuator']))
    policy = mujoco.mjtSleepPolicy
    model.tree_sleep_policy[:] = runtime_sleep_policy(model.tree_sleep_policy,
        auto=int(policy.mjSLEEP_AUTO), auto_never=int(policy.mjSLEEP_AUTO_NEVER),
        auto_allowed=int(policy.mjSLEEP_AUTO_ALLOWED), never=int(policy.mjSLEEP_NEVER),
        allowed=int(policy.mjSLEEP_ALLOWED))
    data = mujoco.MjData(model)
    gpu_model, gpu_data = mjw.put_model(model), mjw.put_data(model, data)
    remap = raw_fisheye_remap(640, 480)
    device = wp.zeros((1, 480, 640), dtype=wp.vec3)
    robots = list(result['lookaround_result'])
    reports = {}
    a.out.mkdir(parents=True)
    for shadows in (True, False):
        label = 'shadows_on' if shadows else 'shadows_off_official_default'
        start = time.perf_counter()
        rc = mjw.create_render_context(model, nworld=1, cam_res=(640, 480),
            render_rgb=True, render_depth=False, render_seg=False, use_textures=True,
            use_shadows=shadows, enabled_geom_groups=[0,1,2,3], cam_active=[r+'__robot_cam' for r in robots])
        localizers = {r: LookaroundLocalizer(static, [0.,0.,0.], mode='setdown_global_v1', map_pose_known=False,
            odometry_profile=result['effective_motion_profile'], localization_support=result['localization_support']) for r in robots}
        measured = {r: [] for r in robots}
        # The recorded lookaround views are synchronized for the two robots.
        views = [result['lookaround_result'][r]['localizer']['views'] for r in robots]
        assert len({len(v) for v in views}) == 1
        for n in range(len(views[0])):
            ticks = {round(v[n]['t']*10) for v in views}
            assert len(ticks) == 1
            tick, = ticks
            k = indices[tick]
            wp.copy(gpu_data.qpos, wp.array(saved['qpos'][k:k+1], dtype=float))
            wp.copy(gpu_data.qvel, wp.array(saved['qvel'][k:k+1], dtype=float))
            mjw.kinematics(gpu_model, gpu_data)
            mjw.camlight(gpu_model, gpu_data)
            mjw.refit_bvh(gpu_model, gpu_data, rc)
            mjw.render(gpu_model, gpu_data, rc)
            for camera, rid in enumerate(robots):
                mjw.get_rgb(rc, camera, device)
                wp.synchronize()
                rgb = np.clip(device.numpy()[0]*255, 0, 255).astype(np.uint8)
                rgb = cv2.remap(rgb, *remap, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                buffer = io.BytesIO()
                Image.fromarray(rgb).save(buffer, format='JPEG', quality=82)
                image_bytes = buffer.getvalue()
                (a.out / f'{label}-{rid}-{n:02d}.jpg').write_bytes(image_bytes)
                view = views[camera][n]
                loc = localizers[rid]
                loc.command_own.x = np.asarray(view['command_pose'])
                rec = loc.observe(view['t'], np.asarray(Image.open(io.BytesIO(image_bytes)).convert('RGB')),
                                  {int(k): v for k, v in view['servo'].items()})
                measured[rid].append(dict(t=view['t'], observations={k: rec.get(k) for k in ('status','wall_points','floor_lines','doors')},
                    recorded={k: view.get(k) for k in ('status','wall_points','floor_lines','doors')},
                    image_sha256=hashlib.sha256(image_bytes).hexdigest()))
        reports[label] = dict(use_shadows=shadows, wall_s=time.perf_counter()-start, rows=measured,
            decisions={rid: loc.finalize(view_start=0) for rid, loc in localizers.items()})
    output = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), host='gcp3', run=str(a.run), world=a.world,
        source=str(a.source), mujoco=mujoco.__version__, reports=reports, physics_steps=0, controller_execution=0,
        reference='https://mujoco.readthedocs.io/en/latest/mjwarp/api.html#create_render_context',
        scope='GPU rendering only; frozen CPU perception; official default comparison, no gate admission')
    (a.out / 'summary.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({label: {rid: {k: d.get(k) for k in ('accepted','reason','groups','score_gap')}
        for rid, d in rep['decisions'].items()} for label, rep in reports.items()}))


if __name__ == '__main__':
    main()
