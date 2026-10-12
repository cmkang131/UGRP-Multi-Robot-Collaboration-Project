"""Own RGB/real CSM + particle correction and real HIGH/SigmaRefix handlers; no physics."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import e2e_setdown_relook as m
from harness.e2e_s3_route import compile_route,plan_from_route
from harness.zone_study_contract import ContractViolation,digest
from harness.zone_pair_highpose_runtime import HighController
from harness.zone_pair_highpose_refix import SigmaRefix
from harness.self_map_rbpf import RaoBlackwellizedGrid
from harness.own_traversal_graph import TraversalGraph,own_sample
from tests.test_e2e_goal_route import texture,ready,controller
from tests.test_e2e_s3_route import fixture


def route(points=((0,0),(.2,0),(.4,0)),walls=()):
    r,args=fixture();r['waypoints']=[list(p) for p in points]
    r['own_map']['walls']=list(walls)
    r['route_hash']=digest({k:v for k,v in r.items() if k!='route_hash'})
    # Actual frozen S3 calibration magnitudes, mirrored endpoints.
    for p in args['profiles'].values():
        i=0 if p['axis']=='forward' else 1
        p['mean_delta'][i]=np.sign(p['u'])*(.012938721811341378 if i==0 else .16694529519717285)
    return r,args


def compiled(points=((0,0),(.2,0),(.4,0))):
    r,args=route(points)
    return compile_route(r,**args,setdown_only_when_relook=m.OPTION)


def own_goal(rid='r1'):
    """Small own frame producer using the actual RBPF facade and graph matcher."""
    g=RaoBlackwellizedGrid(rid,correction_options={'particles':30})
    class Goal:
        robot_id=rid
        def __init__(self):
            self.graph=TraversalGraph(rid);self.offsets=[]
            self.explorer=NS(memory=NS(self_map=g),local_pose=g.odom.pose)
        def pose_covariance(self):return g.odom.covariance.tolist()
        def _localize(self,sample,t):pass
        def receive(self,**kw):
            sample=own_sample(dict(t=kw['t'],frame_id=kw['frame_id'],local_pose=g.odom.pose),
                kw['observation'],rgb=kw['rgb'],frame_sha256=kw['frame_sha256'],covariance=g.odom.covariance)
            self._localize(sample,kw['t'])
            if not self.graph.sealed:self.graph.observe(sample)
            return {'kind':'hold'},sample
    return Goal()


def frame(goal,i,t,*,image=None,segments=True):
    return goal.receive(robot_id=goal.robot_id,t=t,frame_id=i,frame_sha256=f'{i:064x}',
        rgb=texture() if image is None else image,servo={},
        observation=dict(segments=[[[1.,-1.],[1.,1.]],[[1.,1.],[-1.,1.]]] if segments else [],camera=[0.,0.]))


class NativeBoundary(SigmaRefix,HighController):
    def __init__(self,p):
        self.rid='r1';self.seg=0;self.grip_epoch=2;self.high_ready=True;self.state='wait_lower'
        self.segments=p['legs'];self.v3_plan=plan_from_route(None,{**p,'source':'own_map','plan_hash':digest({**{k:v for k,v in p.items() if k!='plan_hash'},'source':'own_map'})})
        self.v3_plan['agreement_route_hash']='a'*64
        self.events=[];self.arm=NS(until=0.)
        self.arm.queue=lambda *a,**kw:setattr(self.arm,'until',a[1]+kw['duration']+kw['settle'])
        self.beam_grasp_receipt={'segment':0};self.issued={1:1500,6:1500}
        self.port=NS(hold=lambda t:self.events.append(('hold',t)),own=NS(pose=NS(begin_relocalization=lambda *a:None)))
        self._cp_open=lambda t,idle:self.events.append(('regrasp',t))
        self._released=lambda t,idle:self.events.append(('done',t))
        self._wait_carry=lambda t,idle:self.events.append(('carry',t))
        self.schedule=[(0.,1.,{})]
    def log(self,rid,event,t,**kw):self.events.append((event,t,kw))
    def _issued(self):return self.issued
    def held_by_command(self):return self.issued[1]<2000
    def fail(self,reason,t):self.events.append(('fail',reason))
    def set(self,state,t):self.state=state
    def _wait(self,barrier,state,t,go):go(t);self.state=state
    def _start_transit(self,*args):self.events.append(('lower',args));self.transit=None
    def _refix_sigma(self):return {}
    def _enter_decide(self,t):self.state='refix_decide'


def endpoint(points=((0,0),(.2,0),(.4,0))):
    ctl=NativeBoundary(compiled(points));a=ready('a'*64);goal=own_goal()
    m.attach(NS(controller=ctl),goal,agreement=a,option=m.OPTION)
    return ctl,goal,a


def test_off_identity_and_closed_options():
    obj=object();assert m.attach(obj) is obj
    with pytest.raises(ContractViolation):m.attach(obj,option='maybe')
    r,args=route();base=compile_route(r,**args)
    assert base==compile_route(r,**args,setdown_only_when_relook='off')
    assert 'setdown_only_when_relook' not in base
    with pytest.raises(ContractViolation):controller(setdown_only_when_relook=m.OPTION)


def test_missing_grip_command_cannot_resume_even_with_current_agreement():
    ctl,g,a=endpoint();ctl.issued[1]=2000
    ctl._wait_carry(2,True)
    assert ctl.events[-1]==('fail','CONTINUATION_GRASP_COMMAND_REQUIRED')


def test_final_lower_cannot_skip_pre_setdown_own_b_rgb_gate():
    ctl,g,a=endpoint();ctl.seg=len(ctl.segments)-1
    ctl._wait_lower(2,True)
    assert ctl.events[-1]==('fail','FINAL_OWN_RGB_GATE_NOT_ATTACHED')
    assert not any(e[0]=='lower' for e in ctl.events)


def test_short_legs_keep_real_high_receipt_and_epoch_with_new_segment_go_required():
    ctl,g,a=endpoint()
    g.explorer.memory.self_map.pending_cov[:]=np.eye(3)*1e-6
    assert not ctl._own_request(1,2)['request']
    assert ctl.carry_decision('set_down',2)['own_status']=='NO_RELOOK_TRIGGER'
    ctl.refix_decided_seg=0 # same pair-OR continue result; real HIGH handler below
    ctl._wait_lower(2,True)
    assert ctl.seg==1 and ctl.grip_epoch==2 and ctl.high_ready
    assert ctl.beam_grasp_receipt['segment']==1
    assert not any(e[0] in ('lower','regrasp') for e in ctl.events)
    ctl._wait_carry(2.1,True);assert ctl.events[-1][0]=='hold'
    newer=ready('a'*64,epoch=2,seg=1);a.__dict__.update(newer.__dict__)
    ctl._wait_carry(2.2,True);assert ctl.events[-1][0]=='carry'


@pytest.mark.parametrize('points,reason',[
    (((0,0),(.4,0),(.85,0)),'measured_continuous_limit'),
    (((0,0),(.2,0),(.2,.2)),'unmeasured_axis_change')])
def test_no_unmeasured_long_or_changed_axis_continuation(points,reason):
    ctl,g,a=endpoint(points)
    assert reason in ctl._own_request(1,2)['named_checkpoints']
    ctl.seg=1;a.__dict__.update(ready('a'*64,seg=1).__dict__)
    ctl._wait_carry(2,True)
    assert ctl.events[-1]==('fail','CONTINUOUS_DISTANCE_UNMEASURED')


def test_covariance_final_and_own_wall_passage_causes():
    p=compiled()
    assert m.boundary_reasons(p,0,0,np.diag([.1,.1,.1]))==['covariance_limit']
    assert 'final_placement' in m.boundary_reasons(p,0,1,np.eye(3)*1e-6)
    r,args=route(points=((-2,0),(-1,0),(0,0),(1,0),(2,0)))
    r['own_map']['walls']=[dict(a=[0,.25],b=[0,1],sources=args['observed'])]
    result=m.narrow_boundaries(r,r['waypoints'])
    assert result=={'1':['before_narrow_passage'],'3':['after_narrow_passage']}
    r['own_map']['walls']=[];assert m.narrow_boundaries(r,r['waypoints'])=={}
    with pytest.raises(ContractViolation):m.covariance_over(np.eye(3)*float('nan'))


def test_real_csm_three_fresh_rgb_apply_particle_position_and_preserve_covariance():
    goal=own_goal();fix=m.OwnRGBRelook(goal)
    frame(goal,1,1.);goal.graph.seal()
    g=goal.explorer.memory.self_map;g.poses[:,0]=.08
    before=g.odom.pose[0];cov=g.odom.covariance.copy()
    fix.request(2.,seg=0,epoch=2)
    frame(goal,2,2.1);frame(goal,3,2.2)
    assert fix.receipt is None and g.odom.pose[0]==before
    frame(goal,4,2.3)
    assert fix.receipt is not None
    assert abs(g.odom.pose[0])<abs(before)
    assert fix.receipt['after']==list(g.odom.pose)
    assert len(fix.receipt['rgb'])==3 and not fix.receipt['covariance_reset']
    assert np.trace(g.odom.covariance)==pytest.approx(np.trace(cov))


@pytest.mark.parametrize('bad',('blank','no_metric','stale','peer','gt'))
def test_missing_visual_metric_freshness_or_own_input_never_mints_fix(bad):
    goal=own_goal();fix=m.OwnRGBRelook(goal);frame(goal,1,1.);goal.graph.seal();fix.request(2.,seg=0,epoch=2)
    if bad in ('peer','gt'):
        kw=dict(robot_id='r2' if bad=='peer' else 'r1',t=2.1,frame_id=2,frame_sha256='b'*64,rgb=texture(),servo={},observation={'truth':0} if bad=='gt' else {})
        with pytest.raises(ContractViolation):goal.receive(**kw)
    else:
        for i in range(2,5):
            frame(goal,i,1.+i*.1 if bad=='stale' else 2.+i*.1,
                image=np.zeros((240,320,3),np.uint8) if bad=='blank' else None,segments=bad!='no_metric')
    assert fix.receipt is None


@pytest.mark.parametrize('handler,complete', (('_cp_open','regrasp'),('_released','done')))
def test_real_rgb_correction_required_after_release_including_final_and_epoch_invalidation(handler,complete):
    ctl,goal,a=endpoint();frame(goal,1,1.);goal.graph.seal()
    g=goal.explorer.memory.self_map;g.poses[:,0]=.08
    getattr(ctl,handler)(2.,True)
    assert a.key is None and not a.votes
    getattr(ctl,handler)(2.1,True);assert ctl.events[-1][0]=='hold'
    for i in range(2,5):frame(goal,i,2.9+(i-2)*.1)
    getattr(ctl,handler)(3.2,True)
    assert ctl.events[-1][0]==complete
    assert any(e[0]=='e2e_pose_correction_applied' for e in ctl.events)
    assert any(e[0]=='e2e_setdown_relook_complete' for e in ctl.events)
    a.__dict__.update(ready('a'*64,epoch=2).__dict__)
    ctl._wait_carry(3.3,True);assert ctl.events[-1][0]=='hold'
    ctl.grip_epoch=3;a.__dict__.update(ready('a'*64,epoch=3).__dict__)
    ctl._wait_carry(3.4,True);assert ctl.events[-1][0]=='hold' # corrected pose cannot reuse old pulses
    plan=ctl.v3_plan['own_route'];plan['route_hash']='c'*64
    plan['plan_hash']=digest({k:v for k,v in plan.items() if k!='plan_hash'})
    ctl.v3_plan['agreement_route_hash']='d'*64
    a.__dict__.update(ready('d'*64,epoch=3).__dict__)
    ctl._wait_carry(3.5,True);assert ctl.events[-1][0]=='hold' # hash-only relabel cannot consume correction


def test_no_rgb_times_out_without_regrasp_and_no_comm_stays_closed():
    ctl,g,a=endpoint();ctl._cp_open(2.,True);ctl._cp_open(18.,True)
    assert ctl.events[-1]==('fail','OWN_RGB_POSITION_CORRECTION_TIMEOUT')
    a.approved=False;ctl._wait_carry(18.1,True);assert ctl.events[-1][0]=='hold'


def test_own_goal_provider_propagates_toggle_and_rejects_plan_mutation():
    from harness.e2e_goal_route import OPTION,provider_plan
    c=controller(own_route=OPTION,setdown_only_when_relook=m.OPTION)
    _,args=route();packet=c.route_to_B(dict(rgb=c.e2e_observed[-1],pose_own_m=[0,0,0]),now=1.3,profiles=args['profiles'])
    assert packet['compiled']['setdown_only_when_relook']==m.OPTION
    a=ready(packet['proposal']['route']['route_hash'])
    assert provider_plan(packet,agreement=a,now=1.3,observed=c.e2e_observed,profiles=args['profiles'])==packet['s3_plan']
    packet['compiled']['relook_boundaries']={}
    packet['compiled']['legs'][0]['command_distance_m']=0.
    with pytest.raises(ContractViolation):provider_plan(packet,agreement=a,now=1.3,observed=c.e2e_observed,profiles=args['profiles'])


def test_corrected_own_map_replans_actual_s3_trajectory_before_new_epoch_carry():
    from harness.e2e_goal_route import OPTION,provider_plan
    ctl,goal,a=endpoint();frame(goal,1,1.);goal.graph.seal()
    g=goal.explorer.memory.self_map;g.poses[:,0]=.08
    ctl._cp_open(2.,True)
    for i in range(10,13):frame(goal,i,2.9+(i-10)*.1)
    ctl._cp_open(3.2,True)
    c=controller(own_route=OPTION,setdown_only_when_relook=m.OPTION)
    c.e2e_relook=goal.e2e_relook
    c.explorer.memory.self_map=g;c.explorer.local_pose=np.array(g.odom.pose)
    c.e2e_observed+=copy.deepcopy(goal.e2e_relook.receipt['rgb'])
    _,args=route();beam=dict(rgb=c.e2e_observed[-1],pose_own_m=[float(g.odom.pose[0])+.1,0.,0.])
    packet=c.route_after_relook(beam,now=3.1,profiles=args['profiles'],agreement=a)
    assert packet['route']['own_map']['pose']['mean']==list(g.odom.pose)
    assert packet['compiled']['waypoints'][0]==beam['pose_own_m'][:2]
    assert not a.approved and a.key is None
    a.__dict__.update(ready(packet['proposal']['route']['route_hash'],epoch=3).__dict__)
    ctl.v3_plan=provider_plan(packet,agreement=a,now=3.1,observed=c.e2e_observed,profiles=args['profiles'])
    ctl.grip_epoch=3;ctl.seg=0;ctl.segments=[l['distance_m'] for l in packet['compiled']['legs']]
    ctl._wait_carry(3.3,True)
    assert ctl.events[-1][0]=='carry'
    assert c.events[-1]['reason']=='e2e_pose_correction_used_by_route'


def test_r2_corrected_map_needs_actual_received_r1_route_and_own_beam_alignment():
    goal=own_goal('r2');fix=m.OwnRGBRelook(goal);frame(goal,1,1.);goal.graph.seal()
    fix.request(2.,seg=0,epoch=2)
    for i in range(2,5):frame(goal,i,2.+i*.1)
    assert fix.receipt
    own_ref=fix.receipt['rgb'][-1];r,args=route()
    mapped=dict(robot_id='r2',frame='r2/own_start',map_version=2,
        pose=dict(mean=list(goal.explorer.local_pose),covariance=goal.pose_covariance(),sources=[own_ref]),
        walls=[],goal=None,sources=[own_ref])
    report=dict(schema='ugrp.e2e_peer_route.v1',sender='r1',recipient='r2',message_id='new-route',route=r,
        beam_alignment=dict(beam_ref='shared_visual_beam',own_rgb=own_ref,peer_rgb=args['observed'][0],
            own_beam_pose=[0.,0.,0.],peer_beam_pose=[0.,0.,0.],covariance=np.eye(3).tolist()))
    kw=dict(own_map=mapped,now=2.4,observed=[own_ref],profiles=args['profiles'])
    with pytest.raises(ContractViolation):m.peer_route_after_relook(goal,report,received_reports={},**kw)
    received={'new-route':dict(report_sha256=digest(report),delivered_at_sim_s=2.4)}
    p=m.peer_route_after_relook(goal,report,received_reports=received,**kw)
    assert fix.bound_plan_hash==p['compiled']['plan_hash']
    assert p['inputs']['provider']['goal'] is None
    bad=copy.deepcopy(mapped);bad['pose']['mean'][0]+=.1
    with pytest.raises(ContractViolation):m.peer_route_after_relook(goal,report,received_reports=received,**{**kw,'own_map':bad})


def test_azure_full_factorial_pairs_resources_and_unsubmitted():
    p=json.loads(Path('experiments/2026-10-11-e2e-stage2-offline/azure-plan.json').read_text())
    assert p['N']==48 and p['server']['vcpu']==16 and p['server']['max_concurrent']<=18
    assert len({(r['condition'],r['seed'],r['candidate']) for r in p['runs']})==24
    assert all({r['setdown_only_when_relook'] for r in p['runs'] if (r['condition'],r['seed'],r['candidate'])==key}=={'off','on_v1'} for key in {(r['condition'],r['seed'],r['candidate']) for r in p['runs']})
    assert p['time']['planned_waves']==3 and not p['physical_execution_authorized']
