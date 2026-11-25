"""Ras1 camera-only frontal sweep using the installed MasterPi driver."""
import hashlib
import json
from pathlib import Path
import signal
import socket
import sys
import time

import cv2


def interrupted(*_):
    raise RuntimeError('front sweep interrupted')


def sweep(out, pans):
    if socket.gethostname() != 'ras1':
        raise RuntimeError('expected ras1')
    sys.path.insert(0, str(Path.home() / 'MasterPi/tools/.ugrp_versions/strict-wall-20261014'))
    import masterpi_control as control
    out.mkdir(parents=True, exist_ok=False)
    result = dict(robot='ras1', sweep=[], chassis_motion_commands=0, stopped=False)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
        signal.signal(sig, interrupted)
    signal.alarm(34)
    cap = None
    try:
        with control.acquire_actuator_lease(owner='codex:ras1-front-door-survey'):
            motors = control.MotorTransport()
            camera = control.ServoTransport()
            try:
                control.stop_all(motors, context='front-survey-start')
                cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
                cap.set(3, 640)
                cap.set(4, 480)
                for _ in range(18):
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError('camera not responding')
                for joint, pwm in ((6, 1500), (5, 1320), (4, 2320), (3, 740)):
                    if control.load_pose_state().get(joint) != pwm and (joint != 6 or not pans):
                        camera.write_servo(joint, pwm, .65)
                        time.sleep(.72)
                targets = [(f'pan-{pan}', pan) for pan in pans]
                if not targets:
                    targets = [('center', 1500), ('pan-1200', 1200), ('pan-1800', 1800), ('center-end', 1500)]
                for label, pan in targets:
                    if control.load_pose_state().get(6) != pan:
                        camera.write_servo(6, pan, .6)
                        time.sleep(.7)
                    for i in range(10):
                        ok, frame = cap.read()
                        if not ok or frame.shape != (480, 640, 3):
                            raise RuntimeError('camera frame not available')
                        if i >= 7:
                            name = f'{label}-{i-7}.jpg'
                            ok, jpg = cv2.imencode('.jpg', frame)
                            if not ok:
                                raise RuntimeError('JPEG encoding failed')
                            data = jpg.tobytes()
                            (out / name).write_bytes(data)
                            result['sweep'].append(dict(name=name, label=label, pose=control.load_pose_state(),
                                                        sha256=hashlib.sha256(data).hexdigest()))
            finally:
                control.stop_all(motors, context='front-survey-final')
                result['stopped'] = True
    except BaseException as error:
        result['error'] = str(error)
    finally:
        if cap:
            cap.release()
        signal.alarm(0)
        (out / 'survey.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k,v in result.items() if k != 'sweep'}))
    return bool(result.get('error'))


if __name__ == '__main__':
    pans = [int(value) for value in sys.argv[2:]]
    if len(pans) > 4 or any(not 850 <= value <= 2150 for value in pans):
        raise ValueError('pan outside frontal survey range')
    raise SystemExit(sweep(Path(sys.argv[1]), pans))
