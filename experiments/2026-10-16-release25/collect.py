"""Mac: retrieve only completed summaries/bounded playback and verify stored SHA."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REMOTE = '/home/ugrp/ugrp-sim/ops-reviews/release25'


def remote(code):
    return json.loads(subprocess.check_output(['ssh', 'gcp2', 'python3', '-'], input=code.encode()))


def collect(config_name, label):
    code = f'''
from pathlib import Path
import json,hashlib
ops=Path({REMOTE!r});cfg=json.loads((ops/{config_name!r}).read_text());sha=cfg['source_sha']
analysis=ops/('release-'+cfg['stage']+'-analysis-'+sha[:8]);batch=ops/('release-'+cfg['stage']+'-'+sha[:8])
assert (batch/'DONE.json').is_file(), 'result still running'
mapping={{'summary.json':analysis/'summary-with-candidates.json',
 'rejection_table.json':analysis/'rejection_table-with-candidates.json',
 'population-funnels.json':analysis/'population-funnels.json',
 'candidate-funnels.json':analysis/'candidate-funnels.json',
 'config.json':ops/{config_name!r}, 'DONE.json':batch/'DONE.json',
 'first30.json':batch/'first30-speed.json','stop.json':batch/'SUPERVISOR_STOP.json'}}
print(json.dumps({{k:dict(remote=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
 for k,p in mapping.items() if p.is_file()}}))
'''
    inventory = remote(code)
    verified = []
    for suffix, spec in inventory.items():
        path = HERE/(label+'-'+suffix)
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            subprocess.run(['scp', '-q', 'gcp2:'+spec['remote'], str(path)], check=True)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == spec['sha256'], path
        verified.append(dict(local=str(path), local_sha256=digest, **spec, match=True))
    (HERE/(label+'-retrieval-verification.json')).write_text(json.dumps(verified, indent=2)+'\n')
    print(label, 'retrieved SHA PASS', len(verified))


if __name__ == '__main__':
    collect(sys.argv[1], sys.argv[2])
