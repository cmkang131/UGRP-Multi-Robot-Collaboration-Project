"""Offline regression checks for the real-robot boundary and the published ACT."""
import base64
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(os.environ.get('UGRP_SOLO_ROOT', Path(__file__).resolve().parents[1]))
import pi_bridge
import run


class FakeControl:
    def __init__(self):
        self.writes = []

    def MotorTransport(self):
        return self

    def ServoTransport(self):
        return self

    def load_pose_state(self):
        return dict(run.FAR_POSTURE)

    def write_motor(self, motor, speed):
        self.writes.append((time.monotonic(), motor, speed))

    def write_servo(self, servo, target, duration):
        self.writes.append((time.monotonic(), 'servo', target))

    def stop_all(self, transport, context):
        for motor in range(1, 5):
            self.write_motor(motor, 0)


def main():
    result = {}
    value = {'t': 0., 'wheels': [.31, .32, -.33, -.40],
             'duration_s': [.04, .06, .08, .15],
             'pwm': {str(k): v for k, v in run.FAR_POSTURE.items()}}
    command, projected = run.board_command(value, 35)
    assert command['motors'] == [-35, -40, 35, 35]
    assert command['duration_s'] == [.06, .15, .04, .08]
    assert projected == [.35, .35, -.35, -.40]
    for invalid in (dict(command, motors=[1]*4), dict(command, duration_s=[.2]*4),
                    dict(command, pwm={'1': 1500})):
        try:
            pi_bridge.validate(invalid)
        except ValueError:
            continue
        raise AssertionError('Invalid hardware command accepted')
    result['motor_mapping_and_validation'] = 'passed'
    control = FakeControl()
    hardware = pi_bridge.Hardware(control)
    hardware.thread.start()
    try:
        hardware.apply(command)
        time.sleep(.04)
        # A newer STOP supersedes pulses that have not reached their deadlines.
        stop = dict(command, motors=[0]*4, duration_s=[0.]*4)
        hardware.apply(stop)
        time.sleep(.025)
        assert hardware.active == [0]*4
        hardware.apply(command)
        time.sleep(.18)
        assert hardware.active == [0]*4
        hardware.apply(command)
        hardware.heartbeat = time.monotonic() - 3.
        time.sleep(.03)
        assert hardware.finish.is_set() and hardware.error == 'Host command stream expired'
        assert hardware.active == [0]*4
        result['pulse_expiry_preemption_and_link_timeout'] = 'passed'
    finally:
        hardware.finish.set()
        hardware.thread.join(timeout=1.)
        hardware.stop()
    # Exception while a real I2C write is being attempted must enter STOP.
    control = FakeControl()
    original = control.write_motor
    def failing(motor, speed):
        if speed:
            raise OSError('injected I2C failure')
        original(motor, speed)
    control.write_motor = failing
    hardware = pi_bridge.Hardware(control)
    hardware.thread.start()
    hardware.apply(command)
    hardware.thread.join(timeout=1.)
    assert hardware.error == 'injected I2C failure' and hardware.active == [0]*4
    result['stop_on_i2c_failure'] = 'passed'

    import torch
    torch.set_num_threads(4)
    actor = run.GraspActor.load(ROOT / 'runtime/actor', device='cpu')
    assert actor.image_frontend == 'seg5_v1'
    capture = json.loads((ROOT.parent/'solo-act-release-20261112/ugrp1-act-camera-sample.json').read_bytes())
    frame = capture['frames'][-1]
    jpeg = base64.b64decode(frame['jpeg'])
    initial = dict(value, wheels=[0.]*4, duration_s=[0.]*4)
    history = run.OwnHistory('r1', 'offline-regression', initial)
    obs, pixels, _ = history.observe(0., jpeg, skill='grasp', object_kind='red', role='west')
    times = []
    for _ in range(3):
        started = time.monotonic()
        chunk = actor.predict(obs, pixels)
        times.append(time.monotonic()-started)
    assert len(chunk) == 8 and all(len(row) == 14 for row in chunk)
    for row in chunk:
        run.board_command({'t': 0., **{key: run.contract.decode_action(row)[key]
                                     for key in ('wheels', 'duration_s', 'pwm')}}, 35)
    approach = run.SurveyApproach(run.contract, lambda entries: run.select_target(entries, 'red'))
    ticks = 0
    for index in range(130):
        step = approach.step(jpeg, index*.1)
        if step is None:
            assert approach.arrived
            break
        run.contract.command(step)
        ticks += 1
    assert approach.entries is not None
    assert run.select_target([{'kind': 'cyan', 'distance_m': .2},
                              {'kind': 'red', 'distance_m': .4},
                              {'kind': 'red', 'distance_m': .3}], 'red') == 2
    result.update(published_model='loaded', image_frontend=actor.image_frontend,
                  model_chunk_shape=[8,14], inference_seconds=times,
                  live_pipeline_simulated_frames=f'{ticks} valid ticks, terminal={approach.reason}',
                  physical_commands_sent=0, physical_grasp_success=None)
    (ROOT/'offline-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
