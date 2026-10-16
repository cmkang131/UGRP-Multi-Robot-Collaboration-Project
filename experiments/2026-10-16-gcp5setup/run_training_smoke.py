"""Launch one finite GPU smoke after complete installation and dataset SHA gate."""
import hashlib
import json
import subprocess
import time
from ops import ROOT, EVIDENCE

base = '/home/ugrp/ugrp-sim/setup'


def ssh(command):
    return subprocess.check_output(['ssh', 'gcp5', command], text=True)


assert ssh('cat '+base+'/install.EXIT').strip() == '0'
assert json.loads(ssh('cat '+base+'/dataset-verification.json'))['all_sha256_match']
freeze = ssh('cat '+base+'/act-freeze.txt')
assert set(freeze.splitlines()) == set((EVIDENCE/'act-freeze-reference.txt').read_text().splitlines())
assert ssh('sha256sum '+base+'/training_smoke.py').split()[0] == hashlib.sha256((ROOT/'training_smoke.py').read_bytes()).hexdigest()
command = ['ssh', 'gcp5', 'cd '+base+' && OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=4 '
           '/home/ugrp/ugrp-rl1b-act-env/bin/python training_smoke.py '+base+'/beamact3-reference '
           +base+'/training-smoke-v1 > training.log 2>&1']
started = time.time()
result = subprocess.run(command, capture_output=True, text=True)
(EVIDENCE/'training-command.json').write_text(json.dumps(dict(command=command,
    returncode=result.returncode, seconds=time.time()-started, stdout=result.stdout,
    stderr=result.stderr), indent=2)+'\n')
if result.returncode:
    print(ssh('tail -60 '+base+'/training.log'))
    raise RuntimeError('GPU smoke failed; original output retained')
ssh('cp '+base+'/training-smoke-v1/summary.json '+base+'/training-summary.json')
subprocess.run(['scp', 'gcp5:'+base+'/training-summary.json', 'gcp5:'+base+'/training.log',
                str(EVIDENCE)+'/'], check=True)
report = json.loads((EVIDENCE/'training-summary.json').read_text())
assert report['status'] == 'PASS' and report['steps_completed'] == 50 and report['readback_verified']
print(json.dumps(dict(status=report['status'], steps=report['steps_completed'],
                      save_reload=report['readback_verified'], wall_s=report['wall_s'])), flush=True)
