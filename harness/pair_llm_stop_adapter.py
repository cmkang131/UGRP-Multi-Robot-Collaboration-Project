"""Own-executor adapter for #363. Evaluation rows never enter the input projection."""
from __future__ import annotations

import copy

from harness import pair_llm_decisions as contract
from harness import pair_llm_clock as clock
from harness.zone_study_contract import ContractViolation

BELIEF_ENUMS = {
    'sigma_xy_band': ('fix', 'budget', 'over', 'unknown'),
    'sigma_yaw_band': ('within', 'over', 'unknown'),
    'fix_age_bucket': ('none', 'lt_6s', 'lt_60s', 'ge_60s'),
    'dr_budget_remaining_bucket': ('gt_50pct', '25_50pct', 'lt_25pct', 'none', 'unknown'),
}


def unknown_belief():
    return {'sigma_xy_band': 'unknown', 'sigma_yaw_band': 'unknown', 'fix_age_bucket': 'none',
            'dr_budget_remaining_bucket': 'unknown', 'over_budget': True}


def belief_violations(value):
    if not isinstance(value, dict) or set(value) != set(BELIEF_ENUMS) | {'over_budget'}:
        return ['own_belief needs exactly the five closed own-estimate fields']
    if any(value[k] not in choices for k, choices in BELIEF_ENUMS.items()) or type(value['over_budget']) is not bool:
        return ['own_belief has a value outside its closed vocabulary']
    return []


def window_violations(value, now):
    if value is None:
        return []
    import math
    keys = {'kind', 'opened_at_sim_s', 'decide_at_sim_s', 'latch_until_sim_s'}
    if not isinstance(value, dict) or set(value) != keys or value['kind'] not in tuple(contract.HOOK_ACTIONS):
        return ['decision_window has unknown fields or kind']
    start, end, cutoff = (value[k] for k in ('opened_at_sim_s', 'decide_at_sim_s', 'latch_until_sim_s'))
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end, cutoff, now)):
        return ['decision_window needs finite times']
    start, end, cutoff, now = (clock.ticks(t) for t in (start, end, cutoff, now))
    if not (start <= now < end and start <= cutoff <= end and 0 < end-start <= clock.WINDOW):
        return ['decision_window is not open on the harness clock']
    return []


class StopAdapter:
    """Reads only the given own executor; never looks up a partner, world or evaluator.

    Commands bind to the window observed at call start, not whichever stop exists on reply arrival.
    Polling is read-only except record annotations and carrying the per-case look cap across own retries.
    """

    def __init__(self, executor, *, condition, origin_s, window=None):
        self.executor, self.condition, self.origin_s = executor, condition, float(origin_s)
        self.window = window or contract.DecisionWindow()
        self.controllers, self.events, self.decisions = [], [], []
        self._event_marks, self._seen_decisions = {}, set()
        self.look_again_total = 0
        self._active = None

    def controller(self):
        pair = getattr(self.executor, '_pair', None)
        ctl = getattr(pair, 'controller', None)
        if ctl is not None and not callable(getattr(ctl, 'carry_decision', None)):
            ctl = None                         # explicit legacy/fake-runtime regression seam
        if ctl is not self._active:
            self.window.current = None
            self._active = ctl
        if ctl is not None and not any(c is ctl for c in self.controllers):
            ctl.refix_condition = self.condition
            ctl.refix_llm_attached = self.condition != 'rule'
            ctl.refix_look_again_total = self.look_again_total
            self.controllers.append(ctl)
        return ctl

    def own_belief(self, absolute_now):
        ctl = self.controller()
        value = unknown_belief() if ctl is None else ctl.own_belief(absolute_now)
        errors = belief_violations(value)
        if errors:
            raise ContractViolation('; '.join(errors))
        return dict(value)

    def poll(self):
        active = self.controller()
        deliveries = []
        for ctl in self.controllers:
            self.look_again_total = max(self.look_again_total, getattr(ctl, 'refix_look_again_total', 0))
            rows = getattr(ctl, 'refix_hook_events', ())
            for row in rows[self._event_marks.get(id(ctl), 0):]:
                if row['event'] not in contract.HOOK_EVENTS:
                    raise ContractViolation('unknown #363 hook event')
                self.events.append({'robot_id': self.executor.robot_id, **copy.deepcopy(row)})
                if ctl is active:
                    sim_s, times = clock.hook_times(row)
                    detail = {'kind': row['event'], **times}
                    deliveries.append({'robot_id': self.executor.robot_id, 'event': 'pair_progress',
                                       'sim_s': sim_s, 'job_kind': 'pair_carry', 'job_id': None,
                                       'scheduler_trigger': None, 'detail': detail})
            self._event_marks[id(ctl)] = len(rows)
            look = getattr(ctl, 'refix_look', {})
            for kind, records in (('carry_decision', getattr(ctl, 'refix_hook_decisions', ())),
                                  ('post_look_decision', look.get('decisions', ()))):
                for row in records:
                    # Retain immutable identities (the controller can replace its look dictionary).
                    key = (id(ctl), kind, row['stop'], row['sim_s'])
                    if key not in self._seen_decisions:
                        self._seen_decisions.add(key)
                        rec = {'robot_id': self.executor.robot_id, 'kind': kind, **copy.deepcopy(row)}
                        for field in ('sim_s', 'decided_s', 'rule_decided_s', 'executed_s'):
                            if rec.get(field) is not None:
                                rec[field+'_absolute'] = rec[field]
                                rec[field] = clock.relative(rec[field], self.origin_s)
                        self.decisions.append(rec)
        return deliveries

    def command(self, api, choice, *, absolute_now, window_ref):
        ctl = self.controller()
        now = clock.relative(absolute_now, self.origin_s)
        w = self.window.snapshot(now)
        reason = None
        if self.condition == 'rule' or ctl is None:
            reason = 'NOT_AT_STOP' if api == 'carry_decision' else 'NOT_AFTER_LOOK'
        elif api not in contract.HOOK_ACTIONS or choice not in contract.HOOK_ACTIONS[api]:
            reason = 'UNKNOWN_CHOICE'
        elif window_ref is None or window_ref != self.window.reference(now) or w['kind'] != api:
            reason = 'DEADLINE_PASSED'
        elif choice == 'set_down' and clock.ticks(now) > clock.ticks(w['latch_until_sim_s']):
            reason = 'DEADLINE_PASSED'
        if reason:
            return {'accepted': False, 'own_status': reason}
        return getattr(ctl, api)(choice, absolute_now)
