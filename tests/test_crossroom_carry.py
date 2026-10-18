"""Contract tests for the cross-room carry Stage A pre-registration.

These tests are stdlib-only and do not import a simulator: they check the
authored starts, the frozen pre-registration, the queue pins and the recount
funnel/door helpers.  Physics execution is measured on gcp3, not here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/2026-10-18-crossroom-carry'


def load_json(path):
    return json.loads(Path(path).read_text())


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_document():
    return load_json(EXP / 'setups.json')


# crossroom_loaded_wallline_v1 (this branch) edits the runner and the fix
# layer.  The strict per-file pins of the already-executed freezes belong to
# those freeze SHAs, so the three moved files are checked for existence only
# (the same rule the v1/v2 pins already use); every other pinned input keeps
# its byte-for-byte check.
WALLLINE_MOVED_INPUTS = {
    'experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py',
    'experiments/2026-10-18-crossroom-carry/scripts/vgs_fix.py',
    'experiments/2026-10-18-crossroom-carry/scripts/carry_state_own.py',
}


def assert_input_pins(pins):
    for name, digest in pins.items():
        path = ROOT / name
        assert path.is_file(), name
        if name in WALLLINE_MOVED_INPUTS:
            continue
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name


def test_setups_are_sixteen_west_starts_with_two_groups():
    doc = setup_document()
    eps = doc['episodes']
    assert doc['n'] == 16 and len(eps) == 16
    assert [e['split'] for e in eps[:8]] == ['west_near_wall'] * 8
    assert [e['split'] for e in eps[8:]] == ['west_far_wall'] * 8
    for e in eps:
        x = e['spawns']['r1'][0]
        # every start is on the pickup-room side of the divider (x=2.20)
        assert x < 2.20 - 0.195, e['start_note']
        assert len(e['spawns']['r1']) == 4
        assert e['seed'] == 601


def test_setups_peer_parks_are_outside_zones_and_clear_of_walls():
    doc = setup_document()
    world = load_json(ROOT / 'maps/zones/zone_wide_door_geometry_v3.json')
    regions = world['regions']

    def aabb_distance(x, y, c, h):
        dx = max(c[0] - h[0] - x, 0.0, x - (c[0] + h[0]))
        dy = max(c[1] - h[1] - y, 0.0, y - (c[1] + h[1]))
        return math.hypot(dx, dy)

    for rid, pose in doc['park_eval_only'].items():
        x, y = pose[0], pose[1]
        for name, r in regions.items():
            inside = (abs(x - r['center_m'][0]) <= r['half_extents_m'][0]
                      and abs(y - r['center_m'][1]) <= r['half_extents_m'][1])
            assert not inside, (rid, name)
            assert aabb_distance(x, y, r['center_m'], r['half_extents_m']) > 0.195
        for obstacle in world['obstacles']:
            if obstacle.get('kind') != 'wall':
                continue
            assert aabb_distance(x, y, obstacle['center_m'],
                                 obstacle['half_extents_m']) > 0.195


def test_prereg_is_stage_a_with_frozen_funnel_and_no_pooling():
    prereg = load_json(EXP / 'prereg.json')
    assert prereg['stage'] == 'A_unloaded'
    assert prereg['cap_sim_s'] == 180
    assert prereg['nworld'] == 16
    assert prereg['destination']['zone'] == 'B'
    assert prereg['scene']['host'] == 'ugrp-act-l4-gcp3'
    funnel = prereg['funnel_stages']['A']
    assert funnel[0] == 'requested_n16' and funnel[-1] == 'gt_inside'
    for name in ('door_crossed', 'post_cross_colour_seen', 'post_cross_found',
                 'arrived_declared'):
        assert name in funnel
    assert 'input_audit_zero' in funnel
    assert prereg['input_audit']['targets']['held_world_reads'] == 0
    assert prereg['toggles']['visgoal_expanding_search_v1'] == 'on'
    assert prereg['toggles']['visgoal_arrival_aim_inset_v1'] == 'off'
    assert prereg['control_policy']['arrival'].startswith('gate r4')
    assert prereg['no_pooling']
    assert 'visgoal-gate-r4-lawnmower' in prereg['no_pooling']
    # the 180 s cap is explicitly not pooled with the 120 s visgoal runs
    assert '120' in prereg['cap_end_note']


def test_queue_pins_existing_inputs_and_current_stack_values():
    queue = load_json(EXP / 'queue-stageA.json')
    assert queue['stage'] == 'A_unloaded'
    assert queue['sim_cap_s'] == 180.0
    assert queue['worlds_per_batch'] == 16
    assert queue['destination_zone'] == 'B'
    assert queue['toggles']['visgoal_expanding_search_v1'] == 'on'
    # Stage A separates C's expanding search from C's arrival-aim regression:
    assert queue['toggles']['visgoal_arrival_aim_inset_v1'] == 'off'
    assert queue['stack_values']['static_map_use'] == 'none'
    assert queue['stack_values']['no_pooling'] is True
    assert len(queue['source_sha']) == 40
    assert queue['input_sha256'], 'queue must pin its inputs'
    for name in queue['input_sha256']:
        assert (ROOT / name).is_file(), name
    # The Stage A pins belong to its executed freeze checkout (bc84e35c); the
    # working tree moved on for Stage B, so only Stage B pins are checked
    # against the current bytes.
    assert queue['no_pooling_conditions']


def test_stack_check_receipt_passed():
    stack = load_json(EXP / 'stack-stageA.json')
    assert stack['ok'] is True
    assert stack['current_compliant'] is True
    assert stack['admission'] == 'pass'


def test_recount_door_crossing_and_funnel_logic():
    recount = load_module('crossroom_recount',
                          EXP / 'scripts/crossroom_recount.py')
    # synthetic eval-only labels: walk east through the door at y=0.05
    labels = []
    for i in range(60):
        t = i / 10.0
        x = 2.00 + 0.02 * i
        labels.append(dict(t=t, frame_id=i, pose=[x, 0.05, 0.0],
                           inside_zone_B=False))
    door = recount.door_crossing(labels)
    assert door['crossed'] is True
    assert door['lateral_offset_m'] == 0.0
    assert abs(door['min_jamb_gap_m'] - 0.055) < 1e-6

    blocked = [dict(t=i / 10.0, frame_id=i, pose=[2.00 + 0.02 * i, 0.9, 0.0],
                    inside_zone_B=False) for i in range(60)]
    assert recount.door_crossing(blocked)['crossed'] is False

    rows = [
        dict(input_audit_zero=True, start_valid=True, door_crossed=True,
             post_cross_colour_seen=True, post_cross_found=True,
             arrived_declared=True, gt_inside=True),
        dict(input_audit_zero=True, start_valid=True, door_crossed=True,
             post_cross_colour_seen=False, post_cross_found=False,
             arrived_declared=False, gt_inside=None),
        dict(input_audit_zero=False, start_valid=True, door_crossed=False,
             post_cross_colour_seen=False, post_cross_found=False,
             arrived_declared=False, gt_inside=None),
    ]
    funnel = recount.funnel(rows)
    assert [s['cumulative_pass_n'] for s in funnel] == [3, 2, 2, 2, 1, 1, 1, 1]
    for prev, cur in zip(funnel, funnel[1:]):
        assert cur['input_n'] == prev['cumulative_pass_n']


def test_stage_b_queue_prereg_and_scene_are_consistent():
    queue = load_json(EXP / 'queue-stageB.json')
    prereg = load_json(EXP / 'prereg-stageB.json')
    scene = load_json(EXP / 'crossroom_carry_scene_v1.json')
    assert queue['stage'] == 'B_loaded'
    assert prereg['stage'] == 'B_loaded'
    assert queue['sim_cap_s'] == 180.0
    assert queue['worlds_per_batch'] == 16
    assert queue['toggles']['crossroom_carry_scene_v1'] == 'on'
    assert queue['toggles']['visgoal_expanding_search_v1'] == 'on'
    assert queue['toggles']['visgoal_arrival_aim_inset_v1'] == 'off'
    assert queue['gripper_pwm_closed'] == 1500
    assert queue['loaded_scene'] == (
        'experiments/2026-10-18-crossroom-carry/crossroom_carry_scene_v1.json')
    assert scene['scenario_id'] == 'crossroom_carry_scene_v1'
    assert len(scene['eval']['setup']['placements']) == 1
    assert scene['eval']['setup']['placements'][0]['kind'] == 'red'
    assert scene['map_id'] == 'zone_wide_door_geometry_v3'
    assert queue['input_sha256'], 'stage B queue must pin its inputs'
    for name in queue['input_sha256']:
        assert (ROOT / name).is_file(), name
    # Stage B pins belong to its executed freeze checkout 868236f55; the
    # working tree moved on for the Stage A-fix candidate, so only existence is
    # checked here (the gate verifies the pins on its own checkout).
    assert 'crossroom-stageA' in prereg['no_pooling']
    assert prereg['funnel_stages']['B'][-1] == 'gt_cargo_in_zone'


def test_carry_state_own_detects_red_box_and_requires_closed_gripper():
    module = load_module(
        'carry_state_own',
        EXP / 'scripts/carry_state_own.py')
    import numpy as np
    # a red rectangle in the near-field ROI
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[300:420, 250:390] = (0, 0, 255)   # BGR red
    det = module.red_component(frame)
    assert det['largest'] >= 90
    mon = module.CarryStateOwn()
    held = mon.update(0.0, frame, 1500)
    assert held['state'] == 'held'
    open_cmd = mon.update(0.1, frame, 2000)
    assert open_cmd['state'] != 'held'
    empty = np.zeros((480, 640, 3), dtype=np.uint8)
    mon2 = module.CarryStateOwn()
    mon2.update(0.0, frame, 1500)
    for i in range(1, 30):
        state = mon2.update(i * 0.1, empty, 1500)
    assert state['state'] == 'lost'


def test_stage_b_settle_validation_passed():
    val = load_json(EXP / 'setup-validation-B.json')
    assert val['n'] == 16
    assert val['pass_n'] == 16
    assert all(r['settle_ok'] for r in val['episodes'])
    assert val['gripper_pwm_closed'] == 1500
    assert val['cargo_own_thresholds']['held_min_pixels'] > 0


def test_fix_queue_and_prereg_contract():
    queue = load_json(EXP / 'queue-stageA-fix.json')
    prereg = load_json(EXP / 'prereg-stageA-fix.json')
    assert queue['stage'] == 'A_unloaded_fix'
    assert prereg['stage'] == 'A_unloaded_fix'
    for key in ('crossroom_gap_twosided_v1', 'crossroom_door_align_v1',
                'crossroom_paint_area_v1', 'crossroom_contacts_v1'):
        assert queue['toggles'][key] == 'on', key
        assert prereg['policy']['toggles'][key] == 'on', key
    assert queue['sim_cap_s'] == 180.0
    assert queue['worlds_per_batch'] == 16
    assert 'crossroom-stageA' in prereg['no_pooling']
    assert prereg['paint_filter']['constant'].startswith('PAINT_MIN_EXTENT_M = 0.15')
    for name in queue['input_sha256']:
        assert (ROOT / name).is_file(), name
    # v1 pins belong to its executed freeze checkout edded4f53; the working
    # tree moved on for the v2 candidate, so only existence is checked here.


def test_paint_area_filter_rejects_beam_sized_extent():
    module = load_module('paint_area_filter',
                         EXP / 'scripts/paint_area_filter.py')
    paint = dict(pixels=17410, reason='destination_colour_observed')
    beam_rec = dict(reason='painted_ground_hypothesis', extent_m=0.041)
    out, info = module.filter_paint(paint, beam_rec)
    assert info['action'] == 'rejected'
    assert out['pixels'] == 0
    zone_rec = dict(reason='painted_ground_hypothesis', extent_m=0.62)
    out2, info2 = module.filter_paint(dict(paint), zone_rec)
    assert info2['action'] == 'accepted'
    assert out2['pixels'] == paint['pixels']
    out3, info3 = module.filter_paint(dict(paint), dict(reason='destination_colour_absent'))
    assert info3['action'] == 'not_metric_patch'


class _FakeGeom:
    def __init__(self, name):
        self.name = name


class _FakeBody:
    def __init__(self, name):
        self.name = name


class _FakeModel:
    ngeom = 3
    geom_bodyid = [0, 1, 2]

    def geom(self, i):
        return _FakeGeom(['r1__v3_gripper_base_plate', 'zone_wall_divider_1',
                          'cargo_red_1_geom'][i])

    def body(self, i):
        return _FakeBody(['r1__robot', 'world', 'world'][i])


class _FakeWD:
    def __init__(self, geom_pairs):
        import numpy as np
        self.nacon = np.array([1, 0])
        self.contact = type('C', (), {'geom': np.array([geom_pairs]),
                                      'worldid': np.array([0])})()


def test_contact_recorder_records_interesting_rising_edge():
    module = load_module('contact_recorder', EXP / 'scripts/contact_recorder.py')
    rec = module.ContactRecorder(_FakeModel(), 2, decimate=1)
    wd = _FakeWD([[0, 2]])  # r1 robot vs cargo contact
    for i in range(3):
        info = rec.update(wd, i * 0.1)
        assert info['counts'] == [1, 0]
    assert rec.events, 'interesting rising edge must be recorded'
    cats = rec.events[0]['categories']
    assert 'wall' in cats or 'cargo' in cats
    summary = rec.summary()
    assert summary['ticks_with_contact'] == 3
    assert summary['ticks_checked'] == 3
    assert summary['ticks_with_interest'] >= 1


def test_fix2_queue_and_prereg_contract():
    queue = load_json(EXP / 'queue-stageA-fix2.json')
    prereg = load_json(EXP / 'prereg-stageA-fix2.json')
    assert queue['stage'] == 'A_unloaded_fix2'
    assert prereg['stage'] == 'A_unloaded_fix2'
    v2 = ('crossroom_gap_twosided_v2_v1', 'crossroom_paint_area_v2_v1',
          'crossroom_approach_escape_v1')
    for key in v2:
        assert queue['toggles'][key] == 'on', key
        assert prereg['policy']['toggles'][key] == 'on', key
    assert queue['sim_cap_s'] == 180.0 and queue['worlds_per_batch'] == 16
    assert 'crossroom-stageA-fix' in prereg['no_pooling']
    cal = prereg['v2_changes']['paint_filter_v2']['calibration_from_recorded_frames']
    assert cal['true_zone_B_patches']['extent_m']['min'] == 0.205
    assert cal['long_beam_blue_end_band_patches']['extent_m']['max'] == 0.099
    for name in queue['input_sha256']:
        assert (ROOT / name).is_file(), name
    # v2 pins belong to its executed freeze checkout 097c335d6; the working
    # tree moved on for v3, so only existence is checked here.


def test_fix3_queue_and_prereg_contract():
    queue = load_json(EXP / 'queue-stageA-fix3.json')
    prereg = load_json(EXP / 'prereg-stageA-fix3.json')
    assert queue['stage'] == 'A_unloaded_fix3'
    assert prereg['stage'] == 'A_unloaded_fix3'
    for key in ('crossroom_gap_v3_v1', 'crossroom_zone_edge_v1'):
        assert queue['toggles'][key] == 'on', key
        assert prereg['policy']['toggles'][key] == 'on', key
    assert queue['sim_cap_s'] == 180.0 and queue['worlds_per_batch'] == 16
    assert 'crossroom-stageA-fix2' in prereg['no_pooling']
    cal = prereg['v3_changes']['gap_v3']['calibration_from_recorded_stage_A_gap_events']
    assert len(cal['events']) == 9
    assert cal['events'][1]['front_cone_points'] == 418
    assert '0.960' in prereg['v3_changes']['zone_edge']['calibration']
    assert_input_pins(queue['input_sha256'])


def test_stageb_fix_two_arm_contract():
    m0 = load_json(EXP / 'queue-stageB-fix-M0.json')
    m1 = load_json(EXP / 'queue-stageB-fix-M1.json')
    prereg = load_json(EXP / 'prereg-stageB-fix.json')
    assert m0['stage'] == 'B_loaded_mask_off'
    assert m1['stage'] == 'B_loaded_mask_on'
    assert m0['toggles']['crossroom_carry_mask_v1'] == 'off'
    assert m1['toggles']['crossroom_carry_mask_v1'] == 'on'
    assert m0['counterfactual_arm'] == 'M0_mask_off'
    assert m1['counterfactual_arm'] == 'M1_mask_on'
    for arm in (m0, m1):
        assert arm['sim_cap_s'] == 180.0 and arm['worlds_per_batch'] == 16
        assert arm['episode_count'] == 16
        assert arm['toggles']['crossroom_carry_scene_v1'] == 'on'
        assert arm['only_difference'] == 'crossroom_carry_mask_v1 toggle'
    assert set(prereg['arms']) == {'M0_mask_off', 'M1_mask_on'}
    assert_input_pins(m0['input_sha256'])


# ---------------------------------------------------------------------------
# crossroom_loaded_wallline_v1 (default off, occlusion-aware loaded follow)
# Design: outputs/reports/crossroom-stageB-fix.md section 2.
# ---------------------------------------------------------------------------

def _loaded_wallline_module():
    return load_module('crossroom_loaded_wallline_test',
                       EXP / 'scripts/loaded_wallline.py')


def _register_vendor_for_fix():
    """Register the byte-vendored policy the fix layer subclasses."""
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    vendor = EXP / 'vendor'
    for name, path in (
            ('sim.grasp_act_solo_lookback',
             vendor / 'grasp_act_solo_lookback.py'),
            ('harness.scene_colour_boundary',
             vendor / 'scene_colour_boundary.py'),
            ('sim.visual_goal_search', vendor / 'visual_goal_search.py')):
        if name in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)


def _vgs_fix_module():
    _register_vendor_for_fix()
    return load_module('crossroom_vgs_fix_test', EXP / 'scripts/vgs_fix.py')


def _wall_point(x, y, row):
    return dict(relative_xy_m=[float(x), float(y)],
                range_m=math.hypot(float(x), float(y)),
                bearing_rad=math.atan2(float(y), float(x)), row=int(row))


def _wall_line(offset_m, bearing_deg, s0, s1, n=6, row=340):
    theta = math.radians(float(bearing_deg))
    d = (math.cos(theta), math.sin(theta))
    normal = (-d[1], d[0])
    cx, cy = -float(offset_m) * normal[0], -float(offset_m) * normal[1]
    return [_wall_point(cx + s * d[0], cy + s * d[1], row)
            for s in (s0 + i * (s1 - s0) / (n - 1) for i in range(n))]


def module_side_foot_none(walls):
    return _loaded_wallline_module().side_foot(walls, 'right') is None


def test_loaded_wallline_toggle_default_off_and_loaded_stages_only():
    import pytest
    module = _loaded_wallline_module()
    assert module.OPTION == 'crossroom_loaded_wallline_v1'
    assert module.toggle_on({}) is False
    assert module.toggle_on({module.OPTION: 'off'}) is False
    assert module.toggle_on({module.OPTION: 'on'}) is True
    assert module.admit({}, 'B_loaded') is False
    for stage in ('B_loaded', 'B_loaded_mask_off', 'B_loaded_mask_on'):
        assert module.admit({module.OPTION: 'on'}, stage) is True
    for stage in ('A_unloaded', 'A_unloaded_fix', 'A_unloaded_fix2',
                  'A_unloaded_fix3'):
        with pytest.raises(ValueError):
            module.admit({module.OPTION: 'on'}, stage)


def test_loaded_wallline_band_top_is_own_rgb_and_state_gated():
    import numpy as np
    module = _loaded_wallline_module()
    carry = load_module('crossroom_carry_state_test',
                        EXP / 'scripts/carry_state_own.py')
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[400:464, 31:587] = (0, 0, 255)   # BGR pure red
    comp = carry.full_frame_red_component(frame)
    assert comp['band_top_row'] == 400
    assert comp['bbox_xywh'][1] == 400 and comp['bbox_xywh'][2] == 556
    assert module.band_top_from_mask(
        np.asarray(frame[:, :, 2] > 200)) == 400
    empty = np.zeros((480, 640), dtype=bool)
    assert module.band_top_from_mask(empty) is None
    # held -> measured row (fallback 400); uncertain -> fallback; lost -> off
    assert module.band_top_for_state('held', 407) == 407
    assert module.band_top_for_state('held', None) == 400
    assert module.band_top_for_state('uncertain', 407) == 400
    assert module.band_top_for_state('lost', 407) is None


def test_loaded_wallline_rows_attach_and_band_filter():
    import numpy as np
    module = _loaded_wallline_module()
    points = [_wall_point(1.0, -0.55, 0), _wall_point(1.1, -0.55, 0),
              _wall_point(1.2, -0.55, 0), _wall_point(1.3, -0.55, 0)]
    rows = np.array([380.0, 396.0, 402.0, 420.0])
    front = np.array([True, True, True, False])
    out = module.attach_rows(points, rows, front)
    assert [p['row'] for p in out] == [380, 396, 402]  # behind-camera dropped
    assert [p['row'] for p in module.above_band(out, 400)] == [380, 396]
    assert module.above_band(out, None) == []


def test_loaded_wallline_fit_drives_tangent_and_offset():
    module = _loaded_wallline_module()
    # robot yawed 25 deg left of the wall -> wall tangent -25 deg -> turn right
    tang = _wall_line(0.55, -25.0, 0.7, 1.1, row=330)
    above = module.above_band(tang, 400)
    fit = module.fit_wall_line(module.side_points(above, 'right'),
                               wall_side='right')
    assert fit['ok'] and abs(fit['tangent_deg'] + 25.0) < 1e-6
    assert abs(fit['offset_m'] - 0.55) < 1e-6
    command = module.follow_command(fit, 'right')
    assert command['reason'] == 'tangent' and command['exact_turn'] == -1
    # tangent aligned: the lateral offset drives the pulse
    close = _wall_line(0.40, 0.0, 1.4, 1.7, row=340)
    fit_close = module.fit_wall_line(close, wall_side='right')
    assert abs(fit_close['offset_m'] - 0.40) < 1e-6
    assert module.follow_command(fit_close, 'right')['reason'] == 'offset_close'
    assert module.follow_command(fit_close, 'right')['exact_turn'] == 1
    far = _wall_line(0.75, 0.0, 1.25, 1.55, row=340)
    fit_far = module.fit_wall_line(far, wall_side='right')
    assert module.follow_command(fit_far, 'right')['reason'] == 'offset_far'
    assert module.follow_command(fit_far, 'right')['exact_turn'] == -1
    dead = _wall_line(0.55, 0.0, 1.4, 1.7, row=340)
    fit_dead = module.fit_wall_line(dead, wall_side='right')
    assert module.follow_command(fit_dead, 'right')['exact_turn'] == 0
    # a fit on the other side of the robot is not this wall
    assert module.fit_wall_line(_wall_line(0.55, 0.0, 1.4, 1.7, row=340),
                                wall_side='left')['ok'] is False


def test_loaded_wallline_occluded_band_does_not_emit_gap():
    module = _loaded_wallline_module()
    # The near foot (row 430, inside the band) is all the robot can see in the
    # base follow sector; the far wall above the band is beyond 1.5 m.
    walls = [_wall_point(0.55, -0.55, 430),
             _wall_point(1.40, -0.55, 340), _wall_point(1.475, -0.55, 340),
             _wall_point(1.55, -0.55, 340), _wall_point(1.625, -0.55, 340),
             _wall_point(1.70, -0.55, 340)]
    assert module.side_foot(walls, 'right') is not None
    gate = module.LoadedWallLineGate(enabled=True, wall_side='right')
    blocked = [w for w in walls if w['row'] > 400]
    hidden = [dict(w) for w in walls if w['row'] <= 400]
    above = module.above_band(walls, 400)
    assert len(above) == 5 and blocked and hidden
    follow = gate.decide(walls, 400, gap_claimed=False)
    assert follow['mode'] == 'follow'
    assert follow['command']['exact_turn'] == 0
    defer = gate.decide(walls, 400, gap_claimed=True)
    assert defer['mode'] == 'defer'
    assert defer['evidence']['ok'] is False
    assert 'front_ok' in defer['evidence'] and defer['evidence']['front_ok']
    assert gate.counters['gap_deferred_cargo_blind'] == 1
    assert gate.counters['gap_confirmed_above_band'] == 0
    # toggle off / no band top: the gate never decides anything
    off = module.LoadedWallLineGate(enabled=False, wall_side='right')
    assert off.decide(walls, 400, gap_claimed=True)['mode'] == 'off'
    assert off.counters['gap_deferred_cargo_blind'] == 0
    assert gate.decide(walls, None, gap_claimed=True)['mode'] == 'off'


def test_loaded_wallline_door_requires_all_positive_evidence():
    module = _loaded_wallline_module()
    near = [_wall_point(x, -0.55, 360)
            for x in (0.30, 0.3625, 0.425, 0.4875, 0.55)]
    far = [_wall_point(x, -0.55, 350) for x in (1.05, 1.09, 1.13, 1.17)]
    points = module.above_band(near + far, 400)
    fit = module.fit_wall_line(module.side_points(points, 'right'),
                               wall_side='right')
    ok = module.door_positive_evidence(points, fit, 'right')
    assert ok['ok'] is True
    assert ok['front_ok'] and ok['hole_ok'] and ok['far_jamb_ok']
    assert abs(ok['hole_m'] - 0.50) < 1e-6
    # 1) front cone occupied -> reject
    blocked = points + [_wall_point(0.90 + 0.01 * i, 0.0, 330)
                        for i in range(30)]
    ev = module.door_positive_evidence(blocked, fit, 'right')
    assert ev['ok'] is False and ev['front_ok'] is False
    # 2) hole too small -> reject
    short = module.above_band(
        near + [_wall_point(x, -0.55, 350) for x in (0.75, 0.79, 0.83)], 400)
    fit_short = module.fit_wall_line(module.side_points(short, 'right'),
                                     wall_side='right')
    ev2 = module.door_positive_evidence(short, fit_short, 'right')
    assert ev2['ok'] is False and ev2['hole_ok'] is False
    # 3) far jamb beyond 1.3 m -> reject
    far_pts = module.above_band(
        [_wall_point(x, -0.55, 360) for x in (0.50, 0.5625, 0.625, 0.6875,
                                              0.75)]
        + [_wall_point(x, -0.55, 350) for x in (1.25, 1.29, 1.33, 1.37)], 400)
    fit_far = module.fit_wall_line(module.side_points(far_pts, 'right'),
                                   wall_side='right')
    ev3 = module.door_positive_evidence(far_pts, fit_far, 'right')
    assert ev3['ok'] is False and ev3['far_jamb_ok'] is False
    assert abs(ev3['hole_m'] - 0.50) < 1e-6
    # 4) no line fit -> reject even with an empty cone
    ev4 = module.door_positive_evidence(points, None, 'right')
    assert ev4['ok'] is False and 'no_line_fit' in ev4['reasons']


def test_loaded_wallline_off_is_base_follow_unchanged():
    fx = _vgs_fix_module()
    option = 'visual_goal_search_v1'
    base = fx.FixedVisualGoalSearch(option=option)
    off = fx.LoadedWallLineSearch(option=option, loaded_wallline=False)
    near = [_wall_point(0.30, -0.55, 430)]
    line = _wall_line(0.55, 0.0, 1.4, 1.7, row=340)
    walls = near + line
    for skill in (base, off):
        skill.wall_side = 'right'
        skill._set_stage(0.0, 'follow_north')
    for tick in range(1, 6):
        t = tick * 0.1
        a = base.control(t, paint={}, walls=walls)
        b = off.control(t, paint={}, walls=walls)
        a.pop('events', None)
        b.pop('events', None)
        assert a == b, (tick, a, b)
    assert off.fix_summary()['loaded_wallline'] is False
    assert off.loaded_gate.enabled is False
    # enabled but unloaded/no band: still the base path
    on = fx.LoadedWallLineSearch(option=option, loaded_wallline=True)
    on.wall_side = 'right'
    on._set_stage(0.0, 'follow_north')
    reference = fx.FixedVisualGoalSearch(option=option)
    reference.wall_side = 'right'
    reference._set_stage(0.0, 'follow_north')
    for tick in range(1, 6):
        t = tick * 0.1
        a = reference.control(t, paint={}, walls=walls)
        b = on.control(t, paint={}, walls=walls)   # no band top -> inactive
        a.pop('events', None)
        b.pop('events', None)
        assert a == b, (tick, a, b)
    assert on.cargo_band_top is None
    assert on.fix_summary()['loaded_band_top_row'] is None


def test_loaded_wallline_loaded_follow_uses_line_not_nearest_foot():
    fx = _vgs_fix_module()
    option = 'visual_goal_search_v1'
    # near side foot at a bearing the base controller would chase (-60 deg),
    # inside the cargo band; the above-band wall is far and straight ahead.
    walls = [_wall_point(0.30, -0.55, 430)] + _wall_line(0.55, 0.0, 1.4, 1.7)
    base = fx.FixedVisualGoalSearch(option=option)
    on = fx.LoadedWallLineSearch(option=option, loaded_wallline=True)
    for skill in (base, on):
        skill.wall_side = 'right'
        skill._set_stage(0.0, 'follow_north')
    base_action = base.control(0.1, paint={}, walls=walls)
    line_action = on.control(0.1, paint={}, walls=walls,
                             cargo_held=True, cargo_band_top=400)
    assert base_action['exact_turn'] != 0          # nearest-foot bearing bias
    assert line_action['exact_turn'] == 0          # fitted line tangent
    assert line_action['forward'] > 0
    assert on.loaded_follow_overrides == 1
    debug = on.loaded_debug()
    assert debug['active'] is True and debug['fit_ok'] is True
    assert debug['mode'] == 'follow' and debug['above_band_points'] == 6


def test_loaded_wallline_vetoes_gap_then_stops_blind():
    fx = _vgs_fix_module()
    option = 'visual_goal_search_v1'
    # The only wall point is inside the cargo band (row 430) and outside the
    # base follow sector, so the base controller sees no side foot and would
    # claim a gap; there is no above-band point to fit.
    walls = [_wall_point(1.50, -0.55, 430)]
    assert module_side_foot_none(walls)
    skill = fx.LoadedWallLineSearch(option=option, loaded_wallline=True)
    skill.wall_side = 'right'
    skill._set_stage(0.0, 'follow_north')
    stages = []
    for tick in range(1, 14):
        t = tick * 0.1
        action = skill.control(t, paint={}, walls=walls,
                               cargo_held=True, cargo_band_top=400)
        stages.append(action['stage'])
        if action['stop']:
            break
    reasons = [e['reason'] for e in skill.events]
    assert stages == ['follow_north'] * 11, stages
    assert skill.gap_claims == 3               # base tried at ticks 3,6,9
    assert skill.loaded_gate.counters['gap_deferred_cargo_blind'] == 3
    assert reasons.count('gap_deferred_cargo_blind') == 3
    assert reasons.count('STOPPED_BLIND_CARGO') == 1
    assert action['stop'] is True
    summary = skill.fix_summary()
    assert summary['loaded_wallline'] is True
    assert summary['blind_cargo_stop_events'] == 1
    assert summary['loaded_gate']['gap_confirmed_above_band'] == 0


def test_loaded_wallline_true_door_keeps_gap_cross():
    fx = _vgs_fix_module()
    option = 'visual_goal_search_v1'
    # no side foot in the base follow sector -> the base claims a gap
    walls = _wall_line(0.55, 0.0, 1.4, 1.7)
    assert module_side_foot_none(walls)
    skill = fx.LoadedWallLineSearch(option=option, loaded_wallline=True)
    skill.wall_side = 'right'
    skill._set_stage(0.0, 'follow_north')

    def forced_allow(self, *args, **kwargs):
        if kwargs.get('gap_claimed'):
            self.counters['gap_confirmed_above_band'] += 1
        return dict(mode='allow_gap', observation=dict(above=[], side=[]),
                    evidence=dict(front_ok=True, front_cone_points=0,
                                  hole_ok=True, hole_m=0.5,
                                  far_jamb_ok=True, far_jamb_range_m=1.1,
                                  ok=True, reasons=[]))

    skill.loaded_gate.decide = forced_allow.__get__(skill.loaded_gate)
    for tick in range(1, 5):
        action = skill.control(tick * 0.1, paint={}, walls=walls,
                               cargo_held=True, cargo_band_top=400)
    reasons = [e['reason'] for e in skill.events]
    assert skill.stage in ('gap_cross', 'gap_forward'), skill.stage
    assert 'gap_confirmed_above_band' in reasons
    assert skill.loaded_gate.counters['gap_confirmed_above_band'] == 1
    assert skill.loaded_gap_confirmed == 1
    assert skill.fix_summary()['loaded_gap_confirmed'] == 1


def test_loaded_wallline_no_queue_enables_it():
    """Default off in the recorded contract: no queue selects the toggle."""
    module = _loaded_wallline_module()
    queues = sorted(EXP.glob('queue-*.json'))
    assert queues, 'queue pins must exist'
    enabled = [q.name for q in queues
               if module.toggle_on(load_json(q).get('toggles', {}))]
    assert enabled == [], enabled
