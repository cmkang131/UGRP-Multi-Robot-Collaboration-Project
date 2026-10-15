"""Static own-estimate geometry counterexamples; no physics or rendering."""
import inspect
import math
from types import SimpleNamespace as NS
import numpy as np
import pytest
from sim import release23, release25
from scripts.run_grasp_act_release import run
from tests.test_release_regrasp import teachers


def case(y=1.24, distance=.30, sign=1.):
    ts=teachers()
    static=dict(bounds_m=[-3,3,-3,1.45],obstacles=[dict(id='wall_north',center_m=[0,1.45],half_extents_m=[3,.025])])
    loc={r:NS(map_pose_known=True,decision=dict(accepted=True),
        own=NS(x=np.array([i,y if i==0 else 0.,-math.pi/2]),P=np.diag([.05**2,.05**2,0.])),
        global_matcher=NS(static=static)) for i,r in enumerate(ts)}
    plans={r:t.shift_plan(distance,sign) for r,t in ts.items()}
    return loc,ts,plans


def check(args, on=True):
    return release23.sweep(*args,0.,computation_budget=release23.COMPUTE,
        release_sweep_wall_aware=release25.MODE if on else 'off')


def test_uncertainty_only_overlap_escapes_with_unchanged_full_geometry():
    args=case()
    old=check(args,False);new=check(args)
    assert not old['accepted'] and old['blocking_object']=='wall_north'
    assert new['accepted'] and new['minimum_gap']==old['minimum_gap']
    escaped=[c for c in new['checks'] if c.get('uncertainty_escape')]
    assert escaped and all(c['nominal_swept_gap_m']>0 for c in escaped)
    assert all(c['halo_m']==pytest.approx(.10) for c in escaped)


@pytest.mark.parametrize('y,distance,sign',[(1.25,.30,1.),(1.24,.30,-1.),(1.24,.02,1.),(1.24,0.,1.)])
def test_nominal_overlap_wallward_motion_or_incomplete_escape_stays_blocked(y,distance,sign):
    assert not check(case(y,distance,sign))['accepted']


def test_direction_reversal_midpath_and_new_obstacle_block_escape():
    loc,ts,plans=case()
    plans['r1']=ts['r1'].shift_plan(.01,-1.)+plans['r1']
    assert not check((loc,ts,plans))['accepted']
    loc,ts,plans=case()
    loc['r1'].global_matcher.static['obstacles'].append(dict(id='midpath',center_m=[0,1.04],half_extents_m=[.1,.002]))
    assert not check((loc,ts,plans))['accepted']


def test_rotation_and_unlocalized_inputs_are_not_translation_escape():
    loc,ts,plans=case()
    from sim.lookaround_localization import rotate_plan
    plans['r1']=rotate_plan(.1,ts['r1'].odometry_profile)
    assert check((loc,ts,plans))['reason_category']=='sweep_nontranslation'
    loc['r1'].decision['accepted']=False
    assert check((loc,ts,plans))['reason_category']=='sweep_pose_unknown'


def test_default_off_and_dependencies():
    assert inspect.signature(run).parameters['release_sweep_wall_aware'].default=='off'
    with pytest.raises(ValueError):release25.validate(dict(release_sweep_wall_aware=release25.MODE))
    release25.validate(dict(release_sweep_wall_aware=release25.MODE,
        release_leg_budget=release23.LEG,release_plan_budget=release23.COMPUTE))
