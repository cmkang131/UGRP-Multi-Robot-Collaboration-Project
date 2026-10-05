"""v98 start-state relief (probe 3358372e raise_high: both robots start inside the 40-60 mm wall margin).

Simulator-free. Fixtures are the recorded r1/r2 guard inputs of the 8.7 s tick (see test_highpose_guard_veto_log).
The relief runs only after the frozen ``motion_clear`` said no and only when a pair already starts negative; every other
answer must be the frozen guard's, bit for bit.
"""
from __future__ import annotations

import itertools
import json
import math
import types

import pytest

from harness import zone_own_guards as g
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_guardlog as gl
from harness import zone_pair_highpose_runtime as rt
from harness import zone_pair_highpose_start_relief as sr
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard, PairArmGuard, PairGeometry
from tests.test_highpose_guard_veto_log import BEAM, R1, R2, SERVO, parent_check, stand_in
from tests.test_zone_final_pair_v3 import MAPS

HIGH = {1: 2000, 3: 1072, 4: 2400, 5: 1482, 6: 1500}


@pytest.fixture(scope='module')
def arm():
    return PairArmGuard(c.resolve(MAPS[0])[0])


def relief_geometry(arm, role, scope=sr.SCOPE):
    geo, trace = PairGeometry(arm, BEAM, role), gl.Trace()
    sr.install(geo, trace)
    geo.scope = scope
    return geo, trace


def drive(forward=0., left=0., turn=0., duration_s=.15):
    return {'kind': 'mecanum', 'forward': forward, 'left': left, 'turn': turn, 'duration_s': duration_s}


# ------------------------------------------------------------------ the recorded 8.7 s ticks
def test_recorded_r1_first_command_is_admitted_and_never_gets_worse(arm):
    geo, trace = relief_geometry(arm, R1['role'])
    plain = PairGeometry(arm, BEAM, R1['role'])
    pose = g.OwnPose(*R1['pose'])
    assert plain.motion_clear(SERVO, pose, R1['cmd'], loaded=False) is False       # the frozen veto of the probe
    assert geo.motion_clear(SERVO, pose, R1['cmd'], loaded=False) is True
    [verdict] = trace.reliefs
    group = verdict['groups']['chassis:wall_west']
    assert group['start_worst_mm'] == pytest.approx(-55.31114977748346, abs=1e-9) and group['pairs'] == 9
    assert group['swept_worst_mm'] == pytest.approx(group['start_worst_mm'], abs=1e-9)      # worst is the start sample
    assert verdict['start_inside_raw'] is False and verdict['refusal'] is None
    assert all(p['worst_change_mm'] >= -1e-9 and p['wall_id'] == 'wall_west' for p in verdict['pairs'])
    assert verdict['frozen_guard_first_negative']['clearance_mm'] == pytest.approx(-55.31114977748346, abs=1e-9)
    assert trace.first is None and trace.calls == 0 and trace.failed_sites == []            # the frozen veto was rolled back
    assert verdict['command'] == R1['cmd'] and verdict['scope'] == 'group'
    json.dumps(verdict)


def test_recorded_r2_is_now_vetoed_because_a_pair_that_starts_outside_the_wall_box_enters_it(arm):
    # Review 5 finding 1: the group floor admitted this tick at 0865a788 (group -42.62 -> -42.71 mm), but a chassis corner
    # that starts 9.64 mm OUTSIDE the west wall box enters it (-9.40 mm at sample 2, -18.9 mm deepest). Not loosened.
    pose = g.OwnPose(*R2['pose'])
    assert PairGeometry(arm, BEAM, R2['role']).motion_clear(SERVO, pose, R2['cmd'], loaded=False) is False
    geo, trace = relief_geometry(arm, R2['role'])
    assert geo.motion_clear(SERVO, pose, R2['cmd'], loaded=False) is False
    assert trace.reliefs == [] and trace.first is not None                                   # the frozen veto stays
    refusal = trace.relief_refusal['refusal']
    assert refusal['why'] == 'start_outside_pair_enters' and refusal['pair'] == ['chassis', 0, 'wall_west']
    assert refusal['sample'] == 2
    assert refusal['start_signed_mm'] == pytest.approx(9.642188250576964, abs=1e-6)
    assert refusal['signed_mm'] == pytest.approx(-9.395921079858518, abs=1e-6)
    # Literal "each pair never worse" also refuses it (as before).
    strict, strict_trace = relief_geometry(arm, R2['role'], scope='pair')
    assert strict.motion_clear(SERVO, pose, R2['cmd'], loaded=False) is False
    assert strict_trace.relief_refusal['refusal']['why'] == 'pair_worse_than_floor' and strict_trace.reliefs == []


REVIEWER_ENTRY = dict(forward=.2, left=.2, turn=-.3, duration_s=.15)


def test_the_reviewers_entry_command_is_vetoed_at_the_r2_pose(arm):
    # forward .2 / left .2 / turn -.3 for .15 s took a start-outside pair to -25.0 mm under the group floor alone.
    geo, trace = relief_geometry(arm, R2['role'])
    assert geo.motion_clear(SERVO, g.OwnPose(*R2['pose']), drive(**REVIEWER_ENTRY), loaded=False) is False
    refusal = trace.relief_refusal['refusal']
    assert refusal['why'] == 'start_outside_pair_enters' and refusal['start_signed_mm'] >= 0. > refusal['signed_mm']
    assert trace.reliefs == []


def test_mutation_without_the_entry_rule_the_reviewers_command_is_admitted_again(arm, monkeypatch):
    monkeypatch.setattr(sr, 'enters', lambda start_pair, pair: False)
    geo, trace = relief_geometry(arm, R2['role'])
    assert geo.motion_clear(SERVO, g.OwnPose(*R2['pose']), drive(**REVIEWER_ENTRY), loaded=False) is True
    assert len(trace.reliefs) == 1


def test_no_admitted_relief_lets_a_start_outside_pair_enter_a_box_on_the_reviewers_grid(arm):
    seen = 0
    for R in (R1, R2):
        pose = g.OwnPose(*R['pose'])
        for f, l, w in itertools.product((-.2, 0., .2), (-.2, 0., .2), (-.3, 0., .3)):
            cmd = drive(forward=f, left=l, turn=w)
            geo, trace = relief_geometry(arm, R['role'])
            if not (geo.motion_clear(SERVO, pose, cmd, loaded=False) and trace.reliefs):
                continue
            seen += 1
            start = None
            for _, _, moved in sr._poses(pose, sr.sample_plan(cmd)):
                pairs = {sr._pair_key(p): p for p in sr._all_pairs(geo, SERVO, moved, False)}
                start = start or pairs
                assert all(p.signed >= 0. for k, p in pairs.items() if start[k].signed >= 0.), (R['role'], cmd)
    assert seen > 0


# ------------------------------------------------------------------ what must still be vetoed
@pytest.mark.parametrize('cmd', [drive(forward=-.11), drive(turn=.5, duration_s=.3), drive(forward=-.06, left=.05, duration_s=.3)])
def test_a_command_toward_the_wall_from_inside_the_margin_is_still_vetoed(arm, cmd):
    geo, trace = relief_geometry(arm, R1['role'])
    assert geo.motion_clear(SERVO, g.OwnPose(*R1['pose']), cmd, loaded=False) is False
    assert trace.reliefs == [] and trace.relief_refusal['refusal']['why'] == 'pair_worse_than_floor'
    assert trace.first is not None and trace.first['kind'] == 'chassis'                      # the frozen veto stays visible


def test_a_lateral_move_that_does_not_change_the_clearance_is_admitted(arm):
    geo, trace = relief_geometry(arm, R1['role'])
    assert geo.motion_clear(SERVO, g.OwnPose(*R1['pose']), drive(left=.08, duration_s=.3), loaded=False) is True
    assert trace.reliefs[0]['groups']['chassis:wall_west']['swept_worst_mm'] == pytest.approx(
        trace.reliefs[0]['groups']['chassis:wall_west']['start_worst_mm'], abs=1e-6)


def test_a_point_inside_the_wall_box_may_not_move_deeper_even_where_the_clamped_distance_stays_flat(arm):
    geo, trace = relief_geometry(arm, R2['role'])
    assert geo.motion_clear(SERVO, g.OwnPose(*R2['pose']), drive(forward=-.1), loaded=False) is False
    refusal = trace.relief_refusal['refusal']
    assert refusal['why'] == 'inside_pair_deeper' and refusal['signed_mm'] < refusal['start_signed_mm']


def test_a_pair_that_starts_clear_must_stay_clear(arm):
    """South-west corner: the rear starts inside the west margin, the right side starts 21 mm clear of wall_south."""
    pose = g.OwnPose(-.87, -2.95, 0., .0194, .0027)
    assert PairGeometry(arm, BEAM, 'end_neg').motion_clear(SERVO, pose, drive(forward=.1127), loaded=False) is False
    geo, trace = relief_geometry(arm, 'end_neg')
    assert geo.motion_clear(SERVO, pose, drive(forward=.1127), loaded=False) is True                  # away from the west wall
    geo, trace = relief_geometry(arm, 'end_neg')
    assert geo.motion_clear(SERVO, pose, drive(forward=.1127, left=-.2, duration_s=.3), loaded=False) is False
    refusal = trace.relief_refusal['refusal']
    assert refusal['why'] == 'start_clear_pair_negative' and refusal['pair'][2] == 'wall_south'
    assert refusal['start_clearance_mm'] > 0 and refusal['floor_mm'] == 0.


def test_invalid_commands_are_left_to_the_frozen_guard(arm):
    pose = g.OwnPose(*R1['pose'])
    for cmd in (drive(forward=.1, duration_s=2.), drive(forward=float('nan')), drive(forward=.1, duration_s=-.1)):
        geo, trace = relief_geometry(arm, R1['role'])
        assert geo.motion_clear(SERVO, pose, cmd, loaded=False) is False and trace.reliefs == [] and trace.relief_refusal is None


# ------------------------------------------------------------------ nothing else changes
def grid_poses():
    return [g.OwnPose(x, y, yaw, sxy, syaw) for x, y, yaw, (sxy, syaw) in itertools.product(
        (-.97, -.9, -.85, -.7), (.55, -2.95), (-.1, .1), ((.0025, .0023), (.0194, .0027)))]


def grid_cmds():
    return [drive(.11, -.027), drive(-.08, 0., 0., .3), drive(0., .06, .3, .2), drive(.1, 0., -.4, .5)]


def frozen_equivalent(geo, servo, pose, cmd, loaded):
    """The frozen verdict re-derived from the pair mirror: every pair >= 0 at every swept sample."""
    plan = sr.sample_plan(cmd)
    if plan is None:
        return False
    f, l, w, duration, n = plan
    spheres = g.body_spheres(servo, loaded=False, mount_xyz_m=geo.mount) + (geo.beam_spheres(servo) if loaded else [])
    lever = max(.2, *(math.hypot(x, y) + r for x, y, _, r in spheres))
    saved = geo.residual
    geo.residual += (math.hypot(f, l) + abs(w) * lever) * duration / n / 2.
    try:
        return all(p.clearance >= 0. for _, _, moved in sr._poses(pose, plan)
                   for p in gl.chassis_pairs(geo, moved) + gl.arm_pairs(geo, servo, moved, loaded))
    finally:
        geo.residual = saved


def test_pair_mirror_and_sample_loop_reproduce_the_frozen_verdict_everywhere(arm):
    plain = PairGeometry(arm, BEAM, 'end_neg')
    seen = set()
    for pose, cmd, (servo, loaded) in itertools.product(grid_poses(), grid_cmds(), ((SERVO, False), (HIGH, True))):
        old = plain.motion_clear(servo, pose, cmd, loaded=loaded)
        assert frozen_equivalent(plain, servo, pose, cmd, loaded) == old
        seen.add(old)
    assert seen == {True, False}


def starts_negative(geo, servo, pose, cmd, loaded):
    """Does any pair of the unmoved start sample violate the margin the frozen guard uses for this command?"""
    plan = sr.sample_plan(cmd)
    if plan is None:
        return None
    f, l, w, duration, n = plan
    spheres = g.body_spheres(servo, loaded=False, mount_xyz_m=geo.mount) + (geo.beam_spheres(servo) if loaded else [])
    lever = max(.2, *(math.hypot(x, y) + r for x, y, _, r in spheres))
    saved = geo.residual
    geo.residual += (math.hypot(f, l) + abs(w) * lever) * duration / n / 2.
    try:
        return any(p.clearance < 0. for p in gl.chassis_pairs(geo, pose) + gl.arm_pairs(geo, servo, pose, loaded))
    finally:
        geo.residual = saved


def test_answers_are_bit_identical_unless_a_pair_starts_negative_and_the_frozen_guard_said_no(arm):
    plain = PairGeometry(arm, BEAM, 'end_neg')
    geo, trace = relief_geometry(arm, 'end_neg')
    counts = {'frozen_yes': 0, 'no_start_negative': 0, 'relieved': 0, 'refused': 0}
    for pose, cmd, (servo, loaded) in itertools.product(grid_poses(), grid_cmds(), ((SERVO, False), (HIGH, True))):
        old = plain.motion_clear(servo, pose, cmd, loaded=loaded)
        new = geo.motion_clear(servo, pose, cmd, loaded=loaded)
        assert (geo.residual, geo._loaded_motion) == (plain.residual, plain._loaded_motion)
        if old:
            assert new is True and trace.reliefs == []                                      # the frozen "yes" is never touched
            counts['frozen_yes'] += 1
        elif not starts_negative(plain, servo, pose, cmd, loaded):
            assert new is False and trace.reliefs == [] and trace.relief_refusal is None    # no start pair negative: frozen "no"
            counts['no_start_negative'] += 1
        else:
            counts['relieved' if new else 'refused'] += 1
            assert bool(trace.reliefs) is bool(new) and (trace.relief_refusal is None) is bool(new)
        trace.reliefs.clear()
        trace.relief_refusal = None
    assert all(counts.values()), counts                                                      # every branch was exercised


def test_every_other_query_answers_bit_for_bit_like_the_frozen_geometry(arm):
    plain, geo = PairGeometry(arm, BEAM, 'end_pos'), relief_geometry(arm, 'end_pos')[0]
    assert type(geo) is sr.StartReliefGeometry and geo.motion_clear.__func__ is not PairGeometry.motion_clear
    for pose, (servo, loaded) in itertools.product(grid_poses(), ((SERVO, False), (HIGH, True))):
        assert geo.arm_clearance(servo, pose, loaded=loaded) == plain.arm_clearance(servo, pose, loaded=loaded)
        assert geo.chassis_clearance(pose) == plain.chassis_clearance(pose)
        assert geo.transition_clear(SERVO, servo, pose, loaded=loaded) == plain.transition_clear(SERVO, servo, pose, loaded=loaded)
    for pose in grid_poses()[:5]:
        assert geo.plan(SERVO, HIGH, [1400, 1500], pose, loaded=False, allow_backoff=True) == \
            plain.plan(SERVO, HIGH, [1400, 1500], pose, loaded=False, allow_backoff=True)


def test_relief_fails_closed_when_its_mirror_disagrees_or_raises(arm, monkeypatch):
    pose = g.OwnPose(*R1['pose'])
    geo, trace = relief_geometry(arm, R1['role'])
    monkeypatch.setattr(sr, '_all_pairs', lambda *a: 1 / 0)
    assert geo.motion_clear(SERVO, pose, R1['cmd'], loaded=False) is False
    assert 'ZeroDivisionError' in trace.relief_notes[0] and trace.reliefs == [] and trace.first is not None
    monkeypatch.undo()
    geo, trace = relief_geometry(arm, R1['role'])
    real = gl.chassis_pairs                                                                     # mirror != frozen number
    monkeypatch.setattr(gl, 'chassis_pairs', lambda geo_, pose_: [p._replace(clearance=p.clearance + 1e-3) for p in real(geo_, pose_)])
    assert geo.motion_clear(SERVO, pose, R1['cmd'], loaded=False) is False
    assert 'pair mirror disagrees' in trace.relief_notes[0]


def test_floors_follow_the_scope():
    P = gl.Pair
    start = {('chassis', 0, 'w'): P('chassis', 0, 'w', -.05, 0., 0., .1, ()), ('chassis', 1, 'w'): P('chassis', 1, 'w', -.01, .03, .03, .1, ()),
             ('chassis', 2, 'w'): P('chassis', 2, 'w', .02, .06, .06, .1, ())}
    assert sr.floors(start, 'group', .001) == pytest.approx({('chassis', 0, 'w'): -.051, ('chassis', 1, 'w'): -.051, ('chassis', 2, 'w'): 0.})
    assert sr.floors(start, 'pair', .001) == pytest.approx({('chassis', 0, 'w'): -.051, ('chassis', 1, 'w'): -.011, ('chassis', 2, 'w'): 0.})


# ------------------------------------------------------------------ the CommandGuard hook
def test_hook_logs_every_admission_as_a_start_relief_event_and_no_veto(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard, commands = stand_in(R1), [dict(R1['cmd'])]
    assert guard.check(8.7, commands) is commands                                           # admitted: the parent's answer
    assert guard.ep.own.events == []                                                         # no job_failed
    [event] = guard.ep.events
    assert event['event'] == sr.EVENT and event['sim_s'] == 8.7 and event['command'] == R1['cmd']
    assert event['groups']['chassis:wall_west']['start_worst_mm'] == pytest.approx(-55.31114977748346, abs=1e-9)
    assert event['estimate']['cov'] == [list(row) for row in R1['cov']] and event['start_inside_raw'] is False
    assert event['scope'] == 'group' and event['pairs'][0]['wall_id'] == 'wall_west'
    json.dumps(guard.ep.events)


def test_hook_keeps_the_veto_and_adds_the_refusal_when_the_relief_says_no(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard = stand_in(R1)
    toward = drive(forward=-.11)
    assert guard.check(8.7, [dict(toward)]) == [{'kind': 'hold'}]
    assert [e['event'] for e in guard.ep.events] == [gl.EVENT]                               # veto only, no relief event
    assert guard.ep.events[0]['start_relief']['refusal']['why'] == 'pair_worse_than_floor'
    assert guard.ep.events[0]['first_negative']['term'] == 'chassis'


def test_hook_leaves_a_clear_command_and_other_aborts_alone(monkeypatch):
    far = {**R1, 'pose': (-.6, .55, 0., .01, .003)}
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard, commands = stand_in(far), [dict(R1['cmd'])]
    assert guard.check(8.7, commands) is commands and guard.ep.events == []


def test_a_relief_log_failure_never_changes_the_run(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard = stand_in(R1)
    real_log = guard.ep.log

    def failing(rid, kind, now, **detail):
        if kind == sr.EVENT and 'log_error' not in detail:
            raise RuntimeError('disk full')
        return real_log(rid, kind, now, **detail)
    guard.ep.log = failing
    commands = [dict(R1['cmd'])]
    assert guard.check(8.7, commands) is commands
    assert 'disk full' in guard.ep.events[0]['log_error']


def test_adoption_record_lists_the_relief_and_the_frozen_parents_are_kept():
    record = rt.adopt_v98_frame_gate(types.SimpleNamespace(actors={}))
    assert record['start_relief'] == sr.record() and record['guard_veto_log'] == gl.record()
    assert sr.record()['arm_and_transition_checks_changed'] is False and sr.record()['shared_sources_modified'] is False
    assert rt.CommandGuard.__mro__[1] is PreviousGuard
    assert 'start_relief' not in PairGeometry.__dict__ and not hasattr(PairGeometry, 'scope')
