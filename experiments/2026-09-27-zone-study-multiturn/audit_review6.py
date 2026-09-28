"""Reproduce the offline exit matrix and enumerate scheduler return/exception sites.

Run from repository root. Produces small local regression records only.
"""
import ast
import gzip
import dis
import hashlib
import json
from pathlib import Path
import socket
import threading
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.modules['mujoco'] = None

def forbidden(*args, **kwargs):
    raise AssertionError('model/network forbidden in review6 audit')
socket.socket.connect = socket.socket.connect_ex = forbidden

from harness import zone_event_scheduler as core
from tests.test_zone_study_multiturn_exits import EXIT_CASES, EXTRA_CASES, MESSAGE_STATES, run_exit_cell, API_PROBES, run_pending_api_probe

from tests.test_zone_study_multiturn_review5 import (
    CHAIN_CASES, BUDGET_KINDS, SETTLEMENTS, run_chain, run_budget_chain)

from tests.test_zone_study_multiturn_review6 import run_review6
def coalesced_probe():
    from tests.test_zone_study_multiturn_review6 import test_coalesced_fresh_message_has_its_own_retry_allowance
    original = core.EventScheduler.__init__
    captured = []
    def capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        captured.append(self)
    core.EventScheduler.__init__ = capture
    try:
        test_coalesced_fresh_message_has_its_own_retry_allowance()
    finally:
        core.EventScheduler.__init__ = original
    s = captured[0]
    return {'path': 'coalesced_fresh_root', 'message_state': 'old_retry_and_fresh',
            'handling': 'retry_fresh_only', 'exception': None,
            'calls': [{'at': r['started_sim_s'], 'id': cid, 'retry_of': r['retry_of']}
                      for cid, r in s.ledger.items()],
            'events': s.events, 'ledger': s.ledger, 'budget': s.budget.to_dict(),
            'roots': [{'cause': r.cause, 'call_id': r.call_id, 'retries': n} for r, n in s._retries.items()],
            'inputs': [{'tags': e.tags, 'claimed_by': e.claimed_by, 'active': e.active} for e in s.event_inputs]}


def account_probes():
    # Exercise the account's explicit preconditions without threads sending or
    # running physics. Only the rejected reservation is called off-owner.
    budget = core.AttemptBudget(total=1)
    errors = []
    for operation in (lambda: budget.reserve('r1', 0),
                      lambda: budget.commit('r1', reserved=0, actual=1)):
        try:
            operation()
        except (ValueError, AssertionError) as exc:
            errors.append(type(exc).__name__)
    def wrong_owner():
        try:
            budget.reserve('r1')
        except RuntimeError as exc:
            errors.append(type(exc).__name__)
    # sys.settrace is thread-local: explicitly install the same trace only for
    # this owned, immediately joined contract probe.
    threading.settrace(sys.gettrace())
    t = threading.Thread(target=wrong_owner)
    t.start()
    t.join()
    threading.settrace(None)
    assert errors == ['ValueError', 'AssertionError', 'RuntimeError']
    return {'path': 'account_preconditions', 'message_state': 'none', 'handling': 'reject',
            'exception': ','.join(errors), 'calls': [], 'events': [], 'budget': budget.to_dict()}


def reask_cap_probe():
    from tests.test_zone_study_multiturn import make_trial, advance
    trial, clock, links, requests = make_trial('no_comm', first='continue', send=False,
        policy=core.CallPolicy(max_calls_per_actor=1), horizon=8.)
    advance(trial, clock, links, 8.)
    result = trial.finish(8.)
    assert result.end_reason == 'budget_exhausted' and trial.quiescent()
    return {'path': 'reask_confirmed_call_cap', 'message_state': 'no_comm', 'handling': 'budget_exhausted',
            'exception': None, 'calls': [{'at': r['started_sim_s']} for r in trial.scheduler.ledger.values()],
            'events': trial.scheduler.events, 'ledger': trial.scheduler.ledger,
            'budget': trial.scheduler.budget.to_dict()}


OUT = Path(__file__).parent
FILES = ('harness/zone_event_scheduler.py', 'harness/zone_study_decisions.py', 'harness/zone_study_integration.py')
ABS = {str(ROOT / name): name for name in FILES}
rows = []
tasks = [(case, state) for case in EXIT_CASES + EXTRA_CASES for state in MESSAGE_STATES]
tasks += [(name, 'api_probe') for name in API_PROBES]
tasks += [(case, condition) for case in CHAIN_CASES
          for condition in ('peer_ko', 'leader_ko', 'structured')]
tasks += [('reservation_' + kind, settlement) for kind in BUDGET_KINDS for settlement in SETTLEMENTS]
tasks += [(case, condition) for case in ('separate_roots', 'timer_reservation', 'refund_horizon')
          for condition in ('no_comm', 'peer_ko', 'leader_ko', 'structured')]
tasks += [('coalesced_fresh_root', 'old_retry_and_fresh'), ('account_preconditions', 'none'), ('reask_confirmed_call_cap', 'no_comm')]
for case, state in tasks:
    hits = {name: set() for name in FILES}
    exceptions = []
    returns = set()
    def trace(frame, event, arg):
        name = ABS.get(frame.f_code.co_filename)
        if name:
            if event == 'line':
                hits[name].add(frame.f_lineno)
            elif event == 'return' and dis.opname[frame.f_code.co_code[frame.f_lasti]].startswith('RETURN'):
                returns.add((name, frame.f_code.co_name, frame.f_lineno))
            elif event == 'exception':
                exceptions.append([name, frame.f_lineno, type(arg[1]).__name__])
            return trace
        return None
    sys.settrace(trace)
    try:
        if case == 'coalesced_fresh_root':
            row = coalesced_probe()
        elif case == 'account_preconditions':
            row = account_probes()
        elif case == 'reask_confirmed_call_cap':
            row = reask_cap_probe()
        elif case in ('separate_roots', 'timer_reservation', 'refund_horizon'):
            row = run_review6(case, state, at=5.2 if case == 'timer_reservation' else 5.5)[2]
        elif isinstance(case, str) and case in CHAIN_CASES:
            row = run_chain(case, state)[2]
        elif isinstance(case, str) and case.startswith('reservation_'):
            row = run_budget_chain(case.removeprefix('reservation_'), state)
        else:
            row = run_pending_api_probe(case) if state == 'api_probe' else run_exit_cell(case, state)
    finally:
        sys.settrace(None)
    row['omitted_observation_ticks'] = sum(e.get('kind') == 'observe' for e in row['events'])
    row['events'] = [e for e in row['events'] if e.get('kind') != 'observe']
    row['executed_lines'] = {k: sorted(v) for k, v in hits.items()}
    row['exception_trace'] = exceptions
    row['normal_returns'] = sorted(returns)
    rows.append(row)

inventory = []
for name in FILES:
    source = (ROOT / name).read_text()
    tree = ast.parse(source)
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or cls.name not in ('EventScheduler', 'DecisionScheduler', 'AttemptBudget', 'IntegratedTrial'):
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            if cls.name == 'IntegratedTrial' and fn.name not in ('decision_budget_spent', 'decision_end_reason', '_arm_reask', 'finish'):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, (ast.Return, ast.Raise, ast.ExceptHandler)):
                    continue
                line = node.body[0].lineno if isinstance(node, ast.ExceptHandler) else node.lineno
                matches = [i for i, r in enumerate(rows)
                           if line in r['executed_lines'][name]]
                inventory.append({'file': name, 'function': fn.name, 'line': node.lineno,
                    'evidence_line': line, 'kind': type(node).__name__,
                    'code': source.splitlines()[node.lineno - 1].strip(), 'executed_by': matches})

def falls_through(block):
    last = block[-1]
    if isinstance(last, (ast.Return, ast.Raise)):
        return False
    if isinstance(last, ast.If):
        return not last.orelse or falls_through(last.body) or falls_through(last.orelse)
    if isinstance(last, ast.Try):
        if last.finalbody and not falls_through(last.finalbody):
            return False
        normal = falls_through(last.body) and (not last.orelse or falls_through(last.orelse))
        return normal or any(falls_through(handler.body) for handler in last.handlers)
    return True


# Include normal fall-through returns too; exception-unwind return events are
# excluded above by the actual bytecode opcode (they did not return normally).
for name in FILES:
    tree = ast.parse((ROOT / name).read_text())
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef) or cls.name not in ('EventScheduler', 'DecisionScheduler', 'AttemptBudget', 'IntegratedTrial'):
            continue
        for fn in cls.body:
            if cls.name == 'IntegratedTrial' and getattr(fn, 'name', None) not in ('decision_budget_spent', 'decision_end_reason', '_arm_reask', 'finish'):
                continue
            if not isinstance(fn, ast.FunctionDef) or not falls_through(fn.body):
                continue
            explicit = {n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return)}
            matches = [i for i, r in enumerate(rows) if any(
                f == name and method == fn.name and line not in explicit
                for f, method, line in r['normal_returns'])]
            inventory.append({'file': name, 'function': fn.name, 'line': fn.end_lineno,
                'kind': 'ImplicitReturn', 'code': 'fall-through return None', 'executed_by': matches})


record = {'schema': 'ugrp.pr245.review6.offline-audit.v1', 'model_calls': 0, 'physics_steps': 0,
          'sources_sha256': {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in FILES},
          'rows': rows, 'branch_inventory': inventory}
# Compact regression record; originals and old audit snapshots stay untouched.
raw = json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode()
(OUT / 'review6-exit-traces.json.gz').write_bytes(gzip.compress(raw, mtime=0))
lines = ['# 검토 6 종료·반환·예외 추적', '',
         '가짜 전송·시계만 사용. 모델 호출·물리 step 0회. 상세 기록은 review6-exit-traces.json.gz.', '',
         '검토 5의 179행을 다시 실행하고 검토 6의 세 연쇄를 4조건, 회계/재질문 계약 2행과 합쳐진 새 사건 계보 1행에 추가했다. 과거 파일은 보존했다.', '',
         '## 종료 표', '', '| 경로 | 조건/상태 | 호출 시작 시각 | 종료 사유/처리 | 예외 |',
         '|---|---|---|---|---|']
for row in rows:
    starts = ', '.join(str(c['at']) for c in row['calls']) or '없음'
    lines.append(f"| {row['path']} | {row['message_state']} | {starts} | {row.get('end_reason', row['handling'])} | {row['exception'] or '-'} |")
lines += ['', '## 반환·raise·except 목록 (암시적 정상 반환 포함)', '',
          '코어 스케줄러·회계 객체·DecisionScheduler와 통합의 재질문/종료 판정을 AST로 열거했다. '
          '실행 근거 없는 지점은 명시하며, 이 표는 모든 boolean 조합의 증명이 아니다.', '',
          '| 위치 | 함수 | 분기 | 실행 근거 |', '|---|---|---|---|']
for branch in inventory:
    evidence = ', '.join(f"{rows[i]['path']}/{rows[i]['message_state']}" for i in branch['executed_by'][:2]) or '미실행'
    lines.append(f"| {branch['file']}:{branch['line']} | {branch['function']} | {branch['kind']} | {evidence} |")
(OUT / 'review6-exit-table.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'cells': len(rows), 'inventory': len(inventory),
                  'executed_sites': sum(bool(b['executed_by']) for b in inventory)}))
for b in inventory:
    if not b['executed_by']:
        print(b['function'], b['line'], b['code'])

assert all(b['executed_by'] for b in inventory), 'untraced return/exception site'
