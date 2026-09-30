"""Independent PR #303 review at f5566289; synthetic offline evidence only.

Copy this file to that PR's git archive and run with the existing Python 3.12
environment. The review branch intentionally does not carry the PR production
modules. All eleven review counterexamples are required passing regressions. No runtime, network, world or renderer is needed.
"""
import hashlib
import json
import shutil

import pytest

j = pytest.importorskip('scripts.zone_study_evidence_join')
from harness.zone_study_contract import digest
from scripts import zone_study_evidence_cohort as cohort
from scripts.tensorboard_tools import export as tb
from scripts.zone_study_evidence_contract import read_auxiliary
from tests.test_zone_study_evidence import (
    MAP, SCENARIO, at_zone, feed, no_runtime, put, reseal, run, synthetic_source, zr,
)


def read(src, name):
    return json.loads((src / name).read_text())


@pytest.fixture(scope='module')
def pristine(tmp_path_factory):
    root = tmp_path_factory.mktemp('review303c-pristine')
    return synthetic_source(root, 'success', run('no_comm', horizon=12.)[:2])


@pytest.fixture
def source(tmp_path, pristine):
    return shutil.copytree(pristine, tmp_path / 'success')


def refresh_receipts(src):
    """Recompute receipts only, NEVER verdicts, facts, IDs or the frozen plan.

    A checksum is not an independent assertion of cross-record consistency.
    These mutations model a bad join before sealing; no research raw is edited.
    """
    record = read(src, 'study/trial_record.json')
    evaluation = read(src, 'eval_only/evaluation.json')
    inputs = {name: hashlib.sha256((src / name).read_bytes()).hexdigest()
              for name in ('study/trial_record.json', 'eval_only/referee.json')
              if (src / name).exists()}
    evaluation['derived'] = j.derivations(
        {k: v for k, v in evaluation.items() if k != 'derived'}, inputs,
        [record['evidence_key'], *record['order_keys']],
    )
    put(src, 'eval_only/evaluation.json', evaluation)
    result = read(src, 'result.json')
    result['eval_only']['evaluation'] = evaluation
    if result['eval_only'].get('referee') is not None:
        result['eval_only']['referee'] = read(src, 'eval_only/referee.json')
    put(src, 'result.json', result)
    auxiliary = read_auxiliary(
        lambda name: read(src, name),
        lambda name: [json.loads(line) for line in (src / name).read_text().splitlines()],
        {str(p.relative_to(src)) for p in src.rglob('*') if p.is_file()},
    )
    put(src, 'study/record_index.json', j.record_index(record, record['evidence_identity'], auxiliary))
    reseal(src)


def assert_rejected_with_fixed_denominator(src, out):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    plan = read(src, 'study/frozen_plan.json')
    try:
        refresh_receipts(src)
    except ValueError:
        # A future fix may refuse the inconsistent relation at index creation.
        # The original plan must still retain this rejected source as INVALID.
        summary = cohort.collect(plan, digest(plan), [src])
        assert (summary['admitted_trials'], summary['successes'], summary['invalid_trials']) == (1, 0, 1)
        return
    summary = cohort.publish(src / 'study/frozen_plan.json', digest(plan), [src], out,
                             allow_synthetic=True)
    event = EventAccumulator(str(out)).Reload()
    observed = event.Scalars('cohort/success_rate')[0].value
    print({'admitted': summary['admitted_trials'], 'successes': summary['successes'],
           'invalid': summary['invalid_trials'], 'event_success_rate': observed}, flush=True)
    assert summary['admitted_trials'] == 1
    assert summary['successes'] == 0 and summary['invalid_trials'] == 1
    assert observed == 0.0


def failing_referee(src):
    """An internally consistent referee: box_00 is settled in the wrong zone."""
    ref = zr.Referee(SCENARIO['orders'], MAP)
    feed(ref, 2., 4., {'box_00': at_zone('C'), 'box_02': at_zone('B'), 'box_05': at_zone('C')})
    assert not ref.orders_complete()
    old = read(src, 'eval_only/referee.json')
    row = ref.record()
    row.update({key: old[key] for key in ('evidence_identity', 'evidence_key', 'order_keys', 'plan_sha256')})
    put(src, 'eval_only/referee.json', row)


def test_failed_referee_cannot_back_a_success_when_counts_are_missing(source, tmp_path):
    failing_referee(source)
    evaluation = read(source, 'eval_only/evaluation.json')
    evaluation.pop('departures')
    evaluation.pop('departed_unsettled_items')
    put(source, 'eval_only/evaluation.json', evaluation)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


def test_same_failed_referee_is_rejected_when_counts_exist(source, tmp_path):
    failing_referee(source)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('field,value', [('run_id', 'foreign-trial'), ('seed', 987654), ('condition', 'peer_ko')])
def test_foreign_referee_history_row_is_invalid(source, tmp_path, field, value):
    referee = read(source, 'eval_only/referee.json')
    referee['history'][0][field] = value
    put(source, 'eval_only/referee.json', referee)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('damage', ['standing_zone', 'referee_order_id', 'referee_verdict'])
def test_conflicting_referee_state_is_invalid(source, tmp_path, damage):
    referee = read(source, 'eval_only/referee.json')
    if damage == 'standing_zone':
        referee['standing']['box_00']['zone'] = 'C'
    elif damage == 'referee_order_id':
        referee['orders'] = {'foreign-order': next(iter(referee['orders'].values()))}
    else:
        referee['orders_complete'] = False
    put(source, 'eval_only/referee.json', referee)
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


@pytest.mark.parametrize('damage', ['dispatch_order', 'input_frame', 'missing_dispatch'])
def test_raw_action_and_camera_receipts_must_match_the_call(source, tmp_path, damage):
    if damage == 'missing_dispatch':
        (source / 'study/dispatch.jsonl').unlink()
    else:
        filename = 'study/dispatch.jsonl' if damage == 'dispatch_order' else 'study/inputs.jsonl'
        path = source / filename
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if damage == 'dispatch_order':
            old = rows[0]['action']['order_id']
            orders = read(source, 'study/trial_record.json')['orders']
            rows[0]['action']['order_id'] = next(o['order_id'] for o in orders if o['order_id'] != old)
        else:
            rows[0]['frame_sha256'] = '0' * 64
        path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
    assert_rejected_with_fixed_denominator(source, tmp_path / 'events')


def test_reordered_simultaneous_referee_rows_preserve_valid_success(source, tmp_path):
    referee = read(source, 'eval_only/referee.json')
    assert len(referee['history']) == 3
    assert len({row['confirmed_sim_s'] for row in referee['history']}) == 1
    referee['history'].reverse()  # still chronological; all rows occur at the same SIM time
    put(source, 'eval_only/referee.json', referee)
    refresh_receipts(source)
    plan = read(source, 'study/frozen_plan.json')
    summary = cohort.publish(source / 'study/frozen_plan.json', digest(plan), [source],
                             tmp_path / 'events', allow_synthetic=True)
    assert summary['admitted_trials'] == 1
    assert summary['successes'] == 1 and summary['invalid_trials'] == 0, summary['sources']


def test_receipt_recomputation_preserves_normal_source(source, tmp_path):
    before = read(source, 'study/frozen_plan.json')
    refresh_receipts(source)
    assert read(source, 'study/frozen_plan.json') == before
    out = tmp_path / 'normal-events'
    manifest = tb.convert(source, out, allow_synthetic=True, max_images=0)
    assert manifest['metadata']['source_metrics']['evaluation/reported_success'] is True
    summary = cohort.collect(before, digest(before), [source])
    assert (summary['admitted_trials'], summary['successes'], summary['invalid_trials']) == (1, 1, 0)
