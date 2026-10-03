"""Own status (refusal feedback), the look_around option and the image bill of the pair LLM layer (v100).

The status is the robot's OWN software state told to its model; these tests pin what it may contain (a closed
record, no raw reason, nothing partner-derived, no ground truth) and that the refusal reaches the model in the real
loop. No physics, network or real model: replies come from stubs behind the real proxy completer.
"""
import json
import random
from pathlib import Path

import pytest

from harness import pair_llm_billing as billing
from harness import pair_llm_dispatch as dispatch
from harness import pair_llm_inputs as pi
from harness import pair_llm_status as st
from harness import zone_study_integration as zi
from harness import zone_study_prompts_ko as pk
from harness import zone_study_protocol as zp
from harness.pair_llm_stub import StubModel, claim_action, reply_json, scripted
from tests.pair_llm_fakes import make_inputs, quiet_status, run_arm

ORDER = {'order_id': 'cargoX', 'destination_zone': 'B'}


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def gate_view(*, permit=None, event=None, total=0):
    return {'permit_released_at_sim_s': permit, 'last_event': event, 'refusal_total': total}


def refused(reason, sim_s, *, retryable):
    return {'kind': 'refused', 'reason': reason, 'sim_s': sim_s, 'retryable': retryable}


def build(**kw):
    base = dict(now=20., claim_issued_s=4., view=gate_view(), job_kind=None, last_end=None,
                refusals_since_last_call=0)
    base.update(kw)
    return st.build(**base)


# --------------------------------------------------------------------------- the record (unit)

def test_a_robot_that_never_claimed_is_no_claim():
    row = build(claim_issued_s=None)
    assert row == {'last_outcome': 'no_claim', 'reason': None, 'since_claim_s': None, 'refusals_since_last_call': 0}
    assert st.status_violations(row) == []


def test_the_smoke1_shape_is_start_refused_with_the_age_of_the_claim_and_the_refusal_count():
    """Two released claims, the blind controller refusing every tick with SELF_UNCERTAIN (smoke1)."""
    row = build(now=44.85, claim_issued_s=4.1,
                view=gate_view(permit=5.4, event=refused('SELF_UNCERTAIN', 44.8, retryable=True), total=1069),
                refusals_since_last_call=262)
    assert row == {'last_outcome': 'start_refused', 'reason': 'SELF_UNCERTAIN', 'since_claim_s': 40.75,
                   'refusals_since_last_call': 262}
    assert st.status_violations(row) == []


def test_a_pending_permit_without_a_refusal_yet_is_claim_released():
    row = build(view=gate_view(permit=5.4))
    assert row['last_outcome'] == 'claim_released' and row['reason'] is None


@pytest.mark.parametrize('reason, token', [
    ('WRONG_PAIR_DESTINATION', 'WRONG_PAIR_DESTINATION'), ('UNKNOWN_ORDER', 'UNKNOWN_ORDER'),
    ('SELF_STOPPED', 'SELF_STOPPED'),
    # partner-derived refusals must not reach the model: no_comm would learn the partner's submission
    ('PAIR_SUBMISSION_MISMATCH', 'other'), ('PAIR_STATIC_INPUT_MISMATCH', 'other'),
    ('PAIR_RENDEZVOUS_TIMEOUT', 'other'), ('PAIR_REQUIRES_NOSLIP_WELD_OFF', 'other'),
    ('PAIR_CALIBRATION_MISMATCH', 'other')])
def test_a_non_retryable_refusal_is_claim_rejected_and_partner_derived_reasons_become_other(reason, token):
    row = build(view=gate_view(event=refused(reason, 9., retryable=False), total=1))
    assert row['last_outcome'] == 'claim_rejected' and row['reason'] == token
    assert st.status_violations(row) == []


def test_running_jobs_and_ended_jobs_are_reported_by_class_only():
    assert build(job_kind='pair_carry')['last_outcome'] == 'pair_job_running'
    assert build(job_kind='look_around')['last_outcome'] == 'look_around_running'
    for raw, klass in (('LOCAL_TIMEOUT:120', 'local_timeout'), ('PAIR_PARTNER_LOST', 'queue_empty'),
                       ('GRASP_NOT_CONFIRMED_AT_xyz', 'queue_empty'), (None, 'queue_empty')):
        end = {'job_kind': 'pair_carry', 'sim_s': 30., 'reason_class': st.end_class(raw)}
        row = build(last_end=end)
        assert row['last_outcome'] == 'pair_job_ended' and row['reason'] == klass
        assert 'GRASP' not in json.dumps(row) and 'PARTNER' not in json.dumps(row)
    ended = build(last_end={'job_kind': 'look_around', 'sim_s': 30., 'reason_class': 'queue_empty'})
    assert ended['last_outcome'] == 'look_around_ended'


def test_the_latest_fact_wins_a_new_claim_after_a_rejection_after_an_end():
    rejected = refused('WRONG_PAIR_DESTINATION', 9., retryable=False)
    ended = {'job_kind': 'pair_carry', 'sim_s': 30., 'reason_class': 'queue_empty'}
    assert build(view=gate_view(event=rejected), last_end=ended)['last_outcome'] == 'pair_job_ended'
    assert build(view=gate_view(event=rejected), last_end=dict(ended, sim_s=5.))['last_outcome'] == 'claim_rejected'
    again = gate_view(permit=40., event=refused('SELF_UNCERTAIN', 12., retryable=True))
    assert build(view=again, last_end=ended)['last_outcome'] == 'claim_released'        # released after both
    stale = gate_view(event=refused('SELF_UNCERTAIN', 12., retryable=True))               # no permit any more
    assert build(view=stale)['last_outcome'] == 'no_claim'


# --------------------------------------------------------------------------- leak tests

HOSTILE = ['GT_CONTACT_SUCCESS', 'SELF_CONTACT', 'SELF_UNCERTAIN ', 'self_uncertain', 'SELF_UNCERTAIN\n', 'success',
           'ground_truth', 'peer_pose_xy=1.2,0.3', 'x' * 5000, '', 'SELF_', 'other', 'delivered', 'teacher_receipt',
           None, 7, 3.5, True, ['SELF_UNCERTAIN'], {'contact': True}, b'SELF_UNCERTAIN']


@pytest.mark.parametrize('retryable', [True, False])
def test_no_hostile_reason_string_ever_passes_through_the_builder(retryable):
    allowed_words = set(st.OUTCOMES) | {None, 'other'} | {r for rs in st.REASONS_BY_OUTCOME.values() for r in rs}
    for reason in HOSTILE:
        for permit in (None, 5.):
            row = build(view=gate_view(permit=permit, event=refused(reason, 9., retryable=retryable)))
            assert st.status_violations(row) == [], (reason, row)
            assert set(row) == set(st.STATUS_KEYS)
            assert {row['last_outcome'], row['reason']} <= allowed_words, (reason, row)
        end = build(last_end={'job_kind': 'pair_carry', 'sim_s': 9., 'reason_class': reason})
        assert st.status_violations(end) == [] and end['reason'] in st.END_REASONS + ('other',)


def test_the_builder_signature_has_no_partner_pose_contact_or_success_input():
    import inspect
    params = set(inspect.signature(st.build).parameters)
    assert params == {'now', 'claim_issued_s', 'view', 'job_kind', 'last_end', 'refusals_since_last_call'}
    random.seed(7)
    for _ in range(200):               # whatever the own bookkeeping holds, the output stays inside the closed schema
        view = gate_view(permit=random.choice([None, 1., 5.]), total=random.randint(0, 9),
                         event=random.choice([None, refused(random.choice(HOSTILE[:12]), 3., retryable=random.random() < .5),
                                              {'kind': 'accepted', 'reason': None, 'sim_s': 4., 'retryable': False}]))
        row = build(view=view, job_kind=random.choice([None, 'pair_carry', 'look_around', 'hold', 'deliver']),
                    last_end=random.choice([None, {'job_kind': 'pair_carry', 'sim_s': 8., 'reason_class': 'x'}]))
        assert st.status_violations(row) == []


def payload_of(own_status):
    inputs, source, _ = make_inputs('peer_nl', 'r1', own_status=own_status)
    return inputs.payload_dict(), source.pinned


def test_a_valid_status_passes_the_payload_boundary_and_is_required():
    payload, pinned = payload_of(quiet_status())
    assert pi.payload_violations(payload, pinned=pinned) == [] and payload['own_status'] == quiet_status()
    assert 'own_status' in pi.allowlist('peer_nl') and 'own_status' in pi.allowlist('no_comm')
    del payload['own_status']
    assert any('own_status' in p for p in pi.payload_violations(payload, pinned=pinned))


@pytest.mark.parametrize('mutate', [
    lambda s: s.update(contact=True),                                   # a key outside the closed schema
    lambda s: s.update(success=False),
    lambda s: s.update(pose_xy=[0., 1.]),
    lambda s: s.pop('refusals_since_last_call'),
    lambda s: s.update(last_outcome='delivered'),                       # not an enum member
    lambda s: s.update(last_outcome='pair_job_ended', reason='GRASP_FAILED'),
    lambda s: s.update(last_outcome='start_refused', reason='ground_truth'),
    lambda s: s.update(last_outcome='start_refused', reason='teacher_receipt'),
    lambda s: s.update(last_outcome='claim_released', reason='SELF_UNCERTAIN'),    # a reason where none is kept
    lambda s: s.update(since_claim_s=-1.), lambda s: s.update(since_claim_s=float('nan')),
    lambda s: s.update(since_claim_s=True), lambda s: s.update(refusals_since_last_call=True),
    lambda s: s.update(refusals_since_last_call=-1), lambda s: s.update(refusals_since_last_call=1.5)])
def test_the_payload_boundary_refuses_a_status_outside_the_closed_record(mutate):
    status = quiet_status()
    mutate(status)
    try:
        payload, pinned = payload_of(status)
    except Exception:                                  # build_payload already refuses it (also a valid outcome)
        return
    assert pi.payload_violations(payload, pinned=pinned)


def test_a_status_never_gets_anything_the_study_boundary_forbids_in_a_real_request():
    inputs, source, _ = make_inputs('peer_nl', 'r1', own_status=build(
        view=gate_view(permit=5., event=refused('SELF_UNCERTAIN', 9., retryable=True)), refusals_since_last_call=40))
    body = json.loads(pi.build_request(inputs, window={'window_id': 'w1'})['messages'][1]['content'])
    assert set(body['own_status']) == set(st.STATUS_KEYS)
    assert body['own_status']['last_outcome'] == 'start_refused'
    assert pi.payload_violations(inputs.payload_dict(), pinned=source.pinned) == []


# --------------------------------------------------------------------------- the refusal reaches the model

def test_in_the_loop_the_model_is_told_its_start_was_refused_and_how_often(tmp_path):
    result, out, _ = run_arm(tmp_path, 'no_comm', cap_s=30.)
    inputs = rows(out / 'llm' / 'inputs.jsonl')
    first = {r['robot']: r['own_status'] for r in inputs if r['sim_s'] == 0.}
    assert all(s == {'last_outcome': 'no_claim', 'reason': None, 'since_claim_s': None,
                     'refusals_since_last_call': 0} for s in first.values())
    refused_calls = [r for r in inputs if r['own_status']['last_outcome'] == 'start_refused']
    assert refused_calls, [r['own_status'] for r in inputs]
    for r in refused_calls:
        assert r['own_status']['reason'] == 'SELF_UNCERTAIN' and r['own_status']['since_claim_s'] > 0
    assert any(r['own_status']['refusals_since_last_call'] > 0 for r in refused_calls)
    # the counts are per call: they add up to no more than the gate's own refusal totals
    gate = json.loads((out / 'llm' / 'claim_gate.json').read_text())
    for rid in ('r1', 'r2'):
        assert sum(r['own_status']['refusals_since_last_call'] for r in inputs if r['robot'] == rid) \
            <= gate['refusal_total'][rid] == sum(gate['refusals'][rid].values())
    # what the model received on the wire is exactly what the input log says
    for row in rows(out / 'llm' / 'requests.jsonl'):
        wire = json.loads(row['user'])['own_status']
        logged = next(r['own_status'] for r in inputs if r['request_id'] == row['request_id'])
        assert wire == logged and st.status_violations(wire) == []
    assert result['status'] == 'COLLECTED_UNQUALIFIED'


def test_the_prompt_tells_the_model_about_own_status_and_the_decision_source_to_cite():
    from harness import pair_llm_prompts_ko as prompts
    text = prompts.system_prompt('no_comm', 'r1')
    assert 'own_status' in text and 'start_refused' in text and 'look_around' in text
    assert 'own_commands로 적습니다' in text
    assert 'own_status' not in zp.DECISION_SOURCES        # the sealed set: the model cites own_commands
    assert prompts.PROMPT_VERSION.endswith('.v3')


# --------------------------------------------------------------------------- look_around

def reply(action, request_id='req_t1', sources=('order_sheet',), messages=()):
    return reply_json(request_id, action, messages, sources)


def test_a_look_around_reply_passes_the_sealed_validator_through_a_placeholder():
    inputs, _, _ = make_inputs('no_comm', 'r1')
    kw = dict(request_id='req_t1', condition=dispatch.study_spec('no_comm'), actor='r1', order_ids=inputs.order_ids(),
              item_ids=inputs.item_ids(), roles_by_order=inputs.roles_by_order(), vocabulary=inputs.vocabulary(),
              passages=inputs.passages(), location_refs=inputs.location_refs(), robots=('r1', 'r2'))
    value = dispatch.validate_reply(reply({'kind': 'look_around'}, sources=('own_commands', 'own_rgb')), **kw)
    assert value['action'] == {'kind': 'look_around'} and value['decision_sources'] == ['own_commands', 'own_rgb']
    with pytest.raises(zp.ProtocolError, match='takes no other field'):
        dispatch.validate_reply(reply({'kind': 'look_around', 'duration_s': 5}), **kw)
    with pytest.raises(zp.ProtocolError, match='request_id'):                # every other sealed rule still applies
        dispatch.validate_reply(reply({'kind': 'look_around'}, request_id='req_other'), **kw)
    with pytest.raises(zp.ProtocolError, match='decision source'):
        dispatch.validate_reply(reply({'kind': 'look_around'}, sources=('own_status',)), **kw)
    with pytest.raises(zp.ProtocolError, match='messages must be'):          # no_comm still cannot talk
        dispatch.validate_reply(reply({'kind': 'look_around'}, messages=[
            {'recipients': ['r2'], 'reply_to': None, 'text': 'hi'}]), **kw)
    with pytest.raises(zp.ProtocolError, match='not allowed'):               # the vocabulary grew by exactly one kind
        dispatch.validate_reply(reply({'kind': 'goto', 'x': 1}), **kw)
    assert dispatch.validate_reply(reply({'kind': 'continue'}), **kw) == zp.validate_reply(reply({'kind': 'continue'}), **kw)
    assert dispatch.PAIR_ACTION_KINDS == tuple(zp.ROBOT_ACTION_KINDS) + ('look_around',)


def test_the_plan_of_every_other_action_is_the_studys_and_look_around_is_the_executors_look_around():
    orders = [{'order_id': 'cargoX', 'kind': 'long_beam', 'required_robots': 2, 'count': 1}]
    for action in ({'kind': 'continue'}, {'kind': 'wait'}, {'kind': 'release', 'order_id': 'cargoX'},
                   claim_action('r1', ORDER), {'kind': 'goto'}):
        job = {'kind': 'pair_carry', 'order_id': 'cargoX', 'job_id': 'j1'}
        assert dispatch.pair_executor_plan(action, job, actor='r1', orders=orders) \
            == zi.executor_plan(action, job, actor='r1', orders=orders)
    plan = dispatch.pair_executor_plan({'kind': 'look_around'}, None, actor='r1', orders=orders)
    assert plan.api == 'look_around' and plan.args == () and plan.rejected_reason is None
    assert dispatch.pair_action_row({'kind': 'look_around'}) == ('observe', {}, None, None)


def test_in_the_loop_a_look_around_runs_on_the_robots_own_executor_and_shows_in_its_own_status(tmp_path):
    table = {('r1', 0): (claim_action('r1', ORDER), []), ('r2', 0): (claim_action('r2', ORDER), []),
             ('r1', 1): ({'kind': 'look_around'}, [])}
    result, out, _ = run_arm(tmp_path, 'no_comm', StubModel(scripted(table)), cap_s=30.)
    dispatched = [d for d in rows(out / 'llm' / 'dispatch.jsonl') if d['action']['kind'] == 'look_around']
    assert len(dispatched) == 1 and dispatched[0]['api'] == 'look_around' and dispatched[0]['actor'] == 'r1'
    ack = dispatched[0]['ack']
    assert ack['accepted'] is True and ack['arguments'] == {'observe': 'wide_look'}
    events = rows(out / 'llm' / 'executor_events.jsonl')
    mine = [e for e in events if e['robot_id'] == 'r1' and e['job_kind'] == 'look_around'
            and e['sim_s'] > dispatched[0]['sim_s']]          # the executor clock runs 1 SIM s ahead of the harness
    assert [e['event'] for e in mine] == ['job_started', 'job_done']
    history = [e for row in rows(out / 'llm' / 'requests.jsonl') if json.loads(row['user'])['robot_id'] == 'r1'
               for e in json.loads(row['user'])['own_command_history']]
    assert any(e['kind'] == 'observe' for e in history)
    later = [r['own_status'] for r in rows(out / 'llm' / 'inputs.jsonl')
             if r['robot'] == 'r1' and r['sim_s'] > dispatched[0]['sim_s']]
    assert later and later[0]['last_outcome'] == 'look_around_ended' and later[0]['reason'] == 'queue_empty'
    # the end of a look-around is not a success flag: the claim is still refused and the count keeps saying so
    assert later[0]['refusals_since_last_call'] > 0 and later[-1]['last_outcome'] == 'start_refused'
    assert result['status'] == 'COLLECTED_UNQUALIFIED' and result['failure'] is None


def test_a_look_around_while_a_job_runs_is_refused_by_the_executor_and_disturbs_nothing(tmp_path):
    # r1 asks twice in a row: the second ask arrives while the first sweep still runs (BUSY from the own executor)
    table = {('r1', 0): ({'kind': 'look_around'}, []), ('r1', 1): ({'kind': 'look_around'}, []),
             ('r2', 0): ({'kind': 'continue'}, [])}
    _, out, _ = run_arm(tmp_path, 'no_comm', StubModel(scripted(table)), cap_s=30.)
    asks = [d for d in rows(out / 'llm' / 'dispatch.jsonl') if d['action']['kind'] == 'look_around']
    assert asks and all(d['api'] == 'look_around' for d in asks)
    refused_asks = [d for d in asks if not d['ack']['accepted']]
    assert all(d['ack']['rejected_reason'].startswith('BUSY:') for d in refused_asks)


# --------------------------------------------------------------------------- the image bill

def test_the_bill_is_the_studys_text_bill_unchanged_plus_a_fixed_charge_per_image():
    inputs, _, _ = make_inputs('peer_nl', 'r1')
    request = pi.build_request(inputs, window={'window_id': 'w1'})
    bill, tokens = request['billed_tokens'], request['tokens']
    assert tokens['images'] == 2
    assert bill['policy'] == pk.FIXED_PROMPT_POLICY and bill['total_text_billed'] == bill['system_billed'] + tokens['user']
    assert bill['image_policy'] == billing.IMAGE_BILLING_VERSION == 'ugrp.pair_image_billing.v2'
    assert bill['image_tokens_per_image'] == billing.IMAGE_TOKENS_PER_IMAGE == 1490
    assert bill['image_tokens_billed'] == 2 * 1490 and bill['total_billed'] == bill['total_text_billed'] + 2980
    assert billing.billing_problems({'request_id': 'r', 'billed_tokens': bill}) == []
    assert pk.verify_archived_request(pk.archive_request(request)) == []      # the sealed recount still accepts it


def test_the_charge_is_a_function_of_the_image_count_only():
    assert [billing.image_tokens(n) for n in (0, 1, 2)] == [0, 1490, 2980]
    with pytest.raises(ValueError):
        billing.image_tokens(-1)
    with pytest.raises(ValueError):
        billing.image_tokens(1.5)
    one, _, _ = make_inputs('no_comm', 'r1', t=0.)
    two, _, _ = make_inputs('no_comm', 'r1', t=0., frame_no=2)
    a, b = pi.build_request(one), pi.build_request(two)
    assert a['billed_tokens']['image_tokens_billed'] == b['billed_tokens']['image_tokens_billed'] == 2980


def test_an_edited_image_bill_is_detected():
    inputs, _, _ = make_inputs('no_comm', 'r1')
    row = pk.archive_request(pi.build_request(inputs))
    assert billing.billing_problems(row) == []
    for key, value in (('image_tokens_per_image', 0), ('image_tokens_billed', 0), ('total_billed', 1),
                       ('image_policy', 'ugrp.pair_image_billing.v1')):
        edited = json.loads(json.dumps(row))
        edited['billed_tokens'][key] = value
        assert billing.billing_problems(edited), key
    assert billing.billing_problems({'request_id': 'x'})


def test_the_history_keeps_v1_for_the_runs_that_billed_images_zero():
    versions = {row['version']: row for row in billing.IMAGE_BILLING_HISTORY}
    v1 = versions['ugrp.pair_image_billing.v1']
    assert v1['image_tokens_per_image'] == 0 and v1['applied'] is False
    assert any('smoke1' in used for used in v1['used_by']) and any('v97' in used for used in v1['used_by'])
    record = billing.record()
    assert record['version'] == 'ugrp.pair_image_billing.v2' and record['deterministic'] is True
    assert record['calibration']['constant'] == 1490 and record['history'][0]['version'] == v1['version']


def test_in_the_loop_the_sim_cost_includes_the_images_and_the_split_is_recorded(tmp_path):
    result, out, _ = run_arm(tmp_path, 'no_comm', cap_s=12.)
    metrics = result['metrics']
    requests = rows(out / 'llm' / 'requests.jsonl')
    assert all(r['billed_tokens']['total_billed'] == r['billed_tokens']['total_text_billed'] + 2980 for r in requests)
    study = json.loads((out / 'llm' / 'study_config.json').read_text())
    assert study['input_billing']['version'] == 'ugrp.pair_image_billing.v2' and study['own_status']['version']
    assert 'look_around' in study['action_kinds']
    posted = metrics['http_attempts']
    assert metrics['image_billing'] == 'ugrp.pair_image_billing.v2' and metrics['input_tokens_image'] == 2980 * posted
    assert metrics['input_tokens_charged'] == metrics['input_tokens'] + metrics['input_tokens_image']
    # the SIM seconds the scheduler charged contain the image part: never below overhead + the full input bill
    from harness.zone_sim_cost import params
    cost = params()
    floor = sum(cost.scale * (cost.call_overhead_s + cost.input_token_s * r['billed_tokens']['total_billed'])
                for r in requests)
    assert metrics['model_cost_sim_s'] >= round(floor, 1) - 1e-9
    text_only = sum(cost.scale * (cost.call_overhead_s + cost.input_token_s * r['billed_tokens']['total_text_billed'])
                    for r in requests)
    assert floor - text_only == pytest.approx(len(requests) * cost.scale * cost.input_token_s * 2980)


def test_the_image_charge_raises_the_charged_sim_seconds_of_one_call_by_a_fixed_amount():
    from harness.zone_sim_cost import Attempt, call_cost
    inputs, _, _ = make_inputs('no_comm', 'r1')
    bill = pi.build_request(inputs)['billed_tokens']
    kw = dict(output_tokens=60, utterances=0)
    v1 = call_cost([Attempt(input_tokens=bill['total_text_billed'], **kw)])
    v2 = call_cost([Attempt(input_tokens=bill['total_billed'], **kw)])
    assert v2.sim_s - v1.sim_s == pytest.approx(0.6, abs=0.11)            # 2980 tokens x 0.0002 s, on the 0.1 s grid
    again = call_cost([Attempt(input_tokens=bill['total_billed'], **kw)])
    assert again.to_dict() == v2.to_dict()                                   # deterministic: same request, same cost


def test_the_bundle_records_the_bill_the_status_and_the_actions():
    from harness import pair_llm_contract as contract
    row = contract.bundle('peer_nl')
    assert row['workflow_version'] == '3.12.0' and row['execution_bundle_id'] == 'zone-pair-llm-v100'
    assert row['cost_model']['input_billing']['version'] == 'ugrp.pair_image_billing.v2'
    assert row['cost_model']['version'] == 'zone_sim_cost.v1'                    # the cost parameters are unchanged
    assert row['prompt']['own_status']['version'] == st.STATUS_VERSION
    assert row['prompt']['action_kinds'][-1] == 'look_around' and 'placeholder continue' in row['prompt']['look_around']
    for needed in ('harness/pair_llm_billing.py', 'harness/pair_llm_status.py', 'harness/pair_llm_live.py'):
        assert needed in row['source_sha256']
    assert contract.bundle('rule')['cost_model']['input_billing'] is None
