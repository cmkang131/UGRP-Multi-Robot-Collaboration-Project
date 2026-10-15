"""gcp1 derived evidence only. No physics or control; fetch summaries/montages."""
from pathlib import Path
from collections import Counter
import argparse,bisect,hashlib,json,math,subprocess,sys,shlex
from PIL import Image,ImageDraw
R=Path('/home/ugrp/ugrp-sim/runs')

def read(path):
 if not path.exists():path=path.with_suffix(path.suffix+'.zst')
 return subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()

def main(names,out):
 out.mkdir(parents=True,exist_ok=True);results=[];reject=Counter();frameN=0;lineN=doneN=eventN=rejectN=0;choice_counts=Counter();sweepN=sweepPass=alternativeN=alternativePass=0
 for name in names:
  root=R/name;raw=root/'raw';d=json.loads(read(raw/'result.json'))
  completed=(root/'EXIT').exists();manifest_ok=False;source_sha=(root/'SOURCE_SHA').read_text().strip()
  if completed:
   subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=root,check=True)
   manifest_ok=True
  original_paths=[p for p in root.rglob('*') if p.is_file()];hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in original_paths}
  assert d['source_sha']==source_sha
  audit={k:d.get('input_audit',{}).get(k) for k in ('invisible_measurements','held_world_reads','control_top_camera_reads','evaluation_top_camera_reads')}
  exit_code=(root/'EXIT').read_text().strip() if completed else None
  classification='running' if not completed else 'success' if d.get('release_success') and exit_code=='0' else 'supervisor_stop' if (root/'SUPERVISOR_STOP.json').exists() else 'HOST_ERROR' if d['status']=='HOST_ERROR' or exit_code not in ('0','130') else 'cap_end' if d.get('release_outcome') in ('cap_end','release_timeout') else 'failure'
  seg=raw/'training-segments.json'
  segments=json.loads(read(seg)) if seg.exists() else {'prefix':{'start_world_t':0.}}
  origin=segments['prefix']['start_world_t']
  tr=[json.loads(l) for l in read(raw/'teacher-r1.jsonl').splitlines()];tr=[v for v in tr if 't' in v]
  release=next((v['t'] for v in tr if v.get('skill')=='release'),origin)
  fs=sorted((raw/'eval-own/r1').glob('*.jpg'),key=lambda f:f.stat().st_mtime)
  def sec(f):return int(f.name.split('-')[0])/10+(0 if '-prefix.' in f.name else release-origin)
  times=[sec(f) for f in fs]
  first=next((i for i,t in enumerate(times) if t-times[0]>=30-1e-8),len(fs)-1)
  first30=dict(sim_s=times[first]-times[0],wall_per_sim=(fs[first].stat().st_mtime-fs[0].stat().st_mtime)/(times[first]-times[0])) if first else None
  # >=6 uniform samples, and no temporal gap beyond60 SIM s.
  indices=sorted(set(round(i*(len(fs)-1)/max(5,math.ceil((times[-1]-times[0])/60))) for i in range(max(5,math.ceil((times[-1]-times[0])/60))+1)))
  selected=[raw/'eval-own'/rid/fs[i].name for i in indices for rid in ('r1','r2')]
  canvas=Image.new('RGB',(660,270*len(indices)),'white');draw=ImageDraw.Draw(canvas)
  review=[]
  for k,p in enumerate(selected):
   im=Image.open(p);im.load();canvas.paste(im,((k%2)*330,(k//2)*270+25))
   elapsed=sec(p);draw.text(((k%2)*330+3,(k//2)*270+5),f'{p.parent.name} SIM {elapsed:.1f}',fill='black')
   review.append(dict(path=str(p),sha256=hashes[str(p.relative_to(root))],elapsed_sim_s=elapsed))
  montage=out/(name+'-montage.jpg');canvas.save(montage,quality=90)
  all_frames=[p for p in raw.rglob('*.jpg')];frameN+=len(all_frames)
  for p in all_frames:
   with Image.open(p) as im:im.verify()
  checks=d.get('line_rechecks',[]);events=[e for c in checks for e in c['events']]
  lineN+=len(checks);doneN+=sum(c['state']=='done' for c in checks);eventN+=len(events)
  for c in d.get('code_decisions',[]):
   if c.get('reason'):choice_counts[c['reason']]+=1
  for s in d.get('release23_sweep_checks',[]):
   for c in s['checks']:sweepN+=1;sweepPass+=int(c['accepted'])
  for e in events:
   if e['event']=='release23_budget_alternative':alternativeN+=1;alternativePass+=int(e['accepted'])
  ledger=d.get('rejection_ledger',[])
  if classification in ('HOST_ERROR','supervisor_stop') and not ledger:
   stop=json.loads((root/'SUPERVISOR_STOP.json').read_text()) if (root/'SUPERVISOR_STOP.json').exists() else {}
   ledger=[dict(reason_category='result_serialization' if classification=='HOST_ERROR' else 'supervisor_stop_same_defect',blocking_object=stop.get('reason','release23 sweep NumPy bool result serialization'),minimum_gap=None,gap_unit='nongeometric',gap_unknown_reason='artifact failure or supervisory stop; no geometric clearance is inferred')]
  for e in ledger:
   assert e.get('reason_category') and e.get('blocking_object') and 'minimum_gap' in e
   reject[e['reason_category']]+=1;rejectN+=1
  plan=json.loads(read(raw/'plan.json'))
  accepts=[c for c in d.get('code_decisions',[]) if c.get('action')=='lower' and str(c.get('reason','')).startswith('localized_margins_')]
  accepted_evaluation=[]
  if accepts:
   sys.path.insert(0,str(Path('/home/ugrp/ugrp-sim/src')/source_sha))
   from harness.zone_final_environment import resolve
   from harness.zone_scenario_feasibility import landing_fits
   static,_,_=resolve(plan['map_id']);z=static['regions'][plan['destination_region']];rect=(*z['center_m'],*z['half_extents_m'])
   ev=[json.loads(l) for l in read(raw/'eval-only.jsonl').splitlines()]
   for c in accepts:
    label=min(ev,key=lambda v:abs(v['t']-c['t']))
    accepted_evaluation.append(dict(decision_t=c['t'],eval_t=label['t'],sample_delta_s=label['t']-c['t'],
       fit=bool(landing_fits('long_beam',label['beam']['pose'],rect)),scope='evaluation-only label; never fed back'))
  results.append(dict(name=name,seed=plan['seed'],source_sha=source_sha,classification=classification,status=d['status'],
   success=classification=='success',physical_evaluation_success=d.get('release_success'),outcome=d.get('release_outcome'),sim_s=d.get('sim_s'),release_sim_s=d.get('release_sim_s'),
   wall_s=d.get('wall_s'),first30=first30,input_audit=audit,evaluation_position_error=d.get('evaluation_position_error'),
   evaluation_settled_s=d.get('evaluation_settled_s'),iterations=d.get('iterations'),shift_steps=d.get('shift_steps'),
   execution_profile={k:d.get(k) for k in ('release_profile','release_goal_region','command_motion','effective_motion_profile','release20_settle','release21','margin_common_mode','release_leg_budget','lateral_rate_cal','release_yaw_budget','release_plan_budget','recording_mode','weld')},
   code_decisions=d.get('code_decisions'),leg_admissions=d.get('release23_leg_admissions'),
   final_acceptance_evaluation=accepted_evaluation,false_final_accepts=sum(not v['fit'] for v in accepted_evaluation),
   sweep_checks=[{k:v for k,v in x.items() if k!='checks'} for x in d.get('release23_sweep_checks',[])],
   rejection_ledger=ledger,line_summary=dict(N=len(checks),done=sum(c['state']=='done' for c in checks),
     events=dict(Counter(e['event'] for e in events)),failures=[c['failure'] for c in checks if c['failure']],
     budget_alternatives=[e for e in events if e['event'].startswith('release23')]),
   remote_raw=str(root),raw_result_sha256=hashes[next(k for k in hashes if k in ('raw/result.json','raw/result.json.zst'))],
   raw_manifest_sha256=hashes.get('SHA256SUMS'),full_original_manifest_verified=manifest_ok,original_file_N=len(original_paths),
   own_frame_N=len(all_frames),frame_decode_verified_N=len(all_frames),frame_review=review,
   montage=dict(path=str(montage),sha256=hashlib.sha256(montage.read_bytes()).hexdigest())))
 n=len(results);complete=sum(v['classification']!='running' for v in results);aud=sum(all(x==0 for x in v['input_audit'].values()) for v in results);success=sum(v['success'] is True for v in results)
 funnel=[dict(gate='queued_candidate',input=n,cumulative_passed=n,rejected=0),dict(gate='terminal_original_and_hash',input=n,cumulative_passed=complete,rejected=n-complete),dict(gate='input_audit_zero',input=complete,cumulative_passed=aud,rejected=complete-aud),dict(gate='physical_release',input=aud,cumulative_passed=success,rejected=aud-success)]
 table=dict(schema='ugrp.release23.rejections.v1',episode_funnel=funnel,
  frame_funnel=[dict(gate='generated_original_own_RGB',input=frameN,cumulative_passed=frameN,rejected=0),dict(gate='original_hash_and_JPEG_decode',input=frameN,cumulative_passed=frameN,rejected=0)],
  event_funnel=[dict(gate='line_candidates',input=lineN,cumulative_passed=lineN,rejected=0),dict(gate='line_alignment_completed',input=lineN,cumulative_passed=doneN,rejected=lineN-doneN)],
  event_counts=dict(total=eventN,rejection_records=rejectN),rejection_reason_table=[dict(category=k,count=v) for k,v in reject.most_common()],
  raw_paths=[v['remote_raw'] for v in results],reproduction=shlex.join([sys.executable,str(Path(__file__)),'--names',json.dumps(names),'--out',str(out)]))
 proposed=sum(choice_counts.values());current=proposed;decision_funnel=[]
 for gate,failures in [('paired_release_candidate',()),('same_round_localized_geometry',('global_pose_unobserved','margin_epoch_mismatch','margin_geometry_unobserved')),('axis_alignment',('release_axis_unaligned',)),('lateral_clearance',('localized_lateral_correction','lateral_clearance_unresolved','lateral_bounds_disagree','lateral_bounds_unobserved')),('margin_sum_consistency',('margin_common_mode_domain','margin_disagreement','margin_goal_interval_empty')),('inside_both_margin_lower_bounds',('localized_margin_correction',))]:
  rejected=sum(choice_counts[k] for k in failures);decision_funnel.append(dict(gate=gate,input=current,cumulative_passed=current-rejected,rejected=rejected));current-=rejected
 table.update(candidate_funnel=decision_funnel,decision_reason_counts=dict(choice_counts),
  sweep_funnel=[dict(gate='whole_sweep_static_constraints',input=sweepN,cumulative_passed=sweepN,rejected=0),dict(gate='positive_static_clearance',input=sweepN,cumulative_passed=sweepPass,rejected=sweepN-sweepPass)],
  alternative_funnel=[dict(gate='budget_alternatives_proposed',input=alternativeN,cumulative_passed=alternativeN,rejected=0),dict(gate='safe_and_improving_or_fresh_reobserve',input=alternativeN,cumulative_passed=alternativePass,rejected=alternativeN-alternativePass)],
  interpretation='Lateral/axial correction rejections are progress alternatives, not failed episodes; frame/line/constraint funnels have different units and are never summed.')
 (out/'rejection_table.json').write_text(json.dumps(table,indent=2)+'\n')
 summary=dict(schema='ugrp.release23.dev.v1',source_sha=results[0]['source_sha'],counts=dict(completed=complete,success=success,N=n),
  classification_counts=dict(Counter(v['classification'] for v in results)),
  verified=all(v['full_original_manifest_verified'] and v['classification'] in ('success','failure','cap_end','supervisor_stop') and all(x==0 for x in v['input_audit'].values()) for v in results),
  failure_seeds_solved=all(sum(v['seed']==seed and v['success'] is True for v in results)==2 for seed in (110622,88639)),
  rejection_table=str(out/'rejection_table.json'),research_result=False,training_rgb=False,student_execution=False,
  pooling='No pooling across old SHA, rounds, A/B, DEV or gate.',runs=results)
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--names',type=json.loads);p.add_argument('--out',type=Path)
 a=p.parse_args();main(a.names,a.out)
