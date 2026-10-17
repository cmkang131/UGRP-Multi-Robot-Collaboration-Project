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
    for name, digest in queue['input_sha256'].items():
        path = ROOT / name
        assert path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
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
