"""Post-run views only; read completed source, never run simulation."""
import hashlib,json,subprocess,sys
from pathlib import Path
from collections import Counter
from urllib.parse import quote
BASE=Path('/Users/changmin/projects/ugrp/outputs/s4grip2-offline')
REPO=Path('/Users/changmin/projects/ugrp-wt/s4-llm')
SHARED=Path('/Users/changmin/projects/ugrp/outputs')
PYTHON='/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python'
SHA=json.loads((BASE/'admissions-r1.json').read_text())['source_sha']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
views=[]
for split in ('explore','confirm'):
 source=BASE/split/'report.json';report=json.loads(source.read_text())
 for rid in ('r1','r2','r3'):
  for policy in (['candidate','legacy'] if split=='confirm' and rid!='r3' else ['candidate']):
   eps=[e for e in report['episodes'] if e['robot_id']==rid]
   records=[e[policy] for e in eps if e.get(policy,{}).get('start_held')]
   fc=Counter()
   for row in records:fc.update(row['frame_counts'])
   loss=[r for r in records if r['actual_loss']];held=[r for r in records if not r['actual_loss']]
   scalars={'offline/planned_episodes':len(eps),'offline/qualified_episodes':len(records),'offline/actual_loss_episodes':len(loss),'offline/actual_hold_episodes':len(held),'offline/true_positive_episodes':sum(r['detected'] for r in loss),'offline/false_positive_hold_episodes':sum(r['false_alarm'] for r in held),'offline/premature_loss_alarms':sum(r['false_alarm'] for r in loss)}
   scalars.update({'offline/'+k:fc[k] for k in ('label_held','label_lost','true_positive','false_positive','false_negative','true_negative','held_unknown','lost_unknown')})
   delays=[r['delay_sim_s'] for r in loss if r['detected']]
   if delays:scalars['offline/max_delay_sim_s']=max(delays)
   commands=0;wall=0.;sim=0.
   for e in eps:
    raw=Path(e['raw']);r=json.loads((raw/'result.json').read_text());wall+=r['wall_s'];sim+=r.get('sim_s',0.)
    for p in raw.glob('robots/*/commands.jsonl'):commands+=sum(json.loads(x)['kind']!='initial_servo_command' for x in p.read_text().splitlines())
   name=f'{split}-{rid}-{policy}';view=BASE/'views'/name;view.mkdir(parents=True)
   data=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,research_result=False,offline_source=dict(path=str(source),sha256=digest(source)),offline_scalar_scope='frozen RGB diagnostic, evaluation-only contacts; frames correlated; S4 LLM untested',offline_scalars=scalars,case=rid,policy=policy,seed=f'{split}-paired',source_sha=SHA,outcome='CV_DIAGNOSTIC_ONLY',model_calls=0,commands=commands,wall_s=wall,sim_s=sim,hparam_metrics=['offline/true_positive_episodes','offline/false_positive_hold_episodes','result/model_calls'],texts={'evaluation/episodes':eps,'provenance/limits':'Fixed wrist and identical O initial setup; not incipient slip or S4 LLM performance. Runtime is sum of recorded trial durations, not batch wall clock. Legacy False mapped to loss diagnostically only.'})
   (view/'result.json').write_text(json.dumps(data,indent=2)+'\n');views.append(view)
snapshot=SHARED/'tensorboard/1010-s4grip2'
subprocess.run([PYTHON,'scripts/export_offline_audit.py',*[x for v in views for x in ('--source',str(v))],'--output',str(snapshot)],cwd=REPO,check=True)
tags=['offline/true_positive_episodes','offline/actual_loss_episodes','offline/false_positive_hold_episodes','offline/actual_hold_episodes','offline/max_delay_sim_s','result/wall_s','result/commands','result/model_calls']
url='http://127.0.0.1:6006/?pinnedCards='+quote(json.dumps([dict(plugin='scalars',tag=t) for t in tags],separators=(',',':')))+'&smoothing=0&runFilter='+quote('^1010-s4grip2/confirm-')+'#timeseries'
vp=SHARED/'tensorboard-view.json';view=json.loads(vp.read_text());view['s4grip2_20261010']=dict(snapshot=str(snapshot),pinned_tags=tags,url=url,hparams_visible_columns=['case','policy','outcome','source_sha'],scope='confirm candidate plus same-cohort legacy; explore saved separately',runs=['1010-s4grip2/'+v.name for v in views]);vp.write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')
(BASE/'tensorboard.json').write_text(json.dumps(view['s4grip2_20261010'],indent=2)+'\n')
print(url)
