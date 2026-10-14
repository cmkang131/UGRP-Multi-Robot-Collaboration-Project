import json
import math
import pytest
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_start_sync import GraspStartSync
from sim.cargo_teacher_profile import BEAM, CRATE, station_xy, end_points, planning_discs
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from scripts.zone_teacher import FOLDED


def lug(world_pose, side, robot=(0., 0., 0.), n=15):
    """Relative lug measurement as sim/grasp_act_visible_measurements would give it (crate pose in world)."""
    x, y, yaw = world_pose
    d = CRATE.band_center_m*(-1 if side == 'teal' else 1)
    wx, wy = x+d*math.cos(yaw), y+d*math.sin(yaw)
    c, s = math.cos(robot[2]), math.sin(robot[2])
    dx, dy = wx-robot[0], wy-robot[1]
    return {'id': 'band_'+side, 'kind': 'band', 'xyz': [c*dx+s*dy, -s*dx+c*dy, .023],
            'yaw': yaw-robot[2], 'visible_n': n, 'probe_N': n}


def test_profile_constants_match_catalogue_and_beam_default():
    from sim.zone_cargo import CATALOGUE
    spec = CATALOGUE['heavy_crate']
    grasps = {g.role: g.grip_xyz for g in spec.grasps}
    assert grasps['west'] == (-CRATE.grasp_m, 0., .024) and grasps['east'] == (CRATE.grasp_m, 0., .024)
    lugs = {p.name: p for p in spec.parts}
    assert lugs['lug_west'].center[:2] == (-CRATE.band_center_m, 0.) and lugs['lug_east'].center[0] == CRATE.band_center_m
    assert lugs['lug_west'].center[2] == pytest.approx(.023) and CRATE.end_z_offset_m == pytest.approx(.001)
    # the lug tip is the landing end: centre .09 + half length .03
    assert lugs['lug_east'].center[0]+lugs['lug_east'].size[0] == pytest.approx(CRATE.landing_end_m)
    assert CRATE.grasp_to_end_m == pytest.approx(.02) and CRATE.band_to_grasp_m == pytest.approx(.01)
    assert spec.mass_kg == .9 and spec.required_carriers == 2 and spec.landing_half_extents_m == (.12, .05)
    assert BEAM.band_center_m == BEAM.grasp_m == .27 and BEAM.landing_end_m == .30 and BEAM.end_z_offset_m == -.0086
    assert [d for d, _ in BEAM.discs] == [-.27, -.135, 0., .135, .27] and {r for _, r in BEAM.discs} == {.02}
    assert CRATE.role_of('teal') == 'west' and CRATE.end_name('east') == 'blue'


def test_visible_world_crate_ends_match_truth_and_beam_default_is_unchanged():
    crate = (.7, .1, .3)
    m = VisibleWorld('r1', 'teal', profile=CRATE)
    w = m.observe([lug(crate, 'teal')], 0.)
    truth = end_points(CRATE, *crate)
    assert w['beam']['ends']['teal'][:2] == pytest.approx(list(truth['teal']), abs=1e-9)
    assert w['beam']['ends']['blue'][:2] == pytest.approx(list(truth['blue']), abs=1e-9)
    assert w['beam']['ends']['teal'][2] == pytest.approx(.024)
    assert w['beam']['pose'][:2] == pytest.approx(list(crate[:2]), abs=1e-9)
    m = VisibleWorld('r1', 'blue', profile=CRATE)
    w = m.observe([lug(crate, 'blue')], 0.)
    assert w['beam']['ends']['blue'][:2] == pytest.approx(list(truth['blue']), abs=1e-9)
    # beam (profile None) keeps the old numbers
    beam = {'id': 'band_teal', 'kind': 'band', 'xyz': [.203, 0., .0326], 'yaw': 0., 'visible_n': 15, 'probe_N': 15}
    assert VisibleWorld('r1', 'teal').observe([beam], 0.)['beam']['ends']['teal'] == pytest.approx([.203, 0, .024])


def test_both_crate_stations_are_free_at_unfolded_radius_and_target_is_not_an_obstacle():
    from sim.grasp_act_visible_route import constraints, free
    crate = (2., 1., .4)
    for end in ('teal', 'blue'):
        sx, sy, heading = station_xy(CRATE, end, *crate)
        # the other robot's view of the world is irrelevant here: only the cargo discs matter
        robot = (sx-.5*math.cos(heading), sy-.5*math.sin(heading), heading)
        m = VisibleWorld('r1', end, profile=CRATE)
        w = m.observe([lug(crate, end, robot)], 0.)
        # the crate is also seen as cargo, as measurements() would report it
        w['objects']['crate_1'] = {'xy': list(crate[:2]), 'radius': .13, 'top_z_bound_m': .06}
        for folded in (True, False):
            radius, discs, rects = constraints(w, 'r1', folded, CRATE)
            assert len(discs) == len(CRATE.discs)          # crate_1 itself is not a second obstacle
            goal = (w['robots']['r1']['pose'][0]+.5, w['robots']['r1']['pose'][1])  # 0.5 m ahead in the odometry frame
            station_local = (goal[0], goal[1])
            assert free(station_local, discs, rects, radius), (end, folded)
        # without the profile the same object would be an obstacle disc (beam behaviour)
        _, discs, _ = constraints(w, 'r1', False)
        assert len(discs) == 5+1


def lifted_teacher():
    m = VisibleWorld('r1', 'teal', profile=CRATE)
    w = m.observe([{'id': 'band_teal', 'kind': 'band', 'xyz': [.213, 0., .023], 'yaw': 0., 'visible_n': 15, 'probe_N': 15}], 0.)
    t = CrateGraspTeacher('r1', 'teal', FOLDED, bounds=(-20, 20, -20, 20))
    t.started = True
    t.skill_started = 0.
    t.phase = 'ready'
    return t, w


def test_lift_waits_for_barrier_and_never_reads_contact_or_height():
    t, w = lifted_teacher()
    assert isinstance(t, VisibleOnlyGraspTeacher) and t.cargo_profile is CRATE
    t._queue_pick(w, 1.)
    assert t.phase == 'pick' and t.lift_pose is not None and not t.lift_done
    events_before_close = len(t.arm.events)
    t.arm.tick = lambda now: True                       # the issued close sequence has completed
    value, done = t.step(w, 5., permit_pick=True, permit_lift=False)
    assert t.phase == 'closed' and not done and not t.command_complete and t.lift_ready()
    assert not any(value['wheels'])
    # waiting: no lift is queued before the barrier
    t.arm.events.clear()
    value, done = t.step(w, 5.1, permit_pick=True, permit_lift=False)
    assert t.phase == 'closed' and not done and not t.arm.events
    # barrier opens: lift queued, done only after the issued lift sequence completes
    value, done = t.step(w, 5.2, permit_pick=True, permit_lift=True)
    assert t.phase == 'lift' and not done and t.arm.events
    value, done = t.step(w, 7.5, permit_pick=True, permit_lift=True)
    assert done and t.command_complete and t.lift_done and t.phase == 'complete'
    assert t.outcome is None and events_before_close >= 0
    assert [e['to'] for e in t.events if e['to'] in ('closed', 'lift', 'complete')] == ['closed', 'lift', 'complete']


def test_lift_barrier_times_out_without_partner():
    t, w = lifted_teacher()
    t._queue_pick(w, 1.)
    t.arm.tick = lambda now: True
    t.step(w, 5., permit_pick=True)
    t.step(w, 5.+21., permit_pick=True, permit_lift=False)
    assert t.outcome == 'lift_barrier_timeout'


def test_lift_sync_is_simultaneous_and_needs_both_closed():
    sync = GraspStartSync(('r1', 'r2'), {'r1': 0., 'r2': 0.})
    seen = []
    for k in range(6):
        permit = sync.tick({'r1': True, 'r2': k >= 2}, k*.1)
        seen.append(permit)
    firsts = [i for i, p in enumerate(seen) if any(p.values())]
    assert firsts and all(not p['r1'] and not p['r2'] for p in seen[:firsts[0]])
    assert seen[firsts[0]] == {'r1': True, 'r2': True}          # both released on the same tick
    assert firsts[0] >= 3                                        # not before r2 reported READY (+GO, ACK)


def test_start_skew_only_delays_start_not_lift():
    start = GraspStartSync(('r1', 'r2'), {'r1': 0., 'r2': 1.2})
    started = {}
    for k in range(40):
        p = start.tick({'r1': True, 'r2': True}, k*.1)
        for r, ok in p.items():
            if ok:
                started.setdefault(r, k*.1)
    assert started['r2']-started['r1'] == pytest.approx(1.2, abs=.11)


def test_release_teacher_crate_geometry():
    from sim.crate_release_teacher import CrateReleaseTeacher
    from sim.grasp_act_release_teacher import ReleaseTeacher
    pwm = {1: 1500, 3: 700, 4: 2300, 5: 1300, 6: 1500}
    kw = dict(handoff_pose_estimate=[0., 0., 0.], zone_rect=(1., 0., .3, .7))
    crate = CrateReleaseTeacher('r1', 'teal', pwm, **kw)
    beam = ReleaseTeacher('r1', 'teal', pwm, **kw)
    (cx, cy), (ox, oy), src = crate.end_and_outward(0.)
    (bx, by), _, _ = beam.end_and_outward(0.)
    assert src == 'commands_fk' and (ox, oy) == (-1., 0.) and cy == by
    assert bx-cx == pytest.approx(CRATE.grasp_to_end_m-.03)       # crate landing end is 0.02 m, beam 0.03 m, from the grip point
    # after release, from the visible lug of the blue end: outward is +axis, landing end 0.03 m beyond the lug centre
    blue = CrateReleaseTeacher('r2', 'blue', pwm, **kw)
    blue.holding = False
    blue.belief.observe('band', [.30, .02, math.pi], 0., source='visible')   # lug centre, crate axis points at the robot
    (ex, ey), (ux, uy), src = blue.end_and_outward(.0)
    assert src == 'visible' and (ux, uy) == pytest.approx((-1., 0.), abs=1e-9)
    assert (ex, ey) == pytest.approx((.27, .02), abs=1e-9)
    (px, py), psrc = blue.pick_target(0.)
    assert (px, py) == pytest.approx((.29, .02), abs=1e-9) and psrc == 'visible'     # grasp point 0.01 m outward of the lug centre
    # own-command release memory: outward is -facing for both ends and rotates with own odometry
    blue.belief.items.clear()
    blue.released_here(0.)
    blue.belief.propagate(0., 0., .0)
    (rx, ry), (vx, vy), rsrc = blue.end_and_outward(0.)
    assert rsrc == 'own_command_release' and (vx, vy) == (-1., 0.)
    assert rx < blue.belief.items['released_band']['pose'][0]


def test_plan_generator_roles_assignment_and_registered_seeds():
    from scripts.make_crate_teacher_plan import prepare, FOOTPRINT
    from harness.grasp_act_seed_splits import split_of
    plan = prepare(count=12, seed=77000, split='crate_gate')
    assert plan['student_evaluation'] is False
    for e in plan['episodes']:
        assert split_of(e['seed']) == 'crate_gate'
        assert e['scenario_id'] in ('s2_unmapped_blockage_v4', 's8_mixed_tiers_v4')
        assert e['object_kind'] == 'heavy_crate' and e['target_item'] == 'crate_1' and e['lug_color_scene'] == 'crate_lug_colors_v1'
        assert sorted(e['roles'].values()) == ['blue', 'teal']                   # two different lugs
        assert e['role_tickets'] == {r: CRATE.role_of(v) for r, v in e['roles'].items()}
        for rid in ('r1', 'r2'):
            assert math.dist(e['spawns'][rid][:2], e['cargo_pose'][:2]) >= .29
        # nearest-lug assignment: no other assignment is shorter in total
        st = {end: station_xy(CRATE, end, *e['cargo_pose'])[:2] for end in ('teal', 'blue')}
        d = lambda rid, end: math.dist(e['spawns'][rid][:2], st[end])
        chosen = d('r1', e['roles']['r1'])+d('r2', e['roles']['r2'])
        other = d('r1', e['roles']['r2'])+d('r2', e['roles']['r1'])
        assert chosen <= other+1e-9
        assert math.dist(e['cargo_pose'][:2], (4.6, -2.1)) <= .8
    alt = prepare(count=4, seed=77000, split='crate_gate', assignment='alternating')
    assert [e['roles']['r1'] for e in alt['episodes']] == ['teal', 'blue', 'teal', 'blue']
    with pytest.raises(ValueError):
        prepare(count=1, seed=80000, split='crate_gate')                          # not in the registered range
    assert FOOTPRINT[0] == (-.12, -.05)


def test_registered_seed_ranges_do_not_overlap_and_are_never_train():
    from harness.grasp_act_seed_splits import registry
    data = registry()
    assert {'crate_gate', 'crate_diagnostic'} <= set(data['gate_seeds_never_train'])


def test_lug_paint_is_appearance_only():
    from sim.crate_scene import paint_lugs, LUG_COLORS_V1
    xml = ("<mujoco><worldbody><body name='cargo_crate_1'><geom name='cargo_crate_1__lug_west' rgba='.06 .06 .06 1' size='1 1 1'/>"
           "<geom name='cargo_crate_1__lug_east' rgba='.06 .06 .06 1' size='1 1 1'/></body></worldbody></mujoco>")
    assert paint_lugs(xml, 'crate_1', 'off') == xml
    out = paint_lugs(xml, 'crate_1', LUG_COLORS_V1)
    assert "rgba=\"0.02 0.95 0.6 1.0\"" in out and "rgba=\"0.02 0.02 0.95 1.0\"" in out and 'size="1 1 1"' in out
    with pytest.raises(ValueError):
        paint_lugs(xml.replace('lug_east', 'lug_x'), 'crate_1', LUG_COLORS_V1)
    with pytest.raises(ValueError):
        paint_lugs(xml, 'crate_1', 'unknown')


def test_lookaround_helpers():
    from sim import crate_lookaround as cl
    static = {'obstacles': [{'id': 'wall_a', 'kind': 'wall', 'center_m': [1., 0.], 'half_extents_m': [.5, .02]}],
              'passages': [{'id': 'door', 'center_m': [2., 0.], 'half_extents_m': [.025, .25], 'axis': 'x'}],
              'regions': {'zone_B': {'center_m': [4., -2.], 'half_extents_m': [.3, .7]}, 'pickup': {'center_m': [0., 0.], 'half_extents_m': [1., 1.]}}}
    lms = cl.landmarks_from_map(static)
    assert len(lms) == 4+2+4 and {l['type'] for l in lms} == {'wall_corner', 'door_post', 'zone_corner'}
    vis = cl.visible_predictor()
    assert vis((0., 0., 0.), 0., 0., {'xy': (2., 0.)}) and not vis((0., 0., 0.), 180., 0., {'xy': (2., 0.)})
    assert vis((0., 0., 0.), 0., 90., {'xy': (0., 2.)}) and not vis((0., 0., 0.), 0., 0., {'xy': (9., 0.)})
    plan = cl.rotation_plan(math.pi/2)
    assert sum(d[0] for _, d in plan)*cl.NOMINAL_YAW_RATE == pytest.approx(math.pi/2, abs=1e-6)
    assert all(w == [-cl.TURN_LEVEL, cl.TURN_LEVEL, -cl.TURN_LEVEL, cl.TURN_LEVEL] for w, _ in plan)
    assert cl.rotation_plan(-.5)[0][0][0] == cl.TURN_LEVEL                         # negative = right turn
    assert cl.pan_pulse(0.) == 1500 and cl.pan_pulse(90.) == 2500 and cl.pan_pulse(-90.) == 500


def test_lookaround_interface_with_active_lookaround():
    pytest.importorskip('sim.active_lookaround')
    import numpy as np
    from sim import crate_lookaround as cl
    from sim.active_lookaround import OwnPose, plan_views
    lms = [{'id': 'a', 'type': 'c', 'xy': (2., 1.)}, {'id': 'b', 'type': 'c', 'xy': (2., -1.)}, {'id': 'c', 'type': 'c', 'xy': (1., 2.)}]
    est = OwnPose((0., 0., 0.))
    p = plan_views(tuple(est.x), est.P, lms, cl.visible_predictor())
    script = cl.execution_script(p)
    assert script and all(set(v) == {'body_yaw_deg', 'pan_deg', 'landmarks'} for v in script)
    assert np.isfinite(p['expected_gain_nats'])


def test_crate_scene_resolves_lug_geoms_and_probes():
    import os
    from scripts.make_crate_teacher_plan import prepare
    from sim.crate_scene import make_crate_scene
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from scripts.audit_grasp_act_visibility import BandVisibility
    os.environ['UGRP_SIM_OBSERVER_WIDTH'] = '320'
    os.environ['UGRP_SIM_OBSERVER_HEIGHT'] = '240'
    plan = prepare(count=1, seed=77900, split='crate_diagnostic')['episodes'][0]
    scene = make_crate_scene(plan)
    world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=320, height=240, render=False,
                        warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None, roller_collision='mesh',
                        idle_robot_contacts='off')
    try:
        m = world.model
        west, east = m.geom('cargo_crate_1__lug_west'), m.geom('cargo_crate_1__lug_east')
        assert list(m.geom_rgba[west.id][:3]) == pytest.approx([.02, .95, .6]) and list(m.geom_rgba[east.id][:3]) == pytest.approx([.02, .02, .95])
        assert list(m.geom_size[west.id]) == pytest.approx([.03, .02, .023])
        band = BandVisibility(m, CRATE)
        assert band.bands == {'teal': west.id, 'blue': east.id} and band.probes['teal'].shape == (15, 3)
        assert band.probes['teal'][:, 2] == pytest.approx(.023+1e-6)                  # lug top face
    finally:
        world.close()


def test_runner_refuses_inconsistent_plans(tmp_path):
    from scripts.run_crate_teacher import run
    base = {'object_kind': 'heavy_crate', 'target_item': 'crate_1', 'roles': {'r1': 'teal', 'r2': 'teal'}}
    with pytest.raises(ValueError):
        run(base, tmp_path/'a')
    with pytest.raises(ValueError):
        run({**base, 'object_kind': 'long_beam'}, tmp_path/'b')
    with pytest.raises(ValueError):
        run({**base, 'roles': {'r1': 'teal', 'r2': 'blue'}}, tmp_path/'c', lookaround='nope')


def test_cargo_scene_version_scales_only_crate_masses_default_unchanged():
    import xml.etree.ElementTree as ET
    from sim.cargo_scene_version import apply_version, check, DEFAULT
    xml = ('<mujoco><worldbody><body name="cargo_crate_1"><geom name="a" mass=".7"/><geom name="b" mass=".1"/>'
           '<geom name="c" mass=".1"/><geom name="nomass"/></body><body name="cargo_beam_1"><geom mass=".3"/></body>'
           '<body name="other"><geom mass="5"/></body></worldbody></mujoco>')
    cargo = [('crate_1', 'heavy_crate'), ('beam_1', 'long_beam')]
    same, record = apply_version(xml, DEFAULT, cargo)
    assert same == xml and record['items'] == {}
    out, record = apply_version(xml, 'crate_mass_030_v1', cargo)
    assert record['items']['crate_1']['catalogue_mass_kg'] == pytest.approx(.9)
    assert record['items']['crate_1']['scale'] == pytest.approx(1/3) and 'beam_1' not in record['items']
    root = ET.fromstring(out)
    masses = [float(g.get('mass')) for g in root.find(".//body[@name='cargo_crate_1']").iter('geom') if g.get('mass')]
    assert sum(masses) == pytest.approx(.3)
    assert float(root.find(".//body[@name='cargo_beam_1']/geom").get('mass')) == .3
    assert float(root.find(".//body[@name='other']/geom").get('mass')) == 5.
    with pytest.raises(ValueError):
        apply_version('<mujoco><worldbody/></mujoco>', 'crate_mass_030_v1', cargo)
    with pytest.raises(ValueError):
        check('mass_nope')


def test_v5_scenario_scene_takes_the_cargo_scene_version(monkeypatch):
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.zone_final_v3_scene import FinalV3Scene
    xml = '<mujoco><worldbody><body name="cargo_crate_1"><geom mass=".9"/></body></worldbody></mujoco>'
    monkeypatch.setattr(FinalV3Scene, 'transform', lambda self, x: xml)
    base = ScenarioFinalV3Scene.from_scenario('s2_unmapped_blockage_v5', 611)
    assert base.cargo_scene_version == 'catalogue_v1' and base.transform('') == xml
    assert 'cargo_scene_version' not in base.manifest                      # default adds nothing
    light = ScenarioFinalV3Scene.from_scenario('s2_unmapped_blockage_v5', 611, cargo_scene_version='crate_mass_030_v1')
    out = light.transform('')
    assert 'mass="0.3"' in out or "mass='0.3'" in out or 'mass="0.30' in out
    assert light.manifest['cargo_scene_version']['items']['crate_1']['mass_kg'] == .3
    with pytest.raises(ValueError):
        ScenarioFinalV3Scene.from_scenario('s2_unmapped_blockage_v5', 611, cargo_scene_version='x')


def test_crate_plan_scenario_set_v5_keeps_v4_default():
    from scripts.make_crate_teacher_plan import prepare
    v4 = prepare(count=2, seed=77100, split='crate_gate_v2')
    v5 = prepare(count=2, seed=77100, split='crate_gate_v2', scenario_set='v5')
    assert [e['scenario_id'] for e in v4['episodes']] == ['s2_unmapped_blockage_v4', 's8_mixed_tiers_v4']
    assert [e['scenario_id'] for e in v5['episodes']] == ['s2_unmapped_blockage_v5', 's8_mixed_tiers_v5']
    assert all(e['object_kind'] == 'heavy_crate' for e in v5['episodes'])


def test_rgb_lift_verdicts_use_own_pixels_only():
    import numpy as np
    from sim.crate_rgb_lift import confirm
    def frame(lug_cols, floor):
        f = np.zeros((60, 80, 3), np.uint8)
        f[:, :] = floor
        f[:30, :lug_cols] = (255, 150, 180)          # crate body (pink), held
        f[30:, :lug_cols] = (0, 10, 255)             # own lug (blue), held
        return f
    before = frame(30, (120, 120, 120))
    lifted = frame(30, (160, 150, 140))              # held part rigid, floor changed (camera rose)
    assert confirm(before, lifted, 'blue')['verdict'] == 'confirmed'
    sagged = frame(30, (121, 120, 120))              # floor unchanged: the arm did not rise
    assert confirm(before, sagged, 'blue')['verdict'] == 'not_confirmed'
    lost = frame(2, (160, 150, 140))                 # held pixels vanished
    assert confirm(before, lost, 'blue')['verdict'] == 'not_confirmed'
    only_held = frame(80, (0, 0, 0))                 # no background in view
    assert confirm(only_held, only_held, 'blue')['verdict'] == 'undetermined'
