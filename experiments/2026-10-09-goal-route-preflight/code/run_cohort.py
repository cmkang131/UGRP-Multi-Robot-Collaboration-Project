"""Finite P1 retry, mandatory preflight and two-identical-host-error breaker."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts.run_goal_route_preflight import RAW,EXP,SEEDS
from scripts.agent_lock import status,DEFAULT_ROOT
from harness.cohort_host_error_guard import HostErrorGuard
SUPERVISOR=Path('/private/tmp/claude-501/-Users-changmin/2eb0ff27-da4f-4484-8131-64ef091df6ae/scratchpad/supervisor-ego.md')


def run_slots(seeds,execute,report):
    guard=HostErrorGuard();results=[]
    for seed in seeds:
        r=execute(seed);results.append(r);report(seed,r)
        if guard.observe(r):
            return dict(results=results,stopped='two_consecutive_identical_HOST_ERROR',remaining=list(seeds[len(results):]))
    return dict(results=results,stopped=None,remaining=[])


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args()
    assert int(subprocess.check_output(['ps','-o','ni=','-p',str(os.getpid())]))==0,'NICE_MUST_BE_ZERO'
    assert json.loads((RAW/'queue-admission.json').read_text())['s3fix_completed']
    initial=SUPERVISOR.read_bytes();os.environ['UGRP_V7_EXACT_SPEEDUPS']='relay-cache-v1'
    # Validate all layouts and frozen source before the first physical owner.
    for seed in SEEDS:
        subprocess.run([sys.executable,'-m','scripts.run_goal_route_preflight','--seed',str(seed),
            '--expected-source-sha',a.source,'--output',str(RAW/f'seed{seed}')],cwd=ROOT,check=True)
    def execute(seed):
        while status(DEFAULT_ROOT) is not None:
            if SUPERVISOR.read_bytes()!=initial:raise RuntimeError('SUPERVISOR_CHANGED_REVIEW_BEFORE_NEXT_SLOT')
            print('Waiting for shared physics lock',seed,flush=True);time.sleep(30)
        if SUPERVISOR.read_bytes()!=initial:raise RuntimeError('SUPERVISOR_CHANGED_REVIEW_BEFORE_NEXT_SLOT')
        out=RAW/f'seed{seed}';assert not out.exists()
        cmd=[sys.executable,'-m','scripts.run_goal_route_preflight','--seed',str(seed),'--expected-source-sha',a.source,'--output',str(out),'--execute']
        log=RAW/f'seed{seed}.log'
        with log.open('x') as f:
            print('START',seed,flush=True);r=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        print('FINISH',seed,'returncode',r.returncode,flush=True)
        if not (out/'result.json').exists():
            # Preflight is outside the physical owner. Keep its refusal too.
            text=log.read_text().splitlines();failure=dict(type='PreflightProcessError',message=text[-1] if text else 'NO_TERMINAL_ARTIFACT')
            result=dict(status='HOST_ERROR',failure=failure,frames=0,source_sha=a.source,seed=seed,
                condition='T1' if seed<55004 else 'T2',physical_started=False)
            out.mkdir(exist_ok=True);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            import hashlib
            (out/'artifacts.sha256.json').write_text(json.dumps({'result.json':hashlib.sha256((out/'result.json').read_bytes()).hexdigest()})+'\n')
        return json.loads((out/'result.json').read_text())
    def report(seed,r):
        cmd=[sys.executable,str(EXP/'code/report.py'),'--seed',str(seed),'--append-readme']
        with (RAW/f'seed{seed}-score.log').open('x') as f:subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,check=True)
        (RAW/'cohort-progress.json').write_text(json.dumps(dict(last_finished_seed=seed,source=a.source,status=r['status']))+'\n')
    summary=run_slots(SEEDS,execute,report)
    (RAW/'cohort-terminal.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(stopped=summary['stopped'],remaining=summary['remaining'],attempted=len(summary['results']))),flush=True)

if __name__=='__main__':main()
