"""Evaluation-only supervisor; never supplies telemetry to a controller."""
import bisect,collections,hashlib,json,math,subprocess,sys,time
from pathlib import Path

def rows(p):
 if p.exists():data=p.read_bytes()
 elif p.with_suffix(p.suffix+'.zst').exists():data=subprocess.check_output(['zstd','-dc',str(p)+'.zst'],timeout=15)
 else:return [],None
 out=[]
 for line in data.splitlines():
  try:out.append(json.loads(line))
  except ValueError:pass
 return out,hashlib.sha256(data).hexdigest()

def angle(a,b):return abs(math.atan2(math.sin(a-b),math.cos(a-b)))
def still(a,b):return math.dist(a['robot_xyz_m'][:2],b['robot_xyz_m'][:2])<.02 and angle(a['robot_yaw_rad'],b['robot_yaw_rad'])<math.radians(3)

def inspect(run,cut=None):
 p=run/'raw/e2e-progress.json'
 if not p.exists():return dict(name=run.name,pending=True)
 g=json.loads(p.read_text());result={}
 if (run/'raw/result.json').exists():result=json.loads((run/'raw/result.json').read_text())
 current=max(g['sim_s'],result.get('sim_s',0)) if result.get('finalization_complete') else g['sim_s']
 end=min(current,cut) if cut else current
 decisions,dh=rows(run/'raw/body-decisions.jsonl');decisions=[r for r in decisions if r.get('t',0)<=end];robots={}
 for rid in ('r1','r2'):
  tr,th=rows(run/f'raw/eval_only/{rid}/trajectory.jsonl');tr=[r for r in tr if r['t']<=end]
  ds=[r for r in decisions if r.get('robot_id')==rid and r.get('decision')!='visual_crosscheck']
  stationary=0.;last_stationary=0.;stationary_spans=[]
  if tr:
   anchor=tr[0]
   for r in tr:
    if not still(anchor,r):
     stationary_spans.append((anchor['t'],r['t']))
     anchor=r
    last_stationary=r['t']-anchor['t'];stationary=max(stationary,last_stationary)
   stationary_spans.append((anchor['t'],tr[-1]['t']))
  intervals=[]
  for r in ds:
   # A skill lasts at most 3 SIM s plus its measured decision hold.
   # Longer silence is a navigator/no-call interval, not a repeated choice.
   valid_end=min(end,r['t']+3.+float(r.get('sim_hold_s',0)))
   if not intervals or intervals[-1]['choice']!=r.get('choice') or intervals[-1]['status']!=r.get('status') or r['t']>intervals[-1]['end']:
    if intervals:intervals[-1]['end']=min(intervals[-1]['end'],r['t'])
    intervals.append(dict(choice=r.get('choice'),status=r.get('status'),start=r['t'],end=valid_end,n=1))
   else:
    intervals[-1]['n']+=1;intervals[-1]['end']=valid_end
  longest_same_still=0.;latest_same_still=0.
  for it in intervals:
   samples=[r for r in tr if it['start']<=r['t']<=it['end']]
   it['all_stationary']=bool(samples) and all(still(samples[0],r) for r in samples)
   it['duration_s']=round(it['end']-it['start'],3)
   if it['n']>=2:
    overlap=max((max(0.,min(it['end'],b)-max(it['start'],a)) for a,b in stationary_spans),default=0.)
    longest_same_still=max(longest_same_still,round(overlap,3))
    if it is intervals[-1] and it['end']>=end-.05:latest_same_still=round(min(last_stationary,it['duration_s']),3)
  waits={'stop_and_look','hold_and_reobserve','wait_and_reobserve','hold_and_wait','wait','hold','relook_wait'}
  waitmax=max((it['duration_s'] for it in intervals if it['choice'] in waits),default=0.)
  robots[rid]=dict(calls=len(ds),choices=dict(collections.Counter(r.get('choice') or '<none>' for r in ds)),statuses=dict(collections.Counter(r.get('status') for r in ds)),max_stationary_s=round(stationary,3),tail_stationary_s=round(last_stationary,3),max_same_choice_without_motion_s=longest_same_still,tail_same_choice_without_motion_s=latest_same_still,max_wait_choice_interval_s=waitmax,last_interval=intervals[-1] if intervals else None,eval_trajectory_sha256=th)
 result={}
 if (run/'raw/result.json').exists():result=json.loads((run/'raw/result.json').read_text())
 return dict(name=run.name,checked_unix=time.time(),cut_sim_s=end,current_sim_s=current,phase=g['phase'],frames=g['frames'],exit=(run/'EXIT').read_text().strip() if (run/'EXIT').exists() else None,model_calls=g['model_attempts'],body_sha256=dh,robots=robots,failure=result.get('controller_failure') or result.get('failure') if result.get('finalization_complete') else None)
roots=[]
for root in sorted((Path.home()/'ugrp-sim/runs').glob(sys.argv[1])):
 if root.is_dir():roots.extend(root.glob('speed-gate-*')) if root.name.startswith('speed-gate-') else roots.append(root)
print(json.dumps([inspect(r,float(sys.argv[2]) if len(sys.argv)>2 else None) for r in roots]))
