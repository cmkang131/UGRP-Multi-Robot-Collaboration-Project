# AMCL 2 — GCP 신규 자기 RGB 기록 준비

## 범위와 실행 경로

1차의 Azure VM3 JPEG 회수 요청은 사용자 지시로 폐기된 경로다. 과거 원본·기록은 보존하며 VM3를 조회·시작·회수하지 않았다. 이번에는 **gcp1에서 새로 기록할 40실행 × r1/r2 = 80구간**을 준비했다. 아직 실제 기록·AMCL 성능 비교는 미측정이다. 합성 fixture 결과를 주행 정확도로 보고하지 않는다.

`e2e18-v225` workflow의 `scripts/run_e2e_ownmap_live.py`, `harness.e2e_live_mapping.Robot`, `sim.e2e_ownmap_live.PhysicsBackend`를 재사용하는 얇은 기록 adapter를 `map-amcl-record`로 등록했다. 별도 물리 엔진·프레임 writer·위치 추정기를 만들지 않았다. `sim.lazy_camera.capture_robot_frames`가 실제 카메라 JPEG 바이트와 frame ID·SIM 시각·명령 servo를 저장한다. AMCL 4후보는 제어에 연결하지 않는다.

#480 코호트는 40개의 **저장 상태 파지 진단 suffix**였고, 원본 길이는 37,572프레임·구간 중앙 456.5프레임이다. 현재 브랜치에는 그 모든 v375–v400 단계 정책과 복원 입력이 없다. 따라서 과거 파지 상태를 재현했다고 주장하지 않는다. 동일 종류의 자기 RGB 기반 주행·회전·정지 관측을 **새 표준 초기화 뒤 60초 지도 탐색**으로 수집한다. E2E 임무·파지/운반·LLM 판단의 대체나 성능 검증이 아니다.

- 장면 `e2e_one_beam_ownmap`, 지도 `zone_wide_door_e2e_b80_v1`, v7 구동, v3 카메라, `real_v1` servo stiffness, `floor_light_v1`, weld OFF를 사용한다. 원본 로컬 bundle과 현재 scenario·map·구동·카메라·RGB VO 소스의 해시 대조는 `recording-provenance.json`이다. 실제 GCP scene XML·지도·런타임 해시는 실행 때 별도 기록한다.
- 현재 코드가 정적 지도→자기 RGB 좌표계 정합 부족으로 `standoff_fullquad_v1`의 live 사용을 거부한다. 그 가드를 유지하고 현재 허용된 `candidate_views_v1`을 사용한다.
- 기준 fused odom은 기존 `e2e_rgb_vo`의 command/RGB fusion과 시각 정지 fallback인 `rgb_vo_v2`, `homography_v1`, `no_ransac_v1`이다. 이전의 `rgb_vo_us_v1`에서 초음파 소비를 뺀 조건이며, 1차의 9.51cm·11.21°를 새 기준값으로 승계하지 않는다.
- 두 자기 카메라만 640×480 native JPEG로 **10 Hz, [0,60]초의 601장/로봇**을 모두 저장·소비한다. 정지·중복 바이트·미안정 카메라 영상도 보존한다. 명령 발행은 기존 5 Hz다. `speed3`·픽셀 축소·관측 stride는 끈다. r3는 표준 초기화 상태로 대기한다. top 영상·상대 카메라·정답 자세는 제어/위치 추정에 전달하지 않는다. 정답은 `eval_only` 출력과 물리 중단 감독에만 있다.

## 시드·분모·예산

예약 시드 **65101–65140**, 각 1회다. 로컬 설정·실험·조정 대기열의 JSON 5,550개(파일당 ≤10MiB)의 seed 필드에서 충돌 0건을 확인했다. 원격 실행 이력은 조회하지 않았으므로 조정자가 미사용 여부를 확인해야 승인할 수 있다. 고정 초기 배치에서 physics seed와 로봇별 RNG seed `2×seed+i`가 달라진다. 40개 독립 지도라는 뜻이 아니다.

모든 예정 구간은 초기 수렴·정지까지 포함한 [0,60]초이고 **N=80**을 유지한다. 프레임 계획은 48,080장으로 과거 37,572장보다 약 28% 많다. 실패·중단·누락을 새 시드로 대체하거나 짧은 성공 부분만 잘라 쓰지 않는다.

| 항목 | 상한/근거 |
|---|---|
| 실행 수·동시 수 | 40회, 동시 1개; 첫 실행이 기록·속도 probe를 겸함 |
| SIM | 실행당 주행 60초 + 초기화 최대 5초; 주행 합계 2,400초, 초기화 포함 ≤2,600초 |
| JPEG 추정 | 2×601×64KiB = 75.125MiB/실행; 64KiB는 계획 여유값이며 GCP 실측 아님 |
| 텍스트·설정 추정 | 128MiB/실행을 추가해 약 203.125MiB 예상 |
| 기록 디스크 예약 | 여유를 둔 **512MiB/실행 ×40 =20GiB**, 실행 중 매 SIM초 사용량 검사 |
| 비교 디스크 예약 | 특징·5개 궤적·원장 ≤8GiB; 합계 28GiB + 서버 최소 여유 8GiB |
| 시간 | 실행당 wall 900초, 오프라인 비교 7,200초, 전체 작업 wall 7시간; VM 8시간/유휴 20분 유지 |
| 회수 | 텍스트·요약·해시만 ≤128MiB; JPEG 원본은 GCP 영속 디스크에 보존 |

GCP n4-highcpu-64의 기존 동시40 속도 측정은 이번 10 Hz 구성의 속도 보증이 아니다. 첫 실행의 첫30 SIM초 wall/SIM ≤3.5와 완전한 기록을 확인해야 후속 실행을 허용한다. 각 실행에도 같은 30초 속도 중단을 적용한다. 30초 원본에서 실제 자기 영상·발행 명령·주행 여부·오류를 조정자가 확인한다. 속도 미달, 실제 제어 결함, 물리 중단 또는 HOST_ERROR가 나오면 영향받는 후속 대기 작업을 중지하고 수정본으로 다시 등록한다. 비용 정지 장치가 발동하면 중지·통보하고 다른 호스트로 넘기지 않는다.

## 오프라인 비교와 관리 명령

아래 `SOURCE_SHA`는 이 코드가 커밋된 전체 SHA이고 대기열이 고정한다. `RAW_ROOT`는 gcp1 영속 디스크의 새 cohort 폴더다. **현재 실행 off**이며 아래는 조정자가 승인한 뒤 사용할 명령이다.

```sh
# 읽기 전용 실행 계획
python -m scripts.sim_cli workflow plan map-amcl-record -- \
  --seed 65101 --expected-source-sha SOURCE_SHA \
  --output RAW_ROOT/map-amcl-record-s65101

# 승인된 Linux gcp1에서만, seed마다 기존 공통 workflow로 실행
UGRP_EXECUTION_HOST=gcp1 MUJOCO_GL=osmesa python -m scripts.sim_cli workflow run map-amcl-record -- \
  --seed 65101 --expected-source-sha SOURCE_SHA --approval APPROVED_QUEUE_JSON \
  --execute --output RAW_ROOT/map-amcl-record-s65101

# 40개 예정 실행의 성공·실패·미실행을 모두 조사하고 같은 프레임 비교
python -m scripts.sim_cli workflow run map-amcl-compare-recording -- \
  --raw-root RAW_ROOT --recording-source-sha SOURCE_SHA --output NEW_COMPARISON_DIR
```

`compare_map_amcl_recording`은 호스트·머신 종류·소스·spec·완료 상태와 원장/JPEG/평가 파일 해시, 10 Hz 시각, 프레임 수를 먼저 검사한다. zstd 텍스트는 해제한 원본 해시를 확인한다. 프레임·특징을 만들 때 평가 값을 읽지 않으며, 각 구간의 **기준 + 벽/벽·랜드마크 × 명령/fused 4후보** 추정 궤적을 모두 만든 후에만 평가 자세를 연다.

같은 프레임 ID·JPEG SHA·구간 정의로 SE(2) 강체 정합 위치/방향 중앙값, 5cm/5° 통과 n/N, 추가 거리비 판정, 절대 지도 오차, 전체 프레임별 명령 대비 점프 표식을 낸다. 점프 표식 5cm/5°는 물리 속도 한계가 아니다. 절대 오차는 전역 지도 오위치를 정합이 숨기지 않는지 확인하는 별도 값이다. 한 후보라도 누락/오류면 해당 구간은 5후보 전체의 `paired_aggregates`에서 미평가로 남고, 원래 후보별 상태·원본은 따로 보존한다. 정지 구간의 미정의 거리비도 유지한다. 자동 승격은 없다.

작업 종료 후 기존 `scripts/compress_json_traces.py`로 >64KiB 텍스트를 무손실 압축·해제 해시 검증하고, 압축 manifest까지 보존한다. 삭제/보존 정책을 바꾸지 않는다. GCP 결과는 Azure 과거 자료와 합산하지 않는다.

## 검증과 인계 상태

검증은 `tests/test_map_amcl_recording.py`, `test_map_amcl.py`, `test_e2e_static_rgb_localizer.py`, `test_e2e_stage_pose_eval.py`만 실행한다. 합성 backend의 10 Hz 전량 저장·5 Hz 명령, Mac/미승인 실행 차단, 기존 actor 생성 및 합성 RGB 소비, 저장 JPEG 특징 추출, 동일 프레임 5후보, 평가 입력 분리, 손상/누락/압축/후보 실패 분모를 검사한다. 최종 수치와 공통 workflow 합성 실행의 종료·출력 해시는 `amcl2-validation.json`에 남긴다. 합성 자료는 로컬 `outputs/map-amcl2-validation/`에 있고 실제 주행 근거가 아니다.

대기열은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-map-amcl-record-<SHA8>.json`에 저장한다. 디렉터리 이름은 공용 대기열 관례일 뿐 대상은 **gcp1 / ugrp-act-train-1014**다. `coordinator_approval.approved=false`, `execution_enabled=false`, `execute=false`, 자동 승격 false다. 이 작업의 원격 연결·시뮬레이션·렌더·모델 호출은 모두 0회다. 실제 기록, GCP 10 Hz 속도·디스크 확인, AMCL 성능 측정은 승인 후 작업으로 남는다.
