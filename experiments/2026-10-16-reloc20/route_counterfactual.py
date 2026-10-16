import subprocess
import platform
assert platform.node().startswith("ugrp-sim-gcp2"), "gcp2-only analysis"
import sys,json,math
from pathlib import Path
import numpy as np
def read(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
root=Path('/home/ugrp/ugrp-sim/src/1b31086019b0d24a696a8069c790f9113d572e0e');sys.path.insert(0,str(root))
from harness.reloc20_motion import LoadedRoute
from harness.visual_arm_v3 import forward_grip
R=Path('/home/ugrp/ugrp-sim/runs');q=json.load(open(R/'reloc20-round2/queue.json'));output=[]
for t in q['runs']:
 if t['kind']!='carry' or t['seed']!=93315:continue
 raw=Path(t['raw']);c=[json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()];first=next(x for x in c if x['phase']=='carry_prepare');low=next(x['command']['pwm'] for x in c if x['phase']=='close');low={int(k):v for k,v in low.items()};grip=forward_grip(low);static=json.load(open(raw/'carry-static-map.json'));start=first['map_pose']['pose_estimate'][:2];ep=json.load(open(raw/'plan.json'));reg=static['regions']['zone_'+ep['destination_zone']];cx,cy=reg['center_m'];hx,hy=reg['half_extents_m'];tracks=first['carry_obstacles']['tracks'];discs=[(*x['xy'],x['radius']+x['range_error_m']) for x in tracks];beam=[i for i,x in enumerate(tracks) if x['kind']=='long_beam'];slots=[(cx+sx*max(0,hx-.20),cy+sy*max(0,hy-.20)) for sx,sy in ((0,0),(-1,0),(1,0),(0,-1),(0,1))]
 for condition,dd in [('all_rgb',discs),('without_beam_disc_only',[d for i,d in enumerate(discs) if i not in beam]),('static_only',[])]:
  route=LoadedRoute(static);route.update_load(True,ep['kind'],low,{int(k):v for k,v in first['command']['pwm'].items()});records=[]
  for slot in slots:
   goal=(slot[0]-grip[0]-.15,slot[1]-grip[1]);path=route.plan(start,goal,static['bounds_m'],dd,radius=route.radius);records.append(dict(slot=slot,goal=goal,path=path,reason=route.last))
  output.append(dict(seed=t['seed'],condition=condition,start=start,radius=route.radius,source_frame_t=first['t'],raw=str(raw),records=records,tracks=tracks,static_keepouts=static.get('fixed_floor_keepouts')))
p=R/'reloc20-prior/route-counterfactual.json';p.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps([{k:v for k,v in x.items() if k not in ('tracks','records')}|dict(accepted=sum(y['path'] is not None for y in x['records']),reasons=[y['reason'] for y in x['records']]) for x in output],indent=2))
