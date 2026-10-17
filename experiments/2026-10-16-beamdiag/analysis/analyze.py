"""beamdiag: finite raw-only analysis; no model, training, simulator, or renderer imports.
All geometric truth is evaluator-only. No acceptance/control constants are changed.
Color assays use literal half-range bright/saturated pixels and palette hue midpoints.
Detection sensitivity at 1/9/25 connected pixels is reported, not hidden as certainty.
"""
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib,json,subprocess,os,time,math
import numpy as np
import cv2
cv2.setNumThreads(1)
B=Path('/home/ugrp/ugrp-sim'); O=B/'ops-reviews/beamdiag/v1'
CFG=json.loads((O/'analysis-config.json').read_text())

def existing(p):return p if p.exists() else Path(str(p)+'.zst')
def data(p):
 p=existing(p)
 return subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
def js(p):return json.loads(data(p))
def rows(p):return [json.loads(s) for s in data(p).splitlines() if s.strip()]
def sha(p):return hashlib.sha256(existing(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def quant(x):
 a=np.asarray(x,float);a=a[np.isfinite(a)]
 return dict(zip(('min','p10','p25','p50','p75','p90','p95','p99','max'),np.quantile(a,[0,.1,.25,.5,.75,.9,.95,.99,1]).tolist())) if len(a) else {}
def longest(v,period=.1):
 v=np.asarray(v,bool);d=np.diff(np.r_[False,v,False].astype(int));starts=np.flatnonzero(d==1);ends=np.flatnonzero(d==-1)
 return float((ends-starts).max()*period) if len(starts) else 0.
def fraction(a):return float(np.mean(a)) if len(a) else None

def feature(p,expected_sha=None):
 raw=p.read_bytes()
 if expected_sha and hashlib.sha256(raw).hexdigest()!=expected_sha:raise ValueError('RGB SHA mismatch '+str(p))
 im=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
 if im is None or im.shape[:2]!=(480,640):raise ValueError('RGB shape '+str(p))
 im=cv2.resize(im,(320,240),interpolation=cv2.INTER_AREA)
 h=cv2.cvtColor(im,cv2.COLOR_BGR2HSV);bright=(h[:,:,1]>=128)&(h[:,:,2]>=128)
 # Measured raw hue modes: lime body39/40, teal83, blue120. Boundaries
 # 61/102 are nearest-palette midpoints; low-saturation indigo floor excluded.
 masks=[bright&(h[:,:,0]>=20)&(h[:,:,0]<=61),bright&(h[:,:,0]>61)&(h[:,:,0]<=101),bright&(h[:,:,0]>101)&(h[:,:,0]<=140)]
 ans=[float(masks[0].mean()),int(masks[0][120,160])]
 for m in masks[1:]:
  n,lab,st,cen=cv2.connectedComponentsWithStats(m.astype(np.uint8),8)
  if n<=1:ans += [0,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan]
  else:
   k=1+int(st[1:,cv2.CC_STAT_AREA].argmax());x,y,w,ht,area=st[k];cx,cy=cen[k]
   ans += [int(area),float(cx/320),float(cy/240),float(x/320),float(y/240),float((x+w)/320),float((y+ht)/240)]
 return ans
# feature columns body_frac,axis_body,teal(area,cx,cy,x0,y0,x1,y1),blue(...)
def wheel(c):return np.rint(np.asarray(c['wheels'])/.35).astype(int)
def cmd_stats(cs,select=None,boundary=None):
 if select is None:select=np.ones(len(cs),bool)
 if not len(cs):return dict(N=0)
 w=np.asarray([wheel(c) for c in cs]);pulse=np.asarray([c['duration_s'] for c in cs]);pwm=np.asarray([[c['pwm'][s] for s in ('1','3','4','5','6')] for c in cs])
 eq=(w[1:]==w[:-1]).all(1);nz=(w[1:]!=0).any(1);sel=np.asarray(select,bool)[1:]
 duty=w*.35*pulse/.1
 out=dict(N=int(np.sum(select)),pair_N=int(sel.sum()),wheel_repeat_N=int((eq&sel).sum()),wheel_repeat_fraction=fraction(eq[sel]),nonzero_pair_N=int((sel&nz).sum()),nonzero_wheel_repeat_fraction=fraction(eq[sel&nz]),full_command_exact_repeat_fraction=fraction((eq&(pulse[1:]==pulse[:-1]).all(1)&(pwm[1:]==pwm[:-1]).all(1))[sel]),duty_delta_abs_mean=float(np.abs(np.diff(duty,axis=0))[sel].mean()) if sel.any() else None,pwm_step_abs_mean=float(np.abs(np.diff(pwm,axis=0))[sel].mean()) if sel.any() else None)
 for j,name in ((0,'gripper'),(1,'arm3'),(2,'arm4'),(3,'arm5'),(4,'camera_pan')):out[name+'_range']=[int(pwm[select,j].min()),int(pwm[select,j].max())] if np.any(select) else None
 if boundary is not None:
  bound=np.asarray(boundary,bool)[1:]
  out['inference_boundary_pair_N']=int((sel&bound).sum());out['inference_boundary_wheel_repeat_fraction']=fraction(eq[sel&bound]);out['chunk_interior_wheel_repeat_fraction']=fraction(eq[sel&~bound])
 return out

def geom(truth,rid):
 p=np.asarray(truth['robots'][rid]['pose']);bp=truth['beam']['pose'];out=[]
 for role in ('teal','blue'):
  e=np.asarray(truth['beam']['ends'][role]);yaw=bp[2]+(math.pi if role=='blue' else 0)
  goal=e[:2]-.203*np.array([math.cos(yaw),math.sin(yaw)])
  out.extend([float(np.linalg.norm(p[:2]-e[:2])),float(np.linalg.norm(p[:2]-goal)),abs(math.atan2(math.sin(yaw-p[2]),math.cos(yaw-p[2])))])
 return out

def student(task):
 arm,seed=task;r=B/f'ops-reviews/beamact3/{arm}/heldout20-v1/seed-{seed}'
 ev=rows(r/'eval-only.jsonl');cs=rows(r/'commands.jsonl');obs=rows(r/'student-inputs.jsonl');result=js(r/'result.json');plan=js(r/'plan.json');pred=rows(r/'chunk-predictions.jsonl')
 assert len(cs)==len(obs)==len(ev)*2
 n=len(ev);ts=np.asarray([e['sim_s'] for e in ev]);origin=ev[0]['t'];out=dict(arm=arm,seed=seed,raw=str(r),source_sha=result['source_sha'],model_sha256=result['model_sha256'],complete=result['complete'],termination=result.get('termination'),cap_end=result['cap_end'],physical_success=result['physical_success'],funnel=result['funnel'],N=n,sim_range_s=[float(ts[0]),float(ts[-1])],roles=plan['roles'],robots={},original_hashes={f:sha(r/f) for f in ('plan.json','result.json','eval-only.jsonl','commands.jsonl','student-inputs.jsonl','chunk-predictions.jsonl')},final_target_finger_min_gap_m=ev[-1]['target_finger_min_gap_m'])
 arrays={'sim_s':ts};pose1=np.asarray([e['truth']['robots']['r1']['pose'][:2] for e in ev]);pose2=np.asarray([e['truth']['robots']['r2']['pose'][:2] for e in ev]);sep=np.linalg.norm(pose1-pose2,axis=1)
 out['robot_center_separation_m']=quant(sep);out['robot_center_separation_final_m']=float(sep[-1]);out['robot_robot_contact']='UNRECORDED: raw contact rows cover target/fingers only; no physical collision verdict'
 for rid in ('r1','r2'):
  oo=[o for o in obs if o['robot_id']==rid];cc=[c for c in cs if c['robot']==rid]
  assert len(oo)==n==len(cc)
  f=np.asarray([feature(r/o['rgb'][-1]['path'],o['rgb'][-1]['sha256']) for o in oo],float)
  gg=np.asarray([geom(e['truth'],rid) for e in ev]);arrays[rid+'_features']=f;arrays[rid+'_geometry']=gg
  role=plan['roles'][rid];j=0 if role=='teal' else 3;other=3-j;fin=gg[ts>=max(0,ts[-1]-10)]
  md=fin[:,0]-fin[:,3];nearest='teal' if np.median(md)<-.03 else 'blue' if np.median(md)>.03 else 'ambiguous_center'
  aligned=(gg[:,j+1]<=.03)&(gg[:,j+2]<=.06)
  near=gg[:,j]<=.8 # inherited evaluator handoff envelope; not learned stage
  boundary=np.asarray([any(abs(p['t']-o['t'])<1e-6 and p['robot']==rid for p in pred) for o in oo])
  owncmd=[c['command'] for c in cc]
  close=[k for k,(o,c) in enumerate(zip(oo,cc)) if c['command']['pwm']['1']<o['issued'][-1]['pwm']['1']]
  ready=next((k for k,c in enumerate(cc) if c['ready']),None)
  firstclose=close[0] if close else None
  rr=dict(assigned_end=role,initial_nearest_end='teal' if gg[0,0]<gg[0,3] else 'blue',final_nearest_end=nearest,nearest_scope='median distance difference in last10SIMs; ambiguous if <=existing3cm XY tolerance',assigned_end_final_distance_m=float(gg[-1,j]),other_end_final_distance_m=float(gg[-1,other]),assigned_station_error_m=quant(gg[:,j+1]),assigned_yaw_error_rad=quant(gg[:,j+2]),other_station_error_m=quant(gg[:,other+1]),ever_assigned_aligned=bool(aligned.any()),first_assigned_aligned_sim_s=float(ts[np.flatnonzero(aligned)[0]]) if aligned.any() else None,first_ready_sim_s=float(ts[ready]) if ready is not None else None,first_ready_geometry=dict(station_error_m=float(gg[ready,j+1]),yaw_error_rad=float(gg[ready,j+2])) if ready is not None else None,first_issued_gripper_decrease_sim_s=float(ts[firstclose]) if firstclose is not None else None,first_issued_gripper_decrease_geometry=dict(station_error_m=float(gg[firstclose,j+1]),yaw_error_rad=float(gg[firstclose,j+2])) if firstclose is not None else None,first_done_sim_s=next((float(ts[k]) for k,c in enumerate(cc) if c['done']),None),waiting_fraction=fraction([c['waiting'] for c in cc]),commands=dict(all=cmd_stats(owncmd,boundary=boundary),near_assigned_end=cmd_stats(owncmd,near,boundary),after_20sim=cmd_stats(owncmd,ts>=20,boundary)),final_pwm=owncmd[-1]['pwm'])
  out['robots'][rid]=rr
 out['same_end_final']=len({v['final_nearest_end'] for v in out['robots'].values()})==1 and all(v['final_nearest_end']!='ambiguous_center' for v in out['robots'].values())
 write(O/'student'/f'{arm}-{seed}.json',out);np.savez_compressed(O/'student'/f'{arm}-{seed}.npz',**arrays)
 return dict(kind='student',id=f'{arm}-{seed}',N=n)

def teacher(seed):
 root=B/f'runs/beampair8-record-{seed}-72c0e83d';r=root/'training';raw=root/'raw'
 plan=js(r/'plan.json');evals=rows(raw/'eval-only.jsonl');truths={round(e['t'],5):e for e in evals};out=dict(seed=seed,raw=str(r),robots={},original_hashes={});arrays={}
 for rid in ('r1','r2'):
  obs=rows(r/f'student-{rid}.jsonl');labels=rows(r/f'teacher-{rid}.jsonl');lookup={l['sample_id']:l for l in labels}
  selected=[o for o in obs if lookup[o['sample_id']]['local_skill_sample']];ll=[lookup[o['sample_id']] for o in selected]
  f=np.asarray([feature(r/o['rgb'][-1]['path'],o['rgb'][-1]['sha256']) for o in selected]);times=np.asarray([o['t'] for o in selected]);phases=np.asarray([l['teacher_phase'] for l in ll]);gg=np.asarray([geom(truths[round(o['t'],5)],rid) for o in selected])
  out['original_hashes'][f'student-{rid}.jsonl']=sha(r/f'student-{rid}.jsonl');out['original_hashes'][f'teacher-{rid}.jsonl']=sha(r/f'teacher-{rid}.jsonl')
  commands=[l['clean_teacher_command'] for l in ll];allpre=[l['clean_teacher_command'] for l in labels];truthvis=[truths[round(o['t'],5)]['visibility'][rid] for o in selected]
  arrays.update({rid+'_features':f,rid+'_t':times,rid+'_phase':phases,rid+'_geometry':gg,rid+'_truth_visible':np.asarray([v['visible'] for v in truthvis]),rid+'_truth_visible_probes':np.asarray([v['visible_probes'] for v in truthvis])})
  out['robots'][rid]=dict(assigned_end=plan['roles'][rid],N=len(selected),phase_counts=dict(Counter(phases.tolist())),commands={p:cmd_stats(commands,phases==p) for p in sorted(set(phases))},commands_all=cmd_stats(commands),excluded_N=len(obs)-len(selected))
 write(O/'train'/f'{seed}.json',out);np.savez_compressed(O/'train'/f'{seed}.npz',**arrays)
 return dict(kind='train',id=seed,N=sum(x['N'] for x in out['robots'].values()))

def main():
 for d in ('student','train'): (O/d).mkdir(exist_ok=True)
 lease=B/'leases/beamdiag.json';v=js(lease);v['pid']=os.getpid();v['command']='analysis-tools/beamdiag/analyze.py';write(lease,v)
 tasks=[('student',(a,s)) for a in ('A','B') for s in CFG['heldout_seeds']]+[('train',s) for s in CFG['train_seeds']]
 started=time.monotonic();done=[]
 with ProcessPoolExecutor(max_workers=8) as pool:
  futs=[pool.submit(student,v) if k=='student' else pool.submit(teacher,v) for k,v in tasks]
  for i,f in enumerate(futs):
   value=f.result();done.append(value)
   if (i+1)%10==0:print(json.dumps(dict(done=i+1,total=len(tasks),latest=value,wall_s=time.monotonic()-started)),flush=True)
 write(O/'scan-complete.json',dict(complete=True,tasks=done,wall_s=time.monotonic()-started,script_sha256=sha(Path(__file__)),image_assay=dict(resize=[320,240],interpolation='cv2.INTER_AREA',S_min=128,V_min=128,hues=dict(body=[20,61],teal=[62,101],blue=[102,140]),raw_hue_modes=[40,83,120],area_sensitivity=[1,9,25]),no_training=True,no_model_inference=True,no_physics=True,no_sim_render=True))
if __name__=='__main__':main()
