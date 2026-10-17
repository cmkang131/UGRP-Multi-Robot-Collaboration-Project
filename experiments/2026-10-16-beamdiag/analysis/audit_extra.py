from analyze import *
from concurrent.futures import ProcessPoolExecutor

def one(task):
 arm,seed=task;r=B/f'ops-reviews/beamact3/{arm}/heldout20-v1/seed-{seed}';ev=rows(r/'eval-only.jsonl');commands=rows(r/'commands.jsonl');obs=rows(r/'student-inputs.jsonl');result=js(r/'result.json');first={};fp=Counter();fr=Counter();stages=('approach','alignment','READY','grasp','lift_3s');events=[];maxhold=hold=0.;last=None
 for e in ev:
  stable=e['truth']['beam']['min_z']>=.012 and e['truth']['beam']['tilt_deg']<=10 and min(v for f in e['assigned_contact_forces'].values() for v in f)>=.5
  hold=hold+(e['t']-last) if stable and last is not None else 0.;last=e['t'];maxhold=max(maxhold,hold)
  for i,s in enumerate(stages):
   eligible=i==0 or stages[i-1] in first
   if eligible and e['passed'][s]:first.setdefault(s,e['t']);fp[s]+=1
   elif eligible:fr[s]+=1
  ends=e['truth']['beam']['ends'];poses={rid:e['truth']['robots'][rid]['pose'] for rid in ('r1','r2')};ds={rid:{c:math.dist(p[:2],v[:2]) for c,v in ends.items()} for rid,p in poses.items()}
  for color in ('teal','blue'):
   if all(ds[rid][color]<=.203+.03 and ds[rid][color]<ds[rid]['blue' if color=='teal' else 'teal'] for rid in poses):events.append(dict(sim_s=e['sim_s'],end=color,center_separation_m=math.dist(poses['r1'][:2],poses['r2'][:2])))
 assert first==result['funnel']['first_pass_sim_t'];assert {s:fp[s] for s in stages}==result['funnel']['frames_pass'];assert {s:fr[s] for s in stages}==result['funnel']['frames_rejected']
 output=dict(arm=arm,seed=seed,recount_funnel_matches=True,eval_N=len(ev),input_command_N=len(obs),same_end_close_frames_N=len(events),same_end_close_time_range_s=[events[0]['sim_s'],events[-1]['sim_s']] if events else None,same_end_close_end=sorted({v['end'] for v in events}),same_end_close_min_center_sep_m=min(v['center_separation_m'] for v in events) if events else None,same_end_close_basis='both robot origins within authored station0.203m + inherited XYtol0.03m of same end, and strictly nearer than other end; evaluation only; not contact proof',min_target_finger_gap_m=min(e['target_finger_min_gap_m'] for e in ev),max_unrestricted_hold_s=max(e['unrestricted_score']['max_stable_lift_s'] for e in ev),max_assigned_hold_s=max(e['score']['max_stable_lift_s'] for e in ev),max_beam_clearance_m=max(e['truth']['beam']['min_z'] for e in ev),done_geometry={})
 for rid in ('r1','r2'):
  cc=[c for c in commands if c['robot']==rid];ii=next((k for k,c in enumerate(cc) if c['done']),None)
  if ii is not None:output['done_geometry'][rid]=dict(sim_s=ev[ii]['sim_s'],beam_clearance_m=ev[ii]['truth']['beam']['min_z'],assigned_forces=ev[ii]['assigned_contact_forces'][rid],unrestricted_forces=ev[ii]['truth']['contacts'][rid],pwm=cc[ii]['command']['pwm'])
 write(O/'student'/f'{arm}-{seed}-extra.json',output);return output
with ProcessPoolExecutor(max_workers=8) as p:out=list(p.map(one,[(a,s) for a in ('A','B') for s in CFG['heldout_seeds']]))
write(O/'extra-audit.json',dict(runs=out,all_funnels_match=True))
for a in ('A','B'):
 q=[r for r in out if r['arm']==a]
 print(a,'same_end_close',[(r['seed'],r['same_end_close_time_range_s']) for r in q if r['same_end_close_frames_N']], 'unrestricted_hold',[(r['seed'],r['max_unrestricted_hold_s']) for r in q if r['max_unrestricted_hold_s']>=3])
