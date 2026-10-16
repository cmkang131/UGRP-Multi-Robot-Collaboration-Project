"""Reproduce the offline exit matrix and enumerate scheduler return/exception sites.

Run from repository root. Produces small local regression records only.
"""
import ast
import dis
import hashlib
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.modules['mujoco'] = None

def forbidden(*args, **kwargs):
    raise AssertionError('model/network forbidden in review4 audit')
socket.socket.connect = socket.socket.connect_ex = forbidden

from harness import zone_event_scheduler as core
from tests.test_zone_study_multiturn_exits import EXIT_CASES, EXTRA_CASES, MESSAGE_STATES, run_exit_cell, API_PROBES, run_pending_api_probe

OUT = Path(__file__).parent
FILES = ('harness/zone_event_scheduler.py', 'harness/zone_study_decisions.py')
ABS = {str(ROOT / name): name for name in FILES}
rows = []
tasks = [(case, state) for case in EXIT_CASES + EXTRA_CASES for state in MESSAGE_STATES]
tasks += [(name, 'api_probe') for name in API_PROBES]
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
        if not isinstance(cls, ast.ClassDef) or cls.name not in ('EventScheduler', 'DecisionScheduler'):
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef):
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
        if not isinstance(cls, ast.ClassDef) or cls.name not in ('EventScheduler', 'DecisionScheduler'):
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef) or not falls_through(fn.body):
                continue
            explicit = {n.lineno for n in ast.walk(fn) if isinstance(n, ast.Return)}
            matches = [i for i, r in enumerate(rows) if any(
                f == name and method == fn.name and line not in explicit
                for f, method, line in r['normal_returns'])]
            inventory.append({'file': name, 'function': fn.name, 'line': fn.end_lineno,
                'kind': 'ImplicitReturn', 'code': 'fall-through return None', 'executed_by': matches})

mutations = []
original = core.EventScheduler._restore_inputs
core.EventScheduler._restore_inputs = lambda *args: None
try:
    try:
        run_exit_cell(next(c for c in EXTRA_CASES if c.path == 'snapshot_error'), 'just_received')
    except AssertionError:
        mutations.append({'mutation': 'remove generic input refund', 'detected': True})
    else:
        mutations.append({'mutation': 'remove generic input refund', 'detected': False})
finally:
    core.EventScheduler._restore_inputs = original

from tests.test_zone_study_multiturn_generated import generated
original = core.EventScheduler.calls_spent
core.EventScheduler.calls_spent = lambda self: self._calls_started >= self.max_calls_total
try:
    try:
        from harness.zone_study_decisions import DecisionScheduler
        generated(0, DecisionScheduler)
    except AssertionError:
        mutations.append({'mutation': 'restore nonrefundable call-ID cap', 'detected': True})
    else:
        mutations.append({'mutation': 'restore nonrefundable call-ID cap', 'detected': False})
finally:
    core.EventScheduler.calls_spent = original

record = {'schema': 'ugrp.pr245.review4.offline-audit.v1', 'model_calls': 0, 'physics_steps': 0,
          'sources_sha256': {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in FILES},
          'rows': rows, 'branch_inventory': inventory, 'mutations': mutations}
(OUT / 'review4-exit-traces.json').write_text(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
lines = ['# 검토 4 종료·반환·예외 추적', '',
         '가짜 전송·가짜 시계만 사용했다. 모델 호출·물리 step 0회. 상세 실행·ledger는 `review4-exit-traces.json`.', '',
         '## 종료 표', '', '| 경로 | 메시지 상태 | 재개 시작 시각 | 처리 | 예외 |', '|---|---|---|---|---|']
for row in rows:
    starts = ', '.join(str(c['at']) for c in row['calls']) or '없음'
    lines.append(f"| {row['path']} | {row['message_state']} | {starts} | {row['handling']} | {row['exception'] or '-'} |")
lines += ['', '## 반환·raise·except 전수 목록 (암시적 정상 반환 포함)', '',
          '각 행은 AST에서 직접 추출했다. 실행 근거 없음은 미실행이며 통과로 세지 않는다. '
          '생성자·입력 검증·읽기 API는 호출 정산 경로와 구분한다.', '',
          '| 위치 | 함수 | 분기 | 종료 표 실행 근거(대표) |', '|---|---|---|---|']
for branch in inventory:
    evidence = ', '.join(f"{rows[i]['path']}/{rows[i]['message_state']}"
                         for i in branch['executed_by'][:2]) or '종료 표 범위 밖'
    lines.append(f"| {branch['file']}:{branch['line']} | {branch['function']} | {branch['kind']} | {evidence} |")
(OUT / 'review4-exit-table.md').write_text('\n'.join(lines) + '\n')
assert all(b['executed_by'] for b in inventory), 'untraced return/exception site'
assert all(m['detected'] for m in mutations), 'surviving fault mutation'
print(json.dumps({'cells': len(rows), 'inventory': len(inventory),
                  'executed_sites': sum(bool(b['executed_by']) for b in inventory), 'mutations': mutations}))
for b in inventory:
    if not b['executed_by']:
        print(b['function'], b['line'], b['code'])
