"""Offline checks: visible-only memory, wheel band, code GO/ACK step choice, seed splits."""
import json, math
import pytest
from sim.visible_belief import VisibleBelief, odometry, relative, wheel_to_body
from sim.grasp_act_release_teacher import check_wheels, PairReleaseCode, zone_edges
from harness.grasp_act_seed_splits import registry, split_of, check_range, check_dataset_splits


def test_belief_visible_then_dead_reckoned_then_expired():
    b = VisibleBelief(memory_s=1.6)
    b.observe('edge:south', [1., 0., 0.], 0.)
    b.propagate(.2, 0., 0.)
    item = b.get('edge:south', 1.)
    assert item['source'] == 'dead_reckoned' and abs(item['pose'][0]-.8) < 1e-9
    assert b.get('edge:south', 1.7) is None
    b.observe('prior:south', [1., 0., 0.], 0., source='map_prior')
    assert b.get('prior:south', 99.)['source'] == 'map_prior'
    with pytest.raises(ValueError):
        b.observe('x', [0, 0, 0], 0., source='truth')


def test_relative_and_odometry_inverse():
    assert relative([1., 1., math.pi/2], (1., 2.)) == pytest.approx([1., 0., -math.pi/2])
    f, l, t = wheel_to_body([.35]*4)
    assert (f, l, t) == pytest.approx((.35, 0., 0.))
    dx, dy, da = odometry([.35]*4, .1)
    assert dx == pytest.approx(.0129) and dy == 0. and da == 0.


def test_wheel_band_and_duration():
    check_wheels([.35, -.35, .31, .40], [.15, .15, .05, .1])
    for bad in ([.2, 0, 0, 0], [.5, 0, 0, 0]):
        with pytest.raises(ValueError):
            check_wheels(bad, [.1, 0, 0, 0])
    with pytest.raises(ValueError):
        check_wheels([.35, 0, 0, 0], [.2, 0, 0, 0])


def msg(kind, m=None):
    return {'phase': 'look', 'kind': kind, 'margin_m': m, 't': 0.}


def test_code_lowers_only_with_visible_evidence_inside():
    code = PairReleaseCode(('r1', 'r2'))
    code.delivered = {'r1': msg('edge', .2), 'r2': msg('inside_lb', .1)}
    assert code.decide(0.)['action'] == 'lower'
    code.delivered = {'r1': msg('prior', .2), 'r2': msg('prior', .2)}
    assert code.decide(0.)['action'] == 'shift'


def test_code_shift_direction_equalizes_margins():
    code = PairReleaseCode(('r1', 'r2'))
    code.delivered = {'r1': msg('edge', -.10), 'r2': msg('edge', .30)}
    c = code.decide(0.)
    assert c['action'] == 'shift' and c['shift_m'] == pytest.approx(.10)   # clipped toward r2's end
    code.delivered = {'r1': msg('outside'), 'r2': msg('edge', .4)}
    assert code.decide(0.)['shift_m'] > 0
    code.delivered = {'r1': msg('edge', .4), 'r2': msg('outside')}
    assert code.decide(0.)['shift_m'] < 0


@pytest.mark.parametrize('other', (msg('none'), msg('edge', .2), msg('prior', .2)))
def test_no_evidence_never_confirms_release_and_records_unbounded_interval(other):
    code = PairReleaseCode(('r1', 'r2'))
    code.delivered = {'r1': msg('none'), 'r2': other}
    lo, _, evidence = code.interval(code.delivered)
    assert lo == -math.inf and evidence[0] == 'none'
    decision = code.decide(0., require_seen=True)
    assert decision['action'] == 'shift' and decision['lo'] is None
    json.dumps(decision, allow_nan=False)   # preserve unknown bounds without nonstandard Infinity


def test_zone_edges_inward_normals():
    e = zone_edges((4.6, .4, .3, .7))
    assert e['south'][0] == pytest.approx((4.6, -.3)) and e['south'][1] == math.pi/2 and e['north'][1] == -math.pi/2


def test_seed_registry_disjoint_and_gate_ranges():
    reg = registry()
    assert split_of(74010, reg) == 'release_gate' and split_of(73000, reg) == 'grasp_gate_v3'
    assert split_of(85000, reg) == 'train' and split_of(50000, reg) is None
    with pytest.raises(ValueError):
        check_range('train', 74000, 1)


def test_dataset_split_check_reads_metadata_and_requires_heldout(tmp_path):
    def ep(name, seed, map_id):
        d = tmp_path/name; d.mkdir()
        (d/'episode.json').write_text(json.dumps({'episode_id': f'x-{seed}', 'map_id': map_id}))
        return name
    data = {'train': [ep('a', 80001, 'zone_wide_door_geometry_v3')], 'development': [ep('b', 90001, 'zone_wide_door_geometry_v3')],
            'heldout_map': [ep('c', 92001, 'zone_wide_corridor_final_v3')]}
    assert check_dataset_splits(data, tmp_path)['heldout_map_check'].startswith('passed')
    with pytest.raises(ValueError, match='non-empty heldout_map'):
        check_dataset_splits({**data, 'heldout_map': []}, tmp_path)
    with pytest.raises(ValueError, match='belongs to'):
        check_dataset_splits({**data, 'train': [ep('g', 72001, 'zone_wide_door_geometry_v3')]}, tmp_path)
    with pytest.raises(ValueError, match='held-out map'):
        check_dataset_splits({**data, 'train': [ep('h', 80002, 'zone_wide_corridor_final_v3')]}, tmp_path)


def test_scan_margin_edge_inside_outside():
    from sim.grasp_act_release_teacher import ReleaseTeacher
    m = ReleaseTeacher.scan_margin
    zone_then_floor = [(s/100, 'zone') for s in range(-10, 12)] + [(s/100, 'floor') for s in range(13, 20)]
    kind, v = m(zone_then_floor)
    assert kind == 'edge' and v == pytest.approx(.12)
    assert m([(s/100, 'zone') for s in range(-5, 8)]) == ('inside_lb', pytest.approx(.07))
    kind, v = m([(s/100, 'zone') for s in range(-20, -9)] + [(s/100, 'floor') for s in range(-8, 5)])
    assert kind == 'outside' and v == pytest.approx(-.09)
    assert m([]) == (None, None)


def test_released_end_uses_own_command_memory():
    from sim.grasp_act_release_teacher import ReleaseTeacher
    pwm = {1: 1500, 3: 700, 4: 2400, 5: 1320, 6: 1500}
    t = ReleaseTeacher('r1', 'teal', pwm, handoff_pose_estimate=[0., 0., 0.], zone_rect=(1., 0., .3, .7))
    (ex, ey), o, src = t.end_and_outward(0.)
    assert src == 'commands_fk' and o == (-1., 0.)
    t.released_here(0.)
    (ex2, ey2), o2, src2 = t.end_and_outward(5.)
    assert src2 == 'own_command_release' and ex2 == pytest.approx(ex) and o2[0] == pytest.approx(-1.)


def test_approach_plan_brings_regrasp_target_to_mid_reach():
    from sim.grasp_act_release_teacher import ReleaseTeacher, REACH_MID_M, WHEEL
    from sim.visible_belief import AXIAL_M_PER_S_AT_035
    from harness.visual_arm_v3 import MOUNT_X_M
    pwm = {1: 1500, 3: 700, 4: 2400, 5: 1320, 6: 1500}
    t = ReleaseTeacher('r1', 'teal', pwm, handoff_pose_estimate=[0., 0., 0.], zone_rect=(1., 0., .3, .7))
    t.belief.observe('released_band', [MOUNT_X_M+REACH_MID_M, 0., 0.], 0., source='own_command')
    assert t.approach_plan(0.) == []
    t.belief.propagate(-.15, 0., 0.)          # stepped back 0.15 m (backoff_v3 observe)
    plan = t.approach_plan(1.)
    assert plan and all(w == [WHEEL]*4 for w, _ in plan)
    assert sum(d[0] for _, d in plan)*AXIAL_M_PER_S_AT_035 == pytest.approx(.15, abs=.006)
    t.belief.propagate(.25, 0., 0.)           # overshoot: target too close -> back up
    assert all(w == [-WHEEL]*4 for w, _ in t.approach_plan(2.))


@pytest.mark.parametrize('y', (-.02, 0., .02))
def test_pad_window_v2_approach_makes_regrasp_solvable(y):
    """5d6e8291 ep4: approach to REACH_MID_M (16.25 cm) left the re-grasp in the pad-IK gap."""
    from sim.grasp_act_release_teacher import ReleaseTeacher, REACH_MID_M, PAD_MID_M, PAD_WINDOW_M, WHEEL
    from sim.visible_belief import AXIAL_M_PER_S_AT_035
    from harness.visual_arm_v3 import MOUNT_X_M
    pwm = {1: 1500, 3: 700, 4: 2400, 5: 1320, 6: 1500}
    x = MOUNT_X_M+math.sqrt(REACH_MID_M**2-y**2)
    old = ReleaseTeacher('r1', 'teal', pwm, handoff_pose_estimate=[0., 0., 0.], zone_rect=(1., 0., .3, .7))
    old.belief.observe('released_band', [x, y, 0.], 0., source='own_command')
    assert old.approach_plan(0.) == []        # calibrated_mid_v1 accepts 16.25 cm ...
    if y:
        with pytest.raises(ValueError):       # ... where the physical-pad IK has no solution off-axis
            old.pick_schedule(0.)
    t = ReleaseTeacher('r1', 'teal', pwm, handoff_pose_estimate=[0., 0., 0.], zone_rect=(1., 0., .3, .7),
                       reach_mode='pad_window_v2')
    t.belief.observe('released_band', [x, y, 0.], 0., source='own_command')
    plan = t.approach_plan(0.)
    assert plan and all(w == [WHEEL]*4 for w, _ in plan)
    moved = sum(d[0] for _, d in plan)*AXIAL_M_PER_S_AT_035
    t.belief.propagate(moved, 0., 0.)
    (bx, by), _ = t.pick_target(1.)
    radius = math.hypot(bx-MOUNT_X_M, by)
    assert PAD_WINDOW_M[0] <= radius <= PAD_WINDOW_M[1] and radius == pytest.approx(PAD_MID_M, abs=.006)
    assert t.approach_plan(1.) == []
    seq, _ = t.pick_schedule(1.)
    assert len(seq) == 11                  # hover, 8 descent, close, lift


def test_reach_mode_rejects_unknown():
    from sim.grasp_act_release_teacher import ReleaseTeacher
    with pytest.raises(ValueError):
        ReleaseTeacher('r1', 'teal', {1: 1500, 3: 700, 4: 2400, 5: 1320, 6: 1500}, handoff_pose_estimate=[0., 0., 0.],
                       zone_rect=(1., 0., .3, .7), reach_mode='x')


def test_destination_slot_geoms_selects_only_own_zone_slots():
    """5d6e8291 ep4: the zone_slot_A2 square (above the zone marking) read as 'floor' -> false edge report."""
    from scripts.run_grasp_act_release import destination_slot_geoms, ZONE_SLOT_MODES
    names = ['floor', 'zone_zone_A', 'zone_slot_A1', 'zone_slot_A2', 'zone_slot_A3', 'zone_slot_B1',
             'zone_slot_A1_label', None, 'zone_wall_A']
    assert destination_slot_geoms(names, 'zone_A') == [2, 3, 4]
    assert destination_slot_geoms(names, 'zone_B') == [5]
    assert ZONE_SLOT_MODES[0] == 'floor'      # default keeps the old classification


def test_held_audit_counts_old_profile_and_refuses_hidden_v1():
    """User 2026-10-14: the held cargo's world pose must not reach decisions while it is held."""
    from scripts.run_grasp_act_release import HeldAudit, HELD_OBJECT_MODES
    assert HELD_OBJECT_MODES[0] == 'visible_v0'            # default keeps the old behaviour
    old = HeldAudit('visible_v0')
    old.read(True, 'scan_end'); old.read(True, 'scan_end'); old.read(False, 'band_pose')
    assert old.record()['held_world_reads'] == 2 and old.record()['held_world_reads_by_site'] == {'scan_end': 2}
    new = HeldAudit('hidden_v1')
    new.read(False, 'band_pose')                           # released cargo seen by the camera: allowed
    with pytest.raises(RuntimeError, match='HELD_WORLD_READ'):
        new.read(True, 'scan_end')
    assert new.record()['held_world_reads'] == 0
    with pytest.raises(ValueError):
        HeldAudit('x')


def test_position_error_and_measurement_audit():
    from scripts.run_grasp_act_release import position_error, HeldAudit
    e = position_error([4.62, 0.30, math.pi/2+math.radians(5)], (4.6, 0.4, .3, .7))
    assert e['center_offset_m'] == pytest.approx([.02, -.10]) and e['yaw_error_deg'] == pytest.approx(5)
    assert e['zone_long_axis'] == 'y' and 0 < e['min_end_margin_m'] < .3
    assert position_error([4.6, 0.4, -math.pi/2], (4.6, 0.4, .3, .7))['yaw_error_deg'] == pytest.approx(0, abs=1e-9)
    a = HeldAudit('hidden_v1')
    a.measurement('observe', 'scan_point', True); a.measurement('observe', 'own_band_pose', False)
    r = a.record()
    assert r['invisible_measurements'] == 1 and r['measurements_by_phase']['observe']['scan_point'] == {'n': 1, 'invisible': 0}


def test_command_handoff_is_independent_of_truth_and_plan():
    from scripts.run_grasp_act_release import CommandPose, handoff_estimate
    class Forbidden(dict):
        def __getitem__(self,key):raise AssertionError('plan truth was read')
    p=CommandPose();p.propagate([.35]*4,1.)
    p.propagate([-.35,.35,-.35,.35],1.)
    p.propagate([.35]*4,1.)
    expected=[.129+.129*math.cos(.35),.129*math.sin(.35),.35]
    for truth in (None,[999.,-999.,2.]):
        assert handoff_estimate(Forbidden(),'r1',p,pose_anchor='command_relative_v1',own_pose_source='commands',truth_pose=truth)==pytest.approx(expected)
    with pytest.raises(ValueError,match='own commands'):
        handoff_estimate({},'r1',p,pose_anchor='command_relative_v1',own_pose_source='truth_comparison')
    assert handoff_estimate({'handoff_pose_error':{'r1':[.1,-.1,.2]}},'r1',p,
        pose_anchor='legacy_truth_v0',own_pose_source='commands',truth_pose=[1.,2.,3.])==pytest.approx([1.1,1.9,3.2])


def test_unknown_map_pose_never_seeds_zone_priors_and_keeps_visual_evidence():
    from sim.grasp_act_release_teacher import ReleaseTeacher
    t=ReleaseTeacher('r1','teal',{1:1500,3:700,4:2400,5:1320,6:1500},
                     handoff_pose_estimate=None,zone_rect=(4.6,.4,.3,.7))
    assert not t.belief.items and t.report(0.) == {'phase':'look','kind':'none','margin_m':None}
    with pytest.raises(ValueError,match='map pose unknown'):t.reanchor_priors([0.,0.,0.])
    (x,y),(ox,oy),_=t.end_and_outward(0.)
    t.perceive({'scan':[[x+ox*s/100,y+oy*s/100,'zone'] for s in range(-5,8)],'band':None},0.)
    assert t.report(0.)['kind']=='inside_lb' and t.report(0.)['margin_m']==pytest.approx(.07)
    assert t.report(.2) == {'phase':'look','kind':'none','margin_m':None}   # expired scan, no map prior


def test_known_map_prior_has_a_numeric_margin_without_visible_scan():
    from sim.grasp_act_release_teacher import ReleaseTeacher
    t=ReleaseTeacher('r1','teal',{1:1500,3:700,4:2400,5:1320,6:1500},
                     handoff_pose_estimate=[4.6,.4,math.pi/2],zone_rect=(4.6,.4,.3,.7))
    report=t.report(0.)
    assert report['kind']=='prior' and math.isfinite(report['margin_m'])


def test_release_visibility_counts_phase_fractions_and_continuous_blind_intervals():
    from scripts.run_grasp_act_release import HeldAudit
    a=HeldAudit('hidden_v1')
    for ph,seen in [('lower',False),('lower',False),('open',False),('open',True),('lower',False)]:
        a.assigned_end(ph,'r1',seen)
    a.assigned_end('look','r2',True)
    a.measurement('lookaround','own_rgb_landmarks',True,count=0)
    a.measurement('observe','scan_end',False,count=2)
    r=a.record();v=r['assigned_end_visibility_by_phase']['r1']
    assert v['lower']=={'N':3,'visible':0,'visible_fraction':0.,'max_blind_s':.2}
    assert v['open']['visible_fraction']==.5 and v['open']['max_blind_s']==.1
    assert r['max_assigned_end_blind_s']['r1']==pytest.approx(.3)
    assert r['max_assigned_end_blind_s']['r2']==0.
    assert r['invisible_measurements']==2 and 'lookaround' not in r['measurements_by_phase']


@pytest.mark.parametrize('end',('teal','blue'))
def test_command_relative_release_keeps_same_landing_end_when_band_is_hidden(end):
    from sim.grasp_act_release_teacher import ReleaseTeacher
    t=ReleaseTeacher('r1',end,{1:1500,3:700,4:2400,5:1320,6:1500},
                     handoff_pose_estimate=None,zone_rect=(4.6,.4,.3,.7))
    before, outward, _=t.end_and_outward(0.)
    t.released_here(0.)
    after, outward_after, source=t.end_and_outward(1.)
    assert after==pytest.approx(before) and outward_after==pytest.approx(outward)
    assert source=='own_command_release'
    t.dead_reckon([-.35]*4,1.)
    after, outward_after, _=t.end_and_outward(2.)
    assert after==pytest.approx((before[0]+.129,before[1]))
    assert outward_after==pytest.approx((-1.,0.))
