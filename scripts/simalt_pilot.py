"""Opt-in, Linux-only simalt1 trace/render diagnostic; no policy or training.

The frozen ACT11 command whitelist is replayed, never its visible_target or
student_context truth. This measures trace completion, not teacher success.
All acceptance numbers belong to the user's 2026-10-15 exploratory proposal;
no pixel tolerance or relaxed task-success threshold is introduced here.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

TEACHER_SHA = '6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def trace_rows(path):
    rows = [json.loads(x) for x in Path(path).read_text().splitlines()]
    for i, row in enumerate(rows):
        if set(row) != {'t', 'phase', 'command'}:
            raise ValueError('trace may contain issued commands and phase metadata only')
        if i and abs(row['t'] - rows[i-1]['t'] - .1) > 1e-6:
            raise ValueError('10 Hz contiguous command trace required')
    if not rows:
        raise ValueError('empty trace')
    return rows


def runtime(root, backend):
    if platform.system() != 'Linux':
        raise RuntimeError('Mac physics/render forbidden')
    if backend not in ('legacy', 'egl_l4_v1'):
        raise ValueError('unknown render backend')
    # Legacy leaves the caller's historical MUJOCO_GL untouched.
    if backend == 'egl_l4_v1':
        os.environ['MUJOCO_GL'] = 'egl'
    sys.path.insert(0, str(Path(root).resolve()))
    import mujoco
    from scripts.grasp_act_host import identity
    host = identity('gcp1')  # historical API name selects GCP metadata, not instance
    expected = ('ugrp-act-l4-pilot1', 'g2-standard-4') if backend == 'egl_l4_v1' else ('ugrp-sim-gcp1', 'n4-highcpu-64')
    if (host['instance'], host['machine_type']) != expected:
        raise ValueError(f'wrong actual host: {host}')
    if mujoco.__version__ != '3.12.0':
        raise ValueError('C evaluation environment must remain mujoco==3.12.0')
    return host


class Timers:
    def __init__(self):
        self.seconds = defaultdict(float)
        self.counts = Counter()
        self.original = []

    def wrap(self, obj, key, label):
        original = getattr(obj, key)
        self.original.append((obj, key, original))
        def measured(*args, **kwargs):
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.seconds[label] += time.perf_counter() - start
                self.counts[label] += 1
        setattr(obj, key, measured)

    def record(self):
        return {'seconds': dict(self.seconds), 'calls': dict(self.counts)}

    def close(self):
        for obj, key, original in reversed(self.original):
            setattr(obj, key, original)


def world_for(plan, render):
    from sim.grasp_act_scene import make_scene
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.s2_realism_camera_binding import bind_camera
    scene = make_scene({**plan, 'end_color_scene': 'off'})
    os.environ['UGRP_SIM_OBSERVER_WIDTH'] = '320'
    os.environ['UGRP_SIM_OBSERVER_HEIGHT'] = '240'
    world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640,
                        height=480, render=render, warehouse_layout=scene.engine_layout,
                        warehouse_cargo_ids=None, roller_collision='mesh', idle_robot_contacts='off')
    for c in world.controllers.values():
        bind_camera(c)
    scene.setup(world)
    import numpy as np
    if world.model.opt.noslip_iterations != 10 or np.any(world.data.eq_active):
        world.close()
        raise RuntimeError('noslip=10 and weld OFF required')
    return world, scene


def gl_info(world):
    def query():
        from OpenGL import GL
        return {k: GL.glGetString(v).decode() for k, v in (
            ('vendor', GL.GL_VENDOR), ('renderer', GL.GL_RENDERER), ('version', GL.GL_VERSION))}
    return world._render_executor.submit(query).result(timeout=30)


def replay(a):
    host = runtime(a.source, a.render_backend)
    import cv2
    import mujoco
    import numpy as np
    from PIL import Image
    from sim.grasp_act_port import DutyActPort
    from scripts.run_grasp_act_teacher import apply
    plan = json.loads(a.plan.read_text())
    rows = trace_rows(a.trace)
    a.out.mkdir(parents=True, exist_ok=False)
    timer = Timers()
    # Renderer.render combines draw/readback; split native calls without changing pixels.
    for obj, key, label in ((mujoco, 'mj_step', 'physics'),
                            (mujoco, 'mjv_updateScene', 'scene_update'),
                            (mujoco, 'mjr_render', 'render'),
                            (mujoco, 'mjr_readPixels', 'readback'),
                            (cv2, 'remap', 'remap'), (Image.Image, 'save', 'JPEG')):
        timer.wrap(obj, key, label)
    world = None
    states, phase_rows, recent = [], [], deque(maxlen=100)
    report = dict(status='running', engine='mujoco-3.12.0', renderer=a.render_backend,
        host=host, source_teacher_sha=TEACHER_SHA, sha=a.sha, attempted=1, completed=0,
        failure=0, HOST_ERROR=0, training=False, live_teacher=False,
        scope='issued-command trace completion; no task success claim', config_hash=digest(a.plan),
        trace_sha256=digest(a.trace), rejection_table=str(a.out/'rejection_table.json'))
    start = time.perf_counter()
    try:
        reset_start = time.perf_counter()
        world, scene = world_for(plan, True)
        report['reset_s'] = time.perf_counter()-reset_start
        report['gl'] = gl_info(world)
        if a.render_backend == 'egl_l4_v1' and 'NVIDIA' not in report['gl']['vendor']:
            raise RuntimeError('EGL vendor is not NVIDIA')
        (a.out/'scene.xml').write_text(world.scene_xml)
        write(a.out/'scene.json', scene.manifest)
        report['scene_sha256'] = digest(a.out/'scene.xml')
        m, d = world.model, world.data
        report['physics_config'] = {k: float(getattr(m.opt,k)) for k in ('timestep','iterations','ls_iterations','noslip_iterations','solver','integrator','cone')}
        report['friction_sha256'] = hashlib.sha256(m.geom_friction.tobytes()).hexdigest()
        port = DutyActPort(world, plan['robot_id'], allow_reverse=True, allow_mecanum=True)
        rid = plan['robot_id']
        previous = {'pwm': {str(s):int(v) for s,v in port._servo_pulses.items()}}
        origin = float(d.time)
        report['origin_sim_s'] = origin
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.zeros(mujoco.mj_stateSize(m,spec))
        bid = m.body(scene.config['setup_only']['objects'][plan['item_id']]['body_name']).id
        gid = np.flatnonzero(m.geom_bodyid == bid).tolist()
        cpu_start = time.process_time()
        loop_start = time.perf_counter()
        for i, row in enumerate(rows):
            if a.cap_s is not None and i*.1 >= a.cap_s:
                report['cap_end'] = True
                break
            now = float(d.time)
            # Sync camera exactly as the existing owned-camera capture path.
            jpg = world.render_jpeg(robot_id=rid, camera='robot_cam')
            recent.append((i, jpg))  # recording-only last 10 SIM seconds at 10 Hz
            world.controllers[rid]._sync_real_camera_mount()
            mujoco.mj_getState(m,d,state,spec)
            states.append(state.copy())
            cid = m.camera(rid+'__robot_cam').id
            phase_rows.append({'index':i,'t':now,'phase':row['phase'],
                'camera_pos':d.cam_xpos[cid].tolist(),'camera_rot':d.cam_xmat[cid].tolist(),
                'cargo_pos_eval_only':d.xpos[bid].tolist(),'ncon_eval_only':int(d.ncon)})
            command = {**row['command'], 't':now}
            apply(port, command, now, previous)
            previous = command
            target = origin+(i+1)*.1
            while float(d.time) < target-1e-8:
                port.tick(float(d.time));world._physics_step_for(world.robot(rid))
            if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all():
                raise RuntimeError('nonfinite state')
            if np.any(d.eq_active):
                raise RuntimeError('WELD_ACTIVE')
            if i == 299:
                report['first30'] = {'wall_s':time.perf_counter()-loop_start,'sim_s':30.,
                    'wall_per_sim':(time.perf_counter()-loop_start)/30.,'timers':timer.record()}
                write(a.out/'progress.json',report['first30'])
        sim_s = len(states)*.1
        report.update(status='cap_end' if len(states)<len(rows) else 'complete',
            completed=int(len(states)==len(rows)), cap_end=len(states)<len(rows),
            sim_s=sim_s, loop_wall_s=time.perf_counter()-loop_start,
            cpu_s=time.process_time()-cpu_start, wall_s=time.perf_counter()-start,
            timers=timer.record(), phase_counts=dict(Counter(r['phase'] for r in phase_rows)),
            final_base_eval_only=world.robot(rid).base_xyz().tolist(),
            final_cargo_eval_only=d.xpos[bid].tolist())
        if a.snapshots:
            np.savez_compressed(a.out/'states.npz',states=np.asarray(states),spec=int(spec))
            write(a.out/'state-index.json',{'rows':phase_rows,'target_geoms':gid,'camera':rid+'__robot_cam'})
    except BaseException as error:
        report.update(status='HOST_ERROR',HOST_ERROR=1,error_type=type(error).__name__,error=str(error))
        raise
    finally:
        # Persist 10 Hz buffer for both terminal failure and completed diagnostic,
        # separate from training cameras; cap is contractual 10s x 10Hz, not control.
        folder = a.out/'failure-rgb-buffer';folder.mkdir()
        for i, jpg in recent:
            (folder/f'{i:06d}.jpg').write_bytes(jpg)
        report['failure_rgb_buffer']={'hz':10,'max_sim_s':10,'frames':len(recent),
            'bytes':sum(p.stat().st_size for p in folder.iterdir()),'recording_only':True}
        if world:world.close()
        timer.close()
        write(a.out/'rejection_table.json',{'funnel':[{'gate':'trace_input','passed':1,'rejected':0},
            {'gate':'trace_completed','passed':report['completed'],'rejected':1-report['completed']}],
            'rejections':[] if report['completed'] else [{'category':report.get('status'),
            'reason':report.get('error','SIM cap reached'),'blocking_object':'not_applicable',
            'minimum_gap_m':None,'minimum_gap_status':'not_a_geometric_rejection'}],
            'raw_path':str(a.out),'reproduce':sys.argv})
        report['raw_paths']=[str(a.out)]
        report['sha256']={str(p.relative_to(a.out)):digest(p) for p in a.out.rglob('*') if p.is_file() and p.name!='result.json'}
        write(a.out/'result.json',report)
    return report


def snapshots(a):
    host = runtime(a.source,a.render_backend)
    import cv2
    import mujoco
    import numpy as np
    plan=json.loads(a.plan.read_text()); index=json.loads((a.states/'state-index.json').read_text())
    data=np.load(a.states/'states.npz'); values=data['states'];spec=int(data['spec'])
    # Five deterministic snapshots per motion stratum, 30 total as user requested.
    strata={'approach':['approach'],'align':['align'],'grasp':['descent','close'],
            'held':['lift','hold','verify_lift'],'release':['lower','open'],
            'lookback_occlusion_candidate':['lookback','lookaround','backoff']}
    picks=[]
    for name, phases in strata.items():
        ids=[r['index'] for r in index['rows'] if r['phase'] in phases]
        if len(ids)<5:raise ValueError('insufficient snapshot stratum: '+name)
        picks.extend((name,int(ids[k])) for k in np.linspace(0,len(ids)-1,5).round().astype(int))
    if a.selection:
        picks=[(r['stratum'],r['index']) for r in json.loads(a.selection.read_text())['selection']]
        if len(picks)!=30 or len({i for _,i in picks})!=30:
            raise ValueError('30 unique audited snapshot states required')
    a.out.mkdir(parents=True,exist_ok=False)
    world, scene=world_for(plan,True);m,d=world.model,world.data
    results=[]
    try:
        for n,(stratum,i) in enumerate(picks):
            mujoco.mj_setState(m,d,values[i],spec);mujoco.mj_forward(m,d)
            def render():
                ctrl=world.controllers[plan['robot_id']]
                # Snapshot camera uses immutable stored SE3; no issued servo clock is reconstructed.
                cid=m.camera(index['camera']).id
                d.cam_xpos[cid]=index['rows'][i]['camera_pos'];d.cam_xmat[cid]=index['rows'][i]['camera_rot']
                r=world.renderer;r.update_scene(d,camera=index['camera'],scene_option=ctrl._robot_sensor_scene_option)
                ideal=r.render().copy();mx,my=ctrl._robot_fisheye_map
                rgb=cv2.remap(ideal,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                r.enable_segmentation_rendering()
                try:
                    r.update_scene(d,camera=index['camera'],scene_option=ctrl._robot_sensor_scene_option)
                    seg=r.render().copy()
                finally:r.disable_segmentation_rendering()
                mask=np.isin(seg[:,:,0],index['target_geoms'])&(seg[:,:,1]==int(mujoco.mjtObj.mjOBJ_GEOM))
                mask=cv2.remap(mask.astype(np.uint8),mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT)
                return rgb,mask
            rgb,mask=world._render_executor.submit(render).result(timeout=30)
            np.savez_compressed(a.out/f'{n:02d}.npz',rgb=rgb,mask=mask,
                camera_pos=d.cam_xpos[m.camera(index['camera']).id],camera_rot=d.cam_xmat[m.camera(index['camera']).id])
            cv2.imwrite(str(a.out/f'{n:02d}.jpg'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            ys,xs=np.nonzero(mask)
            results.append({'n':n,'state_index':i,'stratum':stratum,'phase':index['rows'][i]['phase'],
                'mask_pixels':int(mask.sum()),'mask_bbox':None if not len(xs) else [int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())],
                'edge_pixels':int(mask[0].sum()+mask[-1].sum()+mask[:,0].sum()+mask[:,-1].sum()),
                'black_pixels':int(np.all(rgb==0,axis=2).sum())})
        from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
        write(a.out/'result.json',{'host':host,'gl':gl_info(world),'snapshots':results,
            'K':scaled_camera_matrix(640,480).tolist(),'D':list(CAMERA_FISHEYE_D),
            'source_states_sha256':digest(a.states/'states.npz'),'scene_sha256':hashlib.sha256(world.scene_xml.encode()).hexdigest(),
            'sha256':{p.name:digest(p) for p in a.out.iterdir() if p.is_file()}})
    finally:world.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('replay','snapshots'))
    p.add_argument('--source',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--trace',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--render-backend',choices=('legacy','egl_l4_v1'),default='legacy')
    p.add_argument('--egl-l4-v1',action='store_true',help='explicit off-by-default admission')
    p.add_argument('--sha',required=True);p.add_argument('--cap-s',type=float)
    p.add_argument('--snapshots',action='store_true');p.add_argument('--states',type=Path)
    p.add_argument('--selection',type=Path)
    a=p.parse_args()
    if a.render_backend=='egl_l4_v1' and not a.egl_l4_v1:p.error('egl_l4_v1 is OFF by default')
    try:
        if a.mode=='replay':replay(a)
        else:snapshots(a)
    except Exception as error:
        if not (a.out/'result.json').exists():
            write(a.out/'result.json', {'status':'HOST_ERROR','attempted':1,'completed':0,
                'failure':0,'HOST_ERROR':1,'error_type':type(error).__name__,'error':str(error),
                'stage':'preflight','sha':a.sha,'raw_paths':[str(a.out)]})
        raise


if __name__=='__main__':main()
