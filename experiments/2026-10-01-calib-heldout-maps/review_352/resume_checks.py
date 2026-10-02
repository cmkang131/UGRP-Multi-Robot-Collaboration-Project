"""Finish PR352's interrupted review in a disposable candidate archive only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

archive = Path(sys.argv[1]).resolve()
evidence = Path(sys.argv[2]).resolve()
assert archive.is_relative_to(Path('/private/tmp'))
assert (archive/'harness/zone_final_pair_heldout.py').is_file()
evidence.mkdir(parents=True, exist_ok=True)
python = '/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python'
# All selected tests use fake backends. Also deny accidental shared-output access
# in this process; no inherited GIT_DIR may redirect test Git writes to the host.
guarded = '''import os,sys
shared='/Users/changmin/projects/ugrp/outputs'
def guard(event,args):
    if event in ('open','os.listdir','os.scandir','os.mkdir','os.remove','os.rmdir','os.rename'):
        for arg in args[:2]:
            if isinstance(arg,(str,bytes)):
                path=os.path.abspath(os.fsdecode(arg))
                if path==shared or path.startswith(shared+'/'):
                    raise RuntimeError('review must not access shared outputs: '+event)
sys.addaudithook(guard)
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
'''
env={k:v for k,v in os.environ.items() if k not in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR')}
env['PYTHONDONTWRITEBYTECODE']='1'
rows=[]
def run(name, tests):
    cmd=[python,'-c',guarded,'-q','-rx','-p','no:cacheprovider',*tests,
         '--basetemp',str(archive/'resume-tmp'/name),'--junitxml',str(evidence/(name+'.xml'))]
    (archive/'resume-tmp').mkdir(exist_ok=True)
    with (evidence/(name+'.log')).open('w') as log:
        p=subprocess.run(cmd,cwd=archive,env=env,stdout=log,stderr=subprocess.STDOUT)
    log=evidence/(name+'.log')
    row={'name':name,'tests':tests,'exit_code':p.returncode,
         'summary':log.read_text().splitlines()[-1],
         'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
    rows.append(row)
    (evidence/'resume-runs.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    return p.returncode
assert run('candidate', ['tests/test_zone_final_pair_heldout.py','tests/test_review_352.py'])==0
h='harness/zone_final_pair_heldout.py'; j='configs/zone_final_pair_v90.json'
original={p:(archive/p).read_bytes() for p in (h,j)}
try:
    for p,raw in original.items():
        assert raw.count(b'HELD_OUT_VALIDATION')==1
        (archive/p).write_bytes(raw.replace(b'HELD_OUT_VALIDATION',b'TRAINING'))
    run('training-label-mutation',['tests/test_zone_final_pair_heldout.py'])
    run('training-label-independent',['tests/test_review_352.py::test_literal_heldout_role_in_plan_bundle_and_fake_result'])
finally:
    for p,raw in original.items(): (archive/p).write_bytes(raw)
    assert all((archive/p).read_bytes()==raw for p,raw in original.items())
    (evidence/'mutation-restoration.json').write_text(json.dumps({p:hashlib.sha256(raw).hexdigest() for p,raw in original.items()},indent=2)+'\n')
