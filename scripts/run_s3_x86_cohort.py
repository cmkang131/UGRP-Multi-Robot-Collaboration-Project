"""One frozen finite queue; all conditions submitted together, <=10 workers."""
import argparse,concurrent.futures,json,os,platform,re,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'experiments/2026-10-09-s3-no-prior/s3fix11/batch-plan.json'


def commands(plan,phase,sha,model=None,model_sha=None):
    rows=[]
    for r in plan['runs']:
        if r['phase']!=phase:continue
        if not re.fullmatch('[a-z0-9-]+',r['name']) or r['seed']!=14201+r['condition']:
            raise ValueError('invalid frozen name/seed')
        args=[sys.executable,'-m',r['module'],'--expected-source-sha',sha,
            '--output',f'outputs/{r["name"]}/raw','--condition',str(r['condition']),'--execute']
        if phase=='candidate':args+=['--case',r['case'],'--model',str(model),'--model-sha256',model_sha]
        rows.append((r,args))
    return rows


def execute(item,out,sha):
    r,args=item;target=out/r['name'];target.mkdir(exist_ok=False)
    (target/'SOURCE_SHA').write_text(sha+'\n');(target/'COMMAND.json').write_text(json.dumps(args)+'\n')
    link=ROOT/'outputs'/r['name']
    if link.exists() or link.is_symlink():raise FileExistsError(link)
    link.symlink_to(target.resolve(),target_is_directory=True)
    alias=Path.home()/'ugrp-sim/runs'/r['name']
    if alias.exists() or alias.is_symlink():raise FileExistsError(alias)
    alias.symlink_to(target.resolve(),target_is_directory=True)
    with (target/'log.txt').open('w') as log:
        process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,MUJOCO_GL='osmesa',OMP_NUM_THREADS='1'))
        code=process.wait()
    (target/'EXIT').write_text(str(code)+'\n')
    return dict(name=r['name'],exit_code=code,seed=r['seed'],condition=r['condition'],source_sha=sha)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--phase',choices=('measure','candidate'),required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',type=Path);p.add_argument('--model-sha256');p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    plan=json.loads(PLAN.read_text());items=commands(plan,a.phase,a.expected_source_sha,a.model,a.model_sha256)
    if not a.execute:print(json.dumps(dict(execution_started=False,rows=items,workers=10)));return 0
    if (platform.system()!='Linux' or platform.machine()!='x86_64' or ROOT.name!=a.expected_source_sha
            or not re.fullmatch('[0-9a-f]{40}',a.expected_source_sha) or os.getpriority(os.PRIO_PROCESS,0)!=0):
        raise ValueError('committed Oracle x86 archive and nice0 required')
    if a.phase=='candidate' and (a.model is None or a.model_sha256 is None):raise ValueError('frozen model required')
    if a.output.is_absolute() or len(a.output.parts)!=3 or a.output.parts[0]!='outputs' or a.output.parts[2]!='cohort':raise ValueError('new outputs/<batch>/cohort required')
    if (a.output.resolve().parent/'SOURCE_SHA').read_text().strip()!=a.expected_source_sha:raise ValueError('source receipt mismatch')
    a.output.mkdir(parents=True,exist_ok=False);rows=[]
    # Submit the entire preregistered list before reading any result. Queue
    # capacity, not a signal pause, handles more than ten fixed conditions.
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(execute,item,a.output,a.expected_source_sha) for item in items]
        for f in concurrent.futures.as_completed(futures):rows.append(f.result())
    (a.output/'cohort.json').write_text(json.dumps(sorted(rows,key=lambda r:r['name']),indent=2)+'\n')
    return int(any(r['exit_code'] for r in rows))


if __name__=='__main__':raise SystemExit(main())
