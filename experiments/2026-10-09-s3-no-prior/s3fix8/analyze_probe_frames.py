"""Post-run own-RGB table; evaluation displacement never enters a controller."""
import argparse,bisect,copy,hashlib,importlib.util,json,math
from pathlib import Path
from collections import Counter
import numpy as np
from harness.zone_solo_cyan_vision_v106 import CyanVision
from harness.s2_stiff_camera_calibration import corrected_record
from harness.zone_final_pair_vision import GRASP_RADIUS_M
spec=importlib.util.spec_from_file_location('saved_analysis',Path('experiments/2026-10-09-s3-no-prior/s3fix8/analyze_saved.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def read(p):return json.loads(p.read_text())
p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();R=a.raw;O=a.output;O.mkdir(exist_ok=False)
b=read(R/'bundle.json');st=read(R/'student_record.json');state=read(R/'stage-states.json');result=read(R/'result.json');out={}
for rid in (('r1','r2') if result['case']=='pair' else ('r3',)):
 frames=rows(R/f'robots/{rid}/frames.jsonl');ft=[r['sim_time'] for r in frames];commands=rows(R/f'robots/{rid}/commands.jsonl');ct=[r['t'] for r in commands];truth=rows(R/f'eval_only/{rid}/trajectory.jsonl');tt=[r['t'] for r in truth]
 if rid!='r3':
  ev=[e for se in st['pair']['pair'] for e in se['robots'][rid]['events'] if e['event']=='beam_obs']
 else:
  cal=copy.deepcopy(b['controller_config']['extrinsic_calibration'])
  for tab in cal['camera_models'].values():
   for k,rec in list(tab.items()):tab[k]=corrected_record(rec,b['controller_config']['stiff_camera_table']['poses'][k])
  vision=CyanVision(cal);ev=[];times=[r['t'] for r in state]
  for f in frames:
   if not times or f['sim_time']<times[0]:continue
   stage=state[max(0,bisect.bisect_right(times,f['sim_time'])-1)]['robots'][rid]['state']
   if stage!='align':continue
   servo={int(k):v for k,v in f['commanded_servo'].items()};fits=vision.detect({'image':(R/f['path']).read_bytes()},servo)
   ev.append(dict(sim_s=f['sim_time'],visible=len(fits)==1,reason='unique_fit' if len(fits)==1 else 'missing_or_multiple',detections=len(fits),grip_base_m=fits[0]['estimated_box_center_base_m'][:2] if len(fits)==1 else None,axis_heading_rad=0,posture='recorded'))
 table=[]
 for i,e in enumerate(ev):
  t=e['sim_s'];end=ev[i+1]['sim_s'] if i+1<len(ev) else min(t+.4,tt[-1]);f=frames[max(0,bisect.bisect_right(ft,t+1e-8)-1)]
  active=[c for c in commands[bisect.bisect_left(ct,t-1e-8):bisect.bisect_left(ct,end-1e-8)] if c['kind']=='mecanum' and any(c.get(k,0) for k in ('forward','left','turn'))]
  p0=truth[max(0,bisect.bisect_right(tt,t+1e-8)-1)];p1=truth[max(0,bisect.bisect_right(tt,end+1e-8)-1)];d=np.array(p1['robot_xyz_m'][:2])-p0['robot_xyz_m'][:2];yaw=p0['robot_yaw_rad'];c,s=math.cos(yaw),math.sin(yaw)
  grip=e.get('grip_base_m');errors=[grip[0]-GRASP_RADIUS_M,grip[1],e['axis_heading_rad']] if e['visible'] and grip else None
  px,points=m.pixel_error(b['controller_config'],f['commanded_servo'],grip) if errors else (None,None)
  table.append(dict(t=t,frame=f['path'],frame_sha256=f['sha256'],visible=e['visible'],end_visible=e.get('end_visible'),reason=e['reason'],errors_m_m_rad=errors,pixel_error_xy=px,projected_observed_and_target_pixels=points,pixel_method='projection of own-RGB fitted grip and fixed grasp target; not mask-centroid difference',commands=active,eval_delta_forward_m=c*d[0]+s*d[1],eval_delta_left_m=-s*d[0]+c*d[1],eval_delta_yaw_rad=m.wrap(p1['robot_yaw_rad']-yaw),eval_interval_s=end-t))
 (O/f'{rid}-frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in table))
 moves=[r for r in table if r['commands']];valid=[r for r in table if r['errors_m_m_rad']];last=valid[-1] if valid else None
 def hit(r):
  e=r['errors_m_m_rad'];return bool(e and abs(e[0])<=.003 and abs(e[1])<=.003 and (rid=='r3' or abs(e[2])<=.035))
 out[rid]=dict(rows=len(table),detected=sum(r['visible'] for r in table),tolerance_hit=sum(hit(r) for r in table),end_visible_count=sum(r.get('end_visible') is True for r in table),reasons=dict(Counter(r['reason'] for r in table)),forward_reversals=sum(a['commands'][0].get('forward',0)*b['commands'][0].get('forward',0)<0 for a,b in zip(moves,moves[1:])),turn_reversals=sum(a['commands'][0].get('turn',0)*b['commands'][0].get('turn',0)<0 for a,b in zip(moves,moves[1:])),last=last,
  command_frames=len(moves),data_sha256=hashlib.sha256((O/f'{rid}-frames.jsonl').read_bytes()).hexdigest(),coverage='all RGB alignment frames' if rid=='r3' else 'all actual controller beam observation decisions')
(O/'summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
