"""Read-only gcp2 per-world recount and original candidate/frame/event funnels."""
from collections import Counter
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from scripts.analyze_beampair1 import rejection_rows,candidate_funnels
from scripts.audit_beampair1 import read,read_bytes,ordered_funnel
root=Path(sys.argv[2]);out=Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=True)
reports=[];rejections=[];reasons=Counter();blockers=Counter();checked=0;bad=[]
paths=sorted(root.glob('p*/summary.json')) if list(root.glob('p*/summary.json')) else [root/'summary.json']
for p in paths:
 s=read(p)
 for rel,sha in s.get('sha256',{}).items():
  f=p.parent/rel;checked+=1
  if hashlib.sha256(f.read_bytes()).hexdigest()!=sha:bad.append(str(f))
 worlds=s.get('worlds',[])
 if not worlds:
  worlds=[dict(world=int(b.name.split('-')[1]),seed=read(b/'raw/plan.json')['seed'],physical_success=False,status='supervisor_stop') for b in p.parent.glob('world-*') if (b/'raw/plan.json').exists()]
 for w in worlds:
  base=p.parent/f"world-{w['world']:03d}";raw=base/'raw'
  if not (raw/'result.json').exists() and not (raw/'result.json.zst').exists():continue
  result=read(raw/'result.json');adapter=read(base/'adapter/beampair1-result.json');plan=read(raw/'plan.json')
  rows=rejection_rows(result)
  for row in rows:
   row.update(world=w['world'],job=str(p.parent),seed=w['seed']);reasons[row['reason_category']]+=1;blockers[row['blocked_object']]+=1
  rejections.extend(rows)
  content,_,_=read_bytes(raw/'eval-only.jsonl');frames=[json.loads(x) for x in content.splitlines() if x.strip()]
  n=len(frames)*2
  visible=sum(x['visibility'][rid]['visible_probes']>0 for x in frames for rid in ('r1','r2'))
  region=sum(x['visibility'][rid]['visible_probes']>=5 for x in frames for rid in ('r1','r2'))
  admitted=sum(any(m['id']=='band_'+plan['roles'][rid] for m in x.get('visible_measurements',{}).get(rid,[])) for x in frames for rid in ('r1','r2'))
  events=[{e.get('to') for e in t.get('events',[])} for t in result.get('teachers',{}).values()]
  reports.append(dict(job=str(p.parent),world=w,candidate_populations=candidate_funnels(result),
    frame_funnel=ordered_funnel(n,[('any_assigned_probe',visible),('meaningful_region_5_of_15',region),('measurement_admitted_not_held',admitted)]),
    event_funnel=ordered_funnel(2,[('own_ready',sum(bool(e&{'ready','pick','complete'}) for e in events)),('own_pick_after_go_ack',sum(bool(e&{'pick','complete'}) for e in events)),('own_command_complete',sum('complete' in e for e in events))]),
    held_world_reads=adapter['held_world_reads'],hidden_measurement_ticks=adapter['hidden_measurement_ticks'],raw=str(raw)))
(out/'rejections-full.json').write_text(json.dumps(rejections,indent=2)+'\n')
summary=dict(schema='ugrp.warp2.flow_recount.v1',raw=str(root),reports=reports,reason_distribution=dict(reasons),blocked_object_distribution=dict(blockers),
 sha256_check=dict(files=checked,mismatches=bad),full_rejections=str(out/'rejections-full.json'),
 full_rejections_sha256=hashlib.sha256((out/'rejections-full.json').read_bytes()).hexdigest(),
 scope='original frozen beampair6 reason definitions and sequential populations; successful or capped worlds do not remove rejected candidates',
 reproduce='python3 '+str(Path(__file__).resolve())+' '+' '.join(sys.argv[1:]))
(out/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(N=len(reports),checked=checked,bad=bad,reasons=dict(reasons))))
