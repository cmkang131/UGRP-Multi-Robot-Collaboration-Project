"""Remote-only raw pulse recount; never consumes truth at runtime."""
import collections,hashlib,json,math,pathlib,statistics,subprocess
RUN='crate18-full-reproduction-79314-487579ea'
p=pathlib.Path.home()/'ugrp-sim/runs'/RUN/'raw'
def load(n):
 f=p/n
 b=f.read_bytes() if f.exists() else subprocess.check_output(['zstd','-dc',str(f)+'.zst'])
 return [json.loads(s) for s in b.splitlines()]
ts=load('teacher-r2.jsonl');ev=load('eval-only.jsonl');times=[v['t'] for v in ev]
reasons=collections.Counter();pulses=[];ready=[]
for i,t in enumerate(ts):
 if t['teacher_phase']=='ready' and (i==0 or ts[i-1]['teacher_phase']!='ready'):ready.append(t['t'])
 states=t.get('crate18_states')
 if states and t['teacher_phase'] in ('align','ready'):
  for axis,s in enumerate(states):
   if not s['settled']:reasons[f'axis{axis}_outside_settle_band']+=1
 c=t.get('applied_command',{});w=c.get('wheels',[0]*4)
 if t['teacher_phase'] not in ('align','ready') or not any(w):continue
 v=(sum(w),-w[0]+w[1]+w[2]-w[3],-w[0]+w[1]-w[2]+w[3]);axis=max(range(3),key=lambda a:abs(v[a]))
 k=min(range(len(ev)),key=lambda k:abs(ev[k]['t']-t['t']))
 a=ev[k]['robots']['r2']['pose'];b=ev[min(k+1,len(ev)-1)]['robots']['r2']['pose'];h=a[2]
 forward=(b[0]-a[0])*math.cos(h)+(b[1]-a[1])*math.sin(h)
 other=[j for j in range(i+1,len(ts)) if any(ts[j].get('applied_command',{}).get('wheels',[]))]
 ni=other[0] if other else len(ts)-1
 end=min(range(len(ev)),key=lambda k:abs(ev[k]['t']-ts[ni]['t']))
 q=ev[end]['robots']['r2']['pose']
 net=(q[0]-a[0])*math.cos(h)+(q[1]-a[1])*math.sin(h)
 s=states[axis] if states else {}
 ns=ts[ni].get('crate18_states')
 pulses.append(dict(t=t['t'],axis=axis,sign=math.copysign(1,v[axis]),width_s=max(c['duration_s']),error=s.get('error'),tolerance=s.get('tolerance'),delta=s.get('delta'),
 effect_next_sample_m=forward,retained_to_next_command_m=net,next_command_t=ts[ni]['t'],next_error=ns[axis]['error'] if ns else None))
forward=[x for x in pulses if x['axis']==0 and x['t']>=50 and x['sign']>0]
summary=dict(run=RUN,scope='evaluation only; own visible errors separately from true physical displacement',rejection_distribution=dict(reasons),ready_entries=ready,
 all_pulses=len(pulses),forward_window=[50,ev[-1]['t']],forward_N=len(forward),
 forward_next_sample_median_mm=1000*statistics.median(x['effect_next_sample_m'] for x in forward),
 retained_next_command_median_mm=1000*statistics.median(x['retained_to_next_command_m'] for x in forward),
 delta_mm=3.071185,tolerance_mm=1.842711,trace=pulses,
 inputs={n:hashlib.sha256((p/(n+'.zst')).read_bytes()).hexdigest() for n in ['teacher-r2.jsonl','eval-only.jsonl']})
print(json.dumps(summary,separators=(',',':')))
