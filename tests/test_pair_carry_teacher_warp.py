"""P2 pair-carry GT teacher / evaluator / recorder: pure-function tests (no simulator)."""
import ast
import json
import math
from pathlib import Path

import pytest

from harness import pair_carry_teacher_warp as ct
from harness import pair_carry_eval as ce
from harness import pair_carry_recorder as cr

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json').read_text())
ROLES = {'r1': 'teal', 'r2': 'blue'}
REACH = .5  # synthetic robot-centre to beam-centre distance along the beam axis


def wheels(effort):
    return [0.]*4, [0.]*4  # recorded only; the kinematic test integrates the body command


def handover(beam, reach=REACH):
    robots = {'r1': ct.compose(beam, (-reach, 0., 0.)), 'r2': ct.compose(beam, (reach, 0., math.pi)),
              'r3': (-.8, 1.2, 0.)}
    return truth(beam, robots, held=True)


def truth(beam, robots, *, held, min_z=.03, tilt=1., t=0.):
    f = [2., 2.] if held else [0., 0.]
    return {'t': t, 'beam': {'pose': list(beam), 'min_z': min_z, 'tilt_deg': tilt,
                             'xyz': [beam[0], beam[1], min_z + .02]},
            'robots': {rid: {'pose': list(p)} for rid, p in robots.items()},
            'contacts': {'r1': list(f), 'r2': list(f)}, 'objects': {}}


ARM = {rid: {'place': {1: 1500, 3: 1400, 4: 1600, 5: 1500, 6: 1500},
             'hover': {1: 2000, 3: 1300, 4: 1700, 5: 1500, 6: 1500}} for rid in ROLES}
PWM = {rid: {1: 1500, 3: 1200, 4: 1800, 5: 1500, 6: 1500} for rid in ROLES}


def make(beam, reach=REACH, **kw):
    return ct.PairCarryTeacherWarp(ROLES, handover(beam, reach), 0., MAP, ARM, PWM, wheel_fn=wheels, **kw)


# ------------------------------------------------------------------ geometry

def test_route_uses_wide_door_and_ends_inside_zone_b():
    route, info = ct.carry_route((.7, -1.5, .3), {'r1': (-REACH, 0, 0), 'r2': (REACH, 0, math.pi)}, MAP)
    tags = [t for t, _ in route]
    assert tags == ['to_west_staging', 'rotate_door', 'to_door_entry', 'door_pass', 'to_east_staging',
                    'rotate_zone', 'to_zone']
    door = info['door']
    assert door['id'] == 'door_wide' and door['x'] == pytest.approx(2.2) and door['width'] == pytest.approx(1.)
    entry, exit_ = route[2][1], route[3][1]
    assert entry[0] < door['x'] < exit_[0] and entry[1] == exit_[1]
    assert -3.125 < entry[1] < -2.125
    assert info['passage']['width_needed_m'] < door['width']
    goal = route[-1][1]
    assert ct.beam_in_zone(goal, info['zone'], margin=.02)
    assert goal[:2] == (pytest.approx(4.6), pytest.approx(-2.1))


def test_zone_b_long_axis_is_the_only_slack_orientation():
    z = ct.zone_of(MAP)
    assert ct.beam_in_zone((4.6, -2.1, math.pi/2), z, margin=.02)
    # 0.6 m beam across the 0.6 m short axis fits only with zero slack
    assert ct.beam_in_zone((4.6, -2.1, 0.), z) and not ct.beam_in_zone((4.6, -2.1, 0.), z, margin=.02)


def test_static_map_resolves_to_the_wide_door_map():
    from harness import zone_final_environment as env
    static, _, _ = env.resolve('zone_wide_two_doors_final_v3')
    assert static == MAP
    assert ct.static_map_for({'static_map': static}) is static
    with pytest.raises(NotImplementedError):
        ct.static_map_for({'static_map': {'map_id': 'x', 'passages': [], 'regions': {}}})


def test_door_too_narrow_is_explicit_code():
    narrow = json.loads(json.dumps(MAP))
    for p in narrow['passages']:
        if p['id'] == 'door_wide':
            p['width_m'] = .4
    with pytest.raises(ValueError, match='door_clearance_insufficient'):
        ct.carry_route((.7, -1.5, 0.), {'r1': (-REACH, 0, 0), 'r2': (REACH, 0, math.pi)}, narrow)


def test_rotate_first_fallback_when_translate_sweeps_a_wall():
    offsets = {'r1': (-REACH, 0, 0), 'r2': (REACH, 0, math.pi)}
    start = (0., 0., math.pi/2)                       # robots at y = -0.5 / +0.5
    route = [('to_west_staging', (2., 0., math.pi/2)), ('rotate_door', (2., 0., 0.))]
    wall = [(1., .75, .05, .1, 0.)]                   # grazes the north robot when translating along x
    out, blocked = ct.check_route(start, route, offsets, wall, [])
    assert blocked[0] is True and blocked[1]['segment'] == 'to_west_staging'
    assert out == [('rotate_door', (0., 0., 0.)), ('to_west_staging', (2., 0., 0.))]
    out, blocked = ct.check_route(start, route, offsets, [], [])
    assert blocked is None and out == route
    out, blocked = ct.check_route(start, route, offsets, wall + [(0., 0., .05, .05, 0.)], [])
    assert blocked[0] is False


def test_route_blocked_by_object_disc_is_failure_not_detour():
    beam = (.6, -1.5, 0.)
    teacher = make(beam, obstacles=[{'id': 'box', 'xy': [1.0, -2.0], 'radius': .3},
                                    {'id': 'box2', 'xy': [.6, -1.0], 'radius': .3}])
    assert teacher.outcome == 'route_blocked' and teacher.done


def test_missing_arm_targets_fail_closed():
    t = ct.PairCarryTeacherWarp(ROLES, handover((.7, -1.5, 0.)), 0., MAP, {'r1': ARM['r1']}, PWM, wheel_fn=wheels)
    assert t.outcome == 'arm_targets_missing'


def test_relative_compose_roundtrip():
    a, b = (1., -2., .7), (.3, .4, -2.)
    r = ct.relative(a, b)
    c = ct.compose(a, r)
    assert c[0] == pytest.approx(b[0]) and c[1] == pytest.approx(b[1]) and ct.wrap(c[2]-b[2]) == pytest.approx(0.)


# ------------------------------------------------------- closed-loop kinematic

def integrate(pose, drive, dt=.1):
    fwd, left, turn = drive
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (pose[0] + (c*fwd - s*left)*dt, pose[1] + (s*fwd + c*left)*dt, ct.wrap(pose[2] + turn*dt))


def rollout(beam0, *, drop_at=None, cap=200.):
    """Ideal kinematics: robots follow the body command exactly; the beam is
    rigidly attached to robot r1 while held (offset from the handover)."""
    teacher = make(beam0)
    robots = {rid: tuple(v['pose']) for rid, v in handover(beam0)['robots'].items()}
    off = ct.relative(robots['r1'], beam0)
    beam, rows, t = beam0, [], 0.
    min_z = .03
    while t < cap:
        phase = teacher.phase
        held = phase not in ('open', 'raise', 'retreat', 'done') or (phase == 'open' and t - teacher.phase_t < .2)
        if phase == 'lower':
            min_z = max(0., .03*(1 - (t - teacher.phase_t)/teacher.p.lower_s))
        elif phase in ('open', 'raise', 'retreat', 'done'):
            min_z = 0.
        if drop_at is not None and t >= drop_at and phase not in ('lower', 'open', 'raise', 'retreat', 'done'):
            min_z, held = 0., False
        row = truth(beam, robots, held=held, min_z=min_z, t=t)
        rows.append(ce.eval_row(row))
        if teacher.done:
            if t - teacher.events[-1]['t'] > 1.5:
                break
        out = teacher.step(row, t)
        drives = {rid: teacher.log[-1]['drive'][rid] if teacher.log and teacher.log[-1]['t'] == t else (0., 0., 0.)
                  for rid in ROLES}
        for rid in ROLES:
            robots[rid] = integrate(robots[rid], drives[rid])
        if teacher.phase in ct.PHASES[:ct.PHASES.index('open')] and min_z > 0:
            beam = ct.compose(robots['r1'], off)
        t = round(t + .1, 6)
        for rid, (cmd, _) in out.items():
            assert set(cmd) == {'t', 'wheels', 'duration_s', 'pwm'} and set(cmd['pwm']) == {str(s) for s in ct.SERVOS}
    return teacher, rows


def test_kinematic_rollout_reaches_zone_b_and_evaluates_success():
    teacher, rows = rollout((.7, -1.5, .3))
    assert teacher.outcome == 'command_sequence_complete', teacher.events[-3:]
    phases = [e['to'] for e in teacher.events if e['event'] == 'phase']
    assert phases[:3] == ['to_west_staging', 'rotate_door', 'to_door_entry']
    assert {'door_pass', 'zone_settle', 'lower', 'open', 'raise', 'retreat', 'done'} <= set(phases)
    assert teacher.max_stretch < 1e-6 + .03
    lower = next(e['t'] for e in teacher.events if e.get('to') == 'lower')
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=lower, handover_t=0.)
    assert res['success'], res['failure']
    assert res['funnel'] == {'handover': True, 'carried_1m': True, 'door_passed': True, 'zone_inside_final': True,
                             'lowered_resting': True, 'released': True, 'still_1s': True}
    assert res['robot_robot_contact_ticks'] == 0 and res['drop_events'] == []
    # the final teacher frame keeps the arm on the hover target
    assert teacher.pwm['r1'][1] == ct.GRIPPER_OPEN


def test_kinematic_drop_is_caught_by_teacher_and_evaluator_independently():
    teacher, rows = rollout((.7, -1.5, .3), drop_at=12.)
    assert teacher.outcome == 'carry_hold_lost'
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=None, handover_t=0.)
    assert not res['success'] and res['failure'] == 'drop'
    assert 'carry_low' in {d['kind'] for d in res['drop_events']}


def test_phase_cap_gives_phase_specific_code():
    teacher = make((.7, -1.5, .3))
    row = handover((.7, -1.5, .3))
    t = 0.
    while not teacher.done and t < 60:
        teacher.step(row, t)  # robots never move -> tracking stalls after carry_hold
        t = round(t + .1, 6)
    assert teacher.outcome in ('formation_tracking_lost', 'west_staging_timeout')


# ------------------------------------------------------------------ evaluator

def _rows(beam, robots, n=30, **kw):
    return [ce.eval_row(truth(beam, robots, t=k*.1, **kw)) for k in range(n)]


def test_robot_robot_contact_fails_and_wall_contact_is_recorded_only():
    beam = (4.6, -2.1, math.pi/2)
    robots = {'r1': (4.6, -2.6, math.pi/2), 'r2': (4.6, -2.3, -math.pi/2)}  # 0.30 m apart < 2*0.17
    res = ce.evaluate(_rows(beam, robots, held=False, min_z=0.), MAP, list(ROLES), lower_start_t=0.)
    assert res['failure'] == 'robot_robot_contact'
    robots = {'r1': (4.6, -2.6, math.pi/2), 'r2': (5.30, -1.6, -math.pi/2)}  # r2 disc hits the east wall
    res = ce.evaluate(_rows(beam, robots, held=False, min_z=0.), MAP, list(ROLES), lower_start_t=0.)
    assert res['wall_contact_ticks'] > 0 and res['wall_contact_bodies'] == ['r2']
    assert res['success'] and res['failure'] is None  # wall contact is recorded, never a failure term


def test_beam_pierced_by_wall_end_is_beam_contact():
    # divider_1 lower end at (2.2, -2.125); beam centred on it, along x
    row = ce.eval_row(truth((2.2, -2.13, 0.), {'r1': (1.7, -2.6, 0.), 'r2': (2.7, -2.6, math.pi)}, held=True))
    c = ce.contact_proxy(row, ct.wall_rects(MAP), list(ROLES))
    assert c['beam_wall']


def test_not_released_and_not_in_zone():
    beam = (4.6, -2.1, math.pi/2)
    robots = {'r1': (4.6, -2.7, math.pi/2), 'r2': (4.6, -1.5, -math.pi/2)}
    rows = _rows(beam, robots, held=True, min_z=0.)
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=0.)
    assert not res['success'] and res['failure'] == 'not_released'
    res = ce.evaluate(_rows((4.75, -2.1, 0.), robots, held=False, min_z=0.), MAP, list(ROLES), lower_start_t=0.)
    assert not res['funnel']['zone_inside_final'] and res['failure'] == 'not_in_zone'


def test_tilt_and_fast_fall_are_drops_even_during_setdown():
    beam = (4.6, -2.1, math.pi/2)
    robots = {'r1': (4.6, -2.7, math.pi/2), 'r2': (4.6, -1.5, -math.pi/2)}
    rows = _rows(beam, robots, held=False, min_z=0.)
    rows[5]['beam']['tilt_deg'] = 40.
    rows[8]['beam']['xyz'][2] = rows[7]['beam']['xyz'][2] + .05
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=0.)
    kinds = {d['kind'] for d in res['drop_events']}
    assert {'tilt', 'fall'} <= kinds and res['failure'] == 'drop'


# ------------------------------------------------------------------- recorder

def test_carry_label_fields_match_runner_and_dataset_keys():
    clean = ct.make_command(1., PWM['r1'], (0., 0., 0.))
    row = cr.carry_label('ep:3:r1', clean=clean, applied=clean, done=False, phase='door_pass', outcome=None,
                         assignment_source='fixed')
    assert tuple(row) == cr.LABEL_FIELDS
    assert row['skill'] == 'release' and row['destination_zone'] == 'B' and row['local_skill_sample'] is True
    assert row['teacher_phase'] == 'carry:door_pass' and row['terminal_reason'] is None


def test_student_row_is_valid_v5_observation_with_own_inputs_only():
    history, images = cr.new_buffers()
    clean = ct.make_command(0., PWM['r1'], (0., 0., 0.))
    for k in range(16):
        history.append({**clean, 't': k*.1})
    rec = cr.CarryRecorder('r1', 'teal', history=history, images=images, episode_id='ep')
    for k in range(60):
        rec.add_frame(k, k*.1, b'jpeg%d' % k)
    row = rec.student_row(59, 5.9, clean['pwm'])
    from harness import grasp_act_contract as contract
    assert set(row) == contract.FIELDS
    assert row['skill'] == 'release' and row['destination_zone'] == 'B' and row['role'] == 'teal'
    assert len(row['issued']) == contract.HISTORY and len(row['rgb']) == contract.RGB_HISTORY
    assert all(r['robot_id'] == 'r1' for r in row['rgb'])


def test_recorder_rejects_non_beam_roles():
    history, images = cr.new_buffers()
    with pytest.raises(ValueError):
        cr.CarryRecorder('r1', 'west', history=history, images=images, episode_id='ep')


# --------------------------------------------------------------------- runner

def _runner_function():
    tree = ast.parse((ROOT/'scripts/run_grasp_act_teacher.py').read_text())
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')


def test_runner_keeps_warp_flow_scheduling_shape():
    """scripts/warp_flow_episode.py (root tree) requires exactly one nested
    ``advance`` definition and two ``advance(...)`` calls in ``run``."""
    fn = _runner_function()
    defs = [n for n in ast.walk(fn) if isinstance(n, ast.FunctionDef) and n is not fn and n.name == 'advance']
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'advance']
    assert len(defs) == 1 and len(calls) == 2


def test_runner_signature_defaults_off():
    fn = _runner_function()
    kw = {a.arg: d.value for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if isinstance(d, ast.Constant)}
    assert kw['pair_carry'] == 'off' and kw['carry_cap_s'] == 110.


@pytest.mark.parametrize('kwargs,match', [
    ({'pair_carry': 'bogus'}, 'unknown pair carry'),
    ({'pair_carry': ct.MODE, 'teacher_profile': 'legacy'}, 'visible_only'),
    ({'pair_carry': ct.MODE, 'teacher_profile': 'visible_only', 'carry_cap_s': 0.}, 'finite carry cap'),
    ({'pair_carry': ct.MODE, 'teacher_profile': 'visible_only', 'probe': True}, 'probe'),
])
def test_runner_rejects_invalid_carry_combinations(tmp_path, kwargs, match):
    from scripts import run_grasp_act_teacher as runner
    with pytest.raises(ValueError, match=match):
        runner.run({'roles': ROLES}, tmp_path, **kwargs)


# ------------------------------------- drive response (eval-only, P2 follow-up)

def _teacher_rollout(teacher, beam0, *, speed_gain=1., min_z_fn=None, cap=200.):
    """Like ``rollout`` but with a body-speed gain (GT moves speed_gain x the
    command) and an optional arm-driven beam height model for the set-down."""
    robots = {rid: tuple(v['pose']) for rid, v in handover(beam0)['robots'].items()}
    off = ct.relative(robots['r1'], beam0)
    beam, rows, t, min_z = beam0, [], 0., .03
    while t < cap:
        phase = teacher.phase
        if min_z_fn is not None:
            min_z = min_z_fn(teacher)
            held = phase not in ('raise', 'retreat', 'done') and not (phase == 'open' and t - teacher.phase_t >= .2)
        else:
            held = phase not in ('open', 'raise', 'retreat', 'done') or (phase == 'open' and t - teacher.phase_t < .2)
            if phase == 'lower':
                min_z = max(0., .03*(1 - (t - teacher.phase_t)/teacher.p.lower_s))
            elif phase in ('open', 'raise', 'retreat', 'done'):
                min_z = 0.
        row = truth(beam, robots, held=held, min_z=min_z, t=t)
        rows.append(ce.eval_row(row))
        if teacher.done and t - teacher.events[-1]['t'] > 1.5:
            break
        teacher.step(row, t)
        drives = {rid: teacher.log[-1]['drive'][rid] if teacher.log and teacher.log[-1]['t'] == t else (0., 0., 0.)
                  for rid in ROLES}
        for rid in ROLES:
            robots[rid] = integrate(robots[rid], [speed_gain*v for v in drives[rid]])
        if teacher.phase in ct.PHASES[:ct.PHASES.index('open')] and min_z > 0:
            beam = ct.compose(robots['r1'], off)
        t = round(t + .1, 6)
    return rows


def test_drive_response_matches_ideal_kinematics_and_is_eval_only():
    teacher = make((.7, -1.5, .3))
    rows = _teacher_rollout(teacher, (.7, -1.5, .3))
    assert teacher.outcome == 'command_sequence_complete'
    resp = ce.drive_response(rows, teacher.log, list(ROLES))
    assert resp['affects_success'] is False and resp['affects_phase_timeout'] is False
    for rid in ROLES:
        a = resp['phases']['all'][rid]
        assert a['speed_ratio'] == pytest.approx(1., abs=1e-6) and a['stall_ticks'] == 0
    assert {'to_west_staging', 'door_pass', 'to_zone'} <= set(resp['phases'])


def test_slow_body_shows_in_drive_response_not_in_success_or_timeout_code():
    teacher = make((.7, -1.5, .3))
    rows = _teacher_rollout(teacher, (.7, -1.5, .3), speed_gain=.4, cap=120.)
    resp = ce.drive_response(rows, teacher.log, list(ROLES))
    for rid in ROLES:
        assert resp['phases']['all'][rid]['speed_ratio'] == pytest.approx(.4, abs=1e-6)
    lower = next((e['t'] for e in teacher.events if e.get('to') == 'lower'), None)
    plain = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=lower, handover_t=0.)
    # the evaluator verdict does not depend on the drive diagnostic
    assert set(plain) == set(ce.evaluate(rows, MAP, list(ROLES), lower_start_t=lower, handover_t=0.))
    rep = ce.phase_report(teacher.diagnostic(), resp)
    assert rep['timeout_source'] == 'teacher_events'
    for r in rep['phases']:
        if r['drive_response'] is not None:
            assert r['drive_response']['r1']['speed_ratio'] == pytest.approx(.4, abs=1e-6)
        # a timeout flag only ever comes from a teacher fail event
        assert r['teacher_timeout'] == (r['teacher_code'] is not None and r['teacher_code'].endswith('_timeout'))


def test_phase_report_flags_the_timed_out_phase():
    teacher = make((.7, -1.5, .3))
    row = handover((.7, -1.5, .3))
    t = 0.
    teacher.p.phase_caps_s['to_west_staging'] = 2.     # frozen dataclass, mutable dict: test-only
    try:
        while not teacher.done and t < 10:
            teacher.step(row, t)
            t = round(t + .1, 6)
    finally:
        teacher.p.phase_caps_s['to_west_staging'] = 40.
    assert teacher.outcome == 'west_staging_timeout'
    rows = [ce.eval_row({**row, 't': k*.1}) for k in range(int(t*10) + 1)]
    resp = ce.drive_response(rows, teacher.log, list(ROLES))
    rep = ce.phase_report(teacher.diagnostic(), resp)
    last = rep['phases'][-1]
    assert last['phase'] == 'to_west_staging' and last['teacher_timeout'] and last['teacher_code'] == 'west_staging_timeout'
    assert last['drive_response']['r1']['stall_frac'] == pytest.approx(1.)  # commanded, robots never moved


# ------------------------------------------ set-down: floor_contact_v1 (opt-in)

ARM_DEEP = {rid: {**ARM[rid], 'place_deep': {1: 1500, 3: 1500, 4: 1600, 5: 1500, 6: 1500}} for rid in ROLES}


def _beam_z_from_arm(teacher, floor_at=1460):
    """min_z falls linearly with servo 3 from the lift (1200) to the floor at
    ``floor_at``; the grasp-height place pose (1400) stops 6.9 mm above it."""
    if teacher.phase in ('raise', 'retreat', 'done'):
        return 0.
    s3 = teacher.pwm['r1'][3]
    return max(0., .03*(1 - (s3 - 1200)/(floor_at - 1200)))


def _make_lower(mode, arm=ARM_DEEP):
    params = ct.Params(lower_mode=mode)
    if mode == 'floor_contact_v1':
        params = ct.Params(lower_mode=mode, phase_caps_s={**params.phase_caps_s, 'lower': params.lower_max_s + 1.})
    return ct.PairCarryTeacherWarp(ROLES, handover((.7, -1.5, .3)), 0., MAP, arm, PWM, wheel_fn=wheels, params=params)


def _min_z_at_open(rows, teacher):
    t_open = next(e['t'] for e in teacher.events if e.get('to') == 'open')
    return next(r['beam']['min_z'] for r in rows if r['t'] >= t_open - 1e-9)


def test_default_lower_mode_is_grasp_height_and_unchanged():
    assert ct.Params().lower_mode == 'grasp_height'
    teacher = _make_lower('grasp_height')
    rows = _teacher_rollout(teacher, (.7, -1.5, .3), min_z_fn=_beam_z_from_arm)
    assert teacher.outcome == 'command_sequence_complete'
    assert not any(e.get('event') == 'floor_touch' for e in teacher.events)
    # beam slipped in the grasp model: the IK grasp height opens the jaws 6.9 mm up
    assert _min_z_at_open(rows, teacher) > .006


def test_floor_contact_lowering_stops_at_touch_and_places():
    teacher = _make_lower('floor_contact_v1')
    rows = _teacher_rollout(teacher, (.7, -1.5, .3), min_z_fn=_beam_z_from_arm)
    assert teacher.outcome == 'command_sequence_complete', teacher.events[-3:]
    touch = next(e for e in teacher.events if e.get('event') == 'floor_touch')
    assert touch['min_z'] <= teacher.p.floor_margin_m and touch['lower_elapsed_s'] <= teacher.p.lower_max_s
    d = teacher.diagnostic()
    assert d['lower_mode'] == 'floor_contact_v1' and d['floor_touch_pwm']['r1']['3'] < 1500
    assert _min_z_at_open(rows, teacher) <= teacher.p.floor_margin_m
    lower = next(e['t'] for e in teacher.events if e.get('to') == 'lower')
    res = ce.evaluate(rows, MAP, list(ROLES), lower_start_t=lower, handover_t=0.)
    assert res['success'], res['failure']


def test_floor_contact_no_touch_fails_closed_without_opening():
    teacher = _make_lower('floor_contact_v1')
    _teacher_rollout(teacher, (.7, -1.5, .3), min_z_fn=lambda tc: _beam_z_from_arm(tc, floor_at=1700))
    assert teacher.outcome == ct.LOWER_NO_CONTACT
    assert teacher.pwm['r1'][1] == 1500        # gripper never opened in the air


def test_floor_contact_requires_place_deep_target():
    assert _make_lower('floor_contact_v1', arm=ARM).outcome == 'arm_targets_missing'
    with pytest.raises(ValueError, match='lower mode'):
        ct.PairCarryTeacherWarp(ROLES, handover((.7, -1.5, .3)), 0., MAP, ARM_DEEP, PWM, wheel_fn=wheels,
                                params=ct.Params(lower_mode='bogus'))
    with pytest.raises(ValueError, match='lower phase cap'):
        ct.PairCarryTeacherWarp(ROLES, handover((.7, -1.5, .3)), 0., MAP, ARM_DEEP, PWM, wheel_fn=wheels,
                                params=ct.Params(lower_mode='floor_contact_v1'))


@pytest.mark.parametrize('kwargs,match', [
    ({'carry_lower': 'floor_contact_v1'}, 'requires pair carry'),
    ({'pair_carry': ct.MODE, 'teacher_profile': 'visible_only', 'carry_lower': 'x'}, 'unknown carry lower'),
])
def test_runner_rejects_invalid_lower_mode(tmp_path, kwargs, match):
    from scripts import run_grasp_act_teacher as runner
    with pytest.raises(ValueError, match=match):
        runner.run({'roles': ROLES}, tmp_path, **kwargs)


def test_runner_lower_default_is_grasp_height():
    fn = _runner_function()
    kw = {a.arg: d.value for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if isinstance(d, ast.Constant)}
    assert kw['carry_lower'] == 'grasp_height'


# ------------------------------------------------ P3 recorder: v7 clock + stages

def test_v7_clock_ignores_two_pwm_dither_and_resets_on_three():
    clk = cr.DeadbandIssuedClock()
    base = {'1': 1500, '3': 1400, '4': 1600, '5': 1500, '6': 1500}
    assert clk.observe(('release', 'B'), 0., base)['pwm_elapsed_s'] == 0.
    assert clk.observe(('release', 'B'), .1, {**base, '3': 1402})['pwm_elapsed_s'] == pytest.approx(.1)
    assert clk.observe(('release', 'B'), .2, {**base, '3': 1400})['pwm_elapsed_s'] == pytest.approx(.2)
    out = clk.observe(('release', 'B'), .3, {**base, '3': 1403})
    assert out['pwm_elapsed_s'] == 0. and out['skill_elapsed_s'] == pytest.approx(.3) and clk.resets == 1
    # instruction change resets only the skill clock
    out = clk.observe(('grasp', 'B'), .4, {**base, '3': 1403})
    assert out['skill_elapsed_s'] == 0. and out['pwm_elapsed_s'] == pytest.approx(.1)


def test_v7_clock_deadband_zero_equals_contract_clock():
    from harness import grasp_act_contract as contract
    import random
    rng = random.Random(7)
    a, b = cr.DeadbandIssuedClock(0), contract.IssuedClock()
    pwm = {'1': 1500, '3': 1400, '4': 1600, '5': 1500, '6': 1500}
    for k in range(200):
        if rng.random() < .3:
            pwm = {**pwm, str(rng.choice((1, 3, 4, 5, 6))): 1500 + rng.randint(-4, 4)}
        inst = ('grasp',) if k < 100 else ('release',)
        assert a.observe(inst, k*.1, pwm) == b.observe(inst, k*.1, dict(pwm))
    with pytest.raises(ValueError):
        cr.DeadbandIssuedClock(5)


def test_carry_recorder_shares_the_runner_clock_across_segments():
    clk = cr.DeadbandIssuedClock()
    pwm = {'1': 1500, '3': 1400, '4': 1600, '5': 1500, '6': 1500}
    clk.observe(('grasp', 'teal', True), 0., pwm)
    clk.observe(('grasp', 'teal', True), 3., pwm)
    history, images = cr.new_buffers()
    clean = ct.make_command(0., PWM['r1'], (0., 0., 0.))
    for k in range(16):
        history.append({**clean, 't': k*.1})
    rec = cr.CarryRecorder('r1', 'teal', history=history, images=images, episode_id='ep', clock=clk)
    for k in range(60):
        rec.add_frame(k, k*.1, b'j%d' % k)
    row = rec.student_row(31, 3.1, pwm)
    assert row['skill_elapsed_s'] == 0.                       # new instruction (release, B)
    assert row['pwm_elapsed_s'] == pytest.approx(3.1)         # PWM clock continuous from the grasp segment


def test_only_first_done_carry_row_is_a_local_sample():
    history, images = cr.new_buffers()
    rec = cr.CarryRecorder('r1', 'teal', history=history, images=images, episode_id='ep')
    clean = ct.make_command(0., PWM['r1'], (0., 0., 0.))
    rows = [rec.label_row(k, clean=clean, applied=clean, done=done, phase=ph, outcome=oc)
            for k, (done, ph, oc) in enumerate([(False, 'retreat', None), (True, 'done', 'command_sequence_complete'),
                                                (True, 'done', 'command_sequence_complete')])]
    assert [r['local_skill_sample'] for r in rows] == [True, True, False]
    assert rows[1]['terminal_reason'] == 'command_sequence_complete'


def _phase_literals(path):
    import re
    text = (ROOT/path).read_text()
    return set(re.findall(r"_set\(['\"]([a-z_]+)['\"]", text)) | set(re.findall(r"\bphase *= *['\"]([a-z_]+)['\"]", text))


def test_phase_table_covers_every_teacher_phase_literal():
    grasp = _phase_literals('sim/grasp_act_teacher.py') | _phase_literals('sim/grasp_act_teacher_v3.py')
    assert grasp == set(cr.GRASP_PHASE_TO_STAGE), grasp ^ set(cr.GRASP_PHASE_TO_STAGE)
    assert set(cr.CARRY_PHASE_TO_STAGE) == set(ct.PHASES)
    assert set(cr.TEACHER_PHASE_TO_STAGE.values()) <= set(cr.STAGES)
    # every stage except recover-only paths is reachable from a teacher label
    assert set(cr.TEACHER_PHASE_TO_STAGE.values()) == set(cr.STAGES)
    with pytest.raises(ValueError, match='unmapped'):
        cr.stage_for('carry:unknown')


def test_phase_table_matches_design_doc():
    import re
    text = (ROOT/'experiments/2026-10-21-pairact-p2/DESIGN.md').read_text()
    block = text[text.index('<!-- phase-stage-table -->'):text.index('<!-- /phase-stage-table -->')]
    rows = re.findall(r"^\| `([a-z_:]+)` \| `([a-z_]+)` \|", block, re.M)
    assert dict(rows) == cr.TEACHER_PHASE_TO_STAGE


def test_phase_table_matches_pairact_r1_copy():
    """Same mapping as harness/pairact_r1.py on dsh/pairact-carry-r1 (skipped
    when that ref is not fetched)."""
    import re
    import subprocess
    try:
        src = subprocess.check_output(['git', 'show', 'origin/dsh/pairact-carry-r1:harness/pairact_r1.py'],
                                      cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip('origin/dsh/pairact-carry-r1 not available')
    m = re.search(r"^TEACHER_PHASE_TO_STAGE = \{.*?^TEACHER_PHASE_TO_STAGE\['carry:done'\] = 'complete'$", src, re.S | re.M)
    ns = {}
    exec(m.group(0), ns)
    r1 = ns['TEACHER_PHASE_TO_STAGE']
    stages = re.search(r"^STAGES = (\(.*?\))$", src, re.M).group(1)
    assert eval(stages) == cr.STAGES
    missing = set(cr.TEACHER_PHASE_TO_STAGE) - set(r1)
    assert not missing, f'pairact_r1 lacks {sorted(missing)}'
    assert {k: r1[k] for k in cr.TEACHER_PHASE_TO_STAGE} == cr.TEACHER_PHASE_TO_STAGE


def test_runner_records_carry_with_recorder_and_v7_clock():
    text = (ROOT/'scripts/run_grasp_act_teacher.py').read_text()
    assert 'recorder hook not wired' not in text
    assert "clocks[rid]=v5.IssuedClock() if pair_carry=='off' else DeadbandIssuedClock()" in text
    assert 'recorders[rid].student_row(i,now,previous[rid]' in text and 'recorders[rid].label_row(' in text
    assert "report['grasp_physical_success']" in text


# ---------------------------------------------- P5 student eval (runner side)

from harness import pairact_student_eval as se

CFG = {'mode': se.MODE, 'python': 'py', 'source': '/src', 'model': '/ckpt', 'config': '/cfg.json', 'device': 'cpu'}


class FakeWorker:
    """Scripted stand-in for scripts/pairact_r1_student_worker.py (records requests)."""
    def __init__(self, ready_after=0):
        self.requests, self.ready_after, self.n = [], ready_after, 0

    def request(self, payload):
        self.requests.append(json.loads(json.dumps(payload)))
        op = payload['op']
        if op == 'reset':
            return {'ok': True}
        if op == 'propose':
            self.n += 1
            return {'robots': {r: {'ready': self.n > self.ready_after, 'observation': {'t': payload['t']},
                                   'rgb_path': 'rgb', 'stage': 'ready'} for r in payload['robots']}}
        if op == 'issue':
            cmd = {r: {'command': {'t': payload['t'], 'wheels': [0.]*4, 'duration_s': [0.]*4,
                                   'pwm': {str(s): 1500 for s in ct.SERVOS}},
                       'done': False, 'stage': 'ready', 'segment': 'grasp', 'permit': payload['permits'][r],
                       'blocked': False} for r in payload['permits']}
            return {'robots': cmd, 'finished': False}
        return {'events': [], 'teacher_actions': 0}


def _episode(worker):
    from harness.grasp_act_start_sync import GraspStartSync
    init = {r: {'t': 0., 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': {str(s): 1500 for s in ct.SERVOS}}
            for r in ROLES}
    return se.start(CFG, ROLES, 'ep', init, seed=8342000, factory=GraspStartSync, client=worker)[0], init


def test_student_requests_carry_only_own_camera_and_issued_command():
    worker = FakeWorker()
    ep, init = _episode(worker)
    ep.tick(0., {'r1': b'a', 'r2': b'b'}, init)
    propose = next(r for r in worker.requests if r['op'] == 'propose')
    assert set(propose) == {'op', 't', 'robots'}
    assert all(set(v) == {'jpeg', 'issued'} for v in propose['robots'].values())
    issue = next(r for r in worker.requests if r['op'] == 'issue')
    assert set(issue) == {'op', 't', 'permits'} and all(type(v) is bool for v in issue['permits'].values())
    with pytest.raises(ValueError, match='own camera'):
        ep.tick(.1, {'r1': b'a'}, init)


def test_student_protocol_go_ack_then_permits_and_rearm_on_withdrawal():
    worker = FakeWorker(ready_after=2)
    ep, init = _episode(worker)
    permits = []
    for k in range(40):
        ep.tick(k*.1, {'r1': b'a', 'r2': b'b'}, init)
        permits.append(next(r for r in reversed(worker.requests) if r['op'] == 'issue')['permits'])
    assert not any(permits[0].values())
    assert all(permits[-1].values())          # READY -> GO -> ACK -> START after the bounded delays
    events = [e['event'] for e in ep.sync.events]
    assert events[:1] == ['GO'] and 'START' in events
    ep.sync.tick({'r1': False, 'r2': True}, 5.)
    assert ep.sync.events[-1]['event'] == 'READY_withdrawn_rearm'


def test_student_funnel_chain_and_zone_entry_boundary():
    f = se.StudentFunnel()
    beam = (1., 1., 0.)
    ends = {'teal': [.73, 1., .02], 'blue': [1.27, 1., .02]}
    robots = {'r1': {'pose': [.73 - .203, 1., 0.]}, 'r2': {'pose': [1.27 + .203, 1., math.pi]}}
    truth_row = {'beam': {'pose': list(beam), 'ends': ends}, 'robots': robots, 'contacts': {'r1': [1., 1.], 'r2': [1., 1.]}}
    passed = f.add(0., truth_row, ROLES, {'r1': True, 'r2': True}, True)
    assert all(passed.values())
    rec = f.record({'success': False, 'funnel': {'carried_1m': True, 'door_passed': False}, 'drop_events': []})
    assert rec['reached'] == {'approach': True, 'alignment': True, 'READY': True, 'grasp': True, 'hold_3s': True,
                              'carry_1m': True, 'door': False, 'place': False}
    assert rec['first_failure'] == 'door'
    assert se.StudentFunnel().record(None)['first_failure'] == 'approach'
    rows = [ce.eval_row(truth((x, -2.1, math.pi/2), {'r1': (x, -2.7, 0.), 'r2': (x, -1.5, 0.)}, held=True, t=k*.1))
            for k, x in enumerate((3.5, 4.0, 4.6, 4.6))]
    assert ce.zone_entry_t(rows, MAP) == pytest.approx(.2)


def test_student_config_and_runner_combinations_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        se.validate_config({**CFG, 'gt': True})
    from scripts import run_grasp_act_teacher as runner
    with pytest.raises(ValueError, match='visible_only pair carry'):
        runner.run({'roles': ROLES}, tmp_path, teacher_profile='visible_only', student_eval=CFG)
    with pytest.raises(ValueError, match='never records'):
        runner.run({'roles': ROLES}, tmp_path, teacher_profile='visible_only', pair_carry=ct.MODE, noise=True,
                   student_eval=CFG)


def test_runner_student_branch_never_steps_teachers():
    text = (ROOT/'scripts/run_grasp_act_teacher.py').read_text()
    assert "for rid,t in (teachers.items() if carry is None and student_ep is None else ()):" in text
    assert "if strict and carry is None and student_ep is None:" in text
    fn = _runner_function()
    kw = {a.arg: d for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults)}
    assert isinstance(kw['student_eval'], ast.Constant) and kw['student_eval'].value is None


def test_worker_client_handshake_and_command_line():
    class P:
        def __init__(self, argv, **kw):
            self.argv, self.kw = argv, kw
            import io
            self.stdout = io.StringIO(json.dumps({'ready': True, 'mode': se.MODE}) + '\n')
            self.stdin = io.StringIO()
    client = se.WorkerClient(CFG, popen=P)
    assert client.proc.argv == ['py', '-m', 'scripts.pairact_r1_student_worker', '--model', '/ckpt',
                                '--config', '/cfg.json', '--device', 'cpu']
    assert client.proc.kw['cwd'] == '/src'
