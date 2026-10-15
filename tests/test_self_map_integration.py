"""Offline contracts: synthetic own observations, no simulator or rendering."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import self_map_integration as sm
from harness.natural_floor_slam import Observation


def fixture_mapper(monkeypatch):
    mapper = sm.make_mapper(robot_id='r1', options=sm.Options(self_map_integration=sm.OPTION))
    mapper.command(dict(t=0., kind='initial_servo_command', pulses={1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}))
    rng = np.random.default_rng(42)
    points = rng.uniform([.2, -.6], [1., .6], (25, 2))
    descriptors = rng.integers(0, 256, (25, 32), dtype=np.uint8)
    state = {'pose': np.zeros(3), 'blank': False}

    def extract(rgb, servo, *, frame_id, t, sha256):
        p = state['pose']
        c, s = np.cos(p[2]), np.sin(p[2])
        body = (points-p[:2])@np.array([[c, -s], [s, c]])
        return Observation(frame_id, t, body[:0] if state['blank'] else body,
                           descriptors[:0] if state['blank'] else descriptors, sha256)

    monkeypatch.setattr(sm, 'extract', extract)
    from harness import active_wall_vision
    floor = [[x, y] for x in np.arange(-.4, .81, .1) for y in np.arange(-.4, .41, .1)]
    monkeypatch.setattr(active_wall_vision, 'observe', lambda *a, **k: dict(
        camera=[0., 0.], segments=[[[1., -.6], [1., .6]]], floor_xy=floor))
    mapper.zones = SimpleNamespace(tracks=[], observe=lambda *a, **k: ([], None, {}), snapshot=lambda: {})
    return mapper, state


def receive(mapper, frame):
    return mapper.receive(robot_id='r1', frame_id=frame, t=float(frame),
                          rgb=np.zeros((480, 640, 3), np.uint8))


def test_off_preserves_identity_without_constructing_dependency(monkeypatch):
    monkeypatch.setattr(sm, 'SelfMapIntegration', lambda **k: pytest.fail('off constructed mapper'))
    legacy = {'path': [1, 2], 'status': 'unchanged'}
    before = json.dumps(legacy).encode()
    assert sm.make_mapper(legacy, robot_id='r1') is legacy
    assert json.dumps(legacy).encode() == before
    with pytest.raises(ValueError):
        sm.Options(self_map_integration='unknown')


def test_upstream_dependency_is_verbatim():
    root = Path(__file__).resolve().parents[1]
    provenance = json.loads((root/'experiments/2026-10-15-self-map/dependency.json').read_text())
    assert provenance['source_sha'] == '69eb200ae4a80d53cd7adea9846832426ffef674'
    for path, expected in provenance['files'].items():
        assert hashlib.sha256((root/path).read_bytes()).hexdigest() == expected


def test_estimated_pose_transforms_occupancy_and_preserves_unknown():
    grid = sm.PoseGrid('r1', .1)
    grid.insert(frame_id=1, pose=[.2, 0., 0.], camera=[0., 0.],
                segments=[[[1., -.3], [1., .3]]], floor_xy=[[.5, .5]])
    points = grid.occupancy.occupied_points()
    assert points[:, 0].mean() == pytest.approx(1.15)  # float floor convention
    assert (20, 20) not in grid.navigation.odds
    assert grid.navigation.state((5, 0)) == -1
    before = copy.deepcopy(grid.navigation.odds)
    with pytest.raises(ValueError, match='DUPLICATE'):
        grid.insert(frame_id=1, pose=[0, 0, 0], camera=[0, 0], segments=[], floor_xy=[])
    assert grid.navigation.odds == before


def test_hit_wins_crossing_floor_ray_and_no_duplicate_per_frame():
    g = sm.PoseGrid('r1', .1)
    g.insert(frame_id=1, pose=[0, 0, 0], camera=[0, 0],
             segments=[[[1.05, -.05], [1.05, .05]]], floor_xy=[[1.5, 0]]*5)
    assert g.navigation.odds[(10, 0)] == pytest.approx(g.occupancy.hit)
    assert g.navigation.odds[(5, 0)] == pytest.approx(g.occupancy.miss)


def test_real_slam_to_grid_and_frontier_proposal(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    first = receive(mapper, 1)
    assert first['map_updated'] and first['pose_source'] == 'bootstrap'
    assert first['candidate_count'] > 0 and first['selected_frontier']['path_m']
    state['pose'] = np.array([.04, 0., 0.])
    second = receive(mapper, 2)
    assert second['pose_source'] == 'visual_update'
    np.testing.assert_allclose(second['pose'], state['pose'], atol=1e-8)
    assert second['map_updated'] and not second['complete']
    assert 'required_zone_unconfirmed' in second['completion_blockers']
    saved = json.loads(json.dumps(mapper.snapshot(), allow_nan=False))
    assert saved['cells'] and saved['floor_cells']
    assert saved['zones']['coordinate_frame'] == saved['coordinate_frame']


def test_command_only_never_inserts_or_selects_stale_frontier(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    receive(mapper, 1)
    before = copy.deepcopy(mapper.grid.navigation.odds)
    state['blank'] = True
    row = receive(mapper, 2)
    assert row['pose_source'] == 'command_only' and not row['map_updated']
    assert row['selected_frontier'] is None and not row['complete']
    assert mapper.grid.navigation.odds == before


def test_relocalization_jump_requires_rebuild_not_rigid_shift(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    receive(mapper, 1)
    before = copy.deepcopy(mapper.grid.navigation.odds)
    state['pose'] = np.array([.3, 0., 0.])
    row = receive(mapper, 2)
    assert 'pose_revision_requires_rebuild' in row['insertion_blockers']
    assert mapper.grid.navigation.odds == before
    assert not receive(mapper, 3)['map_updated']


def test_held_cargo_uses_only_issued_grip_and_suppresses_rgb_insertion(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    receive(mapper, 1)
    mapper.command(dict(t=1.1, kind='arm', servo_id=1, pulse=1500))
    monkeypatch.setattr(sm, 'extract', lambda *a, **k: pytest.fail('held cargo used as feature'))
    row = receive(mapper, 4)
    assert 'commanded_grip_closed' in row['insertion_blockers']
    assert not row['map_updated'] and not row['complete']
    with pytest.raises(ValueError, match='ALLOWLIST'):
        mapper.command(dict(t=4., kind='hold', cargo_world_position=[0, 0]))


def test_peer_duplicate_nonfinite_fail_before_mutating_map(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    receive(mapper, 1)
    before = mapper.snapshot()
    with pytest.raises(ValueError, match='CAUSAL'):
        receive(mapper, 1)
    with pytest.raises(ValueError, match='PEER'):
        mapper.receive(robot_id='r2', t=2., frame_id=2, rgb=np.zeros((480, 640, 3), np.uint8))
    assert mapper.snapshot() == before
    with pytest.raises(ValueError, match='FINITE'):
        mapper.grid.insert(frame_id=5, pose=[np.nan, 0, 0], camera=[0, 0], segments=[], floor_xy=[])


def test_no_frontier_is_not_completion_when_no_robot_observation():
    grid = sm.PoseGrid('r1', .1)
    assert sm.raw_frontier_count(grid.navigation, [0, 0, 0]) is None


def test_completion_requires_closed_boundary_sweep_stability_and_zone(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    from harness import active_wall_vision
    corners = np.array([[-1., -1.], [1., -1.], [1., 1.], [-1., 1.]])
    monkeypatch.setattr(active_wall_vision, 'observe', lambda *a, **k: dict(camera=[0., 0.],
        segments=[[a.tolist(), b.tolist()] for a, b in zip(corners, np.roll(corners, -1, axis=0))], floor_xy=[]))
    mapper.sectors = set(range(8))  # previously admitted own views in all sectors
    mapper.zones.tracks = [{'confirmed_t': 0.}]
    result = None
    for f in range(1, 8): result = receive(mapper, f)
    assert result['raw_frontier_cells'] == 0
    assert result['complete'] and result['stop_reason'] == 'self_map_complete'
    mapper.sectors.remove(7)
    result = receive(mapper, 8)
    assert not result['complete'] and 'incomplete_view_sweep' in result['completion_blockers']
