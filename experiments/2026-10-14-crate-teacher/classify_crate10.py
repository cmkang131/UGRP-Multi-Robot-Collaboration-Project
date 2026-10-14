"""Evaluation classification; replay controller receives only saved visible inputs."""
import json,subprocess,math
from pathlib import Path
from collections import Counter
from harness.grasp_act_visible_world import VisibleWorld
from audit_crate10 import pinned
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_visible_route import constraints,free
from scripts.zone_teacher import PeerDisc
B=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs');O=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate10-audit');summary=[]
def load(p):
 data=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
 return [json.loads(l) for l in data.splitlines()] if '.jsonl' in p.name else json.loads(data)
for seed,sha in [(77969,'5644e3dd'),(77978,'bf31840f'),(77979,'bf31840f')]:
 p=B/f'crate-diag-{seed}-{sha}/raw';result=load(p/'result.json');g=[r for r in load(p/'eval-only.jsonl.zst') if r['stage']=='grasp'];roles=result['prefix']['assigned'];labs={r:load(p/f'teacher-{r}.jsonl.zst')[:len(g)] for r in roles}
 CrateGraspTeacher=pinned(result['source_sha'])
 ts={r:CrateGraspTeacher(r,e,labs[r][0]['applied_command']['pwm'],bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_reacquire_v1',approach_goal_set='approach_goal_set_v1',crate_lift_pose=result['crate_lift_pose']) for r,e in roles.items()};ms={r:VisibleWorld(r,e,profile=CRATE) for r,e in roles.items()};trace=[]
 for i,row in enumerate(g):
  now=row['t'];ws={r:ms[r].observe(row['visible_measurements'][r],now) for r in roles}
  for r,t in ts.items():t.prepare_signal(ws[r],now)
  for r,t in ts.items():
   w=ws[r];prev=t.phase;before=len(t.goal_set_log);t.skill_started=now-labs[r][i]['skill_elapsed_s'];cmd,done=t.step(w,now,permit_pick=row['pick_permits'][r],permit_lift=row['lift_permits'][r]);expected=labs[r][i]['clean_teacher_command'];assert cmd['pwm']==expected['pwm'] and cmd['wheels']==expected['wheels'] and t.phase==labs[r][i]['teacher_phase'],(seed,i,r,t.phase,labs[r][i]['teacher_phase'])
   cell={'t':now,'rid':r,'phase':t.phase,'visible':w['visibility'][r]['visible_probes'],'outcome':t.outcome}
   if w['beam'] is not None and cell['visible']>=5:
    radius,discs,rects=constraints(w,r,t.folded_ready,CRATE);pose,pt,heading,goal=t._geometry(w)
    cell.update(goal=goal,pose=pose,blockers={'peer':not free(goal,[d for d in discs if isinstance(d,PeerDisc)],[],radius),'wall':not free(goal,[],rects,radius),'cargo':not free(goal,[d for d in discs if not isinstance(d,PeerDisc)],[],radius)})
   if len(t.goal_set_log)>before:cell['plans']=t.goal_set_log[before:]
   if prev!=t.phase or 'plans'in cell or cell['outcome'] or (cell['visible']>=5 and any(cell.get('blockers',{}).values())):trace.append(cell)
   ms[r].issue(labs[r][i]['applied_command']);t.remember_applied(labs[r][i]['applied_command'])
 data={'seed':seed,'roles':roles,'ticks':len(g),'result_outcomes':result['prefix']['outcomes'],'diagnostics':{r:t.diagnostic() for r,t in ts.items()},'trace':trace}
 decoded=(json.dumps(data,indent=2)+'\n').encode(); encoded=subprocess.check_output(['zstd','-q','-c'],input=decoded); assert subprocess.check_output(['zstd','-dc'],input=encoded)==decoded
 (O/f'{seed}-baseline.json.zst').write_bytes(encoded)
 row={'seed':seed,'roles':roles,'outcomes':result['prefix']['outcomes'],'robots':{}}
 for r,t in ts.items():
  plans=[x for x in trace if x['rid']==r and 'plans'in x];blocked=[x for x in trace if x['rid']==r and any(x.get('blockers',{}).values())]
  row['robots'][r]={'phase':t.phase,'outcome':t.outcome,'blocked_goal_calls':t.blocked_goal_calls,'planner_calls':t.planner_calls,'plan_reason_counts':dict(Counter(c['reason'] for x in plans for q in x['plans'] for c in q['candidates'])),'first_blocked':blocked[:1],'first_failed_plan':next((x for x in plans if any(q['selected'] is None for q in x['plans'])),None),'search_log':t.search_log,'events':t.events}
 summary.append(row)
 print(seed,{r:{k:v for k,v in d.items() if k not in ('events','search_log','first_failed_plan','first_blocked')} for r,d in row['robots'].items()})
 print('first blocked',[(r,[{k:v for k,v in x.items() if k!='plans'} for x in d['first_blocked']]) for r,d in row['robots'].items()])
 print('events',{r:d['events'] for r,d in row['robots'].items()})
Path('experiments/2026-10-14-crate-teacher/crate10-analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
