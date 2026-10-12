import copy,json
from pathlib import Path
import numpy as np
import pytest
from harness.active_wall_recovery import make_mapper,OPTION,ExplorationRecoveryNavigator,RECOVERY
from harness.active_wall_mapping import ActiveMapper
from harness.active_camera import SEARCH
from harness.public_navigation_unknown import UnknownCostmap,from_observed_grid
from harness.self_odom_grid import transform
from tests.test_wall_confidence import FEATURE
from tests.test_self_map_prob import CORNER


def actor(option=OPTION):
    return make_mapper('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1',active_recovery=option)


def test_off_same_type_and_bytes():
    a,b=actor('off'),ActiveMapper('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1')
    assert type(a) is type(b)
    obs=dict(segments=[],features=[],camera=[.124,0.],floor_xy=[])
    for t in (2.,2.2,3.):
        ca,ta=a.receive(robot_id='r3',t=t,frame_id=round(t*10),rgb=np.zeros((480,640,3),np.uint8),servo=SEARCH,observation=obs)
        cb,tb=b.receive(robot_id='r3',t=t,frame_id=round(t*10),rgb=np.zeros((480,640,3),np.uint8),servo=SEARCH,observation=obs)
        assert json.dumps([ca,ta,a.memory.self_map.export()])==json.dumps([cb,tb,b.memory.self_map.export()])
    with pytest.raises(ValueError):actor('unknown')


def test_wrap_and_retry_budget_only_success_counts():
    n=ExplorationRecoveryNavigator()
    actions=[]
    for i in range(6):
        n.context_used={'planner'}
        n.failure(i,'synthetic_unreachable','planner');actions.append(n.phase)
        n.phase_result(i+.1,True)
        assert n.retry==i+1
    assert actions==['clear','spin','backup','wait','clear','spin']
    n.target=n.frontier=np.array([1.,1.]);n.static_mode=True;n.requested_goal=np.array([2.,2.])
    n.context_used={'planner'};n.failure(7.,'synthetic_unreachable','planner')
    assert not n.failed and n.retry==0 and n.target is None
    assert n.blocked([1.,1.],.1) and n.blocked([2.,2.],.1)
    assert n.events[-1]['reason']=='next_frontier_requested'
    n.begin_phase('clear',8.)
    for i in range(4):n.phase_result(8.+i,False)
    assert n.phase is None and not n.failed


def test_aborted_static_goal_selects_other_frontier():
    n=ExplorationRecoveryNavigator()
    raw=np.full((30,40),255,np.uint8);raw[10:20,10:25]=0
    c=UnknownCostmap(raw,[-1.,-1.],.1);pose=np.array([.5,.5,0.])
    n.static_mode=True;n.target=np.array([-5.,-5.]);n.requested_goal=n.target.copy()
    n.action_failed(0.,'recovery_exhausted')
    plan=n.update(c,pose,.2,static_goal=[-5.,-5.])
    assert plan['status']=='public_frontier' and plan['path_m'] and not n.failed


def test_clear_only_navigation_current_scan_and_epoch():
    a=actor();a.grid.odds[(2,2)]=3.;a.latest[(2,2)]=True
    obs=dict(t=3.,frame_id=1,segments=[],features=[],camera=[.124,0.],floor_xy=[[.7,.2],[.7,-.2]])
    a.frames=[obs];saved=json.dumps(a.memory.self_map.export())
    a.clear_navigation(3.)
    assert (2,2) not in a.grid.odds
    assert json.dumps(a.memory.self_map.export())==saved
    before=copy.deepcopy(a.grid.odds)
    a._rays(dict(obs,t=2.,frame_id=0,segments=CORNER.tolist()),[0,0,0])
    assert a.grid.odds==before and not a.navigator.clear_requested


def test_graph_keeps_recovery_and_reset_epoch(monkeypatch):
    a=actor();n=a.navigator
    # No estimator retune: use an isolated fake graph computation to test the TF adapter contract.
    a.memory.self_map.ledger=[{},{}]
    a.navigation_epoch=3.
    n.phase='backup';n.retry=3;n.round_index=2;n.phase_pose=np.array([1.,2.,.1])
    n.target=np.array([3.,4.]);n.checker.baseline=np.array([1.,0.])
    def graph(self,t):
        self.map_to_odom=np.array([.1,.2,.3]);self.navigator.target=None;self.navigator.reset_action()
        self.revisit=None;self.plan=None
    monkeypatch.setattr(ActiveMapper,'graph',graph)
    a.graph(5.)
    assert n.phase=='backup' and n.retry==3 and n.round_index==2 and a.navigation_epoch==3.
    np.testing.assert_allclose(n.target,transform([[3.,4.]],[.1,.2,.3])[0])
    assert n.phase_pose[2]==pytest.approx(.4)


def test_new_run_changes_only_seed_and_recovery_option():
    from scripts.run_active_wall_wide import frozen_bundle as old_bundle
    from scripts.run_active_wall_recovery import frozen_bundle
    a,b=old_bundle('new-seed','f'*40),frozen_bundle('new-seed','f'*40)
    assert b['task']['seed']==29001
    assert b['options'].pop('active_recovery')==OPTION
    b['task']['seed']=a['task']['seed']
    for k in ('execution_bundle_id','check'):b[k]=a[k]
    assert a==b
