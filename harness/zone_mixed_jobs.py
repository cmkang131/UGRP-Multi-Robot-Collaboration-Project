"""Static P02 dev contract. No scene, teacher, provider or runtime truth access.

Bindings are setup/evaluation metadata; robots receive the existing frozen
OrderSheetSource (IDs and initial slots only). This profile is deliberately
limited to one cyan order on r3 and one long_beam order on r1/r2.
"""
from __future__ import annotations

import copy
import math

from harness.zone_study_contract import ContractViolation, digest

PROFILE = 'mixed_cyan_beam_fixed_r12_r3_v1'
MAP_ID = 'zone_wide_door_geometry_v2'
CONSTRAINTS = {'partner_selection': 'fixed_r1_r2', 'solo_robot': 'r3',
               'pair_policy': 'v5h',
               'beam_destination': 'B', 'solo_destination': 'A',
               'new_routes': 'unsupported', 'non_cyan_solo': 'unsupported',
               'heavy_crate': 'unsupported', 'full_s1_s6': False, 'physical_validation': 'not_run'}


def order_bindings(orders, placements):
    """Validate the static order -> physical IDs join, including fungible counts."""
    by_order = {o['order_id']: o for o in orders}
    if len(by_order) != len(orders):
        raise ContractViolation('duplicate order_id')
    out = {oid: [] for oid in by_order}
    seen = set()
    for p in placements:
        item, oid = p.get('item_id'), p.get('order_id')
        if not isinstance(item, str) or not item or item in seen:
            raise ContractViolation('missing/duplicate physical item_id')
        seen.add(item)
        order = by_order.get(oid)
        if order is None or p.get('kind') != order['kind']:
            raise ContractViolation('placement order/kind mismatch')
        if p.get('slot') != order['initial_location']['slot']:
            raise ContractViolation('placement initial slot mismatch')
        pose = p.get('pose_m')
        if (not isinstance(pose, list) or len(pose) != 3 or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in pose)):
            raise ContractViolation('placement needs finite setup x/y/yaw')
        out[oid].append(item)
    for oid, ids in out.items():
        order = by_order[oid]
        if len(ids) != order['count'] or (order.get('item_ids') and set(ids) != set(order['item_ids'])):
            raise ContractViolation('missing/excess/mismatched physical item IDs for order ' + oid)
    return {oid: {'item_ids': sorted(ids), 'kind': by_order[oid]['kind'],
                  'destination_zone': by_order[oid]['destination_zone']} for oid, ids in out.items()}


def mixed_contract(scenario, episode, sheet):
    if episode.get('mixed_jobs_profile') != PROFILE:
        raise ContractViolation('mixed jobs require explicit opt-in profile')
    if scenario['map_id'] != MAP_ID or episode['map'] != MAP_ID:
        raise ContractViolation('UNSUPPORTED_MIXED_ROUTE: only existing M2 door geometry v2')
    if episode.get('pair_policy', 'v5h') != 'v5h':
        raise ContractViolation('UNSUPPORTED_MIXED_PAIR_POLICY: only fake-tested v5h seam')
    orders = sheet['orders']
    if len(orders) != 2 or sorted(o['kind'] for o in orders) != ['cyan', 'long_beam']:
        raise ContractViolation('UNSUPPORTED_MIXED_KINDS: one cyan and one long_beam only')
    if any(o['count'] != 1 for o in orders):
        raise ContractViolation('UNSUPPORTED_MIXED_COUNT')
    solo = next(o for o in orders if o['kind'] == 'cyan')
    pair = next(o for o in orders if o['kind'] == 'long_beam')
    if solo['required_robots'] != 1 or pair['required_robots'] != 2:
        raise ContractViolation('UNSUPPORTED_MIXED_TEAM_SIZE')
    if solo['destination_zone'] != 'A' or pair['destination_zone'] != 'B':
        raise ContractViolation('UNSUPPORTED_MIXED_ROUTE: cyan A and beam B only')
    bindings = order_bindings(orders, scenario['eval']['setup']['placements'])
    # Specific IDs are static task identity, not positions. Pin both items so
    # referee attribution cannot silently substitute another same-colour box.
    if any(o['identity'] != 'specific_item' or len(o['item_ids']) != 1 for o in orders):
        raise ContractViolation('mixed dev requires explicit specific_item identities')
    if set(episode.get('pair_order_sheets', {})) != {pair['order_id']}:
        raise ContractViolation('mixed pair sheet key must be the order_id')
    from harness.pair_owncam_approach import coarse_order_sheet
    pair_pose = next(p['pose_m'] for p in scenario['eval']['setup']['placements'] if p['kind'] == 'long_beam')
    if episode['pair_order_sheets'][pair['order_id']] != coarse_order_sheet(pair_pose):
        raise ContractViolation('mixed pair sheet differs from bound item setup pose')
    if episode['pair_order_sheets'][pair['order_id']] != coarse_order_sheet([1.2, .05, 0.]):
        raise ContractViolation('UNSUPPORTED_MIXED_ROUTE: fixed dev coarse pickup only')
    expected_goal = {solo['destination_zone']: {'cyan': 1}}
    if episode['goal'] != expected_goal or episode['extra_boxes']:
        raise ContractViolation('mixed scene needs exactly one cyan, no spare placeholders')
    record = {'profile': PROFILE, 'map_id': MAP_ID, 'bindings': bindings,
              'pair_sheet_sha256': digest(episode['pair_order_sheets']),
              'jobs': {solo['order_id']: {'api': 'deliver', 'actors': {'r3': 'west'}},
                       pair['order_id']: {'api': 'pair_carry', 'actors': {'r1': 'end_neg', 'r2': 'end_pos'}}},
              'constraints': copy.deepcopy(CONSTRAINTS),
              'setup_placements': copy.deepcopy(scenario['eval']['setup']['placements'])}
    validate_inventory(record, episode.get('team_cargo', []), cargo_only=True)
    return {**record, 'sha256': digest(record)}


def validate_contract(record):
    if not isinstance(record, dict) or record.get('profile') != PROFILE:
        raise ContractViolation('unknown mixed jobs profile')
    if digest({k: v for k, v in record.items() if k != 'sha256'}) != record.get('sha256'):
        raise ContractViolation('mixed jobs contract digest mismatch')
    if record['map_id'] != MAP_ID:
        raise ContractViolation('UNSUPPORTED_MIXED_ROUTE')
    if record['constraints'] != CONSTRAINTS or len(record['bindings']) != 2:
        raise ContractViolation('unsupported mixed constraints')
    if sorted(b['kind'] for b in record['bindings'].values()) != ['cyan', 'long_beam']:
        raise ContractViolation('UNSUPPORTED_MIXED_KINDS')
    if set(record['jobs']) != set(record['bindings']):
        raise ContractViolation('mixed job/binding mismatch')
    seen = set()
    for oid, binding in record['bindings'].items():
        expected_zone = 'A' if binding['kind'] == 'cyan' else 'B'
        if binding['destination_zone'] != expected_zone:
            raise ContractViolation('UNSUPPORTED_MIXED_ROUTE')
        if len(binding['item_ids']) != 1 or seen.intersection(binding['item_ids']):
            raise ContractViolation('duplicate/missing mixed item IDs')
        seen.update(binding['item_ids'])
        expected = ({'api': 'deliver', 'actors': {'r3': 'west'}} if binding['kind'] == 'cyan' else
                    {'api': 'pair_carry', 'actors': {'r1': 'end_neg', 'r2': 'end_pos'}})
        if record['jobs'][oid] != expected:
            raise ContractViolation('UNSUPPORTED_MIXED_ROLE')
        placements = [p for p in record['setup_placements'] if p['order_id'] == oid]
        if (len(placements) != 1 or placements[0]['item_id'] != binding['item_ids'][0]
                or placements[0]['kind'] != binding['kind']):
            raise ContractViolation('mixed binding/placement mismatch')
    if len(record['setup_placements']) != 2:
        raise ContractViolation('mixed placement count mismatch')


def validate_host_spec(spec):
    record = spec['mixed_jobs']
    validate_contract(record)
    rebuilt = mixed_contract({'map_id': spec['map'], 'eval': {'setup': {'placements': record['setup_placements']}}},
                             {**spec, 'mixed_jobs_profile': record['profile']}, spec['order_sheet'])
    if rebuilt != record or spec['map'] != spec['order_sheet']['map_id']:
        raise ContractViolation('mixed host spec differs from static contract')


def validate_inventory(record, inventory, *, cargo_only=False):
    """Inventory rows are SETUP data, never a runtime observer or World query."""
    expected = {p['item_id']: p for p in record['setup_placements']
                if not cargo_only or p['kind'] == 'long_beam'}
    seen = set()
    for row in inventory:
        if set(row) - {'item_id', 'kind', 'pose', 'pose_m'}:
            raise ContractViolation('unsupported mixed inventory override')
        item = row.get('item_id')
        if item in seen:
            raise ContractViolation('duplicate inventory item_id')
        seen.add(item)
        p = expected.get(item)
        if p is None or row.get('kind') != p['kind']:
            raise ContractViolation('inventory item/kind mismatch')
        pose = row.get('pose_m', row.get('pose'))
        if 'pose_m' in row and 'pose' in row:
            raise ContractViolation('ambiguous inventory setup pose')
        if pose != p['pose_m']:
            raise ContractViolation('inventory setup pose mismatch')
    if seen != set(expected):
        raise ContractViolation('missing inventory item')


def dispatch_refusal(record, actor, api, args):
    """Per-caller admission only; never submit/abort a peer or issue a yield."""
    validate_contract(record)
    if api not in ('deliver', 'pair_carry'):
        if api in ('hold', 'wait', 'abort'):
            return None
        return 'UNSUPPORTED_MIXED_API'
    if len(args) != (3 if api == 'pair_carry' else 2):
        return 'BAD_MIXED_ARGUMENTS'
    if not all(isinstance(arg, str) and arg for arg in args):
        return 'BAD_MIXED_ARGUMENTS'
    order = args[0]
    job = record['jobs'].get(order)
    if job is None:
        return 'UNKNOWN_ORDER'
    if job['api'] != api or actor not in job['actors']:
        return 'UNSUPPORTED_MIXED_ROLE'
    if args[1] != record['bindings'][order]['destination_zone']:
        return 'WRONG_MIXED_DESTINATION'
    if api == 'pair_carry' and args[2] != {'r1': 'r2', 'r2': 'r1'}[actor]:
        return 'UNSUPPORTED_PAIR'
    return None


def evidence_join(record, dispatch, terminal_events, deliveries):
    """Offline evidence join. API completion and evaluated arrival stay separate."""
    validate_contract(record)
    rows, jobs = [], {}
    for d in dispatch:
        ack = d.get('ack')
        if not ack or not ack['accepted'] or d['api'] not in ('deliver', 'pair_carry'):
            continue
        oid = d['args'][0]
        if dispatch_refusal(record, d['actor'], d['api'], d['args']):
            raise ContractViolation('dispatch outside mixed contract')
        if (ack.get('robot_id') != d['actor'] or not ack.get('job_id') or
                ack.get('arguments', {}).get('order_id') != oid or
                ack.get('arguments', {}).get('target_ref') != d['args'][1]):
            raise ContractViolation('dispatch ack identity mismatch')
        row = {'actor': d['actor'], 'call_id': d['call_id'], 'job_id': ack['job_id'], 'order_id': oid,
               'item_ids': record['bindings'][oid]['item_ids'], 'terminal_event': None, 'deliveries': []}
        if row['job_id'] in jobs:
            raise ContractViolation('duplicate dispatch job_id')
        jobs[row['job_id']] = row
        rows.append(row)
    for ev in terminal_events:
        if ev['event'] not in ('job_done', 'job_failed'):
            continue
        row = jobs.get(ev['job_id'])
        if row is None or ev['robot_id'] != row['actor'] or row['terminal_event'] is not None:
            raise ContractViolation('unmatched/duplicate terminal event')
        row['terminal_event'] = ev['event']
    seen = set()
    items = {i: (oid, b) for oid, b in record['bindings'].items() for i in b['item_ids']}
    for d in deliveries:
        if d['item_id'] in seen or d['item_id'] not in items:
            raise ContractViolation('unmatched/duplicate evaluation item')
        seen.add(d['item_id'])
        oid, binding = items[d['item_id']]
        if d['kind'] != binding['kind'] or d['zone'] != binding['destination_zone']:
            raise ContractViolation('evaluation kind/destination mismatch')
        if not any(row['order_id'] == oid for row in rows):
            raise ContractViolation('evaluation item has no accepted dispatch')
        for row in rows:
            if row['order_id'] == oid:
                row['deliveries'].append(copy.deepcopy(d))
    return rows
