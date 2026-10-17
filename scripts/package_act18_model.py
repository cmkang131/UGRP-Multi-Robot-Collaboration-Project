"""Stage and hash-stream ACT18 inference assets; no credentials or upload."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256,ACT_SHA,LEROBOT_ACT_SHA256
from act17_data import library,read
from act17_compact_records import original_sha256
from package_act17_model import stream_zip,HashSink

B=Path('/home/ugrp/ugrp-sim')
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--stream',type=Path)
    for key in ('checkpoint','training-summary','dataset-manifest','protocol','training-source','out'):
        p.add_argument('--'+key,type=Path)
    a=p.parse_args()
    if not a.enabled:
        p.error('model packaging default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT);library()
    if a.stream:
        entry=read(a.stream)
        if entry.get('schema')!='ugrp.act18.stream_package.v1' or entry['packaging_source_sha']!=source:
            raise ValueError('registered immutable streaming source required')
        stream_zip(Path(entry['staging']),entry['files'],sys.stdout.buffer)
        return
    if any(getattr(a,k) is None for k in ('checkpoint','training_summary','dataset_manifest','protocol','training_source','out')):
        p.error('all staging inputs required')
    meta,summary,protocol=read(a.checkpoint/'adapter.json'),read(a.training_summary),read(a.protocol)
    provenance=meta['provenance']
    frozen_source(a.training_source,provenance['source_sha'])
    if (meta.get('schema')!='ugrp.act18.adapter.v1' or not provenance.get('training_complete')
            or provenance.get('packaging_eligible') is False
            or provenance.get('step')!=protocol['steps'] or protocol['steps']!=100000
            or not summary.get('complete') or not summary.get('readback_verified')
            or summary.get('checkpoint_sha256')!=sha256(a.checkpoint/'model.safetensors')
            or provenance.get('protocol_sha256')!=sha256(a.protocol)
            or provenance.get('dataset_manifest_sha256')!=original_sha256(a.dataset_manifest)):
        raise ValueError('complete actual100k model/readback/data provenance required')
    hashes=read(a.checkpoint/'SHA256.json')
    if set(hashes)!={'model.safetensors','config.json','adapter.json'} or any(sha256(a.checkpoint/k)!=v for k,v in hashes.items()):
        raise ValueError('checkpoint inventory changed')
    a.out.mkdir(parents=True,exist_ok=False);stage=a.out/'staging';actor=stage/'act';actor.mkdir(parents=True)
    for name in ('model.safetensors','config.json','adapter.json','SHA256.json'):
        os.link(a.checkpoint/name,actor/name)
    inference=stage/'inference';lib=inference/'act_library/harness';lib.mkdir(parents=True)
    for name in ('grasp_act_contract.py','grasp_act_data.py','grasp_act_policy.py','grasp_act_loss.py'):
        shutil.copy2(B/'src'/ACT_SHA/'harness'/name,lib/name)
    (lib/'__init__.py').write_text('')
    for name in ('act18_policy.py','act17_policy.py','act17_data.py','act17_compact_records.py','act17_open_loop.py','act16w_runtime.py'):
        shutil.copy2(a.training_source/'scripts'/name,inference/name)
    from lerobot.policies.act import modeling_act
    runtime=inference/'runtime';runtime.mkdir()
    if sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256:
        raise ValueError('pinned ACT runtime changed')
    shutil.copy2(modeling_act.__file__,runtime/'modeling_act.py')
    distribution=importlib.metadata.distribution('lerobot')
    licenses=[distribution.locate_file(p) for p in distribution.files or [] if str(p).endswith('/licenses/LICENSE')]
    if len(licenses)!=1:
        raise ValueError('exact LeRobot license required')
    shutil.copy2(licenses[0],runtime/'LICENSE.lerobot')
    loader='''import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE/'act_library'))
import lerobot.policies.act as act_package
runtime=HERE/'runtime/modeling_act.py'
expected=json.loads((HERE.parent/'environment.json').read_text())['lerobot_ACT_file_sha256']
if hashlib.sha256(runtime.read_bytes()).hexdigest()!=expected:raise ValueError('runtime hash changed')
name='lerobot.policies.act.modeling_act'
spec=importlib.util.spec_from_file_location(name,runtime)
module=importlib.util.module_from_spec(spec);sys.modules[name]=module
act_package.modeling_act=module;spec.loader.exec_module(module)
import act17_data
act17_data.library=lambda: HERE/'act_library'
from act18_policy import Actor
actor=Actor.load(HERE.parent/'act',device='cpu')
from harness import grasp_act_contract as c
if not Path(c.__file__).resolve().is_relative_to(HERE.resolve()):raise ValueError('bundled input contract not used')
from lerobot.policies.act import modeling_act
if Path(modeling_act.__file__).resolve()!=runtime.resolve():raise ValueError('bundled runtime not used')
print(json.dumps(dict(ready=True,device='cpu',chunk=actor.chunk,bundled_inference_library=True,bundled_act_runtime=True,scope='model loading only; no physical success claim')))
'''
    (inference/'load_model.py').write_text(loader)
    for file,name in ((a.protocol,'comparison-protocol.json'),(a.training_summary,'training-summary.json'),(a.dataset_manifest,'dataset-manifest.json')):
        shutil.copy2(file if file.exists() else Path(str(file)+'.zst'),stage/(name if file.exists() else name+'.zst'))
    environment=dict(python=sys.version,packages={k:importlib.metadata.version(k) for k in ('torch','torchvision','lerobot','numpy','Pillow','draccus','safetensors')},lerobot_ACT_file_sha256=LEROBOT_ACT_SHA256)
    (stage/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    (stage/'provenance.json').write_text(json.dumps(dict(training=provenance,packaging_source_sha=source,host=host,
        ACT_library_source_sha=ACT_SHA,raw_dataset_backup_included=False,public_verification_pending=True),indent=2)+'\n')
    (stage/'README.md').write_text('# ACT18 '+provenance['candidate']+'\n\n실험용 자기 RGB BOX 근거리 ACT100k. `python inference/load_model.py`는 고정 ACT 환경에서 bundled CPU 로딩을 확인합니다. 실제 임무 성공 및 전체 학습자료 백업은 별도입니다.\n')
    files=[dict(path=str(f.relative_to(stage)),bytes=f.stat().st_size,sha256=sha256(f)) for f in sorted(stage.rglob('*')) if f.is_file()]
    sink=HashSink();stream_zip(stage,files,sink)
    model_id='act18-v7-'+provenance['candidate'].lower()+'-step100000-20261017'
    tag='models-20261017-act18-v7-r1';asset=model_id+'.zip';repo='cmkang131/UGRP-Multi-Robot-Collaboration-Project'
    entry=dict(schema='ugrp.act18.stream_package.v1',id=model_id,status='available',candidate=provenance['candidate'],
        source_sha=provenance['source_sha'],packaging_source_sha=source,staging=str(stage),files=files,
        archive=dict(bytes=sink.bytes,sha256=sink.digest.hexdigest()),
        release=dict(tag=tag,asset=asset,url=f'https://github.com/{repo}/releases/download/{tag}/{asset}'),
        limitations=['experimental own-RGB BOX near-field only','loading and physical success separate','public verification pending'],
        verification=dict(state='PENDING'))
    with (a.out/'registry-entry.pending.json').open('x') as f:
        json.dump(entry,f,indent=2);f.write('\n')
    print(json.dumps(dict(id=model_id,archive=entry['archive'],archive_disk_copy=False)))


if __name__=='__main__':
    main()
