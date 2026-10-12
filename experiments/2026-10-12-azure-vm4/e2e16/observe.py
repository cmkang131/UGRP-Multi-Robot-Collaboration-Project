"""Finite E2E16 observer; evaluation numbers never reach the controller."""
from pathlib import Path
import json,os,sys,time,signal,math,bisect,statistics,subprocess,hashlib
from collections import Counter
BASE=Path.home()/'ugrp-sim'
NAMES=[f'e2e-usstall-{group}-s{seed}' for seed in range(61001,61004) for group in ('a','b')]
def obj(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return {}
def rows(p):
 if not p.exists():return []
 out=[]
 for s in p.read_text().splitlines():
  try:out.append(json.loads(s))
  except json.JSONDecodeError:pass
 return out
def write(p,x):
 t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def stat(v):return dict(n=len(v),max=max(v,default=None),median=statistics.median(v) if v else None)
def snapshot(root):
 meta=obj(root/'RUN_META.json');raw=root/meta.get('raw_relative','raw');p=obj(raw/'e2e-progress.json');result=obj(raw/'result.json')
 progress=[]
 if (root/'log.txt').exists():
  for s in (root/'log.txt').read_text().splitlines():
   if s.startswith('{"wall_s"'):
    try:progress.append(json.loads(s))
    except json.JSONDecodeError:pass
 def wall(t):
  if t is None or not progress:return None
  return min(progress,key=lambda x:abs(x['sim_s']-t))['wall_s']
 milestones={k:dict(v) for k,v in (obj(raw/'stage-milestones.json') or result.get('stage_milestones',{})).items()}
 robots={};checks={}
 for rid in ('r1','r2','r3'):
  own=rows(raw/f'robots/{rid}/ownmap.jsonl');frames=rows(raw/f'robots/{rid}/frames.jsonl');truth=rows(raw/f'eval_only/{rid}/trajectory.jsonl');commands=rows(raw/f'robots/{rid}/commands.jsonl')
  translation=sum(c.get('kind')=='mecanum' and abs(c.get('forward',0))+abs(c.get('left',0))>0 for c in commands)
  forward=sum(c.get('kind')=='mecanum' and c.get('forward',0)>0 for c in commands)
  displacement=max((math.dist(x['robot_xyz_m'][:2],truth[0]['robot_xyz_m'][:2]) for x in truth),default=0.)
  errors=[];control_errors=[];unaligned=0
  byframe={x['frame_id']:x for x in frames};ts=[x['t'] for x in truth]
  if frames and truth:
   base=truth[min(range(len(ts)),key=lambda i:abs(ts[i]-frames[0]['sim_time']))];c=math.cos(base['robot_yaw_rad']);s=math.sin(base['robot_yaw_rad'])
   for x in own:
    f=byframe.get(x['frame_id'])
    if not f:unaligned+=1;continue
    i=min(bisect.bisect_left(ts,f['sim_time']),len(ts)-1);i=min((i,max(0,i-1)),key=lambda j:abs(ts[j]-f['sim_time']))
    if abs(ts[i]-f['sim_time'])>1e-6:unaligned+=1;continue
    dx,dy=[truth[i]['robot_xyz_m'][j]-base['robot_xyz_m'][j] for j in (0,1)];actual=[c*dx+s*dy,-s*dx+c*dy];pc=x.get('pose_continuity') or {}
    errors.append(math.dist(actual,pc.get('map_pose',x['pose_own_m'])[:2]));control_errors.append(math.dist(actual,pc.get('control_pose',x['pose_own_m'])[:2]))
  poses=[x['pose_own_m'] for x in own];jumps=[math.dist(a[:2],b[:2]) for a,b in zip(poses,poses[1:])]
  vos=[(x.get('stall_odometry') or {}).get('vo',{}) for x in own]
  if own and not any(vos):
   vos=[x.get('stall_odometry') or {} for x in own]
  ranges=rows(raw/f'robots/{rid}/inputs/range.jsonl')
  sonar=[v.get('ultrasonic') or {} for v in vos]
  us=dict(range_rows=len(ranges),judgements=sum(bool(x) for x in sonar),zupt_count=sum(bool(x.get('stationary')) for x in sonar),zupt_applied=sum(v.get('fusion')=='us_zero' for v in vos),statuses=dict(Counter(x.get('status') for x in sonar if x)),latest=sonar[-1] if sonar else None)
  candidate=next((x['t'] for x in own if x.get('remembered_B')),None)
  views=[x for x in own if (x.get('boundary_view') or {}).get('active')]
  for key,t in [('B_candidate',candidate),('B_view_approach',views[0]['t'] if views else None)]:
   if t is not None and (key not in milestones or milestones[key]['sim_s']>t):milestones[key]=dict(sim_s=t,wall_s=wall(t),robot=rid,wall_alignment='nearest logged SIM second')
  diag=[x['boundary_diagnostics'] for x in own if x.get('boundary_diagnostics')]
  measured=sum(v.get('status')=='measured' for v in vos);applied=sum(bool(v.get('fusion_applied')) for v in vos)
  robots[rid]=dict(ultrasonic=us,frames=len(own),stage=own[-1].get('stage') if own else None,translation_commands=translation,forward_commands=forward,actual_displacement_m=displacement,map_error_m=stat(errors),control_error_m=stat(control_errors),unaligned_frames=unaligned,position_jump_m=stat(jumps),jumps_over_20cm=sum(x>.2 for x in jumps),candidate_first_sim_s=candidate,boundary_view=own[-1].get('boundary_view') if own else None,boundary_diagnostics_latest=diag[-1] if diag else None,boundary_diagnostics_frames=len(diag),boundary_accepted_frames=sum(x.get('accepted_candidates',0)>0 for x in diag),vo=dict(trace_frames=sum(bool(v) for v in vos),measured_frames=measured,applied_frames=applied,applied_fraction=applied/max(1,len(own)),latest=vos[-1] if vos else None))
 checks.update(first_model_response=bool(p.get('first_model_response')),sim_frames_increase=p.get('sim_s',0)>0 and p.get('frames',0)>1,actual_movement=all(robots[r]['actual_displacement_m']>.005 for r in ('r1','r2')),straight_commands=all(robots[r]['forward_commands']>0 for r in ('r1','r2')),mapping_entered=p.get('phase') not in (None,'boot'),no_exception=not result.get('failure'))
 if meta.get('group')=='a':
  checks['vo_recorded']=all(robots[r]['vo']['trace_frames']>1 for r in ('r1','r2'))
  checks['ultrasonic_recorded']=all(robots[r]['ultrasonic']['range_rows']>0 and robots[r]['ultrasonic']['judgements']>0 for r in ('r1','r2'))
 log=(root/'log.txt').read_text() if (root/'log.txt').exists() else ''
 if 'Traceback (most recent call last)' in log:checks['no_exception']=False
 calls=obj(raw/'llm/model_calls.json');calls=calls if isinstance(calls,list) else []
 return dict(run=root.name,unix=time.time(),elapsed_since_submit_s=time.time()-meta['started_unix'],progress=p,result=result,checks=checks,passed=all(checks.values()),robots=robots,stage_milestones=milestones,model=dict(calls=result.get('model_calls',p.get('model_attempts')),known_cost_usd=sum((c.get('provider_usage') or {}).get('cost') or 0 for c in calls),missing_cost_calls=sum((c.get('provider_usage') or {}).get('cost') is None for c in calls)),evaluation_only=True,feedback_to_controller=False)
def stop(root,reason):
 p=obj(root/'PROCESS.json')
 try:
  start=Path(f'/proc/{p["pid"]}/stat').read_text().rsplit(')',1)[1].split()[19]
  if start==p['start'] and p['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip():
   write(root/'OBSERVER_STOP.json',dict(reason=reason,unix=time.time()));os.kill(p['pid'],signal.SIGINT)
 except (KeyError,FileNotFoundError,ProcessLookupError):pass
if __name__=='__main__':
 if len(sys.argv)>1:
  print(json.dumps(snapshot(Path(sys.argv[1])),ensure_ascii=False));raise SystemExit
 done=set();checked=set();last={};alerts=set();deadline=time.time()+26400
 while len(done)<len(NAMES) and time.time()<deadline:
  for name in NAMES:
   if name in done:continue
   root=BASE/'runs'/name;meta=obj(root/'RUN_META.json')
   if not meta:continue
   age=time.time()-meta['started_unix'];ended=(root/'EXIT').exists()
   result=obj(root/meta.get('raw_relative','raw')/'result.json')
   log=(root/'log.txt').read_text() if (root/'log.txt').exists() else ''
   crash=('Traceback (most recent call last)' in log or result.get('termination')=='HOST_ERROR' or (result.get('status')=='HOST_ERROR' and bool(result.get('traceback'))))
   success=bool(result.get('E2E_success')) and all(result.get(k) for k in ('LLM_operated','own_map_completed','start_to_finish_transport'))
   if crash or success:
    kind='execution_error' if crash else 'all_three_conditions'
    if (name,kind) not in alerts:
     ad=BASE/'e2e-usstall-alerts';ad.mkdir(exist_ok=True)
     write(ad/(name+'-'+kind+'.json'),dict(run=name,kind=kind,unix=time.time(),result=result,log_tail=log[-6000:] if crash else None))
     alerts.add((name,kind))
     if crash and not ended:stop(root,'EXECUTION_TRACEBACK')
   if ended or (age>=205 and name not in checked) or (name in checked and time.time()-last[name]>=600):
    try:
     h=snapshot(root);h['exit']=(root/'EXIT').read_text().strip() if ended else None;h['traceback_found']=crash
     if name not in checked:
      write(root/'initial-health.json',h);checked.add(name)
      if not ended and not h['passed']:stop(root,'INITIAL_OPERATIONAL_HEALTH_FAILED')
     write(root/'latest-health.json',h)
     if ended:
      write(root/'final-health.json',h);done.add(name)
      with (BASE/f'{name}-finish.log').open('x') as f:subprocess.Popen(['python3',str(BASE/'e2e-usstall-finish.py'),name],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
     else:
      with (root/'progress-checks.jsonl').open('a') as f:f.write(json.dumps(h,ensure_ascii=False)+'\n')
     last[name]=time.time();print(json.dumps(dict(run=name,ended=ended,sim_s=h['progress'].get('sim_s'),phase=h['progress'].get('phase'),passed=h['passed'])),flush=True)
    except Exception as exc:
     write(BASE/f'{name}-observer-error.json',dict(type=type(exc).__name__,message=str(exc),unix=time.time()))
   if not ended:
    (BASE/'leases'/name).touch()
    if age>=25200:stop(root,'WALL_CAP_25200S')
  time.sleep(5)
