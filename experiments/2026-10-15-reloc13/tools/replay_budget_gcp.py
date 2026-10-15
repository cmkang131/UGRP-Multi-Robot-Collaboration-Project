from pathlib import Path
from scripts.analyze_reloc11_selfmap import rows
import math,json,hashlib
root=Path('/home/ugrp/ugrp-sim/runs');values=[];files=[]
for p in sorted(root.glob('solo-carry-*-rotation-987d033f')):
 commands=rows(p/'raw/teacher-commands.jsonl');evals={round(r['t'],5):r for r in rows(p/'raw/eval-only.jsonl')}
 for r in commands:
  if False:continue
  m=r.get('map_pose',{});e=evals.get(round(r['t'],5),{});s=m.get('sigma_m_m_rad');turn=m.get('issued_turn_since_fix_rad')
  if not s or turn is None or e.get('map_pose_error_yaw_rad') is None:continue
  epoch=m.get('partial_budget_epoch',[0,0]);effective=turn-epoch[1];old=m.get('rotation_error_fraction',.4920507586142564)
  new=s[2]-(old-.29)*effective
  values.append(dict(run=p.name,t=r['t'],new_deg=math.degrees(new),old_deg=math.degrees(s[2]),true_deg=abs(math.degrees(e['map_pose_error_yaw_rad']))))
 for file in (p/'raw/teacher-commands.jsonl.zst',p/'raw/eval-only.jsonl.zst'):
  if file.exists():files.append(dict(path=str(file),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
positive=[r for r in values if r['true_deg']>=20]
minimum=min(r['new_deg'] for r in positive)
trigger=math.floor(minimum) # largest whole-degree trigger preserving all observed >=20deg errors
j=dict(basis='const-audit C1+C3, all phases, unique rotation runs; subtract changed fraction only over logged partial epoch; 20deg evaluator criterion unchanged',fraction=.29,N=len(values),positive_N=len(positive),minimum_positive_new_budget_deg=minimum,trigger_deg=trigger,recall=sum(r['new_deg']>=trigger for r in positive)/len(positive),fire_N=sum(r['new_deg']>=trigger for r in values),in_sample=True,holdout_required=True,sources=files)
Path('/tmp/reloc13-budget-fit.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({k:v for k,v in j.items() if k!='sources'}))
