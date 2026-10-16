"""Finite-SIM default-off frontier capture on gcp5, MJWarp physics and RGB."""
import argparse
from collections import Counter,deque
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from mapbuild4_pulse import bootstrap,dump


def run(a):
    m,xml,cases,initial,controls,admissions=bootstrap(a)
    import cv2
    import numpy as np
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from simalt_physics_compare import unused_efm
    from warp5_render import Renderer
    from sim.masterpi_camera_profile import raw_fisheye_remap
    from sim.masterpi_drive_friction_v7 import DriveParameters
    from mapbuild2_capture import quaternion_heading
    from harness.e2e_rgb_vo import between
    import harness
    harness.__path__.insert(0,str(a.vision_source/'harness'))
    harness.__path__.append(str(ROOT/'harness'))
    from harness.mapbuild_motion import PulsePrediction,OPTION as MOTION
    queue=json.loads(a.queue.read_text())
    if hashlib.sha256(a.motion_calibration.read_bytes()).hexdigest()!=queue['motion_calibration_sha256']:
        raise ValueError('PINNED_MOTION_CALIBRATION_REQUIRED')
    manifest=a.vision_source/'SOURCE_FILES.json'
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=queue['vision_manifest_sha256']:
        raise ValueError('PINNED_VISION_MANIFEST_REQUIRED')
    if any(hashlib.sha256((a.vision_source/p).read_bytes()).hexdigest()!=h for p,h in json.loads(manifest.read_text()).items()):
        raise ValueError('PINNED_VISION_BYTES_REQUIRED')
    spec=importlib.util.spec_from_file_location('mapbuild_frontier',ROOT/'harness/mapbuild_frontier.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    paths=[a.vision_source/'experiments/2026-10-16-reloc16/colour-calibration.json',
           a.vision_source/'experiments/2026-10-16-warp7/paint-calibration.json']
    expected=['a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f',
              'cd4b248fb0698f513aa7a299e6257ed23409527349d67641e37a7e19122cb957']
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=h for p,h in zip(paths,expected)):
        raise ValueError('FROZEN_COLOUR_CALIBRATION_REQUIRED')
    calibration,paint=[json.loads(p.read_text()) for p in paths]
    motion=PulsePrediction(json.loads(a.motion_calibration.read_text()),option=MOTION)
    actor=mod.FrontierActor(cases[0]['pwm'],calibration,paint,motion,option=mod.OPTION)
    a.output.mkdir(parents=True,exist_ok=False);dump(a.output/'queue.json',json.loads(a.queue.read_text()))
    cv2.setNumThreads(1);wp.init();wm=mjw.put_model(m);wm.opt.tolerance.fill_(float(m.opt.tolerance))
    d=mujoco.MjData(m);d.qpos[:]=initial[0];mujoco.mj_forward(m,d)
    def fresh():
        with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=1,nconmax=128,njmax=512)
        wp.copy(wd.qpos,wp.array(initial[:1],dtype=wd.qpos.dtype))
        wp.copy(wd.ctrl,wp.array(controls[:1],dtype=wd.ctrl.dtype));return wd
    wd=fresh();mjw.step(wm,wd);wp.synchronize();wd=fresh()
    substeps=round(.1/m.opt.timestep)
    if substeps*m.opt.timestep!=.1:raise ValueError('EXACT_100MS_GRID_REQUIRED')
    with wp.ScopedCapture() as cap:
        for _ in range(substeps):mjw.step(wm,wd)
    graph=cap.graph
    rc=Renderer(m,wm,wd,[('r1','r1__robot_cam',(640,480)),('r2','r2__robot_cam',(640,480)),
        ('overview','cctv_top',(640,480))],enabled=True,texture_after_lighting=True)
    mx,my=raw_fisheye_remap(640,480);drive=DriveParameters();relay=np.zeros(4,int)
    wheel=[m.actuator('r1__wheel_'+n+'_drive').id for n in ('fl','fr','rl','rr')]
    body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    origin=None;states=[];labels=[];own=[];ring=deque(maxlen=101);error=None;active=None;t0=time.monotonic()
    try:
        for tick in range(round(a.sim_seconds*10)+1):
            t=tick/10;qs=wd.qpos.numpy()
            if np.any(wd.overflow.numpy()) or not np.isfinite(qs).all():raise RuntimeError('CAPACITY_OR_NONFINITE')
            images=rc.render();states.append(qs.copy())
            rgb=None
            for camera in ('r1','r2','overview'):
                im=np.clip(images[camera][0][0],0,255).astype(np.uint8)
                if camera!='overview':im=cv2.remap(im,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                path=a.output/f'{camera}-{tick:04d}.jpg'
                cv2.imwrite(str(path),cv2.cvtColor(im,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82])
                if camera=='r1':
                    # Actor consumes exactly the archived JPEG, as replay does.
                    rgb=cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
            event=actor.observe(rgb,t,tick)
            dump(a.output/'predicted.json',actor.export())
            own.append(dict(t=t,frame_id=tick,rgb=f'r1-{tick:04d}.jpg',servo=cases[0]['pwm'],
                sha256=hashlib.sha256((a.output/f'r1-{tick:04d}.jpg').read_bytes()).hexdigest()))
            absolute=np.r_[qs[0,adr:adr+2],quaternion_heading(qs[0,adr+3:adr+7])]
            if origin is None:origin=absolute.copy()
            labels.append(dict(t=t,frame_id=tick,pose=between(origin,absolute).tolist()))
            ring.append(dict(t=t,frame_id=tick));dump(a.output/'progress.json',dict(status='RUNNING',t=t,known=len(actor.grid.odds),commands=len(actor.commands)))
            if tick%10==0:print(t,len(actor.grid.odds),event['flow']['status'],flush=True)
            if actor.lost:break
            if tick==round(a.sim_seconds*10):break
            command=actor.command(t)
            cs=controls[:1].copy();u=np.zeros(4)
            if command is not None:
                pattern=dict(forward=[1,1,1,1],turn=[-1,1,-1,1])[command['axis']]
                u=command['value']*np.asarray(pattern)
            effective,relay=drive.command_step(u,relay);cs[0,wheel]=drive.torque_cap_nm*effective
            wp.copy(wd.ctrl,wp.array(cs,dtype=wd.ctrl.dtype));wp.capture_launch(graph)
    except BaseException as exc:
        error=repr(exc);raise
    finally:
        status='HOST_ERROR' if error else 'visual_pose_lost' if actor.lost else 'cap_end'
        dump(a.output/'own.json',dict(frames=own,physics_backend='mjwarp',render_backend='mjwarp',robot_id='r1'))
        dump(a.output/'trajectory.json',actor.events);dump(a.output/'commands.json',actor.commands)
        dump(a.output/'predicted.json',actor.export())
        # Labels are separate and never passed back to the actor.
        dump(a.output/'eval-only.json',dict(first_origin=origin.tolist() if origin is not None else None,frames=labels))
        np.savez_compressed(a.output/'eval-state.npz',qpos=np.asarray(states))
        dump(a.output/'summary.json',dict(status=status,error=error,sim_s=labels[-1]['t'] if labels else 0,
            wall_s=time.monotonic()-t0,physics_steps_per_world=max(0,len(states)-1)*substeps,
            frames=len(own),commands=len(actor.commands),known_cells=len(actor.grid.odds),
            camera='FOLDED only; HIGH remains unqualified',option=mod.OPTION,scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
            recording=dict(hz=10,terminal_ring=list(ring),bytes=sum(p.stat().st_size for p in a.output.glob('*.jpg'))),
            input_audit=dict(top_actor_reads=0,truth_feedback=0,prior_map_reads=0,cpu_physics_steps=0),
            plan_budget='finite observed grid A*, inherited node/grid limits; SIM duration only; no wall deadline'))
        qualified=[e for e in actor.events if e['flow']['status'] in ('bootstrap','measured')]
        supported=[e for e in qualified if e['wall_segments']]
        dump(a.output/'rejection_table.json',dict(raw=str(a.output),reproduction=sys.argv,stages=[
            dict(stage='requested_frames',cumulative_pass_n=round(a.sim_seconds*10)+1,rejected_n=0),
            dict(stage='recorded_frames',cumulative_pass_n=len(own),rejected_n=round(a.sim_seconds*10)+1-len(own)),
            dict(stage='visual_pose',cumulative_pass_n=len(qualified),rejected_n=len(own)-len(qualified)),
            dict(stage='supported_wall',cumulative_pass_n=len(supported),rejected_n=len(qualified)-len(supported))],
            reasons=dict(Counter(e['reason'] for e in actor.events)),rejection_fields='trajectory.json'))
        dump(a.output/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir() if p.is_file()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('renderer-source','renderer-receipt','vision-source','motion-calibration','fixture','queue','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--sim-seconds',type=float,default=12.)
    p.add_argument('--mapbuild4-frontier-v1',action='store_true');a=p.parse_args()
    if not a.mapbuild4_frontier_v1:p.error('default off: explicit --mapbuild4-frontier-v1 required')
    if a.sim_seconds<=0 or not __import__('math').isfinite(a.sim_seconds):p.error('positive finite SIM budget required')
    run(a)
