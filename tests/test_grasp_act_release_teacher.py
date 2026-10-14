"""Offline checks: visible-only memory, wheel band, code GO/ACK step choice, seed splits."""
import json, math
import pytest
from sim.visible_belief import VisibleBelief, odometry, relative, wheel_to_body
from sim.grasp_act_release_teacher import check_wheels, PairReleaseCode, zone_edges, MARGIN_M
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
