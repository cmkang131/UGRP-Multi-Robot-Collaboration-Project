import pathlib,sys,json,math,collections
import numpy as np
r=pathlib.Path('/home/ugrp/ugrp-sim');src=r/'src/1ead2bb999bbb0e9d07c7d707be727f8ad563f93';dep=r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247';sys.path.insert(0,str(src))
from scripts.audit_beampair1 import read,read_bytes
from harness.beampair_wall_layer import WallLayer,ray_cells,rectangle_cells,GRID_M
import harness,sim
harness.__path__.append(str(dep/'harness'));sim.__path__.append(str(dep/'sim'))
from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_gaze import camera_extrinsics
raw=r/'runs/beampair5-r1-1ead2bb9/round/diagnostic/episode-000/raw';out=r/'ops-reviews/beampair5'
labels={round(l['applied_command']['t'],5):l for l in map(json.loads,read_bytes(raw/'teacher-r2.jsonl')[0].splitlines())}
rays={round(l['t'],5):l['rays'] for l in map(json.loads,read_bytes(raw.parent/'adapter/wall-rays.jsonl')[0].splitlines()) if l['robot']=='r2'}
model=VisibleWorld('r2','blue',odometry='search17_fixed_v1',search22='search22_v1',search23='search23_v1');layer=WallLayer();miss=collections.Counter();hit=collections.Counter();lastfree=set()
for row in map(json.loads,read_bytes(raw/'eval-only.jsonl')[0].splitlines()):
 now=row['t'];key=round(now,5);ms=row['visible_measurements']['r2'];world=model.observe(ms,now);rr=[]
 if rays.get(key):
  origin,axes=camera_extrinsics({int(k):v for k,v in model.previous['pwm'].items()});p=world['robots']['r2']['pose'];c,s=math.cos(p[2]),math.sin(p[2])
  transform=lambda q:(p[0]+c*q[0]-s*q[1],p[1]+s*q[0]+c*q[1])
  for ray in rays[key]:rr.append(dict(origin=origin,end=(np.asarray(origin)+np.asarray(axes).T@ray['optical_end']).tolist(),hit_wall=ray['hit_wall']))
  free=set();occupied=set()
  for ray in rr:
   free.update(ray_cells(transform(ray['origin']),transform(ray['end'])))
   if ray['hit_wall']:occupied.add(tuple(math.floor(v/GRID_M) for v in transform(ray['end'])))
  for m in world['visibility']['r2']['observations'].values():
   if m['kind']=='wall' and m['seen_t']>=now-1e-8:occupied|=rectangle_cells(m)
  free-=occupied;miss.update(free);hit.update(occupied);lastfree=free
 layer.update(world,'r2',ms,rr)
 if key in labels:model.issue(labels[key]['applied_command'])
result=read(raw/'result.json');event=result['teachers']['r2']['goal_set_log'][-1];candidate=event['candidates'][0];blockers=[b for b in candidate['collision_audit'] if b['blocked']];cells=[]
for b in blockers:
 parts=b['id'].split(':')
 if len(parts)!=5:continue
 _,_,lo,hi,y=parts
 for x in range(int(lo),int(hi)+1):
  k=(x,int(y));cells.append(dict(cell=k,owner=layer.owners.get(k),log_odds=layer.odds.get(k),miss_scan_N=miss[k],hit_scan_N=hit[k],last_scan_free=k in lastfree))
free=np.array([((x+.5)*GRID_M,(y+.5)*GRID_M) for x,y in lastfree]);occupied=np.array([((x+.5)*GRID_M,(y+.5)*GRID_M) for (x,y),v in layer.odds.items() if v>=0 and (x,y) in layer.owners])
report=dict(goal=candidate['goal'],heading_rad=world['beam']['pose'][2]+math.pi,own_pose=world['robots']['r2']['pose'],band=world['beam']['ends']['blue'],blocked_goal_cells=cells,last_free_bounds=[free.min(axis=0).tolist(),free.max(axis=0).tolist()] if len(free) else None,nearest_last_free_to_goal_m=float(np.linalg.norm(free-np.asarray(candidate['goal']),axis=1).min()) if len(free) else None,ray_N=sum(len(v) for v in rays.values()),last_wall_event=layer.events[-1])
(out/'r1-ray-detail.json').write_text(json.dumps(report,indent=2)+'\n')
from PIL import Image,ImageDraw
allxy=np.vstack((free,occupied,np.array([candidate['goal'],world['robots']['r2']['pose'][:2]])))
lo=allxy.min(axis=0);hi=allxy.max(axis=0);scale=700/max(hi-lo)
image=Image.new('RGB',(900,850),'white');draw=ImageDraw.Draw(image)
def pixel(p):return (int(70+(p[0]-lo[0])*scale),int(780-(p[1]-lo[1])*scale))
for color,points in [('red',occupied),('skyblue',free)]:
 for q in points:
  x,y=pixel(q);draw.rectangle((x-2,y-2,x+2,y+2),fill=color)
for color,label,q in [('black','goal',candidate['goal']),('green','issued robot',world['robots']['r2']['pose'][:2]),('blue','visible band',world['beam']['ends']['blue'][:2])]:
 x,y=pixel(q);draw.ellipse((x-6,y-6,x+6,y+6),fill=color);draw.text((x+8,y),label,fill=color)
draw.text((20,20),'Red: occupied wall cells. Blue: last scan free rays. Own issued frame only.',fill='black')
image.save(out/'r1-rays-map.png')
print(json.dumps(report,indent=2))
