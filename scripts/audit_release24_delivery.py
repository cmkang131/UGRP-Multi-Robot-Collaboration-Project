"""VM-only release24 delivery audit, never a controller input."""
from pathlib import Path
from collections import Counter
import json,subprocess,hashlib,statistics,sys
from PIL import Image
R=Path('/home/ugrp/ugrp-sim');O=R/'ops-reviews/release24'
def read(p):
 if not p.exists():p=p.with_suffix(p.suffix+'.zst')
 return json.loads(subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes())
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
current=read(O/'round2-current/summary.json');table=read(O/'round2-current/rejection_table.json');inputs=[]
for r in current['runs']:
 raw=Path(r['remote_raw'])/'raw';d=read(raw/'result.json');seen=set();n=0
 def visit(x):
  global n
  if isinstance(x,dict):
   if 'input_jpeg' in x and 'input_sha256' in x:
    p=raw/x['input_jpeg'];assert p.resolve().is_relative_to(raw.resolve());assert hashlib.sha256(p.read_bytes()).hexdigest()==x['input_sha256']
    with Image.open(p) as im:assert im.size==(640,480);im.verify()
    seen.add(str(p))
   for v in x.values():visit(v)
  elif isinstance(x,list):
   for v in x:visit(v)
 visit(d.get('lookaround_result',{}))
 for x in d.get('regrasp_input_frames',[]):
  p=raw/x['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
  with Image.open(p) as im:assert im.size==(640,480);im.verify()
  seen.add(str(p))
 inputs.append(dict(run=r['name'],verified_native_input_N=len(seen),dimensions=[640,480],source_result_sha256=r['raw_result_sha256']))
 r['native_inputs_verified']=len(seen)
 r['localization_epoch_views']={rid:v['localizer']['decision'].get('observation_epoch_views') for rid,v in d['lookaround_result'].items()}
 r['failure_rgb_recording']=d['failure_rgb_recording']
prior=[]
for label,p in [('fusion',O/'round1-fusion/summary.json'),('gated',O/'round1-gated-corrected/summary.json')]:
 d=read(p);prior.append(dict(candidate=label,round=1,source_sha=d['source_sha'],counts=d['counts'],classification_counts=d['classification_counts'],runs=d['runs'],summary=ref(p)))
# Keep original diagnostic categories with object and minimum gap, not counts alone.
records=[dict(run=r['name'],**e) for r in current['runs'] for e in r['rejection_ledger']]
table.update(schema='ugrp.release24.rejections.v2',native_input_funnel=[dict(gate='recorded_control_RGB',cumulative_passed=sum(x['verified_native_input_N'] for x in inputs),rejected=0),dict(gate='declared_sha256_native_size_JPEG_decode',cumulative_passed=sum(x['verified_native_input_N'] for x in inputs),rejected=0)],rejection_records=records,prior_stage_tables=[ref(O/'round1-fusion/rejection_table.json'),ref(O/'round1-gated-corrected/rejection_table.json')],prior_result_scope='Independent variants/rounds; never pool rates; missing interrupted choice logs are not zero events.',raw_input_verification=inputs)
current.update(schema='ugrp.release24.delivery.v1',round=2,selected_axis_candidate='current',prior_stages=prior,
 native_input_verification=inputs,input_audit_scope='release judgment only; prefix scene preparation excluded',
 false_final_accepts=sum(r['false_final_accepts'] for r in current['runs']),
 first30_wall_per_sim_median=statistics.median(r['first30']['wall_per_sim'] for r in current['runs']),
 physical_robot_verified=False,recording_or_training_started=False,gate40_executed=False,
 methods=['same-round scalar CI mean','current set-down epoch own RGB global localization'],
 caps_unchanged=dict(margin_m=.04,axis_deg=10,yaw_deg=18,episode_sim_s=180,max_corrections=3,weld='off'),
 reproduce='cd /home/ugrp/ugrp-sim/src/8b7f2f4517d827b39a79246b892fa549bbcec0a8 && PYTHONPATH=. .venv-sim/bin/python /home/ugrp/ugrp-sim/ops-reviews/release24/deliver_remote.py')
(O/'delivery-full.json').write_text(json.dumps(current,indent=2)+'\n');(O/'rejection_table.json').write_text(json.dumps(table,indent=2)+'\n')
for p in (O/'delivery-full.json',O/'epoch-replay.json',O/'axis-samples.json'):
 subprocess.run(['zstd','-q','-f',str(p),'-o',str(p)+'.zst'],check=True)
# A small summary for Mac/repo, every run retained with source/hash/outcome.
keys=('name','seed','source_sha','classification','status','success','outcome','sim_s','release_sim_s','iterations','shift_steps','input_audit','evaluation_position_error','false_final_accepts','execution_profile','remote_raw','raw_result_sha256','raw_manifest_sha256','full_original_manifest_verified','frame_decode_verified_N','native_inputs_verified','localization_epoch_views','failure_rgb_recording')
small={k:v for k,v in current.items() if k not in ('runs','prior_stages')};small['runs']=[{k:r[k] for k in keys if k in r} for r in current['runs']]
small['prior_stages']=[dict(s,runs=[{k:r[k] for k in keys if k in r} for r in s['runs']]) for s in prior]
small['full_analysis']=ref(O/'delivery-full.json.zst');small['rejection_table']=str(O/'rejection_table.json');small['rejection_table_sha256']=hashlib.sha256((O/'rejection_table.json').read_bytes()).hexdigest()
(O/'summary.json').write_text(json.dumps(small,indent=2)+'\n');assert (O/'summary.json').stat().st_size<65536
print(json.dumps(dict(counts=small['counts'],verified=small['verified'],failure_seeds_solved=small['failure_seeds_solved'],input_RGB=sum(i['verified_native_input_N'] for i in inputs),false_final_accepts=small['false_final_accepts'])))
