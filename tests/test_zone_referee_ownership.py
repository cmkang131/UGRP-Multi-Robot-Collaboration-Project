"""Raw ownership invariants at production, replay and cohort publication edges."""
import copy
import random
import shutil

import pytest

from harness import zone_referee_replay as replay
from harness import zone_study_referee as zr
from harness.zone_study_contract import digest
from scripts import zone_study_evidence_cohort as cohort
from scripts import zone_study_evidence_join as join
from scripts.tensorboard_tools.zone_study import inspect_study
from scripts.zone_study_evidence_contract import seal_new_evidence
from tests.zone_evidence_fixtures import MAP, at_zone, planned, put, raw_source, read, refresh_receipts
from tests.zone_evidence_assertions import checked_cohort


def test_raw_key_is_copied_at_source_before_any_observation():
    plan, _ = planned(2, 1)
    key = copy.deepcopy(plan['admitted'][0]['key'])
    ref = zr.Referee(plan['admitted'][0]['orders'], MAP, evidence_key=key)
    key.update(plan['admitted'][1]['key'])
    ref.observe(0., {'item-0': at_zone('A')})
    assert all(event['evidence_key'] == plan['admitted'][0]['key'] for event in ref.record()['events'])
    with pytest.raises(ValueError, match='rebound'):
        replay.append_event(ref._events, {'event': 'sample', 'sim_s': 2., 'items': {}}, evidence_key=key)
    # Existing judges without admission still work, but emit no unbound raw log.
    assert zr.Referee(plan['admitted'][0]['orders'], MAP).record()['events'] == []


@pytest.mark.parametrize('position', [0, 1, 2])
@pytest.mark.parametrize('field', join.KEY_FIELDS)
def test_every_raw_event_requires_the_complete_source_key(position, field):
    plan, _ = planned(2, 1)
    key = plan['admitted'][0]['key']
    orders = plan['admitted'][0]['orders']
    ref = zr.Referee(orders, MAP, evidence_key=key)
    for t in (0., 2.):
        ref.observe(t, {'item-0': at_zone('A')})
    events = ref.record()['events']
    events[position]['evidence_key'].pop(field)
    # Fresh checksums cannot substitute for ownership.
    for i, row in enumerate(events):
        row['previous_sha256'] = events[i - 1]['sha256'] if i else None
        row['sha256'] = digest({k: v for k, v in row.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='INVALID'):
        replay.replay(events, orders, plan['referee_policy'], evidence_key=key, source_key=key)


@pytest.mark.parametrize('mismatch', ['event', 'source'])
def test_foreign_key_cannot_replay_into_another_trial(mismatch):
    plan, _ = planned(2, 1)
    key, foreign = [r['key'] for r in plan['admitted']]
    orders = plan['admitted'][0]['orders']
    ref = zr.Referee(orders, MAP, evidence_key=foreign if mismatch == 'event' else key)
    for t in (0., 2.):
        ref.observe(t, {'item-0': at_zone('A')})
    with pytest.raises(ValueError, match='INVALID'):
        replay.replay(ref.record()['events'], orders, plan['referee_policy'], evidence_key=key,
                      source_key=foreign if mismatch == 'source' else key)


@pytest.mark.parametrize('declaration', ['events', 'envelope', 'manifest'])
def test_sealing_never_rekeys_foreign_or_rejected_raw(tmp_path, declaration):
    plan, bundle = planned(2, 1)
    a, b = [raw_source(tmp_path, plan, bundle, i) for i in range(2)]
    # Model a new candidate before its first seal, using synthetic records only.
    (a / 'study/record_index.json').unlink()
    (a / 'study/frozen_plan.json').unlink()
    raw = read(a, 'eval_only/referee.json')
    manifest = read(a, 'manifest.json')
    if declaration == 'events':
        raw['events'] = read(b, 'eval_only/referee.json')['events']
    elif declaration == 'envelope':
        raw['evidence_key'] = plan['admitted'][1]['key']
    else:
        manifest['event_sources']['eval_only/referee.json']['evidence_key'] = plan['admitted'][1]['key']
    raw['policy_sha256'] = '0' * 64
    put(a, 'eval_only/referee.json', raw)
    put(a, 'manifest.json', manifest)
    seal_new_evidence(a, plan, digest(plan))
    assert read(a, 'eval_only/referee.json') == raw
    assert read(a, 'manifest.json')['event_sources'] == manifest['event_sources']
    result = cohort.collect(plan, digest(plan), [a, b])
    assert (result['admitted_trials'], result['successes'], result['invalid_trials']) == (2, 0, 2)
    with pytest.raises(FileExistsError):
        seal_new_evidence(a, plan, digest(plan))


@pytest.mark.parametrize('target', ['event', 'file', 'manifest', 'identity'])
@pytest.mark.parametrize('rejected', [False, True])
def test_key_source_disagreement_invalidates_both_trials(tmp_path, target, rejected):
    plan, bundle = planned(3, 1)
    sources = [raw_source(tmp_path, plan, bundle, i) for i in range(3)]
    a, b, _ = sources
    raw = read(a, 'eval_only/referee.json')
    foreign = plan['admitted'][1]['key']
    if target == 'manifest':
        manifest = read(a, 'manifest.json')
        manifest['event_sources']['eval_only/referee.json']['evidence_key'] = foreign
        put(a, 'manifest.json', manifest)
    elif target == 'file':
        raw = read(b, 'eval_only/referee.json')
    elif target == 'identity':
        raw['evidence_identity'] = plan['admitted'][1]['identity']
    else:
        raw['events'][1] = read(b, 'eval_only/referee.json')['events'][1]
    if rejected:
        raw['policy_sha256'] = '0' * 64
    put(a, 'eval_only/referee.json', raw)
    refresh_receipts(a)
    with pytest.raises(ValueError, match='INVALID'):
        inspect_study(a)
    path = put(tmp_path, 'plan.json', plan)
    summary = checked_cohort(path, digest(plan), sources, tmp_path / 'events')
    assert [r['status'] for r in summary['trials']] == ['INVALID', 'INVALID', 'VALID']
    assert (summary['admitted_trials'], summary['successes']) == (3, 1)
    assert summary['sources'][0]['affected_keys'] == [r['key'] for r in plan['admitted'][:2]]


@pytest.mark.parametrize('damage', ['missing', 'null', 'bool_seed', 'order_scope', 'path'])
def test_manifest_source_entry_is_required_even_for_individual_export(tmp_path, damage):
    plan, bundle = planned(1, 1)
    src = raw_source(tmp_path, plan, bundle, 0)
    manifest = read(src, 'manifest.json')
    entries = manifest['event_sources']
    if damage == 'missing':
        manifest.pop('event_sources')
    elif damage == 'null':
        entries['eval_only/referee.json']['evidence_key'] = None
    elif damage == 'bool_seed':
        entries['eval_only/referee.json']['evidence_key']['seed'] = False
    elif damage == 'order_scope':
        entries['eval_only/referee.json']['evidence_key']['order_id'] = 'o0'
    else:
        entries['foreign/referee.json'] = entries.pop('eval_only/referee.json')
    put(src, 'manifest.json', manifest)
    with pytest.raises(ValueError, match='INVALID'):
        inspect_study(src)
    assert cohort.collect(plan, digest(plan), [src])['successes'] == 0


@pytest.mark.parametrize('operation', ['permute', 'duplicate', 'move'])
def test_192_generated_raw_record_transformations_never_increase_success(tmp_path, operation):
    """64 independent raw cohorts per operation, beyond the prior 24,000 cases.

    Keep keys and the external plan fixed. Include rejected duplicates: moving
    their rows OR renaming their directory to another admitted run must not
    remove their original owner's INVALID verdict. Check
    actual raw -> collect, and real event readback for each operation's last case.
    """
    rng = random.Random(303_500 + ['permute', 'duplicate', 'move'].index(operation))
    for case in range(64):
        root = tmp_path / str(case)
        plan, bundle = planned(rng.randint(2, 4), rng.randint(1, 2))
        flags = [bool(rng.getrandbits(1)) for _ in plan['admitted']]
        rename_rejected = operation == 'move' and case % 3 == 0
        owner, alias = rng.sample(range(len(flags)), 2) if rename_rejected else (0, None)
        if rename_rejected:
            # A must be a success and B a non-success: losing A's rejected
            # duplicate must expose the original 0 -> 1 success inflation.
            flags[owner], flags[alias] = True, False
        sources = [raw_source(root / 'primary', plan, bundle, i, flag) for i, flag in enumerate(flags)]
        if case % 2 or rename_rejected:
            duplicate = raw_source(root / 'extra', plan, bundle, owner, False)
            raw = read(duplicate, 'eval_only/referee.json')
            raw['policy_sha256'] = '0' * 64
            put(duplicate, 'eval_only/referee.json', raw)
            refresh_receipts(duplicate)
            sources.append(duplicate)
        baseline = cohort.collect(plan, digest(plan), sources)
        if rename_rejected:
            assert baseline['successes'] == sum(flags) - 1
            assert baseline['invalid_trials'] == 1
            assert baseline['trials'][owner]['status'] == 'INVALID'
            assert baseline['trials'][alias]['status'] == 'VALID'
        donor, recipient = rng.sample(sources, 2)
        if operation == 'permute':
            rng.shuffle(sources)
            for src in sources:
                raw = read(src, 'eval_only/referee.json')
                rng.shuffle(raw['events'])
                put(src, 'eval_only/referee.json', raw)
                refresh_receipts(src)
        elif operation == 'duplicate':
            if case % 3 == 0:
                duplicate = root / 'copied' / rng.choice(plan['admitted'])['key']['run_id']
                shutil.copytree(donor, duplicate)
                sources.append(duplicate)
            else:
                raw = read(recipient, 'eval_only/referee.json')
                raw['events'].extend(copy.deepcopy(read(donor, 'eval_only/referee.json')['events']))
                put(recipient, 'eval_only/referee.json', raw)
                refresh_receipts(recipient)
        elif rename_rejected:
            # Rename the existing rejected source; retaining an unmoved copy
            # would mask the bug. Every file (including keys/receipts) is fixed.
            original = {p.relative_to(duplicate): p.read_bytes()
                        for p in duplicate.rglob('*') if p.is_file()}
            moved = duplicate.with_name(plan['admitted'][alias]['key']['run_id'])
            duplicate.rename(moved)
            sources[-1] = moved
            assert not duplicate.exists()
            assert {p.relative_to(moved): p.read_bytes()
                    for p in moved.rglob('*') if p.is_file()} == original
        elif case % 3 == 1:
            # The source manifest/envelopes remain, even when its raw file moves.
            shutil.move(str(donor / 'eval_only/referee.json'), str(recipient / 'eval_only/referee.json'))
            refresh_receipts(donor)
            refresh_receipts(recipient)
        else:
            raw = read(donor, 'eval_only/referee.json')
            other = read(recipient, 'eval_only/referee.json')
            other['events'].append(raw['events'].pop(rng.randrange(len(raw['events']))))
            for src, value in ((donor, raw), (recipient, other)):
                put(src, 'eval_only/referee.json', value)
                refresh_receipts(src)
        result = cohort.collect(plan, digest(plan), sources)
        assert result['admitted_trials'] == baseline['admitted_trials'] == len(plan['admitted'])
        assert result['successes'] <= baseline['successes'], (
            operation, case, 'successes', baseline['successes'], result['successes'], result['trials'])
        if rename_rejected:
            assert result['invalid_trials'] == 1
            assert result['trials'][owner]['status'] == 'INVALID'
            assert result['trials'][alias]['status'] == 'VALID'
            receipt = next(r for r in result['sources'] if r['source'] == str(moved.resolve()))
            assert receipt['status'] == 'INVALID'
            assert receipt['affected_keys'] == [plan['admitted'][owner]['key']]
        if operation == 'permute':
            assert result['trials'] == baseline['trials']
        assert all(new['status'] == 'INVALID' for old, new in zip(baseline['trials'], result['trials'])
                   if old['status'] == 'INVALID')
        if case == 63:
            path = put(root, 'plan.json', plan)
            assert checked_cohort(path, digest(plan), sources, root / 'events') == result
