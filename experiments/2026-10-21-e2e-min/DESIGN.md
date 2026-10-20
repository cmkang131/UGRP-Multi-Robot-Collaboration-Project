# 최소 E2E 연결(N2) 설계 (2026-10-21, Claude 구현 워커)

상태: 설계와 CPU 코드만 있습니다. GPU 실행은 없습니다. 코드는 `harness/e2e_min_handoff.py`(default off), `harness/e2e_min_eval.py`, `tests/test_e2e_min.py`입니다.
브랜치 `dsh/e2e-min`의 base는 `origin/dsh/l1lite-alloc`(580e6159f)입니다.

근거 표기 규칙은 다음과 같습니다.
- 브랜치 접두어가 없는 경로는 이 브랜치 기준입니다.
- `[ACT]`는 `origin/dsh/act18-c2c-v7clock`(ac274afeb)입니다.
- `[Q]`·`[O]`·`[T]`는 VM에서 실제로 import되는 frozen source입니다. 각각 `f0db6b1ab`, `0362037`, `6f057f7e`이고, 이 레포에서 `git show <sha>:<path>`로 확인했습니다.
- 확인하지 못한 항목은 [확인 필요]로 표시합니다.

## 1. 두 실행 경로

| 항목 | ACT 경로 (C2c 평가) | nav 경로 (r5, L1-lite) |
|---|---|---|
| 프로세스 | stage driver → evaluator(torch env, `act18_evaluate.py`가 `evaluate_act16w.py`를 runpy로 실행) → physics owner 자식 프로세스(`act17_v7.py --mode eval-owner` → `act16w_native_run.py` → `act16w_eval_owner.py` → `[O] warp_act_api.Owner`) [ACT `act18_evaluate.py:383-419`, `act16w_native_run.py:46-51`, `act16w_eval_owner.py:11-43`] | 단일 runner 프로세스가 MJWarp, 렌더, LLM HTTP 호출을 모두 맡습니다 [`scripts/run_e2e_warp.py:429-546`, `harness/e2e_warp_runtime.py:209-212`] |
| IPC | owner와 JSON lines(stdin/stdout)로 통신합니다. 요청은 `{actions}`/`{instruct,skill}`/`{close}`입니다 [ACT `act16w_eval_owner.py:48-60`] | 없음(같은 프로세스). LLM만 loopback relay를 거칩니다 [`run_e2e_warp.py:216-224`] |
| 장면 | `walls_floor_contrast_v5_indigo110_s80`이 하드코딩되어 있고 선택 플래그가 없습니다 [ACT `scripts/warp_act_scene.py:2,16`] | `configs/current_stack.json:290`의 `walls_floor_contrast_v6_indigo110_s80_neutral_start`입니다 [`scripts/e2e_warp_physics.py:75-76`] |
| 시나리오·맵 | HO4는 `s8_mixed_tiers_v7`/`s5`/`s2`, 맵은 `zone_wide_two_doors_final_v3`와 `zone_wide_door_geometry_v3`가 섞여 있습니다(C2c `plans.json`, 회수본) | `s7_pair_with_solo_v7`, `zone_wide_two_doors_final_v3` [`harness/e2ewarp_nav_gate.py:61`] |
| 물체 | 큐브 1개(cyan/red/green/yellow, role west), r1 단독 [O `warp_act_api.py:149-157`] | **물체 없음**(`scene.cargo=[]`) [`e2e_warp_physics.py:77-80`] |
| 로봇 | r1만 제어합니다. r2·r3는 주차되어 있고 `idle_robot_contacts='off'`입니다 [O `warp_act_api.py:160-162`] | r1·r2를 제어하고 r3는 prune합니다 [`e2e_warp_physics.py:103-105`] |
| 물리 | MJWarp `mjwarp_batch_v1`, `warp_native_contact_v1`(noslip 0, elliptic, implicitfast, impratio 5), CPU·GPU 모두 noslip 0 강제 [ACT `act16w_native_contact.py:42,91-92,128-129`]. dt 0.00025, 0.1 s당 400 step [ACT `experiments/2026-10-16-act16w/resume2/warm-receipts.json:277-282`]. C312 compiled 참조가 정확한 XML sha에 묶여 있습니다 [Q `scripts/simalt_compiled_compat.py:85-89`] | MJWarp, `apply_xml(xml,'warp_native_contact_v1')`, noslip 0 assert [`e2e_warp_physics.py:102,108`]. 0.1 s tick마다 400 step [`scripts/e2ewarp_vendor/warp_schedule_core.py:184-199`]. compiled 참조는 쓰지 않습니다 |
| 제어 주기 | 10 Hz, 최대 900 tick(90 SIM s) [O `warp_act_api.py:410`] | 10 Hz, 기본 60 SIM s [`run_e2e_warp.py:428-430`, `e2ewarp_nav_gate.py:67`] |
| 카메라 | `r1__robot_cam`(그리퍼 몸체에 장착) 640×480 fisheye, JPEG q82 [Q `warp_act_backend.py:289-291`]. 정책 입력은 4 lag(5.2/1.5/0.5/0 s) 몽타주입니다 [`harness/grasp_act_contract.py:22`] | 로봇별 `<rid>__robot_cam` 640×480. 렌더 경로가 같습니다(vendored backend) [`e2e_warp_physics.py:142-146`] |
| 명령 | 14차원: 바퀴 4, 펄스 4, PWM 5(servo 1/3/4/5/6), done 1 [`grasp_act_contract.py:19-27`]. 바퀴도 ACT가 제어합니다 | 바퀴만 제어하고 PWM은 항상 `SEARCH`입니다 [`harness/e2ewarp_selfnav.py:1030-1031`, `harness/active_camera.py:7`] |
| 명령 스키마 | `{t,wheels,duration_s,pwm}` 화이트리스트 [`grasp_act_contract.py:43-62`] | **같은 스키마**입니다(같은 계약으로 검증) |
| 단계 전환 | grasp done → `SETTLE_S` 3.1 s → release skill로 전환합니다. **운반 단계가 없고** 픽업 위치에서 바로 내려놓습니다 [`harness/grasp_act_rollout.py:92-106`, O `warp_act_api.py:66,226`]. done 이후 executor는 마지막 PWM을 유지하고 바퀴는 0으로 둡니다 [`harness/grasp_act_policy.py:168-170`] | 도착 claim(odom projection 0.52 m) 후 모두 도착하면 조기 종료합니다 [`e2ewarp_selfnav.py:266-268,787-790`, `run_e2e_warp.py:524-528`] |
| 시작 자세 | 큐브에서 0.6–1.1 m, 큐브 기준 방위 ±55°, 큐브를 향한 yaw ±25° [T `scripts/make_solo_teacher_plan.py:59-109`] | seed와 무관하게 x=−0.8982, y=−2.375/−2.875, yaw 0으로 고정입니다 [`e2ewarp_nav_gate.py:64,355-363`. r5 `eval_geometry.spawns`] |

**핵심 차이**는 다섯 가지입니다.
1. 프로세스와 Python env가 둘로 나뉘어 있습니다(ACT torch env와 owner, nav 단일 프로세스).
2. ACT owner는 r1 단독만 지원하고, nav에는 물체가 없습니다.
3. ACT는 C312 참조에 XML 해시로 묶여 있어 장면을 바꾸면 참조를 다시 만들어야 합니다.
4. nav 카메라 지면 투영은 SEARCH 팔 자세에서 맞춘 값입니다(`camera_height_m=0.29983`, `pitch_down_deg=18.99`) [`e2ewarp_selfnav.py:280-289`]. 그런데 카메라는 그리퍼 몸체에 붙어 있습니다.
5. ACT release는 학습 분포상 "픽업 바닥 위"에서만 일어났습니다.

## 2. v5(ACT)와 v6(nav) 장면 차이가 ACT 입력에 주는 영향 (추정)
- v6의 정의는 v5와 같은 벽 rgb·hsv·패턴·텍스처(asset alias) + `light_scale 0.30` + `pickup: neutral_grid_v1`입니다 [`sim/scene_contrast_v5.py:31-34`].
  - 조명 0.30은 기본 `noshadow_bright_v1`의 `light_color_scale 0.3`과 같아서 **배율 1.0, 즉 조명 변화가 없습니다** [`sim/scene_contrast_v5.py:25-29,41-45,80-81`, `sim/render_profile.py:53`]. 지시서의 "조명 0.30"은 실제로는 v5와 같은 밝기입니다.
- 실제 차이는 **픽업 바닥 하나**입니다. v5에서는 `zone_pickup`(rgba `.12 .36 .70 .14`)이 MJWarp에서 불투명하게 렌더되어, nav 첫 프레임 픽셀의 57 %가 H 107–108, S 중앙값 212, V 중앙값 90이었습니다. v6는 이것을 채도 0인 회색 타일 60개로 바꿉니다(선형 0.75/0.88/1.0이므로 sRGB 약 225–255) [`sim/neutral_pickup_floor.py:3-17,31-34,57-97`].
- 픽업 영역은 중심 (0.7, −0.85), 반폭 (1.15, 1.95)로 x −0.45…1.85, y −2.8…1.1입니다(`zone_wide_two_doors_final_v3` regions). HO4·TRAIN4의 큐브는 모두 이 안에 있습니다(예: 88668 큐브 (1.275, 0.45), 88600 (−0.2, −2.45)).
- 추정한 영향은 다음과 같습니다(측정 전).
  - ACT 카메라는 그리퍼에 붙어 근거리에서 큐브와 바닥을 봅니다. 그래서 몽타주 4장 대부분의 배경이 "어두운 남색 → 밝은 회색 격자"로 바뀝니다.
  - 학습 분포 밖이 되는 정도는 큽니다. 밝기 V 약 90 → 약 230이고, 텍스처 대신 타일 경계가 생깁니다.
  - 큐브 색 대비는 오히려 커질 수 있습니다. 반면 정책이 바닥 색을 높이나 접촉 단서로 써 왔다면 grasp done과 release 타이밍이 흔들릴 수 있습니다.
  - release는 바닥 위에서 하므로 가장 민감할 것으로 봅니다.
- 그래서 장면 적합성 시험(§7)으로 G를 직접 잽니다. CPU 이미지 비교(하위 워커 ②)는 보조 자료입니다.

## 3. 한 world 안에서 이어 붙이는 방법

### 3.1 world 구성 (미구현, `world_builder`)
- 기반은 nav world(v6, `zone_wide_two_doors_final_v3`, r1·r2, 레인 스폰)입니다. 로봇마다 큐브 1개(role west 박스)를 **ACT 시작 분포 안**에 둡니다.
  - 제안 위치는 각 레인 스폰에서 동쪽으로 0.6–1.1 m, 방위 0°입니다(예: r1 (−0.05, −2.375), r2 (−0.05, −2.875)). 두 위치 모두 픽업 영역 안입니다. 정확한 값은 [확인 필요]입니다.
  - 큐브 사이 간격은 0.5 m(레인 간격)입니다. ACT 학습 world에서는 다른 로봇과 물체가 "주차·접촉 off" 상태였으므로 이 간격은 분포 밖입니다.
- 접촉: ACT world는 `cargo_noslip_v1`의 finger/cargo `<pair>`를 씁니다 [Q `sim/masterpi_drive_friction_v7.py:255`, `sim/dispatch_contact_profile.py:24-57`]. nav world에는 이것이 없습니다. 물체를 든 채 주행하는 경로는 이 pair가 같아야 의미가 있습니다. 같은 builder 경로인지는 [확인 필요]입니다.

### 3.2 단계 상태기계 (`harness/e2e_min_handoff.py`, 구현됨)
```
ALLOCATE ─(LLM 배정 성공: success_eligible ∧ 좌·우 각 1)→ ACT_GRASP | TEACHER_GRASP
        ─(grasp done)→ NAV_CARRY [settle 3.1 s hold → nav]
        ─(own arrival claim)→ ACT_RELEASE | TEACHER_RELEASE
        ─(release done)→ DONE
모든 단계 ─(오류·시간 초과)→ FAIL(code)   (종단, fail-closed)
```
- ALLOCATE는 L1-lite `allocate_slots` 기록을 그대로 씁니다 [`harness/e2ewarp_l1lite.py:446-541`]. 기록이 없거나, fatal이거나, `success_eligible`가 아니면 두 로봇 모두 `E2E_ALLOC_FAILED`입니다. 슬롯이 겹치면 `E2E_ALLOC_SLOTS_INVALID`입니다.
- grasp done 신호는 ACT executor의 issued done(헤드 ≥ .65, [`grasp_act_contract.py:142-153`])이나 teacher done입니다. 상태기계는 GT를 읽지 않습니다.
- 단계별 시간 예산(SIM s)은 grasp 90(ACT 평가 cap), settle 3.1(`SETTLE_S`), carry 60(nav 예산), release 45입니다. release 45 s는 [확인 필요]이며 사전 등록에서 동결합니다.
- fail-closed 오류 코드(`ERRORS`)는 다음과 같습니다.
  - 배정: `E2E_ALLOC_FAILED`, `E2E_ALLOC_SLOTS_INVALID`
  - 집기: `E2E_GRASP_TIMEOUT`, `E2E_GRASP_EXECUTOR_ERROR`, `E2E_HOLD_MISSING`
  - 운반: `E2E_NAV_NO_CLAIM`, `E2E_NAV_TIMEOUT`, `E2E_NAV_EXECUTOR_ERROR`
  - 내려놓기: `E2E_RELEASE_TIMEOUT`, `E2E_RELEASE_EXECUTOR_ERROR`
  - 순서: `E2E_EVENT_OUT_OF_ORDER`

### 3.3 단계 전환 시 명령 hold 규칙
| 규칙 | 내용 | 근거 |
|---|---|---|
| H1 | 전환이 일어난 tick에는 바퀴 0, PWM은 hold 값입니다. 그 tick의 executor 출력은 내보내지 않습니다 | 전환 tick에 두 executor 명령이 섞이는 것을 막습니다 |
| H2 | grasp done 뒤 3.1 s는 정지 hold입니다. 이 동안 nav adapter를 **호출하지 않습니다** | nav의 odom은 자기가 낸 펄스를 적산합니다 [`e2ewarp_selfnav.py:1082-1108`]. 내보내지 않은 명령을 적산하면 안 됩니다. 3.1 s는 ACT의 settle과 같습니다 |
| H3 | NAV_CARRY에서는 nav의 바퀴·펄스를 그대로 쓰고, PWM 5채널은 **grasp done 시점 PWM으로 고정**합니다(`last_hold_all_servos_v1`). nav가 보내는 SEARCH PWM은 버립니다 | 지시서 규칙입니다. ACT도 done 이후 마지막 PWM을 유지합니다 [`grasp_act_policy.py:168-170`] |
| H4 | release 진입 tick은 hold이고, 다음 tick부터 release executor가 hold PWM에서 시작합니다 | release 입력의 issued history 마지막 행이 hold 명령이어야 합니다(연결 지점) |
| H5 | DONE이면 바퀴 0과 마지막 PWM, FAIL이면 바퀴 0과 마지막 PWM입니다. **실패가 그리퍼를 열지 않습니다** | 실패 처리 중 낙하를 막습니다 |
- 대안 규칙 `gripper_hold_arm_search_v1`(그리퍼만 유지하고 팔은 SEARCH로)은 nav 카메라 지면 투영을 되살릴 수 있습니다. 하지만 팔을 움직이는 동안 큐브가 계속 잡혀 있는지는 측정한 적이 없어서 `NotImplementedError`로 남겼습니다.

### 3.4 release (ACT 재개 또는 teacher 대체)
- E2E-2(ACT release)에서는 owner가 `instruct(skill='release')`로 skill을 바꿉니다 [ACT `evaluate_act16w.py:68-69`]. 관측은 `destination_zone='pickup_site'`로 고정입니다 [O `warp_act_api.py:66`].
  - zone B 바닥(파란 페인트 H 110–114) 위의 release는 학습 분포 밖입니다. 그래서 E2E-1에서는 teacher로 대체합니다.
- teacher release는 frozen `SoloTeacher`입니다 [T `sim/grasp_act_solo_teacher.py:252-253,475`]. nav runner 안에서 구성하는 방법과, 픽업 위치가 아닌 곳에서 동작하는지는 [확인 필요]입니다(`teacher_skill`).

## 4. 대체 단계 표기
- queue 필드는 `queue_fields(level)`이 만들고 `validate_queue`가 fail-closed로 검사합니다.
  - 필드: `e2e_min=on_v1`, `e2e_level`, `e2e_substitutions=[...]`, `e2e_overlay_text=false`, `e2e_hold_rule`, `e2e_label`.
  - 레벨별 `e2e_substitutions`: E2E-0은 `['grasp:teacher','release:teacher']`, E2E-1은 `['release:teacher']`, E2E-2는 `[]`입니다.
- 실행 로그 `e2e-handoff.json`(`E2EMinEpisode.export()`)에도 같은 목록, 전환 이력(robot, sim_s, from, to, reason, code), 단계 도달 시각을 남깁니다.
- 평가 보고서는 `e2e_substitutions`와 `substitutions_match_level`을 출력합니다.
- 영상에는 **오버레이 텍스트를 넣지 않습니다**. 대체 단계는 보고서와 영상 설명문에만 적습니다.

## 5. 물체를 든 채 주행할 때의 낙하 지표 (eval-only, `e2e_min_eval.carry_drop`)
- 창은 로봇별 NAV_CARRY 진입부터 이탈까지입니다(handoff 전환 로그 기준). GT는 `evaluation-state.npz`의 10 Hz qpos로, 큐브 free joint와 로봇 base에서 읽습니다.
- 아래 조건 중 하나가 `min_ticks`=5(0.5 s) 연속이면 낙하로 봅니다.
  1. `floor`: 큐브 하단 여유(z − half) ≤ 0.005 m
  2. `detach`: 큐브와 base 중심의 수평 거리 > 0.35 m
  3. `no_grip`: 손가락 힘을 측정했을 때 최대 손가락 힘 < 0.1 N. ACT drop 정의와 같은 임계입니다 [`grasp_act_rollout.py:134-135`]
- 임계값은 [확인 필요]입니다. E2E-0 전에 teacher 운반 trace로 보정한 뒤 사전 등록에서 동결합니다.
- 창이 비었거나, 시계열 길이가 맞지 않거나, 큐브 geometry가 없으면 `dropped=None`(측정 안 됨)이고, 이 경우 성공이 아닙니다.

## 6. 남은 NotImplemented 연결 지점 (추측으로 메우지 않음)
| id | 필요한 것 | 막는 근거 |
|---|---|---|
| `world_builder` | v6 2로봇 world + 로봇별 큐브 + finger/cargo pair | nav는 cargo를 제거합니다 [`e2e_warp_physics.py:77-80`]. ACT owner는 r1 단독에 C312 XML 해시 binding입니다 [O `warp_act_api.py:148-157`] |
| `act_skill_client` | nav runner의 자기 프레임으로 ACT actor 호출(r1·r2) | actor는 별도 torch env RPC입니다. History는 `robot_id='r1'`로 하드코딩되어 있습니다 [O `warp_act_api.py:60,67`]. 정책 context에는 robot id 차원이 없습니다 [`grasp_act_contract.py:27`]. 그래서 r2에 쓸 수 있을 가능성은 있지만 확인하지 않았습니다 |
| `teacher_skill` | nav runner 안에서 SoloTeacher로 grasp·release | teacher는 teacher runner에서만 구성됩니다 |
| `nav_carry_adapter` | grasp 후 자세에서 nav 시작, 팔 hold 상태에서 검출·투영 | 지면 투영이 SEARCH 장착에 맞춰져 있습니다 [`e2ewarp_selfnav.py:280-289`]. 레인 스폰과 yaw 0을 전제합니다 |
| `runner_loop` | tick loop를 `E2EMinEpisode.tick`으로 라우팅하고, 도착 시 조기 종료하지 않음 | [`run_e2e_warp.py:500-506,524-528`] |
| `eval_cube_geometry` | `eval-geometry.json`에 `cube_qpos_adr`, `cube_half_m` 기록 | 현재는 robot qpos만 기록합니다 [`e2ewarp_nav_gate.py:722-733`] |
| `gripper_hold_arm_search_v1` | 대안 hold 규칙 | 팔을 움직일 때 큐브가 유지되는지 측정한 적이 없습니다 |

## 7. 장면 적합성 시험 (D4)
- 명령 초안은 브랜치 `dsh/act18-scene-v6-fit`(base `dsh/act18-c2c-v7clock`)의 `experiments/2026-10-21-act18-scene-fit/COMMANDS_DRAFT.md`에 있습니다. 사전 등록 초안은 같은 폴더의 `SCENE_FIT_PREREG_DRAFT.json`입니다.
- 패치는 default off입니다. `UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1`일 때 `sim.scene_contrast_v5.install`을 감싸 v5에 neutral 픽업 타일을 칠합니다. 판정은 G(v6, HO4×1) ≥ 2/4이면 v6로 통일하고, ≤ 1/4이면 nav를 v5로 재보정하는 쪽으로 분기합니다.
- v6 XML은 C312 참조를 다시 만들어야 합니다(`act17_v7_rebuild_compiled_references.py`에 같은 env를 연결). case index와 seed 대응은 [확인 필요]입니다.

## 8. 가장 큰 위험
1. **nav 카메라 기하.** 카메라가 그리퍼에 붙어 있어서, 팔을 hold 자세(grasp 후 들어 올린 자세)로 두면 nav 검출, stage-2 1.5 m 투영, arming이 SEARCH 자세 보정과 어긋납니다. 큐브가 시야를 가릴 수도 있습니다. H3 규칙(지시서)을 그대로 쓰면 nav가 zone B를 보지 못할 수 있습니다.
2. **ACT 분포 밖.** v6 픽업 바닥(어두운 남색 → 밝은 회색)과 같은 world 안의 다른 활성 로봇·큐브(학습 시에는 접촉 off로 주차)가 문제입니다. release를 zone B 바닥에서 하는 것도 분포 밖입니다.
3. **물체를 든 채 GPU에서 주행한 적이 없습니다.** 바퀴 펄스의 가감속으로 낙하할 수 있고, finger/cargo 접촉 pair가 nav builder에 없습니다. 연결 코드 6개가 미구현이라 E2E-0 일정(10/22 밤)이 이 구현 속도에 묶입니다.
