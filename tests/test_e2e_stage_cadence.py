from types import SimpleNamespace
import numpy as np
import pytest
from harness.e2e_stage_cadence import settling,admit_gaze,GAZE
from tests.test_e2e_align_progress import setup_transport
from harness.e2e_carrier_approach import advance
from sim.e2e_stage_physics import update,OPTION


def test_gaze_holds_body_then_allows_stable_camera_frames():
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',gaze_cadence=GAZE)
    r=tr.robots['r1'];r.goal.explorer.local_pose=np.array([-1.,-.3,0.])
    _,a=advance(tr,'r1',2.);assert a[0]['kind']=='look' and a[-1]['kind']=='hold'
    for now in (2.4,):
        r.last_obs['frame_id']+=1;r.beam['rgb']['t_sim']=now
        _,a=advance(tr,'r1',now);assert a==[{'kind':'hold'}] and r.carrier_approach['status']=='gaze_settle'
    for now in (2.8,3.2,3.6,4.):
        r.last_obs['frame_id']+=1;r.beam['rgb']['t_sim']=now
        _,a=advance(tr,'r1',now);assert a[-1]['kind']=='mecanum' and not any(x['kind']=='look' for x in a)
    r.last_obs['frame_id']+=1;r.beam['rgb']['t_sim']=4.4
    _,a=advance(tr,'r1',4.4);assert a[0]['kind']=='look' and a[-1]['kind']=='hold'


def test_default_off_does_not_change_dispatch():
    tr=setup_transport();a=[dict(kind='look',pan_pulse=1500)];m=dict(kind='hold')
    assert admit_gaze(tr,'r1',0.,a,m)==a+[m] and not settling(tr,'r1',0.)


def shell(option=OPTION):
    calls=[]
    host=SimpleNamespace(bundle={'e2e_options':{'stage_physics':option}},dt=.002,now=12.4,
        world=SimpleNamespace(model=SimpleNamespace(opt=SimpleNamespace(timestep=.002))),
        _clock_snap=lambda:calls.append('snap'),_append=lambda *x:calls.append(x))
    return host,calls


def test_phase_dt_keeps_grasp_and_carry_fine_and_close_latches():
    host,calls=shell();assert not update(host,'mapping')
    assert update(host,'align') and host.dt==.001
    update(host,'align',dict(kind='arm',servo_id=3,pulse=1200));assert host.dt==.001
    assert update(host,'grasp_lift') and host.dt==.00025
    update(host,'carry');assert host.dt==.00025
    update(host,'align',dict(kind='arm',servo_id=1,pulse=1500));assert host.dt==.00025
    update(host,'mapping');assert host.dt==.00025
    assert calls[0]=='snap' and all(c[1]['reason']=='own_execution_phase' for c in calls if isinstance(c,tuple))
    host,calls=shell('off');assert not update(host,'align') and not calls


def test_backend_keeps_parent_drive_conversion_with_stage_option(monkeypatch):
    from sim.e2e_ownmap_live import PhysicsBackend,Evaluation
    calls=[];action=dict(kind='drive',forward=.3,lateral=0.,yaw=0.)
    monkeypatch.setattr(Evaluation,'issue',lambda self,rid,a:calls.append((rid,a)))
    host=PhysicsBackend.__new__(PhysicsBackend);host.bundle={'e2e_options':{'stage_physics':OPTION}};host.dt=.002
    host.issue('r1',action);assert calls==[('r1',action)]


def test_bundle_requires_profile_and_hashes_implementation():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence=GAZE,stage_physics=OPTION,protocol_idempotency='same_route_v1')
    b=bundle('a'*40,61004,'study_gemma4_31b_v1',**options(),**kw)
    require_current(b,ROOT);assert b['execution_bundle_id']=='e2e18-v232'
    assert {'harness/e2e_stage_cadence.py','sim/e2e_stage_physics.py'}<=b['source_sha256'].keys()
    b['stage_physics_profile']['align_dt_s']=.002
    with pytest.raises(ValueError):require_current(b,ROOT)


def test_release_dt1_clears_latch_per_robot_from_issued_open_and_relook_phase():
    from sim.e2e_stage_physics import RELEASE
    close=dict(kind='arm',servo_id=1,pulse=1500);opened=dict(kind='arm',servo_id=1,pulse=2000)
    host,calls=shell(RELEASE)
    assert update(host,'align') and host.dt==.001
    update(host,'grasp_lift',close,'r1');update(host,'grasp_lift',close,'r2');assert host.dt==.00025
    update(host,'lower_open',opened,'r1');assert host.dt==.00025   # r2 may still hold
    update(host,'lower_open',opened,'r2');assert host.dt==.00025 and host._stage_contact_latched is False  # contact-sensitive phase keeps old dt
    assert update(host,'relook_camera') and host.dt==.001
    update(host,'relook');assert host.dt==.001
    update(host,'relook',close,'r1');assert host.dt==.00025          # a new close re-latches
    update(host,'relook',opened,'r1');assert host.dt==.001
    assert [c[1]['reason'] for c in calls if isinstance(c,tuple)][-1]=='own_gripper_open_release'
    assert [c[1]['grip_command_latched'] for c in calls if isinstance(c,tuple)][-1] is False


def test_release_off_and_pregrasp_keep_latch_after_open():
    host,_=shell(OPTION)
    update(host,'grasp_lift',dict(kind='arm',servo_id=1,pulse=1500),'r1')
    update(host,'relook',dict(kind='arm',servo_id=1,pulse=2000),'r1');assert host.dt==.00025


def test_controller_timing_off_installs_nothing_and_on_records_by_phase(tmp_path):
    from types import SimpleNamespace
    from harness import e2e_speed_phase as m
    assert m.install('off',{},None,None,None) is None
    goal=SimpleNamespace(receive=lambda **k:'g');robot=SimpleNamespace(_receive=lambda *a:'r',goal=goal,observe_beam=lambda *a:'b')
    transport=SimpleNamespace(step=lambda now:'s');host=SimpleNamespace(step_to=lambda now:'h')
    backend=SimpleNamespace(capture=lambda:'c')
    t=m.install(m.TIMING,{'r1':robot},transport,host,backend)
    t.phase='relook';assert robot._receive()=='r' and robot.goal.receive()=='g' and transport.step(1)=='s' and host.step_to(1)=='h'
    t.phase='align';assert backend.capture()=='c'
    out=[];t.flush(tmp_path/'x.json',lambda p,v:out.append(v),force=True)
    assert out[0]['phases']['relook']['robot._receive']['calls']==1 and out[0]['phases']['align']['backend.capture']['calls']==1
    assert out[0]['controller_feedback'] is False
    from harness import e2e_live_mapping,e2e_camera_settle
    import importlib;importlib.reload(e2e_live_mapping);importlib.reload(e2e_camera_settle)   # undo module patches


def test_speed_phase_compose_requires_both_and_registers_v290_v291():
    from harness import e2e_speed_phase as m
    b=dict(execution_bundle_id='e2e18-v273',e2e_options={});before=dict(b)
    assert m.compose(b,'off','off')==() and b==before
    for args in (('release_dt1_v1','off'),('off','phase_v1'),('pregrasp_dt1_v1','phase_v1')):
        with pytest.raises(ValueError):m.compose(dict(b,e2e_options={}),*args)
    m.compose(b,'release_dt1_v1','phase_v1');assert b['execution_bundle_id']=='e2e18-v290' and b['workflow_version']=='7.183.0'
    with pytest.raises(ValueError):m.compose(b,'release_dt1_v1','phase_v1')
    b=dict(execution_bundle_id='e2e18-v277',e2e_options={});m.compose(b,'release_dt1_v1','phase_v1');assert b['execution_bundle_id']=='e2e18-v291'
    m.validate(b);b['stage_physics_profile']=dict(m.PROFILE,relook_dt_s=.002)
    with pytest.raises(ValueError):m.validate(b)
