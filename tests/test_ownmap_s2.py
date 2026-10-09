import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from harness import ownmap_s2 as m


def grid():
    return dict(frame=m.FRAME, resolution_m=.1,
        cells=[[0, 0, 2], [1, 0, -2], [2, 0, 0], [0, 1, -1], [1, 1, -2]],
        pose_xyyaw=[999, 999, 999], particle_poses=[[888, 888, 888]])


def test_off_never_reads_input():
    assert m.convert(None) is None
    with pytest.raises(ValueError):
        m.convert(None, option='bad')


def test_own_frame_missing_data_and_grid_cell_centers():
    a = m.convert(grid(), option=m.OPTION); f = m.GridField(a)
    assert a['map_id'] == 'ownmaps2a' and a['regions'] == {} and a['passages'] == []
    assert a['landmarks']['tags'] == [] and a['pickup_slots'] == []
    assert 'pose_xyyaw' not in str(a) and '999' not in str(a)
    assert f.distances(np.array([[.05, .05]]))[0] == 0
    assert f.distances(np.array([[100, 100]]))[0] == 2
    assert f.distances(np.array([[.15, .05]]))[0] == pytest.approx(.06)
    px = f.uniform(np.random.default_rng(10), 1000)
    assert f.free(px[:, :2]).all()
    assert not f.free(np.array([[.25, .05], [.35, .05], [.05, .05]])).any()
    assert px[:, 2].min() < -3 and px[:, 2].max() > 3


def test_partial_region_never_fabricates_boundary():
    goal = dict(entity=dict(kind='floor_zone', id='B'), source='own',
                center_m=[3, 4], bounds_m=[[2, 3], [4, 5]], partial_extent=True)
    original = copy.deepcopy(goal)
    a = m.convert(grid(), goal, option=m.OPTION)
    assert a['observed_regions']['B']['bounds_m'] == goal['bounds_m']
    assert a['observed_floor_edges'] == [] and a['regions'] == {}
    assert goal == original


@pytest.mark.parametrize('change', [dict(frame='world'), dict(resolution_m=float('nan')),
    dict(cells=[[0, 0, 1], [0, 0, -1]]), dict(cells=[[.5, 0, 1], [1, 0, -1]])])
def test_invalid_input_refused(change):
    with pytest.raises(ValueError):
        m.convert({**grid(), **change}, option=m.OPTION)


def test_warning_rule_has_yaw_and_missing_fix():
    r = dict(std_xy_m=.02, std_yaw_rad=.01, last_fix_t=1.)
    assert not m.warned(r)
    assert m.warned({**r, 'last_fix_t': None})
    assert m.warned({**r, 'std_yaw_rad': math.radians(6)})
    with pytest.raises(RuntimeError):
        m._forbid_control()


def test_evaluation_alignment_rotates_covariance_without_fit():
    from scripts.evaluate_ownmap_s2 import anchored_pose
    p,c=anchored_pose(np.array([1.,0.,.1]),np.diag([.04,.01,.09]),np.array([3.,4.,math.pi/2]))
    np.testing.assert_allclose(p,[3.,5.,math.pi/2+.1])
    np.testing.assert_allclose(c,np.diag([.01,.04]),atol=1e-12)


def test_wrong_mode_not_hidden_by_posthoc_trajectory_alignment():
    from scripts.evaluate_ownmap_s2 import score
    r=dict(t=1.,t_est=1.,x=1.,y=0.,yaw=0.,std_xy_m=.01,std_yaw_rad=.01,last_fix_t=1.,
        cov=np.diag([.0001,.0001,.0001]).tolist(),pose_uncertain=False)
    truth=[dict(t=1.,robot_xyz_m=[0,0,0],robot_yaw_rad=0.)]
    out,_=score([r],truth,np.zeros(3),[1.])
    assert out['wrong_mode'] and not out['correct_convergence']
    assert out['post_convergence_rmse_m']==1. and out['unflagged_gt25cm']==1
    assert out['nees_all']==dict(valid=1,exceed=1,exceed_fraction=1.)


def test_gate_requires_seven_and_does_not_skip_failed_own_convergence():
    from scripts.evaluate_ownmap_s2 import gates
    ok=dict(correct_convergence=True,post_convergence_rmse_m=.1,wrong_mode=False,
        unflagged_gt25cm=0,nees_all=dict(valid=1,exceed=0),first_convergence_missing_gt=False,missing_decision_reports=0)
    pairs=[dict(pair_id=str(i),baseline_identity=True,off=copy.deepcopy(ok),own_grid_v1=copy.deepcopy(ok)) for i in range(7)]
    assert gates(pairs)['passed']
    assert not gates(pairs[:-1])['passed']
    pairs[0]['own_grid_v1'].update(correct_convergence=False,post_convergence_rmse_m=None)
    assert not gates(pairs)['passed']


def test_observed_partial_edges_and_doors_are_retained_not_completed():
    source=dict(robot_id='r3',t=1.)
    edge=dict(a=[1.,2.],b=[1.,3.],normal=[1.,0.],hue=105.,source=source,partial_extent=True)
    lm=dict(robot_id='r3',frame='r3/own_start',world_alignment=None,future_observations=0,before_t=2.,
        edges=[edge],doors=[dict(center=[2.,3.],width=.6,source=source)])
    a=m.convert(grid(),landmarks=lm,option=m.OPTION)
    assert a['observed_floor_edges']==[edge] and a['regions']=={}
    assert len(a['passages'])==1 and a['passages'][0]['center_m']==[2.,3.]
    with pytest.raises(ValueError):
        m.convert(grid(),landmarks={**lm,'world_alignment':[1,2,3]},option=m.OPTION)
    lm['edges'][0]['source']={'robot_id':'r2','t':1.}
    with pytest.raises(ValueError):m.convert(grid(),landmarks=lm,option=m.OPTION)


def test_tiled_likelihood_matches_original_on_partial_edges_and_doors():
    from harness.zone_solo_cyan_landmarks import landmark_likelihood
    rng=np.random.default_rng(6);edges=[]
    for i in range(21):
        a=rng.normal(size=2);d=rng.normal(size=2);normal=np.array([-d[1],d[0]])/np.linalg.norm(d)
        edges.append(dict(a=a,b=a+d,normal=normal,hue=float(100+i)))
    mapped=SimpleNamespace(edges=edges,doors=[dict(center=np.array([1.,2.]),width=.5)])
    px=rng.normal(size=(273,3))
    fs=[dict(kind='floor_line',endpoints=[[.5,.3],[1.,.4]],normal=[0.,1.],hue=105.),
        dict(kind='floor_line',endpoints=[[-1.,-.3],[-.5,-.4]],normal=[0.,-1.],hue=10.),
        dict(kind='door',center=[1.,1.],width=.5)]
    np.testing.assert_allclose(m.bounded_landmark_likelihood(mapped,px,fs),landmark_likelihood(mapped,px,fs),rtol=2e-12,atol=1e-15)


def test_real_constructor_under_registered_speedups_uses_only_own_geometry():
    # The exact-speedup installer imports the optional drive kernel even when
    # this test never creates or steps a physics world. Lightweight CI has no
    # MuJoCo; keep the other thirteen adapter/evaluator tests active there.
    pytest.importorskip('mujoco', reason='registered speedup installer imports optional MuJoCo')
    from harness import zone_s2_unknown_start_contract as c
    from harness import zone_solo_cyan_contract_v106 as base
    from harness.zone_pair_highpose_exact_speedups import install
    from harness.zone_solo_cyan_bias_tempering import closure
    from harness import vision_pose_source_highpose as high
    bundle=c.bundle('0'*40,1059,**c.NEW_OPTIONS)
    original=high.HighPoseSource.__init__
    static=m.convert(grid(),option=m.OPTION)
    _,undo=install('v98-exact-v6');runtime=None
    try:
        runtime=m.build_runtime(bundle,static,base.ROOT/base.CALIBRATION,base.CALIBRATION_SHA,option=m.OPTION)
        pf=runtime.pose.provider.loc._pf
        assert pf.n==100000 and runtime.own_map_field.free(pf.px[:,:2]).all()
        assert runtime.route==[] and runtime.slot is None
        selected=closure(pf.update_obs)['selected']
        assert closure(selected)['field'] is runtime.own_map_field
        assert not closure(selected.__globals__['endpoints'])['mapped'].edges
        with pytest.raises(RuntimeError):runtime.step(1.)
    finally:
        if runtime is not None:runtime.close()
        undo()
    assert high.HighPoseSource.__init__ is original
