"""Evaluation-only joins for P06 evidence; never a robot input or run admission."""
import json
import hashlib
import math
from pathlib import Path

from harness import zone_study_eval as ev
from harness.zone_study_contract import MAIN_CONDITIONS, digest, scenario_ref
from scripts import zone_study_evidence_join as join

IDENTITY_SCHEMA = 'ugrp.zone_study_evidence_identity.v1'
IDENTITY_KEYS = {'schema', 'run_id', 'trial_id', 'episode_id', 'attempt', 'condition',
                 'scenario', 'seed', 'bundle_sha256', 'order_sheet_sha256', 'orders_sha256'}


def identity_for(*, run_id, trial_id, episode_id, attempt, condition, scenario, seed, bundle):
    """Keep a logical trial distinct from its physical attempt/directory name."""
    sheet = bundle['host_spec']['order_sheet']
    identity = {'schema': IDENTITY_SCHEMA, 'run_id': run_id, 'trial_id': trial_id,
                'episode_id': episode_id, 'attempt': attempt, 'condition': condition,
                'scenario': scenario, 'seed': seed, 'bundle_sha256': digest(bundle),
                'order_sheet_sha256': digest(sheet), 'orders_sha256': digest(sheet['orders'])}
    validate_identity(identity, bundle)
    return identity


def validate_identity(identity, bundle):
    if not isinstance(identity, dict) or set(identity) != IDENTITY_KEYS:
        raise ValueError('Zone-study evidence identity is required; legacy import is not implicit')
    if (identity['schema'] != IDENTITY_SCHEMA or identity['condition'] not in MAIN_CONDITIONS
            or type(identity['attempt']) is not int or identity['attempt'] < 1
            or type(identity['seed']) is not int
            or any(not isinstance(identity[k], str) or not identity[k]
                   for k in ('run_id', 'trial_id', 'episode_id', 'scenario'))):
        raise ValueError('Invalid zone-study evidence identity')
    sheet = bundle.get('host_spec', {}).get('order_sheet', {})
    if (identity['bundle_sha256'] != digest(bundle)
            or identity['order_sheet_sha256'] != digest(sheet)
            or identity['orders_sha256'] != digest(sheet.get('orders'))
            or sheet.get('scenario_id') != scenario_ref(identity['scenario'])):
        raise ValueError('Zone-study bundle/order-sheet identity mismatch')


def validate_record_identity(record, identity):
    for key in ('trial_id', 'condition', 'scenario', 'seed'):
        if digest(record.get(key)) != digest(identity[key]):
            raise ValueError(f'Zone-study trial identity mismatch: {key}')
    if digest(record.get('orders')) != identity['orders_sha256']:
        raise ValueError('Zone-study trial orders differ from bundled order sheet')
    provenances = [record.get('provenance', {}),
                   *(c.get('provenance', {}) for c in record.get('calls', []))]
    for provenance in provenances:
        if ('order_sheet_sha256' in provenance
                and provenance['order_sheet_sha256'] != identity['order_sheet_sha256']):
            raise ValueError('Zone-study request provenance differs from bundled order sheet')
    for request in record.get('request_archive', []):
        body = json.loads(request['user'])
        if digest(body.get('order_sheet')) != identity['order_sheet_sha256']:
            raise ValueError('Zone-study archived request differs from bundled order sheet')


def per_order_evaluation(record):
    """Recompute referee order/item joins from the terminal trial's deliveries."""
    state = ev.delivery_state(record)
    orders = {}
    for order in record['orders']:
        oid = order['order_id']
        items = {i: d['sim_s'] for i, d in state['delivered'].items() if d['order_id'] == oid}
        row = state['by_order'][oid]
        orders[oid] = {'destination_zone': order['destination_zone'], **row,
                       'item_delivered_sim_s': items,
                       'completed_sim_s': max(items.values()) if row['complete'] and items else None}
    return orders


def verify_identity_join(raw, result, record, evaluation):
    identity = raw.get('evidence_identity')
    validate_identity(identity, raw['bundle'])
    for envelope in (result, record, evaluation):
        if digest(envelope.get('evidence_identity')) != digest(identity):
            raise ValueError('Zone-study evidence identity differs across files')
    for key, identity_key in (('run_id', 'run_id'), ('episode', 'episode_id'),
                              ('condition', 'condition'), ('scenario', 'scenario'), ('seed', 'seed')):
        if digest(result.get(key)) != digest(identity[identity_key]):
            raise ValueError(f'Zone-study result identity mismatch: {key}')
    if raw.get('run_id') != identity['run_id'] or raw.get('bundle_sha256') != identity['bundle_sha256']:
        raise ValueError('Zone-study manifest run/bundle identity mismatch')
    validate_record_identity(record, identity)
    nested = result.get('eval_only', {}).get('evaluation')
    if nested is not None and digest(nested) != digest(evaluation):
        raise ValueError('INVALID: embedded result/referee evaluation conflicts')
    for envelope in (raw, result, record, evaluation):
        join.validate_envelope(envelope, identity, record['orders'])
    if digest(evaluation.get('orders')) != digest(per_order_evaluation(record)):
        raise ValueError('Zone-study referee per-order/item evaluation mismatch')
    metrics = ev.efficiency_metrics(record)
    if digest(evaluation.get('orders_by_id')) != digest(metrics['orders_by_id']):
        raise ValueError('Zone-study referee order counts mismatch')
    return identity


AUXILIARY = {'dispatch': 'study/dispatch.jsonl', 'inputs': 'study/inputs.jsonl',
             'send_ledger': 'study/send_ledger.json', 'model_calls': 'study/model_calls.jsonl'}


def read_auxiliary(read_json, read_jsonl, files):
    return {name: (read_jsonl(path) if path.endswith('.jsonl') else read_json(path))
            for name, path in AUXILIARY.items() if path in files}


def seal_new_evidence(root, plan, plan_sha256):
    """Finalize newly written candidate evidence; cannot re-seal an existing index.

    The caller supplies the cohort plan frozen before execution. Invalid internal
    records stay on disk with an INVALID index; no source rows are dropped/fixed.
    This is not a migration/repair command for old experiment directories.
    """
    root = Path(root)
    if any((root / p).exists() for p in ('study/record_index.json', 'study/frozen_plan.json')):
        raise FileExistsError('Evidence already sealed; preserve original records')
    paths = ('manifest.json', 'result.json', 'study/trial_record.json', 'eval_only/evaluation.json')
    raw, result, record, evaluation = [json.loads((root / p).read_text()) for p in paths]
    nested = result.get('eval_only', {}).get('evaluation')
    if nested is not None and digest(nested) != digest(evaluation):
        raise ValueError('Cannot seal conflicting embedded evaluation')
    identity = raw['evidence_identity']
    validate_identity(identity, raw['bundle'])
    validate_record_identity(record, identity)
    join.admitted_trial(plan, plan_sha256, identity, record['orders'])
    keys = join.envelope_keys(identity, record['orders'])
    for envelope in (raw, result, record, evaluation):
        if digest(envelope.get('evidence_identity')) != digest(identity):
            raise ValueError('Cannot seal conflicting identities')
        for field, value in keys.items():
            envelope.setdefault(field, value)
        envelope.setdefault('plan_sha256', plan_sha256)

    def write(path, value):
        (root / path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')

    write('study/frozen_plan.json', plan)
    write('study/trial_record.json', record)
    if (root / 'eval_only/referee.json').exists():
        referee = json.loads((root / 'eval_only/referee.json').read_text())
        if referee is not None:
            nested = result.get('eval_only', {}).get('referee')
            if nested is not None and digest(nested) != digest(referee):
                raise ValueError('Cannot seal conflicting embedded referee history')
            # Preserve source declarations even when they conflict. Sealing is
            # not permission to rebind rejected raw events to this admission.
            for field, value in keys.items():
                referee.setdefault(field, value)
            referee.setdefault('evidence_identity', identity)
            referee.setdefault('plan_sha256', plan_sha256)
            raw.setdefault('event_sources', {
                'eval_only/referee.json': {'evidence_key': keys['evidence_key']}})
            write('eval_only/referee.json', referee)
            if nested is not None:
                result['eval_only']['referee'] = referee
    record_sha = hashlib.sha256((root / 'study/trial_record.json').read_bytes()).hexdigest()
    # The evaluation consumes the exact terminal trial (including its referee),
    # plus the referee raw record when additional history counts were used.
    inputs = {'study/trial_record.json': record_sha}
    if (root / 'eval_only/referee.json').exists():
        inputs['eval_only/referee.json'] = hashlib.sha256((root / 'eval_only/referee.json').read_bytes()).hexdigest()
    evaluation['derived'] = join.derivations(evaluation, inputs, [keys['evidence_key'], *keys['order_keys']])
    write('eval_only/evaluation.json', evaluation)
    if 'evaluation' in result.get('eval_only', {}):
        result['eval_only']['evaluation'] = evaluation
    write('result.json', result)
    files = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    auxiliary = read_auxiliary(lambda p: json.loads((root / p).read_text()),
                               lambda p: [json.loads(line) for line in (root / p).read_text().splitlines()], files)
    try:
        index = join.record_index(record, identity, auxiliary)
    except ValueError as exc:
        index = {'schema': join.INDEX_SCHEMA, 'status': 'INVALID', 'reason': str(exc),
                 'trial_sha256': record_sha}
    write('study/record_index.json', index)
    raw['files'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(root.rglob('*')) if p.is_file() and p != root / 'manifest.json'}
    write('manifest.json', raw)
    return result


def verify_referee_derivations(record, evaluation, referee, identity, *, pinned_policy=None, bundle=None, source_key=None):
    """Replay the pinned referee, then compare every declared projection.

    Pure callers may use the current policy; publication always supplies the
    externally frozen plan and its admitted bundle. No summary drives replay.
    """
    from harness import zone_referee_replay as replay
    pin = replay.policy() if pinned_policy is None else pinned_policy
    replay.validate_policy(pin)
    if bundle is not None and digest(bundle.get('referee')) != digest(pin['profile']):
        raise ValueError('INVALID: bundle referee differs from frozen policy')
    if not isinstance(referee, dict):
        metrics = ev.efficiency_metrics(record)
        if (referee is None and not record['referee'].get('deliveries')
                and not metrics['success'] and not evaluation.get('success')
                and (record['referee'].get('status') == 'not_evaluated'
                     or record.get('end_reason') in ('host_error', 'api_failure', 'interrupted', 'aborted'))):
            return metrics
        raise ValueError('INVALID: referee event log is missing')
    join.validate_envelope(referee, identity, record['orders'])
    if (referee.get('evidence_identity') != identity or referee.get('plan_sha256') != record['plan_sha256']):
        raise ValueError('INVALID: referee identity/plan mismatch')
    if referee.get('policy_sha256') != pin['sha256'] or digest(referee.get('profile')) != digest(pin['profile']):
        raise ValueError('INVALID: recorded referee policy differs from frozen code/parameters')
    evidence_key = join.key_for(identity)
    source_key = referee['evidence_key'] if source_key is None else source_key
    full = replay.replay(referee.get('events'), record['orders'], pin,
                         evidence_key=evidence_key, source_key=source_key)
    rebuilt = full.record()
    if bundle is not None:
        context = sorted(referee['events'], key=lambda r: r['seq'])[0]['static_map']
        if digest(context) != bundle.get('scene_static_map_sha256'):
            raise ValueError('INVALID: referee static map differs from admitted bundle')
        if digest(bundle.get('horizon_s')) != digest(record['budget']['sim_horizon_s']):
            raise ValueError('INVALID: referee horizon differs from admitted bundle')
    required = {'history', 'standing', 'deliveries', 'orders', 'orders_complete',
                'completion_sim_s', 'departed_unsettled', 'last_sample_sim_s', 'profile',
                'events', 'policy_sha256'}
    if not required <= referee.keys() or type(referee['orders_complete']) is not bool:
        raise ValueError('INVALID: required referee projections are missing/invalid')
    def canonical(rows):
        return join.canonical_referee_rows(rows, identity, record['orders'])
    relations = {'history', 'deliveries', 'departed_unsettled'}
    envelope = {'evidence_identity', 'plan_sha256', 'evidence_key', 'order_keys'}
    # Unknown projections are refused, not silently trusted or ignored. Optional
    # known statistics may be absent; every supplied statistic must match replay.
    for key, actual in referee.items():
        if key in envelope:
            continue
        expected = rebuilt.get(key)
        if key in relations:
            actual, expected = canonical(actual), canonical(expected)
        elif key == 'events':
            actual = sorted(actual, key=lambda r: r['seq'])
        if key not in rebuilt or digest(actual) != digest(expected):
            raise ValueError(f'INVALID: referee replay/summary conflict: {key}')
    observed = record['referee'].get('observed_end_sim_s', record['end_sim_s'])
    if (type(observed) not in (int, float) or not math.isfinite(observed) or observed < 0
            or (full.last_t is not None and full.last_t > observed + pin['time_tolerance_s'])):
        raise ValueError('INVALID: terminal observation end precedes raw referee samples')
    for field, expected in (('deliveries', full.trial_rows()),
                            ('departed_unsettled', full.departed_unsettled())):
        if digest(canonical(record['referee'].get(field))) != digest(canonical(expected)):
            raise ValueError(f'INVALID: trial/referee replay conflict: {field}')
    for key, expected in {'departures': rebuilt['departures'],
                           'departed_unsettled_items': len(full.departed_unsettled()),
                           't0_sim_s': record.get('t0_sim_s'), 'end_sim_s': record['end_sim_s'],
                           'referee_profile_sha256': pin['profile']['sha256']}.items():
        if key in evaluation and digest(evaluation[key]) != digest(expected):
            raise ValueError(f'INVALID: evaluation/referee replay conflict: {key}')
    t0 = float(record.get('t0_sim_s') or 0.)
    cutoff = min(observed, t0 + float(record['budget']['sim_horizon_s']))
    bounded = replay.replay(referee['events'], record['orders'], pin,
                            evidence_key=evidence_key, source_key=source_key, cutoff=cutoff)
    projected = replay.trial_projection(record, bounded)
    metrics = ev.efficiency_metrics(projected)
    if digest(metrics) != digest(ev.efficiency_metrics(record)):
        raise ValueError('INVALID: trial outcome differs from pinned event replay')
    for key in evaluation.keys() & metrics.keys():
        if digest(evaluation[key]) != digest(metrics[key]):
            raise ValueError(f'INVALID: evaluation differs from pinned event replay: {key}')
    return metrics
