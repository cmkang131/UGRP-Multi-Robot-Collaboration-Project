"""Collect labelled REAL camera/drive calibration evidence, without running ACT.

This records measurements; it does not claim or apply a calibrated camera fit.
Robot-base origin is the midpoint between the wheel axles, halfway across.
Axes: +x forward, +y left, +yaw counterclockwise viewed from above.
"""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import threading
import time

import run


class CalibrationLink(run.Link):
    def __init__(self, *args):
        self.request_lock = threading.RLock()
        super().__init__(*args)

    def request(self, payload):
        with self.request_lock:
            return super().request(payload)


def motion_measurement(text):
    if text.strip().lower() == 'skip':
        return None
    values = [float(v.strip()) for v in text.split(',')]
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise ValueError('Enter x_cm,y_cm,yaw_degrees, or skip')
    if any(abs(v) > 100 for v in values[:2]) or abs(values[2]) > 180:
        raise ValueError('Measurement outside the bounded calibration range')
    return {'dx_forward_m': values[0]/100., 'dy_left_m': values[1]/100.,
            'dyaw_rad': math.radians(values[2]), 'source': 'operator measurement'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--expected-host', choices=('ras2', 'ugrp1'), required=True)
    parser.add_argument('--target', choices=('red',), default='red')
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error('seconds must be between 1 and 600')
    output = run.ROOT / 'calibrations' / args.expected_host / time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'starting', 'host': args.host, 'expected_host': args.expected_host,
              'target_edge_m': .03, 'target_shape': 'cube', 'calibration_applied': False,
              'base_origin': 'midpoint between wheel axles, halfway between left/right wheels',
              'samples': [], 'motion_trials': [], 'physical_grasp_tested': False}
    link = None
    finish = threading.Event()
    keepalive = None
    failures = []
    approach = run.SurveyApproach(run.contract, lambda entries: 0)
    current_pose = dict(run.FAR_POSTURE)

    def command(pose, wheels=None):
        values = [0.]*4 if wheels is None else wheels
        hardware, _ = run.board_command({'t': 0., 'wheels': values,
                                        'duration_s': [.1 if v else 0. for v in values],
                                        'pwm': {str(k): v for k, v in pose.items()}}, 35)
        return hardware

    def check():
        if failures:
            raise RuntimeError(f'Calibration connection failed: {failures[0]}')

    def wait_for_operator(message):
        input(message + '\nPress Enter when ready, or Ctrl+C to stop: ')
        check()

    def heartbeat():
        try:
            while not finish.wait(.75):
                link.request({'op': 'observe'})
        except BaseException as error:
            failures.append(str(error))

    def save():
        (output / 'samples.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    def capture(label, point=None):
        check()
        frame = link.request({'op': 'observe'})
        jpeg = base64.b64decode(frame['jpeg'], validate=True)
        path = label + '.jpg'
        (output / path).write_bytes(jpeg)
        blobs = approach.baseline.components(jpeg, 'red')
        sample = {'path': path, 'sha256': hashlib.sha256(jpeg).hexdigest(), 't': frame['t'],
                  'commanded_pose': dict(current_pose), 'known_cube_center_xy_m': point,
                  'red_components': blobs,
                  'timestamp_source': 'Pi snapshot receive time, not exposure time'}
        report['samples'].append(sample)
        save()
        print(f'CAPTURE {label}: {len(blobs)} red candidates', flush=True)
        return sample

    try:
        print('Calibration records REAL measurements; it does not execute ACT.', flush=True)
        print('The arm will use the published survey/near postures. Keep its travel clear.', flush=True)
        link = CalibrationLink(args.host, args.user, output, True, args.seconds, args.expected_host)
        report['hardware'] = link.ready
        if not link.ready['probe'].get('ok'):
            raise RuntimeError('Board probe failed')
        keepalive = threading.Thread(target=heartbeat, daemon=True)
        keepalive.start()
        print('Keep the robot base fixed on a level, clear FLOOR during all camera samples.', flush=True)
        print('Remove other red objects. Align the 3cm cube edges with the base x/y axes.', flush=True)
        points = ((.20, 0.), (.30, 0.), (.45, 0.), (.30, .10), (.30, -.10))
        poses = [('far', dict(run.FAR_POSTURE)),
                 ('mid', {1: 2000, 3: 700, 4: 2440, 5: 1320, 6: 1500}),
                 ('near', {1: 2000, 3: 500, 4: 2500, 5: 1320, 6: 1500})]
        for index, point in enumerate(points):
            x, y = point
            wait_for_operator(f'CAMERA {index+1}/5: place cube CENTER at x={x*100:.0f} cm forward, '
                              f'y={y*100:.0f} cm left of the base origin. Measure these positions now; '
                              'the earlier trial starting distance is not needed. Remove your hands.')
            plan = list(poses)
            if point == (.45, 0.):
                plan += [(f'pan{pan}', {**run.FAR_POSTURE, 6: pan}) for pan in (1250, 1750)]
            for name, pose in plan:
                check()
                link.request(command(pose))
                current_pose = pose
                time.sleep(1.25)
                capture(f'p{index+1}-{name}', list(point))
        print('CAMERA SAMPLES RECORDED. Next: optional measured wheel test pulses.', flush=True)
        link.request(command(run.FAR_POSTURE))
        current_pose = dict(run.FAR_POSTURE)
        time.sleep(1.25)
        print('For each pulse, mark base position and heading first. Measure changes afterwards.', flush=True)
        print('Signs: forward +x; left +y; counterclockwise yaw positive. Units: cm,cm,degrees.', flush=True)
        for mode, pattern in (('forward', [1,1,1,1]), ('turn_left', [-1,1,-1,1]),
                              ('strafe_left', [-1,1,1,-1])):
            answer = input(f'{mode}: clear the floor and mark the base. Type PULSE for ONE 0.10s pulse, '
                           'or SKIP: ').strip().lower()
            check()
            if answer != 'pulse':
                report['motion_trials'].append({'mode': mode, 'status': 'skipped'})
                save()
                continue
            before = capture(f'{mode}-before')
            hardware = command(current_pose, [.35*v for v in pattern])
            trial = {'mode': mode, 'request': hardware, 'measurement': None, 'before_t': before['t']}
            report['motion_trials'].append(trial)
            save()
            trial['accepted'] = link.request(hardware)
            time.sleep(.25)
            link.request(command(current_pose))
            after = capture(f'{mode}-after')
            trial['after_t'] = after['t']
            while True:
                try:
                    trial['measurement'] = motion_measurement(input(
                        f'{mode} measured change: x_cm,y_cm,yaw_degrees (or skip): '))
                    check()
                    break
                except ValueError as error:
                    print(str(error), flush=True)
            save()
        report['status'] = 'raw_calibration_evidence_recorded'
        print('RAW CALIBRATION EVIDENCE RECORDED. No camera fit or drive profile has been applied.', flush=True)
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error))
        raise
    finally:
        finish.set()
        try:
            if keepalive is not None:
                keepalive.join(timeout=6.)
            if link is not None:
                link.close()
        finally:
            save()
            print(f'Calibration directory: {output}', flush=True)


if __name__ == '__main__':
    main()
