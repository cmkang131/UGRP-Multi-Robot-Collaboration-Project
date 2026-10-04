# 높은 자세 공동 운반 후보 v96 (첫 등록 v93은 미실행 은퇴)

2026-10-03. D1의 새 학생 제어기 후보다. **MEASURED_SIM 경로는 #361 D5 계약을 통과하고 승인 목록에 오른 v92 실측 보정
이 없으면 실행을 차단한다(승인 목록은 비어 있음).** 별도 DEV_PILOT 경로는 등록된 정확한 sha256 하나만 받는
비확증 기능 시험이며 결과는 항상 FUNCTIONAL_DEV로, 확증·MEASURED_SIM 증거로 승격할 수 없다(아래 2차 대응).
기존 학생의 성공 판정은 승계하지 않는다. 렌더 수집과 P03 인수는 코디네이터가 수행한다.

현재 P03(seed 911, dock 시작 세 체크포인트)은 **기능 확인용 개발 재생(FUNCTIONAL_DEV_REPLAY)**이며
독립 표본 3개나 확증 자료가 아니다. 확증용 시작점은 별도 등록 파일에 고정했다(아래 P2-1).

## v98 통합 (2026-10-04, Claude) — 현재 상태

v98(`zone-final-pair-highpose-v98`, workflow 3.10.0)에 두 가지를 넣었다. v98 실행 기록은 이 통합 전까지 없었다.

- **자기 영상 문턱 재보정(floor_light_v1):** 별도 진단 작업(Track A)이 사용자가 고른 절차로 다시 정한 값을
  그대로 넣었다. 벽 띠 채도 상한 80→140, 벽 경계 단차 최소 10(새 검사), 프레임 대비 폭 15→1.0, 표준편차 3→0.22.
  값 파일은 `configs/calibration/own_image_gates_floor_light_v1.json`(sha256 `e71bbe4d…`)이고 v98 등록 파일과
  제공자 runtime_contract에 해시로 고정했다. 절차·합격 기준은 [보정 절차](../../docs/own_image_gate_calibration.md)에 있다.
  프레임 문턱은 4차 검토 뒤 v98 전용 모듈로 옮겼다(아래 "REVIEW_363 4차 대응"). 공용 `zone_pair_vision.py`는
  main과 바이트가 같고, 프로세스 전역 값(`use_gates`/`_CONTRAST`)은 없앴다.
  주의: 평가 분할에 이 PR의 DEV 탐침(`v96-dev-probe-raise_high-323fe3f9`) 영상이 들어 있다. v98은 DEV·승격 불가이므로
  막지는 않지만, 이 값으로 얻은 결과를 확증 자료로 쓰면 안 된다.
- **파지 시점 집게 시야 → 기록만:** 바닥 파지 자세에서 빔 점 18개 중 0개가 masterpi_v3 카메라 시야에 들어온다는
  진단에 따라(문턱이 아니라 기하 문제), 사용자의 "첫 E2E 집게 감시는 기록만" 결정 아래 코디네이터가 결정했다.
  닫기 전 준비 조건의 `grip_view_m2` 항과 닫은 뒤의 `GRIP_NOT_SEEN`을 v98에서만 기록만 한다(`applied=false`,
  등록 `grip_monitor.grasp_time_view=log_only_v98`). 파지 준비는 자기 명령 이력(닫기 명령 발행)과 고정 상태 채널로
  판단한다. 자기 위치 확인·자기 집게 열림 명령·프레임 유효성·정지 빔 간격·닫기 barrier·시간 초과와
  `GRIP_NOT_CONFIRMED`는 그대로다. 공유 동결 파일(`zone_pair_grasp.py`, `run_m2_pair.py`)은 바꾸지 않았다.
- **복구 동작은 아직 넣지 않았다**(관측기 수정이 폐루프에서 확인된 뒤).

### 독립 검토(Claude Opus) 대응 — 검토 범위 66ff0978..7bce304a + edge + 도착 확인 (2026-10-05)

검토 보고서 `outputs/review-363-delta-20261005/report.md`(sha256 `b972f916…`). 물리 실행 0회 검토다. 처리:

| 항목 | 내용 | 처리 |
|---|---|---|
| P0-1 | ada1d204 DR 영수증은 실제 실행에서 닿을 수 없음(`begin_relocalization`이 고정 영수증을 지워 `decide()`가 늘 기다림) | 제안 diff `64244540…`와 기록 기반 시험 적용, 커밋 메시지·README 서술 정정. 물리로 그 경로를 지난 적은 아직 없음 |
| P1-1 | 도착 확인 대기 창이 판정 때만 지워져, 경계에서 작은 보정 뒤 진짜 도크를 거절 | 자기 명령마다 창 재시작 + 순서 재현 시험·변이 시험 |
| P1-2 | 거절 뒤 재접근은 믿음·σ를 유지(설명은 "새 localizer") | 조정자 결정대로 문서·`record()` 정정. 과신 PF 회복은 별도 설계(PF 일관성 결과와 함께) |
| P1-3 | 영수증 σ는 정확도 증거가 아님 | "σ 예산 영수증"으로 부르고, 영수증마다 평가 전용 NEES 기록(제어 미사용) |
| P1-4 | 번들 `caps` 120이 900 개정에서 빠짐 | `bundle()`에서 덮어쓰기 + 확인 시험, "모두 바꿈" 정정 |
| P2-2 일부 | `HIGH_EDGE_INFORMATIVE`가 런타임 기록에 없음 | 기록에 넣음 |
| P2-7 | `registry()`가 `prereg_version`을 확인하지 않음 | 확인 추가 |

**남은 문제(이 묶음에서 고치지 않음):**
- P2-1 시작 상태 완화 v2의 대각선 경우: 문 기둥(`wall_divider_1/2`, 두께 50 mm) 끝면이 골라지면 두께 방향 가로지름을 못 잡는다.
  제안은 기준점→점 선분이 지나는 면을 쓰거나 대각선이면 v1/거절. relief v2 밖의 guard 변경은 하지 않는다는 제약이 있어 설계
  담당과 정한다. 기록 기반 시험이 r2 하나뿐이다.
- P2-2 나머지: edge를 끈 뒤 yaw 편향 퍼짐이 약 30 % 커진다(추가 약 1.94e-4 rad/s). 다리별 σ 예측(42/59/79 … mm)과 900초
  유도(351–517초)를 edge를 끈 상태로 다시 계산해야 한다.
- P2-3 프레임 시각: `observe(now, rgb)`는 캡처 시각 대신 `now`를 쓴다. `FRAME_SETTLE_S`의 "캡처 주기 하나"는 0.05초인데
  접근 프레임 주기는 0.2초다. 정착 창 0.65초와 대기 창 1.0초의 차이가 0.35초뿐이다. 값 변경은 근거 조사 뒤에 한다.
- P2-4 도착 확인이 `GuardedDriver._arrive`의 고정·gate 확인보다 먼저 돌아 recheck 때 이벤트가 겹칠 수 있다. 실제 드라이버로
  끝까지 도는 시험이 없다(다음 단계 검사 `dock_approach`가 첫 물리 확인).
- P2-5 여유 픽셀 근거 프레임이 곧 시험 자료다. 다른 seed·다른 정지 장면의 hold-out 프레임과 짝 로봇이 빔을 가리는 경우가 없다.
- P2-6 체크포인트에서 σ가 예산을 넘는 진짜 고정이 오면 예산 초과가 아니라 8초 시간 초과로 끝난다(사유 표기만 다름).
- P2-8 2d285ec4 이후 제어기 동작이 여러 번 바뀌었는데 `BUNDLE_ID`·workflow 3.10.0이 그대로다. DEV에서는 SHA·`source_sha256`으로
  구분되지만 확증 코호트 전에 새 버전 번호를 받아야 한다.
- P2-9 351–517초 추정은 아직 없는 내려놓기 재고정을 전제로 한다(재고정 v3/v4는 설계 담당이 다듬는 중, 여기 통합하지 않음).
- **PF 과신의 근본 원인과 예정된 통합(PF 일관성 담당, 2026-10-05 조정자 전달; 자료 `outputs/pf-live-consistency-20261004/ANALYSIS_DETAILS.txt`):**
  비적재 운동 모델(DEV 기본 앞 이득 1.15)이 실제 이동의 72–87 %만 예측하고(실제 약 1.4–1.5), 과정 잡음은 측정한 적 없는 코드
  기본값(이동거리의 약 1 %)이라 편향을 흡수하지 못해, 주행 중 σ가 3–8 mm로 무너지고 입자가 진짜 위치 근처에 없게 된다.
  측정 모델은 정상이다. 담당이 비적재 이득 DEV 보정을 수집한 뒤 측정 이득 + 등록 잡음(diff C), 회복 R1(국소 증강 MCL),
  R2(도착 거절 경로에서만 `expand_belief`, 위 P1-2의 실질 해결)를 이 PR HEAD 기준 통합 diff로 보낸다. 받으면 별도 커밋으로 넣는다.
  **그 뒤에는:** (1) 이전 v98 기록과 결과를 합산하지 않는다(SHA로 구분). (2) 이 README의 오프라인 NEES 표를 다시 만든다.
  (3) σ 문턱(짝 입장 0.05 m, 도착 확인의 허용 오차 경계)을 다시 검증한다. σ가 정직해지면 같은 문턱의 의미가 바뀌기 때문이다.

### 검토 대응 뒤 단계 검사 3개 (`1236c63d`, 2026-10-05)

DEV_PILOT·FUNCTIONAL_DEV, seed 911, `zone_wide_door_geometry_v3`, 보정 `398372ae…`, weld off, floor_light_v1, LLM 호출 0.
SIM 시간 실행이고 시작 부하 평균 13.9–15.1. 원본 `outputs/v98-dev-probe-<단계>-1236c63d`. 위치 오차·NEES는 평가 전용 정답으로
낸 값이고 제어에 들어가지 않았다. `dock_approach`는 이번에 새로 만든 검사로, staged가 아니다(실제 도크, 실제 PF 사전분포).

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 끝 | result / student_record sha256 |
|---|---|---|---|---|---|
| dock_approach | FAILED | 64.0 | 1046/1002 | r1 `APPROACH_ARRIVAL_NOT_CONFIRMED_BY_VIEW`, r2 `PARTNER_ABORT`(접근 중) | `e99d068d…` / `325be4d2…` |
| raise_high_align (staged) | REACHED | 80.8 | 2057/2154 | 두 로봇 HIGH(`high_carry_pose`) | `4b200c10…` / `2048114f…` |
| align_to_carry (staged) | FAILED | 120.2 | 2397/2494 | r2 `HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED`(다리 2 정지) | `77c4d891…` / `366f72cf…` |

- **dock_approach — 도착 화면 확인이 물리에서 진짜 거짓 도착을 막았다.** r1은 11–23초에 달려 목표 앞을 지나쳐 멈췄다(평가 전용
  정답: x 0.41 m 대 목표 0.227 m, 184 mm). PF 담당이 찾은 이득 편향(예측 1.15 대 실제 약 1.4–1.5)과 맞는 지나침이다. 첫 도착은
  화면으로 거절됐고, 재위치추정·둘러보기 뒤 204 mm 자리에서 다시 도착했지만 같은 화면에서 또 거절돼 64초에 깔끔하게 끝났다.
  믿음을 유지하는 재위치추정이라 회복은 안 된다는 독립 검토 P1-2의 예측 그대로다(회복은 PF 통합 diff R2가 맡음).
  **진짜 도크를 받아들이는 경우는 이 실행에서 지나지 않았다.**
- **dock_approach — r2는 예전 12.1초 멈춤을 지났다.** 1f7fb800에서는 제자리 둘러보기 반복으로 멈췄지만, 이번에는 약 1.8 m를 가서
  목표 272 mm 앞에서 목표 방향으로 돌던 중에 r1 중단으로 끝났다. 23–54초에 약 1 m 앞에서 서 있던 구간이 있는데, 그 구간의
  둘러보기 횟수는 이 실행의 기록에 없다(아래 기록 공백).
- **기록 공백(고침):** 짝 접근 드라이버의 사건 기록(둘러보기, 재위치추정, `arrival_view_*` 판정)이 student_record에 저장되지
  않았다. 위 판단은 실패 코드와 평가 전용 정답 궤적에서 낸 것이다. 커밋 `6980eedc`부터 `approach_driver_log`로 남는다.
- **align_to_carry — DR 영수증 경로가 물리에서 처음 작동했다(P0-1 고침 확인).** 다리 1 정지(99.2초)에서 두 로봇 모두 σ 예산
  영수증(σ_xy r1 36.0 mm, r2 38.3 mm)을 받고 계속 갔다. 다리 2 정지(121.5초)에서 r1은 49.1 mm로 예산 안, r2는 54.1 mm로 예산
  50 mm를 넘어 `HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED`로 멈췄다. 1f7fb800은 다리 1 정지에서 8초 시간 초과로 멈췄었다. 여기가 내려놓기
  재고정이 이어받을 자리다(재고정은 아직 통합 안 함).
- **영수증 평가 전용 NEES:** 영수증 4개 모두 xy NEES 0.16–0.63(χ² 99.9 % 경계 13.8 아래), 실제 위치 오차 15–28 mm. 이 실행은 준비된
  검사라 PF 사전 평균을 실제 시작 자세에 두었으므로(주의 2) 낙관적인 값이다. dock 시작 전체 경로에서 다시 재야 한다.

### 네 묶음 뒤 단계 검사 3개, 전체 경로 (`1f7fb800`, 2026-10-04)

재둘러보기 미루기(2d285ec4) → DR 체크포인트 영수증(ada1d204) → 사례 상한 900초(f38e2eba) → 시작 상태 완화 v2(1f7fb800)를 넣은
머리에서 돌렸다. 확인 범위 `carry`(전체 경로, before_door로 줄이지 않음), 지도 `zone_wide_door_geometry_v3`, seed 911,
DEV_PILOT(FUNCTIONAL_DEV, 승격 불가), floor_light_v1, weld OFF, 모델 호출 0. SIM 시간 병렬 실행(부하 평균 시작 15.8–20.5,
끝 11.7–21.2). 원본 `outputs/v98-dev-probe-<단계>-1f7fb800`. 물리 값은 평가 전용이다. 관련 시험(가상 환경): 검토 412,
highpose 227, 나머지 382 통과. CI 37198572206 33개 작업 모두 성공.

| 단계 | 결과 | SIM 초(검사 상한) | 명령 r1/r2 | 끝·멈춘 이유 | af2f7c2a 대비 |
|---|---|---|---|---|---|
| raise_high(도크 시작) | NOT_REACHED | 150.0 (150) | 1939/2403 | 두 로봇 `LOOKED`(10.05초). 완화 v2가 r2의 첫 틱(10.9초) 명령을 받아들였고 r2는 1.2초 동안 동쪽으로 10.7 cm 움직였다(추정). 완화 사건은 r2 12.1초, r1 11.9초에 끝남(guard 정상 판정으로 돌아옴), guard 거부 0. r1 118.5초 `wait_approach` 도착, r2는 148.4초까지 접근 주행 중에 단계 상한 150초에 닿음 | 이전 r2 10.9초 `PAIR_COLLISION_GUARD`. 이번 시작 막힘 풀림. 접근이 느림(상한 150은 이 단계 검사의 값, 사례 상한 900과 별개) |
| raise_high_align | REACHED | 80.85 (900) | 2057/2154 | 두 로봇 HIGH에서 `wait_carry`. 재둘러보기 미루기 r1·r2 각 1회, 제공자 실패 0 | 이전 27.35초 `ALIGN_RELOOK_NO_FIX` 퇴행이 사라짐 |
| align_to_carry | FAILED | 108.75 (900) | 2203/2300 | 파지 62.0, HIGH 64.8, 운반 barrier 86.4초 통과, 첫 다리 운반 86.4–101.4초, 101.9초 `checkpoint_high_stop`(seg 1). r1 `HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`(110.0초), r2 `PARTNER_ABORT` | 이전에는 운반 다리에 닿지 못함. 이번 첫 다리 완료 |

- **체크포인트 σ(정지 직전 마지막 적재 gate 기록, 101.3초):** r1 36.4 mm / 1.15°, r2 38.8 mm / 1.13°(위치 고정 나이 49.2·43.1초).
  둘 다 DR 예산 50 mm / 3° 안인데 영수증(`checkpoint_high_dr_receipt`)도 예산 초과(`..._over_budget`)도 기록되지 않았다.
- **원인(코드 확인):** 체크포인트에서 런타임이 `begin_relocalization`을 부른다(`zone_pair_highpose_runtime.py` 315행, 48c18dd1부터).
  v98 제공자(`HighPoseSource` ← `PairVisionPoseSource` ← `VisionPoseSource`)의 이 함수는 믿음과 σ는 그대로 두고
  `_pf.last_scan_t = None`으로 이전 고정 영수증만 지운다(`vision_pose_source_p03.py` 137–153행). `estimate()`가
  `last_fix_t`를 이 값으로 채우므로(같은 파일 71–75행) 정지 뒤 모든 보고가 `last_fix_t=None`이고, DR diff(a87325c7)의
  `decide()`는 이를 '쓸 보고 없음'으로 보고 계속 기다려 8초 시간 초과가 났다. diff의 시험은 가짜 보고에 `fix_t`를 넣어
  이 재설정을 흉내 내지 않았다. 병합 실수는 아니다.
- **HIGH 재관측은 성공할 수 없다(제어기 자기 기록):** 마지막 고정 시각이 r1 51.95초, r2 58.05초로 둘 다 HIGH 도착(64.8초)
  전이다(제공자 `begin_relocalization` 기록의 `previous_fix_t`, 적재 gate의 고정 나이). HIGH에 적재한 채 45 SIM초 동안 측정 고정이 0번이다.
  DR 모듈의 오프라인 확인(적재 HIGH 프레임 964장에서 벽 열 0개)과 같다. 101.9초 정지는 등록 경로 다리 0의 끝에서 다음 다리가
  남아 있어 내리지 않고 HIGH에서 멈추는 중간 체크포인트다. 옛 규칙은 정지 뒤 새 고정을 요구하므로 8초 시간 초과가 유일한 출구다.
  이것이 σ 재고정(set-down re-fix)이 대신할 계기다.
- **제안(적용 안 함, 조정자 결정 대기):** `fix363/dr_voided_receipt_v98.proposal.diff`(sha256 `64244540…`, 3파일). 초기화된 새 보고의
  `last_fix_t=None`을 '정지 뒤 고정 없음 = DR 보고'로 본다. 예산(50 mm / 3°)은 그대로다. 기록에서 가져온 시험 3개를 넣었다:
  (1) 기록된 `begin_relocalization` 행(r1·r2)이 고정 영수증만 지우고 입자 해시는 같음, (2) 기록된 공분산의 σ(r1 36.7 mm / 1.16°,
  r2 39.1 mm / 1.14°)를 정지 시각+1.2초에 넣으면 'dr', 기록된 끝은 시간 초과, (3) 실제 v98 제공자에서 `apply_scan` →
  `begin_relocalization` → `report`가 σ는 같고 `last_fix_t=None`인 보고를 내며 `decide()`가 그것을 씀. 고정 자료는
  `tests/fixtures/v98_dr_checkpoint_align_to_carry_1f7fb800.json`(원본 `student_record.json` sha256 `a609368e…`). 시험 16개 통과,
  옛 규칙으로 되돌리는 변이에서 4개 실패(기록 시험 2개 포함). 관련 6개 파일 100개 통과(HEAD 내보내기에 적용).

#### 상시 작업 방식 (조정자 결정 2026-10-04, 이 DR 영수증 누락에서)

- **전제 점검(premise audit):** v98이 자세·입력·단계를 바꿀 때마다, 자기 카메라가 무엇을 본다고 가정하는 물려받은 규칙을
  모두 적고 그 가정이 아직 맞는지 확인해 이 README에 남긴다. 예: "정지 뒤 다시 관측"은 벽이 보인다고 가정했지만 HIGH에서는
  벽이 보이지 않는다. 첫 점검표는 아래에 따로 적는다.
- **기록에서 가져온 시험:** 새 규칙의 시험은 손으로 만든 가짜 값만이 아니라 실제 기록된 실행의 값과 제공자 상태 전이
  (`begin_relocalization` → `last_fix_t=None` 등)를 넣어야 한다.
- TensorBoard: `outputs/tensorboard/1004i-v98-dev-probes-1f7fb800`, 보기 키 `v98_dev_probes_1f7fb800_20261004`,
  기준 실행 1004h(af2f7c2a)·1004g(6727751b). 서버 API와 화면 timeSeries 값이 원본과 같음을 확인했다.

#### HIGH '빔 가장자리'는 렌더러 근접 절단면 흔적이다 (타당성 문제, 2026-10-04)

- **판정: 확인됨(CONFIRMED).** 원본 `outputs/v98-znear-live-check-20261004/`(MANIFEST.sha256, 작성자가 전체 해시 확인).
  - align_to_carry@1f7fb800의 HIGH 기록 프레임 72장을 기록된 상태에서 다시 그렸더니 72장 모두 비트 단위로 같았다.
  - 근접 절단면(near-clip plane)만 1.1 cm나 4.4 cm로 바꾸면 v98 경계 맞춤이 0개가 된다.
  - 1227 프레임에서 맞춘 선과 해석적 절단면 궤적의 중앙 잔차는 1.1 px 미만이다.
  - 빔 yaw를 쓸어 보면 기울기 이득은 0.013/rad이다. 트래커가 가정한 값 1.1067의 약 1/85이다.
  - 실행 중 트래커가 r1 +1.16, r2 −1.59 mrad의 가짜 상대 yaw를 넣었다. 같은 구간 실제 상대 yaw 변화는 0.67–0.78 mrad였다(평가 전용).
- **장면 값:** `scene.xml` 4행과 `sim/masterpi_scene_v2.xml` 4행에 `znear=".002"`가 있다. MuJoCo의 znear는 장면 크기(extent 11.1125 m)에 대한
  비율이라 실제 절단면은 22.2 mm다. HIGH에서 카메라는 빔 윗면 약 13 mm 위, 빔 앞 끝보다 23 mm 뒤에 있다.
  - 따로 발견한 것(고치지 않음): `harness/zone_own_perception_v3.py` 76–79행의 `RENDER_NEAR_CLIP_M = .0297`은 extent 14.86 m에서 나온 값이다.
    장면에 따라 달라지는 값이라 이 장면에서는 틀리다.
- **실제 카메라:** `sim/masterpi_camera_profile.py`에는 최소 초점 거리나 근접 거리가 적혀 있지 않다. 장착 위치도 `UNVALIDATED`라고
  적혀 있다. 실제 모듈이 무엇인지부터 저장소 안에서 정해지지 않았다(`sim/masterpi_geometry_v3.py`: Hiwonder HBVCAM-V2101 또는
  icspring 어안). 사양 출처:
  - Hiwonder MasterPi 제품·문서 페이지: "HD wide-angle camera, 480P" 문구만 확인. 초점·화각 표는 없다.
  - 170° 렌즈(GC0308, f 약 1.7 mm, F2.0)의 값은 판매처 검색 요약에서만 봤다(미확인).
  - 최소 초점 "30 cm~"는 50° HBVCAM-V2101 V11 판매 목록의 문구다(alexnld.com). 다른 렌즈라 ugrp1에 적용하면 안 된다.
  - 실제 렌즈의 최소 초점과 피사계 심도는 미확인이다.
  - 추정(측정 아님): 초점이 무한대이고 위 미확인 값을 쓰면, 13 mm 거리에서 흐림이 약 38 px다. 실제 렌즈는 날카로운 경계 대신
    흐린 면을 볼 것이고, 빔의 물리적 끝 모서리는 렌즈 평면보다 뒤에 있다.
- **제안 → 적용(조정자 지시, 별도 커밋):** `HIGH_EDGE_INFORMATIVE = False`
  (`outputs/v98-probe-tools/high_edge_uninformative_v98.diff`, sha256 `998fb664…`).
  - HIGH 경계 관측과 yaw 주입(`vision_pose_source_highpose.py`), `_wait_carry`의 경계 대기(`HIGH_CARRY_EDGE_REFERENCE_TIMEOUT`)를 끈다.
  - `owncam_carry_v6e.py`의 yaw σ 키우기는 그대로라, 경계가 없으면 `pm`(자기 명령 동기) 변형을 쓴다. 추가 σ는 약 1.9e-4 rad/s로,
    한 다리에 몇 mrad이고 3° gate(52 mrad)보다 훨씬 작다.
  - DR 분해 결과(`outputs/dr-error-decomposition-20261004/`): 적재 운반 452 mm의 물리 DR 오차는 앞뒤 약 4.8 mm, 옆 0.7 mm 이하,
    yaw 1 mrad 이하다.
  - 보정 때에도 경계 변형의 yaw 편향(0.0174)은 경계 없는 변형(0.0173)과 같았다.
  - `_lift`의 `high_view` 감시는 기록만 하므로 그대로 둔다.
  - 독립 검토가 필요하다.

#### r2 접근 멈춤 진단과 수정 (raise_high@1f7fb800, 2026-10-04)

- **원인(제어기 재생 + 평가 전용 정답):** 첫 주행(10.9–22.3초) 동안 위치 추정(PF)이 틀린 자세로 수렴했다. 오차는 65→147 mm로
  커졌는데 σ는 30→7 mm로 줄었다(NEES 약 370, 추정 이동 1.67 m 대 실제 1.80 m). 그래서 σ 기준 둘러보기
  (`LOOK_IF_STD_XY_M` 0.05)가 걸리지 않았다. 대신 고정 나이 3초 규칙(`LOOK_IF_NO_FIX_S`, `zone_own_driver.py` 25·91–92행)이
  제자리 둘러보기를 되풀이했다. 9번의 no_fix 둘러보기 가운데 첫 번째를 뺀 8번 중 7번이 직전 둘러보기 뒤 0–0.077 m만
  움직인 상태였다. 둘러보기 13번이 141초 가운데 113초를 썼고, 150초 단계 상한에 먼저 닿았다. 적재 주행은 같은 문제를
  이동 거리 규칙(`travel`)으로 이미 고쳤는데, 비적재 접근에는 그 규칙이 없었다. guard 거부·도크 재둘러보기·제공자 실패·완화 정리는 원인이 아니다.
- **재생 충실도:** 실제 v98 제공자와 실제 `GuardedPairApproach`를 기록된 r2 프레임·명령에 다시 돌렸더니 10.1–151.2초의
  모든 기록 명령과 같았다(151.3초 1건만 단계 상한 뒤). 작성자가 원본 명령의 둘러보기 구간(13개)과 이동 거리를 다시 확인했다.
- **수정(이 PR, v98 전용):** `harness/zone_pair_highpose_approach_looks.py`. 비적재 접근의 no_fix 둘러보기만, 직전 둘러보기 뒤
  등록된 이동 거리(`_travel_look_m()` = 0.35 m, 새 문턱 아님) 이상 움직였을 때 하게 한다. 첫 둘러보기, σ·초기화·문 정지점·진행 확인·
  재위치 잡기·횟수 상한은 그대로다. 시험: 단위 + 기록에서 가져온 시험(r2 no_fix 9번 중 22.4·80.8초만 남고 7번은 건너뜀) + 변이 시험.
- **참고 자료:** ROS AMCL `update_min_d`(이동한 뒤에만 관측 갱신, amcl_node.cpp, 확인); Nav2 BT RecoveryNode/RoundRobin(재시도는
  무언가를 바꿔야 함, 확인); Roy & Thrun, Coastal Navigation, NIPS 2000(확인); ActLoc arXiv 2508.20981, "When to Localize?"
  arXiv 2411.08281(초록만 확인); Fox·Burgard·Thrun 능동 위치 추정, 증강 MCL, move_base 회복, Nav2 progress_checker 기본값(미확인).

#### r1 거짓 도착과 자기 카메라 도착 확인 제안 (항목 A, 적용 안 함)

- **문제:** raise_high@1f7fb800에서 r1은 자기 추정으로 목표 0.030 m 안이라 도착을 선언했지만(118.5초), 실제로는 0.179 m
  떨어져 있었다(평가 전용; σ 3.5–8 mm, NEES 1000–6000). 도착 판단이 PF σ만 믿는다.
- **제안:** `outputs/v98-probe-tools/arrival_confirm_v98.diff`(sha256 `e433db9e…`, 하위 작업자 작성, r2 수정 위에 적용).
  도착 자세(주행 자세 `740,2320,1320,1500`, 측정 카메라 모델 있음)에서 자기 RGB의 빔 윤곽 네 경계가 도착 허용 범위
  (`ARRIVE_TOL_M` 0.03 m, 0.06 rad + 주문서 칸 절반)의 729개 자세를 측정 모델로 투영한 띠 안에 있어야 도착으로 센다.
  아니면 한 번 다시 위치를 잡고 다시 접근하고, 두 번째도 아니면 `APPROACH_ARRIVAL_NOT_CONFIRMED_BY_VIEW`로 끝낸다.
  네 통신 조건에서 같다. PF σ는 쓰지 않는다.
- **기록 판정:** r1 거짓 도착(아래 경계 460행, 띠 상한 407) 거절, r1·r2 실제 도착 받음. 전제 점검: 빔은 렌즈에서 0.316 m
  이상 떨어져 있어 근접 절단면(near-clip)과 무관하다. 측정 모델은 기록 정지 프레임 5장에서 경계를 0.3 px 안으로 맞혔다.
- **한계:** 위쪽 경계 여유가 약 3 px로 얇다(아래 경계 52 px가 주 근거). 경계마다 따로 보는 검사라 허용 범위 안의 오차는
  못 보고 자세를 고치지도 않는다. PF 오차가 계통적이면 다시 잡아도 같을 수 있고, 그때는 두 번째에서 정직하게 중단한다.
  실제 물리 실행에서 거절·재시도 경로는 아직 돌려 보지 않았다.
- **참고 자료:** Chaumette & Hutchinson, Visual servo control Part I, IEEE RAM 2006(검색 확인); Nav2 opennav_docking 준비 자세 +
  감지 + `max_retries`(검색 확인, `isDocked` 세부는 미확인); Nav2 SimpleGoalChecker·SimpleProgressChecker(인자 이름만 확인);
  Thrun·Fox·Burgard·Dellaert, Robust MCL, AI 2001(검색 확인, 원문 미열람).

#### 앞선 REACHED 재확인 (항목 B, 평가 전용 정답)

raise_high_align@1f7fb800과 @6727751b의 파지와 HIGH는 물리적으로 실제였다(하위 작업자 분석, 작성자가 1f7fb800 원본에서
빔 높이·기울기·손가락 접촉·weld를 다시 확인).

- 도크 오차(hover 때) 앞뒤 2.2 mm 이하, 옆 0.4 mm 이하, yaw 0.1° 미만. 잡은 점은 띠 가운데에서 빔 끝 쪽으로 약 5 mm.
- 손가락 4개가 닫기부터 HIGH까지 모든 표본에서 빔에 닿음(1f7fb800 재확인: 63초 뒤 383/383). 빔 높이 115.0 mm, 기울기 0.03° 이하,
  weld off(번들 `weld: off`). 들어 올리는 동안 빔을 따라 약 2 mm 미끄러짐.
- 여유: 옆 4% 이하 사용, 빔 방향 약 17 mm, 세로가 가장 얇다(약 4.0 mm, 보지 않고 내리는 71 mm 열린 고리 하강이 정함).
- align_to_carry는 HIGH까지 raise_high_align과 비트 단위로 같아서 따로 세지 않는다. 표본은 seed 911, 같은 준비로 2개뿐이다.
- **주의:**
  1. REACHED(`high_carry_pose`)는 자기 명령 이력으로 정한다(`physical_success` null). 파지 시야는 모든 닫기 행에서
     `GRIP_VIEW_NOT_BAND`(seen=false)라 제어기의 파지 판단은 영상 근거가 없다. 내려놓은 뒤 다시 잡을 때 중요하다.
  2. 준비된(staged) 검사는 PF 사전 평균을 실제 시작 자세에 둔다(`test_setup_ground_truth: true`). 그래서 과신·거짓 도착 문제를
     드러낼 수 없다. 정렬·파지·들기는 PF 절대 자세를 쓰지 않는다.
  3. 단계 진입 뒤 PF 절대 자세가 표본마다 기록되지 않았다. `loaded_gate_check`에 자기 보고의 `report_x_m`·`report_y_m`·
     `report_yaw_rad`를 기록만 하도록 추가했다(행동 변화 없음, 2026-10-05 커밋). 이 필드가 있는 실행부터 평가에서 정답과 비교할 수 있다.
  4. 잡는 힘은 재지 않았고 매개변수로 어림했다(턱 한계 약 18 N, 마찰 3.4).

#### #371 걸이(hook) 12항 반영 계획

PR 코멘트에 표로 적었다(`issuecomment-5980026688`에 대한 답). 요약: 1·3·4·5·6·8·9·10·11·12는 받는다. 2는 대기 시간을 고쳐서 받는다.
`CHECKPOINT_REOBSERVE_S`는 8초가 아니라 1.2초다. 7은 `continue`/`set_down`만 받고 `wait`는 보류한다. HIGH에서는 고정이 오지 않아
기다려도 σ만 늘기 때문이다. 걸이는 내려놓기 재고정이 이 PR에 들어간 뒤 따로 붙이고, 규칙 조건의 명령 궤적이 바뀌지 않음을 시험한다.

#### 전제 점검표 1차 (1f7fb800, 2026-10-04, 하위 작업자 읽기 전용 점검 + 작성자 확인)

자기 카메라가 무엇을 본다고 가정하는 물려받은 규칙을 v98 경로에서 모았다. 근거는 DEV 보정의 측정 카메라 모델
(적재는 HIGH `896,2035,1894,1500` 하나뿐, 비적재 12개), DR 모듈 문서의 오프라인 확인(적재 HIGH 프레임 964장 벽 열 0개),
그리고 1f7fb800 단계 검사 3개의 제어기 기록이다. A1·A5·r2 고정 간격은 작성자가 원본에서 다시 확인했다. 나머지 수치는
점검 작업자의 값이고, σ 증가 외삽은 추정이다.

| # | 규칙 (파일) | 쓰이는 곳 | 가정 | 판정 | 어긋나면 |
|---|---|---|---|---|---|
| A1 | HIGH 체크포인트 영수증: `last_fix_t`가 없으면 기다림 (`zone_pair_highpose_dr_checkpoint.py`, 런타임 `_wait_carry`) | HIGH 중간 정지 7곳 | 정지 뒤 보고에 고정 시각이 있음 | **깨짐**: `begin_relocalization`이 지움. 101.9초 정지 뒤 8.1초 시간 초과 | 8초 시간 초과가 유일한 출구. 예산 초과 중단도 닿지 않음 |
| A2 | 같은 곳의 새 고정 분기 | 같은 곳 | HIGH에서 벽 고정이 옴 | **깨짐**: 적재 HIGH 고정 0번(마지막 고정 r1 51.95, r2 58.05초, HIGH 64.8초) | 죽은 분기 |
| A3 | DR 예산 50 mm / 3° (넘으면 중단, 내려놓고 다시 고정하는 단계 없음) | 정지 2–7 | 고정이 자주 와서 σ가 예산 안 | **전체 경로에서는 깨짐**: σ 36/39 mm(101.3초), 외삽하면 정지 2–3(문 근처)에서 50 mm 넘음 | `HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED` |
| A4 | 적재 불확실 gate 70/60 mm, 5°/4° | 적재 중 매 틱 | 고정으로 σ가 묶임 | 지금은 맞음(101.3초까지 모두 통과). 외삽하면 다리 4–5에서 넘음 | `POSE_UNCERTAIN` |
| A5 | 진행 감시 `MovedFixMonitor`: 움직인 뒤 첫 고정이 있어야 기준을 잡음 (`zone_final_pair_guards.py` 63–92행) | 적재 운반 | 운반 중 고정이 옴 | **가정 깨짐, 열린 채 실패**: 기준을 못 잡아 정지·멈춤 감지가 운반 내내 꺼짐 | 소리 없음 |
| A6 | 측정 안 된 자세에서 제공자 닫힘 | 모든 단계 | 정착 프레임만 판정 | 맞음(구조): 적재 정착은 HIGH+8초라 HIGH 모델만 씀 | 영구 실패 |
| A7 | HIGH 빔 경계 기준 | `wait_carry` | 빔 아래 경계가 40–300행에 보임 | 맞음: 86.2초 두 로봇 사용 가능 | `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT` |
| A8 | 경계 끊김 시 yaw σ 키우기 | 운반 | 경계가 계속 맞춰짐 | 미검증(다리 0 뒤, 문 동쪽) | gate 중단 |
| A9 | 문 축 정렬 유의성 | 각 다리 시작 | 보고 σ 있음 | 맞음. σ가 커서 보정이 거의 0 → 열린 고리 주행 | 부모 명령으로 |
| A14 | 적재 중 다시 둘러보기 금지(`PAIR_RELOOK_WHILE_GRIPPED`) | 적재 | 해당 없음 | 구조 문제: A1–A3에 회복 길이 없는 이유. 내려놓고 둘러보는 단계가 아직 없음 | – |
| A15 | 매 틱 `INVALID_OWN_IMAGE` | 모든 틱 | 유효·밝은 프레임 | HIGH에서 맞음. 문 동쪽 어두운 바닥·내려놓기는 미검증 | 중단 |
| A16 | 문 통과 sweep guard | 다리 1–2 | σ 작음 | 차체만 계산: σ 0.05에서 여유 0.071 m, 0.07에서 0.051 m. 팔·빔 구는 미계산 | `PAIR_COLLISION_GUARD` |
| A12·A17·A18 | 내리기 감시, 바닥 복귀, 놓은 뒤 6초 후진(적재 gate 그대로) | 마지막 다리, 놓은 뒤 | 명령 이력 / σ ≤ 70 mm | 미검증. A18은 DR 5.75 m 뒤 σ가 70 mm를 넘으면 빔을 놓은 뒤에 `POSE_UNCERTAIN` | 중단 |
| B1–B5 | 닫기 준비(σ ≤ 50 mm, 정보 있는 고정), 내려다보기 확인, `GRIP_NOT_CONFIRMED`, 들기 명령 확인 | 파지·들기 | 비적재 측정 자세에서 고정 | 맞음(세 검사에서 통과). B1의 정보 있는 고정 조건은 `begin_relocalization` 뒤 죽으므로 내려놓은 뒤 다시 들 때 문제 | – |
| C | 정렬 `fix_gap` 재둘러보기(최대 3방향), 접근 고정 간격 | 정렬·접근 | p45/inspect에서 고정이 나옴 | 겨우 맞음: r2는 세 번 모두 마지막 3번째 방향에서야 고정. raise_high r2 고정 간격 약 30초(19.2→48.9, 88.0→119.5초) | `ALIGN_RELOOK_NO_FIX` 등 |

순서(전체 경로에서 먼저 닿는 것): A1·A2(정지 1) → A3(정지 2–3, 문) → A5(운반 내내 꺼짐) → A14(구조). 미검증: 정지 2–7,
문 통과 팔·빔 여유, 옆·축 다리, 마지막 내리기, 놓은 뒤 후진.

### 시작 상태 완화 v2: 빠져나갈 벽 면 기준 깊이 (Track A diff, 조정자 결정 2026-10-04)

- **원인(`af2f7c2a` raise_high r2 10.9초 거부, 오프라인 평가 전용 정답):** 추정 오차 16.7 mm(벽 쪽 13.8 mm, 정직한 σ에서 NEES 0.42)
  때문에 차체 뒤 모서리(-0.15, -0.09)가 50 mm 벽 상자의 가운데 면 바깥쪽으로 옮겨졌다. "가장 가까운 면까지의 깊이"가 바깥 면을
  가리키게 되어, 벽에서 멀어지는 동쪽 이동이 "더 깊어짐"(`inside_pair_deeper`, -13.3 → -22.9 mm)으로 셈해졌다. 실제 차체는 벽
  안쪽 면에서 34.6 mm 떨어져 있었다. 가장 가까운 면 깊이는 벽의 가운데 축(medial axis)에서 끊어진다.
- **변경(diff `relief_exit_face_v98.diff`, sha256 `80daa894…`, +436/−9, 3 파일):** `harness/zone_pair_highpose_start_relief.py`만
  바꾼다. 시작부터 벽 상자 안에 있는 쌍의 깊이를, 시작 표본에서 고정한 "로봇 자기 추정 기준점이 바라보는 벽 면"까지 잰다
  (`DEPTH = 'exit_face'`, 완화 ID `v98_start_state_relief_v2`). 빈 쪽으로 가는 이동은 더 깊어짐으로 세지 않고, 먼 면 쪽 이동은
  더 깊어짐으로 센다(v1이 받아들이던 후진 134개를 v2는 거절). 무진입 규칙(`start_outside_pair_enters`), 바닥값, 묶음 범위
  `SCOPE='group'`(이미 결정), `zone_own_guards`·`zone_pair_geometry`·`zone_final_pair_guards`는 그대로. `DEPTH='nearest_face'`는
  v1 규칙(재생·돌연변이 시험용). 새 시험 `tests/test_highpose_start_exit_face.py`와 CI 목록 한 줄.
- **작성자 결과(오프라인):** 운전 속도(앞 0.05–0.2)에서 v1은 0개, v2는 800개 명령을 받아들인다. 평가 전용 정답으로 실제 차체 최소
  여유 21.2 → 33.6 mm, 관통 없음. 알려진 한계(의도): 벽 쪽 추정 오차가 약 27 mm(약 1.3σ)를 넘으면 여전히 거절한다.
- **guard 규칙의 의미가 바뀌므로** #363 독립 재검토 범위에 들어간다. 그 검토 없이 병합하지 않는다.
- Track A의 관련 시험(522개)과 `test_review_*`(412개)는 `66ff0978`+diff에서 돌았다. 이 head에서 venv로 다시 돌린 결과는 아래 단계
  검사 절에 적는다.
- **참고 자료(Track A 표기 그대로):** [F] MoveIt `fix_start_state_collision`(humble에만 있음, main은 거절만 함); [F] Nav2
  BackUp/DriveOnHeading의 `isCollisionFree` 앞질러 모의(simulate-ahead); [K] Weidemaier 외 arXiv 2604.16512(가운데 축에서 부호 거리
  기울기가 뛰는 문제) — 검색 요약에서만 확인, **미확인**; [S] 시간 연속성으로 쪽을 고르는 방법 — 다시 읽지 않음, **미확인**.

### 사례 시간 상한 300 → 900 SIM초 (사전 등록 개정 v98-cap-3, 사용자 결정 2026-10-04)

- **결정:** 사용자 "시간 상한도 늘리셈". 조정자가 v98 사례 cap을 900 SIM초로 정했다(모든 집행기 같은 값, v98만).
  P03은 한 번도 실행하지 않았다. 개정과 이유를 [결정 기록](fix363/COORDINATOR_DECISION.md) 1a절에 P03 실행 전에 적었다.
- **유도:** σ가 커지면 내려놓고 둘러보는 재고정을 넣은 전체 경로는 351–517초로 추정된다(재고정 1회 하한 약 41.4초). 900초는
  위 추정의 약 1.75배다. 재고정·재둘러보기가 더 생길 여유를 둔 **DEV 상한이지 목표가 아니다.**
- **300을 하드코딩했던 v98 자리(모두 바꿈):** `harness/zone_pair_highpose_contract.py`의 `CASE_CAP_S`(새 `CAP_PREREG_VERSION`);
  이 값을 쓰는 `Runtime`·`StagedRuntime`의 `job_sim_limit_s`와 번들 `timing.case_sim_cap_s`·`executor_job_sim_limit_s`(같은 상수,
  코드 변경 없이 따라감); `zone_pair_highpose_timing.CAP_S`(같은 상수, 설명 고침); 단계 검사 `align_to_carry` cap
  (`zone_pair_highpose_staging.py`, 300 → 900); 등록 파일 `configs/zone_pair_highpose_v98.json`의 `case_cap`(900, `v98-cap-3`,
  사용자 말); 작업 흐름 `configs/simulation_workflows.d/pair_highpose_v98.json` 설명(3×900); `scripts/run_pair_highpose.py` 설명;
  기록 전용 경계 맞춤 행 상한 `FIT_ROWS_MAX` 5000 → 15000(설명이 300초 기준이었고 900초면 잘림). 시험 기대값(dev_pilot,
  timing, zone_final_pair_highpose, final_veto 가짜 실행기).
- **정정(독립 검토 #363 P1-4, 2026-10-05): "모두 바꿈"은 틀렸다.** 부모 번들에서 물려받은 기록 `caps`
  (`zone_final_pair_contract.py` 213행, `per_case_s` 120, `total_including_reset_s` 375)가 v98 `bundle()`의 deepcopy 뒤 그대로
  남아, 번들 기록이 `caps` 120과 `timing.case_sim_cap_s` 900으로 서로 모순됐다. 실행기는 `caps`를 읽지 않아 동작은 900이었다.
  고침: v98 `bundle()`이 `caps.per_case_s = CASE_CAP_S`, `total_including_reset_s = reset + CASE_CAP_S`,
  `cap_prereg_version = v98-cap-3`으로 덮어쓰고, 두 검사(p03·carry)에서 이를 확인하는 시험을 넣었다. 같은 묶음에서
  `registry()`가 등록 파일 `case_cap.prereg_version`도 확인한다(P2-7, 전에는 시험에서만 확인). 결정 기록 1a절의 "모두 바꿈"
  서술은 조정자 기록이라 이 README 정정으로 대신한다.
- **그대로 둔 것:** 은퇴한 v96 등록 파일(바이트 고정, 300), 다른 단계 검사 cap(raise_high·high_hold 150, raise_high_align 150,
  high_hold_staged 60, carry_leg_staged 150), 하한 자동 검사. v98 결과는 계속 DEV이고 SHA로 구분해 기록한다.

### HIGH 중간 체크포인트의 추측 항법 영수증 (DR checkpoint, 다른 작업자 diff, 조정자 결정 2026-10-04)

- **원인(오프라인, 정답은 평가에만):** HIGH에서 쥔 빔이 자기 영상 위쪽을 r1 약 170행, r2 약 175행까지 덮고, 그 아래에는 차체 앞
  0.285–0.42 m 바닥(두 로봇 사이, 벽이 있을 수 없는 자리)만 보인다. 경로 288자세 모두 벽 열 예측 0개, 녹화 HIGH 영상 964장도
  검출 0개였다. 팬을 돌려도 차체가 반대로 돌아 카메라는 세계 기준 0.45°만 돌고, 적재 카메라 모델은 팬 1500 하나뿐이며, 쥔 채
  재관측은 guard가 막는다. 그래서 "멈춘 뒤 새 고정" 조건은 만족될 수 없고 항상 `HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`이었다.
- **변경(diff `high_checkpoint_dr_v98.diff`, sha256 `a87325c7…`, 기준 `af2f7c2a`, 이 트리에 3-way 적용):** 새 모듈
  `harness/zone_pair_highpose_dr_checkpoint.py`의 순수 함수 `decide()`. 기존 최소 정지(1.2초) 뒤, 같은 문턱(σ_xy ≤ 50 mm,
  σ_yaw ≤ 3°, 넓히지 않음) 안의 신선한 자기 보고를 영수증으로 받는다. 멈춘 뒤 진짜 고정이 오면 예전처럼
  `checkpoint_high_reobserved`, 아니면 `checkpoint_high_dr_receipt`로 따로 기록한다(재관측으로 섞지 않음). 문턱을 넘으면
  바로 `HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED`(`checkpoint_high_dr_over_budget`). 보고가 없으면 기존 8초 시간 초과.
  `run_pair_highpose.checkpoint_record`는 두 영수증을 받고 행마다 `receipt`(`fix`/`dr_budget`)를 남긴다.
- **정정(독립 검토 #363 P0-1, 2026-10-05): 위 변경은 커밋 `ada1d204` 당시 실제 실행에서 작동하지 않았다.** 커밋 메시지와 이 절의
  "받는다" 서술은 틀렸다. 정지할 때 런타임이 `begin_relocalization`을 부르고(`zone_pair_highpose_runtime.py` 318행, 검토 당시 317행), 이것이
  `vision_pose_source_p03.py` 148행에서 `last_scan_t = None`으로 바꿔 정지 뒤 모든 보고의 `last_fix_t`가 `None`이 된다.
  `decide()`는 그런 보고에 늘 `'wait'`를 돌려줬고, 출구는 8초 시간 초과뿐이었다. 시험의 가짜 보고가 이 재설정을 흉내 내지
  않아 잡지 못했다. 고침: a54a26ab에서 진단한 제안 diff `fix363/dr_voided_receipt_v98.proposal.diff`(sha256 `64244540…`)와 기록
  기반 시험을 적용했다(아래 커밋). **고치기 전의 어떤 실행도 "DR 영수증 경로 검증"이 아니다.** 고친 뒤에도 물리 실행으로 영수증
  경로를 지난 적은 아직 없다.
- **이름과 해석(독립 검토 P1-3):** 이 영수증은 **σ 예산 영수증**이다. 보고된 σ가 50 mm / 3° 안에 머물렀다는 기록일 뿐, 위치가
  정확했다는 증거가 아니다. 같은 PR에서 PF 과신이 확인됐다(r2 σ 7 mm에 오차 147 mm, r1 σ 3.5–8 mm에 오차 178 mm). 그래서 영수증
  행에 자기 보고 평균·공분산(`x_m`, `y_m`, `yaw_rad`, `cov`, 기록 전용)을 남기고, 실행이 끝난 뒤 평가 전용 채점기
  `scripts/eval_highpose_receipt_nees.py`가 `eval_only/<로봇>/camera_labels.jsonl` 정답과 비교해 영수증마다 xy(2자유도)·자세(3자유도)
  NEES와 χ² 95 %/99.9 % 경계를 `eval_only/dr_receipt_nees.json`에 쓴다. 채점기는 harness가 import하지 않고(AST 시험) 제어에
  돌아가는 길이 없다. 좌표 규약: 1f7fb800 기록에서 r1 자기 보고–정답 19.5 mm(σ 22 mm), yaw 원점은 r1 0·r2 π로 일치했다. **작은
  회전의 yaw 부호는 수치로 확인하지 못했다**(기록에 0·π가 아닌 yaw의 자기 평균이 없음). MuJoCo `xmat`의 표준 오른손 규약
  `atan2(R[1][0], R[0][0])`을 따른다. 참고 자료: Bar-Shalom·Li·Kirubarajan, Estimation with Applications to Tracking and
  Navigation(Wiley 2001) NEES 일관성 검정(5.4절, 절·쪽 **미확인**).
- **조정자 결정(사용자 정정 반영):** 경로는 **배달까지 전체**다(문 앞으로 줄이지 않음). DR 영수증은 예산이 버티는 동안의 영수증이고,
  `HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED`는 설계 중인 "내려놓기 → 열기 → 둘러보기 → 다시 잡기 → 들기" 재고정의 시작점이 된다
  (다른 작업자 diff 예정, 여기서 만들지 않음).
- **작성자 DR 예산 예측(모델 예측, NEES 미검증):** 다리 끝 σ_xy r1 42.4 / 59.1 / 79.3 … 164.6 mm(다리 0/1/2 … 7), r2도 비슷하다.
  50 mm는 GO 뒤 약 29초(다리 1)에 넘는다. 그래서 align_to_carry는 다리 1 체크포인트에서 예산 초과로 멈출 것으로 예상된다.
- **병합 메모:** `adopt_v98_frame_gate` 기록에 `relook_posture_defer`와 `dr_checkpoint`를 둘 다 남겼다. CI 목록도 둘 다.
- **참고 자료(작성자 표기 그대로):** Reid 외, Localization Requirements for Autonomous Vehicles, SAE Int. J. CAV 2(3), 2019 — 확인;
  Roy·Burgard·Fox·Thrun, Coastal Navigation, ICRA 1999 — 확인; Prentice·Roy BRM, IJRR 2009 — 서지 확인; Bry·Roy RRBT, ICRA 2011 —
  서지 확인; Kosuge·Oosumi IROS 1996, Wang·Schwager Force-ANTS IJRR 2016 — 서지 확인; CoLF arXiv 2602.07776 — 요약 확인;
  Roumeliotis·Bekey IEEE TRA 18(5) 2002 — 서지 확인; arXiv 2305.01614 — 제목만 확인(이전 표기 "Stop-and-Sync, Ghosh 2023" 정정);
  Burgard·Fox·Thrun 1997, Bar-Shalom 외 2001, Huang·Mourikis·Roumeliotis — 미확인.

### 팔 자세 전환 중 재둘러보기 미루기 (조정자 결정 2026-10-04, v98 전용)

- **원인(`af2f7c2a` 정렬 퇴행):** r2가 24.9초에 p45 → `inspect`로 팔을 옮기기 시작했고(0.6초 보간), 25.0초 `fix_gap` 재둘러보기가
  공용 `_begin_align_relook`에서 팔 대기열을 지우고 발행된 PWM을 목표로 삼았다. 팔은 첫 보간 한 칸(765/1991/1865)에서 멈췄고,
  측정한 카메라 모델이 없는 자세라 0.3초 뒤(PF `settle_s`) 제공자가 닫혔다.
- **조정자 결정:** 안전 이유가 아닌 조건으로 진행 중인 동작을 끊지 않는다(행동 트리 표준 의미). 재둘러보기·sweep은 팔 전환이
  끝나 목표 자세에 닿고 그 자세에 측정 모델이 있을 때만 시작한다. 다른 원인으로 전환이 끊겨 측정 안 된 자세에 섰으면, 관측 전에
  전환을 끝내거나 마지막 측정 자세로 돌아간다.
- **변경:** 새 v98 모듈 `harness/zone_pair_highpose_posture_defer.py`의 `DeferRelook`을 v98 제어기 클래스 맨 앞에 둔다(공용
  `zone_pair_align.py`는 그대로).
  - 정렬 재둘러보기 요청(이유 무관: `align_entry`, `fix_gap`, `sigma_reserve`, `pose_missing`, 직접 호출)은 팔 보간 사건이 남아
    있으면 대기열에 넣는다(`align_relook_deferred`). 팔이 목표에 닿고 발행 자세의 `camera_key`가 정적 보정의 측정 모델
    집합(제공자 자기 보고의 `load_state` 기준)에 있으면 그때 시작한다(`align_relook_defer_end`).
  - 기다리는 동안: 처음에 차체 hold 한 번(팔이 움직이는 동안 정렬 처리기도 차체를 움직이지 않음), 매 틱 고정 상태 `aligning`과
    짝 중단 확인(재둘러보기 상태와 같음). 상한은 기존 한 번 보기 허용 시간 `MAX_LOOK_S` 8초(새 문턱 없음, `ALIGN_RELOOK_DEFER_TIMEOUT`).
  - `align`에서 팔이 측정 안 된 자세에 멈춰 있으면(다른 원인의 중단) 바로 마지막 측정 자세로 되돌린다(`align_posture_restore`).
    측정 자세를 모르면 `ALIGN_RELOOK_UNMEASURED_POSTURE`. 재둘러보기 상태 안의 팬 대기열(공용 재계획)과 적재 운반 자세는
    이 규칙 밖이다.
  - 입력: 발행 PWM, 자기 팔 대기열, 자기 제공자 보고의 `load_state`, 정적 보정의 측정 모델 키. 실물 상태·짝 위치는 쓰지 않는다.
- **동작 변화(통과 경로):** 정렬 진입(`align_entry`) 재둘러보기는 이제 `search` 자세 대기열(0.8초)이 끝난 뒤 시작한다(이전에는 같은
  틱에 대기열을 지움). 팔이 쉬고 있을 때의 재둘러보기는 이전과 같다.
- **범위 밖(기록):** 명령 guard가 팔 명령을 막아 실행기가 보간을 미룰 때(`arm_wait_at`) 팔이 중간 자세에 서는 경우는 이 규칙으로
  고치지 않는다(대기 상한으로만 끝남). 실행기 sweep 작업(`look_around`)은 짝 작업 밖에서 팔이 쉬는 상태로 시작한다.
- **시험(`tests/test_highpose_relook_posture_defer.py`, 12개):** 실제 `ArmSequence`·공용 `PairAlignRelook`·`relook_reason`·측정
  모델 키로 af2f7c2a r2 시간선을 재생한다. 미루기를 끄면 기록과 같게 25.25초 `UNMEASURED_V3_CAMERA_POSTURE: unloaded:765,1991,1865,1500`.
  켜면 25.0초 미룸 → 25.5초 `inspect` 마지막 보간 → 25.55초 재둘러보기 → 제공자 초기화 유지, 고정 확인 통과, 정렬 계속.
  돌연변이 2개(전환 검사 제거, 되돌리기 제거)는 모두 제공자 실패로 잡힌다. 중단 뒤 되돌리기, 측정 자세 모름, 기다리는 중 짝 중단,
  상한, 정렬 진입, 연결 기록도 확인한다.
- **참고 자료:** BehaviorTree.CPP `Sequence`/`ReactiveSequence` 문서(진행 중 자식은 `Sequence`에서 다음 틱에 이어지고,
  `ReactiveSequence`만 앞 조건으로 끊는다) — 확인(문서); BehaviorTree.CPP 비동기 동작 `halt()`/`onHalted()` 문서(끊긴 동작은
  스스로 빨리 멈춰 정리해야 함) — 확인(문서); Colledanchise·Ögren, Behavior Trees in Robotics and AI, CRC 2018 — 미확인;
  Colledanchise·Ögren, How Behavior Trees Modularize Robustness and Safety in Hybrid Systems, IROS 2014 — 미확인.

### 운반 다리 묶음 뒤 단계 검사 3개 (`af2f7c2a`, 2026-10-04)

거칠게 하기(K 0.2) → 같은 틱 최종 거부 → 도크 둘러보기 8방향·재둘러보기·30초 만남 대기 → carry-align(z 1.96)을 모두
넣은 머리(`af2f7c2a`)에서 조정자가 요청한 3개를 돌렸다. seed 911, before_door, DEV_PILOT(FUNCTIONAL_DEV, 승격 불가),
floor_light_v1, weld OFF, 모델 호출 0. SIM 시간 병렬 실행(부하 평균 시작 9.1–13.3, 끝 7.3–9.1). 원본
`outputs/v98-dev-probe-<단계>-af2f7c2a`. 물리 값은 평가 전용이다. SIM 초는 결과 파일의 검사 시각이고, 사건 시각은 제어기 시계다.

| 단계 | 결과 | SIM 초 | 명령 r1/r2 | 실패·멈춘 이유 | 6727751b 대비 |
|---|---|---|---|---|---|
| raise_high(도크 시작) | FAILED | 9.65 | 263/263 | 두 로봇 둘러보기 `LOOKED`(10.05초); r2 `PAIR_COLLISION_GUARD`(10.9초), r1 `PARTNER_ABORT` | 이전: r2 `LOOKED_POSE_UNCERTAIN`, 입장 못 함, r1 `PAIR_RENDEZVOUS_TIMEOUT`. 이번: 둘 다 둘러보기 통과, r2가 출발하다 guard 거부 |
| raise_high_align | FAILED | 27.35 | 737/646 | r2 `ALIGN_RELOOK_NO_FIX`(28.6초), r1 `PARTNER_ABORT` | 이전 REACHED(83.55초). **퇴행** |
| align_to_carry | FAILED | 27.35 | 737/646 | raise_high_align과 같은 궤적, 정렬 단계 파지 전에 멈춤 | 이전: 운반 barrier 89.1초 통과 뒤 r1 적재 gate. **퇴행**(운반 다리에 닿지 못함) |

- **raise_high:** r1 `LOOKED`(수준 low, σ_xy 30.7 mm), r2 `LOOKED`(medium, 44.5 mm). r2가 mecanum 앞 0.12를 보내려다
  10.9초에 거부됐다. 차체 대 `wall_west` 여유 −85.1 mm는 전부 여유 항(기본 20 + 잔차 15 + 이동 4.8 + σ_xy 42.7 + yaw 2.6 mm)이고
  원 거리 0 mm다(시작부터 벽 여유 띠 안). 시작 상태 완화는 `inside_pair_deeper`로 거절(시작 −13.3 mm → 표본 1에서 −22.9 mm,
  들어간 쌍이 더 깊어짐). 조정자 결정(무진입 규칙)대로 동작했다.
- **정렬 퇴행의 원인(진단, 고치지 않음):** 두 정렬 검사의 r2 기록이 같다. 20.2초 p45 → 24.9초 `inspect`(`band_clipped`)로
  팔 자세를 바꾸는 중 25.0초에 `fix_gap` 재둘러보기(위치 고정 나이 5.89초)가 걸렸다. 재둘러보기 정지가 팔을 중간 자세
  765/1991/1865(+look 1500)에 세웠고, 이 자세는 측정한 카메라 모델이 없어 25.25초에 제공자가
  `UNMEASURED_V3_CAMERA_POSTURE: unloaded:765,1991,1865,1500`으로 닫혔다(fail-closed, 이후 초기화 안 됨). 재둘러보기 고정
  확인은 26.6·27.6·28.6초 모두 거절(`initialized` false)됐고 28.6초에 `ALIGN_RELOOK_NO_FIX`. r1은 같은 `inspect` 전환을
  했지만 재둘러보기가 26.1초에 걸렸고 그때 멈춘 자세는 측정된 자세였다(제공자 실패 없음). 27.7초에 고정을 얻었다. 6727751b에서는 r2 `fix_gap`이 22.4초(p45
  자세 중), `inspect` 진입이 28.2초라 겹치지 않았다. 8방향 둘러보기로 정렬 진입 시각이 바뀌어(10.1초, 이전 7.9초) 겹침이 생겼다.
  측정 위치 수 r2 134(이전 173), r1 79(이전 87). 고칠 방법(자세 전환 중 재둘러보기를 미루기 등)은 조정자 결정 전이라 넣지 않았다.
- **새 사건:** `look_recovery`(도크 재둘러보기) 시도 0회(두 로봇 모두 처음 둘러보기에서 통과). `final_veto` 0회.
  `loaded_gate_check`는 align_to_carry에서 r1 108회·r2 99회, 모두 통과. 10.75초부터(아직 적재 전) 프로필 `loaded`로 기록됐고,
  r2는 실패한 재둘러보기 중 16회가 `uncertain`/high였지만 움직이지 않아 통과로 남았다(기록만).
  예상했던 다음 막힘 `HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`까지는 가지 못했다.
- TensorBoard: `outputs/tensorboard/1004h-v98-dev-probes-af2f7c2a`, 보기 키 `v98_dev_probes_af2f7c2a_20261004`,
  기준 실행 1004g(6727751b). 첫 내보내기는 상위 폴더를 원천으로 줘서 0개였고, 휴지통으로 옮긴 뒤
  (`outputs/cleanup-records/2026-10-04-1004h-tb-export-retry.json`) 실행별 원천으로 다시 만들었다. 서버 API와 화면의 timeSeries
  값이 원본과 같음을 확인했다.

### REVIEW_363 5차 대응 (검토 APPROVE `2745f1fb` 뒤 병합 전 후속, 2026-10-04)

- **상태(먼저 읽기):** 둘러보기의 σ 완화와 시작 상태 완화는 위치 추정 공분산이 일관적이라는 가정에 기대고 있다. 위치 추정
  일관성 수정(PF consistency)이 들어오기 전에는(8.7초 NEES r1 221, r2 741, 한도 13.8) 어떤 v98 실행도 승격할 수 없고 모든
  실행은 `FUNCTIONAL_DEV`로 남는다. 일관성 수정은 이 묶음의 마지막 커밋으로 넣는다(아래 결과 절).
- **시작 상태 완화의 진입 구멍 막기(발견 1, 조정자 규칙):** 묶음(group) 바닥값만으로는 상자 밖·여유 안에서 시작한 점이 깊이
  제한 없이 벽 상자로 들어갈 수 있었다. 검토자 측정: r2 8.7초 틱은 시작 부호 깊이 최악 -14.2 mm에서 휩쓸기 중 -18.9 mm까지
  (상자 밖에서 시작한 쌍이 들어감, 4.7 mm 더 깊음), 같은 r2 자세에서 `forward .2, left .2, turn -.3, 0.15초`는 -25.0 mm(50 mm
  벽의 가운데)까지 들어갔다. r1(`end_neg`)은 0.0 mm로 들어가지 않았다. 틱을 넘어서 쌓이는 한도는 없었다.
  새 규칙: 시작 때 벽 상자까지의 부호 거리(raw signed)가 0 이상인 쌍은 모든 휩쓸기 표본에서 0 이상이어야 한다(새로 들어가는
  것은 허용하지 않음, 여유 없음). 거부 이유는 `start_outside_pair_enters`. 상자 안에서 시작한 쌍의 "더 깊어지지 않기"(1 mm),
  묶음 바닥값, `EPS_M` = 1 mm는 그대로다. 함수 `enters()`로 분리해 돌연변이 시험(규칙을 끄면 검토자 명령이 다시 허용됨)을 둔다.
  - 결과: 검토자 명령은 거부(chassis 0 / `wall_west`, 시작 +9.64 mm → 표본 1에서 -3.9 mm). 기록된 r1 8.7초 첫 명령은 계속
    허용. **기록된 r2 8.7초 첫 명령은 이제 거부된다**(같은 쌍 +9.64 → 표본 2에서 -9.40 mm, 휩쓸기 최깊이 -18.9 mm). 새 진입이므로
    느슨하게 하지 않았다. 검토자 격자(6×5×5×3 명령, 두 자세)에서 완화가 허용한 명령 중 밖에서 시작한 쌍이 들어간 깊이는 이제
    두 자세 모두 0.0 mm다(r1 233개, r2 10개 허용).
- **빠져 있던 blind 중단 경로 시험:** `BLIND_GRIPPER_REOPENED`(`track.command`로 닫힌 집게를 다시 여는 명령),
  `BLIND_DISTANCE_EXCEEDED`(구간의 하강·수평 거리), `BLIND_TRACK_UNCERTAIN`(σ_xy·σ_yaw 한도, 오래된 기준점)을 더했다.
- **표현 정정:** `BLIND_DISTANCE_EXCEEDED`는 설정 점검(configuration sanity check)이다. 구간 거리는 고정 호버·잡기 자세에서
  계산되므로 실행 중에 바뀌지 않는다. 실제 보호는 명령 범위(envelope) 검사와 잡기 자세 정확 일치다.
- **보지 않는 구간과 짝 로봇 밀림:** `ace8b257` 폐루프에서 r1은 11.4초 동안 보지 않았고, 그동안 추적 σ_xy는 17.4 → 24.2 mm였다
  (한도 50 mm). 짝 로봇이 그 사이 빔을 밀어도 이 구간은 알지 못한다(평가 전용으로 그 구간 빔 xy 이동 0.0).
- **보정 문서:** [보정 절차](../../docs/own_image_gate_calibration.md) 5절 한계에 4차 흐림·가림 수치를 옮겼다.
- **시험 결과(`0d7c5eb3` 전, 작업 트리):** `test_review_*` 412 passed, highpose·경계 227 passed, 둘러보기·blind·완화·거부 기록·CI·heldout
  220 passed, `test_highpose_dev_pilot` 37 passed(문서 수정 뒤 재실행). 커밋 `d41465a2`(완화), `0d7c5eb3`(blind 시험·문서).
  이미 있던 실패(이 PR 범위 밖): `test_zone_pair_v6e_yaw::test_tracker_on_recorded_frames_matches_the_recorded_replay_rows`는
  `outputs/pair-stage-probes-ece38792-cal/` 사례 프레임이 10/1 16:40 이전 outputs 정리로 없어져 실패한다. 시험은 `cases.jsonl`이
  없을 때만 건너뛰고 프레임이 없을 때는 건너뛰지 않는다. 어떤 diff와도 무관하며 조정자가 따로 추적한다.

### 운반 다리 문 축 정렬 유의성 규칙 (carry-align, 다른 작업자 diff, 조정자 결정 2026-10-04)

- **원인(`6727751b` align_to_carry):** 운반 다리는 시작도 하지 않았다. `carry`의 처음 6초는 문 축 정렬이고, 두 로봇이 낸 정렬 보정은
  자기 σ의 0.2–0.4배(잡음 수준)였다. 0이 아닌 명령이 하나라도 나가면 yaw 대체 증가율이 0.0174 rad/s(76배)로 바뀌어 약 2.9초 만에
  σ_yaw가 적재 gate 3°에 닿았다. 들어 올린 뒤에는 위치 측정이 하나도 없었다(HIGH 화면에 벽 열 0개).
- **변경(diff `carry_leg_v98.diff`, sha256 `c4fecd53…`):** 새 모듈 `harness/zone_pair_highpose_carry_align.py`.
  `HighController.door_schedule`이 부모 일정을 그대로 받되, 정렬 두 성분은 자기 σ에 견주어 유의할 때만 남긴다(|dy| > 1.96σ_y,
  |e_yaw| > 1.96σ_yaw). 아니면 0으로 둔다. 시간표·0.5초 쉼·운반 다리·`pair_plan`은 부모와 같다. `CommandGuard.check` 뒤에
  `loaded_gate_check`를 매번 기록한다(관찰만). **gate 값(70/60 mm, 3°/2.5°)은 바꾸지 않았다.**
- **조정자 결정:** z = 1.96(표준 양측 95 %, 조정하지 않은 값).
- **예상되는 다음 막힘(코드에서 예측, 관찰 아님):** leg 0 checkpoint에서 8초 안에 σ ≤ 0.05 m인 새 위치를 얻는 것이 HIGH에서는
  불가능해 `HIGH_CHECKPOINT_REOBSERVE_TIMEOUT`으로 끝날 것이다. 조정자가 설계 중이며 여기서 바꾸지 않는다.
- **병합 메모:** `adopt_v98_frame_gate` 기록 줄에서 dock/relook의 `dock_look`과 이 diff의 `carry_align`을 둘 다 남겼다. 원천 폐쇄 시험
  목록에 새 모듈을 더했다.
- **작성자 결과:** 새 시험 17개, 관련 359 passed, `test_review_*` 412 passed.
- **참고 자료(작성자 표기 그대로; 확인(본문)/확인(서지)/미확인):** Kosuge·Oosumi IROS 1996, Kosuge·Sato IROS 1999 — 확인(서지);
  Wang·Schwager Force-ANTS IJRR 2016 — 확인(본문); Tuci 외 Front. Robot. AI 2018 리뷰 — 확인(본문); Culbertson·Schwager ICRA 2018 —
  확인(본문); CoLF arXiv 2602.07776 — 확인(초록); Ghosh 외 arXiv 2305.01614 — 확인(초록); Fox·Burgard·Thrun 1998 — 확인(서지);
  Roy·Thrun 해안 항법 NIPS 2000 — 확인(본문); Prentice·Roy BRM 2009, Bry·Roy RRBT 2011 — 확인(서지); Nav2 AMCL 설정 문서 — 확인(본문);
  Bar-Shalom 외 2001, Huang 외 IJRR 2010, Julier·Uhlmann 1997 — 확인(서지); Reid 외 SAE 2019(alert limit/protection level) — 확인(본문);
  Probabilistic Robotics 5.4절, Borenstein·Feng 1996 — 미확인. 화물이 자기 카메라를 가리는 운반을 다룬 검증된 논문은 찾지 못했다(우리 설계).

### 도크 둘러보기 넓히기와 정해진 횟수의 재둘러보기 (PF 작업자 diff, 조정자 결정 2026-10-04)

- **원인:** 다섯 팬(1500, 1230, 970, 1770, 2030)만으로는 도크 출발 r2의 y 정보가 부족해 σ_y가 54–57 mm로 남는다(거칠게 하기 절).
  제어기는 한 번 둘러본 뒤 `LOOKED_POSE_UNCERTAIN`이어도 다시 보지 않고 입장 요청만 반복했다(`6727751b` raise_high).
- **변경(diff `dock_relook_v98_incremental.diff`, sha256 `07f2eb87…`):**
  - 여는 둘러보기와 재둘러보기의 팬: 1500, 1230, 970, 700, 1770, 2030, 2300, 1500(6.2초 → 8.4초). 배달·접근 sweep은
    `WIDE_LOOK_PANS` 그대로이고 공용 실행기는 바꾸지 않았다.
  - **정해진 횟수의 재둘러보기:** 둘러보기가 끝나고 1초(`RELOOK_GRACE_S`) 뒤에도 `SELF_UNCERTAIN` 거절이 오고, 로봇이 쉬는 중이며
    빈손일 때만. 팬만 움직인다(guard `pans_only`, 차체 후진 제안 없음). 차체 명령이 나오면 작업을 `LOOK_RECOVERY_BASE_MOTION`으로
    끝낸다. 최대 2회, 그다음 거절은 `LOOK_RECOVERY_EXHAUSTED`. 시도마다 `look_recovery`에 전후 σ를 남긴다. Nav2의 정해진 횟수
    회복(RecoveryNode)과 같은 구조다.
  - v98 Team의 짝 만남 대기 5초 → 30초. 단계 탐침 실행기(staged runtime, `Runtime.__init__`을 건너뜀)에도 같은 회복을 설치한다.
- **조정자 결정:** 만남 대기 30초는 v98에 승인. 고정 열거 상태 채널에 `RELOOKING` 상태가 없고 새로 넣으면 공용 프로토콜 변경이라서다.
  **이 대기는 네 통신 조건에서 똑같다.** 기존 둘러보기 시험의 시간 한도 9.5초 → 12.5초(여덟 팬 때문, 측정 12.3초)도 승인.
- **병합 메모(이 작업 트리):** 같은 틱 최종 거부 diff와 이 diff가 각각 `Runtime.step`을 정의했다. 글자로는 충돌 없이 합쳐지지만 두 번째
  `def step`이 첫 번째를 가려 재둘러보기 훅이 꺼진다(두 diff의 시험이 함께 돌면 11개 실패로 드러남). `step` 하나로 합쳤다: 재둘러보기
  정리(`pre_step`) → 부모 수집(팀 poll 포함) → 재둘러보기 팬 전용 거르기(`filter`) → 같은 틱 최종 거부(마지막). 최종 거부 시험의 `Rig`
  고정 장치도 `StagedRuntime`처럼 `adopt_look_recovery`를 부르게 고쳤고, 한 override가 두 단계를 모두 돈다는 회귀 시험을 더했다.
- **작성자 합성 폐루프 결과:** 여덟 팬이면 r2는 여는 둘러보기 뒤 바로 입장(std_xy 42 mm, 오차 3 mm), 재둘러보기 없음. 다섯 팬 + 회복이면
  재둘러보기 1회(std_xy 63 → 46 mm) 뒤 입장.
- **참고 자료(작성자 표기 그대로):** Nav2 `navigate_to_pose_w_replanning_and_recovery.xml`(RecoveryNode 재시도 횟수, Spin·Wait·BackUp)
  — 확인; Fox·Burgard·Thrun 1998 능동 위치 추정 — 미확인; 우리 코드 `zone_pair_status.py`·`zone_pair_executor.py`·`zone_final_pair_runtime.py` — 확인.

### 같은 틱 최종 거부 (same-tick final veto, Codex #375 검토 지적, 2026-10-04)

- **문제(Codex #375 검토, 확인된 누설):** 부모 `Runtime.step`은 로봇을 차례로 불러 명령을 모은다. 같은 틱에서 나중에 처리된 로봇이
  중단(abort)하면, 먼저 처리된 로봇이 이미 낸 이동 명령이 목록에 남아 실행기로 나갔다(그 로봇은 이미 `PARTNER_ABORT`로 끝난 상태).
  `arm_step`에는 중단 전파(poll)가 아예 없었다.
- **변경(diff `final_veto_v98_on_6727751b.diff`, sha256 `bc954868…`, 기준 `6727751b`; 시험한 쌍둥이는 `36d0f34e` 기준
  `final_veto_v98.diff`):** 새 모듈 `harness/zone_pair_highpose_final_veto.py`와 v98 `Runtime`의 `step`·`arm_step` 재정의. 모든 상태를
  전파한 뒤, 끝난(terminal) endpoint의 hold가 아닌 명령을 같은 틱의 hold 하나로 바꾸고, 지운 명령을 `record()['final_veto']`에 남긴다.
  각 endpoint 자신의 `terminal` 표시만 읽는다(짝의 제어기 상태·위치·평가 자료는 읽지 않음).
- **동작 변화:** `arm_step`이 이제 팀을 poll한다(부모는 하지 않았음). 중단이 없는 경로는 바이트 단위로 같다.
- 작성자 결과: 새 시험 24개, 돌연변이 8개 모두 잡힘, 관련 460 passed. 이것만으로는 탐침을 돌리지 않고, 팬/재둘러보기·운반 다리 diff 뒤
  다음 탐침에 함께 확인한다.

### 재표집 뒤 거칠게 하기 (PF roughening, 다른 작업자 diff, 2026-10-04)

- **원인(작성자 오프라인 재생, 정답은 채점에만):** r2의 도크 출발 오차 50–60 mm는 카메라 모델이 아니라 입자 고갈(particle
  deprivation)이다. 도크 사전분포가 세 공개 출발 줄을 가우시안 하나(y 표준편차 2.8 m)로 덮고 입자 2000개로 뽑으며 거칠게
  하기가 없다. 처음 몇 번 재표집 뒤 참 위치 근처에 서로 다른 입자가 거의 남지 않는다. r2 참 자세의 잡음 없는 합성 관측을 넣어도
  둘러보기 뒤 179 mm(동결 가중, σ 2 mm), 78 mm(v2 가중, σ 95 mm)가 남았다. 먼 팬의 yaw–위치 결합은 원인이 아니었다.
- **변경(diff `pf_roughen_v98_incremental.diff`, sha256 `7b75ce4c…`):** `harness/zone_pair_highpose_pf_consistency.py`만 바꾼다.
  재표집 직후 재표집된 입자에 0 평균 가우시안 흔들기를 더한다. 차원마다 σ = K·범위·N^(−1/3), K = 0.2(Gordon·Salmond·Smith
  1993의 제안값, 조정 없음). yaw 범위는 펼친 각도로 잰다. 주입 입자는 건드리지 않는다. 스키마가 v2 → v3이 되고 `roughen_k`가
  더해져 제공자 `runtime_contract`와 `identity_sha256`이 바뀐다(이전 `6727751b` 탐침과 기록으로 구분된다). 흔들기는 `pf.rng`에서
  난수를 더 뽑으므로 같은 seed에서도 이전과 난수 흐름이 달라진다(모듈 설명의 "no extra random draws"는 v2까지의 설명).
- **작성자 결과:** 둘러보기 끝 r2 오차가 50–103 mm에서 7–17 mm로 줄었다. 그러나 다섯 팬만으로는 y 정보가 부족해 σ_y가 54–57 mm
  (완벽한 합성 관측에서도 56 mm)로 남아 **r2는 도크에서 여전히 입장하지 못한다(정직한 거절, 예상됨)**. 입장 0.05 m는 그대로다.
  공개 사항: 검증 분할 결과를 보정 분할보다 먼저 봤으므로 검증 수치는 독립 확증이 아니다. 보정 분할은 회귀 없음 확인에만 썼다.
- **다음(조정자):** PF 작업자의 v98 전용 diff(도크 둘러보기에 팬 2300·700 추가, 입장 거절 때 정해진 횟수의 재둘러보기)가 들어온 뒤에
  단계 검사를 한다. 거칠게 하기만으로는 예상된 거절이므로 탐침을 돌리지 않는다.
- **발견(바꾸지 않음, 공용 파일):** `harness/zone_final_pair_guards.py:19`의 `LOADED_GATE`(yaw 5°/4°)는 쓰이지 않는다. 95·108·109행이
  묶는 세 함수(`SweepRecheck.check`, `PairCommandGuard.before_control`·`check`)는 `GATE_LOADED`를 읽지 않는다. 실제 적재 한도는
  `zone_own_guards.GATE_LOADED`의 yaw 3°/2.5°, σ_xy 70/60 mm다.
- **참고 자료(작성자 표기 그대로):** Gordon·Salmond·Smith, IEE Proc. F 140(2), 1993 거칠게 하기 — 미확인(2차 자료의 식);
  Thrun·Burgard·Fox 2005 4.3절 입자 고갈 — 미확인; Fox·Burgard·Thrun 1998 능동 위치 추정 — 미확인; Nav2 `nav2_bt_navigator`
  회복 행동 트리 — 확인; Censi ICRA 2007 — 미확인; MuJoCo/OpenCV 화소 중심 규약 — 우리 코드에서 확인.

### 5차 묶음 최종 단계 검사 3개 (`6727751b`, 2026-10-04)

seed 911, before_door, DEV_PILOT(FUNCTIONAL_DEV, 승격 불가), floor_light_v1, weld OFF, 모델 호출 0. SIM 시간 병렬 실행(부하 평균
시작 36–64, 끝 60–140). 원본 `outputs/v98-dev-probe-<단계>-6727751b`. 물리 값(빔 높이·이동·접촉)은 평가 전용이다.

| 단계 | 결과 | SIM 초 | 명령 r1/r2 | 실패·멈춘 이유 | 0865a788/d5ca2ec3 대비 |
|---|---|---|---|---|---|
| raise_high(도크 시작) | FAILED | 11.6 | 291/191 | r2 둘러보기 `LOOKED_POSE_UNCERTAIN`(7.8초), 입장 101회 모두 `SELF_UNCERTAIN`; r1 `PAIR_RENDEZVOUS_TIMEOUT`(12.85초) | 이전: 9.0초 r2 guard 거부(`inside_pair_deeper`), 완화 r1×4·r2×3. 이번: r2가 입장하지 못해 움직이지 않음, 거부·완화 0 |
| raise_high_align | REACHED | 83.55 | 1923/2213 | — | 닫기 64.7·들기 65.9·HIGH 84.8초 같음. r2 명령 바이트 동일, r1은 1932 → 1923(위치 추정 변화) |
| align_to_carry | FAILED | 90.95 | 1954/2244 | 운반 barrier 89.1초 통과 뒤 r1 `POSE_UNCERTAIN`(적재 gate, 92.2초), r2 `PARTNER_ABORT` | 이전: `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT`(99.9초). 이번: 경계 기준점 88.9초, 운반 단계 진입 |

- **raise_high 입장(정직한 σ):** r1 둘러보기는 `LOOKED`(σ_xy 13.4 mm). r2 둘러보기는 1.3–7.8초에 한 번 돌고
  `LOOKED_POSE_UNCERTAIN`(수준 medium)으로 끝났다. 그 뒤 r2는 다시 둘러보지 않고 0.05초마다 입장을 요청만 했다(7.85–12.85초,
  101회, 모두 `SELF_UNCERTAIN`). 그동안 r2 σ_xy는 65.2 → 78.5 mm, σ_yaw 1.1 → 1.7°로 커졌다(한도 50 mm). r1은 5초 기다린 뒤
  `PAIR_RENDEZVOUS_TIMEOUT`. PF 작업자의 예상(r2 실제 오차 50–60 mm라 정직한 σ로는 통과 못 함)과 같다. 입장 0.05 m는 그대로다.
- **raise_high_align:** 호버 확인 두 로봇 모두 2프레임(r1 1013→1015, 가로 0.07 mm; r2 1239→1241, 0.43 mm). 닫기 때 보지 않은 시간
  r1 12.7초(이전 11.4초), r2 1.4초. r1 위치 측정 수 87(이전 200), r2 173(이전 167). 손가락 4개 접촉, 빔 높이 0.115 m, 기울기 0.04°.
- **align_to_carry:** HIGH 84.8초 → 경계 기준점 준비 88.9초 → 운반 barrier 89.1초. 경계 맞춤: r1은 9/9 프레임 `shared_ols`(90열),
  r2는 9/9 `consensus`(80열). `_lift` 기록의 `edge_fit`도 r1 `shared_ols`, r2 `consensus`. 맞춘 행 y320은 r1 170.54–170.58,
  r2 175.05–175.06 px로 위·아래 띠 뒤집힘 없음. 운반 단계에서 두 로봇은 같은 작은 mecanum 명령 30회(앞 거의 0, 옆 -4.8/-7.4 mm/s)를
  보냈고 92.2초에 r1 적재 gate(σ_xy > 70 mm 또는 yaw > 3°)가 풀려 멈췄다. 이때 r1의 σ 값은 기록에 없다. 빔은 0.7 mm 움직였고
  운반 완료 아님(평가 전용).
- TensorBoard: `outputs/tensorboard/1004g-v98-dev-probes-6727751b`(collection sha256 `39e51f74…`), 보기 키
  `v98_dev_probes_6727751b_20261004`, 기준 실행 0865a788 raise_high·raise_high_align, d5ca2ec3 align_to_carry.
  첫 내보내기는 `hparam_metrics`가 내보내지 않는 태그를 적어 실패했고, 휴지통으로 옮긴 뒤(`outputs/cleanup-records/2026-10-04-1004g-tb-export-retry.json`) 다시 만들었다.
- 시험(커밋 전): `test_review_*` 412 passed, highpose·경계 227 passed, 경계 맞춤·PF·둘러보기·blind·완화·CI·heldout 280 passed.

### 위치 추정 일관성 수정 (PF consistency, 다른 작업자 diff, 조정자 결정 2026-10-04)

- **원인(작성자 오프라인 재생, 정답은 채점에만 사용):** 멈춘 채 같은 팔·팬 자세로 본 프레임이 매번 새 측정으로 곱해졌다(적용된
  스캔의 91–97 %가 반복, 뷰당 평균 11, 최대 144). 한 프레임 안의 열도 서로 상관이 있다(유효 열 5–8개). 입자 고갈은 아니었다.
- **변경(diff `pf_consistency_v98.diff`, sha256 `7b334429…`):** 새 모듈 `harness/zone_pair_highpose_pf_consistency.py`와 제공자
  3줄. 한 장면(view)은 한 번 센다: 같은 뷰의 k번째 스캔은 설계 효과 c_k − c_{k−1}(c_K = K/(1+(K−1)ρ), ρ = 0.5)만큼만 반영한다.
  뷰는 자기 입력으로만 정한다(서보 펄스·적재 상태 변화, 0이 아닌 자기 구동 명령, 자기 명령 속도 적분 2 cm/0.035 rad).
  프레임 가중치의 유효 열 수는 4(기존 8)다. `pf.measurement`와 informative 판정 식은 그대로이고, 난수를 더 쓰지 않는다.
- **조정자 결정:** v98에 그대로 넣고 자기 커밋으로 둔다. 제공자 `runtime_contract`에 `pf_consistency` 기록(설정·해시)이 더해진다.
  번들 원천 해시(source closure)도 새 모듈을 포함한다. 입장 기준 0.05 m는 **느슨하게 하지 않는다**.
- **보류 구간 결과(작성자, 오프라인):** NEES(2자유도, 평균) rh-3358 r2 1064 → 0.99, r1 235 → 60, rh-7623 r1 169 → 67,
  r2 2482 → 0.33(잘못된 모드, σ는 정직해졌지만 위치는 더 나빠짐). r1에 남은 과신은 팬 끝 새 뷰 한 장의 yaw–위치 결합으로 보이며
  가중치 조절로는 고칠 수 없다(작성자 열린 결정 3).
- **예상 영향:** r2의 실제 오차는 50–60 mm라서 정직한 σ(약 100 mm)로는 도크 시작에서 입장(σ ≤ 5 cm)을 통과하지 못할 가능성이
  크다. 이전 통과는 거짓 확신에 기댄 것이었다. 왜 r2 오차가 그렇게 큰지는 PF 작업자가 조사 중이다.
- **참고 자료(작성자 표기 그대로):** Bar-Shalom·Li·Kirubarajan 2001 NEES/ANEES — 미확인; Thrun·Burgard·Fox 2005 6장 빔 독립 가정 —
  미확인, UW CSE571 센서 모델 강의 자료 — 확인; Nav2 `amcl_node.cpp` `shouldUpdateFilter`(update_min_d 0.25 m, update_min_a
  0.2 rad)·`likelihood_field_model.cpp` — 확인; Kish 1965 설계 효과 — 미확인; Gordon·Salmond·Smith 1993, Fox 2003 KLD,
  증강 MCL — 미확인; Anderson & Anderson 1999 공분산 부풀리기 — 미확인; Loc-NeRF arXiv 2209.09050 — 확인.

### HIGH 운반 빔 경계 강건 맞춤 (Track A diff, 조정자 결정 2026-10-04)

- **문제(`d5ca2ec3` align_to_carry):** HIGH에서 두 로봇 모두 90열 중 85(r1)/80(r2)열이 아래 빔 띠의 경계(행 169–176)를 봤지만,
  오른쪽 끝 5/10열이 위 띠의 경계(행 79–80)를 읽어 공용 `edge_line`의 한 번 최소제곱이 기울었다(기울기 -0.078/-0.157).
  4 px 띠 안에 25/13열만 남아 모든 HIGH 프레임이 거부됐고 `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT`이 났다.
- **변경(diff `robust_edge_fit_v98.diff`, sha256 `21decf28…`):** 새 모듈 `harness/zone_pair_highpose_edge.py`. 공용
  `edge_line`을 먼저 돌리고, 그 결과를 그대로 쓴다. 공용 함수가 None일 때만 같은 열 표본에 결정론적 최대 합의(consensus) 직선
  (두 열을 지나는 모든 가설, LO-RANSAC식 재맞춤)을 맞춘다. 받아들이는 규칙(4 px 띠, 60 % 열, RMS)은 공용 모듈 값 그대로다.
  공용 `own_beam_edge.py`는 바꾸지 않았다. `_lift` 기록에 `edge_fit`(`shared_ols`/`consensus`)을 남긴다. 시험 50개+고정 자료
  216 KB(`tests/fixtures/highpose_edge/`, 파일당 1 MiB 미만).
- **조정자 결정:**
  1. `cv2.fitLine`(Huber 등 M-추정)이 아니라 합의 직선을 쓴다. 이유는 붕괴점(breakdown point)이다. Track A의 오프라인 사다리에서
     Huber는 90열 중 한쪽 이상치 26열에서 무너지지만 받아들이는 규칙은 36열까지 견딘다. 공용 우선(shared-first)은 유지한다.
  2. 기울기→yaw 비율은 1.1067을 유지한다. 아래 경계로 다시 맞추면 1.085(-2 %)지만, 상대 yaw 범위가 최대 0.116°뿐이라 식별이 약하다
     (신뢰구간 0.63–1.49). **알려진 한계로 기록**한다. ±2–3° 흔들어 재는 측정은 미루며 DEV에는 막는 요인이 아니다.
  3. 경계 뒤집힘 위험: 붙잡고 있는 동안 이기는 경계가 위·아래 띠 사이에서 바뀌면 3–4 mrad 계단이 생긴다. 새 논리는 넣지 않고
     기록만 더했다. `_lift` 기록에 `edge_y320_px`(320열에서의 직선 행)를, 추적기 `stats`(`student_record.json`의
     `carry_yaw_v6e.<로봇>.beam_edge`)에 맞춘 프레임마다 `fit_rows` [t, fit, y320, 기울기, 열 수]와 `fit_shared_ols`/`fit_consensus`
     개수를 남긴다. 뒤집힘은 y320이 약 90 px 뛰는 것으로 보인다. 답은 바뀌지 않는다(시험: 기록 경로와 동결 경로가 같은 답).
- **작성자 결과:** 로봇마다 HIGH 프레임 303/303 맞춤, 재생에서 추적기 기준점 88.35초. `test_review_*` 412 passed, 관련 429 passed
  (실패 1개는 이미 있던 ece38792 프레임 시험).

### REVIEW_363 4차 대응 (검토 BLOCK 5970668877, 2026-10-04)

- **공용 동결 파일 복구:** `harness/zone_pair_vision.py`를 origin/main 바이트 그대로 되돌렸다(sha256 `cce72504…`).
  7623c4dc는 이 파일에 프로세스 전역 대비 문턱을 넣어 이전 번들의 고정 바이트(#352/#355 검사 21개)를 깨뜨렸다.
- **v98 전용 프레임 문턱:** `harness/zone_pair_highpose_frame_gate.py`. 얼린 규칙(신선도·JPEG·크기·어안 테두리·두 어두움
  규칙)은 그대로 옮기고 대비 폭·표준편차 두 값만 등록 파일 값(1.0, 0.22)을 쓴다. `FrameGate(15, 3)`이 기록 프레임 68개와
  합성 프레임에서 얼린 판정과 모두 같고, 등록 값과의 차이는 대비 때문에 거부되던 신선한 프레임에서만 난다(시험).
  적용 위치는 v98 클래스의 얼린 메서드 코드를 그대로 쓰되 개인 builtins로 묶어 그 안의
  `from harness.zone_pair_vision import ...`/`from harness.zone_pair_admission import readiness_snapshot`만 v98 값으로
  답한다(`PairExecution.step/arm_step`, `CommandGuard.preclose_check`, `PairCommandGuard.observe_standoff`,
  `PairGraspRelook._grasp`, `HighController._wait_close`, `ZoneOwnExecutor._ack/pair_readiness`). 모듈 전역·import 훅·
  `sys.modules`는 바꾸지 않는다. 입장 검사는 원래대로 `valid_frame`(ob 아님)을 쓴다. 등록 `frame_gate.profile`
  (`zone_pair_frame_gate_floor_light_v1_v98`)과 번들 소스 해시에 고정했다. 모든 MRO를 훑어 얼린 문턱 참조가 남지 않았는지,
  얼린 문턱을 호출하면 터지는 장치 아래에서 v98 경로가 동작하는지 시험한다. `run_pair_stage_probes.py`의 `image_valid_off`
  같은 모듈 패치는 v98에 닿지 않는다(이전 번들용 도구).
- **이름:** `PROVIDER_ID`와 PF source 접두사를 `…_v98`로 바꿨다. v96 DEV 기록(`v96-dev-probe-*-323fe3f9`)은 git SHA
  `323fe3f9`에서만 재현된다.
- **시험 준비 정답 표시:** 정적 사전분포 평균(실제 생성 위치)과 HIGH 진입의 `gripped`/`lifted` 주장·HIGH 기준 영상은
  교사 준비에서 온 정답이다. 코드(`TEST_SETUP_GT`), 제어기 기록(`stage_probe_entry`), `stage_probe_staging.json`에
  `test_setup_ground_truth: true`와 "정적 DEV 단계 검사 전용, E2E·코호트·사례 결과에 쓰지 않음"을 남긴다. align 진입은
  평소 둘러보기와 짝 입장(실제 자기 카메라 추정) 뒤 첫 제어기 틱에서만 일어나며 입장 문턱은 그대로다.
- **파지 시점 범위 정정:** 기록만으로 바뀐 것은 `grip_view_m2` 두 항(닫기 전 준비 항, 닫은 뒤 `GRIP_NOT_SEEN`)뿐이다.
  프레임 유효성 검사, `preclose_check`(정지 빔 간격, `BEAM_UNCERTAIN`), `GRIP_NOT_CONFIRMED`는 계속 동작한다. 바닥 자세에서
  `beam_track.estimate`가 무엇을 내는지는 아직 확인하지 않았다(닫기에 도달한 검사가 없다).
- **알려진 한계(추가 조정 없음):** 검토자의 오프라인 측정에서 프레임 수준 문턱(대비 폭·표준편차)은 옛 값·새 값 모두
  흐림(σ3/8/16), 가로 움직임 흐림 31/81 px, 세로 41 px, 열 폭 30/50 % 가림을 100 % 통과시켰다. 이 문턱은 흐림·가림
  탐지기가 아니며 원래도 아니었다. 30 % 이상 검은 가림을 거르는 것은 바뀌지 않은 어두움 비율 규칙이다. 열 수준에서는 새
  단계 검사가 옛 규칙보다 오답이 적지만(σ3 96 대 794, σ8 409 대 2734, 가로 31 px 245 대 902, 가로 81 px 781 대 1096),
  강한 흐림에서는 새 문턱도 오답이 많다: σ8에서 남은 592열 중 409열 오답, 가로 81 px 19 %, 흐림 없음 0.4 %.
  옛 규칙과 공유하는 남은 위험으로 기록만 하고 문턱은 더 바꾸지 않는다.

### 보지 않는 마지막 접근 (blind final approach, v98 초안, 2026-10-04)

- **문제:** 바닥 잡기 자세에서는 자기 손목 카메라에 빔이 한 픽셀도 보이지 않아(아래 `3358372e` 결과) 닫기 전 빔 추정이
  구조적으로 `None`이다. 카메라 위치·시야는 바꾸지 않는다.
- **방법(보고 나서 움직이기, look-then-move):** 열린 하강을 호버 자세(서보 807/1897/2187, 공구 높이 95 mm)에서 멈추고
  0.3초 안정화한다. 그 자리에서 바꾸지 않은 `preclose_check`와 새 가로 검사(빔 띠 가로 중심이 고정 잡기 선에서 3 mm 이내)를
  한다. 통과하면 정지 빔 추적에 "보지 않는 구간"을 열고, 고정 경로(7단계 × 0.12초, 수직 71 mm, 차체 이동 없음)와 0.3초
  안정화를 큐에 넣는다. 잡기 자세에서는 구간이 유지되는 동안만 확인 때의 빔 가설을 그대로 쓴다. 구간은 다음 중 하나면
  닫힌다: 시간 22.14초 초과, 내려간 거리 0.075 m 초과·수평 0.002 m 초과, 차체 이동, 시선(pan) 변경, 경로 밖 팔 명령,
  집게 다시 열기, 모르는 명령 종류, 구간 변경, 추적 불확실성(동결 한도 30초·50 mm·3°) 초과. 거리 한도는 설정 점검이다(구간
  거리는 고정 자세에서 계산됨). 실제 보호는 명령 범위 검사와 잡기 자세 정확 일치다. 입력은 자기 RGB·자기 명령
  이력·측정된 호버 카메라 모델뿐이다. 새 모듈 `harness/zone_pair_highpose_blind_close.py`, 등록 키
  `blind_final_approach.profile = zone_pair_blind_final_approach_v98`, 번들 `timing.blind_final_approach`.
  설계 원문은 [blind_final_approach_design_ko.md](blind_final_approach_design_ko.md), 조사 전문은
  [blind_final_approach_survey.md](blind_final_approach_survey.md), 오프라인 재생 스크립트는 `blind_final_approach_replay/`.
- **조정자 결정(2026-10-04)과 적용:**
  1. 번들 ID는 초안 v98을 유지하고 DEV 기록은 SHA로 구분한다. 검토자가 동결 전에 새 번호를 요구하면 모든 브랜치를 확인해 다음 빈 번호를 쓴다.
  2. 보지 않는 구간 22.14초를 유지한다(알려진 한계 아래).
  3. 호버 가로 검사(3 mm)를 바로 적용한다. 측정값은 0.06 mm지만 표본이 하나다.
  4. 호버 확인은 정렬 단계(`aligned_streak >= 2`)처럼 **연속 2개의 서로 다른 자기 프레임**이 통과해야 한다. 실패 프레임이 오면 0으로
     되돌리고, 같은 프레임을 다시 보면 세지 않는다. 구간은 마지막 통과 프레임에서 열린다. 재시도 상한 1.0초(`HOVER_CONFIRM_MAX_S`)는
     그대로이며, 상한을 넘긴 실패 프레임에서 `PREGRASP_HOVER_*`로 멈춘다(`HOVER_CONFIRM_FRAMES = 2`, `limits()`에 기록).
  5. 모르는 명령 종류는 구간을 닫는다(fail-closed, 유지).
  6. 실패 분류: `PREGRASP_HOVER_*` 4개 → `HOVER_NOT_CONFIRMED`, `PREGRASP_BLIND_*` 10개 → `BLIND_WINDOW_CLOSED`.
     공용 `harness/pair_stage_probe.py`의 분류표는 이전 검토 기록(`tests/fixtures/review_355_legacy.json`)이 바이트 해시로 고정하고
     있어 바꾸지 않았다. 대신 v98 실행기 `scripts/run_pair_highpose.py`에 `failure_cause()`를 두어 공용 표를 그대로 쓰고 새
     이름만 더한다. 결과 `controller_outcome.<로봇>.failure_cause`에 남는다(평가 쪽 표시, 원인 증명이 아님).
  7. 더 낮은 하강 자세의 카메라 보정은 미룬다.
  8. 시간 하한 표(`zone_pair_highpose_timing._grasp_s`)는 호버 정지(0.3초와 검사 틱)를 넣지 않았다. 여전히 하한이지만 약 0.4초
     작다. 300초 상한에는 영향이 없다. 표는 바꾸지 않았다(알려진 차이로 기록).
  9. `scripts/run_ci_tests.py`에 v98 시험 목록이 있어 `tests/test_highpose_blind_close.py`를 더했다.
  10. `raise_high_align` 폐루프 재실행: 두 로봇 모두 닫고 HIGH까지 갔다(아래 절).
- **알려진 한계:**
  - 짝 로봇 밀림: 보지 않는 22.14초 동안 짝 로봇이 늦게 닿아 빔을 밀어도 이 구간은 알아채지 못한다. 짧은 상한(예: 3초)과
    호버 재확인은 대안으로만 남겼다(결정 2). `ace8b257`에서 r1은 11.4초 보지 않았고 추적 σ_xy는 17.4 → 24.2 mm(한도 50 mm)였다.
  - 호버 가로 검사 허용치(3 mm)는 정렬 허용치를 그대로 쓴 것이고, 측정 근거는 한 표본(0.06 mm)이다.
  - 닫은 뒤 자기 집게 감시는 여전히 기록만이다(`grip_loss_after_close: log-only`).

### 이어가기 단계 검사 `align_to_carry` (`d5ca2ec3`, 2026-10-04)

조정자 결정(2026-10-04): HIGH staged 진입(`high_hold_staged`, `carry_leg_staged`)은 **보류(parked)**한다. 코드는 두되 실행하지 않고
집계하지 않는다(`staging.PARKED`). 적재 자세에서 둘러보기를 넣으면 시험 준비 정답이 더 늘어나기 때문이다. 대신 raise_high_align과
같은 진입에서 HIGH 유지와 운반 구간까지 이어가는 `align_to_carry`를 더했다. 상한은 SIM 300초이고, 두 로봇이 `done` 상태에 이르면
끝난다(실행기 `terminal_state`). 운반은 제어기가 실제로 도달한 상태에서 시작하며 하네스가 넣은 적재 상태가 없다.

조건은 앞과 같다(seed 911, before_door, DEV_PILOT, floor_light_v1, weld OFF, 모델 호출 0, 조정 PID 60799, 부하 8.2 → 20.3).

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 실패 | 닫기/들기/HIGH | 운반 | 배달(평가 전용) |
|---|---|---|---|---|---|---|---|
| align_to_carry | FAILED | 98.65 | 1933/2214 | r1 `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT` 99.9초, r2 `PARTNER_ABORT` | 64.7초 / 65.9초 / 84.8초 | 운반 barrier 미준비, 이동 없음 | 아니오(빔 0.115 m에 들린 채 제자리, 손가락 4개 접촉) |

- 닫기·들기·HIGH까지는 raise_high_align과 같다(호버 2프레임, 닫기 때 보지 않은 시간 r1 11.4초·r2 1.4초, 완화·거부 0).
- **새 막힘:** `wait_carry`에서 두 로봇 모두 15초 동안 `barrier_report carry ready=false, reason="HIGH edge reference pending"`만
  보냈다. 제공자의 `beam_edge.available()`이 한 번도 참이 되지 않았다(`harness/zone_pair_highpose_runtime.py` 276–282).
- **원인(자기 RGB만으로 오프라인 재생):** `harness/own_beam_edge.edge_line()`이 HIGH 자세의 모든 프레임(r1·r2 각 302장)에서
  None을 냈다. 빔 띠의 아래 경계는 r1 90열 중 85열(r2 80열)이 한 직선 위(169–171행)에 있다. 그런데 오른쪽 끝 5열(r2 10열)은
  첫 띠 구간이 79–80행에서 끝난다. 함수는 모든 열로 최소제곱 직선을 한 번 맞춘 뒤 4 px 안의 열만 남긴다. 이 이상치 열이 직선을
  기울여(기울기 −0.078) 남는 열이 25개뿐이고, 필요한 54개에 못 미친다. 남는 85열로 다시 맞추면 잔차 RMS가 0.5 px이다.
  즉 영상에는 경계가 분명하지만, 한 번만 하는 최소제곱 정리가 이상치에 약해서 실패한다.
- `own_beam_edge.py`는 v6e 공용 모듈이라 고치지 않았다. 처방과 적용 범위는 조정자 결정 사항이다. 표준 방법은 이상치에 강한 직선
  맞춤(RANSAC, 중앙값 기반 맞춤 등)이다. 또 기울기→상대 yaw 비율(`slope_to_yaw_ratio`)은 v6e 낮은 운반 자세의 기록에서 정한
  값이므로, HIGH 자세에 그대로 맞는지도 따로 확인해야 한다.
- TensorBoard: `outputs/tensorboard/1004f-v98-dev-probe-align-to-carry-d5ca2ec3`(기준선 `1004d…/raise_high_align-ace`), 보기 설정 키
  `v98_dev_probe_align_to_carry_d5ca2ec3_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-d5ca2ec3`
  (로컬 보관, 원격 백업 아님).
- raise_high(처음부터)는 위치 추정 과신 수정이 들어온 뒤 다시 돌린다(조정자 결정, guard는 그대로).

### 시작 상태 완화 뒤 단계 검사 4개 (`0865a788`, 2026-10-04)

둘러보기 수정 + 보지 않는 마지막 접근 + 시작 상태 완화(+ 거부 기록)를 모두 넣은 코드다. 조건은 앞과 같다(seed 911, before_door,
DEV_PILOT `398372ae…82f5`, floor_light_v1, weld OFF, 모델 호출 0, SIM 슬롯 4개 동시, 조정 PID 50163). 이 실행 동안 다른 작업 때문에
호스트 부하가 매우 높았다(시작 18.9–22.0, 끝 21.4–264). SIM 시간 실험이라 판정에는 쓰지 않고 기록만 한다.

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 실패 | 닫기/들기 | 완화·거부 |
|---|---|---|---|---|---|---|---|
| raise_high(처음부터) | FAILED | 7.75 | 203/202 | 59/33 | r2 `PAIR_COLLISION_GUARD` 9.0초, r1 `PARTNER_ABORT` | 없음 | 완화 r1 4회·r2 3회(8.7–8.9초), 거부 r2 1회 |
| raise_high_align | **REACHED** | 83.55 | 1932/2213 | 200/167 | 없음 | 닫기 64.7초, 들기 65.9초, HIGH 84.8초 | 없음(0/0) |
| high_hold_staged (보류, 집계 안 함) | NOT_REACHED | 60.0 | 0/0 | 0/0 | 없음(입장 실패) | 없음 | 없음 |
| carry_leg_staged (보류, 집계 안 함) | NOT_REACHED | 150.0 | 0/0 | 0/0 | 없음(입장 실패) | 없음 | 없음 |

- **raise_high:** 시작 상태 완화가 8.7초의 첫 접근 명령을 두 로봇 모두에 허용했다(작성자 반사실 재생과 같다). 0.3초 뒤 9.0초에
  r2의 전진 명령(forward 0.119, 0.15초)이 다시 막혔다. 완화 거부 이유는 `inside_pair_deeper`이다. r2의 추정 뒤 왼쪽 차체 모서리
  (몸체 좌표 −0.15, −0.09 m)가 `wall_west` 벽 상자 안(부호 거리 −0.17 mm)에서 시작하고, 첫 표본에서 −9.7 mm로 더 깊어진다.
  묶음 바닥값 규칙(−43.0 → −43.0 mm)은 통과했지만, "벽 상자 안에서 시작한 점은 더 깊어지면 안 된다"는 점마다 규칙에 걸렸다.
  평가 전용으로 본 9.0초의 실제 r2 위치는 (−0.8924, −0.8497), 추정은 (−0.9269, −0.8778)이다. 오차는 약 44 mm, 추정 std_xy는
  2.6 mm(약 17σ)다. 이 실패는 **알려진 위치 추정 과신 문제 때문**으로 본다. 지시대로 고치지 않았다(다른 작업자 담당).
- **raise_high_align:** `ace8b257`과 결과가 같다. 두 로봇의 자기 명령 기록(`commands.jsonl`)이 바이트까지 같다(r1 `859b2a60…`,
  r2 `18864d91…`). 이 경로에서는 완화와 거부가 한 번도 일어나지 않았다. 호버 확인 2프레임(r1 1039→1041, r2 1239→1241),
  닫기 때 보지 않은 시간 r1 11.4초·r2 1.4초, 평가 전용으로 손가락 4개 접촉·빔 높이 0.115 m·기울기 0.03°.
- **high_hold_staged / carry_leg_staged:** 앞(`b37c9270`)과 같이 짝 입장에서 막혔다. `gate_ok` 거짓 1200회/3000회, std_xy
  0.21–0.22 m, 측정 갱신 0, 명령 0. HIGH 진입은 둘러보기를 건너뛰어 측정이 없으므로 구조적으로 막힌다. 진입 방법은 조정자 결정
  대기다. 시작 빔 높이 0.115 m는 시험 준비(정답 표시 `TEST_SETUP_GT`)이며 결과가 아니다.
- 두 로봇의 위치 추정기 `localizer_stats.updates`가 0인 것도 그대로다(별도 진단 중).
- TensorBoard: `outputs/tensorboard/1004e-v98-dev-probes-0865a788`(기준선 `1004c…/raise_high-335`, `1004d…/raise_high_align-ace`),
  보기 설정 키 `v98_dev_probes_0865a788_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-0865a788`
  (로컬 보관, 원격 백업 아님).

### 짝 guard 거부 기록과 시작 상태 완화 (v98 전용, 다른 작업자 diff, 조정자 결정 2026-10-04)

- **원인(작성자 오프라인 재생, `3358372e` raise_high 8.7초):** 두 로봇이 정해진 도킹 위치에서 시작한다. 그 자리에서 이미
  일부 몸체 점·벽 쌍이 guard 여유(기본 20 + 잔차 15 + 패드 5 mm + σ 항) 안쪽에 있다. `PairSweepGuard.motion_clear`는
  움직이지 않은 첫 표본도 검사하므로, 벽에서 멀어지는 명령까지 모든 명령을 거부했다. r1은 뒤 왼쪽 차체 모서리와
  `wall_west` 사이가 -55.3 mm였고 명령은 -55 → -28 mm로 멀어지는 쪽이었다(실제 간격 34 mm, 평가 전용, 접촉 없음).
- **변경(diff `guard_veto_log_start_relief_v98.diff`, sha256 `448c92cd…`):**
  - `harness/zone_pair_highpose_guardlog.py`: 모든 짝 guard 거부를 `pair_collision_guard_veto`로 기록한다(막힌 명령,
    guard가 쓴 자기 위치·공분산, 실패한 항). 관찰만 하고 판정은 동결 guard와 비트 단위로 같다.
  - `harness/zone_pair_highpose_start_relief.py`: 동결 guard가 "막힘"이라고 한 뒤, 그리고 시작 표본에서 이미 음수인 쌍이 있을
    때만 실행한다. 시작 때 여유 밖이던 쌍은 지금처럼 모든 표본에서 0 이상이어야 한다. 시작 때 여유 안쪽이던 쌍은 바닥값보다
    나빠지면 안 된다. 벽 상자 안에서 시작한 점은 더 깊어지면 안 된다. 벽 상자 밖에서 시작한 점은 상자에 들어가면 안 된다(5차
    대응에서 추가, `start_outside_pair_enters`). 허용하면 `pair_collision_guard_start_relief`를 남긴다.
    팔·전이 검사, 여유, 패드, 이득은 그대로다. 입력은 자기 위치 추정·자기 발행 명령·정적 지도뿐이다.
- **조정자 결정:** `SCOPE='group'`(모듈 기본값), 여유 `EPS_M` = 1 mm. 바닥값은 그 (부위, 벽) 묶음의 시작 최악값 − 1 mm다.
  **글자 그대로의 "점마다 나빠지지 않기"(`'pair'`)보다 약하다.** r2는 추정 뒤 모서리가 50 mm 벽의 반대쪽 면 너머 9.6–14 mm에서
  시작한다. 이것은 위치 추정이 약 48 mm 틀려서 생긴 물리적으로 불가능한 상태다. 점마다 규칙을 쓰면 7쌍이 최대 14.2 mm
  나빠져 r2가 멈춘다. 묶음 규칙에서는 최악값이 -42.6 → -42.7 mm(0.09 mm, 회전 지렛대 항)라서 1 mm 여유 안에서 허용된다.
- **알려진 문제(여기서 고치지 않음, 다른 작업자 담당):** 위치 추정이 지나치게 자신 있다. 8.7초에 NEES(2자유도)가 r2 741,
  r1 221이다. 99.9 % 카이제곱 한도 13.8보다 훨씬 크다(평가 전용 비교). 자신 있게 틀린 추정이 벽 쪽으로 39 mm 틀리면 어떤
  여유도 소용없으므로, 이 완화는 추정을 믿지도 고치지도 않는다.
- 작성자 결과(`ace8b257`+diff): 관련 시험 323 passed, `test_review_*` 412 passed. 반사실 재생에서 8.7초의 첫 접근 명령 두 개가 모두
  허용됐다. 이 작업 트리에서 다시 돌린 결과(`0865a788`): `test_review_*` 412 passed, highpose·경계 225 passed, 둘러보기·blind·
  완화·거부 기록·CI·heldout 211 passed. 새 시험 두 파일은 CI 목록에 넣었다. 커밋 `0865a788`.

### 보지 않는 마지막 접근 폐루프 단계 검사 (`ace8b257`, 2026-10-04)

조건은 앞과 같다(seed 911, before_door, DEV_PILOT `398372ae…82f5`, floor_light_v1, weld OFF, SIM 슬롯
`sim-claude-v98-raise-high-align`, 조정 PID 41085, 시작 부하 11.8, 끝 부하 13.5). 모델 호출 0.

| 검사 | 상태 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 실패 |
|---|---|---|---|---|---|
| raise_high_align | **REACHED** (두 로봇 `high_carry_pose` 84.8초) | 83.55 | 1932/2213 | 200/167 | 없음 |

| 로봇 | 호버 확인(프레임, 통과/연속) | 띠 가로 중심 | 경로 큐 | 닫기 barrier | 닫기 때 보지 않은 시간 | 최대 |
|---|---|---|---|---|---|---|
| r1 | 1039 통과(1) → 1041 통과(2) | 0.05 mm | 53.3초 | 64.7초 | 11.4초 | 11.9초(65.2초, 닫기 램프 끝) |
| r2 | 1239 통과(1) → 1241 통과(2) | 0.43 mm | 63.3초 | 64.7초 | 1.4초 | 1.9초 |

- **닫기가 일어났다.** 두 로봇 모두 호버에서 연속 2프레임 확인(허용 3 mm) 뒤 고정 7단계로 내려갔다. 잡기 자세의
  `preclose_beam_guard`는 `evidence=blind_after_hover_confirmation`으로 통과했고 거부(`PREGRASP_HOVER_*`/`PREGRASP_BLIND_*`)는
  0건이다. 이어서 lift(65.9초) → HIGH 상승(67.5초) → `high_carry_pose`(84.8초, 자기 명령 이력으로 판단)까지 갔다.
- **r1은 짝을 11.4초 동안 기다리며 보지 않았다.** r1이 먼저 내려갔고(53.3초) r2는 10초 늦게 도착했다. 상한 22.14초 안이다.
  이 구간이 결정 2의 "짝 밀림" 위험이 실제로 생기는 시간이다. 이번 실행에서는 평가 전용 기록으로 빔 수평 이동이 0.0 mm였다.
- **평가 전용 확인(제어에 쓰지 않음, `eval_only/`):** 84.8초에 손가락 4개(r1·r2 좌우)가 모두 빔에 닿아 있고, 빔 높이는
  0.115 m(시작 0.0005 m), 기울기 0.03°다. 로봇끼리 접촉 0건, `active_weld_ids` 항상 빈 목록(weld OFF).
  이것은 단계 검사 결과이며 사례 결과나 E2E 성공이 아니다.
- **같이 본 것:** 두 로봇의 위치 추정기 `localizer_stats.updates`가 0이다(`scan_updates` r1 319, r2 489). 이 값의 의미는
  별도 진단 작업이 보고 있다. 여기서는 판단하지 않는다.
- TensorBoard: `outputs/tensorboard/1004d-v98-dev-probes-ace8b257`(기준선 `1004c…/raise_high_align-335`),
  보기 설정 키 `v98_dev_probes_ace8b257_20261004`(고정 카드 8개 링크 포함). raw는
  `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-ace8b257`(로컬 보관, 원격 백업 아님).

### 둘러보기 수정 뒤 폐루프 단계 검사 (`3358372e`, 2026-10-04)

조건은 앞과 같다(seed 911, before_door, DEV_PILOT, floor_light_v1, weld OFF, SIM 슬롯 따로, 조정 PID 24124, 시작 부하 24.6/23.0).

| 검사 | 상태 | 도달한 곳 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 실패 |
|---|---|---|---|---|---|---|
| raise_high(접근 포함) | FAILED | 두 로봇의 둘러보기가 7.8초에 함께 끝났다(LOOKED, r1 std 0.0072 m). 합류를 통과해 7.85초에 짝 작업을 시작했고 approach에 들어갔다. | 7.45 | 200/199 | 53/27 | r1 `PAIR_COLLISION_GUARD` 8.7초(approach 0.85초째), r2 `PARTNER_ABORT` |
| raise_high_align | FAILED | 평소 둘러보기(7.8초, LOOKED)와 입장을 마쳤다. 그 뒤 자기 접근 → align → standoff(빔 9968점 관측) → 열린 하강까지 가서 54.1초에 `wait_close`에 **도달**했다. | 52.85 | 1443/1261 | 200/147 | r1 `preclose_beam_guard` `BEAM_UNCERTAIN` → `PREGRASP_NOT_READY`, r2 `PARTNER_ABORT` |

- **둘러보기 수정은 폐루프에서 확인했다.** 7623c4dc에서는 r2가 끝나지 않아 `PAIR_RENDEZVOUS_TIMEOUT`이 났다. 이번에는 두 로봇이 같은 시각(7.8초)에 끝났고 합류를 통과했다. 5초 합류 시계는 바꾸지 않았다.
- **raise_high의 새 막힘:** approach 0.85초째에 명령 guard가 `PAIR_COLLISION_GUARD`로 멈췄다. 이 guard는 막은 명령을 기록하지 않아(`zone_pair_guards.py` 772–789) 팔·시선 계획과 이동 간격 중 어느 쪽인지 raw로는 가릴 수 없다. 이 검사 경로가 실행된 것은 v98에서 처음이다(앞 실행은 합류 전에 끝났다). 새 둘러보기 guard는 둘러보기 틱 밖에서는 부모와 같이 계산한다(hint 없음 → `PairArmGuard`). 원인 진단은 아직 하지 않았다.
- **raise_high_align의 닫기 거부(조정자 지시 4번 조건에 해당, 여기서 멈춤):** 닫기 시점의 r1 상태를 자기 RGB와 자기 명령 이력만으로 오프라인 재생했다(`replay_preclose_3358372e.py`, 검사 출력의 frames·commands).
  - 빔 추적의 불확실성은 한도 안이었다: std 0.019 m(한도 0.05), 0.024 rad(한도 0.052), 나이 2.3초(한도 30).
  - 바닥 파지 자세(서보 3/4/5 = 1269/2052/2494)의 자기 영상(frame 1057)에는 빔 색 점이 **0개**였다(필요 60). 영상 전체가 바닥이고, `close_grip_view`도 빔 비율 0이었다.
  - 그래서 `beam_track.estimate`는 "보이는 조각 일치 검사"에서 None을 냈다. 직전 standoff 영상(frame 1011)에서는 9911점이 보였다.
  - 즉 `preclose_check`는 바닥 파지 자세에서 구조적으로 통과할 수 없다(카메라 기하, 문턱 문제 아님). 지시대로 고치지 않았다. 조사와 v98 전용 설계("보일 때 확인 후 자기 명령으로 마지막 접근")는 조정자가 다른 작업자에게 맡겼다. `PAIR_COLLISION_GUARD` 진단(막은 명령 기록 포함)은 Track A가 맡는다.
- 닫기에 도달하지 못해 P03 3×300은 시작하지 않았다. TensorBoard: `outputs/tensorboard/1004c-v98-dev-probes-3358372e`(기준선 7623c4dc raise_high), 보기 설정 키 `v98_dev_probes_3358372e_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-3358372e`(로컬 보관)이다.

### r2 늦은 둘러보기 수정 (Track A, v98 전용, 조정자 승인 2026-10-04)

- **원인(7623c4dc raise_high):** r2의 시작 둘러보기는 1.95–8.2초 동안 팔을 움직이지 못했다. 공용 팔 guard가 위치 불확실성을 방향 없이 `std_xy = √(trace Σ)`(2.0초에 0.47 m, 거의 모두 y축)로 계산해 `wall_west`와의 간격에서 뺐기 때문이다. 동쪽을 보는 r2는 y를 관측하지 못하지만, 이 벽의 법선은 x이고 그 방향 σ는 0.048 m였다. 기다리는 틱마다 `hold`가 두 번 나가는 문제도 있었다(`[hold] + [hold]`).
- **수정:** `harness/zone_pair_highpose_lookaround.py`.
  - `LookAroundGuard(PairArmGuard)`는 팔 간격의 위치 항을 장애물 법선 방향 σ로 계산한다: `min(std_xy, √2·√(nᵀΣn))`. Σ는 그 틱의 자기 추정 공분산이다.
  - 둘러보기 틱의 첫 `hold` 중복을 없앤다.
  - 공용 `zone_own_executor.py`·`zone_own_guards.py`·`zone_final_pair_guards.py`는 바꾸지 않았다. `adopt_v98_frame_gate`가 행위자 클래스와 guard 클래스를 바꾸고, `record()['own_image_gates']['look_around']`에 남긴다.
- **guard 의미 변경(명시):** 둥근 추정과 법선 방향으로 긴 추정은 공용 guard와 비트 단위로 같게 계산한다. 법선을 가로지르는 방향으로 긴 타원일 때만 여유를 덜 뺀다. 공용 guard보다 더 빼는 경우는 없다. yaw 항, 기본 여유, residual, 0.15 m 상한, 차체 간격, 후진 이동 검사는 그대로다. 조정자는 이것을 표준 기회 제약 여유로 보고 승인했다(사용자 9/29 guard 완화 허용). 정답 위치는 쓰지 않는다.
- **오프라인 확인(Track A, 폐루프 아님):** 기록된 r1/r2 추정을 지연 제공자로 재생했다.
  - 공용 guard는 r1을 2.00–2.05초(2틱), r2를 1.95–8.20초(126틱) 동안 막았다.
  - 새 guard는 1.95–9.0초의 모든 틱을 통과시켰다. 최소 여유 포함 간격은 r1 28 mm, r2 20 mm이다.
- 5초 합류 시계는 바꾸지 않았다. 폐루프 확인은 `raise_high` 재실행으로 한다.

### v98 DEV 단계 검사 재실행 (`b37c9270`, 2026-10-04)

조건은 앞과 같다(seed 911, before_door, DEV_PILOT, floor_light_v1, weld OFF, SIM 슬롯 따로, 조정 PID 16310, 시작 부하 18.6/15.1). 둘러보기 합류에 기대지 않는 두 HIGH 검사만 돌렸다. `raise_high`·`raise_high_align`은 Track A의 r2 둘러보기 수정을 기다린다.

| 검사 | 상태 | 멈춘 곳·이유 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 입장 거부 r1/r2 |
|---|---|---|---|---|---|---|
| high_hold_staged | NOT_REACHED | 제공자 실패가 사라졌다(`own_history` 18행, 두 로봇 `loaded_by_rule=true`). 그러나 짝 입장이 끝까지 `gate_ok=false`다(std_xy 0.21–0.22 > 0.05). | 60.0 | 0/0 | 0/0 | 1200/1200 |
| carry_leg_staged | NOT_REACHED | 위와 같다. | 150.0 | 0/0 | 0/0 | 3000/3000 |

- **적재 상태 수정은 동작했다.** 7623c4dc의 `UNMEASURED_V3_CAMERA_POSTURE unloaded` 실패가 없어졌다.
- **HIGH 진입도 바닥 진입과 같은 이유로 입장에서 구조적으로 막힌다.** 시작 사전분포 std 0.15 m를 쓰고, 빔을 든 팔을 움직이지 않으려고 둘러보기를 생략한다. HIGH 자세에서는 벽이 보이지 않아 측정 갱신이 0이다. 입장 문턱(std ≤ 0.05)을 완화하지 않는 한 넘을 수 없다. 어떻게 진입할지는 조정자가 정한다. 예를 들어 HIGH 진입도 폐기하고 `raise_high_align` 연속 실행으로 대신할 수 있다. 문턱은 바꾸지 않았다.
- 닫기에 도달한 검사가 없어 `preclose_beam_guard`·`beam_track.estimate` 기록은 아직 없다.
- TensorBoard: `outputs/tensorboard/1004b-v98-dev-probes-b37c9270`(2개 실행, 기준선은 같은 검사의 7623c4dc 실행), 보기 설정 키 `v98_dev_probes_b37c9270_20261004`. raw는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-b37c9270`(로컬 보관, 원격 백업 아님)이다.

### v98 DEV 단계 검사 결과 (`7623c4dc`, 2026-10-04)

조건은 seed 911, `zone_wide_door_geometry_v3` before_door, DEV_PILOT, floor_light_v1, weld OFF이며 SIM 슬롯을 따로 썼다(조정 PID 94817). 다섯 개 모두 단계에 도달하지 못했다. 단계 검사 결과는 사례 결과가 아니다.

| 검사 | 상태 | 멈춘 곳·이유 | SIM초 | 명령 r1/r2 | 측정 갱신 r1/r2 | 집게 기록 |
|---|---|---|---|---|---|---|
| raise_high(접근 포함) | FAILED | r1이 8.3초에 둘러보기를 끝냈다(LOOKED, std 0.0066 m). r2의 둘러보기는 1.95–8초에 정지 명령만 두 배 속도로 내다가 약 6초 늦게 패닝을 시작했고 끝나지 않았다. r1은 13.35초에 `PAIR_RENDEZVOUS_TIMEOUT`으로 끝났다. | 12.1 | 303/417 | **139/23** (323fe3f9: 0/4) | 파지 전이라 없음 |
| raise_high_staged | NOT_REACHED | 짝 작업 입장에서 `gate_ok=false`가 50 ms마다 1800번 나왔다. 시작 사전분포 std 0.15 > 0.05이고, 둘러보기를 생략했으며, 바닥 자세에서 측정이 0이다. 명령 0. | 90.0 | 0/0 | 0/0 | 없음 |
| raise_high_closed | NOT_REACHED | 위와 같다. | 90.0 | 0/0 | 0/0 | 없음 |
| high_hold_staged | NOT_REACHED | 33.5초에 제공자가 `UNMEASURED_V3_CAMERA_POSTURE unloaded:896,2035,1894,1500`로 실패했다. 정적 준비가 적재 상태를 넣지 않았다(시험 준비 누락). 입장 `gate_ok=false`도 함께 나왔다. | 60.0 | 0/0 | 0/0 | 없음 |
| carry_leg_staged | NOT_REACHED | 위와 같다. | 150.0 | 0/0 | 0/0 | 없음 |

- **관측기 수정의 폐루프 효과:** 접근을 포함한 실행에서 r1 측정 갱신이 0에서 139로 늘었고, 두 로봇 모두 둘러보기 결과가 LOOKED_POSE_UNCERTAIN에서 LOOKED로 바뀌었다. 새 막힘은 r2 둘러보기의 늦은 시작이다(Track A 영역이라 손대지 않았다).
- **정적 진입 검사는 구조적으로 막혀 있다.** 시작 사전분포 정의, 둘러보기 생략, 입장 완화 금지를 함께 지키면 입장 문턱(std ≤ 0.05)을 넘을 수 없다. HIGH 진입은 적재 상태도 넣어야 한다. 어느 쪽으로 바꿀지는 조정자가 정한다.
- 차단 실패가 있어 P03 3×300은 시작하지 않았다. TensorBoard는 `outputs/tensorboard/1004-v98-dev-probes`(5개 실행, 기준선 v96 raise_high)에 넣었다. raw 위치는 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-<검사>-7623c4dc`(로컬 보관, 원격 백업 아님)이고 파생 뷰는 `outputs/v98-dev-probe-tbviews-1004/gen_views.py`다.

### 단계 검사 설계 수정 (조정자 결정 2026-10-04, 시험 준비만)

- **바닥 진입 2개 폐기(`DROPPED`):** `raise_high_staged`와 `raise_high_closed`는 시작 사전분포 std 0.15 m, 둘러보기 생략, 바닥 자세 측정 0 때문에 짝 입장(std ≤ 0.05)을 끝까지 넘지 못했다(`7623c4dc`, 각 1800번 거부). 입장을 완화하지 않고 진입점을 버렸다.
- **새 `raise_high_align`:** 계획의 전위치(pre-station, 파지 위치에서 0.30 m 뒤)에 세우고, 평소의 시작 둘러보기를 그대로 둔다. 진입 상태는 실제 접근이 도착할 때 들어가는 `wait_approach`다. 자기 PF 추정으로 `at_prestation`을 기록하고 사전 동작은 없다. 그다음은 제어기 자신의 접근 barrier → align → 열린 하강 → 닫기 barrier → 파지 → 낮은 lift → HIGH로 이어진다. 둘러보기가 끝나는 시점을 맞춰야 하므로 Track A의 r2 수정 뒤에 돌린다.
- **HIGH 진입의 적재 상태:** 정적 사전 동작을 제어기의 자기 명령 이력으로 차례대로 넘긴다. 먼저 닫기 전 자세를 `initial_servo_command`로 넣고, 이어서 닫기·들기 행을 넣는다. 그러면 LoadState가 실제 닫기 뒤와 같은 규칙(파지 높이에서 집게 닫기 명령)으로 `loaded`를 켠다. 이전 방식(최종 펄스 한 줄)은 `loaded=false`로 남아 HIGH 자세에서 `UNMEASURED_V3_CAMERA_POSTURE unloaded`가 났다. 규칙으로 계산한 값을 `staging.own_history`에 기록한다. HIGH 진입은 빔을 든 팔을 움직이지 않도록 시작 둘러보기를 계속 생략하고, 이를 기록한다.

## REVIEW_363 2차 대응 (2026-10-03, Claude) — 이력

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

### HIGH 운반 빔 경계 맞춤 (v98, 처방 제안의 출처)

- Fischler, Bolles, "Random Sample Consensus: A Paradigm for Model Fitting with Applications to Image Analysis and Automated
  Cartography", CACM 24(6), 1981. 이상치가 섞인 자료에서 직선 등 모델을 맞추는 RANSAC. **미확인**(이번 작업에서 원문을 다시 읽지 않음).
- OpenCV `cv::fitLine`(M-estimator 거리 `DIST_HUBER` 등). **미확인**(문서를 이번 작업에서 다시 읽지 않음).
- Chum, Matas, Kittler, "Locally Optimized RANSAC", DAGM 2003. 합의 집합으로 다시 맞추는 국소 최적화. **미확인**(Track A 모듈
  설명의 출처, 이번 작업에서 원문을 다시 읽지 않음).
- 적용: Track A diff(`21decf28…`)가 RANSAC을 모든 두 열 가설로 결정론적으로 돌리고 LO 재맞춤을 쓴다. `cv2.fitLine` M-추정은
  붕괴점(한쪽 이상치 26/90열) 때문에 쓰지 않았다(조정자 결정 1).

### 짝 guard 시작 상태 완화 (v98, 작성자 모듈 설명의 출처)

- Bar-Shalom, Li, Kirubarajan, *Estimation with Applications to Tracking and Navigation*, Wiley 2001. NEES/ANEES 일관성 검사:
  NEES가 카이제곱 한도보다 크면 필터가 지나치게 자신 있다는 뜻이다. 공분산 부풀리기·과정 잡음 추가·적응 잡음 추정이 표준 처방이다.
  **미확인**(작성자 인용, 이 작업에서 본문을 다시 읽지 않음).
- Thrun, Burgard, Fox, *Probabilistic Robotics*, MIT Press 2005. 입자 필터의 무작위 입자 주입(위치 추정 복구). **미확인**(같은 이유).
- 우리 적용: 위 두 출처는 남은 문제(과신)의 처방 근거이고 이번 diff에는 넣지 않았다. 시작 상태 완화 규칙 자체(동결 거부 뒤
  "나빠지지 않으면 허용")는 출처 없이 조정자가 고른 선택지 2다(사용자 9/29 "guard 완화 허용").

### 보지 않는 마지막 접근 (v98, 설계 작업자 조사, 출처 표기 그대로)

"확인"은 해당 절이나 코드를 직접 읽었다는 뜻이고 "미확인"은 초록이나 2차 언급만 봤다는 뜻이다. 조사 전문은
[blind_final_approach_survey.md](blind_final_approach_survey.md).

- Hutchinson, Hager, Corke, "A tutorial on visual servo control", IEEE T-RA 12(5), 1996. 확인. 보고 나서 움직이기와 끝점 개루프·폐루프 구분.
- Chaumette, Hutchinson, "Visual servo control Part I/II", IEEE RAM 2006/2007. 확인. 시야 유지 기법.
- Kragic, Christensen, "Survey on visual servoing for manipulation", KTH/CVAP 2002. 확인. "정렬 뒤 수직으로 몇 cm 내려가 잡기" 사례.
- Folio, Cadenat, "A sensor-based controller able to treat total image loss", IROS 2008 (hal-00603686). 확인. 마지막 측정과 자기 속도 명령으로 특징 예측.
- Morrison, Corke, Leitner, "Closing the loop for robotic grasping" (GG-CNN), RSS 2018, arXiv 1804.05172. 확인(IJRR 2020판 미확인). 코드 github.com/dougsm/ggcnn_kinova_grasping: 150 mm보다 가까우면 목표 고정 후 약 70 mm 개루프, 3샘플 평균.
- Haviland, Dayoub, Corke, "Control of the final-phase of closed-loop visual grasping using IBVS", arXiv 2001.05650. 확인.
- Viereck, ten Pas, Saenko, Platt, CoRL 2017, arXiv 1706.04652. 확인. 14 cm 안에서는 정해진 동작으로 닫음.
- Levine 외, "Learning hand-eye coordination for robotic grasping", IJRR 2018, arXiv 1603.02199. 확인.
- Kalashnikov 외, "QT-Opt", CoRL 2018, arXiv 1806.10293. 확인.
- Burgess-Limerick, Lehnert, Leitner, Corke, "DGBench", arXiv 2204.13879. 확인. 마지막 단계 개루프가 일반적.
- Burgess-Limerick 외, "An architecture for reactive mobile manipulation on-the-move", ICRA 2023, arXiv 2212.06991. 확인.
- hello-robot/stretch_ros(`stretch_demos/nodes/grasp_object`), hello-robot/stretch_visual_servoing. 확인(코드). 한 번 관찰 뒤 고정 접근(반례: 잡기 확인 없음).
- HomeRobot/OVMM arXiv 2306.11565, OK-Robot arXiv 2401.12202. 확인. 개루프 경유점 접근, 오류 감지·재시도 없음을 한계로 적음.
- Boston Dynamics Spot SDK `manipulation_api.proto`. 확인(proto 주석). 내부 제어기는 비공개.
- Will, Grossman, "An experimental system for computer controlled mechanical assembly", IEEE Trans. Computers C-24(9), 1975. 확인. 경계 이동(guarded move).
- 미확인(초록만): Mezouar·Chaumette 2002 (inria-00352101), Garcia-Aracil 외 2005 (hal-04654343), Cherubini·Chaumette 2013 (hal-00750623).
- 우리 적용: 정렬 단계의 연속 2프레임 규칙과 GG-CNN의 "가까우면 목표 고정 후 짧은 개루프"를 따르고, 개루프 구간을 자기 명령 범위·시간·거리로 묶었다(경계 이동). 카메라 기하 때문에 확인 위치를 측정된 호버 자세로 정한 것만 바꿨다.

### r2 둘러보기 guard 여유 (v98, Track A)

- Blackmore, Ono, Williams, "Chance-Constrained Optimal Path Planning With Obstacles", IEEE Transactions on Robotics 27(6), 2011. 가우시안 위치 오차에 대한 선형 기회 제약에서 여유를 `k·√(nᵀΣn)`(장애물 법선 n 방향 표준편차)로 줄이는 방법이다. **미확인:** 본문을 아직 읽지 않았다(조정자 지시). 우리 적용: k = 1(`PairArmGuard`)을 쓰고, `std_xy` 척도(√2 배)를 유지하며, 공용 값보다 커지지 않게 했다.

### 자기 영상 문턱 재보정 조사 (v98, Track A, 출처 표기 그대로)

2026-10-03 조사, 모든 문제에 고전·최신 해결법 조사 선행 규칙.

표시: [F] 원문/소스를 열어 읽음, [S] 검색 요약만 확인, [K] 배경지식(재확인 안 함). 접근이 막혀 못 읽은 곳은 아래 "한계"에 적었다.

#### 가. 길을 잃었을 때: 멈춰서 둘러보기, 복구, 측정이 안 들어올 때
- ROS move_base `rotate_recovery` (`ros-planning/navigation` noetic-devel `rotate_recovery.cpp`, `move_base.cpp`) [F 소스]: 계획이 실패하면 값싼 복구(지도 초기화) 뒤에 360도 회전, 충돌 위험이면 중단. 가져온 것: "실패 시 한 바퀴 둘러보기, 충돌 위험이면 중단". 안 가져온 것: 위치 추정이 좋아졌는지 확인하지 않는다.
- Nav2 `Spin`/기본 행동 트리 (`nav2_behaviors/plugins/spin.cpp`, 문서 api.nav2.org) [F 문서·소스, 기본 time_allowance 10 s는 S]: 90도(1.57 rad) 회전 → 5 s 대기 → 후진 0.30 m, 재시도 6회. 가져온 것: 짧은 회전, 시간 제한, 재시도 전 대기. 안 가져온 것: 맹목 회전.
- Burgard, Fox, Thrun, "Active Mobile Robot Localization", IJCAI-97 [F]: 센서 방향과 움직임을 기대 엔트로피 감소로 고른다. 가져온 것: 지도를 아니 팬 각도별 정보량을 점수로 고를 수 있다는 점(후속 과제). 안 가져온 것: 격자 신념, 초음파.
- Fox, Burgard, Thrun, "Active Markov Localization for Mobile Robots", Robotics and Autonomous Systems 25(3-4):195-207, 1998 [S].
- Fox, Burgard, Thrun, Cremers, "Position Estimation for Mobile Robots in Dynamic Environments", AAAI-98 [F]: 엔트로피 문턱은 "현재 신념을 맞든 틀리든 확인하려는" 경향이 있다. **이번 사고와 직접 같은 구조**: 믿음이 틀리면 증거를 받는 문이 닫힌다. 그래서 "측정이 한 번도 안 들어오는 상태"를 별도 복구 시작 조건으로 둔다.
- Fox, Burgard, Thrun, "Markov Localization for Mobile Robots in Dynamic Environments", JAIR 11:391-427, 1999 [F]: 평평한 사전분포에서 전역 재위치 추정이 받아들여진 마지막 수단.
- Thrun, Burgard, Fox, Probabilistic Robotics (MIT Press, 2005) 증강 MCL(표 8.3, 약 218쪽) [S]/[K], Nav2 AMCL 소스의 `recovery_alpha_fast/slow` 기본값 0 [F 소스]: 단기/장기 평균 가중치 비율로 입자를 주입. 안 가져온 것: 이 방식은 **측정이 0개이면 아무 신호도 못 본다**(우리 사고와 같다). 그래서 "T초 동안 받아들인 갱신 없음"을 따로 시작 조건으로 둔다.
- Thrun, Fox, Burgard, Dellaert, "Robust Monte Carlo Localization for Mobile Robots", Artificial Intelligence 128 (2001) [F]: 센서가 너무 정확하다고 가정하면 입자 필터가 쉽게 길을 잃는다. 처방은 잡음 가정을 키우기, 균일 입자, 혼합. 가져온 것: 입자 주입 전에 잡음부터 키운다.
- Davison, Murray, "Simultaneous Localization and Map-Building Using Active Vision", IEEE TPAMI 24(7):865-880, 2002 [F]: 머리 회전 시간을 비용으로 세어 가장 불확실성을 줄이는 곳을 본다. 가져온 것: 둘러보기 시간을 비용으로 기록.
- Chaplot, Parisotto, Salakhutdinov, "Active Neural Localization", ICLR 2018 [F]: 신념 최대값/엔트로피를 종료 기준, 단계 수를 예산으로. 학습 기반이라 가져오지 않음.
- Mur-Artal, Montiel, Tardós, "ORB-SLAM", IEEE T-RO 2015 [F]: "추적 상실"을 명시적 상태로 두고, 후보 생성은 싸게 검증은 엄격하게, 복구 뒤에는 20프레임 동안 새 키프레임을 막는 완충. 가져온 것: 상실 상태, 복구 뒤 완충. 폴백으로 검출 문턱을 몰래 낮추는 방식은 가져오지 않음.
- 최근 연구(2022~2026): ActLoc, Li 외, arXiv 2508.20981 [F 초록] / "When to Localize? A POMDP Approach", Williams 외, SSRR 2024, arXiv 2411.08281 [F 초록] / Active Particle Filter Networks, Honerkamp 외, arXiv 2209.09646 [F 초록] / F3Loc, Chen 외, CVPR 2024, arXiv 2403.03370 [F 초록] / Semantic Rays, Grader, Averbuch-Elor, ICCV 2025, arXiv 2507.09291 [F 초록] / Sparse Feasible Hypothesis Sampling, Zhang 외, arXiv 2511.01219 [F 초록] / GALoc, Han 외, arXiv 2609.08385 [F 초록만, 2026-09 논문이라 인용 전 재확인 필요]. 가져온 것: 시점별 정보량이 다르다(요에 따라 다름), 실현 가능한 위치만 후보로 주입, 거친 것에서 세밀한 것으로. 모두 학습 깊이/LiDAR가 필요해 그대로는 못 쓴다.
- Boniardi 외, "Robot Localization in Floor Plans Using a Room Layout Edge Extraction Network", IROS 2019, arXiv 1903.01804 [F]: 열마다 **잘라낸(saturated) 잔차**를 쓰고 쓴 열 수로 나눈다. 측정을 다 거절하는 우도에 대한 가장 직접적인 처방 패턴(후속 과제).

#### 나. 멈춤 후 안정화, 번짐 게이트
- Canon, "Robot with camera", US8352076B2 [F 특허]: 옛 방식은 약 1초 고정 안정화 대기, 새 방식은 위치 오차와 속도가 모두 문턱 아래일 때 촬영. 우리는 관절 속도를 못 쓰므로 마지막 자기 명령 뒤 0.2 s 고정 대기를 유지(MuJoCo 렌더는 움직임 번짐이 없다).
- Intrinsic, "Reducing motion blur for robot-mounted cameras", US11472036B2 [F 특허]: 프레임을 팔 움직임 자료와 맞춰 번짐을 본다.
- Pertuz, Puig, Garcia, Pattern Recognition 46(5):1415-1432, 2013 [서지 F, 내용 K]: 라플라시안 분산 등 초점 측정은 상대 비교용이다. Pech-Pacheco 외, ICPR 2000 [S]. Unblur-SLAM, arXiv 2603.26810 [S]. LOVON, arXiv 2507.06747 [S]. 가져온 것: 번짐 점수는 같은 시퀀스의 백분위로 판정(우리 렌더에는 번짐이 없어 쓰지 않음).

#### 다. 광도 강건성과 문턱 재정
- Engel, Usenko, Cremers, "A Photometrically Calibrated Benchmark for Monocular Visual Odometry", arXiv 1607.02555 [F 초록]: 광도 보정을 한 번 하고 문서화.
- Engel, Koltun, Cremers, "Direct Sparse Odometry", arXiv 1607.02565, TPAMI 2018 [F 본문]: 블록별 문턱 = 중앙값 기울기 + 상수. 가져온 것: 문턱을 지역/대상 자료 기준선에 상대화.
- Ulrich, Nourbakhsh, "Appearance-Based Obstacle Detection with Monocular Color Vision", AAAI-2000 [F]: 바닥 기준 영역 분포를 배워 그 분포 대비 이탈로 판정, 조명이 바뀌면 정적 모델은 거짓 양성이 늘고 적응 모델이 줄인다. 가져온 것: 문턱을 대상 프로파일의 기준 프레임 분포에서 정하는 방식.
- Horswill, "Polly: A Vision-Based Artificial Agent", AAAI-93 [F]: 질감 없는 바닥에서는 기울기 문턱 에지 검출이면 충분, 그림자와 약한 바닥-벽 경계가 실패 원인. 가져온 것: 경계에 실제 단차가 있어야 한다는 검사(그림자 그라데이션 거르기).
- Maddern 외, "Illumination Invariant Imaging", ICRA 2014 Workshop on Visual Place Recognition in Changing Environments [F]: 로그 색 조합. 햇빛 가정이라 MuJoCo 렌더와 푸른 바닥 채도 문제에는 안 맞는다. 채도 절대 문턱은 후보가 아니라는 근거로만 사용.
- Lorigo, Brooks, Grimson, IROS 1997:373-379 [S, 2차 인용만]; Lenser, Veloso, IROS 2003:886-891 [S]; OpenCV Canny/CLAHE 튜토리얼(`opencv/opencv` markdown) [F]; Rosebrock, PyImageSearch 2015 자동 Canny [F, 블로그]; Zhang, Forster, Scaramuzza, ICRA 2017 [F 본문]; Shim, Lee, Kweon, IROS 2014 [F 일부]; Tobin 외, IROS 2017, arXiv 1703.06907 [F 일부, 간접 근거]; ORB-SLAM 문턱 기본값 20→7 [S].

#### 라. 우리에게 적용한 것과 바꾼 것
- 적용: (1) 문턱을 조명에 맞춰 **대상 프로파일 기준 프레임의 백분위 + 명시한 여유폭**으로 다시 정함(Ulrich의 기준 영역 학습, DSO의 중앙값+여유폭의 취지). 정확한 이식이 아니라 취지만 빌렸다. (2) 벽 경계 후보에 **단차 검사** 추가(Horswill, Canny의 취지). (3) 문턱을 몰래 낮추는 폴백은 쓰지 않았고 값과 근거를 번들에 고정했다(ORB-SLAM의 폴백을 일부러 안 씀).
- 바꾼 것: 우리는 관절 속도를 못 쓰므로 Canon 특허의 위치/속도 문턱 대신 0.2 s 고정 대기를 유지. 복구 동작은 "T초 동안 받아들인 갱신 없음"을 따로 시작 조건으로 둔다(Fox 1998의 경고, 증강 MCL이 침묵한 필터를 못 보는 점).
- 한계: 렌더 조명이 바뀔 때 고정 광도 문턱이 실패함을 직접 보이고 대상 프레임 보정을 권하는 논문은 찾지 못했다(Tobin 2017은 간접 근거). Pertuz(내용), Lorigo(원문), Horswill 박사논문, Lenser는 원문을 읽지 못했으니 인용 전 확인이 필요하다. wiki.ros.org(봇 차단), Probabilistic Robotics PDF(링크 끊김), ScienceDirect/SAGE(403)는 열지 못했다.

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
