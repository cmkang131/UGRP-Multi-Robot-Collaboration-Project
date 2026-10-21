"""pairact P1: tournament/confirmation OUT_ROOT -> world-run ledger JSONL (pure, eval-only).

Read by ``scripts/report_tables.py pairact-p1`` (branch dsh/report-auto).  Same row
shape as the single-robot tournament ledger (scripts/act18_tournament_ledger.py):

  {"type":"header","prereg_sha256","stage","N_nominal","not_executed","excluded_worlds",
   "arms","summary_sha256":{arm: sha|null},"schema":"ugrp.pairact.p1_ledger.v1"}
  {"type":"world_run","arm","rep":1,"cohort":<stage>,"world":<case index>,"seed",
   "status":"complete"|"HOST_ERROR"|"not_executed"|"excluded","success","cap_end","sim_s"}

One row per arm x registered case index 0..N_nominal-1:
  * excluded       static rule A (prereg static_exclusion.<stage>.excluded_worlds); out of N_eff
  * not_executed   prereg world_set.<stage>.not_executed (world 15); a failure inside N_eff
  * complete       the world is in <OUT_ROOT>/<arm>/summary.json worlds (index via world_indices)
  * HOST_ERROR     an executed index with no world result (summary missing, HOST_ERROR or
                   admission_rejected).  Prereg host_error: stays in N_eff as a failure, never re-run.
An arm without an <OUT_ROOT>/<arm> directory has no rows (not started; the report holds the verdict).

Usage:  python p1_ledger.py PREREG.json tournament|confirmation OUT_ROOT CASES0.json ARM...
        -> writes OUT_ROOT/p1-ledger.jsonl (refuses to overwrite)
"""
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = 'ugrp.pairact.p1_ledger.v1'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arm_rows(arm, summary, *, stage, n_nominal, not_executed, excluded, seeds):
    worlds = {}
    if summary is not None:
        idx = summary.get('world_indices') or list(range(n_nominal))
        for w in summary.get('worlds') or ():
            worlds[int(idx[int(w['world'])])] = w
    why = ('no summary.json' if summary is None else f'summary status {summary.get("status")}')
    rows = []
    for i in range(n_nominal):
        base = dict(type='world_run', arm=arm, rep=1, cohort=stage, world=i, seed=seeds.get(i))
        if i in excluded:
            rows.append(dict(base, status='excluded'))
        elif i in not_executed:
            rows.append(dict(base, status='not_executed', success=False))
        elif i in worlds:
            w = worlds[i]
            if w.get('seed') is not None and seeds.get(i) is not None and int(w['seed']) != seeds[i]:
                raise ValueError(f'{arm} world {i}: seed {w["seed"]} != cases seed {seeds[i]}')
            rows.append(dict(base, status='complete', success=w.get('success') is True,
                             cap_end=w.get('cap_end') is True, sim_s=w.get('sim_s')))
        else:
            rows.append(dict(base, status='HOST_ERROR', success=False, host_error_reason=why))
    return rows


def ledger(prereg_path, stage, out_root, cases_path, arms):
    prereg = json.loads(Path(prereg_path).read_text())
    ws = prereg['world_set'][stage]
    excluded = prereg['static_exclusion'][stage]['excluded_worlds']
    if not isinstance(excluded, list):
        raise ValueError(f'{stage}: excluded_worlds not recorded (static check must run first)')
    n = int(ws['nominal_denominator'])
    cases = json.loads(Path(cases_path).read_text())
    cases = cases['cases'] if isinstance(cases, dict) else cases
    seeds = {i: int(c['plan']['seed']) for i, c in enumerate(cases) if 'plan' in c and 'seed' in c['plan']}
    head = dict(type='header', schema=SCHEMA, prereg_sha256=_sha(prereg_path), stage=stage, N_nominal=n,
                not_executed=sorted(ws.get('not_executed') or []), excluded_worlds=sorted(excluded),
                arms=list(arms), cases_sha256=_sha(cases_path), summary_sha256={},
                host_error_rule='HOST_ERROR stays in N_eff as a failure; never re-run')
    rows = [head]
    for arm in arms:
        d = Path(out_root) / arm
        if not d.is_dir():
            head['summary_sha256'][arm] = None
            continue
        s = d / 'summary.json'
        summary = json.loads(s.read_text()) if s.exists() else None
        head['summary_sha256'][arm] = _sha(s) if s.exists() else None
        rows += arm_rows(arm, summary, stage=stage, n_nominal=n, not_executed=set(ws.get('not_executed') or []),
                         excluded=set(excluded), seeds=seeds)
    return rows


def main(argv):
    prereg, stage, out_root, cases = argv[:4]
    arms = argv[4:]
    out = Path(out_root) / 'p1-ledger.jsonl'
    if out.exists():
        raise SystemExit(f'{out} exists; ledger is written once')
    rows = ledger(prereg, stage, out_root, cases, arms)
    out.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    print(f'{out}: {len(rows) - 1} world-run rows')


if __name__ == '__main__':
    main(sys.argv[1:])
