"""L2 E2E evaluator (eval-only, default OFF).

Two layers, never merged into one number before the final AND:

1. LLM stage (from ``allocate_ends`` records + the admin geometry):
   cooperation judgement, end assignment vs the generator reference,
   duplicate end (conflict), named errors, heuristic hallucination flags,
   rounds/utterances/tokens/USD.
2. execution stage: the P2 root runner's own ``summary.json`` rows
   (``scripts/run_warp_flow_teacher.py``), i.e. the unchanged GT pair-carry
   evaluator ``carry_success`` (placed in zone B, 0 drops, 0 robot-robot
   contacts) plus, for the student arm, ``teacher_steps == 0``.

L2 success for one seed = LLM ``success_eligible`` AND executed AND
``carry_success is True`` AND (student arm) ``teacher_steps == 0``.  The
teacher-fallback arm is reported with its label and is never counted as a
learned result.
"""
from __future__ import annotations

import re

from harness.e2e_l2 import ARM_LABEL, ARMS, ENDS, ROBOTS

#: Words that name a beam end or a band the brief never shows (colour tokens
#: are hidden from the LLM; north/south are not the order's end names).
_FOREIGN_END = re.compile(r'\b(north|south)(ern)?\s+end\b|\b(teal|blue)\b', re.I)
_DIST = re.compile(r'(\d+(?:\.\d+)?)\s*(?:m\b|meters?\b|metres?\b)', re.I)
#: A distance number is "grounded" if within this of any own brief distance
#: (design value: 2x the 0.01 m brief resolution + rounding by the model).
DIST_TOL_M = .1


def hallucination_flags(record, geometry):
    """Heuristic, conservative flags (Codex re-annotates by hand).

    ``foreign_end``: names an end/band the brief does not contain.
    ``ungrounded_distance``: states a distance in metres that matches none of
    the sender's own brief distances (a robot never sees the peer's numbers
    unless the peer sent them; numbers received from the peer are allowed).
    """
    flags = []
    received = {r: [] for r in ROBOTS}
    for msg in record.get('messages') or []:
        body = msg.get('body') or {}
        text = body.get('text') if isinstance(body, dict) else None
        if not isinstance(text, str):
            continue
        sender = msg['sender']
        if _FOREIGN_END.search(text):
            flags.append(dict(robot=sender, round=msg.get('round'), kind='foreign_end'))
        allowed = list(geometry['own_distances'][sender].values()) + received[sender]
        for value in (float(v) for v in _DIST.findall(text)):
            if not any(abs(value - a) <= DIST_TOL_M for a in allowed):
                flags.append(dict(robot=sender, round=msg.get('round'), kind='ungrounded_distance', value=value))
        for to in msg.get('to') or []:
            received[to].extend(float(v) for v in _DIST.findall(text))
    return flags


def llm_metrics(record, geometry, prices=None):
    decisions = dict(record.get('decisions') or {})
    ref = geometry['reference_ends']
    complete = set(decisions) == set(ROBOTS) and all(decisions[r] in ENDS for r in ROBOTS)
    tokens = dict(prompt_tokens=sum(u.get('prompt_tokens', 0) for u in record.get('usage') or []),
                  completion_tokens=sum(u.get('completion_tokens', 0) for u in record.get('usage') or []))
    usd = None
    if prices is not None:
        usd = round((tokens['prompt_tokens'] * prices['prompt'] + tokens['completion_tokens'] * prices['completion'])
                    / 1e6, 6)
    flags = hallucination_flags(record, geometry)
    return dict(
        condition=record.get('condition'), seed=record.get('seed'),
        cooperate_ok=bool(record.get('cooperate_ok')),
        need_partner=dict(record.get('need_partner') or {}),
        decisions=decisions,
        reference_ends=dict(ref),
        assignment_match=complete and decisions == ref,
        min_distance_match=complete and decisions == geometry['min_total_distance_ends'],
        conflict=complete and len(set(decisions.values())) == 1,
        nearer_end_conflict=geometry['nearer_end_conflict'],
        errors=list(record.get('errors') or []), fatal=bool(record.get('fatal')),
        success_eligible=bool(record.get('success_eligible')),
        rounds=record.get('rounds'), utterances=record.get('utterances'),
        language_slips=sum(1 for m in record.get('messages') or [] if m.get('language_slip')),
        message_drops=len(record.get('message_drops') or []),
        hallucination_n=len(flags), hallucination_flags=flags,
        llm_calls=len(record.get('calls') or []), tokens=tokens, usd=usd,
    )


def execution_row(summary, seed):
    """The runner's world row for this seed, or None (not executed)."""
    rows = [w for w in (summary or {}).get('worlds') or [] if w.get('seed') == seed]
    if len(rows) > 1:
        raise ValueError(f'seed {seed} appears {len(rows)} times in one summary')
    return rows[0] if rows else None


def seed_result(record, geometry, summary, *, arm, prices=None):
    if arm not in ARMS:
        raise ValueError('unknown arm ' + str(arm))
    llm = llm_metrics(record, geometry, prices)
    row = execution_row(summary, record.get('seed')) if llm['success_eligible'] else None
    executed = row is not None
    carry = None if row is None else row.get('carry_success')
    teacher_steps = None if row is None else row.get('teacher_steps')
    student_clean = arm != 'student' or teacher_steps == 0
    if arm == 'student' and summary is not None and executed and summary.get('student_eval') is None:
        student_clean = False   # a summary without --student-eval is a teacher run
    success = bool(llm['success_eligible'] and executed and carry is True and student_clean)
    return dict(seed=record.get('seed'), arm=arm, arm_label=ARM_LABEL[arm], llm=llm, executed=executed,
                carry_success=carry, carry_failure=None if row is None else row.get('carry_failure'),
                teacher_steps=teacher_steps, student_funnel=None if row is None else row.get('student_funnel'),
                student_clean=student_clean, success=success,
                failure_stage=('llm' if not llm['success_eligible'] else 'not_executed' if not executed
                               else 'student_contaminated' if not student_clean
                               else None if success else 'execution'))


def aggregate(results):
    by = {}
    for r in results:
        key = (r['llm']['condition'], r['arm'])
        a = by.setdefault(key, dict(condition=key[0], arm=key[1], arm_label=ARM_LABEL[key[1]], N=0, success_n=0,
                                    llm_eligible_n=0, assignment_match_n=0, conflict_n=0, cooperate_ok_n=0,
                                    hallucination_n=0, executed_n=0, carry_success_n=0, tokens=0, usd=0.,
                                    failure_stage={}))
        a['N'] += 1
        a['success_n'] += r['success']
        a['llm_eligible_n'] += r['llm']['success_eligible']
        a['assignment_match_n'] += r['llm']['assignment_match']
        a['conflict_n'] += r['llm']['conflict']
        a['cooperate_ok_n'] += r['llm']['cooperate_ok']
        a['hallucination_n'] += r['llm']['hallucination_n']
        a['executed_n'] += r['executed']
        a['carry_success_n'] += r['carry_success'] is True
        a['tokens'] += sum(r['llm']['tokens'].values())
        a['usd'] = None if a['usd'] is None or r['llm']['usd'] is None else round(a['usd'] + r['llm']['usd'], 6)
        stage = r['failure_stage'] or 'success'
        a['failure_stage'][stage] = a['failure_stage'].get(stage, 0) + 1
    for a in by.values():
        a['report'] = f"{a['success_n']}/{a['N']}"
    return sorted(by.values(), key=lambda a: (a['arm'], a['condition']))
