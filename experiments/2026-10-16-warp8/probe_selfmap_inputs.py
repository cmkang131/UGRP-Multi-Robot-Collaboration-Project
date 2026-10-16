"""gcp3 render-only validation of open-gripper native release observations.

Render and estimator run in separate processes. Evaluation poses never enter
the estimator. No old floor-line or global-consensus detector is invoked.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def read(path):
    return json.loads(path.read_text() if path.exists() else
                      subprocess.check_output(['zstd', '-qdc', str(path)+'.zst'], text=True))


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def render(a):
    sys.path.insert(0, str(a.frozen)); os.chdir(a.frozen)
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp
    from PIL import Image
    from sim.grasp_act_scene import make_scene
    from sim.masterpi_camera_profile import raw_fisheye_remap
    sys.path.insert(0, str(a.backend/'scripts'))
    from simalt_compiled_compat import apply_geometry, apply_reference
    from warp_act_core import runtime_sleep_policy
    def forbidden(*args, **kwargs): raise RuntimeError('PHYSICS_FORBIDDEN')
    mjw.step = mujoco.mj_step = forbidden
    a.output.mkdir(parents=True, exist_ok=False)
    command = read(a.run.with_suffix('.command.json'))['command']
    refs = read(Path(command[command.index('--per-world-model-references-v1')+1]))
    rows, evaluation, hashes = [], [], {}
    for world in range(14):
        raw = a.run/f'world-{world:03d}/raw'
        result, plan = read(raw/'result.json'), read(raw/'plan.json')
        xml = raw/'scene.xml'; model = mujoco.MjModel.from_xml_string(xml.read_text())
        ref = refs[digest(xml)]
        apply_geometry(model, xml, Path(ref['geometry'])); apply_reference(model, xml, Path(ref['actuator']))
        en = mujoco.mjtSleepPolicy
        model.tree_sleep_policy[:] = runtime_sleep_policy(model.tree_sleep_policy,
            auto=int(en.mjSLEEP_AUTO), auto_never=int(en.mjSLEEP_AUTO_NEVER),
            auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED), never=int(en.mjSLEEP_NEVER), allowed=int(en.mjSLEEP_ALLOWED))
        data = mujoco.MjData(model)
        gm, gd = mjw.put_model(model), mjw.put_data(model, data)
        robots = list(result['lookaround_result'])
        rc = mjw.create_render_context(model, nworld=1, cam_res=(640,480), render_rgb=True,
            render_depth=False, render_seg=False, use_textures=True, use_shadows=True,
            enabled_geom_groups=[0,1,2,3], cam_active=[r+'__robot_cam' for r in robots])
        pixels = wp.zeros((1,480,640), dtype=wp.vec3); remap = raw_fisheye_remap(640,480)
        states = np.load(a.run/f'world-{world:03d}-states.npz')
        indices = {int(t): i for i,t in enumerate(states['ticks'])}
        static = make_scene(plan).config['static_map']
        folder = a.output/f'world-{world:03d}'; folder.mkdir()
        dump(folder/'static-map.json', static)
        robot_inputs = {}
        for ci,rid in enumerate(robots):
            robot_inputs[rid] = []
            original = result['lookaround_result'][rid]
            for n,view in enumerate(original['localizer']['views']):
                tick = round(view['t']*10); k = indices[tick]
                wp.copy(gd.qpos, wp.array(states['qpos'][k:k+1], dtype=float))
                wp.copy(gd.qvel, wp.array(states['qvel'][k:k+1], dtype=float))
                mjw.kinematics(gm,gd); mjw.camlight(gm,gd); mjw.refit_bvh(gm,gd,rc); mjw.render(gm,gd,rc)
                mjw.get_rgb(rc,ci,pixels); wp.synchronize()
                rgb = np.clip(pixels.numpy()[0]*255,0,255).astype(np.uint8)
                rgb = cv2.remap(rgb,*remap,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                buffer=io.BytesIO(); Image.fromarray(rgb).save(buffer,format='JPEG',quality=82)
                path=folder/f'{rid}-{n:03d}.jpg'; path.write_bytes(buffer.getvalue())
                saved=raw/view['input_jpeg']
                # Two independent native render invocations, not OpenGL comparison.
                robot_inputs[rid].append(dict(t=view['t'],servo=view['servo'],
                    command_pose=view['command_pose'],rgb=str(path.relative_to(a.output)),
                    rgb_sha256=digest(path),recorded_rgb_sha256=digest(saved),
                    same_native_jpeg=digest(path)==digest(saved)))
                # Kinematics only, evaluation process data; never written to own inputs.
                data.qpos[:]=states['qpos'][k]; mujoco.mj_kinematics(model,data); mujoco.mj_camlight(model,data)
                body=data.body(rid+'__robot'); matrix=body.xmat.reshape(3,3)
                truth=[*body.xpos[:2].tolist(),float(np.arctan2(matrix[1,0],matrix[0,0]))]
                evaluation.append(dict(world=world,rid=rid,view=n,t=view['t'],truth_pose=truth,
                    previous_localizer_evaluation=original.get('evaluation'),
                    new_map_error_xy_m=None,new_map_error_yaw_deg=None,
                    status='unmeasured_static_map_acquisition_pending'))
            hashes[str(xml)]=digest(xml)
        rows.append(dict(world=world,seed=plan['seed'],robots=robot_inputs,static=f'world-{world:03d}/static-map.json'))
        print('rendered',world,{r:len(v) for r,v in robot_inputs.items()},flush=True)
        del rc,gm,gd,pixels
    dump(a.output/'own-inputs.json',dict(worlds=rows,source_run=str(a.run),physics_steps=0,top_inputs=0))
    dump(a.output/'eval-only.json',dict(rows=evaluation,scope='evaluation only; estimator never reads this file'))
    dump(a.output/'render-seal.json',dict(input_xml_sha256=hashes,own_inputs_sha256=digest(a.output/'own-inputs.json'),
        images={str(p.relative_to(a.output)):digest(p) for p in a.output.rglob('*.jpg')},physics_steps=0,top_renders=0))


def probe(a):
    sys.path[:0]=[str(a.owner),str(a.owner/'scripts'),str(a.adapter/'scripts')]
    os.chdir(a.owner)
    import cv2
    import numpy as np
    from PIL import Image
    from release_reloc_selfmap import ReleaseSelfmap
    cv2.setNumThreads(1)
    calibration=read(a.owner/'experiments/2026-10-16-reloc16/colour-calibration.json')
    manifest=read(a.owner/'OWNER_BYTES.json')
    for name,rec in manifest['files'].items():
        if digest(a.owner/name)!=rec['sha256']:raise ValueError('OWNER_BYTES_CHANGED:'+name)
    inputs=read(a.output/'own-inputs.json');reports=[]
    # Colour component audit only, no Hough/line features or pose evidence.
    # These are the archived zone RGB signature parameters, unchanged. They
    # do not constitute a newly qualified zone detector or acceptance gate.
    for w in inputs['worlds']:
        static=read(a.output/w['static']); rr={}
        for rid,frames in w['robots'].items():
            loc=ReleaseSelfmap(static,calibration,method=a.method);rows=[]
            for frame in frames:
                rgb=np.asarray(Image.open(a.output/frame['rgb']).convert('RGB'))
                row=loc.observe(frame['t'],rgb,frame['servo'])
                hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV).astype(float)
                h,s,v=np.moveaxis(hsv,-1,0);zone={}
                for name,region in static['regions'].items():
                    rgba=region['rgba'];rgba=np.fromstring(rgba,sep=' ') if isinstance(rgba,str) else np.asarray(rgba)
                    target=float(cv2.cvtColor(np.array([[rgba[:3]]],np.float32),cv2.COLOR_RGB2HSV)[0,0,0]/2)
                    diff=np.minimum(abs(h-target),180-abs(h-target))
                    mask=((diff<=12)&(s>=20)&(s<=150)&(v>=35)).astype(np.uint8)
                    n,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
                    zone[name]=int(sum(stats[1:,cv2.CC_STAT_AREA]>=300))
                row.update(zone_colour_components_auxiliary=zone,zone_component_scope='RGB signature only; no depth/identity/line fit',
                    native_jpeg_equal=frame['same_native_jpeg'])
                rows.append(row)
            rr[rid]=dict(rows=rows,decision=loc.decision())
        reports.append(dict(world=w['world'],seed=w['seed'],robots=rr))
        print('probed',w['world'],flush=True)
    flat=[r for w in reports for x in w['robots'].values() for r in x['rows']]
    summary=dict(schema='ugrp.warp8e.open_selfmap_inputs.v1',host='gcp3',method=a.method,
        source_run=inputs['source_run'],worlds=reports,world_n=len(reports),views=len(flat),
        camera_qualified_views=sum(r['camera_qualified'] for r in flat),
        views_with_wall_hits=sum(r['wall_hit_columns']>0 for r in flat),
        wall_hit_columns=sum(r['wall_hit_columns'] for r in flat),
        views_with_floor_features=sum((r['floor_features'] or 0)>0 for r in flat),
        floor_features=sum((r['floor_features'] or 0) for r in flat),
        lk_status=dict(Counter(r['lk']['status'] for r in flat)),
        column_reasons=dict(sum((Counter(r['column_reasons']) for r in flat),Counter())),
        native_jpeg_equal_n=sum(r['native_jpeg_equal'] for r in flat),
        map_corrections_accepted=0,offline_gate_pass=False,
        block='owner_static_map_acquisition_api_pending; loaded FK unqualified; sparse look views do not measure carry LK',
        physics_steps=0,truth_inputs=0,top_inputs=0,held_world_reads=0,
        owner_sha=manifest['mapbuild_sha'],owner_bytes_unchanged=True,
        own_inputs_sha256=digest(a.output/'own-inputs.json'))
    dump(a.output/('probe-'+a.method+'.json'),summary)
    dump(a.output/('rejection_table-'+a.method+'.json'),dict(raw=str(a.output),reproduction=sys.argv,
        stages=[dict(stage='worlds',cumulative_pass_n=len(reports),rejected_n=0),
            dict(stage='map_localized_worlds',cumulative_pass_n=0,rejected_n=len(reports))],
        reasons=[dict(category='owner_api_pending',reason=summary['block'],count=len(reports),
            blocking_object='static_wall_map_acquisition',minimum_gap_m=None,gap_status='not_measured')],
        view_counts={k:summary[k] for k in ('views','camera_qualified_views','views_with_wall_hits','views_with_floor_features')},
        constants='unchanged mapbuild virtual-scan/LK; auxiliary HSV/component constants from archived zone signature only'))
    print(json.dumps({k:v for k,v in summary.items() if k!='worlds'}))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--release-reloc-selfmap-v1',choices=['lk','rbpf'],dest='method',required=True)
    p.add_argument('--stage',choices=['render','probe'],required=True)
    for k in ('run','frozen','backend','owner','adapter','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    if socket.gethostname().split('.')[0]!='ugrp-act-l4-gcp3':raise ValueError('GCP3_ONLY')
    os.environ.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MUJOCO_GL='osmesa')
    (render if a.stage=='render' else probe)(a)


if __name__=='__main__': main()
