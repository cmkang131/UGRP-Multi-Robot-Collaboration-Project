"""Finite serialized saved-input queue; source frozen, shared lock per case."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from scripts import agent_lock
from harness.pf_resampling_diversity import OPTIONS

HERE=Path(__file__).parent
ROOT=HERE.parents[2]
RAW=Path('/Users/changmin/projects/ugrp/outputs')
CASES=[('55001','ownmap',RAW/'goal-route-motion-audit-v1/seed55001'),
       ('55002','ownmap',RAW/'goal-route-motion-audit-v1/seed55002'),
       ('v149','s3',RAW/'s3-sweep-b73ce193-s14201-v149'),
       ('v150','s3',RAW/'s3-odometry-4c9eb3aa-s14201-v150')]


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    assert os.getpriority(os.PRIO_PROCESS,0)==0
    receipts=[]
    for option in OPTIONS:
        for case,kind,raw in CASES:
            key=case+'-'+option
            deadline=time.monotonic()+12*3600
            while True:
                try:
                    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s3-no-prior-smoke',
                        purpose='s3fix7 saved PF diversity '+key+'; physics0',pid=os.getpid(),expected_minutes=30)
                    break
                except RuntimeError:
                    if time.monotonic()>deadline:raise
                    time.sleep(1.)
            try:
                source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
                assert source==a.expected_source_sha
                command=[sys.executable,str(HERE/'replay.py'),'--kind',kind,'--raw',str(raw),
                    '--output',str(a.output/key),'--option',option]
                if kind=='ownmap':command+=['--adapter',str(RAW/'s3fix6-20261010/egomap-adapter-5b330946')]
                print(json.dumps(dict(starting=key,source=source)),flush=True)
                with (a.output/(key+'.log')).open('x') as f:
                    completed=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=5400)
            finally:
                released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
                (a.output/(key+'-lock.json')).write_text(json.dumps(dict(acquired=held,released=released))+'\n')
            receipts.append(dict(case=case,option=option,source=source,returncode=completed.returncode))
            (a.output/'progress.json').write_text(json.dumps(receipts,indent=2)+'\n')
            if completed.returncode:raise RuntimeError('REPLAY_FAILED '+key)
            print(json.dumps(dict(completed=key)),flush=True)
            time.sleep(1.)


if __name__=='__main__':main()
