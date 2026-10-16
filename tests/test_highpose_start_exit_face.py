"""v98 start-state relief v2: depth of an inside pair is measured to the wall face that faces the robot.

Probe af2f7c2a (raise_high, 10.9 s): r2's first approach command (forward .1199, left .0033, turn 0) was vetoed by
``PAIR_COLLISION_GUARD`` and refused by the relief as ``inside_pair_deeper`` (-13.3 -> -22.9 mm). Offline, against the
simulator pose (evaluation-only constants below, never an input of any rule under test):

* truth (-0.89802, -0.84991, yaw 5e-5), stationary since 9.7 s; estimate error 13.8 mm west and 9.4 mm south (16.7 mm,
  NEES 0.42 with the honest sigma 42.7 mm);
* the real chassis (scene.xml collision geoms at the true pose) stood 34.6 mm from the wall's inner face;
* the authored rear corner (-0.15, -0.09) is INSIDE the 50 mm wall box at the true pose (23.0 mm past the inner face) and
  2.0 mm east of the wall's mid-plane; the estimate error moved it 11.8 mm west of the mid-plane, where the NEAREST face is
  the outer one, so driving east (toward the inner face, out of the wall) first increases that depth.

Simulator-free. The no-entry rule and the floors are untouched: those tests live in ``test_highpose_start_relief``.
"""
from __future__ import annotations

import itertools
import json
import math

import pytest

from harness import zone_own_guards as g
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_guardlog as gl
from harness import zone_pair_highpose_start_relief as sr
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard, PairArmGuard, PairGeometry
from tests.test_highpose_guard_veto_log import BEAM, R2, SERVO, parent_check, stand_in
from tests.test_zone_final_pair_v3 import MAPS

# The recorded guard inputs of the 10.9 s tick of r2 (pair_collision_guard_veto event of the af2f7c2a probe).
R2_AF = dict(role='end_pos', pose=(-0.9118309319272437, -0.8592547055364095, 0.0016233740120896734,
                                   0.042706544462430725, 0.015087058412845042),
             cmd={'kind': 'mecanum', 'forward': 0.11989494221778893, 'left': 0.0033468280567364034, 'turn': 0.0,
                  'duration_s': 0.15},
             cov=((0.00046253, 0.00021634, -9.679e-05), (0.00021634, 0.00136132, -0.00044249),
                  (-9.679e-05, -0.00044249, 0.00022762)))
# EVALUATION ONLY (simulator pose of r2 at 10.9 s and the real chassis rear extent from the scene's collision geoms).
TRUTH = (-0.89801848, -0.84990616, 5e-5)
REAL_REAR_M = -0.0924
WALL_INNER_X, WALL_OUTER_X = -1.025, -1.075
GAIN = g.BACKOFF_GAIN_MAX


def drive(forward=0., left=0., turn=0., duration_s=.15):
    return {'kind': 'mecanum', 'forward': forward, 'left': left, 'turn': turn, 'duration_s': duration_s}


@pytest.fixture(scope='module')
def arm():
    return PairArmGuard(c.resolve(MAPS[0])[0])


def relief_geometry(arm, role=R2_AF['role'], depth=None):
    geo, trace = PairGeometry(arm, BEAM, role), gl.Trace()
    sr.install(geo, trace)
    if depth is not None:
        geo.depth = depth
    return geo, trace


def verdict_of(arm, pose, cmd, depth=None, role=R2_AF['role']):
    geo, trace = relief_geometry(arm, role, depth)
    ok = geo.motion_clear(SERVO, pose, cmd, loaded=False)
    return ok, trace


def at_error(ex_mm=0., ey_mm=0., sigma=(0.0427, 0.0151)):
    return g.OwnPose(TRUTH[0] + ex_mm / 1000., TRUTH[1] + ey_mm / 1000., TRUTH[2], *sigma)


# ------------------------------------------------------------------ the recorded 10.9 s tick of r2
def test_recorded_r2_first_command_was_refused_by_the_nearest_face_depth(arm):
    pose = g.OwnPose(*R2_AF['pose'])
    assert PairGeometry(arm, BEAM, R2_AF['role']).motion_clear(SERVO, pose, R2_AF['cmd'], loaded=False) is False
    ok, trace = verdict_of(arm, pose, R2_AF['cmd'], depth='nearest_face')
    assert ok is False and trace.reliefs == []
    refusal = trace.relief_refusal['refusal']
    assert refusal['why'] == 'inside_pair_deeper' and refusal['pair'] == ['chassis', 0, 'wall_west']
    assert refusal['start_signed_mm'] == pytest.approx(-13.315369320367456, abs=1e-6)       # as recorded at af2f7c2a
    assert refusal['signed_mm'] == pytest.approx(-22.906517407116446, abs=1e-6)
    assert trace.first['clearance_m'] * 1000. == pytest.approx(-85.14336765467306, abs=1e-6)


def test_recorded_r2_first_command_is_admitted_with_the_exit_face_depth(arm):
    pose = g.OwnPose(*R2_AF['pose'])
    ok, trace = verdict_of(arm, pose, R2_AF['cmd'])
    assert ok is True and sr.DEPTH == 'exit_face'
    [verdict] = trace.reliefs
    assert verdict['depth'] == 'exit_face' and verdict['refusal'] is None and verdict['start_inside_raw'] is True
    assert verdict['command'] == R2_AF['cmd'] and verdict['scope'] == 'group'
    row = next(p for p in verdict['pairs'] if p['index'] == 0)
    assert row['start_inside_raw'] and row['exit_face'] == 'x+'                              # the face toward the robot
    assert row['start_exit_signed_mm'] == pytest.approx(-36.68, abs=.01)                     # 36.7 mm to the INNER face
    assert all(p['worst_change_mm'] >= -1e-6 for p in verdict['pairs'])                       # nothing got worse
    assert verdict['groups']['chassis:wall_west']['swept_worst_mm'] == pytest.approx(
        verdict['groups']['chassis:wall_west']['start_worst_mm'], abs=1e-6)
    assert trace.first is None and trace.failed_sites == []                                  # the frozen veto was rolled back
    json.dumps(verdict)


def test_the_cause_is_the_approach_direction_not_turn_or_lateral_sign(arm):
    pose = g.OwnPose(*R2_AF['pose'])
    cmd = R2_AF['cmd']
    assert cmd['turn'] == 0. and abs(cmd['left']) * GAIN * .05 < 5e-4                         # 0.3 mm of lateral at sample 1
    # Flip the lateral sign, drop it, add a turn of either sign: the nearest-face rule still refuses, because the
    # forward component alone moves the corner toward the wall's mid-plane.
    for variant in (drive(cmd['forward'], -cmd['left']), drive(cmd['forward']), drive(cmd['forward'], 0., .1),
                    drive(cmd['forward'], 0., -.1)):
        ok, trace = verdict_of(arm, pose, variant, depth='nearest_face')
        assert ok is False and trace.relief_refusal['refusal']['why'] == 'inside_pair_deeper', variant
    # Without the forward component the same lateral/turn motion does not trip the depth rule.
    ok, trace = verdict_of(arm, pose, drive(0., cmd['left']), depth='nearest_face')
    assert ok is True


# ------------------------------------------------------------------ evaluation-only facts (never a rule input)
def test_evaluation_only_truth_shows_the_corner_inside_the_wall_near_its_mid_plane(arm):
    ex, ey = R2_AF['pose'][0] - TRUTH[0], R2_AF['pose'][1] - TRUTH[1]
    assert (ex * 1000., ey * 1000.) == pytest.approx((-13.81, -9.35), abs=.01)
    assert math.hypot(ex, ey) * 1000. == pytest.approx(16.68, abs=.01)
    corner_true, corner_est = TRUTH[0] - .15, R2_AF['pose'][0] - .15
    mid = (WALL_INNER_X + WALL_OUTER_X) / 2.
    assert corner_true - mid == pytest.approx(.0020, abs=1e-4) and corner_est - mid < -.0115      # east / west of mid-plane
    assert (corner_true - WALL_OUTER_X > WALL_INNER_X - corner_true) and (corner_est - WALL_OUTER_X < WALL_INNER_X - corner_est)
    assert (TRUTH[0] + REAL_REAR_M - WALL_INNER_X) * 1000. == pytest.approx(34.6, abs=.5)    # the real chassis is clear
    # At the TRUE pose the nearest face is the inner one, so the old rule would have admitted the same command.
    ok, trace = verdict_of(arm, g.OwnPose(*TRUTH, 0.0427, 0.0151), R2_AF['cmd'], depth='nearest_face')
    assert ok is True and len(trace.reliefs) == 1


def test_the_old_rule_flips_with_the_estimate_error_the_new_one_does_not(arm):
    cmd, seen = R2_AF['cmd'], {}
    for ex in (-20, -14, -10, -5, 0, 10, 40):
        seen[ex] = [verdict_of(arm, at_error(ex), cmd, depth=d)[0] for d in ('nearest_face', 'exit_face')]
    assert seen == {-20: [False, True], -14: [False, True], -10: [False, True], -5: [True, True], 0: [True, True],
                    10: [True, True], 40: [True, True]}
    for ey in (-30, -9, 0, 20):                                                              # the other axis is irrelevant
        assert verdict_of(arm, at_error(-14, ey), cmd, depth='exit_face')[0] is True


def test_the_no_entry_rule_still_refuses_a_corner_estimated_beyond_the_far_face(arm):
    # 30 mm west error: the corner is estimated OUTSIDE the box on its far side; driving east enters the box. Not relaxed.
    for depth in ('nearest_face', 'exit_face'):
        ok, trace = verdict_of(arm, at_error(-30), R2_AF['cmd'], depth=depth)
        assert ok is False and trace.relief_refusal['refusal']['why'] == 'start_outside_pair_enters'


# ------------------------------------------------------------------ what the new depth must not admit
def test_a_move_toward_the_far_face_is_admitted_by_the_old_depth_and_refused_by_the_new_one(arm):
    pose = g.OwnPose(*R2_AF['pose'])
    for cmd in (drive(-.05, 0., 0., .05), drive(-.1, .1, 0., .05)):
        old_ok, _ = verdict_of(arm, pose, cmd, depth='nearest_face')
        new_ok, trace = verdict_of(arm, pose, cmd, depth='exit_face')
        assert old_ok is True                                                                # west, toward the outer face
        assert new_ok is False and trace.relief_refusal['refusal']['why'] == 'inside_pair_deeper'
        assert trace.relief_refusal['refusal']['exit_face'] == 'x+'


def test_the_reviewers_entry_command_differs_by_pose_it_leaves_the_wall_at_af2f7c2a_and_enters_it_at_3358372e(arm):
    # forward .2 / left .2 / turn -.3 (the Review-5 entry command). At the af2f7c2a pose the pair is already INSIDE the wall
    # box and the command moves east, out of it: the nearest-face depth refused that only because the estimate error had put
    # the corner on the far side of the mid-plane; the exit-face depth admits it, and the real chassis never gets closer to
    # the wall than it started (34.6 mm). At the 3358372e pose the same command takes a start-OUTSIDE pair into the box: both
    # depths refuse it with the entry rule (unchanged, tested in test_highpose_start_relief as well).
    entry = drive(.2, .2, -.3)
    pose_af = g.OwnPose(*R2_AF['pose'])
    old_ok, old_trace = verdict_of(arm, pose_af, entry, depth='nearest_face')
    new_ok, new_trace = verdict_of(arm, pose_af, entry, depth='exit_face')
    assert old_ok is False and old_trace.relief_refusal['refusal']['why'] == 'inside_pair_deeper'
    assert new_ok is True and len(new_trace.reliefs) == 1 and new_trace.reliefs[0]['depth'] == 'exit_face'
    assert evaluation_only_real_clearance_mm(entry) >= evaluation_only_real_clearance_mm(drive()) - 1e-6     # moves away
    pose_old = g.OwnPose(*R2['pose'])
    for depth in ('nearest_face', 'exit_face'):
        ok, trace = verdict_of(arm, pose_old, entry, depth=depth, role=R2['role'])
        refusal = trace.relief_refusal['refusal']
        assert ok is False and refusal['why'] == 'start_outside_pair_enters'
        assert refusal['start_signed_mm'] >= 0. > refusal['signed_mm']


def evaluation_only_real_clearance_mm(cmd, pose=TRUTH, steps=40):
    """Clearance of the REAL chassis rectangle (rear -0.0924, the guard's other extents) along the commanded arc from the
    true pose, with the guard's own gain; simulator truth, used only to judge what the rule admitted."""
    plan = sr.sample_plan(cmd)
    f, l, w, duration, _ = plan
    boxes = PairArmGuard(c.resolve(MAPS[0])[0]).boxes
    pts = [(x, y) for x in [REAL_REAR_M + i * (.10 - REAL_REAR_M) / 8. for i in range(9)] for y in (-.09, .09)] + \
          [(x, y) for x in (REAL_REAR_M, .10) for y in [-.09 + i * .18 / 8. for i in range(9)]]
    best = math.inf
    for omega in sorted({-abs(w), 0., abs(w)}):
        for k in range(steps + 1):
            t = duration * k / steps
            a = omega * t
            if omega:
                dx, dy = (f * math.sin(a) + l * (math.cos(a) - 1.)) / omega, (f * (1. - math.cos(a)) + l * math.sin(a)) / omega
            else:
                dx, dy = f * t, l * t
            cs, sn = math.cos(pose[2] + a), math.sin(pose[2] + a)
            for bx, by in pts:
                mx, my = pose[0] + dx + cs * bx - sn * by, pose[1] + dy + sn * bx + cs * by
                for box in boxes:
                    ddx, ddy = abs(mx - box['center'][0]) - box['half'][0], abs(my - box['center'][1]) - box['half'][1]
                    best = min(best, -min(-ddx, -ddy) if ddx <= 0 and ddy <= 0 else math.hypot(max(ddx, 0.), max(ddy, 0.)))
    return best * 1000.


def reduced_grid():
    return [drive(f, l, w, d) for f, l, w, d in itertools.product((-.1, -.05, 0., .05, .12, .3), (-.2, 0., .2),
                                                                 (-.3, 0., .3), (.05, .15, .5)) if (f, l, w) != (0., 0., 0.)]


def test_every_admitted_command_keeps_the_real_chassis_clear_and_the_old_rule_did_not(arm):
    pose = g.OwnPose(*R2_AF['pose'])
    worst = {}
    admitted = {}
    for depth in ('nearest_face', 'exit_face'):
        rows = [(evaluation_only_real_clearance_mm(cmd), cmd) for cmd in reduced_grid() if verdict_of(arm, pose, cmd, depth=depth)[0]]
        admitted[depth], worst[depth] = rows, min(r for r, _ in rows)
    assert admitted['exit_face'] and admitted['nearest_face']
    assert worst['exit_face'] >= 33. > worst['nearest_face']                                  # old: reverse moves to ~21 mm
    # Nothing at the controller's operating speed (forward .05-.2 command units) was admitted before; now it is.
    band = lambda rows: [cmd for _, cmd in rows if .04 < cmd['forward'] <= .21]
    assert band(admitted['nearest_face']) == [] and len(band(admitted['exit_face'])) >= 10
    # And no reverse (westward) command is admitted any more.
    assert [cmd for _, cmd in admitted['exit_face'] if cmd['forward'] < 0.] == []
    assert [cmd for _, cmd in admitted['nearest_face'] if cmd['forward'] < 0.] != []


def test_after_the_first_tick_the_approach_goes_on(arm):
    """Offline chain (hypothetical advance of 18 mm per tick, estimate error and sigma held): only tick 0 needed help."""
    answers = []
    for k in range(8):
        pose = g.OwnPose(R2_AF['pose'][0] + k * .018, *R2_AF['pose'][1:])
        ok, trace = verdict_of(arm, pose, R2_AF['cmd'])
        answers.append('relief' if (ok and trace.reliefs) else 'clear' if ok else 'veto')
    assert answers[0] == 'relief' and 'veto' not in answers and answers[-1] == 'clear'


# ------------------------------------------------------------------ the helpers
BOX = {'id': 'w', 'center': (-1.05, -.85), 'half': (.025, 2.3), 'yaw': 0.}


def make_pair(box, x, y, r=0., kind='chassis'):
    """A guard pair exactly as ``chassis_pairs``/``arm_pairs`` build it (raw and signed from the frozen helpers)."""
    raw = g._rect_distance(box, x, y)
    return gl.Pair(kind, 0, box['id'], 0., raw - r, gl._signed(box, x, y, raw) - r, 0., (0., 0., None, r, x, y))


def test_exit_face_is_the_face_toward_the_reference_point():
    assert sr.exit_face(BOX, -.9, -.85) == (0, 1)                 # east of the wall
    assert sr.exit_face(BOX, -1.3, -.85) == (0, -1)               # west
    assert sr.exit_face(BOX, -1.05, -3.3) == (1, -1)              # beyond the south end
    assert sr.exit_face(BOX, -1.05, -.85) is None                 # inside: no side
    assert sr.exit_face(BOX, -.9, -3.3) == (0, 1)                 # diagonal: the face whose plane is nearer (x: 125 mm)
    rotated = {'id': 'r', 'center': (0., 0.), 'half': (.025, 1.), 'yaw': math.pi / 2}     # long axis along world x
    assert sr.exit_face(rotated, 0., .3) == (0, 1) and sr.exit_face(rotated, 0., -.3) == (0, -1)


def test_exit_signed_equals_the_nearest_face_where_that_face_is_the_exit_face_and_is_deeper_elsewhere():
    face = sr.exit_face(BOX, -.9, -.85)                           # east side: the inner face x = -1.025
    for x in (-1.030, -1.040, -1.045):                            # inner half: nearest face is the exit face
        p = make_pair(BOX, x, -.85)
        assert sr.exit_signed(BOX, p, face) == pytest.approx(p.signed, abs=1e-12)
    for x in (-1.055, -1.062, -1.074):                            # outer half: the nearest face is the far one
        p = make_pair(BOX, x, -.85)
        assert sr.exit_signed(BOX, p, face) == pytest.approx(-(WALL_INNER_X - x), abs=1e-12)
        assert sr.exit_signed(BOX, p, face) < p.signed
    # moving east along the way out strictly decreases the exit depth, the nearest-face depth first increases it
    depths = [sr.exit_signed(BOX, make_pair(BOX, x, -.85), face) for x in (-1.0617, -1.0521, -1.0425, -1.0329)]
    nearest = [make_pair(BOX, x, -.85).signed for x in (-1.0617, -1.0521, -1.0425, -1.0329)]
    assert depths == sorted(depths) and nearest[1] < nearest[0]


def test_exit_signed_keeps_a_centre_outside_the_box_and_the_sphere_radius():
    face = (0, 1)
    outside = make_pair(BOX, -.95, -.85, r=.04, kind='body')       # centre 100 mm east of the box; surface 60 mm
    assert sr.exit_signed(BOX, outside, face) == pytest.approx(outside.signed)
    mid = make_pair(BOX, -1.05, -.85, r=.04, kind='body')          # centre on the mid-plane: 25 mm to either face
    assert sr.exit_signed(BOX, mid, face) == pytest.approx(-.025 - .04, abs=1e-12) == pytest.approx(mid.signed, abs=1e-12)
    deep = make_pair(BOX, -1.06, -.85, r=.04, kind='body')         # centre in the outer half: 35 mm to the exit face
    assert sr.exit_signed(BOX, deep, face) == pytest.approx(-.035 - .04, abs=1e-12)
    assert sr.exit_signed(BOX, deep, face) < deep.signed


# ------------------------------------------------------------------ nothing else changes
def grid_poses():
    return [g.OwnPose(x, y, yaw, sxy, syaw) for x, y, yaw, (sxy, syaw) in itertools.product(
        (-.97, -.9, -.85), (.55, -.85, -2.95), (-.1, .1), ((.0025, .0023), (.0427, .0151)))]


def test_the_two_depths_differ_only_where_an_inside_pair_has_a_far_nearest_face(arm):
    differing = same = 0
    for pose, cmd, role in itertools.product(grid_poses(), (drive(.11, -.027), drive(-.08, 0., 0., .3), drive(.12, 0.), drive(0., .06, .3, .2)),
                                             ('end_neg', 'end_pos')):
        old, _ = verdict_of(arm, pose, cmd, depth='nearest_face', role=role)
        new, trace = verdict_of(arm, pose, cmd, depth='exit_face', role=role)
        if old == new:
            same += 1
            continue
        differing += 1
        geo, _ = relief_geometry(arm, role)
        start = {sr._pair_key(p): p for p in sr._all_pairs(geo, SERVO, pose, False)}
        boxes = {b['id']: b for b in geo.boxes}
        outer = [k for k, p in start.items() if p.clearance < 0. and p.raw <= 0.
                 and (face := sr.exit_face(boxes[k[2]], pose.x, pose.y)) is not None
                 and sr.exit_signed(boxes[k[2]], p, face) < p.signed - 1e-12]
        assert outer, (pose, cmd, role)                       # a differing answer needs such a pair at the start
    assert same > 0 and differing > 0


def test_the_hook_logs_the_admission_with_the_depth_and_the_exit_face(monkeypatch):
    monkeypatch.setattr(PreviousGuard, 'check', parent_check())
    guard, commands = stand_in(R2_AF), [dict(R2_AF['cmd'])]
    assert guard.check(10.9, commands) is commands                                           # admitted, not vetoed
    assert guard.ep.own.events == []
    [event] = guard.ep.events
    assert event['event'] == sr.EVENT and event['log_id'] == sr.ID == 'v98_start_state_relief_v2'
    assert event['depth'] == 'exit_face' and event['pairs'][0]['exit_face'] == 'x+'
    assert event['groups']['chassis:wall_west']['start_worst_mm'] == pytest.approx(-85.14336765467306, abs=1e-6)
    json.dumps(guard.ep.events)


def test_record_names_the_depth():
    assert sr.record()['depth'] == 'exit_face' and sr.ID == 'v98_start_state_relief_v2'
    assert 'wall face that faces the robot' in sr.record()['rule']


# ------------------------------------------------------------------ mutations
def test_mutation_nearest_face_depth_brings_the_veto_back(arm, monkeypatch):
    monkeypatch.setattr(sr, 'DEPTH', 'nearest_face')
    monkeypatch.setattr(sr.StartReliefGeometry, 'depth', 'nearest_face')
    ok, trace = verdict_of(arm, g.OwnPose(*R2_AF['pose']), R2_AF['cmd'])
    assert ok is False and trace.relief_refusal['refusal']['why'] == 'inside_pair_deeper'


def test_mutation_exit_face_on_the_far_side_vetoes_the_way_out_and_admits_the_way_in(arm, monkeypatch):
    monkeypatch.setattr(sr, 'exit_face', lambda box, x, y: (0, -1))                          # the wrong (outer) face
    pose = g.OwnPose(*R2_AF['pose'])
    assert verdict_of(arm, pose, R2_AF['cmd'])[0] is False                                    # east is now "deeper"
    assert verdict_of(arm, pose, drive(-.05, 0., 0., .05))[0] is True                         # west is now "out"


def test_mutation_without_a_depth_check_the_reverse_move_is_admitted(arm, monkeypatch):
    monkeypatch.setattr(sr, 'exit_signed', lambda box, pair, face: 0.)
    assert verdict_of(arm, g.OwnPose(*R2_AF['pose']), drive(-.05, 0., 0., .05))[0] is True


def test_mutation_exit_depth_that_ignores_the_side_cannot_tell_the_directions_apart(arm, monkeypatch):
    real = sr.exit_signed
    monkeypatch.setattr(sr, 'exit_signed', lambda box, pair, face: real(box, pair, (face[0], 1)))
    pose = g.OwnPose(*R2_AF['pose'])
    assert verdict_of(arm, at_error(-14), R2_AF['cmd'])[0] is True                            # side + is the right one here
    monkeypatch.setattr(sr, 'exit_signed', lambda box, pair, face: real(box, pair, (face[0], -1)))
    assert verdict_of(arm, pose, R2_AF['cmd'])[0] is False
