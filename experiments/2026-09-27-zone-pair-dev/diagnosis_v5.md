# dev07/dev08 사후 진단 v5 — 2026-09-27

**tags_temporary · dev · 연구 결과 아님. 코드 수정·신규 물리 step·모델 호출·git 커밋 없음.**

dev07의 직접 원인은 **근접 프레임 `END_CLIPPED`와 추적기의 `BAND_CLIPPED` 전용 계약 불일치**다.
standoff·재관측은 성공했고 자세/빔 σ도 통과했다. dev08은 **align 중 XY σ가 loaded HIGH 7 cm를 초과**했다.
dev06의 yaw σ 초과와 직접 조건은 다르지만, 빔을 보는 동안 태그 갱신이 끊기는 구조는 같다.
권고는 **align 전/중 안전한 태그 재관측(A)과 근접 관측 계약 보완(B)**을 각각 검증하는 것이다.
dev07을 자세 불확실성 실패로 합산하거나 임계값 완화로 두 문제를 함께 해결해서는 안 된다.

## 범위·고정 조건

- 주 실행 소스/분석 HEAD: `8effc2cee5c3534d553adb75a0d82b49097e5286`, [prereg_v4.json](prereg_v4.json).
  원본 `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v4-8effc2cee5c3534d553adb75a0d82b49097e5286/{dev07,dev08}`는 읽기만 했다.
- 비교 dev05/dev06은 `4a17e7d47616056db85f35933327c6b63581853d`, prereg_v3다.
  원본은 `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v3-4a17e7d47616056db85f35933327c6b63581853d/{dev05,dev06}`.
  [진단 v4](diagnosis_v4.md)를 보존하고 사용한 로그·프레임·평가 trace를 다시 읽었다.
- 요청의 `dev05–08`은 실행 ID로 **4회**, 정상 시도 2회와 carry-GO 후 abort 진단 2회다.
  서로 다른 소스/사전등록이며 연구 성공률이나 통신 효과로 합산하지 않는다.
- 두 v4 manifest에서 `zone_wide_door_tags_v2_dock_v3`, `cargo_noslip_v1`, noslip=10,
  timestep=0.00025 s, **weld OFF**, source/input 변경 없음이 일치한다.
- 판정에는 events/status/commands/pair_records/robots와 실제 입력 JSON/JPEG를 사용했다.
  실제 위치·접촉·공간 여유는 아래 **eval_only** 절과 JSON의 `eval_only` 키에 분리했다.
  제어 입력·제어 후보의 수치 설정에 쓰지 않는다. 상세 수치·경로·해시는 [diagnosis_v5.json](diagnosis_v5.json).

## 실행 결과

시각은 SIM 절대시각이다. dev08의 계획된 운반 중 abort 개입은 미도달이다.

| 항목 | dev07 / seed901 / 정상 시도 | dev08 / seed902 / abort 진단 |
|---|---|---|
| approach 준비 r1 / r2 | 99.9 / 154.3 s | 113.8 / 151.7 s |
| 양쪽 approach GO → align | 154.7 → 154.8 s | 152.1 → 152.2 s |
| pregrasp_look → fix | 양쪽 190.4 → 199.6 s, fix=true | 미도달 |
| standoff → descend | 양쪽 199.6 → 200.8 s | 미도달 |
| 최초 중단 | **202.799999997 s r1 PREGRASP_NOT_READY** | **175.599999998 s r2 POSE_UNCERTAIN** |
| 상대 종료 | 같은 시각 r2 PARTNER_ABORT | 같은 시각 r1 PARTNER_ABORT |
| close PWM / joint_grasp / lift / door / 배치 | 0건 / 모두 미도달 | 0건 / 모두 미도달 |
| 평가 | DEV_NOT_CONFIRMED, physical_success=false | 동일, intervention_not_reached=true |
| 종료 SIM 절대 / 경과(시작 1.3 s 제외) | 205.30025 / 204.00025 s | 178.10025 / 176.80025 s |
| 기록 wall / motion 명령 | 699.62448 s / 2,591건 | 645.71966 s / 1,799건 |
| 모델 호출·API 비용·응답 시간 | 0 / 발생 없음 / 해당 없음 | 동일 |

wall은 기록된 비용이며 속도 비교가 아니다. motion은 arm/look/drive/mecanum 발행 행의 수다.
status 스트림과 pair_records의 status_messages는 네 실행 모두 행 전체가 일치한다.
dev07 r1은 `wait_close`에 진입해 close 보고 `ready=false, accepted=true`를 남겼다.
여기서 accepted는 보고 접수이지 READY가 아니다. 양쪽 close_ready/close GO는 없다.
r2는 descend 중 상대 abort로 종료했으므로 r1의 검사 결과를 r2에 대입하지 않는다.

## dev07: PREGRASP_NOT_READY의 정확한 하위 조건

호출 경로는 [PairGraspRelook._wait_close](../../harness/zone_pair_grasp.py)(181–195행)
→ [PairCommandGuard.preclose_check](../../harness/zone_pair_guards.py)(132–160행)
→ [RestingBeamTrack.estimate](../../harness/zone_pair_beam_track.py)(151–178행)다.
`preclose_beam_guard clear=false, reason=BEAM_UNCERTAIN` 이벤트가 있으므로 그보다 앞선
short-circuit 조건인 pregrasp_done·공통 pose·OPEN·grasp PWM·fresh frame·grip_view는 통과했다.

| 하위 조건 | 실제 증거와 재구성 | 판정 |
|---|---|---|
| standoff 관측 | r1 200.8 s frame 1702, accepted=true; 7개 edge strip, span 0.12103 m | 성공 |
| 공통 위치 재관측 | r1 199.6 s fix=true; 마지막 태그 199.9 s, pregrasp 시작 190.4 s 이후 | 성공 |
| 자세 σ | 202.8 s XY **0.02383 m**, yaw **0.01208 rad**; 한도 0.05 m / 0.05235988 rad | 통과 |
| 영상·손목·집게 | frame 1722, PWM `{1:2000,3:1161,4:1904,5:2500,6:1486}`; 입력과 명령 일치 | 통과 |
| grip_view | seen=true, dark=0.4931, top beam=0.4343, bottom beam=0.2384 | 통과 |
| 새 full-beam fit | `END_CLIPPED`, end_visible=false, grip_source=end_plus_inset_v1 | 불가; track 경로로 이동 |
| anchor age / 전파 σ | age 2.0 s < 30 s; XY **0.018945 m**, yaw **0.04232276 rad (2.42492°)** | 0.05 m / 3° 이내 |
| **partial 분류** | **실제 END_CLIPPED, 요구 BAND_CLIPPED** | **최초 거부, 161–162행** |
| partial 일치율 | 거부 뒤의 검사를 별도 계산하면 147점 중 147점, **1.0 ≥ 0.95** | 온라인에서는 미실행 |
| 전체 빔 여유 | reason gate 때문에 거리 계산 미도달 | 여유 부족으로 종료한 것이 아님 |

저장한 JPEG+발행 PWM으로 standoff anchor JSON을 그대로 재현했다. 그 뒤 발행 명령을
RestingBeamTrack에만 재생했다(물리/PF 재실행 없음). 비집게 PWM 절댓값 변화 합은 2,945이며,
빔 XY σ는 `0.015 + 0.0005×2 + 0.000001×2945 = 0.018945 m`,
yaw σ는 `0.035432760565 + 0.0005×2 + 0.000002×2945 = 0.042322760565 rad`다.
이 구간 base 이동 명령은 없었다. 위 빔 σ는 보정된 통계적 정확도가 아닌 개발용 보수 경계다.
r1 프레임 SHA는 `2b613b886920cff5486227063b33cac4a86349dc422c3a10e4e7a1c9c4369afd`.
로그의 반올림 시각은 202.8로 정규화했다. 실제 시각과 약 3 ns 차이이며 이 판정을 바꾸지 않는다.

근접 영상에서는 검은 밴드와 노란 빔이 화면 대부분을 차지한다. geometry detector의 좁은
lime 마스크가 top-plane에 남기는 점은 **147개**인 반면, 기존 grip_view용 넓은 색상 마스크는
같은 투영 필터에서 **16,751개**를 남긴다. 좁은 strip의 PCA 방향은 −91.007°이며
standoff axis −3.745°와 다르다. 소스의 band 탐색은 이 PCA 방향의 corridor에 의존한다.
따라서 **파지 높이의 색상·부분 시야와 detector 계약 불일치**가 구체적인 후속 검증 대상이다.
넓은 마스크의 점이 많다는 사실을 새 빔 좌표/정확도/안전의 증명으로 쓰지는 않는다.

같은 source의 기존 standoff 회귀는 저장 dev06 r2의 **BAND_CLIPPED** 사례였다.
그 회귀 통과가 이번 dev07 r1 **END_CLIPPED**를 포괄하지 않는다.
dev07 r2의 최신 pre-abort 입력은 202.7 s이며 뒤에 camera PWM이 바뀌었다.
미래 202.9 s 프레임을 쓰거나 r2도 READY였다고 소급 판정하지 않았다.

### 사후 여유 — eval_only

온라인에서 거부된 분류 조건만 진단상 건너뛰고, **자기 입력으로 유지하던 기존 anchor/σ/pose**를
동일 거리 함수에 넣으면 여유는 **+0.680877 m**, 제한 벽은 wall_divider_1이다.
이는 미실행 분기의 사후 산술이며 온라인 통과 기록이나 enum 허용의 근거가 아니다.

별도로 저장된 **202.8 s eval_only/trace**의 빔 8개 꼭짓점으로 XY convex footprint를 만들고,
정적 벽/문기둥 표면까지 선분 거리를 계산했다. 최소 실제 XY 표면 여유는
**+0.904724 m**(wall_divider_1/2 동률), 문기둥은 +0.906008 m다.
이는 빔–정적 벽의 순간 여유이며 로봇 간/팔의 미래 swept clearance가 아니다.
양쪽 손가락 힘은 0/0 N이고 평가 joint_grasp=false다.
이 값으로 제어를 교정하거나 임계값을 정하지 않으며 이후 파지 성공도 추론하지 않는다.

## dev08: dev06과 같은 태그 공백 계열, 다른 σ/단계

[before_control](../../harness/zone_pair_guards.py)(214–226행)은 approach 계열 밖에서는
실제 파지 여부와 관계없이 loaded gate를 적용한다. HIGH는 XY **0.07 m**, yaw **3°**다.
따라서 **gate profile=loaded와 localizer load_state=loaded는 서로 다른 개념**이다.

| r2 시점 | XY σ (m) | yaw σ (rad) | 의미 |
|---|---:|---:|---|
| 160.3 s | 0.04615 | 0.01622 | 마지막 수용 태그 [33,34,35,36,37], frame 1298 |
| 175.5 s | 0.06993 | 0.02626 | HIGH 이하 |
| **175.6 s** | **0.07004** | **0.02639 = 1.51204°** | **XY HIGH 초과**, frame 1451, abort |
| 176.2 s | 0.07039 | 0.02684 | abort 뒤 dwell 이벤트; 요약 std_xy=0.0704 |

XY의 초과폭 0.00004 m는 보고 반올림 오차 ±0.000005 m보다 크다. yaw는 한도 아래다.
0.6초 dwell은 이벤트 알림 지연이며 HIGH 상태 행동의 유예가 아니다.
당시 집게 PWM=2000, `load_state=unloaded`, 닫힘 명령 0건이다.
dev06의 loaded yaw process-noise 증가를 이번 실패 원인으로 그대로 옮길 수 없다.

r2는 160.2 s p45 전환, 160.3 s 마지막 태그, 166.5 s inspect 전환, 175.6 s 중단 순서다.
그동안 **153개의 새 프레임**, 최대 프레임 간격 약 **0.1 s**, 태그 갱신 공백 **15.3 s**다.
r1도 164.8→175.6 s **10.8 s/108프레임**의 공백이다. 캡처/전송 공백이 아니다.
여기서 공백은 localizer가 수용한 새 태그 관측의 부재다. 모든 픽셀의 태그 검출 가능성을
재검사한 것은 아니지만 마지막 태그/중단 JPEG를 직접 비교해 시야 변화를 확인했다.

자기 발행 PWM의 고정 카메라 FK에서 optical pitch는 search **−20.62°** → p45 **−37.54°**
→ inspect **−51.58°**, pan은 자기 base 전방 0°다. inspect에서는 빔/바닥을 보고 벽 태그가
화면에서 사라진다. 이는 명령 기반 FK이며 측정 관절/실제 카메라 자세라고 표현하지 않는다.
dev08은 align을 끝내지 못해 v4의 **align 후 pregrasp relook에는 아예 도달하지 못했다.**

dev06은 r2가 이미 close 명령 뒤 wait_lift에서, 태그 공백 30.5 s 동안 loaded 운동 잡음이
누적돼 yaw σ 0.05238 rad > 3°가 됐다. 두 경우 모두 태그 갱신 없이 PF 예측이 이어지지만,
dev08은 open-align의 XY 한도, dev06은 close 뒤 대기의 yaw 한도라는 차이가 핵심이다.

## dev05–08 누적: 공통 취약점과 분리해야 할 실패

| 실행 | 관측 공백/중단 경로 | 해석 |
|---|---|---|
| dev05 | r1/r2 태그 공백 28.2/26.7 s → 미파지 전체 빔을 붙인 guard의 벽 거부 | align 관측 소실 + 기존 기하 계약; v4와 다른 코드 |
| dev06 | 26.9/30.5 s → r2 wait_lift yaw HIGH | 태그 공백 + close 뒤 loaded 예측 누적 |
| dev07 | relook 직전 25.4/24.5 s → 양쪽 fresh fix → 중단 때 2.9/2.8 s | 공통 pose 재관측 성공; 최종 실패는 별도 근접 관측 계약 |
| dev08 | 10.8/15.3 s → r2 align XY HIGH | align 이후에만 있는 relook으로는 늦음 |

공통 구조는 **손목 한 시야가 빔 정렬과 벽 태그 위치 추정을 번갈아 담당하는데,
빔 관측이 잘 된다는 이유만으로 전역 자기 위치도 계속 갱신되는 것은 아니라는 점**이다.
자기 RGB beam 관측은 계속 있어도 PF는 명령 예측을 이어간다.
동결 [M2 소스](../../scripts/run_m2_pair.py)(352–355행)도 drive 자세용 운동 모델이
팔을 낮춘 align 명령을 과대예측할 수 있다고 기록한다. dev07의 shared-pose relook은
이 연결을 실제로 갱신했지만, dev08처럼 그 이전에 HIGH가 되거나 근접 시야 계약이 달라지는
경로는 남아 있다. 네 실행으로 발생률·새 seed 일반화·통신 효과는 입증하지 못한다.

### 누적 위치 오차 비교 — eval_only

저장 보고와 동시각 평가 trace를 대조한 r1/r2 XY 오차는 dev05 **0.759/0.887 m**,
dev06 **0.703/0.949 m**, dev08 **0.683/0.760 m**다.
dev07은 relook 직전 **0.913/0.869 m**, 중단 직전 **0.00925/0.00911 m**다.
dev08 r2의 마지막 태그 이후 추정 변위/실제 변위는 **0.78143/0.13689 m (5.71배)**다.
사후로는 단순 σ 하나가 bias를 보증하지 않는다는 증거이며, 이 GT 차이를 제어 보정이나
gate 수치 선택에 넣지 않는다. 전체 PF RNG/실제 마찰·구동 지연의 원인별 분해는 하지 않았다.

## 후보 3개와 권고

모두 제안 단계다. 자기 RGB·정적 지도/고정 보정·자기 명령, 기존 STATUS enum만 쓰고
GT 제어 금지·카메라 배치/FOV 유지·weld OFF·cargo_noslip_v1을 유지한다.

| 후보 | 겨냥하는 원인·구체적 방향 | 위험·검증 |
|---|---|---|
| **A. align 전/중 전용 look + 공통 pose 갱신 (우선)** | align 진입 전 새 태그를 얻고, p45/inspect 전환 뒤 태그 age/명령 누적에 유한 예산을 두어 정지 재관측. guard가 읽는 동일 own.pose/last_report를 갱신 | 시작 전 한 번만 보면 긴 align 공백은 남음. 기존 collision guard·재관측 예산을 유지하고, 잡은 뒤 일방 sweep 금지. 새 태그 없는 low-σ/VO-only 준비 거부 검사 |
| **B. preclose 전용 관측 계약 (A와 함께)** | dev07의 fresh full anchor를 보존하면서 END_CLIPPED·색상 변화·부분 관측 종류를 구별. 동일 PWM·fresh frame·전파 σ·patch 일치·전체 빔 clearance를 모두 요구 | enum 일괄 허용 금지. partial PCA/그립점으로 pose·age·σ를 갱신하지 않음. 저장 dev07 r1 반례와 다른 물체·잘못된 hue·누락/노후 anchor·문기둥 충돌을 함께 회귀 검증 |
| **C. align 자세별 운동 모델 + phase별 gate 계약** | 별도 보정/검증된 자세·펄스 모델과 자기 RGB 상대 변위의 보수적 결합 검토. 접촉 전 재관측/파지 확인/운반의 허용 행동을 구분 | calibration 출처·held-out 조건·σ 적합도 필요. VO로 PF 덮기, 정지 명령을 실제 정지로 단정하기, align gate만 unloaded로 바꾸는 처방은 피함 |

**A로 관측 공백이 쌓이기 전에 대응하고, B로 dev07의 미포괄 입력을 다루는 순서를 권고한다.**
양쪽 준비 맞추기는 기존 `aligning`, `close_ready_<segment>`, GO/abort와 TTL만 사용한다.
STATUS enum 범위에서는 상대의 좌표·이미지·σ·태그 관측 자체를 교환할 수 없다.
즉 후보는 각자 자기 관측을 갱신하고 **준비 상태만 동기화**하는 방식이다.

임계값 완화는 관측/phase 계약과 불확실성 calibration을 검증한 뒤에도 필요한 경우의 마지막
수단이다. dev07의 enum 불일치를 고치지 못하고 dev08은 실패를 뒤로 미룰 수 있어 현재는 권고하지 않는다.
이 진단의 eval_only 공간 여유나 GT 오차는 후보 제어값에 사용하지 않는다.
후보 구현·새 입력 회귀·물리 효과 검증은 이번 범위 밖이며, 전체 경로와 예정 abort는 별도
소스 고정·사전등록·예산·잠금 아래 유한 dev로 확인해야 한다.

## 검증·보존·남은 문제

- dev07 **9,001개**, dev08 **7,641개** artifact 크기/SHA256 전부 일치.
  분석 관련 frozen 소스는 회차별 **36개** 모두 현재 HEAD와 일치했다.
  dev05/06에서 이번에 사용한 원본 20개씩도 기존 index와 대조했다.
  localizer·공용 pose gate·동결 M2 소스는 v3→v4 사이 변경이 없음을 Git diff로 확인했다.
- 회귀 **81 passed / 4.00 s**: `test_zone_pair_grasp.py`, `test_zone_pair_preclose.py`,
  `test_zone_pair_standoff.py`, `test_zone_pair_review7.py`.
  `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `--basetemp=./.pytest_tmp`.
  pytest와 재구성에서 mujoco/torch/tensorflow import를 차단했고 `.pytest_tmp` 삭제를 확인했다.
  기존 회귀의 통과이며 새 후보의 구현/물리 성공 검증은 아니다. 테스트 파일도 수정하지 않았다.
- 저장 접촉 기록: dev07/08 **816,001/707,201 step**, 간격 오류 0, 금지 접촉 카운트 모두 0,
  max_eq_active=0. 실행 중 새 물리 step은 0이다. overview 전체 수동 승인 상태는 원본대로 pending이다.
- **TensorBoard 임시 변환/실제 이벤트 로딩 완료:** `/tmp/pair-v5-tensorboard-20260927`.
  EventAccumulator에서 각 run의 scalar 5개(성공 0, SIM 절대 종료, wall, 명령, 호출 0),
  HParams 이벤트와 `media/overview.mp4` 등록을 읽었다. 값은 원본과 float32 반올림 범위에서 일치한다.
  원본 `result/sim_s`는 **절대 종료 시각**이므로 임무 경과와 구분한다.
- **공유 게시·화면 검증 미완료:** 공유 snapshot manifest 1,141개에서 이번 v4 원본 참조는 없었다.
  primary `outputs/`가 허용 쓰기 범위 밖이라 공용 snapshot/view를 변경하지 않았다.
  ps도 차단돼 viewer PID·소유권·logdir를 검증하지 못했으며 서버를 시작/종료하지 않았다.
  [기존 TensorBoard 주소](http://127.0.0.1:6006)에 새 run·비교 baseline·핀·HParams 열·영상 재생이
  표시됐다는 주장은 하지 않는다. 기존 view의 v1/v2 설정과 snapshot은 보존했다.
- Git fetch는 공유 FETCH_HEAD 쓰기 제한, gh pr list는 GitHub 네트워크 제한으로 실패했다.
  커밋·push·PR 변경/댓글·병합·primary 갱신 없음. 이번 worktree의 진단 MD/JSON와 README만 변경했다.
  UGRP 예외에 따라 Drive는 사용하지 않았다. 로컬 원본 해시 확인은 원격 백업이 아니다.
