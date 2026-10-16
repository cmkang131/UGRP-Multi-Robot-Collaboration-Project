import copy,json
from pathlib import Path
import numpy as np
import pytest
from harness.active_navfn_start import make_mapper,OPTION,CYCLE,StartRecoveryNavigator,StartCycleNavigator
from harness.active_frontier_cycle import make_mapper as legacy
from harness.active_wall_recovery import ExplorationRecoveryNavigator
from harness.active_camera import SEARCH
from harness.public_navigation_unknown import UnknownCostmap
from harness.public_navigation_recovery import issued_twist

ARGS=dict(active_mapping='frontier_rbpf_v1',active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')

def clear():return UnknownCostmap(np.zeros((120,120),np.uint8),[-3,-3],.05)

@pytest.mark.parametrize('cycle',['off',CYCLE])
def test_off_trace_bytes(cycle):
    a=make_mapper('r3',0,SEARCH,frontier_observation=cycle,**ARGS)
    b=legacy('r3',0,SEARCH,frontier_observation=cycle,**ARGS)
    assert type(a) is type(b)
    obs=dict(segments=[],features=[],floor_xy=[[.7,-.2],[.7,.2]],camera=[.124,0.])
    rgb=np.zeros((480,640,3),np.uint8)
    for i,t in enumerate([2.,2.2,3.]):
        x=a.receive(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,observation=obs)
        y=b.receive(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,observation=obs)
        assert json.dumps([x,a.memory.self_map.export(),a.navigator.events])==json.dumps([y,b.memory.self_map.export(),b.navigator.events])
    with pytest.raises(ValueError):make_mapper('r3',0,SEARCH,navigation_start='bad',**ARGS)

@pytest.mark.parametrize('start_cost',[253,254])
def test_start_cell_only_cleared_in_planning_copy(start_cost):
    c=clear();p=np.array([.025,.025,0.]);s=c.world_to_map(p[:2]);c.raw[s[1],s[0]]=254;c.costs[s[1],s[0]]=start_cost
    before=c.costs.copy();n=StartRecoveryNavigator();original=n.core.plan;seen=[]
    def plan(costs,start,goal):seen.append(costs.copy());return original(costs,start,goal)
    n.core.plan=plan
    assert n.plan_to(c,p,[1.,0.])
    changed=np.argwhere(before!=seen[0]);np.testing.assert_array_equal(changed,[[s[1],s[0]]])
    assert seen[0][s[1],s[0]]==0 and c.raw[s[1],s[0]]==254
    np.testing.assert_array_equal(before,c.costs)
    assert n.plan_to(c,[-10,0,0],[1,0])==[]

def test_recorded_four_candidates_and_local_collision_guard_retained():
    d=np.load(Path(__file__).parent/'fixtures/navfn_start_costmap.npz')
    c=UnknownCostmap(d['raw'],d['origin'],float(d['resolution']));p=d['pose']
    old,n=ExplorationRecoveryNavigator(),StartRecoveryNavigator()
    fs=old.core.frontiers(c.raw,c.origin,c.resolution,p[:2]);assert len(fs)==4
    before=(c.raw.tobytes(),c.costs.tobytes())
    for f in fs:
        assert not old.plan_to(c,p,f[:2]);path=n.plan_to(c,p,f[:2]);assert path
        assert not c.sweep_clear(p,[*path[1],p[2]])
    assert before==(c.raw.tobytes(),c.costs.tobytes())
    c.pose_clear=lambda pose:False
    n=StartRecoveryNavigator();n.select_frontier=lambda *args:None;n.static_mode=True
    n.target=np.array([p[0]+1,p[1]]);n.frontier=n.target.copy();n.last_plan_t=0.
    plan=dict(status='public_static',path_m=[p[:2].tolist(),n.target.tolist()],heading_rad=float(p[2]))
    cmd=n.command(c,p,plan,.2)
    assert not np.any(issued_twist(cmd)) and n.phase=='context_clear'

@pytest.mark.parametrize('cls',[StartRecoveryNavigator,StartCycleNavigator])
def test_planner_failure_recovers_before_blacklist(cls):
    n=cls();c=clear();p=np.zeros(3)
    if isinstance(n,StartCycleNavigator):n.sweep_pending=None
    n.core.frontiers=lambda *args:np.array([[1.,0.,1.,0.,1.,20.,-1.]])
    n.plan_to=lambda *args:[]
    n.update(c,p,0.)
    assert n.phase=='context_clear' and not n.blacklist and not n.finished
    n.clear_requested=False;n.phase_result(.2,True)
    assert n.target is not None and not n.blacklist
    n.failure(.4,'planner_failed','planner');assert n.phase=='clear'
    for t,phase in [(1.,'spin'),(2.,'wait'),(3.,'backup')]:
        n.phase_result(t,False);assert n.phase==phase
    n.phase_result(4.,False)
    assert n.blacklist and not n.finished
    assert any(e['reason']=='navigation_action_aborted' for e in n.events)

def test_bundle_only_registered_difference():
    from scripts.run_frontier_duration import bundle as previous
    from scripts.run_active_navfn_start import bundle,actor
    a,b=previous('B','a'*40),bundle('a'*40)
    assert b['task']['seed']==47001 and b['case_cap_s']==360.
    assert b['options'].pop('navigation_start')==OPTION
    b['task']['seed']=a['task']['seed']
    for k in ('execution_bundle_id','check','preregistration','condition','admission'):b[k]=a[k]
    assert a==b
    assert isinstance(actor('r3',0,SEARCH,**ARGS).navigator,StartCycleNavigator)
