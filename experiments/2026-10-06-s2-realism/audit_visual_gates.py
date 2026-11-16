import sys,json,pathlib,collections,hashlib,numpy as np,cv2
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/drive-friction')
from harness.zone_solo_cyan_visual_fix import flow_pair,FLOW
from harness.zone_solo_cyan_pulse_cal import profile_key
ROOT=pathlib.Path('/Users/changmin/projects/ugrp/outputs');OUT=ROOT/'s2-visual-fix-20261007'
model=json.loads(pathlib.Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text())
summary={};flows=[]
for seed,stem in [(1022,'s2-graduation-fae1fc4a-s1022-P1-2-place'),(1045,'s2-realism-f0bb26e7-s1045-P1-2-place'),(1046,'s2-realism-e619ee57-s1046-P1-2-place')]:
 run=ROOT/stem;s=json.loads((run/'student_record.json').read_text());ev=[e for e in s['events'] if e['event']=='state'];phases=[]
 for i,e in enumerate(ev[:-1]):
  if e['state']=='carry':
   start,end=e['t'],ev[i+1]['t'];ps=[p for p in s['poses'] if start<=p['t']<end];g=[p['last_scan_gate'] for p in ps if p.get('last_scan_gate')]
   fixes=sorted(set(p['last_fix_t'] for p in ps if p['last_fix_t'] is not None and p['last_fix_t']>=start))
   phases.append(dict(start=start,end=end,frames=len(ps),scan_gates=len(g),unique_fixes=len(fixes),fixes_per_second=len(fixes)/(end-start),last_fix=ps[-1]['last_fix_t'],
      rejection_counts=dict(fraction=sum(q.get('inlier_fraction',0)<.66 for q in g),support=sum(q.get('posterior_support',0)<.10 for q in g),rank=sum(q.get('observed_rank',0)<2 for q in g),saturated=sum(q.get('saturated',False) for q in g)),
      medians={k:float(np.median([q[k] for q in g if k in q])) if g else None for k in ('inlier_fraction','posterior_support')},
      n_terms_median=float(np.median([p['observation_quality']['diagnostics'].get('n_terms',0) for p in ps]))))
 summary[str(seed)]=dict(path=str(run),student_sha256=hashlib.sha256((run/'student_record.json').read_bytes()).hexdigest(),carry_phases=phases,provider_counts=s['provider']['provider']['counts'],
  max_fix_gap_s=max(np.diff(sorted(set([p['last_fix_t'] for p in s['poses'] if p['last_fix_t'] is not None])))))
 if seed==1022:continue
 fs=[json.loads(l) for l in (run/'robots/r3/frames.jsonl').read_text().splitlines()];ts=np.array([f['sim_time'] for f in fs]);tr=[json.loads(l) for l in (run/'eval_only/trajectory.jsonl').read_text().splitlines()];tt=np.array([t['t'] for t in tr]);streak=0
 for cmd in s['commands']:
  if cmd['kind']!='mecanum' or not any(cmd.get(k,0) for k in ('forward','left','turn')):continue
  if not any(p['start']<=cmd['t']<p['end'] for p in phases):continue
  try:profile=model['profiles'][profile_key(cmd,True)]
  except KeyError:continue
  i=int(np.argmin(abs(ts-cmd['t'])));j=int(np.searchsorted(ts,cmd['t']+profile['times'][-1]-1e-8))
  if j>=len(fs) or fs[i]['commanded_servo']!=fs[j]['commanded_servo']:streak=0;continue
  def image_at(n):
   f=fs[n];data=(run/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256'];return cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
  flow=flow_pair(image_at(i),image_at(j));streak=streak+1 if flow['status']=='stationary_view' else 0
  # Evaluation only, after own-input verdict. No truth enters flow_pair.
  a=tr[int(np.argmin(abs(tt-ts[i])))];b=tr[int(np.argmin(abs(tt-ts[j])))];dy=(b['robot_yaw_rad']-a['robot_yaw_rad']+np.pi)%(2*np.pi)-np.pi
  flows.append(dict(seed=seed,t=cmd['t'],before=fs[i]['path'],after=fs[j]['path'],command=cmd,**flow,streak=streak,would_stop=streak>=3,
    eval_only=dict(distance_m=float(np.linalg.norm(np.array(b['robot_xyz_m'][:2])-a['robot_xyz_m'][:2])),yaw_deg=float(np.degrees(dy)))))
 for_status=collections.Counter(x['status'] for x in flows if x['seed']==seed)
 summary[str(seed)]['flow']=dict(counts=dict(for_status),would_stop=sum(x['would_stop'] for x in flows if x['seed']==seed),stationary_samples=[x for x in flows if x['seed']==seed and x['status']=='stationary_view'][:6])
 print(seed,summary[str(seed)]['flow']['counts'],flush=True)
(OUT/'saved-audit.json').write_text(json.dumps(summary,indent=2)+'\n');(OUT/'flow-audit.json').write_text(json.dumps(flows,indent=1)+'\n')
print(json.dumps({k:v['carry_phases'] for k,v in summary.items()},indent=1))
