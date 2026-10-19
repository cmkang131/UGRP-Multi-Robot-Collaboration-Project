"""Synthetic eval-only fixtures for the e2ewarp evaluator; no simulator import.

Every case writes only ``evaluation-state.npz`` and ``eval-geometry.json`` and
calls the manifest entry the run invokes after controllers stopped. No physics,
no mujoco, no model call.
"""
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from harness.e2e_warp_components import require_components
from harness.e2ewarp_evaluator import (GEOMETRY_FILE, GEOMETRY_SCHEMA, SCHEMA, STATE_FILE, EvaluatorError,
                                       build_geometry, evaluate, sha256_file)

DT = .1
ROBOTS = ('r1', 'r2')
CARGO = 'beam_1'
HALF = {CARGO: [.30, .02]}
ZONE_B = {'center_m': [4.6, -2.1], 'half_extents_m': [.3, .7]}
GATE = {'id': 'door_1', 'axis': 'x', 'plane_m': 2.2, 'center_lateral_m': .05, 'half_width_m': .25}
SOURCE = 'a' * 40
ROWS_SHA = hashlib.sha256(b'localization rows').hexdigest()


def path(points, steps=10):
    """Linear interpolation through (x, y, yaw) waypoints."""
    out = []
    for start, end in zip(points, points[1:]):
        for index in range(steps):
            fraction = index / steps
            out.append(tuple(start[i] + (end[i] - start[i]) * fraction for i in range(3)))
    out.append(tuple(points[-1]))
    return out


def success_series():
    return {
        'r1': path([(.7, .05, 0.), (2.35, .05, 0.), (4.45, -1.8, 0.)]),
        'r2': path([(1.3, .12, 0.), (2.55, .12, 0.), (4.75, -2.4, 0.)]),
        CARGO: path([(1.0, .10, 0.), (2.5, .10, 0.), (4.6, -2.1, math.pi / 2)]),
    }


def outside_series():
    return {
        'r1': path([(.7, .05, 0.), (2.35, .05, 0.), (4.45, -.2, 0.)]),
        'r2': path([(1.3, .12, 0.), (2.55, .12, 0.), (4.75, -.2, 0.)]),
        CARGO: path([(1.0, .10, 0.), (2.5, .10, 0.), (4.6, 0., math.pi / 2)]),
    }


def aperture_series():
    return {
        'r1': path([(.7, 1.0, 0.), (2.35, 1.0, 0.), (4.45, -1.8, 0.)]),
        'r2': path([(1.3, 1.0, 0.), (2.55, 1.0, 0.), (4.75, -2.4, 0.)]),
        CARGO: path([(1.0, 1.0, 0.), (2.5, 1.0, 0.), (4.6, -2.1, math.pi / 2)]),
    }


def sideways_series():
    series = success_series()
    series[CARGO] = path([(1.0, .10, math.pi / 2), (2.5, .10, math.pi / 2),
                          (4.6, -2.1, math.pi / 2)])
    return series


def write_state(raw, series, *, dt=DT, worlds=1, extra=None):
    """Write a synthetic ``evaluation-state.npz`` and return qpos addresses."""
    names = list(series)
    lengths = {len(rows) for rows in series.values()}
    if len(lengths) != 1:
        raise ValueError('all entities need the same number of ticks')
    ticks = lengths.pop()
    qpos = np.zeros((ticks, worlds, 7 * len(names)), dtype=np.float64)
    addresses = {name: 7 * index for index, name in enumerate(names)}
    for index, name in enumerate(names):
        address = addresses[name]
        for tick, (x, y, yaw) in enumerate(series[name]):
            qpos[tick, :, address:address + 7] = [x, y, .02, math.cos(yaw / 2), 0., 0., math.sin(yaw / 2)]
    payload = dict(qpos=qpos, dt=dt, **(extra or {}))
    np.savez_compressed(raw / STATE_FILE, **payload)
    return addresses


def evidence(*, used=True, robots=ROBOTS, gt_fields=None):
    return {
        'source': 'localization.json',
        'rows_sha256': ROWS_SHA,
        'worlds': [{'world_id': world, 'robots': {
            robot: {'observations': 20 if used else 0,
                    'inserted_frames': 3 if used else 0,
                    'occupied_cells_max': 12 if used else 0,
                    'map_correction_active_rows': 20 if used else 0,
                    'own_gauge_pose_rows': 20 if used else 0,
                    'gt_fields_present': list(gt_fields or [])}
            for robot in robots}} for world in range(1)],
    }


def write_geometry(raw, addresses, *, initial=None, half=None, state_sha=None, source=SOURCE,
                   required=ROBOTS, base_requirement='all', cargo_ids=(CARGO,), require_cargo=True,
                   gate=GATE, self_map=None, policy=None, dt=DT, nworld=1):
    state_path = raw / STATE_FILE
    if state_sha is None:
        state_sha = sha256_file(state_path)
    cargo = [{'id': name, 'kind': 'long_beam', 'qpos_adr': addresses[name],
              'initial_xy_m': (initial or {name: [1.0, .10]})[name],
              'half_extents_m': (HALF if half is None else half).get(name),
              'initial_yaw_rad': 0.}
             for name in (CARGO,) if name in addresses]
    worlds = [{'world_id': world, 'robots': [{'id': robot, 'base_qpos_adr': addresses[robot]}
                                             for robot in ROBOTS], 'cargo': cargo}
              for world in range(nworld)]
    document = build_geometry(
        source_sha=source, evaluation_state_sha256=state_sha, dt=dt, worlds=worlds,
        zones={'B': ZONE_B}, gate=gate,
        mission={'destination_zone': 'B', 'base_requirement': base_requirement,
                 'required_robots': list(required), 'cargo_ids': list(cargo_ids),
                 'require_cargo': require_cargo, 'require_gate': gate is not None},
        self_map=evidence() if self_map is None else self_map, policy=policy)
    (raw / GEOMETRY_FILE).write_text(json.dumps(document, indent=2))
    return document


def success_case(raw, **geometry):
    addresses = write_state(raw, success_series())
    return write_geometry(raw, addresses, initial={CARGO: [1.0, .10]}, **geometry)


def timed(points, steps, ticks):
    trail = path(points, steps)
    assert len(trail) <= ticks
    return trail + [trail[-1]] * (ticks - len(trail))


def unattended_series():
    """Cargo moves across the door while both robots are still far west."""
    return {
        'r1': [(-.85, -1.35, 0.)] * 20 + path([(-.85, -1.35, 0.), (2.35, .05, 0.), (4.45, -1.8, 0.)]),
        'r2': [(-.85, -2.0, 0.)] * 20 + path([(-.85, -2.0, 0.), (2.55, .12, 0.), (4.75, -2.4, 0.)]),
        CARGO: timed([(1.0, .10, 0.), (2.5, .10, 0.), (4.6, -2.1, math.pi / 2)], 8, 41),
    }


def test_unattended_cargo_motion_is_not_transport(tmp_path):
    write_geometry(tmp_path, write_state(tmp_path, unattended_series()), initial={CARGO: [1.0, .10]})
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['physical_success'] is True, world['reasons']
    assert world['first_to_end_transport'] is False
    assert world['zone_check']['cargo'][0]['carried'] is False
    assert 'cargo_not_carried:' + CARGO in world['reasons']


def test_success_inside_zone_through_gate(tmp_path):
    success_case(tmp_path)
    outcome = evaluate(raw=tmp_path)
    world = outcome['worlds'][0]
    assert outcome['schema'] == SCHEMA
    assert outcome['source_sha'] == SOURCE
    assert outcome['evaluation_state_sha256'] == sha256_file(tmp_path / STATE_FILE)
    assert outcome['agent_claim_used'] is False and outcome['eval_only'] is True
    assert world['physical_success'] is True, world['reasons']
    assert world['first_to_end_transport'] is True, world['reasons']
    assert world['same_episode'] is True
    assert world['self_map_used'] is True
    assert world['zone_check']['bases_inside'] is True
    assert world['zone_check']['cargo'][0]['inside'] is True
    assert world['gate_check']['required'] is True and world['gate_check']['ok'] is True
    assert world['reasons'] == []
    assert [row['world_id'] for row in outcome['worlds']] == [0]


def test_outside_zone_never_success(tmp_path):
    write_geometry(tmp_path, write_state(tmp_path, outside_series()))
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['physical_success'] is False
    assert world['first_to_end_transport'] is False
    assert world['same_episode'] is True
    assert world['zone_check']['bases_inside'] is False
    assert world['zone_check']['cargo'][0]['inside'] is False
    assert 'base_outside_zone:r1' in world['reasons']
    assert 'cargo_outside_zone:' + CARGO in world['reasons']


def test_crossing_outside_door_aperture_is_rejected(tmp_path):
    write_geometry(tmp_path, write_state(tmp_path, aperture_series()),
                   initial={CARGO: [1.0, 1.0]})
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['physical_success'] is False
    assert world['first_to_end_transport'] is False
    assert world['gate_check']['ok'] is False
    assert any(reason.startswith('gate_outside_aperture:') for reason in world['reasons'])
    assert any(reason.startswith('cargo_gate_outside_aperture:') for reason in world['reasons'])


def test_sideways_cargo_footprint_does_not_fit_aperture(tmp_path):
    write_geometry(tmp_path, write_state(tmp_path, sideways_series()))
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['zone_check']['cargo'][0]['inside'] is True
    assert world['gate_check']['ok'] is False
    assert world['physical_success'] is False
    assert any(reason.startswith('cargo_gate_outside_aperture:') for reason in world['reasons'])


def test_jump_between_ticks_is_not_one_episode(tmp_path):
    series = success_series()
    series['r1'][10] = (series['r1'][10][0] + 2.0, series['r1'][10][1], 0.)
    write_geometry(tmp_path, write_state(tmp_path, series), initial={CARGO: [1.0, .10]})
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['same_episode'] is False
    assert world['physical_success'] is False
    assert world['first_to_end_transport'] is False
    assert 'episode_not_contiguous' in world['reasons']
    assert world['continuity']['teleports'][0]['entity'] == 'r1'


def test_missing_state_file_is_an_error(tmp_path):
    success_case(tmp_path)
    (tmp_path / STATE_FILE).unlink()
    with pytest.raises(EvaluatorError, match='EVALUATOR_INPUT_MISSING'):
        evaluate(raw=tmp_path)


def test_missing_geometry_file_is_an_error(tmp_path):
    success_case(tmp_path)
    (tmp_path / GEOMETRY_FILE).unlink()
    with pytest.raises(EvaluatorError, match='EVALUATOR_INPUT_MISSING'):
        evaluate(raw=tmp_path)


def test_corrupt_state_file_is_an_error(tmp_path):
    success_case(tmp_path)
    (tmp_path / STATE_FILE).write_bytes(b'not an npz archive')
    with pytest.raises(EvaluatorError, match='EVALUATOR_INPUT_CORRUPT'):
        evaluate(raw=tmp_path)


def test_corrupt_geometry_file_is_an_error(tmp_path):
    success_case(tmp_path)
    (tmp_path / GEOMETRY_FILE).write_text('{not json')
    with pytest.raises(EvaluatorError, match='EVALUATOR_INPUT_CORRUPT'):
        evaluate(raw=tmp_path)


def test_state_sha_mismatch_is_an_error(tmp_path):
    success_case(tmp_path)
    document = json.loads((tmp_path / GEOMETRY_FILE).read_text())
    document['evaluation_state_sha256'] = '0' * 64
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    with pytest.raises(EvaluatorError, match='EVALUATOR_STATE_SHA_MISMATCH'):
        evaluate(raw=tmp_path)


def test_invalid_source_sha_is_an_error(tmp_path):
    success_case(tmp_path)
    document = json.loads((tmp_path / GEOMETRY_FILE).read_text())
    document['source_sha'] = 'z' * 40
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    with pytest.raises(EvaluatorError, match='EVALUATOR_SOURCE_SHA_INVALID'):
        evaluate(raw=tmp_path)


def test_world_set_mismatch_is_an_error(tmp_path):
    addresses = write_state(tmp_path, success_series(), worlds=2)
    write_geometry(tmp_path, addresses)
    with pytest.raises(EvaluatorError, match='EVALUATOR_WORLD_SET_MISMATCH'):
        evaluate(raw=tmp_path)


def test_state_nan_is_an_error(tmp_path):
    addresses = write_state(tmp_path, success_series())
    with np.load(tmp_path / STATE_FILE, allow_pickle=False) as data:
        qpos, dt = data['qpos'], data['dt']
    qpos[3, 0, addresses['r1']] = np.nan
    np.savez_compressed(tmp_path / STATE_FILE, qpos=qpos, dt=dt)
    write_geometry(tmp_path, addresses)
    with pytest.raises(EvaluatorError, match='EVALUATOR_STATE_NOT_FINITE'):
        evaluate(raw=tmp_path)


def test_agent_claim_files_are_ignored(tmp_path):
    write_geometry(tmp_path, write_state(tmp_path, outside_series()))
    (tmp_path / 'result.json').write_text(json.dumps({'schema': 'ugrp.e2ewarp.result.v1',
                                                      'E2E_success': True, 'status': 'OWN_COMPLETION_CLAIM'}))
    (tmp_path / 'mission-events.json').write_text('not even json; the evaluator must not read claims')
    (tmp_path / 'physical-evaluation.json').write_text(json.dumps({'physical_success': True,
                                                                   'first_to_end_transport': True,
                                                                   'same_episode': True, 'self_map_used': True}))
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['physical_success'] is False
    assert world['first_to_end_transport'] is False
    assert world['reasons']


def test_extra_npz_claims_are_ignored(tmp_path):
    addresses = write_state(tmp_path, outside_series(), extra={'claimed_success': True, 'E2E_success': True})
    write_geometry(tmp_path, addresses)
    assert evaluate(raw=tmp_path)['worlds'][0]['physical_success'] is False


def test_self_map_evidence_is_required(tmp_path):
    success_case(tmp_path)
    document = json.loads((tmp_path / GEOMETRY_FILE).read_text())
    del document['self_map']
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    with pytest.raises(EvaluatorError, match='EVALUATOR_GEOMETRY_INVALID'):
        evaluate(raw=tmp_path)


def test_missing_self_map_robot_evidence_is_an_error(tmp_path):
    success_case(tmp_path)
    document = json.loads((tmp_path / GEOMETRY_FILE).read_text())
    del document['self_map']['worlds'][0]['robots']['r2']
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    with pytest.raises(EvaluatorError, match='EVALUATOR_SELF_MAP_EVIDENCE_MISSING'):
        evaluate(raw=tmp_path)


def test_zero_self_map_evidence_is_not_success(tmp_path):
    success_case(tmp_path)
    document = json.loads((tmp_path / GEOMETRY_FILE).read_text())
    document['self_map'] = evidence(used=False)
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['physical_success'] is True
    assert world['self_map_used'] is False
    assert 'self_map_not_used' in world['reasons']


def test_ground_truth_in_self_map_ledger_fails_closed(tmp_path):
    success_case(tmp_path)
    document = json.loads((tmp_path / GEOMETRY_FILE).read_text())
    document['self_map']['worlds'][0]['robots']['r1']['gt_fields_present'] = ['gt_pose']
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['self_map_used'] is False


def test_any_base_mode_allows_one_arriving_robot(tmp_path):
    series = success_series()
    series['r2'] = [(1.3, .12, 0.)] * len(series['r2'])
    write_geometry(tmp_path, write_state(tmp_path, series), initial={CARGO: [1.0, .10]},
                   base_requirement='any')
    world = evaluate(raw=tmp_path)['worlds'][0]
    assert world['physical_success'] is True, world['reasons']
    assert world['zone_check']['robots'][1]['inside'] is False
    assert world['zone_check']['bases_inside'] is True


def test_factory_entry_equals_evaluate_and_rejects_missing_raw(tmp_path):
    with pytest.raises(EvaluatorError, match='EVALUATOR_INPUT_MISSING'):
        evaluate(raw=tmp_path / 'does-not-exist')


@pytest.mark.parametrize('ready,entry,sha,owner,evidence_text,expected', [
    (None, 'ev:factory', 'valid', None, None, 'DEPENDENCY_WAIT:evaluator_factory'),
    ('yes', 'ev:factory', 'valid', 'owner', 'evidence', 'DEPENDENCY_WAIT:evaluator_factory'),
    (True, 'ev:factory', 'stale', 'owner', 'evidence', 'DEPENDENCY_WAIT:hash-bound evaluator_factory'),
    (True, 'missing:factory', 'valid', 'owner', 'evidence', 'DEPENDENCY_WAIT:hash-bound evaluator_factory'),
])
def test_manifest_evaluator_entry_must_be_ready_and_hash_bound(tmp_path, ready, entry, sha, owner,
                                                              evidence_text, expected):
    (tmp_path / 'ev.py').write_text('def factory(**kwargs):\n    return None\n')
    files = {}
    for name, factory_name in (('nav', 'navigation_factory'), ('rel', 'release_factory')):
        (tmp_path / (name + '.py')).write_text('def factory(**kwargs):\n    return None\n')
        files[factory_name] = hashlib.sha256((tmp_path / (name + '.py')).read_bytes()).hexdigest()
    ev_sha = hashlib.sha256((tmp_path / 'ev.py').read_bytes()).hexdigest()
    manifest = {
        'navigation': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'loaded_camera_fk': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'static_map_registration': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'release_relocalization': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'selfmap_map_correction': {'ready': True, 'owner': 'owner', 'evidence': 'evidence',
                                   'mode': 'on', 'own_and_static_map': True, 'spawn_anchor_used': False},
        'navigation_factory': {'entry': 'nav:factory', 'sha256': files['navigation_factory']},
        'release_factory': {'entry': 'rel:factory', 'sha256': files['release_factory']},
        'evaluator_factory': {'entry': entry,
                              'sha256': ev_sha if sha == 'valid' else '0' * 64,
                              **({'ready': True} if ready is True else
                                 ({'ready': ready} if ready is not None else {})),
                              **({'owner': owner} if owner else {}),
                              **({'evidence': evidence_text} if evidence_text else {})},
        'ACT': {},
    }
    path = tmp_path / 'components.json'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=expected):
        require_components(path, tmp_path)


def test_manifest_ready_evaluator_reaches_the_next_gate(tmp_path):
    for name in ('nav', 'rel', 'ev'):
        (tmp_path / (name + '.py')).write_text('def factory(**kwargs):\n    return None\n')
    manifest = {
        'navigation': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'loaded_camera_fk': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'static_map_registration': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'release_relocalization': {'ready': True, 'owner': 'owner', 'evidence': 'evidence'},
        'selfmap_map_correction': {'ready': True, 'owner': 'owner', 'evidence': 'evidence',
                                   'mode': 'on', 'own_and_static_map': True, 'spawn_anchor_used': False},
        'navigation_factory': {'entry': 'nav:factory',
                               'sha256': hashlib.sha256((tmp_path / 'nav.py').read_bytes()).hexdigest()},
        'release_factory': {'entry': 'rel:factory',
                            'sha256': hashlib.sha256((tmp_path / 'rel.py').read_bytes()).hexdigest()},
        'evaluator_factory': {'entry': 'ev:factory', 'ready': True, 'owner': 'owner', 'evidence': 'evidence',
                              'sha256': hashlib.sha256((tmp_path / 'ev.py').read_bytes()).hexdigest()},
        'ACT': {},
    }
    path = tmp_path / 'components.json'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='selected native ACT'):
        require_components(path, tmp_path)


def test_pending_manifest_hash_binds_this_evaluator():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'experiments/2026-10-17-e2ewarp/components.pending.json').read_text())
    record = manifest['evaluator_factory']
    assert record['ready'] is True
    assert record['entry'] == 'harness.e2ewarp_evaluator:evaluator_factory'
    assert record['sha256'] == sha256_file(root / 'harness/e2ewarp_evaluator.py')


def test_module_import_does_not_load_simulator():
    code = ('import sys; import harness.e2ewarp_evaluator; '
            'assert "mujoco" not in sys.modules; print("ok")')
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'


class _Body:
    def __init__(self, name, index):
        self.name, self.id = name, index


class _Model:
    """Only the integer qpos-address surface the run's eval sink uses."""

    def __init__(self):
        self.nbody = 4
        self._bodies = [_Body('world', 0), _Body('r1__robot', 1),
                        _Body('cargo_beam_1', 2), _Body('cargo_red_1', 3)]
        self.body_jntadr = [-1, 0, 1, 2]
        self.jnt_type = [0, 0, 0]
        self.jnt_qposadr = [0, 7, 14]

    def body(self, key):
        if isinstance(key, int):
            return self._bodies[key]
        return next(body for body in self._bodies if body.name == key)


class _Scene:
    config = {
        'static_map': {
            'regions': {'pickup': {'center_m': [0.7, -0.85], 'half_extents_m': [1.15, 1.95]},
                        'zone_B': {'center_m': [4.6, -2.1], 'half_extents_m': [.3, .7]}},
            'passages': [{'id': 'door_1', 'kind': 'door', 'axis': 'x', 'center_m': [2.2, .05],
                          'half_extents_m': [.025, .25], 'width_m': .5}],
        },
        'setup_only': {'objects': {'red_1': {'kind': 'red', 'position_m': [1.0, -.85, .016],
                                             'half_extents_m': [.017, .02, .016]}}},
        'cargo_set': {'items': [{'item_id': 'beam_1', 'kind': 'long_beam',
                                 'pose': [1.2, .3, 1.5708]}]},
    }
    scene = {'params': {'scenario_setup': {
        'orders': [{'order_id': 'order-2', 'kind': 'red', 'destination_zone': 'B'},
                   {'order_id': 'order-5', 'kind': 'long_beam', 'destination_zone': 'A'}],
        'eval': {'setup': {'placements': [{'item_id': 'red_1', 'order_id': 'order-2'}]}},
    }}}


def test_run_eval_sink_builds_the_evaluator_contract(tmp_path):
    from scripts.run_e2e_warp import evaluation_geometry
    initial = np.zeros(21)
    initial[0:7] = [.7, .05, .02, 1., 0., 0., 0.]
    initial[7:14] = [1.2, .3, .02, math.cos(1.5708 / 2), 0., 0., math.sin(1.5708 / 2)]
    initial[14:21] = [1.0, -.85, .016, 1., 0., 0., 0.]
    contexts = [{'world': type('World', (), {'model': _Model()})(), 'scene': _Scene(),
                 'ports': {'r1': object()}}]
    rows = [{'world': 0, 'robot': 'r1', 'sim_s': 0., 'self_map': {'inserted': True, 'occupied_cells': 5},
             'own_gauge_pose': [0., 0., 0.]}]
    (tmp_path / STATE_FILE).write_bytes(b'state')
    document = evaluation_geometry(contexts, [initial], rows, 'b' * 40,
                                   sha256_file(tmp_path / STATE_FILE), .1)
    assert document['schema'] == GEOMETRY_SCHEMA
    assert document['mission']['destination_zone'] == 'B'
    assert document['mission']['cargo_ids'] == ['red_1']
    assert document['gate']['id'] == 'door_1'
    assert document['worlds'][0]['robots'][0]['base_qpos_adr'] == 0
    cargo = {row['id']: row for row in document['worlds'][0]['cargo']}
    assert cargo['beam_1']['initial_xy_m'] == [1.2, .3]
    assert cargo['beam_1']['half_extents_m'] == [.30, .02]
    assert cargo['red_1']['half_extents_m'] == [.017, .02]
    assert document['self_map']['worlds'][0]['robots']['r1']['inserted_frames'] == 1
    # The built document validates as evaluator input (state is still a dummy).
    (tmp_path / GEOMETRY_FILE).write_text(json.dumps(document))
    with pytest.raises(EvaluatorError, match='EVALUATOR_INPUT_CORRUPT'):
        evaluate(raw=tmp_path)

