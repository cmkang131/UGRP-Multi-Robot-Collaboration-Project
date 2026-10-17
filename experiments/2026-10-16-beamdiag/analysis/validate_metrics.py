from analyze import *
from collections import Counter
R=js(O/'beamdiag.json');S=js(O/'strata.json');cm=Counter();wrong=Counter();epwrong=[];maximumdist=S['train_geometry']['align']['assigned_distance_m']['max'];maxstation=S['train_geometry']['align']['station_error_m']['max']
for p in (O/'train').glob('*.json'):
 r=js(p);f=np.load(p.with_suffix('.npz'))
 for rid,rr in r['robots'].items():
  x=f[rid+'_features'];ph=f[rid+'_phase'];tr=f[rid+'_truth_visible'];g=f[rid+'_geometry'];j=2 if rr['assigned_end']=='teal' else 9;k=0 if j==2 else 3;m=np.isin(ph,['approach','align']);pr=x[:,j]>=9
  cm['N']+=int(m.sum());cm['TP']+=int((m&pr&tr).sum());cm['TN']+=int((m&~pr&~tr).sum());cm['FP']+=int((m&pr&~tr).sum());cm['FN']+=int((m&~pr&tr).sum())
  yes=g[:,k+1]<=.03;no=g[:,3-k+1]<=.03;ai=np.flatnonzero(yes);oi=np.flatnonzero(no)
  first='assigned' if len(ai) and (not len(oi) or ai[0]<=oi[0]) else 'opposite' if len(oi) else 'neither';wrong[first]+=1
  if first=='opposite':epwrong.append([r['seed'],rid])
output=dict(TRAIN_approach_align_color_assay_vs_geometric5probe_visible=dict(cm),TRAIN_first_station_visits=dict(wrong),TRAIN_opposite_first=epwrong,align_proxy_basis=dict(distance_m=maximumdist,station_error_m=maxstation,origin='maximum TRAIN align raw geometry; descriptive stratum, no controller change'),arms={})
for arm in ('A','B'):
 stats=[];still=[]
 for r in R['arms'][arm]['runs']:
  p=Path(r['raw']);cc=rows(p/'commands.jsonl');f=np.load(O/'student'/f"{arm}-{r['seed']}.npz");pred=rows(p/'chunk-predictions.jsonl')
  for rid,rr in r['robots'].items():
   cs=[z for z in cc if z['robot']==rid];g=f[rid+'_geometry'];j=0 if rr['assigned_end']=='teal' else 3;near=(g[:,j]<=maximumdist)&(g[:,j+1]<=maxstation);active=np.asarray([not z['done'] and not z['waiting'] for z in cs]);bound=np.asarray([any(abs(z['t']-c['t'])<1e-6 and z['robot']==rid for z in pred) for c in cs]);stats.append(cmd_stats([z['command'] for z in cs],near&active,bound))
   if r['seed']==8329001:
    m=f['sim_s']>=20;w=np.asarray([wheel(z['command']) for z in cs]);still.append(dict(robot=rid,after20_N=int(m.sum()),all_wheel_zero_fraction=fraction((w[m]==0).all(1)),yaw_after20_rad=quant(g[m,j+2]),station_after20_m=quant(g[m,j+1])))
 den=sum(z['pair_N'] for z in stats);bden=sum(z['inference_boundary_pair_N'] for z in stats)
 output['arms'][arm]=dict(align_proxy_active=dict(pair_N=den,wheel_repeat_fraction=sum(z['wheel_repeat_N'] for z in stats)/den,boundary_N=bden,inference_boundary_wheel_repeat_fraction=sum((z['inference_boundary_wheel_repeat_fraction'] or 0)*z['inference_boundary_pair_N'] for z in stats)/bden,full_command_exact_repeat_fraction=sum((z['full_command_exact_repeat_fraction'] or 0)*z['pair_N'] for z in stats)/den),seed8329001_after20=still)
write(O/'metric-validation.json',output);print(json.dumps(output,indent=2))
