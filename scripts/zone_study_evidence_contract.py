"""Evaluation-only joins for P06 evidence; never a robot input or run admission."""
import json

from harness import zone_study_eval as ev
from harness.zone_study_contract import MAIN_CONDITIONS, digest, scenario_ref

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
    if digest(evaluation.get('orders')) != digest(per_order_evaluation(record)):
        raise ValueError('Zone-study referee per-order/item evaluation mismatch')
    metrics = ev.efficiency_metrics(record)
    if digest(evaluation.get('orders_by_id')) != digest(metrics['orders_by_id']):
        raise ValueError('Zone-study referee order counts mismatch')
    return identity
