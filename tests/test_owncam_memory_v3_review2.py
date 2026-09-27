"""Second adversarial review: slot clearance, simultaneous captures, free grid."""
from dataclasses import replace
import base64
import hashlib
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np
import pytest

from tests.test_owncam_memory_v3 import controller, feed, fix, memory, report
from tests.test_owncam_memory_v3_review import SAVED, saved_place, track_at, explicit_empty_slot_evidence
from harness.owncam_drive import SEARCH_POSE
from harness.owncam_memory_v3 import BoxTrackV3, P_KEEPOUT
from harness.owncam_pose_guard_v3 import PoseGuardV3
from harness.owncam_visibility_v3 import self_arm_clear


def test_p1_unknown_slot_never_authorizes_release():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    with mock.patch.object(ctl, '_start_leg'):
        assert ctl._boundary_gate(now, 'place') is not None
    assert not any(e['event'] == 'boundary_verified' for e in ctl.events)


def test_p1_time_decay_cannot_remove_slot_occupancy_veto():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    tr = BoxTrackV3('old-obstacle', 'red', np.array(ctl.slot_xy), np.eye(2)*.01,
                    now-225., 1, 'far_coarse', .001)
    tr.evidence(now-225., detected=True, range_class='far_coarse', pose_sigma=.02)
    ctl.memory.tracks.append(tr)
    ctl.memory.log_odds[:] = -2.
    ctl.memory.free_observed_at[:] = now
    state = ctl.memory.slot_state(now, ctl.slot_xy, ctl._slot_half())
    assert tr.existence_p < P_KEEPOUT  # The probabilistic survival prior may decay.
    assert state['state'] != 'free'    # It cannot itself authorize manipulation.
    with mock.patch.object(ctl, '_start_leg'):
        assert ctl._boundary_gate(now, 'place') is not None


def test_p1_new_frame_at_same_time_is_accepted_without_extra_pose_evidence():
    guard = PoseGuardV3()
    guard.observe_evidence(1., 1, nis=0., log_likelihood=-1., settled=True)
    guard.observe_evidence(1., 2, nis=0., log_likelihood=-1., settled=True)
    assert guard.good_times == [1.]
    assert not guard.consistent(1.)
    guard.observe_evidence(1.4, 3, nis=0., log_likelihood=-1., settled=True)
    assert guard.consistent(1.4)


def test_p1_controller_normal_same_time_capture_does_not_raise():
    ctl = controller()
    ctl.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
    rgb = np.zeros((480, 640, 3), np.uint8)
    jpeg = cv2.imencode('.jpg', rgb)[1].tobytes()
    obs = {'sim_time': 1., 'frame_id': 1, 'image': base64.b64encode(jpeg).decode(),
           'robot_id': 'r1', 'camera': 'robot_cam', 'sha256': hashlib.sha256(jpeg).hexdigest(),
           'actuator_state': {'servo_pulses': {str(k): v for k, v in SEARCH_POSE.items()}}}
    ctl.on_frame(1., obs, rgb)
    ctl.on_frame(1., {**obs, 'frame_id': 2}, rgb)
    assert ctl.memory.last_frame_id == 2


def test_p2_floor_free_requires_whole_yaw_interval_visible():
    mem = memory()
    for t in (1., 1.4, 1.8):
        rep = replace(report(t, x=0., y=0.), std_yaw_rad=.5,
                      cov=tuple(map(tuple, np.diag([.0001, .0001, .25]))))
        feed(mem, t, rep=rep)
    free = mem.log_odds <= -.6
    assert len(mem.view.floor_footprint((0., 0., 0.), SEARCH_POSE, False, max_range=1.1)[0]) > 0
    invisible = [i for i in np.flatnonzero(free)
                 if not mem.view.point_in_view((0., 0., 1.), SEARCH_POSE, False, (*mem.view.cells[i], 0.))]
    assert not invisible


def test_p2_floor_free_requires_self_arm_visibility():
    mem = memory()
    for t in (1., 1.4, 1.8):
        feed(mem, t, rep=report(t, x=0., y=0.))
    free = mem.log_odds <= -.6
    assert free.any()
    hidden = [i for i in np.flatnonzero(free)
              if not self_arm_clear((0., 0., 0.), SEARCH_POSE, np.array([[*mem.view.cells[i], 0.]]))]
    assert not hidden


@pytest.mark.parametrize('item', SAVED, ids=lambda x: f"s{x['seed']}")
def test_saved_release_inputs_alone_now_require_inspection(item):
    ctl, now, _, _, _ = saved_place(item)
    with mock.patch.object(ctl, '_start_leg') as start:
        result = ctl._boundary_gate(now, 'place')
    assert result['mode'] == 'tick'
    assert ctl.slot_record['state'] == 'unknown'
    assert ctl.slot_inspection['stage'] == 'outbound'
    assert start.call_args.kwargs['loaded']
    assert start.call_args.args[0][0] < ctl.slot_xy[0]-.9


def test_unknown_inspection_is_bounded_and_handed_to_upper_controller():
    from harness.owncam_slot_inspection_v3 import MAX_SLOT_VIEWS
    ctl, now, _, _, _ = saved_place(SAVED[0])
    with mock.patch.object(ctl, '_start_leg'):
        ctl._boundary_gate(now, 'place')
        for _ in range(MAX_SLOT_VIEWS):
            result = ctl._next_slot_view(now+1.)
    assert result['mode'] == 'done'
    assert result['outcome'] == 'SLOT_UNVERIFIED'
    assert result['handoff']['attempts'] == MAX_SLOT_VIEWS
    assert result['handoff']['requires_upper_level_decision']
    assert not result['handoff']['release_started']
    assert ctl.skill.box.phase == 'carry'
    assert ctl.decide(now+2.) == result


def test_inspection_timeout_terminates_even_without_new_frames():
    from harness.owncam_slot_inspection_v3 import SLOT_INSPECTION_TIMEOUT_S
    ctl, now, _, _, _ = saved_place(SAVED[0])
    with mock.patch.object(ctl, '_start_leg'):
        ctl._boundary_gate(now, 'place')
    ctl.slot_inspection['stage'] = 'checked_view'
    ctl.reanchor_needed = True
    ctl.last_obs = None
    assert ctl.decide(now+1.)['mode'] == 'tick'
    result = ctl.decide(now+SLOT_INSPECTION_TIMEOUT_S)
    assert result['handoff']['reason'] == 'inspection_timeout'
    assert result['outcome'] == 'SLOT_UNVERIFIED'


def test_inspection_leg_failure_does_not_release_or_relabel_success():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    with mock.patch.object(ctl, '_start_leg'):
        ctl._boundary_gate(now, 'place')
    with mock.patch.object(ctl, '_drive_leg', return_value=([], 'no_path')):
        result = ctl.decide(now+.1)
    assert result['outcome'] == 'SLOT_UNVERIFIED'
    assert result['handoff']['reason'] == 'outbound_leg_no_path'
    assert ctl.skill.box.phase == 'carry'


def test_slot_inspection_moves_looks_returns_and_only_then_dispatches():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    with mock.patch.object(ctl, '_start_leg') as start:
        ctl._boundary_gate(now, 'place')
        with mock.patch.object(ctl, '_drive_leg', return_value=([], 'arrived')):
            ctl.decide(now+.1)
        assert ctl.sweep['pose'] == {k: (1500 if k == 1 else v) for k, v in SEARCH_POSE.items() if k != 6}
        assert len(ctl.sweep['queue']) == 4  # multiple distinct-time frames
        assert ctl.skill.box.phase == 'carry'
        ctl.sweep = None
        ctl.slot_inspection['stage'] = 'checked_view'
        ctl.reanchor_needed = False
        explicit_empty_slot_evidence(ctl, now)
        ctl.decide(now+.2)
        assert ctl.slot_inspection['stage'] == 'return'
        assert start.call_args.args[0] == ctl.skill._preplace_goal()
        assert start.call_args.kwargs['loaded']
        assert 'empty_slot_evidence' in ctl.verification['place']
        ctl.last_obs = {**ctl.last_obs, 'sim_time': now+.3, 'frame_id': ctl.last_obs['frame_id']+1}
        with mock.patch.object(ctl, '_drive_leg', return_value=([], 'arrived')):
            ctl.decide(now+.3)
        assert ctl.slot_inspection['stage'] == 'restore'
        ctl.decide(now+1.)
        assert ctl.slot_inspection is None
        assert ctl.reanchor_needed
        assert ctl.skill.box.phase == 'carry'
    # Final boundary still independently checks current pose/attachment/floor.
    ctl.last_obs = {**ctl.last_obs, 'sim_time': now+1., 'frame_id': ctl.last_obs['frame_id']+1}
    rep = replace(ctl.pose.report(now), t_est=now+1.)
    ctl.pose.report = lambda t: rep
    fix(ctl.memory, now+1., (rep.x_m, rep.y_m))
    assert ctl._boundary_gate(now+1., 'place') is None


def test_observation_only_occupancy_veto_survives_decay_and_needs_visible_misses():
    _, tr = track_at()
    tr.evidence(0., detected=True, range_class='far_coarse', pose_sigma=.02)
    p_observed = tr.observation_existence_p
    tr.predict(1000.)
    assert tr.existence_p < .01
    assert tr.observation_existence_p == p_observed
    assert tr.slot_blocking
    for t in (1000., 1000.4, 1000.8):
        tr.evidence(t, detected=False)
    assert not tr.slot_blocking
    assert tr.last_visible_clear_t == 1000.8
    tr.evidence(1001.2, detected=True, pose_sigma=.02)
    assert tr.slot_blocking


@pytest.mark.parametrize('bad_time,bad_id', [(1., 2), (.9, 3), (1.1, 1)])
def test_pair_order_rejects_duplicate_rewind_or_reused_id(bad_time, bad_id):
    guard = PoseGuardV3()
    guard.observe_evidence(1., 2, nis=0., log_likelihood=-1., settled=True)
    with pytest.raises(ValueError):
        guard.observe_evidence(bad_time, bad_id, nis=0., log_likelihood=-1., settled=True)


def test_same_time_capture_does_not_reweight_pf_or_recertify_free_cells():
    ctl = controller()
    ctl.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SEARCH_POSE})
    rgb = np.zeros((480, 640, 3), np.uint8)
    ctl.pose.on_frame(1., rgb)
    with mock.patch.object(ctl.pose.loc, 'update') as update:
        ctl.pose.on_frame(1., rgb)
    update.assert_not_called()
    mem = memory()
    feed(mem, 1.)
    before = mem.log_odds.copy()
    mem.observe_frame(1., frame_id=101, image=None, servo=SEARCH_POSE, report=report(1.),
                      arm_settled_s=1., loaded=False)
    np.testing.assert_array_equal(mem.log_odds, before)


def test_same_time_bad_diagnostic_invalidates_but_cannot_add_confidence():
    guard = PoseGuardV3()
    guard.observe_evidence(1., 1, nis=0., log_likelihood=-1., settled=True)
    guard.observe_evidence(1.4, 2, nis=0., log_likelihood=-1., settled=True)
    assert guard.consistent(1.4)
    guard.observe_evidence(1.4, 3, nis=100., log_likelihood=-20., settled=True)
    assert not guard.consistent(1.4)


@pytest.mark.parametrize('item', SAVED, ids=lambda x: f"s{x['seed']}")
def test_real_cargo_mask_and_synthetic_precise_inspection_pose_can_observe_slot(item):
    ctl, now, _, _, image = saved_place(item)
    mem = ctl.memory
    mem._frame_loaded = mem._frame_pose_good = True
    limit = mem.cargo_row_limit(image)
    assert limit is not None
    # New synthetic pose evidence, not a claim that the v2 recording visited here.
    cov = np.diag([.005**2, .005**2, .005**2])
    for view, standoff in enumerate((.95, 1.05)):
        pose = (ctl.slot_xy[0]-standoff, ctl.slot_xy[1], 0.)
        for frame in range(4):
            t = now + view*2. + frame*.4
            mem._observe_floor(t, pose, {**SEARCH_POSE, 1: 1500}, [], cov=cov,
                               cargo_row_limit=limit, frame_id=6000+view*4+frame)
    state = mem.slot_state(now+3.2, ctl.slot_xy, ctl._slot_half(), since=now)
    assert state['state'] == 'free'
    assert state['known_free_cells'] == state['cells'] == 16


def test_loaded_floor_without_current_cargo_mask_is_never_free():
    mem = memory()
    mem._frame_loaded = mem._frame_pose_good = True
    for t in (1., 1.4, 1.8):
        mem._observe_floor(t, (0., 0., 0.), {**SEARCH_POSE, 1: 1500}, [], cov=np.eye(3)*.00001)
    assert not np.any(mem.free_observed_at > -np.inf)


def test_loaded_search_frames_reach_floor_observer_without_opening_grip():
    from tests.test_owncam_memory_v3 import consistent
    ctl, now, _, _, image = saved_place(SAVED[0])
    mem = ctl.memory
    mem._detect = lambda image, servo: []
    pose = (ctl.slot_xy[0]-1.05, ctl.slot_xy[1])
    for frame in range(4):
        t = now+frame*.4
        consistent(mem.guard, t)
        rep = replace(report(t, x=pose[0], y=pose[1], sigma=.007), load_state='loaded')
        mem.observe_frame(t, frame_id=7000+frame, image=image, servo={**SEARCH_POSE, 1: 1500},
                          report=rep, arm_settled_s=1., loaded=True)
    assert mem.slot_state(now+1.2, ctl.slot_xy, ctl._slot_half(), since=now)['state'] == 'free'


def test_new_obstacle_or_expired_floor_certificate_blocks_returned_release():
    from harness.owncam_memory_v3 import SLOT_CLEAR_MAX_AGE_S
    ctl, now, _, _, _ = saved_place(SAVED[0])
    explicit_empty_slot_evidence(ctl, now)
    assert ctl._boundary_gate(now, 'place') is None
    # Certificate expiration cannot be repaired by a new pose/attachment image.
    mask = ctl.memory.slot_cells(ctl.slot_xy, ctl._slot_half())
    ctl.memory.free_observed_at[mask] = now-SLOT_CLEAR_MAX_AGE_S-.01
    with mock.patch.object(ctl, '_start_leg'):
        assert ctl._boundary_gate(now, 'place') is not None
    explicit_empty_slot_evidence(ctl, now)
    _, tr = track_at(*ctl.slot_xy)
    tr.t = now
    ctl.memory.tracks.append(tr)
    result = ctl._boundary_gate(now, 'place')
    assert result['outcome'] == 'SLOT_OCCUPIED_IN_MEMORY'
    assert result['handoff']['requires_upper_level_decision']


def test_all_updated_floor_cells_pass_the_shared_full_support_predicate():
    mem = memory()
    rep = report(1., x=0., y=0.)
    feed(mem, 1., rep=rep)
    ids = np.flatnonzero(mem.free_observed_at == 1.)
    assert len(ids) > 0
    assert all(mem.floor_cell_visible(mem.view.cells[i], (0., 0., 0.), np.array(rep.cov), SEARCH_POSE)
               for i in ids)
