"""Evaluation-only synthetic prior geometry and false-convergence scoring."""
import math
import numpy as np
from scripts.mapbuild10_mc import make_prior,evaluate_case


def test_synthetic_prior_is_uncertainty_box_without_exact_pose_or_center_alignment():
    pose=np.array([1.3,-.7,math.pi-.01]);rng=np.random.default_rng(42);fractions=[]
    for i in range(20):
        p=make_prior(pose,{'map_id':'fixture'},rng,f'fixture-{i}')
        b=p['bounds_m'];assert np.isclose(b[1]-b[0],.5) and np.isclose(b[3]-b[2],.5)
        u=(pose[:2]-np.array([b[0],b[2]]))/.5
        assert np.all((u>0)&(u<1)) and not np.allclose(u,.5)
        angle=math.atan2(math.sin(pose[2]-p['heading_center_rad']),math.cos(pose[2]-p['heading_center_rad']))
        assert abs(angle)<math.pi/6
        assert not {'pose','spawn','evaluation_pose','offset','seed'}&set(p)
        fractions.append(u)
    assert np.ptp(fractions,axis=0).min()>.8


REQ=dict(position_error_m=.2007512557246549,yaw_error_rad=.3739074138060199,nominal_target_range_m=.8483145702460003)


def test_scoring_requires_improvement_after_convergence_and_never_accepts_wrong_mode():
    rows=[dict(t=0.,candidate=[0,0,0],ready=True),dict(t=1.,candidate=[0,0,0],ready=True)]
    truth=[[0,0,0],[0,0,0]];off=[[0,0,0],[.05,0,0]]
    s=evaluate_case(rows,truth,off,REQ)
    assert s['offline_pass'] and s['ready_updates']==2 and s['wrong_ready_updates']==0
    bad=[{**r,'candidate':[1,0,0]} for r in rows]
    s=evaluate_case(bad,truth,off,REQ)
    assert s['wrong_ready_updates']==2 and not s['offline_pass']


def test_unresolved_diagnostic_endpoint_is_not_an_offline_pass():
    rows=[dict(t=0.,candidate=[0,0,0],ready=False),dict(t=1.,candidate=[0,0,0],ready=False)]
    s=evaluate_case(rows,[[0,0,0],[0,0,0]],[[0,0,0],[.1,0,0]],REQ)
    assert s['final_xy_m']==0 and not s['offline_pass'] and s['first_converged_sim_s'] is None
