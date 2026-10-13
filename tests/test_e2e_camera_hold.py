from types import SimpleNamespace
import pytest
from tests.test_camera_robot_port import _WorldSpy
from sim.camera_robot_port import CameraRobotPort
from sim.zone_s3_host import PhysicsBackend
from harness.e2e_camera_hold import actions,OPTION,ZERO
from harness.e2e_pulse_admission import Admission
from harness.active_camera import SEARCH
from tests.test_e2e18 import options,ROOT
from harness import e2e_camera_settle as c,e2e_pregrasp_acquire as m
from scripts.run_e2e_ownmap_live import bundle
from harness.e2e_runtime_registration import require_current


def replay(option,odom=None):
    world=_WorldSpy();port=CameraRobotPort(world,'r1',allow_mecanum=True)
    backend=SimpleNamespace(ports={'r1':port},now=0.,commands={'r1':dict(SEARCH)},_append=lambda *a:None)
    robot=SimpleNamespace(servo=dict(SEARCH))
    batch=[('r1',dict(kind='look',pan_pulse=1117)),('r1',dict(kind='hold'))]
    for rid,action in Admission('finish_active_v1').step(0.,actions(batch,{'r1':robot},'align',option)):
        PhysicsBackend.issue(backend,rid,action)
        if odom is not None:odom.command(dict(t=0.,**action))
    port.tick(.6)
    return world,port,backend


def test_actual_issue_path_reproduces_cancel_and_fixed_wait_reaches_command_target():
    _,old,old_backend=replay('off')
    assert old_backend.commands['r1'][6]==1117 and old._actuator_state()['servo_pulses']['6']==1500
    world,new,backend=replay(OPTION)
    assert new._actuator_state()['servo_pulses']['6']==backend.commands['r1'][6]==1117
    assert world.robots['r1'].servo_calls[-1][6]==1117
    assert world.robots['r1'].motor_calls[-1]==[0.]*4


def test_real_revocation_hold_still_cancels_pending_camera_target():
    world,port,_=replay(OPTION)
    port.apply(dict(kind='look',pan_pulse=2000),.6);port.tick(.7);port.hold(.7);port.tick(1.5)
    assert port._actuator_state()['servo_pulses']['6']==1317
    assert world.robots['r1'].servo_calls[-1][6]==1317


@pytest.mark.parametrize('phase,grip',[('grasp_lift',2000),('align',1600),('carry',1400)])
def test_loaded_and_grasp_phase_holds_unchanged(phase,grip):
    batch=[('r1',dict(kind='hold'))]
    assert actions(batch,{'r1':SimpleNamespace(servo={1:grip})},phase,OPTION)==batch


@pytest.mark.parametrize('option,version,clearance',[(OPTION,240,'off'),(ZERO,241,'off'),(ZERO,242,'range_v1'),(ZERO,243,'range_wall_v1'),(ZERO,244,'range_wall_slots_v1'),(ZERO,245,'range_v1'),(ZERO,246,'range_wall_v1'),(ZERO,247,'range_wall_slots_v1'),(ZERO,248,'off'),(ZERO,249,'range_wall_v1'),(ZERO,250,'range_wall_v1'),(ZERO,251,'range_wall_v1'),(ZERO,252,'range_wall_v1'),(ZERO,253,'range_wall_v1'),(ZERO,254,'range_wall_v1'),(ZERO,255,'range_wall_v1'),(ZERO,256,'range_wall_v1'),(ZERO,257,'range_wall_v1'),(ZERO,258,'range_wall_v1'),(ZERO,259,'range_wall_v1'),(ZERO,260,'range_wall_v1'),(ZERO,261,'range_wall_v1'),(ZERO,262,'range_wall_v1'),(ZERO,263,'range_wall_v1'),(ZERO,264,'range_wall_v1'),(ZERO,265,'range_wall_v1'),(ZERO,266,'range_wall_v1'),(ZERO,267,'range_wall_v1'),(ZERO,268,'range_wall_v1'),(ZERO,269,'range_wall_v1'),(ZERO,270,'range_wall_v1'),(ZERO,271,'range_wall_v1'),(ZERO,272,'range_wall_v1'),(ZERO,273,'range_wall_v1'),(ZERO,274,'range_wall_v1'),(ZERO,275,'range_wall_v1'),(ZERO,276,'range_wall_v1'),(ZERO,277,'range_wall_v1'),(ZERO,290,'range_wall_v1'),(ZERO,291,'range_wall_v1')])
def test_registered_wheel_wait_candidate(option,version,clearance):
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='release_dt1_v1' if version>=290 else 'pregrasp_dt1_v1',controller_timing='phase_v1' if version>=290 else 'off',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    b=bundle('a'*40,61008,'study_gemma4_31b_v1',**options(),**kw,compute_budget='lean_v1',mapping_cadence='0p6_v1',stale_station='expire12_v1',carrier_goal='seek_own_B_v1',blocked_path_recovery='backup_v1',perception_settle=c.SETTLE,landmark_cache=c.CACHE,camera_motion=c.MOTION,camera_hold=option,arm_clearance=clearance,sonar_frame='site_z_v1' if version>=245 else 'off',acquisition_mobility={249:'resume_v1',250:'remembered_view_v1',251:'resume_v1',252:'resume_v1',253:'resume_v1',254:'resume_v1',255:'resume_v1',256:'resume_v1',257:'resume_v1',258:'resume_v1',259:'resume_v1',260:'resume_v1',261:'resume_v1',262:'resume_v1',263:'resume_v1',264:'resume_v1',265:'resume_v1',266:'resume_v1',267:'resume_v1',268:'resume_v1',269:'resume_v1',270:'resume_v1',271:'resume_v1',272:'resume_v1',273:'resume_v1',290:'resume_v1',274:'resume_v1',275:'resume_v1',276:'resume_v1',277:'resume_v1',291:'resume_v1'}.get(version,'off'),approach_commit={251:'memory20_v1',252:'memory60_v1',253:'memory60_view_v1',254:'memory60_view_v1',255:'memory60_view_v1',256:'memory60_view_v1',257:'memory60_view_v1',258:'memory60_view_v1',259:'memory60_view_v1',260:'memory60_view_v1',261:'memory60_view_v1',262:'memory60_view_v1',263:'memory60_view_v1',264:'memory60_view_v1',265:'memory60_view_v1',266:'memory60_view_v1',267:'memory60_view_v1',268:'memory60_view_v1',269:'memory60_view_v1',270:'memory60_view_v1',271:'memory60_view_v1',272:'memory60_view_v1',273:'memory60_view_v1',290:'memory60_view_v1',274:'memory60_view_v1',275:'memory60_view_v1',276:'memory60_view_v1',277:'memory60_view_v1',291:'memory60_view_v1'}.get(version,'off'),scan_guard={254:'map_v1',255:'retreat_v1',256:'retreat_slots_v1',257:'map_v1',258:'map_v1',259:'map_v1',260:'map_v1',261:'map_v1',262:'map_v1',263:'map_v1',264:'map_v1',265:'map_v1',266:'map_v1',267:'map_v1',268:'map_v1',269:'map_v1',270:'map_v1',271:'map_v1',272:'map_v1',273:'map_v1',290:'map_v1',274:'map_v1',275:'map_v1',276:'map_v1',277:'map_v1',291:'map_v1'}.get(version,'off'),fine_view={257:'stage08_v1',258:'stage20_v1',259:'inspect40_v1',260:'inspect60_v1',261:'inspect60_v1',262:'inspect60_v1',263:'inspect60_v1',264:'inspect60_v1',265:'inspect60_v1',266:'inspect60_v1',267:'inspect60_v1',268:'inspect60_v1',269:'inspect60_v1',270:'inspect60_v1',271:'inspect60_v1',272:'inspect60_v1',273:'inspect60_v1',290:'inspect60_v1',274:'inspect60_v1',275:'inspect60_v1',276:'inspect60_v1',277:'inspect60_v1',291:'inspect60_v1'}.get(version,'off'),approach_heading={261:'path10_v1',262:'path20_v1',264:'path20_v1',265:'path20_v1',266:'path20_v1',267:'path20_v1',268:'path20_v1',269:'path20_v1',270:'path20_v1',271:'path20_v1',272:'path20_v1',273:'path20_v1',290:'path20_v1',274:'path20_v1',275:'path20_v1',276:'path20_v1',277:'path20_v1',291:'path20_v1'}.get(version,'off'),fine_entry={263:'capture60_v1',264:'capture60_mpc_v1',265:'capture60_mpc_v1',266:'capture60_mpc_v1',267:'capture60_mpc_v1',268:'capture60_mpc_v1',269:'capture60_mpc_v1',270:'capture60_mpc_v1',271:'capture60_mpc_v1',272:'capture60_mpc_v1',273:'capture60_mpc_v1',290:'capture60_mpc_v1',274:'capture60_mpc_v1',275:'capture60_mpc_v1',276:'capture60_mpc_v1',277:'capture60_mpc_v1',291:'capture60_mpc_v1'}.get(version,'off'),station_heading={265:'station10_v1',266:'station20_v1',268:'station20_v1',269:'station20_v1',270:'station20_v1',271:'station20_v1',272:'station20_v1',273:'station20_v1',290:'station20_v1',274:'station20_v1',275:'station20_v1',276:'station20_v1',277:'station20_v1',291:'station20_v1'}.get(version,'off'),clip_recovery={267:'back3_v1',268:'back3_v1',269:'back6_v1',270:'back3_v1',271:'back3_v1',272:'back3_v1',273:'back3_v1',290:'back3_v1',274:'back3_v1',275:'back3_v1',276:'back3_v1',277:'back3_v1',291:'back3_v1'}.get(version,'off'),station_handoff={270:'hold_v1',271:'pan_v1',272:'pan_v1',273:'pan_v1',290:'pan_v1',274:'pan_v1',275:'pan_v1',276:'pan_v1',277:'pan_v1',291:'pan_v1'}.get(version,'off'),relook_search={275:'view5_v1',276:'view5_pan_v1',277:'view5_restore_v1',291:'view5_restore_v1'}.get(version,'off'),capture_pose={272:'pose08_v1',273:'pose08_track_v1',290:'pose08_track_v1',274:'pose12_track_v1',275:'pose08_track_v1',276:'pose08_track_v1',277:'pose08_track_v1',291:'pose08_track_v1'}.get(version,'off'))
    assert b['execution_bundle_id']==f'e2e18-v{version}';require_current(b,ROOT)
    b['e2e_options']['camera_hold']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)


def test_zero_wheel_native_port_and_real_pulse_odometry_consume_same_commands():
    from harness.self_pulse_odom import PulseOdometry
    odom=PulseOdometry();world,port,backend=replay(ZERO,odom)
    assert odom.servo[6]==port._actuator_state()['servo_pulses']['6']==backend.commands['r1'][6]==1117
    assert odom.pose==(0.,0.,0.) and world.robots['r1'].motor_calls[-1]==[0.]*4
