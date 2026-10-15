"""Visible/issued graph and memory regressions. No simulator or renderer."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np
import pytest

from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_search15_modes import add_arguments, options, validate, match
from sim.grasp_act_search18 import body_clearance
from sim.grasp_act_search20 import PlanningBudget, PlanningBudgetExceeded
from sim.grasp_act_search22 import BodyNavigation as Previous, uncertainty
from sim.grasp_act_search23 import BodyNavigation, PEER_TTL_S, enabled
from tests.test_grasp_act_search22 import teacher as old_teacher, measurement, FIX


def teacher():
    t=old_teacher();t.search15_modes['search23']='search23_v1';return t


def maze():
    t=teacher();t.bounds=(-1.,2.,-1.,1.)
    w={'t':0.,'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{},'beam':None,
       'walls':[(.5,0.,.04,.6,0.)],
       'visibility':{'r1':{'objects':[],'peers':[],'visible_probes':0,'observations':{}}}}
    w['visibility']['r1']['observations']['wall']={'id':'wall','kind':'wall','seen_t':0.,
        'xyz':[.5,0.,.1],'half_extents':[.04,.6],'yaw':0.}
    return t,w


def test_default_off_dependency_and_provenance():
    p=argparse.ArgumentParser();add_arguments(p)
    assert options(p.parse_args([]))['search23']=='off'
    with pytest.raises(ValueError,match='search23 requires search22'):
        validate({'search23':'search23_v1'},recovery='progress_view_recovery_v3')
    with pytest.raises(ValueError,match='search23 mode mismatch'):
        match({}, {'search23':'search23_v1'},'gate')
    assert not enabled(old_teacher())


def test_grid_finds_detour_outside_all_sixteen_polyline_families():
    t,w=maze();old=Previous(t,w);nav=BodyNavigation(t,w)
    assert old.plan_path((0.,0.),(1.,0.),t.bounds,[]) is None
    path=nav.plan_path((0.,0.),(1.,0.),t.bounds,[])
    assert path and path[0]==(0.,0.) and path[-1]==(1.,0.)
    assert max(abs(p[1]) for p in path)>.68
    assert all(old.segment_free(a,b,[],[],0.) for a,b in zip(path,path[1:]))
    assert nav.last_path_audit['min_gap_m']>=.005
    assert nav.last_path_audit['path_length_m']>1.
    json.dumps(t.search23_log,allow_nan=False)


def test_multi_goal_does_not_spend_the_step_on_an_unreachable_first_endpoint():
    t,w=maze();w['walls']=[(.5,0.,.04,2.,0.)]
    nav=BodyNavigation(t,w)
    t.search20_budget=PlanningBudget(max_checks=100,max_s=1.)
    path=nav.plan_paths((0.,0.),[(1.,0.),(-.4,.4)])
    assert path[-1]==(-.4,.4) and not t.search20_budget.exhausted


@pytest.mark.parametrize('episode',['000','002'])
def test_frozen_budget_starvation_world_admits_a_fully_checked_stance(episode):
    from sim.grasp_act_search19 import body_fallback
    snapshot=json.loads((Path(__file__).parent/'fixtures'/f'grasp_act_search23_{episode}.json').read_text())
    t=teacher();t.sink.pwm.update({int(k):v for k,v in snapshot['pwm'].items()})
    t.search20_budget=PlanningBudget(max_checks=98304,max_s=10.)
    selected,rows=body_fallback(t,snapshot['world'],snapshot['world']['t'])
    assert selected is not None and any(r.get('body_sweep') and r.get('arm_sweep') for r in rows)
    assert selected['path'][0]==tuple(snapshot['world']['robots']['r1']['pose'][:2])
    assert selected['path'][-1]==selected['goal']


def test_batched_geometry_matches_exact_existing_footprint():
    t,w=maze();nav=BodyNavigation(t,w)
    rng=np.random.default_rng(23);xy=rng.uniform((-.8,-.9),(1.8,.9),(100,2));yaw=rng.uniform(-math.pi,math.pi,100)
    gaps,_=nav.measure(xy,yaw)
    exact=[body_clearance((*p,a),[],w['walls']) for p,a in zip(xy,yaw)]
    assert gaps[:,0]==pytest.approx(exact,abs=1e-12)
    w=deepcopy(FIX['world']);nav=BodyNavigation(teacher(),w,admission=True)
    p=np.array([w['robots']['r1']['pose'][:2],w['beam']['ends']['blue'][:2]])
    gaps,_=nav.measure(p,[0.,.2])
    for i in range(2):
        assert gaps[i,:len(nav.discs)]==pytest.approx([body_clearance((*p[i],[0.,.2][i]),[d],[]) for d in nav.discs])


def test_blocked_start_and_timeout_are_distinguished_and_auditable():
    t,w=maze();nav=BodyNavigation(t,w)
    assert nav.plan_path((.5,0.),(1.,0.),t.bounds,[]) is None
    audit=nav.last_path_audit
    assert audit['blocked_obstacles'][0]['id']=='wall'
    assert audit['min_gap_m']==0. and audit['path_length_m']==0.
    t.search20_budget=PlanningBudget(max_checks=2,max_s=10.)
    nav=BodyNavigation(t,w)
    with pytest.raises(PlanningBudgetExceeded):nav.plan_path((0.,0.),(1.,0.),t.bounds,[])
    assert nav.last_path_audit['status']=='planning_budget'
    json.dumps(t.search23_log,allow_nan=False)


def test_dynamic_peer_grows_expires_reappears_and_old_mode_is_unchanged():
    m=measurement();m.update(id='r2',kind='robot',radius=.17,top_z_bound_m=.32)
    a=VisibleWorld('r1','blue',search22='search22_v1')
    b=VisibleWorld('r1','blue',search22='search22_v1',search23='off')
    dynamic=VisibleWorld('r1','blue',search22='search22_v1',search23='search23_v1')
    for now,ms in [(0.,[m]),(1.,[]),(PEER_TTL_S+.01,[])]:
        assert a.observe(ms,now)==b.observe(ms,now)
        w=dynamic.observe(ms,now);t=teacher()
        if now==1.:
            nav=BodyNavigation(t,w);d=next(d for d in nav.details if d['id']=='r2')
            assert d['sigma_m']>uncertainty(w['visibility']['r1']['observations']['r2'],dynamic.pose)['sigma_m']
            assert d['dynamic'] and d['age_s']==1.
    assert 'r2' in a.memory and 'r2' not in dynamic.memory and 'r2' not in w['robots']
    t.search18_space.ghosts['r2']={**m,'seen_t':0.};t.reobserver.hints['r2']={**m,'seen_t':0.}
    clean=t.search18_space.update(w,t,w['t'])
    assert 'r2' not in clean['robots'] and not t.search18_space.ghosts and not t.reobserver.hints
    w=dynamic.observe([m],3.);assert 'r2' in w['robots']
    nav=BodyNavigation(t,w);assert next(d for d in nav.details if d['id']=='r2')['margin_m']==.005
