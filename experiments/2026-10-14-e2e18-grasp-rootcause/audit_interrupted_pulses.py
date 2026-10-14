import json,math,pathlib,subprocess,statistics,bisect,hashlib
root=pathlib.Path.home()/'ugrp-sim/runs/grasp-teacher-gate-9d9b90b9/cohort-000'
def read(p):
 if not p.exists():p=pathlib.Path(str(p)+'.zst')
 b=p.read_bytes();raw=subprocess.check_output(['zstd','-qdc'],input=b) if p.suffix=='.zst' else b
 return [json.loads(x) for x in raw.splitlines()],{'path':str(p),'sha256':hashlib.sha256(b).hexdigest()}
def wrap(a):return math.atan2(math.sin(a),math.cos(a))
def stats(v):
 v=sorted(v)
 return {'N':len(v),'median':statistics.median(v) if v else None,'p95':v[min(len(v)-1,int(.95*len(v)))] if v else None,'max':max(v) if v else None}
report={'rows':[],'all_pulses':[],'raw':[],'scope':'all 16 episodes administratively interrupted; no physical gate denominator'}
for case in sorted(root.glob('episode-*')):
 ev,source=read(case/'raw/eval-only.jsonl');report['raw'].append(source);times=[x['t'] for x in ev]
 plan=json.loads((case/'raw/plan.json').read_text())
 for rid,end in plan['roles'].items():
  ys,source=read(case/f'raw/teacher-{rid}.jsonl');report['raw'].append(source);phase={};pulses=[];previous={};switches={};errors=[]
  for i,y in enumerate(ys):
   c=y['applied_command'];t=c['t'];p=y['teacher_phase'];phase[p]=phase.get(p,0)+.1
   if p=='align':
    pose=ev[i]['robots'][rid]['pose'];g=ev[i]['beam']['ends'][end];dx,dy=g[0]-pose[0],g[1]-pose[1];co,si=math.cos(pose[2]),math.sin(pose[2]);errors.append((t,1000*(co*dx+si*dy-.203),1000*(-si*dx+co*dy),math.degrees(wrap(ev[i]['beam']['pose'][2]+(math.pi if end=='blue' else 0)-pose[2]))))
   if not any(c['drive']):continue
   axis=next(j for j,v in enumerate(c['drive']) if v);sign=1 if c['drive'][axis]>0 else -1;key=(p,axis)
   if key in previous and previous[key]!=sign:switches[key]=switches.get(key,0)+1
   previous[key]=sign
   j=bisect.bisect_left(times,t+c['duration_s']+.2-1e-7)
   if j>=len(ev):continue
   a=ev[i]['robots'][rid]['pose'];b=ev[j]['robots'][rid]['pose'];dx,dy=b[0]-a[0],b[1]-a[1];co,si=math.cos(a[2]),math.sin(a[2]);delta=[1000*(co*dx+si*dy),1000*(-si*dx+co*dy),math.degrees(wrap(b[2]-a[2]))]
   pulses.append({'phase':p,'axis':axis,'duration':c['duration_s'],'t':t,'dt':times[j]-t,'sign':sign,'directed_delta':sign*delta[axis],'delta':delta})
  metrics={}
  for p in ('approach','align'):
   for axis in range(3):
    for dur in (.06,.15):
     vals=[x['directed_delta'] for x in pulses if (x['phase'],x['axis'],x['duration'])==(p,axis,dur)]
     if vals:metrics[f'{p}:{axis}:{dur}']=stats(vals)
  row={'case':case.name,'robot':rid,'end':end,'phase_sim_s':phase,'direction_reversals':{f'{p}:{a}':n for (p,a),n in switches.items()},'pulse_stats':metrics,'align_start_end_error':errors[:1]+errors[-1:],'align_error_ranges':{name:stats([abs(x[i+1]) for x in errors]) for i,name in enumerate(('forward_mm','side_mm','yaw_deg'))},'pulses':pulses,'align_errors':errors}
  report['rows'].append(row);report['all_pulses'].extend(pulses)
report['aggregate']={}
for axis in range(3):
 for dur in (.06,.15):
  vals=[x['directed_delta'] for x in report['all_pulses'] if x['phase']=='align' and x['axis']==axis and x['duration']==dur]
  if vals:report['aggregate'][f'align:{axis}:{dur}']=stats(vals)
report.pop('all_pulses')
print(json.dumps(report))
