# pairact P2: MJWarp GT 공동 운반·하차 경로 설계 (2026-10-21)

계획 근거: `outputs/reports/claude-arch-parallel-20261019/pair-act-carry-plan.md` §1 P2, `carry-place-owner-plan-v1.md` §B1-2(B-b).
브랜치: teacher `dsh/pairact-p2-carrypath`(base `376c006f1` = `claude/beamact5-r2-t` 끝, `.py`는 r13 teacher `fe6858ec`와 동일), adapter `dsh/pairact-p2-carrypath-a`(base r13 adapter `d354468a`), root `dsh/pairact-p2-carrypath-r`(base r13 root `05046e9d`). 실행 방법은 root 브랜치의 `SMOKE.md`를 봅니다.

## 0. 범위와 금지

- 교사(teacher)는 *시연 생성 전용*이라 GT를 씁니다(계획 P2의 시연 예외). 학생 입력으로는 절대 들어가지 않습니다.
- 공동 파지는 바꾸지 않습니다. r13 프로필(`beamact5_r13`)이 `joint_held`(양쪽 손가락 접촉 ≥ 0.5, 빔 최저점 ≥ 0.012 m, 기울기 ≤ 10°가 3 SIM s 유지)에 도달한 바로 그 tick에서 운반 교사가 넘겨받습니다(handover).
- 새 모드는 모두 *기본 off*입니다. `--pair-carry pair_carry_gt_v1` 또는 adapter 후보 `pairact_p2_r13`일 때만 켜집니다. off면 runner 동작은 바이트 단위로 기존과 같습니다(기존 runner 테스트 280개 통과).
- 학습 기록(`record_training`)과 운반을 함께 켜면 P3 recorder가 운반 구간을 기록합니다(§7, 2026-10-21 배선). 기록은 기존 recording proof(≥38/40 관문) 조건을 그대로 요구합니다.
- `Params`의 거리·속도·시간 값은 모두 *새 P2 후보 상수*이고 측정값이 아닙니다. smoke가 처음 측정합니다.
- CPU 결과(beampair7 40/40, b-v6e 13/13)와 합산하지 않습니다.

## 1. 지도 (maps/zones_final_v3/zone_wide_two_doors_final_v3.json)

| 항목 | 값 |
|---|---|
| door_wide | x = 2.2, y ∈ [−3.125, −2.125] (폭 1.0 m). 남쪽은 `wall_south` 안쪽 면, 북쪽은 `wall_divider_1` 끝 |
| zone_B | x ∈ [4.3, 4.9], y ∈ [−2.8, −1.4] (0.6 × 1.4 m) |
| 빔 footprint | 0.60 × 0.04 m (`sim/zone_cargo.py` `beam_len`, `HANDLE_WIDTH_M`) |
| 로봇 계획 원 | 반지름 0.17 m (기존 교사의 계획 원과 같은 값) |

zone B 폭 0.6 m와 빔 길이 0.6 m가 같으므로 *빔을 zone 장축(y)에 맞춰야만 여유가 생깁니다*. 빔을 x축으로 두면 오차 0일 때만 안에 들어갑니다(테스트 `test_zone_b_long_axis_is_the_only_slack_orientation`).

지도 연결(코드 확인): adapter의 v7 scenario(`experiments/2026-10-15-beampair1/scenario-v7.json`)는 `map_id = zone_wide_two_doors_final_v3`이고, `ScenarioFinalV3Scene`(→ `FinalV3Scene._resolve`)이 `scene.config['static_map']`를 `harness.zone_final_environment.resolve(map_id)` 결과로 둡니다. 이 결과는 위 지도 파일과 같고 `passages`·`regions`를 담습니다(테스트 `test_static_map_resolves_to_the_wide_door_map`). 없으면 `static_map_for()`가 `NotImplementedError`로 멈춥니다(다른 지도를 조용히 쓰지 않음). 실제 실행 값은 smoke의 `carry.route_info`로 확인합니다.

## 2. 상태기계 (harness/pair_carry_teacher_warp.py)

하나의 GT 감독자가 두 로봇을 같은 clock으로 움직입니다. 그래서 두 로봇 동기는 구조적으로 맞습니다(peer 메시지는 이 교사에 모델링하지 않습니다).

| 단계 | 하는 일 | 끝나는 조건 | cap(SIM s) | 실패 코드 |
|---|---|---|---|---|
| (init) | handover 자세에서 두 로봇의 빔 기준 오프셋 고정, 경로 계산, 경로 GT 검사 | — | — | `arm_targets_missing`, `staging_unclear`, `door_clearance_insufficient`, `zone_unreachable`, `route_blocked` |
| carry_hold | 들어 올린 자세(lift PWM) 유지 | 1.0 s 동안 hold 유지 | 4 | `carry_hold_lost` |
| to_west_staging | 빔 yaw 유지한 채 서쪽 대기점(문 평면에서 0.95 m)까지 | 가상 자세 도착 + 두 로봇 추종 오차 ≤ 0.04 m·6° | 40 | `west_staging_timeout` |
| rotate_door | 제자리 회전으로 빔을 문 축(x, 0 또는 π 중 가까운 쪽)에 맞춤 | 같음 | 20 | `rotate_door_timeout` |
| to_door_entry | 문 중심선(formation 횡폭 기준 중앙)에서 문 평면 0.75 m 앞 | 같음 | 25 | `door_entry_timeout` |
| door_pass | 문 축을 따라 문 평면 0.75 m 뒤까지 직진 | 같음 | 30 | `door_pass_timeout` |
| to_east_staging | 동쪽 대기점(회전 원이 벽과 0.05 m 이상 떨어진 첫 점) | 같음 | 30 | `east_staging_timeout` |
| rotate_zone | zone B 장축(y)으로 회전 | 같음 | 20 | `rotate_zone_timeout` |
| to_zone | zone B 중심까지 | 같음 | 30 | `zone_approach_timeout` |
| zone_settle | *실제 GT 빔 자세* 잔차로 가상 목표 보정 | 빔 중심 오차 ≤ 0.03 m, yaw ≤ 4°, footprint가 zone 안(0.02 m 안쪽) | 8 | `zone_align_timeout` |
| lower | 두 팔이 같은 clock으로 lift → place(잡은 높이) smoothstep 1.6 s | 1.6 s + 0.3 s settle | 4 | `lower_timeout` |
| open | 집게만 1500 → 2000 (0.8 s) | 0.8 s + 0.3 s | 2 | `open_timeout` |
| raise | open → hover(0.095 m) 1.0 s | 1.0 s + 0.3 s | 3 | `raise_timeout` |
| retreat | 두 로봇이 자기 −x(빔 반대쪽)로 0.06 m/s, 0.15 m | 둘 다 0.15 m → `retreat_complete`. 벽 0.03 m 앞 검사에 걸리거나 4 s → `retreat_bounded`(성공 판정과 무관, b-v6e와 같은 처리) | 5 | `retreat_timeout` |

### 2-1. 하강 목표 옵션 `floor_contact_v1` (기본 off, 2026-10-21 추가)

- 기본값 `lower_mode = grasp_height`는 위 표 그대로입니다(동작 변화 0, 기존 테스트 그대로 통과).
- `floor_contact_v1`(runner `--carry-lower floor_contact_v1`, adapter 후보 `pairact_p2_r13_floor`): lift → `place_deep`(잡은 높이보다 `place_deep_m` 0.025 m 아래로 같은 IK) 을 `lower_max_s` 4 s 동안 같은 smoothstep으로 내립니다. *GT 빔 최저점 ≤ `floor_margin_m` 0.004 m*가 0.2 s 유지되면 그 자리에서 두 팔을 멈추고(`floor_touch` 이벤트, 그 PWM을 `floor_touch_pwm`에 기록), 0.3 s 뒤 그 자세에서 집게만 엽니다.
- 4 s 안에 닿지 않으면 `lower_no_floor_contact`로 끝냅니다. 공중에서 열지 않습니다. lower 단계 cap은 이 모드에서 `lower_max_s + 1` = 5 s입니다.
- 0.004 m는 evaluator의 rest 기준 0.006 m보다 작게 잡은 *새 후보 상수*입니다. `place_deep`이 IK 작업 공간 밖이면 IK가 자르거나 실패할 수 있습니다 [확인 필요, gcp6 smoke].
- 이유: 기본 모드는 운반 중 빔이 손가락 안에서 미끄러졌을 때 바닥 위에서 집게를 엽니다(테스트 `test_default_lower_mode_is_grasp_height_and_unchanged`: 6.9 mm 위에서 열림). 바닥 접촉 모드는 같은 조건에서 0.004 m 이내에서 엽니다(`test_floor_contact_lowering_stops_at_touch_and_places`).

운반 중 공통 감시(carry_hold ~ zone_settle): hold(양쪽 접촉 ≥ 0.5 ∧ 최저점 ≥ 0.012 m) 끊김 0.5 s → `carry_hold_lost`; 로봇 간 거리 변화 > 0.08 m 1 s → `formation_stretch`; 추종 오차 > 0.15 m 3 s → `formation_tracking_lost`; 전체 운반 110 SIM s → `carry_total_timeout`. 정상 종료는 `command_sequence_complete`입니다. 교사 outcome은 *참고용*이고 성공 판정은 §5 evaluator만 합니다.

경로 계획: formation-space planner는 없습니다. 위 7개 직선 구간(자세 선형 보간)을 0.05 m 간격으로 GT 검사합니다(로봇 원·빔 모서리 vs 벽, 로봇 원 vs 다른 물체·대기 로봇 r3). 처음 구간이 막히면 *단 하나의 대안*인 "handover 지점에서 먼저 문 축으로 회전한 뒤 이동"을 검사합니다. 둘 다 막히면 `route_blocked`로 끝내고 우회하지 않습니다. 어느 쪽을 썼는지 `route_info.variant`에 남깁니다.

## 3. 협조 주행 (빔 길이 구속, 속도 상한)

- 가상 빔 자세를 하나 두고, 매 0.1 s tick마다 목표 쪽으로 최대 `v_max` 0.08 m/s, `w_max` 0.25 rad/s만큼 전진시킵니다. 이동과 회전이 같은 비율로 끝나도록 맞춥니다.
- 각 로봇 목표 = 가상 빔 자세 ∘ handover 오프셋. 로봇 명령 = 강체 속도 feed-forward + P 제어(k_xy 1.5/s, k_yaw 1.2/s), 로봇당 0.10 m/s·0.35 rad/s 상한. 출력은 기존 교사 `_continuous`와 같은 환산(전진·횡 ×3, 회전 ×0.65 → `duty_wheels`, 14차원 명령 v5 형식)입니다.
- *빔 길이 구속*: 두 로봇 중심 거리 d12가 handover 값에서 0.03 m 넘게 변하면 가상 자세 전진을 멈춥니다(로봇은 현재 목표로 계속 수렴). 0.08 m 초과가 1 s 지속되면 실패입니다. 두 로봇 중 하나라도 추종 오차 0.04 m·6°를 넘으면 역시 멈춥니다. 그래서 한 로봇이 밀리면 다른 로봇이 앞서 나가 빔을 당기지 않습니다.
- [확인 필요] 듀티 펄스 명령(속도 35, 폭 ≤ 0.1 s)에서 빔을 든 두 로봇의 실제 몸체 속도는 측정 기록이 없습니다. 0.08 m/s보다 느리면 가상 자세가 자주 멈춰 느려질 뿐 안전 쪽이고, 그 경우 cap에 걸리면 단계 코드로 드러납니다.
- *측정 배선(eval-only, 2026-10-21)*: `pair_carry_eval.drive_response()`가 매 tick 교사가 낸 몸체 명령(fwd, left, turn)·바퀴 듀티·펄스 폭을 다음 tick의 GT 자세 차분(몸체 좌표 속도)과 짝지어 단계별·로봇별로 집계합니다: `cmd_speed_mps`, `gt_speed_mps`, `gt_along_cmd_mps`, `speed_ratio`, `turn_ratio`, `wheel_duty_abs_mean`, `pulse_width_s_mean`, `stall_ticks`(GT 속도 < 명령의 25%). 결과는 `carry-eval.json`의 `drive_response`에 `affects_success = false`, `affects_phase_timeout = false`로 남습니다. 교사·evaluator 판정·단계 timeout은 이 값을 읽지 않습니다.
- `phase_report`는 단계별 소요·cap·교사 timeout 코드(교사 events에서만)와 같은 단계의 drive 집계를 *나란히* 둡니다. timeout 여부는 교사 events만으로 정하고, drive 값은 원인 해석용입니다(예: `door_pass_timeout`이면서 `speed_ratio` 0.3이면 몸체 속도 환산 문제 쪽).

## 4. 문 정렬·통과 기하 (handover 오프셋 ±0.5 m 가정 시 계산값)

- 문 축 방향 formation 횡폭 = 로봇 원 0.34 m(빔 0.04 m는 그 안) → 필요 폭 0.34 + 2×0.05 = 0.44 m < 1.0 m. 중앙선 y = −2.625.
- 서쪽 대기점 (1.25, −2.275): 회전 원 반지름 0.67 m(+0.05 m)가 남쪽 벽과 떨어지도록 y를 0.05 m 간격으로 올려 찾습니다. 동쪽 대기점 (3.15, −2.375)도 같은 방식입니다.
- 문 진입 x = 1.45, 통과 후 x = 2.95(빔 중심). 앞 로봇 원 앞 끝 2.12 < 2.175(벽 서쪽 면), 뒤 로봇 원 뒤 끝 2.28 > 2.225(벽 동쪽 면). 즉 통과 구간 동안 문 안에는 로봇 원과 빔만 있고 벽 끝과 겹치지 않습니다.
- 실제 오프셋은 handover에서 GT로 정하므로 위 수치는 달라질 수 있습니다. 실행 시 값은 `result.json` → `carry.route_info`(passage 폭, 대기점, formation 반지름)에 기록됩니다.

## 5. 사전 등록 성공 기준 (harness/pair_carry_eval.py, eval-only)

판정 입력: runner가 매 tick 쓰는 eval-only GT 행(`snapshot()`: 빔 자세·최저점·기울기·끝점, 로봇 자세, 손가락 접촉력)과 교사의 lower 시작 시각(운반/하차 경계)만 씁니다. 교사 outcome은 쓰지 않습니다.

*성공 = placed_in_zone_B ∧ drop_events = 0 ∧ robot_robot_contacts = 0*

- placed_in_zone_B: 마지막 행에서 빔 footprint 4모서리가 모두 zone B 안 ∧ 최저점 ≤ 0.006 m ∧ 기울기 ≤ 5° ∧ 양쪽 집게 접촉 < 0.5(해제) ∧ 마지막 1 s 동안 빔 이동 ≤ 0.005 m·1°(정지). runner는 교사 종료 후 1.5 SIM s 수동 행을 더 남겨 정지를 판정할 수 있게 합니다.
- *낙하 감지(eval-only)*: ①운반 구간(handover ~ lower 시작) 최저점 < 0.012 m가 0.3 s 지속(`carry_low`) ②전 구간 기울기 > 30°(`tilt`) ③전 구간 빔 중심 하강 속도 > 0.25 m/s(`fall`, 계획된 하강 1.6 s는 약 0.02 m/s). 셋 중 하나라도 있으면 낙하입니다.
- 로봇 간 접촉: 두 로봇 원(0.17 m) 겹침 tick 수. 0이어야 합니다.
- 벽 접촉: 로봇 원 vs 벽, 빔 사각형 vs 벽(양방향 모서리 검사)을 *기록만* 합니다(tick 수, 첫 시각, 몸체). 실패 항목이 아닙니다.
- 접촉 출처: 기본은 GT 기하 proxy(`contact_source = gt_geometry_proxy_v1`). MJWarp native 접촉 행은 아직 배선하지 않았습니다(§8).
- 퍼널(0/N이어도 어디까지 갔는지): handover → 1 m 이상 운반 → 문 통과(두 로봇과 빔 중심이 문 평면 +0.2 m 넘음) → 최종 zone 안 → 내려놓음 → 해제 → 1 s 정지.
- 실패 코드 우선순위: `drop` > `robot_robot_contact` > `not_through_door` > `not_in_zone` > `not_resting` > `not_released` > `not_still`.

## 6. 시간 상한

- 파지 구간 cap은 기존 그대로 60 SIM s(r13 gate와 같음). handover 뒤 운반 구간에 `carry_cap_s` 110 SIM s를 더합니다(runner 루프 상한 = 60 + 110, 0 < carry_cap_s ≤ 120 강제). 교사 내부 `carry_total_timeout`도 110 s입니다.
- 단계 cap 합(221 s)은 전체 cap보다 크며, 전체 cap이 우선합니다.
- 공칭 소요 추정: 이동 약 4.6 m / 0.08 m/s ≈ 57 s + 회전 약 8 s + 정렬·팔 동작·후진 약 10 s ≈ 75 s. [확인 필요] 추종 정지가 잦으면 더 깁니다.
- root runner(`run_warp_flow_teacher.py`)는 lane이 끝날 때까지 돌고 tick 예산이 없으므로 이 연장과 충돌하지 않습니다. `--cap-s`는 60으로 둡니다(root는 ≤ 180, adapter가 runner에 그대로 전달).

## 7. Recorder (P3, 2026-10-21 배선, 기본 off)

`harness/pair_carry_recorder.py`. `record_training`과 `pair_carry`를 *둘 다* 켤 때만 운반 tick에서 기록합니다(이전의 fail-closed 거부는 없앴습니다). 둘 중 하나라도 off면 기존 동작 그대로입니다. 형식은 beampair8 `dataset-v1` raw와 *같은 파일·같은 키*입니다.

- `student-{rid}.jsonl`: `ugrp.grasp_act.student.v5` 행. 키는 `harness/grasp_act_contract.py` FIELDS와 정확히 같습니다: 자기 RGB 참조 4장(5.2/1.5/0.5/0 s 전), 자기 발행 명령 16개, 번호표 토큰(skill `release`, object_kind `long_beam`, role `teal|blue`, destination_zone `B`), 자기 명령 시계(skill_elapsed_s, pwm_elapsed_s). 상대 로봇 정보·GT·접촉은 없습니다. 운반 tick도 파지 tick과 같은 순서(관측 기록 → 교사 명령)입니다.
- `teacher-{rid}.jsonl`: `carry_label()` 행(clean/applied 명령, done, `teacher_phase = carry:<단계>`, `segment = pair_carry_gt`, `teacher_input = simulator_truth_demo_exception`). `local_skill_sample`은 *첫 `done=true` 행까지만* true이고, 교사 종료 뒤 1.5 s 수동 행은 false입니다.
- *시계(v7)*: pair_carry가 켜지면 runner의 로봇별 시계가 `DeadbandIssuedClock(2)`가 됩니다(`harness/pairact_r1.py`, act18 C2c `ac274afeb`와 같은 규칙: 직전 관측 PWM 대비 |Δ| ≤ 2는 `pwm_elapsed_s`를 리셋하지 않음). *같은 시계 객체*를 파지 구간과 운반 구간이 같이 씁니다. 그래서 운반 첫 행에서 `skill_elapsed_s`는 0으로 리셋되고 `pwm_elapsed_s`는 이어집니다(배포된 학생과 같음). deadband 0이면 계약 `IssuedClock`과 같습니다(테스트). `result.json → carry_recording`에 `issued_clock = v7_issued_clock_deadband_2`, `issued_clock_deadband = 2`, 로봇별 리셋 횟수를 남깁니다. pair_carry off 실행의 시계는 바뀌지 않습니다. `skill_elapsed_s`는 v6·v7이 같으므로 교사의 `skill_started` 동작도 바뀌지 않습니다.
- *성공 필드*: pair_carry 실행에서 `grasp_physical_success`(기존 파지 관문 정의)와 `carry_success`(evaluator)를 따로 남깁니다. `physical_success`는 smoke(기록 off)에서는 기존 파지 정의 그대로이고, *기록 on(P3)에서만* `grasp ∧ carry`가 됩니다(COLLECT_SPEC §5, `grasp_act_data.convert`의 admission). 그래서 root summary의 `success`는 smoke에서 파지 관문, P3 수집에서 시연 admission을 뜻합니다.
- 16개 명령 이력은 파지에서 운반으로 끊기지 않습니다(runner의 같은 deque). beampair8 변환기는 (robot_id, skill, object_kind, role, destination_zone)로 구간을 나누므로 파지(`grasp`, `none`)와 운반(`release`, `B`)이 같은 로봇 스트림의 연속된 두 구간이 됩니다.

### 7-1. teacher_phase → pairact-r1 단계 head 8단계 대응표 (고정)

코드: `pair_carry_recorder.TEACHER_PHASE_TO_STAGE`(`stage_for()`는 없는 값을 거부). 같은 표가 `dsh/pairact-carry-r1`의 `harness/pairact_r1.TEACHER_PHASE_TO_STAGE`에 있어야 합니다(테스트 `test_phase_table_matches_pairact_r1_copy`가 origin ref를 읽어 비교). 파지 구간 어휘는 visible_only 교사 코드의 phase 리터럴 전체입니다(테스트 `test_phase_table_covers_every_teacher_phase_literal`). 아래 표와 코드가 다르면 테스트가 실패합니다. 단계 순서: approach → alignment → ready → execute → carry → place → recover → complete.

<!-- phase-stage-table -->
| teacher_phase | stage | 출처 |
|---|---|---|
| `approach` | `approach` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` |
| `search` | `approach` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` — 시야 탐색(접근 전) |
| `align` | `alignment` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` |
| `relook` | `recover` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` — 정렬 재관측(align_relook_v1) — READY 철회 |
| `ready` | `ready` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` |
| `pick` | `execute` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` — 고정 파지 동작 |
| `verify` | `execute` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` — GraspTeacher 기본 경로만 |
| `complete` | `complete` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` — 파지 명령 완료(done) |
| `done` | `complete` | grasp: `sim/grasp_act_teacher_v3.py`/`grasp_act_teacher.py` — GraspTeacher 기본 경로만 |
| `carry:carry_hold` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:to_west_staging` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:rotate_door` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:to_door_entry` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:door_pass` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:to_east_staging` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:rotate_zone` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:to_zone` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:zone_settle` | `carry` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:lower` | `place` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:open` | `place` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:raise` | `place` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:retreat` | `place` | carry: `pair_carry_teacher_warp.PHASES` |
| `carry:done` | `complete` | carry: `pair_carry_teacher_warp.PHASES` — 교사 종료 후 1.5 s 수동 행 포함 |
<!-- /phase-stage-table -->

- `relook`은 정렬 중 재관측(정렬 진행 없음 → 다시 보기)이라 `recover`입니다. StudentBarrier에서 READY를 철회하는 단계와 같은 뜻입니다.
- 파지 구간의 `wait` skill 행도 `teacher_phase`는 교사 phase(대개 `ready`) 그대로입니다. skill 토큰과 단계는 별개입니다.
- 실제 기록에 이 표에 없는 값이 나오면 sidecar 생성이 그 에피소드를 거부합니다. 그때 표를 고치고 다시 사전 등록합니다.

## 8. 남은 TODO와 [확인 필요]

1. (해결, 코드 확인) scene static_map 연결은 §1 참고. gcp6 실행 값 확인만 남음.
2. [확인 필요] MJWarp mirror(`world.data`)가 운반 중 빔·로봇 자세를 매 tick 갱신하는지. 파지 gate에서는 같은 `snapshot()`으로 joint_held를 판정했으므로 갱신된다고 보지만, 바퀴를 굴리며 빔을 든 상태는 GPU에서 처음입니다.
3. native 접촉 행(로봇-로봇, 로봇-벽, 빔-벽) 배선: `pair_carry_eval.native_contacts`는 `NotImplementedError`. 지금은 GT 기하 proxy만 씁니다.
4. formation-space planner 없음. 물체가 직선 구간을 막으면 `route_blocked`.
5. `arm_targets_from_teacher`: 하강 목표 = 파지 때 기록한 `grasp_xyz` 높이로 같은 IK. 빔이 바닥에 닿기 전에 IK 높이에 도달하면 공중에서 집게를 엽니다(작은 낙하, 기울면 `tilt`). 대안 `floor_contact_v1`(§2-1, 기본 off)을 넣었습니다. smoke는 기본 모드로 돌리고, 열 때 최저점(`teacher-r?.jsonl`의 `carry:open` 첫 행 시각의 eval 행)을 봅니다.
6. warp4에서 빔 짝·release 12건이 전부 HOST_ERROR(CUDA 700)였습니다(P0 진단 중). 운반 smoke도 같은 fault를 낼 수 있습니다.

## 9. P5 학생 평가 경로 (2026-10-21, 기본 off)

- runner 인자 `student_eval`(CLI `--student-eval <config.json>`, root `--student-eval`)이 None이면 동작 변화 0입니다. 켜면 같은 visible_only pair-carry 에피소드에서 *학생 ACT가 모든 명령을 냅니다*. 교사 객체는 setup에서 만들어지지만 `step()`은 한 번도 호출되지 않고(`teacher_steps = 0`), 운반 교사도 만들지 않습니다. 기록·노이즈·probe와 함께 켤 수 없습니다.
- 학생 정책은 별도 프로세스(`dsh/pairact-p5-student`의 `scripts/pairact_r1_student_worker.py`, 체크포인트 옆 Python)에서 돕니다. runner가 보내는 것은 로봇별 *자기 카메라 JPEG*와 *runner가 실제로 적용한 자기 명령*뿐이고(`harness/pairact_student_eval.py`, 요청 키 allowlist 테스트), 받는 것은 명령뿐입니다. 학생 행동에 teacher·GT 보정은 0입니다(runner는 받은 명령을 계약 `command()` 검사만 하고 그대로 적용).
- READY → GO → ACK는 기존 `GraspStartSync`에 beamact4 re-arm 규칙(READY 철회 시 barrier 재생성)을 씌워 씁니다. 시작 지연 RNG는 beampair7 runner와 같습니다(seed 기반 0–1.5 s).
- 지시 순서(사전 등록 초안): 파지 구간 skill `grasp`(GO 대기 중이면 `wait`), 두 로봇의 *자기 done 플래그*가 3.0 SIM s 동안 함께 참이면 둘 다 `release`·목적지 `B`로 바꿉니다. 두 로봇의 release done이 1.5 s 함께 참이면 끝내고, 아니면 cap까지 돕니다(cap = `cap_s + carry_cap_s`).
- 판정은 *같은 evaluator*(`pair_carry_eval.evaluate`)입니다. 시작점은 GT 3초 공동 유지에 처음 도달한 시각(eval-only), 하강 경계는 학생에게 교사 lower 시각이 없으므로 `zone_entry_t`(빔 footprint가 처음 zone B 안에 든 행)로 둡니다. 그 전의 낮은 빔은 낙하, 기울기·급강하 낙하는 전 구간 적용입니다. `physical_success = (3초 유지 도달) ∧ carry_eval.success`.
- 퍼널(eval-only, `StudentFunnel`): approach(맡은 끝 0.8 m) → alignment(station 0.203 m에서 0.03 m·0.06 rad) → READY(두 학생 READY 메시지) → grasp(양쪽 접촉 ≥ 0.5) → hold_3s → carry_1m → door → place. 상수는 CPU 학생 runner(`run_beamact2_student.py`)와 같습니다. 행은 `student-eval.jsonl`에 쓰고 학생에게는 가지 않습니다.
- [확인 필요] 실제 체크포인트·GPU에서 worker 왕복 지연, adapter(`run_beampair1.py`)가 교사 step 없는 결과를 그대로 받는지는 gcp smoke에서 확인합니다.
