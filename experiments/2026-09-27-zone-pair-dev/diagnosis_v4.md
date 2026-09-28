# dev05/dev06 사후 진단 v4 — 2026-09-27

**tags_temporary · dev · 연구 결과 아님. 코드 변경·신규 물리 step·모델 호출·git 커밋 없음.**

두 회차 모두 출발/approach는 통과했으나 공동 파지·lift·door·배치는 실패/미도달이다.
dev05는 **잘못된 PF 위치에서 아직 잡지 않은 빔 전체를 손목에 붙인 것으로 검사한 정적 벽 guard**가 중단시켰다.
dev06은 **loaded yaw σ가 3°를 초과**해 중단됐다. 위치 σ 5 cm 초과가 원인이라는 요약은 수정해야 한다.
권고는 **A: 파지 전 안전한 재관측으로 공통 위치 추정을 갱신하고 양쪽 준비 뒤 close**다.
임계값 완화나 guard 해제로 해결할 근거는 없다.

## 고정 조건과 증거

- 실행/분석 소스: `4a17e7d47616056db85f35933327c6b63581853d`, [prereg_v3.json](prereg_v3.json).
  scene `zone_wide_door_tags_v2_dock_v3`, dock x=−0.65 m, 기존 tags_v2/벽 0.10 m.
- `cargo_noslip_v1`, `noslip_iterations=10`, timestep 0.00025 s, weld OFF.
  두 manifest에서 applied 일치, source/input 변경 없음. 주요 분석 소스 12개도 frozen execution manifest 해시와 일치했다.
- 원본: `/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v3-4a17e7d47616056db85f35933327c6b63581853d/{dev05,dev06}`.
  **읽기만 했다.** dev05 8,381개 + dev06 8,545개 artifact 해시 전부 일치.
- `events.jsonl`, `status.jsonl`, `commands.jsonl`, `pair_records.json`, `robots.json`, 실제 입력 JSON/JPEG,
  `eval_only/{trace.jsonl,contacts.json,result.json,overview.mp4,video_frames.jsonl}`을 대조했다.
  status 스트림은 pair_records의 status_messages와 행 전체가 일치한다.
- 세부 수치·원본 경로/해시·환경·프레임 ID·guard 재구성·후보·검증 영수증은 [diagnosis_v4.json](diagnosis_v4.json)에 저장했다.
  `eval_only`는 사후 원인 판별에만 사용했다. 아래 GT 비교를 로봇 입력이나 온라인 보정으로 제안하지 않는다.

## 모든 결과와 중단 순서

시각은 SIM 절대시각이다. 종료 후 관찰까지 포함한 총 SIM 경과는 시작 1.3 s를 뺀 값이다.
두 조건은 정상 전체 시도와 carry-GO 후 abort 진단이므로 연구 성공률로 합산하지 않는다.

| 항목 | dev05 / seed901 / 정상 시도 | dev06 / seed902 / carry-GO abort 진단 |
|---|---|---|
| approach 완료 진입 r1 / r2 | 109.9 / 152.7 s | 81.2 / 154.1 s |
| 양쪽 approach GO | 153.0 s | 154.5 s |
| grasp 진입 r1 / r2 | 189.7 / 188.2 s | 192.7 / 186.7 s |
| wait_lift 진입 | 양쪽 미도달 | r2 189.6 s, r1 미도달 |
| 최초 abort | r1, **190.42875 s**, `PAIR_COLLISION_GUARD` | r2, **193.70000 s**, `POSE_UNCERTAIN` |
| 상대 종료 | r2 `PARTNER_ABORT`, 같은 SIM 시각 | r1 `PARTNER_ABORT`, 같은 SIM 시각 |
| 공동 파지 / lift / door / 배치 | 모두 미도달 | 모두 미도달 |
| 계획된 개입 | 해당 없음 | **intervention_not_reached**; abort 진단 통과 아님 |
| 저장 평가 | `DEV_NOT_CONFIRMED`, physical_success=false | `DEV_NOT_CONFIRMED`, physical_success=false |
| 종료 절대 SIM / 총 경과 | 192.929 / 191.629 s | 196.20025 / 194.90025 s |
| wall / 발행 motion 명령 수 | 692.084 s / 2,098 | 846.129 s / 1,893 |
| 외부 모델 호출·비용 | 호출 0, API 비용 발생 없음 | 호출 0, API 비용 발생 없음 |

wall 수치는 기록된 실행 비용이며 잠금 조건을 새로 맞춘 속도 비교가 아니다. 명령 수는
arm/look/drive/mecanum 발행 횟수이고 물리 행동 성공 횟수가 아니다. 응답 시간은 해당 없음이다.

두 회차 모두 매 물리 step 접촉 기록의 누락/잘못된 간격은 0이다(766,516 / 779,601 step).
robot–robot, robot–wall, beam–wall, approach 중 robot–beam, r3 간섭 카운트는 모두 0,
`max_eq_active=0`이다. abort 뒤 큐 비움·추가 motion 0건·관찰 구간 충족도 기록에서 확인했다.
이는 **발생한 안전 중단**의 정리 결과다. dev06의 예정된 운반 중 abort 시험을 수행한 것은 아니다.

`protocol_complete=true`/`STUDY_LAYER_DONE`은 실행 드라이버 종료다. dev05는 필수 후속 GO가 없어
평가 protocol=false, dev06은 관측된 GO/abort 검사 protocol=true지만 주입 개입에는 도달하지 못했다.
`no_drop=false`도 낙하가 관측됐다는 뜻이 아니다. `drop_samples=[]`이며 들어 올린 적이 없다.
전체 영상 수동 검토는 원본대로 pending으로 보존했다.

## P1 — dev05: 실제 로봇 간 충돌 위험이 아니라 가상 빔의 벽 여유 소진

### 어떤 명령을 무엇 때문에 거부했는가

실제 abort STATUS는 190.428749997 s, events에는 190.429 s로 반올림됐다.
직전 r1 보고는 frame_id=1598, 190.4 s다. 새 보고 age는 약 0.029 s로 신선하다.
명령 이력의 집게는 OPEN=2000이고 파지 hover로 팔을 이동 중이다.

| 거부 입력/계산 | 재구성 값 |
|---|---|
| guard가 읽은 r1 PF 위치 | (1.31836, 0.09247), yaw 0.067231 rad |
| σxy / σyaw / 마지막 태그 age | 0.05985 m / 0.02378 rad / 28.2 s |
| 직전 발행 PWM | `{1:2000, 3:672, 4:1885, 5:1999, 6:1489}` |
| 다음 거부 후보 | arm servo 3 → **687**, 190.4 s 예정 → 190.42875 s arm tick |
| 제한 물체 | **wall_divider_2**, 중심 (2.2, 0.875), half=(0.025, 0.575), 높이 0.10 m |
| 제한 형상 | 전체 빔의 먼 끝 sphere(index 30); 추정 world (2.04109, 0.12860, 0.11220) |
| sphere radius / XY 표면 거리 / 불확실성 margin | 0.027495 / 0.190010 / 0.190424 m |
| 최종 clearance | **−0.000413508 m (−0.414 mm)** → `no_clear_pan`, transition_clear=false |

거부 명령 자체는 `commands.jsonl`에 남지 않으므로 확정 소스의 IK/`ArmSequence.queue`로 재구성했다.
직전까지 실제 발행된 hover 명령 **65개가 순서·PWM 모두 일치**하고 바로 다음 명령이 위 후보다.
기록된 보고 반올림의 32개 모서리 조합에서도 clearance는 −0.438~−0.389 mm로 음수다.
PF 자체나 물리 상태를 재실행한 것은 아니다.

[PairCommandGuard](../../harness/zone_pair_guards.py)의 `carrying_beam`은 `grasp`부터 true다(124–126행).
[PairSweepGuard](../../harness/zone_pair_geometry.py)는 자기 명령 FK의 grip point에 **600 mm 전체 빔**을
붙여 벽/문기둥과 검사한다(24–61행). 따라서 아직 집게가 열려 있고 바닥에 있는 빔도 hover 중에는
가상의 손목 고정 빔으로 검사된다. 코드의 guard에는 동적 peer 위치나 실제 빔까지의 접근 거리 검사가 없다.
`PAIR_`라는 이름을 “로봇끼리 너무 가까움”으로 해석하면 안 된다.

### 실제 위험과 오탐의 구분

평가 trace의 같은 190.4 s r1 위치는 (0.56059, 0.04570), PF XY 오차는 **0.75921 m**다.
같은 PWM/동일 σ를 두고 **사후 진단에서만** 평가 위치로 좌표 변환하면 최저 clearance는 **+0.70264 m**다.
오래된 PF 좌표를 유지해도 σ=0인 민감도 검사에서는 clear, 전체 빔을 제외한 팔 검사도 clear다.
즉 잘못된 위치 + 큰 불확실성 여유 + 아직 잡지 않은 전체 빔 영역이 함께 거부를 만든다.

실제 금지 접촉 0건, overview의 문 서쪽 바닥 빔, 정적 재구성의 큰 실제 공간 여유를 합치면
**실제 충돌 임박보다 잘못 배치한 보수적 빔 영역의 오탐이라는 근거가 강하다.**
“파지에 필요한 로봇 간 거리와 guard 여유의 필연적 모순”은 이번 원인이 아니다.
다만 거부된 다음 명령을 실제로 실행하지 않았으므로 그 뒤 무충돌·파지 성공을 증명한 것은 아니다.
σ=0/빔 제외/GT 좌표 치환은 원인 분해용 계산이며 실행 후보로 채택하지 않는다.

## P1 — dev06: loaded yaw 불확실성 초과, 5 cm 기준 문제가 아님

실제 [loaded gate](../../harness/zone_own_guards.py)(61–66행)의 HIGH는 **σxy 0.07 m / σyaw 3°**,
LOW는 **0.06 m / 2.5°**다. 0.05 m는 unloaded LOW 등 다른 기준이다.
HIGH 초과는 현재 행동을 즉시 막고, 0.6 s dwell은 이벤트 상태 전환 지연일 뿐 행동 허용 유예가 아니다.
`before_control`은 움직임 명령이 없는 `wait_lift`에서도 이를 검사한다(157–168행).

| r2 시점 | σxy (m) | σyaw (rad) | 의미 |
|---|---:|---:|---|
| 186.7 s grasp | 0.05702 | 0.02080 | load_state=unloaded, 마지막 태그 163.2 s |
| 189.1 s | 0.05736 | 0.02132 | commanded-close로 load_state=loaded 첫 보고 |
| 189.6 s wait_lift | 0.05736 | 0.02646 | 자기 RGB grip_view 통과 |
| 193.6 s | 0.05756 | 0.05185 | yaw HIGH 이하 |
| **193.7 s abort** | **0.05753** | **0.05238 = 3.00115°** | yaw HIGH 0.05235988 rad 초과 |
| 194.3 s 이벤트 | 0.0576 (4자리) | 별도 미기록 | dwell 뒤 `pose_uncertain`, ends_job=false |

요약의 `std_xy=0.0576`은 **중단 0.6초 뒤 알림**의 수치다. 중단 frame_id=1632의 XY σ는
LOW 6 cm보다도 작다. yaw를 제외하면 이 입력으로 loaded HIGH를 넘지 않는다.
따라서 위치 기준을 5→6/7 cm로 바꾸자는 처방은 실제 실패 조건을 고치지 못한다.

r2의 마지막 base motion은 185.7 s, duration 0.2 s다. wait_lift 중 새 base motion 없이 자기 RGB를
계속 처리했다. 평가에서 193.7 s 양 손가락 힘은 약 **5.480 / 5.493 N**, r1은 **0 / 0 N**이다.
r2 단독 파지는 관측됐지만 공동 파지·들기는 아니며 lift GO도 없었다.
자기 RGB `hold_ratio=1.00~1.04` 준비 보고가 189.7~193.2 s 이어져도 위치 gate는 별개다.

[LoadState](../../harness/owncam_localizer.py)(91–106행)는 측정 접촉이 아닌 닫힘 명령과 FK 높이로
loaded를 선택한다. 이때 `motion_loaded.noise_abs[yaw]=0.09762`가 기본 0.01406보다 약 6.94배 크고,
`predict_to`는 정지 명령에도 absolute noise를 넣는다(189–216행).
189.1→193.7 s 관측 yaw 분산 증가율은 약 0.000498 rad²/s이며,
단순 독립 0.05 s step 근사 `0.09762²×0.05=0.000476`과 비슷하다.
이는 **태그 없이 loaded process noise가 누적되는 경로**를 뒷받침한다. PF RNG 전체 재생이나
실제 정지 잡음의 적정성 검증은 아니므로 잡음을 임의로 줄여서는 안 된다.

## 공통 근본 원인: 관측 빈도가 아니라 관측 정보와 위치 추정의 연결

| 회차·로봇 | 마지막 태그 → 중단 보고 | 새 태그 없는 프레임 | 중단 XY 오차 / 보고 σ | 마지막 태그→grasp 추정 이동 / 실제 이동 |
|---|---|---:|---|---|
| dev05 r1 | 162.2 → 190.4 s | 282 | 0.759 / 0.05985 m | 0.883 / 0.158 m (5.60배) |
| dev05 r2 | 163.7 → 190.4 s | 267 | 0.887 / 0.05441 m | 0.972 / 0.154 m (6.31배) |
| dev06 r1 | 166.8 → 193.7 s | 269 | 0.703 / 0.05653 m | 0.829 / 0.158 m (5.23배) |
| dev06 r2 | 163.2 → 193.7 s | 305 | 0.949 / 0.05753 m | 1.038 / 0.158 m (6.59배) |

위 구간 프레임 간 최대 간격은 모두 약 **0.1 s**다. 영상 전송/캡처 공백이 아니며 **위치 추정을
갱신할 태그 정보가 사라진 것**이다. 가까운 inspect/grasp 자세에서는 영상이 빔·바닥·집게로 채워졌다.
overview 6장과 자기 카메라 8장(마지막 태그/중단)을 직접 추출·확인했다. 프레임 번호와 해시는 JSON에 있다.
추출본은 `/tmp`의 검토용이고 원본이나 평가 video 승인 상태를 바꾸지 않았다.

[M2DoorStudent](../../scripts/run_m2_pair.py)는 이미 낮춘 팔의 align 명령에서 기존 구동 자세용
dead reckoning이 과대예측될 수 있음을 설명한다(352–355행). 이번 기록도 태그 소실 후 이동 과대예측을
보이며, 실제 마찰/팔 하중/구동 지연 각각의 비중은 이번 분석만으로 분리하지 못했다.

더 직접적인 **통합 불일치**는 다음과 같다.

1. M2 v3는 arrival estimate + 자기 RGB 빔 변위로 `vo_pose`를 만든다(480–492행).
2. `vo_pose != None`이면 첫 grasp에서 `pregrasp_done=true`로 두고 `pregrasp_look`을 건너뛴다(494–503행).
3. 그 VO는 `grasp_estimate`에만 저장된다(537–553행). executor의 공통 PF/`own.last_report`를 갱신하지 않는다.
4. guard/gate는 계속 `own.last_report`를 읽는다. 따라서 M2와 안전 검사가 서로 다른 자기 위치를 사용한다.

실제로 네 로봇 기록 모두 `vo_pose` 이벤트는 있고 `pregrasp_look`은 없다.
파지 진입 시 VO의 사후 XY 오차는 dev05 r1/r2 **2.35/1.89 cm**, dev06 **2.58/2.42 cm**였다.
이는 후보의 근거일 뿐, VO를 covariance 없이 PF에 덮어쓰거나 어느 조건에서나 정확하다고 볼 근거는 아니다.
실제 XY 오차는 현재 보고 σ의 약 12.4~16.5배다. **σ 임계값 하나가 실제 위치 정확도를 보증하지 않는다.**

위치 5 cm 기준의 파지 적정성도 이 두 실패로 승인할 수 없다. 실제 loaded HIGH는 7 cm이며,
정적 clearance에는 `0.020 + 0.015 + 2σxy + 2σyaw×lever`가 별도로 들어간다.
임계값은 도구/빔 길이·가용 공간·시야와 함께 검증해야 한다. 더 느슨한 기준은 이미 큰 bias를
통과시키고, 5 cm로 더 엄격하게 하면 원인을 해결하지 않은 채 정렬을 일찍 중단시킬 수 있다.

## 수정 후보와 권고

모든 후보는 **자기 RGB·정적 지도/고정 보정·자기 명령**, 기존 승인된 고정 enum 상태 동기화만 사용한다.
peer 좌표·GT·접촉 판정을 넣지 않고 카메라 배치/FOV, weld OFF, cargo_noslip_v1을 유지한다.
아래는 구현/실행 전 제안이며 dev05/dev06 결과에 소급 적용하지 않는다.

| 후보 | 장점 | 단점·위험 | 예측 |
|---|---|---|---|
| **A. 파지 전 재관측으로 공통 위치 갱신 + 양쪽 준비 뒤 close (권고)** | 두 실패의 공통 PF bias/태그 공백을 겨냥. 기존 안전 sweep·localizer 재사용. gate 수치 유지 | 재관측 시간 추가, 근접 자세에서 tag 미획득 시 유한 실패 가능. 큰 drift가 생기기 전에 정렬 중 태그 age/자기 VO와 PF 불일치로 조기 중지해야 함. 이미 한쪽이 잡은 뒤 일방 sweep/backoff 금지 | 잘못된 위치의 가상 벽 침범과 먼저 잡은 로봇의 긴 wait_lift가 줄 것으로 예상. 태그 재획득 불가 시 grasp 전 명확한 실패로 이동 가능; 완주 미검증 |
| **B. 정렬 자세용 운동 모델 + 자기 RGB 변위 융합** | 5.2~6.6배 이동 과대예측을 지속적으로 줄일 수 있음. 기존 VO 수치는 개발 근거 | 자세/펄스별 calibration, VO covariance/anchor 편향 검증 필요. 빔이 실제 움직인 뒤 정지 물체로 가정하면 자기 위치를 잘못 보정함. σ 임의 축소 금지 | align drift 감소 예상. loaded 정지 yaw noise와 준비 시차는 남아 B 단독으로 dev06 해결 보장 못함 |
| **C. 접촉 전·파지 확인·정지 대기·운반의 guard 조건 분리** | 미파지 빔을 손목에 붙이는 모델 불일치와 stationary wait의 즉시 종료를 직접 다룸 | 바닥/부착 상태의 불확실성 영역도 자기 RGB로 보수적으로 검사해야 함. `grasp`에서 빔 guard 일괄 OFF, unloaded로 일괄 완화, timeout 동안 lift 허용은 위험. PF bias 자체는 남음 | 이번 거부 후보의 팔 단독 계산은 clear. 그러나 실패를 뒤로 미루거나 실제 위험을 숨길 수 있어 단독 비권고 |

**A를 먼저 권고한다.** VO 존재만으로 재관측을 생략하지 말고, guard가 읽는 동일 `own.pose/last_report`에
새 태그 관측을 반영해야 한다. 양쪽 각자 정렬·재관측·안전 조건을 만족한 뒤 동일 고정 STATUS 준비 절차로
close 시점을 맞추는 후보가 적합하다. 관측 횟수만 늘려 태그 없는 같은 자세를 계속 보는 방식으로는 부족하다.
재관측 sweep도 기존 전체 팔/벽 검사를 통과해야 하며, 실패하면 누적 예산 안에서 중단한다.
발행 hold를 실제 정지로 단정하거나 이전 위치를 무기한 동결해 불확실성을 없애서는 안 된다.

후속 비물리 검증은 태그 없는 low-σ/VO-only 진입 차단, 공통 보고 갱신, 한쪽만 준비된 GO 거부,
이미 잡은 상태의 일방 sweep 차단, 실제 문기둥/빔 충돌 반례 보존을 먼저 확인해야 한다.
물리 효과는 별도 소스 고정·새 사전등록·예산/잠금 뒤 **전체 경로와 예정 abort를 포함한 유한 dev**로
확인해야 한다. 여기서는 새 실행을 승인·시작하거나 성공을 예측 확정하지 않았다.

## 검증·저장·남은 작업

- 비물리 테스트: `test_zone_pair_review4.py`, `review5.py`, `review7.py` **65 passed / 5.00 s**.
  `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, `--basetemp=./.pytest_tmp`.
  pytest 시작 전 import hook으로 **mujoco/torch/tensorflow import 자체를 차단**했다. 잠금·물리·모델 호출 없음.
  `.pytest_tmp` 삭제 확인. 기존 충돌/높은 σ 차단/재관측 예산 회귀의 확인이며 수정 후보 검증은 아니다.
- 재구성: 원본 hash 16,926개, status 일치, frozen 소스 해시, hover 명령 prefix 65개,
  보고 반올림 32모서리 검사를 통과했다. rejected-command receipt가 원본에 없다는 한계는 위에 명시했다.
- TensorBoard: 두 실패의 `eval_only/result.json`을 원본 밖 임시 snapshot
  `/tmp/pair-v4-tensorboard-20260927`로 변환했다. EventAccumulator로 각각 성공=0, 명령=2098/1893,
  SIM·wall·model_calls=0의 **5개 scalar**, HParams와 `media/overview.mp4`를 읽었고 media registry **2개**를 확인했다.
  scalar float32 반올림만 있으며 source result 해시도 일치한다. 응답 시간은 호출 0이라 해당 없음이다.
- **공유 TensorBoard 게시·화면 검증 미완료:** 허용 쓰기 경로에 primary `outputs/`가 없어
  공용 snapshot/view 설정을 수정하지 않았다. [기존 대시보드 주소](http://127.0.0.1:6006)의 새 두 run 표시,
  baseline·HParams 열·핀·영상 HTTP 재생·viewer 소유권/logdir는 확인하지 않았다. 서버를 시작/종료하지 않았다.
  임시 변환 검증을 공유 대시보드 완료로 표현하지 않는다.
- Git: fetch는 공유 `FETCH_HEAD` 쓰기 제한, `gh pr list`는 네트워크 제한으로 실패.
  GitHub connector에서 [PR #235](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/235)
  open/draft와 head `4a17e7d4`를 읽어 확인했다. 커밋·push·PR 수정/댓글·병합·primary 갱신 없음.
- 이번 저장은 이 worktree의 진단 MD/JSON와 README뿐이다. UGRP 지침에 따라 Drive를 쓰지 않았고,
  로컬 raw 해시 확인은 원격 백업이 아니다. 원본·기존 실패 기록·사전등록·기존 snapshot은 보존했다.
