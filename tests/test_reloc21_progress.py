import math
from types import SimpleNamespace

import pytest

from harness.reloc20_motion import LoadedRoute
from harness.reloc21_progress import RouteProgress, install, shortcut


def carry():
    static=dict(bounds_m=[-3,3,-3,3],obstacles=[])
    c=SimpleNamespace(static=static,reloc20_route=LoadedRoute(static),reloc20_heading=True,
        region=dict(center_m=[2,0],half_extents_m=[.5,.5]),
        obstacles=SimpleNamespace(discs=lambda t:[]),loc=SimpleNamespace(pose=[-2.,0.,0.]),
        advance_m=.15,grip_xy=(.2,0),slot=None,goal=None,path=None)
    return c


def test_off_does_not_install_or_modify_legacy_path():
    c=carry();old=c.path;install(c,{})
    assert not hasattr(c,'reloc21_nav') and c.path is old


def test_far_visible_target_persists_while_start_changes():
    c=carry();nav=RouteProgress(c);assert nav.select(0,c.grip_xy)
    target=nav.target;plans=nav.plans
    for i in range(1,20):
        c.loc.pose[0]+=.01
        drive,arrived,error=nav.step(i*.1)
        assert nav.target==target and nav.plans==plans
        assert drive[1]==0 and not arrived and error is None


def test_shortcut_never_cuts_loaded_wall_corner():
    c=carry();c.static['obstacles']=[dict(id='wall',center_m=[0,0],half_extents_m=[.1,.5])]
    r=LoadedRoute(c.static);path=r.plan((-2,0),(2,0),c.static['bounds_m'],[])
    simple=shortcut(r,path,[])
    assert len(simple)>2
    assert all(r.segment(a,b,[])[0] for a,b in zip(simple,simple[1:]))


def test_same_failed_choice_is_removed_on_third_sim_opportunity():
    c=carry();nav=RouteProgress(c);assert nav.select(0,c.grip_xy);key=tuple(c.slot)
    context=dict(blocked_object='wall',minimum_gap_m=-.01,gap_scope='strict_enclosure')
    nav.failed(0,'blocked',context);nav.failed(.1,'blocked',context)
    assert nav.failures[key]==1 and key not in nav.excluded
    nav.failed(1,'blocked',context);nav.failed(2,'blocked',context)
    assert key in nav.excluded
    assert nav.select(3,c.grip_xy) and tuple(c.slot)!=key
    assert all(e['blocked_object'] for e in nav.events if e['event'].startswith('candidate_'))


def test_progress_resets_failed_choice_count():
    c=carry();nav=RouteProgress(c);nav.select(0,c.grip_xy)
    context=dict(blocked_object='wall',minimum_gap_m=-.01,gap_scope='strict_enclosure')
    nav.failed(0,'blocked',context);nav.failed(1,'blocked',context)
    c.loc.pose[0]+=.03;nav.failed(2,'blocked',context)
    assert not nav.excluded


def test_complete_plan_scores_all_five_slots_and_checks_advance_retreat():
    c=carry();nav=RouteProgress(c,complete=True);assert nav.select(0,c.grip_xy)
    assert len(nav.selection)==5 and all(x['accepted'] for x in nav.selection)
    accepted=min(nav.selection,key=lambda x:x['estimated_command_s'])
    assert tuple(c.slot)==tuple(accepted['slot'])
    assert nav.record()['slot_candidates']==5


def test_final_heading_and_arrival_keep_existing_tolerances():
    c=carry();nav=RouteProgress(c);nav.select(0,c.grip_xy)
    c.loc.pose=[*c.goal,.1]
    drive,arrived,error=nav.step(0)
    assert drive[2]<0 and not arrived and error is None
    c.loc.pose[2]=0
    assert nav.step(1)==((0.,0.,0.),True,None)


def test_incomplete_dependencies_fail_closed():
    c=carry();c.reloc20_route=None
    with pytest.raises(ValueError):install(c,dict(reloc21_route_progress_v1=True))
    with pytest.raises(ValueError):install(c,dict(reloc21_complete_plan_v1=True))
