"""Stage a real readback-verified ACT16 model for a versioned Release asset.

No upload or credentials. Exact inference assets only; original checkpoints,
optimizer states and raw data stay on the host. Synthetic probes are rejected.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
from act16w_runtime import ACT_SHA,LEROBOT_ACT_SHA256,require_gcp2,frozen_source,sha256
from model_artifacts import pack

ROOT=Path(__file__).resolve().parents[1];B=Path('/home/ugrp/ugrp-sim')


def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')


def check_model(meta,summary,*,allow_incomplete=False):
    prov=meta['provenance'];step=prov.get('step')
    if prov.get('synthetic_only') or type(step) is not int or step<=0:
        raise ValueError('synthetic/untrained models cannot enter research Releases')
    if (summary.get('status')=='running' or summary.get('steps_completed')!=step
            or summary.get('readback_verified') is not True
            or prov.get('act_source_sha')!=ACT_SHA or prov.get('lerobot_act_sha256')!=LEROBOT_ACT_SHA256
            or summary.get('source_sha')!=prov.get('source_sha')
            or summary.get('dataset_manifest_sha256')!=prov.get('dataset_manifest_sha256')):
        raise ValueError('matching stopped model/summary and exact readback proof required')
    complete=step==10000 and summary.get('complete') is True
    if not complete and not allow_incomplete:raise ValueError('explicit incomplete comparison preservation required')
    return step,complete


def main():
    p=argparse.ArgumentParser();p.add_argument('--enabled',action='store_true');p.add_argument('--allow-incomplete',action='store_true')
    p.add_argument('--arm',choices=['A','B','C','D1'],required=True)
    for k in ('checkpoint','training-summary','dataset-manifest','protocol','out'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--tag',default='models-20261016-act16w-v1');a=p.parse_args()
    if not a.enabled:p.error('model staging default OFF')
    host=require_gcp2();source=frozen_source(ROOT);ACT=B/'src'/ACT_SHA;frozen_source(ACT,ACT_SHA)
    meta=read(a.checkpoint/'adapter.json');summary=read(a.training_summary)
    step,complete=check_model(meta,summary,allow_incomplete=a.allow_incomplete)
    dataset=read(a.dataset_manifest)
    if not dataset['complete'] or sha256(a.dataset_manifest)!=meta['provenance']['dataset_manifest_sha256']:
        raise ValueError('exact completed training dataset manifest required')
    if a.checkpoint.resolve()!=(Path(summary['last_checkpoint'])/'actor').resolve():raise ValueError('exact final saved actor required')
    training_source=B/'src'/meta['provenance']['source_sha'];frozen_source(training_source,meta['provenance']['source_sha'])
    hashes=read(a.checkpoint/'SHA256.json')
    if set(hashes)!={'model.safetensors','config.json','adapter.json'} or any(sha256(a.checkpoint/k)!=v for k,v in hashes.items()):raise ValueError('actor inventory changed')
    a.out.mkdir(parents=True,exist_ok=False);stage=a.out/'staging';stage.mkdir();actor=stage/'act';actor.mkdir()
    for name in ('model.safetensors','config.json','adapter.json','SHA256.json'):shutil.copy2(a.checkpoint/name,actor/name)
    inference=stage/'inference';library=inference/'act_library/harness';library.mkdir(parents=True)
    for name in ('grasp_act_contract.py','grasp_act_data.py','grasp_act_policy.py','grasp_act_loss.py'):shutil.copy2(ACT/'harness'/name,library/name)
    (library/'__init__.py').write_text('')
    for name in ('act16w_input.py','act16w_runtime.py'):shutil.copy2(training_source/'scripts'/name,inference/name)
    loader='''import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'act_library'))
from act16w_input import Act16wActor
p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,default=HERE.parent/'act');a=p.parse_args()
actor=Act16wActor.load(a.model_dir,device='cpu')
print(json.dumps(dict(ready=True,device='cpu',history_mode=actor.mode,scope='hash-checked model loading only; no physics success claim')))
'''
    (inference/'load_model.py').write_text(loader)
    shutil.copy2(a.protocol,stage/'comparison-protocol.json');shutil.copy2(a.training_summary,stage/'training-summary.json')
    shutil.copy2(a.dataset_manifest,stage/'dataset-manifest.json');write(stage/'native-camera.json',dataset['camera'])
    environment=dict(python=sys.version,packages={k:importlib.metadata.version(k) for k in ('torch','torchvision','lerobot','numpy','Pillow','draccus','safetensors')},lerobot_ACT_file_sha256=LEROBOT_ACT_SHA256)
    write(stage/'environment.json',environment)
    provenance=dict(arm=a.arm,step=step,registered_steps=10000,matched_arm_complete=complete,model_sha256=hashes['model.safetensors'],
        training_source_sha=meta['provenance']['source_sha'],ACT_library_source_sha=ACT_SHA,packaging_source_sha=source,packaging_host=host,
        dataset_manifest_sha256=meta['provenance']['dataset_manifest_sha256'],training_summary_sha256=sha256(a.training_summary),
        teacher_library_sha='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8',qualified_controller_sha='f0db6b1abb842ea65b71c433738210254f300a7c',
        record_API_upstream_sha='0362037280c6cbc4677f70366db43b9892b23690',record_host_schema_adapter_sha='813b9113b16e382712a00b911a9dcc7c06fbd77d',
        scope='experimental solo r1 BOX near-field grasp/release; no multi-robot/transport or legacy can/tile/crate capability claim; loading and task success are separate',
        public_redownload_and_loading_verified=False,original_checkpoint=str(a.checkpoint),optimizer_original_retained=True,raw_dataset_backup_included=False)
    write(stage/'provenance.json',provenance)
    (stage/'README.md').write_text('# ACT16 '+a.arm+' step'+str(step)+'\n\n실험 모델이며 기본 제어기가 아닙니다. '+('등록한10000스텝 학습 완료.' if complete else '8시간 예산 안의 미완료 비교 체크포인트 보존.')+'\n\n기존 고정 ACT 환경에서 `python inference/load_model.py`로 CPU 로딩을 확인합니다. 필수 패키지 버전은 environment.json, 원 학습/교사/데이터 해시는 provenance.json에 있습니다. 로딩 성공은 물리 임무 성공이 아닙니다. 이 ZIP은 가중치·필수 추론 소스·출처만 포함하며 raw 데이터나 optimizer 백업을 대체하지 않습니다.\n')
    model_id='act16w-'+a.arm.lower()+'-step'+str(step)+'-20261016';asset=model_id+'.zip';repo='cmkang131/UGRP-Multi-Robot-Collaboration-Project'
    row=dict(id=model_id,status='available',description='ACT16 '+a.arm+' experimental '+('10000-step model' if complete else 'incomplete comparison snapshot'),source_sha=meta['provenance']['source_sha'],training_source_sha=meta['provenance']['source_sha'],packaging_source_sha=source,
        release=dict(tag=a.tag,asset=asset,url=f'https://github.com/{repo}/releases/download/{a.tag}/{asset}'),
        files=[dict(path=str(f.relative_to(stage)),bytes=f.stat().st_size,sha256=sha256(f)) for f in sorted(stage.rglob('*')) if f.is_file()],
        limitations=['experimental; not a default controller','public re-download/hash/loading verification pending','matched10000 steps complete' if complete else 'incomplete matched comparison; not eligible for final40 evaluation'],
        verification=dict(state='PENDING',scope='no deployment or task-success claim before public checks'))
    archive=pack(row,stage,a.out/asset);row['archive']={k:archive[k] for k in ('sha256','bytes')}
    write(a.out/'registry-entry.pending.json',row);write(a.out/'package-summary.json',dict(status='staged_not_uploaded',registry_entry=str(a.out/'registry-entry.pending.json'),archive=archive,synthetic=False,complete_training=complete))
    print(json.dumps(dict(status='staged_not_uploaded',id=model_id,archive=archive)))


if __name__=='__main__':main()
