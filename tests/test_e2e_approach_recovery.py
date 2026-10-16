import pytest
from harness.active_camera import SEARCH
from harness.e2e_carrier_approach import advance
from harness import e2e_pregrasp_acquire as m
from tests.test_e2e_align_progress import setup_transport
from tests.test_e2e18 import options,ROOT
from scripts.run_e2e_ownmap_live import bundle
from harness.e2e_runtime_registration import require_current


def test_missing_own_B_uses_own_explorer_not_repeated_beam_scan():
    tr=setup_transport(pregrasp_acquire=m.OPTION);tr.carrier_goal='seek_own_B_v1'
    r=tr.robots['r2'];r.goal.entities.pop('B');r.beam=None;r.nav_command=dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
    fine,actions=advance(tr,'r2',2.)
    assert not fine and actions==[r.nav_command] and not tr.queue
    assert r.carrier_approach['status']=='seek_own_B' and 'station' not in tr.approach['r2']
    r.last_obs['frame_id']=11;r.servo[6]=1750
    assert advance(tr,'r2',2.4)==(False,[dict(kind='hold')]) and tr.queue
    assert 'B' not in r.goal.entities


def test_three_fresh_failed_plans_trigger_existing_bounded_backup(monkeypatch):
    import harness.e2e_beam_avoidance as avoidance
    tr=setup_transport(dev_light=True,pregrasp_progress='backup_replan_v1',pregrasp_recovery='bounded_search_v1')
    tr.blocked_path_recovery='backup_v1';tr.beam_avoidance='own_obstacle_v1'
    monkeypatch.setattr(avoidance,'fallback',lambda *a:[])
    r=tr.robots['r1'];r.translation_commands=0
    for i in range(3):
        now=2.+i*.4;r.last_obs['frame_id']=10+i;r.beam['rgb']['t_sim']=now
        fine,actions=advance(tr,'r1',now);assert not fine
        if i<2:assert actions==[dict(kind='hold')]
    assert actions[0]['kind']=='mecanum' and actions[0]['forward']<0 and actions[0]['duration_s']==.1
    assert tr.approach['r1']['progress_watch']['phase']=='backup'
    assert any(e['event']=='own_pregrasp_blocked_plan_recovery' for e in tr.events)
    # No-path recovery remains independently off by default.
    from harness.e2e_approach_recovery import no_path
    tr.blocked_path_recovery='off';assert no_path(tr,'r1',4.,{},1.) is None


def test_current_recovery_registration():
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    b=bundle('a'*40,61002,'study_gemma4_31b_v1',**options(),**kw,compute_budget='lean_v1',mapping_cadence='0p6_v1',stale_station='expire12_v1',carrier_goal='seek_own_B_v1',blocked_path_recovery='backup_v1')
    assert b['execution_bundle_id']=='e2e18-v238';require_current(b,ROOT)
    b['e2e_options']['carrier_goal']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
