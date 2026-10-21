#!/usr/bin/env python3
"""L1-lite main-experiment analysis: ledger -> per-condition n/6 table (eval-only).

Pre-registered in ``experiments/2026-10-20-l1lite-alloc/PREREG_L1LITE.md``.
The input is the run ledger (one row per attempted run); every one of the
24 planned (condition, test seed) cells is in the denominator whether it ran,
crashed, hit a HOST_ERROR or was never started.  Smoke and dev-seed rows are
listed as excluded and never pooled.  The output is descriptive (n/6 per
condition plus auxiliary metrics and failure reasons); no statistical test is
computed, because n=6 per condition is exploratory (PREREG §8).

Ledger (JSON)::

    {"schema": "ugrp.e2ewarp.l1lite_ledger.v1",
     "frozen_source_sha": "<40 hex>",
     "prereg_sha256": "<sha256 of the FROZEN PREREG_L1LITE.md>",   # read by report_tables.py l1lite
     "runs": [{"order": 1, "condition": "no_comm", "seed": 601,
               "kind": "main",              # main | smoke | dev
               "status": "NAV_ARRIVAL_UNVERIFIED",   # runner status, HOST_ERROR, ...
               "source_sha": "<40 hex>",
               "run_dir": "o01-no_comm-s601",        # relative to the ledger
               "evaluation_path": null}]}           # optional saved report

A row's evaluation is ``evaluation_path`` if given, else a raw recount with
``harness.e2ewarp_l1lite_eval.evaluate_run(run_dir)``.  Nothing here writes
into a run directory.

``prereg_sha256`` is copied into the analysis; with ``--prereg`` the file's sha256 must
equal it.  ``scripts/report_tables.py l1lite --analysis <out-json> --ledger LEDGER.json``
(branch dsh/report-auto) turns the analysis into the n/6 report with Wilson intervals.

Usage::

    python scripts/analyze_l1lite.py LEDGER.json [--prereg PREREG_L1LITE.md] [--out-json X] [--out-md Y]
    python scripts/analyze_l1lite.py --print-order          # pre-registered order
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.e2ewarp_l1lite import CONDITIONS, DEV_SEEDS, TABLE_SEEDS  # noqa: E402

SCHEMA = 'ugrp.e2ewarp.l1lite_analysis.v1'
LEDGER_SCHEMA = 'ugrp.e2ewarp.l1lite_ledger.v1'
HOST_ERROR = 'HOST_ERROR'
#: Williams 4x4 square over CONDITIONS (each ordered neighbour pair once in
#: rows 0-3).  Block b (seed TABLE_SEEDS[b]) uses row b % 4; blocks 4-5 repeat
#: rows 0-1, so positions are balanced for 4 of the 6 blocks only.
WILLIAMS_ROWS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
PART_SPLIT_ORDER = 12  # part 1 = orders 1-12 (seeds 601-603), part 2 = 13-24
#: Failure reasons in reporting priority (first one is the run's primary reason).
REASON_ORDER = (
    'NOT_RUN', HOST_ERROR, 'SHA_MISMATCH', 'EVAL_MISSING',
    'L1LITE_NO_DECISION', 'L1LITE_INVALID_DECISION', 'L1LITE_INVALID_SLOT',
    'L1LITE_LEADER_REPORT_MISSING', 'L1LITE_LEADER_UNASSIGNED',
    'L1LITE_LEADER_ACK_MISSING', 'L1LITE_ORDER_CANDIDATE_MISSING',
    'L1LITE_MESSAGE_INVALID', 'L1LITE_DUPLICATE_SLOT', 'ALLOCATION_NOT_OK',
    'SLOTS_NOT_DISTINCT', 'CONSTRAINT_VIOLATION', 'GT_UNMEASURED',
    'GT_NOT_IN_CHOSEN_SLOT', 'CLAIM_INCOMPLETE', 'CONTACT_UNAVAILABLE',
    'ROBOT_CONTACT', 'SUCCESS_FLAG_FALSE')


def run_order():
    """The pre-registered 24-run condition x seed interleaving (deterministic)."""
    rows = []
    for block, seed in enumerate(TABLE_SEEDS):
        for pos, idx in enumerate(WILLIAMS_ROWS[block % len(WILLIAMS_ROWS)]):
            order = block * len(CONDITIONS) + pos + 1
            rows.append(dict(order=order, block=block + 1, seed=seed,
                             condition=CONDITIONS[idx],
                             part=1 if order <= PART_SPLIT_ORDER else 2))
    return rows


def planned_cells():
    return {(r['condition'], r['seed']): r['order'] for r in run_order()}


def _is_main(row):
    return (row.get('kind', 'main') == 'main' and row.get('seed') in TABLE_SEEDS
            and row.get('condition') in CONDITIONS)


def _exclusion_reason(row):
    if row.get('kind', 'main') != 'main':
        return 'kind=' + str(row.get('kind'))
    if row.get('seed') in DEV_SEEDS:
        return 'dev_seed'
    if row.get('seed') not in TABLE_SEEDS:
        return 'unknown_seed'
    return 'unknown_condition'


def failure_reasons(evaluation):
    """Every failing component of one evaluation report, in REASON_ORDER."""
    if not evaluation:
        return ['EVAL_MISSING']
    comp = evaluation.get('success_components') or {}
    reasons = [str(e) for e in comp.get('allocation_errors') or ()]
    if comp.get('allocation_ok') is not True and not reasons:
        reasons.append('ALLOCATION_NOT_OK')
    if comp.get('distinct_slots') is not True:
        reasons.append('SLOTS_NOT_DISTINCT')
    if comp.get('constraint_ok') is not True:
        reasons.append('CONSTRAINT_VIOLATION')
    if comp.get('gt_measured') is not True:
        reasons.append('GT_UNMEASURED')
    elif comp.get('arrival_in_chosen_slot') is not True:
        reasons.append('GT_NOT_IN_CHOSEN_SLOT')
    if comp.get('claims_2_of_2') is not True:
        reasons.append('CLAIM_INCOMPLETE')
    if comp.get('contacts_available') is not True:
        reasons.append('CONTACT_UNAVAILABLE')
    elif comp.get('robot_contact_zero') is not True:
        reasons.append('ROBOT_CONTACT')
    if not reasons and evaluation.get('success') is not True:
        reasons.append('SUCCESS_FLAG_FALSE')
    rank = {name: i for i, name in enumerate(REASON_ORDER)}
    return sorted(dict.fromkeys(reasons), key=lambda r: (rank.get(r, len(rank)), r))


def _load_evaluation(row, base, evaluate_run):
    path = row.get('evaluation_path')
    if path:
        p = Path(path)
        p = p if p.is_absolute() else base / p
        if not p.is_file():
            return None, 'evaluation_path missing: ' + str(p)
        return json.loads(p.read_text()), None
    run_dir = row.get('run_dir')
    if not run_dir:
        return None, 'no run_dir'
    d = Path(run_dir)
    d = d if d.is_absolute() else base / d
    if not d.is_dir():
        return None, 'run_dir missing: ' + str(d)
    if evaluate_run is None:
        from harness.e2ewarp_l1lite_eval import evaluate_run
    return evaluate_run(d), None


def _cell(condition, seed, order, rows, frozen_sha, base, evaluate_run):
    cell = dict(condition=condition, seed=seed, planned_order=order, success=False,
                attempts=len(rows), counted_order=None, status=None,
                reasons=[], primary_reason=None, deviations=[], aux=None, note=None)
    if not rows:
        cell['reasons'] = ['NOT_RUN']
    else:
        rows = sorted(rows, key=lambda r: (r.get('order') is None, r.get('order')))
        row = rows[0]  # first attempt counts; later attempts never replace it
        if len(rows) > 1:
            cell['deviations'].append('EXTRA_ATTEMPTS_NOT_COUNTED:'
                                      + ','.join(str(r.get('order')) for r in rows[1:]))
        cell.update(counted_order=row.get('order'), status=row.get('status'))
        if row.get('order') != order:
            cell['deviations'].append(f'ORDER_DEVIATION:planned={order},'
                                      f'actual={row.get("order")}')
        if row.get('status') == HOST_ERROR:
            cell['reasons'] = [HOST_ERROR]
        elif frozen_sha and row.get('source_sha') != frozen_sha:
            cell['reasons'] = ['SHA_MISMATCH']
            cell['deviations'].append('SOURCE_SHA:' + str(row.get('source_sha')))
        else:
            evaluation, why = _load_evaluation(row, base, evaluate_run)
            cell['note'] = why
            cell['reasons'] = failure_reasons(evaluation)
            if evaluation:
                cell['aux'] = evaluation.get('aux')
                cell['success'] = (evaluation.get('success') is True
                                   and not cell['reasons'])
    if cell['success']:
        cell['reasons'] = []
    cell['primary_reason'] = cell['reasons'][0] if cell['reasons'] else None
    return cell


def _median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 4) if values else None


def _aux_summary(cells):
    aux = [c['aux'] for c in cells if c.get('aux')]
    ok = [c['aux'] for c in cells if c['success'] and c.get('aux')]
    llm = [a.get('llm') or {} for a in aux]
    gaps = [a.get('min_body_gap_m') for a in aux if a.get('min_body_gap_m') is not None]
    hall = [int((a.get('hallucination') or {}).get('count') or 0) for a in aux]
    n = len(aux)
    return dict(
        runs_with_eval=n,
        completion_sim_s_success_median=_median([a.get('completion_sim_s') for a in ok]),
        completion_sim_s_success=[a.get('completion_sim_s') for a in ok],
        min_body_gap_m_min=(round(min(gaps), 4) if gaps else None),
        min_body_gap_m_median=_median(gaps),
        min_center_distance_m_min=(round(min(v for v in (a.get('min_center_distance_m')
                                                        for a in aux) if v is not None), 4)
                                   if any(a.get('min_center_distance_m') is not None
                                          for a in aux) else None),
        llm_calls_total=sum(int(x.get('calls') or 0) for x in llm),
        llm_tokens_total=sum(int(x.get('total_tokens') or 0) for x in llm),
        llm_cost_usd_total=round(sum(float(x.get('cost_usd') or 0.0) for x in llm), 8),
        llm_usage_missing_rows=sum(int(x.get('usage_missing') or 0) for x in llm),
        llm_calls_per_run_mean=(round(sum(int(x.get('calls') or 0) for x in llm) / n, 3)
                                if n else None),
        utterances_per_run_mean=(round(sum(int(a.get('utterances') or 0) for a in aux) / n, 3)
                                 if n else None),
        hallucination_total=sum(hall),
        hallucination_runs=sum(1 for h in hall if h > 0),
        deadlock_runs=sum(1 for a in aux if a.get('deadlock_60s') is True),
    )


def analyze(ledger, *, base=Path('.'), frozen_sha=None, evaluate_run=None):
    """Pure analysis of a parsed ledger; returns the summary mapping."""
    if ledger.get('schema') != LEDGER_SCHEMA:
        raise ValueError('ledger schema must be ' + LEDGER_SCHEMA)
    frozen_sha = frozen_sha or ledger.get('frozen_source_sha')
    if not frozen_sha:
        raise ValueError('frozen source SHA is required (ledger or --frozen-sha)')
    rows = list(ledger.get('runs') or ())
    main = [r for r in rows if _is_main(r)]
    excluded = [dict(order=r.get('order'), condition=r.get('condition'),
                     seed=r.get('seed'), kind=r.get('kind', 'main'),
                     reason=_exclusion_reason(r))
                for r in rows if not _is_main(r)]
    cells = []
    for (condition, seed), order in sorted(planned_cells().items(), key=lambda kv: kv[1]):
        mine = [r for r in main if r['condition'] == condition and r['seed'] == seed]
        cells.append(_cell(condition, seed, order, mine, frozen_sha, base, evaluate_run))
    table = {}
    for condition in CONDITIONS:
        mine = sorted((c for c in cells if c['condition'] == condition),
                      key=lambda c: c['seed'])
        reasons = {}
        for c in mine:
            if c['primary_reason']:
                reasons[c['primary_reason']] = reasons.get(c['primary_reason'], 0) + 1
        table[condition] = dict(
            n_success=sum(c['success'] for c in mine), n_total=len(mine),
            per_seed={str(c['seed']): c['success'] for c in mine},
            primary_failure_reasons=reasons,
            host_error=sum(c['primary_reason'] == HOST_ERROR for c in mine),
            not_run=sum(c['primary_reason'] == 'NOT_RUN' for c in mine),
            aux=_aux_summary(mine))
    deviations = [dict(condition=c['condition'], seed=c['seed'], items=c['deviations'])
                  for c in cells if c['deviations']]
    return dict(schema=SCHEMA, frozen_source_sha=frozen_sha,
                prereg_sha256=ledger.get('prereg_sha256'),
                denominator_rule='every planned (condition, test seed) cell; '
                                 'NOT_RUN/HOST_ERROR/SHA_MISMATCH/EVAL_MISSING are failures',
                statistical_test=None,
                note='exploratory n=6 per condition; descriptive only (PREREG §8)',
                table=table, cells=cells, excluded=excluded,
                protocol_deviations=deviations)


def _mark(ok):
    return 'O' if ok else 'x'


def to_markdown(summary):
    seeds = [str(s) for s in TABLE_SEEDS]
    lines = ['# L1-lite main experiment: condition table (eval-only, n/6)', '',
             f'frozen source SHA `{summary["frozen_source_sha"]}`. '
             'Descriptive only; no statistical test (n=6 per condition).', '',
             '| condition | success | ' + ' | '.join(seeds)
             + ' | primary failure reasons |',
             '|---|---|' + '---|' * len(seeds) + '---|']
    for condition, row in summary['table'].items():
        reasons = ', '.join(f'{k} {v}' for k, v in sorted(row['primary_failure_reasons'].items()))
        lines.append(f'| {condition} | {row["n_success"]}/{row["n_total"]} | '
                     + ' | '.join(_mark(row['per_seed'][s]) for s in seeds)
                     + f' | {reasons or "-"} |')
    lines += ['', '## Auxiliary metrics', '',
              '| condition | completion SIM s (median, successes) | min body gap m (min / median) '
              '| LLM calls / tokens / USD | utterances/run | hallucination (count / runs) '
              '| deadlock runs |',
              '|---|---|---|---|---|---|---|']
    for condition, row in summary['table'].items():
        a = row['aux']
        lines.append(f'| {condition} | {a["completion_sim_s_success_median"]} | '
                     f'{a["min_body_gap_m_min"]} / {a["min_body_gap_m_median"]} | '
                     f'{a["llm_calls_total"]} / {a["llm_tokens_total"]} / '
                     f'{a["llm_cost_usd_total"]} | {a["utterances_per_run_mean"]} | '
                     f'{a["hallucination_total"]} / {a["hallucination_runs"]} | '
                     f'{a["deadlock_runs"]} |')
    lines += ['', '## Per-run failure reasons', '',
              '| order | condition | seed | status | success | reasons |',
              '|---|---|---|---|---|---|']
    for c in sorted(summary['cells'], key=lambda c: c['planned_order']):
        lines.append(f'| {c["planned_order"]} | {c["condition"]} | {c["seed"]} | '
                     f'{c["status"]} | {_mark(c["success"])} | '
                     f'{", ".join(c["reasons"]) or "-"} |')
    if summary['excluded']:
        lines += ['', '## Excluded rows (never pooled)', '']
        lines += [f'- order {r["order"]}: {r["condition"]} s{r["seed"]} ({r["reason"]})'
                  for r in summary['excluded']]
    if summary['protocol_deviations']:
        lines += ['', '## Protocol deviations', '']
        lines += [f'- {d["condition"]} s{d["seed"]}: {"; ".join(d["items"])}'
                  for d in summary['protocol_deviations']]
    return '\n'.join(lines) + '\n'


def order_markdown():
    lines = ['| order | part | block | seed | condition |', '|---:|---:|---:|---:|---|']
    lines += [f'| {r["order"]} | {r["part"]} | {r["block"]} | {r["seed"]} | {r["condition"]} |'
              for r in run_order()]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('ledger', nargs='?', type=Path)
    p.add_argument('--frozen-sha')
    p.add_argument('--prereg', type=Path, help='PREREG_L1LITE.md; sha256 must equal ledger prereg_sha256')
    p.add_argument('--out-json', type=Path)
    p.add_argument('--out-md', type=Path)
    p.add_argument('--print-order', action='store_true')
    a = p.parse_args(argv)
    if a.print_order:
        sys.stdout.write(order_markdown())
        return 0
    if a.ledger is None:
        p.error('ledger is required unless --print-order')
    raw = a.ledger.read_bytes()
    summary = analyze(json.loads(raw), base=a.ledger.resolve().parent,
                      frozen_sha=a.frozen_sha)
    if a.prereg:
        pre_sha = hashlib.sha256(a.prereg.read_bytes()).hexdigest()
        if summary['prereg_sha256'] != pre_sha:
            p.error(f'ledger prereg_sha256 {summary["prereg_sha256"]} != {a.prereg} sha256 {pre_sha}')
        summary['prereg'] = dict(path=str(a.prereg.resolve()), sha256=pre_sha)
    summary['ledger'] = dict(path=str(a.ledger.resolve()),
                             sha256=hashlib.sha256(raw).hexdigest())
    text = json.dumps(summary, indent=2, sort_keys=True)
    if a.out_json:
        a.out_json.write_text(text + '\n')
    md = to_markdown(summary)
    if a.out_md:
        a.out_md.write_text(md)
    if not a.out_json and not a.out_md:
        sys.stdout.write(md)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
