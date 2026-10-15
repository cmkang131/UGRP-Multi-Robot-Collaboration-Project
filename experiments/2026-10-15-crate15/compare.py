"""Teacher-forced saved-input comparisons, never counterfactual physics success.

Every candidate goal is retested. Route failures are retested with the same
visible input. Fine control is probed from the exact baseline teacher state,
then discarded; the next baseline state still follows the ORIGINAL command.
"""
import json, math, sys
from pathlib import Path
from collections import Counter
from copy import deepcopy
from replay import RAW, js, replay
from sim.crate_motion_v15 import MODE, Navigation
from sim.crate_navigation_v12 import WallFootprint
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_goal_set import geometry
from harness.grasp_act_visible_world import command_delta
A=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate15-8007db00')
results=[];fixtures=[]
for folder in ([] if '--probes-only' in sys.argv else sorted(RAW.glob('crate-*-8007db00'))):
 res=js(folder/'raw/result.json');ws=json.loads((A/(folder.name+'-worlds.json')).read_text());counts=Counter();margins={};routes=[];t0=ws['r1'][0]['t']
 for rid,d in res['prefix']['teachers'].items():
  end=res['prefix']['assigned'][rid]
  for call in d['goal_set_log']:
   w=min(ws[rid],key=lambda x:abs(x['t']-call['t']));nav=Navigation(w,rid,True,CRATE,(-20,20,-20,20),end=end)
   for c in call['candidates']:
    if c['reason'] not in ('blocked_goal','no_path','feasible'):continue
    _,_,h,g=geometry(w,rid,end,(math.radians(c['offset_deg']),c['distance_m']))
    newfree=nav.free(g,h);counts[c['reason']+'->'+('goal_clear' if newfree else 'goal_blocked')]+=1
    for kind,v in nav.clearances(g,h):
     key=f'{rid}:{c["reason"]}:{kind}';bounds=margins.setdefault(key,[v*1000,v*1000]);bounds[0]=min(bounds[0],v*1000);bounds[1]=max(bounds[1],v*1000)
    if c['reason']=='no_path':
     path=nav.path(w['robots'][rid]['pose'][:2],g,h) if newfree else None
     counts['no_path->'+('path' if path else 'no_path')]+=1
     routes.append({'t':call['t'],'robot':rid,'choice':[math.radians(c['offset_deg']),c['distance_m']], 'new_path':path})
     if path and not any(f['run']==folder.name for f in fixtures):fixtures.append({'run':folder.name,'robot':rid,'world':w,'end':end,'choice':[math.radians(c['offset_deg']),c['distance_m']]})
 print(folder.name,dict(counts),flush=True)
 row={'run':folder.name,'candidate_transitions':dict(counts),'new_margin_ranges_mm':margins,'route_retests':routes}
 results.append(row);(A/'comparison.json').write_text(json.dumps(results,indent=2)+'\n')
if '--probes-only' in sys.argv:results=json.loads((A/'comparison.json').read_text())
# Probes are evaluated on exact baseline states, using its ORIGINAL issued
# history. Their altered actions are never fed into future saved observations.
for row in results:
 probes=[];search_seen=set()
 def hook(stage,i,now,r,t,w,plain,ev,*rest):
  if stage!='pre':return
  search=(t.phase=='search' and r not in search_seen and t.folded_ready and
          'crate_1' in plain['visibility'][r]['objects'])
  if t.phase not in ('align','ready') and not search:return
  clone=deepcopy(t);clone.crate_motion=MODE
  permits=ev['pick_permits'];lifts=ev['lift_permits']
  cmd,done=clone.step(w,now,permit_pick=permits[r],permit_lift=lifts[r])
  if search:search_seen.add(r)
  probes.append({'tick':i,'t':now,'robot':r,'phase_before':t.phase,'phase_after':clone.phase,
   'outcome':clone.outcome,'errors':clone.crate15_errors,'new_delta':command_delta(cmd,.1),'new_width_s':max(cmd['duration_s']),
   'recovery':clone.crate_recovery_log[-1:]})
 r=replay(row['run'],hook=hook);r.pop('teachers')
 row['baseline_after_edit']=r;row['state_probes']=probes
 (A/'comparison.json').write_text(json.dumps(results,indent=2)+'\n')
 print(row['run'],'state probes',len(probes),'baseline matches',r['matched'],r['total'],flush=True)
if fixtures:Path(__file__).with_name('route-fixtures.json').write_text(json.dumps(fixtures,indent=2)+'\n')
