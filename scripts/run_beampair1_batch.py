"""Bounded six-run development round; stop owned siblings on confirmed failure."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.run_beampair1 import MODE
from harness.grasp_act_data import write_json


def final_adapter_result(path):
    """Result compression is part of normal finalization, not missing evidence."""
    if not path.exists() and not Path(str(path)+'.zst').exists():return None
    from scripts.audit_beampair1 import read
    return read(path)


def python_processes():
    # Count all Python processes, including model workers. This overestimates
    # simulation concurrency; it cannot undercount another Python task here.
    return sum('python' in p.read_text().split('\0')[0] for p in Path('/proc').glob('[0-9]*/cmdline')
               if p.exists())


def run(args):
    if sys.platform!='linux':raise RuntimeError('GCP Linux only')
    plan=json.loads(args.plan.read_text());count=len(plan['episodes'])
    if not 4<=count<=6:raise ValueError('four to six probes per round required')
    existing=python_processes()
    if existing+count>40:raise RuntimeError('shared host capacity unavailable')
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=False)
    write_json(root/'batch-plan.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        planned_N=count,concurrency=count,host_python_processes=existing,host_total_limit=40,
        candidate=args.candidate,training_rgb=False,cap_s=60,loadavg=os.getloadavg()))
    children=[];stopped=False
    try:
        for i in range(count):
            d=root/'diagnostic'/f'episode-{i:03d}';d.mkdir(parents=True)
            log=(d/'log.txt').open('w')
            cmd=[sys.executable,'-m','scripts.run_beampair1','--plan',str(args.plan.resolve()),
                '--episode',str(i),'--dependency-root',str(args.dependency_root.resolve()),'--out',str(d/'raw'),
                '--mode',MODE,'--candidate',args.candidate,'--cap-s','60']
            cmd += ['--rendezvous',args.rendezvous]
            process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
            children.append((process,d,log));write_json(d/'PROCESS.json',dict(pid=process.pid,command=cmd))
            if i<getattr(args,'first_episodes',0) or (i==0 and args.first_episode_first):
                code=process.wait()
                report_path=d/'adapter/beampair1-result.json'
                adapter=final_adapter_result(report_path)
                report=adapter['result'] if adapter else None
                if code or not report or not report['physical_success']:
                    stopped=True
                    write_json(root/'SUPERVISOR_STOP.json',dict(episode=d.name,reason='sentinel_seed_failed',exit=code))
                    break
        while any(p.poll() is None for p,d,l in children):
            failure=None
            for p,d,l in children:
                result=d/'adapter/beampair1-result.json'
                adapter=final_adapter_result(result)
                if adapter:
                    report=adapter['result']
                    if report and report['status'] in ('complete','HOST_ERROR') and not report['physical_success']:
                        failure=dict(episode=d.name,result=report['status'],reason=report.get('end_reason') or report.get('error') or 'teacher_failure')
                if p.poll() not in (None,0) and not adapter:
                    failure=dict(episode=d.name,result='HOST_ERROR',reason='nonzero_exit_before_adapter_result')
            if failure and not stopped:
                stopped=True;write_json(root/'SUPERVISOR_STOP.json',failure)
                for p,d,l in children:
                    if p.poll() is None:
                        write_json(d/'SUPERVISOR_STOP.json',failure);p.send_signal(signal.SIGINT)
            time.sleep(.25)
    except BaseException:
        for p,d,l in children:
            if p.poll() is None:p.send_signal(signal.SIGINT)
        raise
    finally:
        exits=[]
        for p,d,l in children:
            exits.append(dict(episode=d.name,exit=p.wait()));l.close()
        write_json(root/'batch-result.json',dict(exits=exits,supervisor_stopped=stopped,planned_N=count))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--dependency-root',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--candidate',choices=['baseline','soft'],default='baseline')
    p.add_argument('--rendezvous',choices=['off','peer_rendezvous_v1'],default='off')
    p.add_argument('--first-episode-first',action='store_true')
    p.add_argument('--first-episodes',type=int,choices=range(7),default=0,
                   help='Run this many leading regression sentinels serially before filling')
    run(p.parse_args())
