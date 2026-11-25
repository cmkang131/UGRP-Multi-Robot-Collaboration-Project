"""Offline checks of cube geometry and the operator-guided calibration session."""
import base64
from collections import deque
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

import calibrate
import cube_alignment
import pi_bridge
import run


def main():
    source = run.ROOT
    jpeg = (source/'runs/20261125-172842/rgb/r1/000345.jpg').read_bytes()
    instances = []

    class FakeLink:
        def __init__(self, *args):
            self.ready = {'host': 'ras2', 'probe': {'ok': True}}
            self.commands = []
            self.reads = 0
            self.closed = False
            instances.append(self)

        def request(self, value):
            if value['op'] == 'observe':
                self.reads += 1
                return {'t': float(self.reads), 'jpeg': base64.b64encode(jpeg).decode('ascii')}
            assert value['op'] == 'command'
            pi_bridge.validate(value)
            self.commands.append(value)
            return {'accepted_at': float(self.reads), 'pwm': value['pwm']}

        def close(self):
            self.closed = True

    def exercise(answers, interrupt=False):
        answers = deque(answers)
        calls = 0
        def operator(prompt):
            nonlocal calls
            calls += 1
            if calls == 1:
                # A slow operator must not let the Pi heartbeat expire.
                threading.Event().wait(.85)
                if interrupt:
                    raise KeyboardInterrupt()
            return answers.popleft()
        with tempfile.TemporaryDirectory(prefix='solo-calibration-test-') as folder:
            root = Path(folder)
            with patch.object(run, 'ROOT', root), patch.object(calibrate, 'CalibrationLink', FakeLink), \
                 patch.object(calibrate.time, 'sleep'), patch('builtins.input', side_effect=operator), \
                 patch.object(sys, 'argv', ['calibrate.py', '--host', '192.168.137.11',
                                           '--user', 'example', '--expected-host', 'ras2']), \
                 contextlib.redirect_stdout(io.StringIO()):
                try:
                    calibrate.main()
                except KeyboardInterrupt:
                    assert interrupt
            result_path = next((root/'calibrations/ras2').glob('*/samples.json'))
            report = json.loads(result_path.read_bytes())
            assert instances[-1].closed
            assert report['calibration_applied'] is False
            assert instances[-1].reads > len(report['samples']), 'No heartbeat while waiting for operator'
            moving = [v for v in instances[-1].commands if any(v['motors'])]
            if interrupt:
                assert report['status'] == 'interrupted' and not moving
            else:
                assert report['status'] == 'raw_calibration_evidence_recorded'
                assert len(report['samples']) == 23 and len(moving) == 3
                assert sum(s['known_cube_center_xy_m'] is not None for s in report['samples']) == 17
                assert all(v['duration_s'] == [.1]*4 for v in moving)
                assert all(s['measurement'] is not None for s in report['motion_trials'])
            return {'status': report['status'], 'recorded_samples': len(report['samples']),
                    'fake_motion_requests': len(moving), 'connection_closed': True}

    completed = exercise(['']*5 + ['pulse', '1,0,0', 'pulse', '0,0,5', 'pulse', '0,1,0'])
    interrupted = exercise([], interrupt=True)
    for invalid in ('nan,0,0', '1,2', '1000,0,0', '0,0,190'):
        try:
            calibrate.motion_measurement(invalid)
        except ValueError:
            continue
        raise AssertionError(f'Accepted invalid measurement: {invalid}')
    result = {'cube_alignment': cube_alignment.self_test(), 'fake_session_completed': completed,
              'fake_session_interrupted': interrupted, 'invalid_measurements_rejected': True,
              'physical_commands_sent': 0, 'real_calibration_applied': False,
              'real_grasp_verified': False}
    (source/'calibration-offline-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
