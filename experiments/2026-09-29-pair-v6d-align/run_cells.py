#!/usr/bin/env python3
"""Driver for the b-v6d stage probe cells (experiments/2026-09-29-pair-v6d-align/README.md).

Same grid, cases, workers and result layout as ``scripts/run_pair_stage_probes.py`` (its parser,
``build_cases`` and ``run_worker`` are reused unchanged, the physical case code runs in that module's
``--worker-case`` processes). Two differences, both recorded in ``manifest.json``:

* no ``agent_lock``: the runner's gate requires the exclusive physics lock, which another task held for
  its stage 4/5 probes while this ran. These are synchronous SIM-time probes that make no wall-time
  claim, so the lock is neither taken nor imitated (``manifest['lock']`` is ``null``); ``loadavg`` and
  ``uptime`` are recorded at start and end instead, and at most 2 workers run in parallel;
* ``--only-failed-of <cases.jsonl>`` keeps only the cases that failed in an earlier grid (same case id
  with the baseline policy name), which is the pilot on the 12 failed b-v6c cells.

  plan only:  python3 experiments/2026-09-29-pair-v6d-align/run_cells.py --stage align ... --output <dir>
  physical:   ... --execute --output /Users/changmin/projects/ugrp/outputs/<name>
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import pair_stage_probe as sp  # noqa: E402
from scripts import run_pair_stage_probes as rp  # noqa: E402

BASELINE_POLICY = 'b-v6c'
MAX_WORKERS = 2


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def only_failed(cases, baseline_jsonl, baseline_policy, policy):
    rows = [json.loads(line) for line in Path(baseline_jsonl).read_text().splitlines() if line.strip()]
    failed = {r['case_id'].replace(f'@{baseline_policy}:', f'@{policy}:', 1) for r in rows if not r['passed']}
    return [c for c in cases if c['case_id'] in failed], sorted(failed)


def main(argv=None):
    p = rp.parser()
    p.add_argument('--only-failed-of', type=Path, help='cases.jsonl of an earlier grid; keep its failed cells only')
    p.add_argument('--baseline-policy', default=BASELINE_POLICY)
    p.set_defaults(workers=MAX_WORKERS)
    args = p.parse_args(argv)
    if not args.stage or not args.output:
        p.error('--stage and --output are required')
    if args.output.exists():
        p.error('output must be new; raw results are never overwritten')
    if not 1 <= args.workers <= MAX_WORKERS:
        p.error(f'workers must be 1..{MAX_WORKERS} (host load)')
    if args.lock_owner:
        p.error('this driver takes no agent_lock; use scripts/run_pair_stage_probes.py for a locked grid')
    args.unavailable = []
    cases = rp.build_cases(args)
    baseline = None
    if args.only_failed_of:
        if len(args.policies) != 1:
            p.error('--only-failed-of needs exactly one --policies value')
        cases, wanted = only_failed(cases, args.only_failed_of, args.baseline_policy, args.policies[0])
        baseline = {'cases_jsonl': str(args.only_failed_of), 'sha256': _sha(args.only_failed_of),
                    'policy': args.baseline_policy, 'failed_case_ids': wanted}
        missing = sorted(set(wanted) - {c['case_id'] for c in cases})
        if missing:
            p.error(f'baseline failures without a matching case: {missing}')
    if len({c['case_id'] for c in cases}) != len(cases):
        p.error('duplicate case ids')
    from sim.workflow_manager import environment_identity, git_identity, source_fingerprint
    manifest = {'schema': sp.SCHEMA, 'workflow': rp.WORKFLOW, 'labels': sp.LABELS, 'probe_version': sp.PROBE_VERSION,
                'research_result': False, 'e2e_success_claim': False, 'model_calls': 0,
                'stages': args.stage, 'criteria': {s: sp.CRITERIA[s] for s in args.stage},
                'stage_registry': {s: sp.STAGES[s] for s in sp.STAGES},
                'source': {**git_identity(ROOT), 'execution_tree': source_fingerprint(ROOT)},
                'driver': {'file': str(Path(__file__).relative_to(ROOT)), 'sha256': _sha(__file__),
                           'argv': sys.argv[1:]},
                'environment': {**environment_identity(), 'loadavg_at_start': list(os.getloadavg()),
                                'uptime_at_start': subprocess.check_output(['uptime'], text=True).strip()},
                'workers': args.workers, 'omp_num_threads_per_worker': 2, 'lock': None,
                'lock_note': 'synchronous SIM-time probe, no wall-time claim; agent_lock held by another task and '
                             'neither taken nor imitated; host load recorded',
                'baseline': baseline, 'cases': len(cases), 'cases_sha256': sp.digest(cases),
                'unavailable_e2e': args.unavailable, 'state': 'planned'}
    if not args.execute:
        print(json.dumps({'state': 'planned', 'cases': len(cases), 'case_ids': [c['case_id'] for c in cases],
                          'baseline': baseline, 'unavailable_e2e': args.unavailable}, ensure_ascii=False, indent=1))
        return 0
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to(rp.primary_root() / 'outputs'):
        p.error('physical raw output must be absolute under the primary checkout outputs/')
    if rp.git('status', '--porcelain', '--untracked-files=no'):
        p.error('tracked source must be clean (commit the probe source first)')
    args.output.mkdir(parents=True)
    (args.output / 'cases').mkdir()
    rp.write_json(args.output / 'plan.json', {'labels': sp.LABELS, 'cases': cases})
    manifest['state'] = 'running'
    rp.write_json(args.output / 'manifest.json', manifest)
    start = time.monotonic()
    rows = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool, (args.output / 'cases.jsonl').open('x') as sink:
        futures = {pool.submit(rp.run_worker, c, args.output / 'cases' / rp.safe_name(c['case_id']),
                               args.case_timeout_s): c for c in cases}
        for fut in cf.as_completed(futures):
            row = fut.result()
            rows.append(row)
            sink.write(json.dumps(row, ensure_ascii=False, default=rp._jsonable) + '\n')
            sink.flush()
            print(f"[{len(rows)}/{len(cases)}] {row['case_id']}: {row['category']} "
                  f"(stage {row.get('stage_sim_s')} SIM s, {row.get('wall_s')} wall s)", flush=True)
    summary = sp.summarize(rows)
    summary.update(wall_s_total=round(time.monotonic() - start, 1), unavailable_e2e=args.unavailable)
    rp.write_json(args.output / 'summary.json', summary)
    manifest.update(state='completed', wall_s=summary['wall_s_total'],
                    source_after_sha256=source_fingerprint(ROOT)['sha256'])
    manifest['source_changed'] = manifest['source_after_sha256'] != manifest['source']['execution_tree']['sha256']
    manifest['environment']['loadavg_at_end'] = list(os.getloadavg())
    manifest['environment']['uptime_at_end'] = subprocess.check_output(['uptime'], text=True).strip()
    rp.write_json(args.output / 'manifest.json', manifest)
    files = {str(q.relative_to(args.output)): {'bytes': q.stat().st_size, 'sha256': sp.sha_file(q)}
             for q in sorted(args.output.rglob('*')) if q.is_file() and q.name != 'artifacts.sha256.json'}
    rp.write_json(args.output / 'artifacts.sha256.json', files)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
