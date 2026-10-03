# 높은 자세 공동 운반 후보 v96 (첫 등록 v93은 미실행 은퇴)

2026-10-03. D1의 새 학생 제어기 후보다. **MEASURED_SIM 경로는 #361 D5 계약을 통과하고 승인 목록에 오른 v92 실측 보정
이 없으면 실행을 차단한다(승인 목록은 비어 있음).** 별도 DEV_PILOT 경로는 등록된 정확한 sha256 하나만 받는
비확증 기능 시험이며 결과는 항상 FUNCTIONAL_DEV로, 확증·MEASURED_SIM 증거로 승격할 수 없다(아래 2차 대응).
기존 학생의 성공 판정은 승계하지 않는다. 렌더 수집과 P03 인수는 코디네이터가 수행한다.

현재 P03(seed 911, dock 시작 세 체크포인트)은 **기능 확인용 개발 재생(FUNCTIONAL_DEV_REPLAY)**이며
독립 표본 3개나 확증 자료가 아니다. 확증용 시작점은 별도 등록 파일에 고정했다(아래 P2-1).

## REVIEW_363 2차 대응 (2026-10-03, Claude) — 현재 상태

2차 BLOCK(리뷰 코멘트 5967979217)과 코디네이터·사용자 결정을 반영했다. 결정 근거와 출처는
[COORDINATOR_DECISION.md](fix363/COORDINATOR_DECISION.md)에 있다.

- **P1-2 시간 → 해소:** P03 사례 cap을 사전 등록 개정(v96-cap-2)으로 3×300 SIM초로 바꿨다. P03 자료 전에 정했고,
  세 사례(before_door, after_door, before_destination)를 모두 실행 대상으로 계획한다. 하한 63.8/104.2/184.6초,
  전체 운반 190–219초([생성기](fix363/time_lower_bounds.py)). 부모 실행기가 넣던 집행기 작업 제한
  `job_sim_limit_s=120`도 300초로 맞추고 번들 timing에 기록했다.
- **P1-4 이동 중 grip 감시 → 사용자 범위 결정으로 해소:** 첫 E2E에서 집게 감시는 **기록만** 한다
  (사용자: "ㅇㅇ 그렇게 하자"). 단계 진행·barrier 준비는 자기 명령 이력 + 고정 상태 채널로만 판단한다.
  이 버전은 빔을 떨어뜨려도 실행 중 감지·통보하지 않는다. 자기 집게 감지 + 조건별 신호(사용자: "상대가 놓치면,
  놓쳤다고 신호를 보내면 되잖아 llm을 통하던지 실험 조건에 따라서")는 첫 E2E 뒤로 미뤘다.
  `relation()`은 실제 렌더에서 정상 상승·하강 대부분을 실패하고 상대가 놓친 쪽을 통과시킨다([점수](fix363/relation_zero_check.json)).
- **비순환 테스트:** `tests/test_highpose_transit.py`는 합성 영상 대신 실제 렌더 손목 영상
  ([fixture](../../tests/fixtures/highpose_recorded_frames/manifest.json), 68장, sha256 확인)으로 상태 기계를 돌린다.
  정상 완주, 집게 열림 영상도 기록만 됨, 감시값을 적대적으로 바꿔도 제어 궤적이 비트 단위로 같음(쓰기 전용 기록기),
  중간 HIGH 체크포인트 재개·재관측 시간 초과 시 상대가 상태로 멈춤을 확인한다.
- **DEV_PILOT:** v92 조립이 PARTIAL이라 MEASURED_SIM 승인이 비어 있다. 코디네이터 결정으로 정확한 sha256 하나만
  받는 DEV_PILOT 입장 경로를 추가했다(`--admission dev-pilot`). 결과·체크포인트 기록에 `FUNCTIONAL_DEV`,
  전용 코호트·TensorBoard 코호트, `promotable:false`가 붙고 확증 진입(`starts.qualify_run`)이 거부한다.
- **기록 위치:** 렌더 영상 raw `/Users/changmin/projects/ugrp/outputs/pr363-render-frames-20261003`,
  `...-seed912-20261003`, `...-seed913-20261003`(로컬 보관, 원격 백업 아님). 1차 진단 스크립트
  (`fix363/headless_grip_monitor.py`)는 기록된 SHA에서만 재현된다(`check_source`로 고정, 이후 감시 API 변경).

## REVIEW_363 1차 대응 (2026-10-03, Claude, 이력)

리뷰([REVIEW_363.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/review-363/REVIEW_363.md),
[PR 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5966787118))의
P1-1~P2-1을 한 묶음으로 고쳤다. Codex 작업 중 파일(WIP)은 검토 뒤 맞는 부분만 남겼다.

- **#361 의존:** 파일 복사 대신 `origin/codex/v92-loaded-schedule`을 병합 커밋으로 가져왔다(2d441ebe,
  ab180f2d로 재병합). #361이 main에 병합된 뒤(00eafd63) `origin/main`을 병합했으며(18b45f89), 이제 D5 로더·조립기는
  main에서만 오고 이 PR 차이에는 남지 않는다.
- **번호:** 바이트가 바뀌어 새 번호 **`zone-final-pair-highpose-v96` / 3.8.0**을 쓴다. v93/3.5.0은 실행
  기록이 없어 등록·계약 파일을 바이트 그대로 은퇴 보존한다. #365(criterion-B)는 v95만 사용한다(v94는 미사용 예약).
  [조회 원본](fix363/reservation_scan_v96.json): main과 열린 PR 8개에서 v96·3.8.0은 이 PR만 쓴다.
- **P1-1 실측 보정 관문:** `harness/zone_pair_highpose_contract.py`. 실행 CLI와 `run_case()` 직접 호출 모두
  #361 로더(`ugrp.final_environment_measured_calibration.v92`, `loader_contract_version=2`)를 통과하고,
  일정·B″·조립기 hash가 등록과 같으며, [승인 목록](../../configs/calibration/zone_pair_highpose_d5_admission.json)의
  `calibration_sha256`·source·manifest·수집 기록이 일치하고, 옆의 `input_manifest.json`·`fit_report.json`
  hash와 수집 감사 PASS를 확인해야 한다. 레지스트리와 번들 `runnable:false`도 존중한다.
  synthetic 보정은 테스트 전용 승인 행으로만 쓴다(CLI 우회 옵션 없음). 실측 params에는 PF 기본값이 없어
  `student_calibration()`이 `harness/owncam_localizer.py` 정적 기본값에 실측값을 덮어쓰고 그 hash를 기록한다.
- **P1-2 시간:** 중간 체크포인트에서 HIGH 유지(정지·재관측만), 마지막에만 하강. 사례별 시간 하한 자동 검사.
  before_destination과 전체 운반은 120초 안에 원리적으로 불가 → 2차에서 cap 300초로 개정(위).
- **P1-3 자세별 기준:** HIGH 기준(anchor)과 바닥 기준을 자세·epoch별로 따로 두고, 하강 뒤 바닥 복귀 영상을
  원래 바닥 기준과 비교(IoU≥0.70, 최대 3초)해야 open으로 간다. 합성 영상 회귀에서는 정상 하강이 통과하고
  하강 중 미끄러짐이 `FLOOR_RETURN_GRIP_CHANGED`로 멈춘다(BARRIER_OPEN_TIMEOUT으로 끝나지 않음).
  **실제 기하·RGB에서의 검증은 아직 없다**(무렌더 대역 영상은 집게·바닥을 그리지 않아 IoU 값이 의미 없음).
- **P1-4 이동 중 grip 감시 — 1차 당시 해결 못 함(2차에서 사용자 범위 결정으로 log-only):** `harness/zone_pair_highpose_grip.py`의 감시 틀
  (자기 명령 일치, 새 프레임, 상대 상태, 상승 끝 2초 안정 창, 중단 사유)은 넣었다. 그러나 핵심인
  빔 관계 검사(`relation()`, 명령 기하로 예상한 빔 위치 vs 빔 색 마스크)가 **실제 물리 기하에서 정상
  표본을 100% 실패**한다. 이대로면 정상 상승도 첫 표본(10.0초)에서 중단된다. 원인과 두 번의 수정 시도는
  아래 "fix363 무렌더 진단" 절에 있다. 규칙(같은 문제 두 번 → 멈춤)에 따라 시도를 되돌리고 재설계 결정으로 넘긴다.
- **P2-1 개발/확증 분리:** [확증 시작점](../../configs/zone_pair_highpose_confirmation_v96.json) 3개(seed 9301001–3)를
  고정했다. 이전 시작점 36개와 최소 0.127 m, 서로 최소 0.054 m 떨어진다(기준 0.05 m, 로봇 id·지도·seed와 무관).
  수집 뒤에는 `harness/kinematic_overlap.py`(#365 12c1e58c와 바이트 동일)로 t·위치·회전을 비교해 겹치면 거부한다.
  파일 바이트가 아니라 운동 내용으로 비교한다(#219 코멘트 5966536405·5966843527). 이전 궤적 목록이 아직
  없어 확증 자격 판정은 `PRIOR_KINEMATIC_INVENTORY_REQUIRED`로 거부된다.

## fix363 무렌더 진단 (P1-4)

리뷰어의 무렌더 3조건(정상, 한쪽 2초 지연, 상승 중 한쪽 집게 열림; 52 SIM초, 렌더·모델 0, weld OFF)을
소스 `255a4401`로 다시 돌렸다. 0.1초마다 실제 카메라 위치와 실제 빔 상자로 만든 **기하 대역 영상**(조명·질감·
JPEG·집게 가림 없음)을 v96 판단 코드에 자기 발행 PWM과 함께 넣었다. RGB 검출기 검증이 아니며 학생 실행·P03도 아니다.
[집계](fix363/headless_grip_monitor_results.json), [구동 코드](fix363/headless_grip_monitor.py), [기하 비교](fix363/projection_check.py).

| 조건 | r1 관계 통과 (상승/HIGH/하강) | r2 관계 통과 | 첫 중단 시각 | 빔 최대 기울기 |
|---|---|---|---|---|
| 정상 | 0/172, 0/68, 0/136 | 0/172, 0/68, 0/136 | 10.0초 (둘 다) | 0.016° |
| r2 2초 지연 | 0/172, 0/68, 0/136 | 0/172, 0/68, 0/136 | 10.0 / 12.0초 | 1.68° |
| r2 집게 열림 | **98/172, 68/68**, — | 1/172, 0/68 | 10.0초 (둘 다) | 11.47° |

정상에서 전부 실패하고, 오히려 상대가 빔을 놓친 r1은 HIGH에서 68/68 통과한다. 즉 지금 검사는
"보수적"이 아니라 실제 기하에서는 거꾸로에 가깝다. 정상과 grip 손실을 구분하지 못하므로 감지 시각은 의미가 없다.

원인(같은 정상 물리에서 제어기 모델과 실제 MuJoCo 카메라·집게 위치를 로봇 바닥 좌표로 비교):

- 짐을 든 팔은 명령 기하보다 낮은 lift에서 약 11 mm, HIGH에서 약 14 mm 낮고(0.136 vs 0.150 m),
  카메라는 5–8° 더 숙여진다(처짐, sag). 명령 기하만으로는 화면 예측이 틀린다.
- HIGH에서 보이는 빔은 **집게 앞 1.5–3.1 cm뿐**이다. 렌즈 아래 12–16 mm, 근접 절단면(near plane 2.2 cm)
  근처라서 몇 mm 차이로 화면 넓은 영역이 바뀐다. 실제 빔 중심은 집게 기준 4.6 mm 아래로 카탈로그 값 8 mm와 3.4 mm 다르다.
- 시도 1: D5 실측 적재 카메라(여기서는 실제 카메라를 이상적 측정으로 사용)로 투영하고 집게를 카메라에 강체로 붙임 →
  집게 위치는 0.1 mm까지 맞지만 HIGH coverage 0.38→0.50(기준 0.65)으로 여전히 실패.
- 시도 2: 미리 정한 먼 영역(집게 0.06 m 너머)만 사용 → 그런 영역이 화면에 아예 없어 support 0.
- 두 시도 모두 되돌렸다. 재설계 방향(결정 필요): 투영 대신 같은 자세의 자기 기준 영상과 비교하는
  기존 검증 방식(hold IoU, 가장자리 추적)으로 바꾸고, 상승 중 보이지 않는 구간은 "관측 불가"로 명시하며,
  실제 렌더 RGB로 정상/지연/집게 열림을 다시 검증해야 한다.

(1차 당시) 번들은 `runnable:false`이고 실측 보정 승인도 비어 있어 실제 실행은 막혀 있었다. 2차에서는 감시를 기록 전용으로 바꿔 이 검사가 진행을 막지 않는다.
raw: `/Users/changmin/projects/ugrp/outputs/pr363-fix-grip-monitor-20261003`,
`/Users/changmin/projects/ugrp/outputs/pr363-fix-projection-check-20261003` (로컬 보관, 원격 백업 아님).


## 변경과 입력 경계

기존 `zone-final-pair-v88`의 `zone_final_pair_skill.Team/Execution`과 b-v6g/b-v6h1 계열
beam-relative 제어기, 빔 추적기(BeamEdgeTracker), 정적 경로, 가드, 상태 통신, P03의 동일 PF·
0.16 SIM초 지연을 재사용한다. `scripts/run_camera_pair_transport.py`는 이전 LLM 두 로봇
경로이며, 현재 최종 v3 학생의 기반은 v88 어댑터다. 이를 새 LLM 제어기로 대체하지 않는다.

바닥 파지→기존 낮은 lift의 자기 RGB 확인→110/130 mm 경유→150 mm 높은 자세(HIGH)→
운반→역순 경유 하강→바닥 내려놓기→release 순서다. 높은 자세 PWM(3·4·5·6)은
`896,2035,1894,1500`으로 PR #361과 같다. 경유마다 1.2초 보간·2.8초 대기,
HIGH 도착 뒤 8초 대기를 둔다. 실제 발행에는 기존 ArmSequence와 0.05초 격자를 사용한다.
새 높은 영상에서 가장자리가 보인 뒤 유지 기준 영상을 갱신하고, 지연된 자기 영상의
가장자리 기준이 생겨야 운반 준비를 보고한다. HIGH 밖의 적재 base 명령은 거부한다.

10/3 사용자 결정에 따라 위치 추정은 OpenCV다. 기존 markerless probe의 왜곡 보정·
명암/색차·균일 벽 띠 검출을 재사용해, 모호한 여러 띠와 유채색 가림은 버리고 정적 지도
PF에 벽 경계를 전달한다. 기존 PF 수명·운동·관측 품질 검사는 유지하며 학습 분할망이나
체크포인트를 생성·호출하지 않는다. 새 OpenCV 경로의 실제 RGB 정확도는 인수 대상이다.

제어 입력은 자기 RGB·공개 정적 지도·자기 발행 명령과 기존 상태 메시지뿐이다. 현재 좌표,
측정 관절, 접촉, 성공 판정은 제어기에 전달하지 않는다. 카메라 배치/FOV, 로봇·화물 외관,
`masterpi_v3`, `floor_light_v1`, `cargo_noslip_v1`, weld OFF, 초음파 OFF를 유지한다.

## 첫 등록 v93 기록 (은퇴, 이력 보존)

아래 절과 "검증 기록"은 v93 시점 기록이며 현재 v96 관문을 설명하지 않는다.


- 기준 소스: `7cd729416fc04dfc4633cb4da5c4cd9435dd582d`, 브랜치 `codex/pair-carry-highpose`.
- 새 번들·실행 경로: **`zone-final-pair-highpose-v93`**, 버전 **3.5.0**.
- main+열린 PR 9개 총 10 refs를 조회해 v92/3.4.0 최댓값과 원격 HEAD 일치를 확인했다.
  [조회 원본](reservation_scan.json)을 보존한다. 게시 직전 main+열린 PR 7개 총 8 refs를
  [다시 조회](reservation_scan_final.json)했고 최댓값 v92/3.4.0과 v93 미사용을 재확인했다.
- 새 [등록](../../configs/zone_pair_highpose_v93.json)과 [보정 계약](../../configs/calibration/zone_pair_highpose_v93_contract.json).
  v88/v90/v91 등록과 동결 B/B′/r4/r5는 수정하지 않는다. v91 held-out raw는 읽지 않는다.

새 로더는 schema `ugrp.final_pair_highpose_measured_calibration.v1`, `status=MEASURED_SIM`,
새 계약 hash, 세 지도 hash, `loaded_measurement_bundle_id=zone-final-pair-v92`,
`loaded_pose_id=masterpi-v3-pair-high-150mm-minus40-v1`, `loaded_camera_scope=high_only`를 요구한다.
source SHA, 실측 manifest·v92 일정·기준·조립기 SHA-256도 필수다. 이전 params/pair_model/
camera_models 형식은 재사용한다. loaded 카메라 키는 HIGH 하나이며 바닥/낮은 자세는 요구하지 않는다.
닫기부터 HIGH 정착 전, 하강 중에는 자기 영상의 grip/hold 검사만 유지하고 절대 위치 관측은
건너뛴다. 발행 명령 기반 예측과 불확실성은 유지한다. 이 구간에 임의 카메라 보정값을 채우지 않는다.

이 계약은 D1의 임시 소비자 인터페이스다. D5 담당자는 별도
`ugrp.final_environment_measured_calibration` 계열 HIGH 계약을 만들고 있어 **최종 D5
산출물과의 schema/필드/hash 호환 확인이 남았다**. 정확한 D5 원격 소스가 공개되면 새
로더에 연결하고 관련 회귀를 다시 검증해야 한다. 현재 로더의 synthetic 보정 수락 검사는
D5 호환 완료가 아니다. 실제 보정 파일·기준 B″·조립기 승인이나 v92 측정 완료를 만들지 않는다.

## 코디네이터 인수 계획

1. D2–D5의 기준·일정·조립기 고정 및 v92 수집/적합/독립 검토를 마친다. 해당 실측 파일과
   새 학생 후보 SHA·번들/소스 hash·환경을 고정한다. 아래 계획 출력의 실행 가능 조건을 먼저 검사한다.
2. 기존 stage probe의 구조로 최종 v3 장면에서 **단계별 준비 상태(staged state)**를 만든다.
   정렬 시작, 바닥 파지 직전, 낮은 lift 직후, HIGH 유지, 목적지 HIGH 상태에서 각각
   정렬→파지/lift→HIGH 상승→한 leg 운반→역순 하강/release를 검사한다. staging의 정답은
   평가 소유자만 사용한다. 학생에 전달하는 것은 동일 자기 RGB·발행 명령 이력뿐이며,
   준비 상태의 평가 좌표를 PF 현재 위치로 주입하지 않는다. staged 결과는 E2E/P03와 별도 분모다.
3. 각 단계에서 실제 RGB 가장자리 열/검출/기준 획득, 관절 제한, 빔 상승·기울기·네 집게 접촉,
   외부 지지/weld 없음, 명령·가드 중단을 평가 전용 출력으로 확인한다. 낮은/높은 영상 사이 IoU를
   같은 자세 유지 점수로 해석하지 않는다. 명령 이후의 실제 접촉·관절·카메라 응답을 독립 검토한다.
4. 단계 인수 뒤 **`zone_wide_door_geometry_v3` P03 3×300 SIM초**(사전 등록 개정 v96-cap-2)를 수행한다. 세 사례는
   지도 수가 아니라 문 앞·문 뒤·목적지 전 체크포인트다. 각 사례는 dock 독립 reset에서 시작하며
   실제 이전 leg를 거친다. 중간 체크포인트에서는 HIGH를 유지한 채 정지·재관측만 하고(lower/open/재상승 없음),
   같은 PF로 이어야 한다. 세 사례 모두 하한이 300초 안이라 실행 대상이다(하한이 cap을 넘으면 실행 전 거부).
   GT 재배치/PF 교체 없이 실행하며 미도달도 분모 3에 포함한다. reset은 회당 최대
   5초로 별도 기록한다(총 900+최대15 SIM초). MEASURED_SIM 보정이 없으면 DEV_PILOT(FUNCTIONAL_DEV, 승격 불가)로만 돈다. stage 준비 상태를 P03 성공으로 합산하지 않는다.
5. `SEQUENCE_OBSERVED_UNQUALIFIED`는 순서 관측일 뿐이다. 별도 실제 오차·접촉·운반·방출 판정,
   가림/edge 실패·시간 초과·미시도·HOST_ERROR/ENOSPC를 전부 보존한다. 세 지도 전체 carry,
   일반화, 실물 성공은 별도이며 이번 P03로 확대하지 않는다.
6. raw는 기본 체크아웃 `outputs/` 새 절대 경로에 보존한다. 모델 입력·자기 JPEG/명령·평가 기록과
   SHA-256, source/calibration/bundle/environment를 회수하고 TensorBoard 새 스냅샷에 표시·검증한다.
   자기 세션·자식·잠금만 정리한다. Google Drive는 사용하지 않는다.

계획 확인(물리·렌더 시작 없음):

```bash
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
"$PY" -m scripts.run_pair_highpose --check p03 --expected-source-sha "$FINAL_SHA" \
  --output /Users/changmin/projects/ugrp/outputs/pair-highpose-P03-NEW
```

실측 보정 뒤 코디네이터는 자기 worktree의 고정 SHA·깨끗한 tree·10 GiB 여유·소유 잠금을
확인하고 `ugrp_session.py run <새 세션> -- "$PY" -m scripts.sim_cli workflow run
zone-final-pair-highpose-v96 -- --check p03 --expected-source-sha "$FINAL_SHA"
--calibration <실측 파일> --calibration-sha256 <실측 SHA256> --lock-owner <소유자>
--output <새 절대 raw 경로> --execute`로 실행한다. 보정 부재의 차단을 해제하는 별도 우회 옵션은 없다.

## 검증 기록

관련 5개 파일의 최종 통과 줄은 **`138 passed, 1 deselected in 70.08s (0:01:10)`**이다.
새 후보 검사 20개, 기존 v3·카메라 계약·가장자리 추적·P03 수명주기 회귀를 포함한다.
과거 v6e 재생용 로컬 JPEG `r2/00025.jpg`가 없어 해당 검사 1개는 실행 목록에서 제외했다.
첫 실행의 `138 passed / 1 failed`와 원본 오류도 보존한다. 실제 RGB 재생 통과로 바꾸지 않는다.
[검증 명령·환경·로그/JUnit hash](validation.json), [기존 30개 파일 보존 hash](preservation.json)를 따른다.
컴파일, `git diff --check`, 고정 CI 자료 3개, 표준 workflow 계획 출력도 확인했다.
이는 로컬 결과이며 원격 CI·독립 검토·렌더/P03 인수는 별도다.

추가 workflow 카탈로그 검사는 **`17 passed, 1 deselected in 1.00s`**다.
전체 파일의 첫 실행은 17 pass/1 fail이며, 프로세스 정리 검사의 `/bin/ps`가 샌드박스에서
거부되어 그 검사만 제외했다. 로컬 프로세스 정리 검증 완료로 보고하지 않는다.

[고정 진단 명령](probe_headless.py)을 커밋 **`a19e232a3a2576832a145a0435e9450da017f759`**로
고정하고 52 SIM초 실행했다. teacher station 시작에서 실제 학생의 ArmSequence 상승/하강
경로를 재사용했다. [전체 집계](headless_check.json)와 [집계 코드](summarize_headless.py)를 보존한다.

| 구간/검사 | 실제 결과 |
|---|---|
| 낮은 lift 정착 [8,10)초 | 40/40 표본 상승·네 집게 접촉·외부 지지 없음 |
| HIGH 상승 [10,27.2)초 | 344/344 같은 조건 |
| HIGH 유지 [27.2,34)초 | 136/136 같은 조건, 빔 바닥 최소 114.849 mm |
| 하강 [34,47.6)초 | 257 lifted / 15 not_lifted; 전부 보존 |
| 전체 1,041표본 | 849 lifted / 192 not_lifted; 초기·바닥·release 포함 |
| 목표 관절 2,352개 | 제한 위반 0, 팔 최소 여유 0.2992 rad, 집게 0 m |
| HIGH 순기구학 | 높이 149.857 mm, pitch −40.05° |
| 자기 카메라 기하 | 낮은 자세 양쪽 0열, HIGH 30/32초 양쪽 90열 |
| 비용/환경 | 1,948명령, 모델 호출 0, weld OFF, 렌더 0 |

`lifted`는 빔 바닥≥10 mm·네 집게 접촉·외부 지지 없음·weld 없음의 평가 전용 판정이다.
기하 가시성은 RGB 검출 성공이 아니다. 이 결과는 운반 base 주행·자기 RGB 학생·v92 보정·
P03 인수를 포함하지 않는다. raw manifest의 모든 파일 hash를 대조했으며 원본 위치는
`/Users/changmin/projects/ugrp/outputs/pair-highpose-offline-20261003/headless-a19e232a`다.
원본은 로컬 보관이며 원격 백업으로 표현하지 않는다.

첫 관리 세션은 샌드박스 `/bin/ps` 거부로 물리 시작 전에 종료되었다. 별도 자식/렌더가 없는
고정 종료 진단을 직접 실행했고 종료 코드 0·소유 잠금 해제를 확인했다. 시작/끝 부하 평균은
집계 JSON에 보존했다. 다른 작업의 세션/서버는 변경하지 않았다.

TensorBoard 새 스냅샷 `1003-pair-highpose-v93/high-hold`에 같은 진단의 low 0열/HIGH 90열,
유지 136/136, 상승 344/344, SIM 52초·명령 1,948·모델 호출 0을 등록했다. 이벤트와
서버 API를 원본과 대조했다. 새 영상 등록은 0개이며 없는 wall/model 지연·임무 성공을
0으로 채우지 않는다. [대시보드 검증과 고정 링크](tensorboard_verification.json)를 따른다.

## 참고 자료

### 집게 감시 조사 (2차 대응, 출처 표기 그대로)

표기: [F] 페이지를 열어 읽음, [S] 검색 결과 요약만 봄, [K] 배경 지식(이번에 재확인 안 함).
[S] 표기 자료는 최종 보고서에 인용하기 전에 원문을 확인해야 한다.

- 기준 영상 + 마스크 정렬(ECC/ZNCC)이 1순위 추천. 같은 카메라·장착·실제 파지에서 얻은 기준 영상을 쓰면 일정한
  투영·보정 오차가 상쇄된다(목표 영상을 계산하지 않고 기록하는 teach-by-showing 시각 서보와 같은 논리).
  - G. D. Evangelidis, E. Z. Psarakis, "Parametric Image Alignment Using Enhanced Correlation Coefficient Maximization," IEEE TPAMI 30(10), 2008. http://xanthippi.ceid.upatras.gr/people/psarakis/publications/PAMI.pdf [S]
  - OpenCV `findTransformECC` / `findTransformECCWithMask` 문서 https://docs.opencv.org/4.x/dc/d6b/group__video__track.html , 마스크 PR https://github.com/opencv/opencv/pull/22997 , https://github.com/opencv/opencv/pull/3845 [S]
  - S. Baker, I. Matthews, "Lucas-Kanade 20 Years On: A Unifying Framework," IJCV 56, 2004, doi:10.1023/B:VISI.0000011205.11775.fd [S]
  - B. Espiau, F. Chaumette, P. Rives, "A New Approach to Visual Servoing in Robotics," IEEE T-RA 8(3):313-326, 1992 [S]. F. Chaumette, S. Hutchinson, "Visual Servo Control, Part I: Basic Approaches," IEEE RAM 13(4), 2006 [S]
- 집게 카메라 기준 물체 상대 움직임(광류 + 앞뒤 오차 검사).
  - L. Marx, A. A. Palsdottir, L. N. S. Andreasen Struijk, "Frame-Based Slip Detection for an Underactuated Robotic Gripper for Assistance of Users with Disabilities," 2023. https://research.utwente.nl/en/publications/frame-based-slip-detection-for-an-underactuated-robotic-gripper-f [F]
  - Z. Kalal, K. Mikolajczyk, J. Matas, "Forward-Backward Error: Automatic Detection of Tracking Failures," ICPR 2010 [S]
  - Reinold et al., "Combined Physics and Event Camera Simulator for Slip Detection," WACV Workshops 2025. https://arxiv.org/abs/2503.04838 [S]
- 기준 영상 차분(image differencing): "Slip Detection with Combined Tactile and Visual Information," ICRA 2018 (authors not checked), https://arxiv.org/abs/1802.10153 [S]
- 학습 기반 파지 확인(상한 참고용, 우리 제약 밖): Nair, Pakdaman, Ploeger, IROS 2020, https://arxiv.org/abs/2003.10167 [F]; Amargant, Honig, Vincze, 2025, https://arxiv.org/abs/2505.03046 [F]
- 다중 로봇 협동 운반(관련성 낮음): Tuci, Alkilabi, Akanyeti, Frontiers in Robotics and AI 5:59, 2018 [S]; Zhang et al., "Image-Based Visual Servoing for Enhanced Cooperation of Dual-Arm Manipulation," IEEE RA-L 2025, https://arxiv.org/abs/2410.19432 [F]; "Robust Cooperative Manipulation without Force/Torque Measurements," https://arxiv.org/abs/1710.11088 [S], authors not checked

### 기존 참고 자료

- REVIEW_363: [리뷰 문서](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/review-363/REVIEW_363.md),
  [PR 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5966787118)
- D5 로더·조립기: [PR #361](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361) (병합 의존)
- 운동 내용 중복 판정: [PR #365](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/365)의
  `harness/kinematic_overlap.py`(12c1e58c, 바이트 동일 사본), [#219 코멘트 5966536405](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966536405),
  [5966843527](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966843527)
- 기존 자기 기준 유지 검사(재설계 후보): [hold IoU](../../harness/owncam_pair_hold_v3.py), [가장자리 추적](../../harness/own_beam_edge.py)

- [D1–D5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204)
- [높은 자세 후보 PR #361](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361),
  [소스 고정 설계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a9481446d9c7c503bdbc53941d3538cd5ec5ee12/experiments/2026-10-03-v92-loaded-schedule/README.md)
- [현재 v3 학생](../../harness/zone_final_pair_skill.py), [기존 운반·빔 추적](../2026-09-29-pair-v6e-carry/README.md),
  [b-v6h1 범위](../2026-09-30-pair-v6h-carry/README.md)
- [P01](../2026-09-30-e2e-p01-env/README.md), [P03](../2026-09-30-e2e-p03-provider/README.md),
  [물리 인계](../../PHYSICS_HANDOFF.md), [실행 버전 관리](../../docs/execution_versioning.md)
- [재사용 OpenCV 검출기](../2026-09-26-markerless-probe/markerless_probe.py),
  [새 관측 어댑터](../../harness/opencv_wall_observation.py), [새 제어기](../../harness/zone_pair_highpose_runtime.py)
