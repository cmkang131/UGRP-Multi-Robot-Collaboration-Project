"""Finite four-job Oracle submission; read-only unless --submit is explicit.

No SSH key/API secret handling. oracle_run.sh ships committed HEAD and owns
status/fetch. Only exit 3 (memory admission refusal) is retried, at 30 s, with
the unchanged argv/SHA. A run's nonzero exit is never automatically retried.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time

from scripts.run_s4_pair_preparation import ROOT, validate_release

PLAN = ROOT/'experiments/2026-10-06-s4-llm/s4live4/batch-plan.json'
RELEASE = ROOT/'experiments/2026-10-06-s4-llm/s4live4/release.json'


def commands(sha):
    data = json.loads(PLAN.read_text())
    if len(data['runs']) != 4 or data['max_concurrent'] > 6:
        raise ValueError('frozen four-condition batch required')
    return [(r['name'], [s.replace('<S4_SHA>', sha) for s in r['argv']]) for r in data['runs']]


def submit_one(runner, root, name, argv, *, invoke=subprocess.run, wait=time.sleep):
    command = [str(runner), str(root), name, '--', *argv]
    env = {**os.environ, 'ORACLE_HOST':'oracle-x86'}
    for attempt in range(120):  # finite <1 h admission wait, never background monitoring
        result = invoke(command, env=env, capture_output=True, text=True)
        if result.returncode != 3:
            return dict(name=name, argv=argv, admission_attempts=attempt+1, returncode=result.returncode,
                        stdout=result.stdout, stderr=result.stderr)
        if attempt < 119: wait(30.)
    return dict(name=name, argv=argv, admission_attempts=120, returncode=3,
                status='MEMORY_ADMISSION_BLOCKED_NOT_SIM_FAILURE')


def stage_source(sha):
    """Finish one archive transfer before concurrent helpers check the shared SHA directory."""
    # sha comes only from git rev-parse; all remote paths here are task-owned.
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('full source SHA required')
    command = (f'set -e; cd ~/ugrp-sim; test ! -e src/{sha}; '
               f'mkdir src/s4live4-{sha}; tar xf - -C src/s4live4-{sha}; '
               f'ln -s ~/ugrp-sim/ugrp/.venv-sim src/s4live4-{sha}/.venv-sim; '
               f'mv src/s4live4-{sha} src/{sha}')
    archive=subprocess.Popen(['git','archive','--format=tar',sha],cwd=ROOT,stdout=subprocess.PIPE)
    try:
        result=subprocess.run(['ssh','oracle-x86',command],stdin=archive.stdout)
        archive.stdout.close()
        if archive.wait() or result.returncode:
            raise RuntimeError('source staging failed; no batch submitted; preserve staging directory for inspection')
    finally:
        if archive.poll() is None:
            archive.terminate(); archive.wait()


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--oracle-runner', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--submit', action='store_true')
    a=p.parse_args(argv)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    rows=commands(sha)
    if not a.submit:
        print(json.dumps(dict(submitted=False, source_sha=sha, runs=rows), indent=2)); return 0
    validate_release(json.loads(RELEASE.read_text()))
    if not a.oracle_runner or not a.oracle_runner.is_file() or not a.output or a.output.exists():
        raise ValueError('existing oracle runner and new local result path required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('commit the complete frozen batch first')
    release=json.loads(RELEASE.read_text())
    subprocess.run(['git','merge-base','--is-ancestor',release['s3_source_sha'],sha],cwd=ROOT,check=True)
    # Receipt contains hashes/identity only; no key or credential goes to Oracle.
    subprocess.run(['ssh','oracle-x86','test -r ~/ugrp-sim/s4live4-relay.json'],check=True)
    for name, _ in rows:
        subprocess.run(['ssh','oracle-x86',f'test ! -e ~/ugrp-sim/runs/{name}'],check=True)
    stage_source(sha)
    # Four submissions at once, not one experiment followed by a code change.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(submit_one,a.oracle_runner,ROOT,name,cmd) for name,cmd in rows]
        results=[f.result() for f in futures]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        json.dump(dict(source_sha=sha, research_result=False, admissions=results),f,indent=2)
    return int(any(r['returncode'] for r in results))


if __name__=='__main__': raise SystemExit(main())
