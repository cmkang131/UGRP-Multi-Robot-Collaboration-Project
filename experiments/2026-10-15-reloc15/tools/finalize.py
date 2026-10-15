from pathlib import Path
import json,hashlib,statistics,subprocess,re
R=Path('/Users/changmin/projects/ugrp-wt/map-selfmap');E=R/'experiments/2026-10-15-reloc15';P=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/reloc15')
load=lambda n:json.loads((E/n).read_text());dump=lambda n,x:(E/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
runs=[dict(round=i,**q) for i in (1,2,3) for q in load(f'round{i}.json')['runs']];assert len(runs)==18
integrity=load('integrity.json');assert len(integrity)==18 and all(r['verified'] for r in integrity)
for r in runs:assert re.fullmatch('[0-9a-f]{40}',r['source_sha'])
audit=all(r['input_audit'].get('invisible_measurements')==0 and r['input_audit'].get('held_world_reads')==0 for r in runs)
first30=[]
for i in (1,2,3):
 for kind in ('selfmap','carry'):
  group=[r for r in runs if r['round']==i and kind in r['run']];values=[r['first30']['wall_per_sim'] for r in group if r.get('first30',{}).get('wall_per_sim') is not None]
  first30.append(dict(round=i,kind=kind,measured_N=len(values),N=len(group),median=statistics.median(values) if values else None,max=max(values) if values else None,scope='one sparse baseline intentionally stopped before30; no speed conclusion for it'))
commands=[]
for name in ('round1-submission.json','round2-submission.json','round2-carry-submission.json','round3-selfmap-submission.json','round3-carry-submission.json'):
 p=R/'outputs/reloc15'/name
 if p.exists():commands+=json.loads(p.read_text())
dump('gcp-commands.json',commands)
for d in commands:
 if d.get('submission_exit')==0:assert len(d['source_sha'])==40
upper=max(d['reservation']['conservative_upper_bound'] for d in commands)
termination=[]
for r in runs:
 t=r.get('termination') or dict(category=r.get('termination_category'),reason=r.get('termination_reason'))
 termination.append(dict(run=r['run'],source_sha=r['source_sha'],**t))
dump('termination.json',termination)
state=load('final-state.json');assert state['all_exit'] and not state['active_owned_controller_pids'] and not state['held_owned_reservations'] and not state['owned_leases']
media=load('media-verification.json');local_paths=[P/'overview-own.mp4',P/'r1-candidate/overview-own.mp4',P/'playback-3x.mp4'];receipts=[]
for spec,p in zip(media,local_paths):
 assert hashlib.sha256(p.read_bytes()).hexdigest()==spec['sha256'];receipts.append(dict(local_path=str(p),sha256=spec['sha256'],bytes=p.stat().st_size,verified=True))
for p in (P/'final-review').glob('*.json'):
 j=json.loads(p.read_text());im=p.with_suffix('.jpg');assert hashlib.sha256(im.read_bytes()).hexdigest()==j['montage_sha256']
dump('local-media-verification.json',dict(videos=receipts,all_18_montage_download_hashes_verified=True,directly_reviewed_final_montages=6,full_original_replay_review=dict(hz=2,sim_start=1.3,sim_end=125.7,tail_hz=10,tail_start=115.7),same_condition_carry_success_video_available=False))
code_sha=subprocess.check_output(['git','rev-parse','accff491'],cwd=R,text=True).strip()
summary=dict(schema='ugrp.reloc15.summary.v1',status='NOT_READY',ready=False,round_count=3,round_sizes=[6,6,6],physical_run_N=18,source_shas=sorted({r['source_sha'] for r in runs}),post_round3_code_sha=code_sha,post_round3_selfmap_recording_fix_physics_N=0,
 baseline_original_carry_run_N=13,baseline_carry_with_logs_N=11,baseline_missing_logs_HOST_ERROR_N=2,
 findings=dict(physical='exact replay: held red30g box not dragging; contact with other floor beam, plausible torque scale; simulator defect not established',physics_parameters_changed=False,
  sparse_rgb_yaw='stationary image-border inliers dominate homography; true floor outliers',dense_rgb_yaw='masked ECC detects saved pairs but false admitted rotations remain; uncertainty undercovers',
  selfmap_93584_matched=dict(baseline_bad=152,baseline_N=214,update_candidate_bad=73,update_candidate_N=216,baseline_drive_bad=43,candidate_drive_bad=6,drive_N=45,scope='same recording-condition comparison only; not qualified post-recording-fix source'),
  final_false_acceptance=dict(seed=93266,t=59.5,actual_yaw_deg=.22099640533918188,observed_yaw_deg=12.473796121192155,predicted_3sigma_deg=4.8366458104426115)),
  destination_release_verified_N=sum(r.get('funnel',{}).get('release',0) for r in runs if 'carry' in r['run']),input_audit_zero=audit,original_manifests_verified_N=18,first30=first30,
  max_admission_conservative_upper=upper,max_own_candidate_parallel=6,planned16_same_cohort_replay_verified=False,host_guard_s=86400,budget_stop_state='ACTIVE',
  validation=dict(mac_nonphysics_pytest_passed=31,gcp_saved_image_regression_direct_passed=1,gcp_pytest_available=False,github_ci='pending after push',scope='32 distinct offline checks; one GCP test function executed directly; no Mac physics/render/model'),
  own_processes_remaining=0,own_leases_remaining=0,own_reservations_remaining=0,model_calls=0,training_runs=0,weld='off',google_drive_used=False,
  media_root=str(P),rejection_table=str(E/'rejection-table.json'),followup_queues_submitted=False,
  blockers=['selfmap pose errors remain across seeds','false accepted carry yaw despite nominal precision bound','no destination release verified','post-round3 control-frame-preserving recording fix lacks physics','same-condition carry success video absent'],
  original_storage='GCP persistent disk; no separate full backup',diagnostic_replays=dict(exact_completed=4,failed_attempts=2,failures=['EGL import before physics, retried OSMesa','scene XML byte mismatch after setup, rerun from exact original source']),runs=[dict(run=r['run'],round=r['round'],source_sha=r['source_sha'],raw=r.get('raw'),summary=f"round{r['round']}.json") for r in runs])
assert not summary['destination_release_verified_N'];dump('summary.json',summary)
funnel=[];lines=['# reloc15 관문표 — NOT_READY','','기본off·원본GCP평가전용. 같은시드짝비교외소스/조건/시간구간을합산하지않는다. 프레임분모는독립성공률아님. 3라운드18회 종료, 후속큐미제출.','','|실행|등록→전달→삽입→주행|제어오류|주행오류|종료|','|---|---|---|---|---|']
for r in runs:
 if 'selfmap' in r['run']:
  f=r['funnel'];gates=['registered','execution_pose_delivered','map_inserted','control_drive_used'];n=f['frames'];st=[]
  for k in gates:
   v=f[k];st.append(dict(gate=k,received=n,cumulative_passed=v,rejected=n-v));n=v
  e=r['registered_errors'];d=r['drive_errors'];lines.append(f"|{r['run']}|"+'→'.join(str(f[k]) for k in gates)+f"|{e['bad_N']}/{e['N']}|{d['bad_N']}/{d['N']}|{r['termination']['category']}|")
 else:
  f=r['funnel'];gates=['pickup_seen','aligned','lifted_controller','zone_place_view','release'];n=1;st=[]
  for k in gates:
   v=int(bool(f[k]));st.append(dict(gate=k,received=n,cumulative_passed=min(n,v),rejected=n-min(n,v)));n=min(n,v)
 funnel.append(dict(run=r['run'],round=r['round'],source_sha=r['source_sha'],raw=r.get('raw'),unit='frames' if 'selfmap' in r['run'] else 'episode',gates=st,first_rejections=r.get('known_mode_measurement_funnel',{}).get('first_rejections',[]),registration_funnel=r.get('registration_frame_funnel'),heading_observation_counts=r.get('heading_observation_counts'),termination=r.get('termination') or dict(category=r.get('termination_category'),reason=r.get('termination_reason'))))
lines+=['','|운반실행|본pickup→align→lift→구역뷰→release|held yaw p95/max °|20°초과|종료|','|---|---|---|---|---|']
for r in runs:
 if 'carry' not in r['run']:continue
 f=r['funnel'];e=r['held_cargo_yaw'];v=e['p50_p95_max_deg'];label=f'{v[1]:.2f}/{v[2]:.2f}' if v else 'N/A (held sample0)';lines.append(f"|{r['run']}|"+'→'.join(str(f[k]) for k in ['pickup_seen','aligned','lifted_controller','zone_place_view','release'])+f"|{label}|{e['over20_N']}/{e['N']}|{r.get('termination_category')}|")
lines+=['','R1–R3自己지도buffer의control frame_id소비결함을최종코드에서고쳤지만새물리0. 운반held평가는finger contact+바닥보다높음으로통일(5cm임의경계사용안함). 0명령yaw비는undefined, 원본미가용은성공0으로대체하지않는다.','', '재현: GCP의해당source checkout에서 PYTHONPATH=. .venv-sim/bin/python /tmp/analyze-reloc15-round.py <1|2|3>. 저장helper=tools/analyze_round.py. 전체raw/SHA256SUMS는GCP에보존.']
(E/'rejection-table.md').write_text('\n'.join(lines)+'\n')
dump('rejection-table.json',dict(schema='ugrp.reloc15.rejection_table.v2',ready=False,analysis_host='gcp1',portable_aggregation_host='Mac summaries only',runs=funnel,integrity='integrity.json',commands='gcp-commands.json',raw_root='gcp1:/home/ugrp/ugrp-sim/runs',reproduce='tools/analyze_round.py round_number on GCP in the run source checkout; evaluation-only truth',scope='Frame/episode gates are cumulative; prediction is not a new measurement; source cohorts not pooled'))
dump('queue-readiness.json',dict(status='BLOCKED',ready=False,submitted=False,runs_enabled=False,rejection_table=str(E/'rejection-table.json'),selfmap=dict(source_sha=subprocess.check_output(['git','rev-parse','e44b4987'],cwd=R,text=True).strip(),ready=False),carry=dict(source_sha=subprocess.check_output(['git','rev-parse','1d7d5b26'],cwd=R,text=True).strip(),ready=False),planned_max_parallel=16,global_limit=40,reason=summary['blockers']))
print(json.dumps(dict(runs=len(runs),integrity=18,audit_zero=audit,max_admission_upper=upper,ready=False)))
