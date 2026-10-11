"""Seal metrics and explicit per-arm sources after C3 consumer repair."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from harness.python_source_closure import source_closure
from harness.pf_observation_consistency import ALPHA_ASSET
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--replays',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
root=Path.cwd();source=json.loads((a.replays/'corrected-source.json').read_text())['source_sha']
v=json.loads(a.input.read_text());paths=set(source_closure(root,['harness/zone_s3_consistent_runtime.py']))
paths.add(str(ALPHA_ASSET.relative_to(root)))
proof={}
for path in sorted(paths):
    data=(root/path).read_bytes()
    archived=subprocess.check_output(['git','show',source+':'+path])
    assert data==archived,path
    proof[path]=hashlib.sha256(data).hexdigest()
retained=json.loads((a.replays/'retained-source-proof.json').read_text());assert len(retained['receipts'])==14
receipts={}
for path in sorted(a.replays.glob('*/result.json')):
    r=json.loads(path.read_text());assert r.get('failure') is None and r.get('error') is None
    key=path.parent.name;digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if key in retained['receipts']:
        old=retained['receipts'][key];assert digest==old['sha256'] and str(path.resolve())==old['path']
        arm_source=old['source_sha']
    else:
        assert key.endswith('-effective_sqrt_alpha_v1') and not path.parent.is_symlink()
        arm_source=source
        state=json.loads((path.parent/'recovered-student-record.json').read_text())['localizers']
        for rid in ('r1','r2'):
            assert state[rid]['observation_consistency']['motion_noise_commands']>0
    receipts[key]=dict(source_sha=arm_source,path=str(path.resolve()),sha256=digest)
    if key.endswith('-effective_sqrt_alpha_v1'):
        if key.startswith('550'):
            receipts[key]['actual_consumer_audit']=r['audit']
        else:
            record=path.parent/'recovered-student-record.json'
            receipts[key]['consumer_record_sha256']=hashlib.sha256(record.read_bytes()).hexdigest()
            receipts[key]['actual_consumer_audit']={rid:state[rid]['observation_consistency'] for rid in ('r1','r2','r3')}
assert len(receipts)==16
v.update(replay_source_sha=source,runtime_source_sha256=proof,replay_receipts=receipts,
    mixed_replay_sources=True,retained_arms_equivalence=retained,
    ownmap_original_source_sha='5b33094635804662a8a604718aead132c420b5ba',
    numerical_repair='defer_unmeasured_v1',selection_metrics_unchanged=True)
with a.output.open('x') as f:f.write(json.dumps(v,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(sealed=str(a.output),runtime_files=len(proof),receipts=len(receipts),smoke_option=v['smoke_option'])))
