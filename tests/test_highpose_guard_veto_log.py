"""v98 PAIR_COLLISION_GUARD evidence log (probe 3358372e raise_high: r1 failed at 8.7 s with no trace of why).

Simulator-free. Fixtures are the recorded r1/r2 guard inputs of the 8.7 s tick (command, own estimate, issued servo
PWM), obtained by replaying the recorded own frames through the real v98 Runtime offline (every replayed command
equalled the recorded one). The log only observes: the recording geometry must answer exactly like ``PairGeometry``.
"""
from __future__ import annotations

import itertools
import math
import types

import pytest

from harness import zone_own_guards as g
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_guardlog as gl
from harness import zone_pair_highpose_runtime as rt
from harness.owncam_pose_source import PoseReport
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard, PairArmGuard, PairGeometry
from tests.test_zone_final_pair_v3 import MAPS

BEAM = {'center_m': [0., 0., .016], 'half_extents_m': [.3, .02, .016],
        'grasps': {'end_neg': {'xyz_m': [-.27, 0., .024], 'yaw_rad': 0.},
                   'end_pos': {'xyz_m': [.27, 0., .024], 'yaw_rad': 3.141592653589793}}}
SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}          # issued reset posture at 8.7 s
R1 = dict(role='end_neg', pose=(-0.8700080262285412, 0.5653211382897314, -0.009271600544431102,
                                0.01936797860813731, 0.0026647544256222467),
          cmd={'kind': 'mecanum', 'forward': 0.11274498977490782, 'left': -0.027394786857323616, 'turn': 0.0,
               'duration_s': 0.15},
          cov=((0.00036097, -6.645e-05, 3.217e-05), (-6.645e-05, 1.415e-05, -6.36e-06), (3.217e-05, -6.36e-06, 7.1e-06)))
R2 = dict(role='end_pos', pose=(-0.9369527160577948, -0.8785887011813964, 0.02514818367963967,
                                0.002522724436345828, 0.0023083912740434276),
          cmd={'kind': 'mecanum', 'forward': 0.11925038890234238, 'left': 0.008927977166440747, 'turn': 0.0,
               'duration_s': 0.15},
          cov=((2.28e-06, 6.5e-07, -5.4e-07), (6.5e-07, 4.08e-06, -1.41e-06), (-5.4e-07, -1.41e-06, 5.33e-06)))


@pytest.fixture(scope='module')
def arm():
    return PairArmGuard(c.resolve(MAPS[0])[0])


def geometry(arm, role, *, recorded=True):
    geo, trace = PairGeometry(arm, BEAM, role), gl.Trace()
    return (gl.recording(geo, trace), trace) if recorded else (geo, None)


# ------------------------------------------------------------------ the recorded 8.7 s vetoes
@pytest.mark.parametrize('fixture, clearance_mm, raw_mm, corner', [(R1, -55.31114977748346, 4.163988824633334, [-.15, -.09]),
                                                                   (R2, -42.61665190012048, 0.0, [-.10, -.09])])
def test_recorded_tick_is_vetoed_by_the_start_sample_rear_corner_against_wall_west(arm, fixture, clearance_mm, raw_mm,
                                                                                   corner):
    geo, trace = geometry(arm, fixture['role'])
    pose = g.OwnPose(*fixture['pose'])
    assert geo.motion_clear(SERVO, pose, fixture['cmd'], loaded=False) is False
    assert trace.calls == 1 and trace.failed_sites == ['motion_clear']        # the very first (unmoved) sample
    row = gl._describe(trace.first, trace.origin)
    assert (row['term'], row['wall_id'], row['site'], row['query_index']) == ('chassis', 'wall_west', 'motion_clear', 0)
    assert row['moved_from_start_mm'] == 0. and row['yaw_offset_rad'] == 0.
    assert row['clearance_mm'] == pytest.approx(clearance_mm, abs=1e-9)
    assert row['raw_mm'] == pytest.approx(raw_mm, abs=1e-9)
    assert row['point_base_m'] == pytest.approx(corner)                       # rear-left of the chassis envelope
    assert row['point_world_m'][0] < -1.0                                     # wall_west's inner face is x = -1.025
    t = row['margin_terms']
    assert row['mirror_matches'] and t['sum_matches']
    assert (t['base_mm'], t['residual_mm']) == (20., 15.)
    cmd = fixture['cmd']                                       # 0.15 s command, 3 samples: pad = |v|*1.6 * 0.05 / 2
    pad_mm = 1000. * math.hypot(cmd['forward'], cmd['left']) * g.BACKOFF_GAIN_MAX * cmd['duration_s'] / 3 / 2
    assert t['motion_pad_mm'] == pytest.approx(pad_mm, abs=1e-9)
    assert t['sigma_xy_mm'] == pytest.approx(min(pose.std_xy, g.SIGMA_CAP_XY_M) * 1000.)
    assert row['raw_mm'] - t['total_mm'] == pytest.approx(row['clearance_mm'], abs=1e-9)
    # The veto does not depend on sigma: with an exact estimate the same corner still violates the same wall.
    exact = g.OwnPose(pose.x, pose.y, pose.yaw, 0., 0.)
    geo0, trace0 = geometry(arm, fixture['role'])
    assert geo0.motion_clear(SERVO, exact, fixture['cmd'], loaded=False) is False
    assert trace0.first['kind'] == 'chassis' and trace0.first['wall_id'] == 'wall_west' and trace0.first['index'] == 0


def test_arm_term_is_reported_with_its_sphere_and_the_bar_when_loaded(arm):
    geo, trace = geometry(arm, 'end_neg')
    servo = {1: 1500, 3: 1500, 4: 1500, 5: 1500, 6: 1500}
    pose = g.OwnPose(-.95, .55, 0., .01, .003)
    clearance, wall = geo.arm_clearance(servo, pose, loaded=True)
    assert clearance < 0. and wall == 'wall_west' and trace.first['kind'] == 'arm'
    row = gl._describe(trace.first, trace.origin)
    assert row['mirror_matches'] and row['margin_terms']['sum_matches'] and row['part'] == 'beam'
    assert row['servo_pwm'] == {str(k): v for k, v in sorted(servo.items())} and row['loaded'] is True
    assert row['clearance_mm'] == pytest.approx(clearance * 1000.)
    unloaded, trace2 = geometry(arm, 'end_neg')
    assert unloaded.arm_clearance(servo, pose, loaded=False)[0] >= 0. and trace2.first is None   # nothing recorded


def test_plan_and_transition_sites_are_named(arm):
    geo, trace = geometry(arm, 'end_neg')
    pose = g.OwnPose(-1., .55, 0., .01, .003)
    out = geo.plan(SERVO, {**SERVO, 3: 1072}, [1500], pose, loaded=False, allow_backoff=False)
    assert out['reason'] != 'clear' or not out.get('transition_clear', False)
    assert trace.failed_sites[-1] == 'plan' and trace.first['site'].startswith('plan')
    assert trace.plan_result == {'reason': out['reason'], 'transition_clear': out.get('transition_clear')}
    geo2, trace2 = geometry(arm, 'end_neg')
    assert geo2.transition_clear(SERVO, {**SERVO, 3: 1072}, pose, loaded=False) is False
    assert trace2.failed_sites == ['transition_clear'] and trace2.first['site'] == 'transition_clear'


# ------------------------------------------------------------------ observation only
def test_recording_geometry_answers_bit_for_bit_like_the_shared_geometry(arm):
    servos = (SERVO, {1: 2000, 3: 1072, 4: 2400, 5: 1482, 6: 1500}, {1: 1500, 3: 1500, 4: 1500, 5: 1500, 6: 1500})
    poses = [g.OwnPose(x, y, yaw, sxy, syaw) for x, y, yaw, (sxy, syaw) in itertools.product(
        (-.97, -.9, -.8, -.6), (.55, -.85), (-.1, .08), ((.0025, .0023), (.0194, .0027), (.08, .02)))]
    cmds = [{'kind': 'mecanum', 'forward': f, 'left': l, 'turn': w, 'duration_s': d}
            for f, l, w, d in ((.11, -.027, 0., .15), (-.08, 0., 0., .3), (0., .06, .3, .2), (.1, 0., -.4, .5))]
    plain, rec = PairGeometry(arm, BEAM, 'end_pos'), PairGeometry(arm, BEAM, 'end_pos')
    gl.recording(rec, gl.Trace())
    assert type(rec) is gl.RecordingGeometry and type(plain) is PairGeometry
    for pose, servo, loaded in itertools.product(poses, servos, (False, True)):
        assert rec.arm_clearance(servo, pose, loaded=loaded) == plain.arm_clearance(servo, pose, loaded=loaded)
        assert rec.chassis_clearance(pose) == plain.chassis_clearance(pose)
        assert rec.transition_clear(SERVO, servo, pose, loaded=loaded) == plain.transition_clear(SERVO, servo, pose, loaded=loaded)
    for pose, cmd, loaded in itertools.product(poses, cmds, (False, True)):
        assert rec.motion_clear(SERVO, pose, cmd, loaded=loaded) == plain.motion_clear(SERVO, pose, cmd, loaded=loaded)
        assert (rec.residual, rec._loaded_motion) == (plain.residual, plain._loaded_motion) == (rec.residual0, False)
    for pose in poses[:6]:
        assert rec.plan(SERVO, servos[1], [1400, 1500], pose, loaded=False, allow_backoff=True) == \
            plain.plan(SERVO, servos[1], [1400, 1500], pose, loaded=False, allow_backoff=True)


def test_recording_installs_only_on_the_exact_shared_geometry_class(arm):
    geo, trace = PairGeometry(arm, BEAM, 'end_neg'), gl.Trace()
    assert gl.recording(geo, None) is geo and type(geo) is PairGeometry
    assert not hasattr(PairGeometry, 'trace') and not hasattr(PairGeometry, 'residual0')

    class Other(PairGeometry):
        pass
    other = Other(arm, BEAM, 'end_neg')
    assert gl.recording(other, trace) is other and type(other) is Other
    assert gl.recording(geo, trace) is geo and type(geo) is gl.RecordingGeometry


# ------------------------------------------------------------------ the CommandGuard hook
def stand_in(fixture, *, carrying=False):
    pose = fixture['pose']
    report = PoseReport(8.54, True, pose[0], pose[1], pose[2], fixture['cov'], pose[3], pose[4], .04,
                        source='replayed_estimate', last_fix_t=8.5, fix_age_s=.04)
    own = types.SimpleNamespace(robot_id='r1', events=[], servo=dict(SERVO), last_report=report,
                                guard=PairArmGuard(c.resolve(MAPS[0])[0]))
    ep = types.SimpleNamespace(own=own, plan={'beam_geometry': BEAM}, arguments={'role': fixture['role']}, events=[],
                               controller=types.SimpleNamespace(state='approach', beam_grasp_confirmed=carrying))
    ep.log = lambda rid, kind, now, **detail: ep.events.append({'robot_id': rid, 'event': kind, 'sim_s': now, **detail})
    guard = object.__new__(rt.CommandGuard)
    guard.ep = ep
    return guard


def parent_check(abort_reason=None):
    """Stand-in for the frozen ``PairCommandGuard.check``: query the sweep guard, abort the job when not clear."""
    def check(self, now, commands):
        own = self.ep.own
        servo, pose = dict(own.servo), g.OwnPose.from_report(own.last_report)
        reason = abort_reason
        if reason is None:
            for cmd in commands:
                if not self.sweep_guard().motion_clear(servo, pose, cmd, loaded=self.carrying_beam):
                    reason = 'PAIR_COLLISION_GUARD'
        if reason:
            own.events.append({'sim_s': now, 'event': 'job_failed', 'detail': {'reason': reason}})
            return [{'kind': 'hold'}]
        return commands
    return check


# R1's own recorded command is now admitted by the v98 start-state relief (test_highpose_start_relief); the veto log is
# exercised with a command that moves the rear toward the wall, which both the frozen guard and the relief refuse.
TOWARD = {'kind': 'mecanum', 'forward': -.11, 'left': 0., 'turn': 0., 'duration_s': .15}


def test_hook_logs_one_veto_event_with_command_estimate_and_term(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard = stand_in(R1)
    commands = [dict(TOWARD)]
    assert guard.check(8.7, commands) == [{'kind': 'hold'}]
    assert guard.veto_trace is None and rt.CommandGuard.veto_trace is None
    [event] = guard.ep.events
    assert event['event'] == gl.EVENT and event['reason'] == 'PAIR_COLLISION_GUARD' and event['sim_s'] == 8.7
    assert event['commands'] == [TOWARD] and event['site'] == 'motion_clear' and event['queries'] == 1
    assert event['start_relief']['refusal']['why'] == 'pair_worse_than_floor' and event['relief_notes'] == []
    assert event['estimate']['cov'] == [list(row) for row in R1['cov']] and event['estimate']['std_xy_m'] == R1['pose'][3]
    assert event['servo_pwm'] == {str(k): v for k, v in sorted(SERVO.items())} and event['loaded'] is False
    first = event['first_negative']
    assert (first['term'], first['wall_id']) == ('chassis', 'wall_west') and first['mirror_matches']
    assert first['clearance_mm'] == pytest.approx(-55.07013142952537, abs=1e-9) and first['query_index'] == 0
    assert event['minimum_is_first_negative'] is True and event['minimum'] is None
    import json
    json.dumps(guard.ep.events)                                                    # the record is JSON-serializable


def test_hook_is_silent_without_a_collision_veto_and_returns_the_parents_answer(monkeypatch):
    far = {**R1, 'pose': (-.6, .55, 0., .01, .003)}
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard, commands = stand_in(far), [dict(R1['cmd'])]
    assert guard.check(8.7, commands) is commands and guard.ep.events == [] and guard.ep.own.events == []
    monkeypatch.setattr(PreviousGuard, 'check', parent_check('POSE_UNCERTAIN'))
    guard = stand_in(R1)
    assert guard.check(8.7, [dict(R1['cmd'])]) == [{'kind': 'hold'}] and guard.ep.events == []
    assert guard.ep.own.events[-1]['detail'] == {'reason': 'POSE_UNCERTAIN'}


def test_a_log_failure_never_changes_the_run(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    monkeypatch.setattr(gl, '_describe', lambda *a: 1 / 0)
    guard = stand_in(R1)
    assert guard.check(8.7, [dict(TOWARD)]) == [{'kind': 'hold'}]
    [event] = guard.ep.events
    assert event['event'] == gl.EVENT and 'ZeroDivisionError' in event['log_error'] and event['commands'] == [TOWARD]


def test_trace_is_not_shared_between_checks_or_left_installed(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard = stand_in(R1)
    assert type(guard.sweep_guard()) is PairGeometry                                 # outside check(): not recorded
    guard.check(8.7, [dict(TOWARD)])
    assert guard.veto_trace is None and type(guard.sweep_guard()) is PairGeometry


def test_v98_classes_keep_the_frozen_parents_and_the_adoption_record_lists_the_log():
    assert rt.CommandGuard.__mro__[1] is PreviousGuard
    assert rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={}))['guard_veto_log'] == gl.record()
    assert gl.record()['decisions_changed'] is False and gl.record()['shared_sources_modified'] is False
