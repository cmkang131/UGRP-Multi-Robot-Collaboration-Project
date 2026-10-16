import sys,json,bisect
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path.cwd()/'experiments/2026-10-06-s2-realism'))
from evaluate_sensor_consistency import line_match
from harness.zone_solo_cyan_landmarks import MapFeatures
from harness import zone_solo_cyan_contract_v106 as c
raw=Path(sys.argv[1]);root=Path('/Users/changmin/projects/ugrp/outputs/s2-active-observation-v58-20261009')
r=json.loads((raw/'student_record.json').read_text());result=json.loads((raw/'result.json').read_text());events=r.get('active_localization',{}).get('events',[])
truth=[json.loads(q) for q in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()];ts=np.array([q['t'] for q in truth]);xyz=np.array([q['robot_xyz_m'][:2] for q in truth]);yaw=np.unwrap([q['robot_yaw_rad'] for q in truth]);mapped=MapFeatures(c.hp.resolve(c.MAP_ID)[0])
rows=[]
for q in r['sensor_landmarks']['rows']:
 t=q['t'];gt=np.array([np.interp(t,ts,xyz[:,0]),np.interp(t,ts,xyz[:,1]),np.interp(t,ts,yaw)])
 phase='normal'
 for e in events:
  a=e['action'];start=e['t']+a['pulses']*a['horizon_s']+.4;end=start+1.5
  if e['t']<=t<=e.get('completed_t',e['t']):phase='active_rotation_episode'
  if start<=t<=end:phase='active_outward_view'
 matches=[]
 for f in q['features']:
  m=line_match(mapped,f,gt)
  if m:
   e=mapped.edges[m['edge']];m['constrains']='Y' if abs(e['normal'][1])>abs(e['normal'][0]) else 'X'
  matches.append(dict(kind=f['kind'],match=m))
 rows.append(dict(t=t,phase=phase,wall_count=q['wall_count'],features=matches))
out=dict(seed=result['seed'],evaluation_only=True,measurements=rows,phases={})
for phase in ('normal','active_rotation_episode','active_outward_view'):
 selected=[q for q in rows if q['phase']==phase];fs=[f for q in selected for f in q['features']]
 out['phases'][phase]=dict(updates=len(selected),floor=sum(f['kind']=='floor_line' for f in fs),door=sum(f['kind']=='door' for f in fs),Y_lines=sum(f['match'] is not None and f['match']['constrains']=='Y' for f in fs))
(root/f'features-s{result["seed"]}.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out['phases']))
