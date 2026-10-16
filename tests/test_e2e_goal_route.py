"""Offline own-input integration: synthetic images/grids, no world or renderer."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from harness import e2e_goal_route as m
from harness import e2e_rgb_gate as rgbgate
from harness.e2e_own_inputs import Agreement, FORBIDDEN
from harness.e2e_covariance import inflate
from harness.zone_study_contract import ContractViolation
from harness.own_map_navigation import ObservedGrid
from harness.active_camera import SEARCH
from tests.test_e2e_s3_route import fixture as pulse_fixture


def ref(i):return dict(robot_id='r1',frame_id=i,t_sim=1.+i*.1,sha256=f'{i:064x}')

def texture():
    # Repeatable high-texture floor image for real ORB + RANSAC, not a rendered scene.
    rng=np.random.default_rng(9101)
    return rng.integers(0,256,(240,320,3),dtype=np.uint8)


def controller(**options):
    goal=SimpleNamespace(observe=lambda *a,**kw:([],None,{}),detector=lambda *a,**kw:([],None,{}))
    grid=ObservedGrid('r1',.1)
    cells=[(x/10+.05,y/10+.05) for x in range(-12,43) for y in range(-15,16)]
    for i in (1,2,3):grid.observe(robot_id='r1',frame_id=i,pose=[0,0,0],floor_xy=cells)
    explorer=SimpleNamespace(robot_id='r1',started=0.,goal=goal,grid=grid,map_to_odom=np.zeros(3),
        local_pose=np.zeros(3),memory=SimpleNamespace(self_map=SimpleNamespace(odom=SimpleNamespace(covariance=np.eye(3)*1e-6))))
    c=m.attach(m.GoalRoute(explorer),**options)
    if options:
        from tests.test_own_traversal_graph import sample
        c.graph.observe(sample(1))
        c.e2e_observed=[ref(i) for i in (1,2,3)]
        c._entity('B',[2.,0.],1.1,1,ref(1)['sha256'])
        f=rgbgate.features(texture())
        b=dict(center=[2.,0.],polygon=[[1.6,-.7],[2.4,-.7],[2.4,.7],[1.6,.7]],complete=True)
        c.e2e_gate.references['B']=dict(ref=ref(1),features=f,boundary=b)
        c.e2e_gate.current=dict(ref=ref(3),features=f,boundary=b,pose=[0,0,0],covariance=np.eye(3)*1e-6)
    return c


def ready(route_hash,epoch=2,seg=0):
    a=Agreement();a.propose(route_hash,'msg',delivered_ids={'msg'})
    a.approve(route_hash,'msg',robot_id='r2',response_id='approve',model_response_ids={'approve'})
    a.begin_epoch(order_id='order-5',route_hash=route_hash,grip_epoch=epoch,seg=seg)
    for rid in ('r1','r2'):
        for kind in ('GO','ACK'):
            response=rid+kind
            a.vote(rid,kind,a.key,response_id=response,model_response_ids={response})
    return a


def test_every_toggle_off_identity_and_frozen_nees_no_gt_channel():
    marker=object();assert m.attach(marker) is marker
    assert m.attach_setdown_gate(marker,None,agreement=None,observation=None) is marker
    assert inflate(marker) is marker
    profile=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    p=np.array([[.01,.001,.002],[.001,.02,.003],[.002,.003,.03]])
    actual=np.array(inflate(p,option=m.NEES,profile=profile))
    assert actual[:2,:2]==pytest.approx(p[:2,:2]*profile['xy_scale'])
    assert actual[2,2]==p[2,2] and np.linalg.eigvalsh(actual).min()>0
    c=controller(covariance_inflation=m.NEES,covariance_profile=profile)
    assert c.pose_covariance()==c.pose_covariance() # view; no repeated accumulation
    assert c.explorer.memory.self_map.odom.covariance[0,0]==1e-6
    with pytest.raises(ContractViolation):inflate(p,option=m.NEES,profile={**profile,'truth':[]})
    with pytest.raises(ContractViolation):inflate(np.diag([-1.,1.,1.]),option=m.NEES,profile=profile)


def test_real_goalroute_memory_to_observed_corridor_to_s3_no_static_reader():
    c=controller(own_route=m.OPTION)
    packet=c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    assert packet['route']['waypoints'][-1]==[2.,0.]
    assert packet['route']['B_rgb_sources']==[ref(1)]
    assert packet['s3_plan']['route'][-1]==[2.,0.]
    assert packet['compiled']['source']=='own_map' and packet['inputs']['provider']['robot_id']=='r1'
    assert not packet['inputs']['transport_admitted']
    assert set(packet['s3_plan'])=={'route','checkpoint_segments','own_route','registered_route_source','agreement_route_hash'}
    c.entities['B']['center_m']=[1.5,.3]
    moved=c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    assert moved['route']['waypoints'][-1]==[1.5,.3]
    assert moved['route']['route_hash']!=packet['route']['route_hash']


@pytest.mark.parametrize('bad',('missing_B','peer','stale','unknown_grid','uncertain','GT'))
def test_provider_rejects_missing_provenance_or_unobserved_geometry(bad):
    c=controller(own_route=m.OPTION);beam=dict(rgb=ref(3),pose_own_m=[0.,0.,0.])
    if bad=='missing_B':del c.entities['B']
    elif bad=='peer':beam['rgb']['robot_id']='r2'
    elif bad=='stale':beam['rgb']=ref(1)
    elif bad=='unknown_grid':c.explorer.grid=ObservedGrid('r1')
    elif bad=='uncertain':c.explorer.memory.self_map.odom.covariance=np.eye(3)*100
    elif bad=='GT':beam['eval_only']={'B_coordinates':[2.,0.]}
    with pytest.raises((ContractViolation,ValueError)):
        c.route_to_B(beam,now=1.6 if bad=='stale' else 1.3,profiles=pulse_fixture()[1]['profiles'])


@pytest.mark.parametrize('key',sorted(FORBIDDEN))
def test_gt_and_static_inputs_rejected_before_goalroute_frontend(key):
    c=controller(own_route=m.OPTION)
    with pytest.raises(ContractViolation,match='PRIVILEGED'):
        c.receive(robot_id='r1',t=1.4,frame_id=4,rgb=texture(),servo=SEARCH,observation={key:[]},frame_sha256=ref(4)['sha256'])


def test_actual_orb_ransac_accepts_geometry_but_rejects_aliased_descriptors():
    image=texture();f=rgbgate.features(image)
    shifted=cv2.warpPerspective(image,np.array([[1.,0.,3.],[0.,1.,4.],[0.,0.,1.]]),(320,240))
    assert rgbgate.geometric_match(f,rgbgate.features(shifted))['accepted']
    bad=copy.deepcopy(f);bad['points']=np.random.default_rng(5).uniform(0,200,bad['points'].shape).astype(np.float32)
    assert not rgbgate.geometric_match(f,bad)['accepted']
    assert not rgbgate.geometric_match(f,rgbgate.features(np.zeros_like(image)))['accepted']


def test_three_fresh_frames_uncertainty_and_start_geometry_are_required():
    c=controller(arrival_gate=m.RGB);g=c.e2e_gate
    g.references['start']=copy.deepcopy(g.references['B'])
    g.current['pose']=[2.,0.,0.]
    for i in (4,5,6):
        g.current['ref']=ref(i)
        result=g.verify('B',now=ref(i)['t_sim'],target=[2.,0.])
        assert result['accepted']==(i==6)
        # Reusing an exact frame cannot supply the remaining temporal evidence.
        assert g.verify('B',now=ref(i)['t_sim'],target=[2.,0.])['accepted']==(i==6)
    assert not g.verify('B',now=3.,target=[2.,0.])['accepted']
    g.current['ref']=ref(7);g.current['covariance']=np.eye(3)
    assert not g.verify('B',now=1.7,target=[2.,0.])['accepted']
    g.current['covariance']=np.eye(3)*1e-6
    assert not g.verify('start',now=1.7,target=[2.,0.],geometry_confirmed=False)['accepted']
    g.current['boundary']=None
    assert not g.verify('B',now=1.7,target=[2.,0.])['accepted']


def test_reinspection_changes_route_revokes_epoch_and_requires_full_beam_inside(monkeypatch):
    c=controller(own_route=m.OPTION,setdown_reobserve=m.SETDOWN)
    profiles=pulse_fixture()[1]['profiles']
    packet=c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=profiles)
    a=ready(packet['proposal']['route']['route_hash'],epoch=2,seg=len(packet['compiled']['legs'])-1)
    # Fresh RGB boundary moved by .1 m; only its current object can become an endpoint.
    b=copy.deepcopy(c.e2e_gate.current['boundary']);b['center']=[2.1,0.];b['polygon']=[[1.7,-.7],[2.5,-.7],[2.5,.7],[1.7,.7]]
    c.e2e_gate.current['boundary']=b
    for i in (4,5,6):
        c.e2e_observed.append(ref(i));c.e2e_gate.current['ref']=ref(i)
        result=c.reobserve_setdown(packet,dict(rgb=ref(i),pose_own_m=[2.,0.,0.]),now=ref(i)['t_sim'],profiles=profiles,agreement=a)
        assert result['status']==('REAPPROVAL_REQUIRED' if i==6 else 'WAIT_OWN_RGB_BOUNDARY')
    pending=result['pending_route'];h=pending['proposal']['route']['route_hash'];seg=len(pending['compiled']['legs'])-1
    assert h!=packet['proposal']['route']['route_hash'] and not a.ready and a.key is None
    assert pending['route']['waypoints'][-1]==[2.1,0.]
    assert not result['allow_lower']
    again=c.reobserve_setdown(packet,dict(rgb=ref(6),pose_own_m=[2.,0.,0.]),now=1.6,profiles=profiles,agreement=a)
    assert again['pending_route']['proposal']['route']['route_hash']==h
    footprint=dict(rgb=ref(6),polygon_own_m=[[1.8,-.4],[2.4,-.4],[2.4,.4],[1.8,.4]])
    kw=dict(now=1.6,order_id='order-5',seg=seg)
    assert not c.setdown_ready(footprint,agreement=ready(h,2,seg),grip_epoch=2,**kw)
    a=ready(h,3,seg)
    assert c.setdown_ready(footprint,agreement=a,grip_epoch=3,**kw)
    assert not c.setdown_ready({**footprint,'rgb':ref(5)},agreement=a,grip_epoch=3,**kw)
    outside=copy.deepcopy(footprint);outside['polygon_own_m'][0]=[1.69,0.]
    assert not c.setdown_ready(outside,agreement=a,grip_epoch=3,**kw)
    calls=[];ctl=SimpleNamespace(rid='r1',seg=seg,v3_plan=pending['s3_plan'],_wait_lower=lambda *a:calls.append('lower'),
        port=SimpleNamespace(hold=lambda t:calls.append('hold')),log=lambda *a,**k:None)
    ep=SimpleNamespace(controller=ctl)
    m.attach_setdown_gate(ep,c,agreement=a,observation=lambda now:dict(footprint=footprint,order_id='order-5',grip_epoch=3,seg=seg),option=m.SETDOWN)
    ctl._wait_lower(1.6,True);assert calls==['lower']
    ctl.v3_plan=packet['s3_plan'];ctl.seg=len(ctl.v3_plan['route'])-2
    ctl._wait_lower(1.6,True);assert calls[-1]=='hold'


def test_boundary_detects_actual_rgb_edges_markers_and_rejects_clipping(monkeypatch):
    # Pure pinhole fixture: camera calibration and body mask are fixed inputs,
    # while edge/marker extraction and projection are the real implementation.
    monkeypatch.setattr(rgbgate,'goal_camera',lambda *a:(np.array([0.,0.,1.]),np.diag([1.,-1.,-1.])))
    monkeypatch.setattr(rgbgate,'project_envelopes',lambda *a:np.zeros((240,320),bool))
    image=np.zeros((240,320,3),np.uint8)
    cv2.rectangle(image,(60,60),(260,200),(0,0,255),-1)
    for x in (100,160,220):cv2.rectangle(image,(x-5,120),(x+5,130),(255,255,255),-1)
    found=rgbgate.boundary(image,SEARCH,[0,0,0]);assert found and found['white_markers']==3
    assert len(found['polygon'])==4
    image[:,0:70]=[0,0,255]
    assert rgbgate.boundary(image,SEARCH,[0,0,0]) is None


def test_s4_compact_approval_binds_full_private_s3_plan_and_no_comm_stays_closed():
    from harness.e2e_dialogue import route_contract
    c=controller(own_route=m.OPTION)
    packet=c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    proposal=route_contract(packet['proposal'])
    assert proposal['route']['route_hash']!=packet['route']['route_hash']
    for a in (Agreement(),ready(packet['route']['route_hash'])):
        with pytest.raises(ContractViolation):m.provider_plan(packet,agreement=a,now=1.3,observed=c.e2e_observed,profiles=pulse_fixture()[1]['profiles'])
    a=ready(proposal['route']['route_hash'])
    assert m.provider_plan(packet,agreement=a,now=1.3,observed=c.e2e_observed,profiles=pulse_fixture()[1]['profiles'])==packet['s3_plan']
    c.entities['B']['center_m']=[1.5,0.]
    newer=c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    with pytest.raises(ContractViolation):m.provider_plan(newer,agreement=a,now=1.3,observed=c.e2e_observed,profiles=pulse_fixture()[1]['profiles'])


def test_real_declaration_hooks_log_verdict_and_require_current_geometry(monkeypatch):
    c=controller(arrival_gate=m.RGB)
    assert not c.arrival_evidence('B',1.3,3,[0.,0.,0.],True)
    assert c.events[-1]['reason']=='e2e_B_declaration_gate'
    monkeypatch.setattr(c.graph,'match',lambda *a:dict(status='rejected'))
    assert not c.return_evidence(dict(t=1.3),True)
    assert c.events[-1]['reason']=='e2e_return_declaration_gate'


def test_mutated_private_payload_and_compiled_plan_cannot_reuse_approval():
    from harness.zone_study_contract import digest
    c=controller(own_route=m.OPTION)
    packet=c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    a=ready(packet['proposal']['route']['route_hash'])
    for change in ('private_hash','compiled','source'):
        bad=copy.deepcopy(packet)
        if change=='private_hash':bad['route']['own_map']['pose']['mean'][0]=.1
        elif change=='source':bad['compiled']['source']='test_route_provider'
        else:
            bad['compiled']['waypoints'][-1]=[4.6,-2.1]
            bad['compiled']['plan_hash']=digest({k:v for k,v in bad['compiled'].items() if k!='plan_hash'})
        with pytest.raises(ContractViolation):
            m.provider_plan(bad,agreement=a,now=1.3,observed=c.e2e_observed,profiles=pulse_fixture()[1]['profiles'])


def test_prepared_plan_never_authorizes_execution_and_stays_within_azure_budget():
    options=json.loads(Path('configs/e2e_stage2_options_v1.json').read_text())
    assert set(options.values())=={'off'}
    p=json.loads(Path('experiments/2026-10-11-e2e-stage2-offline/azure-plan.json').read_text())
    assert not p['physical_execution_authorized'] and p['status']=='PREPARED_NOT_SUBMITTED'
    assert p['N']==len(p['runs'])==48 and len({tuple(r.values()) for r in p['runs']})==48
    assert p['server']['max_concurrent']*p['server']['cpu_per_run_estimate']<p['server']['vcpu']*.8
