"""Nonphysics contracts for known-cargo geometry and deterministic boundaries."""
from types import ModuleType,SimpleNamespace
import sys
import numpy as np
import pytest
from harness.beampair_geometry import navigation_class,checks_only_class,MODE


def modules(monkeypatch):
    specifications={'sim.zone_arena':dict(BOX_HALF=(.017,.02,.016),COLORS=('cyan','red')),
        'sim.grasp_act_search23':dict(rectangle_gaps=lambda xy,yaw,rect:np.full(len(xy),.03)),
        'sim.grasp_act_search21':dict(FRESH_MARGIN_M=.005),
        'sim.grasp_act_search25':dict(hard_margins=lambda nav:[d['margin_m'] for d in nav.audit_details])}
    for name,values in specifications.items():
        m=ModuleType(name);m.__dict__.update(values);monkeypatch.setitem(sys.modules,name,m)


def navigation(monkeypatch,mode=MODE,observations=None):
    modules(monkeypatch)
    class Native:
        def __init__(self,t,w,*a,**kw):
            self.teacher=t
            self.details=[dict(id='cyan_1',fresh=True,margin_m=.02),dict(id='unknown_1',fresh=False,margin_m=.04)]
            self.audit_details=self.details;self.blocked={};self.pose=(0,0,0);self.target=None;self.inflation_soft=False
        def measure(self,xy,yaw=None):
            self.blocked['cyan_1']=dict(slack_m=-.05574)
            return np.tile([-.03574,.2],(len(xy),1)),None
    t=SimpleNamespace(rid='r1',box_geometry=mode,box_geometry_log=[],search20_budget=None)
    obs=observations if observations is not None else dict(cyan_1=dict(kind='cargo',xyz=[1,2,0],yaw=.6))
    w=dict(t=1.,visibility=dict(r1=dict(observations=obs)))
    return navigation_class(Native)(t,w),t


def test_geometry_replaces_only_known_observed_box_and_keeps_confidence(monkeypatch):
    n,t=navigation(monkeypatch)
    gaps,slack=n.measure([[0,0],[1,0]])
    assert len(n.boxes)==1 and n.boxes[0][1]==(1,2,.017,.02,.6)
    assert gaps[:,0]==pytest.approx([.025,.025])
    assert slack[:,0]==pytest.approx([.005,.005])
    assert gaps[:,1]==pytest.approx([.2,.2])
    assert 'cyan_1' not in n.blocked and not n.last_blockers
    assert t.box_geometry_log[0]['source'].startswith('zone_arena.BOX_HALF')


@pytest.mark.parametrize('mode,obs',[('off',None),(MODE,{})])
def test_default_and_missing_own_observation_do_not_replace_any_geometry(monkeypatch,mode,obs):
    n,t=navigation(monkeypatch,mode,obs)
    assert n.boxes==[] and t.box_geometry_log==[]
    assert n.measure([[0,0]])[0][0,0]==-.03574


def test_confidence_rejection_still_blocks_after_box_shape_substitution(monkeypatch):
    n,_=navigation(monkeypatch)
    n.audit_details[0]['margin_m']=.04
    _,slack=n.measure([[0,0]])
    assert slack[0,0]<0
    assert n.last_blockers[0]['id']=='cyan_1'



def test_checks_only_retains_native_count_without_wall_selection():
    class Budget:
        def __init__(self,**kw):self.options=kw
    cls=checks_only_class(Budget)
    assert cls(max_checks=98304,max_s=3,safety_s=30).options==dict(max_checks=98304,max_s=None,safety_s=None)


def test_vector_work_budget_counts_scalar_pairs_and_fails_before_excess(monkeypatch):
    m=ModuleType('sim.grasp_act_search20')
    class Exhausted(RuntimeError):pass
    m.PlanningBudgetExceeded=Exhausted;monkeypatch.setitem(sys.modules,m.__name__,m)
    class Native:
        def __init__(self,**kw):self.max_checks=kw['max_checks'];self.checks=0;self.exhausted=False
        def check(self):self.checks+=1
    b=checks_only_class(Native,weighted=True)(max_checks=98304)
    b.next_work=100*400;b.check();assert b.checks==40000
    b.next_work=100*400;b.check();assert b.checks==80000
    b.next_work=100*400
    with pytest.raises(Exhausted):b.check()
    assert b.exhausted and b.checks==80000


def test_setup_cargo_check_cannot_accept_walls_only_clearance():
    from scripts.prepare_beampair6 import validity_checker
    family=[(0.,.203,None,None)]
    static=dict(obstacles=[dict(id='wall',center_m=[9,9],half_extents_m=[.1,.1])])
    clear=lambda pose,discs,rects:0. if rects[0][0]==0 else 1.
    assert validity_checker(family,clear,.005,1)((0,0,0),static)['accepted']
    checked=validity_checker(family,clear,.005,1,cargo_rects=[('cyan_1',(0,0,.017,.02,0))])((0,0,0),static)
    assert not checked['accepted']
    assert checked['ends']['teal']['blocked_object']=='cyan_1'


def test_new_setup_mode_preserves_assigned_color_after_rejected_proposal(tmp_path,monkeypatch):
    import json
    from scripts import prepare_beampair1 as p
    monkeypatch.setattr(p,'EXP',tmp_path)
    scenario=dict(scenario_id='fixture',map_id='fixture',eval=dict(setup=dict(placements=[
        dict(item_id='cyan_1',kind='cyan',pose_m=[99,99,0])])) )
    (tmp_path/'scenario-v7.json').write_text(json.dumps(scenario))
    static=dict(bounds_m=[-10,10,-10,10],regions=dict(pickup=dict(center_m=[0,0],half_extents_m=[1,1])))
    monkeypatch.setattr(p,'resolve',lambda _: (static,None,None))
    monkeypatch.setattr(p,'keepout_rects',lambda *a,**kw:[])
    monkeypatch.setattr(p,'pose_clear',lambda *a,**kw:True)
    monkeypatch.setattr(p,'kind',lambda _:SimpleNamespace(landing_half_extents_m=[.3,.02],
        grasps=[SimpleNamespace(grip_xyz=[-.27,0,0]),SimpleNamespace(grip_xyz=[.27,0,0])]))
    calls=0
    def validity(*a):
        nonlocal calls
        calls+=1
        return dict(k=1,accepted=calls>1,ends={end:dict(free_goal_N=int(calls>1),
            blocked_object='cyan_1',min_gap_m=0.) for end in ('teal','blue')})
    out=tmp_path/'new';p.prepare(123,output=out,validity=validity,preserve_role_strata=True)
    plans=json.loads((out/'gate-plan.json').read_text())['episodes']
    assert [e['roles']['r1'] for e in plans]==['teal','blue']*20
