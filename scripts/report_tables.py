#!/usr/bin/env python3
"""Result ledger -> Markdown tables + matplotlib figures (report automation, eval-only).

Tracks (one subcommand each; usage in docs/report_auto.md):

  tournament      (a) single-robot ACT release tournament A
                      (CARRY_TOURNAMENT_A_PREREG_DRAFT.json, dsh/act18-carry-cand-1..3)
  pairact-collect (b1) pair carry teacher collection, label A
                      (scripts/run_pairact_collect.py report -> report.json, dsh/pairact-carry-r1-v2)
  pairact-eval    (b2) P5 same-seed evaluation, label C: student n/20 vs teacher n/20 + funnel
                      (PAIRACT_R1_EVAL_PREREG_DRAFT.json)
  l1lite          (c) L1-lite, n/6 per condition (harness/e2ewarp_l1lite_eval.evaluate_run reports)
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
    status = None
    try:
        status = json.loads(data).get('status')
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        status = None          # non-JSON prereg (e.g. PREREG_DRAFT.md): status unknown
    final = isinstance(status, str) and status.split()[0].rstrip('.:-') in FINAL_STATUSES
    if not final and not allow_draft:
        raise ReportError(f'prereg status {status!r} is not {"/".join(FINAL_STATUSES)}; '
                          'pass --allow-draft for a labelled draft table (no verdict)')
    return dict(path=str(path), sha256=sha, status=status, final=final)


def header_sha(rows, name):
    """prereg sha256 from the ledger header row(s); every header must agree."""
    heads = [r for r in rows if r.get('type') == 'header']
    if not heads:
        raise ReportError(f'{name}: no header row with prereg_sha256')
    shas = {h.get('prereg_sha256') for h in heads}
    if len(shas) != 1 or None in shas:
        raise ReportError(f'{name}: header rows disagree or lack prereg_sha256: {sorted(map(str, shas))}')
    return heads[0], shas.pop()


def load_report_rows(inputs, rows, base):
    """Run rows carry either an embedded 'report' or a 'report_path' (relative to the rows file)."""
    out = []
    for r in rows:
        if r.get('type') != 'run':
            continue
        r = dict(r)
        if r.get('report') is None:
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
    """Ledger contract [확인 필요: no tournament runner exists yet; DeepSeek writes this JSONL]:
    header {"type":"header","prereg_sha256"}; one row per world-run
    {"type":"world_run","arm","rep","cohort":"HO4"|"TRAIN4","seed","status":"complete"|"HOST_ERROR",
     "release_success","physical_success","drop_detected"  (harness/grasp_act_rollout.py record keys),
     "G","early_open_grasp","open_issued","release_done","cap_end"  (C2c aggregate terms, [확인 필요] keys)}.
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
    notes = [
        f'분모 규칙: arm당 {N} world-run 고정(8 seed × N={n_rep}). HOST_ERROR와 미실행도 분모에 남깁니다(성공 아님) {CHECK}: '
        '토너먼트 사전 등록에 HOST_ERROR 재실행 규칙이 없어 C2c·E2E 관례(실패도 분모)를 따릅니다.',
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
    """Rows contract [확인 필요: the P5 rollout writer does not exist yet (dsh/pairact-p5-student has the
    controller only)]: header {"type":"header","prereg_sha256","excluded_seeds":[...],
    "static_check_sha256"}; one row per arm x seed x attempt {"type":"episode","arm":"student"|"teacher",
    "seed","attempt":1|2,"status":"complete"|"HOST_ERROR","success","funnel":{stage: bool},
    "termination","student_gt_corrections","teacher_commands_issued_to_student"}.
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
    final, host2, missing, gt_viol = {a: {} for a in arms}, {a: [] for a in arms}, {a: [] for a in arms}, []
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
        if a == 'student' and (r.get('student_gt_corrections') or r.get('teacher_commands_issued_to_student')):
            gt_viol.append(r['seed'])
            return False
        return True

    Ne = len(eff)
    res = {a: dict(n=sum(success(a, final[a].get(s)) for s in eff),
                   funnel={st: sum(1 for s in eff if (final[a].get(s) or {}).get('funnel', {}).get(st) is True)
                           for st in funnel},
                   termination={}, missing=missing[a], host_error_twice=host2[a]) for a in arms}
    for a in arms:
        for s in eff:
            t = (final[a].get(s) or {}).get('termination') or ('미실행' if s in missing[a] else 'unknown')
            res[a]['termination'][t] = res[a]['termination'].get(t, 0) + 1
    for a in arms:
        f = res[a]['funnel']
        if any(f[funnel[i + 1]] > f[funnel[i]] for i in range(len(funnel) - 1)):
            res[a]['funnel_non_monotone'] = True
    body = ['*표기 C — 보류 seed 같은-seed 평가.* teacher는 기준선(GT 사용 허용)이며 학습 결과가 아닙니다.',
            md_table(['arm', f'성공 n/N_eff', '미실행', 'HOST_ERROR 2회(실패로 셈)'],
                     [[a, nn(res[a]['n'], Ne), len(res[a]['missing']), len(res[a]['host_error_twice'])] for a in arms]),
            '단계 퍼널(각 단계에 도달한 seed 수, 같은 seed 순서):',
            md_table(['단계'] + arms, [[st] + [nn(res[a]['funnel'][st], Ne) for a in arms] for st in funnel]),
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
            stop = next((st for st in funnel if f.get(st) is not True), None)
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
    for a in arms:
        if res[a].get('funnel_non_monotone'):
            notes.append(f'{a}: 퍼널이 단조 감소가 아님(행 기록 확인 필요)')
    figs = [bar_figure(Path(args.out) / 'fig-pairact-eval-funnel.png', f'C: 단계 퍼널 (n/{Ne})', funnel,
                       [(a, [(res[a]['funnel'][st], Ne) for st in funnel]) for a in arms])]
    return dict(track='pairact-eval', title='(b2) 공동 운반 P5 같은-seed 평가 (표기 C)', prereg=pre, body=body,
                notes=notes, figures=figs, data=dict(arms=res, N_eff=Ne, excluded=excluded),
                headline=', '.join(f'{a} {res[a]["n"]}/{Ne}' for a in arms))


# ------------------------------------------------------------------ (c) L1-lite

L1_CONDITIONS = ('no_comm', 'structured', 'peer_en', 'leader_en')   # harness/e2ewarp_l1lite.py
L1_TEST_SEEDS = (601, 602, 603, 604, 605, 606)                       # TEST_TABLE; DEV 701/702 never pooled
L1_COMPONENTS = ('allocation_ok', 'distinct_slots', 'arrival_in_chosen_slot', 'claims_2_of_2',
                 'constraint_ok', 'robot_contact_zero')


def l1lite(args, inputs):
    """Rows: header {"type":"header","prereg_sha256"} + {"type":"run","condition","seed",
    "report"|"report_path"} where report = harness.e2ewarp_l1lite_eval.evaluate_run(run_dir).
    Conditions/seeds come from the prereg keys "conditions"/"seeds" when present, else the
    dsh/l1lite-alloc defaults (prereg schema [확인 필요]: Claude writes it 10/22)."""
    rows = inputs.jsonl(args.rows)
    _, rec = header_sha(rows, args.rows)
    pre = check_prereg(inputs, args.prereg, recorded_sha={'rows header': rec},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    try:
        prereg = json.loads(Path(args.prereg).read_text())
    except json.JSONDecodeError:
        prereg = {}
    conds = list(prereg.get('conditions') or L1_CONDITIONS)
    seeds = [int(s) for s in (prereg.get('seeds') or L1_TEST_SEEDS)]
    runs = load_report_rows(inputs, rows, Path(args.rows).parent)
    grid = {}
    for r in runs:
        c, s = r['condition'], int(r['seed'])
        if c not in conds:
            raise ReportError(f'condition {c!r} not registered {conds}')
        if s not in seeds:
            raise ReportError(f'seed {s} is not a registered test seed {seeds} (DEV seeds are never pooled)')
        if (c, s) in grid:
            raise ReportError(f'duplicate run {c}/{s} (seed당 run 1개)')
        rep = r['report']
        if rep.get('schema') != 'ugrp.e2ewarp.l1lite_evaluation.v1':
            raise ReportError(f'{c}/{s}: report schema {rep.get("schema")!r}')
        grid[(c, s)] = rep
    N = len(seeds)
    stat = {}
    for c in conds:
        reps = [grid.get((c, s)) for s in seeds]
        done = [x for x in reps if x is not None]
        comp = {k: sum(1 for x in done if x['success_components'].get(k) is True) for k in L1_COMPONENTS}
        compl = [x['aux']['completion_sim_s'] for x in done if x['aux'].get('completion_sim_s') is not None]
        stat[c] = dict(n=sum(1 for x in done if x['success'] is True), missing=[s for s, x in zip(seeds, reps) if x is None],
                       components=comp, completion_median=(sorted(compl)[len(compl) // 2] if compl else None),
                       utterances=sum(int(x['aux'].get('utterances') or 0) for x in done),
                       deadlock=sum(1 for x in done if x['aux'].get('deadlock_60s')),
                       hallucination=sum(1 for x in done if (x['aux'].get('hallucination') or {}).get('count')),
                       cost=round(sum(float((x['aux'].get('llm') or {}).get('cost_usd') or 0) for x in done), 4))
    body = [md_table(['조건', f'성공 n/{N}', '미실행'] + list(L1_COMPONENTS),
                     [[c, nn(stat[c]['n'], N), len(stat[c]['missing'])] + [f'{stat[c]["components"][k]}/{N}' for k in L1_COMPONENTS]
                      for c in conds]),
            md_table(['조건', '완료 SIM s(중앙값)', '발화 수', '60 s 교착', '환각 run', 'LLM 비용 USD'],
                     [[c, stat[c]['completion_median'], stat[c]['utterances'], stat[c]['deadlock'],
                       stat[c]['hallucination'], stat[c]['cost']] for c in conds]),
            'seed × 조건(✓ 성공, ✗ 실패, – 미실행):',
            md_table(['seed'] + conds, [[s] + ['–' if grid.get((c, s)) is None else ('✓' if grid[(c, s)]['success'] else '✗')
                                          for c in conds] for s in seeds])]
    notes = [f'분모: 조건당 {N}(seed당 run 1개) 고정. 실패·HOST_ERROR·L1LITE_ALLOCATION_FAILED도 분모에 남깁니다. 미실행은 표에 따로 적고 판정 보류.',
             '성공 = 배정 유효 + 서로 다른 슬롯 + GT 슬롯 도착 + ARRIVED claim 2/2 + 사적 제약 준수 + 로봇 간 접촉 0(채널 관측 시). '
             '도착 claim은 물리 성공 주장이 아닙니다(집기·내려놓기 제외).',
             'no_comm 기대값 2/6(충돌 seed 4/6). DEV seed 701·702는 합산하지 않습니다.']
    if not prereg.get('conditions'):
        notes.append(f'조건·seed 목록은 dsh/l1lite-alloc 기본값을 썼습니다 {CHECK}(L1-lite 사전 등록 필드 이름 미정).')
    figs = [bar_figure(Path(args.out) / 'fig-l1lite.png', f'L1-lite: 조건별 성공 (n/{N})', conds,
                       [('성공', [(stat[c]['n'], N) for c in conds])])]
    return dict(track='l1lite', title='(c) L1-lite 통신 조건 비교', prereg=pre, body=body, notes=notes, figures=figs,
                data=dict(conditions=stat, N=N), headline=', '.join(f'{c} {stat[c]["n"]}/{N}' for c in conds))


# ------------------------------------------------------------------ (d) E2E

E2E_PLANNED = {'E2E-1p': 3, 'E2E-2': 6}            # PREREG_DRAFT.md §2 (smoke excluded)
E2E_DISPLAY = {'E2E-1p': "E2E-1' 혼합", 'E2E-2': 'E2E-2 순수'}
E2E_STAGES = ('allocate', 'grasp', 'carry', 'release', 'done')


def e2e(args, inputs):
    """Rows: header {"type":"header","prereg_sha256"} + {"type":"run","level","seed","smoke":bool,
    "report"|"report_path"} where report = harness.e2e_min_eval.recount_run(run_dir)."""
    rows = inputs.jsonl(args.rows)
    _, rec = header_sha(rows, args.rows)
    pre = check_prereg(inputs, args.prereg, recorded_sha={'rows header': rec},
                       expect_sha=args.expect_prereg_sha, allow_draft=args.allow_draft)
    planned = dict(E2E_PLANNED)
    for item in args.planned or ():
        k, v = item.split('=')
        planned[k] = int(v)
    runs = load_report_rows(inputs, rows, Path(args.rows).parent)
    by, smoke = {k: [] for k in planned}, []
    for r in runs:
        rep = r['report']
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
        reach = {s: sum(1 for r in rs for rb in r['report']['aux']['stage_reach'].values() if rb['reached'][s]) for s in E2E_STAGES}
        codes = {}
        for r in rs:
            for rb in r['report']['aux']['stage_reach'].values():
                if rb.get('fail_code'):
                    codes[rb['fail_code']] = codes.get(rb['fail_code'], 0) + 1
        subs = sorted({json.dumps(x, sort_keys=True) for r in rs for x in r['report']['e2e_substitutions']})
        stat[lv] = dict(n=sum(1 for r in rs if r['report']['success'] is True), N=N, ran=len(rs), reach=reach,
                        robot_N=2 * N, fail_codes=codes, substitutions=[json.loads(x) for x in subs],
                        drops=sum(1 for r in rs if r['report']['success_components'].get('drops_zero') is False))
    lv_list = list(planned)
    body = [md_table(['레벨', '표기', '성공 n/N', '실행/N', '대체 단계', '낙하 run', 'FAIL 코드'],
                     [[lv, E2E_DISPLAY.get(lv, lv), nn(stat[lv]['n'], stat[lv]['N']), f'{stat[lv]["ran"]}/{stat[lv]["N"]}',
                       '; '.join(f'{x["stage"]}←{x["by"]}' for x in stat[lv]['substitutions']) or '없음(순수)',
                       stat[lv]['drops'], '; '.join(f'{k} {v}' for k, v in stat[lv]['fail_codes'].items()) or '-']
                      for lv in lv_list]),
            '단계 도달(로봇 단위, 분모 = 2 × 등록 N):',
            md_table(['단계'] + lv_list, [[s] + [nn(stat[lv]['reach'][s], stat[lv]['robot_N']) for lv in lv_list]
                                         for s in E2E_STAGES])]
    if smoke:
        body.append(f'smoke {len(smoke)}회는 배관 확인용이라 위 n/N에 넣지 않습니다: '
                    + ', '.join(f'{r["level"]}/{r["seed"]} {"성공" if r["report"]["success"] else "실패"}' for r in smoke))
    notes = ["레벨끼리 합산하지 않습니다. E2E-1'은 내려놓기를 규칙 스크립트 release_open_v1로 대체한 혼합 결과입니다.",
             '실패와 HOST_ERROR도 분모에 넣습니다. 미실행은 실행/N 열로 보이며 판정 보류입니다.',
             f'등록 N: {planned} (PREREG_DRAFT.md §2 기본값, --planned로 바꿀 수 있음{"" if args.planned else " " + CHECK})',
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


TRACKS = {'tournament': tournament, 'pairact-collect': pairact_collect, 'pairact-eval': pairact_eval,
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
    common(sub.add_parser('pairact-collect')).add_argument('--report', required=True,
                                                           help='run root report.json (run_pairact_collect.py report)')
    common(sub.add_parser('pairact-eval')).add_argument('--rows', required=True)
    common(sub.add_parser('l1lite')).add_argument('--rows', required=True)
    p = common(sub.add_parser('e2e'))
    p.add_argument('--rows', required=True)
    p.add_argument('--planned', action='append', help='LEVEL=N registered runs, e.g. E2E-1p=3')
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
