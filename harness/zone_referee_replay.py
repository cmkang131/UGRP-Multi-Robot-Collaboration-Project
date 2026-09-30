"""Pinned, evaluation-only event replay. No runtime, model or publication effects.

Orders/map are the first event; each complete truth sample is appended after
validation. Confirmations and cancellations are projections, never replay input.
Sequence numbers and the hash chain survive physical JSON row reordering.
"""
from __future__ import annotations

import copy
import hashlib
import math
from functools import lru_cache
from pathlib import Path

from harness.zone_study_contract import digest

EVENT_SCHEMA = 'ugrp.zone_referee_events.v1'
POLICY_SCHEMA = 'ugrp.zone_referee_policy.v1'


@lru_cache(maxsize=1)
def _code_hashes():
    # Snapshot the entire local import closure of the loaded referee/replay.
    # Starting a publisher under changed code requires a new frozen plan.
    from harness.python_source_closure import source_closure
    root = Path(__file__).resolve().parents[1]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in source_closure(root, ['harness/zone_referee_replay.py',
                                          'harness/zone_study_referee.py'])}


def policy():
    from harness import zone_study_referee as zr
    row = {'schema': POLICY_SCHEMA, 'profile': zr.profile(),
           'code_sha256': dict(_code_hashes()), 'event_schema': EVENT_SCHEMA,
           'time_tolerance_s': 0.0001,
           'cutoff': 'replay all samples through min(observed_end, t0 + horizon)',
           'success_clock': 'settle start of the final delivered order',
           'missing_raw': 'INVALID except an explicit pre-referee terminal failure'}
    return {**row, 'sha256': digest(row)}


def validate_policy(pin):
    if not isinstance(pin, dict) or digest(pin) != digest(policy()):
        raise ValueError('INVALID: frozen referee policy code/parameters differ from the loaded implementation')


def append_event(events, payload):
    row = {'seq': len(events), 'previous_sha256': events[-1]['sha256'] if events else None,
           **copy.deepcopy(payload)}
    events.append({**row, 'sha256': digest(row)})


def replay(events, orders, pin, *, cutoff=None):
    """Rebuild from zero, never from standing/deliveries/success summary fields.

    Validate the whole immutable stream, including samples beyond cutoff, then
    apply only the requested prefix. A later cancellation always removes the
    earlier confirmation. A late redelivery cannot resurrect that confirmation.
    """
    from harness import zone_study_referee as zr
    validate_policy(pin)
    if not isinstance(events, list) or not events:
        raise ValueError('INVALID: raw referee event log missing')
    if any(not isinstance(r, dict) or type(r.get('seq')) is not int for r in events):
        raise ValueError('INVALID: referee event sequence missing/invalid')
    ordered = sorted(events, key=lambda r: r['seq'])
    previous, last = None, None
    ref = None
    for seq, row in enumerate(ordered):
        payload = {k: v for k, v in row.items() if k not in ('seq', 'previous_sha256', 'sha256')}
        if (row['seq'] != seq or row.get('previous_sha256') != previous
                or row.get('sha256') != digest({k: v for k, v in row.items() if k != 'sha256'})):
            raise ValueError('INVALID: referee event duplicate/gap/hash chain conflict')
        previous = row['sha256']
        if seq == 0:
            if (set(payload) != {'event', 'orders', 'static_map'} or payload['event'] != 'orders'
                    or digest(payload['orders']) != digest(orders)):
                raise ValueError('INVALID: referee order event conflicts with admission')
            ref = zr.Referee(orders, payload['static_map'])
            continue
        if set(payload) != {'event', 'sim_s', 'items'} or payload['event'] != 'sample':
            raise ValueError('INVALID: unknown referee input event')
        t = payload['sim_s']
        if (type(t) not in (int, float) or not math.isfinite(t) or t < 0
                or (last is not None and t < last)):
            raise ValueError('INVALID: referee samples must be finite and chronological')
        last = t
        if cutoff is None or t <= cutoff + 1e-9:
            ref.observe(t, payload['items'])
    return ref


def trial_projection(record, referee):
    """Outcome from the replayed prefix; lifecycle failures remain failures.

    The terminal reason is a lifecycle input only for API/host/policy aborts.
    Eligible normal endings derive their success and completion clock here.
    """
    from harness import zone_study_eval as ev
    result = copy.deepcopy(record)
    result['referee'] = {**result['referee'], 'deliveries': referee.trial_rows(),
                         'departed_unsettled': referee.departed_unsettled()}
    eligible = (not result.get('failure_class') and result['end_reason'] in
                ('sim_horizon', 'orders_incomplete', ev.SUCCESS_END_REASON))
    if eligible:
        if referee.orders_complete():
            result['end_reason'] = ev.SUCCESS_END_REASON
            result['end_sim_s'] = referee.completion_sim_s()
        elif result['end_reason'] == ev.SUCCESS_END_REASON:
            result['end_reason'] = 'orders_incomplete'
    return result
