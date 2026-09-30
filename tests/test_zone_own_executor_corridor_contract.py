"""T10a static/fake only; no world, renderer, physics, or model calls.

Filename deliberately joins the existing test_zone_own_executor*.py CI glob.
Synthetic map/path proposals are not original study placements or successes.
"""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from harness.zone_corridor_contract import CorridorContract, UnsupportedCorridor, create_own_executor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def static():
    # Spacious explicit dev geometry; the real bay is tested separately below.
    return {'robot_model': 'masterpi_v3', 'bounds_m': [-4., 5., -3., 3.], 'obstacles': [],
            'passages': [{'id': 'corridor_1', 'kind': 'corridor', 'axis': 'x',
                          'center_m': [0., 0.], 'half_extents_m': [1., .25], 'width_m': .5},
                         {'id': 'bay_1', 'kind': 'passing_bay', 'axis': 'y', 'opens_to': 'corridor_1',
                          'center_m': [0., -1.], 'half_extents_m': [.8, .5]}]}


@pytest.fixture
def contract(static):
    return CorridorContract(static)


def solo(contract, robot='r3'):
    return contract.formation('cyan', {'west': robot})


def pair(contract):
    return contract.formation('long_beam', {'end_neg': 'r1', 'end_pos': 'r2'})


def test_corridor_only_entry_never_requires_a_door(contract):
    f = solo(contract)
    path = [(-2., 0., 0.), (2., 0., 0.)]
    report = contract.check(f, forward_path=path, reverse_path=path[::-1])
    assert report['disc_passage']['static_ok'] is True
    assert all(v['static_ok'] is True for v in report['pose_paths'].values())
    assert report['simultaneous_occupancy']['status'] == 'unsupported'
    assert report['item_rotation']['status'] == 'unsupported'
    assert report['runtime_support'] == 'unsupported_T10b_required'
    assert report['physics_verified'] is False and report['sim_cap_s'] == 0


def test_legacy_factory_refuses_before_pose_provider_or_skill_construction(static):
    def forbidden(*args, **kwargs):
        pytest.fail('runtime must not be constructed on corridor-only map')
    with pytest.raises(UnsupportedCorridor, match='CORRIDOR_RUNTIME_UNSUPPORTED'):
        create_own_executor('r1', static, {}, {}, skill_factory=forbidden)


def test_legacy_door_factory_preserves_arguments(monkeypatch):
    from harness import zone_own_executor
    calls = []
    monkeypatch.setattr(zone_own_executor, 'ZoneOwnExecutor', lambda *a, **kw: calls.append((a, kw)))
    static = {'passages': [{'kind': 'door'}]}
    create_own_executor('r2', static, {'param': 1}, {'orders': []}, mode='m1')
    assert calls == [(('r2', static, {'param': 1}, {'orders': []}), {'mode': 'm1'})]


@pytest.fixture
def managed_study(tmp_path, monkeypatch):
    """Real CLI/catalog dispatch, fake files; any launch is a test failure."""
    from scripts import sim_cli
    from sim import workflow_manager as wm
    row = next(r for r in json.loads((ROOT / wm.CATALOG).read_text())['workflows']
               if r['id'] == 'zone-study-integration-run')
    (tmp_path / 'configs').mkdir()
    (tmp_path / wm.CATALOG).write_text(json.dumps({
        'schema': 'ugrp.local_workflow_catalog.v1', 'workflows': [row]}))
    entry = tmp_path / row['entry']
    entry.parent.mkdir()
    entry.write_text('raise AssertionError("legacy runtime must not start")\n')
    (tmp_path / 'maps/zones').mkdir(parents=True)
    (tmp_path / 'maps/zones_final').mkdir()
    (tmp_path / 'scenario.json').write_text(json.dumps({'map_id': 'selected'}))
    pre = {'schema': 'ugrp.zone_study_integration_prereg.v1', 'episodes': [
        {'episode_id': 'unselected', 'map': 'missing', 'scenario': 'missing.json'},
        {'episode_id': 'chosen', 'map': 'selected', 'scenario': 'scenario.json'}]}
    (tmp_path / 'prereg.json').write_text(json.dumps(pre))
    monkeypatch.setattr(sim_cli, 'ROOT', tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail('admission must precede records, subprocesses, host and physics')

    monkeypatch.setattr(wm, '_new_record', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    return tmp_path, pre


@pytest.mark.parametrize('action', ['plan', 'run'])
@pytest.mark.parametrize('condition', ['no_comm', 'peer_ko', 'leader_ko', 'structured'])
@pytest.mark.parametrize('directory', ['zones', 'zones_final'])
def test_managed_corridor_entry_refuses_before_runtime(managed_study, capsys, action, condition, directory):
    from scripts import sim_cli
    root, _ = managed_study
    # A neutral file name proves admission checks passages, not an ID substring.
    static = json.loads((ROOT / 'maps/zones_final/zone_wide_corridor_final_v1.json').read_text())
    static['map_id'] = 'selected'
    (root / f'maps/{directory}/selected.json').write_text(json.dumps(static))
    with pytest.raises(SystemExit) as error:
        sim_cli.main(['workflow', action, 'zone-study-integration-run', '--',
                      '--prereg=prereg.json', '--episode=chosen', f'--condition={condition}',
                      '--output=never-created', '--dev-horizon-s=1'])
    assert error.value.code == 2
    assert 'CORRIDOR_RUNTIME_UNSUPPORTED' in capsys.readouterr().err
    assert not (root / 'outputs').exists() and not (root / 'never-created').exists()


def test_managed_door_entry_preserves_selected_runner_and_arguments(managed_study):
    from sim import workflow_manager as wm
    root, _ = managed_study
    static = json.loads((ROOT / 'maps/zones/zone_wide_door_geometry_v2.json').read_text())
    static['map_id'] = 'selected'
    (root / 'maps/zones/selected.json').write_text(json.dumps(static))
    args = ['--prereg', 'prereg.json', '--episode', 'chosen', '--condition', 'no_comm',
            '--output', 'never-created']
    result = wm.plan(root, 'zone-study-integration-run', args)
    assert result['command'] == [sys.executable, '-m', 'scripts.run_zone_study_integration', *args]
    assert result['execution_started'] is False
    assert not (root / 'outputs').exists()


@pytest.mark.parametrize('fault', ['unknown_episode', 'duplicate_episode', 'map_mismatch',
                                  'missing_map', 'ambiguous_map', 'empty_passages'])
def test_managed_study_selection_fails_closed(managed_study, fault):
    from sim import workflow_manager as wm
    root, pre = managed_study
    static = {'map_id': 'selected', 'passages': [{'kind': 'door'}]}
    if fault == 'empty_passages':
        static['passages'] = []
    if fault != 'missing_map':
        (root / 'maps/zones/selected.json').write_text(json.dumps(static))
    if fault == 'ambiguous_map':
        (root / 'maps/zones_final/selected.json').write_text(json.dumps(static))
    if fault == 'unknown_episode':
        pre['episodes'].pop()
    if fault == 'duplicate_episode':
        pre['episodes'].append(copy.deepcopy(pre['episodes'][-1]))
    if fault == 'map_mismatch':
        (root / 'scenario.json').write_text(json.dumps({'map_id': 'different'}))
    (root / 'prereg.json').write_text(json.dumps(pre))
    with pytest.raises(ValueError):
        wm.run_workflow(root, 'zone-study-integration-run',
                        ['--prereg', 'prereg.json', '--episode', 'chosen', '--condition', 'no_comm'])
    assert not (root / 'outputs').exists()


def test_missing_corridor_missing_bay_and_unknown_axis_are_explicit(static):
    with pytest.raises(UnsupportedCorridor, match='CORRIDOR_NOT_FOUND'):
        CorridorContract({**static, 'passages': []})
    static['passages'] = static['passages'][:1]
    c = CorridorContract(static)
    assert c.check(solo(c), bay_pose=(0., -1., 0.))['bay']['stop']['status'] == 'unsupported'
    static['passages'][0]['axis'] = 'y'
    with pytest.raises(UnsupportedCorridor, match='ONLY_EAST_WEST'):
        CorridorContract(static)


@pytest.mark.parametrize('fault', ['model', 'width', 'duplicate', 'bay_link', 'nan', 'negative_extent'])
def test_malformed_static_geometry_fails_closed(static, fault):
    if fault == 'model': static.pop('robot_model')
    if fault == 'width': static['passages'][0]['width_m'] = 1.
    if fault == 'duplicate': static['passages'].append(copy.deepcopy(static['passages'][0]))
    if fault == 'bay_link': static['passages'][1]['opens_to'] = 'other'
    if fault == 'nan': static['bounds_m'][0] = math.nan
    if fault == 'negative_extent': static['passages'][1]['half_extents_m'][0] = -.1
    with pytest.raises(ValueError):
        CorridorContract(static)


def test_full_catalogue_roles_required(contract):
    with pytest.raises(ValueError, match='all catalogue'):
        contract.formation('long_beam', {'end_neg': 'r1'})
    with pytest.raises(ValueError, match='distinct'):
        contract.formation('long_beam', {'end_neg': 'r1', 'end_pos': 'r1'})
    with pytest.raises(ValueError, match='unknown item kind'):
        contract.formation('unknown', {'west': 'r1'})


def test_mouth_touch_or_wrong_direction_is_not_full_crossing(contract):
    f = solo(contract)
    mouth = [(-2., 0., 0.), (-1., 0., 0.)]
    assert contract.passage_path(f, mouth, 'west_to_east')['full_crossing'] is False
    path = [(2., 0., 0.), (-2., 0., 0.)]
    assert contract.passage_path(f, path, 'east_to_west')['static_ok'] is True
    assert contract.passage_path(f, path, 'west_to_east')['static_ok'] is False
    around = [(-2., 1., 0.), (2., 1., 0.)]
    assert contract.passage_path(f, around, 'west_to_east')['full_crossing'] is False


def test_original_final_bay_does_not_automatically_fit_pair():
    data = json.loads((ROOT / 'maps/zones_final/zone_wide_corridor_final_v1.json').read_text())
    c = CorridorContract(data, robot_model='masterpi_v3')
    f = pair(c)
    # Test length and width, not a point centre or cargo alone.
    for yaw in (0., math.pi / 2, math.pi / 4):
        result = c.bay_stop(f, (3.1, .625, yaw))
        assert result['static_ok'] is False and result['boundary_gap_m'] < 0
    assert c.check(f)['bay']['stop']['status'] == 'unsupported'


def test_final_map_explicit_solo_refuge_and_pair_crossing_are_only_static():
    data = json.loads((ROOT / 'maps/zones_final/zone_wide_corridor_final_v1.json').read_text())
    c = CorridorContract(data, robot_model='masterpi_v3')
    p, s = pair(c), solo(c)
    stop = (3.2, .625, 0.)  # authored proposal, not setup or live GT
    escape = [(3.2, 1.175, 0.), stop]
    crossing = [(1.5, 1.175, 0.), (4.6, 1.175, 0.)]
    assert c.bay_stop(s, stop)['static_ok'] is True
    assert c.bay_motion(s, escape, stop)['static_ok'] is True
    assert c.bay_motion(s, escape[::-1], stop, reentry=True)['static_ok'] is True
    result = c.check(p, forward_path=crossing, reverse_path=crossing[::-1],
                     placements=[(p, (3.0625, 1.175, 0.)), (s, stop)])
    assert all(v['static_ok'] is True for v in result['pose_paths'].values())
    assert result['simultaneous_occupancy']['static_ok'] is True
    assert result['simultaneous_occupancy']['simultaneous_passing'] == 'unsupported'
    assert result['physics_verified'] is False


def test_terrain_and_explicit_model_mismatch_are_unsupported(static):
    with pytest.raises(UnsupportedCorridor, match='MASTERPI_V3'):
        CorridorContract(static, robot_model='masterpi_v2')
    static['terrain'] = [{'kind': 'step'}]
    with pytest.raises(UnsupportedCorridor, match='TERRAIN'):
        CorridorContract(static)


def test_bay_boundary_exact_required_clearance_and_just_outside(static):
    c = CorridorContract(static, clearance_m=0.)
    f = solo(c)
    lo, hi, bottom, top = c._extent((0., -1., 0.), f.parts)
    static['passages'][1]['center_m'] = [(lo + hi) / 2, (bottom + top) / 2]
    static['passages'][1]['half_extents_m'] = [(hi - lo) / 2 + .011, (top - bottom) / 2 + .011]
    c = CorridorContract(static, clearance_m=.01)
    assert c.bay_stop(f, (0., -1., 0.))['static_ok'] is True
    assert c.bay_stop(f, (.002, -1., 0.))['static_ok'] is False
    assert c.bay_stop(f, (0., -1.002, 0.))['static_ok'] is False


def test_empty_bay_rectangle_does_not_override_internal_wall(static):
    static['obstacles'] = [{'center_m': [0., -1.], 'half_extents_m': [.03, .03]}]
    c = CorridorContract(static)
    assert c.bay_stop(solo(c), (0., -1., 0.))['static_ok'] is False


def test_stop_evacuation_and_reentry_are_separate_connected_sweeps(contract):
    f, stop = solo(contract), (0., -1., 0.)
    path = [(0., 0., 0.), stop]
    result = contract.check(f, bay_pose=stop, evacuation_path=path, reentry_path=path[::-1])
    assert all(result['bay'][k]['static_ok'] is True for k in ('stop', 'evacuation', 'reentry'))
    wrong = [(0., -.9, 0.), (0., 0., 0.)]
    assert contract.check(f, bay_pose=stop, reentry_path=wrong)['bay']['reentry']['static_ok'] is False
    assert contract.check(f, bay_pose=stop)['bay']['evacuation']['status'] == 'unsupported'


def test_bay_entry_sweep_fails_even_when_stop_fits(static):
    static['obstacles'] = [{'center_m': [0., -.5], 'half_extents_m': [.8, .01]}]
    c = CorridorContract(static)
    f, stop = solo(c), (0., -1., 0.)
    assert c.bay_stop(f, stop)['static_ok'] is True
    assert c.bay_motion(f, [(0., 0., 0.), stop], stop)['static_ok'] is False


def test_pair_width_length_and_yaw_sweep_distinct_from_disc(static):
    # Pair endpoints at yaw 0 and pi clear; a 180-degree turn sweeps the walls.
    static['obstacles'] = [{'center_m': [0., y], 'half_extents_m': [3., .05]} for y in (-.4, .4)]
    c = CorridorContract(static)
    f = pair(c)
    assert c._clear((0., 0., 0.), f.parts)
    assert c._clear((0., 0., math.pi), f.parts)
    report = c.check(f, rotation_path=[(0., 0., 0.), (0., 0., math.pi)],
                     forward_path=[(-2., 0., 0.), (2., 0., 0.)],
                     reverse_path=[(2., 0., math.pi / 2), (-2., 0., math.pi / 2)])
    assert report['disc_passage']['static_ok'] is True
    assert report['pose_paths']['west_to_east']['static_ok'] is True
    assert report['pose_paths']['east_to_west']['static_ok'] is False
    assert report['item_rotation']['formation_swept_clear'] is False


def test_item_rotation_clear_does_not_prove_carriers_clear(static):
    static['obstacles'] = [{'center_m': [0., .52], 'half_extents_m': [.01, .01]}]
    c = CorridorContract(static)
    value = c.item_rotation(pair(c), [(0., 0., 0.), (0., 0., math.pi)])
    assert value['static_ok'] is True
    assert value['formation_swept_clear'] is False


def test_bay_yaw_endpoints_fit_but_sweep_does_not(contract):
    f = pair(contract)
    path = [(0., -1., 0.), (0., -1., math.pi)]
    assert all(contract.bay_stop(f, p)['static_ok'] for p in path)
    assert contract.bay_rotation(f, path)['static_ok'] is False


def test_narrow_corridor_metadata_rejects_wide_disc_even_without_walls(contract):
    assert contract.check(solo(contract), disc_radius_m=.26)['disc_passage']['static_ok'] is False


def test_thin_wall_between_waypoints_is_not_skipped(static):
    static['obstacles'] = [{'center_m': [.12345, 0.], 'half_extents_m': [.00001, .4]}]
    c = CorridorContract(static)
    assert c.passage_path(solo(c), [(-2., 0., 0.), (2., 0., 0.)], 'west_to_east')['static_ok'] is False


def test_pair_plus_solo_three_robots_not_two_pairs_four(contract):
    p, s = pair(contract), solo(contract)
    separated = contract.simultaneous_occupancy([(p, (0., 0., 0.)), (s, (0., -1., 0.))])
    assert separated['static_ok'] is True and separated['robot_count'] == 3
    assert separated['simultaneous_passing'] == 'unsupported'
    collide = contract.simultaneous_occupancy([(p, (0., 0., 0.)), (s, (0., 0., 0.))])
    assert collide['static_ok'] is False
    two_pairs = contract.simultaneous_occupancy([(p, (0., 0., 0.)), (p, (0., -1., 0.))])
    assert two_pairs['status'] == 'unsupported' and two_pairs['robot_count'] == 4
    assert 'TEAM_SIZE_EXCEEDED' in two_pairs['reason']
    reused = contract.simultaneous_occupancy([(p, (0., 0., 0.)), (solo(contract, 'r1'), (0., -1., 0.))])
    assert reused['reason'] == 'ROBOT_ASSIGNED_TWICE'


def test_private_mutation_and_four_conditions_cannot_change_geometry(static):
    before = copy.deepcopy(static)
    kwargs = {'forward_path': [(-2., 0., 0.), (2., 0., 0.)], 'bay_pose': (0., -1., 0.)}
    c = CorridorContract(static)
    expected = c.check(pair(c), **kwargs)
    for mode in ('no_comm', 'peer_ko', 'leader_ko', 'structured'):
        private = copy.deepcopy(static)
        private.update(eval={'setup': {'placements': [{'pose_m': [999., -999., 2.]}]},
                             'events': [{'at_sim_s': 1e6}]}, current_truth={'contact': True},
                       communication_mode=mode, inventory={'secret': 'not read'})
        changed = CorridorContract(private)
        assert changed.check(pair(changed), **kwargs) == expected
    assert static == before


@pytest.mark.parametrize('poses', [[], [(0., 0., 0.)], [(0., 0., math.nan), (1., 0., 0.)],
                                 [(True, 0., 0.), (1., 0., 0.)]])
def test_bad_path_is_not_a_static_pass(contract, poses):
    with pytest.raises(ValueError):
        contract.passage_path(solo(contract), poses, 'west_to_east')


def test_import_and_checks_do_not_load_simulator_model_or_p09():
    code = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch', 'google', 'openai') or fullname == 'harness.zone_scenario_feasibility':
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from harness.zone_corridor_contract import CorridorContract
import json
data = json.load(open('maps/zones_final/zone_wide_corridor_final_v1.json'))
c = CorridorContract(data, robot_model='masterpi_v3')
c.check(c.formation('long_beam', {'end_neg': 'r1', 'end_pos': 'r2'}))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
