"""Offline robust graph/evidence acceptance, no physics, network or GT files."""
import copy
import json
import math

import numpy as np
import pytest

from harness.self_loop_rejection import optimize_switchable, refine_cached_graph
from harness.self_pose_graph import GraphOptions, apply_pose_graph, rebuild
from harness.self_wall_evidence import build_evidence, gaussian
from harness.self_wall_memory_motion import SelfWallMemory as Previous
from harness.self_wall_memory_robust import SelfWallMemory
from tests.test_self_pose_graph import row
from tests.test_wall_projection_guard import FRONT, ORIGIN, ROT, rec


def test_switches_keep_consistent_edge_and_suppress_false_edge_without_changing_anchor():
    rows = [row(0), row(1, (1., 0., 0.))]
    cov = np.diag([.01, .01, .01])
    edges = [dict(kind='intra', submap=0, scan=i, relative_pose=r['pose'],
                  covariance=cov.tolist()) for i, r in enumerate(rows)]
    edges += [dict(kind='loop', submap=0, scan=1, relative_pose=p,
                   covariance=cov.tolist()) for p in ([1.,0.,0.], [5.,0.,.8])]
    source = json.dumps([rows, edges])
    solved, d = optimize_switchable([{'pose':np.zeros(3)}], rows, edges)
    assert d['accepted'] and d['final_cost'] < d['initial_cost']
    assert d['switches'][0]['switch'] > .99 and d['switches'][1]['switch'] < .01
    # Eq (1), at fixed poses: s = 1 / (1 + Xi * chi^2).
    for event in d['switches']:
        optimum = 1/(1+event['unscaled_chi2'])
        # At the upper bound TRF can stop with a small switch error but a much
        # smaller objective error; verify the objective, not unattained digits.
        cost = lambda s:s*s*event['unscaled_chi2']+(1-s)**2
        assert cost(event['switch'])-cost(optimum) < 1e-6
    np.testing.assert_array_equal(solved[0], np.zeros(3))
    assert np.linalg.norm(solved[-1]-rows[-1]['pose']) < .01
    assert json.dumps([rows, edges]) == source


def test_failed_optimizer_reverts_to_frontend_and_does_not_claim_retention():
    rows = [row(0)]
    edges = [dict(kind='intra', submap=0, scan=0, relative_pose=[0.,0.,0.], covariance=np.eye(3).tolist()),
             dict(kind='loop', submap=0, scan=0, relative_pose=[4.,0.,0.], covariance=np.eye(3).tolist())]
    solved, d = optimize_switchable([{'pose':np.zeros(3)}], rows, edges, GraphOptions(max_nfev=1))
    assert not d['accepted'] and all(e['reason']=='optimizer_failed' for e in d['switches'])
    np.testing.assert_array_equal(solved, np.zeros((2,3)))


def test_invalid_covariance_and_peer_rows_fail_closed():
    edges = [dict(kind='loop', submap=0, scan=0, relative_pose=[0.,0.,0.], covariance=(-np.eye(3)).tolist())]
    with pytest.raises(ValueError, match='INVALID'):
        optimize_switchable([{'pose':np.zeros(3)}], [row(0)], edges)
    for f, kwargs in [(refine_cached_graph, dict(poses=[], legacy_result=None, loop_rejection='switchable_v1')),
                      (build_evidence, dict(wall_evidence='tsdf_weight_v1'))]:
        with pytest.raises(ValueError, match='PEER'):
            f([row(0)], robot_id='r2', **kwargs)


def test_off_is_identity_without_reading_inputs_and_options_are_explicit():
    a, b, result = object(), object(), object()
    assert refine_cached_graph(a, b, result, robot_id='r1') is result
    assert build_evidence(a, robot_id='r1') is None
    with pytest.raises(ValueError, match='UNKNOWN'):
        refine_cached_graph(a, b, result, robot_id='r1', loop_rejection='typo')
    with pytest.raises(ValueError, match='REQUIRES'):
        SelfWallMemory('r1', loop_rejection='switchable_v1')


def test_tsdf_one_update_per_scan_cap_and_angular_diversity_not_probability():
    segment = [[[1.,-.4],[1.,.4]]]
    single = row(0, segments=segment)
    one = build_evidence([single], robot_id='r1', wall_evidence='tsdf_weight_v1')
    duplicate = build_evidence([row(0, segments=segment*2)], robot_id='r1', wall_evidence='tsdf_weight_v1')
    assert one == duplicate
    assert all(c['observations']==1 and c['view_circular_variance'] < 1e-15 for c in one['cells'])
    rows = [row(i, segments=segment) for i in range(40)]
    repeated = build_evidence(rows, robot_id='r1', wall_evidence='tsdf_weight_v1')
    assert max(c['weight'] for c in repeated['cells']) == 10.
    assert all(c['observations']==40 for c in repeated['cells'])
    assert max(c['view_circular_variance'] for c in repeated['cells']) < 1e-12
    assert 'NOT probability' in repeated['semantics']
    assert all('probability' not in c for c in repeated['cells'])
    other = row(1, segments=segment)
    other['camera'] = [.16, .3]
    mixed = build_evidence([single, other], robot_id='r1', wall_evidence='tsdf_weight_v1')
    assert max(c['view_circular_variance'] for c in mixed['cells']) > .001
    assert gaussian(0., .5) == pytest.approx(1/math.sqrt(.5*math.pi))
    assert gaussian(1., .5) < gaussian(0., .5)


def test_evidence_keeps_occupancy_and_existing_free_carving_intact():
    rows = [row(i, segments=[[[1.,-.4],[1.,.4]]]) for i in range(2)]
    before = json.dumps(rebuild('r1', rows).export())
    build_evidence(rows, robot_id='r1', wall_evidence='tsdf_weight_v1')
    assert json.dumps(rebuild('r1', rows).export()) == before
    assert any(v<0 for v in rebuild('r1', rows).cells.values())


@pytest.mark.parametrize('mode', ['off', 'own_map_csm_prob_v1', 'own_map_rbpf_v1'])
def test_memory_off_golden_bytes_and_frontend_unchanged(mode):
    args=dict(self_map='odom_grid_v1', pose_correction=mode, self_map_options={'settle_s':None},
              wall_projection_guard='positive_depth_v1', clock=lambda:9.)
    memories = [Previous('r1', **args), SelfWallMemory('r1', **args),
                SelfWallMemory('r1', loop_rejection='off', wall_evidence='off', **args)]
    for i in range(3):
        for m in memories:
            m.command(dict(t=float(i), kind='drive', forward=.01, turn=.01, duration_s=.2))
            m.observe_wall(rec([FRONT],float(i),i), camera_xy=ORIGIN[:2], robot_id='r1', camera_origin=ORIGIN, camera_rotation=ROT)
        blobs=[json.dumps([m.snapshot(),m.self_map.export()]).encode() for m in memories]
        assert blobs[0] == blobs[1] == blobs[2]


def test_memory_finalization_options_keep_frontend_and_invalidate_evidence():
    args=dict(self_map='odom_grid_v1', pose_correction='own_map_rbpf_v1', self_map_options={'settle_s':None},
              wall_projection_guard='positive_depth_v1', pose_graph='own_submap_v1', clock=lambda:9.)
    old, off, on = Previous('r1', **args), SelfWallMemory('r1', **args), SelfWallMemory('r1',
        loop_rejection='switchable_v1', wall_evidence='tsdf_weight_v1', **args)
    for m in (old, off, on):
        m.observe_wall(rec([FRONT],1.,1), camera_xy=ORIGIN[:2], robot_id='r1', camera_origin=ORIGIN, camera_rotation=ROT)
    before = json.dumps(on.self_map.export())
    old_result, off_result, on_result = [m.finalize_pose_graph() for m in (old,off,on)]
    assert json.dumps(old_result).encode() == json.dumps(off_result).encode()
    assert json.dumps(old.snapshot()).encode() == json.dumps(off.snapshot()).encode()
    assert json.dumps(on.self_map.export()) == before
    assert on_result['wall_evidence']['cells'] and on.evidence_view is not None
    on.command(dict(t=2.,kind='stop'))
    assert on.evidence_view is None and on.pose_graph_result is None


def test_no_loop_cached_replay_and_uncorrected_prefix():
    rows = [row(0), row(1)]
    path = [dict(robot_id='r1',t=-1.,pose=[0.,0.,0.]), dict(robot_id='r1',t=1.,pose=[0.,0.,0.])]
    legacy = apply_pose_graph(rows,path,robot_id='r1',pose_graph='own_submap_v1')
    original = json.dumps([rows,path,legacy])
    out, poses, d = refine_cached_graph(rows,path,legacy,robot_id='r1',loop_rejection='switchable_v1')
    assert out==rows and poses==path and d['optimization']['reason']=='no_loop_constraints'
    assert json.dumps([rows,path,legacy])==original


def test_score_diagnostic_does_not_claim_probability_calibration():
    import importlib.util
    from pathlib import Path
    import sys
    directory=Path(__file__).resolve().parents[1]/'experiments/2026-10-07-robust-wall-map/code'
    sys.path.insert(0,str(directory))
    spec=importlib.util.spec_from_file_location('egomap21_score_test',directory/'offline_score.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result=module.score_gap(np.array([.95,.95]),np.array([0.,1.]))
    assert result['score_ece']==pytest.approx(.45)
    assert 'NOT a probability' in result['qualification']
    assert 'ece' not in result and 'brier' not in result
    assert 'mujoco' not in sys.modules
