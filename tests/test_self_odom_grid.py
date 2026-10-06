"""Command-only replay, inverse sensor geometry and off-byte contract; no physics/model."""
import copy
import json
import math

import numpy as np
import pytest

from harness.coela_modules import Memory
from harness.self_wall_memory import SelfWallMemory
from harness.self_odom_grid import CommandOdometry, OdomGrid, ray_cells, transform


def rec(t=1., view=1, x=2., y=.5):
    r, a = math.hypot(x, y), math.atan2(y, x)
    return {'t_sim': t, 'view_index': view, 'seg': [[r, -a, r, a, None]], 'posture': 'other', 'load': False}


def profile():
    return {'motion': {'gain': np.eye(3).tolist(), 'tau_s': 1e-6, 'tau_stop_s': 1e-6}}


def grid(**kw):
    return OdomGrid('r1', profiles=profile(), settle_s=None, **kw)


def test_own_command_integration_and_rotation_not_measured_pose():
    od = CommandOdometry(profiles=profile())
    od.command({'kind': 'mecanum', 't': 0., 'forward': 1., 'left': 0., 'turn': 0., 'duration_s': .125,
                'true_pose': [100, 100, 100]})
    np.testing.assert_allclose(od.advance(.3), [.125, 0., 0.], atol=1e-8)
    od.command({'kind': 'drive', 't': .3, 'forward': 0., 'turn': math.pi/2, 'duration_s': 1.})
    od.advance(1.3)
    od.command({'kind': 'mecanum', 't': 1.3, 'forward': 1., 'left': 0., 'turn': 0., 'duration_s': 1.})
    np.testing.assert_allclose(od.advance(2.3), [.125, 1., math.pi/2], atol=1e-8)
    np.testing.assert_allclose(transform([[2., 0.]], od.pose), [[.125, 3.]], atol=1e-8)


def test_grid_fuses_same_world_wall_after_translation():
    g = grid()
    g.observe(rec(0.), camera_xy=[.2, 0.], robot_id='r1')
    before = set(k for k, v in g.cells.items() if v > 0)
    g.odom.command({'kind': 'drive', 't': 0., 'forward': 1., 'turn': 0., 'duration_s': 1.})
    g.observe(rec(1., 2, x=1.), camera_xy=[.2, 0.], robot_id='r1')
    after = set(k for k, v in g.cells.items() if v > 0)
    # Floating bin boundaries can differ by one column; all remain at the same wall.
    assert all(abs((x+.5)*g.resolution_m - 2.) <= .051 for x, y in after)
    assert after & before
    assert g.cells[(10, 0)] < 0
    assert (24, 0) not in g.cells  # no clearing behind the face


def test_camera_origin_rays_negative_cells_and_dedup():
    g = grid()
    r = rec(x=2.)
    r['seg'] *= 5
    g.observe(r, camera_xy=[1., 0.], robot_id='r1')
    assert (0, 0) not in g.cells  # rays start at camera, not chassis
    assert max(g.cells.values()) == pytest.approx(g.hit)  # one update per frame
    before = copy.deepcopy(g.cells)
    g.observe(r, camera_xy=[1., 0.], robot_id='r1')
    assert before == g.cells
    assert ray_cells([-.01, -.01], [-.21, -.21], .1)[-1] == (-3, -3)


def test_prior_clamp_and_contradictory_free_evidence():
    g = grid()
    wall = np.array([[1.05, -.05], [1.05, .05]])
    for _ in range(20):
        g.insert(np.array([0., 0.]), [wall])
    assert g.cells[(10, 0)] == pytest.approx(g.hi)
    for _ in range(20):
        g.insert(np.array([0., 0.]), [wall + [1., 0.]])
    assert g.cells[(10, 0)] < 0
    assert min(g.cells.values()) >= g.lo


def test_settle_and_range_rejection_use_own_commands():
    g = OdomGrid('r1', profiles=profile())
    g.odom.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': {1: 2000, 3: 740}})
    assert not g.observe(rec(.1), camera_xy=[0., 0.], robot_id='r1')
    assert g.observe(rec(.25, 2), camera_xy=[0., 0.], robot_id='r1')
    assert not g.observe(rec(.3, 3, x=4.1), camera_xy=[0., 0.], robot_id='r1')
    g.odom.command({'t': .4, 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
    assert not g.observe(rec(1., 4), camera_xy=[0., 0.], robot_id='r1')
    assert g.observe(rec(2.65, 5), camera_xy=[0., 0.], robot_id='r1')
    assert g.rejected == {'unsettled': 2, 'range_segments': 1}


def test_memory_is_private_text_bounded_and_peer_reports_do_not_fuse():
    a = SelfWallMemory('r1', self_map='odom_grid_v1', self_map_options={'settle_s': None, 'text_max_tokens': 180})
    b = SelfWallMemory('r2', self_map='odom_grid_v1')
    a.observe_wall(rec(), camera_xy=[.2, 0.], robot_id='r1')
    before = copy.deepcopy(a.self_map.cells)
    a.observe({'observation_id': 'a', 'cargo': [], 'self_map': {'peer_grid': [1, 2, 3]}}, 1.)
    assert a.self_map.cells == before
    assert not b.self_map.cells
    with pytest.raises(ValueError, match='PEER'):
        b.observe_wall(rec(), camera_xy=[0., 0.], robot_id='r1')
    text = a.snapshot()['self_map_text']
    assert 'start odom' in text and '->' in text and len(text.encode()) <= 180
    assert 'self_map' not in a.snapshot()  # no full grid duplicated into the LLM prompt


@pytest.mark.parametrize('enabled', [False, True])
def test_off_snapshot_is_bytes_identical_to_before_option(enabled):
    from pathlib import Path
    import types
    # Frozen pre-change source; includes legacy on_v1 records and wording.
    old = types.ModuleType('old_self_wall_memory')
    exec((Path(__file__).parent/'fixtures/self_wall_memory_before_odom.py.txt').read_text(), old.__dict__)
    for flag in ({}, {'self_map': 'off'}):
        args = dict(self_walls_enabled=enabled, self_walls_text=enabled, clock=lambda: 5.)
        previous, current = old.SelfWallMemory('r1', **args), SelfWallMemory('r1', **args, **flag)
        current.command({'bad': 'ignored while off'})
        current.observe_wall({}, camera_xy=None, robot_id='peer')
        for i in range(3):
            observation = {'observation_id': str(i), 'cargo': [], 'self_walls': [rec(float(i), i)]}
            previous.observe(observation, float(i)); current.observe(observation, float(i))
            assert json.dumps(previous.snapshot()).encode() == json.dumps(current.snapshot()).encode()


def test_out_of_order_and_invalid_inputs_fail_without_peer_effect():
    g = grid()
    g.observe(rec(2.), camera_xy=[0., 0.], robot_id='r1')
    with pytest.raises(ValueError, match='NON_MONOTONIC'):
        g.observe(rec(1., 2), camera_xy=[0., 0.], robot_id='r1')
    with pytest.raises(ValueError, match='CAMERA'):
        g.observe(rec(3., 3), camera_xy=[math.nan, 0.], robot_id='r1')
    with pytest.raises(ValueError):
        SelfWallMemory('r1', self_map='unknown')


def test_eval_uses_fixed_all_wall_denominator_and_exposes_false_cells():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[1]/'experiments/2026-10-05-ego-wall-map-probe/code/odom_grid_replay.py'
    spec = importlib.util.spec_from_file_location('odom_grid_replay', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rects = np.array([[0., 0., 1., 1.]])
    samples = module.wall_samples(rects)
    metrics, covered = module.quality(np.array([[1., 0.], [3., 3.]]), rects, samples)
    assert metrics['precision_015'] == .5
    assert 0 < metrics['wall_coverage'] < .1
    assert len(covered) == len(samples) > 50
    assert module.quality(np.empty((0, 2)), rects, samples)[0]['precision_015'] is None


def test_rays_terminate_on_rounding_sensitive_endpoint_and_reverse():
    for end in ([2.-1e-15, .5], [2., -.5], [-2., -.5], [-2.+1e-15, .5]):
        cells = ray_cells([.2, 0.], end, .1)
        reverse = ray_cells(end, [.2, 0.], .1)
        assert cells[-1] == tuple(np.floor(np.array(end)/.1).astype(int))
        assert reverse[-1] == (2, 0)
        assert len(cells) < 40 and len(reverse) < 40
