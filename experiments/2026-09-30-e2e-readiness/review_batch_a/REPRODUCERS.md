# Batch A 재현 코드

실행용 원본과 로그의 로컬 보관 위치: `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-a-20260930-76c6a8fe`. 이 문서는 코드 예시이며 CI/실험 실행기에 등록하지 않았다. 각 코드는 아래 고정 Git archive에서 기존 Python·공용 잠금 아래 실행한다. 실제 결과 디렉터리는 대상으로 쓰지 않는다.

## P06

대상: `cbac1dfca5d0a1d8f18e4ff2633626d4cadf2af8`. archive 경로를 cwd와 `PYTHONPATH`로 지정한다.

```python
"""Synthetic evidence adversarial probes; no simulator or provider calls."""
import copy,json,pathlib,shutil,sys,tempfile
from tests.test_zone_study_evidence import run, synthetic_source, put, reseal, ev, tb
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

results={}
with tempfile.TemporaryDirectory(prefix='e2e-review303-') as work:
 root=pathlib.Path(work)
 src=synthetic_source(root,'success',run('no_comm',horizon=12.)[:2])
 baseline=json.loads((src/'study/trial_record.json').read_text())
 results['baseline_ids']={'raw_run_id':'success','trial_id':baseline['trial_id'],'scenario':baseline['scenario'],'seed':baseline['seed']}
 for case in ('foreign_identity','foreign_order_ids','missing_terminal','missing_image_refs'):
  path=root/case; shutil.copytree(src,path)
  record=json.loads((path/'study/trial_record.json').read_text())
  if case=='foreign_identity':
   record.update(trial_id='unrelated-trial',scenario='unrelated-scenario',seed=987654)
  elif case=='foreign_order_ids':
   for i,row in enumerate(record['orders']): row['order_id']=f'unrelated-order-{i}'
  elif case=='missing_terminal':
   result=json.loads((path/'result.json').read_text()); result.pop('terminal'); put(path,'result.json',result)
   manifest=json.loads((path/'manifest.json').read_text()); manifest.pop('terminal'); put(path,'manifest.json',manifest)
  elif case=='missing_image_refs':
   for row in record['request_archive']: row['image_refs']=[]
   for image in (path/'study/request_images').glob('*.jpg'): image.unlink()
  put(path,'study/trial_record.json',record); reseal(path)
  out=root/f'{case}-events'
  try:
   manifest=tb.convert(path,out,allow_synthetic=True,max_images=0)
   ea=EventAccumulator(str(out)).Reload()
   results[case]={'accepted':True,'success':ea.Scalars('evaluation/reported_success')[0].value,'run_id':manifest['metadata']['run_id'],'scenario':manifest['metadata']['case'],'seed':manifest['metadata']['seed'],'request_images_verified':manifest['metadata']['request_images_verified']}
  except Exception as exc:
   results[case]={'accepted':False,'type':type(exc).__name__,'error':str(exc)}
print(json.dumps(results,indent=2,ensure_ascii=False))
```

## P01 legacy

대상: `main c12796676802ab54cad2f0635e3e96e911691c76 및 #305 5a852fbfde3b0df836f3a423be29a774a9c54614`. archive 경로를 cwd와 `PYTHONPATH`로 지정한다.

```python
"""The existing dock route with a fake Scene factory; no construction/physics."""
import json,sys
from unittest.mock import patch
sys.modules['mujoco']=None
sys.modules['torch']=None
sys.modules['sim.multi_masterpi_production']=None
from sim.zone_dock_scene import DockTaggedCargoZoneScene
from sim.zone_start_dock import MAP_ID
from sim.zone_own_scene_provider import own_scene
spec={'map':MAP_ID,'seed':911,'goal':{'C':{'long_beam':1}},
      'team_cargo':[{'item_id':'team_beam','kind':'long_beam','pose':[0.,0.,0.]}]}
sentinel=object()
with patch.object(DockTaggedCargoZoneScene,'from_tagged_cargo',return_value=sentinel) as factory:
 try:
  result=own_scene(spec,'cargo_noslip_v1')
  outcome={'accepted':result is sentinel,'factory_calls':factory.call_count,'map':MAP_ID}
 except Exception as exc:
  outcome={'accepted':False,'factory_calls':factory.call_count,'map':MAP_ID,'exception':type(exc).__name__,'error':str(exc)}
print(json.dumps(outcome,indent=2))
```

## P01 and P292

대상: `merge-tree 2d5126c7aacd9918ddc4bd8c36650112cf1df4fb`. archive 경로를 cwd와 `PYTHONPATH`로 지정한다.

```python
"""Static candidate-hash mutation in disposable merge-tree archive only."""
import hashlib,json,pathlib,sys
sys.modules['mujoco']=None
sys.modules['torch']=None
sys.modules['sim.multi_masterpi_production']=None
from scripts.zone_pair_v6_contract import candidate_contract
from harness import zone_environment_registry as registry
before=candidate_contract('v6h')
p=registry.ROOT/registry.REGISTRY_FILE
original=p.read_bytes()
mid='zone_wide_door_tags_v2'
registry.resolve_static_map(mid)
try:
 data=json.loads(original); data['status']='INVALID_REVIEW_MUTATION'
 p.write_text(json.dumps(data))
 after=candidate_contract('v6h')
 try:
  registry.resolve_static_map(mid)
  refuses=False
 except ValueError as exc:
  refuses=str(exc)
 print(json.dumps({'candidate_same':before==after,'candidate_sources':len(before['source_sha256']),
  'registry_pinned':registry.REGISTRY_FILE in before['source_sha256'],
  'final_catalog_pinned':'maps/zones_final/catalog.json' in before['source_sha256'],
  'registry_source_module_pinned':'harness/zone_environment_registry.py' in before['source_sha256'],
  'valid_before':True,'after_resolver_error':refuses},indent=2))
finally:
 p.write_bytes(original)
 assert p.read_bytes()==original
```
