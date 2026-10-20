# 운반 자세 카메라 렌더 시험: 사전 등록과 명령 초안 (DRAFT)

상태: **DRAFT**입니다. 판정 규칙(§3)은 GPU 실행 전에 FROZEN으로 커밋하고, 결과를 본 뒤에는 바꾸지 않습니다.
범위: render-only입니다. 물리 step 0, 제어기 0, LLM 0이고 큐브를 잡고 있는지(유지 여부)는 판정하지 않습니다.
실행은 DeepSeek이 10/21 밤 D4와 같은 세션에서 합니다. 예상 GPU 시간은 0.3 h 이하입니다(world 32개, tick 0 렌더만).

## 1. 왜 필요한가
- nav 카메라 `<rid>__robot_cam`은 그리퍼 몸체에 붙어 있습니다.
- nav의 지면 투영(stage-2 1.5 m, arming)은 SEARCH 장착 자세에서 맞춘 값입니다(height 0.29983 m, pitch 18.99°) [`harness/e2ewarp_selfnav.py:280-289`].
- 집은 뒤 팔을 hold 자세로 두면 nav가 zone B를 못 볼 수 있습니다. 이것이 DESIGN.md §8의 위험 1입니다.

## 2. 후보 자세 (CPU에서 도출, `carry_pose_candidates.json`)
도출 코드는 `harness/e2e_min_carry_pose.build_candidates`입니다. servo는 1 그리퍼, 3 손목, 4 팔꿈치, 5 어깨, 6 yaw입니다. 카메라 pitch는 SDK `camera_extrinsics`로 계산한 값이고, 참고용이며 판정에는 쓰지 않습니다.

| 자세 | PWM {1,3,4,5,6} | 카메라 pitch↓ / 원점 z(SDK) | 도출 |
|---|---|---|---|
| (a) `act_lift_end` | 1499, 738, 1828, 2216, 1493 | 57.2° / 0.118 m | C2c-HO4에서 grasp done을 낸 11개 world의 done tick issued PWM 중 medoid |
| (b) `teacher_hold_max_pitch` | 1500, 837, 1930, 2173, 1510 | 53.6° / 0.119 m | teacher 데이터셋에서 grasp skill, 그리퍼 닫힘(≤1600), hold 계열 phase인 행 중 tool pitch가 가장 높은 벡터(110행) |
| (c) `carry_look_v1` | 1499, **550**, 1828, **1620**, 1493 | 20.4° / 0.228 m | (a)에서 어깨·손목만 움직였습니다. 격자 탐색(step 10, PWM 550–2450, tool pitch −90…0°)으로 SEARCH 카메라에 가장 가까운 자세입니다 |
| 참조 `search_grip_ref` | 1499, 740, 2320, 1320, 1500 | 20.6° / 0.211 m | `gripper_hold_arm_search_v1`(SEARCH + 그리퍼 닫힘). **판정 후보가 아닙니다.** 대안 규칙의 가림을 알아 두려고 렌더합니다 |

- CPU 사전 관찰은 판정이 아닙니다. (a)·(b)는 카메라가 54–57° 아래를 봅니다. fisheye 상단 가장자리에서만 원거리가 보일 수 있습니다.
- (c)는 손목이 탐색 범위 하한(550)에 닿아 있습니다. 실물 손목 관절 한계 안인지는 [확인 필요]입니다.

## 3. 판정 (사전 등록 초안)
- 측정 위치는 nav 레인 위입니다(r1 y=−2.375, r2 y=−2.875, yaw 0). x는 1.5, 2.0, 2.8, 3.5 m입니다.
- 지표(로봇·x·자세마다)는 다음과 같습니다.
  - v230 밴드(H 110–114, S≥100, V 30–230) 최대 4-연결 성분 px
  - 그 bbox의 마지막 행(포함)
  - v230 detector 검출 수
  - 큐브 가림 비율: 큐브가 있을 때와 없을 때 프레임에서 |ΔRGB| 합이 40을 넘는 픽셀의 비율
  - 보조: zone 밴드 마스크 손실 비율
- 규칙(`harness/e2e_min_carry_pose.verdict`)은 다음과 같습니다.
  - x=2.8 m에서 **r1과 r2 모두** 성분 ≥ 600 px이고 가림 < 0.30이면 그 후보가 통과합니다.
  - 통과한 후보 중 (a) → (b) → (c) 순으로 첫 번째를 채택합니다. 집은 뒤 팔이 덜 움직이는 순서입니다. 채택한 자세가 `nav_carry_adapter`의 hold 규칙이 됩니다.
  - 셋 다 실패하면 운반 구간은 `gripper_hold_arm_search_v1`(팔 SEARCH + 그리퍼만 유지)로 갑니다. 이 경우 팔을 SEARCH로 옮기는 동안의 낙하 위험은 **별도 물리 시험**(새 사전 등록)으로 확인합니다.
  - 측정 행이 없으면 실패로 봅니다.
- 판정 이후에도 남는 일이 있습니다.
  - 어느 자세를 채택하든 SEARCH가 아니면 nav의 지면 투영 상수(카메라 높이, pitch)를 그 자세로 다시 맞춰야 합니다. 이것은 nav 재보정 과제이고, 이 시험 범위 밖입니다.
  - 지시서 원래 규칙(`last_hold_all_servos_v1`)은 (a)와 같은 자세입니다.

## 4. 명령 초안 (gcp6 또는 gcp2의 L4, nav `.venv-warp`)
```bash
SRC=/home/ugrp/ugrp-sim/src/e2e-min-<SHA>          # dsh/e2e-min clean clone, HEAD=<SHA>
cd $SRC && git status --porcelain                   # 0줄이어야 합니다
TS=$(date -u +%Y%m%dT%H%MZ)
/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python experiments/2026-10-21-e2e-min/carry_pose_render.py \
  --out /home/ugrp/ugrp-sim/runs/e2e-min-carry-pose-render-$TS --expected-source-sha <SHA>
jq '.verdict' /home/ugrp/ugrp-sim/runs/e2e-min-carry-pose-render-$TS/measure.json
```
- [확인 필요] 실행 venv 경로: r3 reproduce 문서에는 gcp6 `.venv-warp`로 적혀 있습니다. D4와 같은 세션에서 gcp2로 돌린다면 gcp2의 nav venv 경로를 확인해야 합니다.
- 출력은 `measure.json`(행 32 × 2로봇, 판정, `cargo_contact_pairs` 감사)과 `frames/*.jpg`(on/off)입니다. 회수할 때 sha256을 대조합니다.
- 가림은 큐브 on/off 두 렌더의 차이로 잽니다. 두 렌더는 scene XML이 같고 qpos만 다릅니다. 큐브는 손가락 패드 중점에 둡니다. 손가락과 겹칠 수 있다는 점을 기록합니다.

## 5. 함께 확인되는 것 (world_builder 첫 실행)
- `build_context(nav_cubes=...)`가 s7 시나리오의 `cyan_1`·`red_1`만 남기는지 확인합니다. body가 정확히 일치하지 않으면 fail-closed입니다.
- 손가락-큐브 `<pair>`가 몇 개 있는지 `cargo_contact_pairs`에 기록됩니다. ACT owner의 pair와 같은지는 아직 판정하지 않습니다([확인 필요]).
