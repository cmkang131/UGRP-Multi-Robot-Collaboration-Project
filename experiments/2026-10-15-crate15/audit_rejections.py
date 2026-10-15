"""Refine saved rejection labels; no control, simulation or GT inputs."""
import json,math
from pathlib import Path
from collections import Counter
from itertools import product
from replay import RAW,js
from sim.grasp_act_goal_set import geometry
from sim.crate_alignment_v14 import STATION_M,OUTER,lift_feasible
from sim.crate_antipodal import visible_grasp
from sim.grasp_act_teacher import local
from sim.crate_navigation_v12 import WallFootprint,HALF_X,HALF_Y,PAD_M
from sim.cargo_teacher_profile import CRATE
from scripts.zone_teacher import plan_path
A=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate15-8007db00')
records=[]
def why(w,r,e,p):
 report=visible_grasp(w,r,e,pose=p)
 if not report['valid']:return report['reason']
 g=w['beam']['ends'][e];x,y=local(p,g)
 if not lift_feasible(x,y,g[2]):return 'lift_window'
 return None
for f in sorted(RAW.glob('crate-*-8007db00')):
 ws=json.loads((A/(f.name+'-worlds.json')).read_text());res=js(f/'raw/result.json');counts=Counter();examples=[]
 for rid,d in res['prefix']['teachers'].items():
  end=res['prefix']['assigned'][rid];first=True
  for call in d['goal_set_log']:
   w=min(ws[rid],key=lambda q:abs(q['t']-call['t']))
   for c in call['candidates']:
    _,g,h,goal=geometry(w,rid,end,(math.radians(c['offset_deg']),c['distance_m']))
    if c['reason']=='grasp_geometry':
     reason=why(w,rid,end,(*goal,h));where='centre'
     if reason is None:
      for dx,dy,da in product(*[(-b,b)for b in OUTER]):
       a=h-da;x,y=STATION_M+dx,dy;co,si=math.cos(a),math.sin(a)
       p=(g[0]-co*x+si*y,g[1]-si*x-co*y,a);reason=why(w,rid,end,p)
       if reason:where='outer_corner';break
     counts[rid+':'+where+':'+str(reason)]+=1
    if c['reason']=='no_path' and first:
     first=False;nav=WallFootprint(w,rid,True,CRATE,(-20,20,-20,20));start=nav.pose[:2];r=min(HALF_X,HALF_Y)+PAD_M
     ds=[(d[0],d[1],d[2]+nav.radius-r)for d in nav.discs]
     path=plan_path(start,goal,nav.bounds,ds,rects=nav.rects,radius=r)
     if path:
      margin=lambda p:min((math.dist(p,d[:2])-d[2]-nav.radius)*1000 for d in nav.discs)
      examples.append({'robot':rid,'teacher_t':call['t'],'start':start,'first_grid':path[0],
       'start_circle_margin_mm':margin(start),'first_grid_circle_margin_mm':margin(path[0]),
       'first_connector_valid':nav.segment(start,path[0],nav.pose[2],h),
       'skip_first_grid_connector_valid':nav.segment(start,path[1],nav.pose[2],h)})
 row={'run':f.name,'geometry_rejections':dict(counts),'first_path_failure':examples};records.append(row)
 print(row,flush=True)
(A/'rejection-detail.json').write_text(json.dumps(records,indent=2)+'\n')
