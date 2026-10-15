"""Saved evidence only; GT is restricted to error/relationship evaluation."""
import json, math, sys, hashlib
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from replay import js, rows, RAW
from harness.grasp_act_visible_world import VisibleWorld, command_delta
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_visible_route import constraints
from sim.crate_navigation_v12 import FOOTPRINT, PAD_M
from harness.static_keepouts import polygon_at, rect_corners, _axes
from sim.grasp_act_teacher import local, wrap
from sim.crate_alignment_v14 import STATION_M
OUT=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate15-8007db00')
def gap(a,b):
 return max(max(min(x*u+y*v for x,y in b)-max(x*u+y*v for x,y in a),min(x*u+y*v for x,y in a)-max(x*u+y*v for x,y in b)) for u,v in (*_axes(a),*_axes(b)))
def margins(w,rid,p,yaw,folded):
 rad,ds,rs=constraints(w,rid,folded,CRATE);own=polygon_at((*p,yaw),FOOTPRINT)
 from scripts.zone_teacher import PeerDisc
 vals=[]
 for d in ds:
  # Existing constraint source ordering is peers, other cargo, assigned crate discs.
  src='peer' if isinstance(d,PeerDisc) else 'crate' if d in ds[-len(CRATE.discs):] else 'other_cargo'
  vals.append((src,1000*(math.dist(p,d[:2])-rad-d[2])))
 for rect in w['walls']:vals.append(('wall',1000*gap(own,rect_corners(rect,margin=PAD_M))))
 return {k:min(v for n,v in vals if n==k) for k in {n for n,v in vals}}
all_out=[]
for folder in sorted(RAW.glob('crate-*-8007db00')):
 raw=folder/'raw';res=js(raw/'result.json');ev=[e for e in rows(raw/'eval-only.jsonl') if e['stage']=='grasp'];t0=ev[0]['t'];roles=res['prefix']['assigned']
 labs={r:rows(raw/f'teacher-{r}.jsonl') for r in roles};mods={r:VisibleWorld(r,e,profile=CRATE,static_walls=res['static_walls']) for r,e in roles.items()}
 worlds={r:[] for r in roles}
 for i,e in enumerate(ev):
  for r,m in mods.items():worlds[r].append(m.observe(e['visible_measurements'][r],e['t']));m.issue(labs[r][i]['applied_command'])
 (OUT/(folder.name+'-worlds.json')).write_text(json.dumps(worlds)+'\n')
 ro={}
 for rid,end in roles.items():
  diag=res['prefix']['teachers'][rid];cs=Counter();blocks=Counter();mm=defaultdict(list);detail=[];folded_at=next((x['t'] for x in diag['events'] if x.get('phase')=='approach'),float('inf'))
  for call in diag['goal_set_log']:
   i=min(range(len(ev)),key=lambda j:abs(ev[j]['t']-call['t']));w=worlds[rid][i]
   for c in call['candidates']:
    cs[c['reason']]+=1
    if c['reason']=='blocked_goal':
     yaw=w['beam']['pose'][2]+(math.pi if end=='blue' else 0)+math.radians(c['offset_deg']);v=margins(w,rid,c['goal'],yaw,True)
     # folded_ready becomes true at the end of initial fold; saved planner radius disambiguates.
     for k,g in v.items():
      mm[k].append(g)
      if g<0:blocks[k]+=1
     detail.append({'sim_s':call['t']-t0,'candidate':c,'margins_mm':v})
  align=[]
  for i,(e,l,w) in enumerate(zip(ev,labs[rid],worlds[rid])):
   if l['teacher_phase'] not in ('align','ready') or not w['beam']:continue
   g=w['beam']['ends'][end];p=w['robots'][rid]['pose'];x,y=local(p,g);selected=[c['selected'] for c in diag['goal_set_log'] if c['t']<=e['t']+1e-8 and c['selected']]
   offset=selected[-1]['choice'][0] if selected else 0.
   h=w['beam']['pose'][2]+(math.pi if end=='blue' else 0)+offset
   dx,dy,da=command_delta(l['applied_command'],.1)
   align.append({'sim_s':e['t']-t0,'phase':l['teacher_phase'],'x_error_mm':1000*(x-STATION_M),'y_error_mm':1000*y,'yaw_error_rad':wrap(h-p[2]),'issued_delta':[dx,dy,da], 'width_s':max(l['applied_command']['duration_s'])})
  ro[rid]={'outcome':diag['outcome'],'phase':diag['phase'],'events':diag['events'],'candidates':dict(cs),'blocked_by':dict(blocks),'margin_mm':{k:{'min':min(v),'max':max(v)} for k,v in mm.items()},'staging_clock':diag['staging_clock'],'recovery_counts':dict(Counter(e.get('recovery') for e in diag['crate_recovery_log'])),'align_rows':len(align),'ready_rows':sum(x['phase']=='ready' for x in align),'align_trace':align}
  (OUT/(folder.name+'-blocked.json')).write_text(json.dumps(detail,indent=2)+'\n')
 # Relationship only: use evaluated GT here, never forward to either policy.
 relation=[]
 for i in [0,len(ev)//2,len(ev)-1]:
  e=ev[i];bp=e['crate'];ends=bp['ends'];relation.append({'sim_s':e['t']-t0,'closest_lug':{r:min(ends,key=lambda k:math.dist(e['robots'][r]['pose'][:2],ends[k][:2])) for r in roles},'base_separation_m':math.dist(e['robots']['r1']['pose'][:2],e['robots']['r2']['pose'][:2])})
 row={'name':folder.name,'sim_s':res['sim_s'],'roles':roles,'evaluation_relationship':relation,'robots':ro};all_out.append(row)
 print(folder.name, {r:{k:v for k,v in x.items() if k not in ('events','align_trace')} for r,x in ro.items()},flush=True)
(OUT/'saved-analysis.json').write_text(json.dumps(all_out,ensure_ascii=False,indent=2)+'\n')
