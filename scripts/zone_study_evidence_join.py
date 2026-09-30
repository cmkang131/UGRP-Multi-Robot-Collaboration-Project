"""Evaluation-only relational integrity and frozen-plan aggregation for P06.

Legacy runtime logs are immutable inputs, not a second authority for identity.
Normalized rows carry a six-column foreign key plus a table-local row ID.
Publication must build these rows from verified raw files, then re-derive them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter, defaultdict

from harness.zone_study_contract import MAIN_CONDITIONS, digest

KEY_FIELDS = ('run_id', 'trial_id', 'condition', 'seed', 'order_id', 'attempt')
TRIAL_SCOPE = '__trial__'
PLAN_SCHEMA = 'ugrp.zone_study_frozen_evidence_plan.v1'
INDEX_SCHEMA = 'ugrp.zone_study_record_index.v1'
TABLES = ('trial', 'referee', 'order', 'manifest', 'tensorboard')


def strict_json(data):
    def object_pairs(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f'INVALID: duplicate JSON key {key}')
            out[key] = value
        return out
    def nonfinite(value):
        raise ValueError(f'INVALID: nonfinite JSON number {value}')
    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=nonfinite)


def key_for(identity, order_id=TRIAL_SCOPE):
    key = {name: identity[name] for name in KEY_FIELDS if name != 'order_id'}
    key['order_id'] = order_id
    key_tuple(key)
    return key


def key_tuple(key):
    if not isinstance(key, dict) or set(key) != set(KEY_FIELDS):
        raise ValueError('INVALID: missing/extra composite key columns')
    if (any(type(key[k]) is not str or not key[k] for k in ('run_id', 'trial_id', 'order_id'))
            or key['condition'] not in MAIN_CONDITIONS or type(key['condition']) is not str
            or type(key['seed']) is not int or type(key['attempt']) is not int or key['attempt'] < 1):
        raise ValueError('INVALID: composite key type/value conflict')
    return tuple(key[k] for k in KEY_FIELDS)


def unique(rows, field, label):
    """No dict comprehension may silently overwrite a duplicate record."""
    if not isinstance(rows, list):
        raise ValueError(f'INVALID: {label} is not a relation')
    out = {}
    for row in rows:
        value = row.get(field) if isinstance(row, dict) else None
        if type(value) not in (str, int) or value == '' or value in out:
            raise ValueError(f'INVALID: {label} duplicate/missing {field}')
        out[value] = row
    return out


def admission(identity, orders):
    return {'key': key_for(identity), 'identity': copy.deepcopy(identity), 'orders': copy.deepcopy(orders)}


def freeze_plan(admitted):
    """Call before execution, from the planned cohort, never from found results."""
    plan = {'schema': PLAN_SCHEMA, 'admitted': copy.deepcopy(admitted)}
    validate_plan(plan, digest(plan))
    return plan


def validate_plan(plan, expected_sha256):
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or digest(plan) != expected_sha256 or not isinstance(plan, dict)
            or set(plan) != {'schema', 'admitted'} or plan['schema'] != PLAN_SCHEMA
            or not isinstance(plan['admitted'], list) or not plan['admitted']):
        raise ValueError('Frozen plan is missing, empty or differs from its external SHA-256 pin')
    keys, logical, runs = set(), set(), set()
    for row in plan['admitted']:
        if not isinstance(row, dict) or set(row) != {'key', 'identity', 'orders'}:
            raise ValueError('Invalid frozen admission')
        key = key_tuple(row['key'])
        ident = row['identity']
        if row['key'] != key_for(ident) or key in keys or row['key']['order_id'] != TRIAL_SCOPE:
            raise ValueError('Duplicate/conflicting frozen admission')
        # One preselected attempt per logical trial. No best-of-retries selection.
        if ident['trial_id'] in logical or ident['run_id'] in runs:
            raise ValueError('Frozen plan repeats a logical trial/run; retries cannot enlarge the denominator')
        orders = unique(row['orders'], 'order_id', 'planned orders')
        if not orders or TRIAL_SCOPE in orders or digest(row['orders']) != ident['orders_sha256']:
            raise ValueError('Frozen plan has missing/conflicting orders')
        keys.add(key)
        logical.add(ident['trial_id'])
        runs.add(ident['run_id'])
    return plan['admitted']


def admitted_trial(plan, expected_sha256, identity, orders):
    admitted = validate_plan(plan, expected_sha256)
    matches = [row for row in admitted if row['key'] == key_for(identity)]
    if len(matches) != 1 or digest(matches[0]) != digest(admission(identity, orders)):
        raise ValueError('INVALID: trial is orphaned/conflicts with frozen admission')
    return matches[0]


def envelope_keys(identity, orders):
    return {'evidence_key': key_for(identity),
            'order_keys': [key_for(identity, o['order_id']) for o in orders]}


def validate_envelope(envelope, identity, orders):
    expected = envelope_keys(identity, orders)
    if key_tuple(envelope.get('evidence_key')) != key_tuple(expected['evidence_key']):
        raise ValueError('INVALID: envelope composite key conflict')
    values = envelope.get('order_keys')
    if not isinstance(values, list):
        raise ValueError('INVALID: missing order foreign keys')
    keys = [key_tuple(k) for k in values]
    if len(keys) != len(set(keys)) or set(keys) != {key_tuple(k) for k in expected['order_keys']}:
        raise ValueError('INVALID: duplicate/missing/orphan order foreign key')


def row_key(row, identity, order_id=TRIAL_SCOPE):
    """Resolve a legacy row only after checking every declared key column.

    Legacy run_id denotes the logical trial. An explicit evidence_key uses the
    physical run_id, as in the frozen plan. Never overwrite either declaration.
    """
    if not isinstance(row, dict):
        raise ValueError('INVALID: internal row is not an object')
    expected = key_for(identity, order_id)
    for field in KEY_FIELDS:
        value = identity['trial_id'] if field == 'run_id' else expected[field]
        if field == 'order_id' and order_id == TRIAL_SCOPE:
            value = None
        if field in row and digest(row[field]) != digest(value):
            raise ValueError(f'INVALID: declared internal {field} conflicts with admission')
    if 'evidence_key' in row and key_tuple(row['evidence_key']) != key_tuple(expected):
        raise ValueError('INVALID: declared internal composite key conflicts with admission')
    return key_tuple(expected)


def canonical_referee_rows(rows, identity, orders):
    """A relation has no list-position identity; retain duplicates for rejection."""
    if not isinstance(rows, list):
        raise ValueError('INVALID: referee rows are not a relation')
    def sort_key(row):
        if not isinstance(row, dict):
            raise ValueError('INVALID: referee row is not an object')
        named = [o['order_id'] for o in orders if row.get('item_id') in o.get('item_ids', [])]
        oid = named[0] if len(named) == 1 else row.get('order_id') or TRIAL_SCOPE
        if oid != TRIAL_SCOPE and oid not in {o['order_id'] for o in orders}:
            raise ValueError('INVALID: referee order key is orphaned')
        key = row_key(row, identity, oid)
        time = row.get('confirmed_sim_s', row.get('sim_s')) if row.get('event') != 'departed' else row.get('sim_s')
        if type(time) not in (int, float) or not math.isfinite(time):
            raise ValueError('INVALID: referee time is missing/nonfinite')
        return (*key, time, row.get('item_id', ''), digest(row))
    return sorted(rows, key=sort_key)


def validate_internal(record, identity, auxiliary=None):
    """Validate old log IDs BEFORE assigning new keys; never relabel foreign rows.

    run_id in calls/actions/messages is explicitly the logical trial_id, while
    key.run_id is the physical attempt directory. Request/call IDs bridge the
    request, action, dispatch and transport tables, without position-based joins.
    """
    auxiliary = auxiliary or {}
    calls = unique(record.get('calls', []), 'request_id', 'calls')
    requests = unique(record.get('request_archive', []), 'request_id', 'requests')
    actions = unique(record.get('actions', []), 'action_id', 'actions')
    messages = unique(record.get('messages', []), 'message_id', 'messages')
    orders = unique(record['orders'], 'order_id', 'orders')
    complete = record.get('record_complete', True)
    declared_rows = [*calls.values(), *requests.values(), *actions.values(), *messages.values(),
                     *record.get('referee', {}).get('deliveries', [])]
    for name in ('inputs', 'model_calls'):
        declared_rows.extend(auxiliary.get(name, []))
    declared_rows.extend(auxiliary.get('send_ledger', {}).get('entries', []))
    for row in declared_rows:
        row_key(row, identity, row.get('order_id') or TRIAL_SCOPE)
        if row.get('order_id') is not None and row['order_id'] not in orders:
            raise ValueError('INVALID: declared internal order foreign key is orphaned')
    for table in (calls, actions, messages):
        for row in table.values():
            for name, expected in (('run_id', identity['trial_id']), ('condition', identity['condition']),
                                   ('seed', identity['seed'])):
                if digest(row.get(name)) != digest(expected):
                    raise ValueError(f'INVALID: internal log {name} conflicts with trial identity')
    if set(calls) != set(requests):
        # Partial snapshots can stop between request creation and call completion,
        # but are INVALID evidence, never silently pruned into complete evidence.
        raise ValueError('INVALID: call/request join is not one-to-one')
    request_calls = unique(list(requests.values()), 'call_id', 'request call IDs')
    action_requests = unique(list(actions.values()), 'request_id', 'action requests')
    claimed_actions, claimed_messages, message_owners = [], [], defaultdict(set)
    for rid, call in calls.items():
        request = requests[rid]
        body = strict_json(request['user'])
        for name, expected in (('request_id', rid), ('condition', identity['condition'])):
            if body.get(name) != expected:
                raise ValueError(f'INVALID: archived request {name} conflict')
        if request.get('robot') != call.get('actor') or body.get('robot_id') != call.get('actor'):
            raise ValueError('INVALID: request/call actor conflict')
        if request.get('input_sha256') != call.get('input_sha256'):
            raise ValueError('INVALID: request/call input hash conflict')
        aid = call.get('action_id')
        if aid is not None:
            claimed_actions.append(aid)
            action = actions.get(aid)
            if (action is None or action.get('request_id') != rid or action.get('actor') != call.get('actor')
                    or action.get('submitted_at_sim_s') != call.get('released_at_sim_s')):
                raise ValueError('INVALID: call/action foreign key conflict')
        claimed_messages.extend(call.get('message_ids', []))
        for mid in call.get('message_ids', []):
            if mid not in messages or messages[mid].get('sender') != call.get('actor'):
                raise ValueError('INVALID: call/message foreign key conflict')
            message_owners[mid].add(rid)
    # The pinned scheduler stores one message_id reference per recipient. This
    # is a normalized junction relation, not duplicate message rows: PK=(mid,
    # recipient), with exactly one producing call per message. Never set-dedupe
    # the raw references (that would hide a missing/duplicated recipient edge).
    expected_edges = {}
    for mid, message in messages.items():
        recipients = message['recipients']
        delivered = unique(message['deliveries'], 'recipient', 'message recipient edges')
        if (len(set(recipients)) != len(recipients) or set(delivered) != set(recipients)
                or len(message_owners[mid]) != 1):
            raise ValueError('INVALID: message recipient/owner foreign key conflict')
        expected_edges[mid] = len(recipients)
    if (Counter(claimed_actions) != Counter(actions.keys()) or dict(Counter(claimed_messages)) != expected_edges
            or set(action_requests) - set(calls)):
        raise ValueError('INVALID: orphan/duplicate action or message reference')
    for row in actions.values():
        if row.get('order_id') is not None and row['order_id'] not in orders:
            raise ValueError('INVALID: action references an orphan order')
    # Empty early-failure records need no fabricated rows. Once a relation has
    # consumers, losing its entire source table is still a missing foreign key.
    complete_relations = complete and (calls or record.get('end_reason') not in
        ('host_error', 'api_failure', 'interrupted', 'aborted', 'not_evaluated'))
    for name, consumers in (('dispatch', actions), ('inputs', requests)):
        if (consumers or complete_relations) and name not in auxiliary:
            raise ValueError(f'INVALID: missing required {name} table')
    if 'dispatch' in auxiliary:
        from harness.zone_study_offline import _action_row
        dispatch = unique(auxiliary['dispatch'], 'call_id', 'dispatch')
        expected = {requests[rid]['call_id'] for rid in action_requests}
        if set(dispatch) != expected:
            raise ValueError('INVALID: dispatch/action join is not one-to-one')
        for cid, row in dispatch.items():
            request = request_calls[cid]
            action = action_requests[request['request_id']]
            kind, arguments, oid, role = _action_row(row['action'])
            dispatch_key = row_key(row['action'], identity, oid or TRIAL_SCOPE)
            if (row_key(row, identity, oid or TRIAL_SCOPE) != dispatch_key
                    or dispatch_key != row_key(action, identity, action.get('order_id') or TRIAL_SCOPE)
                    or digest([kind, arguments, oid, role]) != digest(
                        [action['kind'], action['arguments'], action.get('order_id'), action.get('role')])):
                raise ValueError('INVALID: dispatch/action composite key or content conflict')
            if row.get('actor') != action['actor'] or row.get('sim_s') != action['submitted_at_sim_s']:
                raise ValueError('INVALID: dispatch actor/time conflict')
    if 'inputs' in auxiliary:
        inputs = unique(auxiliary['inputs'], 'request_id', 'inputs')
        if set(inputs) != set(requests):
            raise ValueError('INVALID: input/request join is not one-to-one')
        for rid, row in inputs.items():
            request, call = requests[rid], calls[rid]
            body = strict_json(request['user'])
            if (row_key(row, identity) != row_key(request, identity)
                    or row.get('robot') != request.get('robot')
                    or digest(row.get('sim_s')) != digest(body.get('sim_time_s'))
                    or digest(row.get('sim_s')) != digest(call.get('requested_at_sim_s'))):
                raise ValueError('INVALID: input/request composite key, robot or time conflict')
            frame_index = row.get('frame_index')
            if type(frame_index) is not int or frame_index < 0:
                raise ValueError('INVALID: missing/invalid input frame index')
            frame = {'kind': 'own_wrist_rgb', 'ref': f'own-{row["robot"]}-{frame_index:04d}',
                     'captured_at_sim_s': row.get('frame_t'), 'sha256': row.get('frame_sha256')}
            refs = body.get('own_rgb_refs', [])
            images = request.get('image_refs', [])
            own_images = [image for image in images if image.get('ref') == frame['ref']]
            if (digest(refs) != digest([frame]) or not images
                    or len(own_images) != 1
                    or any(digest(own_images[0].get(k)) != digest(v) for k, v in (
                        ('bytes_sha256', frame['sha256']), ('sha256', frame['sha256']),
                        ('captured_at_sim_s', frame['captured_at_sim_s'])))
                    or row.get('history_entries') != len(body.get('own_command_history', []))
                    or row.get('inbox_ids') != [m['message_id'] for m in body.get('inbox', [])]):
                raise ValueError('INVALID: input/request frame or content conflict')
    ledger = auxiliary.get('send_ledger')
    if ledger is not None:
        entries = unique(ledger.get('entries'), 'seq', 'transport entries')
        counts = defaultdict(lambda: {'sent': 0, 'blocked': 0})
        for row in entries.values():
            cid = row.get('call_id')
            if (cid not in request_calls or row.get('actor') != request_calls[cid].get('robot')
                    or row.get('status') not in ('sent', 'blocked')):
                raise ValueError('INVALID: transport/request foreign key conflict')
            counts[cid][row['status']] += 1
        # Ledger digest uses ASCII escaping (the original transport convention).
        sha = hashlib.sha256(json.dumps(ledger['entries'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (digest(dict(counts)) != digest(ledger.get('by_call')) or sha != ledger.get('sha256')
                or sum(c['sent'] for c in counts.values()) != ledger.get('sent')
                or sum(c['blocked'] for c in counts.values()) != ledger.get('blocked')):
            raise ValueError('INVALID: transport totals/digest conflict')
        if complete:
            summary = record.get('send_ledger')
            if not isinstance(summary, dict) or summary.get('sha256') != ledger['sha256']:
                raise ValueError('INVALID: trial/transport ledger digest conflict')
            for rid, call in calls.items():
                if call['http_attempts'] != counts[requests[rid]['call_id']]['sent']:
                    raise ValueError('INVALID: charged calls differ from actual sends')
        if 'model_calls' in auxiliary:
            model = unique(auxiliary['model_calls'], 'seq', 'model calls')
            if set(model) != set(entries):
                raise ValueError('INVALID: model/transport join is not one-to-one')
            for seq, row in model.items():
                for k in ('call_id', 'actor', 'status', 'body_sha256', 'response_sha256'):
                    if row.get(k) != entries[seq].get(k):
                        raise ValueError(f'INVALID: model/transport {k} conflict')
    elif calls and complete:
        raise ValueError('INVALID: complete calls lack transport ledger')


def record_index(record, identity, auxiliary):
    """Canonical JSON record hashes; list position is never a row identifier."""
    validate_internal(record, identity, auxiliary)
    tables = {}
    specifications = [('order', record['orders'], 'order_id'), ('call', record.get('calls', []), 'request_id'),
                      ('request', record.get('request_archive', []), 'request_id'),
                      ('action', record.get('actions', []), 'action_id'),
                      ('message', record.get('messages', []), 'message_id')]
    for name, field in (('dispatch', 'call_id'), ('inputs', 'request_id'), ('model_calls', 'seq')):
        if name in auxiliary:
            specifications.append((name, auxiliary[name], field))
    if 'send_ledger' in auxiliary:
        specifications.append(('send', auxiliary['send_ledger']['entries'], 'seq'))
    for name, rows, field in specifications:
        unique(rows, field, name)
        keyed = []
        for row in rows:
            oid = row['order_id'] if name == 'order' else row.get('order_id') or TRIAL_SCOPE
            if name == 'dispatch':
                from harness.zone_study_offline import _action_row
                oid = _action_row(row['action'])[2] or TRIAL_SCOPE
            keyed.append({'key': key_for(identity, oid), 'row_id': row[field], 'sha256': digest(row)})
        tables[name] = sorted(keyed, key=lambda row: (key_tuple(row['key']), str(row['row_id']), row['sha256']))
    messages = {row['message_id']: row for row in record.get('messages', [])}
    edges = []
    for call in record.get('calls', []):
        for mid in sorted(set(call['message_ids'])):
            for recipient in sorted(messages[mid]['recipients']):
                edges.append({'key': key_for(identity), 'row_id': [mid, recipient],
                              'request_id': call['request_id'],
                              'inputs_sha256': [digest(call), digest(messages[mid])]})
    tables['message_recipient'] = sorted(edges, key=lambda row: row['row_id'])
    deliveries, seen = [], set()
    for row in record.get('referee', {}).get('deliveries', []):
        pk = (row.get('item_id'), row.get('sim_s'))
        if not isinstance(pk[0], str) or type(pk[1]) not in (float, int) or pk in seen:
            raise ValueError('INVALID: duplicate/missing referee delivery primary key')
        seen.add(pk)
        orders = [o['order_id'] for o in record['orders'] if row['item_id'] in o.get('item_ids', [])]
        oid = orders[0] if len(orders) == 1 else TRIAL_SCOPE
        if row.get('order_id') is not None and oid != TRIAL_SCOPE and row['order_id'] != oid:
            raise ValueError('INVALID: referee item/order key conflict')
        deliveries.append({'key': key_for(identity, oid), 'row_id': list(pk), 'sha256': digest(row)})
    tables['referee_delivery'] = sorted(deliveries, key=lambda row: row['row_id'])
    return {'schema': INDEX_SCHEMA, 'tables': tables}


def numeric_leaves(value, path=''):
    if type(value) in (bool, int, float):
        if not math.isfinite(value):
            raise ValueError('Nonfinite derived number')
        yield path, value
    elif isinstance(value, dict):
        for name, child in value.items():
            yield from numeric_leaves(child, path + '/' + name.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from numeric_leaves(child, path + '/' + str(i))


def derivations(values, inputs, keys=()):
    return {name: {'value': value, 'keys': copy.deepcopy(list(keys)), 'inputs_sha256': dict(sorted(inputs.items()))}
            for name, value in numeric_leaves(values)}


def relation_rows(identity, orders, success, hashes, plan_sha256):
    """Only the raw verifier calls this in the publication path."""
    if type(success) is not bool:
        raise ValueError('Success must be a boolean')
    data = {
        'trial': {'success': success, 'sha256': hashes['study/trial_record.json']},
        'referee': {'success': success, 'sha256': hashes['eval_only/evaluation.json'],
                    'trial_sha256': hashes['study/trial_record.json']},
        'manifest': {'sha256': hashes['manifest.json'], 'plan_sha256': plan_sha256,
                     'trial_sha256': hashes['study/trial_record.json'],
                     'referee_sha256': hashes['eval_only/evaluation.json']},
        'tensorboard': {'success': success, 'inputs_sha256': dict(sorted(hashes.items()))},
    }
    tables = {name: [] for name in TABLES}
    for order in orders:
        for name in TABLES:
            payload = {'order': order} if name == 'order' else data[name]
            tables[name].append({'key': key_for(identity, order['order_id']),
                                 'payload': copy.deepcopy(payload), 'sha256': digest(payload)})
    return tables


def aggregate(plan, expected_sha256, tables, *, invalid=None):
    """Exact one-to-one joins; every admitted trial gets a verdict, even with no raw.

    Unattributable orphans invalidate the entire cohort, rather than disappearing.
    Attributable defects invalidate the whole trial, including its other orders.
    The tables are normalized *verified* records, never a source of new admission.
    """
    admitted = validate_plan(plan, expected_sha256)
    owner, planned, indexes = {}, {}, {}
    for i, row in enumerate(admitted):
        for order in row['orders']:
            key = key_tuple(key_for(row['identity'], order['order_id']))
            owner[key], planned[key] = i, order
    reasons = [set((invalid or {}).get(i, [])) for i in range(len(admitted))]
    orphan = set(tables) != set(TABLES)
    for name in TABLES:
        indexes[name] = defaultdict(list)
        rows = tables.get(name, [])
        if not isinstance(rows, list):
            orphan = True
            continue
        for row in rows:
            try:
                key = key_tuple(row['key'])
                if key not in owner:
                    orphan = True
                    continue
                indexes[name][key].append(row)
                if set(row) != {'key', 'payload', 'sha256'} or digest(row['payload']) != row['sha256']:
                    reasons[owner[key]].add(f'{name}:record_hash')
            except (KeyError, TypeError, ValueError):
                orphan = True
        for key in owner:
            if len(indexes[name][key]) != 1:
                reasons[owner[key]].add(f'{name}:cardinality')
    if orphan:
        for reason in reasons:
            reason.add('unattributable_orphan')
    successes = defaultdict(list)
    for key, i in owner.items():
        if reasons[i]:
            continue
        rows = {name: indexes[name][key][0]['payload'] for name in TABLES}
        trial, referee, manifest, board = (rows[n] for n in ('trial', 'referee', 'manifest', 'tensorboard'))
        try:
            if (digest(rows['order']['order']) != digest(planned[key])
                    or type(trial['success']) is not bool or type(referee['success']) is not bool
                    or type(board['success']) is not bool
                    or trial['success'] != referee['success'] or trial['success'] != board['success']
                    or referee['trial_sha256'] != trial['sha256']
                    or manifest['trial_sha256'] != trial['sha256']
                    or manifest['referee_sha256'] != referee['sha256']
                    or manifest['plan_sha256'] != expected_sha256
                    or board['inputs_sha256']['study/trial_record.json'] != trial['sha256']
                    or board['inputs_sha256']['eval_only/evaluation.json'] != referee['sha256']
                    or board['inputs_sha256']['manifest.json'] != manifest['sha256']):
                reasons[i].add('conflicting_join')
            successes[i].append(trial['success'])
        except (KeyError, TypeError):
            reasons[i].add('missing_join')
    verdicts = []
    for i, row in enumerate(admitted):
        flags = successes[i]
        if flags and len(set(flags)) != 1:
            reasons[i].add('conflicting_trial_orders')
        success = not reasons[i] and bool(flags) and all(flags)
        verdicts.append({'key': row['key'], 'status': 'INVALID' if reasons[i] else 'VALID',
                         'success': success, 'reasons': sorted(reasons[i])})
    n = len(admitted)
    count = sum(v['success'] for v in verdicts)
    result = {'plan_sha256': expected_sha256, 'admitted_trials': n, 'successes': count,
              'success_rate': count / n, 'invalid_trials': sum(v['status'] == 'INVALID' for v in verdicts),
              'trials': verdicts}
    # Include every supplied row, including duplicates and unassignable orphans.
    inputs = {'frozen_plan': expected_sha256, 'invalid_records': digest(invalid or {})}
    for name, rows in sorted(tables.items()):
        inputs[name] = digest(sorted((digest(row) for row in rows))) if isinstance(rows, list) else digest(rows)
    result['derived'] = derivations({k: result[k] for k in ('admitted_trials', 'successes', 'success_rate', 'invalid_trials')},
                                    inputs, [row['key'] for row in admitted])
    return result
