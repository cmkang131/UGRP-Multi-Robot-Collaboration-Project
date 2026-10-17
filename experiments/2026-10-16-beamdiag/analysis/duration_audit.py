from analyze import *
def contiguous(m,t):
 best=run=0
 for i,yes in enumerate(m):
  run=(run+1 if i and abs(t[i]-t[i-1]-.1)<1e-5 else 1) if yes else 0
  best=max(best,run)
 return best*.1
R=js(O/'beamdiag.json');dwell=defaultdict(list);blind=Counter();epochs=Counter();records=[]
for p in (O/'train').glob('*.json'):
 r=js(p);f=np.load(p.with_suffix('.npz'))
 for rid,rr in r['robots'].items():
  ph=f[rid+'_phase'];x=f[rid+'_features'];ts=f[rid+'_t']
  for phase in ('approach','align','ready','pick','search'):
   m=ph==phase
   if m.any():dwell[phase].append(contiguous(m,ts))
  rrblind=(x[:,1]>0)&(x[:,2]<9)&(x[:,9]<9)
  for phase in ('approach','align','ready','pick','search'):
   m=ph==phase;epochs[phase]+=int(m.sum());blind[phase]+=int((rrblind&m).sum())
for arm in ('A','B'):
 for r in R['arms'][arm]['runs']:
  for rid,rr in r['robots'].items():
   if rr['visual']['body_axis_no_end_fraction']>=.5:records.append(dict(arm=arm,seed=r['seed'],robot=rid,fraction=rr['visual']['body_axis_no_end_fraction'],longest_s=rr['visual']['body_axis_no_end_longest_s'],first_done=rr['first_done_sim_s'],first_ready=rr['first_ready_sim_s'],max_assigned_lift_s=r['raw_recount']['max_assigned_hold_s']))
out=dict(TRAIN_phase_contiguous_duration_s={p:dict(actor_N=len(x),q=quant(x)) for p,x in dwell.items()},TRAIN_blind_counts=dict(blind),TRAIN_phase_N=dict(epochs),student_majority_blind_actors=records)
write(O/'duration-audit.json',out);print(json.dumps(out,indent=2))
