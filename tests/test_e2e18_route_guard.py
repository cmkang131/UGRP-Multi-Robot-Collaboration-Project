"""DEV margin relaxation must not fabricate observed free corridors."""
from types import SimpleNamespace
import copy
import numpy as np
import pytest
from tests.test_e2e_goal_route import controller,ref,pulse_fixture
from tests.test_e2e18 import options,ROOT
from harness.e2e_goal_route import OPTION
from harness.zone_study_contract import ContractViolation
from harness.own_map_navigation import ObservedGrid


def goal():
    g=controller(own_route=OPTION)
    g.dev_light=True;g.e2e_route_guard='dev_nominal_v1'
    g.explorer.memory.self_map.odom.covariance=np.eye(3)*.1
    return g


def route(g, yaw=0.):
    return g.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,yaw]),now=1.3,profiles=pulse_fixture()[1]['profiles'])


def test_only_dev_sigma_margin_can_fall_back_with_numeric_evidence():
    g=goal();g.e2e_route_guard='off'
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)
    g.e2e_route_guard='dev_nominal_v1';out=route(g)
    assert out['compiled']['source']=='own_map'
    d=g.e2e_route_diagnostics
    assert d['would_stop_sigma'] and d['attempts'][0]['path_cells']==0 and d['attempts'][1]['path_cells']>0
    assert d['sigma_xy_m']==pytest.approx(.1**.5) and d['applied_margin_m']==.02
    g.dev_light=False
    with pytest.raises(ValueError,match='DEV'):route(g)


def test_unseen_grid_and_wrong_beam_axes_stay_rejected():
    g=goal();g.explorer.grid=ObservedGrid('r1')
    with pytest.raises(ContractViolation,match='GRID_ROUTE'):route(g)
    assert not g.e2e_route_diagnostics['would_stop_sigma']
    g=goal()
    with pytest.raises(ContractViolation,match='BEAM_ALIGNMENT'):route(g,.5)
    assert g.e2e_route_diagnostics['beam_pose_own_m'][2]==.5
    assert g.e2e_route_diagnostics['stage']=='beam_axes'


def test_same_rgb_cannot_repeat_route_search():
    from harness.e2e_live_mapping import Robot
    calls=[];g=SimpleNamespace(e2e_route_guard='dev_nominal_v1',route_to_B=lambda *a,**k:calls.append(k))
    r=Robot.__new__(Robot);r.robot_id='r1';r.goal=g;r.now=1.3;r.beam=dict(rgb=ref(3),pose_own_m=[0.,0.,0.])
    r.route({},'off');r.route({},'off');assert len(calls)==1
    r.beam['rgb']=ref(4);r.route({},'off');assert len(calls)==2


def test_registered_dev_bundle():
    from scripts.run_e2e_ownmap_live import bundle
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1')
    assert b['execution_bundle_id']=='e2e18-v221';require_current(b,ROOT)
    bad=copy.deepcopy(b);bad['e2e_options']['dev_light']=False
    with pytest.raises(ValueError):require_current(bad,ROOT)
