"""Evaluation-only referee and hidden-event schedule of the integrated zone study (B6, #224).

EVALUATION ONLY. Nothing in this module may reach robot control, a stage
transition or a robot-visible message. The physics owner
(``scripts/run_zone_study_integration.py``) feeds it simulator truth after each
physics chunk and writes its output under ``eval_only/`` and the trial record's
``referee`` block. The only effect on the episode is that the physics owner stops
the episode when :meth:`Referee.orders_complete` holds; robots are not told why,
exactly as when the horizon ends an episode. ``harness.zone_study_integration``
(the study layer) never imports this module (tested).

Delivery rule (one item, per physics chunk of simulator truth):

* the item's object-frame landing rectangle at its current pose lies inside the
  destination zone rectangle. The rectangle and the containment test are the
  catalogue's (``sim.zone_cargo`` ``landing_half_extents_m``; colour boxes use
  ``sim.zone_arena.BOX_HALF``), reused from
  ``harness.zone_scenario_feasibility.landing_fits`` and ``zone_rect``;
* it rests on the floor: body height below ``ON_FLOOR_MAX_Z_M`` (the previous
  integration referee's constant);
* no robot finger touches it (``held`` is False);
* it is settled: linear speed below ``SETTLED_SPEED_M_S``;
* all four held continuously for ``SETTLE_S`` SIM seconds. The delivery time is
  the start of that window (``sim_s``, the previous referee's convention); the
  confirmation time is ``confirmed_sim_s``.

After a confirmation an item stays delivered while its landing rectangle stays
in the same zone and it stays on the floor. A bump does not undo it, and neither
does a brief touch: only a hold lasting ``HELD_DEPART_S`` (PR #257 review P2-K;
fingers brushing a delivered item or a re-grasp given up at once) records a
``departed`` row, as do leaving the zone and being lifted. A later settle
confirms again. Order matching (fungible counts, named items, misdeliveries) is
``harness.zone_study_eval.delivery_state`` on CONFIRMATION rows only: the trial
record gets every confirmation of each item still standing (so a corrected
misdelivery stays in the history) and nothing for an item that departed and
never settled again; that item is listed apart in ``departed_unsettled``
(neither delivered nor misdelivered). ``par_makespan_sim_s`` and
``delivery_rate`` come from ``zone_study_eval.efficiency_metrics`` on the saved
trial record (the runner calls it), not from a second formula here.

Hidden events (scenario ``eval.hidden_events``, schema checked by
``harness.zone_study_scenarios``): :class:`HiddenEventSchedule` only says which
events are due at a SIM time. Their physical realisation is
``sim.zone_hidden_events`` in the physics owner. A hidden event never produces a
robot input, message, command row or wake.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence

from harness import zone_study_eval as ev
from harness.zone_scenario_feasibility import landing_fits, zone_rect
from harness.zone_study_contract import ContractViolation, digest
from harness.zone_study_inputs import hidden_events as scenario_hidden_events
from harness.zone_study_scenarios import EVENT_KINDS
from sim import zone_hidden_events as realisation

REFEREE_PROFILE = 'zone_study_referee.v3'
SETTLE_S = 2.0
ON_FLOOR_MAX_Z_M = .05
SETTLED_SPEED_M_S = .01
HELD_DEPART_S = 1.0
ZONES = ('A', 'B', 'C')
TRUTH_KEYS = frozenset({'kind', 'x', 'y', 'yaw', 'z', 'held', 'speed'})


def profile() -> dict:
    """Everything that fixes the referee's decisions (hashed into the run bundle)."""
    row = {'profile': REFEREE_PROFILE, 'settle_s': SETTLE_S, 'on_floor_max_z_m': ON_FLOOR_MAX_Z_M,
           'settled_speed_m_s': SETTLED_SPEED_M_S, 'held_depart_s': HELD_DEPART_S,
           'landing_rule': 'harness.zone_scenario_feasibility.landing_fits',
           'order_rule': 'harness.zone_study_eval.delivery_state',
           'metrics': 'harness.zone_study_eval.efficiency_metrics',
           'penalty_factor': ev.DEFAULT_PENALTY_FACTOR, 'success_end_reason': ev.SUCCESS_END_REASON,
           'confirmation_window': 'confirmation must precede observed end and SIM cap',
           'missing_sample': 'break settling window; invalidate standing delivery',
           'scope': 'evaluation only; stops the episode on orders_complete; never a robot input'}
    return {**row, 'sha256': digest(row)}


class Referee:
    """Online delivery judge from simulator truth. Evaluation only."""

    def __init__(self, orders: Sequence[Mapping], static_map: Mapping):
        if not orders:
            raise ContractViolation('the referee needs a non-empty order sheet')
        self.orders = [copy.deepcopy(dict(o)) for o in orders]
        ev._orders({'orders': self.orders})  # reject ambiguous order/item joins before sampling
        self.zones = {z: zone_rect(static_map, z) for z in ZONES if f'zone_{z}' in static_map['regions']}
        self._cand: dict[str, dict] = {}        # item -> {'zone', 'since'} while not yet confirmed
        self._held_since: dict[str, float] = {}  # standing item -> SIM start of its current continuous hold
        self.standing: dict[str, dict] = {}     # item -> confirmation row still standing
        self.history: list[dict] = []           # confirmations and departures, in SIM order
        self.samples = 0
        self.last_t = None
        self.completed_at = None                # SIM time orders_complete first held (chunk boundary)
        self._kinds: dict[str, str] = {}

    # -- judgement ----------------------------------------------------------
    def zone_of(self, row: Mapping):
        """The zone whose rectangle contains the item's whole landing rectangle, or None."""
        pose = (float(row['x']), float(row['y']), float(row['yaw']))
        for z, rect in self.zones.items():
            if landing_fits(row['kind'], pose, rect):
                return z
        return None

    def _resting_zone(self, row):
        if row['held'] or float(row['z']) >= ON_FLOOR_MAX_Z_M:
            return None
        return self.zone_of(row)

    def _departure(self, item, row, done, t):
        """Why a standing delivery ends now, or None (a bump or a brief touch keeps it)."""
        if float(row['z']) >= ON_FLOOR_MAX_Z_M:
            return 'lifted'
        if self.zone_of(row) != done['zone']:
            return 'left_zone'
        if not row['held']:
            self._held_since.pop(item, None)
            return None
        since = self._held_since.setdefault(item, t)
        return 'held' if t - since >= HELD_DEPART_S - 1e-9 else None

    def observe(self, t: float, items: Mapping[str, Mapping]) -> list[dict]:
        """One truth sample at SIM ``t``. Returns the rows it appended (eval only)."""
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
            raise ContractViolation('referee SIM time must be finite and nonnegative')
        t = float(t)
        if self.last_t is not None and t < self.last_t - 1e-9:
            raise ContractViolation('referee samples must be in SIM order')
        for item, row in sorted(items.items()):
            if set(row) != TRUTH_KEYS:
                raise ContractViolation(f'{item}: truth row keys {sorted(row)} != {sorted(TRUTH_KEYS)}')
            if not isinstance(row['held'], bool) or any(
                    isinstance(row[k], bool) or not isinstance(row[k], (int, float)) or not math.isfinite(row[k])
                    for k in ('x', 'y', 'yaw', 'z', 'speed')):
                raise ContractViolation(f'{item}: truth row needs finite numbers and a bool held (corrupted '
                                        'simulator state is refused, never judged)')
            if (not isinstance(item, str) or not item or not isinstance(row['kind'], str)
                    or not row['kind'] or row['speed'] < 0 or row['z'] < 0
                    or self._kinds.get(item, row['kind']) != row['kind']):
                raise ContractViolation('invalid item identity, kind, height or speed')
        self.last_t, self.samples = t, self.samples + 1
        new = []
        # A missing truth sample is not evidence of continuous settling/standing.
        for item in (self._cand.keys() | self.standing.keys()) - items.keys():
            self._cand.pop(item, None)
            self._held_since.pop(item, None)
            done = self.standing.pop(item, None)
            if done is not None:
                gone = {**done, 'event': 'departed', 'zone': None, 'from_zone': done['zone'],
                        'sim_s': t, 'reason': 'missing_truth'}
                self.history.append(gone)
                new.append(gone)
        for item, row in sorted(items.items()):
            self._kinds[item] = row['kind']
            zone = self._resting_zone(row)
            done = self.standing.get(item)
            if done is not None:
                why = self._departure(item, row, done, t)
                if why is None:
                    continue                       # still delivered
                del self.standing[item]
                held_since = self._held_since.pop(item, None)
                gone = {'item_id': item, 'kind': row['kind'], 'zone': None, 'from_zone': done['zone'],
                        'sim_s': round(t, 4), 'event': 'departed', 'reason': why,
                        **({'held_since_sim_s': round(held_since, 4)} if why == 'held' else {})}
                self.history.append(gone)
                new.append(gone)
            settled = zone is not None and float(row['speed']) < SETTLED_SPEED_M_S
            cand = self._cand.get(item)
            if not settled:
                self._cand.pop(item, None)
                continue
            if cand is None or cand['zone'] != zone:
                self._cand[item] = {'zone': zone, 'since': t}
                continue
            if t - cand['since'] >= SETTLE_S - 1e-9:
                del self._cand[item]
                done = {'item_id': item, 'kind': row['kind'], 'zone': zone, 'sim_s': round(cand['since'], 4),
                        'confirmed_sim_s': round(t, 4), 'event': 'confirmed'}
                self.standing[item] = done
                self.history.append(done)
                new.append(done)
        if self.completed_at is None and self.orders_complete():
            self.completed_at = round(t, 4)
        return new

    def state(self, end_sim_s=None) -> dict:
        """``zone_study_eval.delivery_state`` over the standing confirmations."""
        end = self.last_t if end_sim_s is None else end_sim_s
        rows = [{k: r[k] for k in ('item_id', 'kind', 'zone', 'sim_s')} for r in self.standing.values()]
        return ev.delivery_state({'orders': self.orders, 't0_sim_s': 0.0, 'end_sim_s': end or 0.0,
                                  'referee': {'deliveries': rows}})

    def orders_complete(self) -> bool:
        return bool(self.standing) and self.state()['orders_complete']

    def completion_sim_s(self):
        """Delivery time of the last item that completed the orders (None if incomplete)."""
        state = self.state()
        if not state['orders_complete']:
            return None
        return max(d['sim_s'] for d in state['delivered'].values())

    def per_order(self) -> dict:
        """order_id -> ordered/delivered counts, item delivery times and completion time."""
        state = self.state()
        out = {}
        for order in self.orders:
            oid = order['order_id']
            items = {i: d['sim_s'] for i, d in state['delivered'].items() if d['order_id'] == oid}
            row = state['by_order'][oid]
            out[oid] = {'destination_zone': order.get('destination_zone'), 'ordered': row['ordered'],
                        'delivered': row['delivered'], 'complete': row['complete'],
                        'item_delivered_sim_s': dict(sorted(items.items())),
                        'completed_sim_s': max(items.values()) if row['complete'] and items else None}
        return out

    def departed_unsettled(self) -> list[dict]:
        """Items whose last referee event is a departure: neither delivered nor misdelivered."""
        last = {}
        for r in self.history:
            last[r['item_id']] = r
        return [dict(r) for item, r in sorted(last.items()) if r['event'] == 'departed']

    def trial_rows(self) -> list[dict]:
        """``delivery_state`` rows: every confirmation of each item still standing, in SIM order."""
        return [{k: r[k] for k in ('item_id', 'kind', 'zone', 'sim_s', 'confirmed_sim_s')} for r in self.history
                if r['event'] == 'confirmed' and r['item_id'] in self.standing]

    def record(self) -> dict:
        """The eval-only referee block (deliveries = confirmations; history also has departures)."""
        return {'profile': profile(), 'source': 'eval_only simulator truth',
                'deliveries': [dict(r) for r in self.history if r['event'] == 'confirmed'],
                'history': [dict(r) for r in self.history], 'standing': copy.deepcopy(self.standing),
                'departures': sum(r['event'] == 'departed' for r in self.history),
                'departed_unsettled': self.departed_unsettled(),
                'orders': self.per_order(), 'orders_complete': self.orders_complete(),
                'completion_sim_s': self.completion_sim_s(), 'completed_at_chunk_sim_s': self.completed_at,
                'samples': self.samples, 'last_sample_sim_s': self.last_t}


def evaluation_block(record: Mapping, referee: Referee) -> dict:
    """PAR-2 / delivery rate from ``zone_study_eval.efficiency_metrics`` + per-order times."""
    metrics = ev.efficiency_metrics(record)
    state = ev.delivery_state(record)
    orders = referee.per_order()
    for oid, row in orders.items():
        items = {i: d['sim_s'] for i, d in state['delivered'].items() if d['order_id'] == oid}
        row.update(state['by_order'][oid], item_delivered_sim_s=items,
                   completed_sim_s=max(items.values()) if state['by_order'][oid]['complete'] and items else None)
    keys = ('end_reason', 'success', 'par_makespan_sim_s', 'penalty_factor', 'sim_horizon_s', 'makespan_sim_s',
            'delivery_rate', 'delivered_items', 'ordered_items', 'misdelivered_items', 'surplus_items',
            'orders_complete', 'orders_by_id')
    return {'schema': 'ugrp.zone_study_referee_evaluation.v2', **{k: metrics[k] for k in keys},
            'departures': sum(r['event'] == 'departed' for r in referee.history),
            'departed_unsettled_items': len(referee.departed_unsettled()),
            't0_sim_s': record.get('t0_sim_s'), 'end_sim_s': record['end_sim_s'],
            'orders': orders, 'referee_profile_sha256': profile()['sha256'],
            'note': 'evaluation only; never a robot input'}


def apply_to_record(record: dict, referee: Referee) -> dict:
    """Fill a package I trial record's referee block; success only from the referee."""
    record['referee'] = {'deliveries': referee.trial_rows(), 'departed_unsettled': referee.departed_unsettled(),
                         'profile': REFEREE_PROFILE, 'observed_end_sim_s': record['end_sim_s']}
    done = referee.completion_sim_s()
    eligible = (not record.get('failure_class') and record['end_reason'] in
                ('sim_horizon', 'orders_incomplete', ev.SUCCESS_END_REASON))
    if done is not None and eligible and ev.delivery_state(record)['orders_complete']:
        record['end_reason'], record['end_sim_s'] = ev.SUCCESS_END_REASON, done
    return record


def not_evaluated(record: dict) -> dict:
    """The referee block when no referee exists (the run failed before it); the study
    layer never sets ``orders_complete``, so such a record is never a success."""
    record['referee'] = {'deliveries': [], 'status': 'not_evaluated', 'profile': REFEREE_PROFILE}
    if record.get('end_reason') == ev.SUCCESS_END_REASON:
        record['end_reason'] = 'not_evaluated'
    return record


# ---------------------------------------------------------------------------
# Hidden events: when, never how (``sim.zone_hidden_events`` realises them)

class HiddenEventSchedule:
    """The scenario's private hidden events, fired once each at their SIM trigger time."""

    def __init__(self, scenario: Mapping):
        self.events = scenario_hidden_events(scenario)
        for e in self.events:
            if e.get('kind') not in EVENT_KINDS or (e.get('trigger') or {}).get('kind') != 'sim_time':
                raise ContractViolation(f'unsupported hidden event {e!r:.200}')
        self.events.sort(key=lambda e: float(e['trigger']['at_sim_s']))
        self._next = 0

    def due(self, t: float) -> list[dict]:
        out = []
        while self._next < len(self.events) and float(self.events[self._next]['trigger']['at_sim_s']) <= t + 1e-9:
            out.append(copy.deepcopy(self.events[self._next]))
            self._next += 1
        return out

    def obstacles(self) -> list[dict]:
        """Static obstacle shapes the scene must build (parked) for later events."""
        return [copy.deepcopy(e['target']['obstacle']) for e in self.events
                if e['kind'] in ('passage_blocked', 'obstruction_added')]

    def config(self) -> dict:
        row = {**realisation.profile({e['kind'] for e in self.events}),
               'events': [{'event_id': e['event_id'], 'kind': e['kind'], 'at_sim_s': e['trigger']['at_sim_s']}
                          for e in self.events]}
        return {**row, 'sha256': digest(row)}


def item_yaw(quat: Sequence[float]) -> float:
    """Yaw of a MuJoCo (w, x, y, z) quaternion."""
    w, x, y, z = (float(v) for v in quat)
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
