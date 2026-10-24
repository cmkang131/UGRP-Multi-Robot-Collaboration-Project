"""Solo carry teacher, grounding glue and plan validation (derived, unverified; CPU only, no physics)."""
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import pair_carry_teacher_warp as ct
from harness import solo_carry_contract as sc
from harness import solo_carry_eval as ev
from harness import solo_carry_teacher as st
from harness import solo_carry_visible as vis

ROOT = Path(__file__).resolve().parents[1]
MAP = json.loads((ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json').read_text())
SLOT = {'zone': 'zone_B', 'pose': [4.6, -2.1, 0.], 'half_extents_m': [.10, .10]}
ARM = {'r1': {'place': {1: 1500, 3: 1400, 4: 1600, 5: 1500, 6: 1500},
              'hover': {1: 2000, 3: 1300, 4: 1700, 5: 1500, 6: 1500}}}
PWM = {'r1': {1: 1500, 3: 1200, 4: 1800, 5: 1500, 6: 1500}}
REACH = .2          # synthetic robot-centre to can-centre distance along the robot heading
PARKED_BEAM = {'xy': [1.6, 0.4], 'radius': .30}
BASE_COMMIT = '75929e7719ad98a089e3dda5251f4249d8bae511'     # the pinned pairact tree this branch is cut from


def wheels(effort):
    return [0.]*4, [0.]*4


def truth(can, robot, *, held, min_z=.065, tilt=1., t=0., objects=None):
    f = [4.3, 4.3] if held else [0., 0.]
    return {'t': t, 'beam': {'pose': list(can), 'min_z': min_z, 'tilt_deg': tilt},
            'robots': {'r1': {'pose': list(robot)}, 'r2': {'pose': [-.8, 1.2, 0.]}, 'r3': {'pose': [-.8, 1.6, 0.]}},
            'contacts': {'r1': f}, 'objects': objects if objects is not None else {}}


def handover(robot=(.5, -1.5, 0.)):
    can = ct.compose(robot, (REACH, 0., 0.))
    return truth(can, robot, held=True), can


def make(robot=(.5, -1.5, 0.), slot=SLOT, arm=ARM, obstacles=(), **kw):
    row, _ = handover(robot)
    return st.SoloCarryTeacher('r1', row, 0., MAP, arm, PWM, slot, wheel_fn=wheels, obstacles=obstacles, **kw)


def integrate(pose, drive, dt=.1):
    fwd, left, turn = drive
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (pose[0] + (c*fwd - s*left)*dt, pose[1] + (s*fwd + c*left)*dt, ct.wrap(pose[2] + turn*dt))


def rollout(robot0=(.5, -1.5, 0.), *, slot=SLOT, drop_at=None, cap=200.):
    """Ideal kinematics: the robot follows its body command exactly; the can is rigid in the grip while held."""
    teacher = make(robot0, slot=slot)
    row0, can0 = handover(robot0)
    robot, can, off = robot0, can0, ct.relative(robot0, can0)
    rows, t, min_z = [], 0., .065
    while t < cap:
        phase = teacher.phase
        held = phase not in ('open', 'raise', 'retreat', 'done') or (phase == 'open' and t - teacher.phase_t < .2)
        if phase == 'lower':
            min_z = max(0., .065*(1 - (t - teacher.phase_t)/teacher.p.lower_s))
        elif phase in ('open', 'raise', 'retreat', 'done'):
            min_z = 0.
        if drop_at is not None and t >= drop_at and phase not in ('lower', 'open', 'raise', 'retreat', 'done'):
            min_z, held = 0., False
        row = truth(can, robot, held=held, min_z=min_z, t=t)
        rows.append(row)
        if teacher.done and t - teacher.events[-1]['t'] > 1.5:
            break
        out = teacher.step(row, t)
        drive = teacher.log[-1]['drive']['r1'] if teacher.log and teacher.log[-1]['t'] == t else (0., 0., 0.)
        robot = integrate(robot, drive)
        if teacher.phase in ct.PHASES[:ct.PHASES.index('open')] and min_z > 0:
            can = ct.compose(robot, off)
        t = round(t + .1, 6)
        for _, (cmd, _) in out.items():
            assert set(cmd) == {'t', 'wheels', 'duration_s', 'pwm'} and set(cmd['pwm']) == {str(s) for s in ct.SERVOS}
    return teacher, rows


# ------------------------------------------------------------------ teacher

def test_ideal_kinematic_rollout_completes_and_the_gates_pass():
    teacher, rows = rollout()
    assert teacher.outcome == 'command_sequence_complete', teacher.events[-3:]
    phases = [e['to'] for e in teacher.events if e.get('event') == 'phase']
    assert phases == ['to_west_staging', 'rotate_door', 'to_door_entry', 'door_pass', 'to_east_staging',
                      'rotate_zone', 'to_zone', 'zone_settle', 'lower', 'open', 'raise', 'retreat', 'done']
    lower = next(e['t'] for e in teacher.events if e.get('event') == 'phase' and e['to'] == 'lower')
    # ideal-kinematics rows (no physics): teacher and gates must agree end to end
    report = ev.evaluate(rows, SLOT, 'r1', lower_start_t=lower, cap_s=200.)
    assert report['success'] is True, report['gates']
    assert sc.slot_contains(SLOT, rows[-1]['beam']['pose'][:2], st.CARGO_RADIUS_M)
    assert teacher.p.carry_cap_s == 110. and rows[-1]['t'] < teacher.p.carry_cap_s       # ideal tracking fits the pair cap
    assert teacher.diagnostic()['mode'] == sc.MODE and teacher.diagnostic()['status'] == sc.STATUS


def test_slot_target_is_the_last_route_waypoint_and_no_pair_beam_geometry_is_required():
    teacher = make()
    tags = [t for t, _ in teacher.route]
    assert tags[-1] == 'to_zone' and teacher.route[-1][1][:2] == (4.6, -2.1)
    assert teacher.outcome is None and teacher.route_info['slot'] == [4.6, -2.1, 0.]
    assert teacher.rids == ('r1',) and teacher.roles == {'r1': 'teal'}


def test_commands_are_the_14_dim_issued_format():
    teacher = make()
    row, _ = handover()
    out = teacher.step(row, 0.)
    cmd, done = out['r1']
    assert done is False and set(cmd) == {'t', 'wheels', 'duration_s', 'pwm'}


@pytest.mark.parametrize('slot,code', [
    ({**SLOT, 'pose': [4.6, -2.1 + .62, 0.]}, 'zone_unreachable'),        # rectangle pokes out of zone B
    ({**SLOT, 'half_extents_m': [.5, .1]}, 'zone_unreachable'),
])
def test_slot_outside_zone_b_fails_closed(slot, code):
    teacher = make(slot=slot)
    assert teacher.outcome == code and teacher.done


def test_missing_arm_targets_and_wrong_robot_fail_closed():
    assert make(arm={}).outcome == 'arm_targets_missing'
    assert make(arm={'r1': {'place': ARM['r1']['place']}}).outcome == 'arm_targets_missing'
    row, _ = handover()
    with pytest.raises(ValueError):
        st.SoloCarryTeacher('r2', row, 0., MAP, ARM, PWM, SLOT, wheel_fn=wheels)
    with pytest.raises(ValueError):
        st.SoloCarryTeacher('r1', row, 0., MAP, ARM, PWM, SLOT, wheel_fn=wheels,
                            params=ct.Params(lower_mode='floor_contact_v1'))


def test_parked_beam_on_the_route_is_a_blocking_obstacle_not_ignored():
    blockers = [{'id': 'beam_1', 'xy': [1.4, -1.5], 'radius': .30}, {'id': 'beam_x', 'xy': [.9, -1.1], 'radius': .6}]
    assert make(obstacles=blockers).outcome == 'route_blocked'
    assert make(obstacles=[{'id': 'beam_1', 'xy': PARKED_BEAM['xy'], 'radius': PARKED_BEAM['radius']}]).outcome is None


def test_obstacles_for_keeps_the_parked_beam_but_not_the_carried_can():
    objects = {'beam_1': {'xy': [1.6, .4], 'radius': .3}, 'can_1': {'xy': [.7, -1.5], 'radius': .02}}
    row, _ = handover()
    row['objects'] = objects
    discs = {d['id']: d for d in st.obstacles_for(row, 'r1')}
    assert 'beam_1' in discs and 'can_1' not in discs and {'r2', 'r3'} <= set(discs) and 'r1' not in discs


def test_hold_lost_during_carry_aborts_with_a_code_never_a_silent_drop():
    teacher, rows = rollout(drop_at=8.)
    assert teacher.outcome == 'carry_hold_lost' and teacher.done


def test_total_cap_and_phase_cap_fail_closed():
    teacher = make(params=ct.Params(carry_cap_s=5.))
    row, _ = handover()
    teacher.step(row, 0.)
    out = teacher.step(row, 5.)
    assert teacher.outcome == 'carry_total_timeout' and out['r1'][1] is True


def test_pair_teacher_is_unchanged_and_solo_state_does_not_leak_into_it():
    import subprocess
    run = subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', BASE_COMMIT, '--', 'harness/pair_carry_teacher_warp.py',
                          'harness/pair_carry_recorder.py', 'harness/pair_carry_eval.py', 'harness/grasp_act_contract.py',
                          'sim/grasp_act_teacher_v3.py', 'harness/grasp_act_visible_world.py'])
    assert run.returncode == 0, 'a pinned pair/grasp file differs from the base commit'
    assert not hasattr(ct.PairCarryTeacherWarp, 'slot')


# ------------------------------------------------------------ plan validation

def good_plan():
    return {'roles': {'r1': 'teal'}, 'solo_cargo': {'item_id': 'can_1', 'kind': 'can', 'pose': [.7, -1.5, 0.]},
            'solo_slot': copy.deepcopy(SLOT), 'episode_id': 'e0', 'seed': 1}


def runner_args(**over):
    base = dict(pair_carry='off', teacher_profile='visible_only', plan=good_plan(), probe=False, student_eval=None,
                carry_cap_s=110., record_training=False, handoff_observation='off')
    base.update(over)
    return base


def test_validate_runner_args_off_is_a_noop_and_hard_requirements_hold():
    sc.validate_runner_args('off', **runner_args(pair_carry='pair_carry_gt_v1', teacher_profile='legacy', plan={}))
    sc.validate_runner_args('solo_box_v1', **runner_args())
    with pytest.raises(ValueError, match='unknown solo carry mode'):
        sc.validate_runner_args('solo_v2', **runner_args())
    with pytest.raises(ValueError, match='mutually exclusive'):
        sc.validate_runner_args('solo_box_v1', **runner_args(pair_carry='pair_carry_gt_v1'))
    with pytest.raises(ValueError, match='visible_only'):
        sc.validate_runner_args('solo_box_v1', **runner_args(teacher_profile='legacy'))
    with pytest.raises(ValueError, match='probe'):
        sc.validate_runner_args('solo_box_v1', **runner_args(probe=True))
    with pytest.raises(ValueError, match='student eval'):
        sc.validate_runner_args('solo_box_v1', **runner_args(student_eval={'mode': 'x'}))
    for cap in (0., -1., 121., float('inf')):
        with pytest.raises(ValueError, match='carry cap'):
            sc.validate_runner_args('solo_box_v1', **runner_args(carry_cap_s=cap))
    with pytest.raises(ValueError, match='visible handoff'):
        sc.validate_runner_args('solo_box_v1', **runner_args(record_training=True))
    sc.validate_runner_args('solo_box_v1', **runner_args(record_training=True, handoff_observation='visible_handoff_v1'))


@pytest.mark.parametrize('mutate', [
    lambda p: p.pop('solo_cargo'), lambda p: p.pop('solo_slot'),
    lambda p: p.update(roles={'r1': 'teal', 'r2': 'blue'}), lambda p: p.update(roles={'r1': 'blue'}),
    lambda p: p['solo_cargo'].update(kind='long_beam'), lambda p: p['solo_cargo'].update(item_id='beam_1'),
    lambda p: p['solo_cargo'].update(pose=[.7, float('nan'), 0.]), lambda p: p['solo_cargo'].update(extra=1),
    lambda p: p['solo_slot'].update(zone='zone_A'), lambda p: p['solo_slot'].update(half_extents_m=[0., .1]),
    lambda p: p['solo_slot'].update(pose=[4.6, -2.1]),
])
def test_bad_plans_are_rejected(mutate):
    plan = good_plan()
    mutate(plan)
    with pytest.raises(ValueError):
        sc.validate_plan(plan)


def test_cargo_kind_is_a_one_robot_catalogue_kind():
    from sim import zone_cargo
    spec = zone_cargo.kind(sc.OBJECT_KIND)
    assert spec.tier == 'solo' and spec.required_carriers == 1 and spec.mass_kg == .080
    one_robot_limit_low_kg = .66      # experiments/2026-09-25-zone-cargo-catalogue/README.md s1 (0.66 ok, 0.68 tips)
    assert spec.mass_kg < one_robot_limit_low_kg*.2
    assert zone_cargo.kind('heavy_crate').mass_kg > .68 and zone_cargo.kind('tri_frame').mass_kg > .68
    assert zone_cargo.kind('long_beam').required_carriers == 2
    assert tuple(spec.landing_half_extents_m) == (st.CARGO_RADIUS_M, st.CARGO_RADIUS_M)


# ------------------------------------------------------------ grounding glue

def cargo_m(x, y, *, visible=40, total=60, item='can_1'):
    return {'id': item, 'kind': 'cargo', 'xyz': [x, y, .0], 'yaw': 0., 'radius': .02, 'top_z_bound_m': .06,
            'visible_n': visible, 'probe_N': total}


def band_m(end, x, y):
    return {'id': 'band_' + end, 'kind': 'band', 'xyz': [x, y, .03], 'yaw': 0., 'visible_n': 9, 'probe_N': 9}


def test_visible_world_maps_the_can_onto_the_beam_fields_and_drops_bands():
    world = vis.SoloVisibleWorld('r1', 'teal', 'can_1')
    parked = cargo_m(3., 1., item='beam_1')
    seen = world.observe([band_m('teal', 1., 1.), band_m('blue', 1.5, 1.), cargo_m(.6, .1), parked], 0.)
    assert seen['beam']['ends']['teal'] == [.6, .1, 0.024] and seen['beam']['ends']['blue'] == seen['beam']['ends']['teal']
    assert seen['beam']['pose'][2] == pytest.approx(math.atan2(.1, .6))
    assert 'can_1' not in seen['objects'] and 'beam_1' in seen['objects']
    assert 'can_1' not in seen['visibility']['r1']['objects']
    assert seen['visibility']['r1']['visible_probes'] >= 5
    # a band alone (the parked beam's) never creates a target
    bare = vis.SoloVisibleWorld('r1', 'teal', 'can_1')
    assert bare.observe([band_m('teal', 1., 1.)], 0.)['beam'] is None


def test_target_bearing_is_latched_at_first_sight_and_visibility_follows_the_current_tick():
    world = vis.SoloVisibleWorld('r1', 'teal', 'can_1')
    first = world.observe([cargo_m(.6, .1)], 0.)
    yaw0 = first['beam']['pose'][2]
    world.issue({'t': 0., 'wheels': [.4, .4, .4, .4], 'duration_s': [.1]*4, 'pwm': {}})
    second = world.observe([cargo_m(.5, .3)], .1)                    # robot moved/turned; the can is seen elsewhere
    assert second['beam']['pose'][2] == yaw0
    gone = world.observe([], .2)                                      # not visible this tick, still in memory
    assert gone['beam'] is not None and gone['visibility']['r1']['visible_probes'] == 0
    expired = world.observe([], 6.)                                   # past the student memory horizon
    assert expired['beam'] is None


def test_unchanged_visible_only_teacher_accepts_the_adapted_world():
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    pwm = {str(s): 1500 for s in (1, 3, 4, 5, 6)}
    teacher = VisibleOnlyGraspTeacher('r1', 'teal', pwm, bounds=(-20, 20, -20, 20))
    world = vis.SoloVisibleWorld('r1', 'teal', 'can_1')
    perceived = world.observe([cargo_m(.45, 0.), cargo_m(3., 1., item='beam_1')], 0.)
    teacher.skill_started = 0.
    for k in range(5):
        clean, done = teacher.step(perceived, k*.1, permit_pick=False)
        assert set(clean) >= {'wheels', 'duration_s', 'pwm'} and done is False
        world.issue(clean)
        perceived = world.observe([cargo_m(.45, 0.), cargo_m(3., 1., item='beam_1')], (k + 1)*.1)
    assert teacher.phase in ('approach', 'align', 'ready', 'search')
    assert teacher.end == 'teal'                         # the teacher-private end token stays internal


def test_snapshot_cargo_gives_a_three_axis_shell_and_scene_injection_is_additive():
    from sim.zone_cargo import CargoInstance
    inst = CargoInstance('can_1', 'can', (.7, -1.5, 0.))
    shell = vis.SnapshotCargo(inst)
    part, = shell.spec().parts
    assert part.size == (.019, .019, .025) and part.collision and shell.geom('shell') == 'cargo_can_1__shell'
    assert shell.body == 'cargo_can_1' and tuple(shell.spec().landing_half_extents_m) == (.019, .019)
    beam = CargoInstance('beam_1', 'long_beam', (1., 1., 0.))
    scene = SimpleNamespace(cargo=[beam], config={'cargo_set': {'items': [{'item_id': 'beam_1'}], 'schema': 'x'}})
    added = vis.add_solo_cargo(scene, {'item_id': 'can_1', 'kind': 'can', 'pose': [.7, -1.5, 0.]})
    assert [c.item_id for c in scene.cargo] == ['beam_1', 'can_1'] and added.pose == (.7, -1.5, 0.)
    assert [i['item_id'] for i in scene.config['cargo_set']['items']] == ['beam_1', 'can_1']
    with pytest.raises(ValueError):
        vis.add_solo_cargo(scene, {'item_id': 'can_1', 'kind': 'can', 'pose': [0., 0., 0.]})
