from pathlib import Path
import json,urllib.request
base=Path('/Users/changmin/projects/ugrp/outputs/s4grip2-offline');rawroot=Path('/Users/changmin/projects/ugrp/outputs/oracle-runs');plan=json.loads(Path('experiments/2026-10-06-s4-llm/s4grip2/batch-plan.json').read_text());pairs=0;weldrows=0;labelcheck=0;mismatches=[]
for job in plan['runs']:
 rid=job['robot_id']
 for c in job['cases']:
  raw=rawroot/job['name']/'raw'/c['id'];frames=[json.loads(x) for x in (raw/f'robots/{rid}/frames.jsonl').read_text().splitlines()];labels=[json.loads(x) for x in (raw/'eval_only/labels.jsonl').read_text().splitlines()];contacts={}
  for line in (raw/'eval_only/contacts.jsonl').read_text().splitlines():
   row=json.loads(line);assert not row['active_weld_ids'];weldrows+=1;contacts[round(row['t'],8)]=row['contacts']
  setup=json.loads((raw/'eval_only/stage-setup.json').read_text());objects=setup['truth']['items'];obj=next(k for k in objects if ('cyan' in k if rid=='r3' else 'beam' in k))
  assert len(frames)==len(labels)==61
  for f,label in zip(frames,labels):
   assert round(f['sim_time'],8)==round(label['sim_time'],8)
   sides=[]
   for side in ('left','right'):
    finger=rid+'__'+side+'_finger'
    sides.append(any(co['dist_m']<=0 and finger in (co['geom1'],co['geom2']) and any((g or '').startswith('cargo_'+obj+'_') for g in (co['geom1'],co['geom2'])) for co in contacts[round(label['sim_time'],8)]))
   if sides!=label['finger_sides']:mismatches.append(dict(job=job['name'],case=c['id'],sim_time=label['sim_time'],pre_capture=sides,post_capture=label['finger_sides']))
   else:labelcheck+=1
  if job['variant']=='hold':
   peer=rawroot/job['name'].replace('-hold-','-loss-')/'raw'/c['id']
   for p in raw.glob('robots/*/commands.jsonl'):assert p.read_bytes()==(peer/p.relative_to(raw)).read_bytes()
   pairs+=1
r=dict(paired_command_sequences_identical=pairs,weld_off_samples=weldrows,independent_contact_label_rechecks=labelcheck,pre_post_capture_mismatches=mismatches,contact_proxy='distance<=0 named cargo/finger geometry; no force threshold',research_result=False)
(base/'boundary-verification.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
for media in json.loads((base/'tensorboard-verification.json').read_text())['media']:
 req=urllib.request.Request(media['url'].replace('/video/','/raw/'),headers={'Range':'bytes=0-127'})
 with urllib.request.urlopen(req) as resp:assert resp.status==206 and len(resp.read())==128
print('4 video byte ranges verified')
