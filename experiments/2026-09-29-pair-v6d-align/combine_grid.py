#!/usr/bin/env python3
"""Combine the outputs of several ``run_cells.py`` invocations into one derived grid result (read-only on the members).

The stage-2 b-v6d grid was run as an interrupted pilot (the coordinator asked for one worker at a time), a
finishing pilot and two single-worker shards. Each cell was physically run exactly once. This script reads every
``cases/<name>/result.json`` of the member directories (so the interrupted pilot's two rows that never reached its
``cases.jsonl`` are included), checks that the expected case set is complete and unique, and writes

  <output>/cases.jsonl    one row per case (the runner's row + ``raw_dir``), rows sorted by case id
  <output>/summary.json   ``harness.pair_stage_probe.summarize`` of those rows (+ member list)
  <output>/manifest.json  members (manifest / summary sha256, source sha, uptime at start/end, states), baseline
  <output>/artifacts.sha256.json  the three files above

  combine_grid.py --output /Users/changmin/projects/ugrp/outputs/<name> --expect-cases-of <baseline cases.jsonl> \
      --baseline-policy b-v6c --policy b-v6d --member <dir> [--member <dir> ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import pair_stage_probe as sp  # noqa: E402


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--member', type=Path, action='append', required=True)
    p.add_argument('--expect-cases-of', type=Path, required=True, help='cases.jsonl of the baseline grid (case set to match)')
    p.add_argument('--baseline-policy', default='b-v6c')
    p.add_argument('--policy', default='b-v6d')
    a = p.parse_args(argv)
    if a.output.exists():
        p.error('output must be new')
    expected = {json.loads(line)['case_id'].replace(f'@{a.baseline_policy}:', f'@{a.policy}:', 1)
                for line in a.expect_cases_of.read_text().splitlines() if line.strip()}
    rows, members = {}, []
    for m in a.member:
        manifest = json.loads((m / 'manifest.json').read_text())
        n = 0
        for f in sorted((m / 'cases').glob('*/result.json')):
            row = json.loads(f.read_text()).get('row')
            if not row:
                continue
            if row['case_id'] in rows:
                p.error(f"case run twice: {row['case_id']}")
            rows[row['case_id']] = {**row, 'raw_dir': str(m), 'result_json_sha256': sha(f)}
            n += 1
        members.append({'dir': str(m), 'cases_with_result': n, 'state': manifest.get('state'),
                        'manifest_sha256': sha(m / 'manifest.json'),
                        'summary_sha256': sha(m / 'summary.json') if (m / 'summary.json').exists() else None,
                        'source_sha': manifest['source']['source_sha'],
                        'execution_tree_sha256': manifest['source']['execution_tree']['sha256'],
                        'workers': manifest.get('workers'), 'omp_num_threads_per_worker': manifest.get('omp_num_threads_per_worker'),
                        'shard': manifest.get('shard'),
                        'uptime_at_start': manifest['environment'].get('uptime_at_start'),
                        'uptime_at_end': manifest['environment'].get('uptime_at_end')})
    missing, extra = sorted(expected - set(rows)), sorted(set(rows) - expected)
    if missing or extra:
        p.error(f'case set mismatch: missing={missing} extra={extra}')
    trees = {m['execution_tree_sha256'] for m in members}
    ordered = [rows[k] for k in sorted(rows)]
    a.output.mkdir(parents=True)
    with (a.output / 'cases.jsonl').open('x') as f:
        for r in ordered:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
    summary = sp.summarize(ordered)
    summary.update(members=[m['dir'] for m in members], combined=True)
    (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')
    manifest = {'schema': sp.SCHEMA, 'labels': sp.LABELS, 'probe_version': sp.PROBE_VERSION, 'research_result': False,
                'e2e_success_claim': False, 'model_calls': 0, 'combined': True, 'policy': a.policy,
                'baseline': {'cases_jsonl': str(a.expect_cases_of), 'sha256': sha(a.expect_cases_of), 'policy': a.baseline_policy},
                'source': {'source_sha': members[-1]['source_sha'], 'execution_tree': {'sha256': sorted(trees)[0]}},
                'execution_tree_identical_across_members': len(trees) == 1, 'members': members,
                'cases': len(ordered), 'state': 'completed'}
    (a.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    files = {n: {'bytes': (a.output / n).stat().st_size, 'sha256': sha(a.output / n)}
             for n in ('cases.jsonl', 'summary.json', 'manifest.json')}
    (a.output / 'artifacts.sha256.json').write_text(json.dumps(files, indent=1) + '\n')
    print(json.dumps({'cases': len(ordered), 'passed': sum(1 for r in ordered if r['passed']),
                      'execution_tree_identical': len(trees) == 1}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
