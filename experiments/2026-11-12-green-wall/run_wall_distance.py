"""Fixed-head physical wall-normal motion, continuous own RGB and design-cm map.

Only chassis motor writes. No servo writes. RGB verifies which action actually
changes the green-wall gap. A motor command is never converted into distance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sys
import threading
import time
import cv2
import numpy as np
from green_wall_mapper import Mapper,POSE,RUNTIME
from wall_distance import design_scale,distance_from_contact,infer_wall_actions


def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--floor-profile',type=Path,required=True)
    parser.add_argument('--move',action='store_true')
    parser.add_argument('--excursion-cm',type=float,default=5.,help='design-scale target gap increase; not measured ground truth')
    parser.add_argument('--output',type=Path,default=Path.home()/'wall-distance-runs')
    a=parser.parse_args()
    if not 0<a.excursion_cm<=8:raise ValueError('finite DEV excursion must be0..8 design cm')
    if socket.gethostname()!='ras1':raise ValueError('ras1 only')
    sys.path.insert(0,str(RUNTIME));import masterpi_control as c
    profile=json.loads(a.floor_profile.read_text());mapper=Mapper(profile);scale=design_scale()
    root=a.output/time.strftime('%Y%m%d-%H%M%S');root.mkdir(parents=True,exist_ok=False)
    lease=c.acquire_actuator_lease(owner='codex:fixed-head-wall-distance')
    motors=c.MotorTransport();c._active_motor_transport=motors
    stop=threading.Event();condition=threading.Condition();latest=[];stream_errors=[]
    frames=[];checkpoints=[];commands=[];errors=[];cap=None;worker=None;stopped=False
    start=time.monotonic();initial_pose=c.load_pose_state();actions=None
    def interrupt(*_):raise RuntimeError('signal/watchdog')
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,interrupt)
    signal.alarm(120)
    def capture():
        last=-1.
        try:
            while not stop.is_set():
                ok,raw=cap.read();now=time.monotonic()
                if not ok:raise RuntimeError('camera read failed')
                if now-last<1/12:continue
                last=now;name='frame-%05d.jpg'%len(frames)
                ok,jpeg=cv2.imencode('.jpg',raw,[cv2.IMWRITE_JPEG_QUALITY,90])
                if not ok:raise RuntimeError('JPEG encoder failed')
                raw_bytes=jpeg.tobytes();(root/name).write_bytes(raw_bytes)
                row=dict(image=name,t=now-start,sha256=hashlib.sha256(raw_bytes).hexdigest())
                frames.append(row)
                with condition:
                    latest[:]=[row,cv2.imdecode(jpeg,cv2.IMREAD_COLOR)];condition.notify_all()
                if len(frames)>=600:raise RuntimeError('finite600-frame recording budget')
        except BaseException as e:
            stream_errors.append(repr(e));stop.set()
            with condition:condition.notify_all()
    def observe(after,phase):
        deadline=time.monotonic()+5
        with condition:
            while not latest or latest[0]['t']<after-start:
                if stream_errors:raise RuntimeError(str(stream_errors))
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('fresh post-stop image missing')
                condition.wait(min(.3,remaining))
            row,raw=latest[0].copy(),latest[1].copy()
        overlay,info=mapper.update(raw)
        if mapper.lost or info['contact_pixels']<96:raise RuntimeError('floor/contact lost: '+str(info))
        if checkpoints:
            pose=info.get('pose')
            if pose is None:raise RuntimeError('relative pose rejected: '+info.get('pose_status','unknown'))
            camera=np.array([pose['camera_x'],pose['camera_y']])
            yaw=pose['yaw_deg']
        else:camera=np.zeros(2);yaw=0.
        contact=np.asarray(mapper.views[-1]['boundary_points'])
        distance=distance_from_contact(contact,camera,scale['camera_height_cm'])
        cp=dict(t=row['t'],image=row['image'],phase=phase,tracking=info,
                camera_xy_cm=(camera*scale['camera_height_cm']).tolist(),yaw_deg=yaw,
                commanded_arm_pose=c.load_pose_state(),**distance)
        if cp['commanded_arm_pose']!=initial_pose:raise RuntimeError('head commands changed')
        checkpoints.append(cp);cv2.imwrite(str(root/('checkpoint-%02d.jpg'%(len(checkpoints)-1))),overlay)
        print(json.dumps(dict(checkpoint=len(checkpoints),phase=phase,gap_cm=cp['wall_gap_cm'],
                              camera_xy_cm=cp['camera_xy_cm'],inliers=info.get('inliers',0))),flush=True)
        return cp
    def pulse(action,phase,duration=.06):
        if stream_errors:raise RuntimeError(str(stream_errors))
        if c.load_pose_state()!=initial_pose:raise RuntimeError('head changed before motion')
        command=dict(action=action,speed=65 if action in ('left','right') else 35,
                     duration_s=duration,phase=phase,t_start=time.monotonic()-start)
        commands.append(command)
        c._run_motion(motors,c.drive_speeds(action,command['speed']),duration)
        command['t_stop']=time.monotonic()-start
        return observe(time.monotonic()+.2,phase)
    try:
        c.stop_all(motors,context='fixed-head-start')
        if initial_pose!=POSE:raise RuntimeError('fixed search arm pose required')
        # Reuse the original12-read/two-within500mV preflight; no invalid value
        # is promoted to a battery estimate (one-shot reads failed previously).
        samples=[];probe=None
        for _ in range(12):
            try:
                candidate=c.probe_hardware()
                if any(abs(candidate['battery_mv']-v['battery_mv'])<=500 for v in samples):probe=candidate;break
                samples.append(candidate)
            except c.ControlError:pass
            time.sleep(.03)
        if probe is None:raise RuntimeError('no two consistent battery probes')
        cap=cv2.VideoCapture(0,cv2.CAP_V4L2);cap.set(3,640);cap.set(4,480)
        if not cap.isOpened():raise RuntimeError('camera unavailable')
        for _ in range(45):
            ok,_=cap.read()
            if not ok:raise RuntimeError('camera warmup failed')
        worker=threading.Thread(target=capture,daemon=True);worker.start()
        before=observe(time.monotonic(),'initial')
        if a.move:
            # Prior RGB suggested left increases the gap. Verify on this run,
            # then use the OBSERVED action polarity, never its label as truth.
            first=pulse('left','direction_probe')
            actions=infer_wall_actions(before,first,'left')
            print('ACTIONS '+json.dumps(actions),flush=True)
            target=before['wall_gap_cm']+a.excursion_cm
            for _ in range(5):
                if checkpoints[-1]['wall_gap_cm']>=target:break
                old=checkpoints[-1];new=pulse(actions['away'],'away')
                if new['wall_gap_cm']<=old['wall_gap_cm']:raise RuntimeError('away action did not increase observed gap')
            away_gap=checkpoints[-1]['wall_gap_cm']
            for _ in range(8):
                remaining=checkpoints[-1]['wall_gap_cm']-before['wall_gap_cm']
                if remaining<=.4:break
                step=abs(actions['observed_gap_change_cm'])
                duration=max(.02,min(.06,.06*remaining/max(step,.2)*.7))
                old=checkpoints[-1];new=pulse(actions['toward'],'toward',duration)
                if new['wall_gap_cm']>=old['wall_gap_cm']:raise RuntimeError('toward action did not decrease observed gap')
            if away_gap<=before['wall_gap_cm']+.2:raise RuntimeError('no resolved wall-normal excursion')
        time.sleep(.5)
    except BaseException as e:
        errors.append(repr(e));print('ERROR '+repr(e),flush=True)
    finally:
        signal.alarm(0)
        try:c.stop_all(motors,context='fixed-head-final');stopped=True
        finally:
            stop.set()
            if worker:worker.join(timeout=4)
            if cap:cap.release()
            lease.close()
        errors.extend(stream_errors)
        (root/'frames.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in frames))
        result=dict(scale=scale,checkpoints=checkpoints,commands=commands,actions=actions,
                    frames=len(frames),errors=errors,stopped=stopped,
                    initial_pose=initial_pose,final_pose=c.load_pose_state(),servo_writes=0,
                    floor_profile=profile,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    metric_accuracy_verified=False,raw_location=str(root))
        (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        (root/'RUN_META.json').write_text(json.dumps(dict(**{'class':'dev'},sha=os.environ.get('UGRP_SOURCE_SHA'),branch='codex/strict-wall-motion-ras1',pr=None,batch=root.name),indent=2)+'\n')
        print('OUTPUT '+str(root),flush=True)
    return bool(errors)


if __name__=='__main__':raise SystemExit(run())
