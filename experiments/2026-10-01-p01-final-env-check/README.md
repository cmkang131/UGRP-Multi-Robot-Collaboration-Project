# P01 최종 환경 v84 물리 점검 (3지도 × reset 30 SIM초)

**결과 요약.** PR #338이 main에 넣은 `zone-final-environment-v84` / `zone-final-environment-check` 2.17.0의
P01을 handoff 명령 그대로 실행했다. 3지도 모두 `COLLECTED_UNQUALIFIED`로 끝났고(실패 0, 미시도 0, 분모 3),
handoff가 적은 기계적 점검 10개를 모두 만족했다. 이것은 **환경 적합(PASS) 판정도 임무 성공도 아니다.**
이 실행에는 학생·LLM·제어기·교사 주행 명령이 없다(모델 호출 0). P03(3×120 SIM초)은 실행하지 않았다.

새 번들·workflow ID는 만들지 않았다(기존 v84 / 2.17.0 사용). 기본 체크아웃과 봉인 파일은 바꾸지 않았다.

## 고정한 조건

| 항목 | 값 |
|---|---|
| 실행 소스 | main `5ba853ddc5b0e300e45f8361e98e7f9f16e08c18` (작업 트리 깨끗, 실행 전후 소스 변경 없음) |
| 번들 / workflow | `zone-final-environment-v84` / `zone-final-environment-check` 2.17.0, catalog sha256 `bef2764a…a256` |
| 관리 기록 | `sim-record/manifest.json` (sha256 `f764467080bb7d0c…1e6e`), run_id `20261001-040457-zone-final-environment-check-002d4bcc` |
| 시드 / 시계 | seed 911 / SIM(동기 모드) |
| 물리 | `cargo_noslip_v1`(timestep 0.00025 s, noslip 10), weld OFF, 초음파 OFF, robot `masterpi_v3` |
| 렌더 | **번들이 고정한 기본 authored/default 렌더.** 작업 지시의 `floor_light_v1`은 적용하지 않았다(아래 "사용자 결정") |
| 환경 | Python 3.12.13, mujoco 3.12.0, numpy 2.5.2, macOS 27.2 arm64 (.venv-sim-worker-mac) |
| 잠금 | `agent_lock.py` owner=claude, branch=`claude/phys-p01-1001`, pid 37441 → 실행 뒤 `release`(status null 확인) |
| 부하 | 잠금 획득 시 load avg 15.95/16.76/17.68, 종료 시 14.78/16.03/17.32. 사례별 값은 아래 표 |
| 디스크 | 실행 전후 여유 38 GiB(10 GiB 기준 충족). raw 15 MiB |

명령(handoff 그대로, `RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-env-v84-p01-1001`):

```sh
python -m scripts.sim_cli workflow plan zone-final-environment-check -- \
  --check p01 --expected-source-sha 5ba853dd… --output $RUN_ROOT/p01      # runnable, execution_started=false
python3 scripts/ugrp_session.py run final-env-v84-p01-1001 -- \
  python -m scripts.sim_cli workflow run zone-final-environment-check -- \
  --check p01 --seed 911 --expected-source-sha 5ba853dd… \
  --execute --lock-owner claude --output $RUN_ROOT/p01                    # exit 0, process_completed, 60.1 s wall
```

정적 사전 확인 `python -m scripts.zone_environment_bundle --map-id zone_wide_door_geometry_v3 --check p01`의
`blocked_on`은 `[]`였다. 잠금·세션 드라이버는 작업 스크래치의 작은 bash 래퍼(`drive.sh`)로 위 명령을 감쌌다.

## 결과 (사례별, SIM 시간 기준)

| 지도 | reset SIM s (상한 5) | 관찰 SIM s (정확히 30) | 총 SIM s | 상태 | 기계 점검 10/10 | load avg 시작→끝(1분) |
|---|---|---|---|---|---|---|
| 문 1개 `zone_wide_door_geometry_v3` | 1.30 | 30.00 | 31.30 | COLLECTED_UNQUALIFIED | 통과 | 15.95 → 12.48 |
| 문 2개 `zone_wide_two_doors_final_v3` | 1.30 | 30.00 | 31.30 | COLLECTED_UNQUALIFIED | 통과 | 12.48 → 13.64 |
| 복도 `zone_wide_corridor_final_v3` | 1.30 | 30.00 | 31.30 | COLLECTED_UNQUALIFIED | 통과 | 13.64 → 14.78 |

합계 94 SIM초(상한 105). 실행 벽시계 60.1초는 부하 12~16 조건의 참고값이며 속도 비교용이 아니다.

handoff의 검토 항목별 결과(3지도 동일; 계산은 `analyze_p01.py`, 원본 수치는 `analysis/*.json`):

| 점검 | 결과 |
|---|---|
| map/scene XML sha256이 bundle·scene.json·applied.json에서 일치 | 일치 (3/3) |
| 실제 robot XML 모델 v3, weld off, noslip 10, timestep 0.00025 | 일치 |
| 표식(tag) geom 0, scene.xml에 tag/landmark/marker 문자열 0 | 0 |
| 벽 높이 | 0.40 m (XML half-z 0.2) |
| 초기 배치 | 로봇 3대 x=-0.8982, 문/복도 지도도 같은 시작점; 예기치 않은 장애물 0 |
| 초기 겹침·관통 | 비바닥 접촉 0행/601표본. 바닥–바퀴 최소 거리 -0.161 mm(정상 접촉 깊이) |
| 정지 drift (30 s) | 위치 ≤ 2e-9 mm, yaw ≤ 4e-12 도 (사실상 0) |
| 자기 영상 | 로봇당 7프레임(t=1.3, 6.3, …, 31.3), 3지도×3로봇=63 PNG 640×480, 해시 전부 일치 |
| 카메라 | fovy 42.19°, 640×480, 위치·자세가 `masterpi_camera_profile`과 동일(3로봇 동일) |
| 학생/LLM/교사 명령 | 0. 로봇마다 초기 서보 고정 자세 명령 1건(1:2000, 3:740, 4:2320, 5:1320, 6:1500)이 commands.jsonl에 있다 |

접촉 기록은 0.05 s 간격 표본이며 모든 내부 substep 접촉을 기록했다는 근거가 아니다.

## 눈으로 본 관찰 (`outputs/final-env-v84-p01-1001/contact_sheet_first_frames.png`(첫 프레임 합성, 커밋 안 함): 열=3지도, 행=r1/r2/r3)

- 세 로봇 모두 +x를 향하고 화면은 바닥 격자가 대부분이며 수평선·벽 윗부분·작은 색 상자가 화면 위쪽에 보인다. 팔·집게는 보이지 않는다(카메라 외관을 바꾸지 않았다).
- 기본 렌더라 전체적으로 어둡고(특히 r3) 채도가 낮다. 정지 조건이라 한 로봇의 7프레임은 해시가 모두 같다(정상).
- 문 1개·문 2개·복도 지도는 같은 시작 위치에서 본 첫 화면이 서로 매우 비슷하다. 이 점검만으로 지도 구분 가능성을 주장할 수 없다.
- 위는 사람이 본 인상이며 "카메라 문제 없음"을 자동 판정한 것이 아니다. 위치 추정 정확도·파지·연쇄는 이 실행의 범위 밖이다.

## 실행하지 않은 것 (목록만)

1. **P03 3×120 SIM초**: 실행하지 않았다. handoff상 측정된 v3 보정과 v3 pair chain adapter가 없어 `runnable:false`다.
2. **unloaded 보정 수집** (handoff에 SIM으로 가능하다고 적힘, 추가 예산 필요, 이번에 실행하지 않음):
   3지도 × 120 SIM초, reset 포함 최대 375 SIM초. 정적 측정 계획은 `configs/final_environment_measurement_v1.json`.
   search/p20/빈 carry 팔 자세 각각 8 pan × 3초 = 72초, 전진·측면·회전의 ±0.03 명령(0.25초×4회)과 정지 관찰.
   실행 로봇은 r1(나머지 정지), 3대 자기 영상·명령 저장, GT는 `eval_only/`(오프라인 보정용)에만.
   ```sh
   python3 scripts/ugrp_session.py run final-env-v84-calibration -- \
     python -m scripts.sim_cli workflow run zone-final-environment-check -- \
     --check calibration --seed 911 --expected-source-sha <SHA> \
     --execute --lock-owner <owner> --output <새 경로>/calibration-unloaded
   ```
   (잠금 획득/해제는 P01과 동일.) 이 수집은 **원시 자료만**이며 보정 파일이나 성공 판정을 만들지 않는다.
3. **loaded/fine 수집·fitting·pan–chassis yaw 결합·자세별 카메라 외부 보정**: 수집 경로가 아직 없다(v3 pair adapter가 먼저 필요).
   따라서 측정된 v3 보정 파일(`MEASURED_SIM`)은 unloaded 수집만으로 완성되지 않는다.

## 사용자 결정 필요

- **렌더 프로필:** 작업 지시는 `floor_light_v1`이었으나 handoff는 "밝은 바닥/C_mix_rgb를 몰래 채택하지 않는다"며 번들이 기본 렌더에 고정돼 있다.
  나는 번들·handoff를 따라 기본 렌더로 실행했다. 운반 코호트 기본 프로필(floor_light_v1)로 바꿔 P01을 다시 보려면 새 번들 버전이 필요하다.
- 기본 렌더의 어두운 화면이 위치 추정 입력으로 충분한지는 P01로 판단할 수 없다. 비교가 필요하면 별도 지시가 필요하다.
- unloaded 보정 수집(최대 375 SIM초)을 승인할지.

## 원본·보존

- raw: `/Users/changmin/projects/ugrp/outputs/final-env-v84-p01-1001/` (`p01/` 119파일 15 MiB(PNG 63), `raw_p01.sha256`=전체 파일 sha256 목록(그 자체의 sha256 `b71deb9f4d3a9239…0cc8`),
  `sim-record/`, `logs/`, `derived/`). 삭제·덮어쓰기 없음. 원격 백업 아님(로컬 보관).
- 이 폴더의 `raw_small/`은 결과·bundle·scene·applied·setup JSON과 해시 목록의 사본(작은 파일만). PNG·접촉 JSONL은 outputs에만 있다.
- 기본 sim 관리 기록은 worktree `outputs/simulation-runs/…/manifest.json`에서 위 `sim-record/`로 복사했다.
- Drive 미사용.

## TensorBoard

- 스냅샷 `outputs/tensorboard/1001-p01-final-env-v84-audit` (파생 뷰 3개; 지표: 비바닥 접촉 수, 최소 접촉 거리, drift, reset/관찰 SIM 시간, 프레임 수, 벽 높이, load avg).
  `evaluation/reported_success`는 위 기계 점검 10개 통과 여부일 뿐 환경 PASS·임무 성공이 아니며 정의를 `result/summary`에 적었다.
- 스냅샷 `outputs/tensorboard/1001-p01-final-env-v84` (표준 변환기; `claims/protocol_complete`, `result/model_calls`, 요약 텍스트).
- 공용 뷰어(127.0.0.1:6006, 기존 서버)가 두 스냅샷의 6개 run을 읽음을 API와 화면(고정 카드 값: door1 비바닥 접촉 0, 최소 거리 -0.1608 mm)으로 확인했다.
  run이 500개를 넘어 새 run은 선택 해제 상태로 열리므로 왼쪽에서 3개를 체크해야 한다. `outputs/tensorboard-view.json`에 키 `p01_final_env_v84_20261001`만 추가했다.
- 영상은 없다(정지 PNG 자료). 이미지 카드는 만들지 않았다.

## 한계

- 정지 자료 수집 점검이다. 제어기·위치 추정·파지·문 통과·운반은 전혀 검증하지 않았다.
- 접촉은 0.05 s 표본, 카메라 판정은 사람 눈 확인이다. v3 보정은 여전히 미측정(null)이다.
- 같은 seed 911, 사례 1회씩이라 통계 주장은 없다. 3지도의 시작 배치가 동일해 지도 차이는 벽·문 배치 외에는 드러나지 않는다.

## 참고 자료

- PR #338(P01/P03 실행 등록), [PHYSICS_HANDOFF.md](../../PHYSICS_HANDOFF.md), [등록 기록](../2026-10-01-final-env-runnable/README.md)
- [P01 계획](../2026-09-30-e2e-p01-env/README.md), [실행 버전 관리](../../docs/execution_versioning.md), [TensorBoard](../../docs/tensorboard.md)
- 물리 큐 #337
