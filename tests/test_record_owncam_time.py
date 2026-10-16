"""Standalone LoggingPort -> actual M1 memory-v3, with images/fake ports only."""
import base64
import hashlib
from types import SimpleNamespace as NS

import cv2
import numpy as np
import pytest

from harness.owncam_drive import SEARCH_POSE
from scripts.record_owncam_localization import LoggingPort
from tests.test_owncam_memory_v3 import controller


@pytest.mark.parametrize('raw', [2.000049, 2.000051])
@pytest.mark.parametrize('kind', ['hold', 'arm', 'mecanum'])
def test_raw_frame_command_frame_clock_in_standalone_m1(raw, kind):
    ctl = controller()
    ctl.on_command(dict(t=0., kind='initial_servo_command', pulses=SEARCH_POSE))
    rgb = np.zeros((480, 640, 3), np.uint8)
    jpeg = cv2.imencode('.jpg', rgb)[1].tobytes()
    obs = dict(sim_time=raw, frame_id=1, image=base64.b64encode(jpeg).decode(),
               robot_id='r1', camera='robot_cam', sha256=hashlib.sha256(jpeg).hexdigest(),
               actuator_state={'servo_pulses': {str(k): v for k, v in SEARCH_POSE.items()}})
    ctl.on_frame(raw, obs, rgb)
    rows, issued = [], []
    def sink(row):
        rows.append(row)
        ctl.on_command(row)
    port = LoggingPort(NS(hold=lambda t: issued.append(t),
                          apply=lambda action, t: issued.append(t)), sink)
    if kind == 'hold':
        port.hold(raw)
    else:
        action = (dict(kind='arm', servo_id=6, pulse=1500) if kind == 'arm' else
                  dict(kind='mecanum', forward=.1, left=0., turn=0., duration_s=.3))
        port.apply(action, raw)
    # Round-up used to fail on this subsequent raw frame (or memory freshness).
    ctl.on_frame(raw, {**obs, 'frame_id': 2}, rgb)
    assert rows[-1]['t'] == issued[-1] == ctl.memory.guard.command_t == raw
    assert ctl.pose.loc.t == raw
    if kind == 'mecanum':
        assert ctl.memory.guard.expires == raw + .3
    else:
        assert ctl.memory.guard.command_travel_m == 0.


def test_action_cannot_override_port_time_and_genuine_clock_reversal_is_rejected():
    ctl = controller()
    port = LoggingPort(NS(apply=lambda action, t: None, hold=lambda t: None), ctl.on_command)
    port.apply(dict(kind='hold', t=-999.), 2.000049)
    assert ctl.memory.guard.command_t == 2.000049
    with pytest.raises(ValueError, match='non-monotonic command clock'):
        port.hold(2.000048)


@pytest.mark.parametrize('raw', [2.000049, 2.000051])
def test_dataset_capture_keeps_raw_replay_input_time(tmp_path, raw):
    from scripts.record_owncam_localization import Recorder
    rec = Recorder.__new__(Recorder)
    rec.out, rec.rid, rec.cam_id, rec.box_body = tmp_path, 'r1', 0, 'box'
    rec.frames, rec.frame_gt, rec.servo = [], [], SEARCH_POSE
    rec.now, rec._truth, rec.robot = lambda: raw, lambda: (0., 0., 0.), NS(phase='fake')
    rec.world = NS(render_rgb=lambda **kw: np.zeros((480, 640, 3), np.uint8),
                   data=NS(cam_xpos=[np.zeros(3)], cam_xmat=[np.eye(3)],
                           body=lambda name: NS(xpos=[0., 0., 0.])))
    rec.capture('test')
    assert rec.frames[0]['t'] == raw
    assert hashlib.sha256((tmp_path / rec.frames[0]['file']).read_bytes()).hexdigest() == rec.frames[0]['sha256']
