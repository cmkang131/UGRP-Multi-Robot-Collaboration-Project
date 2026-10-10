import copy
import json
from types import SimpleNamespace
import pytest
from harness.e2e_s3_route import compile_route,plan_from_route
from harness.e2e_test_route_provider import provide,WAYPOINTS
from harness.zone_study_contract import ContractViolation,digest


def fixture():
    ref=dict(robot_id='r1',frame_id=17,t_sim=2.,sha256='a'*64)
    route=provide(ref)['route']
    profiles={}
    for axis,duration,u,i in (('forward',.1,.35,0),('left',.65,.65,1)):
        for sign in (-1,1):
            delta=[0.,0.,0.];delta[i]=sign*.015
            profiles[str((axis,sign))]=dict(axis=axis,u=sign*u,duration_s=duration,loaded=True,mean_delta=delta)
    return route,dict(now=2.,observed=[ref],profiles=profiles,option='on_v1',source='test_route_provider')


def test_off_never_reads_route_or_profiles_and_execute_off_does_not_construct_world(monkeypatch):
    assert compile_route(None,now=None,observed=None,profiles=None) is None
    from scripts import run_e2e_s3_route as runner
    with pytest.raises(ValueError,match='OFF'):runner.run(dict(own_route_adapter='off'),None)


def test_route_5_475m_seven_segments_one_corner_shared_cardinal_integer_plan():
    route,args=fixture();plan=compile_route(route,**args)
    assert plan['length_m']==pytest.approx(5.475)
    assert len(plan['legs'])==7 and len(plan['turns'])==1
    assert plan['turns'][0]['route_turn_rad']==pytest.approx(-1.5707963267948966)
    assert plan['own_waypoints']==WAYPOINTS and plan['waypoints'][0]==WAYPOINTS[0]
    assert plan['waypoints'][-1]==WAYPOINTS[-1] and plan['route_hash']==route['route_hash']
    for leg in plan['legs']:
        assert leg['distance_m']<=.85 and leg['plans']['r1']['pulses']==leg['plans']['r2']['pulses']
        for a,b in zip(leg['plans']['r1']['windows'],leg['plans']['r2']['windows']):
            assert a[:2]==b[:2] and a[1]>a[0]
            assert a[2]['turn']==b[2]['turn']==0
            assert sum(bool(v) for v in a[2].values())<=1
            assert all(a[2][k]==-b[2][k] for k in a[2])
    assert not plan['transport_admitted'] and not plan['research_result']
    assert plan['plan_hash']==digest({k:v for k,v in plan.items() if k!='plan_hash'})


@pytest.mark.parametrize('change',('hash','goal','source','diagonal','duplicate','too_long'))
def test_invalid_or_unobserved_routes_do_not_compile(change):
    route,args=fixture()
    if change=='hash':route['route_hash']='0'*64
    elif change=='goal':route['B_rgb_sources']=[]
    elif change=='source':args['observed']=[]
    elif change=='diagonal':route['waypoints'][1][1]=.10
    elif change=='duplicate':route['waypoints'][1]=copy.deepcopy(route['waypoints'][0])
    elif change=='too_long':route['waypoints']=[[float(i),0.] for i in range(65)]
    if change not in ('hash','source'):route['route_hash']=digest({k:v for k,v in route.items() if k!='route_hash'})
    with pytest.raises(ContractViolation):compile_route(route,**args)


def test_test_provider_is_explicit_and_authored_route_replaced_without_mutation():
    route,args=fixture();plan=compile_route(route,**args)
    old=dict(route=[[0,0],[1,0]],stations={'r1':[0,0]},checkpoint_segments={'old':3})
    result=plan_from_route(old,plan)
    assert result['route']==plan['waypoints'] and result['registered_route_source']=='test_route_provider'
    assert result['own_route']['B_rgb_sources']==route['B_rgb_sources']
    assert old['route']==[[0,0],[1,0]]
    with pytest.raises(ContractViolation):plan_from_route(old,{**plan,'source':'own_map'})
    ref=args['observed'][0];supplied=provide(ref)
    assert supplied['source']=='test_route_provider' and supplied['synthetic'] and not supplied['E2E_success_eligible']


def test_scene_retains_original_beam_and_b_size_without_world():
    from sim.e2e_s3_test import test_scenario
    from harness.e2e_environment import resolve
    from sim.zone_scenario_scene import load_scenario,ScenarioFinalV3Scene
    original=load_scenario('e2e_one_beam_ownmap');scenario=test_scenario()
    assert scenario['eval']['setup']['placements']==original['eval']['setup']['placements']
    assert scenario['eval']['setup']['robot_spawns']['r3']==original['eval']['setup']['robot_spawns']['r3']
    assert scenario['eval']['setup']['weld']=='off'
    assert resolve()[0]['regions']['zone_B']['half_extents_m']==[.4,.7]
    scene=ScenarioFinalV3Scene.from_scenario(scenario,61001)
    assert len(scene.cargo)==1 and scene.cargo[0].item_id=='beam_1'


def test_unmeasured_new_map_is_not_admitted_and_legacy_test_runtime_has_no_pose_prior():
    from pathlib import Path
    from harness.e2e_environment import resolve
    from harness.zone_s3_recovery_runtime import Runtime
    from harness.zone_s3_recovery_contract import inputs
    b=json.loads(Path('configs/e2e_s3_test_runtime_v1.json').read_text())
    args=(resolve()[0],inputs()[2]['orders'],Path(b['calibration']),b['calibration_sha256'])
    with pytest.raises(ValueError,match='outside DEV scope'):Runtime(*args,seed=61001,config=b['controller_config'])
    from harness.zone_final_environment import resolve as parent_resolve
    rt=Runtime(parent_resolve('zone_wide_door_geometry_v3')[0],*args[1:],seed=61001,config=b['controller_config'])
    try:
        assert set(rt.localizers)=={'r1','r2','r3'}
        assert rt.localizers['r1'].pulse_profiles and rt.localizers['r1'].pose.provider.prior['known_own_dock'] is False
    finally:rt.close()


def test_whole_outline_rejects_center_only_pass_and_rotation():
    from scripts.evaluate_e2e_s3_route import footprint_inside
    assert footprint_inside(dict(x=4.6,y=-2.1,yaw=0.))[0]
    assert not footprint_inside(dict(x=4.71,y=-2.1,yaw=0.))[0]
    assert footprint_inside(dict(x=4.6,y=-2.1,yaw=1.5707963267948966))[0]
    assert not footprint_inside(dict(x=4.6,y=-1.65,yaw=1.5707963267948966))[0]


def test_frozen_two_seed_limits_default_off_and_runtime_source_hash(monkeypatch):
    from scripts import run_e2e_s3_route as runner
    monkeypatch.setattr(runner,'source_closure',lambda *a:())
    b=runner.bundle('0'*40,61001)
    assert b['own_route_adapter']=='off' and not b['E2E_success']
    assert b['cap_sim_s']==b['case_cap_s']==900 and b['wall_cap_s']==18000
    assert b['route_source']=='test_route_provider' and b['legacy_authored_guard_provider']
    assert b['calibration_status']=='UNMEASURED_NEW_MAP'
    assert b['final_release_guard']=='off'
    assert runner.TEMPLATE in b['source_sha256']
    for seed in (61001,61002):assert runner.bundle('0'*40,seed)['provider_seeds']['r1']==seed
    with pytest.raises(ValueError):runner.bundle('0'*40,14201)


def test_cohort_command_uses_both_seeds_same_candidate_persistent_outputs():
    from scripts.run_e2e_s3_route_cohort import commands
    cc=commands('a'*40,1,'visual')
    assert [r['seed'] for r,args in cc]==[61001,61002]
    for r,args in cc:
        assert args[args.index('--output')+1]==f'outputs/{r["name"]}/raw'
        assert args[args.index('--own-route-adapter')+1]=='on_v1'
        assert args[args.index('--candidate')+1]=='visual'
    grouped=commands('a'*40,2,'visual',('off','saved_phase','local_servo'))
    assert len(grouped)==len({r['name'] for r,args in grouped})==6
    grouped=commands('a'*40,3,'visual',('local_servo',),('off','supported_phase','floor_latch'))
    assert len(grouped)==len({r['name'] for r,args in grouped})==6
    assert {r['final_guard'] for r,args in grouped}=={'off','supported_phase','floor_latch'}


def entrance_fixture():
    from types import MethodType
    from scripts.run_m2_pair import M2DoorStudent
    from harness.zone_final_pair_binding import bind
    log=[]
    ctl=SimpleNamespace(version='v3',state='align',seg=0,vo_obs=[],align_cmds0=None,commands=0,
        pending_reapproach=None,beam_grasp_confirmed=False,rid='r1',
        log=lambda *a,**k:log.append((a,k)))
    ctl._on_beam_obs=MethodType(bind(M2DoorStudent._on_beam_obs,EXPECT_GRIP_X_M=.5032),ctl)
    ep=SimpleNamespace(controller=ctl,own=SimpleNamespace(robot_id='r1',servo={1:2000},
        last_obs=dict(frame_id=2,sha256='a'*64,sim_time=2.)))
    beam=dict(visible=True,end_visible=True,reason='BAND_VISIBLE',grip_base_m=[.227,.002],axis_heading_rad=.157)
    return ep,beam,log


def test_entrance_owner_fix_replays_real_legacy_callback_without_faking_commands():
    from harness.e2e_s3_entrance import attach
    ep,beam,log=entrance_fixture();old=ep.controller._on_beam_obs
    assert attach(ep) is ep and ep.controller._on_beam_obs is old
    old(2.,beam);assert ep.controller.pending_reapproach==[.227,.002]
    ep,beam,log=entrance_fixture();attach(ep,'local_servo');ep.controller._on_beam_obs(2.,beam)
    assert ep.controller.pending_reapproach is None
    assert ep.controller.commands==0 and ep.controller.vo_obs[-1]['moved_before'] is False
    assert log[-1][0][1]=='test_local_alignment_owner' and not log[-1][1]['GO_bypassed']


@pytest.mark.parametrize('change',('stale','closed','far','missing_end','later_segment'))
def test_near_entrance_never_relaxes_stale_closed_far_or_later_stage(change):
    from harness.e2e_s3_entrance import attach
    ep,beam,log=entrance_fixture()
    if change=='stale':ep.own.last_obs['sim_time']=1.
    elif change=='closed':ep.own.servo[1]=1500
    elif change=='far':beam['grip_base_m'][0]=.9
    elif change=='missing_end':beam['end_visible']=False
    elif change=='later_segment':ep.controller.seg=1
    attach(ep,'local_servo');ep.controller._on_beam_obs(2.,beam)
    assert not any(a[1]=='test_local_alignment_owner' for a,k in log)
    with pytest.raises(ValueError):attach(ep,'local_servo',source='own_map')


def floor_row():
    return dict(t=419.65,states={'r1':'released','r2':'released'},
        fingers={'r1':[True,True],'r2':[True,True]},floor_normal_n=2.934,
        cargo_z_m=.015896,vertical_speed_m_s=-.0000116,cargo_tilt_deg=.0335,controller_feedback=False)


def test_final_release_counterexample_is_floor_supported_before_OPEN_dispatch():
    from sim.s3_setdown import supported_lower
    from sim.e2e_s3_final_release import supported_final
    row=floor_row()
    assert supported_lower({**row,'states':{'r1':'wait_open','r2':'wait_open'}})
    assert not supported_lower(row)
    assert not supported_final(None,None)
    for mode in ('supported_phase','floor_latch'):assert supported_final(row,True,mode)


@pytest.mark.parametrize('change',('air','no_floor','fast','tilted','carry','mixed','not_final','nonfinite'))
def test_final_release_classifier_never_admits_unsupported_or_nonfinal_rows(change):
    from sim.e2e_s3_final_release import supported_final
    row=floor_row();final=True
    if change=='air':row['cargo_z_m']=.08
    elif change=='no_floor':row['floor_normal_n']=0.
    elif change=='fast':row['vertical_speed_m_s']=-.3
    elif change=='tilted':row['cargo_tilt_deg']=10.
    elif change=='carry':row['states']={'r1':'carry','r2':'carry'}
    elif change=='mixed':row['states']['r2']='wait_open'
    elif change=='not_final':final=False
    elif change=='nonfinite':row['cargo_z_m']=float('nan')
    for mode in ('off','supported_phase','floor_latch'):assert not supported_final(row,final,mode)


def test_backend_final_guard_is_eval_only_and_latch_rearms_on_lost_floor(monkeypatch):
    import numpy as np
    from sim.e2e_s3_test import PhysicsBackend
    from sim.s3_release_epoch import PhysicsBackend as Parent
    from sim.zone_s3_no_prior import PhysicalStop
    def legacy(self):
        if 'beam_1' in self.lifted:raise PhysicalStop('LOAD_DROP:beam_1')
    monkeypatch.setattr(Parent,'eval_sample',legacy)
    for mode in ('off','supported_phase','floor_latch'):
        host=PhysicsBackend.__new__(PhysicsBackend);row=floor_row();events=[]
        host.bundle={'final_release_guard':mode};host.lifted={'beam_1'}
        host.final_segment_getter=lambda:True;host.setdown_row=lambda:row
        host.record_dynamics=lambda:events.append('dynamics');host.progress=lambda:events.append('progress')
        host._append=lambda path,value:events.append((path,value))
        host._box_geom={'beam_1':{0}}
        host.world=SimpleNamespace(model=SimpleNamespace(geom_type=[6],geom_size=np.array([[.3,.02,.015]])),
            data=SimpleNamespace(time=row['t'],geom_xmat=np.array([np.eye(3).ravel()]),geom_xpos=np.array([[4.6,-2.1,.015]])))
        if mode=='off':
            with pytest.raises(PhysicalStop):host.eval_sample()
            assert not events
            continue
        host.eval_sample()
        assert any(isinstance(x,tuple) and x[0]=='eval_only/final-release-classification.jsonl' and not x[1]['controller_feedback'] for x in events)
        row['floor_normal_n']=0.
        with pytest.raises(PhysicalStop):host.eval_sample()
        assert 'beam_1' in host.lifted
