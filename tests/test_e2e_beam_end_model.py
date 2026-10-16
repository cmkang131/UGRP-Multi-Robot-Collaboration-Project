import base64,hashlib,json,math
from pathlib import Path
import numpy as np
import pytest
from harness import e2e_beam_end_model as m
from harness.e2e_live_mapping import beam_observer


def test_long_side_resolves_sign_without_treating_small_end_cap_as_body():
    near=np.r_[np.linspace(.025,.5,200),np.linspace(-.03,-.02,10)]
    assert m.inward_sign(near)[0]==1
    assert m.inward_sign(-near)[0]==-1
    assert m.inward_sign(np.r_[near,-near])[0] is None
    assert m.inward_sign(np.linspace(-.04,.04,100))[0] is None
    assert m.inward_sign([float('nan')])[0] is None


def test_recorded_far_band_changes_center_by_54cm_without_using_truth():
    p=Path('experiments/2026-10-12-e2e18/evidence/v231-s61010-r1-01070.jpg')
    data=p.read_bytes();assert hashlib.sha256(data).hexdigest()=='ed2fd94e38fa07c9fb9381ffadd670ab9ba6c2ef693153d16eebc053c233570d'
    servo={1:2000,3:740,4:2320,5:1320,6:1047};image=base64.b64encode(data).decode()
    old=beam_observer()(image,servo);new=beam_observer(m.OPTION)(image,servo)
    assert old['end_visible'] and new['end_visible']
    assert new['observed_band_side']=='far'
    assert new['grip_base_m']==old['grip_base_m']
    assert new['endpoint_side_evidence']['long_before']>1000
    assert new['endpoint_side_evidence']['long_after']<25
    a=np.array([math.cos(old['axis_heading_rad']),math.sin(old['axis_heading_rad'])])
    b=np.array([math.cos(new['axis_heading_rad']),math.sin(new['axis_heading_rad'])])
    np.testing.assert_allclose(a,-b,atol=1e-12)
    assert np.linalg.norm(.27*(a-b))==pytest.approx(.54)


def test_off_returns_original_and_cannot_promote_clipped_end():
    value=dict(visible=True,end_visible=False)
    assert m.refine(value,None,None,None) is value
    assert m.refine(value,None,None,None,m.OPTION) is value


def test_v234_bundle_is_registered_and_source_complete():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model=m.OPTION,beam_avoidance="own_obstacle_v1")
    b=bundle('a'*40,61010,'study_gemma4_31b_v1',**options(),**kw)
    assert b['execution_bundle_id']=='e2e18-v234'
    assert 'harness/e2e_beam_end_model.py' in b['source_sha256']
    assert 'harness/e2e_beam_avoidance.py' in b['source_sha256']
    require_current(b,ROOT)
    b['e2e_options']['beam_end_model']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
