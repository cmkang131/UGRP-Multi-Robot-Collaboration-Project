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
