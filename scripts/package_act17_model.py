"""Stage completed ACT17 inference assets; stream deterministic ZIP without a disk copy.

No credentials or upload. Weight staging uses a same-filesystem hard link, and
every streamed file is checked against its registered full hash and length.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256,ACT_SHA,LEROBOT_ACT_SHA256
from act17_data import read
from act17_compact_records import original_sha256
from act17_v7 import ROOT,B


def stream_zip(stage,files,sink):
    with zipfile.ZipFile(sink,'w') as archive:
        for row in sorted(files,key=lambda r:r['path']):
            path=stage/row['path'];info=zipfile.ZipInfo(row['path'],(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
            h=hashlib.sha256();n=0
            with archive.open(info,'w') as target,path.open('rb') as source:
                while block:=source.read(1024**2):h.update(block);n+=len(block);target.write(block)
            if n!=row['bytes'] or h.hexdigest()!=row['sha256']:raise ValueError('staged file changed during ZIP stream')


class HashSink:
    def __init__(self):self.digest=hashlib.sha256();self.bytes=0
    def write(self,value):self.digest.update(value);self.bytes+=len(value);return len(value)
    def flush(self):pass


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    p.add_argument('--stream',type=Path,help='registered staging receipt; emit ZIP only on stdout')
    p.add_argument('--candidate',choices=['M','F','S'])
    for key in ['checkpoint','training-summary','dataset-manifest','protocol','out']:p.add_argument('--'+key,type=Path)
    a=p.parse_args()
    if not a.enabled:p.error('model staging/stream default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT)
    if a.stream:
        entry=read(a.stream)
        if entry.get('schema')!='ugrp.act17.stream_package.v1' or entry['packaging_source_sha']!=source:
            raise ValueError('exact clean registered streaming source required')
        stream_zip(Path(entry['staging']),entry['files'],sys.stdout.buffer);return
    if not a.candidate or any(getattr(a,k.replace('-','_')) is None for k in ['checkpoint','training-summary','dataset-manifest','protocol','out']):
        p.error('all staging inputs required')
    meta=read(a.checkpoint/'adapter.json');summary=read(a.training_summary);manifest=read(a.dataset_manifest);protocol=read(a.protocol)
    provenance=meta['provenance'];step=protocol['training']['steps_round1']
    if (meta.get('schema')!='ugrp.act17.adapter.v1' or provenance.get('candidate')!=a.candidate or provenance.get('cohort')!='act17-v7-native'
            or not provenance.get('training_complete') or provenance.get('step')!=step or not summary.get('complete')
            or not summary.get('readback_verified') or summary.get('checkpoint_sha256')!=sha256(a.checkpoint/'model.safetensors')
            or summary.get('source_sha')!=provenance.get('source_sha') or provenance.get('protocol_sha256')!=sha256(a.protocol)
            or provenance.get('dataset_manifest_sha256')!=original_sha256(a.dataset_manifest) or not manifest.get('complete')
            or provenance.get('lerobot_act_sha256')!=LEROBOT_ACT_SHA256):
        raise ValueError('complete matched model, data, protocol and actual readback proof required')
    hashes=read(a.checkpoint/'SHA256.json')
    if set(hashes)!={'model.safetensors','config.json','adapter.json'} or any(sha256(a.checkpoint/k)!=v for k,v in hashes.items()):
        raise ValueError('checkpoint inventory mismatch')
    a.out.mkdir(parents=True,exist_ok=False);stage=a.out/'staging';actor=stage/'act';actor.mkdir(parents=True)
    for name in ['model.safetensors','config.json','adapter.json','SHA256.json']:os.link(a.checkpoint/name,actor/name)
    inference=stage/'inference';library=inference/'act_library/harness';library.mkdir(parents=True)
    for name in ['grasp_act_contract.py','grasp_act_data.py','grasp_act_policy.py','grasp_act_loss.py']:
        shutil.copy2(B/'src'/ACT_SHA/'harness'/name,library/name)
    (library/'__init__.py').write_text('')
    training_source=B/'src'/provenance['source_sha'];frozen_source(training_source,provenance['source_sha'])
    for name in ['act17_policy.py','act17_data.py','act17_compact_records.py','act17_open_loop.py','act16w_runtime.py']:
        shutil.copy2(training_source/'scripts'/name,inference/name)
    # The normalizer/loss-compatible ACT file is hash-pinned by Actor.load.
    # Bundle its exact bytes so loading does not depend on an unpublished
    # modification to the existing environment. Other dependency versions are
    # recorded below; no installed package is modified by the bundle loader.
    from lerobot.policies.act import modeling_act
    runtime=inference/'runtime';runtime.mkdir()
    if sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256:raise ValueError('pinned ACT runtime changed')
    shutil.copy2(modeling_act.__file__,runtime/'modeling_act.py')
    distribution=importlib.metadata.distribution('lerobot')
    licenses=[distribution.locate_file(p) for p in distribution.files or [] if str(p).endswith('/licenses/LICENSE')]
    if len(licenses)!=1:raise ValueError('exact upstream runtime license required')
    shutil.copy2(licenses[0],runtime/'LICENSE.lerobot')
    loader="""import hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE/'act_library'))
import lerobot.policies.act as act_package
runtime=HERE/'runtime/modeling_act.py'
expected=json.loads((HERE.parent/'environment.json').read_text())['lerobot_ACT_file_sha256']
if hashlib.sha256(runtime.read_bytes()).hexdigest()!=expected:raise ValueError('bundled ACT runtime changed')
name='lerobot.policies.act.modeling_act'
spec=importlib.util.spec_from_file_location(name,runtime)
module=importlib.util.module_from_spec(spec);sys.modules[name]=module
act_package.modeling_act=module;spec.loader.exec_module(module)
import act17_data
act17_data.library=lambda: HERE/'act_library'
from act17_policy import Actor
actor=Actor.load(HERE.parent/'act',device='cpu')
from harness import grasp_act_contract as c
if not Path(c.__file__).resolve().is_relative_to(HERE.resolve()):raise ValueError('bundle inference library not used')
from lerobot.policies.act import modeling_act
if Path(modeling_act.__file__).resolve()!=runtime.resolve():raise ValueError('bundled ACT runtime not used')
print(json.dumps(dict(ready=True,device='cpu',image_mode=actor.image_mode,bundled_inference_library=True,bundled_act_runtime=True,scope='model loading only; not physical success')))
"""
    (inference/'load_model.py').write_text(loader)
    for file,name in [(a.protocol,'comparison-protocol.json'),(a.training_summary,'training-summary.json'),(a.dataset_manifest,'dataset-manifest.json')]:
        if file.exists():shutil.copy2(file,stage/name)
        else:shutil.copy2(Path(str(file)+'.zst'),stage/(name+'.zst'))
    environment=dict(python=sys.version,packages={k:importlib.metadata.version(k) for k in ['torch','torchvision','lerobot','numpy','Pillow','draccus','safetensors']},lerobot_ACT_file_sha256=LEROBOT_ACT_SHA256,bundled_ACT_runtime=True)
    (stage/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    (stage/'provenance.json').write_text(json.dumps(dict(training=provenance,ACT_library_source_sha=ACT_SHA,packaging_source_sha=source,
        packaging_host=host,original_checkpoint=str(a.checkpoint),contact_profile='warp_native_contact_v1',raw_dataset_backup_included=False,
        optimizer_state_saved=False,public_verification_pending=True),indent=2)+'\n')
    (stage/'README.md').write_text('# ACT17 v7 '+a.candidate+'\n\n실험용 단독 BOX 근거리 모델이며 기본 제어기가 아닙니다. 기존 고정 ACT 환경에서 `python inference/load_model.py`로 CPU 로딩합니다. 필수 추론 소스·설정·출처·해시는 함께 포함합니다. 로딩은 물리 임무 성공이나 raw 데이터 전체 백업을 뜻하지 않습니다.\n')
    files=[dict(path=str(f.relative_to(stage)),bytes=f.stat().st_size,sha256=sha256(f)) for f in sorted(stage.rglob('*')) if f.is_file()]
    sink=HashSink();stream_zip(stage,files,sink)
    model_id='act17-v7-native-r1-'+a.candidate.lower()+'-step'+str(step)+'-20261017';tag='models-20261017-act17-v7-r1';asset=model_id+'.zip';repo='cmkang131/UGRP-Multi-Robot-Collaboration-Project'
    entry=dict(schema='ugrp.act17.stream_package.v1',id=model_id,status='available',candidate=a.candidate,source_sha=provenance['source_sha'],
        packaging_source_sha=source,staging=str(stage),files=files,archive=dict(bytes=sink.bytes,sha256=sink.digest.hexdigest()),
        release=dict(tag=tag,asset=asset,url=f'https://github.com/{repo}/releases/download/{tag}/{asset}'),
        limitations=['experimental own-RGB BOX near-field only','loading and physical success separate','public verification pending'],verification=dict(state='PENDING'))
    with (a.out/'registry-entry.pending.json').open('x') as f:json.dump(entry,f,indent=2)
    print(json.dumps(dict(id=model_id,archive=entry['archive'],staging_hardlinks=True,archive_disk_copy=False)))


if __name__=='__main__':main()
