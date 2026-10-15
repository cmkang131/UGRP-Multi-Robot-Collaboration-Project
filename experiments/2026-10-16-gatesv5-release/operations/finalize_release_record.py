"""Package retrieved evidence, without simulation, rendering, or GUI on Mac."""
from pathlib import Path
import json,shutil,hashlib,subprocess
root=Path('/Users/changmin/projects/ugrp');ops=root/'outputs/e2e18-admin/gatesv5'
record=Path('/Users/changmin/projects/ugrp-wt/gatesv5-release/experiments/2026-10-16-gatesv5-release')
def write(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
for name in [
 'release-gate-summary.json','release-gate-rejection_table.json','release-gate-population-funnels.json',
 'release-gate-candidate-funnels.json','release-gate-first30-initial.json','release-gate-first30-resumed.json',
 'release-gate-DONE.json','release-gate-final-analysis-DONE.json','release-final-stop.json',
 'release-final-attempt-ledger.json','release-failure-analysis.json','host-finalization-preservation-v2.json',
 'release-short-population-funnels.json','retrieval-verification-release.json','cleanup.json',
 'release-gate-config.json','release-gate-attempt1-config.json','release-gate-resume-config.json',
]:shutil.copy2(ops/name,record/name)
(record/'operations').mkdir(exist_ok=True)
for name in ['run_queue.py','analyze_release.py','prepare_release_funnel.py','prepare_release_playback.py','release_candidate_funnel.py','release_failure_analysis.py','release_final_attempts.py','release_native_event_tail.py','finish_release.py','collect_release.py','finalize_release_record.py']:
 shutil.copy2(ops/name,record/'operations'/name)
shutil.copy2(Path('/Users/changmin/projects/ugrp-wt/gatesv5-beampair/experiments/2026-10-16-gatesv5-beampair/operations/review_beampair_gatesv5_fisheye.py'),record/'operations/review_beampair_gatesv5_fisheye.py')
reviews=[]
for label in ['success','failure','host-stop','failure-event-native-tail']:
 source=root/'outputs/e2e18-admin/playback'/('gatesv5-release-'+label);dest=record/'playback'/label;dest.mkdir(parents=True,exist_ok=True)
 names=['playback-3x.mp4','review.json']
 names += [p.name for p in source.glob('*provenance.json')]
 if label in ('success','failure'):names += [p.name for p in source.glob('full-*.jpg')]
 if label=='failure-event-native-tail':names += [p.name for p in source.glob('tail-*.jpg')]
 for name in names:shutil.copy2(source/name,dest/name)
 d=json.loads((source/'review.json').read_text());viewed=[]
 patterns=['full-*.jpg','tail-*.jpg'] if label=='failure' else ['tail-*.jpg'] if label=='failure-event-native-tail' else ['full-*.jpg']
 for pattern in patterns:
  for p in sorted(source.glob(pattern)):viewed.append(dict(local=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 reviews.append(dict(label=label,direct_visual_review_completed=True,viewed_files=viewed,video_bytes=d['video_bytes'],video_sha256=d['video_sha256'],duration_sim_s=d['duration_sim_s'],ffprobe=d['ffprobe'],original_native_frames=d['original_own_rgb_frames_used'],max_body_replay_error_m=d['max_body_xyz_error_m'],raw_review_file=str(source/'review.json')))
visual=dict(direct_file_review=True,mac_gui_opened=False,mac_rendering=False,gcp2_renderer='saved evaluator qpos + original own RGB native ring; no physics steps/controller rerun',reviews=reviews,timeline=dict(
 failure='A110633: clip0-8 prefix;9-13 lower/open;14-24.5 backoff and two actual scans;25-31 line recheck;32-35 approach/repick;36-53.6 held wrist view and regrasp waiting;53.7 sweep rejection before shift;53.8-56.1 evaluator tail. No completed final placement.',
 native_failure_event_tail='Original world45.5-55.5, both own cameras202 native JPEGs. Entire10SIMs at10Hz directly viewed. Shaft occupies central wrist view with small image drift; no fast yaw/body oscillation visible. This excludes subsequent2.4SIMs evaluator settling included in full replay.',
 success='B110600 clip0-8 prefix;9-14 lower/open;15 backoff;16-17 and21-23 actual pan scans;25-32.2 observe/backoff/done, cargo remains in zone. Already-inside case, not a full mission claim.',
 host_stop='Superseded B110614 attempt2: full0-48.8 at2Hz viewed, setup/lower/open/two scans/line recheck/repick then held regrasp check at operator stop. Not a teacher failure or qualified gate result; its10Hz tail sheets were retrieved but not directly inspected.'),dense_vs_sparse='The10Hz native failure-event band shows a sustained held view, not hidden rapid oscillations. The overview confirms no shift after the guard rejection; a sparse shot of closed grippers cannot establish release success.',scope='review.json retains its original machine-only direct_visual_review_completed=false; this separate signed-by-run record documents actual file inspection. Reconstructed views preserve original calibrated fisheye, geom masks and no_mip; native originals remain distinct from reconstructed views.')
write(record/'visual-review.json',visual)
s=json.loads((ops/'release-gate-summary.json').read_text())
summary=dict(status='NOT_READY',source_sha=s['source_sha'],host='gcp2',machine_type='n4-highcpu-64',physics='C MuJoCo3.12.0 CPU',scene='walls_floor_contrast_v5_indigo110_s80',floor='v1 unchanged',camera_quality='no_mip_v1',scene_asset_extension='release_geometry_v1',scene_colour_transition_v1='off',boundary_scope='Only the new toggle is off; existing own RGB line extraction remains active',planned_N=80,started_N=78,completed_control_terminal_N=63,success_n=62,failure_N=1,cap_end_N=0,supervisor_stop_N=15,HOST_ERROR_N=0,not_submitted_N=2,cohorts=s['cohorts'],short='A3/3 B3/3 separate',input_audit=dict(runs_N=78,invisible_measurements=0,held_world_reads=0,control_top_camera_reads=0),scene_runtime_verified_N=78,manifest_files_verified=22899,hash_errors=0,false_accepts=0,first30=dict(initial_wave=dict(n=16,median=4.181827091308201),resumed_wave=dict(n=16,median=4.058100856475143),block_threshold=6.0),raw_recount='release-gate-summary.json',rejection_table='release-gate-rejection_table.json',operating_attempts='release-final-attempt-ledger.json',weld='off',training_rgb=False,student_execution=False,model_calls=0,pooling=False,raw_backup='gcp2 persistent disk; no independent full raw backup; Mac retrieved summaries/montages/review frames/bounded videos only',remaining='Seed110633 static sweep guard rejection requires source diagnosis/new candidate and fresh gate.15 supervised stops +2 unsubmitted do not count as control failures or successes.',runs=[{k:v for k,v in r.items() if k in ['name','seed','candidate','raw','source_sha','started','category','status','outcome','recount_success','audit']} for r in s['runs']])
write(record/'summary.json',summary);write(record/'status.json',{k:v for k,v in summary.items() if k!='runs'})
(record/'README.md').write_text('''# gatesv5 release: NOT_READY

확정 장면의 release24 교사 관문이다. 실행 소스 `a41781dd122b1e20b8eec7e43c553e779e6cfc30`, PR #491. gcp2 `n4-highcpu-64`, C MuJoCo3.12.0 CPU, `walls_floor_contrast_v5_indigo110_s80` + 원본 v1 바닥 + `no_mip_v1`. 옛 release 맵의 벽 모양 하나에 같은 PR527 재질 생성법으로 `release_geometry_v1` 자산만 추가했다. 물리·맵·기존 release23/24 제어와 수용 기준은 유지했다. 새 `scene_colour_transition_v1` 토글은 OFF이며 기존 자기 RGB 선 검출은 계속 사용한다. weld OFF, 학습/모델 호출0, ACT 학생 검증 아님.

| 계획 | 성공 | 제어 실패 | cap_end | 감독 중단 | 미제출 |
|---|---:|---:|---:|---:|---:|
| A40 / release18 |31|1|0|7|1|
| B40 / release19 |31|0|0|8|1|

짧은 A3/3·B3/3 통과 후 고정 대기열을 승인해16동시 실행했다. 원본 재집계는 최종78회 중 성공62·제어 실패1·감독 중단15이며2회 미제출이다. 성공/실패로 끝난63회와 감독 중단을 구분한다. 새 소스의 HOST_ERROR0은 최종 계획별 선택 결과에만 해당하며, 운영 오류는 아래에 전부 따로 기록했다. 이전 장면·gcp1·짧은 실행·A/B를 합산한 성공률은 제시하지 않는다.

실패 A110633은 `static_sweep / wall_north / minimum_gap=-0.0992883263m`로 이동 전에 거부됐다. B110633도 -0.0953608971m를 기록했으나 SIGINT로 `interrupted`이므로 감독 중단으로 분류했다. A는 불확실성 halo를 포함한 시작 로봇 범위만으로도 -0.0992883231m이다(halo 제외 같은 추정 기하 틈 +0.0007184585m). 이는 예상 안전 범위의 겹침이며 물리 충돌을 측정한 값이 아니다. RGB 위치 추정은 두 로봇 모두 수용됐고 마지막 둘러보기 평가 오차는44.9mm/13.4mm였으나, 위치 추정·halo·이동 계획 사이 정확한 원인과 불필요한 거부인지는 미분리다. 색 검출/정렬의 장면 회귀라고 확정할 근거는 없다. 원장 뒤 제어를 임의로 완화하지 않고 `SUPERVISOR_STOP.json`과 단일 SIGINT로 중단했다.

`release-gate-rejection_table`은 사례별 funnel과 사유/물체/최소 틈을, `release-gate-population-funnels`는6519개 native 입력 파일·2229개 선 이미지 후보·1536개 위치 추정 뷰·158개 들기 시도를 서로 다른 모집단으로 기록한다. `release-gate-candidate-funnels`는512개 위치 추정 fit의 생성→지도 지지→수치 중복 제거 후보 수와 최선 fit의 선→뷰→normal rank→점수 차이 관문을 기록한다. 원본이 남기지 않은 중간 최적화 생존 수는 미기록으로 명시했고 추정하지 않았다. 재현 명령과 원본 SHA는 각 JSON에 있다.

입력 감사78/78: `invisible_measurements=0`, `held_world_reads=0`, `control_top_camera_reads=0`. 확정 장면/원본 v1 바닥/no_mip 및 새 경계 토글OFF도78/78 확인했다. 원본 manifest22,899파일 저장/압축 해시 불일치0, 최종 오수용0. 최종 구역 적합성과2초 안정은 저장된 evaluator qpos/contact에서 `mj_forward`만 사용해 다시 셌다. 짧은6회는 별도2534파일 검증이며 당시 전체 안정 snapshot이 없어 지속 시간은 원래 evaluator 기록을 사용했다. 첫30SIM초 wall/SIM 중앙은 최초16회4.181827, 재개 첫16회4.058101로6.0 차단 기준을 통과했다.

실패 전체0–56.1SIM초2Hz, 성공0–32.2초2Hz와 실패 사건 직전 world45.5–55.5초10Hz(자기 RGB 원본202장)를 파일로 직접 확인했다. A는 둘러보기·재파지 뒤 빔을 든 채 멈췄고, 마지막10초에서 빠른 진동은 관찰하지 못했다. 전체 재생 끝의2.4초는 평가용 안정 확인이므로 실제 실패 직전 native10초 띠를 별도로 만들었다. `visual-review.json`에 시각 범위·타임라인·듬성한 검토와 차이를 기록했다.3배속 개요+r1+r2 영상은 각각8MB 이하이며 `ffprobe`를 통과했다. Mac 물리·렌더·GUI는0이다.

운영 오류와 무효 시도는 `release-final-attempt-ledger`의126회에 모두 보존했다. 장면 연결 두 버전의 HOST_ERROR12, 최종 소스 기록 훅 API 오류16 HOST_ERROR, 용량 입장 거부를 예외 처리한 옛 감독기에서 중단14(10회 중단 최종화·4회 최종화 미완 HOST_ERROR)가 있었다.4개의 원래 `running` 상태는 고치지 않고 불완전 원본 SHA 목록을 보존했다. 최종 계획80에서 검증된20성공을 그대로 유지하고 중단/미제출60개만 같은 소스·조건으로 재개했다. 입장 거부 시 대기하고 제출 성공 뒤 pending을 빼며 Python 자식에 SIGINT를 한 번만 보내도록 수정했다. 용량5건·단일 SIGINT 회귀 검사를 통과했고, 결과 수집기 DONE 경합도 수정했다. 제어 후보를 합친 결과가 아니다.

검증: 관련 비물리 release24 14 PASS(빔 짝32 PASS는 별도 PR522). 판정 상수는 새로 추가하거나 완화하지 않았다. 소스·기록·작은 대표 영상은 Git에, 원본은 gcp2 `/home/ugrp/ugrp-sim/runs/gv5-release-*`에 있다. 독립된 전체 raw 백업은 만들지 않았다. Mac에는 요약·몽타주·검토 프레임·작은 영상만 회수했고 `retrieval-verification-release.json`으로 gcp2 저장 SHA를 대조했다. 큰 JSON은 `.json.zst`로 무손실 압축하고 복호화 SHA를 `.compression.json`에 기록했다.

자기 실행 프로세스와 임대를 정리했다. 다른 `beampair7` 임대가 있어 VM은 정지하지 않았고 기존 유휴/예산/24시간 STOP 장치를 유지했다(`cleanup.json`). 원본·소스·공유 참조 저장소를 보존했다. 새 후보와 새 관문 전까지 잔여 제출은 차단 상태다.
''')
# Compress only the copied record artifacts; remote inputs and fetched originals stay intact.
compression=[]
for p in record.rglob('*.json'):
 if p.stat().st_size<=65536:continue
 before=p.read_bytes();subprocess.run(['zstd','-q','-f','-k',str(p)],check=True)
 zipped=Path(str(p)+'.zst');assert subprocess.check_output(['zstd','-qdc',str(zipped)])==before
 meta=dict(file=zipped.name,decoded_bytes=len(before),decoded_sha256=hashlib.sha256(before).hexdigest(),stored_bytes=zipped.stat().st_size,stored_sha256=hashlib.sha256(zipped.read_bytes()).hexdigest())
 write(Path(str(p)+'.compression.json'),meta);compression.append(str(p.relative_to(record)));p.unlink()
for name in ['summary.json','status.json']:
 p=record/name
 if not p.exists():continue
 d=json.loads(p.read_text())
 for k in ['raw_recount','rejection_table','operating_attempts']:
  if k in d and d[k] in compression:d[k]+='.zst'
 write(p,d)
print(json.dumps(dict(record=str(record),compressed=compression,files=sum(p.is_file() for p in record.rglob('*')))))
