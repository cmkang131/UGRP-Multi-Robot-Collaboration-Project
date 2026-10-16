"""Opt-in GCP2 L4 issued-wheel MJWarp acquisition, four shared worlds.

Physics owns state and evaluation labels. Actor records contain only own RGB,
issued PWM/wheels and (explicit ON runs) the existing front range observation.
No CPU physics steps, camera/geometry changes, wall deadline or truth feedback.
"""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RENDERER_SHA = '5974a181a2cec9731339a6ce3aadc0464b8dddcf'
PROFILE = 'walls_floor_contrast_v5_indigo110_s80'


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quaternion_heading(q):
    """Yaw of the projected body x axis; exact quaternion rotation formula."""
    w,x,y,z=q
    return math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))


def stimulus(t):
    # Diagnostic coverage reuses v122's calibrated command magnitudes/durations;
    # it is not a success threshold. Stop tails are part of those profiles.
    for start, axis, value, duration in ((1., 'forward', .35, .10),
            (2., 'left', .35, .06), (3., 'turn', .35, .10)):
        if round(start*100) <= round(t*100) < round((start+duration)*100):
            pattern = {'forward':[1,1,1,1], 'left':[-1,1,1,-1], 'turn':[-1,1,-1,1]}[axis]
            return [value*x for x in pattern]
    return [0.]*4


def run(a):
    v3=getattr(a,'mapbuild3_v1',False)
    task='mapbuild3' if v3 else 'mapbuild2'
    expected_host='ugrp-act-l4-gcp5' if v3 else 'ugrp-act-l4-gcp2'
    if platform.system()!='Linux' or not platform.node().startswith(expected_host):
        raise ValueError('GCP2_L4_ONLY')
    q=json.loads(a.queue.read_text()); table=Path(q['rejection_table'])
    if not table.is_absolute() or not table.is_file():raise ValueError('EXISTING_ABSOLUTE_FUNNEL_REQUIRED')
    if q['toggle']!=task+'_v1' or q['enabled'] is not True:raise ValueError('EXPLICIT_CANDIDATE_REQUIRED')
    if v3 and q.get('spawn_overlap_check')!='spawn_overlap_check_v1':raise ValueError('SPAWN_CHECK_REQUIRED')
    for source, expected in ((ROOT,q['source_sha']),(a.renderer_source,RENDERER_SHA)):
        if v3 and source==a.renderer_source and (source/'.git').exists() is False:
            receipt=json.loads(a.renderer_receipt.read_text())
            if receipt['source_sha']!=expected or any(sha(source/p)!=h for p,h in receipt['files'].items()):
                raise ValueError('PINNED_RENDERER_HASH_MISMATCH')
            continue
        if v3 and source==ROOT and (source/'SOURCE_SHA').is_file():
            receipt=json.loads((source/'SOURCE_FILES.json').read_text())
            if (source/'SOURCE_SHA').read_text().strip()!=expected or any(sha(source/p)!=h for p,h in receipt.items()):
                raise ValueError('ARCHIVE_SOURCE_HASH_MISMATCH')
            continue
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()!=expected:
            raise ValueError('PINNED_SOURCE_REQUIRED')
        if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source):
            raise ValueError('CLEAN_SOURCE_REQUIRED')
    base=Path('/home/ugrp/ugrp-sim')
    leases=[json.loads(p.read_text()) for p in (base/'leases').glob('*.json')]
    if not any(p.get('task')==task for p in leases):raise ValueError('OWN_LEASE_REQUIRED')
    if sum(int(p.get('concurrency',0)) for p in leases if p.get('task')!=task)+4>40:
        raise ValueError('SHARED_WORLD_LIMIT')
    # Existing x86 persistent-storage floor (AGENTS); resource admission only.
    if os.statvfs(base).f_bavail*os.statvfs(base).f_frsize < 8*1024**3:
        raise ValueError('DISK_FLOOR_8GIB')
    available=int(next(line for line in Path('/proc/meminfo').read_text().splitlines()
        if line.startswith('MemAvailable:')).split()[1])*1024
    # Existing project x86 admission floor, separate from behavior budgets.
    if available<6*1024**3:raise ValueError('MEMORY_FLOOR_6GIB')
    a.output.mkdir(parents=True,exist_ok=False)
    dump(a.output/'queue.json',q);dump(a.output/'leases-start.json',leases)
    dump(a.output/'resources-start.json',dict(mem_available_bytes=available,load_average=list(os.getloadavg()),
        disk_free_bytes=os.statvfs(base).f_bavail*os.statvfs(base).f_frsize,shared=True,
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.total,utilization.gpu','--format=csv,noheader'],text=True)))
    dump(a.output/'RUN_META.json',dict(schema='ugrp.run_meta.v1',**{'class':'dev'},pr=556,
        branch='codex/mapbuild1',sha=q['source_sha'],batch=task))
    sys.path.insert(0,str(a.renderer_source));sys.path.insert(1,str(a.renderer_source/'scripts'))
    os.chdir(a.renderer_source)
    import cv2
    import numpy as np
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from scripts import probe_scene_tex2 as scene_tools
    from scripts.generate_scene_textures import MAPS
    from scripts.simalt_physics_compare import unused_efm
    from scripts.warp5_render import Renderer
    from scripts.warp_act_core import runtime_sleep_policy
    from sim.masterpi_drive_friction_v7 import DriveParameters
    from sim.masterpi_camera_profile import raw_fisheye_remap
    from sim.ultrasonic_range import MujocoUltrasonic
    from harness.ultrasonic_model import sensor_seed
    from harness.self_pulse_odom import PulseOdometry
    from harness.e2e_rgb_vo import between
    cv2.setNumThreads(1);wp.init()
    m,scene,hardware,xml,audit=scene_tools.build_model(MAPS[0],PROFILE)
    from sim.camera_render_quality import configure_model
    configure_model(m,'no_mip_v1')
    enum=mujoco.mjtSleepPolicy
    native=m.tree_sleep_policy.copy()
    m.tree_sleep_policy[:]=runtime_sleep_policy(native,auto=int(enum.mjSLEEP_AUTO),
        auto_never=int(enum.mjSLEEP_AUTO_NEVER),auto_allowed=int(enum.mjSLEEP_AUTO_ALLOWED),
        never=int(enum.mjSLEEP_NEVER),allowed=int(enum.mjSLEEP_ALLOWED))
    d=mujoco.MjData(m);view=scene_tools.wall_views(scene.config['static_map'])[0]
    cases=[];initial=[];ctrl=[];odoms=[]
    fixture=np.load(a.fixture/'fixture.npz') if v3 else None
    if v3:
        import sim
        sim.__path__.append(str(ROOT/'sim'))
        from sim.spawn_overlap_check import check,OPTION
        from mapbuild3_prepare import named_sets
        classifications=named_sets(m)
    for pose in ('drive','high'):
        for sensor in (('off',) if v3 else ('off','on_v1')):
            pwm,setup=scene_tools.fixture(m,d,scene,view,pose,hardware)
            if v3:
                d.qpos[:]=fixture[pose+'_qpos'];d.qvel[:]=0
                admission=check(m,d,**classifications,option=OPTION)
                dump(a.output/(pose+'-spawn-admission.json'),admission)
                if not admission['accepted']:raise ValueError('SPAWN_OVERLAP_REJECTED')
            d.ctrl[:]=0
            # Set the issued position targets from the commanded fixture, before
            # physics. Subsequent measured joints never alter any command.
            for i in range(m.nu):
                if '__servo_' in m.actuator(i).name:
                    d.ctrl[i]=d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i,0])])]
            initial.append(d.qpos.copy());ctrl.append(d.ctrl.copy())
            cases.append(dict(name=pose+'-'+sensor,pwm=pwm,sensor=sensor,setup=setup))
            odom=PulseOdometry();odom.command(dict(kind='initial_servo_command',t=0,pulses=pwm));odoms.append(odom)
    if np.any(d.eq_active) or m.opt.noslip_iterations!=10:raise ValueError('WELD_OFF_NOSLIP10_REQUIRED')
    worlds=len(cases)
    wm=mjw.put_model(m);wm.opt.tolerance.fill_(float(m.opt.tolerance))
    # Workspace sizing reuses simalt/warp_act allocation minima and rounds
    # observed import contacts up; these are not physics acceptance constants.
    ncon=1<<(max(32,int(d.ncon))-1).bit_length()
    njmax=1<<(max(256,int(d.nefc))-1).bit_length()
    if v3:
        # PR564 clean-start native peak78 contacts/345 constraints ->128/512.
        # Allocation only; overflow remains HOST_ERROR, never physics tuning.
        ncon=max(ncon,128);njmax=max(njmax,512)
    dump(a.output/'initialization.json',dict(nq=m.nq,nv=m.nv,ncon=int(d.ncon),nefc=int(d.nefc),
        capacities=dict(nconmax=ncon,njmax=njmax),timestep=float(m.opt.timestep),
        basis='warp_act_backend allocation minima and next power of two of native import counts; overflow is HOST_ERROR'))
    with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=worlds,nconmax=ncon,njmax=njmax)
    wp.copy(wd.qpos,wp.array(np.stack(initial),dtype=wd.qpos.dtype))
    wp.copy(wd.ctrl,wp.array(np.stack(ctrl),dtype=wd.ctrl.dtype))
    rc=Renderer(m,wm,wd,[('r1','r1__robot_cam',(640,480)),('r2','r2__robot_cam',(640,480)),
        ('overview','cctv_top',(640,480))],enabled=True,texture_after_lighting=True)
    mx,my=raw_fisheye_remap(640,480)
    wheel=[m.actuator('r1__wheel_'+n+'_drive').id for n in ('fl','fr','rl','rr')]
    dt=float(m.opt.timestep);substeps=round(.01/dt)
    if Fraction(str(dt))*substeps!=Fraction(1,100):raise ValueError('EXACT_10MS_COMMAND_GRID_REQUIRED')
    # Ten milliseconds preserves the 60ms side pulse; graph replay batches only
    # fixed-timestep physics, with no clock-dependent action selection.
    mjw.step(wm,wd);wp.synchronize()
    # Compile without retaining its integration as an unissued motion.
    with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=worlds,nconmax=ncon,njmax=njmax)
    wp.copy(wd.qpos,wp.array(np.stack(initial),dtype=wd.qpos.dtype))
    wp.copy(wd.ctrl,wp.array(np.stack(ctrl),dtype=wd.ctrl.dtype));rc.wd=wd
    with wp.ScopedCapture() as capture:
        for _ in range(substeps):mjw.step(wm,wd)
    graph=capture.graph;drive=DriveParameters();relay=np.zeros(4,int)
    sensor_data=mujoco.MjData(m)
    us=MujocoUltrasonic(m,sensor_data,'r1',sensor_seed(20261016,'r1'))
    own=[];labels=[];ranges=[];commands=[];states=[];ring=deque(maxlen=101);previous=[np.zeros(3) for _ in cases]
    body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    origins=None;error=None;start=time.monotonic();steps=0
    try:
        for centi in range(401):
            t=centi/100
            if centi%100==0 and centi in (100,200,300):
                axis,value,duration={100:('forward',.35,.10),200:('left',.35,.06),300:('turn',.35,.10)}[centi]
                for odom in odoms:odom.command(dict(kind='mecanum',t=t,duration_s=duration,**{axis:value}))
                commands.append(dict(t=t,axis=axis,value=value,duration_s=duration))
            if centi%10==0:
                qpos=wd.qpos.numpy();qvel=wd.qvel.numpy()
                if np.any(wd.overflow.numpy()) or not np.isfinite(qpos).all():raise RuntimeError('CAPACITY_OR_NONFINITE')
                angles=np.asarray([quaternion_heading(row[adr+3:adr+7]) for row in qpos])
                absolute=np.column_stack((qpos[:,adr:adr+2],angles))
                if origins is None:origins=absolute.copy()
                images=rc.render();tick=centi//10
                states.append(qpos.copy())
                for i,case in enumerate(cases):
                    folder=a.output/case['name'];folder.mkdir(exist_ok=True)
                    for camera in ('r1','r2','overview'):
                        rgb=np.clip(images[camera][0][i],0,255).astype(np.uint8)
                        if camera!='overview':rgb=cv2.remap(rgb,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                        path=folder/f'{camera}-{tick:04d}.jpg'
                        ok,jpeg=cv2.imencode('.jpg',cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82])
                        if not ok:raise RuntimeError('JPEG_ENCODE_FAILED')
                        path.write_bytes(jpeg.tobytes())
                        if camera=='r1':
                            cv2.imwrite(str(folder/f'r1-{tick:04d}.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
                    pred=np.asarray(odoms[i].advance(t));delta=between(previous[i],pred);previous[i]=pred.copy()
                    path=folder/f'r1-{tick:04d}.jpg'
                    own.append(dict(sequence=case['name'],robot_id='r1',frame_id=tick,t=t,
                        rgb=str(path.relative_to(a.output)),sha256=sha(path),servo={str(k):v for k,v in case['pwm'].items()},
                        command_delta=delta.tolist(),command_covariance=odoms[i].covariance.tolist()))
                    labels.append(dict(sequence=case['name'],frame_id=tick,t=t,pose=between(origins[i],absolute[i]).tolist()))
                    if case['sensor']=='on_v1':
                        # Acquisition-only CPU mj_forward evaluates the existing
                        # transducer model at the actual Warp state. No CPU step.
                        sensor_data.qpos[:]=qpos[i];sensor_data.qvel[:]=qvel[i];mujoco.mj_forward(m,sensor_data)
                        reading=us.measure(t).as_dict();ranges.append(dict(sequence=case['name'],**reading))
                ring.append(dict(t=t,frame_id=tick))
                dump(a.output/'recording-progress.json',dict(status='RUNNING',sim_t=t,own_frames=len(own),physics_steps=steps))
                print('recorded',t,flush=True)
            if centi==400:break
            u=stimulus(t);effective,relay=drive.command_step(u,relay)
            controls=np.stack(ctrl);controls[:,wheel]=drive.torque_cap_nm*effective
            wp.copy(wd.ctrl,wp.array(controls,dtype=wd.ctrl.dtype));wp.capture_launch(graph);steps+=substeps
    except BaseException as exc:
        error=dict(category='HOST_ERROR',reason=repr(exc),blocked_object='physics_recorder',minimum_gap_m=None,gap_status='not_measured')
        raise
    finally:
        # Recompute from issued history only. Never serialize cumulative pose
        # covariance as the independent uncertainty of one frame increment.
        sys.path.insert(0,str(ROOT/'scripts'))
        from mapbuild2_commands import increments
        corrected=increments(own,commands)
        own=[{**row,**corrected[row['sequence'],row['frame_id']]} for row in own]
        dump(a.output/'own.json',dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',
            physics_backend='mjwarp',scope='issued_wheel_physics',frames=own))
        dump(a.output/'eval-only.json',dict(frames=labels,map=str(MAPS[0]),map_sha256=sha(MAPS[0]),
            first_origin=None if origins is None else origins.tolist()))
        dump(a.output/'range.json',ranges);dump(a.output/'commands.json',commands)
        np.savez_compressed(a.output/'eval-state.npz',qpos=np.asarray(states))
        dump(a.output/'summary.json',dict(status='HOST_ERROR' if error else 'cap_end',source_sha=q['source_sha'],
            renderer_sha=RENDERER_SHA,scene=PROFILE,scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
            shared=True,speed_admission=False,physics_steps=steps,worlds=worlds,frames=len(own),wall_s=time.monotonic()-start,
            error=error,renderer_audit=rc.audit,sensors='drive/high x OFF only' if v3 else 'drive/high x OFF/ON; range recorded, no control fusion',
            recording=dict(hz=10,terminal_sim_s=10,retained=list(ring),bytes=sum(p.stat().st_size for p in a.output.rglob('*.jpg'))),
            camera_qualification='HIGH closed remains unknown; no claimed load or successful carry',
            capacities=dict(nconmax=ncon,njmax=njmax),input_audit=dict(top_actor_reads=0,truth_feedback=0,cpu_physics_steps=0)))
        dump(a.output/'rejection-table.json',dict(raw=str(a.output),reproduction=sys.argv,stages=[
            dict(stage='requested_own_frames',cumulative_pass_n=worlds*41,rejected_n=0),
            dict(stage='recorded_own_frames',cumulative_pass_n=len(own),rejected_n=worlds*41-len(own))],reasons=[] if error is None else [error]))
        dump(a.output/'recording-progress.json',dict(status='HOST_ERROR' if error else 'cap_end',
            own_frames=len(own),physics_steps=steps))
        dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):sha(p) for p in a.output.rglob('*') if p.is_file()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue',type=Path,required=True);p.add_argument('--renderer-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:p.error('explicit --execute required; default off')
    try:run(a)
    except BaseException as exc:
        if a.output.is_dir() and not (a.output/'summary.json').exists():
            dump(a.output/'summary.json',dict(status='HOST_ERROR',frames=0,error=dict(category='HOST_ERROR',
                reason=repr(exc),blocked_object='recorder_initialization',minimum_gap_m=None,gap_status='not_measured')))
        raise


if __name__=='__main__':main()
