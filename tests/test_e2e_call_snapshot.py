"""Real request/scheduler fixtures; logical clocks only, no physics or providers."""
import copy,json,math
from types import SimpleNamespace
import pytest
from harness import e2e_call_snapshot as m
from harness import e2e_s4_live as live
from harness.s4_event_policy import Options
from harness.zone_final_pair_binding import bind
from tests.test_e2e_dialogue import build,trigger,claim_phase
from tests.test_pair_llm_s4_host import setup_data,no_external_work,advance
from tests.test_e2e_dialogue_call_policy import make_event_host


@pytest.mark.parametrize('option',['off','prepared_v1'])
def test_delayed_prepare_keeps_call_start_own_state_and_protocol(tmp_path,setup_data,option):
    host,inner,wire=make_event_host(tmp_path,setup_data)
    advance(host,inner,1,6)
    trial=host.trial
    trial.event_projection='route_hash_v1'
    for r in inner.values():
        route=r.own_inputs_at(6).get('own_route')
        r.packet=None if route is None else dict(route=route)
        r.now=6.
        r.goal=SimpleNamespace(stage='explore')
    m.install(trial,option)
    call=SimpleNamespace(actor='r1',started_sim_s=6.,call_id='call-frozen-r1')
    trial.snapshot(call)
    # Same 0.1 SIM skew as actual r77 (74.9 start -> 75.0 prepare).
    inner['r1'].now=6.1;inner['r1'].goal.stage='future_stage'
    if option=='off':
        with pytest.raises(ValueError,match='FUTURE_EVENT_OWNER_STATE'):trial.prepare_call(call)
    else:
        prepared=trial.prepare_call(call)
        body=json.loads(prepared.request['messages'][1]['content'])
        assert body['sim_time_s']==6. and body['own_state_summary']['stage']=='explore'
        assert body['own_rgb']['t_sim']<=6.
        with pytest.raises(ValueError,match='PREPARED_CALL_SNAPSHOT_REQUIRED'):trial.prepare_call(call)


@pytest.mark.parametrize('arm',['no_comm','structured','peer_ko','leader_ko'])
def test_actual_scheduler_snapshot_route_claim_and_go_ack(tmp_path,setup_data,arm):
    def factory(*args,**kwargs):
        for link in kwargs['links'].values():
            r=link.inner;r.study_options=Options(True,True,'en')
            route=r.own_inputs_at(0).get('own_route');r.packet=None if route is None else dict(route=route)
        host=live.Host(*args,**kwargs)
        host.trial.dialogue_call_policy='event_v1'
        host.trial.event_projection='route_hash_v1'
        m.install(host.trial,'prepared_v1')
        # Production mapping captures every 0.6 SIM s; scheduler ticks are finer.
        # Stamp the fixture's observed state at that cadence, not in the future
        # of a queued report from the immediately preceding scheduler tick.
        step=host.step_to
        def observed_step(at):
            for link in kwargs['links'].values():
                link.inner.now=math.floor((at-1e-8)/.6)*.6
            return step(at)
        host.step_to=observed_step
        return host
    host,inner,wire=bind(build,s4=SimpleNamespace(Host=factory))(tmp_path,setup_data,arm,61001)
    claim_phase(host,inner);d=host.trial.dialogue
    if arm!='no_comm':
        assert d.approved and d.claims=={'r1','r2'}
        t=host.trial.scheduler.clock
        d.begin_epoch(order_id='order-5',route_hash=d.proposal['route']['route_hash'],grip_epoch=1,seg=0,now=t)
        trigger(host,inner,('r1','r2'),t)
        trigger(host,inner,('r1','r2'),t+4)
        advance(host,inner,t+8,t+12)
        assert d.allowed(d.key,t+12)
    else:assert not d.approved and not d.received
    assert not host.trial.scheduler.unsent_calls
    assert wire.requests


def test_registered_snapshot_children(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args[1]=61013;kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1',dialogue_call_policy='event_v1')
    for v in range(369,373):
        flags=dict(post_relook='carry_through_v1',body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1')
        if v==369:flags=dict(post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1')
        if v>=371:flags['approach_efficiency']='regulated_v1'
        flags['speech_context']='recent8_v1' if v==372 else 'recent4_v1'
        b=bundle(*args,**kw,**flags,call_snapshot='prepared_v1');require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert m.parent_for_validation(b)['e2e_options']==bundle(*args,**kw,**flags)['e2e_options']
        assert accepted_call_id(f'speed-gate-e2e18-v{v}-s61013-r78:call-0001-r1:1')
        bad=copy.deepcopy(b);bad['call_snapshot_parameters']['future_state']='allowed'
        with pytest.raises(ValueError):require_current(bad,ROOT)
    b={};assert m.compose(b)==() and b=={}
