#!/usr/bin/env python3
"""Result ledger -> Markdown tables + matplotlib figures (report automation, eval-only).

Tracks (one subcommand each; usage in docs/report_auto.md):

  tournament      (a) single-robot ACT release tournament A
                      (CARRY_TOURNAMENT_A_PREREG_DRAFT.json, ledger scripts/act18_tournament_ledger.py,
                       dsh/act18-carry-cand-1)
  pairact-p1      (a') pair carry P1 MJWarp teacher gate tournament / confirmation
                      (PAIRACT_P1_PREREG_DRAFT.json, ledger p1_ledger.py, dsh/pairact-p0-diag)
  pairact-collect (b1) pair carry teacher collection, label A
                      (scripts/run_pairact_collect.py report -> report.json, dsh/pairact-carry-r1-v2)
  pairact-eval    (b2) P5 same-seed evaluation, label C: student n/20 vs teacher n/20 + funnel
                      (PAIRACT_R1_EVAL_PREREG_DRAFT.json, rows scripts/pairact_p5_rows.py,
                       dsh/pairact-p2-carrypath-r-c2)
  l1lite          (c) L1-lite, n/6 per condition (scripts/analyze_l1lite.py analysis, dsh/l1lite-alloc)
  e2e             (d) minimal single-robot-per-slot E2E (harness/e2e_min_eval.recount_run reports)

Every subcommand:
  * hashes every input file (sha256) into the output,
  * compares the pre-registration file sha256 against the sha256 recorded in the ledger/report
    (and against --expect-prereg-sha when given) and refuses (exit 2) on any mismatch,
  * refuses a DRAFT / unregistered prereg unless --allow-draft; with --allow-draft every output is
    labelled "초안 기준, 판정 아님" and no verdict is printed,
  * keeps the registered denominator (missing runs are listed, never dropped from N),
  * writes <out>/report.md, <out>/report.json and <out>/fig-*.png (Wilson 95% CI error bars).

Nothing here runs physics or touches a run root; it only reads files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

SCHEMA = 'ugrp.report_auto.v1'
FINAL_STATUSES = ('FROZEN', 'REGISTERED')
CHECK = '[확인 필요]'


class ReportError(Exception):
    """Refusal: the inputs cannot be reported under this pre-registration."""


# ------------------------------------------------------------------ basics

def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Inputs:
    """Reads files and remembers their sha256 (recorded in every output)."""

    def __init__(self):
        self.files = {}

    def raw(self, path):
        path = Path(path)
        data = path.read_bytes()
        self.files[str(path)] = hashlib.sha256(data).hexdigest()
        return data

    def json(self, path):
        return json.loads(self.raw(path))

    def jsonl(self, path):
        rows = []
        for i, line in enumerate(self.raw(path).decode().splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ReportError(f'{path}:{i}: not JSON ({e})') from None
        return rows


def wilson(n, N, z=1.959963984540054):
    """Wilson score 95% interval for n successes of N; (None, None) when N == 0."""
    if not N:
        return None, None
    if not 0 <= n <= N:
        raise ValueError(f'n={n} outside 0..N={N}')
    p = n / N
    d = 1 + z * z / N
    c = (p + z * z / (2 * N)) / d
    h = z * math.sqrt(p * (1 - p) / N + z * z / (4 * N * N)) / d
    return max(0.0, c - h), min(1.0, c + h)


def nn(n, N):
    """'n/N (p%, 95% CI lo–hi%)' — the only rate format used in the tables."""
    if not N:
        return f'{n}/{N}'
    lo, hi = wilson(n, N)
    return f'{n}/{N} ({100 * n / N:.0f}%, CI {100 * lo:.0f}–{100 * hi:.0f}%)'


def md_table(headers, rows):
    out = ['| ' + ' | '.join(map(str, headers)) + ' |', '|' + '---|' * len(headers)]
    out += ['| ' + ' | '.join('' if v is None else str(v) for v in r) + ' |' for r in rows]
    return '\n'.join(out)


def check_prereg(inputs, path, *, recorded_sha=None, expect_sha=None, allow_draft=False):
    """Pre-registration gate.  Returns dict(path, sha256, status, final)."""
    data = inputs.raw(path)
    sha = hashlib.sha256(data).hexdigest()
    if expect_sha and expect_sha != sha:
        raise ReportError(f'prereg sha256 {sha} != --expect-prereg-sha {expect_sha}')
    for label, value in (recorded_sha or {}).items():
        if value != sha:
            raise ReportError(f'{label}: recorded prereg sha256 {value} != prereg file sha256 {sha} ({path})')
    status = prereg_status(data)
    final = isinstance(status, str) and status.split()[0].rstrip('.:-') in FINAL_STATUSES
    if not final and not allow_draft:
        raise ReportError(f'prereg status {status!r} is not {"/".join(FINAL_STATUSES)}; '
                          'pass --allow-draft for a labelled draft table (no verdict)')
    return dict(path=str(path), sha256=sha, status=status, final=final)


MD_STATUS = (re.compile(r'상태:\s*\**\s*([A-Z][A-Z_]+)'), re.compile(r'(?im)^\W*status\W*:?\s*\**\s*([A-Z][A-Z_]+)'))


def prereg_status(data):
    """JSON 'status', else the first Markdown '상태: **X**' / 'status: X' (PREREG_L1LITE.md, PREREG_DRAFT.md)."""
    try:
        value = json.loads(data)
        return value.get('status') if isinstance(value, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    try:
        text = data.decode()
    except UnicodeDecodeError:
        return None
    for pat in MD_STATUS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def header_sha(rows, name):
    """prereg sha256 from the ledger header row(s); every header must agree."""
    heads = [r for r in rows if r.get('type') == 'header']
    if not heads:
        raise ReportError(f'{name}: no header row with prereg_sha256')
    shas = {h.get('prereg_sha256') for h in heads}
    if len(shas) != 1 or None in shas:
        raise ReportError(f'{name}: header rows disagree or lack prereg_sha256: {sorted(map(str, shas))}')
    return heads[0], shas.pop()


def load_report_rows(inputs, rows, base, *, host_error_without_report=False):
    """Run rows carry either an embedded 'report' or a 'report_path' (relative to the rows file).
    With host_error_without_report, a status HOST_ERROR row may have neither (report None = failure)."""
    out = []
    for r in rows:
        if r.get('type') != 'run':
            continue
        r = dict(r)
        if (host_error_without_report and r.get('status') == 'HOST_ERROR'
                and r.get('report') is None and not r.get('report_path')):
            r['report'] = None
        elif r.get('report') is None:
            if not r.get('report_path'):
                raise ReportError(f'run row without report/report_path: {r}')
            p = Path(r['report_path'])
            r['report'] = inputs.json(p if p.is_absolute() else Path(base) / p)
        out.append(r)
    return out


# ------------------------------------------------------------------ figures

def bar_figure(path, title, groups, series, ylabel='성공 비율 (Wilson 95% CI)'):
    """groups: x labels; series: [(label, [(n, N), ...])] aligned with groups."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    for fam in ('NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR', 'UnDotum'):
        from matplotlib import font_manager
        if any(f.name == fam for f in font_manager.fontManager.ttflist):
            plt.rcParams['font.family'] = fam
            break
    plt.rcParams['axes.unicode_minus'] = False
    k = len(series)
    width = 0.8 / max(k, 1)
    fig, ax = plt.subplots(figsize=(min(11.0, max(5.0, 0.7 * len(groups) * max(k, 1) + 1.5)), 3.8))
    for j, (label, vals) in enumerate(series):
        xs, ys, lo, hi, texts = [], [], [], [], []
        for i, (n, N) in enumerate(vals):
            x = i + (j - (k - 1) / 2) * width
            if not N:
                ax.text(x, 0.02, 'N=0', ha='center', fontsize=7)
                continue
            p = n / N
            a, b = wilson(n, N)
            xs.append(x), ys.append(p), lo.append(max(0.0, p - a)), hi.append(max(0.0, b - p)), texts.append(f'{n}/{N}')
        ax.bar(xs, ys, width * 0.92, yerr=[lo, hi], capsize=3, label=label)
        for x, y, t in zip(xs, ys, texts):
            ax.text(x, min(y + 0.04, 1.02), t, ha='center', fontsize=7)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels(groups, fontsize=8)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.set_title(title, fontsize=9)
    if k > 1:
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path)


# ------------------------------------------------------------------ (a) tournament

TOURNAMENT_REQUIRED = ('arm', 'rep', 'cohort', 'seed', 'status')


def tournament(args, inputs):
    """Ledger written by scripts/act18_tournament_ledger.py (dsh/act18-carry-cand-1) from the run root:
    header {"type":"header","prereg_sha256"}; one row per world-run
    {"type":"world_run","arm","rep","cohort":"HO4"|"TRAIN4","seed","status":"complete"|"HOST_ERROR",
     "release_success","physical_success","drop_detected","cap_end"  (summary student_scores),
     "G" (act18_c2c_analyze definition), "early_open_grasp","open_issued","release_done"}.
    """
    rows = inputs.jsonl(args.ledger)
    _, rec = header_sha(rows, args.ledger)
    pre = check_prereg(inputs, args.prereg, recorded_sha={'ledger header': rec},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    prereg = json.loads(Path(args.prereg).read_text())
    arms = list(prereg['arms'])
    base = 'A-base' if 'A-base' in arms else arms[0]
    cohorts = {k: [int(s) for s in v] for k, v in prereg['seeds'].items() if isinstance(v, list)}
    seed_cohort = {s: c for c, ss in cohorts.items() for s in ss}
    N = int(prereg['metrics']['primary']['denominator'])
    n_rep = int(prereg['replicates']['N_per_arm'])
    min_gain = 3 if '+3' in prereg['metrics']['minimum_improvement'] else None
    safety = -2
    if min_gain is None:
        raise ReportError('minimum_improvement is not "+3/24"; update the parser before reporting')
    world = [r for r in rows if r.get('type') == 'world_run']
    seen = set()
    for r in world:
        miss = [k for k in TOURNAMENT_REQUIRED if k not in r]
        if miss:
            raise ReportError(f'world_run row missing {miss}: {r}')
        if r['arm'] not in arms:
            raise ReportError(f'arm {r["arm"]!r} not in prereg arms {arms}')
        if r['status'] not in ('complete', 'HOST_ERROR'):
            raise ReportError(f'world_run status {r["status"]!r} is not complete/HOST_ERROR: {r}')
        if seed_cohort.get(int(r['seed'])) != r['cohort']:
            raise ReportError(f'seed {r["seed"]} is not a registered {r["cohort"]} seed')
        if not 1 <= int(r['rep']) <= n_rep:
            raise ReportError(f'rep {r["rep"]} outside 1..{n_rep}')
        key = (r['arm'], int(r['rep']), int(r['seed']))
        if key in seen:
            raise ReportError(f'duplicate world-run {key}')
        seen.add(key)
    expected = {(a, rep, s) for a in arms for rep in range(1, n_rep + 1) for s in seed_cohort}
    if len(expected) != N * len(arms):
        raise ReportError(f'prereg arms x reps x seeds = {len(expected)} != denominator {N} per arm')
    missing = sorted(expected - seen)

    def ok(r):
        return r['status'] == 'complete' and r.get('release_success') is True and r.get('physical_success') is True

    def cnt(a, pred, cohort=None):
        return sum(1 for r in world if r['arm'] == a and (cohort is None or r['cohort'] == cohort) and pred(r))

    stats = {}
    for a in arms:
        stats[a] = dict(
            primary=cnt(a, ok), G=cnt(a, lambda r: r['status'] == 'complete' and r.get('G') is True),
            early_open=cnt(a, lambda r: r.get('early_open_grasp') is True),
            drops=cnt(a, lambda r: r.get('drop_detected') is True),
            host_error=cnt(a, lambda r: r['status'] == 'HOST_ERROR'),
            missing=sum(1 for m in missing if m[0] == a),
            by_cohort={c: (cnt(a, ok, c), n_rep * len(ss)) for c, ss in cohorts.items()},
            descriptive={k: cnt(a, lambda r, k=k: r.get(k) is True) for k in ('open_issued', 'release_done', 'cap_end')})
    complete = not missing
    verdicts = {}
    for a in arms:
        s, b = stats[a], stats[base]
        if a == base:
            verdicts[a] = '기준'
        elif s['G'] - b['G'] < safety:
            verdicts[a] = f'탈락(안전: G {s["G"] - b["G"]:+d}/{N})'
        elif s['primary'] - b['primary'] < min_gain:
            verdicts[a] = f'최소 개선폭 미달({s["primary"] - b["primary"]:+d}/{N})'
        else:
            verdicts[a] = '후보'
    cands = [a for a in arms if verdicts[a] == '후보']
    winner = None
    if cands:
        best = max(stats[a]['primary'] for a in cands)
        top = [a for a in cands if stats[a]['primary'] == best]
        top = [a for a in top if stats[a]['early_open'] == 0] or top
        mind = min(stats[a]['drops'] for a in top)
        top = [a for a in top if stats[a]['drops'] == mind]
        winner = top[0] if len(top) == 1 else None
        for a in cands:
            verdicts[a] = '승자' if a == winner else ('동률(규칙으로 결정 불가)' if len(top) > 1 and a in top else '후보(패)')
    decide = pre['final'] and complete
    if not decide:
        verdicts = {a: '판정 보류' for a in arms}
        winner = None
    body = [md_table(
        ['arm', f'release 물리 성공 n/{N}', 'Δ vs 기준', f'G n/{N}', 'ΔG', '조기 open', '낙하', 'HOST_ERROR', '미실행', '판정'],
        [[a, nn(stats[a]['primary'], N), f'{stats[a]["primary"] - stats[base]["primary"]:+d}', nn(stats[a]['G'], N),
          f'{stats[a]["G"] - stats[base]["G"]:+d}', stats[a]['early_open'], stats[a]['drops'], stats[a]['host_error'],
          stats[a]['missing'], verdicts[a]] for a in arms])]
    body.append('코호트 분리(분모는 사전 등록 seed × 반복, 다른 실험과 합산 금지):')
    body.append(md_table(['arm'] + [f'{c} release 성공' for c in cohorts],
                         [[a] + [nn(*stats[a]['by_cohort'][c]) for c in cohorts] for a in arms]))
    body.append(md_table(['arm', 'open issued', 'release done', 'cap_end'],
                         [[a] + [stats[a]['descriptive'][k] for k in ('open_issued', 'release_done', 'cap_end')]
                          for a in arms]))
    host_rule = (f'사전 등록 host_error: HOST_ERROR는 재실행하지 않고 분모에 남겨 실패로 셉니다. 미실행 run은 판정 보류입니다.'
                 if 'host_error' in prereg else
                 f'HOST_ERROR와 미실행도 분모에 남깁니다(성공 아님) {CHECK}: 사전 등록에 host_error 규칙이 없습니다.')
    notes = [
        f'분모 규칙: arm당 {N} world-run 고정(8 seed × N={n_rep}). {host_rule}',
        f'채택 규칙: 기준 대비 +{min_gain}/{N} 이상, G가 기준 대비 {safety}/{N}보다 나쁘면 탈락, 동률은 조기 open 0 → 낙하 수.',
        'HO4는 진단용 보류 seed이고 TRAIN4는 적합 진단입니다. 승격 관문이 아닙니다.',
        '확인 run(미사용 seed 4 × N=2)은 seed 목록이 [확인 필요]라 이 표에 없습니다.',
    ]
    if missing:
        notes.append('미실행 world-run: ' + ', '.join(f'{a}/rep{r}/{s}' for a, r, s in missing[:24])
                     + (' …' if len(missing) > 24 else '') + ' → 판정 보류')
    fig = bar_figure(Path(args.out) / 'fig-tournament.png', f'Tournament A: release 물리 성공 (n/{N})', arms,
                     [('release 성공', [(stats[a]['primary'], N) for a in arms]), ('G', [(stats[a]['G'], N) for a in arms])])
    data = dict(arms=stats, verdicts=verdicts, winner=winner, complete=complete, missing=missing, base=base)
    return dict(track='tournament', title='(a) 단독 ACT release tournament A', prereg=pre, body=body,
                notes=notes, figures=[fig], data=data,
                headline=f'승자: {winner}' if winner else ('승자 없음' if decide else '판정 보류'))


# ------------------------------------------------------------------ (a') pairact P1 teacher gate tournament

P1_STATUSES = ('complete', 'HOST_ERROR', 'not_executed', 'excluded')
P1_TIE_ORDER = ('c3', 'c1', 'c2b')       # prereg adoption.winner: smaller behaviour change first
P1_FLAKE_WORLD = 27


def pairact_p1(args, inputs):
    """Ledger written by experiments/2026-10-21-pairact-p1/p1_ledger.py (dsh/pairact-p0-diag):
    header {"type":"header","prereg_sha256","stage","excluded_worlds","not_executed","arms"} + one row
    per arm x case index {"type":"world_run","arm","world","seed","status":complete|HOST_ERROR|
    not_executed|excluded,"success","cap_end"}.  Adoption: success >= ceil(0.95 x N_eff)."""
    rows = inputs.jsonl(args.ledger)
    head, rec = header_sha(rows, args.ledger)
    pre = check_prereg(inputs, args.prereg, recorded_sha={'ledger header': rec},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    prereg = json.loads(Path(args.prereg).read_text())
    stage = head.get('stage')
    if stage not in ('tournament', 'confirmation'):
        raise ReportError(f'ledger stage {stage!r} is not tournament/confirmation')
    ws = prereg['world_set'][stage]
    N = int(ws['nominal_denominator'])
    excl = prereg['static_exclusion'][stage]['excluded_worlds']
    if not isinstance(excl, list):
        raise ReportError(f'{stage}: prereg excluded_worlds not recorded (static check first)')
    excl, not_exec = set(excl), set(ws.get('not_executed') or [])
    if sorted(head.get('excluded_worlds') or []) != sorted(excl):
        raise ReportError(f'ledger excluded_worlds {head.get("excluded_worlds")} != prereg {sorted(excl)}')
    if 'c3 → c1 → c2b' not in prereg['adoption']['winner']:
        raise ReportError('prereg tie order is not "c3 → c1 → c2b"; update P1_TIE_ORDER before reporting')
    registered = [a['arm'] for a in prereg['arms_registered_order']]
    arms = list(head.get('arms') or registered)
    if stage == 'tournament' and arms != registered:
        raise ReportError(f'tournament arms {arms} != registered order {registered}')
    if stage == 'confirmation' and (len(arms) != 2 or arms[0] != 'r13' or arms[1] not in registered[1:]):
        raise ReportError(f'confirmation arms {arms} must be [r13, winner]')
    grid = {}
    for r in (r for r in rows if r.get('type') == 'world_run'):
        a, w, st = r.get('arm'), int(r['world']), r.get('status')
        if a not in arms:
            raise ReportError(f'arm {a!r} not in {arms}')
        if not 0 <= w < N or st not in P1_STATUSES:
            raise ReportError(f'world {w} / status {st!r} outside 0..{N - 1} / {P1_STATUSES}')
        if (st == 'excluded') != (w in excl) or (st == 'not_executed') != (w in not_exec):
            raise ReportError(f'{a} world {w}: status {st} disagrees with prereg exclusions/not_executed')
        if (a, w) in grid:
            raise ReportError(f'duplicate world-run {a}/{w} (HOST_ERROR is never re-run)')
        grid[(a, w)] = r
    n_eff = N - len(excl)
    need = math.ceil(round(.95 * n_eff, 9))
    stats, missing = {}, []
    for a in arms:
        mine = [grid[(a, w)] for w in range(N) if (a, w) in grid]
        if not mine:
            missing.append(a)
        elif len(mine) != N:
            raise ReportError(f'{a}: {len(mine)} rows != {N} registered indices (writer must cover every index)')
        ok = {r['world'] for r in mine if r['status'] == 'complete' and r.get('success') is True}
        stats[a] = dict(n=len(ok), started=bool(mine), adopt=bool(mine) and len(ok) >= need,
                        host_error=sum(r['status'] == 'HOST_ERROR' for r in mine),
                        cap_end=sum(r.get('cap_end') is True for r in mine),
                        not_executed=sum(r['status'] == 'not_executed' for r in mine),
                        failed=sorted(w for w in range(N) if w not in excl and w not in ok and mine),
                        flake_world=(P1_FLAKE_WORLD in ok) if mine else None)
    base = stats.get('r13')
    for a in arms:
        stats[a]['new_failures_vs_r13'] = (sorted(set(stats[a]['failed']) - set(base['failed']))
                                           if a != 'r13' and base and base['started'] and stats[a]['started'] else [])
    decide = pre['final'] and not missing
    verdicts, winner = {}, None
    if stage == 'tournament':
        cands = [a for a in arms if a != 'r13' and stats[a]['adopt']]
        if cands:
            best = max(stats[a]['n'] for a in cands)
            top = [a for a in cands if stats[a]['n'] == best]
            top = [a for a in top if stats[a]['flake_world']] or top
            winner = min(top, key=P1_TIE_ORDER.index)
        for a in arms:
            verdicts[a] = ('기준(재실행)' if a == 'r13' else '승자' if a == winner else
                           '채택 기준 통과(패)' if stats[a]['adopt'] else '채택 기준 미달')
        headline = f'승자: {winner}' if winner else '채택 없음(r13 유지)'
    else:
        w = arms[1]
        adopt = stats[w]['adopt'] and stats[w]['n'] >= stats['r13']['n']
        winner = w if adopt else None
        verdicts = {'r13': '기준(같은 world)', w: '채택' if adopt else
                    ('불채택(r13보다 적음, D5)' if stats[w]['adopt'] else '불채택(채택 기준 미달)')}
        headline = f'{w} 채택' if adopt else f'{w} 불채택(r13 유지)'
    if not decide:
        verdicts, winner, headline = {a: '판정 보류' for a in arms}, None, '판정 보류'
    body = [f'*{"tournament" if stage == "tournament" else "confirmation(새 world)"} — MJWarp teacher 관문(공동 파지 + 3초 유지).* '
            f'채택 = 통과 ≥ ceil(0.95 × N_eff) = {need}, N_eff = {N} − 규칙 A 제외 {len(excl)} = {n_eff}.',
            md_table(['arm', f'통과 n/{N}', f'통과 n/N_eff', '필요', 'HOST_ERROR', '미실행(world 15 등)', 'cap_end',
                      f'world {P1_FLAKE_WORLD}', 'r13 대비 새 실패', '판정'],
                     [[a, f'{stats[a]["n"]}/{N}' if stats[a]['started'] else '미실행',
                       nn(stats[a]['n'], n_eff) if stats[a]['started'] else '-', need, stats[a]['host_error'],
                       stats[a]['not_executed'], stats[a]['cap_end'],
                       {True: 'PASS', False: 'FAIL', None: '-'}[stats[a]['flake_world']],
                       ', '.join(map(str, stats[a]['new_failures_vs_r13'])) or '-', verdicts[a]] for a in arms]),
            '실패 world(N_eff 안):',
            md_table(['arm', '실패 world'], [[a, ', '.join(map(str, stats[a]['failed'])) or '-'] for a in arms])]
    notes = [f'제외 world(규칙 A, 실행 전 정적 검사): {sorted(excl) or "없음"}. 미실행 world {sorted(not_exec) or "없음"}은 N_eff 안의 실패입니다.',
             '사전 등록 host_error: HOST_ERROR는 재실행하지 않고 N_eff 안의 실패로 셉니다. 시작하지 않은 arm만 판정 보류입니다.',
             f'동률: world {P1_FLAKE_WORLD} 통과 arm → {" → ".join(P1_TIE_ORDER)} 순. world 27 단일 결과로 후보 효과를 주장하지 않습니다(flake_note).',
             'teacher 결과는 시연 생성 자격이며 학습 결과가 아닙니다. CPU 결과·다른 관문 회차와 합산하지 않습니다.']
    if stage == 'confirmation':
        notes.append('confirmation 채택(D5): winner ≥ 필요 수 그리고 같은 world에서 winner 통과 ≥ r13 통과.')
    if missing:
        notes.append(f'시작하지 않은 arm: {missing} → 판정 보류')
    fig = bar_figure(Path(args.out) / f'fig-pairact-p1-{stage}.png', f'P1 {stage}: 관문 통과 (n/N_eff={n_eff})', arms,
                     [('통과', [(stats[a]['n'], n_eff if stats[a]['started'] else 0) for a in arms])])
    return dict(track='pairact-p1', title=f"(a') 공동 운반 P1 teacher 관문 {stage}", prereg=pre, body=body, notes=notes,
                figures=[fig], data=dict(stage=stage, arms=stats, N=N, N_eff=n_eff, need=need, winner=winner,
                                         verdicts=verdicts, missing=missing), headline=headline)


# ------------------------------------------------------------------ (b1) pairact collect

def pairact_collect(args, inputs):
    rep = inputs.json(args.report)
    if rep.get('schema') != 'ugrp.pairact_r1.collect_report.v2':
        raise ReportError(f'report schema {rep.get("schema")!r} is not ugrp.pairact_r1.collect_report.v2')
    pre = check_prereg(inputs, args.prereg, recorded_sha={'report.json': rep.get('prereg_sha256')},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    body, figs = [], []
    if rep['mode'] == 'measurement':
        p = rep['pilot']
        body.append(f'*pilot(수율 측정, 시연 아님)*: 물리 성공 {nn(p["successes"], p["attempts"])}, 채택 후보 '
                    f'{nn(p["admitted"], p["attempts"])}, 환경 실패 {p["env_failures"]} 별도')
        bins, label = p['bins'], 'pilot'
    else:
        a, v = rep['A'], rep['validation']
        body.append('*표기 A — 교사 시연 수집(데이터 필터용, 학습 결과 아님).* 200은 채택 목표이며 분모가 아닙니다.')
        body.append(md_table(['구분', '물리 성공 S/N', '채택 A/N', '환경 실패(N 밖)', '기록 오류'],
                             [['A 전체', nn(a['successes'], a['attempts']), nn(a['admitted'], a['attempts']),
                               a['env_failures'], a['record_errors']]]
                             + [[f'A {ph}', nn(x['successes'], x['attempts']), nn(x['admitted'], x['attempts']),
                                 x['env_failures'], x['record_errors']] for ph, x in a['by_seed_phase'].items()]))
        body.append(f'*validation*(분모 20 고정, 환경 실패 별도): {v["text"]}')
        d = rep['decision']
        body.append(md_table(['학습 결정', 'train_stop', 'validation', '라벨'],
                             [[d['decision'], d['train_stop'], json.dumps(d['validation'], ensure_ascii=False)
                               if isinstance(d['validation'], dict) else d['validation'], '; '.join(d['labels']) or '-']]))
        bins, label = a['bins'], 'A'
    body.append(md_table(['구간', '거리 m', 'yaw', '물리 성공 S/N', '채택 A/N', '부족', '구간 제한', '설정 거절', '실패 세부'],
                         [[b['bin'], '–'.join(map(str, b['distance_m'])), b['yaw'], nn(b['successes'], b['attempts']),
                           nn(b['admitted'], b['attempts']), b['need'], 'Y' if b['bin_limited'] else '',
                           b['setup_rejections'], '; '.join(f'{k} {c}' for k, c in b['failure_subreasons'].items()) or '-']
                          for b in bins]))
    figs.append(bar_figure(Path(args.out) / 'fig-pairact-collect-bins.png', f'{label}: 구간별 물리 성공·채택 (S/N, A/N)',
                           [b['bin'] for b in bins],
                           [('물리 성공', [(b['successes'], b['attempts']) for b in bins]),
                            ('채택', [(b['admitted'], b['attempts']) for b in bins])]))
    notes = ['A·pilot·validation·B(교사 관문 n/40)·C(학생 n/20)는 더하거나 평균하지 않습니다(COLLECT_PREREG reporting.never_pool).',
             '분모 N은 행동 시도만 셉니다. 환경 실패(HOST_ERROR 등)는 N 밖에 따로 적습니다.',
             'report.json의 not_pooled_with: ' + ', '.join(rep.get('not_pooled_with', []))]
    return dict(track='pairact-collect', title='(b1) 공동 운반 교사 시연 수집 (표기 A)', prereg=pre, body=body,
                notes=notes, figures=figs, data=dict(mode=rep['mode'], run_state=rep.get('run_state')),
                headline=rep.get('A', rep.get('pilot', {})).get('text', ''))


# ------------------------------------------------------------------ (b2) pairact P5 eval

def pairact_eval(args, inputs):
    """Rows written by scripts/pairact_p5_rows.py (dsh/pairact-p2-carrypath-r-c2): header
    {"type":"header","prereg_sha256","excluded_seeds":[...],"static_check_sha256"}; one row per
    arm x seed x attempt {"type":"episode","arm":"student"|"teacher","seed","attempt":1|2,
    "status":"complete"|"HOST_ERROR","success","funnel":{stage: true|false|null},"termination",
    "student_gt_corrections","teacher_commands_issued_to_student"}.  null funnel stage = not recorded
    (teacher approach/alignment/READY/grasp); null GT/teacher counters = unverified, never a success.
    """
    rows = inputs.jsonl(args.rows)
    head, rec = header_sha(rows, args.rows)
    pre = check_prereg(inputs, args.prereg, recorded_sha={'rows header': rec},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    prereg = json.loads(Path(args.prereg).read_text())
    sd = prereg['seeds']
    seeds = list(range(int(sd['first']), int(sd['last']) + 1))
    if len(seeds) != int(sd['n']):
        raise ReportError('prereg seeds first..last != n')
    funnel = list(prereg['funnel']['order'])
    excluded = sorted(int(s) for s in head.get('excluded_seeds') or [])
    if any(s not in seeds for s in excluded):
        raise ReportError(f'excluded seeds {excluded} not all heldout seeds')
    if excluded and not head.get('static_check_sha256'):
        raise ReportError('excluded seeds without static_check_sha256 (rule A output must be hashed before the run)')
    eff = [s for s in seeds if s not in excluded]
    arms = [a['id'] for a in prereg['arms']]
    ep = [r for r in rows if r.get('type') == 'episode']
    final, host2, missing, gt_viol, gt_unknown = ({a: {} for a in arms}, {a: [] for a in arms},
                                                  {a: [] for a in arms}, [], [])
    for r in ep:
        if r.get('arm') not in arms:
            raise ReportError(f'arm {r.get("arm")!r} not in prereg {arms}')
        s = int(r['seed'])
        if s not in seeds:
            raise ReportError(f'seed {s} is not a heldout seed')
        if s in excluded:
            raise ReportError(f'seed {s} is excluded by rule A but has an episode row')
        if r.get('success') is True and r.get('funnel', {}).get(funnel[-1]) is not True:
            raise ReportError(f'{r["arm"]} seed {s}: success without funnel {funnel[-1]}')
        prev = final[r['arm']].get(s)
        if prev is not None and not (prev['status'] == 'HOST_ERROR' and int(r.get('attempt', 1)) == 2):
            raise ReportError(f'{r["arm"]} seed {s}: more than one counted episode (only one HOST_ERROR rerun allowed)')
        final[r['arm']][s] = r
    for a in arms:
        for s in eff:
            r = final[a].get(s)
            if r is None:
                missing[a].append(s)
            elif r['status'] == 'HOST_ERROR' and int(r.get('attempt', 1)) == 2:
                host2[a].append(s)

    def success(a, r):
        if r is None or r['status'] != 'complete' or r.get('success') is not True:
            return False
        if a == 'student':
            counters = (r.get('student_gt_corrections'), r.get('teacher_commands_issued_to_student'))
            if None in counters:
                gt_unknown.append(r['seed'])
                return False
            if any(counters):
                gt_viol.append(r['seed'])
                return False
        return True

    Ne = len(eff)
    res = {a: dict(n=sum(success(a, final[a].get(s)) for s in eff),
                   funnel={st: sum(1 for s in eff if (final[a].get(s) or {}).get('funnel', {}).get(st) is True)
                           for st in funnel},
                   unrecorded=[st for st in funnel
                               if all(((final[a].get(s) or {}).get('funnel') or {}).get(st) is None for s in eff)
                               and any(final[a].get(s) is not None and final[a][s]['status'] == 'complete' for s in eff)],
                   termination={}, missing=missing[a], host_error_twice=host2[a]) for a in arms}
    for a in arms:
        for s in eff:
            t = (final[a].get(s) or {}).get('termination') or ('미실행' if s in missing[a] else 'unknown')
            res[a]['termination'][t] = res[a]['termination'].get(t, 0) + 1
    for a in arms:
        rec = [st for st in funnel if st not in res[a]['unrecorded']]
        f = res[a]['funnel']
        if any(f[rec[i + 1]] > f[rec[i]] for i in range(len(rec) - 1)):
            res[a]['funnel_non_monotone'] = True
    body = ['*표기 C — 보류 seed 같은-seed 평가.* teacher는 기준선(GT 사용 허용)이며 학습 결과가 아닙니다.',
            md_table(['arm', f'성공 n/N_eff', '미실행', 'HOST_ERROR 2회(실패로 셈)'],
                     [[a, nn(res[a]['n'], Ne), len(res[a]['missing']), len(res[a]['host_error_twice'])] for a in arms]),
            '단계 퍼널(각 단계에 도달한 seed 수, 같은 seed 순서):',
            md_table(['단계'] + arms, [[st] + ['미기록' if st in res[a]['unrecorded'] else nn(res[a]['funnel'][st], Ne)
                                            for a in arms] for st in funnel]),
            md_table(['종료 사유'] + arms,
                     [[t] + [res[a]['termination'].get(t, 0) for a in arms]
                      for t in sorted({t for a in arms for t in res[a]['termination']})])]
    first_fail = []
    for s in eff:
        row = [s]
        for a in arms:
            r = final[a].get(s)
            if r is None:
                row.append('미실행')
                continue
            f = r.get('funnel', {})
            stop = next((st for st in funnel if f.get(st) is False
                         or (f.get(st) is None and st not in res[a]['unrecorded'])), None)
            if success(a, r):
                row.append('성공')
            elif stop is None:
                row.append('전 단계 도달, 성공 불인정(상태·보정 기록)')
            else:
                row.append(f'{stop}에서 멈춤')
        first_fail.append(row)
    body.append('seed별 첫 실패 단계:')
    body.append(md_table(['seed'] + arms, first_fail))
    notes = [f'분모 N_eff = {sd["n"]} − 규칙 A 정적 제외 {len(excluded)} = {Ne}. 제외 seed: {excluded or "없음"} '
             f'(static check sha256 {head.get("static_check_sha256") or "-"}). 대체 seed 없음, 두 arm 같은 seed.',
             'HOST_ERROR는 같은 seed 1회 재실행, 두 번째 HOST_ERROR는 실패로 세고 따로 적습니다. 사후 제외 금지.',
             '학생 성공은 student_gt_corrections == 0 이고 teacher 명령 0일 때만 셉니다.',
             'A(교사 시연 수집)·B(교사 관문 n/40)와 합산하지 않습니다.']
    if sorted(set(gt_viol)):
        notes.append(f'학생 GT/teacher 보정 기록이 있어 실패로 센 seed: {sorted(set(gt_viol))}')
    if sorted(set(gt_unknown)):
        notes.append(f'학생 GT/teacher 보정 기록(student_gt_corrections·teacher 명령)이 없어 성공으로 세지 않은 seed: '
                     f'{sorted(set(gt_unknown))}')
    for a in arms:
        if res[a]['unrecorded']:
            notes.append(f'{a}: {", ".join(res[a]["unrecorded"])} 단계는 runner가 기록하지 않아 "미기록"입니다(0이 아님).')
    for a in arms:
        if res[a].get('funnel_non_monotone'):
            notes.append(f'{a}: 퍼널이 단조 감소가 아님(행 기록 확인 필요)')
    figs = [bar_figure(Path(args.out) / 'fig-pairact-eval-funnel.png', f'C: 단계 퍼널 (n/{Ne}, 미기록 N=0)', funnel,
                       [(a, [(res[a]['funnel'][st], 0 if st in res[a]['unrecorded'] else Ne) for st in funnel])
                        for a in arms])]
    return dict(track='pairact-eval', title='(b2) 공동 운반 P5 같은-seed 평가 (표기 C)', prereg=pre, body=body,
                notes=notes, figures=figs, data=dict(arms=res, N_eff=Ne, excluded=excluded),
                headline=', '.join(f'{a} {res[a]["n"]}/{Ne}' for a in arms))


# ------------------------------------------------------------------ (c) L1-lite

L1_CONDITIONS = ('no_comm', 'structured', 'peer_en', 'leader_en')   # harness/e2ewarp_l1lite.py CONDITIONS
L1_TEST_SEEDS = (601, 602, 603, 604, 605, 606)                       # TABLE_SEEDS; DEV 701/702 never pooled
L1_DEV_SEEDS = (701, 702)
L1_ANALYSIS_SCHEMA = 'ugrp.e2ewarp.l1lite_analysis.v1'               # scripts/analyze_l1lite.py SCHEMA
#: analyze_l1lite.failure_reasons names -> success component (PREREG_L1LITE.md §4) for the component table
L1_COMPONENT_REASONS = (
    ('배정(allocation_ok)', ('ALLOCATION_NOT_OK',), 'L1LITE_'),
    ('서로 다른 슬롯', ('SLOTS_NOT_DISTINCT',), None),
    ('사적 제약 준수', ('CONSTRAINT_VIOLATION',), None),
    ('GT 도착 2/2', ('GT_UNMEASURED', 'GT_NOT_IN_CHOSEN_SLOT'), None),
    ('ARRIVED claim 2/2', ('CLAIM_INCOMPLETE',), None),
    ('로봇 간 접촉 0', ('CONTACT_UNAVAILABLE', 'ROBOT_CONTACT'), None),
    ('실행(NOT_RUN·HOST_ERROR·SHA·평가 없음)', ('NOT_RUN', 'HOST_ERROR', 'SHA_MISMATCH', 'EVAL_MISSING'), None))
L1_INCOMPLETE = 5          # PREREG §7-6: NOT_RUN + HOST_ERROR >= 5 of 24 -> "실행 불완전", no comparison


def l1lite(args, inputs):
    """Input = scripts/analyze_l1lite.py --out-json (dsh/l1lite-alloc), which already applies PREREG §7
    (24 planned cells, first attempt per cell, NOT_RUN/HOST_ERROR/SHA_MISMATCH/EVAL_MISSING = failure,
    smoke/dev rows excluded).  The prereg sha256 is the ledger key prereg_sha256 copied into the analysis;
    --ledger (optional) must hash to analysis.ledger.sha256."""
    an = inputs.json(args.analysis)
    if an.get('schema') != L1_ANALYSIS_SCHEMA:
        raise ReportError(f'analysis schema {an.get("schema")!r} is not {L1_ANALYSIS_SCHEMA}')
    if args.ledger:
        led = sha256_file(args.ledger)
        inputs.raw(args.ledger)
        if (an.get('ledger') or {}).get('sha256') != led:
            raise ReportError(f'ledger sha256 {led} != analysis.ledger.sha256 {(an.get("ledger") or {}).get("sha256")}')
    pre = check_prereg(inputs, args.prereg, recorded_sha={'analysis prereg_sha256 (ledger)': an.get('prereg_sha256')},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    table, cells = an['table'], an['cells']
    if list(table) != list(L1_CONDITIONS):
        raise ReportError(f'analysis conditions {list(table)} != {list(L1_CONDITIONS)}')
    keys = sorted((c['condition'], int(c['seed'])) for c in cells)
    if keys != sorted((c, s) for c in L1_CONDITIONS for s in L1_TEST_SEEDS):
        raise ReportError('analysis cells are not exactly 4 conditions x test seeds 601-606 (DEV seeds never pooled)')
    N = len(L1_TEST_SEEDS)
    stat = {}
    for c in L1_CONDITIONS:
        mine = sorted((x for x in cells if x['condition'] == c), key=lambda x: x['seed'])
        n = sum(1 for x in mine if x['success'] is True)
        if n != table[c]['n_success'] or table[c]['n_total'] != N:
            raise ReportError(f'{c}: table {table[c]["n_success"]}/{table[c]["n_total"]} disagrees with cells {n}/{N}')
        comp = {}
        for label, names, prefix in L1_COMPONENT_REASONS:
            comp[label] = sum(1 for x in mine if any(r in names or (prefix and r.startswith(prefix)) for r in x['reasons']))
        stat[c] = dict(n=n, per_seed={int(x['seed']): x['success'] is True for x in mine},
                       primary=dict(table[c]['primary_failure_reasons']), component_failures=comp,
                       host_error=table[c]['host_error'], not_run=table[c]['not_run'], aux=table[c]['aux'],
                       extra_attempts=sum(1 for x in mine if x.get('attempts', 0) > 1))
    lost = sum(stat[c]['host_error'] + stat[c]['not_run'] for c in L1_CONDITIONS)
    incomplete = lost >= L1_INCOMPLETE
    body = [md_table(['조건', f'성공 n/{N}', 'HOST_ERROR', '미실행', '1차 실패 사유'],
                     [[c, nn(stat[c]['n'], N), stat[c]['host_error'], stat[c]['not_run'],
                       '; '.join(f'{k} {v}' for k, v in sorted(stat[c]['primary'].items())) or '-'] for c in L1_CONDITIONS]),
            '성분별 실패 run 수(한 run이 여러 성분에 걸칠 수 있음):',
            md_table(['성분'] + list(L1_CONDITIONS),
                     [[label] + [f'{stat[c]["component_failures"][label]}/{N}' for c in L1_CONDITIONS]
                      for label, _, _ in L1_COMPONENT_REASONS]),
            md_table(['조건', '완료 SIM s(성공 중앙값)', '최소 차체 간격 m(최소/중앙)', '발화/run', '60 s 교착 run',
                      '환각(수/run)', 'LLM 호출/토큰/USD'],
                     [[c, a['completion_sim_s_success_median'], f'{a["min_body_gap_m_min"]} / {a["min_body_gap_m_median"]}',
                       a['utterances_per_run_mean'], a['deadlock_runs'], f'{a["hallucination_total"]} / {a["hallucination_runs"]}',
                       f'{a["llm_calls_total"]} / {a["llm_tokens_total"]} / {a["llm_cost_usd_total"]}']
                      for c, a in ((c, stat[c]['aux']) for c in L1_CONDITIONS)]),
            'seed × 조건(✓ 성공, ✗ 실패):',
            md_table(['seed'] + list(L1_CONDITIONS),
                     [[s] + ['✓' if stat[c]['per_seed'][s] else '✗' for c in L1_CONDITIONS] for s in L1_TEST_SEEDS])]
    notes = [f'분모: 조건당 {N}칸 고정(PREREG §7). NOT_RUN·HOST_ERROR·SHA_MISMATCH·EVAL_MISSING은 실패로 셉니다. '
             '재실행은 칸을 바꾸지 않습니다(첫 시도만, 추가 시도는 미합산).',
             '성공 = 배정 유효 + 서로 다른 슬롯 + 제약 준수 + GT 도착 2/2 + ARRIVED claim 2/2 + 로봇 간 접촉 0(채널 관측 시). '
             'L1-lite(이동·배정 과제, 집기 제외)이며 claim은 물리 성공 주장이 아닙니다.',
             'n=6/조건은 탐색 수준입니다. 통계 검정과 효과 유무 결론을 쓰지 않습니다. no_comm 상한 2/6은 설계상 기대값입니다.',
             f'frozen source SHA `{an.get("frozen_source_sha")}`; analysis 원장 sha256 `{(an.get("ledger") or {}).get("sha256")}`.']
    if incomplete:
        notes.insert(0, f'*실행 불완전*: NOT_RUN + HOST_ERROR = {lost}/24 ≥ {L1_INCOMPLETE}. 표만 보고하고 조건 비교 문장을 쓰지 않습니다.')
    if an.get('excluded'):
        notes.append('제외 행(합산 안 함): ' + ', '.join(f'o{r["order"]} {r["condition"]}/{r["seed"]}({r["reason"]})'
                                                     for r in an['excluded']))
    if an.get('protocol_deviations'):
        notes.append('프로토콜 편차: ' + '; '.join(f'{d["condition"]}/{d["seed"]} {",".join(d["items"])}'
                                              for d in an['protocol_deviations']))
    figs = [bar_figure(Path(args.out) / 'fig-l1lite.png', f'L1-lite: 조건별 성공 (n/{N})', list(L1_CONDITIONS),
                       [('성공', [(stat[c]['n'], N) for c in L1_CONDITIONS])])]
    head = ', '.join(f'{c} {stat[c]["n"]}/{N}' for c in L1_CONDITIONS)
    return dict(track='l1lite', title='(c) L1-lite 통신 조건 비교 (이동·배정 과제, 집기 제외)', prereg=pre, body=body,
                notes=notes, figures=figs, data=dict(conditions=stat, N=N, incomplete=incomplete),
                headline=head + (' (실행 불완전)' if incomplete else ''))


# ------------------------------------------------------------------ (d) E2E

E2E_PLANNED = {'E2E-1p': 3, 'E2E-2': 6}            # registered N, fixed (claude/e2e-min-runner PREREG_DRAFT.md §2; smoke excluded)
E2E_DISPLAY = {'E2E-1p': "E2E-1' 혼합", 'E2E-2': 'E2E-2 순수'}
E2E_STAGES = ('allocate', 'grasp', 'carry', 'release', 'done')


def e2e(args, inputs):
    """Rows (PREREG_DRAFT.md §10): header {"type":"header","prereg_sha256"} + {"type":"run","level","seed",
    "smoke":bool,"status":"complete"|"HOST_ERROR","report"|"report_path"} where report =
    harness.e2e_min_eval.recount_run(run_dir).  A HOST_ERROR row may omit the report (failure, reach 0)."""
    rows = inputs.jsonl(args.rows)
    _, rec = header_sha(rows, args.rows)
    pre = check_prereg(inputs, args.prereg, recorded_sha={'rows header': rec},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    planned = dict(E2E_PLANNED)
    runs = load_report_rows(inputs, rows, Path(args.rows).parent, host_error_without_report=True)
    by, smoke = {k: [] for k in planned}, []
    for r in runs:
        if r.get('status', 'complete') not in ('complete', 'HOST_ERROR'):
            raise ReportError(f'run status {r.get("status")!r} is not complete/HOST_ERROR')
        if r['level'] not in planned:
            raise ReportError(f'unknown level {r["level"]!r}')
        rep = r['report']
        if rep is None:
            (smoke if r.get('smoke') else by[r['level']]).append(r)
            continue
        if rep.get('schema') != 'ugrp.e2e_min.evaluation.v1':
            raise ReportError(f'report schema {rep.get("schema")!r}')
        if rep.get('level') != r['level'] or r['level'] not in planned:
            raise ReportError(f'level mismatch / unknown level: row {r["level"]!r} report {rep.get("level")!r}')
        if rep.get('substitutions_match_level') is not True:
            raise ReportError(f'{r["level"]} seed {r["seed"]}: e2e_substitutions do not match the level label')
        (smoke if r.get('smoke') else by[r['level']]).append(r)
    stat = {}
    for lv, rs in by.items():
        N = planned[lv]
        if len(rs) > N:
            raise ReportError(f'{lv}: {len(rs)} runs > registered N={N}')
        ev = [r for r in rs if r['report'] is not None and r.get('status', 'complete') != 'HOST_ERROR']
        reach = {s: sum(1 for r in ev for rb in r['report']['aux']['stage_reach'].values() if rb['reached'][s]) for s in E2E_STAGES}
        codes = {}
        for r in ev:
            for rb in r['report']['aux']['stage_reach'].values():
                if rb.get('fail_code'):
                    codes[rb['fail_code']] = codes.get(rb['fail_code'], 0) + 1
        subs = sorted({json.dumps(x, sort_keys=True) for r in ev for x in r['report']['e2e_substitutions']})
        stat[lv] = dict(n=sum(1 for r in ev if r['report']['success'] is True), N=N, ran=len(rs), reach=reach,
                        robot_N=2 * N, fail_codes=codes, substitutions=[json.loads(x) for x in subs],
                        host_error=len(rs) - len(ev),
                        drops=sum(1 for r in ev if r['report']['success_components'].get('drops_zero') is False))
    lv_list = list(planned)
    body = [md_table(['레벨', '표기', '성공 n/N', '실행/N', 'HOST_ERROR', '대체 단계', '낙하 run', 'FAIL 코드'],
                     [[lv, E2E_DISPLAY.get(lv, lv), nn(stat[lv]['n'], stat[lv]['N']), f'{stat[lv]["ran"]}/{stat[lv]["N"]}',
                       stat[lv]['host_error'],
                       '; '.join(f'{x["stage"]}←{x["by"]}' for x in stat[lv]['substitutions']) or '없음(순수)',
                       stat[lv]['drops'], '; '.join(f'{k} {v}' for k, v in stat[lv]['fail_codes'].items()) or '-']
                      for lv in lv_list]),
            '단계 도달(로봇 단위, 분모 = 2 × 등록 N):',
            md_table(['단계'] + lv_list, [[s] + [nn(stat[lv]['reach'][s], stat[lv]['robot_N']) for lv in lv_list]
                                         for s in E2E_STAGES])]
    if smoke:
        body.append(f'smoke {len(smoke)}회는 배관 확인용이라 위 n/N에 넣지 않습니다: '
                    + ', '.join(f'{r["level"]}/{r["seed"]} {"HOST_ERROR" if r["report"] is None else "성공" if r["report"]["success"] else "실패"}'
                               for r in smoke))
    notes = ["레벨끼리 합산하지 않습니다. E2E-1'은 내려놓기를 규칙 스크립트 release_open_v1로 대체한 혼합 결과입니다.",
             '실패와 HOST_ERROR도 분모에 넣습니다. HOST_ERROR는 재실행하지 않습니다(PREREG_DRAFT §3). 미실행은 실행/N 열로 보이며 판정 보류입니다.',
             "등록 N(고정, PREREG_DRAFT §2): E2E-1' 3, E2E-2 6. smoke는 N 밖입니다.",
             '성공 = 배정 유효 + GT 큐브가 배정 슬롯 안 + 낙하 0(측정됨) + 로봇 간 접촉 0 + claim 2/2. 미측정은 실패.']
    figs = [bar_figure(Path(args.out) / 'fig-e2e-stages.png', 'E2E: 단계 도달 (로봇 단위)', list(E2E_STAGES),
                       [(E2E_DISPLAY.get(lv, lv), [(stat[lv]['reach'][s], stat[lv]['robot_N']) for s in E2E_STAGES])
                        for lv in lv_list])]
    return dict(track='e2e', title='(d) 단독 최소 E2E', prereg=pre, body=body, notes=notes, figures=figs,
                data=dict(levels=stat), headline=', '.join(f'{E2E_DISPLAY.get(lv, lv)} {stat[lv]["n"]}/{stat[lv]["N"]}'
                                                           for lv in lv_list))


# ------------------------------------------------------------------ output

def render(result, inputs):
    pre = result['prereg']
    lines = [f'# {result["title"]}', '']
    if not pre['final']:
        lines += [f'> **초안 기준, 판정 아님.** 사전 등록 상태 `{pre["status"]}`(FROZEN/REGISTERED 아님). '
                  '이 표는 서술용이며 n/N 판정에 쓰지 않습니다.', '']
    lines += [f'요약: {result["headline"]}', '']
    for block in result['body']:
        lines += [block, '']
    lines += ['## 규칙과 주의', ''] + [f'- {n}' for n in result['notes']] + ['']
    figs = [f for f in result['figures'] if f]
    if figs:
        lines += ['## 그림', ''] + [f'![{Path(f).stem}]({Path(f).name})' for f in figs] + ['']
        lines += ['오차막대는 Wilson 95% 신뢰구간입니다.', '']
    else:
        lines += ['그림: 생성 안 됨(matplotlib 없음). 표만 유효합니다.', '']
    lines += ['## 입력', '', f'- 사전 등록: `{pre["path"]}` sha256 `{pre["sha256"]}` (상태 `{pre["status"]}`)']
    lines += [f'- `{p}` sha256 `{h}`' for p, h in sorted(inputs.files.items())]
    lines += ['', f'생성: `scripts/report_tables.py {result["track"]}` ({SCHEMA}). 원본 결과는 읽기만 했습니다.', '']
    return '\n'.join(lines)


TRACKS = {'tournament': tournament, 'pairact-p1': pairact_p1, 'pairact-collect': pairact_collect, 'pairact-eval': pairact_eval,
          'l1lite': l1lite, 'e2e': e2e}


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='track', required=True)

    def common(p):
        p.add_argument('--prereg', required=True, help='pre-registration file (sha256 compared with the ledger)')
        p.add_argument('--out', required=True, help='new output directory (report.md, report.json, fig-*.png)')
        p.add_argument('--expect-prereg-sha', help='committed prereg sha256; mismatch -> refuse')
        p.add_argument('--allow-draft', action='store_true', help='allow a DRAFT prereg (output labelled, no verdict)')
        return p
    common(sub.add_parser('tournament')).add_argument('--ledger', required=True)
    common(sub.add_parser('pairact-p1')).add_argument('--ledger', required=True, help='OUT_ROOT/p1-ledger.jsonl')
    common(sub.add_parser('pairact-collect')).add_argument('--report', required=True,
                                                           help='run root report.json (run_pairact_collect.py report)')
    common(sub.add_parser('pairact-eval')).add_argument('--rows', required=True)
    p = common(sub.add_parser('l1lite'))
    p.add_argument('--analysis', required=True, help='scripts/analyze_l1lite.py --out-json output')
    p.add_argument('--ledger', help='ledger.json; its sha256 must equal analysis.ledger.sha256')
    common(sub.add_parser('e2e')).add_argument('--rows', required=True)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    inputs = Inputs()
    try:
        result = TRACKS[args.track](args, inputs)
    except ReportError as e:
        print(f'REFUSED: {e}', file=sys.stderr)
        return 2
    (out / 'report.md').write_text(render(result, inputs))
    doc = dict(schema=SCHEMA, track=result['track'], prereg=result['prereg'], headline=result['headline'],
               inputs_sha256=inputs.files, figures=[Path(f).name for f in result['figures'] if f],
               data=result['data'], verdict_allowed=result['prereg']['final'])
    (out / 'report.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str) + '\n')
    print(f'{result["track"]}: {result["headline"]} -> {out / "report.md"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
