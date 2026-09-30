"""Fourth independent P06 review, PR head 3a46de0b. Synthetic offline only.

Run in the PR's git archive. Main lacks the candidate modules; a module skip on
the notes branch is not verification. All eleven counterexamples are required
passing regressions; no xfail or optional dependency may bypass the verdicts.
"""
import pytest

j = pytest.importorskip('scripts.zone_study_evidence_join')
from harness import zone_study_referee as zr
from harness.zone_study_contract import digest
from scripts import zone_study_evidence_cohort as cohort
from tests.zone_evidence_fixtures import read, refresh_receipts
from tests.zone_evidence_fixtures import planned, put, raw_source
from tests.zone_evidence_fixtures import MAP, at_zone, feed
from tests.zone_evidence_assertions import checked_cohort


def pinned_plan(n=2, order_count=2):
    plan, bundle = planned(n, order_count)
    # Real run_bundle() pins this profile. The submitted minimal raw fixture
    # omits it, so include it BEFORE freezing the external plan, not after.
    bundle['referee'] = zr.profile()
    for row in plan['admitted']:
        row['identity']['bundle_sha256'] = digest(bundle)
    plan = j.freeze_plan(plan['admitted'])
    return plan, bundle


def save_outcome(src, record, referee):
    """Use production derivations and preserve the existing admission/pin."""
    old = read(src, 'eval_only/referee.json')
    put(src, 'eval_only/referee.json', {**old, **referee.record()})
    put(src, 'study/trial_record.json', record)
    evaluation = {
        **zr.evaluation_block(record, referee),
        **j.envelope_keys(record['evidence_identity'], record['orders']),
        'evidence_identity': record['evidence_identity'],
        'plan_sha256': record['plan_sha256'],
    }
    put(src, 'eval_only/evaluation.json', evaluation)
    for path, field in (('result.json', 'study'), ('manifest.json', 'terminal')):
        row = read(src, path)
        row[field].update(end_reason=record['end_reason'], end_sim_s=record['end_sim_s'])
        put(src, path, row)
    refresh_receipts(src)


def published(root, plan, sources):
    path = put(root, 'external-plan.json', plan)
    pin = digest(plan)
    result = checked_cohort(path, pin, sources, root / 'events')
    assert result['admitted_trials'] == len(plan['admitted'])
    assert read(root, 'external-plan.json') == plan
    print({'admitted': result['admitted_trials'], 'successes': result['successes'],
           'invalid': result['invalid_trials'], 'success_rate': result['success_rate']}, flush=True)
    return result


def redelivery_record(src, release):
    record = read(src, 'study/trial_record.json')
    ref = zr.Referee(record['orders'], MAP)
    feed(ref, 2., 4., {'item-0': at_zone('A'), 'item-1': at_zone('C')})
    feed(ref, 5., 6., {'item-0': at_zone('A', held=True), 'item-1': at_zone('C')})
    feed(ref, 6.1, 8.1, {'item-0': at_zone('A', held=True), 'item-1': at_zone('A')})
    assert not ref.orders_complete()
    feed(ref, release, release + 2., {'item-0': at_zone('A'), 'item-1': at_zone('A')})
    assert ref.orders_complete()
    record.update(end_sim_s=ref.last_t, end_reason='sim_horizon')
    zr.apply_to_record(record, ref)
    return record, ref


@pytest.mark.parametrize('release', [10.1, 11.0])
def test_late_redelivery_cannot_resurrect_a_departed_delivery(tmp_path, release):
    plan, bundle = pinned_plan()
    bad = raw_source(tmp_path, plan, bundle, 0)
    good = raw_source(tmp_path, plan, bundle, 1)
    record, ref = redelivery_record(bad, release)
    cap = record['budget']['sim_horizon_s']
    assert ref.standing['item-0']['confirmed_sim_s'] > cap
    # Raw history proves item-0 departed at 6 s and was not confirmed again
    # before the cap. The other item only becomes delivered at 8.1 s.
    assert [r['sim_s'] for r in ref.history
            if r['item_id'] == 'item-0' and r['event'] == 'departed'] == [6.]
    save_outcome(bad, record, ref)
    summary = published(tmp_path, plan, [bad, good])
    assert summary['successes'] <= 1, summary['trials']


@pytest.mark.parametrize('end', [4.0, 5.0])
def test_failed_final_referee_cannot_join_an_earlier_success_window(tmp_path, end):
    plan, bundle = pinned_plan(order_count=1)
    bad = raw_source(tmp_path, plan, bundle, 0)
    good = raw_source(tmp_path, plan, bundle, 1)
    record = read(bad, 'study/trial_record.json')
    ref = zr.Referee(record['orders'], MAP)
    feed(ref, 2., 4., {'item-0': at_zone('A')})
    feed(ref, 6., 8., {'item-0': at_zone('C')})
    assert not ref.orders_complete()
    record['end_sim_s'] = end  # stale terminal record; admission and raw history unchanged
    record['referee']['deliveries'] = ref.trial_rows()
    save_outcome(bad, record, ref)
    summary = published(tmp_path, plan, [bad, good])
    assert summary['successes'] <= 1, summary['trials']


@pytest.mark.parametrize('field,value', [('settle_s', .1), ('on_floor_max_z_m', .5),
                                       ('settled_speed_m_s', .5), ('held_depart_s', 10.)])
def test_other_referee_policy_cannot_use_the_original_frozen_bundle(tmp_path, field, value):
    plan, bundle = pinned_plan(order_count=1)
    bad = raw_source(tmp_path, plan, bundle, 0)
    good = raw_source(tmp_path, plan, bundle, 1)
    raw = read(bad, 'eval_only/referee.json')
    raw['profile'][field] = value
    raw['profile']['sha256'] = digest({k: v for k, v in raw['profile'].items() if k != 'sha256'})
    assert raw['profile']['sha256'] != bundle['referee']['sha256']
    put(bad, 'eval_only/referee.json', raw)
    evaluation = read(bad, 'eval_only/evaluation.json')
    evaluation['referee_profile_sha256'] = raw['profile']['sha256']
    put(bad, 'eval_only/evaluation.json', evaluation)
    refresh_receipts(bad)
    summary = published(tmp_path, plan, [bad, good])
    assert summary['successes'] <= 1 and summary['invalid_trials'] == 1, summary['trials']


@pytest.mark.parametrize('duration', [0., .1, 1.9])
def test_confirmation_cannot_be_shorter_than_its_pinned_settle_window(tmp_path, duration):
    plan, bundle = pinned_plan(order_count=1)
    bad = raw_source(tmp_path, plan, bundle, 0)
    good = raw_source(tmp_path, plan, bundle, 1)
    raw = read(bad, 'eval_only/referee.json')
    record = read(bad, 'study/trial_record.json')
    assert duration < bundle['referee']['settle_s'] == raw['profile']['settle_s']
    for rows in (raw['history'], raw['deliveries'], list(raw['standing'].values()),
                 record['referee']['deliveries']):
        for row in rows:
            row['confirmed_sim_s'] = row['sim_s'] + duration
    put(bad, 'eval_only/referee.json', raw)
    put(bad, 'study/trial_record.json', record)
    # Only receipts change; evaluation success/counts and the frozen plan do not.
    refresh_receipts(bad)
    summary = published(tmp_path, plan, [bad, good])
    assert summary['successes'] <= 1 and summary['invalid_trials'] == 1, summary['trials']


@pytest.mark.parametrize('release', [9.0, 10.0])
@pytest.mark.parametrize('reverse', [False, True])
def test_normal_redelivery_at_or_before_cap_and_reordering_remain_valid(tmp_path, release, reverse):
    plan, bundle = pinned_plan()
    first = raw_source(tmp_path, plan, bundle, 0)
    second = raw_source(tmp_path, plan, bundle, 1)
    record, ref = redelivery_record(first, release)
    assert ref.standing['item-0']['confirmed_sim_s'] <= record['budget']['sim_horizon_s']
    save_outcome(first, record, ref)
    if reverse:
        raw = read(first, 'eval_only/referee.json')
        raw['history'].reverse()
        raw['deliveries'].reverse()
        record['referee']['deliveries'].reverse()
        put(first, 'eval_only/referee.json', raw)
        put(first, 'study/trial_record.json', record)
        refresh_receipts(first)
    summary = published(tmp_path, plan, [second, first] if reverse else [first, second])
    assert (summary['successes'], summary['invalid_trials']) == (2, 0), summary['sources']


def test_missing_and_duplicate_sources_keep_the_external_denominator(tmp_path):
    plan, bundle = pinned_plan(4, 1)
    good = raw_source(tmp_path, plan, bundle, 0)
    failure = raw_source(tmp_path, plan, bundle, 1, success=False)
    duplicated = raw_source(tmp_path, plan, bundle, 2)
    summary = published(tmp_path, plan, [failure, duplicated, good, duplicated])
    assert (summary['admitted_trials'], summary['successes'], summary['invalid_trials']) == (4, 1, 2)
