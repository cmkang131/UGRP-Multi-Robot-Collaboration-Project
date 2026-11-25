import hashlib
import json
from pathlib import Path
import socket
import sys
import time
import cv2

if socket.gethostname() != 'ras1':
    raise RuntimeError('ras1 only')
sys.path.insert(0,str(Path.home()/'MasterPi/tools/.ugrp_versions/strict-wall-20261014'))
import masterpi_control as c
out=Path(sys.argv[1]);out.mkdir(parents=True)
pwm=int(sys.argv[2])
if pwm not in (500,650,740):
    raise ValueError('expected configured wrist camera posture')
result=dict(stopped=False,frames=[],chassis_motion_commands=0)
try:
    with c.acquire_actuator_lease(owner='codex:wrist-tilt-front-locked'):
        motors=c.MotorTransport()
        cap=None
        try:
            c.stop_all(motors,context='tilt-before')
            pose=c.load_pose_state()
            if any(pose.get(k)!=v for k,v in {4:2320,5:1320,6:1500}.items()) or pose[3] not in (500,650,740):
                raise RuntimeError('camera posture changed')
            if pose[3]!=pwm:
                c.ServoTransport().write_servo(3,pwm,.55)
                time.sleep(.66)
            cap=cv2.VideoCapture(0,cv2.CAP_V4L2);cap.set(3,640);cap.set(4,480)
            for i in range(42):
                ok,f=cap.read()
                if not ok or f.shape!=(480,640,3): raise RuntimeError('camera unavailable')
                if i>=37:
                    ok,j=cv2.imencode('.jpg',f)
                    if not ok: raise RuntimeError('JPEG fail')
                    name=f'tilt-{i-37}.jpg'
                    blob=j.tobytes(); (out/name).write_bytes(blob)
                    result['frames'].append(dict(file=name,sha256=hashlib.sha256(blob).hexdigest()))
            result['pose']=c.load_pose_state()
        finally:
            if cap: cap.release()
            c.stop_all(motors,context='tilt-after')
            result['stopped']=True
finally:
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
