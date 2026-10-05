"""Own status (refusal feedback), the look_around option and the image bill of the pair LLM layer (v100).

The status is the robot's OWN software state told to its model; these tests pin what it may contain (a closed
record, no raw reason, no name of a partner-caused reason, no ground truth) and that the refusal reaches the model
in the real loop, identically in both LLM arms. No physics, network or real model: replies come from stubs behind the real proxy completer.
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
    # the NAME of a partner-caused refusal is folded (the refused-claim event itself stays visible, in both arms)
    ('PAIR_SUBMISSION_MISMATCH', 'other'), ('PAIR_STATIC_INPUT_MISMATCH', 'other'),
    ('PAIR_REQUIRES_NOSLIP_WELD_OFF', 'other'), ('PAIR_CALIBRATION_MISMATCH', 'other'),
    ('INVALID_PAIR_PLAN', 'other')])
def test_a_non_retryable_refusal_is_claim_rejected_and_partner_caused_names_become_other(reason, token):
    row = build(view=gate_view(event=refused(reason, 9., retryable=False), total=1))
    assert row['last_outcome'] == 'claim_rejected' and row['reason'] == token
    assert st.status_violations(row) == []


@pytest.mark.parametrize('reason', ['PAIR_RENDEZVOUS_TIMEOUT', 'PAIR_SUBMISSION_MISMATCH',
                                    'PAIR_STATIC_INPUT_MISMATCH', 'PARTNER_ABORT', 'PARTNER_SILENT',
                                    'PARTNER_MISSED_GO', 'PAIR_JOB_LOST', 'M2_FAILED'])
def test_a_partner_caused_job_end_is_a_job_end_reason_that_becomes_queue_empty(reason):
    """``PAIR_RENDEZVOUS_TIMEOUT`` is not a start refusal: ``PairTeam.start`` hands it to ``first.abort`` only, so it
    reaches the waiting robot as the reason of its own job end. Any end that is not a local timeout is
    ``queue_empty`` (the study's own classification, ``on_executor_event``)."""
    assert st.end_class(reason) == 'queue_empty'
    row = build(last_end={'job_kind': 'pair_carry', 'sim_s': 30., 'reason_class': st.end_class(reason)})
    assert row['last_outcome'] == 'pair_job_ended' and row['reason'] == 'queue_empty'
    assert reason not in json.dumps(row) and st.status_violations(row) == []
    assert st.end_class('LOCAL_TIMEOUT') == 'local_timeout'


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
    assert prompts.PROMPT_VERSION.endswith('.v4')


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
    assert dispatch.PAIR_ACTION_KINDS == tuple(k for k in zp.ROBOT_ACTION_KINDS if k != 'wait') + ('look_around', 'carry_decision', 'post_look_decision')


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


def test_high_runtime_refuses_a_model_look_while_its_own_bounded_recovery_is_running(tmp_path):
    table = {('r1', 0): (claim_action('r1', ORDER), []), ('r2', 0): (claim_action('r2', ORDER), []),
             ('r1', 1): ({'kind': 'look_around'}, [])}
    result, out, _ = run_arm(tmp_path, 'no_comm', StubModel(scripted(table)), cap_s=30.)
    dispatched = [d for d in rows(out / 'llm' / 'dispatch.jsonl') if d['action']['kind'] == 'look_around']
    assert len(dispatched) == 1 and dispatched[0]['api'] == 'look_around' and dispatched[0]['actor'] == 'r1'
    ack = dispatched[0]['ack']
    assert ack['accepted'] is False and ack['arguments'] == {'observe': 'wide_look'}
    assert ack['rejected_reason'].startswith('BUSY:look_around:')
    job_id = ack['rejected_reason'].split(':', 2)[2]
    # #363 already started its own bounded recovery. The model must not preempt it or add a second sweep.
    own = [e for e in rows(out / 'llm' / 'executor_events.jsonl')
           if e['robot_id'] == 'r1' and e['job_id'] == job_id]
    started = next(e for e in own if e['event'] == 'job_started')
    ended = next(e for e in own if e['event'] == 'job_done')
    assert started['sim_s'] < ack['sim_s'] < ended['sim_s']
    recovery = json.loads((out / 'student_record.json').read_text())['look_recovery']['robots']['r1']
    assert any(a['job_id'] == job_id and a['trigger'] == 'SELF_UNCERTAIN' for a in recovery['attempts'])
    history = [e for row in rows(out / 'llm' / 'requests.jsonl') if json.loads(row['user'])['robot_id'] == 'r1'
               for e in json.loads(row['user'])['own_command_history']]
    assert any(e['kind'] == 'observe' and e['local_state'] == 'command_rejected' for e in history)
    later = [r['own_status'] for r in rows(out / 'llm' / 'inputs.jsonl')
             if r['robot'] == 'r1' and r['sim_s'] > dispatched[0]['sim_s']]
    assert any(s['last_outcome'] == 'look_around_ended' and s['reason'] == 'queue_empty' for s in later)
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
    assert 'look_around' in row['prompt']['action_kinds'] and 'placeholder continue' in row['prompt']['look_around']
    for needed in ('harness/pair_llm_billing.py', 'harness/pair_llm_status.py', 'harness/pair_llm_live.py'):
        assert needed in row['source_sha256']
    assert contract.bundle('rule')['cost_model']['input_billing'] is None


# --------------------------------------------------------------------------- partner events: identical in both LLM arms

def partner_run(tmp_path, arm, *, r2):
    """r1 claims the real order; r2 claims ``r2`` (a mismatching submission) or does not claim at all."""
    from tests.pair_llm_fakes import ReadyRuntime
    table = {('r1', 0): (claim_action('r1', ORDER), [])}
    if r2 is not None:
        table[('r2', 0)] = (claim_action('r2', r2), [])
    model = StubModel(scripted(table, default=lambda rid, i, body, sys_text: ({'kind': 'continue'}, [])))
    return run_arm(tmp_path, arm, model, cap_s=40., runtime_factory=ReadyRuntime, name=f'{arm}-{bool(r2)}')


def status_trace(out):
    return [(r['robot'], r['sim_s'], r['own_status']) for r in rows(out / 'llm' / 'inputs.jsonl')]


def test_a_partner_submission_mismatch_gives_identical_own_status_in_both_llm_arms(tmp_path):
    """M1 of the #371 review (accepted design): a partner-caused refusal reveals ONE bit through the robot's own
    command outcome (my claim was not accepted / the pair job ended), identically in no_comm and peer_nl; the NAME of
    the reason is folded to ``other``."""
    wrong = {'order_id': ORDER['order_id'], 'destination_zone': 'A'}              # a different submission than r1's
    traces, outs = {}, {}
    for arm in ('no_comm', 'peer_nl'):
        _, out, _ = partner_run(tmp_path, arm, r2=wrong)
        traces[arm], outs[arm] = status_trace(out), out
        gate = json.loads((out / 'llm' / 'claim_gate.json').read_text())['log']
        submitted = {r['robot_id']: r for r in gate if r['event'] == 'claim_submitted'}
        assert submitted['r1']['accepted'] is True and submitted['r2']['accepted'] is False
        assert submitted['r2']['reason'] == 'PAIR_SUBMISSION_MISMATCH'          # the gate (own log) keeps the real name
    assert traces['no_comm'] == traces['peer_nl']                                # identical, call by call
    last = {rid: [s for r, _, s in traces['no_comm'] if r == rid][-1] for rid in ('r1', 'r2')}
    assert last['r2']['last_outcome'] == 'claim_rejected' and last['r2']['reason'] == 'other'
    assert last['r1']['last_outcome'] == 'pair_job_ended' and last['r1']['reason'] == 'queue_empty'
    for arm, out in outs.items():                                                # the name never reaches the model
        wire = ' '.join(r['system'] + r['user'] for r in rows(out / 'llm' / 'requests.jsonl'))
        assert 'PAIR_SUBMISSION_MISMATCH' not in wire and 'SUBMISSION' not in wire.upper().replace('SUBMITTED', '')


def test_a_waiting_robots_job_that_ends_without_a_partner_submission_is_queue_empty_in_both_arms(tmp_path):
    """r2 never claims, so r1's job ends without a partner. On the fake physics the end reason is
    ``INVALID_OWN_IMAGE`` (its synthetic frames fail the pair job's own-image check before the 5 s window runs out);
    the real ``PAIR_RENDEZVOUS_TIMEOUT`` is a job-end reason too and is pinned as ``queue_empty`` by
    ``test_a_partner_caused_job_end_is_a_job_end_reason_that_becomes_queue_empty``. Whatever the reason, the model
    sees only the class, the same in both arms."""
    traces = {}
    for arm in ('no_comm', 'peer_nl'):
        _, out, _ = partner_run(tmp_path, arm, r2=None)
        traces[arm] = status_trace(out)
        failed = [e for e in rows(out / 'llm' / 'executor_events.jsonl')
                  if e['robot_id'] == 'r1' and e['event'] == 'job_failed' and e['job_kind'] == 'pair_carry']
        assert failed
        reason = failed[0]['detail']['reason']
        wire = ' '.join(r['system'] + r['user'] for r in rows(out / 'llm' / 'requests.jsonl'))
        assert reason not in wire                                                  # the raw reason never reaches the model
    assert traces['no_comm'] == traces['peer_nl']
    final = [s for r, _, s in traces['no_comm'] if r == 'r1'][-1]
    assert final['last_outcome'] == 'pair_job_ended' and final['reason'] == 'queue_empty'


# --------------------------------------------------------------------------- the stored image_policy decides the check

SMOKE1_V1_BILLS = (   # billed_tokens of v99 smoke1 request rows (call 1, a later call): no image keys, images billed 0
    {'policy': 'fixed_prompt_equalized.v1', 'tokenizer': 'ugrp.zone_study_tokens.v1', 'system_actual': 914,
     'system_billed': 914, 'user': 2100, 'images': 2, 'total_text_billed': 3014},
    {'policy': 'fixed_prompt_equalized.v1', 'tokenizer': 'ugrp.zone_study_tokens.v1', 'system_actual': 914,
     'system_billed': 914, 'user': 2259, 'images': 2, 'total_text_billed': 3173})
SMOKE1_REQUESTS = Path('/Users/changmin/projects/ugrp/outputs/pair-llm-v99-live/smoke1/peer_nl/llm/requests.jsonl')


def test_v1_rows_have_no_image_keys_and_are_checked_as_zero_tokens_per_image():
    for bill in SMOKE1_V1_BILLS:
        row = {'request_id': 'req_smoke1', 'billed_tokens': dict(bill)}
        assert billing.billing_problems(row) == []                                 # v1: absent policy = v1
        assert billing.billing_problems(
            {'request_id': 'r', 'billed_tokens': dict(bill, image_policy=billing.IMAGE_BILLING_V1)}) == []
        # a run of the CURRENT bundle must have used v2: a v1-shaped row cannot be passed off as one
        assert billing.billing_problems(row, require=billing.IMAGE_BILLING_VERSION)
    assert billing.IMAGE_TOKENS_BY_POLICY == {'ugrp.pair_image_billing.v1': 0, 'ugrp.pair_image_billing.v2': 1490}


def test_a_v1_row_that_states_image_keys_must_state_zero_and_an_unknown_policy_is_refused():
    base = dict(SMOKE1_V1_BILLS[0])
    ok = dict(base, image_policy=billing.IMAGE_BILLING_V1, image_tokens_per_image=0, image_tokens_billed=0,
              total_billed=base['total_text_billed'])
    assert billing.billing_problems({'request_id': 'r', 'billed_tokens': ok}) == []
    for key, value in (('image_tokens_per_image', 1490), ('image_tokens_billed', 2980), ('total_billed', 6000)):
        assert billing.billing_problems({'request_id': 'r', 'billed_tokens': dict(ok, **{key: value})}), key
    assert billing.billing_problems({'request_id': 'r', 'billed_tokens': dict(base, image_policy='ugrp.x.v3')})
    inputs, _, _ = make_inputs('no_comm', 'r1')
    v2 = pk.archive_request(pi.build_request(inputs))
    assert billing.billing_problems(v2, require=billing.IMAGE_BILLING_VERSION) == []
    stripped = json.loads(json.dumps(v2))
    for key in ('image_policy', 'image_tokens_per_image', 'image_tokens_billed', 'total_billed'):
        del stripped['billed_tokens'][key]
    assert billing.billing_problems(stripped) == []                              # reads as a v1 row (images 0) ...
    assert billing.billing_problems(stripped, require=billing.IMAGE_BILLING_VERSION)   # ... which a v2 run may not be


@pytest.mark.skipif(not SMOKE1_REQUESTS.is_file(), reason='the preserved v99 smoke1 archive is local evidence only')
def test_the_preserved_v99_smoke1_request_rows_verify_under_v1_with_zero_problems():
    smoke = rows(SMOKE1_REQUESTS)
    assert len(smoke) == 12 and all('image_policy' not in r['billed_tokens'] for r in smoke)
    assert [p for r in smoke for p in billing.billing_problems(r)] == []
    assert all(billing.billing_problems(r, require=billing.IMAGE_BILLING_VERSION) for r in smoke)


# --------------------------------------------------------------------------- the two clocks are named

def test_dispatch_rows_and_executor_events_name_both_clocks_and_the_reset_offset(tmp_path):
    table = {('r1', 0): (claim_action('r1', ORDER), []), ('r2', 0): (claim_action('r2', ORDER), [])}
    result, out, _ = run_arm(tmp_path, 'no_comm', StubModel(scripted(table)), cap_s=14.)
    claims = [d for d in rows(out / 'llm' / 'dispatch.jsonl') if d['ack']]
    assert claims
    for d in claims:
        assert d['sim_s'] == d['sim_s_since_reset'] and d['sim_s_absolute'] == d['ack']['sim_s']
        assert d['reset_offset_s'] == pytest.approx(result['reset_sim_s'])         # 1.0 on the fake, 1.3 in smoke1
    others = [d for d in rows(out / 'llm' / 'dispatch.jsonl') if not d['ack']]
    assert all(d['sim_s_absolute'] is None and d['reset_offset_s'] is None for d in others)
    events = rows(out / 'llm' / 'executor_events.jsonl')
    assert events and all(e['sim_s_absolute'] == e['sim_s'] for e in events)
    for e in events:           # received by the harness at or after the event time on the harness clock (one tick later)
        late = e['delivered_at_sim_s_since_reset'] - (e['sim_s'] - result['reset_sim_s'])
        assert -1e-6 <= late <= 0.1 + 1e-6
    study = json.loads((out / 'llm' / 'study_config.json').read_text())
    assert set(study['clocks']) == {'sim_s', 'sim_s_since_reset', 'sim_s_absolute', 'reset_offset_s',
                                    'delivered_at_sim_s_since_reset', 'claim_gate_log'}


# --------------------------------------------------------------------------- the arms differ only in the channel

def test_the_prompts_of_the_two_llm_arms_differ_only_in_the_channel_and_messages_blocks():
    from harness import pair_llm_prompts_ko as prompts
    for rid in ('r1', 'r2'):
        a, b = prompts.prompt_parts('no_comm', rid), prompts.prompt_parts('peer_nl', rid)
        assert list(a) == list(b)
        assert sorted(k for k in a if a[k] != b[k]) == ['channel', 'messages']
        rest = [k for k in a if k not in ('channel', 'messages')]
        assert '\n\n'.join(a[k] for k in rest) == '\n\n'.join(b[k] for k in rest)
        assert prompts.system_prompt('no_comm', rid) != prompts.system_prompt('peer_nl', rid)
    # the request body differs only in the condition label, the channel description and the inbox
    for rid in ('r1', 'r2'):
        one, _, _ = make_inputs('no_comm', rid)
        two, _, _ = make_inputs('peer_nl', rid)
        pa, pb = one.payload_dict(), two.payload_dict()
        assert sorted(k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k)) == ['channel', 'condition', 'inbox']


def test_the_prompt_does_not_state_that_a_look_around_recovers_the_position():
    from harness import pair_llm_prompts_ko as prompts
    text = prompts.system_prompt('no_comm', 'r1')
    assert '제자리에서 돌며' in text and '도움이 될 수' in text and '보장되지는 않습니다' in text
    assert '다시 추정할 수 있습니다' not in text and '풀리지 않습니다' not in text


# --------------------------------------------------------------------------- retired (run-recorded) bundles

RETIRED = Path(__file__).resolve().parents[1] / 'experiments' / '2026-10-03-pair-llm-viability' / 'retired-bundle'
RETIRED_SHA256 = {   # bytes of the files at the commits that ran them (v97 stub smoke b201f777, v99 smoke1 ad1dda73)
    'v97/configs/pair_llm_v97.json': 'ca0c34b2f7acf904376584ebb2f595b1278275c447e827292666b2e14f01b808',
    'v97/configs/simulation_workflows.d/pair_llm_v97.json':
        '9077a7dd83bda8123ef6c844827f66c689227465315f99cd4206878d98587eb6',
    'v99/configs/pair_llm_v99.json': '284232e5955eb4c0b753497c8e59f81a072506b08d33ff8ad1e9183c496137b4',
    'v99/configs/simulation_workflows.d/pair_llm_v99.json':
        'a0d8a41eebd04d2656acdfe622cec5ba3ef5af5baa547192f339fb61900719c3'}


def test_the_run_recorded_v97_and_v99_bundle_files_are_kept_byte_identical_and_not_registered():
    import hashlib
    for rel, digest in RETIRED_SHA256.items():
        assert hashlib.sha256((RETIRED / rel).read_bytes()).hexdigest() == digest, rel
    repo = RETIRED.parents[2]
    assert not list((repo / 'configs').glob('pair_llm_v97.json')) and not list((repo / 'configs').glob('pair_llm_v99.json'))
    catalog = json.loads((RETIRED / 'v99/configs/simulation_workflows.d/pair_llm_v99.json').read_text())
    assert catalog['workflows'][0]['id'] == 'zone-pair-llm-v99' and catalog['workflows'][0]['version'] == '3.11.0'
    live = json.loads((repo / 'configs' / 'pair_llm_v100.json').read_text())
    assert live['execution_bundle_id'] == 'zone-pair-llm-v100' and live['workflow_version'] == '3.12.0'


# --------------------------------------------------------------------------- the prompt holds no unfilled placeholder

def test_the_final_system_text_of_every_arm_and_robot_has_no_placeholder_and_the_enforced_message_cap():
    """v99 smoke1 showed the literal ``__CHARS__`` to the peer_nl model. The slot now holds the study's own prompt
    value ``zp.PROMPT_TEXT_CHARS`` (no new policy), which the transport enforces as a hard limit at
    ``zp.MAX_TEXT_CHARS``; the final text of both conditions x both robots must hold no ``__X__`` slot."""
    import re
    from harness import pair_llm_prompts_ko as prompts
    cap = zp.PROMPT_TEXT_CHARS
    assert cap == 240 and cap <= zp.MAX_TEXT_CHARS
    for condition in ('no_comm', 'peer_nl'):
        for rid in ('r1', 'r2'):
            text = prompts.system_prompt(condition, rid)
            assert '__' not in text and not re.findall(r'__[A-Za-z0-9_]+__', text), (condition, rid)
            inputs, _, _ = make_inputs(condition, rid)
            wire = pi.build_request(inputs, window={'window_id': 'w1'} if condition == 'peer_nl' else None
                                    )['messages'][0]['content']
            assert '__' not in wire and wire == text                          # what the model receives is this text
            asked = re.findall(r'text는 (\d+)자 이내', text)
            assert asked == ([str(cap)] if condition == 'peer_nl' else []), (condition, rid, asked)
    # the number the prompt gives is a length the sealed validator accepts; the hard limit is the study's 600
    inputs, _, _ = make_inputs('peer_nl', 'r1')
    kw = dict(request_id='req_t1', condition=dispatch.study_spec('peer_nl'), actor='r1', order_ids=inputs.order_ids(),
              item_ids=inputs.item_ids(), roles_by_order=inputs.roles_by_order(), vocabulary=inputs.vocabulary(),
              passages=inputs.passages(), location_refs=inputs.location_refs(), robots=('r1', 'r2'))
    say = lambda n: [{'recipients': ['r2'], 'reply_to': None, 'text': 'x' * n}]
    assert dispatch.validate_reply(reply({'kind': 'continue'}, messages=say(cap)), **kw)['messages']
    with pytest.raises(zp.ProtocolError, match='longer than'):
        dispatch.validate_reply(reply({'kind': 'continue'}, messages=say(zp.MAX_TEXT_CHARS + 1)), **kw)


def test_system_prompt_fails_closed_when_a_template_slot_is_left_unfilled(monkeypatch):
    from harness import pair_llm_prompts_ko as prompts
    monkeypatch.setattr(prompts, 'KO_PAIR_MESSAGES', prompts.KO_PAIR_MESSAGES + '\n- limit: __LIMIT__')
    with pytest.raises(zp.ProtocolError, match='__LIMIT__'):
        prompts.system_prompt('peer_nl', 'r1')
    assert 'limit' not in prompts.system_prompt('no_comm', 'r1')                 # no_comm has no messages schema


# --------------------------------------------------------------------------- own_status does not depend on the reset origin

def link_at(origin):
    """A ``PairLink`` over a real ``ClaimGate`` whose backend clock runs ``origin`` SIM seconds ahead of the harness."""
    import types
    from harness.pair_llm_runtime import ClaimGate
    gate = ClaimGate(('r1', 'r2'))
    gate.bind(lambda rid, order, zone, partner, *, now: {'robot_id': rid, 'accepted': False,
                                                         'rejected_reason': 'SELF_UNCERTAIN', 'job_id': None})
    runtime = types.SimpleNamespace(actors={'r1': object(), 'r2': object()}, gate=gate)
    return gate, dispatch.PairLink(runtime, 'r1', origin_s=origin)


def relative_story(origin, *, refused_at=None):
    """The same RELATIVE facts (permit 10.0, own look-around end 10.5, optional refusal) at one backend origin."""
    gate, link = link_at(origin)
    gate.grant('r1', 'cargoX', 'B', 'r2', now=10.0 + origin, call_ref='call-1')          # absolute, as the gate stores it
    if refused_at is not None:
        gate.start('r1', now=refused_at + origin)
    last_end = {'job_kind': 'look_around', 'sim_s': 10.5, 'reason_class': 'queue_empty'}   # harness clock, as delivered
    view = link.gate_view()
    row = st.build(now=11.0, claim_issued_s=9.0, view=view, job_kind=None, last_end=last_end,
                   refusals_since_last_call=2)
    return row, view, gate


ORIGINS = (0., 1.3, 2.6, 7.0)


@pytest.mark.parametrize('refused_at, outcome, reason', [
    (None, 'look_around_ended', 'queue_empty'),            # permit 10.0 < end 10.5: the end is the latest fact
    (10.3, 'look_around_ended', 'queue_empty'),            # a refusal before the end
    (10.7, 'start_refused', 'SELF_UNCERTAIN')])            # a refusal after the end
def test_own_status_is_identical_for_the_same_relative_events_at_every_reset_origin(refused_at, outcome, reason):
    """Codex review (#375) P2: a permit at relative 10.0 and a look-around end at relative 10.5 picked the older
    ``claim_released`` at origin 1.3 because the gate's absolute time was compared with the harness clock."""
    rows = {origin: relative_story(origin, refused_at=refused_at)[0] for origin in ORIGINS}
    assert len({json.dumps(r, sort_keys=True) for r in rows.values()}) == 1, rows
    assert rows[0.]['last_outcome'] == outcome and rows[0.]['reason'] == reason


def test_the_gate_view_is_on_the_harness_clock_and_leaves_the_gates_own_record_absolute():
    for origin in ORIGINS:
        row, view, gate = relative_story(origin, refused_at=10.7)
        assert view['permit_released_at_sim_s'] == pytest.approx(10.0)
        assert view['last_event']['sim_s'] == pytest.approx(10.7) and view['refusal_total'] == 1
        assert gate.status_view('r1')['permit_released_at_sim_s'] == pytest.approx(10.0 + origin)   # untouched
        assert gate.log[0]['sim_s'] == pytest.approx(10.0 + origin)


def test_without_the_conversion_the_origin_would_change_the_status():
    """Documents the defect the conversion fixes: feeding the gate's absolute view to the builder is origin-dependent."""
    picked = {}
    for origin in (0., 1.3):
        gate, _ = link_at(origin)
        gate.grant('r1', 'cargoX', 'B', 'r2', now=10.0 + origin)
        row = st.build(now=11.0, claim_issued_s=9.0, view=gate.status_view('r1'), job_kind=None,
                       last_end={'job_kind': 'look_around', 'sim_s': 10.5, 'reason_class': 'queue_empty'},
                       refusals_since_last_call=0)
        picked[origin] = row['last_outcome']
    assert picked == {0.: 'look_around_ended', 1.3: 'claim_released'}


def backend_with_origin(origin):
    from tests.pair_llm_fakes import FakeBackend

    class Backend(FakeBackend):
        def reset(self, cap):
            self.now = origin
            return self.now
    return Backend


def test_in_the_loop_the_outcome_sequence_of_own_status_is_the_same_at_every_reset_origin(tmp_path):
    """Whole loop, same scripted model, fake physics reset at 0.0 / 1.3 / 4.9 SIM s (the case runner refuses a reset
    longer than 5 s, so 7.0 is covered by the unit test above). The tick grid shifts a call by 0.1 SIM s, so the
    comparison is on outcomes, reasons and refusal counts; ``since_claim_s`` must be the harness-clock difference."""
    traces = {}
    for origin in (0., 1.3, 4.9):
        result, out, _ = run_arm(tmp_path, 'no_comm', cap_s=30., backend=backend_with_origin(origin),
                                 name=f'origin-{origin}')
        assert result['status'] == 'COLLECTED_UNQUALIFIED' and result['reset_sim_s'] == pytest.approx(origin)
        traces[origin] = rows(out / 'llm' / 'inputs.jsonl')
    shape = lambda trace: [(r['robot'], r['own_status']['last_outcome'], r['own_status']['reason'],
                            r['own_status']['refusals_since_last_call']) for r in trace]
    assert shape(traces[1.3]) == shape(traces[0.]) == shape(traces[4.9])
    assert any(s[1] == 'look_around_ended' for s in shape(traces[4.9]))        # the case the old mixed clocks lost
    for origin, trace in traces.items():
        for r in trace:
            since = r['own_status']['since_claim_s']
            assert since is None or 0 <= since <= r['sim_s'] + 1e-6              # a harness-clock age, never absolute
