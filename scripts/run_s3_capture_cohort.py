"""Submit a complete immutable diagnostic plan, at most ten subprocesses."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import platform
import re
import sys
from scripts.run_s3_x86_cohort import execute, ROOT

PLAN=ROOT/'experiments/2026-10-10-s3-capture-region/diagnostic-plan.json'


def commands(plan,sha):
    items=[]
    for row in plan['runs']:
        if not re.fullmatch('[a-z0-9-]+',row['name']) or row['seed']!=14201+row['condition']:
            raise ValueError('invalid frozen name/seed')
        args=[sys.executable,'-m','scripts.run_s3_capture_diagnostic','--expected-source-sha',sha,
            '--output',f'outputs/{row["name"]}/raw','--kind',row['kind'],'--condition',str(row['condition']),*row['flags'],'--execute']
        items.append((row,args))
    return items


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    plan=json.loads(PLAN.read_text());items=commands(plan,a.expected_source_sha)
    if not a.execute:print(json.dumps(items));return 0
    if (platform.system()!='Linux' or platform.machine()!='x86_64' or ROOT.name!=a.expected_source_sha
            or not re.fullmatch('[0-9a-f]{40}',a.expected_source_sha) or os.getpriority(os.PRIO_PROCESS,0)!=0):
        raise ValueError('committed Oracle x86 archive and nice0 required')
    if a.output.is_absolute() or len(a.output.parts)!=3 or a.output.parts[0]!='outputs' or a.output.parts[2]!='cohort':
        raise ValueError('relative outputs/<batch>/cohort required')
    if (a.output.resolve().parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha:raise ValueError('source receipt')
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('frozen batch requires LP_NUM_THREADS=4')
    a.output.mkdir(parents=True,exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(execute,item,a.output,a.expected_source_sha) for item in items]
        results=[f.result() for f in concurrent.futures.as_completed(futures)]
    (a.output/'cohort.json').write_text(json.dumps(sorted(results,key=lambda x:x['name']),indent=2)+'\n')
    return int(any(x['exit_code'] for x in results))


if __name__=='__main__':raise SystemExit(main())
