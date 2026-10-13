import copy
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import e2e_post_relook as m
from harness.e2e_relook_giveup import giveup


def fixture(mode):
    events=[];emit=lambda x:events.append(x)
    goals={r:NS(e2e_relook=NS(pending={'node':4,'matches':[]},receipt=None,emit=emit),
                pose_covariance=lambda:np.eye(3),setdown_ready=lambda *a,**k:True) for r in ['r1','r2']}
    d=NS(approved=True,claims={'r1','r2'},proposal={'route':{'route_hash':'a'*64}},
         key=('order-5','a'*64,1,0),votes={'r1':{'GO':{}},'r2':{'ACK':{}}})
    d.allowed=lambda key,now:False
    tr=NS(dev_light=True,post_relook_mode=mode,state='relook',stage_t=10.,seg=0,first_seg=0,epoch=1,
          plan={'agreement_route_hash':'a'*64,'own_route':{'legs':[{},{}]}},dialogue=d,
          robots={r:NS(goal=g,packet={}) for r,g in goals.items()},aligned={'r1':{},'r2':{}},
          approach={'r1':{}},permit=('old',),align={r:NS(streak=2,last_frame=3,chosen={}) for r in goals},done=False)
    tr.event=lambda now,event,**kw:events.append(dict(t=now,event=event,**kw))
    tr.set=lambda state,now:setattr(tr,'state',state)
    tr._lower=lambda now:None;tr._after_carry=lambda now:events.append({'event':'original_after_carry'})
    tr._open_epoch=lambda now:events.append({'event':'open_epoch','seg':tr.seg})
    tr.events=events
    return m.install(tr,mode)


def test_retains_remaining_route_but_revokes_old_votes_and_fresh_alignment():
    tr=fixture('retain_route_v1');plan=tr.plan
    giveup(tr,70.)
    assert tr.plan is plan and tr.seg==1 and tr.state=='align'
    assert tr.dialogue.approved and tr.dialogue.claims=={'r1','r2'}
    assert tr.dialogue.key is None and tr.dialogue.votes=={} and tr.aligned=={}
    assert all(s.streak==0 and s.last_frame is None for s in tr.align.values())
    assert all(r.goal.e2e_relook.receipt is None for r in tr.robots.values())
    from harness.e2e_live_transport import Transport
    assert not Transport._carry(tr,70.)  # the real carry entry rejects missing current GO/ACK


def test_final_task_skip_requires_original_final_lower_permission_key():
    tr=fixture('retain_route_v1');tr.seg=1
    giveup(tr,70.);assert not tr.done and tr.state=='mapping'
    tr=fixture('retain_route_v1');tr.seg=1
    tr.post_relook_final_permission={'key':['other'], 't':20.}
    giveup(tr,70.);assert not tr.done
    tr=fixture('retain_route_v1');tr.seg=1
    tr.post_relook_final_permission={'key':list(tr.dialogue.key),'t':20.}
    giveup(tr,70.);assert tr.done and tr.state=='done'
    assert all(r.goal.e2e_relook.receipt is None for r in tr.robots.values())


def test_final_permission_cannot_be_minted_from_intermediate_lower():
    tr=fixture('carry_through_v1');tr.state='lower_open'
    tr.dialogue.allowed=lambda key,now:True
    tr._lower(15.);assert not hasattr(tr,'post_relook_final_permission')
    tr.state='final_lower_go_ack';tr._lower(16.)
    assert not hasattr(tr,'post_relook_final_permission')
    tr.robots['r1'].goal.setdown_ready(agreement=NS(key=tr.dialogue.key),now=16.)
    tr._lower(16.)
    assert tr.post_relook_final_permission['key']==list(tr.dialogue.key)


def test_carry_through_preserves_final_observation_and_asks_new_epoch(monkeypatch):
    tr=fixture('carry_through_v1');monkeypatch.setattr(m,'boundary_reasons',lambda *a:['covariance_limit'])
    tr._after_carry(20.);assert tr.seg==1 and tr.events[-1]=={'event':'open_epoch','seg':1}
    tr._after_carry(21.);assert tr.events[-1]['event']=='original_after_carry'


def test_current_parent_registration_and_default_off(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    kw={};args=[]
    def captured(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',captured)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1')
    for mode,v in m.VERSIONS.items():
        b=bundle(*args,**kw,post_relook=mode);assert b['execution_bundle_id']==f'e2e18-v{v}'
        require_current(b,ROOT)
        bad=copy.deepcopy(b);bad['e2e_options']['dev_light']=False
        with pytest.raises(ValueError):require_current(bad,ROOT)
    assert m.install(object(),'off') is not None


def test_nominal_dev_margin_keeps_fresh_rgb_agreement_and_whole_outline(monkeypatch):
    from harness import e2e_goal_route as route
    monkeypatch.setattr(route,'wire_route',lambda r:{'route_hash':'b'*64})
    ref=dict(robot_id='r1',frame_id=3,t_sim=1.,sha256='a'*64)
    covariance=np.diag([.1,.1,.1]);events=[]
    boundary=dict(center=[0.,0.],polygon=[[-.4,-.4],[.4,-.4],[.4,.4],[-.4,.4]])
    goal=NS(e2e_options={'setdown_reobserve':'boundary_reobserve_v1'},
        e2e_pending_setdown=dict(packet=dict(compiled={'legs':[{}]},route={}),previous_epoch=1,boundary_center=[0.,0.]),
        e2e_observed=[ref],e2e_gate=NS(current=dict(ref=ref,boundary=boundary),verify_boundary=lambda now:{'accepted':True}),
        pose_covariance=lambda:covariance,event=lambda *a,**k:events.append((a,k)))
    footprint=dict(rgb=ref,polygon_own_m=[[-.3,-.025],[.3,-.025],[.3,.025],[-.3,.025]])
    kwargs=dict(now=1.,agreement=NS(ready=True,key=('order-5','b'*64,2,0)),order_id='order-5',grip_epoch=2,seg=0)
    ready=lambda f,**k:route.IntegratedGoalRoute.setdown_ready(goal,f,**k)
    assert not ready(footprint,**kwargs)
    goal.e2e_dev_nominal_setdown=True
    assert ready(footprint,**kwargs) and events and np.array_equal(covariance,np.diag([.1,.1,.1]))
    assert not ready(footprint,**dict(kwargs,now=1.3))
    assert not ready(footprint,**dict(kwargs,agreement=NS(ready=True,key=('wrong','b'*64,2,0))))
    outside=copy.deepcopy(footprint);outside['polygon_own_m'][0][0]=-.5
    assert not ready(outside,**kwargs)
