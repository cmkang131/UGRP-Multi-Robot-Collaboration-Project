"""Export only committed training source to setup/, with original SHA/file hashes.

This is a setup reference archive, not a production src/<sha> checkout. Production
checkouts must use the shared Git reference via remote_run; no Git history is copied.
"""
import hashlib
import json
from pathlib import Path
import subprocess
from ops import EVIDENCE, ROOT

sha=subprocess.check_output(['git','rev-parse','codex/beamact3'],text=True).strip()
paths=['harness','scripts','experiments/2026-10-16-beamact3/train_shared.py']
reference='/home/ugrp/ugrp-sim/setup/beamact3-reference'
subprocess.run(['ssh','gcp5','mkdir '+reference],check=True)
a=subprocess.Popen(['git','archive',sha,*paths],stdout=subprocess.PIPE)
b=subprocess.Popen(['ssh','gcp5','tar -xf - -C '+reference],stdin=a.stdout)
a.stdout.close();bcode=b.wait();acode=a.wait()
assert not (acode or bcode)
files=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'--',*paths],text=True).splitlines()
hashes={name:hashlib.sha256(subprocess.check_output(['git','show',sha+':'+name])).hexdigest() for name in files}
provenance=dict(source_sha=sha,files_sha256=hashes,scope='committed training module reference, no history/keys/data')
(EVIDENCE/'training-source-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
subprocess.run(['scp',str(EVIDENCE/'training-source-provenance.json'),'gcp5:'+reference+'/source-provenance.json'],check=True)
subprocess.run(['scp',str(ROOT/'training_smoke.py'),'gcp5:/home/ugrp/ugrp-sim/setup/'],check=True)
print(json.dumps(dict(source_sha=sha,files=len(files),reference=reference)),flush=True)
