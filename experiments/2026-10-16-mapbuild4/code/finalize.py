import hashlib,json,sys
from pathlib import Path
from collections import Counter
base=Path('/home/ugrp/ugrp-sim');runs=base/'runs/mapbuild4';out=runs/'analysis-final';out.mkdir(exist_ok=True)
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
allrows=[];summaries=[];integrity=[];commands=[]
for prefix,round_,history in [('pulse',1,False),('phase',2,True),('native-pulse',3,False),('native-phase',3,True)]:
 for backend in ['warp','cpu']:
  root=runs/f'{prefix}-{backend}-r{round_}';summary=json.load(open(root/'summary.json'));meta=json.load(open(root/'queue.json'));metrics=json.load(open(root/'metrics.json'))
  assert summary['status']=='cap_end' and len(metrics)==summary['worlds']
  summaries.append(dict(run=root.name,raw=str(root),source_sha=meta['source_sha'],**summary))
  for r in metrics:
   row={k:r[k] for k in ['name','pose','axis','u','ms','delta','during_delta','wheel_phase','wheel_rotation','subtree_com','mass']}
   row.update(backend=backend,history=history,profile='warp_native_contact_v1' if 'native' in prefix else 'baseline_noslip10',raw=str(root))
   allrows.append(row)
  manifest=json.load(open(root/'SHA256SUMS.json'));bad=[p for p,h in manifest.items() if hashlib.sha256((root/p).read_bytes()).hexdigest()!=h]
  integrity.append(dict(raw=str(root),checked=len(manifest),mismatches=bad,manifest_sha256=hashlib.sha256((root/'SHA256SUMS.json').read_bytes()).hexdigest()))
  assert not bad
for profile in ['baseline_noslip10','warp_native_contact_v1']:
 write(out/(profile+'-matrix.json'),[r for r in allrows if r['profile']==profile])
write(out/'summary.json',dict(status='STOPPED_AFTER_THIRD_ROUND_NOT_READY',reason='history-dependent 60ms lateral recoil remains under both profiles; user three-round stop rule',runs=summaries,total_run_n=len(summaries),map_extension=dict(status='NOT_RUN',reason='lateral60ms defect remains; third-round stop rule',blocked_object='wheel_floor_response',minimum_gap_m=None,gap_status='not_measured'),gate4=dict(status='WITHHELD',reason='warp10 NOT_READY'),cpu_scope='same model C3.16 on gcp5 comparison only; no pooling with MJWarp or prior runs',input_audit=dict(top_actor_reads=0,truth_feedback=0,model_calls=0),frontier_candidate='prepared default off; physical runs0; no admitted correction'))
write(out/'integrity.json',integrity)
write(out/'rejection_table.json',dict(status='NOT_READY',raw=str(runs),reproduction='reproduce.json',unit='diagnostic world per backend/profile/history/primitive',stages=[dict(stage=s,cumulative_pass_n=112,rejected_n=0) for s in ['requested','nonpenetrating_start','completed_cap_end','finite_measurement']],reasons=[dict(category='history_dependent_response',reason='60ms lateral moves transiently then recoils; same pulse response depends on preceding forward command',n=16,scope='history60ms x2postures x2directions x2backends x2profiles',blocked_object='wheel_floor_roller_contacts',minimum_gap_m=None,gap_status='external_gap_not_measured_no_r1_nonfloor_contacts_at_onset'),dict(category='prediction_support',reason='v122 exact primitive key missing',n=64,scope='all112 diagnostic worlds',blocked_object='historical_v122_profile',minimum_gap_m=None,gap_status='not_applicable'),dict(category='prediction_support',reason='loaded fine profiles are unqualified transfer',n=16,scope='overlaps exact keys; not additive to 64 missing',blocked_object='HIGH_camera_and_response',minimum_gap_m=None,gap_status='not_applicable')],v122_profile_distribution=dict(missing_exact_key=64,historical_CPU_fit=32,unqualified_loaded_fine_transfer=16),gate3=dict(status='NOT_RUN',coverage=None,reason='third-round stop before frontier physics',blocked_object='lateral60ms_response',minimum_gap_m=None,gap_status='not_measured'),gate4=dict(status='WITHHELD',reason='warp10 NOT_READY',blocked_object='warp10_CPU_contact_export',minimum_gap_m=None,gap_status='not_measured')))
# Preserve launch scripts as actual commands; they are the exact finite round orchestration.
for name in ['native-launch.json','phase-launch.json']:
 commands+=json.load(open(base/'ops-reviews/mapbuild4'/name))['commands']
write(out/'reproduce.json',dict(source_snapshots=[dict(raw=s['raw'],source_sha=s['source_sha']) for s in summaries],r1_launcher=str(base/'ops-reviews/mapbuild4-run.sh'),r1_note='supervisor was stopped after its own Warp child launch; CPU command launched independently with same arguments to avoid idle waiting',r2_r3_commands=commands,analysis_commands=[str(base/'ops-reviews/mapbuild4-phase-analysis.py'),str(base/'ops-reviews/mapbuild4-playback.py'),str(base/'ops-reviews/mapbuild4-playback2.py')],env=dict(MUJOCO_GL='osmesa',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')))
write(out/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'})
print(json.dumps(dict(runs=len(summaries),worlds=len(allrows),files_checked=sum(r['checked'] for r in integrity),mismatches=sum(len(r['mismatches']) for r in integrity))))
