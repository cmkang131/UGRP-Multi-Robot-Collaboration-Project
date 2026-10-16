"""Memory ON/OFF with delayed own providers; fake vision, no physics/models."""
import copy

import numpy as np
import pytest

from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3
from harness.zone_study_pose_delay import DelayedPoseSource
from tests.test_vision_pose_source import CALIB, SEARCH_POSE, provider
from tests.test_zone_pair_tag_boundary_matrix import block_measurements, damaged_map
from tests.test_zone_own_executor import ROWS_Y, make, obs, rgb_of


@pytest.mark.parametrize('controller', [M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3])
@pytest.mark.parametrize('kind', ['vision', 'tags'])
@pytest.mark.parametrize('delayed', [False, True])
def test_memory_commands_use_public_motion_interface(monkeypatch, controller, kind, delayed):
    static = damaged_map('no_landmarks') if kind == 'vision' else make().map
    raw = provider() if kind == 'vision' else make().pose
    calls = block_measurements(monkeypatch) if kind == 'vision' else []
    pose = DelayedPoseSource(raw) if delayed else raw
    try:
        ctl = controller(static, CALIB['params'], pose_source=pose, box_kind='cyan',
                         slot_id='A2', slot_xy=(4., -1.), skill_factory=lambda *a: None,
                         pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
        ctl.on_command({'kind': 'initial_servo_command', 't': 0., 'pulses': SEARCH_POSE})
        frame = obs('r1', 1, 0., SEARCH_POSE)
        ctl.on_frame(0., frame, rgb_of(frame))
        motion = pose.get_motion_params()
        ctl.on_command({'kind': 'mecanum', 't': .1, 'forward': .2, 'left': .1,
                        'turn': 0., 'duration_s': .5})
        ctl.memory.guard.advance(.6)
        expected = np.linalg.norm(np.asarray(motion['gain'])[:2] @ [.2, .1, 0.]) * .5
        assert ctl.memory.guard.command_travel_m == pytest.approx(expected)
        assert not calls
        if kind == 'vision':
            assert not raw.worker.calls  # unsettled blank frame, no fake inference needed
    finally:
        close = getattr(pose, 'close', None)
        if close:
            close()


@pytest.mark.parametrize('kind', ['vision', 'tags'])
def test_delayed_motion_query_is_detached_and_does_not_release_inputs(kind):
    raw = provider() if kind == 'vision' else make().pose
    pose = DelayedPoseSource(raw)
    try:
        before = raw.get_motion_params()
        profile = next(iter(raw.loc.params['motion_profiles']))
        pose.set_motion_profile(.2, profile)
        pose.report(.3)
        queued = copy.deepcopy(pose.pending)
        assert pose.get_motion_params() == before
        detached = pose.get_motion_params()
        detached['gain'][0][0] += 123
        assert pose.get_motion_params() == before and pose.pending == queued
        assert raw.loc.motion_profile is None
        pose.report(.36)
        assert raw.loc.motion_profile == profile
        assert pose.get_motion_params() == raw.loc.params['motion_profiles'][profile]
    finally:
        close = getattr(pose, 'close', None)
        if close:
            close()
