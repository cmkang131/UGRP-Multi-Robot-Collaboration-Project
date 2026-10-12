from types import SimpleNamespace
import pytest
from harness import e2e_camera_settle as c,e2e_pregrasp_acquire as m
from harness.active_camera import SEARCH
from tests.test_e2e_align_progress import setup_transport
from tests.test_e2e18 import options,ROOT
from scripts.run_e2e_ownmap_live import bundle
from harness.e2e_runtime_registration import require_current


def test_own_command_gate_rejects_geometry_until_settled_and_preserves_raw_reference():
    calls=[];records=[]
    r=SimpleNamespace(robot_id='r1',servo=dict(SEARCH),perception_settle=c.SETTLE,camera_settle_until=0.,receive=lambda *a:calls.append(a) or {'ok':True})
    obs=dict(frame_id=7,sha256='a'*64)
    c.commanded(r,dict(kind='mecanum',forward=.35),1.)
    assert c.receive(r,obs,b'pixels',1.,lambda *a:records.append(a))=={'ok':True}
    c.commanded(r,dict(kind='look',pan_pulse=1700),2.)
    assert c.receive(r,obs,b'pixels',2.4,lambda *a:records.append(a)) is None
    assert records[-1][1]['frame_id']==7 and records[-1][1]['sha256']=='a'*64 and len(calls)==1
    assert c.receive(r,obs,b'pixels',2.6,lambda *a:records.append(a))=={'ok':True}
    r.perception_settle='off';assert c.receive(r,obs,b'pixels',2.4,lambda *a:records.append(a))=={'ok':True}


def test_camera_pose_schedule_is_slower_but_grasp_schedule_is_unchanged():
    tr=setup_transport();tr.state='align';tr.camera_motion=c.MOTION
    tr._poses('r1',0.,[(dict(SEARCH),.3,.6)])
    assert tr.robot_queue_until['r1']==pytest.approx(1.4)
    tr.queue.clear();tr.queue_until=0.;tr.robot_queue_until={};tr.state='grasp_lift'
    tr._poses('r1',0.,[(dict(SEARCH),.3,.6)])
    assert tr.robot_queue_until['r1']==pytest.approx(.9)


def test_cache_bounds_preserve_most_recent_exact_objects_and_default_is_off():
    sensor=SimpleNamespace(cache={i:object() for i in range(100)},visibility=SimpleNamespace(cache={i:object() for i in range(100)}))
    value=sensor.cache[0];c.trim(sensor,0);assert len(sensor.cache)==100
    with c.using(c.CACHE):c.trim(sensor,0)
    assert len(sensor.cache)==len(sensor.visibility.cache)==64 and sensor.cache[0] is value and 1 not in sensor.cache


def test_registered_settled_candidate():
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    b=bundle('a'*40,61008,'study_gemma4_31b_v1',**options(),**kw,compute_budget='lean_v1',mapping_cadence='0p6_v1',stale_station='expire12_v1',carrier_goal='seek_own_B_v1',blocked_path_recovery='backup_v1',perception_settle=c.SETTLE,landmark_cache=c.CACHE,camera_motion=c.MOTION)
    assert b['execution_bundle_id']=='e2e18-v239';require_current(b,ROOT)
    b['e2e_options']['perception_settle']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
