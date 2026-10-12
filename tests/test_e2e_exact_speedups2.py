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


@pytest.mark.parametrize('scalar', [False, True])
@pytest.mark.parametrize('seed', [0, 1, 2])
def test_receive_rays_state_and_iteration_order_identical(seed, scalar):
    from harness.public_navigation_raytrace import receive_rays
    states = []
    for options in (Options(scalar_cells=scalar), Options(scalar_cells=scalar, vector_rays=True)):
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
        s2.wall_frontend(compute, rgb, **{**kw, 'wall_detector': 'floor_boundary_v1'})
        s2.wall_frontend(compute, rgb, **{**kw, 'wall_detector': 'floor_boundary_v1'})
        assert len(calls) == 8


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


def test_v200_bundle_unchanged_and_round2_registers_v203():
    from scripts.run_e2e_ownmap_live import bundle
    v200 = dict(provenance_index=True, sha_validation_cache=True, omit_discarded_copy=True, scalar_cells=True,
                geometry_cache=True)
    common = dict(enabled=True, mapping_budget='case_cap_v1', path_follow='rpp_v1', dev_light=True,
                  stall_odometry='rgb_pulse_gate_v1', stall_recovery='backup_replan_v1', stall_noise='amcl_alpha_v1')
    old = bundle('0'*40, 61001, 'study_gemma4_31b_v1', **common, exact_speedups=v200)
    assert old['execution_bundle_id'] == 'e2e-exact-speed-v200' and old['workflow_version'] == '7.93.0'
    assert old['e2e_options']['exact_speedups'] == v200
    assert not any(k.endswith('_v203.json') for k in old['source_sha256'])
    new = bundle('0'*40, 61001, 'study_gemma4_31b_v1', **common, exact_speedups={**v200, 'vector_rays': True})
    assert new['execution_bundle_id'] == 'e2e-exact-speed2-v203' and new['workflow_version'] == '7.96.0'
    assert new['e2e_options']['exact_speedups'] == {**vars(Options(**v200)), 'vector_rays': True}
    assert {'configs/simulation_workflows.d/e2e_exact_speed2_v203.json', 'scripts/e2e_speed_measure.py'} <= set(new['source_sha256'])
    assert {k for k in old if old[k] != new[k]} == {'schema', 'execution_bundle_id', 'workflow_version', 'e2e_options', 'source_sha256'}
    for k in ('contact_profile', 'calibration', 'case_cap_s', 's3_camera_binding', 'controller_config'):
        assert old[k] == new[k]
    flag = bundle('0'*40, 61001, 'study_gemma4_31b_v1', **common, exact_speedups=v200, speed2_bundle=True)
    assert flag['execution_bundle_id'] == 'e2e-exact-speed2-v203'


# ---- rbpf_audit_hash=binary_v1 ------------------------------------------------

def _audit_robot(seed=0, n=6):
    from types import SimpleNamespace as NS
    rng = np.random.default_rng(seed)
    maps = []
    for i in range(n):
        cells = {(int(x), int(y)): float(rng.normal()) for x, y in rng.integers(-30, 30, size=(40, 2))}
        maps.append(NS(cells=cells))
    histories = [[dict(t=.2*k, frame_id=k, pose=rng.normal(size=3).tolist(),
                       wall_confidence=[dict(weight=float(rng.random()), factors=dict(range=np.float64(rng.random())))])
                  for k in range(3)] for _ in range(n)]
    grid = NS(poses=rng.normal(size=(n, 3)), pending_cov=rng.normal(size=(n, 3, 3)), weights=np.full(n, 1/n),
              log_weights=np.zeros(n), rng=np.random.default_rng(seed+7), best=0, resamples=1, revision=4,
              histories=histories, maps=maps)
    return NS(robot_id='r1', frame=NS(index=3), now=.6, goal=NS(explorer=NS(memory=NS(self_map=grid))))


def _mutations():
    def first_cell(g):
        return next(iter(g.maps[0].cells))
    yield 'poses value', lambda g: g.poses.__setitem__((0, 0), g.poses[0, 0]+1e-12)
    yield 'pending_cov value', lambda g: g.pending_cov.__setitem__((1, 2, 0), 0.)
    yield 'weights -0.0', lambda g: g.weights.__setitem__(0, -0.)
    yield 'log_weights dtype', lambda g: setattr(g, 'log_weights', g.log_weights.astype(np.float32))
    yield 'poses shape', lambda g: setattr(g, 'poses', g.poses.reshape(3, -1))
    yield 'rng advanced', lambda g: g.rng.random()
    yield 'best', lambda g: setattr(g, 'best', 1)
    yield 'best bool', lambda g: setattr(g, 'best', False)
    yield 'resamples', lambda g: setattr(g, 'resamples', 2)
    yield 'revision float', lambda g: setattr(g, 'revision', 4.)
    yield 'history float', lambda g: g.histories[2][1]['pose'].__setitem__(0, 9.)
    yield 'history np.float64', lambda g: g.histories[0][0]['wall_confidence'][0]['factors'].__setitem__('range', np.float64(.5))
    yield 'history key', lambda g: g.histories[1][0].__setitem__('extra', None)
    yield 'history append', lambda g: g.histories[3].append(dict(t=9.))
    yield 'map value', lambda g: g.maps[0].cells.__setitem__(first_cell(g), g.maps[0].cells[first_cell(g)]+1.)
    yield 'map value -0.0', lambda g: g.maps[1].cells.__setitem__(first_cell(g) if False else next(iter(g.maps[1].cells)), -0.)
    yield 'map value int', lambda g: g.maps[2].cells.__setitem__(next(iter(g.maps[2].cells)), 1)
    yield 'map key moved', lambda g: g.maps[0].cells.__setitem__((99, -99), g.maps[0].cells.pop(first_cell(g)))
    yield 'map key bool', lambda g: g.maps[4].cells.__setitem__((True, 5), 1.)
    yield 'map cell added', lambda g: g.maps[5].cells.__setitem__((1000, 1000), .25)
    yield 'map key beyond int64', lambda g: g.maps[5].cells.__setitem__((2**70, 1), .25)
    yield 'map cell removed', lambda g: g.maps[5].cells.pop(next(iter(g.maps[5].cells)))
    yield 'map emptied', lambda g: g.maps[3].cells.clear()
    yield 'maps swapped', lambda g: g.maps.reverse()
    yield 'map dropped', lambda g: g.maps.pop()


@pytest.mark.parametrize('name', [n for n, _ in _mutations()])
def test_binary_audit_changes_whenever_json_audit_changes(name):
    from scripts.e2e_speed_measure import rbpf_digest, rbpf_digest_binary
    mutate = dict(_mutations())[name]
    robot = _audit_robot()
    j0, b0 = rbpf_digest(robot), rbpf_digest_binary(robot)
    mutate(robot.goal.explorer.memory.self_map)
    j1, b1 = rbpf_digest(robot), rbpf_digest_binary(robot)
    assert j1 != j0, name  # each mutation is visible to the legacy JSON digest
    assert b1 != b0, name


def test_binary_audit_pure_and_order_independent_like_json():
    from scripts.e2e_speed_measure import rbpf_digest, rbpf_digest_binary
    a, b = _audit_robot(), _audit_robot()
    gb = b.goal.explorer.memory.self_map
    for m in gb.maps:  # same content, reversed dict insertion order
        m.cells = dict(reversed(list(m.cells.items())))
    for h in gb.histories:
        for rec in h:
            items = list(rec.items()); rec.clear(); rec.update(reversed(items))
    assert rbpf_digest(a) == rbpf_digest(b)
    assert rbpf_digest_binary(a) == rbpf_digest_binary(b)
    assert rbpf_digest_binary(a) != rbpf_digest(a)
    gb.maps[0].cells[next(iter(gb.maps[0].cells))] = np.float64(gb.maps[0].cells[next(iter(gb.maps[0].cells))])
    rbpf_digest_binary(b)  # typed fallback path still hashes


def test_audit_modes_rows_compare_like_with_like_and_mapping():
    from scripts.e2e_speed_measure import audit_row, compare_rbpf, hash_mapping, rbpf_digest
    robot = _audit_robot()
    seconds = dict(json_v1=0., binary_v1=0.)
    off = audit_row(robot, 'off', seconds)
    assert list(off) == ['robot', 'frame', 't', 'sha256'] and off['sha256'] == rbpf_digest(robot)
    binary = audit_row(robot, 'binary_v1', seconds)
    both = audit_row(robot, 'both_v1', seconds)
    assert set(binary) == {'robot', 'frame', 't', 'binary_sha256'} and both['binary_sha256'] == binary['binary_sha256']
    with pytest.raises(ValueError, match='RBPF_HASH_SCHEME_MISMATCH'):
        compare_rbpf([off], [binary])
    with pytest.raises(ValueError, match='RBPF_HASH_SCHEME_MISMATCH'):
        compare_rbpf([both], [off], 'binary_v1')
    assert compare_rbpf([off], [both])['scheme'] == 'json_v1'
    assert compare_rbpf([binary], [both])['scheme'] == 'binary_v1'
    assert compare_rbpf([both], [both], 'binary_v1')['equal']
    mapping = hash_mapping([both])
    assert mapping['functional'] and mapping['mapping'][0]['json_v1'] == off['sha256']
    with pytest.raises(ValueError):
        audit_row(robot, 'json', seconds)


def test_selected_workflow_rejects_mismatched_bundle_before_preparation(tmp_path, capsys):
    import json
    from pathlib import Path
    from sim import workflow_manager as wm
    from scripts import run_e2e_ownmap_live as run
    root=Path(__file__).resolve().parents[1]
    row=wm._row(root,'e2e-exact-speed2-v203')[0]
    args=['--expected-source-sha','a'*40,'--seed','61001',
          '--driver-profile','study_gemma4_31b_v1','--relay-receipt',str(tmp_path/'receipt.json'),
          '--output',str(tmp_path/'unused'),'--decider','off','--exploration-progress','off',
          '--pose-fix','off','--path-follow','off','--wall-cap-s','12600',
          '--stall-odometry','off','--stall-recovery','off','--stall-noise','off',
          '--mapping-budget','case_cap_v1']
    command,_=wm._runner_command(root,row,args,record=None)
    assert command[-2:]==['--expected-workflow-id','e2e-exact-speed2-v203']
    with pytest.raises(ValueError,match='WORKFLOW_BUNDLE_ID_MISMATCH'):
        run.main(command[3:])
    assert not capsys.readouterr().out and not (tmp_path/'unused').exists()
    run.main([*command[3:],'--exact-speed2-bundle'])
    assert json.loads(capsys.readouterr().out)['execution_bundle_id']==row['id']
    with pytest.raises(ValueError,match='WORKFLOW_OWNS_BUNDLE_ID'):
        wm._runner_command(root,row,[*args,'--expected-workflow-id=arbitrary'],record=None)


def test_receive_failure_keeps_original_frame_manifest(monkeypatch):
    from types import SimpleNamespace
    from scripts import replay_e2e_receive_speed as replay
    class BrokenRobot:
        def receive(self,*a):raise RuntimeError('fixture failure')
    monkeypatch.setattr(replay,'build_robots',lambda *a:({'r1':BrokenRobot()},SimpleNamespace(snapshot=lambda:{})))
    frames={'r1':[dict(name='first.jpg',sha256='1'*64,jpeg=b'first',rgb=np.zeros((1,1,3),np.uint8)),
                  dict(name='second.jpg',sha256='2'*64,jpeg=b'second',rgb=np.zeros((1,1,3),np.uint8))]}
    before=pickle.dumps(frames)
    rows,_,_=replay.replay(frames,{})
    assert pickle.dumps(frames)==before and len(rows)==1
    assert rows[0]['frame_name']=='first.jpg' and rows[0]['frame_sha256']=='1'*64
    assert rows[0]['error']=='RuntimeError:fixture failure'
