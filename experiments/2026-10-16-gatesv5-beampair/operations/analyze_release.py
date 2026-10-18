"""GCP raw recount; no controller or physics steps. A/B remain separate."""
import collections,hashlib,json,pathlib,statistics,subprocess,sys
OPS=pathlib.Path('/home/ugrp/ugrp-sim/ops-reviews/gatesv5');ROOT=OPS.parents[1]
def read(p):
 if not p.exists():p=pathlib.Path(str(p)+'.zst')
 if not p.exists():return None
 raw=subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
 return json.loads(raw)
def write(p,d):p.write_text(json.dumps(d,indent=2,default=str)+'\n')
def analyze(config):
 cfg=read(pathlib.Path(config));sys.path.insert(0,str(ROOT/'src'/cfg['source_sha']))
 from harness.zone_final_environment import resolve
 from harness.zone_scenario_feasibility import landing_fits
 from scripts.run_grasp_act_release import SUCCESS
 out=OPS/('release-'+cfg['stage']+'-analysis-'+cfg['source_sha'][:8]);out.mkdir(exist_ok=True)
 rows=[];reject=collections.Counter();ledger=[];hashN=0;hasherrors=[];timings=[];sources=[]
 for x in cfg['runs']:
  raw=ROOT/'runs'/x['name']/'raw';d=read(raw/'result.json');exit=read(raw.parent/'EXIT.json')
  if not d:
   rows.append(dict(name=x['name'],seed=x['seed'],candidate=x['candidate'],started=raw.exists(),category='HOST_ERROR' if raw.exists() else 'not_started'));continue
  plan=read(raw/'plan.json');static,_,_=resolve(plan['map_id']);z=static['regions'][plan['destination_region']];rect=(*z['center_m'],*z['half_extents_m'])
  last=d.get('evaluation_last') or {};pose=last.get('beam_xy_yaw');fit=bool(pose and landing_fits('long_beam',pose,rect))
  final_conditions=dict(fit=fit,on_floor=bool(last and last['z']<SUCCESS['on_floor_z_m']),tilt=bool(last and last['tilt_deg']<SUCCESS['tilt_deg']),no_finger_contact=bool(last and all(max(v)<1e-6 for v in last['contact_n'].values())),open_issued_command=bool(last and all(v>=SUCCESS['open_pwm'] for v in last['open_pwm'].values())),grippers_clear=bool(last and min(last['grip_to_beam_m'])>=SUCCESS['clear_m']))
  final=all(final_conditions.values());settled=d.get('evaluation_settled_s',0)>=SUCCESS['settle_s']-1e-6
  audit={k:(d.get('input_audit') or {}).get(k) for k in ['invisible_measurements','held_world_reads','control_top_camera_reads']};audit_ok=all(v==0 for v in audit.values())
  success=d.get('status')=='complete' and d.get('release_outcome')=='teacher_done' and final and settled and audit_ok
  category='success' if success else 'HOST_ERROR' if d.get('status')=='HOST_ERROR' else 'supervisor_stop' if d.get('status')=='interrupted' else 'cap_end' if d.get('termination_category')=='cap_end' or d.get('release_outcome') in ['cap_end','release_timeout'] else 'failure'
  if category!='success':reject[category+':'+str(d.get('release_outcome') or d.get('error_type'))]+=1
  for item in d.get('rejection_ledger',[]):ledger.append(dict(run=x['name'],**item))
  resultp=raw/'result.json';resultp=resultp if resultp.exists() else pathlib.Path(str(resultp)+'.zst');sources.append(dict(path=str(resultp),sha256=hashlib.sha256(resultp.read_bytes()).hexdigest()))
  manifest=read(raw/'manifest.json') or {}
  for name,spec in manifest.items():
   p=raw/name
   if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=spec['sha256']:hasherrors.append(str(p));continue
   hashN+=1
   if spec.get('decoded_sha256'):
    data=subprocess.check_output(['zstd','-qdc',str(p)])
    if hashlib.sha256(data).hexdigest()!=spec['decoded_sha256']:hasherrors.append(str(p)+':decoded')
  first30=read(raw.parent/'FIRST30.json')
  if first30:timings.append(dict(run=x['name'],**first30))
  rows.append(dict(name=x['name'],seed=x['seed'],candidate=x['candidate'],raw=str(raw),source_sha=cfg['source_sha'],started=True,category=category,status=d.get('status'),outcome=d.get('release_outcome'),reported_success=d.get('release_success'),recount_success=success,false_accept=bool(d.get('release_success') and not success),prefix_held=d.get('prefix_held'),final_conditions=final_conditions,settled_s=d.get('evaluation_settled_s'),audit=audit,sim_s=d.get('sim_s'),wall_s=d.get('wall_s'),iteration=d.get('iterations'),failure_rgb_recording=d.get('failure_rgb_recording'),teacher_done=d.get('release_outcome')=='teacher_done',final_pass=final,settled_pass=settled,audit_ok=audit_ok))
 funnels={}
 for c in sorted({x['candidate'] for x in cfg['runs']}):
  subset=[r for r in rows if r['candidate']==c];survive=subset[:];f=[]
  for gate,pred in [('started',lambda r:r.get('started')),('prefix_held',lambda r:r.get('prefix_held')),('teacher_done',lambda r:r.get('teacher_done')),('final_geometry_contact_command_clear',lambda r:r.get('final_pass')),('settled_2s_original_evaluation',lambda r:r.get('settled_pass')),('input_audit_zero',lambda r:r.get('audit_ok'))]:
   entered=len(survive);survive=[r for r in survive if pred(r)];f.append(dict(gate=gate,entered=entered,cumulative_passed=len(survive),rejected=entered-len(survive)))
  funnels[c]=dict(N=len(subset),success=sum(r.get('recount_success',False) for r in subset),categories=dict(collections.Counter(r['category'] for r in subset)),funnel=f)
 reasons=collections.Counter(r.get('reason_category','missing_reason_category') for r in ledger)
 summary=dict(source_sha=cfg['source_sha'],host='gcp2',scene_profile='walls_floor_contrast_v5_indigo110_s80',camera_quality='no_mip_v1',stage=cfg['stage'],cohorts=funnels,runs=rows,false_accepts=sum(r.get('false_accept',False) for r in rows),manifest_files_verified=hashN,hash_errors=hasherrors,reason_distribution=dict(reasons),outcome_rejections=dict(reject),sources=sources,first30=timings,first30_wall_per_sim_median=statistics.median([x['wall_per_sim'] for x in timings]) if timings else None,settle_verification_scope='Final saved evaluation values and independently recomputed zone fit. Original short runner did not save every settle check; duration uses its original evaluation_settled_s. Gate launcher additionally records evaluator snapshots.',training_rgb=False,model_calls=0,pooling='A/B, short/gate, source, scene and host never pooled',reproduce='python3 '+str(pathlib.Path(__file__).resolve())+' '+str(config))
 write(out/'summary.json',summary);write(out/'rejection_table.json',dict(cohorts=funnels,reason_distribution=dict(reasons),outcome_rejections=dict(reject),rejection_ledger=ledger,raw_sources=sources,reproduce=summary['reproduce']))
 print(json.dumps(dict(out=str(out),cohorts=funnels,hashN=hashN,hash_errors=len(hasherrors),false_accepts=summary['false_accepts'])))
if __name__=='__main__':analyze(sys.argv[1])
