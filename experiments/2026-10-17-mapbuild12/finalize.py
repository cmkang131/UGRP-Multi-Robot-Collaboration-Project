"""Post-seal source-VM integrity/recount, then standard lossless compression."""
import argparse,json,math,os,platform,subprocess,sys,time
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--host',choices=['gcp5','gcp3'],required=True);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
if not platform.node().startswith('ugrp-act-l4-'+a.host):raise ValueError('SOURCE_VM_ONLY')
sys.path.insert(0,str(a.source))
from scripts.mapbuild10_mc import read,sha,dump
from harness.mapbuild_amcl import StaticField
from harness.mapbuild_own_grid import RESOLUTION,LIMIT,MIN_HITS
b=Path('/home/ugrp/ugrp-sim');ops=b/'ops-reviews/mapbuild12';out=ops/('gcp5-long' if a.host=='gcp5' else 'gcp3-release418')
lease=b/'leases/mapbuild12-finalize.json'
with lease.open('x') as f:json.dump(dict(task='mapbuild12-finalize',pid=os.getpid(),start_unix=time.time(),expected_end_unix=None),f)
try:
 seal=read(out/'prediction-seal.json')
 for x,h in {**seal['inputs'],**seal['outputs']}.items():
  if sha(Path(x))!=h:raise ValueError('SEAL_CHANGED:'+x)
 index=read(out/'index.json');sm=read(out/'summary.json');errs=read(out/'frame-errors.json');extra=[];maxdiff=0.;compared=0;baseline_diff=0.;baseline_presence=0
 for s in index:
  rows=read(out/(s['id']+'-predictions.json'));err=errs[s['id']];truth=read(Path(s['evaluation_source']))
  gt=truth['frames'] if s['world'] is None else [r for r in truth['rows'] if r['world']==s['world'] and r['rid']==s['rid']]
  poses=np.array([r['pose' if s['world'] is None else 'truth_pose'] for r in gt]);req=sm['requirements']
  # Independent vectorized evaluation-column recomputation, no estimator calls.
  for n in ('static','static_own'):
   pred=np.array([r['models'][n]['candidate'] if r['models'][n]['candidate'] is not None else [np.nan]*3 for r in rows]);valid=np.isfinite(pred).all(1)
   delta=pred[valid]-poses[valid];xy=np.linalg.norm(delta[:,:2],axis=1);yaw=abs(np.arctan2(np.sin(delta[:,2]),np.cos(delta[:,2])));coupled=yaw+np.arctan2(xy,req['nominal_target_range_m']-xy)
   for col,values in [('xy_m',xy),('yaw_deg',np.degrees(yaw)),('coupled_deg',np.degrees(coupled))]:
    saved=np.array([r['models'][n][col] for r,v in zip(err,valid) if v]);maxdiff=max(maxdiff,float(np.max(abs(values-saved))) if len(saved) else 0.);compared+=len(saved)
  previous=b/('ops-reviews/mapbuild11/long-recording2/score/predictions.json' if a.host=='gcp5' else 'runs/mapbuild10-rgb-field-legacy-v3/predictions/'+s['id']+'-coarse-000.json')
  old=read(previous);old=old if a.host=='gcp5' else old['rows']
  if len(old)!=len(rows):raise ValueError('HISTORICAL_JOIN_REQUIRED')
  for r,z in zip(rows,old):
   v=r['models']['static']['candidate'];u=z['models']['nav2_rgb_field_v1']['candidate'] if a.host=='gcp5' else z['candidate']
   baseline_presence+=int((v is None)!=(u is None))
   if v is not None and u is not None:baseline_diff=max(baseline_diff,float(np.max(abs(np.array(v)-u))))
  m=read(out/(s['id']+'-maps.json'));field=StaticField(s['static'],full_wall_extent=True);quality={}
  for n in ('static','static_own'):
   cells=np.asarray(m[n]['cells'],float).reshape(-1,5);stable=(cells[:,2]>=LIMIT)&(cells[:,3]>=MIN_HITS);pts=(cells[:,:2]+.5)*RESOLUTION
   d=field.distances(pts);v=d[stable]
   quality[n]=dict(stable_cells=int(stable.sum()),stable_wall_residual_p50_p95_max_m=np.percentile(v,[50,95,100]).tolist() if len(v) else None,
                  stable_static_overlap_ratio=float(np.mean(v<=RESOLUTION/math.sqrt(2))) if len(v) else None)
  visible=[r for r in rows if r['models']['static_own']['insertion']['hits']>0];first_used=next((r for r in rows if r['models']['static_own']['attempted'] and r['models']['static_own']['stable_reference_cells']),None)
  first_changed=next((r for r in rows if r['models']['static']['candidate']!=r['models']['static_own']['candidate']),None)
  extra.append(dict(id=s['id'],frames=len(rows),visible_insertions=len(visible),quality=quality,first_own_field_sim_s=first_used['t'] if first_used else None,first_different_pose_sim_s=first_changed['t'] if first_changed else None))
 result=dict(source_sha=subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip(),finalizer_sha256=sha(Path(__file__)),seal_inputs=len(seal['inputs']),seal_outputs=len(seal['outputs']),
   evaluator_columns_recomputed=compared,maximum_eval_column_difference=maxdiff,historical_static_baseline_max_pose_difference=baseline_diff,historical_static_presence_mismatches=baseline_presence,streams=extra,
   exact_truth_inputs_prediction=0,physics_steps=0,render_calls=0)
 dump(ops/(a.host+'-integrity.json'),result)
 # Compact summary remains useful without fetching any raw grids or traces.
 compact=dict(host=a.host,streams=len(sm['streams']),frames=sum(v['whole']['off']['frames'] for v in sm['streams']),models={})
 for n in ('off','static','static_own'):
  vs=[v['whole'][n] for v in sm['streams'] if v['whole'][n]]
  compact['models'][n]=dict(finite_frames=sum(v['frames'] for v in vs),requirement_frames=sum(v['requirement_frames'] for v in vs),converged_updates=sum(v['converged_updates'] for v in vs),wrong_converged_updates=sum(v['wrong_converged_updates'] for v in vs),
   median_end_xy_mm=float(np.median([v['end_xy_mm'] for v in vs])),maximum_xy_mm=max(v['max_xy_mm'] for v in vs))
 compact['own_field_updates']=sum(v['own_field_used_updates'] for v in sm['streams']);compact['diagnostics']=extra
 if a.host=='gcp5':
  events=read(b/'runs/mapbuild11-long-round1/unloaded-v2/events.json');stops=[e for e in events if e['event']=='would_stop' or e.get('would_stop',False)]
  compact['recorded_would_stop_count']=len(stops);compact['first_recorded_would_stop']=stops[0] if stops else None
 dump(ops/(a.host+'-compact-summary.json'),compact)
 # Mark only this finished analysis output; original recording unchanged.
 dump(out/'RUN_META.json',{'class':'dev','pr':556,'branch':'codex/mapbuild1','sha':result['source_sha'],'batch':'mapbuild12-'+a.host,'physics_steps':0})
 (out/'EXIT').write_text('0\n')
 subprocess.run(['python3',str(a.source/'scripts/compress_json_traces.py'),str(out),'--execute'],check=True,stdout=(ops/(a.host+'-compression.json')).open('x'))
 compressed=[]
 for line in (out/'COMPRESSED.jsonl').read_text().splitlines():
  e=json.loads(line);cp=out/e['compressed_path']
  if sha(out/e['path'])!=e['sha256'] or sha(cp)!=e['compressed_sha256']:raise ValueError('COMPRESSED_HASH_CHANGED')
  compressed.append(e)
 dump(ops/(a.host+'-compressed-integrity.json'),dict(files=len(compressed),records=compressed,all_hashes_verified=True))
 print(json.dumps(dict(host=a.host,seal_verified=True,baseline_maxdiff=baseline_diff,presence_mismatch=baseline_presence,eval_maxdiff=maxdiff,frames=compact['frames'],own_field_updates=compact['own_field_updates'])),flush=True)
finally:
 lease.unlink(missing_ok=True)
