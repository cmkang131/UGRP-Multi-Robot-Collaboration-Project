"""pairact-r1 train-ready plan: training tiers, P5 v2 counting, hybrid switch rule (pure functions).

Nothing here runs a simulator, a trainer or a GPU. It turns the registered texts
(``experiments/2026-10-21-pairact-r1/TRAIN_PLAN.json``, ``PAIRACT_R1_EVAL_PREREG_DRAFT.json`` v2,
``HYBRID_SWITCH_RULE.md``) into functions so the numbers are computed the same way by
DeepSeek (runner side), Codex (recount) and the report.

- ``train_plan``: collection decision (harness.pairact_collect.decision) -> what P4/P5 do.
- ``episode_cap_s``: P5 episode cap from P2 teacher smoke carry durations (same cap both arms).
- ``p5_counts``: rows (``ugrp.pairact.p5_rows.v1``, scripts/pairact_p5_rows.py) -> per-arm
  n/N_eff, funnel, correction audit. Same semantics as dsh/report-auto ``pairact_eval``.
- ``hybrid_decision``: registered switch rule (pure student vs hybrid carry vs other fixes).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

FUNNEL = ('approach', 'alignment', 'READY', 'grasp', 'hold_3s', 'carry_1m', 'door', 'place')
ROWS_SCHEMA = 'ugrp.pairact.p5_rows.v1'

# --------------------------------------------------------------------------- training tiers

TRAINABLE = ('TRAIN', 'TRAIN_DATA_RANGE_LIMITED', 'TRAIN_SMALL_DATA')
NO_TRAIN = ('NO_TRAIN_BELOW_FLOOR', 'NO_TRAIN_DISTANCE_GATE', 'NO_TRAIN_VALIDATION_INSUFFICIENT',
            'NO_TRAIN_RECORD_ERROR')

_TIER = {
    'TRAIN': dict(
        claim='primary', p5_primary='success n/N_eff (student) beside teacher n/N_eff, funnel secondary',
        label=None, per_bin_report=False),
    'TRAIN_DATA_RANGE_LIMITED': dict(
        claim='primary_with_range_label',
        p5_primary='success n/N_eff beside teacher n/N_eff; heldout seeds of limited bins (index % 6) '
                   'reported in a separate row, never dropped',
        label='데이터 범위 제한', per_bin_report=True),
    'TRAIN_SMALL_DATA': dict(
        claim='funnel_primary',
        p5_primary='stage funnel n/N_eff per arm is the headline; success n/N_eff is still reported '
                   'and still counts for the r1 minimum',
        label='소량 데이터(A<150)', per_bin_report=True),
}


def train_plan(decision, labels=(), limited_bins=()):
    """Collection decision -> P4/P5 plan. Training hyperparameters never depend on the tier."""
    if decision in TRAINABLE:
        t = _TIER[decision]
        return dict(decision=decision, train=True, config='PAIRACT_R1_TRAIN_CONFIG_DRAFT.json',
                    config_deltas={}, steps=20000, offline_gate='OFFLINE_GATE.md (same thresholds)',
                    p5=True, claim=t['claim'], p5_primary=t['p5_primary'],
                    per_bin_report=t['per_bin_report'],
                    labels=list(labels) or ([t['label']] if t['label'] else []),
                    limited_bins=[b['bin'] if isinstance(b, dict) else b for b in limited_bins],
                    hybrid_rule=True)
    if decision in NO_TRAIN:
        nxt = {'NO_TRAIN_BELOW_FLOOR': 'P2 teacher path fix (owner 2026-10-21: A < 80 -> back to P2)',
               'NO_TRAIN_DISTANCE_GATE': 'report; start-distance coverage fails COLLECT_SPEC 2',
               'NO_TRAIN_VALIDATION_INSUFFICIENT': 'report; validation split cannot run the offline gate',
               'NO_TRAIN_RECORD_ERROR': 'report; recorder fault, data not usable'}[decision]
        return dict(decision=decision, train=False, p5=False, claim='none', labels=list(labels),
                    limited_bins=[], hybrid_rule=False, next=nxt,
                    report='A (collection yield) only; no C row, no student number')
    raise ValueError(f'unknown or unfinished collection decision {decision!r}')


# --------------------------------------------------------------------------- P5 episode cap

GRASP_CAP_S = 60.0          # P1 gate / --cap-s 60
RELEASE_INSTRUCTION_S = 3.0
FINISH_AFTER_S = 1.5
CARRY_BUDGET_MAX_S = 120.0  # runner carry cap upper bound


def episode_cap_s(carry_s, *, any_timeout=False):
    """cap = 60 + carry_budget; carry_budget = ceil10(1.5 * max carry_s) + 3.0 + 1.5, at most 120.

    carry_s: SIM s from handover to the teacher 'done' phase, one per P2 smoke world whose teacher
    command sequence completed. No complete carry -> None (P5 does not start). Any carry timeout ->
    budget 120 (recorded)."""
    if any_timeout:
        budget = CARRY_BUDGET_MAX_S
    else:
        vals = [float(x) for x in carry_s]
        if not vals:
            return None
        if any(not math.isfinite(v) or v <= 0 for v in vals):
            raise ValueError('carry durations must be finite and positive')
        budget = min(CARRY_BUDGET_MAX_S,
                     10 * math.ceil(1.5 * max(vals) / 10) + RELEASE_INSTRUCTION_S + FINISH_AFTER_S)
    return dict(cap_s=GRASP_CAP_S + budget, grasp_cap_s=GRASP_CAP_S, carry_budget_s=budget,
                rule='60 + min(120, ceil10(1.5*max carry_s) + 3.0 + 1.5); timeout -> 120')


# --------------------------------------------------------------------------- P5 counting


def read_rows(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if not rows or rows[0].get('type') != 'header' or rows[0].get('schema') != ROWS_SCHEMA:
        raise ValueError(f'{path}: first row must be the {ROWS_SCHEMA} header')
    return rows[0], rows[1:]


def p5_counts(header, episodes, *, seeds, arms):
    """Per arm: success n/N_eff, funnel n/N_eff, correction audit. Mirrors report-auto pairact_eval.

    One final row per (arm, seed): attempt 2 replaces attempt 1 only when attempt 1 was HOST_ERROR.
    Excluded seeds (rule A, header) leave the denominator; an episode on an excluded seed is an error.
    A student success needs both correction counters == 0; None = unverified = not a success."""
    excluded = {int(s) for s in header.get('excluded_seeds') or ()}
    if excluded - set(seeds):
        raise ValueError('excluded seed outside the heldout range')
    if excluded and not header.get('static_check_sha256'):
        raise ValueError('rule A exclusion needs static_check_sha256 in the header')
    eff = [s for s in seeds if s not in excluded]
    final = {a: {} for a in arms}
    for r in episodes:
        if r.get('type') != 'episode':
            continue
        a, s = r['arm'], int(r['seed'])
        if a not in final:
            raise ValueError(f'arm {a!r} not registered')
        if s in excluded:
            raise ValueError(f'episode on excluded seed {s}')
        prev = final[a].get(s)
        if prev is not None and not (prev['status'] == 'HOST_ERROR' and int(r.get('attempt', 1)) == 2):
            raise ValueError(f'duplicate {a} seed {s}')
        final[a][s] = r
    out = dict(n_eff=len(eff), excluded_seeds=sorted(excluded), arms={})
    for a in arms:
        res = dict(success=0, missing=[], host_error=[], corrections_nonzero=[], corrections_unknown=[],
                   funnel={st: 0 for st in FUNNEL}, unrecorded=[])
        for s in eff:
            r = final[a].get(s)
            if r is None:
                res['missing'].append(s)
                continue
            if r['status'] == 'HOST_ERROR':
                res['host_error'].append(s)
                continue
            ok = r.get('success') is True
            if a != 'teacher':
                c = (r.get('student_gt_corrections'), r.get('teacher_commands_issued_to_student'))
                if any(v is None for v in c):
                    res['corrections_unknown'].append(s)
                    ok = False
                elif any(v != 0 for v in c):
                    res['corrections_nonzero'].append(s)
                    ok = False
            res['success'] += ok
            for st in FUNNEL:
                v = (r.get('funnel') or {}).get(st)
                if v is None:
                    if st not in res['unrecorded']:
                        res['unrecorded'].append(st)
                elif st == 'place':
                    res['funnel'][st] += bool(v) and ok
                else:
                    res['funnel'][st] += bool(v)
        out['arms'][a] = res
    return out


# --------------------------------------------------------------------------- hybrid switch rule

HYBRID_RULE_ID = 'pairact_r1_hybrid_switch_v1'


def k_hold(n_eff):
    """Registered threshold for 'student reaches the 3 s joint hold often enough'."""
    return max(3, math.ceil(0.15 * n_eff))


def hybrid_decision(counts, *, student='student', teacher='teacher'):
    """Registered rule (HYBRID_SWITCH_RULE.md), evaluated once on the P5 counts, in this order.

    0 INVALID_STUDENT_CORRECTED  any student row with a nonzero correction counter
    0 UNVERIFIED_CORRECTIONS      any completed student row with an unknown counter
    1 GRASP_FIRST                 H < k            (failure before the hold; hybrid cannot help)
    2 P2_PATH_FIRST               teacher door < ceil(N/2) (carry path itself weak)
    3 HYBRID_CARRY                D <= floor(H/2)  (most hold-passers fail before the door)
    4 PLACE_FIRST                 P <= floor(D/2)  (carry works, lowering/releasing fails)
    5 PURE_CONTINUE               otherwise
    H, D, P = student hold_3s, door, place counts; N = N_eff; k = max(3, ceil(0.15 N))."""
    n = counts['n_eff']
    s, t = counts['arms'][student], counts['arms'][teacher]
    h, d, p = s['funnel']['hold_3s'], s['funnel']['door'], s['funnel']['place']
    td = t['funnel']['door']
    k = k_hold(n)
    base = dict(rule=HYBRID_RULE_ID, n_eff=n, k=k, H=h, D=d, P=p, teacher_door=td,
                pure_minimum_met=s['success'] >= 1)
    if s['corrections_nonzero']:
        return dict(base, decision='INVALID_STUDENT_CORRECTED', seeds=s['corrections_nonzero'])
    if s['corrections_unknown']:
        return dict(base, decision='UNVERIFIED_CORRECTIONS', seeds=s['corrections_unknown'])
    if 'hold_3s' in s['unrecorded'] or 'door' in s['unrecorded'] or 'door' in t['unrecorded']:
        return dict(base, decision='UNVERIFIED_FUNNEL')
    if h < k:
        return dict(base, decision='GRASP_FIRST')
    if td < math.ceil(n / 2):
        return dict(base, decision='P2_PATH_FIRST')
    if d <= h // 2:
        return dict(base, decision='HYBRID_CARRY')
    if p <= d // 2:
        return dict(base, decision='PLACE_FIRST')
    return dict(base, decision='PURE_CONTINUE')
