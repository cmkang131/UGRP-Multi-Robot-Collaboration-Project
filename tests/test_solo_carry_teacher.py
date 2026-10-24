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
REACH = .2          # synthetic robot-centre to box-centre distance along the robot heading
PARKED_BEAM = {'xy': [1.6, 0.4], 'radius': .30}
BASE_COMMIT = '75929e7719ad98a089e3dda5251f4249d8bae511'     # the pinned pairact tree this branch is cut from


def wheels(effort):
    return [0.]*4, [0.]*4


def truth(box, robot, *, held, min_z=.065, tilt=1., t=0., objects=None):
    f = [4.3, 4.3] if held else [0., 0.]
    return {'t': t, 'beam': {'pose': list(box), 'min_z': min_z, 'tilt_deg': tilt},
            'robots': {'r1': {'pose': list(robot)}, 'r2': {'pose': [-.8, 1.2, 0.]}, 'r3': {'pose': [-.8, 1.6, 0.]}},
            'contacts': {'r1': f}, 'objects': objects if objects is not None else {}}


def handover(robot=(.5, -1.5, 0.)):
    box = ct.compose(robot, (REACH, 0., 0.))
    return truth(box, robot, held=True), box


def make(robot=(.5, -1.5, 0.), slot=SLOT, arm=ARM, obstacles=(), **kw):
    row, _ = handover(robot)
    return st.SoloCarryTeacher('r1', row, 0., MAP, arm, PWM, slot, wheel_fn=wheels, obstacles=obstacles, **kw)


def integrate(pose, drive, dt=.1):
    fwd, left, turn = drive
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (pose[0] + (c*fwd - s*left)*dt, pose[1] + (s*fwd + c*left)*dt, ct.wrap(pose[2] + turn*dt))


def rollout(robot0=(.5, -1.5, 0.), *, slot=SLOT, drop_at=None, cap=200.):
    """Ideal kinematics: the robot follows its body command exactly; the box is rigid in the grip while held."""
    teacher = make(robot0, slot=slot)
    row0, box0 = handover(robot0)
    robot, box, off = robot0, box0, ct.relative(robot0, box0)
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
        row = truth(box, robot, held=held, min_z=min_z, t=t)
        rows.append(row)
        if teacher.done and t - teacher.events[-1]['t'] > 1.5:
            break
        out = teacher.step(row, t)
        drive = teacher.log[-1]['drive']['r1'] if teacher.log and teacher.log[-1]['t'] == t else (0., 0., 0.)
        robot = integrate(robot, drive)
        if teacher.phase in ct.PHASES[:ct.PHASES.index('open')] and min_z > 0:
            box = ct.compose(robot, off)
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
    assert sc.slot_contains(SLOT, rows[-1]['beam']['pose'], st.CARGO_HALF_EXTENTS_M)
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


def test_obstacles_for_keeps_the_parked_beam_and_other_boxes_but_not_the_carried_box():
    objects = {'beam_1': {'xy': [1.6, .4], 'radius': .3}, 'cyan_1': {'xy': [.7, -1.5], 'radius': .026},
               'red_1': {'xy': [1.45, -.85], 'radius': .026}}
    row, _ = handover()
    row['objects'] = objects
    discs = {d['id']: d for d in st.obstacles_for(row, 'r1')}
    assert {'beam_1', 'red_1'} <= set(discs) and 'cyan_1' not in discs
    assert {'r2', 'r3'} <= set(discs) and 'r1' not in discs


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
    return {'roles': {'r1': 'teal'}, 'solo_cargo': {'item_id': 'cyan_1', 'kind': 'cyan', 'pose': [.7, -1.5, 0.]},
            'solo_slot': copy.deepcopy(SLOT), 'episode_id': 'e0', 'seed': 1, 'cargo_scene': 'cargo_v6'}


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
    lambda p: p['solo_cargo'].update(kind='can'), lambda p: p['solo_cargo'].update(kind='red'),
    lambda p: p['solo_cargo'].update(item_id='cyan_2'),
    lambda p: p['solo_cargo'].update(pose=[.7, float('nan'), 0.]), lambda p: p['solo_cargo'].update(extra=1),
    lambda p: p['solo_slot'].update(zone='zone_A'), lambda p: p['solo_slot'].update(half_extents_m=[0., .1]),
    lambda p: p['solo_slot'].update(pose=[4.6, -2.1]),
    lambda p: p.pop('cargo_scene'), lambda p: p.update(cargo_scene='off'),
])
def test_bad_plans_are_rejected(mutate):
    plan = good_plan()
    mutate(plan)
    with pytest.raises(ValueError):
        sc.validate_plan(plan)


def test_cargo_is_the_production_box_with_its_real_geometry():
    """Every box constant traces to the tree (no new number): shape, mass, grasp height, colour."""
    from sim import zone_arena, zone_cargo
    assert sc.OBJECT_KIND == 'cyan' and sc.OBJECT_KIND in zone_arena.COLORS          # sim/zone_arena.py:43-45
    assert sc.CARGO_HALF_EXTENTS_M == zone_arena.BOX_HALF == (.017, .020, .016)      # sim/zone_arena.py:46
    box = zone_cargo.EXISTING_SOLO['box']
    assert box['dims_m'] == [2*h for h in sc.CARGO_HALF_EXTENTS_M] and box['required_carriers'] == 1
    assert sc.CARGO_MASS_KG == box['mass_kg'] == .030
    text = (ROOT/'sim/research_dispatch_arena.py').read_text()                      # :135-137 production box spec
    assert "(.034,.040,.032),.03," in text
    assert sc.GRASP_Z_M == zone_cargo.GRASP_Z_M == .024                              # sim/zone_cargo.py:34
    assert zone_cargo.HANDLE_WIDTH_M == 2*sc.CARGO_HALF_EXTENTS_M[1]                # 40 mm across the jaws
    lo, _ = zone_cargo.MEASURED_SINGLE_ROBOT_CAPACITY_KG                             # 0.66 kg ok, 0.68 kg tips
    assert sc.CARGO_MASS_KG < lo*.1
    assert tuple(st.CARGO_HALF_EXTENTS_M) == sc.CARGO_HALF_EXTENTS_M


def test_cargo_v6_user_decision_holds_and_the_role_is_the_v5_box_role():
    from harness import grasp_act_contract as c
    from sim.grasp_act_scene import validate_cargo_scene        # refuses a cargo_v6 plan that still has tile/can
    assert validate_cargo_scene is not None
    assert sc.OBJECT_KIND not in ('can', 'tile') and c.KIND_ROLES[sc.OBJECT_KIND] == ('west',) == (sc.ROLE,)
    for path in sorted((ROOT/'configs/zone_study_scenarios_v6').glob('*.json')):
        kinds = [p['kind'] for p in json.loads(path.read_text())['eval']['setup']['placements']]
        assert not {'can', 'tile'} & set(kinds), path.name


def test_box_colour_is_separable_from_the_scene_paint_and_the_parked_beam_bands():
    """Nominal (unlit) RGBA -> OpenCV hue only; the rendered hue is NOT checked here (docs s6)."""
    import colorsys
    from harness.zone_own_perception import APPEARANCE, PAINT_HUE
    from sim import zone_arena
    from sim.grasp_act_scene import COLORS as END_COLORS

    def hue(rgb):
        return colorsys.rgb_to_hsv(*rgb[:3])[0]*180

    def inside(h, bands):
        return any(lo <= h <= hi for lo, hi in bands)
    cyan = APPEARANCE[sc.OBJECT_KIND]['hue']
    assert inside(hue([float(v) for v in zone_arena.COLORS['cyan'].split()]), cyan)
    for other in ('red', 'green', 'yellow'):
        assert not inside(hue([float(v) for v in zone_arena.COLORS[other].split()]), cyan)
    for end in ('teal', 'blue'):                                   # grasp_act_teal_blue_v1 band paint
        assert not inside(hue(END_COLORS[end]), cyan)
    assert not any(lo <= PAINT_HUE['B'][1] and PAINT_HUE['B'][0] <= hi for lo, hi in cyan)   # destination paint


# ------------------------------------------------------------ grounding glue

def cargo_m(x, y, *, yaw=0., visible=40, total=60, item='cyan_1'):
    return {'id': item, 'kind': 'cargo', 'xyz': [x, y, .016], 'yaw': yaw, 'radius': .026, 'top_z_bound_m': .032,
            'visible_n': visible, 'probe_N': total}


def band_m(end, x, y):
    return {'id': 'band_' + end, 'kind': 'band', 'xyz': [x, y, .03], 'yaw': 0., 'visible_n': 9, 'probe_N': 9}


def test_visible_world_maps_the_box_onto_the_beam_fields_and_drops_bands():
    world = vis.SoloVisibleWorld('r1', 'teal', 'cyan_1')
    parked = cargo_m(3., 1., item='beam_1')
    seen = world.observe([band_m('teal', 1., 1.), band_m('blue', 1.5, 1.), cargo_m(.6, .1, yaw=.2), parked], 0.)
    assert seen['beam']['ends']['teal'] == [.6, .1, 0.024] and seen['beam']['ends']['blue'] == seen['beam']['ends']['teal']
    assert seen['beam']['pose'][2] == pytest.approx(.2)              # the box's own visible yaw, not a bearing
    assert 'cyan_1' not in seen['objects'] and 'beam_1' in seen['objects']
    assert 'cyan_1' not in seen['visibility']['r1']['objects']
    assert seen['visibility']['r1']['visible_probes'] >= 5
    # a band alone (the parked beam's) never creates a target
    bare = vis.SoloVisibleWorld('r1', 'teal', 'cyan_1')
    assert bare.observe([band_m('teal', 1., 1.)], 0.)['beam'] is None


@pytest.mark.parametrize('xy,yaw,heading', [
    ((.6, 0.), 0., 0.),                 # box ahead, its +x away from the robot: approach its -x side
    ((.6, 0.), math.pi, 0.),            # same box turned 180 deg (identical shape): same approach
    ((-.6, 0.), 0., math.pi),           # box behind: fold to the side that faces the robot
    ((0., .6), math.pi/2 + .1, math.pi/2 + .1),
])
def test_box_heading_is_folded_to_the_robot_side_at_first_sight(xy, yaw, heading):
    world = vis.SoloVisibleWorld('r1', 'teal', 'cyan_1')
    seen = world.observe([cargo_m(*xy, yaw=yaw)], 0.)
    assert math.cos(seen['beam']['pose'][2] - heading) == pytest.approx(1.)
    bearing = math.atan2(xy[1], xy[0])
    assert math.cos(seen['beam']['pose'][2] - bearing) > 0           # the robot stands on its own side


def test_fold_is_latched_and_visibility_follows_the_current_tick():
    world = vis.SoloVisibleWorld('r1', 'teal', 'cyan_1')
    first = world.observe([cargo_m(.6, .1)], 0.)
    assert first['beam']['pose'][2] == pytest.approx(0.) and world.fold == 0.
    world.issue({'t': 0., 'wheels': [.4, .4, .4, .4], 'duration_s': [.1]*4, 'pwm': {}})
    second = world.observe([cargo_m(.5, .3, yaw=.05)], .1)          # robot moved; the box is seen elsewhere
    assert world.fold == 0. and math.cos(second['beam']['pose'][2] - first['beam']['pose'][2]) > .9
    gone = world.observe([], .2)                                      # not visible this tick, still in memory
    assert gone['beam'] is not None and gone['visibility']['r1']['visible_probes'] == 0
    expired = world.observe([], 6.)                                   # past the student memory horizon
    assert expired['beam'] is None


def test_unchanged_visible_only_teacher_accepts_the_adapted_world():
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    pwm = {str(s): 1500 for s in (1, 3, 4, 5, 6)}
    teacher = VisibleOnlyGraspTeacher('r1', 'teal', pwm, bounds=(-20, 20, -20, 20))
    world = vis.SoloVisibleWorld('r1', 'teal', 'cyan_1')
    perceived = world.observe([cargo_m(.45, 0.), cargo_m(3., 1., item='beam_1')], 0.)
    teacher.skill_started = 0.
    for k in range(5):
        clean, done = teacher.step(perceived, k*.1, permit_pick=False)
        assert set(clean) >= {'wheels', 'duration_s', 'pwm'} and done is False
        world.issue(clean)
        perceived = world.observe([cargo_m(.45, 0.), cargo_m(3., 1., item='beam_1')], (k + 1)*.1)
    assert teacher.phase in ('approach', 'align', 'ready', 'search')
    assert teacher.end == 'teal'                         # the teacher-private end token stays internal


def test_teacher_station_is_the_calibrated_box_grasp_reach():
    """The unchanged grasp teacher stands STATION_M behind the target; for a box that is the
    calibrated box grasp: arm-axis mount + grasp radius (sim/zone_cargo.py:32)."""
    from harness.visual_arm_v3 import MOUNT_X_M
    from sim.grasp_act_teacher import STATION_M, XY_TOL_M
    from sim.zone_cargo import GRASP_RADIUS_M
    assert abs(STATION_M - (MOUNT_X_M + GRASP_RADIUS_M)) < .001
    assert abs(STATION_M - (MOUNT_X_M + .152)) < XY_TOL_M         # solo box teacher station (act-solo-teacher)


def scenario_scene(name):
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    return ScenarioFinalV3Scene.from_scenario(name, 1)


def test_select_uses_the_scenario_box_and_adds_nothing_to_the_scene():
    scene = scenario_scene('s6_novel_relation_v6')                   # beam_1 + red_1 + one cyan_1
    before = json.dumps(scene.config, sort_keys=True, default=str)
    box = vis.select_solo_cargo(scene, {'item_id': 'cyan_1', 'kind': 'cyan', 'pose': [.7, -1.5, .3]})
    assert json.dumps(scene.config, sort_keys=True, default=str) == before
    assert (box.body, box.joint, box.geom(box.spec().parts[0].name)) == ('cargo_cyan_1', 'cargo_cyan_1_free',
                                                                          'cargo_cyan_1_geom')
    part, = box.spec().parts
    assert part.collision and part.size == sc.CARGO_HALF_EXTENTS_M and box.pose == (.7, -1.5, .3)
    assert tuple(box.spec().landing_half_extents_m) == sc.CARGO_HALF_EXTENTS_M[:2]


def test_select_refuses_a_scene_with_two_cyan_boxes_or_a_missing_box():
    with pytest.raises(ValueError, match='unique'):
        vis.select_solo_cargo(scenario_scene('s1_normal_mixed_v6'),    # cyan_1 and cyan_2
                              {'item_id': 'cyan_1', 'kind': 'cyan', 'pose': [0., 0., 0.]})
    scene = SimpleNamespace(cargo=[], config={'setup_only': {'objects': {}}})
    with pytest.raises(ValueError, match='not a scenario box'):
        vis.select_solo_cargo(scene, {'item_id': 'cyan_1', 'kind': 'cyan', 'pose': [0., 0., 0.]})
    odd = {'cyan_1': {'kind': 'cyan', 'body_name': 'cargo_cyan_1', 'joint_name': 'cargo_cyan_1_free',
                      'position_m': [0, 0, .016], 'half_extents_m': [.02, .02, .016]}}
    with pytest.raises(ValueError, match='production box'):
        vis.select_solo_cargo(SimpleNamespace(cargo=[], config={'setup_only': {'objects': odd}}),
                              {'item_id': 'cyan_1', 'kind': 'cyan', 'pose': [0., 0., 0.]})


def test_place_solo_cargo_sets_the_plan_pose_on_the_free_joint():
    mujoco = pytest.importorskip('mujoco')
    model = mujoco.MjModel.from_xml_string(
        '<mujoco><worldbody><geom type="plane" size="5 5 .1"/><body name="cargo_cyan_1">'
        '<joint name="cargo_cyan_1_free" type="free"/><geom name="cargo_cyan_1_geom" type="box" size=".017 .020 .016"'
        ' mass=".03"/></body></worldbody></mujoco>')
    world = SimpleNamespace(model=model, data=mujoco.MjData(model))
    box = vis.SoloBox('cyan_1', 'cyan', 'cargo_cyan_1', 'cargo_cyan_1_free', (.7, -1.5, .3), sc.CARGO_HALF_EXTENTS_M)
    vis.place_solo_cargo(world, box)
    body = world.data.body('cargo_cyan_1')
    assert list(body.xpos) == pytest.approx([.7, -1.5, .016])
    r = body.xmat.reshape(3, 3)
    assert math.atan2(r[1, 0], r[0, 0]) == pytest.approx(.3)
