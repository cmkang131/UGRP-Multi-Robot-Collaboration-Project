"""Bounded real-scheduler reproductions of the 49.1 -> 64.1 retry loop."""
import copy
import pytest
from harness import e2e_admission_clock as m
from tests.test_e2e_dialogue_call_policy import make_event_host
from tests.test_pair_llm_s4_host import setup_data,no_external_work


@pytest.mark.parametrize('option',['off','tick_v1','deadline_v1'])
def test_real_scheduler_float_boundary_is_finite(option):
    from types import SimpleNamespace
    from harness.e2e_dialogue_call_policy import Policy
    from harness.e2e_s4_live import Trial
    from harness.zone_event_scheduler import EventScheduler,ReplayTransport
    from tests.test_zone_event_scheduler import _reply
    scheduler=EventScheduler(ReplayTransport({'r1':[_reply()]}),actors=('r1',),start_s=49.1)
    policy=Policy();policy.decide('r1',49.1,{'stage':'old'},{},[])
    trial=SimpleNamespace(scheduler=scheduler,call_events=policy,dialogue_call_policy='event_v1',
                          provenance={},call_state=lambda actor,now: ({'stage':'new'},{},[]))
    scheduler.call_admission=lambda actor,trigger,now: Trial.admit_dialogue_call(trial,actor,trigger,now)
    m.install(trial,option)
    scheduler.trigger('r1','report',at=64.1)
    result=scheduler.run(until_s=64.2,max_events=20,close_at_horizon=False)
    if option=='off':
        assert result.stop_reason=='max_events' and result.sim_s==64.1
        assert len(policy.events)==21 and not scheduler.ledger
    else:
        assert result.stop_reason!='max_events'
        assert sum(x['admitted'] for x in policy.events)==2
        assert len(policy.events)==2
        assert scheduler.ledger


@pytest.mark.parametrize('option',['tick_v1','deadline_v1'])
def test_boundary_grid_and_strictly_future_retry(option):
    for tick in range(1,100000,97):
        last=tick/1000
        wait,due=m.pending(last+14.999,last,15,option)
        assert wait and due>last+14.999
        assert not m.pending(round(last+15,6),last,15,option)[0]
    assert m.pending(64.1,49.1,15,'off')[0]


def test_registered_clock_candidates(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args[1]=61013;kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1',dialogue_call_policy='event_v1',call_snapshot='prepared_v1',speech_context='recent4_v1')
    for v in (375,376,377,378):
        flags=dict(post_relook='carry_through_v1',body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1',approach_efficiency='regulated_v1')
        if v in (375,377):flags=dict(post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1')
        b=bundle(*args,**kw,**flags,admission_clock='tick_v1' if v<377 else 'deadline_v1');require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert m.parent_for_validation(b)['e2e_options']==bundle(*args,**kw,**flags)['e2e_options']
        assert accepted_call_id(f'speed-gate-e2e18-v{v}-s61013-r79:call-0001-r1:1')
        bad=copy.deepcopy(b);bad['admission_clock_parameters']['same_timestamp_retry']='allowed'
        with pytest.raises(ValueError):require_current(bad,ROOT)
