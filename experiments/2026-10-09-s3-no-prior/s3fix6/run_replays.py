"""Finite 4-run x 4-option offline replay queue; one shared lock at a time."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from scripts import agent_lock
from harness.pf_observation_consistency import OPTIONS
ROOT=Path(__file__).resolve().parents[3]
RAW=Path('/Users/changmin/projects/ugrp/outputs')
HERE=Path(__file__).parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--retain-from',type=Path);a=p.parse_args()
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==a.expected_source_sha
    assert os.getpriority(os.PRIO_PROCESS,0)==0
    a.output.mkdir(parents=True,exist_ok=False)
    cases=[('55001',RAW/'goal-route-motion-audit-v1/seed55001','ownmap'),('55002',RAW/'goal-route-motion-audit-v1/seed55002','ownmap'),
        ('v149',RAW/'s3-sweep-b73ce193-s14201-v149','s3'),('v150',RAW/'s3-odometry-4c9eb3aa-s14201-v150','s3')]
    completed=[]
    if a.retain_from:
        from replay_equivalence import retained_proof
        proof=retained_proof(ROOT,a.retain_from)
        (a.output/'retained-source-proof.json').write_text(json.dumps(proof,indent=2)+'\n')
        for key in proof['receipts']:
            (a.output/key).symlink_to((a.retain_from/key).resolve(),target_is_directory=True)
        (a.output/'corrected-source.json').write_text(json.dumps(dict(source_sha=a.expected_source_sha))+'\n')
    for option in (OPTIONS[-1:] if a.retain_from else OPTIONS):
        for case,raw,kind in cases:
            key=case+'-'+option;out=a.output/key
            if a.retain_from and key in proof['receipts']:continue
            command=[sys.executable,str(HERE/f'replay_{kind}.py'),'--raw',str(raw),'--output',str(out),'--option',option]
            if kind=='ownmap':command+=['--adapter',str(RAW/'s3fix6-20261010/egomap-adapter-5b330946')]
            deadline=time.monotonic()+10800
            while True:
                try:
                    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s3-no-prior-smoke',
                        purpose='s3fix6 saved posterior comparison '+key+'; physics0; no speed claim',pid=os.getpid(),expected_minutes=20,timing_sensitive=False)
                    break
                except RuntimeError:
                    if time.monotonic()>=deadline:raise
                    time.sleep(1.)
            try:
                assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==a.expected_source_sha
                print(json.dumps(dict(starting=key,source=a.expected_source_sha)),flush=True)
                with (a.output/(key+'.log')).open('x') as log:
                    result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
            finally:
                released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
                (a.output/(key+'-lock.json')).write_text(json.dumps(dict(acquired=held,released=released))+'\n')
            completed.append(dict(case=case,option=option,returncode=result.returncode))
            (a.output/'progress.json').write_text(json.dumps(completed,indent=2)+'\n')
            if result.returncode:raise RuntimeError('REPLAY_FAILED '+key)
            print(json.dumps(dict(completed=key)),flush=True)
            # Release between finite jobs. Another queued owner may acquire;
            # it is never stopped or released by this driver.
            time.sleep(1.)
    print(json.dumps(dict(completed=len(completed),physics_runs=0)),flush=True)

if __name__=='__main__':main()
