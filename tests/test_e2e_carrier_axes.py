"""Coordinate invariance, causal wire, and actual pregrasp dispatch without physics."""
import copy,math
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_carrier_axes as ca
from harness.e2e_s3_route import compile_route,plan_from_route
from harness.e2e_dialogue import wire_route,route_contract
from harness.zone_study_contract import digest,ContractViolation
from tests.test_e2e_s3_route import fixture
from tests.test_e2e18_route_guard import goal,route
from harness.self_odom_grid import transform


def axis_route(angle):
    r,args=fixture();r['waypoints']=[[0.,0.],[.413,0.],[.413,.237]]
    r['route_hash']=digest({k:v for k,v in r.items() if k!='route_hash'})
    original=compile_route(r,**args)
    r['waypoints']=transform(r['waypoints'],[0.,0.,angle]).tolist()
    r['schema']=ca.ROUTE_SCHEMA;r['carrier_basis']=dict(yaw_rad=angle,center_m=r['waypoints'][0],rgb=args['observed'][0],rule=ca.RULE)
    r['route_hash']=digest({k:v for k,v in r.items() if k!='route_hash'})
    args['source']='own_map'
    return r,args,original


@pytest.mark.parametrize('angle',[.31,math.pi/4,-2.1])
def test_compiler_rotates_metric_path_but_preserves_opposed_body_commands(angle):
    r,args,old=axis_route(angle);p=compile_route(r,**args)
    assert p['length_m']==pytest.approx(old['length_m'])
    assert np.asarray(p['command_waypoints'])==pytest.approx(np.asarray(old['waypoints']))
    assert np.asarray(p['waypoints'])==pytest.approx(np.asarray(r['waypoints']))
    for a,b in zip(old['legs'],p['legs']):
        assert a['axis']==b['axis'] and a['plans']==b['plans']
    assert plan_from_route(None,p)['route']==p['command_waypoints']
    contract=dict(kind='OwnRoute',route=wire_route(r),source_message_id=None)
    assert route_contract(contract)==contract
    contract['route']['carrier_basis']['yaw_rad']+=.1
    with pytest.raises(ContractViolation,match='HASH'):route_contract(contract)


def test_forged_or_unobserved_basis_fails_real_contract():
    r,args,_=axis_route(.4);r['carrier_basis']['rgb']={**r['carrier_basis']['rgb'],'sha256':'b'*64}
    r['route_hash']=digest({k:v for k,v in r.items() if k!='route_hash'})
    with pytest.raises(ContractViolation,match='UNOBSERVED'):compile_route(r,**args)


def test_real_goal_route_arbitrary_beam_heading_and_default_off():
    g=goal()
    with pytest.raises(ContractViolation,match='BEAM_ALIGNMENT'):route(g,math.pi/4)
    g.e2e_carrier_axes='beam_v1';p=route(g,math.pi/4)
    assert p['route']['schema']==ca.ROUTE_SCHEMA
    assert p['compiled']['carrier_basis']['yaw_rad']==pytest.approx(math.pi/4)
    assert p['route']['waypoints'][-1]==pytest.approx([2.,0.])
    assert route_contract(p['proposal'])==p['proposal']


def test_independent_private_frames_produce_same_physical_role_stations():
    ref=dict(robot_id='r1',frame_id=1,t_sim=0.,sha256='a'*64)
    beam=dict(rgb=ref,pose_own_m=[1.,2.,.7]);target=[3.,4.]
    for rid in ('r1','r2'):
        station,grip,b=ca.station(beam,target,rid)
        for tf in ([3.,-2.,1.1],[-1.,.4,-.9]):
            moved=dict(rgb=ref,pose_own_m=[*transform([beam['pose_own_m'][:2]],tf)[0],beam['pose_own_m'][2]+tf[2]])
            s2,g2,_=ca.station(moved,transform([target],tf)[0],rid)
            assert s2[:2]==pytest.approx(transform([station[:2]],tf)[0])
            assert g2==pytest.approx(transform([grip],tf)[0])
            assert math.cos(s2[2])==pytest.approx(math.cos(station[2]+tf[2]))
    a,_,_=ca.station(beam,target,'r1');b,_,_=ca.station(beam,target,'r2')
    assert abs(math.atan2(math.sin(a[2]-b[2]),math.cos(a[2]-b[2])))==pytest.approx(math.pi)


def test_approach_hands_fresh_correct_end_to_real_servo_only_after_settle():
    from harness.e2e_carrier_approach import advance
    from harness.owncam_pair_beam_v2 import pose_of
    g=goal();beam=dict(rgb=dict(frame_id=10,t_sim=2.),pose_own_m=[0.,0.,0.],grip_base_m=[.2032,0.],axis_heading_rad=0.)
    s,_,_=ca.station(beam,[2.,0.],'r1');g.explorer.local_pose=s
    r=SimpleNamespace(goal=g,beam=beam,last_obs={'frame_id':10},servo=pose_of('inspect'),nav_command={'kind':'hold'})
    tr=SimpleNamespace(robots={'r1':r},approach={},_poses=lambda *a:None,align={'r1':SimpleNamespace(gate=SimpleNamespace(until=0.))},dev_light=True)
    ok,actions=advance(tr,'r1',2.);assert ok and not actions and r.carrier_approach['correct_end']
    tr.approach['r1']['motion_until']=2.;r.last_obs['frame_id']=11;beam['rgb']['t_sim']=2.1
    ok,actions=advance(tr,'r1',2.1);assert not ok and actions==[{'kind':'hold'}]
    r.last_obs['frame_id']=12;beam['rgb']['t_sim']=2.6
    assert advance(tr,'r1',2.6)[0]


def test_registered_carrier_axes_and_approach():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    b=bundle('a'*40,61004,'study_gemma4_31b_v1',**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1')
    assert b['execution_bundle_id']=='e2e18-v224';require_current(b,ROOT)
    b['e2e_options']['carrier_approach']='off'
    with pytest.raises(ValueError,match='CARRIER'):require_current(b,ROOT)



def test_pregrasp_uses_real_calibrated_rpp_command_on_private_map():
    from harness.e2e_carrier_approach import advance
    from harness.active_camera import SEARCH
    from pathlib import Path
    import json
    g=goal();g.explorer.local_pose=np.array([-1.,0.,0.]);g.explorer.latest={}
    g.explorer.navigator=SimpleNamespace(plan_to=lambda cm,pose,target:[pose[:2].tolist(),list(target)])
    b=dict(rgb=dict(frame_id=10,t_sim=2.),pose_own_m=[0.,0.,0.],grip_base_m=[.73,0.],axis_heading_rad=0.)
    r=SimpleNamespace(goal=g,beam=b,last_obs={'frame_id':10},servo=dict(SEARCH),nav_command={'kind':'hold'})
    profiles=json.loads(Path('configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    tr=SimpleNamespace(robots={'r1':r},approach={},_poses=lambda *a:None,align={'r1':SimpleNamespace(gate=SimpleNamespace(until=0.))},dev_light=True,profiles=profiles,event=lambda *a,**kw:None)
    fine,actions=advance(tr,'r1',2.)
    assert not fine and actions[0]['kind']=='mecanum' and actions[0]['forward']>0
    assert actions[0]['duration_s']==.1 and r.carrier_approach['rpp']['path_follow']=='rpp_v1'
