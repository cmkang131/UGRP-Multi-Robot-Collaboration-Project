"""T08b decision tests: fake own providers/pixels, no simulator or inference."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness import beam_approach as ba
from harness import beam_initial_pose_plan as bp
from harness.owncam_pose_source import PoseReport
from harness.owncam_drive import SEARCH_POSE

# Collect the imported independent counterexample in the existing CI glob.
pytest.register_assert_rewrite('test_review_e2e_batch_h')
from test_review_e2e_batch_h import (  # noqa: E402,F401
    beam, test_beam_accepts_native_issued_search_history_without_rescaling,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = [('s1_normal_mixed_v2', [1.3, .4, 1.570796]),
         ('s3_late_rendezvous_v2', [.1, .4, 1.570796]),
         ('s6_novel_relation_v2', [1.1, -.8, 1.570796])]
SERVO = dict(SEARCH_POSE)


def public_inputs(index=0):
    name, pose = CASES[index]
    scene = json.loads((ROOT / 'configs/zone_study_scenarios_v2' / (name + '.json')).read_text())
    order = next(o for o in scene['orders'] if o['kind'] == 'long_beam')
    directory = 'zones' if index != 2 else 'zones_final'
    static = json.loads((ROOT / 'maps' / directory / (scene['map_id'] + '.json')).read_text())
    coarse = {'beam_xyyaw': pose, 'grid': dict(bp.GRID), 'source': bp.SOURCE}
    return static, bp.freeze_public_sheet(static, coarse, order), order


class FakeProvider:
    def __init__(self, pose=(-.85, -.85, 0.)):
        self.loc = object()  # identity stands in for a persistent posterior
        self.commands, self.images = [], []
        self.pose = pose
        self.std = .001
        self.initialized = True
        self.source = 'owncam_pf_test_fake'
        self.fix_offset = 0.

    def on_frame(self, now, frame):
        self.images.append((now, frame.copy()))

    def on_command(self, row):
        self.commands.append(copy.deepcopy(row))

    def report(self, now):
        return PoseReport(now, self.initialized, *self.pose, std_xy_m=self.std,
                          std_yaw_rad=.001, source=self.source, last_fix_t=now-self.fix_offset)


class FakeBeam:
    def __init__(self):
        self.calls = []
        self.result = {'visible': True, 'end_visible': True, 'grip_base_m': [.40, .03],
                       'axis_heading_rad': .1, 'std_xy_m': .001, 'std_yaw_rad': .001}

    def __call__(self, image, servo, role):
        self.calls.append((image.copy(), dict(servo), role))
        return copy.deepcopy(self.result)


class Guard:
    def __init__(self):
        self.calls, self.allowed = [], True

    def __call__(self, action, report, servo, phase):
        self.calls.append((action, report, servo, phase))
        return self.allowed


def controller(index=0, role='end_neg', condition='no_comm', assignment=None,
               initial_servo=None, search_servo=None, provider=None):
    static, sheet, order = public_inputs(index)
    p, beam, guard = provider or FakeProvider(), FakeBeam(), Guard()
    initial = [{'kind': 'initial_servo_command', 't': 0., 'pulses': dict(SERVO if initial_servo is None else initial_servo)},
               {'kind': 'mecanum', 't': .1, 'forward': .03, 'left': 0., 'turn': 0., 'duration_s': .1},
               {'kind': 'hold', 't': .2}]
    # Pretend earlier owned port commands were already consumed, exactly once.
    for row in initial:
        p.on_command(copy.deepcopy(row))
    memory = ba.OwnApproachMemory(p, initial)
    assignment = assignment or {'end_neg': 'r1', 'end_pos': 'r2'}
    ctl = ba.BeamApproach(static, sheet, order, robot_id=assignment[role], role_assignment=assignment,
                          task_id='beam-approach', condition=condition, memory=memory,
                          observe_beam=beam, command_clear=guard, search_servo=SERVO if search_servo is None else search_servo,
                          started_at=0.)
    return ctl, p, beam, guard


def image(ctl, now, fid, *, pixels=None, **updates):
    if pixels is None:
        pixels = np.arange(48*64*3, dtype=np.uint8).reshape(48, 64, 3)
    ok, jpeg = cv2.imencode('.jpg', pixels)
    assert ok
    data = jpeg.tobytes()
    return {'robot_id': ctl.robot_id, 'camera': 'robot_cam', 'frame_id': fid, 'sim_time': now,
            'sha256': hashlib.sha256(data).hexdigest(), 'image': base64.b64encode(data).decode(), **updates}


def status(ctl, now, state='busy', seq=1):
    return {'robot_id': ctl.peer, 'task_id': 'beam-approach', 'seq': seq, 'state': state,
            'sent_at_s': now, 'observed_at_s': None, 'frame_id': None, 'ready_until_s': None}


def step(ctl, now, fid, *, ack=True, obs=None):
    ctl.receive_status(status(ctl, now, seq=fid+1), now)
    decision = ctl.tick(now, obs if obs is not None else image(ctl, now, fid))
    if ack and decision.action:
        assert ctl.on_command({'t': now, **decision.action})
    return decision


def enter_alignment(ctl, p):
    p.pose = ctl.goal
    assert step(ctl, .3, 1).phase == 'approaching'
    assert step(ctl, .5, 2).phase == 'aligning'


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('role,heading', [('end_neg', math.pi/2), ('end_pos', -math.pi/2)])
def test_new_prestation_headings_and_true_history_handoff(index, role, heading):
    ctl, p, beam, guard = controller(index, role)
    memory, loc, history, servo = ctl.memory, p.loc, ctl.memory.history, ctl.memory.servo
    before = copy.deepcopy(history)
    assert ctl.goal[2] == pytest.approx(heading, abs=1e-6)
    assert math.dist(ctl.goal[:2], ctl.plan['roles'][role]['station_xyyaw'][:2]) == pytest.approx(.25)
    # A genuine controller-issued turn at the fake starting observation, not a reset.
    first = step(ctl, .3, 1)
    assert first.action['kind'] == 'mecanum'
    assert math.copysign(1., first.action['turn']) == math.copysign(1., heading)
    assert p.loc is loc and ctl.alignment_entry is None
    # Fake RGB-localizer receipt after movement; no production assignment of pose.
    p.pose = ctl.goal
    assert step(ctl, .5, 2).phase == 'approaching'
    assert step(ctl, .7, 3).phase == 'aligning'
    assert ctl.handoff() is memory
    assert ctl.handoff().provider is p and p.loc is loc
    assert ctl.handoff().history is history and ctl.handoff().servo is servo
    assert history[:len(before)] == before and len(history) == len(before)+3
    assert p.commands == history
    assert ctl.alignment_entry['history_count'] == len(history)-1
    assert ctl.alignment_entry['history_sha256'] == bp.digest(history[:-1])
    assert guard.calls and not beam.calls
    correction = step(ctl, .9, 4)
    assert correction.action == {'kind': 'mecanum', 'forward': .04, 'left': .018,
                                 'turn': pytest.approx(.06), 'duration_s': .1}
    assert beam.calls[-1][1:] == (SERVO, role)
    beam.result.update(grip_base_m=[.2032, 0.], axis_heading_rad=0.)
    assert step(ctl, 1.1, 5).phase == 'aligning'
    assert step(ctl, 1.3, 6).phase == 'aligned'
    assert ctl.handoff() is memory and p.commands == history
    assert ctl.audit['delivery_success'] is None
    assert not any(e.get('event') == 'delivered' for e in ctl.events)


def test_real_static_navigation_commands_from_own_pose_and_no_path():
    ctl, p, _, guard = controller()
    p.pose = (ctl.goal[0]-.5, ctl.goal[1]-.25, ctl.goal[2])
    d = step(ctl, .3, 1)
    assert d.phase == 'approaching' and d.action['kind'] == 'mecanum'
    assert d.action['forward'] > 0 and d.action['left'] < 0
    assert len(guard.calls) == 1
    ctl2, p2, _, _ = controller()
    # Opposite-role corridor must not be used as the approach start.
    opposite = ctl2.plan['roles']['end_pos']['prestation_xyyaw']
    p2.pose = (*opposite[:2], ctl2.goal[2])
    d = step(ctl2, .3, 1)
    assert d.reason == 'APPROACH_NO_PATH' and d.status == 'abort'
    assert d.action == {'kind': 'hold'}


@pytest.mark.parametrize('fault', ['std', 'uninitialized', 'nan', 'negative_std', 'gt', 'stale_fix', 'future_fix'])
def test_self_pose_uncertain_stops_without_hidden_reset(fault):
    ctl, p, beam, guard = controller()
    original_loc = p.loc
    if fault == 'std': p.std = .026
    if fault == 'uninitialized': p.initialized = False
    if fault == 'nan': p.pose = (float('nan'), 0., 0.)
    if fault == 'negative_std': p.std = -.001
    if fault == 'gt': p.source = 'gt_stub_eval_only'
    if fault == 'stale_fix': p.fix_offset = 2.001
    if fault == 'future_fix': p.fix_offset = -.01
    a = step(ctl, .3, 1)
    assert a.status == 'uncertain' and a.action == {'kind': 'hold'}
    assert step(ctl, 30.3, 2).reason == 'SELF_POSE_UNCERTAIN'
    assert p.loc is original_loc and not beam.calls and not guard.calls
    p.std = .001
    assert step(ctl, 30.5, 3).phase == 'failed'  # failure is sticky
    with pytest.raises(ValueError, match='HANDOFF_NOT_READY'): ctl.handoff()


@pytest.mark.parametrize('fault', ['camera', 'robot', 'stale', 'future', 'hash', 'base64', 'black', 'nan_time', 'bool_frame'])
def test_invalid_own_images_never_reach_provider_or_motion(fault):
    ctl, p, _, guard = controller()
    obs = image(ctl, .3, 1)
    if fault == 'camera': obs['camera'] = 'top_cam'
    if fault == 'robot': obs['robot_id'] = ctl.peer
    if fault == 'stale': obs['sim_time'] = .049
    if fault == 'future': obs['sim_time'] = .301
    if fault == 'hash': obs['sha256'] = '0'*64
    if fault == 'base64': obs['image'] = '!!!!'
    if fault == 'black': obs = image(ctl, .3, 1, pixels=np.zeros((48, 64, 3), np.uint8))
    if fault == 'nan_time': obs['sim_time'] = float('nan')
    if fault == 'bool_frame': obs['frame_id'] = True
    d = step(ctl, .3, 1, obs=obs)
    assert d.reason == 'OWN_IMAGE_INVALID' and d.status == 'abort'
    assert not p.images and not guard.calls


def test_repeated_frame_cannot_confirm_arrival_or_alignment():
    ctl, p, beam, _ = controller()
    p.pose = ctl.goal
    obs = image(ctl, .3, 1)
    assert step(ctl, .3, 1, obs=obs).phase == 'approaching'
    d = ctl.tick(.4, obs)
    assert d.phase == 'approaching' and len(p.images) == 1
    assert ctl.on_command({'t': .4, **d.action})
    step(ctl, .5, 2)
    beam.result.update(grip_base_m=[.2032, 0.], axis_heading_rad=0.)
    obs = image(ctl, .7, 3)
    step(ctl, .7, 3, obs=obs)
    d = ctl.tick(.8, obs)
    assert d.phase == 'aligning' and len(beam.calls) == 1


def test_arm_transition_uses_issued_servo_and_waits_for_ack_and_image_after_settle():
    ctl, p, _, guard = controller()
    ctl.search_servo[3] = 780
    old = dict(ctl.memory.servo)
    d = step(ctl, .3, 1, ack=False)
    assert d.action == {'kind': 'arm', 'servo_id': 3, 'pulse': 760, 'duration_s': .1}
    assert ctl.memory.servo == old and len(ctl.memory.history) == 3
    assert ctl.tick(.35, image(ctl, .35, 2)).action == {}
    assert ctl.on_command({'t': .3, **d.action})
    assert ctl.memory.servo[3] == 760
    assert step(ctl, .35, 2).action == {'kind': 'hold'}
    assert step(ctl, .5, 3).action['pulse'] == 780
    assert len(guard.calls) == 2 and len(p.commands) == len(ctl.memory.history)


@pytest.mark.parametrize('fault', ['missing_ack', 'wrong_ack', 'guard'])
def test_command_failures_stop_and_do_not_forge_history(fault):
    ctl, p, _, guard = controller()
    before = copy.deepcopy(ctl.memory.history)
    if fault == 'guard': guard.allowed = False
    d = step(ctl, .3, 1, ack=False)
    if fault == 'missing_ack': d = ctl.tick(.8, image(ctl, .8, 2))
    if fault == 'wrong_ack':
        assert not ctl.on_command({'t': .3, 'kind': 'hold'})
        d = ctl.tick(.5, image(ctl, .5, 2))
    assert d.phase == 'failed' and d.status == 'abort' and d.action == {'kind': 'hold'}
    assert ctl.memory.history == before and p.commands == before


@pytest.mark.parametrize('fault', ['abort', 'missing', 'expired', 'private_status'])
def test_delivered_status_failure_is_terminal(fault):
    ctl, p, _, guard = controller()
    if fault == 'abort': ctl.receive_status(status(ctl, .3, 'abort'), .3)
    if fault == 'expired': ctl.receive_status(status(ctl, .3), .3)
    if fault == 'private_status': ctl.receive_status({**status(ctl, .3), 'partner_pose': [1, 2, 3]}, .3)
    t = .3 if fault in ('abort', 'private_status') else 5.2
    d = ctl.tick(t, image(ctl, t, 1))
    assert d.phase == 'failed' and d.status == 'abort' and d.action == {'kind': 'hold'}
    assert not guard.calls and not p.images


@pytest.mark.parametrize('field,value', [('grip_base_m', [-.2, 0.]), ('axis_heading_rad', math.pi),
                                         ('grip_base_m', [.3, .2])])
def test_cross_approach_relative_refusal(field, value):
    ctl, p, beam, _ = controller()
    enter_alignment(ctl, p)
    beam.result[field] = value
    d = step(ctl, .7, 3)
    assert d.reason == 'CROSS_APPROACH_OR_WRONG_END' and d.action == {'kind': 'hold'}


@pytest.mark.parametrize('fault', ['missing', 'nan', 'std', 'clipped'])
def test_relative_failure_status_without_reset(fault):
    ctl, p, beam, _ = controller()
    enter_alignment(ctl, p)
    loc = p.loc
    if fault == 'missing': beam.result = {}
    if fault == 'nan': beam.result['grip_base_m'][0] = float('nan')
    if fault == 'std': beam.result['std_xy_m'] = .013
    if fault == 'clipped': beam.result['end_visible'] = False
    assert step(ctl, .7, 3).action == {'kind': 'hold'}
    assert step(ctl, 5.7, 4).reason == 'RELATIVE_BEAM_UNCERTAIN'
    assert p.loc is loc


@pytest.mark.parametrize('condition', ba.CONDITIONS)
def test_private_noninterference_and_four_condition_same_control(condition):
    def trace(private):
        ctl, p, beam, _ = controller(condition=condition)
        actions = []
        for i, t in enumerate((.3, .5, .7)):
            # Private data never enters constructor/provider/observer arguments;
            # extra host metadata in a frame is not forwarded either.
            obs = image(ctl, t, i+1, evaluation=copy.deepcopy(private))
            actions.append(step(ctl, t, i+1, obs=obs))
        return actions, {k: v for k, v in ctl.audit.items() if k != 'condition'}, p.images, ctl.memory.frames
    a = trace({'partner_pose': [1, 2, 3], 'contact': True, 'event_time': 12, 'held': True})
    b = trace({'partner_pose': [9, 8, 7], 'contact': False, 'event_time': 999, 'held': False})
    assert a[:2] == b[:2] and a[3] == b[3]
    assert all(np.array_equal(x[1], y[1]) for x, y in zip(a[2], b[2]))
    ref, _, _, _ = controller(condition='no_comm')
    assert a[1] == {k: v for k, v in ref.audit.items() if k != 'condition'}


def test_sim_cap_includes_posture_and_staging_and_boundary_is_failure():
    ctl, p, _, guard = controller()
    ctl.search_servo[3] = 780
    step(ctl, .3, 1)
    ctl.receive_status(status(ctl, 900., seq=3), 900.)
    d = ctl.tick(900., image(ctl, 900., 2))
    assert d.reason == 'APPROACH_ALIGNMENT_TIMEOUT' and d.status == 'abort'
    assert ctl.alignment_entry is None


@pytest.mark.parametrize('role_assignment', [{'end_neg': 'r1', 'end_pos': 'r1'},
                                            {'end_neg': 'r1', 'end_pos': 'r4'}])
def test_unsupported_role_mapping(role_assignment):
    with pytest.raises(ValueError, match='ROLE_ASSIGNMENT'): controller(assignment=role_assignment)


def test_t08a_source_grid_range_and_original_bytes_still_enforced():
    static, sheet, order = public_inputs()
    p = FakeProvider()
    memory = ba.OwnApproachMemory(p, [{'t': 0., 'kind': 'initial_servo_command', 'pulses': SERVO}])
    kwargs = dict(robot_id='r1', role_assignment={'end_neg': 'r1', 'end_pos': 'r2'}, task_id='t',
                  condition='no_comm', memory=memory, observe_beam=FakeBeam(), command_clear=Guard(),
                  search_servo=SERVO, started_at=0.)
    sheet['coarse']['source'] = 'private live beam pose'
    with pytest.raises(bp.PlanRefusal, match='UNTRUSTED'): ba.BeamApproach(static, sheet, order, **kwargs)
    static, sheet, order = public_inputs()
    sheet['initial_error_bound']['xy_per_axis_m'] = 0.
    with pytest.raises(bp.PlanRefusal, match='BINDING'): ba.BeamApproach(static, sheet, order, **kwargs)


def test_v3_relative_target_is_not_legacy_point_one_five_five():
    ctl, p, beam, _ = controller()
    enter_alignment(ctl, p)
    beam.result.update(grip_base_m=[.155, 0.], axis_heading_rad=0.)
    d = step(ctl, .7, 3)
    assert d.phase == 'aligning' and d.action['forward'] < 0
    assert ctl.aligned_streak == 0


def test_world_estimate_cannot_jump_to_other_end_after_handoff():
    ctl, p, beam, guard = controller()
    enter_alignment(ctl, p)
    p.pose = tuple(ctl.plan['roles']['end_pos']['prestation_xyyaw'])
    assert step(ctl, .7, 3).reason == 'CROSS_APPROACH_OR_WRONG_END'
    assert not beam.calls and not guard.calls


def test_uncertainty_after_entry_blocks_handoff_and_never_refills_deadline():
    ctl, p, _, _ = controller()
    enter_alignment(ctl, p)
    p.std = .026
    d = step(ctl, .7, 3)
    assert d.status == 'uncertain' and d.action == {'kind': 'hold'}
    with pytest.raises(ValueError, match='HANDOFF_NOT_READY'): ctl.handoff()
    assert ctl.started_at == 0.


@pytest.mark.parametrize('fault', ['frame_time_repeat', 'frame_id_regress', 'frame_rewrite'])
def test_frame_identity_counterexamples(fault):
    ctl, p, _, _ = controller()
    p.pose = ctl.goal
    step(ctl, .3, 1)
    if fault == 'frame_time_repeat': obs = image(ctl, .3, 2)
    if fault == 'frame_id_regress': obs = image(ctl, .4, 0)
    if fault == 'frame_rewrite': obs = image(ctl, .4, 1)
    assert step(ctl, .4, 2, obs=obs).reason == 'OWN_IMAGE_INVALID'
    assert len(p.images) == 1


@pytest.mark.parametrize('component', ['guard', 'observer'])
def test_dependency_errors_fail_closed(component):
    ctl, p, _, _ = controller()
    def broken(*args):
        raise RuntimeError('dependency unavailable')
    if component == 'guard':
        ctl.command_clear = broken
        d = step(ctl, .3, 1)
        assert d.reason == 'COMMAND_GUARD_ERROR'
    else:
        enter_alignment(ctl, p)
        ctl.observe_beam = broken
        d = step(ctl, .7, 3)
        assert d.reason == 'RELATIVE_OBSERVER_ERROR'
    assert d.status == 'abort' and d.action == {'kind': 'hold'}


@pytest.mark.parametrize('role', bp.ROLES)
def test_r3_role_selection_does_not_route_commands_to_another_actor(role):
    assignment = {'end_neg': 'r3' if role == 'end_neg' else 'r1',
                  'end_pos': 'r3' if role == 'end_pos' else 'r2'}
    ctl, p, _, _ = controller(role=role, assignment=assignment)
    assert ctl.robot_id == 'r3'
    enter_alignment(ctl, p)
    assert all(f['robot_id'] == 'r3' for f in ctl.memory.frames)
    assert ctl.audit['role_assignment_sha256'] == bp.digest(assignment)


def test_continuous_route_sweep_is_checked_after_grid_planning(monkeypatch):
    ctl, p, _, guard = controller()
    p.pose = (ctl.goal[0]-.5, ctl.goal[1]-.2, ctl.goal[2])
    # A broken upstream planner routes through the public beam then to goal.
    monkeypatch.setattr(ba, 'plan_path', lambda *a, **k: {
        'waypoints_m': [p.pose[:2], CASES[0][1][:2], ctl.goal[:2]]})
    d = step(ctl, .3, 1)
    assert d.reason == 'APPROACH_SWEEP_BLOCKED' and not guard.calls


def test_condition_traces_are_identical_not_just_metadata():
    traces = []
    for condition in ba.CONDITIONS:
        ctl, p, beam, _ = controller(condition=condition)
        actions = [step(ctl, .3, 1)]
        p.pose = ctl.goal
        actions.extend([step(ctl, .5, 2), step(ctl, .7, 3), step(ctl, .9, 4)])
        beam.result.update(grip_base_m=[.2032, 0.], axis_heading_rad=0.)
        actions.extend([step(ctl, 1.1, 5), step(ctl, 1.3, 6)])
        traces.append((actions, ctl.events, ctl.memory.history, ctl.memory.frames))
    assert all(trace == traces[0] for trace in traces)


@pytest.mark.parametrize('method', ['on_frame', 'report'])
def test_provider_failure_does_not_recreate_it_or_emit_motion(method):
    ctl, p, _, guard = controller()
    old = p.loc
    def broken(*args):
        raise RuntimeError('provider unavailable')
    setattr(p, method, broken)
    d = step(ctl, .3, 1)
    assert d.reason == 'POSE_PROVIDER_ERROR' and d.action == {'kind': 'hold'}
    assert ctl.memory.provider is p and p.loc is old and not guard.calls


def test_issued_command_is_retained_even_if_provider_rejects_it():
    ctl, p, _, _ = controller()
    d = step(ctl, .3, 1, ack=False)
    def broken(row):
        raise RuntimeError('provider unavailable')
    p.on_command = broken
    row = {'t': .3, **d.action}
    assert not ctl.on_command(row)
    assert ctl.memory.history[-1] == row
    result = ctl.tick(.4, image(ctl, .4, 2))
    assert result.reason == 'POSE_PROVIDER_COMMAND_ERROR' and result.action == {'kind': 'hold'}


def test_controller_and_assignment_hashes_are_separate():
    ctl, _, _, _ = controller()
    assert ctl.audit['controller_code_sha256'] == hashlib.sha256((ROOT/'harness/beam_approach.py').read_bytes()).hexdigest()
    assert ctl.audit['role_assignment_sha256'] == bp.digest({'end_neg': 'r1', 'end_pos': 'r2'})
    assert ctl.audit['search_servo_sha256'] == bp.digest(SERVO)


@pytest.mark.parametrize('role', bp.ROLES)
@pytest.mark.parametrize('condition', ba.CONDITIONS)
@pytest.mark.parametrize('json_keys', [False, True])
def test_native_pwm_posture_navigation_and_handoff_keep_provider_history(role, condition, json_keys):
    from types import SimpleNamespace
    from harness.owncam_pose_source import OwnCamPoseSource

    class NativeBookkeepingProvider(FakeProvider):
        # Exercise the actual provider command consumer; only RGB localization
        # is fake. No PF initialization, simulator state or measured joint input.
        def __init__(self):
            super().__init__()
            self.loc = SimpleNamespace(command=lambda row: self.commands.append(copy.deepcopy(row)))

        on_command = OwnCamPoseSource.on_command

    initial = {**SEARCH_POSE, 3: 700, 6: 1460}
    if json_keys:
        initial = {str(k): v for k, v in initial.items()}
    ctl, p, beam, guard = controller(role=role, condition=condition, initial_servo=initial,
                                     provider=NativeBookkeepingProvider())
    memory, loc, history, servo = ctl.memory, p.loc, ctl.memory.history, ctl.memory.servo
    prefix = copy.deepcopy(history)
    assert servo == p.servo == {int(k): v for k, v in initial.items()}
    for fid, t, expected in [
        (1, .3, {'kind': 'arm', 'servo_id': 3, 'pulse': 720, 'duration_s': .1}),
        (2, .5, {'kind': 'arm', 'servo_id': 3, 'pulse': 740, 'duration_s': .1}),
        (3, .7, {'kind': 'look', 'pan_pulse': 1480, 'duration_s': .1}),
        (4, .9, {'kind': 'look', 'pan_pulse': 1500, 'duration_s': .1}),
    ]:
        assert step(ctl, t, fid).action == expected
        assert p.servo == servo and p.commands == history
        assert servo[1] == 2000 and set(servo) == {1, 3, 4, 5, 6}
    assert p.servo == servo == SEARCH_POSE
    p.pose = (ctl.goal[0] - .5, ctl.goal[1] - .25, ctl.goal[2])
    assert step(ctl, 1.1, 5).action['kind'] == 'mecanum'
    p.pose = ctl.goal  # fake next RGB estimate, not a production state/reset hook
    assert step(ctl, 1.3, 6).phase == 'approaching'
    assert step(ctl, 1.5, 7).phase == 'aligning'
    assert ctl.handoff() is memory and memory.provider is p and p.loc is loc
    assert memory.history is history and memory.servo is servo
    assert history[:len(prefix)] == prefix and history[0]['pulses'] == initial
    assert ctl.alignment_entry['servo'] == SEARCH_POSE
    assert ctl.alignment_entry['history_sha256'] == bp.digest(history[:-1])
    beam.result.update(grip_base_m=[.2032, 0.], axis_heading_rad=0.)
    assert step(ctl, 1.7, 8).phase == 'aligning'
    assert step(ctl, 1.9, 9).phase == 'aligned'
    assert ctl.handoff() is memory and p.commands == history and p.servo == SEARCH_POSE
    assert all(call[1] == SEARCH_POSE for call in beam.calls)
    assert guard.calls and ctl.audit['delivery_success'] is None


@pytest.mark.parametrize('location', ['initial', 'search'])
@pytest.mark.parametrize('fault', ['missing', 'inactive', 'unknown', 'bool_channel', 'fractional_channel',
                                 'duplicate_channel', 'low', 'high', 'fractional_pwm', 'bool_pwm', 'nan'])
def test_native_servo_contract_rejects_missing_unknown_or_noninteger_values(location, fault):
    pulses = dict(SEARCH_POSE)
    if fault == 'missing': del pulses[3]
    if fault == 'inactive': pulses[2] = 1500
    if fault == 'unknown': pulses[7] = 1500
    if fault == 'bool_channel':
        del pulses[1]
        pulses[True] = 2000
    if fault == 'fractional_channel': pulses[3.5] = 1500
    if fault == 'duplicate_channel': pulses['3'] = pulses[3]
    if fault == 'low': pulses[3] = 499
    if fault == 'high': pulses[3] = 2501
    if fault == 'fractional_pwm': pulses[3] = 740.5
    if fault == 'bool_pwm': pulses[3] = True
    if fault == 'nan': pulses[3] = float('nan')
    error = 'ISSUED_SERVO' if location == 'initial' else 'OPEN_SEARCH_POSTURE_REQUIRED'
    with pytest.raises(ValueError, match=error):
        controller(**{location + '_servo' if location == 'initial' else 'search_servo': pulses})


@pytest.mark.parametrize('kind', ['arm', 'look'])
@pytest.mark.parametrize('pulse', [499, 2501, 740.5, True, float('nan')])
def test_bad_incremental_pwm_cannot_be_clamped_or_truncated(kind, pulse):
    row = ({'kind': 'arm', 'servo_id': 3, 'pulse': pulse} if kind == 'arm' else
           {'kind': 'look', 'pan_pulse': pulse})
    history = [{'t': 0., 'kind': 'initial_servo_command', 'pulses': dict(SEARCH_POSE)},
               {'t': .1, **row}]
    before = copy.deepcopy(history[0])
    with pytest.raises(ValueError, match='BAD_ISSUED_SERVO'):
        ba.OwnApproachMemory(object(), history)
    assert history[0] == before and history[1]['kind'] == kind


@pytest.mark.parametrize('pulse', [500, 2500])
def test_native_pwm_endpoints_and_json_keys_are_preserved(pulse):
    pose = {**SEARCH_POSE, 3: pulse, 6: pulse}
    serialized = {str(k): v for k, v in pose.items()}
    ctl, p, _, _ = controller(initial_servo=serialized, search_servo=serialized)
    assert ctl.memory.servo == ctl.search_servo == pose
    assert ctl.memory.history[0]['pulses'] == serialized
    p.pose = ctl.goal
    assert step(ctl, .3, 1).phase == 'approaching'


@pytest.mark.parametrize('location', ['initial_servo', 'search_servo'])
@pytest.mark.parametrize('pulse', [500, 1500, 1999, 2000, 2500])
def test_open_gripper_threshold_is_native_pwm(location, pulse):
    kwargs = {location: {**SEARCH_POSE, 1: pulse}}
    if pulse < 2000:
        with pytest.raises(ValueError, match='OPEN_SEARCH_POSTURE_REQUIRED'):
            controller(**kwargs)
    else:
        ctl, _, _, _ = controller(**kwargs)
        assert ctl.memory.servo[1] >= 2000 and ctl.search_servo[1] >= 2000
