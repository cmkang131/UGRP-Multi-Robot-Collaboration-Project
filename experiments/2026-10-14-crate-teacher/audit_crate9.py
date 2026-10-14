"""Evaluation-only saved telemetry arithmetic. No simulator, renderer or control calls."""
import hashlib,json,math,subprocess
from collections import Counter
from pathlib import Path
import numpy as np
from harness.visual_arm_v3 import tool_pose,MOUNT_X_M
from harness import visual_arm as sdk

EXP=Path(__file__).resolve().parent
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
OUT=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate9-audit')
LIMIT=.1765197
EQUAL=.125*9.81

def read(p):
 p=p if p.exists() else p.with_suffix(p.suffix+'.zst')
 b=p.read_bytes();return (subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else b)
def lines(p):return [json.loads(x) for x in read(p).splitlines()]
def ref(p):
 p=p if p.exists() else p.with_suffix(p.suffix+'.zst')
 return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def stat(xs):
 a=np.asarray(xs);return {'mean':float(a.mean()),'median':float(np.median(a)),'min':float(a.min()),'max':float(a.max())}
def fk(q):
 s,e,w=q;f=s+e;p=f+w
 return (.062*math.cos(f)+.08685*math.cos(p),.062*math.sin(f)+.08685*math.sin(p),
         9.81*(.00403*math.cos(f)+.0023435*math.cos(p)+.00012*math.sin(p)))
def wrap(a):return (a+math.pi)%(2*math.pi)-math.pi

def robot_sample(row,rid,pwm):
 d=row['load_detail'];j=d['joints'][rid];q=[j[n]['q_rad'] for n in ('shoulder','elbow','wrist')];ctrl=[j[n]['ctrl_rad'] for n in ('shoulder','elbow','wrist')]
 l,z,own=fk(q);lc,zc,ownc=fk(ctrl)
 yaw=row['robots'][rid]['pose'][2]+math.radians((int(pwm['6'])-sdk.BASE_CENTER)/sdk.PULSE_PER_DEGREE)
 u=np.array([math.cos(yaw),math.sin(yaw),0.]);grip=np.array(d['grip_world_m'][rid]);elbow=grip-u*l-np.array([0,0,z])
 cs=[c for c in d['contacts'] if any(n.startswith(rid+'__') and n.endswith('_finger') for n in (c['geom1'],c['geom2']))]
 other=[c for c in d['contacts'] if any(n.startswith(rid+'__') for n in (c['geom1'],c['geom2'])) and c not in cs]
 f=np.array(d['finger_force_on_cargo_world_n'][rid]);contactz=horizontal=nonfinger=0.;along=[];kinds=Counter()
 for c in cs:
  v=np.array(c['force_on_cargo_world_n']);p=np.array(c['position_world_m']);off=p-grip
  contactz+=float(off@u)*v[2];horizontal-=float((p-elbow)[2])*float(v@u)
  along.append((float(off@u)*math.cos(sum(q))+off[2]*math.sin(sum(q)))*1000)
  kinds[next(n for n in (c['geom1'],c['geom2']) if n.startswith('cargo_'))]+=1
 for c in other:
  v=np.array(c['force_on_cargo_world_n']);p=np.array(c['position_world_m'])-elbow
  nonfinger+=float(p@u)*v[2]-p[2]*float(v@u)
 baseline=ownc+EQUAL*lc;share=(f[2]-EQUAL)*lc;deflection=own-ownc+f[2]*(l-lc)
 predicted=baseline+share+deflection+contactz+horizontal+nonfinger
 return {'fz_n':f[2],'horizontal_n':float(np.linalg.norm(f[:2])),'radial_n':float(f@u),
  'torque_nm':j['elbow']['actuator_nm'],'sat':int(abs(j['elbow']['actuator_nm'])>=.999*LIMIT),
  'error_deg':math.degrees(j['elbow']['ctrl_error_rad']),'q_deg':[math.degrees(x) for x in q],
  'ctrl_deg':[math.degrees(x) for x in ctrl],'qvel_deg_s':math.degrees(j['elbow']['qvel_rad_s']),
  'lever_mm':l*1000,'ctrl_lever_mm':lc*1000,'lever_delta_mm':(l-lc)*1000,
  'baseline_nm':baseline,'share_delta_nm':share,'deflection_delta_nm':deflection,
  'contact_delta_nm':contactz,'horizontal_nm':horizontal,'nonfinger_nm':nonfinger,
  'reconstructed_nm':predicted,'residual_nm':j['elbow']['actuator_nm']-predicted,
  'finger_contact_geoms':dict(kinds),'pad_along_mm':along,
  'nonfinger_fz_n':sum(c['force_on_cargo_world_n'][2] for c in other),
  'nonfinger_geoms':sorted({n for c in other for n in (c['geom1'],c['geom2']) if n.startswith(rid+'__')})}

def main():
 OUT.mkdir(exist_ok=True,parents=True);runs=[];integrity=[];series=[]
 for seed in range(77960,77970):
  root=RAW/f'crate-diag-{seed}-5644e3dd';p=root/'raw';result=json.loads(read(p/'result.json'));ev=lines(p/'eval-only.jsonl.zst');g=[x for x in ev if x['stage']=='grasp'];labels={r:lines(p/f'teacher-{r}.jsonl.zst')[:len(g)] for r in ('r1','r2')}
  ok=missing=bad=0
  for line in (root/'SHA256SUMS').read_text().splitlines():
   h,n=line.split(maxsplit=1);n=n.lstrip('*');suffix=n.split(root.name+'/',1)[-1];f=root/suffix
   if not f.exists():missing+=1;continue
   if hashlib.sha256(f.read_bytes()).hexdigest()==h:ok+=1
   else:bad+=1
  integrity.append({'seed':seed,'matched':ok,'missing':missing,'mismatched':bad})
  r={'seed':seed,'raw':str(p),'source_sha':result['source_sha'],'success':result['prefix_held'] and result['release_success'],
     'prefix_held':result['prefix_held'],'release_success':result['release_success'],'outcomes':result['prefix']['outcomes'],
     'input_audit':{k:result['input_audit'][k] for k in ('invisible_measurements','held_world_reads')},
     'sources':[ref(p/n) for n in ('result.json','eval-only.jsonl.zst','teacher-r1.jsonl.zst','teacher-r2.jsonl.zst','scene.xml')],
     'robots':{},'start_delay_s':result['grasp_start_delays_s'],
     'lift_start_events':[x for x in result['prefix']['lift_protocol'] if x['event']=='START']}
  for rid in ('r1','r2'):
   phases={ph:next((i for i,x in enumerate(labels[rid]) if x['teacher_phase']==ph),None) for ph in ('pick','closed','lift')}
   close=phases['closed'];pick=phases['pick'];d={'phase_start_t':{ph:g[i]['t'] if i is not None else None for ph,i in phases.items()},'visible_n':sum(x['visible_probes'][rid]>=5 for x in g),'N':len(g)}
   if close is not None:
    pose=tool_pose(labels[rid][close]['applied_command']['pwm']);row=g[pick];pwm=labels[rid][close]['applied_command']['pwm'];target=result['prefix']['assigned'][rid];axis=row['crate']['pose'][2]+(math.pi if target=='blue' else 0.)
    pan=math.radians((int(pwm['6'])-sdk.BASE_CENTER)/sdk.PULSE_PER_DEGREE)
    d.update(closed_radius_mm=1000*math.hypot(pose.x_m-MOUNT_X_M,pose.y_m),closed_z_mm=pose.z_m*1000,closed_pitch_deg=pose.pitch_deg,
      actual_pick_axis_offset_deg=math.degrees(wrap(row['robots'][rid]['pose'][2]+pan-axis)),closed_pwm=pwm,
      close_contacts=robot_sample(g[close],rid,pwm),pick_tick=pick,closed_tick=close)
   r['robots'][rid]=d
  start=next((i for i,x in enumerate(g) if any(x['lift_permits'].values())),None)
  if start is not None:
   rows=[]
   for i in range(start,len(g)):
    row=g[i];d=row['load_detail'];f1=np.array(d['finger_force_on_cargo_world_n']['r1']);f2=np.array(d['finger_force_on_cargo_world_n']['r2']);u=np.array(d['grip_world_m']['r2'])-np.array(d['grip_world_m']['r1']);u[2]=0;u/=np.linalg.norm(u)
    z={'t':row['t'],'dt':row['t']-g[start]['t'],'min_z_mm':row['crate']['min_z']*1000,'tilt_deg':row['crate']['tilt_deg'],
      'paired_axial_n':float((f1-f2)@u/2),'paired_horizontal_n':float(np.linalg.norm((f1-f2)[:2]/2)),
      'other_fz_n':d['other_force_on_cargo_world_n'][2],
      'vertical_balance_error_n':f1[2]+f2[2]+d['other_force_on_cargo_world_n'][2]-.25*9.81,
      'floor_fz_n':sum(c['force_on_cargo_world_n'][2] for c in d['contacts'] if 'floor' in (c['geom1'],c['geom2'])),
      'robots':{rid:robot_sample(row,rid,labels[rid][i]['applied_command']['pwm']) for rid in ('r1','r2')}};rows.append(z)
   windows={'lift_all':rows,'matched_3_to_6s':[x for x in rows if 3.-1e-7 <= x['dt'] < 6.-1e-7], 'tail_3s':rows[-30:]}
   r['windows']={}
   for key,window in windows.items():
    w={'N':len(window),'t_range':[window[0]['t'],window[-1]['t']],**{k:stat([x[k] for x in window]) for k in ('min_z_mm','tilt_deg','paired_axial_n','paired_horizontal_n','other_fz_n','floor_fz_n','vertical_balance_error_n')},'robots':{}}
    for rid in ('r1','r2'):
     rr=[x['robots'][rid] for x in window];w['robots'][rid]={k:stat([x[k] for x in rr]) for k in rr[0] if isinstance(rr[0][k],(int,float,np.number))};w['robots'][rid]['sat_n']=sum(x['sat'] for x in rr)
     w['robots'][rid]['contact_sample_counts']={geom:sum(geom in x['finger_contact_geoms'] for x in rr) for geom in sorted({a for x in rr for a in x['finger_contact_geoms']})}
     vals=[a for x in rr for a in x['pad_along_mm']];w['robots'][rid]['pad_along_mm']=stat(vals) if vals else None
     w['robots'][rid]['q_deg_mean']=np.mean([x['q_deg'] for x in rr],axis=0).tolist();w['robots'][rid]['ctrl_deg_mean']=np.mean([x['ctrl_deg'] for x in rr],axis=0).tolist()
    r['windows'][key]=w
   series.append({'seed':seed,'rows':rows})
  runs.append(r)
 (OUT/'integrity.json').write_text(json.dumps(integrity,indent=2));(OUT/'series.json').write_text(json.dumps(series,separators=(',',':')))
 summary={'source_sha':runs[0]['source_sha'],'success_n':sum(x['success'] is True for x in runs),'N':10,'physics_steps':0,'render_calls':0,
  'method':'Measured contact forces exact; elbow moment decomposition uses level base and issued yaw, measured shoulder/elbow/wrist. Signed cargo support -> required raising torque. Residual includes unsaved base tilt/yaw error, contact couple, robot-other contacts and dynamics. Matched window=3.0<=time since lift permit<6.0 s (30 samples per run), independent of outcome; tail=last30 grasp samples.',
  'integrity':integrity,'runs':runs,'series':ref(OUT/'series.json')}
 (EXP/'crate9-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 for r in runs:
  print(r['seed'],r['success'],'close',[(v.get('closed_radius_mm'),v.get('closed_z_mm'),v.get('closed_pitch_deg'),v.get('actual_pick_axis_offset_deg')) for v in r['robots'].values()])
  if 'windows' not in r:continue
  w=r['windows']['tail_3s'];print(' tail N',w['N'],'minz',round(w['min_z_mm']['mean'],3),'axial',round(w['paired_axial_n']['mean'],3),'floor',round(w['floor_fz_n']['mean'],3))
  for rid,z in w['robots'].items():print(rid,{k:round(z[k]['mean'],5) for k in ('fz_n','horizontal_n','error_deg','lever_delta_mm','torque_nm','baseline_nm','share_delta_nm','deflection_delta_nm','contact_delta_nm','horizontal_nm','nonfinger_nm','residual_nm')},z['contact_sample_counts'])
 print('integrity',integrity)
if __name__=='__main__':main()
