from analyze import *
R=js(O/'beamdiag.json');out=dict(train_geometry={},student_initial={},commands={},timelines={})
for phase in ('approach','align','search','pick','all'):
 gg=[]
 for p in sorted((O/'train').glob('*.json')):
  r=js(p);f=np.load(p.with_suffix('.npz'))
  for rid,rr in r['robots'].items():
   x=f[rid+'_geometry'];ph=f[rid+'_phase'];j=0 if rr['assigned_end']=='teal' else 3;m=np.ones(len(ph),bool) if phase=='all' else ph==phase
   gg.extend(x[m,j:j+3])
 x=np.asarray(gg);out['train_geometry'][phase]=dict(N=len(x),assigned_distance_m=quant(x[:,0]),station_error_m=quant(x[:,1]),yaw_error_rad=quant(x[:,2]),outside_0p8_fraction=fraction(x[:,0]>.8))
for arm in ('A','B'):
 groups=defaultdict(list);initial=[]
 for r in R['arms'][arm]['runs']:
  raw=Path(r['raw']);cs=rows(raw/'commands.jsonl');f=np.load(O/'student'/f"{arm}-{r['seed']}.npz");ts=f['sim_s'];pred=rows(raw/'chunk-predictions.jsonl')
  for rid,rr in r['robots'].items():
   cc=[c for c in cs if c['robot']==rid];commands=[c['command'] for c in cc];g=f[rid+'_geometry'];j=0 if rr['assigned_end']=='teal' else 3;k=2 if j==0 else 9;x=f[rid+'_features'];vis=x[:,k]>=9
   initial.append(dict(seed=r['seed'],robot=rid,distance_m=float(g[0,j]),station_error_m=float(g[0,j+1]),visible=bool(vis[0])))
   origin=cc[0]['t'];bound=np.asarray([any(abs(p['t']-c['t'])<1e-6 and p['robot']==rid for p in pred) for c in cc]);active=np.asarray([not c['done'] and not c['waiting'] for c in cc]);near=g[:,j]<=.8
   groups['active'].append(cmd_stats(commands,active,bound));groups['active_near'].append(cmd_stats(commands,active&near,bound));groups['active_near_nonzero'].append(cmd_stats(commands,active&near&np.asarray([(wheel(c)!=0).any() for c in commands]),bound))
   if r['seed'] in (8329000,8329001,8329019):
    timeline=[]
    for t in [0,.3,.5,2,4,6,8,10,12,16,20,24,30,40,50,59.9]:
     idx=int(np.abs(ts-t).argmin())
     if t>ts[-1]+.1:continue
     c=cc[idx];timeline.append(dict(sim_s=float(ts[idx]),station_error_m=float(g[idx,j+1]),yaw_error_rad=float(g[idx,j+2]),wheel_class=wheel(c['command']).tolist(),pulse_ms=[round(d*1000,2) for d in c['command']['duration_s']],pwm=c['command']['pwm'],done=c['done'],assigned_band_pixels=int(x[idx,k]),body_fraction=float(x[idx,0]),body_axis=bool(x[idx,1])))
    out['timelines'][f"{arm}-{r['seed']}-{rid}"]=timeline
 out['student_initial'][arm]=dict(N=len(initial),outside_0p8_N=sum(i['distance_m']>.8 for i in initial),assigned_visible_N=sum(i['visible'] for i in initial),distance_m=quant([i['distance_m'] for i in initial]),rows=initial)
 out['commands'][arm]={name:dict(pair_N=sum(z['pair_N'] for z in vs),wheel_repeat_fraction=sum(z['wheel_repeat_N'] for z in vs)/sum(z['pair_N'] for z in vs),inference_boundary_N=sum(z['inference_boundary_pair_N'] for z in vs),inference_boundary_wheel_repeat_fraction=sum((z['inference_boundary_wheel_repeat_fraction'] or 0)*z['inference_boundary_pair_N'] for z in vs)/sum(z['inference_boundary_pair_N'] for z in vs),full_command_exact_repeat_fraction=sum((z['full_command_exact_repeat_fraction'] or 0)*z['pair_N'] for z in vs)/sum(z['pair_N'] for z in vs)) for name,vs in groups.items()}
write(O/'strata.json',out)
print(json.dumps({k:v for k,v in out.items() if k!='timelines'},indent=2))
