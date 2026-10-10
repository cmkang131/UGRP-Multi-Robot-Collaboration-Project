"""Two simultaneous seeds, live health receipt, immediate verified ARM copy."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from scripts.run_s3_integer_carry_cohort import execute
from scripts.evaluate_e2e_s3_route import evaluate, file_sha

ROOT=Path(__file__).resolve().parents[1]


def commands(sha,attempt,candidate):
    return [(dict(name=f'e2e3-{candidate}-s{seed}-r{attempt}',seed=seed,case='pair',candidate=candidate),
        [sys.executable,'-m','scripts.run_e2e_s3_route','--expected-source-sha',sha,
         '--output',f'outputs/e2e3-{candidate}-s{seed}-r{attempt}/raw','--seed',str(seed),
         '--candidate',candidate,'--own-route-adapter','on_v1','--execute']) for seed in (61001,61002)]


def run_one(item,out,sha):
    result=execute(item,out,sha)
    target=out/result['name']
    try:
        result['evaluation']=evaluate(target/'raw')
        (target/'evaluation.json').write_text(json.dumps(result['evaluation'],indent=2,allow_nan=False)+'\n')
        # Archive complete originals without deleting/replacing x86 evidence.
        arm=Path.home()/'ugrp-sim/arm'/result['name']
        arm.mkdir(exist_ok=False)
        subprocess.run(['rsync','-a',str(target)+'/',str(arm)+'/'],check=True)
        differences=subprocess.check_output(['rsync','-anc','--out-format=%n',str(target)+'/',str(arm)+'/'],text=True)
        if differences.strip():raise ValueError('ARM_ARCHIVE_CHECKSUM_MISMATCH:'+differences)
        manifest=json.loads((target/'raw/artifacts.sha256.json').read_text())
        for rel,h in manifest.items():
            if file_sha(arm/'raw'/rel)!=h:raise ValueError('ARM_SHA256_MISMATCH:'+rel)
        result['arm_archive']=dict(path=str(arm),verified_files=len(manifest),all_sha256_match=True,
                                   x86_original_preserved=True)
    except Exception as exc:
        result['retrieval_error']=str(exc)
    (target/'completion.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--attempt',type=int,default=1)
    p.add_argument('--candidate',choices=('visual','recovery'),default='visual');p.add_argument('--execute',action='store_true')
    a=p.parse_args();items=commands(a.expected_source_sha,a.attempt,a.candidate)
    if not a.execute:print(json.dumps(items));return 0
    if (platform.system()!='Linux' or platform.machine()!='x86_64' or ROOT.name!=a.expected_source_sha
            or os.getpriority(os.PRIO_PROCESS,0)!=0 or os.environ.get('LP_NUM_THREADS')!='4'):
        raise ValueError('COMMITTED_X86_LP4_NICE0_REQUIRED')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs') or a.output.exists():
        raise ValueError('NEW_PERSISTENT_COHORT_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda item:run_one(item,a.output,a.expected_source_sha),items))
    (a.output/'cohort.json').write_text(json.dumps(results,indent=2,allow_nan=False)+'\n')
    print(json.dumps([dict(name=r['name'],exit_code=r['exit_code'],archive_ok='arm_archive' in r,
                           success=r.get('evaluation',{}).get('S3_route_success')) for r in results]))
    return int(any(r['exit_code'] or 'retrieval_error' in r for r in results))


if __name__=='__main__':raise SystemExit(main())
