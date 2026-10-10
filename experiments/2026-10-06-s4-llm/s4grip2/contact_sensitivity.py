from pathlib import Path
import json
from scripts.evaluate_s4_grip_dataset import score
base=Path('/Users/changmin/projects/ugrp/outputs/s4grip2-offline');changed=[]
for split in ('explore','confirm'):
 for e in json.loads((base/split/'report.json').read_text())['episodes']:
  raw=Path(e['raw']);rid=e['robot_id'];prefix='cargo_'+('cyan_1' if rid=='r3' else 'beam_1')+'_'
  contacts={round(r['t'],8):r['contacts'] for r in map(json.loads,(raw/'eval_only/contacts.jsonl').read_text().splitlines())}
  labels=[]
  for l in map(json.loads,(raw/'eval_only/labels.jsonl').read_text().splitlines()):
   cs=contacts[round(l['sim_time'],8)];sides=[any(c['dist_m']<=0 and rid+'__'+side+'_finger' in (c['geom1'],c['geom2']) and any((g or '').startswith(prefix) for g in (c['geom1'],c['geom2'])) for c in cs) for side in ('left','right')]
   labels.append(dict(sim_time=l['sim_time'],label='held' if all(sides) else 'partial' if any(sides) else 'zero'))
  preds=[r['prediction'] for r in map(json.loads,(base/split/(e['job']+'-'+e['case']['id']+'.jsonl')).read_text().splitlines())]
  q=score(labels,preds);keys=['start_held','actual_loss','onset_frame','alarm_frame','detected','false_alarm','delay_frames','delay_sim_s']
  diffs={k:dict(pre_capture=q[k],post_capture=e['candidate'][k]) for k in keys if q[k]!=e['candidate'][k]}
  if diffs:changed.append(dict(job=e['job'],case=e['case']['id'],differences=diffs))
p=base/'boundary-verification.json';r=json.loads(p.read_text());r.update(pre_capture_label_sensitivity_episode_changes=changed,confirmation_label_match='732/732',primary_label_position='after capture; render refresh invokes mj_forward without advancing SIM clock')
p.write_text(json.dumps(r,indent=2)+'\n');print(changed)
