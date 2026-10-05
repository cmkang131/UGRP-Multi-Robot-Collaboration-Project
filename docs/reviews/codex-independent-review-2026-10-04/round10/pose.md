# 현재 #363의 uncertainty 분기: 제어 경계와 기록으로 판별 가능한 범위

현재 공개 `SELF_UNCERTAIN`/`POSE_UNCERTAIN`은 하나의 σ 초과 원인을 뜻하지 않는다. 입장은 이력이 있는 gate 상태를, carry 제어는 현재 σ·유효 pose·gate 상태를 함께 본다. **먼저 실제 실패 predicate를 구분해야 하며, threshold 조정이나 PF 원인 단정은 그 다음에도 별도 증거가 필요하다.** 이 검토는 공개 기록과 정확한 소스로 가능한 구분을 정리하고 합성 분기 23개로 확인했다. 새로운 물리 실행·모델 호출·raw/held-out 열람·제어 코드 변경은 없다.

## 1. 고정한 코드와 현재 적용 범위

- 공식 #363 재확인: `2026-10-04T07:00:58.038Z`, head `de03fe87d08879abefaa7dac67c7ff313df5df89`, PR updated `2026-10-04T06:47:46Z`.
- 앞서 검토한 소스는 `6727751b49ce11fb62234bb97274137f22850765`. 공식 비교상 672→de03는 실험 README +27줄뿐이다. `../round9/frontier-de03-doc-only.json` (Mac 전달본 증거), [공개 단계 결과 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/experiments/2026-10-03-pair-carry-highpose/README.md).
- 실행 계보: highpose `Execution` → final `Execution` → `PairExecution`. final 생성자가 `policy='b-v6g'`를 명시한다. 이 정책은 `beam_relative=False`다. 따라서 아래 carry 표는 **이 현재 정책의 비상대 pose 경로**에 한정한다. 다른 `a+b` 상대 조작의 envelope/certificate 우회 분기를 여기에 합치지 않는다.
- `zone_final_pair_guards.py:19`에는 yaw 5°/4°의 `LOADED_GATE` 상수가 있고 일부 함수 globals에 바인딩된다. 그러나 현재 `before_control`/`check`는 `self.loaded_profile`을 읽으며, 그것은 `b-v6g.loaded_gate_yaw_deg=None`에서 기본 3°/2.5°로 만들어진다. 합성 검증은 **실제 initializer의 해당 assignment**를 그대로 실행해 3°를 확인했다. 5°가 의도된 요구사항인지 확인하지 않았으므로 이를 새 안전 버그나 5°로 변경할 근거로 세지 않는다. 기록의 `b-v6h1-v3-highpose-opencv` 이름만으로 effective threshold를 추정하지 말아야 한다.

근거: `harness/zone_pair_highpose_runtime.py:394–428`, `zone_final_pair_skill.py:227–253`, `zone_pair_v6_policy.py:29–153`, `zone_pair_guards.py:209–243`, `zone_final_pair_guards.py:19,99–120`.

## 2. 숫자와 상태의 정확한 뜻

| 값/상태 | 현재 계산/규칙 | 해석 경계 |
|---|---|---|
| σxy | `sqrt(max(cov[x,x]+cov[y,y], 0))` | x 또는 y 한 축의 σ가 아니다. 위치 오차의 관측값이나 보정된 coverage도 아니다. |
| σyaw | `sqrt(max(cov[yaw,yaw], 0))` | 단위 rad. 실제 yaw 오차 측정이 아니다. |
| unloaded HIGH | xy > 0.08m **또는** yaw > 0.10rad | HIGH와 같은 값은 high가 아니다. |
| unloaded LOW | xy ≤ 0.05m **그리고** yaw ≤ 0.06rad | uncertain에서 이 두 조건이 0.4초 유지돼야 ok로 복귀한다. |
| loaded HIGH | xy > 0.07m **또는** yaw > 3° | 현재 carry에서 즉시 중단하는 high 비교다. |
| loaded LOW | xy ≤ 0.06m **그리고** yaw ≤ 2.5° | uncertain→ok 복귀는 0.4초 dwell. |
| 초기 gate | uncertain | LOW 복귀 확인 없이 중간 band라는 이유만으로 열리지 않는다. |
| ok→uncertain | HIGH가 0.6초 유지 | **동작 허용 유예 시간이 아니다.** `allows`와 carry guard가 현재 HIGH를 즉시 막는다. |
| 중간 band | HIGH도 LOW도 아님 | 기존 gate 상태를 유지하며 진행 중 후보 dwell은 취소한다. |
| profile 변경 | profile과 candidate_since만 변경 | 기존 state/since/last_update를 그대로 보존한다. |
| `uncertainty_level=medium` | initialized·finite이고 xy ≤ 0.08m, yaw ≤ 0.10rad; low 기준 초과 | loaded 안전 허가가 아니다. 70.001mm 또는 3.0001°는 medium이면서 carry 실패할 수 있다. |

Gate는 프레임이 전달된 `now`로 업데이트된다(`ZoneOwnExecutor.on_frame → _update_gate`). 보고서의 `t_est`는 지연 추정 시각일 수 있다. 둘을 섞지 않는다. `pose_report_fresh`는 `−0.0001 ≤ now−t_est ≤ 0.3001`이며, fix age와 다른 시계다. admission의 observation freshness는 별도로 `0 ≤ now−obs.sim_time ≤ 0.3`이다. 이후 이미지 validator에는 더 엄격한 0.25초 조건이 있다.

근거: `owncam_localizer.py:517–532`, 실제 상속의 `vision_pose_source_pair_v3.py:15–38,61–76`, `vision_motion_init.py:12`; `zone_own_guards.py:51–146`; `m1_owncam_delivery.py:54–59`; `owncam_drive_v2.py:26`; `zone_own_status.py:19–43`; `owncam_time.py:4–16`; `zone_pair_highpose_frame_gate.py:52–80`.

## 3. 입장 SELF_UNCERTAIN의 fault tree

`readiness_snapshot`의 실제 우선순위는 stopped → busy → 주문 비호환 → uncertain → invalid_image → occupied/available이다. 단순히 같은 tick의 여러 문제를 모두 첫 원인으로 표시하지 않는다.

| 도달 분기 | predicate | 기존 입장 receipt에서 보는 값 |
|---|---|---|
| uncertain: 실행 상태/초기화 | mode가 m1이 아님, report가 없거나 uninitialized | `checks.mode_m1/report_present/report_initialized` |
| uncertain: gate 이력 | `gate.ok == False` | `checks.gate_ok`, gate state/profile/thresholds/candidate_since/last_update/since, report classification |
| uncertain: report 시각 | report freshness 실패 | `checks.report_fresh`, report.t_est/age_s |
| uncertain: 숫자 | σxy 또는 σyaw 비유한 | 해당 finite check와 report σ; JSON에서는 비유한 값이 null |
| uncertain: 관측/명령 상태 | observation 없음/age 범위 밖/servo 1,3,4,5,6 누락 | 해당 checks, observation frame/time/age, missing_servo_ids |
| invalid_image | 앞 uncertain checks 모두 통과했지만 validator 실패 | `checks.image_valid`; 시간/JPEG/shape/dark/contrast 세부 원인은 이 receipt만으로 분리되지 않음 |
| available | 위 조건을 통과하고 holding answer가 no | 상태 available. 현재 σ HIGH 여부를 여기서 다시 직접 비교하지 않음 |

입장에는 `gate.ok`와 σ 유한성만 있으며 `gate.allows()` 또는 `classification != high`라는 직접 조건은 없다. 실제 합성 결과에서 같은 65mm/2° 보고서는 이전 gate가 uncertain이면 거부, ok이면 available이다. 현재 49mm여도 LOW dwell이 아직 없으면 거부되고, 0.4초 LOW 이력을 주면 통과한다. 현재 81mm라도 기존 gate가 ok인 HIGH 진입 dwell 중에는 available이 가능하다. 후속 command guard가 현재 HIGH를 별도로 막으므로 **입장이 곧 높은 σ로 이동했다는 증거는 아니다.**

따라서 공개 r2 65.2→78.5mm와 101회 SELF_UNCERTAIN을 “매번 직접 50mm 상한을 비교해 거부했다”고 압축하면 실제 이력 조건을 잃는다. 공개 수치는 LOW 복귀에 못 미친 설명과 양립하지만, 실제 receipt를 읽지 않은 여기서는 각 tick의 failed_checks가 gate 하나였다고 확정하지 않는다. 또한 101은 요청/거부 횟수이며 accepted measurement, 독립 view, PF update 횟수가 아니다.

`fix_age_s`·`last_fix_t`는 admission에서 설명용이며 추가 admission threshold가 아니다. fresh report와 오래된 fix는 동시에 가능하다. `Runtime.step`은 시작 때 look 한 번을 요청한 후, 미제출 idle actor의 입장 요청을 반복한다. 이 거부 경로 자체가 새 look를 예약하지는 않는다. 이는 #363 scripted runtime 범위이며 #371의 모델 정책이 별도 look를 요청하는 경우에 확장하지 않는다.

근거: `zone_pair_admission.py:7–67`, `zone_own_executor.py:249–261`, `zone_pair_executor.py`의 `PairTeam.start`, `zone_final_pair_runtime.py:56–75`.

## 4. 현재 carry POSE_UNCERTAIN의 fault tree

`PairExecution.step`은 local/peer/timeout 확인 → 이미지 gate → 시작/rendezvous → 필요하면 fresh capture 요청 → `before_control` → controller tick → `check(commands)` 순서다. 이미지가 먼저 invalid면 `INVALID_OWN_IMAGE`가 되므로 모든 오래된 입력을 POSE_UNCERTAIN으로 묶을 수도 없다.

현재 비상대 carry의 `before_control`은 loaded profile을 선택하고 `_pose(now)`를 구한 뒤 아래 OR로 abort한다. `OwnPose.from_report`는 initialized뿐 아니라 x/y/yaw/σxy/σyaw 모두의 유한성을 요구한다.

| 같은 POSE_UNCERTAIN을 내는 carry 원인 | 실제 분기 | 최소 판별값 | 현재 writer의 한계 |
|---|---|---|---|
| report 없음/미초기화/비유한 pose | `_pose is None` | report presence/initialized, x/y/yaw와 두 σ의 유한성 | 실패 사건에 full report를 자동 추가하지 않음 |
| report stale | `_pose is None` | now와 report.t_est | 실패 reason만으로 복원 불가 |
| gate 이력상 uncertain | `not own.gate.ok` | state/profile/candidate_since/last_update와 직전 프레임들 | 현재 σ가 LOW/band여도 가능 |
| 현재 xy HIGH | `_high: std_xy > profile.high_xy` | σxy·σyaw·effective thresholds | yaw HIGH와 같은 reason; 단일 원인 선택 불가 |
| 현재 yaw HIGH | `_high: std_yaw > profile.high_yaw` | 위와 같음 | 공개 실패 tick의 두 σ가 없으므로 실제 축 미식별 |

후속 `check(commands)`에도 pose/high/gate 검사가 있다. reobserve의 이동 중·잘못된 command, base motion에서 gate가 닫힘 등은 다른 세부 분기로 같은 reason을 낼 수 있다. 다만 이번 공개 `carry` 단계에서는 위 `before_control` 경로를 우선 확인한다. reobserve 중 carrying beam이면 별도 `PAIR_RELOOK_WHILE_GRIPPED`, 진행 미확인에서 `POSE_UNCERTAIN_PROGRESS`, 충돌 guard에서 `PAIR_COLLISION_GUARD`로 구분된다.

합성 9개 carry 대조에서 정상 band와 HIGH와 정확히 같은 경계(70mm, 3°)는 통과했고, xy HIGH·yaw HIGH·low지만 gate uncertain·stale·report 없음·비유한 x는 모두 POSE_UNCERTAIN이었다. fresh/valid/low이고 gate ok이면 accepted fix가 없다는 사실만으로 이 `before_control` 분기가 거부하지도 않는다. 이것은 fixed contract의 분리이며 fresh fix가 항상 필요하다는 새 요구를 넣을 근거가 아니다.

근거: `zone_pair_executor.py:310–408`; `zone_pair_guards.py:503–525,559–561,619–686,704–797`; `zone_own_guards.py:252–255`.

## 5. 기록의 구멍과 가장 작은 다음 판별

`_update_gate`가 uncertain **전이**를 기록할 때 level/profile/σxy만 포함한다. `_fail('POSE_UNCERTAIN')`은 level/profile/reason을 기록하며 양 σ나 결정 predicate를 넣지 않는다. 단순 `check`/`before_control` abort에는 충돌 geometry의 상세 veto 기록이 따라오지 않는다. 따라서 de03 공개 “거부 때 σ 값은 없다”는 한계를 종료 집계로 채워 넣을 수 없다.

별도 look 완료 진단에도 범위가 있다. `_step_look_around`는 `gate.allows AND accepted_fix_checks`를 성공 조건으로 삼지만, 실패 때 `failed_checks`는 **accepted_fix_checks의 실패만** 나열한다. 합성에서 fresh하고 sweep 안의 accepted fix가 있어도 gate가 uncertain이면 `LOOKED_POSE_UNCERTAIN, level=medium, gate=uncertain, failed_checks=[]`가 나온다. 반대 대조에서는 같은 valid fix+gate ok가 LOOKED, 오래된 fix만 넣으면 `failed_checks=['fix_in_sweep']`였다. 빈 목록을 “실패 predicate 없음”으로 읽으면 안 된다. 함수가 목록을 모든 guard의 완전한 설명이라고 보장하지는 않으므로 여기서는 새 제어 결함으로 집계하지 않는다.

기존 admission receipts가 있으면 추가 실행 없이 checks → gate history → report/fix/frame time 순서로 판별할 수 있다. carry 실패에 같은 tick의 상태가 없으면 현재 공개 자료로는 미식별이다. 향후 진단이 필요할 때 최소 후보는 **이미 제어기에 존재하는** 다음 상태를 private audit receipt로 함께 남기는 것이다. 이를 STATUS/모델 입력으로 추가할 필요는 없다.

1. now, phase, 직접 거부한 predicate, gate state/effective profile/candidate_since/last_update.
2. report.t_est/initialized, σxy/σyaw, 필요한 유한성 booleans, last_fix_t/fix_age.
3. 소비한 own frame 식별자와 capture/available/consumed 시각을 구분한 연결.
4. 이번 scan의 quality와 마지막 성공 fix quality를 구분하고, 누적 counts만 있는 경우 관측 갱신 수와 informative fix 수를 혼동하지 않기.

4번의 정확한 수치 갱신과 receipt 차이는 [scan-receipt-semantics.md](vision.md)의 독립 actual-source fixture가 보완한다. weak scan은 PF weight/covariance를 갱신해도 informative=False여서 fix clock이 그대로일 수 있다. 원인 가설의 순서와 각 가설을 약화시키는 대조는 [uncertainty-diagnostic-map.md](research.md)에 정리했다. sigma 증가만으로 model bias/관측 누락/기하 모호성을 서로 구분하지 않는다.

## 6. 재현과 판정

```bash
python uncertainty-fault-tree-repro.py --repo /path/to/UGRP-Multi-Robot-Collaboration-Project
```

clone에 de03 commit이 있어야 하며 checkout은 바꾸지 않는다. `uncertainty-fault-tree-repro.py` (Mac 전달본 증거)는 정확한 Git blob에서 AST를 추출해 원래 predicate 메서드를 실행한다. 무거운 vision/geometry 초기화와 이미지 validator는 명시적 fake port이고, 실제 이미지를 검증한 것으로 세지 않는다. actual b-v6g policy와 loaded_profile initializer assignment, gate, admission, `_pose`, `before_control`, look 종료 predicate는 원문이다.

`uncertainty-fault-tree-result.json` (Mac 전달본 증거): admission 11 + carry 9 + look 3 = **23개 분기/대조**, 모든 assertion 통과, source SHA-256 포함. 이는 결정 분기의 도달 가능성과 기록 의미 검증이며 de03 실패 시계열 재생이나 실제 pose error 확인이 아니다. 신규 제어 안전 버그 수를 늘리지 않았다. 이번 결과의 실용적 산출물은 현재 실패를 더 작은 원인 집합으로 줄이는 fault tree와, 지금 기록으로는 결정할 수 없는 경계다.
