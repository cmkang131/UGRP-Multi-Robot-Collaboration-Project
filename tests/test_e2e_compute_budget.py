import copy,base64
from pathlib import Path
import cv2,pytest
from harness.e2e_compute_budget import PROFILE
from harness import e2e_pregrasp_acquire as m
from tests.test_e2e18 import options,ROOT
from scripts.run_e2e_ownmap_live import bundle
from harness.e2e_runtime_registration import require_current


def test_new_profile_requires_new_bundle_and_does_not_change_old():
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    old=bundle('a'*40,61001,'study_gemma4_31b_v1',**options(),**kw)
    new=bundle('a'*40,61001,'study_gemma4_31b_v1',**options(),**kw,compute_budget='lean_v1')
    assert old['execution_bundle_id']=='e2e18-v235' and not old['speed4']['render_half']
    assert new['execution_bundle_id']=='e2e18-v236' and new['speed4']==PROFILE
    assert new['speed4_record']['sensor_raster']==[320,240]
    assert new['speed3_profile']==old['speed3_profile'] and new['stage_physics_profile']==old['stage_physics_profile']
    require_current(old,ROOT);require_current(new,ROOT)
    new['e2e_options']['compute_budget']='off'
    with pytest.raises(ValueError):require_current(new,ROOT)


def test_saved_own_rgb_band_remains_observable_at_reduced_raster():
    from harness.e2e_live_mapping import beam_observer
    data=Path('experiments/2026-10-12-e2e18/evidence/v231-s61010-r1-01070.jpg').read_bytes()
    import numpy as np
    rgb=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
    small=cv2.resize(rgb,(320,240),interpolation=cv2.INTER_AREA)
    restored=cv2.resize(small,(640,480),interpolation=cv2.INTER_LINEAR)
    ok,encoded=cv2.imencode('.jpg',restored);assert ok
    b=beam_observer('long_side_v1','once_v1')(base64.b64encode(encoded).decode(),{1:2000,3:740,4:2320,5:1320,6:1047})
    assert b['visible'] and b['end_visible'] and b['observed_band_side']=='far'
