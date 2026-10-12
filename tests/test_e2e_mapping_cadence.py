import copy
import pytest
from types import SimpleNamespace
from harness import e2e_pregrasp_acquire as m
from harness.e2e_mapping_cadence import period,expire
from tests.test_e2e_align_progress import setup_transport
from tests.test_e2e18 import options,ROOT
from scripts.run_e2e_ownmap_live import bundle
from harness.e2e_runtime_registration import require_current


def test_mapping_only_clock_and_vo_freshness():
    from harness.e2e_observation_cadence import configure
    assert period('off','mapping')==.4
    assert period('0p6_v1','mapping')==.6 and period('0p6_v1','align')==.4
    goal=SimpleNamespace(e2e_vo=SimpleNamespace(range_stall=SimpleNamespace()))
    configure(goal,'on_v1',.6);assert goal.e2e_vo.max_pair_gap_s==pytest.approx(.65)
    configure(goal,'on_v1',.4);assert goal.e2e_vo.max_pair_gap_s==pytest.approx(.45)


def test_stale_station_expires_without_reusing_it_for_motion():
    from harness.e2e_carrier_approach import advance
    tr=setup_transport(pregrasp_acquire=m.OPTION);tr.stale_station='expire12_v1'
    r=tr.robots['r1'];r.last_beam=copy.deepcopy(r.beam);r.beam=None
    state=dict(station=[3.,4.,0.],grip=[3.,4.],basis={},last_seen=2.,frame=1)
    assert not expire(tr,'r1',14.,state,False)
    assert not expire(tr,'r1',100.,state,True)
    tr.approach['r1']=state;r.last_obs['frame_id']=2
    fine,actions=advance(tr,'r1',15.)
    assert not fine and 'station' not in state and state['acquisition']['phase']=='scan' and actions==[dict(kind='hold')]
    assert tr.events[-2]['event']=='own_stale_station_retired'
    assert r.carrier_approach['status']=='acquire_turn'


def test_current_cadence_registration():
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection='route_hash_v1',pregrasp_progress='backup_replan_v1',gaze_cadence='settled_frames_v1',stage_physics='pregrasp_dt1_v1',protocol_idempotency='same_route_v1',route_handle="typed_ref_v1",boundary_frame="observed_own_v1",beam_end_model="long_side_v1",beam_avoidance="own_obstacle_v1",pregrasp_acquire=m.OPTION,align_queues=m.QUEUES,beam_decode="once_v1",mapping_acquire=m.MAPPING)
    b=bundle('a'*40,61007,'study_gemma4_31b_v1',**options(),**kw,compute_budget='lean_v1',mapping_cadence='0p6_v1',stale_station='expire12_v1')
    assert b['execution_bundle_id']=='e2e18-v237';require_current(b,ROOT)
    b['mapping_cadence_profile']['other_s']=.6
    with pytest.raises(ValueError):require_current(b,ROOT)
