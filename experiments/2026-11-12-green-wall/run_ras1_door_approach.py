"""Align ras1 with a visible doorway and stop on the near side."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import signal
import socket
import sys
import time

import cv2
import numpy as np

from ras1_door_observation import CameraProjection, geometry

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'harness'))
from place_memory_v1 import obstacle_points

# The physical ras1 wheel axes were observed from its images. These names are
# the legacy driver's actions, not the chassis translation directions.
AXES = {
    'right': (1., 0., 65, .55),
    'left': (-1., 0., 65, .55),
    'forward': (0., 1., 35, .30),
    'backward': (0., -1., 35, .30),
}
HEADING_TOLERANCE_DEG = 7.
LATERAL_TOLERANCE_M = .035
FRONT_M = .095   # axle midpoint to front plate in MasterPi drawing
HALF_WIDTH_M = .081
MARGIN_M = .028


def interrupted(*_):
    raise RuntimeError('run interrupted')


def approach_fields(door):
    normal = np.asarray(door['toward'])
    center = np.asarray(door['center'])
    return {
        'heading_deg': math.degrees(math.atan2(normal[1], normal[0])),
        'lateral_m': float(np.array([-normal[1], normal[0]]) @ center),
        'distance_m': door['wall_plane_m'],
    }


def in_view(projection, points):
    pixels = projection.ground_pixels(points)
    if pixels is None:
        return False
    if projection.use_raw:
        rays = (np.column_stack((pixels, np.ones(len(pixels)))) @ np.linalg.inv(projection.K).T)[:, :2]
        pixels = cv2.fisheye.distortPoints(rays[:, None, :], projection.K, projection.D)[:, 0]
    return bool(np.all(pixels[:, 0] > 15) and np.all(pixels[:, 0] < 626) and np.all(pixels[:, 1] > 8) and np.all(pixels[:, 1] < 474))


def choose_step(door, projection, standoff):
    state = approach_fields(door)
    yaw, distance, lateral = state['heading_deg'], state['distance_m'], state['lateral_m']
    normal = np.asarray(door['toward'])
    center = np.asarray(door['center'])
    jambs = np.asarray(door['jambs'])
    footprint = normal[0] * FRONT_M + abs(normal[1]) * HALF_WIDTH_M
    if normal[0] < .45 or distance < footprint + .010 or distance > .85:
        raise ValueError('door outside the pre-threshold approach envelope')
    if abs(yaw) <= HEADING_TOLERANCE_DEG and abs(lateral) <= LATERAL_TOLERANCE_M and distance <= standoff + .010:
        return None

    if abs(yaw) > HEADING_TOLERANCE_DEG and distance > .17:
        turn = 'rotate-left' if yaw > 0 else 'rotate-right'
        duration = min(.25, max(.08, (abs(yaw) - 3.) / 108.))
        while duration >= .075:
            angle = math.copysign(math.radians(108. * duration), yaw)
            c, s = math.cos(angle), math.sin(angle)
            if in_view(projection, jambs @ np.array([[c, -s], [s, c]])):
                return turn, 35, duration, np.zeros(2)
            duration -= .02

    target = center - max(standoff, footprint + MARGIN_M) * normal
    order = ('forward', 'backward', 'right', 'left')
    moves = []
    for action in order:
        x, y, speed, upper_speed = AXES[action]
        unit = np.array([x, y])
        remaining = float(target @ unit)
        if remaining <= .012:
            continue
        if action == 'right' and abs(yaw) <= HEADING_TOLERANCE_DEG and abs(lateral) > LATERAL_TOLERANCE_M:
            continue
        cap = .21 if x else .32
        duration = min(cap, max(.045 if x else .085, (remaining - .004) / upper_speed))
        while duration >= (.042 if x else .07):
            bound = upper_speed * duration * unit
            if distance - (normal @ bound) >= footprint + MARGIN_M and in_view(projection, jambs - bound):
                moves.append((np.linalg.norm(target - bound), action, speed, duration, bound))
                break
            duration -= .012
    if not moves:
        raise ValueError('no visible bounded step toward the pre-door target')
    _, action, speed, duration, bound = min(moves, key=lambda row: row[0])
    return action, speed, duration, bound


def blocked(door, obstacles, action, bound):
    normal = np.asarray(door['toward'])
    for point in map(np.asarray, obstacles):
        if point @ normal >= door['wall_plane_m'] - .035:
            continue
        if action.startswith('rotate'):
            if np.linalg.norm(point) < .17:
                return True
            continue
        if bound @ bound > 0.:
            u = np.clip(float((point @ bound) / (bound @ bound)), 0., 1.)
            if np.linalg.norm(point - u * bound) < .125:
                return True
    return False


def run(args):
    if socket.gethostname() != 'ras1':
        raise ValueError('ras1 only')
    if not .125 <= args.stop_distance_cm / 100 <= .65:
        raise ValueError('expected a pre-threshold stop distance between 12.5 and 65 cm')
    sys.path.insert(0, str(args.runtime))
    import masterpi_control as control

    profile = json.loads(args.lens.read_text())
    path = args.output
    path.mkdir(parents=True, exist_ok=False)
    result = dict(status='hold', stopped=False, commands=[], observations=[], metric_accuracy_verified=False)
    started = time.monotonic()
    cap = None
    standoff = args.stop_distance_cm / 100
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGALRM):
        signal.signal(sig, interrupted)
    signal.alarm(66)

    def observe(label, frames):
        pose = control.load_pose_state()
        if any(pose.get(j) != pwm for j, pwm in ((4,2320),(5,1320),(6,1500))) or pose.get(3) not in (500,650,740):
            raise ValueError('expected fixed forward camera at a supported wrist tilt')
        projection = CameraProjection(profile, pose)
        blobs, files = [], []
        for idx in range(frames):
            ok, image = cap.read()
            if not ok or image.shape != (480,640,3):
                raise RuntimeError('camera read failed')
            if idx < frames - 5:
                continue
            ok,jpg = cv2.imencode('.jpg',image)
            if not ok:
                raise RuntimeError('cannot encode camera JPEG')
            data = jpg.tobytes()
            filename = f'{label}-{len(blobs)}.jpg'
            (path / filename).write_bytes(data)
            blobs.append(data)
            files.append(dict(file=filename,sha256=hashlib.sha256(data).hexdigest()))
        if control.load_pose_state() != pose:
            raise RuntimeError('camera posture changed')
        door = geometry(blobs,projection)
        entry = dict(label=label,pose=pose,frames=files,t=time.monotonic()-started,**approach_fields(door),**door)
        result['observations'].append(entry)
        print(f'{label}: heading={entry["heading_deg"]:+.1f} lateral={entry["lateral_m"]:+.3f} distance={entry["distance_m"]:.3f}',flush=True)
        return entry, projection, obstacle_points(blobs[-1],pose,projection)

    def settle(label, frames=13):
        try:
            return observe(label,frames)
        except ValueError:
            time.sleep(.38)
            return observe(label+'-retry',19)

    try:
        with control.acquire_actuator_lease(owner='ras1-front-camera-door-approach'):
            motors = control.MotorTransport()
            try:
                control.stop_all(motors,context='door-approach-start')
                cap = cv2.VideoCapture(0,cv2.CAP_V4L2)
                cap.set(3,640)
                cap.set(4,480)
                current, projection, obstacles = settle('initial',42)
                if not args.move:
                    result['status']='observed'
                else:
                    for step in range(14):
                        move = choose_step(current,projection,standoff)
                        if move is None:
                            result['status']='in_front_of_door'
                            break
                        action,speed,duration,bound = move
                        if blocked(current,obstacles,action,bound):
                            raise ValueError('observed obstruction along next movement')
                        if control.load_pose_state() != current['pose']:
                            raise RuntimeError('camera posture changed before movement')
                        command = dict(action=action,speed=speed,duration_s=duration,t=time.monotonic()-started)
                        result['commands'].append(command)
                        control._run_motion(motors,control.drive_speeds(action,speed),duration)
                        command['t_stopped']=time.monotonic()-started
                        time.sleep(.26)
                        following, projection, obstacles = settle(f'step-{step+1:02d}')
                        if (abs(following['width_m'] - current['width_m']) > .08
                                or abs(following['distance_m'] - current['distance_m']) > .14):
                            raise ValueError('door geometry changed across movement')
                        current = following
                    if result['status']=='hold':
                        result['reason']='bounded approach limit reached'
            finally:
                control.stop_all(motors,context='door-approach-final')
                result['stopped']=True
    except Exception as error:
        result['reason']=str(error)
    finally:
        if cap:
            cap.release()
        signal.alarm(0)
        (path/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('commands','observations')}),flush=True)
    return result['status']=='hold'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--lens',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--stop-distance-cm',type=float,default=22.)
    parser.add_argument('--move',action='store_true',help='enable bounded movement after visual checks')
    return run(parser.parse_args())


if __name__=='__main__':
    raise SystemExit(main())
