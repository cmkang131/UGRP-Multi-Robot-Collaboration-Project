"""Submit the entire registered ten-case S3 round before reading any result."""
import argparse
import concurrent.futures
import json
import os
import platform
import re
import sys
from pathlib import Path
from scripts.run_s3_x86_cohort import execute, ROOT

PLAN=ROOT/'experiments/2026-10-10-s3-alignment-ownership/batch-plan.json'


def commands(plan,sha):
    rows=[]
    for r in plan['runs']:
        assert re.fullmatch('[a-z0-9-]+',r['name']) and r['seed']==14201+r['condition']
        args=[sys.executable,'-m','scripts.run_s3_alignment_ownership','--expected-source-sha',sha,
              '--output',f'outputs/{r["name"]}/raw','--case',r['case'],
              '--condition',str(r['condition']),*plan['flags'],'--execute']
        rows.append((r,args))
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    plan=json.loads(PLAN.read_text());items=commands(plan,a.expected_source_sha)
    if not a.execute:print(json.dumps(items));return 0
    if (platform.system()!='Linux' or platform.machine()!='x86_64'
            or ROOT.name!=a.expected_source_sha or not re.fullmatch('[0-9a-f]{40}',a.expected_source_sha)
            or os.getpriority(os.PRIO_PROCESS,0)!=0):raise ValueError('committed x86 archive, nice0 required')
    if a.output.is_absolute() or len(a.output.parts)!=3 or a.output.parts[0]!='outputs' or a.output.parts[2]!='cohort':
        raise ValueError('new relative outputs/<batch>/cohort required')
    if (a.output.resolve().parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha:
        raise ValueError('source receipt mismatch')
    if os.environ.get('LP_NUM_THREADS') != '4': raise ValueError('LP_NUM_THREADS=4 required')
    a.output.mkdir(parents=True,exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(execute,item,a.output,a.expected_source_sha) for item in items]
        rows=[f.result() for f in concurrent.futures.as_completed(futures)]
    (a.output/'cohort.json').write_text(json.dumps(sorted(rows,key=lambda r:r['name']),indent=2)+'\n')
    return int(any(r['exit_code'] for r in rows))


if __name__=='__main__':raise SystemExit(main())
