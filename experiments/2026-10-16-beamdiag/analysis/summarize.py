"""Descriptive distributions and ordered rejection counts. No new control path."""
from analyze import *
from scipy.signal import find_peaks

def vv(f,role,ts=None,mask=None,edge=0.,prominence=1.):
 n=len(f);sel=np.ones(n,bool) if mask is None else np.asarray(mask,bool)
 j=2 if role=='teal' else 9;v=f[:,j]>=9;blind=(f[:,1]>0)&(f[:,2]<9)&(f[:,9]<9);u=f[:,j+1];y=f[:,j+2]
 m=sel&v;rad=np.sqrt((u-.5)**2+(y-.5)**2);margin=np.minimum.reduce([u,1-u,y,1-y]);out=dict(N=int(sel.sum()),assigned_visible_N=int(m.sum()),assigned_visible_fraction=fraction(v[sel]),body_frame_fraction=quant(f[sel,0]),body_majority_fraction=fraction((f[:,0]>=.5)[sel]),body_axis_no_end_fraction=fraction(blind[sel]),body_axis_no_end_longest_s=longest(blind&sel),assigned_center_min_normalized_radius=float(rad[m].min()) if m.any() else None,assigned_center_min_pixels_320x240=float(np.sqrt(((u[m]-.5)*320)**2+((y[m]-.5)*240)**2).min()) if m.any() else None,assigned_center_min_horizontal_pixels=float((np.abs(u[m]-.5)*320).min()) if m.any() else None,assigned_center_horizontal_q=quant(u[m]),assigned_center_vertical_q=quant(y[m]),edge_margin_threshold_train_align_p10=edge,assigned_edge_fraction_visible=fraction((margin<edge)[m]),visibility_sensitivity={str(k):fraction((f[:,j]>=k)[sel]) for k in (1,9,25)},oscillation_prominence_px=prominence)
 # Do not bridge invisible frames, excluded intervals, or >one-tick gaps.
 valid=m.copy()
 if ts is not None:valid[1:] &= np.diff(ts)<.10001
 edges=np.diff(np.r_[False,valid,False].astype(int));starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
 reversals=rawreversals=crossings=0;amplitudes=[]
 for s,e in zip(starts,ends):
  z=u[s:e]*320
  if len(z)<3:continue
  peaks=find_peaks(z,prominence=prominence)[0];valleys=find_peaks(-z,prominence=prominence)[0];ext=sorted([*peaks,*valleys]);reversals+=len(ext)
  if len(ext)>1:amplitudes.extend(np.abs(np.diff(z[ext])).tolist())
  d=np.sign(np.diff(np.rint(z)));d=d[d!=0]
  rawreversals+=int((d[1:]!=d[:-1]).sum());sg=np.sign(z-160);sg=sg[sg!=0];crossings+=int((sg[1:]!=sg[:-1]).sum())
 out.update(horizontal_reversal_extrema_N=reversals,horizontal_rounded1px_reversals_N=rawreversals,centerline_crossings_N=crossings,extrema_horizontal_excursion_px=quant(amplitudes))
 return out

def weighted(items,key,den='pair_N'):
 good=[(r[key],r[den]) for r in items if r.get(key) is not None and r.get(den,0)>0]
 return sum(x*n for x,n in good)/sum(n for x,n in good) if good else None

def summarize():
 train=[];prebody=[];alignmargin=[];step=[];trainvis=[]
 for p in sorted((O/'train').glob('*.json')):
  r=js(p);f=np.load(p.with_suffix('.npz'))
  for rid,rr in r['robots'].items():
   x=f[rid+'_features'];ph=f[rid+'_phase'];ts=f[rid+'_t'];j=2 if rr['assigned_end']=='teal' else 9
   m=ph=='align';vis=x[:,j]>=9;u=x[:,j+1];v=x[:,j+2]
   alignmargin.extend(np.minimum.reduce([u,1-u,v,1-v])[m&vis]);sel=m[1:]&m[:-1]&vis[1:]&vis[:-1]&(np.diff(ts)<.10001)
   step.extend(np.abs(np.diff(u))[sel]*320)
   train.append((r['seed'],rid,rr,x,ph,ts,f[rid+'_geometry'],f[rid+'_truth_visible']))
 edge=float(np.quantile(alignmargin,.1));prominence=max(1.,float(np.quantile(step,.95)))
 trainstats={};phases=sorted(set(np.concatenate([a[4] for a in train]).tolist()))
 for phase in phases+['all','pregrasp']:
  chunks=[];blindruns=[];cm=[];examples=[]
  for seed,rid,rr,x,ph,ts,gg,trvis in train:
   m=np.ones(len(ph),bool) if phase=='all' else np.isin(ph,['approach','align','search','relook','ready']) if phase=='pregrasp' else ph==phase
   if not m.any():continue
   j=2 if rr['assigned_end']=='teal' else 9
   # Remap assigned band to teal slots so pooled summaries retain roles.
   z=x.copy()
   if j==9:z[:,2:9],z[:,9:16]=x[:,9:16],x[:,2:9]
   chunks.append(z[m]);blind=(x[:,1]>0)&(x[:,2]<9)&(x[:,9]<9)&m
   blindruns.append(longest(blind));
   if phase in rr['commands']:cm.append(rr['commands'][phase])
   if phase=='all':cm.append(rr['commands_all'])
   if blind.any():examples.append(dict(seed=seed,robot=rid,blind_N=int(blind.sum()),longest_s=longest(blind)))
  arr=np.concatenate(chunks)
  v=vv(arr,'teal',edge=edge,prominence=prominence)
  # Oscillation and dwell must respect episode boundaries: pooled contiguous
  # values are not time series. Replace pooled reversal/dwell with per-actor.
  vm=[vv(x,rr['assigned_end'],ts,np.ones(len(ph),bool) if phase=='all' else np.isin(ph,['approach','align','search','relook','ready']) if phase=='pregrasp' else ph==phase,edge,prominence) for seed,rid,rr,x,ph,ts,gg,trvis in train]
  v['body_axis_no_end_longest_s']=max(blindruns);v['actor_longest_blind_s']=quant(blindruns);v['horizontal_reversal_extrema_N']=sum(t['horizontal_reversal_extrema_N'] for t in vm);v['horizontal_rounded1px_reversals_N']=sum(t['horizontal_rounded1px_reversals_N'] for t in vm);v['centerline_crossings_N']=sum(t['centerline_crossings_N'] for t in vm);v.pop('extrema_horizontal_excursion_px')
  trainstats[phase]=dict(visual=v,commands=dict(pair_N=sum(t['pair_N'] for t in cm),wheel_repeat_fraction=weighted(cm,'wheel_repeat_fraction'),full_command_exact_repeat_fraction=weighted(cm,'full_command_exact_repeat_fraction'),duty_delta_abs_mean=weighted(cm,'duty_delta_abs_mean')),blind_actors=examples)
 blind_limit=trainstats['pregrasp']['visual']['body_axis_no_end_longest_s']
 result=dict(schema='ugrp.beamdiag.v1',analysis_only=True,host=dict(project='ugrp-sim-b-1014',account='changmin5781@gmail.com',instance='ugrp-sim-gcp2',machine_type='n4-highcpu-64'),source_analysis_sha256=sha(Path(__file__)),train_N=60023,train_seed_N=166,train=trainstats,thresholds=dict(color_assay=js(O/'scan-complete.json')['image_assay'],visible_largest_component_pixels=9,visible_sensitivity=[1,9,25],area_basis='minimum observed component among >=5-probe-visible TRAIN frames=34 pixels; tested1/9/25; >=9 is3x3 connected-pixel reporting assay, not control',edge_margin=edge,edge_basis='TRAIN align visible centroid frame-margin p10',oscillation_prominence_px=prominence,oscillation_basis='TRAIN align adjacent visible horizontal displacement p95; 1px resolution floor',body_occlusion_primary_basis='one actor axis-body/no-end in >=half of run frames; literal majority, not controller tolerance',sustained_blind_longest_s_above=blind_limit,blind_basis='strictly beyond maximum TRAIN pregrasp contiguous axis-body/no-end dwell',station_m=.203,XY_tol_m=.03,yaw_tol_rad=.06,geometry_basis='inherited pinned teacher/evaluator; not new acceptance criteria'),arms={})
 assert sum(rr['N'] for _,_,rr,*rest in train)==60023
 rejection=dict(schema='ugrp.beamdiag.rejections.v1',source_root=str(O),reproduce='env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python /home/ugrp/ugrp-sim/analysis-tools/beamdiag/analyze.py && /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python /home/ugrp/ugrp-sim/analysis-tools/beamdiag/summarize.py',arms={})
 for arm in ('A','B'):
  rruns=[];categories=Counter();runstage=Counter();framepass=Counter();framereject=Counter();facts=Counter();commands=[];commandsnear=[];input_rows=0;vparts=[];nearparts=[]
  for p in [O/'student'/f'{arm}-{seed}.json' for seed in CFG['heldout_seeds']]:
   r=js(p);r['raw_recount']=js(p.with_name(p.stem+'-extra.json'));f=np.load(p.with_suffix('.npz'));ts=f['sim_s'];anyblind=False;wrongfirst=False;everwrong=False
   actual=[]
   for rid,rr in r['robots'].items():
    x=f[rid+'_features'];gg=f[rid+'_geometry'];j=0 if rr['assigned_end']=='teal' else 3;k=3-j
    rr['visual']=vv(x,rr['assigned_end'],ts,edge=edge,prominence=prominence);rr['visual_near_assigned_end']=vv(x,rr['assigned_end'],ts,gg[:,j]<=.8,edge,prominence)
    av=(gg[:,j+1]<=.03)&(gg[:,j+2]<=.06);ov=(gg[:,k+1]<=.03)&(gg[:,k+2]<=.06)
    avxy=gg[:,j+1]<=.03;ovxy=gg[:,k+1]<=.03
    ai=np.flatnonzero(avxy);oi=np.flatnonzero(ovxy)
    first='assigned' if len(ai) and (not len(oi) or ai[0]<=oi[0]) else 'opposite' if len(oi) else 'neither'
    rr['approached_end_evidence']=dict(first_3cm_station_visit=first,first_assigned_XY_sim_s=float(ts[ai[0]]) if len(ai) else None,first_other_XY_sim_s=float(ts[oi[0]]) if len(oi) else None,other_station_min_m=float(gg[:,k+1].min()),other_end_min_distance_m=float(gg[:,k].min()),other_aligned_any=bool(ov.any()),assigned_aligned_any=bool(av.any()),limitation='XY visit is evaluation geometry; it does not establish intent or correct facing. Initial r2 station is included.')
    wrongfirst|=first=='opposite';everwrong|=bool(ovxy.any());actual.append(rr['final_nearest_end'])
    blind=rr['visual']['body_axis_no_end_longest_s']>blind_limit;anyblind|=blind
    facts['actor_sustained_blind']+=blind;facts['actor_done']+=rr['first_done_sim_s'] is not None
    facts['actor_ready_before_individual_alignment']+=rr['first_ready_sim_s'] is not None and (rr['first_ready_geometry']['station_error_m']>.03 or rr['first_ready_geometry']['yaw_error_rad']>.06)
    commands.append(rr['commands']['all']);commandsnear.append(rr['commands']['near_assigned_end']);input_rows+=len(x)
    z=x.copy()
    if j==3:z[:,2:9],z[:,9:16]=x[:,9:16],x[:,2:9]
    vparts.append(z);nearparts.append(z[gg[:,j]<=.8])
   # Primary categories are mutually exclusive, using inherited run funnel
   # before mechanism flags. Wrong-end visit uses3cm authored stance evidence,
   # never final nearest-half alone; long blindness calibrated on TRAIN max.
   if not r['funnel']['cumulative_run_pass']['approach']:cat='approach_not_acquired'
   elif r['raw_recount']['same_end_close_frames_N']>0:cat='same_end_close_competition'
   elif wrongfirst:cat='opposite_end_station_first'
   elif any(v['visual']['body_axis_no_end_fraction']>=.5 for v in r['robots'].values()):cat='body_occlusion_majority'
   elif r['funnel']['failure_stage']=='grasp':cat='grasp_after_alignment'
   elif any(v['assigned_station_error_m']['min']>.03 for v in r['robots'].values()):cat='assigned_station_not_reached'
   else:cat='alignment_not_completed'
   r['final_state']=('both_done_wrong_end_lift' if r['raw_recount']['max_unrestricted_hold_s']>=3 and not r['physical_success'] else 'one_done_peer_incomplete' if sum(v['first_done_sim_s'] is not None for v in r['robots'].values())==1 else 'both_incomplete' if all(v['first_done_sim_s'] is None for v in r['robots'].values()) else 'both_done_failed')
   r['primary_category']=cat;r['flags']=dict(same_end_close_competition=r['raw_recount']['same_end_close_frames_N']>0,sustained_body_occlusion=anyblind,opposite_station_first=wrongfirst,ever_opposite_station=everwrong,final_same_nearest_end=r['same_end_final'])
   categories[cat]+=1;facts['run_sustained_blind']+=anyblind;facts['run_opposite_station_first']+=wrongfirst;facts['run_ever_opposite_station']+=everwrong;facts['run_final_same_half']+=r['same_end_final']
   facts['run_same_end_close_competition']+=r['raw_recount']['same_end_close_frames_N']>0
   facts['cap_end']+=r['cap_end'];facts['HOST_ERROR']+=not r['complete'];facts['physical_success']+=r['physical_success']
   for st,n in r['funnel']['cumulative_run_pass'].items():runstage[st]+=n
   framepass.update(r['funnel']['frames_pass']);framereject.update(r['funnel']['frames_rejected'])
   rruns.append(r)
  pooled=vv(np.concatenate(vparts),'teal',edge=edge,prominence=prominence);poolednear=vv(np.concatenate(nearparts),'teal',edge=edge,prominence=prominence)
  for v in (pooled,poolednear):
   for k in ('horizontal_reversal_extrema_N','horizontal_rounded1px_reversals_N','centerline_crossings_N','body_axis_no_end_longest_s','extrema_horizontal_excursion_px'):v.pop(k)
  result['arms'][arm]=dict(N=20,input_rows=input_rows,category_distribution=dict(categories),facts=dict(facts),funnel={s:dict(cumulative_runs=runstage[s],frame_pass=framepass[s],frame_reject=framereject[s]) for s in ('approach','alignment','READY','grasp','lift_3s')},visual_all=pooled,visual_near_assigned_end=poolednear,commands=dict(wheel_repeat_fraction=weighted(commands,'wheel_repeat_fraction'),full_command_exact_repeat_fraction=weighted(commands,'full_command_exact_repeat_fraction'),near_assigned_wheel_repeat_fraction=weighted(commandsnear,'wheel_repeat_fraction'),inference_boundary_wheel_repeat_fraction=weighted(commands,'inference_boundary_wheel_repeat_fraction','inference_boundary_pair_N')),runs=rruns)
  rejection['arms'][arm]=dict(N=20,category_distribution=dict(categories),funnel=result['arms'][arm]['funnel'],runs=[dict(seed=r['seed'],reason_category=r['primary_category'],termination=r['termination'],blocked_object='UNDETERMINED: target-finger contact ledger lacks robot/body blockers; visible beam_1 recorded separately',min_gap_m=r['final_target_finger_min_gap_m'],min_gap_scope='evaluation-only final target-finger signed gap; not blocker clearance',raw=r['raw'],flags=r['flags']) for r in rruns])
 write(O/'beamdiag.json',result);write(O/'rejection-table.json',rejection)
 print(json.dumps(dict(thresholds=result['thresholds'],train={p:dict(N=v['visual']['N'],visible=v['visual']['assigned_visible_fraction'],blind=v['visual']['body_axis_no_end_fraction'],dwell=v['visual']['body_axis_no_end_longest_s'],repeat=v['commands']['wheel_repeat_fraction']) for p,v in trainstats.items()},arms={a:{k:v for k,v in r.items() if k not in ('runs',)} for a,r in result['arms'].items()}),indent=2))
if __name__=='__main__':summarize()
