"""egomap60 fixed dependency batch. No tuning or retry between jobs."""
from pathlib import Path
import argparse,importlib.util,json,os,platform,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]


def plan(out):
    out=Path(out)
    jobs=[dict(name=f'egomap60-stage-60011-{p}',seed=60011,profile=p,
               status='BLOCKED_PREPARE_B_UNOBSERVED',source_run='egomap60-prep-60011-r4')
          for p in ('baseline','a','b','c')]
    for p in ('baseline','a','b','c'):
        name=f'egomap60-stage-60012-{p}'
        jobs.append(dict(name=name,seed=60012,profile=p,status='WAITING_CHECKPOINT',
            output=str(out/name)))
    return jobs


def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--smoke',type=Path,required=True);args=parser.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':
        raise RuntimeError('ORACLE_X86_ONLY_NO_MAC_PHYSICS')
    smoke=json.loads(args.smoke.read_text())
    if not all(smoke[k]['status']=='RECORDED' and smoke[k]['source_sha']==ROOT.name for k in ('save','resume')):
        raise ValueError('SAME_SOURCE_SMOKE_REQUIRED')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    jobs=plan(out);write(out/'batch-plan.json',dict(source_sha=ROOT.name,host='oracle-x86',jobs=jobs,smoke=str(args.smoke),max_concurrent=4))
    def launch(mode,seed,profile,output,checkpoint=None):
        cmd=[sys.executable,'-m','scripts.run_own_route_particle_stages','--mode',mode,'--seed',str(seed),
             '--profile',profile,'--output',str(output)]
        if checkpoint:cmd+=['--checkpoint',str(checkpoint)]
        stream=(out/(output.name+'.log')).open('x')
        child=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        return child,stream,cmd
    # Required start-state construction. All dependents are already registered;
    # no operator inspection, edits, ranking or retry occurs between the phases.
    prep=out/'egomap60-prep-60012-batch'
    child,stream,cmd=launch('prepare',60012,'baseline',prep)
    code=child.wait();stream.close()
    prepared=json.loads((prep/'result.json').read_text()) if (prep/'result.json').exists() else {'status':'HOST_ERROR'}
    write(out/'prepare-job.json',dict(command=cmd,exit_code=code,result=prepared))
    children=[]
    if prepared['status']=='RECORDED' and 'saved_checkpoint' in prepared:
        cp=prep/'checkpoints'/prepared['saved_checkpoint']['file']
        for job in jobs:
            if job['seed']!=60012:continue
            child,stream,cmd=launch('stage',60012,job['profile'],Path(job['output']),cp)
            job.update(status='RUNNING',pid=child.pid,command=cmd)
            children.append((job,child,stream))
    else:
        for job in jobs:
            if job['seed']==60012:job['status']='BLOCKED_PREPARE_'+prepared['status']
    write(out/'batch-status.json',jobs)
    for job,child,stream in children:
        job['exit_code']=child.wait();stream.close()
        p=Path(job['output'])/'result.json'
        job['status']=json.loads(p.read_text())['status'] if p.exists() else 'HOST_ERROR_NO_RESULT'
    write(out/'batch-status.json',jobs)
    spec=importlib.util.spec_from_file_location('stage_score',ROOT/'experiments/2026-10-10-own-route-particle-stages/code/score.py')
    scoring=importlib.util.module_from_spec(spec);spec.loader.exec_module(scoring)
    reports=[]
    for job in jobs:
        if job['status'].startswith('BLOCKED'):
            reports.append(dict(seed=job['seed'],profile=job['profile'],status=job['status'],samples=0));continue
        try:report=scoring.score(Path(job['output']))
        except Exception as e:report=dict(seed=job['seed'],profile=job['profile'],status='SCORING_ERROR',error=repr(e))
        reports.append(report)
    write(out/'scores.json',reports);write(out/'selection.json',scoring.select(reports))
    print(json.dumps(dict(jobs=jobs,selection=scoring.select(reports))),flush=True)
    return 0 if all(j['status']=='RECORDED' for j in jobs if j['seed']==60012) else 1


if __name__=='__main__':raise SystemExit(main())
