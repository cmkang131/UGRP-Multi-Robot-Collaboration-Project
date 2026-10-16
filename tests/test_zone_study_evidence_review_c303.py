"""General raw-relation properties beyond the eleven independent C303 cases."""
import copy
import itertools
import json
import random

import pytest

from harness.zone_study_contract import digest
from scripts import zone_study_evidence_join as join
from scripts import zone_study_evidence_cohort as cohort
from scripts.zone_study_evidence_contract import verify_referee_derivations
from scripts.tensorboard_tools.zone_study import inspect_study
from tests.test_review_303c import (
    source, pristine, read, put, refresh_receipts, assert_rejected_with_fixed_denominator,
)
from tests.test_zone_study_evidence import no_runtime


@pytest.mark.parametrize('field', ['history', 'standing', 'deliveries', 'orders', 'orders_complete',
    'completion_sim_s', 'departed_unsettled', 'last_sample_sim_s', 'profile'])
@pytest.mark.parametrize('optional_counts', [True, False])
def test_missing_required_raw_outcome_is_invalid(source, tmp_path, field, optional_counts):
    referee = read(source, 'eval_only/referee.json')
    referee.pop(field)
    put(source, 'eval_only/referee.json', referee)
    if not optional_counts:
        evaluation = read(source, 'eval_only/evaluation.json')
        for key in ('departures', 'departed_unsettled_items'):
            evaluation.pop(key)
        put(source, 'eval_only/evaluation.json', evaluation)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('field', ['item_id', 'kind', 'zone', 'event', 'sim_s', 'confirmed_sim_s'])
def test_missing_history_outcome_column_is_invalid(source, tmp_path, field):
    referee = read(source, 'eval_only/referee.json')
    referee['history'][0].pop(field)
    put(source, 'eval_only/referee.json', referee)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('field', join.KEY_FIELDS)
@pytest.mark.parametrize('table', ['dispatch', 'inputs', 'history'])
def test_all_six_declared_key_columns_are_checked(source, tmp_path, table, field):
    identity = read(source, 'study/trial_record.json')['evidence_identity']
    if table == 'history':
        referee = read(source, 'eval_only/referee.json')
        row = referee['history'][0]
    else:
        path = source / f'study/{table}.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        row = rows[0]
    row[field] = identity[field] + 1 if field in ('seed', 'attempt') else 'foreign'
    if table == 'history':
        put(source, 'eval_only/referee.json', referee)
    else:
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('table', ['dispatch', 'inputs'])
@pytest.mark.parametrize('field', join.KEY_FIELDS)
def test_explicit_full_composite_key_cannot_be_relabelled(source, tmp_path, table, field):
    record = read(source, 'study/trial_record.json')
    path = source / f'study/{table}.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    oid = rows[0]['action'].get('order_id') if table == 'dispatch' else None
    key = join.key_for(record['evidence_identity'], oid or join.TRIAL_SCOPE)
    key[field] = key[field] + 1 if field in ('seed', 'attempt') else 'foreign'
    rows[0]['evidence_key'] = key
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('damage', ['frame_index', 'frame_t', 'sim_s', 'history_entries',
    'inbox_ids', 'destination_zone', 'role', 'missing_inputs', 'missing_referee'])
def test_raw_content_conflicts_and_missing_tables_are_invalid(source, tmp_path, damage):
    if damage.startswith('missing_'):
        name = {'missing_inputs': 'study/inputs.jsonl', 'missing_referee': 'eval_only/referee.json'}[damage]
        (source / name).unlink()
        # No embedded copy may substitute for a missing required raw table.
        result = read(source, 'result.json')
        result['eval_only'].pop('referee', None)
        put(source, 'result.json', result)
    else:
        table = 'dispatch' if damage in ('destination_zone', 'role') else 'inputs'
        path = source / f'study/{table}.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        row = rows[0]['action'] if table == 'dispatch' else rows[0]
        row[damage] = {'destination_zone': 'B', 'role': 'east', 'inbox_ids': ['foreign']}.get(
            damage, row.get(damage, 0) + 1 if isinstance(row.get(damage), (int, float)) else None)
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


def test_missing_optional_counts_preserve_valid_raw_success(source):
    evaluation = read(source, 'eval_only/evaluation.json')
    for key in ('departures', 'departed_unsettled_items'):
        evaluation.pop(key)
    put(source, 'eval_only/evaluation.json', evaluation)
    refresh_receipts(source)
    _, values, _ = inspect_study(source)
    assert values['evaluation/reported_success'] is True


def test_exhaustive_independent_referee_row_permutations(source):
    """6^3 = 216 permutations of three unordered raw/trial relations."""
    record = read(source, 'study/trial_record.json')
    referee = read(source, 'eval_only/referee.json')
    evaluation = read(source, 'eval_only/evaluation.json')
    identity = record['evidence_identity']
    expected = verify_referee_derivations(record, evaluation, referee, identity)
    original = copy.deepcopy(referee)
    trial_rows = copy.deepcopy(record['referee']['deliveries'])
    permutations = list(itertools.permutations(range(len(original['history']))))
    checked = 0
    for h, d, t in itertools.product(permutations, repeat=3):
        referee['history'] = [original['history'][i] for i in h]
        referee['deliveries'] = [original['deliveries'][i] for i in d]
        record['referee']['deliveries'] = [trial_rows[i] for i in t]
        assert verify_referee_derivations(record, evaluation, referee, identity) == expected
        checked += 1
    assert checked == 216


def test_permutations_preserve_raw_publication_verdict(source):
    referee = read(source, 'eval_only/referee.json')
    original = copy.deepcopy(referee['history'])
    plan = read(source, 'study/frozen_plan.json')
    for permutation in itertools.permutations(original):
        referee['history'] = list(permutation)
        put(source, 'eval_only/referee.json', referee)
        refresh_receipts(source)
        summary = cohort.collect(plan, digest(plan), [source])
        assert (summary['admitted_trials'], summary['successes'], summary['invalid_trials']) == (1, 1, 0)


def test_duplicate_referee_key_stays_invalid_after_canonical_sort(source, tmp_path):
    referee = read(source, 'eval_only/referee.json')
    referee['history'].append(copy.deepcopy(referee['history'][0]))
    put(source, 'eval_only/referee.json', referee)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('table', ['dispatch', 'inputs'])
def test_complete_zero_call_success_requires_empty_tables(tmp_path, table):
    from tests.test_zone_study_evidence_join import planned, raw_source
    plan, bundle = planned(1)
    src = raw_source(tmp_path, plan, bundle, 0)
    assert cohort.collect(plan, digest(plan), [src])['successes'] == 1
    (src / f'study/{table}.jsonl').unlink()
    assert_rejected_with_fixed_denominator(src, tmp_path / 'events')


@pytest.mark.parametrize('recover', [False, True])
def test_history_reconstruction_keeps_failures_and_recoveries_order_independent(source, recover):
    from harness import zone_study_referee as zr
    from tests.test_zone_study_referee import MAP, at_zone, feed
    record = read(source, 'study/trial_record.json')
    identity = record['evidence_identity']
    ref = zr.Referee(record['orders'], MAP, evidence_key=record['evidence_key'])
    truth = {'box_00': at_zone('A'), 'box_02': at_zone('B'), 'box_05': at_zone('C')}
    feed(ref, 0., 2., truth)
    truth['box_00'] = at_zone('C')
    feed(ref, 2.1, 4.1, truth)  # departure followed by a confirmed misdelivery
    if recover:
        truth['box_00'] = at_zone('A')
        feed(ref, 4.2, 6.2, truth)
    record.update(end_sim_s=10., end_reason='sim_horizon')
    zr.apply_to_record(record, ref)
    referee = {**ref.record(), **join.envelope_keys(identity, record['orders']),
               'evidence_identity': identity, 'plan_sha256': record['plan_sha256']}
    evaluation = zr.evaluation_block(record, ref)
    expected = verify_referee_derivations(record, evaluation, referee, identity)
    assert expected['success'] is recover
    rng = random.Random(303_3 + recover)
    for _ in range(128):
        for rows in (referee['history'], referee['deliveries'], record['referee']['deliveries']):
            rng.shuffle(rows)
        assert verify_referee_derivations(record, evaluation, referee, identity) == expected
