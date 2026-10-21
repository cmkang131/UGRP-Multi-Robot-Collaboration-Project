"""BRANCH_NAV_V5 render sweep: pure helpers and frozen band rules (no simulator)."""
import colorsys
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/2026-10-21-nav-v5-recal'
spec = importlib.util.spec_from_file_location('render_sweep_v5', EXP / 'render_sweep_v5.py')
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)


def rgb_of(hue_cv, s=0.8, v=0.6):
    r, g, b = colorsys.hsv_to_rgb(hue_cv * 2 / 360.0, s, v)
    return [int(round(255 * c)) for c in (r, g, b)]


def image(zone=None, floor=None, size=(480, 640)):
    img = np.full(size + (3,), 128, dtype=np.uint8)  # neutral grey, S = 0
    if floor is not None:
        (t, b, l, r), colour = floor
        img[t:b, l:r] = colour
    if zone is not None:
        (t, b, l, r), colour = zone
        img[t:b, l:r] = colour
    return img


def test_constants_match_the_step_a_method():
    assert sweep.STEP_A_X == (1.5, 2.0, 2.5, 2.8, 3.0, 3.5)
    assert sweep.TICKS == (0, 5)
    assert sweep.MIN_COMPONENT_PX == 600
    assert [b[0] for b in sweep.BANDS] == ['B0', 'B1', 'B2']
    assert sweep.BANDS[0][1:] == ('gpu_calib_v230', 'v230_r5')


def test_ablation_repaints_only_zone_b():
    xml = ('<mujoco><worldbody><geom name="zone_zone_B" rgba=".2 .4 .95 .3" material="m"/>'
           '<geom name="zone_pickup" rgba=".12 .36 .70 .14"/></worldbody></mujoco>')
    out = sweep.ablate_zone_xml(xml)
    assert 'rgba="0.5 0.5 0.5 1"' in out and 'material' not in out
    assert 'rgba=".12 .36 .70 .14"' in out
    with pytest.raises(ValueError, match='ZONE_GEOM_NOT_UNIQUE'):
        sweep.ablate_zone_xml('<mujoco><worldbody/></mujoco>')


def test_lane_poses_keep_both_lanes_at_the_same_x():
    lane = {'r1': [-0.8982, -2.375, 0.03, 0.0], 'r2': [-0.8982, -2.875, 0.03, 0.0]}
    poses = sweep.lane_poses(lane, (1.5, 3.5))
    assert poses['x+1.500']['r1'][:2] == [1.5, -2.375]
    assert poses['x+3.500']['r2'][:2] == [3.5, -2.875]
    free = sweep.zone_free_poses(lane)
    assert set(free) == {p[0] for p in sweep.ZONE_FREE_POSES}
    assert free['wall_north']['r2'] == lane['r2']


def test_measure_pair_separates_zone_from_floor():
    zone = ((100, 150, 100, 400), rgb_of(112))
    floor = ((150, 300, 50, 600), rgb_of(110.5))  # inside B0, outside B1/B2, touching zone
    normal = image(zone=zone, floor=floor)
    ablated = image(floor=floor)
    b0 = sweep.measure_pair(normal, ablated, 'gpu_calib_v230')
    assert b0['detected'] and b0['nonzone']['detected']
    assert not sweep.edges_match(b0['detection']['bbox'], b0['zone_only']['bbox'])
    b1 = sweep.measure_pair(normal, ablated, 'gpu_calib_v5_h111')
    assert b1['detected'] and not b1['nonzone']['detected']
    assert sweep.edges_match(b1['detection']['bbox'], b1['zone_only']['bbox'])
    assert b1['detection']['bottom_row'] == 149
    assert b1['zone_only']['px'] == 50 * 300


def _row(group, robot, m, key='k'):
    return dict(key=key, group=group, robot=robot, tick=0, pose='p', m=m)


def _measure(detected=True, nonzone_px=0, merge=False):
    bbox = [100, 100, 400, 150]
    det = dict(bbox=[100, 100, 400, 300] if merge else bbox) if detected else None
    m = dict(detected=detected, largest=dict(px=15000, bbox=bbox) if detected else None,
             zone_only=dict(px=15000, bbox=bbox),
             nonzone=dict(total_px=nonzone_px, detected=nonzone_px >= 600,
                          largest=dict(px=nonzone_px, bbox=bbox) if nonzone_px else None))
    if det:
        m['detection'] = det
    return m


def test_evaluate_band_criteria_and_selection_rule():
    good = [_row('zone_free', 'r1', _measure(detected=False)),
            _row('step_a', 'r1', _measure()), _row('step_a', 'r2', _measure()),
            _row('path', 'r1', _measure(detected=False))]
    v = sweep.evaluate_band(good)
    assert v['passed'] and all(not f for f in v['failing_frames'].values())
    fp = good + [_row('path', 'r2', _measure(detected=False, nonzone_px=900), 'fp')]
    assert sweep.evaluate_band(fp)['failing_frames']['c2'] == ['fp']
    merge = good + [_row('step_a', 'r2', _measure(merge=True), 'mg')]
    assert sweep.evaluate_band(merge)['failing_frames']['c4'] == ['mg']
    miss = good + [_row('step_a', 'r1', _measure(detected=False), 'miss')]
    assert sweep.evaluate_band(miss)['failing_frames']['c3'] == ['miss']
    # r2 step-A miss is report-only (C3 is r1 lane, as in Step A)
    assert sweep.evaluate_band(good + [_row('step_a', 'r2', _measure(detected=False))])['passed']
    zf = good + [_row('zone_free', 'r1', _measure(), 'zf')]
    assert sweep.evaluate_band(zf)['failing_frames']['c1'] == ['zf']

    assert sweep.select_band({'B0': {'passed': True}, 'B1': {'passed': True}})['selected'] == 'B0'
    sel = sweep.select_band({'B0': {'passed': False}, 'B1': {'passed': False},
                             'B2': {'passed': True}})
    assert sel == dict(selected='B2', profile='gpu_calib_v5_h112', gate_mode='v230_r5_v5h112',
                       step_b_allowed=True)
    stop = sweep.select_band({'B0': {'passed': False}, 'B1': {'passed': False},
                              'B2': {'passed': False}})
    assert stop['selected'] is None and stop['step_b_allowed'] is False


def test_prereg_draft_matches_the_script():
    draft = json.loads((EXP / 'NAV_V5_RECAL_PREREG_DRAFT.json').read_text())
    assert draft['status'] in ('DRAFT', 'FROZEN')
    assert draft['scene']['profile'] == sweep.V5_PROFILE
    assert draft['sweep']['step_a_x'] == list(sweep.STEP_A_X)
    assert draft['sweep']['path_x'] == list(sweep.PATH_X)
    assert draft['sweep']['ticks'] == list(sweep.TICKS)
    assert [c['id'] for c in draft['band_candidates']] == [b[0] for b in sweep.BANDS]
    for cand, (name, profile, mode) in zip(draft['band_candidates'], sweep.BANDS):
        assert cand['profile'] == profile and cand['gate_mode'] == mode
    from harness.e2ewarp_selfnav import GPU_CALIB_PROFILES
    for cand in draft['band_candidates']:
        band = GPU_CALIB_PROFILES[cand['profile']]
        assert list(band['hue_cv']) == cand['hue_cv']
        assert band['sat_min'] == cand['sat_min'] and list(band['val']) == cand['val']
    assert set(draft['criteria']) == {'C1_zone_free', 'C2_nonzone_fp0', 'C3_step_a_r1_detect',
                                      'C4_no_floor_merge'}
    assert draft['criteria_constants']['edge_tol_px'] == sweep.EDGE_TOL_PX


def test_analysis_checks_use_the_r3_render_check_spelling():
    rows = [_row('zone_free', 'r1', _measure(detected=False)),
            _row('zone_free', 'r2', _measure()),  # r2 zone-free frames are not counted
            _row('step_a', 'r1', _measure()),
            _row('path', 'r2', _measure(detected=False, nonzone_px=900))]
    c = sweep.analysis_checks(rows)['zone_free']
    assert c['frame_n'] == 3 and c['detections_total'] == 1
    assert c['max_largest_component_px'] == 900 and c['passed'] is False
    clean = sweep.analysis_checks(rows[:3])['zone_free']
    assert clean['detections_total'] == 0 and clean['passed'] is True
