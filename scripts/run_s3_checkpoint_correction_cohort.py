"""Frozen six-case simultaneous Oracle batch; resource admission and live checks."""
import argparse
import concurrent.futures
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from harness.zone_final_pair_binding import bind
from scripts.run_s3_integer_carry_cohort import execute, admission as resource_admission
from scripts.run_s3_checkpoint_correction import ROOT, PLAN


def commands(plan, sha):
    return [(r, [sys.executable,'-m','scripts.run_s3_checkpoint_correction',
        '--expected-source-sha',sha,'--output',f'outputs/{r["name"]}/raw',
        '--condition',str(r['condition']),'--route-case',r['route_case'],
        '--seed',str(r['seed']),'--candidate',r['candidate'],'--execute'])
        for r in plan['runs']]


def admission():
    receipt = resource_admission()
    free = shutil.disk_usage(Path.home()/'ugrp-sim/runs').free
    if free < 13*1024**3:
        raise OSError('ENOSPC: reserve plus probe budget; HOST_ERROR')
    return dict(receipt, disk_free_bytes=free)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--attempt',type=int,choices=(1,2,3),default=1)
    a = p.parse_args()
    selected=PLAN if a.attempt==1 else f'experiments/2026-10-11-s3-checkpoint-correction/retry{a.attempt}.json'
    items = commands(json.loads((ROOT/selected).read_text()), a.expected_source_sha)
    if not a.execute:
        print(json.dumps(items))
        return 0
    if (platform.system()!='Linux' or platform.machine()!='x86_64'
            or ROOT.name!=a.expected_source_sha or not re.fullmatch('[a-f0-9]{40}',a.expected_source_sha)
            or os.getpriority(os.PRIO_PROCESS,0)!=0 or os.environ.get('LP_NUM_THREADS')!='4'):
        raise ValueError('committed x86 archive / priority zero / LP4 required')
    if len(items)!=6 or len({r['name'] for r,_ in items})!=6:
        raise ValueError('frozen six cases required')
    if (a.output.is_absolute() or len(a.output.parts)!=3 or a.output.parts[0]!='outputs'
            or a.output.parts[-1]!='cohort'
            or not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs')):
        raise ValueError('new persistent outputs/<batch>/cohort required')
    if (a.output.resolve().parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha:
        raise ValueError('source receipt mismatch')
    a.output.mkdir(parents=True, exist_ok=False)
    worker = bind(execute, admission=admission)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(worker,item,a.output,a.expected_source_sha) for item in items]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    (a.output/'cohort.json').write_text(json.dumps(sorted(results,key=lambda x:x['name']),indent=2)+'\n')
    return int(any(r['exit_code'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
