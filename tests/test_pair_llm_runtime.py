"""The pair LLM seam: claims gate ``Team.start`` (real GatedRuntime, real executors, blind plumbing provider).
No physics, network or real model."""
import pytest

from harness import pair_llm_contract as contract
from harness.pair_llm_case import claim_counts, sabotage_events
from harness.pair_llm_dispatch import PairLink
from harness.pair_llm_runtime import GatedRuntime, NOT_RELEASED, ClaimGate, retryable
from harness.zone_study_contract import ContractViolation
from tests.pair_llm_fakes import gated_runtime, offline_only, ready  # noqa: F401  (autouse fixture)

ORDER, ZONE = 'cargoX', 'B'


@pytest.fixture
def runtime(tmp_path):
    rt = gated_runtime(tmp_path)
    try:
        yield rt
    finally:
        rt.close()


def start(rt, rid, now=0., zone=ZONE, partner=None):
    return rt.team.start(rid, ORDER, zone, partner or ('r2' if rid == 'r1' else 'r1'), now=now)


def test_start_is_refused_until_a_claim_is_released(runtime):
    ready(runtime)
    ack = start(runtime, 'r1')
    assert not ack['accepted'] and ack['rejected_reason'] == NOT_RELEASED
    assert runtime.actors['r1'].job is None and runtime.team.sessions == []
    assert runtime.gate.refused_without_permit == {'r1': 1, 'r2': 0}
    runtime.grant('r1', ORDER, ZONE, 'r2', now=0., call_ref='call-0001-r1')
    ack = start(runtime, 'r1', now=.05)
    assert ack['accepted'] and runtime.actors['r1'].job.kind == 'pair_carry'
    row = runtime.gate.log[-1]
    assert row['event'] == 'claim_submitted' and row['accepted'] and row['call_ref'] == 'call-0001-r1'
    assert row['released_at_sim_s'] == 0. and row['sim_s'] == .05 and row['job_id'] == ack['job_id']
    assert not runtime.gate.pending('r1')                     # consumed
    # the partner is untouched: it never submitted, so no session has two endpoints
    assert runtime.actors['r2'].job is None
    assert list(runtime.team.sessions[0]['endpoints']) == ['r1']


def test_the_claims_own_arguments_reach_team_start_not_the_runtimes_defaults(runtime):
    ready(runtime)
    runtime.grant('r1', ORDER, 'A', 'r2', now=0.)             # the model claimed the wrong destination
    ack = start(runtime, 'r1')                                # Runtime.step would pass zone B
    assert not ack['accepted'] and ack['rejected_reason'] == 'WRONG_PAIR_DESTINATION'
    assert not retryable(ack['rejected_reason']) and not runtime.gate.pending('r1')
    row = runtime.gate.log[-1]
    assert row['zone'] == 'A' and row['accepted'] is False and row['reason'] == 'WRONG_PAIR_DESTINATION'
    assert runtime.actors['r1'].job is None
    link = PairLink(runtime, 'r1')
    events = sabotage_events({'r1': link}, runtime.gate)
    assert [e['kind'] for e in events] == ['claim_refused'] and events[0]['reason'] == 'WRONG_PAIR_DESTINATION'
    assert claim_counts(runtime.gate)['rejected'] == 1


def test_a_transient_refusal_keeps_the_permit_and_the_next_tick_retries(runtime):
    runtime.grant('r1', ORDER, ZONE, 'r2', now=0.)
    first = start(runtime, 'r1', now=.05)                     # no pose report yet: SELF_<state>
    assert not first['accepted'] and retryable(first['rejected_reason'])
    assert runtime.gate.pending('r1') and runtime.gate.retries['r1'] == 1
    assert not [r for r in runtime.gate.log if r['event'] == 'claim_submitted']
    ready(runtime)
    second = start(runtime, 'r1', now=.10)
    assert second['accepted']
    row = runtime.gate.log[-1]
    assert row['retried_ticks'] == 1 and row['accepted']
    assert runtime.gate.record()['refusals']['r1'] == {first['rejected_reason']: 1}


def test_a_claim_without_a_partner_claim_times_out_and_a_mismatching_partner_claim_is_refused(runtime):
    ready(runtime)
    runtime.grant('r1', ORDER, ZONE, 'r2', now=0.)
    assert start(runtime, 'r1', now=.05)['accepted']
    runtime.grant('r2', ORDER, 'A', 'r1', now=.1)             # r2 claims another destination than r1 did
    ack = start(runtime, 'r2', now=.15)
    assert not ack['accepted'] and ack['rejected_reason'] == 'PAIR_SUBMISSION_MISMATCH'
    events = [e for rid in ('r1', 'r2') for e in runtime.actors[rid].drain_events()]
    assert any(e['event'] == 'pair_refused' and e['robot_id'] == 'r2' for e in events)
    runtime.team.poll(.2)
    assert runtime.team.sessions[0]['closed'] is True            # the mismatch closed r1's pending session
    rejected = [r for r in runtime.gate.log if r['event'] == 'claim_submitted' and not r['accepted']]
    assert [r['robot_id'] for r in rejected] == ['r2']


def test_pair_link_releases_permits_only_and_never_starts_a_job(runtime):
    link = PairLink(runtime, 'r1', origin_s=0.)
    ack = link.call('pair_carry', ORDER, ZONE, 'r2')
    assert ack['accepted'] and ack['arguments']['role'] == 'end_neg' and ack['job_id'] is None
    assert runtime.gate.pending('r1') and runtime.actors['r1'].job is None
    again = link.call('pair_carry', ORDER, ZONE, 'r2')       # replaces the pending permit
    assert again['accepted'] and runtime.gate.log[-1]['replaced_pending'] is True
    with pytest.raises(ContractViolation):
        link.call('deliver', ORDER, ZONE)
    with pytest.raises(ContractViolation):
        PairLink(runtime, 'r3')
    assert PairLink(runtime, 'r2').call('pair_carry', ORDER, ZONE, 'r1')['arguments']['role'] == 'end_pos'


def test_a_stop_revokes_a_pending_claim(runtime):
    ready(runtime)
    link = PairLink(runtime, 'r1', origin_s=0.)
    link.call('pair_carry', ORDER, ZONE, 'r2')
    assert runtime.gate.pending('r1')
    stop = link.call('hold', 10.)
    assert stop['accepted'] and not runtime.gate.pending('r1')
    assert runtime.gate.log[-1]['event'] == 'claim_revoked' and runtime.gate.log[-1]['reason'] == 'hold_requested'
    refused = start(runtime, 'r1', now=.1)                      # nothing is left to submit
    assert not refused['accepted'] and refused['rejected_reason'] == NOT_RELEASED


def test_a_duplicate_claim_during_the_pair_job_is_busy(runtime):
    ready(runtime)
    link = PairLink(runtime, 'r1', origin_s=0.)
    runtime.grant('r1', ORDER, ZONE, 'r2', now=0.)
    assert start(runtime, 'r1', now=.05)['accepted']
    busy = link.call('pair_carry', ORDER, ZONE, 'r2')
    assert not busy['accepted'] and busy['rejected_reason'].startswith('BUSY:pair_carry:')
    assert not runtime.gate.pending('r1')


def test_an_accepted_abort_of_a_running_pair_job_is_self_sabotage(runtime):
    from harness.zone_study_integration import executor_plan
    ready(runtime)
    link = PairLink(runtime, 'r1', origin_s=0.)
    runtime.grant('r1', ORDER, ZONE, 'r2', now=0.)
    assert start(runtime, 'r1', now=.05)['accepted']
    runtime.actors['r1'].now = .1
    plan = executor_plan({'kind': 'wait'}, link.job(), actor='r1', orders=[])
    assert plan.api == 'abort'                                   # a model that says wait while carrying
    ack = link.call(plan.api, *plan.args)
    assert ack['accepted']
    events = sabotage_events({'r1': link, 'r2': PairLink(runtime, 'r2')}, runtime.gate)
    assert [(e['kind'], e['robot_id'], e['job_kind']) for e in events] == [('abort_pair_carry', 'r1', 'pair_carry')]


def test_gate_refuses_bad_permits_and_double_binding():
    gate = ClaimGate(('r1', 'r2'))
    with pytest.raises(ValueError):
        gate.grant('r1', ORDER, ZONE, 'r1', now=0.)
    with pytest.raises(ValueError):
        gate.grant('r3', ORDER, ZONE, 'r1', now=0.)
    with pytest.raises(RuntimeError):
        gate.start('r1', ORDER, ZONE, 'r2', now=0.)             # not bound to a Team.start
    gate.bind(lambda *a, **k: {})
    with pytest.raises(RuntimeError):
        gate.bind(lambda *a, **k: {})


def test_gated_runtime_is_the_v88_runtime_with_one_replaced_attribute(runtime):
    from harness.zone_final_pair_runtime import Runtime
    assert isinstance(runtime, Runtime) and isinstance(runtime, GatedRuntime)
    assert runtime.team.start == runtime.gate.start
    from harness.pair_llm_runtime import _Gated
    assert GatedRuntime.__bases__ == (_Gated, Runtime)
    assert {n for n in vars(_Gated) if not n.startswith('__')} == {'grant', 'record'}
    assert GatedRuntime.step is Runtime.step and GatedRuntime.arm_step is Runtime.arm_step
    assert 'claim_gate' in runtime.record() and 'pair' in runtime.record()
    assert contract.read_registry()['weld'] == 'off'
