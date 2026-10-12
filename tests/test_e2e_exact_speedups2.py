"""Round-2 exact receive-chain toggles: bit/order identity with the originals."""
import copy
import math
import pickle

import numpy as np
import pytest

from harness import e2e_exact_speedups2 as s2
from harness.e2e_exact_speedups import OFF, Options, using
from harness.own_map_navigation import ObservedGrid

ALL = Options(provenance_index=True, sha_validation_cache=True, omit_discarded_copy=True, scalar_cells=True,
              geometry_cache=True, vector_rays=True, shared_wall_frontend=True, lazy_scan_path=True,
              vector_costmap_writes=True, track_cell_tuples=True)


def test_new_toggles_default_off_and_boolean():
    assert not any(getattr(OFF, k) for k in ('vector_rays', 'shared_wall_frontend', 'lazy_scan_path',
                                              'vector_costmap_writes', 'track_cell_tuples'))
    with pytest.raises(ValueError):
        Options(vector_rays=1)


@pytest.mark.parametrize('scalar', [False, True])
def test_vector_cells_match_scalar_and_numpy_paths(scalar):
    rng = np.random.default_rng(3)
    grid = ObservedGrid('r1', .1)
    p = np.r_[rng.normal(scale=3., size=(4000, 2)), np.arange(-20, 20).reshape(-1, 2)*.1,
              [[-0., 0.], [-1e-300, 1e-300], [.3, -.7], [1e6, -1e6]]]
    with using(Options(scalar_cells=scalar)):
        expected = [grid.cell(v) for v in p]
    got = s2.cells(grid, p)
    assert got == expected
    assert all(type(c) is tuple and type(c[0]) is int and type(c[1]) is int for c in got)
    assert s2.cells(grid, np.array([[np.nan, 0.]])) is None
    assert s2.cells(grid, np.array([[np.inf, 0.]])) is None


def _rays(rng, n):
    a = rng.integers(-40, 40, size=(n, 2))
    b = a + rng.integers(-25, 26, size=(n, 2))
    rays = [((int(x), int(y)), (int(u), int(v))) for (x, y), (u, v) in zip(a, b)]
    rays += [((0, 0), (0, 0)), ((1, 1), (5, 5)), ((2, 3), (-4, 3)), ((0, 0), (3, -3)), ((0, 0), (-2, 7)),
             ((5, 0), (5, -6)), ((0, 0), (4, 2)), ((0, 0), (-4, -2)), ((0, 0), (2, 4))]
    return rays


@pytest.mark.parametrize('scalar', [False, True])
def test_bresenham_cells_equal_both_raytrace_generators_and_set_order(scalar):
    from harness.grid_acceleration import using as scalar_rays
    from harness.public_navigation_persistent import raytrace_cells
    rays = set(_rays(np.random.default_rng(5), 3000))
    with scalar_rays('scalar_rays_v1' if scalar else 'off'):
        expected = [c for s, e in rays for c in raytrace_cells(s, e)]
        expected_set = {c for s, e in rays for c in raytrace_cells(s, e)}
    x, y = s2.bresenham_cells(rays)
    assert list(zip(x, y)) == expected
    got_set = set(zip(x, y))
    assert got_set == expected_set and list(got_set) == list(expected_set)
    assert s2.bresenham_cells([((0, 0), (np.int64(1), 0))]) is None


def _receive_rays_state(seed):
    rng = np.random.default_rng(seed)
    grid = ObservedGrid('r1', .05)
    latest, static_hits = {}, {(3, 4), (-2, 1)}
    for frame in range(1, 6):
        n, m = int(rng.integers(20, 200)), int(rng.integers(0, 40))
        floor = rng.normal(scale=1.5, size=(n, 2))
        wall = rng.normal(scale=2., size=(m, 2))
        obs = dict(robot_id='r1', frame_id=frame, floor_xy=floor.tolist(), wall_xy=wall.tolist(),
                   floor_origins_xy=np.tile(rng.normal(scale=.05, size=2), (n, 1)).tolist(),
                   wall_origins_xy=np.tile(rng.normal(scale=.05, size=2), (m, 1)).tolist())
        pose = [float(rng.normal()), float(rng.normal()), float(rng.uniform(-math.pi, math.pi))]
        yield grid, latest, static_hits, obs, pose


@pytest.mark.parametrize('seed', [0, 1, 2])
def test_receive_rays_state_and_iteration_order_identical(seed):
    from harness.public_navigation_raytrace import receive_rays
    states = []
    for options in (Options(scalar_cells=True), Options(scalar_cells=True, vector_rays=True)):
        out = []
        grid = latest = None
        for grid, latest, static_hits, obs, pose in _receive_rays_state(seed):
            with using(options):
                out.append(receive_rays(grid, latest, static_hits, copy.deepcopy(obs), pose))
        states.append(pickle.dumps((out, grid.__dict__, latest), protocol=5))
    assert states[0] == states[1]


def test_wall_frontend_hit_returns_owned_copies_and_checks_bits():
    calls = []
    rgb = np.random.default_rng(1).integers(0, 255, size=(12, 16, 3), dtype=np.uint8)
    kw = dict(servo={1: 1500, 6: 1400}, origin=np.zeros(3), rotation=np.eye(3), params={'a': 1}, loaded=False,
              wall_detector='off', contact_rule='off', contact_state=None, mp=np, hfw=math)

    def compute():
        calls.append(1)
        return rgb[..., 0].copy(), dict(vb=np.arange(4.)), rgb[..., 1].astype(float)
    s2._FRONTEND.clear()
    with using(OFF):
        s2.wall_frontend(compute, rgb, **kw); s2.wall_frontend(compute, rgb, **kw)
    assert len(calls) == 2
    with using(ALL):
        first = s2.wall_frontend(compute, rgb, **kw)
        first[1]['vb'][0] = 99.  # caller mutation must not leak into the cache
        second = s2.wall_frontend(compute, rgb, **kw)
        assert len(calls) == 3 and second[1]['vb'][0] == 0.
        changed = rgb.copy(); changed[0, 0, 0] ^= 1
        s2.wall_frontend(compute, changed, **kw)
        assert len(calls) == 4
        s2.wall_frontend(compute, rgb, **{**kw, 'contact_rule': 'floor_appearance_ulrich_v1'})
        s2.wall_frontend(compute, rgb, **{**kw, 'servo': {1: 1500, 6: 1401}})
        assert len(calls) == 6


def _scan_cases():
    good = dict(a=[1., 2, [3., [4., 'x']], None, True], b=dict(c=(1., 2.), d=[]), e=np.float64(3.))
    return [good, dict(a=[1., [2., float('nan')]]), dict(a=dict(b=[0., float('inf')])), dict(x=np.float64('nan')),
            dict(a=[dict(static_map=1)]), {'a': {1: 2.}}, [[1., 2.], [3., float('-inf')]], float('nan'), 'ok']


@pytest.mark.parametrize('case', range(9))
def test_lazy_scan_same_result_and_message(case):
    from harness.e2e_own_inputs import scan
    value = _scan_cases()[case]
    results = []
    for options in (OFF, ALL):
        with using(options):
            try:
                results.append(('ok', scan(value)))
            except Exception as exc:  # message and type must be identical
                results.append((type(exc).__name__, str(exc)))
    assert results[0] == results[1]


def test_costmap_writes_identical_including_fallback():
    from harness.public_navigation_unknown import from_observed_grid
    rng = np.random.default_rng(4)
    grid = ObservedGrid('r1', .05)
    for c in map(tuple, rng.integers(-30, 30, size=(300, 2)).tolist()):
        grid.odds[c] = float(rng.normal()); grid.floor_frames.setdefault(c, set()).add(1)
    latest = {c: bool(rng.integers(2)) for c in list(grid.odds)[:120]}
    for static_hits in ({(0, 0), (5, -3)}, {(400, 400)}):  # second: out of dense range -> original path
        outputs = []
        for options in (OFF, ALL):
            with using(options):
                try:
                    c = from_observed_grid(grid, np.array([.1, .2, 0.]), latest, static_hits)
                    outputs.append(pickle.dumps((c.costs, c.__dict__), protocol=5))
                except Exception as exc:
                    outputs.append((type(exc).__name__, str(exc)))
        assert outputs[0] == outputs[1]
