"""Frozen-plan properties and publication tests. Synthetic JSON only, no physics."""
import copy
import json
import random

import pytest

from harness.zone_study_contract import digest, scenario_ref
from harness import zone_study_eval as ev
from scripts import zone_study_evidence_join as j
from scripts import zone_study_evidence_cohort as cohort
from scripts.zone_study_evidence_contract import identity_for, per_order_evaluation, seal_new_evidence
from scripts.tensorboard_tools import export as tb
from tests.test_zone_study_eval import trial as metric_trial


def planned(n=3, order_count=2):
    orders = [{'order_id': f'o{i}', 'item_ids': [f'item-{i}'], 'kind': 'cyan',
               'count': 1, 'destination_zone': 'A'} for i in range(order_count)]
    bundle = {'host_spec': {'order_sheet': {'scenario_id': scenario_ref('synthetic'), 'orders': orders}}}
    identities = [identity_for(run_id=f'run-{i}', trial_id=f'trial-{i}', condition='no_comm', seed=i,
                               episode_id=f'episode-{i}', scenario='synthetic', attempt=1, bundle=bundle)
                  for i in range(n)]
    plan = j.freeze_plan([j.admission(identity, orders) for identity in identities])
    return plan, bundle


def tables_for(plan, flags):
    tables = {name: [] for name in j.TABLES}
    for row, success in zip(plan['admitted'], flags, strict=True):
        hashes = {path: digest([row['key'], path]) for path in
                  ('manifest.json', 'study/trial_record.json', 'eval_only/evaluation.json')}
        for name, rows in j.relation_rows(row['identity'], row['orders'], success, hashes, digest(plan)).items():
            tables[name].extend(rows)
    return tables


# Hypothesis is not installed in the existing Python 3.12 environment. Keep a
# replayable seeded generator, with independent cases rather than one invariant
# repeated against an all-success cohort. 12,000 generated cohort mutations.
@pytest.mark.parametrize('operation', ['mix', 'duplicate', 'drop', 'reorder'])
def test_12000_seeded_relational_invariants(operation):
    rng = random.Random(303_20260930 + ['mix', 'duplicate', 'drop', 'reorder'].index(operation))
    for case in range(3000):
        plan, _ = planned(rng.randint(1, 5), rng.randint(1, 3))
        flags = [bool(rng.getrandbits(1)) for _ in plan['admitted']]
        tables = tables_for(plan, flags)
        baseline = j.aggregate(plan, digest(plan), tables)
        assert baseline['successes'] == sum(flags)
        table = rng.choice(j.TABLES)
        row = rng.choice(tables[table])
        affected = row['key']['trial_id']
        if operation == 'mix':
            field = j.KEY_FIELDS[case % len(j.KEY_FIELDS)]
            row['key'][field] = row['key'][field] + 100000 if field in ('seed', 'attempt') else 'foreign'
        elif operation == 'duplicate':
            tables[table].append(copy.deepcopy(row))
        elif operation == 'drop':
            tables[table].remove(row)
        else:
            for rows in tables.values():
                rng.shuffle(rows)
        result = j.aggregate(plan, digest(plan), tables)
        assert result['admitted_trials'] == len(plan['admitted']), (operation, case)
        assert result['success_rate'] <= baseline['success_rate'], (operation, case)
        assert result['successes'] <= sum(flags)
        if operation == 'reorder':
            assert result == baseline
        else:
            verdict = next(t for t in result['trials'] if t['key']['trial_id'] == affected)
            assert verdict['status'] == 'INVALID' and not verdict['success'], (operation, case)


@pytest.mark.parametrize('damage', ['duplicate_admission', 'retry', 'wrong_pin', 'bool_seed', 'missing_key', 'empty'])
def test_plan_is_external_and_cannot_be_reconstructed_from_found_records(damage):
    plan, _ = planned()
    pin = digest(plan)
    if damage == 'duplicate_admission':
        plan['admitted'].append(copy.deepcopy(plan['admitted'][0]))
    elif damage == 'retry':
        row = copy.deepcopy(plan['admitted'][0])
        row['key']['attempt'] = row['identity']['attempt'] = 2
        row['key']['run_id'] = row['identity']['run_id'] = 'retry'
        plan['admitted'].append(row)
    elif damage == 'bool_seed':
        plan['admitted'][0]['key']['seed'] = True
    elif damage == 'missing_key':
        del plan['admitted'][0]['key']['attempt']
    elif damage == 'empty':
        plan['admitted'] = []
    else:
        pin = '0' * 64
    with pytest.raises(ValueError):
        j.validate_plan(plan, pin if damage == 'wrong_pin' else digest(plan))


@pytest.mark.parametrize('damage', ['hash', 'success', 'referee_link', 'board_link', 'order', 'missing_payload', 'bool_key'])
def test_rehashed_conflicting_records_make_whole_trial_invalid(damage):
    plan, _ = planned(2, 3)
    tables = tables_for(plan, [True, True])
    name = {'referee_link': 'referee', 'board_link': 'tensorboard', 'order': 'order'}.get(damage, 'trial')
    row = tables[name][0]
    if damage == 'hash':
        row['sha256'] = '0' * 64
    elif damage == 'bool_key':
        row['key']['seed'] = False
    else:
        if damage == 'success':
            row['payload']['success'] = False
        elif damage == 'referee_link':
            row['payload']['trial_sha256'] = '0' * 64
        elif damage == 'board_link':
            row['payload']['inputs_sha256']['manifest.json'] = '0' * 64
        elif damage == 'order':
            row['payload']['order']['count'] += 1
        else:
            row['payload'] = {}
        row['sha256'] = digest(row['payload'])
    result = j.aggregate(plan, digest(plan), tables)
    assert result['admitted_trials'] == 2
    assert result['trials'][0]['status'] == 'INVALID'
    assert result['success_rate'] <= .5


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    return path


def raw_source(root, plan, bundle, i, success=True):
    """Direct provisional JSON source. No runtime imports or fabricated calls."""
    admitted = plan['admitted'][i]
    identity, orders = admitted['identity'], admitted['orders']
    src = root / identity['run_id']
    # A successful publication now requires the independent raw referee too.
    # Use pure truth samples, never a world or a copied success declaration.
    from harness import zone_study_referee as zr
    from tests.test_zone_study_referee import MAP, at_zone, feed
    referee = zr.Referee(orders, MAP)
    if success:
        feed(referee, 2., 4., {o['item_ids'][0]: at_zone('A') for o in orders})
    deliveries = referee.trial_rows()
    record = metric_trial(condition='no_comm', scenario='synthetic', seed=i, orders=orders,
                          deliveries=deliveries, horizon=12., end_sim_s=5., model={}, requests=[], provenance={},
                          end_reason='orders_complete' if success else 'host_error')
    record.update(trial_id=identity['trial_id'], evidence_identity=identity, record_complete=True,
                  failure_class=None if success else 'infra:HOST_ERROR')
    record['referee']['status'] = 'evaluated'
    record['referee']['departed_unsettled'] = []
    metrics = ev.efficiency_metrics(record)
    assert metrics['success'] is success
    put(src, 'study/trial_record.json', record)
    (src / 'study/dispatch.jsonl').write_text('')
    (src / 'study/inputs.jsonl').write_text('')
    put(src, 'eval_only/referee.json', referee.record())
    put(src, 'eval_only/evaluation.json', {**metrics, 'orders': per_order_evaluation(record),
                                          'evidence_identity': identity})
    terminal = {'end_reason': record['end_reason'], 'end_sim_s': record['end_sim_s'],
                'failure_class': record['failure_class'], 'sim_horizon_s': 12., 'record_complete': True}
    put(src, 'result.json', {'schema': 'ugrp.zone_study_integration_run.v1', 'run_id': identity['run_id'],
                            'evidence_kind': 'synthetic', 'evidence_identity': identity, 'condition': 'no_comm',
                            'episode': identity['episode_id'], 'scenario': 'synthetic', 'seed': i,
                            'bundle_sha256': digest(bundle), 'terminal': True, 'sim_horizon_s': 12.,
                            'eval_only': {'evaluation': json.loads((src / 'eval_only/evaluation.json').read_text())},
                            'study': terminal, 'failure_class': record['failure_class']})
    put(src, 'manifest.json', {'schema': 'ugrp.zone_study_integration_run.v1', 'run_id': identity['run_id'],
                              'bundle': bundle, 'bundle_sha256': digest(bundle), 'evidence_identity': identity,
                              'terminal': terminal})
    seal_new_evidence(src, plan, digest(plan))
    return src


def test_missing_invalid_duplicate_trials_stay_in_frozen_denominator(tmp_path):
    plan, bundle = planned(5)
    paths = [raw_source(tmp_path, plan, bundle, i, i != 1) for i in range(4)]
    # 0 succeeds, 1 fails, 2 is corrupted, 3 duplicated, 4 entirely absent.
    rec = paths[2] / 'study/trial_record.json'
    rec.write_text('{}')
    result = cohort.collect(plan, digest(plan), [*paths, paths[3]])
    assert result['admitted_trials'] == 5 and result['successes'] == 1
    assert result['success_rate'] == .2 and result['invalid_trials'] == 3
    assert [r['status'] for r in result['trials']] == ['VALID', 'VALID', 'INVALID', 'INVALID', 'INVALID']
    assert len(result['sources']) == 5  # duplicate and corrupt source receipts retained


def test_no_sources_is_zero_success_over_all_admitted(tmp_path):
    plan, _ = planned()
    result = cohort.collect(plan, digest(plan), [])
    assert (result['admitted_trials'], result['successes'], result['invalid_trials']) == (3, 0, 3)


@pytest.mark.parametrize('damage', ['number', 'hash', 'record', 'plan'])
def test_published_summary_is_rederived_from_exact_inputs(tmp_path, damage):
    plan, bundle = planned(2)
    paths = [raw_source(tmp_path, plan, bundle, i, i == 0) for i in range(2)]
    summary = cohort.collect(plan, digest(plan), paths)
    if damage == 'number':
        summary['success_rate'] = 1.
    elif damage == 'hash':
        summary['derived']['/success_rate']['inputs_sha256']['frozen_plan'] = '0' * 64
    elif damage == 'record':
        with (paths[0] / 'study/trial_record.json').open('a') as stream:
            stream.write(' ')
    else:
        plan['admitted'].pop()
    with pytest.raises(ValueError):
        cohort.verify_summary(summary, plan, summary['plan_sha256'], paths)


def test_cohort_event_readback_and_keyed_derived_records(tmp_path):
    pytest.importorskip('tensorboard')
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    plan, bundle = planned(3)
    paths = [raw_source(tmp_path, plan, bundle, i, i == 0) for i in range(2)]
    plan_path = put(tmp_path, 'frozen-plan.json', plan)
    out = tmp_path / 'events'
    summary = cohort.publish(plan_path, digest(plan), paths, out, allow_synthetic=True)
    ea = EventAccumulator(str(out)).Reload()
    assert ea.Scalars('cohort/trials')[0].value == 3.
    assert ea.Scalars('cohort/success_rate')[0].value == pytest.approx(1 / 3)
    assert ea.Scalars('trial/2/reported_success')[0].value == 0.
    assert summary['trials'][2]['status'] == 'INVALID'
    assert json.loads((out / 'summary.json').read_text()) == summary
    cohort.verify_summary(summary, plan, digest(plan), paths)
    with pytest.raises(FileExistsError):
        cohort.publish(plan_path, digest(plan), paths, out, allow_synthetic=True)


def test_change_during_publication_never_exposes_events(tmp_path, monkeypatch):
    pytest.importorskip('tensorboard')
    plan, bundle = planned(1)
    paths = [raw_source(tmp_path, plan, bundle, 0)]
    plan_path = put(tmp_path, 'frozen-plan.json', plan)
    original = tb.Writer.close
    def mutate(writer):
        original(writer)
        (paths[0] / 'study/trial_record.json').write_text('{}')
    monkeypatch.setattr(tb.Writer, 'close', mutate)
    out = tmp_path / 'events'
    with pytest.raises(ValueError, match='re-derived'):
        cohort.publish(plan_path, digest(plan), paths, out, allow_synthetic=True)
    assert not out.exists()


@pytest.mark.parametrize('condition', ['no_comm', 'structured', 'peer_ko', 'leader_ko'])
def test_normal_internal_rows_keep_their_explicit_logical_trial_mapping(tmp_path, condition):
    from tests.test_zone_study_evidence import synthetic_source, run
    from scripts.tensorboard_tools.zone_study import inspect_study
    completed = run(condition, horizon=12.)[:2]
    src = synthetic_source(tmp_path, 'success', completed)
    meta, values, _ = inspect_study(src)
    assert values['evaluation/reported_success'] is True
    assert meta['evidence_key']['run_id'] != meta['evidence_key']['trial_id']


@pytest.mark.parametrize('table,field', [('calls', 'run_id'), ('actions', 'seed'), ('messages', 'condition'),
                                       ('request_archive', 'call_id')])
def test_internal_conflict_is_caught_before_index_hash_comparison(tmp_path, table, field):
    from tests.test_zone_study_evidence import synthetic_source, run
    from scripts.zone_study_evidence_contract import read_auxiliary
    src = synthetic_source(tmp_path, 'success', run('peer_ko', horizon=12.)[:2])
    record = json.loads((src / 'study/trial_record.json').read_text())
    assert record[table]
    record[table][0][field] = 999 if field == 'seed' else 'foreign'
    auxiliary = read_auxiliary(lambda p: json.loads((src / p).read_text()),
                               lambda p: [json.loads(s) for s in (src / p).read_text().splitlines()],
                               {str(p.relative_to(src)) for p in src.rglob('*') if p.is_file()})
    with pytest.raises(ValueError, match='INVALID'):
        j.record_index(record, record['evidence_identity'], auxiliary)


@pytest.mark.parametrize('table', ['calls', 'request_archive', 'actions', 'messages'])
@pytest.mark.parametrize('operation', ['duplicate', 'drop', 'reorder'])
def test_internal_primary_and_foreign_keys_without_file_hash_shortcuts(tmp_path, table, operation):
    from tests.test_zone_study_evidence import synthetic_source, run
    from scripts.zone_study_evidence_contract import read_auxiliary
    src = synthetic_source(tmp_path, 'success', run('peer_ko', horizon=12.)[:2])
    record = json.loads((src / 'study/trial_record.json').read_text())
    auxiliary = read_auxiliary(lambda p: json.loads((src / p).read_text()),
                               lambda p: [json.loads(s) for s in (src / p).read_text().splitlines()],
                               {str(p.relative_to(src)) for p in src.rglob('*') if p.is_file()})
    baseline = j.record_index(record, record['evidence_identity'], auxiliary)
    if operation == 'duplicate':
        record[table].append(copy.deepcopy(record[table][0]))
    elif operation == 'drop':
        record[table].pop(0)
    else:
        record[table].reverse()
        assert j.record_index(record, record['evidence_identity'], auxiliary) == baseline
        return
    with pytest.raises(ValueError, match='INVALID'):
        j.record_index(record, record['evidence_identity'], auxiliary)


@pytest.mark.parametrize('damage', ['duplicate_json_key', 'bool_envelope_key', 'duplicate_delivery'])
def test_rehashed_raw_key_conflicts_publish_no_success(tmp_path, damage):
    from tests.test_zone_study_evidence import reseal
    plan, bundle = planned(2, 1)
    src = raw_source(tmp_path, plan, bundle, 1)
    if damage == 'duplicate_json_key':
        path = src / 'manifest.json'
        path.write_text(path.read_text().replace('"seed": 1', '"seed": 999, "seed": 1', 1))
    elif damage == 'bool_envelope_key':
        manifest = json.loads((src / 'manifest.json').read_text())
        manifest['evidence_key']['seed'] = True
        put(src, 'manifest.json', manifest)
    else:
        record = json.loads((src / 'study/trial_record.json').read_text())
        record['referee']['deliveries'] *= 2
        put(src, 'study/trial_record.json', record)
        reseal(src)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, allow_synthetic=True, max_images=0)
    assert not list(out.glob('events*'))
    result = cohort.collect(plan, digest(plan), [src])
    assert result['admitted_trials'] == 2 and result['successes'] == 0
    assert all(row['status'] == 'INVALID' for row in result['trials'])


def test_unreadable_input_is_recorded_invalid_without_dropping_admission(tmp_path, monkeypatch):
    plan, bundle = planned(1)
    src = raw_source(tmp_path, plan, bundle, 0)
    file_digest = cohort.file_digest
    def deny(path):
        if path.name == 'trial_record.json':
            raise PermissionError('test unreadable raw')
        return file_digest(path)
    monkeypatch.setattr(cohort, 'file_digest', deny)
    summary = cohort.collect(plan, digest(plan), [src])
    assert summary['admitted_trials'] == 1 and summary['invalid_trials'] == 1 and summary['successes'] == 0
    assert summary['sources'][0]['unavailable_inputs'] == {'study/trial_record.json': 'PermissionError'}


@pytest.mark.parametrize('damage', ['schemas', 'missing_manifest', 'embedded_evaluation', 'ledger_digest'])
def test_no_schema_downgrade_or_conflicting_embedded_record(tmp_path, damage):
    from tests.test_zone_study_evidence import synthetic_source, run, reseal
    src = synthetic_source(tmp_path, 'success', run('no_comm', horizon=12.)[:2])
    if damage == 'schemas':
        for name in ('result.json', 'manifest.json'):
            row = json.loads((src / name).read_text())
            row['schema'] = 'generic'
            row['success'] = True
            put(src, name, row)
    elif damage == 'missing_manifest':
        (src / 'manifest.json').unlink()
        (src / 'result.json').unlink()
        put(src, 'report.json', {'progress': [{'step': 1, 'loss': .1}]})
    elif damage == 'embedded_evaluation':
        row = json.loads((src / 'result.json').read_text())
        row['eval_only']['evaluation']['evidence_identity']['trial_id'] = 'foreign'
        put(src, 'result.json', row)
        reseal(src)
    else:
        row = json.loads((src / 'study/trial_record.json').read_text())
        row['send_ledger']['sha256'] = '0' * 64
        put(src, 'study/trial_record.json', row)
        reseal(src)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(src, out, allow_synthetic=True, max_images=0)
    assert not list(out.glob('events*'))


def test_cohort_cli_keeps_all_missing_trials_in_denominator(tmp_path):
    import subprocess
    import sys
    pytest.importorskip('tensorboard')
    plan, _ = planned(2)
    path = put(tmp_path, 'plan.json', plan)
    out = tmp_path / 'cli-events'
    result = subprocess.run([sys.executable, '-m', 'scripts.zone_study_evidence_cohort',
                             '--plan', str(path), '--plan-sha256', digest(plan), '--output', str(out)],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == {'admitted_trials': 2, 'successes': 0, 'success_rate': 0., 'invalid_trials': 2}
    assert len(list(out.glob('events*'))) == 1


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity'])
def test_nonfinite_json_is_invalid_evidence(value):
    with pytest.raises(ValueError, match='nonfinite'):
        j.strict_json('{"seed":' + value + '}')


@pytest.mark.parametrize('table', ['dispatch', 'inputs', 'send_ledger', 'referee'])
def test_declared_foreign_keys_in_auxiliary_rows_are_not_overwritten(tmp_path, table):
    from tests.test_zone_study_evidence import synthetic_source, run
    from scripts.zone_study_evidence_contract import read_auxiliary
    src = synthetic_source(tmp_path, 'success', run('no_comm', horizon=12.)[:2])
    record = json.loads((src / 'study/trial_record.json').read_text())
    auxiliary = read_auxiliary(lambda p: json.loads((src / p).read_text()),
                               lambda p: [json.loads(s) for s in (src / p).read_text().splitlines()],
                               {str(p.relative_to(src)) for p in src.rglob('*') if p.is_file()})
    if table == 'referee':
        row = record['referee']['deliveries'][0]
    elif table == 'send_ledger':
        row = auxiliary[table]['entries'][0]
    else:
        row = auxiliary[table][0]
    row['run_id'] = 'foreign-trial'
    with pytest.raises(ValueError, match='declared internal run_id'):
        j.record_index(record, record['evidence_identity'], auxiliary)
