"""gcp2 evaluation only: authored beam setups, never a teacher input."""
import argparse,collections,hashlib,json,math,pathlib,sys,csv
p=argparse.ArgumentParser();p.add_argument('--input',type=pathlib.Path,required=True);p.add_argument('--dependency',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.dependency))
from harness.zone_final_environment import resolve
from sim.grasp_act_search24 import reachability_map
from sim.grasp_act_search18 import body_clearance,rectangles_overlap,HALF_X,HALF_Y
from sim.grasp_act_search21 import FRESH_MARGIN_M
from sim.zone_cargo import kind

def evaluate(pose,static,extra=()):
 rects=[(o['id'],(*o['center_m'],*o['half_extents_m'],o.get('yaw_rad',0.))) for o in [*static['obstacles'],*extra]]
 beam=kind('long_beam');ends={}
 for end,g in zip(('teal','blue'),beam.grasps):
  gx,gy,z=g.grip_xyz;c,s=math.cos(pose[2]),math.sin(pose[2]);target=(pose[0]+c*gx-s*gy,pose[1]+s*gx+c*gy,z)
  rows=[]
  for offset,distance,_,certificate in reachability_map(z):
   yaw=pose[2]+(math.pi if end=='blue' else 0.)+offset
   goal=(target[0]-distance*math.cos(yaw),target[1]-distance*math.sin(yaw),yaw)
   gaps=[(name,body_clearance(goal,[],[rect]),rectangles_overlap((*goal[:2],HALF_X,HALF_Y,yaw),rect)) for name,rect in rects]
   blocked=[dict(blocked_object=name,min_gap_m=gap,reason_category='actual_overlap' if overlap else 'existing_5mm_padding') for name,gap,overlap in gaps if overlap or gap<FRESH_MARGIN_M]
   name,gap,overlap=min(gaps,key=lambda v:v[1])
   rows.append(dict(offset_rad=offset,distance_m=distance,goal=goal,collision_free=not any(v[2] for v in gaps),admitted=not blocked,blocked=blocked,nearest_object=name,min_gap_m=gap))
  ends[end]=dict(certified_N=len(rows),collision_free_N=sum(r['collision_free'] for r in rows),free_goal_N=sum(r['admitted'] for r in rows),minimum_gap_m=min(r['min_gap_m'] for r in rows),best_gap_m=max(r['min_gap_m'] for r in rows),blocker_occurrences=dict(collections.Counter(b['blocked_object'] for r in rows for b in r['blocked'])),rejected_stances=[r for r in rows if r['blocked']])
 return ends

rows=[];hashes={};scenarios=sorted((a.input/'inputs-v7').glob('*.json'))
assert len(scenarios)==8
for f in scenarios:
 data=f.read_bytes();hashes[f.name]=hashlib.sha256(data).hexdigest();s=json.loads(data);static,_,_=resolve(s['map_id'])
 beams=[v for v in s['eval']['setup']['placements'] if v['kind']=='long_beam']
 extras=[dict(id=e['target']['obstacle']['obstacle_id'],**{k:v for k,v in e['target']['obstacle'].items() if k!='obstacle_id'}) for e in s['eval'].get('hidden_events',[]) if 'obstacle' in e.get('target',{})]
 for seed in s['seeds']:
  if not beams:rows.append(dict(population='v7',scenario=s['scenario_id'],seed=seed,item=None,phase='initial',ends={}))
  for beam in beams:
   for phase,extra in [('initial',[]),*([('all_authored_fixed_events_present',extras)] if extras else [])]:
    rows.append(dict(population='v7',scenario=s['scenario_id'],seed=seed,item=beam['item_id'],beam_pose=beam['pose_m'],phase=phase,ends=evaluate(beam['pose_m'],static,extra)))
plan=a.input/'gate-plan.json';hashes['gate-plan.json']=hashlib.sha256(plan.read_bytes()).hexdigest()
for e in json.loads(plan.read_bytes())['episodes']:
 static,_,_=resolve(e['map_id']);rows.append(dict(population='gate_v1',scenario=e['scenario_id'],seed=e['seed'],item=e['target_item'],beam_pose=e['beam_pose'],phase='initial',ends=evaluate(e['beam_pose'],static)))
counts=lambda population:[v['free_goal_N'] for r in rows if r['population']==population and r['phase']=='initial' for v in r['ends'].values()]
v7=counts('v7');gate=counts('gate_v1');k=min(v7)
report=dict(schema='ugrp.beampair6.placement_validity.v1',scope='evaluation-only authored setup; all actual map walls/fixed obstacles incl authored inserted fixed event; no other cargo or robot/path/sweep test; no controller receives rows',scenario_source_sha='34e5deb40caa58317ae9ec5e9ac934c8cf09a941',dependency_sha=a.dependency.name,input_sha256=hashes,analysis_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),height_m=kind('long_beam').grasps[0].grip_xyz[2],padding_m=FRESH_MARGIN_M,padding_basis='unchanged search21 FRESH_MARGIN_M',v7_unique_beams=sum(len([v for v in json.loads(f.read_bytes())['eval']['setup']['placements'] if v['kind']=='long_beam']) for f in scenarios),v7_seeded_ends_N=len(v7),v7_distribution=dict(sorted(collections.Counter(v7).items())),gate_seeded_ends_N=len(gate),gate_distribution=dict(sorted(collections.Counter(gate).items())),branch='A' if k>0 else 'B',k=k,k_basis='minimum (empirical percentile 0) of all v7 authored initial end counts; event phase separately checked',rows=rows)
a.out.mkdir(exist_ok=True,parents=True);(a.out/'placement-validity.json').write_text(json.dumps(report,indent=2)+'\n')
with (a.out/'placement-validity.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['population','scenario','seed','item','phase','end','certified_N','collision_free_N','free_goal_N','best_gap_m','blockers'])
 for r in rows:
  for end,v in r['ends'].items():w.writerow([r['population'],r['scenario'],r['seed'],r['item'],r['phase'],end,*[v[k] for k in ('certified_N','collision_free_N','free_goal_N','best_gap_m')],json.dumps(v['blocker_occurrences'])])
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
