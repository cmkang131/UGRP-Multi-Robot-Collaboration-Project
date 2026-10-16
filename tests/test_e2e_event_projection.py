from types import SimpleNamespace
import pytest
from harness.e2e_event_projection import route_for_events,OPTION
from harness import e2e_s4_live as live
from harness.zone_final_pair_binding import bind
from harness.s4_event_policy import Options
from tests.test_e2e_dialogue import build
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance


def test_event_projection_tracks_new_route_without_full_validation():
    calls=[]
    robot=SimpleNamespace(now=1.,packet=None,own_inputs_at=lambda t:calls.append(t) or {'own_route':{'route_hash':'old'}})
    trial=SimpleNamespace(links={'r1':SimpleNamespace(inner=robot)},event_projection=OPTION)
    assert route_for_events(trial,'r1',1.) is None
    robot.packet={'route':{'route_hash':'new'}}
    assert route_for_events(trial,'r1',1.)=={'route_hash':'new'} and not calls
    with pytest.raises(ValueError,match='FUTURE'):route_for_events(trial,'r1',.5)
    trial.event_projection='off'
    assert route_for_events(trial,'r1',1.)=={'route_hash':'old'} and calls==[1.]


def test_real_scheduler_still_builds_validated_model_inputs(tmp_path,setup_data):
    validations=[]
    def factory(*args,**kw):
        for rid,link in kw['links'].items():
            r=link.inner;original=r.own_inputs_at
            p=original(1.)['own_route'];r.packet={'route':p} if p else None
            r.study_options=Options(True,True,'en');r.event_projection=OPTION;r.protocol_progress='stage_retry_v1'
            def checked(now,original=original,rid=rid):
                validations.append((rid,now));return original(now)
            r.own_inputs_at=checked
        return live.Host(*args,**kw)
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data)
    advance(host,inner,1,55)
    assert host.trial.dialogue.claims=={'r1','r2'}
    assert wire.requests and len(validations)>=len(wire.requests)
    assert len(validations)<60 # 3 robots x 55 ticks would be >=165 without projection.


def test_bundle_closes_and_enforces_both_options():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1',camera_load='nominal_command_v1',route_tokens='1600_v1',protocol_progress='stage_retry_v1',route_cost='bounded_morphology_v1',align_progress='dev_continue_v1',pregrasp_recovery='bounded_search_v1',pregrasp_gaze='own_bearing_v1',search_bearing='last_seen_v1',pulse_admission='finish_active_v1',event_projection=OPTION,pregrasp_progress='backup_replan_v1')
    b=bundle('a'*40,61004,'study_gemma4_31b_v1',**options(),**kw)
    require_current(b,ROOT);assert b['execution_bundle_id']=='e2e18-v231'
    assert {'harness/e2e_event_projection.py','harness/e2e_pregrasp_progress.py','harness/e2e_pulse_admission.py'}<=b['source_sha256'].keys()
    b['e2e_options']['pregrasp_progress']='off'
    with pytest.raises(ValueError):require_current(b,ROOT)
