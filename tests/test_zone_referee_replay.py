"""Pinned event sourcing invariants; synthetic observations, never physics."""
import copy
import random
import subprocess
import sys

import pytest

from harness import zone_referee_replay as replay
from harness import zone_study_referee as zr
from harness.zone_study_contract import digest
from scripts import zone_study_evidence_join as join
from scripts import zone_study_evidence_cohort as cohort
from scripts.zone_study_evidence_contract import verify_referee_derivations
from tests.zone_evidence_fixtures import (
    MAP, at_zone, claims, planned, put, raw_source, read, refresh_receipts,
)


@pytest.mark.parametrize('operation', ['rebuild', 'summary', 'events', 'reorder'])
def test_12000_generated_replay_vs_summary_invariants(operation):
    """3,000 cases per operation, in addition to 12,000 relational cases.

    Vary wrong/correct zones, hold, height, speed, absent samples, dwell duration
    and redeliveries. An independent two-item expectation is checked at every
    observation: success needs both final confirmed destinations at A.
    """
    rng = random.Random(30304 + ['rebuild', 'summary', 'events', 'reorder'].index(operation))
    plan, _ = planned(1, 2)
    pin = plan['referee_policy']
    orders = plan['admitted'][0]['orders']
    for case in range(3000):
        ref = zr.Referee(orders, MAP, evidence_key=plan['admitted'][0]['key'])
        # Initial settle followed by cancellation/recovery, all inside the cap.
        for t in (0., 2.):
            ref.observe(t, {'item-0': at_zone('A'), 'item-1': at_zone('A')})
        mode = rng.randrange(6)
        changed = at_zone(rng.choice(['A', 'C']), **[
            {}, {'held': True}, {'z': .1}, {'speed': .1}, {}, {}][mode])
        items = {'item-0': changed, 'item-1': at_zone('A')}
        if mode == 4:
            items.pop('item-0')
        since = round(rng.uniform(2.1, 3.), 4)
        duration = rng.choice([0., .1, 1., 1.9, 2., 2.1])
        ref.observe(since, items)
        ref.observe(since + duration, items)
        if rng.getrandbits(1):
            ref.observe(7., {'item-0': at_zone('A'), 'item-1': at_zone('A')})
            ref.observe(9., {'item-0': at_zone('A'), 'item-1': at_zone('A')})
        expected_success = (set(ref.standing) == {'item-0', 'item-1'}
                            and all(r['zone'] == 'A' for r in ref.standing.values()))
        record, evaluation, raw, identity = claims(ref, plan)
        baseline = verify_referee_derivations(record, evaluation, raw, identity, pinned_policy=pin)
        assert baseline['success'] is expected_success, (operation, case)
        if operation == 'rebuild':
            rebuilt = replay.replay(raw['events'], orders, pin, evidence_key=join.key_for(identity), source_key=raw['evidence_key'])
            assert rebuilt.record() == ref.record(), case
        elif operation == 'summary':
            field = ['orders_complete', 'samples', 'last_sample_sim_s', 'departures',
                     'completion_sim_s', 'policy_sha256'][case % 6]
            raw[field] = not raw[field] if field == 'orders_complete' else (
                '0' * 64 if field == 'policy_sha256' else (raw[field] or 0) + 1)
            with pytest.raises(ValueError, match='INVALID'):
                verify_referee_derivations(record, evaluation, raw, identity, pinned_policy=pin)
        elif operation == 'events':
            # File hash refresh cannot repair an append-only sequence/chain.
            if case % 3 == 0:
                raw['events'].pop(rng.randrange(len(raw['events'])))
            elif case % 3 == 1:
                raw['events'].append(copy.deepcopy(rng.choice(raw['events'])))
            else:
                raw['events'][1]['items']['item-0']['held'] = True
            with pytest.raises(ValueError, match='INVALID'):
                verify_referee_derivations(record, evaluation, raw, identity, pinned_policy=pin)
        else:
            for rows in (raw['history'], raw['deliveries'], raw['events'], record['referee']['deliveries']):
                rng.shuffle(rows)
            assert verify_referee_derivations(record, evaluation, raw, identity, pinned_policy=pin) == baseline


@pytest.mark.parametrize('damage', ['missing_events', 'policy_hash', 'code_hash', 'missing_profile',
                                   'map', 'horizon', 'unknown_projection', 'sample_summary'])
def test_rehashed_event_or_policy_conflict_is_invalid_under_fixed_plan(tmp_path, damage):
    plan, bundle = planned(2, 1)
    bad = raw_source(tmp_path, plan, bundle, 0)
    good = raw_source(tmp_path, plan, bundle, 1)
    raw = read(bad, 'eval_only/referee.json')
    if damage == 'missing_events':
        raw.pop('events')
    elif damage in ('policy_hash', 'code_hash'):
        raw['policy_sha256'] = digest({'different_code': damage})
    elif damage == 'missing_profile':
        raw.pop('profile')
    elif damage == 'unknown_projection':
        raw['new_success_counter'] = 100
    elif damage == 'sample_summary':
        raw['samples'] += 1
    else:
        # Altered context cannot be admitted by merely recomputing all receipts.
        manifest = read(bad, 'manifest.json')
        manifest['bundle']['scene_static_map_sha256' if damage == 'map' else 'horizon_s'] = 'different'
        put(bad, 'manifest.json', manifest)
    put(bad, 'eval_only/referee.json', raw)
    refresh_receipts(bad)
    result = cohort.collect(plan, digest(plan), [bad, good])
    assert (result['admitted_trials'], result['successes'], result['invalid_trials']) == (2, 1, 1)


def test_changed_loaded_policy_is_refused_not_silently_reinterpreted(monkeypatch):
    pin = replay.policy()
    monkeypatch.setattr(zr, 'SETTLE_S', .1)
    with pytest.raises(ValueError, match='policy'):
        replay.validate_policy(pin)


def test_changed_code_hash_requires_a_new_plan(monkeypatch):
    pin = replay.policy()
    changed = {**replay._code_hashes(), 'harness/zone_study_referee.py': '0' * 64}
    monkeypatch.setattr(replay, '_code_hashes', lambda: changed)
    with pytest.raises(ValueError, match='policy'):
        replay.validate_policy(pin)


def test_lazy_writer_needs_no_tensorboard_until_an_event(tmp_path, monkeypatch):
    from scripts.tensorboard_tools.export import Writer
    monkeypatch.setitem(sys.modules, 'tensorboard', None)
    writer = Writer(tmp_path, 0.)
    writer.close()
    assert not list(tmp_path.glob('events*'))


@pytest.mark.parametrize('break_kind', ['missing', 'moving', 'held', 'lifted'])
def test_full_settle_window_restarts_on_interruptions(break_kind):
    plan, _ = planned(1, 1)
    ref = zr.Referee(plan['admitted'][0]['orders'], MAP, evidence_key=plan['admitted'][0]['key'])
    ref.observe(0., {'item-0': at_zone('A')})
    row = at_zone('A', **{'missing': {}, 'moving': {'speed': .1},
                         'held': {'held': True}, 'lifted': {'z': .1}}[break_kind])
    ref.observe(1.9, {} if break_kind == 'missing' else {'item-0': row})
    for t in (2., 3.9):
        ref.observe(t, {'item-0': at_zone('A')})
    assert not replay.replay(ref.record()['events'], ref.orders, plan['referee_policy'],
                             evidence_key=plan['admitted'][0]['key'], source_key=ref.record()['evidence_key']).orders_complete()
    ref.observe(4., {'item-0': at_zone('A')})
    assert replay.replay(ref.record()['events'], ref.orders, plan['referee_policy'],
                             evidence_key=plan['admitted'][0]['key'], source_key=ref.record()['evidence_key']).orders_complete()


def test_offline_counterexamples_do_not_import_tensorboard(tmp_path):
    # Use the installed environment but make the optional dependency unavailable
    # in a fresh process, without changing its packages or another task's host.
    code = """
import sys, os
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
for name in ('tensorboard', 'mujoco', 'torch', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
import pytest
raise SystemExit(pytest.main(['-q', 'tests/test_review_303d.py', 'tests/test_review_303c.py',
    'tests/test_zone_study_evidence_review_c303.py', 'tests/test_zone_study_evidence_review_a303.py',
    'tests/test_zone_study_evidence_review_f303.py', 'tests/test_review_303e.py',
    'tests/test_zone_referee_ownership.py', '-k', 'not 192']))
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'skipped' not in result.stdout and 'xfailed' not in result.stdout, result.stdout
