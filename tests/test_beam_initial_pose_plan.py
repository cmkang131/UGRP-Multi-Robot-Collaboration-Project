"""T08a static/fake only: no renderer, physics, model or controller execution."""
import copy
import itertools
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from harness import beam_initial_pose_plan as bp
from harness.static_keepouts import polygon_at

ROOT = Path(__file__).resolve().parents[1]
# Public setup declarations, authored literally; NOT extracted from eval.setup.
CASES = [('s1_normal_mixed_v2', [1.3, .4, 1.570796], (1.275, .45, math.pi / 2)),
         ('s3_late_rendezvous_v2', [.1, .4, 1.570796], (.125, .45, math.pi / 2)),
         ('s6_novel_relation_v2', [1.1, -.8, 1.570796], (1.1, -.85, math.pi / 2))]


def inputs(index=0):
    name, pose, _ = CASES[index]
    scenario = json.loads((ROOT / 'configs/zone_study_scenarios_v2' / (name + '.json')).read_text())
    order = next(o for o in scenario['orders'] if o['kind'] == 'long_beam')
    map_id = scenario['map_id']
    directory = 'zones' if map_id == 'zone_wide_door_geometry_v2' else 'zones_final'
    static = json.loads((ROOT / 'maps' / directory / (map_id + '.json')).read_text())
    coarse = {'beam_xyyaw': list(pose), 'grid': dict(bp.GRID), 'source': bp.SOURCE}
    return static, coarse, order


def plan(index=0):
    static, coarse, order = inputs(index)
    return bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, order), order)


@pytest.mark.parametrize('index', range(3))
def test_original_pose_counterexamples_remain_refused_by_legacy(index):
    from harness.zone_pair_executor import make_plan
    from harness.pair_owncam_approach import coarse_order_sheet
    static, coarse, _ = inputs(index)
    assert coarse_order_sheet(CASES[index][2]) == coarse
    # Original s6's two-door map fails even earlier; use the supported M2 map
    # to isolate the initial-pose refusal shared by all three exact poses.
    m2_map = inputs(0)[0]
    with pytest.raises(ValueError, match='PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE'):
        make_plan(m2_map, coarse, 'A')
    if index == 2:
        with pytest.raises(ValueError, match='UNSUPPORTED_PAIR_MAP'):
            make_plan(static, coarse, 'A')


@pytest.mark.parametrize('index', range(3))
def test_formal_north_south_geometry_is_static_only(index):
    value = plan(index)
    pose = CASES[index][1]
    radius = .27 + value['model_convention']['station_radius_m']
    for role, sign in [('end_neg', -1), ('end_pos', 1)]:
        g = value['roles'][role]
        assert g['station_xyyaw'][:2] == pytest.approx([pose[0], pose[1] + sign * radius], abs=1e-6)
        assert g['station_xyyaw'][2] == pytest.approx(-sign * math.pi / 2, abs=1e-6)
        assert math.dist(g['prestation_xyyaw'][:2], g['station_xyyaw'][:2]) == pytest.approx(.25)
    assert value['model_convention']['robot_model'] == 'masterpi_v3'
    assert value['role_assignment'] is value['controller_code_sha256'] is None
    assert not value['executable'] and not value['e2e_admitted'] and value['sim_cap_s'] == 0
    assert 'route' not in value and 'door_plan' not in value
    assert set(value['refusals']) == {'spawn_to_prestation', 'carry_route', 'pivot', 'execution'}
    assert set(value['swept_bounds_m']) == {'beam', 'end_neg', 'end_pos'}


def test_static_pass_cannot_be_submitted_as_a_legacy_executable_plan():
    from harness.zone_pair_executor import make_plan
    value = plan()
    for payload in (value, value['sheet']):
        with pytest.raises(ValueError, match='BAD_COARSE_ORDER_SHEET'):
            make_plan(inputs()[0], payload, 'A')


@pytest.mark.parametrize('index', range(3))
def test_continuous_uncertainty_box_contains_original_and_all_carrier_sweeps(index):
    value = plan(index)
    cx, cy, yaw = CASES[index][1]
    original = CASES[index][2]
    assert max(abs(original[i] - (cx, cy)[i]) for i in (0, 1)) <= bp.ERROR['xy_per_axis_m']
    assert abs(original[2] - yaw) <= bp.ERROR['yaw_rad']
    e, a = bp.ERROR.values()
    # Independent vertices/translation fractions and interior yaw samples,
    # including all error-box corners and both physical carrier roles.
    for role in bp.ROLES:
        g = value['roles'][role]
        endpoints = g['local_parts_at_endpoints']
        n = len(endpoints) // 2
        samples = [g['search_at_pre']]
        for t in (0., .17, .5, .91, 1.):
            for p, q in zip(endpoints[:n], endpoints[n:]):
                samples.append([(x*(1-t)+u*t, y*(1-t)+v*t) for (x, y), (u, v) in zip(p, q)])
        x0, x1, y0, y1 = value['swept_bounds_m'][role]
        for dx, dy, da in itertools.product((-e, e), (-e, e), (-a, -.31*a, 0, .79*a, a)):
            for poly in samples:
                for x, y in polygon_at((cx+dx, cy+dy, yaw+da), poly):
                    assert x0 + bp.MARGIN_M - 1e-12 <= x <= x1 - bp.MARGIN_M + 1e-12
                    assert y0 + bp.MARGIN_M - 1e-12 <= y <= y1 - bp.MARGIN_M + 1e-12


def test_analytic_extrema_include_interior_turning_point_not_only_endpoints():
    lo, hi = bp._rotated_range(1., 1., -.9, -.7)
    assert hi == pytest.approx(math.sqrt(2))
    assert lo < hi


@pytest.mark.parametrize('key,value,reason', [
    ('source', 'eval.setup.placements', 'UNTRUSTED_COARSE_SOURCE'),
    ('source', 'live RGB', 'UNTRUSTED_COARSE_SOURCE'),
    ('grid', {'xy_m': .01, 'yaw_rad': .174533}, 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('grid', {'xy_m': .1, 'yaw_rad': .1}, 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [1.275, .45, 1.570796], 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [1.3, .4, math.pi/2], 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [True, .4, 1.570796], 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [float('nan'), .4, 1.570796], 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [float('inf'), .4, 1.570796], 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [1e308, .4, 1.570796], 'ORDER_SHEET_NOT_ON_COARSE_GRID'),
    ('beam_xyyaw', [1.3, .4, 0.], 'UNSUPPORTED_BEAM_HEADING'),
])
def test_bad_coarse_input_refused(key, value, reason):
    static, coarse, order = inputs()
    coarse[key] = value
    with pytest.raises(bp.PlanRefusal, match=reason):
        bp.freeze_public_sheet(static, coarse, order)


@pytest.mark.parametrize('key,value', [('item_id', 'other'), ('order_id', 'beam_1'),
                                     ('provenance', 'live'), ('order_sha256', '0'*64),
                                     ('coarse_sha256', '0'*64),
                                     ('map_sha256', '0'*64), ('initial_error_bound', {'xy_per_axis_m': 0.})])
def test_frozen_binding_and_error_range_cannot_be_relabelled(key, value):
    static, coarse, order = inputs()
    sheet = bp.freeze_public_sheet(static, coarse, order)
    sheet[key] = value
    with pytest.raises(bp.PlanRefusal, match='PUBLIC_SHEET_BINDING_MISMATCH'):
        bp.make_initial_pose_plan(static, sheet, order)


def test_changing_a_frozen_coarse_pose_requires_a_new_declaration():
    static, coarse, order = inputs()
    sheet = bp.freeze_public_sheet(static, coarse, order)
    coarse['beam_xyyaw'][0] = .1
    assert sheet['coarse']['beam_xyyaw'][0] == 1.3  # no caller alias
    sheet['coarse']['beam_xyyaw'][0] = .1
    with pytest.raises(bp.PlanRefusal, match='PUBLIC_SHEET_BINDING_MISMATCH'):
        bp.make_initial_pose_plan(static, sheet, order)


@pytest.mark.parametrize('role', bp.ROLES)
@pytest.mark.parametrize('field', ['obstacles', 'terrain'])
def test_carrier_outer_corner_blocked_even_when_beam_and_centres_clear(role, field):
    static, coarse, order = inputs()
    value = plan()
    x0, x1, y0, y1 = value['swept_bounds_m'][role]
    static[field].append({'id': 'corner_block', 'center_m': [x1-.002, (y0+y1)/2],
                          'half_extents_m': [.001, .001], 'yaw_rad': .37})
    with pytest.raises(bp.PlanRefusal, match='INITIAL_APPROACH_BLOCKED') as exc:
        bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, order), order)
    assert exc.value.detail['component'] == role


@pytest.mark.parametrize('axis,side', [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_all_outer_map_boundaries_touch_and_epsilon_crossing_refused(axis, side):
    static, coarse, order = inputs()
    boxes = plan()['swept_bounds_m'].values()
    idx = axis * 2 + side
    edge = (max if side else min)(box[idx] for box in boxes)
    for delta, accepted in [(0., False), ((1 if side else -1)*1e-7, True),
                            ((-1 if side else 1)*1e-7, False)]:
        changed = copy.deepcopy(static)
        changed['bounds_m'][idx] = edge + delta
        sheet = bp.freeze_public_sheet(changed, coarse, order)
        if accepted:
            bp.make_initial_pose_plan(changed, sheet, order)
        else:
            with pytest.raises(bp.PlanRefusal, match='INITIAL_APPROACH_OUTSIDE_MAP'):
                bp.make_initial_pose_plan(changed, sheet, order)


def test_old_point_three_backoff_cannot_silently_replace_new_v3_contract(monkeypatch):
    static, coarse, order = inputs()
    monkeypatch.setattr(bp, 'PRESTATION_BACK_M', .30)
    with pytest.raises(bp.PlanRefusal, match='INITIAL_APPROACH_OUTSIDE_MAP') as exc:
        bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, order), order)
    assert exc.value.detail['component'] == 'end_pos'
    assert exc.value.detail['bounds_m'][3] > static['bounds_m'][3]


def test_public_identity_changes_hashes_without_conflating_item_and_order():
    static, coarse, order = inputs()
    before = plan()
    assert before['sheet']['order_id'] == 'order-5' and before['sheet']['item_id'] == 'beam_1'
    for mutation in ({'order_id': 'order-99'}, {'item_ids': ['beam_2']}, {'destination_zone': 'B'}):
        changed = {**order, **mutation}
        with pytest.raises(bp.PlanRefusal, match='PUBLIC_SHEET_BINDING_MISMATCH'):
            bp.make_initial_pose_plan(static, before['sheet'], changed)
        after = bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, changed), changed)
        assert after['order_sha256'] != before['order_sha256']
        assert after['plan_sha256'] != before['plan_sha256']
        assert after['role_geometry_sha256'] == before['role_geometry_sha256']


@pytest.mark.parametrize('mutation', [{'count': 2}, {'kind': 'heavy_crate'}, {'required_robots': True},
                                      {'identity': 'kind_fungible'}, {'item_ids': ['a', 'b']},
                                      {'eval': {}}, {'initial_location': {'pickup_bay': 'P2', 'slot': 'P1-1'}}])
def test_unsupported_order_refused(mutation):
    static, coarse, order = inputs()
    with pytest.raises(bp.PlanRefusal):
        bp.freeze_public_sheet(static, coarse, {**order, **mutation})


def test_unknown_map_private_sheet_and_unknown_target_are_refusals():
    static, coarse, order = inputs()
    for extra in ({'eval': {}}, {'setup_only': {}}, {'landmarks': {}}):
        with pytest.raises(bp.PlanRefusal, match='UNSUPPORTED_STATIC_MAP'):
            bp.freeze_public_sheet({**static, **extra}, coarse, order)
    with pytest.raises(bp.PlanRefusal, match='BAD_COARSE_ORDER_SHEET'):
        bp.freeze_public_sheet(static, {**coarse, 'private_pose': [1.275, .45, 1.5708]}, order)
    del static['regions']['zone_A']
    with pytest.raises(bp.PlanRefusal, match='UNKNOWN_TARGET_ZONE'):
        bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, order), order)


@pytest.mark.parametrize('error', ['outside_pickup', 'bad_bounds', 'bad_obstacle', 'bad_wall_profile'])
def test_invalid_geometry_is_an_explicit_refusal(error):
    static, coarse, order = inputs()
    if error == 'outside_pickup':
        coarse['beam_xyyaw'][0] = 5.
    elif error == 'bad_bounds':
        static['bounds_m'][0] = static['bounds_m'][1]
    elif error == 'bad_obstacle':
        static['obstacles'][0]['half_extents_m'][0] = -1.
    else:
        static['wall_profile'] = None
    with pytest.raises(bp.PlanRefusal):
        bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, order), order)


def test_s4_corridor_map_needs_no_door_alias_for_initial_geometry():
    static, coarse, order = inputs()
    static = json.loads((ROOT / 'maps/zones_final/zone_wide_corridor_final_v1.json').read_text())
    order['order_id'] = 'order-4'
    assert all(p['kind'] != 'door' for p in static['passages'])
    value = bp.make_initial_pose_plan(static, bp.freeze_public_sheet(static, coarse, order), order)
    assert value['verdict'] == 'STATIC_INITIAL_GEOMETRY_ONLY'
    assert value['refusals']['carry_route'].startswith('REQUIRES_')


def test_static_only_determinism_private_noninterference_and_no_io(monkeypatch):
    static, coarse, order = inputs()
    sheet = bp.freeze_public_sheet(static, coarse, order)
    frozen = copy.deepcopy((static, sheet, order))
    expected = bp.make_initial_pose_plan(static, sheet, order)
    scenario = json.loads((ROOT / 'configs/zone_study_scenarios_v2/s1_normal_mixed_v2.json').read_text())
    scenario['eval'] = {'setup': {'placements': 'arbitrary private changes'},
                        'hidden_events': [{'time': -1, 'partner': 'r3'}], 'contacts': True}
    def forbidden(*args, **kwargs):
        raise AssertionError('planner attempted I/O or private access')
    monkeypatch.setattr(Path, 'read_text', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr('builtins.open', forbidden)
    for condition in ('no_comm', 'peer_ko', 'leader_ko', 'structured'):
        # Condition/private data are intentionally not API inputs. Same public
        # order selected from changed scenario, without accessing its eval key.
        changed_order = next(o for o in scenario['orders'] if o['order_id'] == order['order_id'])
        assert bp.make_initial_pose_plan(static, sheet, changed_order) == expected
    assert (static, sheet, order) == frozen
    expected['roles']['end_neg']['station_xyyaw'][0] = 999
    assert bp.make_initial_pose_plan(static, sheet, order) != expected


def test_clean_import_has_no_physics_controller_model_or_p09_dependency():
    code = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in {'mujoco', 'torch', 'google', 'openai'}
            or any(v in fullname for v in ('zone_pair_executor', 'pair_stage_probe',
                   'zone_scenario_feasibility', 'zone_geometry_scene', 'run_m2_pair'))):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from harness.beam_initial_pose_plan import make_initial_pose_plan
'''
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True, capture_output=True, text=True)


def test_registered_in_normal_ci():
    from scripts import run_ci_tests as ci
    files = ci.collect_test_files(ROOT, ci.TEST_PATTERNS)
    shards = ci.shard_test_files(files, 8)
    ci.validate_shards(files, shards)
    assert sum(path == 'tests/test_beam_initial_pose_plan.py'
               for shard in shards for path in shard) == 1
