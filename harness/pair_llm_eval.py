"""EVALUATION-ONLY judge and metrics of the pair LLM test. No robot-facing module imports this.

The physics owner writes ``eval_only/trajectory.jsonl`` (beam position every 0.05 SIM s). This module
reads it AFTER the case and returns a verdict. The verdict never re-enters a prompt, a permit, a wake-up or
an executor decision (``tests/test_pair_llm_boundary.py`` pins that no robot-side module imports it).

The judge is deliberately small and PROVISIONAL (``JUDGE_STATUS``). The v88 pair path records
``physical_success: None`` and the v96 judge (#363) is not final; this module does not invent a stronger
one. It states a geometric criterion on the beam alone so the three arms are compared with the SAME
evaluator, and it must be replaced by #363's judge when that is final.

Provisional criterion (all on the beam, SIM labels, evaluation only):

* ``in_zone_final``: the beam centre ends inside the destination zone rectangle of the static map;
* ``lifted``: the beam centre rose at least ``LIFT_MIN_M`` above its initial height at some time;
* ``set_down``: at the end the beam centre is at most ``SET_DOWN_MAX_M`` above its initial height.

``success_provisional`` is the conjunction. Delivery time is the first sample inside the zone.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from harness.pair_llm_decisions import LLM_INERT_THRESHOLD

CALL_CAP_LABELS = ('budget', 'http_budget', 'episode_call_cap')


def decision_evidence(*, condition, success, decisions=(), scheduler_events=(), failure_class=None):
    """Post-run classification only; never changes the controller or the raw geometric verdict."""
    counts = _count(r['decided_by'] for r in decisions)
    total = len(decisions)
    default_fraction = counts.get('rule_default', 0) / total if total else None
    labels = sorted({label for e in scheduler_events for label in CALL_CAP_LABELS
                     if e.get('event') == label or
                     (e.get('kind') == 'call_refused' and str(e.get('line', '')).endswith(' '+label))})
    cap = condition != 'rule' and bool(labels)
    inert = condition != 'rule' and default_fraction is not None and default_fraction > LLM_INERT_THRESHOLD
    api = failure_class == 'infra:API'
    classes = (['LLM_CALL_CAP_REACHED'] if cap else []) + (['LLM_INERT'] if inert else [])
    if api:
        classes.append('infra:API')
    return {'decisions_total': total, 'decided_by': counts, 'rule_default_fraction': default_fraction,
            'last_llm_decision_sim_s': max((r.get('decided_s', 0.) for r in decisions
                                          if r['decided_by'] == 'llm'), default=None),
            'llm_inert_threshold': LLM_INERT_THRESHOLD, 'classifications': classes,
            'call_cap_labels': labels, 'call_cap_end_reason': 'budget_exhausted' if cap else None,
            'llm_condition_evidence': condition != 'rule' and not (cap or inert or api),
            'primary_success': bool(success and not (cap or inert or api)),
            'completed_by_rule_default': bool(success and cap),
            'token_cap_label': 'pilot_budget_exhausted' if any(
                e.get('event') == 'pilot_budget_exhausted' for e in scheduler_events) else None}

EVAL_VERSION = 'ugrp.pair_llm_eval.v1'
JUDGE_STATUS = 'PROVISIONAL_GEOMETRIC_JUDGE_NOT_THE_363_JUDGE'
LIFT_MIN_M = .03
SET_DOWN_MAX_M = .05
MOTION_MIN_M = .02


def read_trajectory(path) -> list:
    rows = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _inside(xy, region) -> bool:
    (cx, cy), (hx, hy) = region['center_m'], region['half_extents_m']
    return abs(xy[0] - cx) <= hx and abs(xy[1] - cy) <= hy


def judge(rows, *, static_map, target_zone, start_s=0.) -> dict:
    """Verdict of one case from beam samples ``{'t', 'beam_xyz_m'}`` (``t`` in absolute SIM seconds)."""
    samples = [r for r in rows if r.get('t') is not None and r['t'] >= start_s - 1e-9]
    out = {'schema': EVAL_VERSION, 'judge_status': JUDGE_STATUS, 'target_zone': target_zone,
           'samples': len(samples), 'success_provisional': False}
    if len(samples) < 2:
        return {**out, 'reason': 'NO_TRAJECTORY'}
    region = static_map['regions'][f'zone_{target_zone}']
    first, last = samples[0], samples[-1]
    x0, y0, z0 = first['beam_xyz_m']
    traveled, lift_max, first_motion, first_zone = 0., 0., None, None
    previous = (x0, y0)
    for row in samples:
        x, y, z = row['beam_xyz_m']
        traveled += math.dist(previous, (x, y))
        previous = (x, y)
        lift_max = max(lift_max, z - z0)
        t = round(row['t'] - start_s, 6)
        if first_motion is None and math.dist((x0, y0), (x, y)) >= MOTION_MIN_M:
            first_motion = t
        if first_zone is None and _inside((x, y), region):
            first_zone = t
    xe, ye, ze = last['beam_xyz_m']
    in_zone = _inside((xe, ye), region)
    lifted = lift_max >= LIFT_MIN_M
    set_down = (ze - z0) <= SET_DOWN_MAX_M
    out.update({
        'start_xyz_m': [x0, y0, z0], 'final_xyz_m': [xe, ye, ze], 'displacement_m': math.dist((x0, y0), (xe, ye)),
        'traveled_m': traveled, 'lift_max_m': lift_max, 'in_zone_final': in_zone, 'lifted': lifted,
        'set_down': set_down, 'first_motion_s': first_motion, 'delivery_s': first_zone,
        'end_s': round(last['t'] - start_s, 6), 'success_provisional': bool(in_zone and lifted and set_down),
        'reason': 'OK' if (in_zone and lifted and set_down) else
        'NOT_IN_ZONE' if not in_zone else 'NEVER_LIFTED' if not lifted else 'NOT_SET_DOWN'})
    return out


# ---------------------------------------------------------------------------
# metrics of one trial (success comes ONLY from ``judge``)

def _sum(values) -> int:
    return sum(int(v) for v in values)


def trial_metrics(*, condition, verdict, command_counts, trial=None, ledger_walls=(), sabotage=(),
                  end_sim_s=None, model_calls_expected=True) -> dict:
    """The metric row of one arm. ``trial`` is None for the rule arm (no model, no messages)."""
    row = {'schema': EVAL_VERSION, 'condition': condition,
           'success': bool(verdict.get('success_provisional')), 'success_source': 'pair_llm_eval.judge',
           'judge_status': verdict.get('judge_status'), 'verdict_reason': verdict.get('reason'),
           'first_motion_s': verdict.get('first_motion_s'), 'delivery_s': verdict.get('delivery_s'),
           'end_sim_s': end_sim_s if end_sim_s is not None else verdict.get('end_s'),
           'command_count': dict(command_counts), 'command_count_total': _sum(command_counts.values()),
           'model_calls': 0, 'http_attempts': 0, 'model_cost_sim_s': 0., 'input_tokens': 0, 'output_tokens': 0,
           'input_tokens_image': 0, 'input_tokens_charged': 0, 'image_billing': None,
           'provider_usage': None, 'response_wall_s': None, 'messages': {'sent': 0, 'accepted': 0, 'rejected': 0},
           'language': {'messages': 0, 'hangul_ratio_ge_0_9': 0, 'share': None, 'flagged': 0, 'gate': False},
           'self_sabotage': {'events': len(sabotage), 'rows': [dict(r) for r in sabotage]},
           'claims': {'released': 0, 'submitted': 0, 'accepted': 0, 'rejected': 0, 'not_released_ticks': None}}
    if trial is None:
        return row
    cost = trial.cost_summary()
    row.update(model_calls=len(trial.calls), http_attempts=cost['http_attempts'],
               model_cost_sim_s=cost['call_sim_s'], input_tokens=cost['input_tokens'],
               input_tokens_image=cost['input_tokens_image'], input_tokens_charged=cost['input_tokens_charged'],
               image_billing=cost['image_billing'], output_tokens=cost['output_tokens'], model_calls_by_status=_count(c['status'] for c in trial.calls),
               model_calls_by_actor=_count(c['actor'] for c in trial.calls), censored_calls=cost['censored_calls'])
    walls = [float(w) for w in ledger_walls if w is not None]
    if walls:
        row['response_wall_s'] = {'total': round(sum(walls), 6), 'mean': round(sum(walls) / len(walls), 6),
                                  'max': round(max(walls), 6), 'requests': len(walls)}
    usages = [c.get('provider_usage') for c in trial.requests if c.get('provider_usage')]
    if usages:
        row['provider_usage'] = {k: sum(int(u.get(k, 0)) for u in usages)
                                 for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    channel = trial.channel_summary()
    row['messages'] = {'sent': channel['sent'] + channel['rejected'], 'accepted': channel['accepted_messages'],
                       'rejected': channel['rejected']}
    rows = [r for r in trial.language_rows if r['accepted']]
    # User decision 2026-10-03: no language requirement. ``language_report`` is a RECORD (the share of
    # messages with hangul ratio >= 0.9 and the flag count), never a gate and never a pass/fail field.
    hangul = sum(1 for r in rows if r['korean'])
    row['language'] = {'messages': len(rows), 'hangul_ratio_ge_0_9': hangul,
                       'share': None if not rows else hangul / len(rows),
                       'flagged': sum(1 for r in rows if r['flags']), 'gate': False,
                       'note': 'record only: no language is required of the messages'}
    row['actions'] = _count(a['kind'] for a in trial.actions)
    return row


def _count(values) -> dict:
    out: dict = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


__all__ = ['EVAL_VERSION', 'JUDGE_STATUS', 'read_trajectory', 'judge', 'trial_metrics']
