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


@pytest.mark.parametrize('option,version',[(OPTION,240),(ZERO,241)])
def test_registered_wheel_wait_candidate(option,version):
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    b=bundle('a'*40,61008,'study_gemma4_31b_v1',**options(),**kw,compute_budget='lean_v1',mapping_cadence='0p6_v1',stale_station='expire12_v1',carrier_goal='seek_own_B_v1',blocked_path_recovery='backup_v1',perception_settle=c.SETTLE,landmark_cache=c.CACHE,camera_motion=c.MOTION,camera_hold=option)
    assert b['execution_bundle_id']==f'e2e18-v{version}';require_current(b,ROOT)
    b['e2e_options']['camera_hold']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)


def test_zero_wheel_native_port_and_real_pulse_odometry_consume_same_commands():
    from harness.self_pulse_odom import PulseOdometry
    odom=PulseOdometry();world,port,backend=replay(ZERO,odom)
    assert odom.servo[6]==port._actuator_state()['servo_pulses']['6']==backend.commands['r1'][6]==1117
    assert odom.pose==(0.,0.,0.) and world.robots['r1'].motor_calls[-1]==[0.]*4
