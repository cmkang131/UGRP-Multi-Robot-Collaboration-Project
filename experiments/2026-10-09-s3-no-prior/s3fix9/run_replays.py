"""Finite, serial queue. Never take/release another branch's lock."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from scripts import agent_lock

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RAW = Path('/Users/changmin/projects/ugrp/outputs')
BRANCH = 'codex/s3-no-prior-smoke'
CASES = [('55001', 'ownmap', RAW/'goal-route-motion-audit-v1/seed55001'),
         ('55002', 'ownmap', RAW/'goal-route-motion-audit-v1/seed55002'),
         ('v149', 's3', RAW/'s3-sweep-b73ce193-s14201-v149'),
         ('v150', 's3', RAW/'s3-odometry-4c9eb3aa-s14201-v150')]


def main():
    p = argparse.ArgumentParser(); p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    if os.getpriority(os.PRIO_PROCESS, 0) != 0: raise ValueError('nice zero required')
    receipts = []
    deadline = time.monotonic()+12*3600
    for case, kind, raw in CASES:
        for arm in ('n100', 'n500', 'sensor100'):
            key = case+'-'+arm
            while True:
                held = agent_lock.status(agent_lock.DEFAULT_ROOT)
                if held is None:
                    try:
                        acquired = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch=BRANCH,
                            purpose='s3fix9 saved proposal '+key+'; physics0', pid=os.getpid(),
                            expected_minutes=35, timing_sensitive=True)
                        break
                    except RuntimeError: pass
                (a.output/'waiting.json').write_text(json.dumps(dict(case=key, at=time.time(), held=held))+'\n')
                if time.monotonic() > deadline: raise TimeoutError('finite shared-lock wait expired')
                time.sleep(30.)
            try:
                source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
                if source != a.expected_source_sha: raise ValueError('source changed during queue')
                command = [sys.executable, str(HERE/'replay.py'), '--kind', kind, '--raw', str(raw),
                    '--output', str(a.output/key), '--arm', arm]
                if kind == 'ownmap': command += ['--adapter', str(RAW/'s3fix6-20261010/egomap-adapter-5b330946')]
                print(json.dumps(dict(starting=key, source=source)), flush=True)
                with (a.output/(key+'.log')).open('x') as stream:
                    run = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=5400)
                receipts.append(dict(case=key, source=source, returncode=run.returncode))
                (a.output/'progress.json').write_text(json.dumps(receipts, indent=2)+'\n')
            finally:
                held = agent_lock.status(agent_lock.DEFAULT_ROOT)
                if held and held['pid'] == os.getpid() and held['branch'] == BRANCH:
                    released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
                    (a.output/(key+'-lock.json')).write_text(json.dumps(dict(acquired=acquired, released=released))+'\n')
            if run.returncode: raise RuntimeError('saved replay failed: '+key)
            print(json.dumps(dict(completed=key)), flush=True)


if __name__ == '__main__': main()
