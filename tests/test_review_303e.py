"""Fifth independent P06 review: pure samples, no physics or model calls.

Execute in PR 303's archived tree. A skip on the notes branch is not evidence.
All generalization controls and eight E303-1 publication probes must pass.
Source keys are supplied before the first sample; no evidence is relabelled.
"""
import copy
import random
import shutil
from pathlib import Path

import pytest

replay = pytest.importorskip('harness.zone_referee_replay')
from harness import zone_study_referee as zr
from harness.zone_study_contract import digest
from scripts import zone_study_evidence_join as join
from scripts.zone_study_evidence_contract import verify_referee_derivations
from tests.zone_evidence_fixtures import MAP, at_zone, claims, planned
from tests.zone_evidence_fixtures import put, raw_source, read, refresh_receipts
from tests.zone_evidence_assertions import checked_cohort


@pytest.mark.parametrize('zone', ['A', 'B', 'C'])
@pytest.mark.parametrize('departure', ['held', 'lifted', 'left_zone', 'missing'])
@pytest.mark.parametrize('release', [8.0, 10.0, 10.0002, 11.3])
def test_cancellation_and_redelivery_cap_generalization(zone, departure, release):
    """The independent expectation is the final release + pinned settle time.

    The second item reaches its destination only after the first has departed.
    Thus the two demands are never simultaneously filled before redelivery.
    The old confirmation must not substitute for a late new confirmation.
    """
    plan, bundle = planned(1, 2)
    wrong = next(z for z in ('A', 'B', 'C') if z != zone)
    for order in bundle['host_spec']['order_sheet']['orders']:
        order['destination_zone'] = zone
    admitted = plan['admitted'][0]
    admitted['orders'] = copy.deepcopy(bundle['host_spec']['order_sheet']['orders'])
    admitted['identity'].update(bundle_sha256=digest(bundle),
        order_sheet_sha256=digest(bundle['host_spec']['order_sheet']),
        orders_sha256=digest(admitted['orders']))
    plan = join.freeze_plan([admitted])
    ref = zr.Referee(admitted['orders'], MAP, evidence_key=admitted['key'])
    for t in (.5, 2.5):
        ref.observe(t, {'item-0': at_zone(zone), 'item-1': at_zone(wrong)})
    bad = {'held': at_zone(zone, held=True), 'lifted': at_zone(zone, z=.1),
           'left_zone': at_zone(wrong), 'missing': None}[departure]
    for t in (3., 4.):
        items = {'item-1': at_zone(wrong)}
        if bad is not None:
            items['item-0'] = bad
        ref.observe(t, items)
    for t in (5., 7.):
        items = {'item-1': at_zone(zone)}
        if bad is not None:
            items['item-0'] = bad
        ref.observe(t, items)
    assert not ref.orders_complete()
    for t in (release, release + 2.):
        ref.observe(t, {'item-0': at_zone(zone), 'item-1': at_zone(zone)})
    record, evaluation, raw, identity = claims(ref, plan)
    expected = release + 2. <= bundle['horizon_s']
    try:
        metrics = verify_referee_derivations(record, evaluation, raw, identity,
            pinned_policy=plan['referee_policy'], bundle=bundle)
    except ValueError as exc:
        assert not expected, str(exc)
        assert 'INVALID' in str(exc)
    else:
        assert metrics['success'] is expected


@pytest.mark.parametrize('position', [0, 1, 2])
@pytest.mark.parametrize('operation', ['drop', 'duplicate', 'edit'])
def test_event_chain_corruption_at_every_position_is_rejected(position, operation):
    plan, bundle = planned(1, 1)
    ref = zr.Referee(plan['admitted'][0]['orders'], MAP, evidence_key=plan['admitted'][0]['key'])
    for t in (2., 4.):
        ref.observe(t, {'item-0': at_zone('A')})
    record, evaluation, raw, identity = claims(ref, plan)
    if operation == 'drop':
        raw['events'].pop(position)
    elif operation == 'duplicate':
        raw['events'].append(copy.deepcopy(raw['events'][position]))
    else:
        raw['events'][position]['previous_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='INVALID'):
        verify_referee_derivations(record, evaluation, raw, identity,
            pinned_policy=plan['referee_policy'], bundle=bundle)


def test_all_projection_relations_reorder_independently():
    plan, bundle = planned(1, 2)
    ref = zr.Referee(plan['admitted'][0]['orders'], MAP, evidence_key=plan['admitted'][0]['key'])
    for t in (0., 2.):
        ref.observe(t, {'item-0': at_zone('C'), 'item-1': at_zone('C')})
    ref.observe(3., {})
    for t in (4., 6.):
        ref.observe(t, {'item-0': at_zone('A'), 'item-1': at_zone('A')})
    record, evaluation, raw, identity = claims(ref, plan)
    baseline = verify_referee_derivations(record, evaluation, raw, identity,
        pinned_policy=plan['referee_policy'], bundle=bundle)
    assert baseline['success']
    rng = random.Random(30305)
    for _ in range(128):
        r, e = copy.deepcopy(record), copy.deepcopy(raw)
        for rows in (r['referee']['deliveries'], e['events'], e['history'], e['deliveries']):
            rng.shuffle(rows)
        assert verify_referee_derivations(r, evaluation, e, identity,
            pinned_policy=plan['referee_policy'], bundle=bundle) == baseline


def _conflicting_sources(root, alias):
    plan, bundle = planned(2, 1)
    success = raw_source(root / 'primary', plan, bundle, 0)
    failure = raw_source(root / 'primary', plan, bundle, 1, success=False)
    duplicate = raw_source(root / 'duplicate', plan, bundle, 0, success=False)
    if alias != duplicate.name:
        duplicate = Path(shutil.move(str(duplicate), str(duplicate.with_name(alias))))
    assert read(duplicate, 'manifest.json')['evidence_identity'] == plan['admitted'][0]['identity']
    return plan, [success, failure, duplicate]


def _damage_referee(src, damage):
    raw = read(src, 'eval_only/referee.json')
    if damage == 'policy_hash':
        raw['policy_sha256'] = '0' * 64
    elif damage == 'profile':
        raw['profile']['settle_s'] = .1
        raw['profile']['sha256'] = digest({k: v for k, v in raw['profile'].items() if k != 'sha256'})
    elif damage == 'events':
        raw['events'] = []
    elif damage == 'summary':
        raw['orders_complete'] = True
    else:
        raise AssertionError(damage)
    put(src, 'eval_only/referee.json', raw)
    refresh_receipts(src)


@pytest.mark.parametrize('damage', ['policy_hash', 'profile', 'events', 'summary'])
@pytest.mark.parametrize('reverse', [False, True])
def test_invalidating_duplicate_replay_cannot_increase_cohort_success(tmp_path, damage, reverse):
    plan, sources = _conflicting_sources(tmp_path, 'run-1')
    path = put(tmp_path, 'external-plan.json', plan)
    ordered = list(reversed(sources)) if reverse else sources
    before = checked_cohort(path, digest(plan), ordered, tmp_path / 'before')
    assert before['admitted_trials'] == 2 and before['successes'] == 0
    assert before['trials'][0]['status'] == 'INVALID'  # duplicate run-0
    assert before['trials'][1]['status'] == 'VALID' and not before['trials'][1]['success']
    _damage_referee(sources[-1], damage)
    after = checked_cohort(path, digest(plan), ordered, tmp_path / 'after')
    print({'damage': damage, 'reverse': reverse,
           'before': {k: before[k] for k in ('admitted_trials', 'successes', 'invalid_trials', 'success_rate')},
           'after': {k: after[k] for k in ('admitted_trials', 'successes', 'invalid_trials', 'success_rate')},
           'trials': after['trials']}, flush=True)
    assert any(r['status'] == 'INVALID' for r in after['sources'])
    assert read(tmp_path, 'external-plan.json') == plan
    assert after['admitted_trials'] == before['admitted_trials']
    assert after['successes'] <= before['successes'], after['trials']


@pytest.mark.parametrize('alias', ['run-0', 'unattributable'])
def test_duplicate_replay_rejection_keeps_its_trial_invalid_without_foreign_alias(tmp_path, alias):
    plan, sources = _conflicting_sources(tmp_path, alias)
    _damage_referee(sources[-1], 'policy_hash')
    path = put(tmp_path, 'external-plan.json', plan)
    result = checked_cohort(path, digest(plan), sources, tmp_path / 'events')
    assert (result['admitted_trials'], result['successes']) == (2, 0)
    assert result['trials'][0]['status'] == 'INVALID'
