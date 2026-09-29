# 공동 운반 b-v6e: 운반(단계 4) + 내려놓기(단계 5) 통합 후보 — 코드·사전 등록 (2026-09-29, Claude)

**이 문서는 사전 등록 계획과 부분 측정 결과를 함께 담는다.** 2026-09-29 측정에서 스모크·cal·내려놓기 격자는 돌렸고, 운반 33셀 격자·held-out·절제는 조정자 결정으로 돌리지 않았다(아래 "결과"). 앞 절들의 "미측정", "한 번도 돌리지 않았다"는 **등록 시점(커밋 ece38792)의 기록**이며 결과는 "결과" 절이 우선한다.
- **E2E 성공이 아니다.** 나중에 돌릴 측정도 한 단계씩만 통과시키는 stage probe다(PR #260 하네스).
- **제어기 결과가 아니다.** 코드는 단위 테스트로만 확인했다(합성 데이터). 운반·내려놓기가 실제로 개선되는지는 아직 아무도 모른다.
- 근거 진단은 [`2026-09-29-pair-v6c-carry`](../2026-09-29-pair-v6c-carry/README.md)(기준선 b-v6c 운반 0/33, 목적지 내려놓기 0/13)의 측정이다. 그 README의 "진단 전용 패치" 결과는 원인 확인용이며 제어기 결과가 아니다.

로봇 입력 경계: 제어기에는 자기 RGB·공용 top RGB·자기 발행 명령 이력·정적 지도/보정만 들어간다. 정답(GT)·시뮬 상태는 staging(teacher 예외)과 `eval_only/` 판정에만 쓴다. 초음파는 번들이 켜지지 않았으므로 쓰지 않는다. AprilTag 조건은 v6c-carry README '한계'와 같다. weld OFF, `cargo_noslip_v1`, 모델 호출 0.

Refs #221. 실험 ID `2026-09-29-pair-v6e-carry`. 브랜치 `claude/pair-v6e-carry`(로컬, push 안 함). 소스: 이 브랜치의 `harness/`, `scripts/`, `tests/` 변경(`4c94138f` 병합 커밋 + origin/main `45a21b23` 병합 이후 커밋).

## 번호 (등록 전)

| 항목 | 값 | 상태 |
|---|---|---|
| 실행 번들 | `v81` | **아직 등록하지 않았다.** 측정이 끝난 뒤 최종 상태에서 **한 번만** 등록·봉인 |
| workflow | `2.14.0` | 위와 같음 |
| revision | `v6e` (`REVISION_POLICIES`) | 위와 같음 |
| 쓰지 않는 번호 | 번들 v82 / workflow 2.15.0 / revision v6f | v6f(내려놓기) 변경은 v6e에 합쳐서 등록한다 |

지금 상태에서 `EXECUTION_BUNDLE_ID`, `REVISION_POLICIES`, `configs/simulation_workflows.json`, 봉인 해시(`scripts/zone_pair_v6_contract.py`), v6c/v6d 은퇴 목록은 **바꾸지 않았다.** 그래서 `tests/test_zone_pair_registered_source.py`의 봉인 해시 테스트 5건은 소스가 바뀐 만큼 실패한다(예상, 등록 때 해결).

## 가설

기준선 b-v6c(v6c-carry README)의 세 가지 막힘마다 코드로 옮긴 가설이다. 각 가설은 **플래그 하나**이고 기본 OFF다.

| 막힘 | 관측(v6c-carry) | 가설(원인) | 이 브랜치의 수정 | 플래그 |
|---|---|---|---|---|
| 1 운반 중 σ 확산 | 33건 모두 leg 시작 2.4–3.3 s에 `SELF_POSE_UNCERTAIN`/yaw. σ_yaw가 0.0218·√t로 자라 게이트 3°에 닿음 | 든 상태의 등록 운동 모델(`motion_loaded.noise_abs` yaw 0.0976 rad/s)이 멈춰 있을 때도 백색 속도 잡음을 넣고, 이는 유한차분 GT 잔차를 백색 잡음으로 잘못 본 것이다. 실제 yaw 드리프트는 leg마다 일정한 편향(잔차 lag-1 자기상관 0.96)이다 | 필터가 든 플랜트의 보정된 dead-reckoning 오차(이동할 때만 켜지는 백색 잡음 + 입자별 leg 고정 yaw 편향 + 든 상태 slip 배율 산포)를 갖는다. 게이트와 임계값은 그대로 | `carry_dr_model` |
| 2 옆 이동 열린 고리 | σ를 고정해도 옆 이동 leg 3·4·5가 계획보다 15.6 % 더 감(`MOTION_ERROR`) | 상수 `CARRY_ODOM_SCALE['lateral']=0.697`은 한 leg 길이에서만 맞는다. 1차 지연 플랜트(든 `tau_s` 0.8 s)의 이동거리는 `v·(T − τ(1−e^(−T/τ)))`라 명령 길이 T에 비선형이다 | 보정된 든 플랜트(gain, `tau_s`, `tau_stop_s`)를 역산해 옆 이동 leg 명령 길이를 정한다 | `carry_lateral_lag` |
| 3 목적지 내려놓기 | 기준선 0/13 전부 r1 `OWN_IMAGE_INVALID`. 우회하면 물러남이 `wall_east`에 막혀 `COLLISION_GUARD` | (a) 밝기 V<8 고정 기준이 목적지의 어두운 바닥을 "가려짐"으로 오판한다. (b) 벽이 가까워 물러남 여유(0.17 m)가 필요량(0.163 m)보다 얇고, 가드 거절이 곧 작업 실패가 된다 | (a) `own_image_ob`: "어둡다"의 기준을 프레임 자체의 광학 검정(어안 렌즈 바깥 영역) 중앙값 + 2 LSB로 잡는다(고정 기준 7을 넘지 않음). (b) `bounded_retreat`: 놓은 뒤 후진 명령을 기존 스윕 가드가 거절하면 명령을 내지 않고 멈춘다(작업 실패로 만들지 않음) | `own_image_ob`, `bounded_retreat` |

**가설의 한계.** 막힘 1의 편향 모델과 옆 이동 지연 모델은 v6c 진단 패치(σ 고정, 배율 0.806)가 보인 것과 같은 방향이지만, 진단 패치와 같은 방식은 아니다(아래). 가설이 맞는지는 측정 전에는 알 수 없다.

## 변경 요약

### 정책과 플래그 (`harness/zone_pair_v6_policy.py`)

- 새 필드 4개(모두 기본 `False`): `carry_dr_model`, `carry_lateral_lag`, `own_image_ob`, `bounded_retreat`.
- 새 정책 6개. 등록된 정책은 하나도 바뀌지 않았다.

| 정책 | 구성 | 용도 |
|---|---|---|
| `b-v6d` (기존) | 대조 | 운반 대조군 |
| `b-v6e-dr` | b-v6d + `carry_dr_model` | 막힘 1 절제 |
| `b-v6e-lag` | b-v6d + `carry_lateral_lag` | 막힘 2 절제 |
| **`b-v6e`** | b-v6d + 위 두 운반 플래그 + `own_image_ob` + `bounded_retreat` | **통합 후보** |
| `b-v6f-a` | b-v6c + `own_image_ob` | 내려놓기 절제(영상) |
| `b-v6f-b` | b-v6c + `bounded_retreat` | 내려놓기 절제(물러남) |
| `b-v6f` | b-v6c + 둘 다 | 내려놓기 단독 후보(측정에는 b-v6e가 대신함) |

### 파일

| 파일 | 변경 |
|---|---|
| `harness/owncam_carry_v6e.py` (신규) | 보정 프로필 로드(`carry_dr_fit.json`, 파일 sha256과 프로필 sha256을 기록), 든 필터 교체, 옆 이동 leg 길이 역산(`leg_duration`) |
| `harness/owncam_localizer.py` | 선택 키(`motion_loaded.load_transition` 등)가 있을 때만 동작. 키가 없으면 출력이 바이트 동일 |
| `harness/owncam_recovery_v6.py` | 위 플랜트 상태 초기화 훅 2줄(플래그 OFF면 no-op) |
| `harness/zone_pair_executor.py` | `door_schedule`의 lag 분기, `PairTeam`의 활성화·기록(`carry_dr_v6e`), 영상 게이트를 `frame_gate(policy)`로 |
| `harness/zone_pair_vision.py` | `valid_frame_ob`, `frame_gate`. `valid_frame`은 바이트 그대로 |
| `harness/zone_pair_guards.py` | `_bounded_retreat`(놓은 뒤 후진 명령만, 스윕 가드 판정은 그대로), 영상 게이트 조회 |
| `harness/zone_pair_grasp.py` | 영상 게이트 조회 |
| `harness/pair_stage_probe.py` 0.6.0 | 정책 6개, `SETUP_VARIANTS`(`cal`, `hA`, `hB`, `hC`), 케이스 id `:V<이름>` |
| `scripts/run_pair_stage_probes.py` | `--pf-track`, `--omp-threads`, `--setup-variant`, `image_valid_off` 진단이 `valid_frame_ob`도 강제 |
| `scripts/build_pair_stage_probe_views.py` | 새 정책 약어, 배치 태그 |
| `scripts/run_ci_tests.py` | `tests/test_zone_pair_v6e.py`, `tests/test_zone_pair_v6f.py`를 shard 구조(8 shard, main #267)에 등록 |
| `tests/` | `test_zone_pair_v6e.py`(신규 17), `test_zone_pair_v6f.py`(신규 10), 프로즌 M1 임포트 해시 2곳에 post-freeze 해시 추가(`test_zone_pair_executor.py`, `test_owncam_memory.py`), `test_owncam_bootstrap_v6b.py`(정책 dict) |
| `experiments/2026-09-29-pair-v6e-carry/` | `fit_carry_dr.py`, `carry_dr_fit.json`(보정 입력·산출), 이 README |

### 플래그 OFF일 때 기존 출력이 바이트 불변인 근거 (테스트로 확인)

- `test_flags_off_localizer_is_bit_identical_to_main_1e7bdfe0`: 든 PF의 평균·표준편차·RNG 상태가 main의 골든 값과 `1e-9` 안에서 같다(같은 난수 소비 횟수).
- `test_flags_are_off_for_every_registered_policy_and_on_only_for_the_v6e_set`, `test_flags_are_off_in_every_existing_policy_and_the_v6f_policies_are_v6c_plus_flags`: `v5h`·`b-only`·`a+b`·`b-boot`·`a+b-boot`·`b-v6c`·`b-v6d` 전부 새 플래그 OFF, `frame_gate`가 `valid_frame` 그 자체를 돌려줌, 절제 정책은 대조 정책 + 지정 플래그 외 차이 없음. `REVISION_POLICIES['v6c']`는 그대로.
- `test_lateral_lag_flag_changes_only_the_lateral_leg_duration`, `test_bounded_retreat_never_clears_a_command_the_guard_would_have_cleared_differently`: lag는 옆 이동 leg 길이만, 물러남은 놓은 뒤 후진 명령만 바꾼다.
- 기존 `test_zone_pair_v6c.py`·`test_zone_pair_v6d.py`·`test_zone_pair_v6.py`·`test_zone_pair_executor.py`(단계별 명령 골든 포함)와 `test_owncam_bootstrap_v6b.py`(정책 필드 dict 전체 비교)가 통과한다.
- 한계: 이것은 **합성/단위 수준**의 바이트 동일성이다. 등록된 번들의 실제 물리 실행을 전과 비교한 것이 아니다(그 비교는 등록 뒤 측정 계획 1번의 대조군이 한다).

## 진단 패치와 실제 제어기의 차이 (σ 인위 고정 없음)

| | v6c-carry의 진단 패치(제어기 결과 아님) | 이 브랜치의 제어기 코드 |
|---|---|---|
| σ | `sigma_held_at_prior`: **보고 σ를 0.03 m / 0.012 rad로 잘라서** 게이트에 넣음 | **고정·제한 없음.** 필터가 계산한 σ가 그대로 게이트에 간다. 테스트 `test_loaded_rest_does_not_diffuse_and_leg_sigma_stays_under_the_hold_gate_with_the_profile`가 fix 없는 14 s leg에서도 σ_yaw>0.0357, σ_xy>0.03으로 **계속 자란다**는 것과 등록 모델은 약 3 s에 게이트를 넘는다는 것을 함께 확인한다 |
| 자라는 이유 | 자람 자체를 없앰 | 정지 중 확산만 제거(모션 게이트), 움직이는 동안은 보정된 백색 잡음 + leg 고정 편향 + 배율 산포로 자란다. 필터는 이 편향을 fix로 배울 수 있다(편향이 입자와 함께 재표집됨) |
| 게이트 | 진단은 게이트를 넓히는 패치(`loaded_yaw_gate_wide`)도 있었음 | 게이트 임계(3°/2.5°, xy 0.07 m, 체류 0.6 s/0.4 s)와 스윕 가드 여유식은 그대로 (`test_profile_keeps_the_gate_and_the_mean_motion_untouched`) |
| 옆 이동 배율 | `carry_lateral_scale_measured`: **측정된 0.806을 상수로** 넣음 (v6c의 33셀과 같은 자료에서 얻은 값) | 상수 없음. 보정 파일의 든 플랜트(gain·`tau_s`·`tau_stop_s`)에서 leg 길이별로 역산. 0.806을 코드에 쓰지 않았고 leg 길이가 바뀌면 배율도 바뀐다 (`test_shipped_lateral_leg_length_comes_from_the_loaded_plant_not_the_measured_scale`) |
| 영상 검사 | `image_valid_off`: 검사를 **항상 통과**로 | 검사는 살아 있다. 기준만 프레임의 광학 검정에 상대적으로 바꿨고 완전히 검은/균일/가려진 시야는 여전히 거절한다(`test_a_view_that_is_wholly_black_uniform_or_mostly_covered_by_a_black_occluder_still_fails`) |
| 물러남 | 진단은 σ를 0으로 해 여유를 키움 | 스윕 가드 판정은 그대로다. 거절된 후진 명령을 내지 않고 멈출 뿐이다(가드를 우회한 명령 없음) |

**보정 자료의 출처.** 든 플랜트의 오차 모델(`carry_dr_fit.json`)은 **dev 박스 운반 episode 8개**(`outputs/owncam-loop-20260925/dev-a1..a4/dev-box-s31..33`, student 구간 3191개 창)에서 맞췄다. **33셀 stage 격자·held-out 배치·cohort-2는 읽지 않았다**(스크립트 머리말). 오프라인 적합에서 GT를 참조로 읽는 것은 `calibration_loop_v2.json`과 같은 정적 보정이며 제어기 입력에 GT를 넣는 것이 아니다. 적합값은 leave-one-episode-out 범위의 **최댓값**을 써서 보수적으로 잡았다(yaw 편향 σ 0.00139 rad/s, x·y 백색 속도 잡음 0.0177·0.0111 m/s 등). 실제 실행에서는 파일 sha256과 프로필 sha256을 `carry_dr_v6e` 기록에 남긴다.

**아직 검증되지 않은 것.** 이 모델이 stage 운반 셀(두 로봇이 든 빔, 다른 하중과 접촉)에서도 맞는지는 측정 전에 알 수 없다. 그래서 측정 계획 1번(보정 코호트)이 먼저다.

## 근거와 참고 자료

v6c-carry README(`experiments/2026-09-29-pair-v6c-carry/README.md`)에서 인용한 것과, 이번 코드가 실제로 쓴 방식이다.

- **S. Thrun, W. Burgard, D. Fox, *Probabilistic Robotics*, MIT Press 2005, 5장 odometry 운동 모델**(잡음을 이동량에 비례). v6c-carry의 막힘 1 제안 근거. 이번 코드에서는 "움직이지 않으면 σ가 자라지 않는다"는 부분을 채택했다(정지 확산 제거). 잡음을 이동량에 비례시키는 α1–α4 형식은 쓰지 않았고, 든 플랜트 자료에 맞춘 이동 시간 기준 백색 잡음 + 편향으로 했다. **차이**: 우리 필터는 이미 등록된 PF라 잡음 형식만 바꿨다.
- **Nav2 AMCL 설정**(`alpha1…alpha5`, `update_min_d`, `update_min_a`: 움직임이 없으면 갱신하지 않음): https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/others/configuring_amcl/. 같은 정지 게이팅 근거.
- **O. J. Woodman, "An introduction to inertial navigation," Univ. of Cambridge TR-696, 2007**(`owncam_carry_v6e.py` 머리말이 인용). 백색 속도 잡음은 위치/각도 오차가 √t로, 일정한 편향은 t로 적분됨. 이 구분이 "정지 중 σ 확산"과 "leg 고정 편향"을 나누는 근거이며, 적합 식 `var(e_yaw)=a·T+b·T²`(`fit_carry_dr.py`)가 여기서 온다.
- **J. Borenstein, L. Feng, "Measurement and correction of systematic odometry errors in mobile robots," IEEE Trans. Robotics and Automation 12(6):869–880, 1996**(UMBmark). 체계적 오도메트리 오차는 하중·지면에 따라 달라 보정 값을 한 번만 맞추면 틀어진다는 근거(막힘 2, 그리고 편향 항). 이번 코드는 배율 상수 대신 플랜트 모델로 leg 길이를 계산한다. 지형/하중 성능은 실제 검증 없이 확정하지 않는다.
- **MoveIt Task Constructor, `MoveRelative`(min/max distance)와 Pick and Place 튜토리얼**: https://moveit.picknik.ai/main/doc/tutorials/pick_and_place_with_moveit_task_constructor/pick_and_place_with_moveit_task_constructor.html. 물러남을 "충돌 없는 데까지 움직이고 멈춤"(min distance 0)으로 정의한 `bounded_retreat`의 근거. 실제 소스(`core/src/stages/move_relative.cpp`)는 v6f 조사에서 열어 봤다.
- **광학 검정(optical black) 기준**(`own_image_ob`): e-con Systems "Black Level Correction in Image Sensors"(센서의 차광 영역으로 검정 기준 보정). v6f 조사에서 열어 본 것이며, 우리 렌더러에서는 어안 렌즈 바깥의 노출되지 않은 영역을 같은 역할로 썼다(`harness/zone_pair_vision.py`). 3000개 무작위 프레임 실험(5000개 미만 표본, 전체 275,205장 중): 기존 `valid_frame`은 49장 거절(전부 r1), `valid_frame_ob`는 0장. 한계: V가 광학 검정보다 3–7 높은 거의 검은 가림막은 저조도로 취급된다(테스트 `test_a_near_black_cover_above_the_optical_black_level_is_a_documented_limit_of_the_reference`).
- 저장소 내부: `experiments/2026-09-29-pair-v6c-carry/`(막힘 1–3 측정), `experiments/2026-09-28-pair-stage-probes/README.md`(#260 하네스), `harness/zone_own_guards.py`(`GATE_LOADED`), `scripts/study_owncam_pair_beam.py`(`CARRY_ODOM_SCALE`), `docs/execution_versioning.md`.

## 한계

- **물리 미실행.** 모든 물리 결과는 없다. 코드는 합성 단위 테스트만 통과했다.
- **stage probe이며 E2E가 아니다.** teacher 정답으로 자세를 만들고 한 leg 또는 내려놓기만 돌린다. 8 leg 이어 달리기 누적은 재지 않는다.
- **제어기 결과가 아니다.** 아직 어떤 셀도 b-v6e로 돌리지 않았다. "가설"은 v6c 진단 패치와 오프라인 계산의 방향에서 나온 것이다.
- **개발 지도에는 AprilTag가 있다**(v6c-carry '한계'와 동일: 시작 fix가 태그로 만들어지고 운반은 tag-blind). 최종 환경(태그 0개)에서의 증거가 아니다.
- **통로·지형 지도는 측정하지 못한다.** 하네스가 `UNSUPPORTED_PAIR_MAP`을 낸다(v6c-carry와 같음).
- **teacher IK 범위.** 19셀 중 6셀은 staging 불가라 분모에서 뺀다(along±·모서리 경계가 얇음).
- **seed는 PF 난수만 바꾼다.** 물리는 같으므로 seed 반복은 독립 증거가 아니다. held-out은 **배치**를 바꾸지만 같은 지도·같은 빔이다.
- **내려놓기 held-out은 같은 셀의 PF seed만 바꾼다**(경계 소스가 없어서). 독립 기하가 아니다.
- **보정 자료가 다른 하중이다**(dev 박스 운반 vs 두 로봇이 든 빔). 모델 오정합 가능성이 있다.
- 다른 에이전트의 작업이 같은 Mac에서 돈다(부하 15–25 관찰). SIM 시간이 판정이며 wall은 참고용이다.
- 테스트: origin/main `45a21b23`(#267·#268) 병합 뒤 관련 테스트 묶음(약 2000건)에서 실패는 봉인 해시 5건(`tests/test_zone_pair_registered_source.py`, 등록 전까지 예상)뿐이다. 병합 전 main `f5da3c6d`에서 보이던 기존 4건(v5c 태그 id, `test_zone_study_pair_delay` 3건)은 병합 뒤 통과했다. 전체 CI 묶음(316개 파일, 8 shard)은 배터리·부하(load 18) 때문에 로컬에서 돌리지 않았다. 코드가 바뀐 모듈을 import하는 테스트 파일만 골라 돌렸다.

## 사전 등록된 측정 계획

**이 계획은 측정 전에 고정한다.** 소스는 코호트 동안 커밋된 상태로 고정한다(러너가 tracked 소스 clean을 요구하고 `source_changed`를 기록). 이 계획과 다르게 한 것은 결과에 "계획 이탈"로 적는다. 아래 셀 수는 러너의 계획 출력(`--execute` 없이 나온 `cases` 수)으로 확인했다. staged 분모는 실제 실행 때 정해진다.

### 공통 조건

- 러너: `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.run_pair_stage_probes … --workers 2 --omp-threads 1 --execute --lock-owner claude --output /Users/changmin/projects/ugrp/outputs/pair-stage-probes-<sha8>-<태그>`. 병렬 워커 최대 2개, `--omp-threads 1`(러너 기본은 2). raw는 기본 체크아웃 `outputs/`에 절대 경로로 쓴다.
- 사전분포 `--prior-std e2e`(E2E 정합, σ 0.03 m / 0.012 rad), `--sources teacher`, seed `911`, nominal seed `911 912 913`(nominal 셀만 3 seed).
- **PF seed는 독립 반복이 아니다**(위 한계). 셀 단위 통과율은 분포를 보는 용도이고 통계적 유의성 검정에 쓰지 않는다.
- 진단 패치(`--diag-patch`)는 **쓰지 않는다.** 이 계획의 모든 실행은 패치 없는 제어기다.

### 계획 변경: 조건부 단계로 축소 (사용자 요청, 결과 확인 전, 2026-09-29)

사유: 케이스당 wall 약 90초, 전체 약 400건이면 약 5시간. **cal 코호트가 이미 시작된 뒤(첫 2건이 끝난 시점)이지만 어떤 코호트의 결과도 보기 전**에 정했다. 임계값·판정 기준은 그대로다. 아래가 실제 실행 계획이며, 뒤의 2–4번 절은 "전체 계획"으로 남기되 다음과 같이 읽는다.

1. **cal 40건**은 그대로 끝낸다.
2. **33셀 운반 격자는 정책 `b-v6e` 하나만** 돌린다. 기준선은 v6c-carry의 `b-v6c` 0/33을 인용한다. `b-v6d` 대조 재실행은 생략한다. 근거: carry 단계는 staging된 상태에서 시작하며, `b-v6d`가 `b-v6c`에 더한 두 플래그가 carry 코드 경로에 들어가지 않는다. (i) `align_fine_motion`은 `profile_for(state)`가 align 상태 4개(`align`, `align_relook_stop`, `align_relook`, `align_relook_return`)에서만 M1 프로필을 돌려주므로 carry 상태에서는 `None`이고, 프로필이 바뀌지 않는다(`harness/owncam_align_motion_v6d.py`, `harness/zone_pair_align.py::set`). (ii) `beam_wide_hue`는 `_beam_hue_lo`가 `p45`/`inspect` 자세에서만 값을 내며 이는 `_align` 관측에서만 호출된다(`scripts/study_owncam_pair_beam.py`). 이것은 **코드 읽기 근거**이며 `b-v6d`를 carry에서 돌려 확인한 것은 아니다. 그래서 개선 판정의 "기준선"은 `b-v6c` 0/33(v6c-carry)이고, 이 격자의 정책 차이 `b-v6e` vs `b-v6c`는 carry 플래그 두 개(+place 플래그 두 개가 carry에서는 무관)와 위 두 플래그(carry에서는 무관)다.
3. **절제**(`b-v6e-dr`, `b-v6e-lag`, `b-v6f-a`, `b-v6f-b`)는 통합 `b-v6e`가 임계값(운반 26/33, 내려놓기 10/13)에 **못 미칠 때만**, 실패 원인을 가르는 데 필요한 셀만 돌린다. 임계를 넘으면 절제는 돌리지 않으며, 그때 "절제가 보인 것"은 없다고 적는다(사전 예측 ①–③ 중 절제 정책에 대한 것은 검증하지 못함).
4. **내려놓기**는 `b-v6e` 목적지 13셀(staged 분모)과 픽업 위치 회귀 3셀(`nominal` 3 seed)을 먼저 돌린다. `b-v6c` 대조는 이미 있는 기준선 0/13, 3/3을 인용한다(v6c-carry).
5. **held-out은 배치 `hA` 하나만 먼저**(운반 legs 0 1 3 6 7, cells `nominal` + `yaw-/opp`, 내려놓기). **게이트를 통과할 때만** `hB`, `hC`를 돌린다. held-out 대조 `b-v6c`는 기준선 0/33에서 이미 실패가 확인된 정책이므로 생략하고 `b-v6e`만 돌린다(운반 hA 계획 10건).
6. 워커 2개 유지(부하 평균이 20을 넘으면 3개로 올리지 않는다).

### 계획 변경 2: 스모크 우선 순서 (사용자 요청, 격자 결과 확인 전, 2026-09-29)

사유: 전부 실패하는 문제가 있으면 400건을 돌리는 것은 낭비다. 임계값·판정 기준은 그대로다. **정직하게 적는 순서:** 이 변경은 cal의 첫 14건이 끝나(전부 PASS, 아래 결과 참조) 그 결과를 본 **뒤**에 정했다. 격자·내려놓기·held-out 결과는 보기 전이다. 이 변경으로 계획은 다음과 같다.

1. **cal 중단.** 40건 중 14건(leg 0·1·2, 셀 nominal×3 seed·`yaw+/same`·`lat-/opp`)이 끝난 시점에서 `ugrp_session.py stop v6e-cal`로 멈췄다(진행 중이던 케이스 2건은 결과 없이 버려졌고 표에서 뺀다). 끝난 14건은 그대로 보존한다. 나머지 cal(leg 3–7 26건)은 스모크가 통과한 뒤 필요하면 재개한다. **cal 정직성 판정은 아직 내리지 않았다**(표본 부족, 아래 결과).
2. **스모크 (`b-v6e`, 하나의 소스 SHA `ece38792`)** 10건: 운반 5(`--legs 0 1 3 6 7 --cells nominal`, 옆 이동 L3 포함), 내려놓기 5(목적지 `nominal`·`lat+/opp`·`yaw-/opp` 3건 + 픽업 위치 `nominal` 2 seed). 워커 2개.
3. **스모크 판정.** 같은 원인으로 전부 실패, 게이트가 무의미한 즉시 종료, 예외/HOST_ERROR, σ가 약 3 s에 게이트로 다시 자람 중 하나라도 보이면 즉시 멈추고 원인 진단을 보고한다(격자로 확장하지 않는다). 같은 문제로 두 번 막히면 멈추고 선행 자료를 조사한다.
4. **스모크가 정상일 때만** 위 "계획 변경"의 조건부 단계(33셀 격자 b-v6e, 내려놓기 13셀 + 픽업 3셀, hA)로 확장한다. 실패가 드물면 셀당 seed를 줄일 수 있다(줄이면 결과 표에 적는다).

### 1. 보정 코호트 `cal` (제어기가 아닌 필터 정직성 확인)

목적: 보정한 오차 모델이 stage 운반 셀에서도 PF를 "정직"하게(과신도 과소신뢰도 아니게) 만드는지 본다. 격자와 겹치지 않는다(`--setup-variant cal`은 격자·held-out과 다른 빔 배치 [.93, .03, 0]).

```
--stage carry --sources teacher --policies b-v6e --prior-std e2e --seeds 911 --nominal-seeds 911 912 913 \
--legs 0 1 2 3 4 5 6 7 --cells nominal yaw+/same lat-/opp --setup-variant cal --pf-track
```
계획 40건(셀 5 × leg 8, 1 정책). `--pf-track`은 PF 사후 평균·공분산을 0.25 SIM s마다 GT 옆에 기록하는 평가 전용·읽기 전용 출력이다(제어기 입력 아님).

- **정직성 판정(사전 제안):** leg 끝 시점에서 (x, y, yaw) 3자유도 평균 NEES가 [1.5, 6](기대값 3)이고, 각 축 ±2σ 커버리지가 ≥ 90 %. 정확한 임계는 **조정자 확정 대상**이다.
- 판정을 못 넘으면: **cal 자료로만** `fit_carry_dr.py`를 다시 맞추고 소스를 다시 커밋·고정한 뒤 1번을 반복한다. 격자(2번)는 시작하지 않는다. 격자·held-out 결과를 보고 모델을 고치지 않는다.

### 2. 단계 4 운반 33셀 격자 (본 측정)

분모는 19-6 + 4×(7-2) = **33**(셀 19에서 IK 범위 밖 6, leg 1·3·6·7은 7셀에서 2). 정책마다 같은 33셀이다(계획 76 + 112건, staged 132건 예상: 4 정책 × 33).

```
공통: --stage carry --sources teacher --policies b-v6d b-v6e-dr b-v6e-lag b-v6e --prior-std e2e --seeds 911 --nominal-seeds 911 912 913
(a) L0: --legs 0                                   (셀 19 전부: 계획 76건 = 19 × 4 정책)
(b) L1·L3·L6·L7: --legs 1 3 6 7 --cells nominal lat+/same yaw+/same along+/same corner++/same   (계획 112건 = 7 × 4 leg × 4 정책)
```

- **정책 절제 목록:** `b-v6d`(대조) / `b-v6e-dr`(막힘 1만) / `b-v6e-lag`(막힘 2만) / `b-v6e`(통합). 기준선은 같은 33셀의 `b-v6c` **0/33**(v6c-carry).
- **사전 예측(반증 가능):** ① `b-v6d`는 `b-v6c`와 같은 구조적 실패(≈3 s `SELF_POSE_UNCERTAIN`/yaw, 0/33 근처). ② `b-v6e-lag`도 σ 확산이 먼저 막아 0/33 근처. ③ `b-v6e-dr`은 L0·L1·L6은 통과하고 L3(옆 이동)에서 `MOTION_ERROR`, L7은 영상 검사로 실패할 것(`own_image_ob`가 없으므로). ④ `b-v6e`는 위 실패를 모두 피할 것. 예측이 어긋나면(예: `b-v6e-dr`이 L3에서 통과) 어긋난 대로 기록하고 원인을 진단한다.
- 성공 임계·중단 조건은 아래 공통 항목.

### 3. Held-out 코호트 `hA` / `hB` / `hC`

격자 설계·보정에 쓰지 않은 세 빔 배치(`SETUP_VARIANTS`: hA [.84, .13, 0], hB [1.13, −.04, 0], hC [1.03, .12, 0]; 모두 제어기 pickup 범위 안). 결과를 보고 어떤 소스도 고치지 않는다.

```
--stage carry --sources teacher --policies b-v6c b-v6e --prior-std e2e --seeds 911 --nominal-seeds 914 \
--legs 0 1 3 6 7 --cells nominal yaw-/opp --setup-variant hA    # hB, hC도 한 번에 하나씩
```
배치당 계획 20건(셀 2 × leg 5 × 정책 2), 합계 60건. 대조는 `b-v6c`(기준선 실패 재확인)와 b-v6e.

### 4. 단계 5 내려놓기 (같은 러너, 다른 stage)

place 단계 id와 격자는 `claude-v6e-place` 쪽 CHECKPOINT를 따른다: `--stage setdown --legs end`(목적지 = 경로 마지막 단계), 19셀 격자에서 staged 13(IK 밖 6). 기준선 b-v6c **0/13**(전부 `OWN_IMAGE_INVALID`), 예전 픽업 위치 3/3(`--stage setdown`, `--legs` 없음, `--cells nominal`).

```
목적지:   --stage setdown --sources teacher --policies b-v6c b-v6e b-v6f-a b-v6f-b --prior-std e2e --seeds 911 --nominal-seeds 911 912 913 --legs end   (계획 76건 = 19 × 4 정책)
픽업위치: --stage setdown --sources teacher --policies b-v6c b-v6e --prior-std e2e --cells nominal --nominal-seeds 911 912 913                         (계획 6건, 회귀 확인)
held-out: 목적지 격자에서 --seeds 921 --nominal-seeds 921 922 923, 정책 b-v6c b-v6e
```
- 정책 절제: `b-v6f-a`(영상만), `b-v6f-b`(물러남만), `b-v6e`(둘 다 + 운반 플래그; 내려놓기에서는 운반 플래그가 관여하지 않으므로 `b-v6f`와 동등해야 한다. 이를 확인하는 것도 측정이다). 대조 `b-v6c`(OMP=1 재측정 포함).
- 셀 (13): nominal(s911 912 913), along−/same, lat+/same, lat+/opp, lat−/same, lat−/opp, yaw+/same, yaw+/opp, yaw−/same, yaw−/opp, corner−−/same.
- **사전 예측:** `b-v6f-a` 단독은 영상 검사를 넘어 `COLLISION_GUARD`(물러남)로 끝나고(v6c-carry의 `image_valid_off` 0/13과 같은 원인), `b-v6f-b` 단독은 `OWN_IMAGE_INVALID`로 0/13 근처, `b-v6e`가 둘을 합쳐 통과. 내려놓은 뒤 후진이 벽에 막혀 **멈추면** 통과 판정(빔이 바닥에 안정)이지만 로봇이 충분히 물러나지 못한 것이므로 물러난 거리를 지표로 따로 기록한다.
- 일부만 서로 다르면 어긋난 대로 기록한다.

### 성공 판정 (GT, eval-only; v6c-carry와 동일, 결과를 본 뒤 바꾸지 않음)

| 단계 | 기준 |
|---|---|
| 4 운반 | 든 채 유지(높이 ≥ 3 cm), 기울기 ≤ 10°, 두 집게 접촉, 빔 이동거리와 계획 leg 길이 차 ≤ 10 cm(`leg_error`), 빔 끝점과 계획 경로점 거리 ≤ 10 cm(`end_error`) |
| 5 내려놓기 | 빔이 바닥에(높이 ≤ 5 mm), 기울기 ≤ 3°, 두 집게 모두 떨어짐, 이동 ≤ 5 cm |

**개선 판정(사전 제안, 조정자 확정 대상).** 아래 두 조건이 모두 성립해야 "이 stage probe에서 b-v6e가 기준선보다 낫다"고 적는다. 어느 쪽도 제어기 성공·E2E·학생 성공이 아니다.
1. 33셀 격자에서 `b-v6e`가 **≥ 26/33**(≈ 79 %)이고 leg 0·1·3·6·7 각각 최소 절반 이상 통과. 목적지 내려놓기 staged 13셀에서 **≥ 10/13**.
2. held-out에서 `b-v6e`가 운반 **≥ 24/30**, 내려놓기 **≥ 8/10**. 격자보다 크게 낮으면(격자 대비 20 %p 초과) 과적합 의심으로 기록한다.

### 중단 조건

- 시작 전: `agent_lock.py status`가 null이 아니면 시작하지 않는다(다른 작업 소유). 디스크 여유 < 10 GiB이면 시작하지 않는다(`ugrp_session.py run`이 거부하고, 사전 등록 규칙으로 ENOSPC는 `HOST_ERROR` 분류). 전원 어댑터 미연결(배터리)이면 시작하지 않는다(장시간 실행). tracked 소스가 dirty이거나 실행 SHA와 다르면 시작하지 않는다.
- 실행 중: ① 한 raw에서 `HOST_ERROR`·타임아웃이 20 % 넘으면 중단하고 원인 진단(소스 수정은 코호트 종료 뒤 새 커밋으로). ② manifest에 `source_changed=True`가 나오면 그 raw는 폐기가 아니라 "계획 이탈"로 표시하고 코호트를 다시 시작. ③ 보정 코호트가 정직성 판정을 못 넘으면 격자 진행을 멈춘다(위 1번). ④ 이 계획 안에서 새 실패 원인이 발견되어도 **코호트 도중에 코드를 고치지 않는다.**
- 사용자·조정자 중단 지시는 언제든 우선한다. 중단은 SIGINT로 자기 프로세스 그룹만 정리하고 다른 에이전트의 프로세스는 건드리지 않는다. 중단된 raw는 지우지 않고 "중단"으로 표시해 표·TensorBoard에서 뺀다.

### 예상 자원 (측정 전 추정, 부정확할 수 있다)

| 항목 | 추정 | 근거 |
|---|---|---|
| 케이스 수(계획) | 운반: cal 40 + 격자 188(76+112) + held-out 60 = 288 / 내려놓기: 목적지 76 + 픽업 6 + held-out 26 정도 ≈ 110 (staged는 약 70 %) | 러너 계획 출력 |
| SIM 시간 | 통과 운반 22–26 s, 실패 3–4 s, 예산 상한 운반 90 s / 내려놓기 60 s. 합계 **약 2–3 SIM 시간(상한 약 7 SIM 시간)** | v6c-carry의 SIM 시간 분포 |
| wall | 부하 15–25에서 통과 케이스가 워커당 약 4–5분(v6c-carry 합성 실행: 16건에 2268 s, 워커 2). 전체 **약 6–10 h**(2 워커). 1 raw씩 나눠 돌린다 | v6c-carry 표 |
| 디스크 | 케이스당 약 10–15 MB(v6c-carry: 167 MB / 16건, 173 MB / 13건). 전체 **약 3–5 GB**, `pf-track`으로 조금 더. 실행 전 여유 **≥ 10 GiB**(현재 여유 97 GiB) | 같음 |
| 부하 | 시작·종료 시 `uptime`/`sysctl vm.loadavg`를 driver 로그에 기록 | 공용 Mac |

### 실행 명령 (예시만, 지금 실행하지 않는다)

물리·학습은 `agent_lock`을 잡는다(driver가 자기 PID로 잡고 EXIT에서 해제하는 방식, v6f driver와 동일):

```bash
# 1) 다른 작업이 없는지
python3 scripts/agent_lock.py status            # null이어야 시작
# 2) driver가 자기 PID로 잠금을 잡는다 (PID $$는 driver 셸의 PID)
python3 scripts/agent_lock.py acquire --owner claude --branch claude/pair-v6e-carry \
    --purpose "v6e carry stage probes (cal cohort; SIM time, no models)" --pid $$ --expected-minutes 90
# 3) 끝나면
python3 scripts/agent_lock.py release --owner claude
```

`ugrp_session.py run`으로 자식 프로세스를 모두 정리하며 실행(디스크 10 GiB 미만이면 시작 거부):

```bash
python3 scripts/ugrp_session.py run v6e-cal -- bash /abs/path/driver.sh cal 90 /abs/path/spec-cal.txt
# spec 한 줄 예 (driver가 --workers 2 --omp-threads 1 --execute --lock-owner claude --output …/pair-stage-probes-<sha8>-cal 을 붙인다):
# cal --stage carry --sources teacher --policies b-v6e --prior-std e2e --seeds 911 --nominal-seeds 911 912 913 --legs 0 1 2 3 4 5 6 7 --cells nominal yaw+/same lat-/opp --setup-variant cal --pf-track
python3 scripts/ugrp_session.py stop v6e-cal      # 중단/정리
```

driver 스크립트는 v6f 작업의 `driver.sh`(scratchpad, 잠금·로그·부하 기록 포함)를 그대로 쓰되 브랜치와 worktree 경로를 이 worktree로 바꾼다. zsh에서는 셀 이름을 따옴표 없이 문자 그대로 전달한다(변수 확장 분리 안 됨).

## 실행 후 절차 (측정이 끝난 뒤에만)

1. 결과 확인 뒤 번들 `v81` / workflow `2.14.0` / revision `v6e`를 **한 번만** 등록·봉인(`scripts/zone_pair_v6_contract.py` 봉인, v6c/v6d 은퇴 목록, 봉인 해시 5건 해결). 이 등록 커밋 뒤에는 이 README의 측정 계획을 바꾸지 않는다.
2. 결과 표·raw 위치·해시를 이 README에 채운다(아래 "결과"). raw는 로컬 `outputs/`에만 있으며 원격 백업이 아니다.
3. TensorBoard 스냅샷(`docs/tensorboard.md`; `outputs/tensorboard-view.json`은 쓰기 직전에 다시 읽고 내 키만 추가), push는 최종 상태에서 1회 + PR(`Refs #221`).

## 결과 (부분 측정: 스모크, cal 2회, 내려놓기 목적지·픽업. 운반 격자·held-out·절제는 실행하지 않음)

**이 절의 모든 수치는 stage probe이며 E2E·제어기·학생 성공이 아니다.** 소스 트리 해시(`source.execution_tree.sha256`)는 `ece38792`와 `a704ecc6`(문서만 다름)에서 같고(`d4afff8b…`), `d08818ef`는 재적합 1회로 바뀌었다(`2549d0b3…`). 모든 raw에서 `source_changed=False`. weld OFF, `cargo_noslip_v1`, 모델 호출 0, 진단 패치 없음.

### 계획 변경 3 (조정자, 2026-09-29, cal 결과를 본 뒤)

cal이 아래 구조 문제를 보여서 **33셀 운반 격자·held-out 운반·운반 절제는 현재 소스로 돌리지 않았다**(L1이 실패할 것이 예상되고 정보가 없다). 독립인 내려놓기 격자는 현재 소스 `d08818ef`로 돌렸다. 게이트 임계 상향은 SweepGuard가 σ_yaw·lever로 다음 게이트에서 다시 막는다는 v6c-carry 진단이 있어 단독으로 하지 않았다. **내려놓기 결과는 운반 수정 뒤의 최종 소스에서 다시 확인해야 한다.**

### 표

| 코호트 | 소스 | 정책 | 통과/분모 | 기준선 | 판정·비고 |
|---|---|---|---|---|---|
| 스모크 운반 (L0 1 3 6 7 nominal, 기본 배치) | a704ecc6 | b-v6e | **5/5** | b-v6c 0/33(격자) | 스모크. 아래 "스모크 통과의 뜻" 참조 |
| 스모크 내려놓기 (목적지 3, 픽업 2) | a704ecc6 | b-v6e | **5/5** | b-v6c 0/13, 3/3 | 스모크 |
| cal-1 (40건, cal 배치, leg 0–7 × nominal×3 seed·yaw+/same·lat-/opp) | ece38792 = a704ecc6 소스 | b-v6e | **35/40** | – | 실패 5건 전부 L7 `COLLISION_GUARD`(r2). PF 정직성 **불통과**(yaw 커버리지 82.5 %) |
| cal-2 (같은 40건) | d08818ef (재적합) | b-v6e | **23/40** | – | L0 4/5(yaw+/same `COLLISION_GUARD`), **L1 0/5, L2 0/5 `SELF_POSE_UNCERTAIN`(yaw)**, L3·L4·L5 15/15, L6 4/5(nominal s913 `SELF_POSE_UNCERTAIN`), **L7 0/5 `COLLISION_GUARD`**. PF 정직성 **수치상 통과(표본 안)** |
| 운반 33셀 격자 | – | – | **미측정(조정자 결정으로 보류)** | b-v6c 0/33 | – |
| 운반 held-out hA/hB/hC | – | – | 미측정 | – | – |
| 절제 b-v6e-dr/-lag, b-v6f-a/-b | – | – | 미실행(통합이 임계 미달일 때만이 계획이었고 운반은 격자를 안 돌림, 내려놓기는 임계 통과) | – | – |
| **내려놓기 목적지 13셀(staged 분모)** | d08818ef | b-v6e | **13/13** (계획 19 = 13 + STAGING_IK_ENVELOPE 6) | b-v6c 0/13 | 임계 10/13 통과. 아래 주의 |
| **내려놓기 픽업 위치 3셀(nominal×3 seed)** | d08818ef | b-v6e | **3/3** | b-v6c 3/3 | 회귀 없음 |
| 내려놓기 held-out | – | – | 미측정 | – | – |

내려놓기 13/13의 뜻: 13 = nominal 3 seed + 10 셀(along−/same, lat+/same, lat+/opp, lat−/same, lat−/opp, yaw+/same, yaw+/opp, yaw−/same, yaw−/opp, corner−−/same). 6셀은 staging IK 범위 밖이라 분모에서 뺐다(along+/same·along+/opp·along−/opp·corner++/same·corner++/opp·corner−−/opp). **PASS 13건 모두에서 `retreat_bounded`(`SWEEP_GUARD_VETO_AFTER_RELEASE`, SIM 12.7–13.1 s)가 발생했다**: 놓은 뒤 후진을 스윕 가드가 거절해 멈춘 것이다. 트레이스에서 시작 위치 대비 최종 이동량은 r1 약 0.15 m, r2 약 0.07–0.09 m로, 충분히 물러났다는 뜻이 아니다(예측대로 "멈추면 통과"). 이 이동량은 트레이스 처음과 끝의 GT 위치 차이로 계산한 대략치다. 한 번에 seed는 nominal만 3개이고 다른 셀은 1 seed다. seed는 PF 난수만 바꾸므로 독립 반복이 아니다.

### cal 게이트 판정

목적: 오차 모델이 PF를 정직하게 만드는가(NEES [1.5, 6], ±2σ 커버리지 ≥ 90 %). leg 끝(실패 시 정지 시점) 3자유도 NEES, 케이스×로봇 80개 표본. nominal 3 seed는 같은 물리라 실효 표본은 더 적다.

| | 평균 NEES | x 커버리지 | y 커버리지 | yaw 커버리지 | 판정 |
|---|---|---|---|---|---|
| cal-1 (yaw bias 0.00139 rad/s, dev-box 적합) | 4.02 | 100 % | 100 % | **82.5 %** | **불통과** |
| cal-2 (yaw bias 0.00233 rad/s, cal 자료로만 재적합 1회) | 2.30 | 100 % | 100 % | 93.8 % | 통과. **같은 cal 자료로 맞춘 표본 안 결과이며 독립 검증이 아니다** |

- 재적합 규칙: `refit_carry_dr_cal.py`. 케이스×로봇의 yaw 오차 성장률(마지막-처음 PF-vs-GT yaw 오차/경과)을 셀별 RMS(nominal 0.00090, yaw+/same 0.00182, lat-/opp 0.00349 rad/s)로 내고 셀 가중 평균 RMS 0.00233 rad/s를 새 bias std로 썼다. x/y 항·백색 잡음·게이트는 그대로다. 격자·held-out은 읽지 않았다. 테스트 `test_loaded_rest_does_not_diffuse_…`의 마진을 0.005→0.003 rad로 완화해야 했다(정직한 σ가 14 s에 이미 2.77°까지 자란다).
- 재적합은 사전 등록된 대응(README "1. 보정 코호트")을 그대로 한 것이며, 결과 후 임계값은 바꾸지 않았다.
- 분석 파일: `analysis/nees_cal1.txt`, `analysis/nees_cal2.txt`(스크립트 `analysis/nees_pf.py`).

### 스모크 통과의 뜻 (정직한 기록)

스모크 5/5는 **운반이 해결됐다는 뜻이 아니다.** 스모크는 기본 배치의 nominal 셀만 돌렸고, 이 셀이 yaw 편향이 가장 작다(아래 분해: nominal 계통 편향 0.9 mrad/s RMS, 다른 셀 1.8–3.5). 사용한 σ는 ece38792의 dev-box 적합값이며, 그 σ는 cal에서 yaw 커버리지 82.5 %로 **yaw를 과소 표현**했다. 즉 스모크의 통과 일부는 σ가 작게 보고돼 3° 게이트에 닿지 않았기 때문이다. 실제로 σ를 정직하게 키우자(cal-2) 같은 nominal L1·L2가 `SELF_POSE_UNCERTAIN`으로 0/5가 됐다. baseline b-v6c(0/33)와 같은 원인이 σ 크기만 바꿔 다시 나타난 것이다.

### 운반 원인 분석 (기록된 raw만, 새 시뮬 0, 코드 수정 0)

스크립트: `analysis/yaw_drift_decomposition.py`(GT 로봇 yaw 변화율 / PF yaw 변화율 / GT 빔 yaw 변화율, mrad/s), `analysis/carry_frame_features.py`(운반 프레임 특징). 출력은 같은 폴더의 txt.

1. **yaw 오차는 결정적이고 두 성분이다.** PF seed 3개의 leg별 오차율 차이는 0.16 mrad/s 이하(재현됨). (i) **모델 유래 성분:** nominal 셀 옆 이동 leg(L3–5)에서 GT 빔 yaw는 거의 안 움직이는데(-0.3…+0.3) PF yaw만 r1 +1.5, r2 −1.5 mrad/s로 움직인다. 이는 한 대가 든 상자로 적합한 등록 든 플랜트의 yaw 결합 항이 **빔으로 yaw가 구속된 쌍**에는 맞지 않기 때문이다(평균 모델 오차). (ii) **물리 성분:** lat-/opp·yaw+/same 셀에서는 빔 자체가 축 이동 leg에서 실제로 돈다(빔 yaw +2.6…+3.3, +1.6 mrad/s). 시작 배치 차이는 빔 횡 오프셋 ±1 cm, yaw ±2° 정도인데 회전율이 0에서 3 mrad/s로 달라져 단순 오프셋으로 예측하기 어렵다(3개 배치라 회귀는 못 함). 편향이 leg 안에서 상수라 정지 시 σ만 키우는 모델(분산 인플레)은 잘못된 도구다(Thrun *Probabilistic Robotics* 5장의 systematic drift, Borenstein·Feng UMBmark의 계통 오차는 분산이 아니라 평균 모델 보정 대상).
2. **운반 중 yaw 관측이 없다.** 기록된 운반 자기 RGB 프레임(loaded 상태 3396장 표본, 12프레임마다) 전체에서 빔이 시야 위쪽 약 20 %를 차지하고 나머지는 어두운 바닥(V 평균 16)이다. 빔이 아닌 픽셀 중 V>45인 구조 픽셀 비율은 평균 0.06 %, 1 % 넘는 프레임은 11장뿐이고 전부 들기 직후 자세 전환 프레임(픽업 2 s 뒤)이다. 벽·구조물·바닥 경계·태그가 운반 자세에서는 보이지 않는다(카메라는 팔에 달려 있고 팔이 빔을 잡고 있다). 그래서 등록 PF의 마지막 태그 관측은 운반 시작 전(`last_valid_obs` t=3.1 s)에 머무른다. 기존 tag-free 관측기(#233, 벽/문 분할)도 같은 프레임을 쓰므로 여기서는 관측을 못 준다. 공용 top RGB는 stage probe raw에 기록되지 않아 분석하지 못했다.
3. **leg 분할·정지 후 둘러보기는 σ를 리셋하지 못한다.** 위 2 때문에 정지해도 볼 수 있는 것이 없다(팔을 움직이면 빔을 놓는다). 한 leg의 이동은 약 17 s이고 경로는 8 leg(약 120 s 이동)다. bias std 0.00139 rad/s여도 120 s에 σ_yaw 0.17 rad(9.6°), 0.00233이면 0.28 rad(16°)로 게이트 3°(0.052 rad)를 leg 하나 안에서도(약 22 s) 넘는다. 분할은 leg당 σ가 아니라 경로 누적이 문제라서 도움이 안 된다.
4. **L7 `COLLISION_GUARD`는 σ 문제가 아니라 배치 문제로 보인다.** cal 배치 L7만 5/5 실패(σ 두 값 모두), 기본 배치 L7은 통과. 실패 시점의 남은 그립 오차 −1.15 cm(leg를 거의 끝내고 마지막 스윕을 가드가 거절). 원인 확정은 못 했다(동쪽 벽 근접 가설, 미검증).

### 후보 방향과 추천 (코드 수정 없음, 조정자 결정용)

| 후보 | 근거 | 기대 효과 | 위험 |
|---|---|---|---|
| (a) 평균 모델 보정: 든 **쌍** 플랜트에서 yaw 결합을 빼거나 cal로 다시 적합 | 위 1(i), UMBmark, Thrun 5장 | nominal 계통 성분(±1.5 mrad/s)을 거의 제거해 nominal은 0.2 mrad/s 근처로 | 물리 성분(ii)은 남는다(2–3 mrad/s × 17 s ≈ 2–3°). 3개 배치만 있어 배치 의존을 못 보임 |
| (b) 운반 중 yaw 관측 추가: 공용 top RGB로 쌍의 빔·로봇 yaw 측정 | AGENTS의 허용 입력(자기 RGB·공용 top RGB), 위 2 | 유일하게 (ii)도 다룬다. AMCL처럼 측정이 편향을 계속 지운다 | 저장소에 운반 중 top 기반 추정기가 없고 stage probe에는 top이 기록되지 않아 정밀도 추정을 못 했다. 새 관측기·검증 필요 |
| (d) leg 분할·정지 둘러보기 | 위 3 | 없음(관측이 없음) | 시간만 늘고 σ 누적은 그대로 |
| (c) 게이트 임계 상향 | – | 단독으로는 v6c-carry 진단에 따라 SweepGuard가 σ로 막음 | 사전 등록 파라미터 변경, 실제 yaw 오차 5–7°를 허용 |

**추천 1안: (a)를 먼저 하고 (b)를 병행 설계.** (a)는 코드 한 항이고 cal 자료로 검증할 수 있으며 nominal 유래 오차의 대부분을 없앤다. 다만 (a)만으로는 물리 성분 때문에 정직한 σ가 leg 후반에 게이트를 넘을 가능성이 높아 운반 완주의 충분조건이 아니다. 경로 전체(약 120 s 이동)를 넘는 yaw 유지는 관측이 있어야 하므로 (b)의 top RGB 관측 가능성(정밀도·가림)을 먼저 측정하는 것이 다음 단계다. 이것은 추정이며 측정하지 않았다.

### 실행 기록

| raw (`/Users/changmin/projects/ugrp/outputs/pair-stage-probes-…`) | 케이스 | cases.jsonl sha256 | 크기 | 시작(UTC)/부하(1분) |
|---|---|---|---|---|
| ece38792-cal (중단, 14건 완료 + 2건 버려짐) | 14 | 3a349438…16b74e | 154 MB | 03:19:59 / 14.6 |
| a704ecc6-smokeC | 5 | 8219921f…070bc | 52 MB | 03:33:01 / 8.7 |
| a704ecc6-smokeSD | 3 | 1ddd9b58…87de4 | 17 MB | 03:37:11 / 13.9 |
| a704ecc6-smokeSP | 2 | ca7e52fb…c79 | 13 MB | 03:38:47 / 13.2 |
| a704ecc6-calB2 (cal 이어서: L2 yaw+/same) | 1 | 8be12822…88ce9 | 11 MB | 03:40:20 / 9.6 |
| a704ecc6-calB (cal 이어서: L3–L7) | 25 | b84fd24c…f2728460 | 258 MB | 03:41:45 / 14.1 |
| d08818ef-cal2 | 40 | 59784ca5…da8a | 414 MB | 04:09:16 / 7.4 |
| d08818ef-placeD (목적지 19 계획, 13 staged) | 19 | be366619…11db | 75 MB | 04:47:43 / 9.1 |
| d08818ef-placeP (픽업) | 3 | fd22c9bb…920c | 19 MB | 04:53:47 / 26.7 (다른 작업 부하) |

- 잠금: 케이스마다가 아니라 driver 실행마다 `agent_lock.py acquire`/release(각 driver 종료 시 자동). 워커 2개, `--omp-threads 1`. 케이스당 wall 운반 약 80–120 s, 내려놓기 약 45–55 s, SIM 시간 통과 운반 19–26 s. HOST_ERROR 없음(내려놓기 STAGING_IK_ENVELOPE 6건은 staging 불가로 분모에서 뺌). cal-1 도중 조정자 지시로 `ugrp_session.py stop v6e-cal`을 했다(진행 중 2건 결과 없음).
- cal-1은 14건 완료 시점(전부 PASS)에서 멈췄다가 나머지 26건을 소스 트리가 같은 a704ecc6 커밋에서 이어 돌렸다(raw 3개, 위 표).
- 소스 SHA: 스모크·cal-1 이어 돌리기 `a704ecc6`(문서만 변경), 내려놓기·cal-2 `d08818ef`. 결과는 raw로컬에만 있고 원격 백업이 아니다.
- **등록(v81/2.14.0/v6e)·봉인·push·PR 하지 않았다.** 봉인 해시 테스트 5건은 예상대로 실패 상태다.

### 한계·미해결

- 운반은 33셀 격자·held-out·절제를 측정하지 못했다. 운반 결과는 cal 배치(격자와 다른 배치) 40건과 스모크 5건뿐이다. b-v6e의 운반 개선 여부는 **모른다**.
- cal-2의 "정직성 통과"는 재적합에 쓴 같은 cal 자료 위의 결과다.
- 내려놓기 13/13은 놓은 뒤 후진이 가드에 막혀 멈춘 통과다. 운반 수정 뒤 최종 소스에서 재확인이 필요하다. held-out은 없다.
- 반증 예측 ①–④(운반 절제 정책)는 격자를 안 돌려 검증하지 못했다. 예측 ⑤(내려놓기: `b-v6f-a` 단독은 물러남에서 막힘, `b-v6f-b` 단독은 영상 검사에서 막힘)도 절제를 안 돌려 검증하지 못했다. 통합 b-v6e의 내려놓기 통과는 예측과 같은 방향이다.
- TensorBoard: 아래 절.

## yaw 방향 분석 (오프라인, 2026-09-29, 새 물리·probe 0, 소스 변경 0)

**이 절은 기록된 raw만 다시 읽은 분석이다.** 제어기 결과도, E2E도, 새 측정도 아니다. 아래 모든 "예측"은 leave-one-cell-out(LOPO)로 검증한 오프라인 회귀이며 물리로 확인하지 않았다. 스크립트·출력은 `analysis/`(`yaw_direction_*.py/.txt/.json`, `beam_edge_*.py/.txt/.json`, `ultrasonic_yaw_information.py/.txt/.json`)에 있다. 입력 경계: 표적(GT yaw)은 eval-only이고 분석에서만 쓴다. 후보로 남기는 양은 자기 명령·정적 계획·자기 손목 RGB뿐이다(TOP·GT 배치는 "누출"로 표시하고 후보에서 뺐다).

### 읽은 raw와 한계

- 읽은 것: cal-1(`ece38792-cal`, `a704ecc6-calB2`, `-calB`), cal-2(`d08818ef-cal2`), 스모크(`a704ecc6-smokeC`), 그리고 v6c-carry의 **진단 패치 full-leg raw**(`e1c99f99-dxSigma/B/C/D/E`, `3061a66e-dxAllC`, `64767041-dxAllC2/D/S`, `cc84a791-postAllL3`; 명령이 열린 고리라 물리는 같다). 합계 328 case-robot, 물리 기준 124 레코드, 셀 이름 11개(nominal, along−/same, lat±/same, lat±/opp, yaw±/same, yaw±/opp, corner−−/same). 프레임 분석은 seed 911 200 case-robot.
- **이 분석이 33셀 격자의 경계 셀을 이미 읽었다.** 그래서 그 셀은 이 회귀의 held-out이 아니다. 진짜 held-out(hA/hB/hC, 반쪽 허용오차 셀)은 아직 읽지도 측정하지도 않았다.
- 11개 셀은 **허용오차 경계값(8 mm·12 mm·0.035 rad)과 0**뿐이다. 중간 크기 오프셋에서 선형인지, 다른 빔·다른 하중에서도 같은지는 모른다. 물리는 하나(같은 지도·같은 빔)라 seed·배치 반복은 독립 증거가 아니다.
- 표적 = (GT 로봇 yaw 변화 − 등록 든 플랜트 예측)/구간. 예측은 기록된 자기 mecanum 명령을 `calibration_loop_v2`의 `motion_loaded`(tau 0.8/0.05 s, gain 3행)로 다시 적분한 것이며, PF 평균과 비교해 검증했다(160건, RMS 차 1.5 mrad/20 s 창, 상관 0.998). 구간은 entry~exit(프레임 분석은 entry+3 s~exit).
- RMS는 "셀별 RMS의 셀 균형 RMS"다(각 셀 1회, `refit_carry_dr_cal.py`와 같은 규칙). 게이트 시간은 `σ(t)=√(σ0²+(b·t)²)`, σ0=0.0104–0.0129 rad, 3° 게이트로 계산했고 cal-2 PF 기록으로 검증했다(L0 끝 σ 0.048 rad, b=0.00233·20 s). 통과 leg의 이동 시간(live)은 L0 18.5, L1 24.4, L2 23.3, L3–5 20.75, L6–7 21.15 s(합 170.8 s).

### (a) 든 쌍 플랜트 yaw 평균 모델의 상한 효과

먼저 원인 (i)와 (ii)를 분리해서 보였다. (i) 플랜트 결합 오차는 **정확히 반대칭**이다. 등록 모델의 yaw 행 결합(옆 이동 −0.0512, 앞 이동 +0.0023)이 r1 +1.4, r2 −1.4 mrad/s를 예측하는데(옆 이동 leg) 실제 빔은 강체라 두 로봇이 같이 돈다. 둘의 예측 평균을 쓰면(빔 yaw 추정 = 두 플랜트 예측의 평균, 상대 명령은 정적 계획에서 알 수 있어 통신이 필요 없다) nominal의 RMS가 1.11 → 0.11 mrad/s로 줄고 8 leg 누적 오차가 ±5° → 0°다(아래 표). (ii)는 물리다.

| 추정기 | 알아야 하는 것 | 셀 균형 RMS (mrad/s) | 3° 게이트 도달 (live s) | L1 24.4·L2 23.3 통과 |
|---|---|---:|---:|---|
| E0 등록(현 v6e, 3 cal 셀 기준 0.00233) | 자기 명령 | 2.33 (11셀 2.15) | 21.8–22.0 (11셀 23.5–23.8) | 0/5·0/5 (cal-2 실측), 11셀 값은 L2 경계 |
| M1 명령만의 평균 보정(LOPO) | 명령, 역할 | 2.25 | 22.6–22.8 | 효과 없음 |
| **E1 쌍 평균 모델** | 명령, 계획 | **1.86** | **27.2–27.5** | 예(여유 11 %) |
| **E2 = E1 + 자기 RGB 상대 yaw** | + 빔 가장자리 기울기 | **1.50** | **33.8–34.2** | 예(여유 39 %) |
| E3 = E2 − 배치 회귀(측정 오프셋 오차 4 mm·3 mm·8 mrad, 가정) | + 쌍 오프셋 측정 | 0.80 | 63.7–64.5 | 예(여유 160 %) |
| E3, 오프셋 오차 2배 | | 1.53 | 33.1–33.5 | 예 |
| E3, 오프셋을 **첫 프레임 영상에서 추정**(LOPO) | 영상 y 0.5 mm, yaw 23 mrad | 1.14 | 44.6–45.1 | 예 |
| E3, 오프셋 오차 0(상한) | | 0.25 | 203–205 | 예 |
| 누출 L1: GT 빔 yaw를 관측한다고 가정 | GT | 0.18 | 281–284 | – |
| 누출 L2: 셀 고정효과(GT 배치 신원, 표본 안, 로봇별 회귀 표) | GT | 0.29 | 약 177 | – |

- **명령만으로는 (ii)가 예측되지 않는다**(M1 2.25 ≥ M0 2.18). 배치 의존 성분(셀 RMS 1.4–3.5 mrad/s)은 자기 오프셋으로만 설명된다. 로봇 자기 오프셋만 쓰면(파트너 오프셋 없이) 1.61로 거의 못 줄인다(M2o). **쌍 오프셋(양쪽)이 필요하다.**
- 물리 회귀(전 데이터 적합, 참고): 축 방향 leg에서 공통 yaw 오차율 = −0.38 mrad/s per mm(두 로봇이 빔에 대해 같은 방향으로 옆으로 치우친 정도, `u_y`), −0.79 per 10 mrad(반대 방향 yaw 오프셋, `w_s`), +0.23 per 10 mrad(같은 yaw 오프셋); 옆 이동 leg는 `u_y`에 무감각(+0.02)하고 yaw 오프셋(+0.25 per 10 mrad)에만 반응한다. 축 방향으로 갈 때 두 로봇이 같은 방향의 힘을 같은 옆 오프셋에서 내므로 빔에 우력이 생긴다는 해석이다(추정, 미검증). `u_x`(along 반대부호)는 격자에서 staging이 안 돼 데이터가 없다.
- **LOPO는 거울 셀이 훈련에 남아 있어 선형·기함수 가정을 시험할 뿐이다**(lat+/opp를 빼도 lat−/opp가 있음). 새 오프셋 크기·새 요인은 시험하지 않았다.
- 정직성(2σ 커버리지, σ_end=√(0.0104²+(b·live)²)): E0 97.0 %, E1 93.5 %, E2 98.0 %, E3(오차 x1) 98.2 %. 모두 ≥ 90 %.
- **한 leg 게이트만 통과한다는 뜻이다.** 상수 편향 b가 8 leg 전체(170.8 s)를 관측 없이 3° 안에 두려면 b ≤ 0.30 mrad/s여야 한다. 위 표의 어떤 추정기도(E3 상한 0.25만 예외) 이를 못 넘고, E3(오차 x1) 8 leg 끝 σ_yaw는 7.8°, E2는 14.7°다. 실제 3 cal 셀의 8 leg 누적 오차(GT − 추정, 도, r1/r2): nominal E0 −5.5/+5.1 → E1 0.0/−0.4; yaw+/same E0 +2.8/+13.4 → E1 +8.4/+7.8 → E2 +8.3/+7.8; **lat−/opp E0 −5.0/+38.0 → E1 +0.6/+32.4 → E2 +16.4/+16.2**. 즉 경계 배치에서는 **추정이 아니라 빔이 실제로 8–16° 돈다**(공통 모드). 추정기로는 못 없앤다.
- L7은 live 21.2 s라 yaw 게이트만 보면 E0도 통과하고, cal의 L7 실패는 `COLLISION_GUARD`(이 분석과 무관, 미해명)다.
- 표에서 E0(11셀)의 L2는 경계값이라 cal-2 실측(0/5)과 헷갈리지 않아야 한다. cal 3셀 값 0.00233이 실제 등록값이고 그때 L1·L2가 실패했다.
- 남는 모르는 것: yaw+/same의 L2에서만 회전이 0.02 mrad/s(L1은 1.58)인 이유(leg 의존성 미해명), L1이 L0보다 옵셋 셀에서 1.25–1.4배 큰 이유, 창 시작 3 s 차이.

### (b) 초음파(자기 전면 거리)

결론: **어떤 leg에도 yaw 정보가 없다.** 두 가지가 독립적으로 막는다(`analysis/ultrasonic_yaw_information.txt`, 저장소의 `expected_range`, 같은 ray 패턴·에코 규칙, 정적 지도 `zone_wide_door_tags_v2_dock_v3`).

1. **시선이 막힌다.** 마주 보는 쌍의 전면 원뿔은 빔 축(±x)을 따라 상대 로봇을 향한다. 현 lift(0.095)에서 첫 에코는 자기 짐의 끝면(0.042 m, docs 4·8절)이고, 권장 lift 0.110로 짐을 원뿔 위로 올려도 상대 로봇 전면(0.666 m)이다. 지도의 벽·문기둥은 모든 leg에서 1.0–3.97 m라 항상 뒤에 있다(첫 에코가 되지 않는다). 측면은 보지 못한다.
2. **막히지 않아도 yaw는 안 나온다(가상).** 원뿔 최소 거리 에코는 평평한 벽을 수직 입사할 때 수선의 발이 첫 에코라 **거리가 원뿔 반각(15°) 안의 yaw에 독립**이다(constant-depth 성질). 지도의 벽이 모두 축 정렬이고 로봇도 축 방향이라 유일한 회전 신호는 yaw ≥ 9–15° 근처의 문기둥 가장자리뿐이다. yaw −3°와 +3°에서 거리 차가 1σ를 넘는 표본은 leg 8개·로봇 2대 전부 **0 %**(표본 28–43개/leg, 차이 중앙값 0.0 mm, σ 중앙값 16–39 mm). ray 표본 빈틈(2.2°)에서 오는 ±1 mm 요동은 잡음(3 mm + 1 %)보다 작다.

| leg | 지도 앞 벽 거리 r1 / r2 (가상, m) | 실제 첫 에코 | yaw 정보 |
|---|---|---|---|
| L0 | 1.00–1.54 / 2.37–2.92 | 짐 끝면 0.04 m(현) 또는 상대 0.67 m(lift 0.110) | 없음 |
| L1 | 1.00–3.95 / 2.92–3.77 | 같음 | 없음 |
| L2 | 2.52–3.32 / 1.00–3.97(일부 무에코) | 같음 | 없음 |
| L3–L5 | 2.52 / 1.32–1.35 | 같음 | 없음 |
| L6 | 1.82–2.52 / 1.32–2.02 | 같음 | 없음 |
| L7 | 1.12–1.82 / 2.02–2.72 | 같음 | 없음 |

- 상대 로봇 전면 거리(0.666 m)는 상대 yaw에 0.34 mm/deg만 반응하고(±6°, 표본) 읽기 σ는 9.7 mm라 leg 평균(330회)으로도 1.6° 잡음이며, 간격 1 mm가 2.9°와 구분되지 않는다. 그 정보는 (c1)의 영상이 이미 더 정확히 준다. 초음파의 쓸모는 **쌍 간격(파지 미끄러짐) 확인**과 충돌 여유이며 yaw가 아니다. 이 용도는 이번 분석 범위 밖이다.
- 센서 모델 오차(장착 위치·기울기, 15° 반각 미확인, 2.2° ray 빈틈, 상대 센서 간섭 crosstalk)는 위 결론을 바꾸지 못한다(간섭은 오히려 상대 로봇 에코를 대체해 더 나쁘다).
- 문헌(원문 이번에 미확인, 기억): Leonard & Durrant-Whyte, IEEE TRA 7(3), 1991("regions of constant depth": 단일 초음파 거리는 평면의 방위가 아니라 수직 거리만 준다). 저장소 조사(`docs/ultrasonic_range_sensor.md`, Thrun 6.3 beam 모델)와 일치한다.

### (c) 그 외 자기 입력 후보

| 후보 | 근거 | 측정한 것 | 위험 |
|---|---|---|---|
| **c1 자기 RGB 빔 가장자리 = 로봇-빔 상대 yaw** | 이 분석에서 새로 측정. 손목 카메라가 빔 윗면 띠를 위쪽 20 %에 보고, 띠 아랫 가장자리의 기울기 변화가 로봇-빔 상대 yaw 변화와 1:1이다 | 200 case-robot에서 기울기 변화 = 0.96 × 상대 yaw 변화(상관 0.994), 중앙 비율 0.995, 잔차 1.9 mrad(0.11°/leg), 상대 yaw 변화가 작은 138건의 기울기 변화 표준편차 0.73 mrad(최대 1.9). 최저 비율 0.56–0.71은 corner−−/same, lat+/same의 r1(원인 미확인) | **공통 모드(빔 yaw)는 못 본다**(yaw+/same은 상대 yaw 0). 경계 셀에서 RMS 2.15 → 1.50 mrad/s(E2)만 줄인다. 조명 색이 바뀌면(hue 25–90 마스크) 재보정. 새 추출기 코드 필요 |
| **c2 쌍 대칭 플랜트 (E1)** | Thrun *Prob. Robotics* 5장·UMBmark(계통 오차는 평균 모델 보정), 강체 쌍 제약 | nominal RMS 1.11 → 0.11, 8 leg 누적 ±5° → 0° | 배치 의존 성분은 그대로. 상대 명령이 정적 계획에서 나온다는 가정(역할 부호). 정렬 구간의 turn 명령은 비대칭이라 평균에 잘못 들어간다(무시할 크기 −0.0006) |
| **c3 오프셋 회귀 (E3, 우력 사전 보정)** | 위 회귀. 자기 영상으로 측정: 옆 오프셋 y는 첫 프레임 (기울기, 중심 높이)에서 0.5 mm(11셀 LOPO), **yaw 오프셋은 못 잰다**(오차 23 mrad, 허용오차 35 mrad과 같음) | E3 영상 오프셋 b=1.14. yaw±/opp가 남는다(2.2–2.4 mrad/s) | 쌍 오프셋이 필요하므로 **파트너의 측정값 전달(상태 레코드)이 필요**하다. 통신 조건이 조작 변수라 사용자 결정 필요. 선형 가정, 경계 셀 11개뿐 |
| c4 leg 분할·정지 자세 둘러보기 | v6e 위 "운반 원인 분석 3" | 운반 중 팬은 1467–1533 펄스(±33)만 썼고 구조 픽셀 0.06 %. **더 넓은 팬으로 벽/바닥 경계가 보이는지는 측정하지 않았다**(팔이 빔을 잡고 있어 팬이 가능한지 미확인) | 안 되면 시간만 늘고 σ는 그대로. 물리 확인 필요 |
| c5 leg 순서·경로 재설계로 편향 상쇄 | UMBmark의 대칭 경로(시계·반시계) | 축 방향 leg는 모두 +x 방향이고 우력 부호가 힘 방향을 따라 뒤집히므로 −x 축 leg가 있어야 상쇄한다. 경로가 문→영역 B로 고정이라 불가 | 전진·후진 왕복은 시간 2배, 상쇄는 일부 |
| c6 옆 오프셋 허용오차 강화 / 우력 상쇄 yaw 트림 | 회귀 계수: 축 leg에서 0.38 mrad/s per mm → 5 축 leg(109 s)에서 mm당 2.4° | 8 mm 오프셋은 19°까지 커질 수 있다(선형 외삽). 경로 누적 3°를 지키려면 옆 오프셋 ≤ 1.2 mm, 반대 yaw 오프셋 ≤ 6 mrad. 영상은 y를 0.5 mm로 잴 수 있어 옆 오프셋은 파지 전 정렬로 줄일 수 있다 | 정렬 허용오차·성공 기준은 사전 등록값이다(사용자 결정). turn 명령 트림은 빔 강체 접촉이라 효과·안전 미검증 |

### 추천 1–2안

**추천 1안: E1 + E2(쌍 대칭 플랜트 + 자기 RGB 상대 yaw)로 한 leg의 정직한 σ를 게이트 아래로 만든다.** 단계 probe(한 leg)에서 L1·L2를 통과시키는 것이 목표다. 정직한 b는 1.5 mrad/s, 게이트 도달 34 s(leg 24 s 대비 여유 39 %). 배치 물리(공통 모드)는 못 없애므로 **경로 전체 통과 주장은 하지 않는다.**
- 필요한 코드(추정, 이번에 만들지 않았다): `harness/zone_pair_v6_policy.py`(플래그 `carry_pair_yaw`, `carry_beam_edge_yaw`, 기본 OFF), `harness/owncam_carry_v6e.py`(든 쌍 프로필의 yaw 결합 행을 0으로, 새 b), `harness/owncam_localizer.py`(상대 yaw 증분 입력 훅, 키가 없으면 출력 바이트 동일), 새 `harness/own_beam_edge.py`(마스크→하단 경계 직선→기울기, 순수 numpy), `harness/zone_pair_executor.py`(운반 중 프레임 전달·기록), `harness/pair_stage_probe.py`(정책 이름), `tests/test_zone_pair_v6e.py` 계열(합성 프레임으로 기울기=상대 yaw, 플래그 OFF 바이트 동일).
- 사전 등록 제어 파라미터: 게이트(3°/2.5°, xy 0.07 m, 체류)·스윕 가드 식은 그대로. **새로 적합하는 값**은 공통 모드 b 하나(cal 코호트의 E2 잔차 셀 균형 RMS로만, 격자·held-out은 읽지 않는다는 v6e와 같은 규칙)이고 기울기→yaw 비 1.0은 기하 상수다. 이 분석이 경계 셀을 이미 읽었으므로 b는 새 cal 코호트에서 다시 정해야 한다.
- 검증 순서(물리 전에 무료 단계 먼저): ① **오프라인 재생**: 기록된 cal 프레임·명령으로 새 추정기를 돌려 NEES(1.5–6)와 yaw 2σ 커버리지(≥ 90 %)를 본다. ② stage probe cal 코호트 40건(nominal×3 seed, yaw+/same, lat−/opp × leg 0–7, 워커 2·`--omp-threads 1`, agent_lock): 판정 = L1·L2 nominal 각 ≥ 4/5, 정직성 통과(같은 재적합 코호트 안이므로 독립이 아님을 표시). ③ **반쪽 허용오차 셀**(lat ±4 mm/opp, yaw ±0.0175 rad/opp, 필요하면 hA/hB/hC 배치)로 b와 선형 가정을 시험한다(셀 정의 추가 필요: `harness/pair_stage_probe.py`). 판정 = 위 게이트 도달 시간과 2σ 커버리지. 이것도 leg 단계 probe이며 E2E가 아니다.

**추천 2안(결정 필요): 경로 전체 yaw는 추정이 아니라 물리 편향을 줄여야 한다.** 옆 오프셋 y를 영상으로 0.5 mm까지 잴 수 있으므로 파지 전 정렬의 옆 허용오차(8 mm)를 줄이거나(사전 등록 정렬 기준 변경) 측정한 y로 우력 트림을 시험하는 것이 실질적인 경로다. 검증은 offset-graded 셀에서 GT 빔 yaw 표류율의 감소(축 leg, mrad/s per mm)와 stage 통과율이다.

### 사용자 결정이 필요한 것

1. 쌍 오프셋 측정값을 상태 레코드로 파트너에게 알려도 되는가(E3·c3). 통신 조건이 조작 변수이므로 네 조건에 동일하게 줘도 되는지 확인이 필요하다. E1·E2는 통신이 필요 없다.
2. 경로 전체 3° yaw 게이트를 유지할지, 아니면 leg별 σ 재설정이 없는 현 설계에서 8 leg 누적(경계 배치 8–16° 물리 회전)을 받아들일지. 정렬 옆 허용오차(현 8 mm)를 줄일지.
3. 더 넓은 팬으로 정지 중 벽·바닥 경계를 보는 실험(c4)을 물리 probe 한 번으로 해 볼지(빔을 놓지 않는 팬 범위 확인).
4. 초음파를 켜는 실행을 쓴다면 용도는 쌍 간격·충돌 여유(yaw 아님). 운반 lift를 0.110으로 바꾸는 별도 결정이 필요하다.

### 테스트

이 절은 문서와 오프라인 분석 스크립트뿐이다(`harness/`·`scripts/`·`tests/` 미변경, 소스 트리 해시 불변). 저장소 테스트는 돌리지 않았다(코드가 바뀌지 않았고 분석 스크립트는 `harness.ultrasonic_map`을 읽기 전용으로 import한다). 스크립트는 각각 한 번씩 실행해 `.txt`에 저장했다.

## yaw 플래그 구현과 사전 등록 재측정 계획 (2026-09-29, 소스 `86cdefc9`에 고정)

> **갱신 안내.** 이 절과 아래 "결과 (소스 `86cdefc9`)"는 첫 소스의 기록이다. 독립 검토(Codex, fix-then-proceed)를 반영해 소스가 `4fac772d`로 바뀌었고 **b·비율 수치, 가장자리 마스크 규칙, σ 폴백은 뒤의 "소스 `4fac772d` 갱신" 절이 대체한다.** 첫 소스의 35/40 결과는 비교용으로 그대로 둔다.

조정자 결정(추천 1 구현; 파트너 오프셋 전달·초음파 yaw·yaw 게이트/정렬 허용오차 변경은 하지 않음)에 따른 구현이다. **물리 시뮬은 아직 돌리지 않았다**(아래 "실행 상태"). 이 절의 모든 수치는 기록된 cal raw의 재생이며 제어기 결과가 아니다.

### 무엇을 넣었나 (기본 OFF, 다른 정책 출력 바이트 불변)

| 플래그 | 정책 필드 | 내용 | 파일 |
|---|---|---|---|
| (i) 쌍 평균 플랜트 yaw 모델 | `carry_pair_yaw` | 운반 중 PF의 yaw 예측 목표 = (자기 loaded 플랜트 yaw 목표 + 계획에서 유도한 파트너 명령의 yaw 목표)/2. x/y는 자기 플랜트 그대로 | `harness/owncam_localizer.py`(`pair_plan`, `_partner_of`), `harness/owncam_carry_v6e.py`(`set_partner_plan`), `harness/zone_pair_executor.py` |
| (ii) 자기 RGB 빔 아랫 가장자리 상대 yaw | `carry_beam_edge` | 손목 RGB의 빔 띠 아랫 가장자리 기울기 변화/`slope_to_yaw_ratio` = 로봇-빔 상대 yaw 변화. 증분을 모든 입자 yaw에 더한다 | `harness/own_beam_edge.py`(신규), `harness/owncam_pose_source.py::on_frame`, `localizer.apply_relative_yaw` |

정책(`harness/zone_pair_v6_policy.py`): `b-v6e` = 두 플래그 모두, `b-v6e-pm` = (i)만, `b-v6e-edge` = (ii)만, 나머지 필드는 모두 같다(테스트로 고정). **주의: 이름 `b-v6e`의 뜻이 바뀌었다.** 예전 raw(`carry@b-v6e:…`, cal1·cal2·스모크·진단)의 `b-v6e`는 이제 `b-v6e-base`(= dr + lag + 내려놓기 플래그 2개)와 같다. 예전 raw를 새 `b-v6e`와 섞어 합산하지 않는다. `PROBE_VERSION` 0.7.0. 둘 다 `carry_dr_model`이 필요하다(PF의 입자별 yaw-rate 편향 std를 변형별 cal 적합값으로 바꾸므로; 없으면 `PairTeam`이 거부).

**입력 경계.** (i)의 파트너 명령은 통신·GT·상태 채널 없이 계획에서 유도한다(아래). (ii)는 자기 RGB 프레임, 자기 발행 서보 명령, 자기 load 상태(자기 명령으로 판단)만 쓴다. 초음파·GT·파트너 오프셋은 쓰지 않는다. 게이트(σ_yaw 3°/2.5°, 0.6 s/0.4 s dwell)·스윕 가드·정렬 허용오차는 그대로다.

### 파트너 명령이 통신·GT 없이 유도되는가 (코드로 확인, 결론: 된다)

1. 운반 leg 명령은 `RoutedM2.door_schedule`의 함수 `leg_command(sign)`이 만든다: 경로 leg `(a, b) = plan['route'][seg:seg+2]`(정적 지도·주문서의 경로 계획)에서 `dx, dy`, 축은 `abs(dy) > 1e-6`, 크기 `SPEED_M_S`/게인 상수, 방향 `sign`. `turn = 0`이다.
2. `sign`은 역할 상수 `carry_role_sign(rid)`(r1 = +1, r2 = -1; 예전 코드의 `1. if self.rid == 'r1' else -1.`과 같은 식)이다. 두 로봇은 같은 경로 leg를 서로 마주 보고 든다. 파트너 명령 = 같은 함수에 `carry_role_sign(execution.partner_id)`를 넣은 값이다. `partner_id`는 job의 쌍 구성(정적)이다. 입력은 `plan`(정적)과 역할뿐이며 파트너 프로세스의 어떤 출력도 읽지 않는다.
3. 유도 결과는 `claims['segments'][-1]['pair_partner_command']`(source = "route plan + role sign (no message)")로 기록된다. 테스트 `test_partner_command_is_derived_from_the_plan_and_the_role_only`는 유도한 파트너 벡터가 **다른 로봇의 실제 own 스케줄 명령과 같음**을 축·옆 이동 두 leg에서 확인한다(파트너 상태 채널을 읽지 않고도 같다).
4. PF는 발행된 own 명령이 계획된 own 명령과 정확히 같고 그 leg 시간 창 안일 때만 파트너 벡터를 쓴다(`_partner_of`). 어긋난 명령은 `pair_unmatched`로 세고 registered 예측으로 돌아간다. 실행 기록 `carry_yaw_v6e`에 로봇별 `partner_plan_matched/unmatched`가 남는다.
5. 가정과 한계(정직하게): 파트너가 실제로는 그 leg를 그대로 수행한다고 가정한다(양쪽 스케줄이 같은 시간 창을 가진다는 `_wait_carry` 계약). 파트너가 실패·정지하면 모델이 틀리지만 그때는 쌍 운반이 이미 실패다. 파트너 상태 채널(`aligning/ready/lift/carry`)은 쓰지 않는다. **GT나 상태 채널이 필요하지 않았으므로 중단 조건은 발동하지 않았다.**

### 빔 가장자리 측정 (`harness/own_beam_edge.py`)

- 마스크(PIL HSV 0–255): H 25–90, S > 100, V > 60. 열 140..500(4 간격), 행 40..300에서 열마다 첫 run의 아랫 경계를 잡아(20 px 초과) 20열 이상이면 직선 적합, 기울기를 쓴다. 분석의 `edge_line`과 같다.
- 추적기: 적재 중이고 팔 서보(2–6)가 3 s 안 변했으면 대기, 처음 2개 표본 평균이 기준 기울기, 이후 최근 3개 중앙값−기준 = 누적 상대 yaw(÷ratio), **증분**만 PF에 준다(증분이 telescope하므로 누적 이동 = 평활한 측정 1회, 프레임 잡음이 랜덤워크로 쌓이지 않는다). 프레임 간격 ≥ 0.5 s, 한 걸음 0.03 rad 초과는 거절(5회 연속이면 기준 재시작), 서보 변화·적재 해제 때 기준 재시작(이미 준 이동은 유지).
- 보이지 않는 것: 빔 자체의 공통 회전(common mode)과 집게 yaw 오프셋은 이 뷰에 없다. 그 몫은 입자별 yaw-rate 편향 b가 맡는다.

### 공통 모드 b와 비율: cal 자료로만 적합 (`fit_carry_pair_yaw.py` → `carry_pair_fit.json`)

입력은 cal1 raw 3개(`ece38792-cal`, `a704ecc6-calB2`, `a704ecc6-calB`; `refit_carry_dr_cal.py`와 같은 raw)뿐이다. 격자·held-out은 읽지 않았고, cal2(`d08818ef-cal2`)는 적합에 넣지 않고 복제 확인으로만 출력했다. 구현된 추정기(기록된 프레임에 실제 추적기, 기록된 명령의 플랜트 재생, 반전 명령 = 유도한 파트너)를 케이스·로봇별로 돌려 (GT yaw 변화 − 추정)/창 길이의 셀 균형 RMS를 b로 쓴다(48 case-robot, 3 셀).

| 변형 | b [mrad/s] (cal1 적합) | cal2 복제(적합 밖) | 비고 |
|---|---:|---:|---|
| 등록 v6e(재생) | 2.28 | 2.28 | 등록값 2.331(PF 기반)과 일치 → 재생 검증 |
| `pm`(b-v6e-pm) | 1.90 | 1.88 | |
| `edge`(b-v6e-edge) | 1.87 | 1.84 | 자기 모델 + 가장자리 |
| `pm+edge`(b-v6e) | 1.57 | 1.54 | |

`slope_to_yaw_ratio` = 1.065(기울기 변화 = 1.065 × 상대 yaw 변화, 상관 0.9996, 잔차 sd 0.54 mrad, 48 case-robot). 분석 절의 0.96(전 코호트, 다른 창 정렬)과 다르므로 cal 값으로 고정했다. 즉 **b는 등록값의 약 0.69배**(pm+edge)라 σ가 게이트에 도달하는 시간이 약 34 s로 늘 뿐이다(분석 표의 E2). 전 경로(170.8 s)를 3°로 유지하지 못하는 한계는 그대로다(분석 절). 이 수치는 기록 재생이며 **PF NEES·커버리지는 아래 cal 재측정으로만 확인된다.**

### 테스트 (관련 테스트만, 전체 CI 안 돌림)

`tests/test_zone_pair_v6e_yaw.py` 15건: 정책 필드(세 정책만 ON, 서로 한 플래그 차이, `b-v6e-base` = 예전 b-v6e), 변형 바인딩·적합 파일 출처, 파트너 명령의 계획·역할 유도, OFF일 때 door_schedule이 등록 식과 비트 동일, 쌍 평균이 반대칭 yaw 결합을 상쇄하고 x/y·비적재는 그대로, 국소 PF 난수 흐름 불변(기존 골든 `test_flags_off_localizer_is_bit_identical_to_main_1e7bdfe0`도 통과), 합성 띠 기울기 회복·추적기 telescope·재시작·글리치 거절, 기록된 프레임 재생(커밋된 48행 상관 > 0.99, 잔차 sd < 2 mrad; cal raw가 있으면 실제 프레임을 다시 읽어 GT 상대 yaw와 3 mrad 이내 + 커밋 행과 비트 동일). 기존 `test_zone_pair_v6e.py`(정책 목록), `test_owncam_bootstrap_v6b.py`(정책 필드 목록), `test_zone_pair_executor.py`(동결 해시 목록에 두 파일 새 해시)를 필드 추가에 맞춰 고쳤다. 봉인 해시 테스트 5건은 등록 전이라 이전과 같이 실패한다(예상, 등록 때 해결).

### 사전 등록 재측정 계획 (측정 전 고정; 소스 `86cdefc9`, 적합 파일 `carry_pair_fit.json` sha256 `52f996b7c5e793439211a3c1b9b42c5a69b41a790804c7eeed931896c032d5a1`)

소스·적합 파일은 코호트 동안 바꾸지 않는다. 결과를 보고 임계값·판정 기준을 바꾸지 않는다. 각 단계는 **앞 단계 통과 시에만** 진행한다(스모크 우선·조건부). 러너는 위 "공통 조건"과 같다(`--workers 2 --omp-threads 1`, 사전분포 e2e, seed 911, 기록 `--pf-track`). 성공 판정은 위 "성공 판정" 표 그대로다.

| 단계 | 내용 | 통과 기준(사전 고정) | 미통과 시 |
|---|---|---|---|
| 0 스모크 | cal 배치(`--setup-variant cal`) `b-v6e` 4건: nominal L0·L1, lat−/opp L1·L3 | ① HOST_ERROR·예외 0 ② `carry_yaw_v6e`에서 모든 로봇 `partner_plan_matched` > 0, `partner_plan_unmatched` = 0(leg 명령 안), `beam_edge.applied` > 0(운반 10 s 이상인 케이스) ③ 계획된 leg에서 PF yaw σ가 등록 v6e 대비 같거나 작음 | 멈추고 배선 진단(소스 수정은 새 커밋·새 코호트) |
| 1 cal 40건 | `--stage carry --policies b-v6e --cells nominal yaw+/same lat-/opp --legs 0..7 --nominal-seeds 911 912 913 --setup-variant cal --pf-track`(40건) | **① L1과 L2 각각 cal 5건 중 ≥ 4건 통과**(nominal 3 seed + yaw+/same + lat−/opp; 기준선 `b-v6e-base`(소스 d08818ef, 정직한 b)는 cal-2에서 L1 0/5, L2 0/5 `SELF_POSE_UNCERTAIN`(yaw)). L7 `COLLISION_GUARD`(cal-2 0/5)는 yaw 문제가 아니므로 이 플래그의 판정 대상이 아니며 보고에 따로 적는다. ② 정직성: leg 끝 (x, y, yaw) 3자유도 평균 NEES ∈ [1.5, 6]와 yaw ±2σ 커버리지 ≥ 90 % | 정직성만 실패하면 **cal 자료로만** `fit_carry_pair_yaw.py`를 한 번 다시 적합·재커밋 후 1번 반복(1회 한정). ①이 실패하면 멈추고 보고(격자·held-out 시작 안 함) |
| 1b 절제(정보용, 게이트 아님) | 1이 통과하면 cal에서 leg 1·2·3만 `b-v6e-pm`, `b-v6e-edge`(각 15건) | 어느 플래그가 통과를 만드는지 기록. 임계 없음 | — |
| 2 진짜 held-out | 배치 `hA`(legs 0 1 3 6 7 × nominal·yaw−/opp, `b-v6e`, 10건, `--nominal-seeds 914`)를 먼저. 통과하면 `hB`, `hC` 각각 같은 10건 | 배치당 **≥ 8/10**, 세 배치 합 ≥ 24/30, 격자보다 20 %p 넘게 낮으면 과적합 의심으로 기록. hA 미통과 시 hB·hC는 돌리지 않는다 | 멈추고 원인 진단 보고. 결과를 보고 소스를 고치지 않는다 |
| 3 운반 33셀 격자 | `--policies b-v6e`(33건, nominal 3 seed). 기준선은 `b-v6c` 0/33과 `b-v6e-base`(측정된 cal·스모크 값, 격자는 미측정)를 인용 | **≥ 26/33**이고 legs 0·1·3·6·7 각각 최소 절반 이상 | 임계에 못 미치면 실패 원인을 가르는 셀만 `b-v6e-pm`/`b-v6e-edge`/`b-v6e-base`로 절제 |

- 정직성 지표(NEES·커버리지) 산출은 `refit_carry_dr_cal.py`와 cal 게이트 판정(위 "cal 게이트 판정")과 같은 방식이다.
- 보고 항목: 통과율, 실패 원인 코드, leg 끝 yaw 오차 분포(GT vs PF, eval-only), σ가 게이트에 닿은 시각, `carry_yaw_v6e` 카운터, NEES·커버리지. 이 측정은 stage probe이며 제어기·E2E·학생 성공이 아니다.
- 등록(v81/2.14.0, revision v6e)은 측정이 끝난 뒤 최종 소스로 한 번만 한다.

### 실행 상태 (이 절 작성 시점)

`python3 scripts/agent_lock.py status`가 `claude/render-profile`(렌더 프로필 A/B, PID 94410, 생존)이 잡은 잠금을 보고했고 부하 평균이 20을 넘었다(약 75). 지침에 따라 **물리 실행을 시작하지 않았다.** 실행 준비 완료 명령은 보고서에 있다.

## 결과: yaw 플래그 스모크 4건 + cal 40건 재측정 (소스 `86cdefc9`, 2026-09-29, stage probe)

**stage probe이며 E2E·제어기·학생 성공이 아니다.** 소스 트리 해시 `23351504a85d…`가 스모크·cal에서 같고 계획 이탈 없음(적합 파일 `carry_pair_fit.json` sha256 `52f996b7…` 그대로, 재적합 없음). 정책 `b-v6e`(두 yaw 플래그 모두), cal 배치, `--workers 2 --omp-threads 1 --pf-track`, 모델 호출 0, weld OFF, 진단 패치 없음. raw는 로컬 `outputs/`이며 원격 백업이 아니다: `pair-stage-probes-f2186414-yawsmoke`, `-yawsmoke2`, `-yawcal`(디렉터리 이름의 `f2186414`는 실행 시점 HEAD인 README 커밋이고 소스는 `86cdefc9`와 같다). cases.jsonl sha256 앞 16자: yawcal `ebab748c2d94f08c`, yawsmoke `bdc5c3691792473d`, yawsmoke2 `0b813dc13b162164`. 부하 평균(1분)은 1분마다 `pair-stage-probes-f2186414-yawcal-load.log`에 기록했다(cal 실행 중 9.1–32.3, 중앙값 15.6; wall 2467 s = 41 min; SIM 시간 결과에는 영향 없음). agent_lock은 driver PID로 잡고 종료 때 해제했다(`status` null).

### 스모크 (단계 0)
4/4 통과: nominal L0·L1, lat−/opp L1·L3(전부 cal 배치). ① HOST_ERROR·예외 0. ② 모든 로봇 `partner_plan_matched` 140–183, `unmatched` 0, `beam_edge.applied` 36–45. ③ leg 끝 PF yaw σ가 cal-2(등록 v6e)보다 작음: 1.9–2.3° 대 2.8–3.0°. 기준 통과.

### cal 40건 (단계 1)

| 항목 | 값 | 사전 기준 | 판정 |
|---|---|---|---|
| 전체 통과 | 35/40 | (게이트 아님) | – |
| leg별 통과 | L0–L6 각 5/5, **L7 0/5** | – | – |
| **L1** | **5/5** | ≥ 4/5 | 통과 |
| **L2** | **5/5** | ≥ 4/5 | 통과 |
| leg 끝 3자유도 평균 NEES (80 표본) | **2.25** (중앙값 1.70) | [1.5, 6] | 통과 |
| ±2σ 커버리지 x / y / yaw | 100 % / 100 % / **93.8 %** | yaw ≥ 90 % | 통과 |

- 비교(같은 40건, 기준선 정책): 예전 `b-v6e`(= `b-v6e-base`)의 cal-2(정직한 b 0.00233)는 L1 0/5, L2 0/5 `SELF_POSE_UNCERTAIN`(yaw), 전체 23/40이었다. 이제 L1·L2가 5/5다. 개선폭은 yaw σ가 게이트 밖으로 자라지 않게 된 것(leg 끝 σ 약 1.9–2.3° 대 2.8–3.0°)이며, 이 표는 **같은 cal 배치**의 결과라 독립 검증이 아니다(b는 이 cal 자료로 적합했다). 독립 검증은 held-out(단계 2)이다.
- 실패 5건은 모두 L7 `PAIR_COLLISION_GUARD`(nominal 3 seed, lat−/opp, yaw+/same)이며 cal-2의 L7 0/5와 같은 원인 계열이다. yaw 플래그의 판정 대상이 아니다. L7은 내려놓기 직전의 마지막 leg이고 이 실패는 아직 진단하지 않았다.
- 남은 오차: lat−/opp의 r2는 leg 끝 yaw 오차가 4–6°(NEES 7–10, yaw z 2.0–2.5)로 여전히 σ(약 2°)보다 크다. 평균 NEES와 커버리지 기준은 넘었지만 이 셀의 한쪽 로봇은 과신이다(공통 모드 물리 회전은 가장자리로 안 보인다는 분석 절의 한계와 일치). 통과에는 영향이 없었다.
- 세부: `analysis/nees_yawcal.txt`(스크립트 `analysis/nees_pf.py`).

### 판정
사전 등록 단계 1 기준(L1·L2 각 ≥ 4/5, NEES ∈ [1.5, 6], yaw 커버리지 ≥ 90 %)을 **모두 충족**했다. 계획대로 다음은 단계 2(held-out `hA`)이지만 이번 작업 범위 밖이라 시작하지 않았다. 절제 1b(`b-v6e-pm`, `-edge`)도 돌리지 않았다.

### 운반 시작 때 PF는 무엇을 이어받나 (오프라인 확인, 새 물리 0; 2026-09-29)

**질문.** hR에서 문 통과 실패의 뿌리는 운반 시작 PF의 y가 실제보다 최대 0.05 m 어긋난 것(주문서 격자 0.1 m 반올림)이었다. 실제 파이프라인도 운반 진입 때 그 반올림 값으로 PF를 다시 시작하는가?

**코드 확인 (근거).**
- 실제 실행기(`harness/zone_pair_executor.py`)는 작업 하나 동안 로봇마다 PF 객체 하나(`OwnCamLocalizer`)를 유지한다. 운반 진입에서 격자 값으로 다시 초기화하는 코드는 없다(`seed_gaussian_prior`는 stage probe 전용이고 실행기에 없다). 모든 기록 raw에서 `localizer_replaced`(=`localizer_object_replaced` 이벤트 수)는 0이다. 즉 **정렬·파지·들기 단계의 사후분포를 그대로 이어받는다.**
- stage probe의 `--prior-std e2e`가 흉내 내는 것은 "정렬 진입 때 로봇 자신의 `PoseReport` σ(0.026–0.033 m, 0.009–0.012 rad)"를 **표준편차로만** 빌리는 것이다. 평균은 시트 격자값에서 계산한 계획 위치(`plan_geo[key]`)로 넣는다(`prior_seeded`에 t, estimate가 기록되고 `last_tag_t`는 None). 그래서 진짜 빔 y 0.05 vs 시트 0.0의 5 cm가 모든 단계에서 **처음부터 결정적인 y 오차**로 들어간다. 정렬 e2e 체크포인트(실제 E2E 진입 상태)만은 실제 PF 값으로 시작하므로 5 cm 오차가 없다.
- PF는 바닥 표식만 본다(벽·문틀 관측 항 없음: `owncam_localizer.py`에 벽 우도가 없음). 정렬 시작 때 화면에 벽이 약 5 % 보이지만 지금 코드는 그 정보로 y를 고치지 못한다.

**기존 raw의 종료 시점 PF 오차 (GT 대비, 평가용; `analysis/pf_at_stage_end.py` → `.txt`, `.json`).** 정지 시점 가중 평균 vs 실제 베이스 자세:

| 단계 · 출처 · 정책 | 시작 사전 y 오차 | 종료 \|y 오차\| 중앙 / p90 / p95 | 종료 σ_xy 중앙 |
|---|---|---|---|
| 정렬 · **실제 E2E 체크포인트** · b-v6d (n=28 로봇) | 중앙 0.2 cm, p95 2.3 cm | **0.5 / 1.2 / 1.2 cm** | 2.8 cm |
| 정렬 · 교사 격자 · b-v6d (n=80) | p90/p95 4.0 cm | 1.2 / 2.1 / 2.2 cm | 2.7 cm |
| 파지·들기 · 허용 경계 · b-v6d (n=142) | **5.0 cm (시트 계획 위치)** | 2.9 / 5.9 / 6.2 cm | 2.9 cm |
| 파지·들기 · 교사 격자 · b-v6c (n=66) | 5.0 cm | 3.6 / 4.4 / 4.8 cm | 4.5 cm |

**해석.**
1. 기록된 파지·들기 raw는 **전부 5 cm 시트 사전분포로 시작**했다. 그래서 그 끝의 3–6 cm는 "실제 파지 단계가 만든 오차"가 아니라 "5 cm에서 시작해 조금 줄어든 값"이다(파지 중 표식이 y를 5 cm → 3 cm 정도로 줄인다). hR이 이 raw에서 자세만 뽑고 PF 사전은 다시 격자값에서 만든 것은 이중으로 비관적이었다.
2. 실제 E2E에서 정렬 진입 PF 오차는 ≤ 2.3 cm이고 b-v6d 정렬이 끝날 때 y 오차는 중앙 0.5 cm, p95 1.2 cm다. 파지·들기가 이 값을 얼마나 바꾸는지는 **기록된 적이 없다**(파지 raw가 모두 5 cm에서 시작하므로).
3. 결론은 (a)에 가깝다: 사후분포는 이어받고, 정렬 종료 시점 오차는 작다. 다만 "파지·들기 종료 시점의 이어받은 오차"는 직접 측정이 없어, 기록된 파지 raw를 그대로 쓰면 hR와 같은 비관 편향이 남는다. 따라서 hR2의 표본은 기존 파지 raw가 아니라 **정렬 종료 상태에서 파지·들기를 새로 이어 실행해 얻는다**(아래 hG → hR2). 이것은 사전 오차를 사람이 정하는 것이 아니라 실제 정렬 종료 사후분포를 연결하는 것이다.

## hG → hR2: 이어받은 사후분포로 시작하는 opt-in 스테이징 (측정 전 고정; 컨트롤러·PF·적합은 `f844a373` 그대로)

**스테이징(소스 `PROBE_VERSION` 0.10.0).** `--setup-variant hG`(grasp_lift 진입) / `hR2`(carry 진입): 표본 파일(`hG_samples.json`, `hR2_samples.json`)의 각 표본은 앞 단계 종료 시점의 실제 로봇·빔 자세와 그 시점의 PF 사후분포(가중 평균, 퍼짐)를 담는다. 케이스는 그 자세에서 시작하고, **컨트롤러가 받는 시작 사전은 "기록된 사후분포의 평균과 σ를 가진 명시적 가우시안"** 하나다(GT를 컨트롤러에 넘기지 않는다; 평균은 스테이징 자세에 기록된 (PF−GT) 오차를 더한 값). 기본 실행과 기존 변형은 바뀌지 않는다(`rows`의 네 번째 원소가 있을 때만 작동, 케이스 id 꼬리표 `:pPOST`, 변형 `:VhG`/`:VhR2`).

**hG (파지·들기 생성, 물리 10건).** 표본 규칙(`extract_hG_samples.py`, 측정 전 고정): 최신 소스 raw `pair-stage-probes-052e3eba-v6d-venv-align-combined`의 `b-v6d` 정렬 PASS에서 실제 E2E 체크포인트 6건 전부 + 교사 격자 4건(정렬된 case_id의 round(i·(n−1)/3), i=0..3). 정렬 종료 PF−GT 오차는 y −0.7…+2.8 cm, x ≤ 1.2 cm, yaw ≤ 0.54°로 실제 E2E 범위다. 정책 `b-v6g`, seed 911, `--render-profile floor_light_v1`. 이 실행은 기준을 둔 시험이 아니라 표본 생성이지만 파지 실패도 숨기지 않고 표로 남긴다(파지가 실패한 표본은 hR2에서 빠지고 그 수를 적는다).

**hR2 (carry 시험, 사전 기준 고정).** 표본은 hG 결과 중 **grasp_lift가 PASS이고 체크포인트가 있는 것 전부**(최대 10; `extract_hR2_samples.py`, 규칙: hG 표본 순서 그대로 채택, 선별 없음). 케이스는 표본 × 운반 구간 L0–L6(`b-v6g`, seed 911, `--setup-variant hR2`, `--render-profile floor_light_v1`), L7은 `b-v6g-l7`로 별도(합산하지 않음). 구간 k의 진입은 경로 변위만큼 함께 이동하고 기록된 (PF−GT) 오차는 그대로 유지한다(다리마다 독립 진입으로 보는 점은 hR와 같다; 앞 구간에서 누적되는 추측 항법 오차는 이 시험이 아니라 체인 실행이 본다).
- **기준(hR과 동일, 값 불변).** 통과율 ≥ 80 %(전체 케이스 수 기준; 스테이징 불가 `STAGING_IK_ENVELOPE`는 표에 별도로 보이되 분모에서 빼지 않는다); leg 끝 3자유도 평균 NEES ∈ [1.5, 6]; x·y·yaw ±2σ 커버리지 ≥ 90 %(로봇 표본). NEES·커버리지가 기준 밖이면 통과율이 충족돼도 미통과. 구간별(L0–L6) 표를 내고 어느 구간도 0인 채 숨기지 않는다. 가드·게이트 문턱(`GATE_LOADED` 3°/2.5°, 가드 요구 0.02 + 0.015 + 2σ_xy + 2σ_yaw·0.18)은 바꾸지 않는다.
- **결과 표시.** 실패는 원인 코드, 실패 시각의 PF 위치·σ, 문 가장자리(y −0.20, 0.30)까지의 GT 여유와 가드 요구 여유를 수치로 낸다(`analysis/hR_analysis.py` 재사용).
- **통과 시** 작동 범위를 "이어받은 사후분포가 정렬 종료 범위(PF y 오차 ≲ 3 cm, σ_xy ≈ 3 cm, 파지 오차 ≤ 2.6 cm)일 때"로 명시해 v81 / 2.14.0 / v6e로 등록·봉인·push·PR(Opus 독립 검토 요청 포함). **미통과 시** 등록하지 않고 원인 보고.
- **한계(미리 적는다).** hG의 시작은 정렬 raw 10건(E2E 6 + 교사 4)뿐이라 분포 폭이 좁다. 파지·들기 종료 오차가 이 표본에서 작게 나와도 다른 시드·장면·긴 작업 뒤의 드리프트로 일반화하지 못한다. 그리고 운반 구간 L1 이후는 앞 구간 오차를 이어받지 않은 독립 진입이다.

### hG 실행 결과 (소스 `19c8f0b2`, raw `pair-stage-probes-19c8f0b2-ghG`, 부하 평균 10.4 / 12.6 / 15.3, 잠금 획득·해제 기록됨)

- 10/10 PASS(파지·들기 실패 0, 각 7.3 s). 시작 사전이 기록된 정렬 종료 사후분포로 들어갔는지 확인: `prior_seeded`의 추정이 GT 대비 y +0.3 cm 등 기록값과 일치(예: hG01 r1 추정 y 0.0455 vs GT 0.0421).
- **파지·들기가 끝난 시점의 이어받은 PF 오차(GT 대비, 로봇 20표본)**: |y| 중앙 0.7 cm / 최대 2.7 cm, |x| 0.2 / 0.7 cm, |yaw| 0.30° / 1.31°, σ_xy 중앙 2.6 cm (최대 3.2 cm). 즉 시작이 실제 정렬 종료 값이면 파지·들기가 y 오차를 키우지 않는다(3–6 cm는 5 cm 시트 사전에서 시작했기 때문이었다). 이 20표본이 hR2 진입 사전이다(`hR2_samples.json`, `extract_hR2_samples.py 19c8f0b2-ghG`, 선별 없이 10건 전부).

## TensorBoard
스냅샷 `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6e-yaw`(run 41개 = 경우 40 + 집계 1, `collection.json` sha256 `9a5eba0cd3fc922e419343cad908bcf9f6a9b904d0a6f36875cfe74c9bf42035`), 파생 뷰 `outputs/pair-stage-probes-tbviews-0929-v6e-yaw`. 스모크 4건은 cal과 같은 경우 이름이라 넣지 않았다(raw는 위에 있음). EventAccumulator로 경우별 `offline/stage_pass` 합 35 = cases.jsonl 통과 35, 집계 `pass_rate` 0.875를 확인했다. `outputs/tensorboard-view.json`에는 키 `pair_stage_probes_v6e_yaw_20260929` 하나만 추가했다(run filter `^0929-pair-stage-probes-v6(c(-carry)?|e|e-yaw)/`로 v6c·v6e 기준선과 함께 보임). TensorBoard 서버가 떠 있지 않았고 새로 시작하지 않았다(브라우저 표시는 확인하지 못했다).

## 소스 `4fac772d` 갱신: 독립 검토 반영, cal 재측정, hA 결과 (2026-09-29, stage probe)

**stage probe이며 E2E·제어기·학생 성공이 아니다.** 소스 `4fac772d`(커밋 메시지: availability fallback, first-run edge check, canonical b-v6e-base, MED4 refit) = `86cdefc9` + 아래 수정. 플래그 OFF 출력은 여전히 main과 바이트 동일(기존 골든 테스트 통과). 등록·번들·push·PR 없음.

### 검토 지적과 반영

| 지적 | 반영 |
|---|---|
| HIGH: b가 영구 교체됨(`owncam_carry_v6e.py`, `own_beam_edge.py`) — 빔이 안 보이거나 글리치 재시작·계획 불일치일 때도 작은 b를 씀 | **가용성 폴백.** 프레임마다 (쌍 평균 계획 일치, 가장자리 추적 중) 조합을 판단해 실제로 유효한 추정기의 b를 쓴다. 조합별 b 표: `pm+edge`(적합값 1.56), `pm`, `edge`, `''`(등록값 2.331). 유효하지 않은 추정기의 몫은 입자별 상수 yaw-rate 오차 `sqrt(b_eff² − b_full²)`로 보탠다(`localizer.set_extra_yaw_std`). 계획 불일치는 2 s 유지(`PM_HOLD_S`)해 깜빡임을 막고, 하역 시 해제. 가장자리 최근 성공(`last_ok_t`)이 2 s 넘게 없으면 가장자리 무효. 테스트: 마스크 비움, 글리치 1프레임 억제·지속 점프 거절, 계획 불일치 주입 |
| MED1: `MIN_RUN_PX`가 첫 run에 안 걸림 | `_first_run_end`: 첫 연속 run이 40 px 이상일 때만 아랫 경계 채택. 직선 적합 후 잔차 4 px 초과 열 제거, 남은 열 ≥ 20이고 ≥ 60 %, RMS ≤ 2.5 px 아니면 거절. 낱개 픽셀·비직선 경계 테스트(기록 프레임에서 띠는 모든 열에서 76–89 px 연속, 잔차 RMS ≤ 1.2 px) |
| MED2: 쌍 평균 모델이 파트너 타이밍·정지에 취약 | 아래 "쌍 평균 모델의 가정과 한계" |
| MED3: 예전 `b-v6e` raw가 새 이름과 섞임 | `harness/pair_stage_probe.py::canonical_policy`(PROBE_VERSION < 0.7.0 또는 버전 불명 → `b-v6e-base`); 뷰 빌더가 사용. 테스트 포함(cal-2 raw가 있으면 실제로 `E0-…` 확인) |
| MED4: `fit_carry_pair_yaw.py`의 RGB/GT 시간 창 불일치 | GT 상대 yaw를 추적기의 실제 기준·유효 시각(`ref_t`, `eff_t`)에서 보간해 창을 맞춤. **cal1 자료로만** 재적합 |

재적합 결과(`carry_pair_fit.json` sha256 `5dfa75587ae19fbe7278f8fd783cfb71638b160f3aa7247f91ca416f6ff7a88b`): `slope_to_yaw_ratio` 1.008(이전 1.065; 상관 0.9996, 잔차 0.53 mrad), b[mrad/s] = 등록 재생 2.30(등록값 2.331과 일치), `pm` 1.90, `edge` 1.85, `pm+edge` 1.56. cal2 복제(적합 밖): 2.28 / 1.88 / 1.82 / 1.53. 이전 표의 1.065, 1.87, 1.57은 폐기.

### 쌍 평균 모델의 가정과 한계 (MED2)

- **가정.** 파트너는 계획된 leg를 같은 시간 창에 그대로 수행한다(`_wait_carry` 계약). 파트너 명령은 계획·역할에서만 유도한다(통신·GT 없음).
- **기록된 cal 케이스에서 본 타이밍.** 파트너와의 시작 어긋남 0 s, 끝 어긋남 ≥ −0.1 s. 어긋남 δ의 yaw 오차는 0.5·a·δ; 옆 이동 leg의 a = −0.0026 rad/s면 0.1 s당 약 0.13 mrad로 무시할 수준이다.
- **상한.** 파트너가 옆 이동 leg 전체에서 없는 최악은 약 1.1°이며 그때는 이미 쌍 운반 실패다.
- **신뢰 제한.** 자기 발행 명령이 계획된 own 명령과 같고 leg 창 안일 때만 파트너 항을 쓴다. 아니면 `pair_unmatched`로 세고 등록값 b로 폴백한다(위 폴백). cal 40건에서 `unmatched` 0.
- **한계.** 파트너가 다르게 움직이는 것(지연, 미끄러짐, 다른 게인)은 볼 수 없다. 이는 뒤의 lat−/opp·hA 과신의 한 원인 후보다.

### 소스 고정과 스모크·cal 40 재측정 (사전 기준 그대로)

관련 테스트: `test_zone_pair_v6e*`, `owncam_localizer`, `zone_pair_executor`, `v6c/v6d/v6f`, `pair_stage_probe`, `pair_chain_probe`, `registered_source`, `provider_init`, `bootstrap_v6b`, `vision_pose_source`, `zone_pair_v6`, `owncam_loop_views`: 414 통과, 2 skip, **5 실패 = 봉인 해시 테스트(등록 전 예상, main 병합 커밋 `62a5deaa`에서도 같음)**. 모델 호출 0, weld OFF, `--workers 2 --omp-threads 1 --pf-track`, driver PID로 agent_lock. raw(로컬, 원격 백업 아님): `outputs/pair-stage-probes-4fac772d-yawsmoke`, `-yawsmoke2`, `-yawcal`, `-yawhA`(각 `.stdout.log`, `-driver-driver.log`). cases.jsonl sha256 앞 16자: yawsmoke `8852c99fcbe1278f`, yawsmoke2 `95cd444f9cc0b9d0`, yawcal `97c39c53ef3dab0c`. cal 시작 부하 평균(1분) 9.3–28.2, 중앙 14.3(케이스별 `loadavg_case`; SIM 시간 결과 영향 없음), wall 합 4195 s.

| 항목 | 새 소스 `4fac772d` | 이전 `86cdefc9` | 사전 기준 |
|---|---|---|---|
| 스모크 | 4/4 | 4/4 | 통과 |
| cal 40건 전체 | 35/40 | 35/40 | (게이트 아님) |
| L1 / L2 | 5/5 / 5/5 | 5/5 / 5/5 | ≥ 4/5 |
| leg 끝 3자유도 평균 NEES (80 표본) | 2.20 (중앙 1.70) | 2.25 | [1.5, 6] |
| ±2σ 커버리지 x / y / yaw | 100 / 100 / 96.2 % | 100 / 100 / 93.8 % | yaw ≥ 90 % |
| L7 | 0/5 `PAIR_COLLISION_GUARD` | 0/5 | (판정 대상 아님) |

**판정: 사전 등록 cal 기준을 모두 충족(폴백이 통과를 깨지 않음).** 폴백 발동 비율(cal 40건, 로봇·프레임 합): `pm+edge` 59 %, `edge`만 23 %, `pm`만 7 %, 등록값 11 %; `partner_plan_unmatched` 0, 가장자리 `no_edge` 0·`rejected` 0(`resets` 560은 서보 변화·하역에 따른 기준 재시작). 세부: `analysis/nees_yawcal2.txt`(이전 `nees_yawcal.txt`).

### held-out hA 결과 (단계 2): **4/10, 기준(≥ 8/10) 미달**

cal 통과 뒤 계획대로 hA 10건(`--setup-variant hA`, legs 0 1 3 6 7 × nominal·yaw−/opp, `--nominal-seeds 914`)을 한 번 돌렸다. 계획에 따라 **hB·hC는 돌리지 않았고**, 소스·적합·기준을 바꾸지 않았다(재적합 없음). 앞서 중단한 `pair-stage-probes-b16f7987-yawhA`는 결과를 열지 않았고 held-out 증거로 쓰지 않는다(위 소스 변경 전 실행, 중단됨).

| 원인 | 건수 | 케이스 |
|---|---:|---|
| `MOTION_ERROR` end_error(끝점 오차 > 0.10 m) | 4 | yaw−/opp L0(0.116), yaw−/opp L1(0.130), nominal L1(0.105), yaw−/opp L6(0.111) |
| `PAIR_COLLISION_GUARD` (L7, 27.6–27.8 s) | 2 | nominal, yaw−/opp |
| 통과 | 4 | nominal L0, L3, L6; yaw−/opp L3 |

- 통과한 4건의 끝점 오차도 0.068–0.097 m로 기준 0.10 m에 붙어 있다. hA는 빔이 경로선(y=0.05)에서 옆으로 0.08 m 떨어진 채 시작한다(cal은 0.02 m). 끝점 오차는 계획 경로점과의 거리라 시작 오프셋이 이미 0.08 m를 차지한다(여유 2 cm). 결과는 시작 오프셋 + 열린루프 drift가 기준을 넘는지의 문제다.
- **PF 정직성도 hA에서 깨졌다**: leg 끝 NEES 8.62(> 6), 커버리지 x 100 / **y 35** / yaw 80 %(`analysis/nees_yawhA.txt`). 지배 항은 **y**다(z 1.3–3.4, err_y 5–12 cm 대 σ 약 3 cm). PF y 오차는 시작 −0.03 m에서 leg 끝 −0.04…−0.12 m로 자란다(yaw−/opp r2는 GT y가 0.13→0.18로 밀리는데 PF y가 거의 못 따라감). cal에서는 같은 셀(lat−/opp)의 GT y drift(+8 cm)를 PF가 따라갔는데(끝 오차 −2 cm) hA에서는 아니므로, y 쪽 dr 모델이 cal 배치(y = 0.03)에 맞춰져 있고 y = 0.13 배치에서 일반화하지 않았다고 본다(추정, 검증 안 됨).
- yaw는 σ 약 2.2°, 게이트 σ 상한 아래(σ_yaw_max 2.0–2.4°)라 `SELF_POSE_UNCERTAIN` 없음. yaw−/opp r2 leg 끝 yaw 오차 +4.3…+5.1°는 cal lat−/opp r2와 같은 크기의 과신이다(아래 분석).
- 축 leg에서 빔 이동 거리는 계획을 넘는다(0.89 대 0.85, 0.727 대 0.70 m). 열린루프 게인 초과 +3–4 cm.
- **해석 범위.** 이 4/10은 "hA 배치에서 cal로 적합한 dr 모델이 일반화하지 않았다"로 읽는다. 원인 분해(y 모델 vs 열린루프 물리 vs 시작 오프셋)는 하지 않았다. hB·hC는 미실행이므로 held-out 통과율은 hA 하나(4/10)뿐이다.

### L7 `PAIR_COLLISION_GUARD` 오프라인 진단 (raw만 읽음, 새 시뮬 0, 코드 변경 0)

재구성: 같은 장면의 정적 지도로 `PairSweepGuard`(role end_pos)를 만들고 기록된 r2 PF 자세(σ 포함)와 팔 서보 명령(`{1:1500,3:611,4:1711,5:2200,6:1500}`)으로 leg 7 마지막 명령(`forward -0.038, 0.15 s`) 직전 여유를 계산했다(작업 스크래치 `l7diag.py`). 대상 raw는 소스 `86cdefc9` 실행(`f2186414-yawcal`) nominal s911 L7이며 새 소스 raw도 같은 시각(27.8 s)에 같은 원인으로 실패했다.

- **어느 장애물, 어느 로봇**: 동쪽 벽 `wall_east`(x = 5.4 중심, 안쪽 면 5.375 m)와 r2(동쪽 끝 캐리어, 방위 π라 차체 뒤쪽이 +x). 판정 함수는 `PairSweepGuard.motion_clear` → `chassis_clearance`(뒤쪽 차체 모서리). 팔·빔 구가 아니라 차체다(팔+빔 여유는 +0.12 m).
- **숫자 (27.8 s)**: PF r2 x = 5.087, GT x = 5.065(PF가 벽 쪽으로 +2.2 cm 치우침). GT 원 간격(σ·잔차 없음) 0.157 m. 가드 여유 항: 기본 0.02 + 잔차 0.015 + 2σ_xy = 0.082(σ_xy 0.041) + 2σ_yaw·레버 = 0.012(σ_yaw 0.0344 rad, 레버 0.18 m) → 여유 합 0.130 m. 정지 여유 +0.008 m인데 다음 명령의 이동(0.038×1.6×0.15 ≈ 9 mm)과 표본 보정(1.5 mm)을 더하면 음수 → 거부.
- **σ가 작아지면 여유가 늘었나**: cal-2(σ_yaw 0.0499, σ_xy 0.045) 여유 합 0.142 m, 실패 시각 27.5–27.6 s. 새 σ(σ_yaw 0.0344, σ_xy 0.041) 0.130 m, 실패 27.8 s. 즉 **여유 항이 0.012 m 줄었고 실패가 0.2–0.3 s 늦어졌을 뿐 통과에는 못 미친다.** 줄어든 몫은 σ_xy 0.007 m + σ_yaw·레버 0.0055 m. σ_yaw·레버 항은 전체 여유의 10 % 안팎이고 지배 항은 2σ_xy(63 %)다. 부족분은 약 0.5–0.7 cm이고 PF의 x 편향 +2 cm가 그보다 크다.
- **좁은 통로/문인가**: 아니다. 문(`door_1`)은 x = 2.2, 이 leg는 x = 3.9→4.6의 목적 구역 B 안이다(`zone_B` 중심 (4.6, −2.1), 반폭 0.3 × 0.7). 병목이 아니라 **동쪽 벽까지 끝점 접근**이다: 빔 중심 4.6 + 캐리어 r2 기준점 +0.42 + 뒤쪽 0.15 = 약 5.2 m, 벽 면 5.375 m → 물리 간격 약 0.16 m(GT), 가드는 0.13 m 이상의 여유를 요구.
- **후보(적용 안 함, 입력 경계 준수)**: (1) 경로 끝점을 안쪽으로 0.10 m(x = 4.5, `zone_B` 반폭 0.3 안) — 물리 간격 약 0.26 m로 늘어 가드 여유를 넉넉히 통과, 지도·경로 계획 변경이라 가장 작은 변경; 성공 판정(구역 안 도착)이 x = 4.5에서도 유지되는지 확인 필요. (2) 가드 문턱: `BASE_MARGIN_M` 0.02 또는 xy `K_SIGMA`를 낮추면 통과하지만 안전 여유를 줄이는 결정이라 사용자 결정. (3) 정렬 허용오차·yaw 개선은 이 벽 접촉과 무관(σ_yaw 항 10 %). (4) PF x 편향(+2 cm)을 줄이면 0.5–0.7 cm 부족은 해소. 어느 것이든 새 코호트가 필요하다.

### lat−/opp·yaw−/opp r2 leg 끝 yaw 오차 4–6° > σ 2° (과신) 원인 추정 (기록만)

관찰: cal lat−/opp r2는 L1·L2·L6에서 −5.7°, −5.0°, −4.2°(σ 2.1–2.3°, z 2.0–2.5), 같은 leg의 nominal은 −0.5…−0.1°. L3–L5(옆 이동)는 작다(−0.75°). r1도 L1·L2에서 −3.6°, −3.1°. L1을 GT로 분해: 실제 yaw 변화 r1 +1.5°, r2 +7.9°, 빔 +4.7°(= 두 로봇 평균). PF 변화 r1 −2.1°, r2 +2.1°(평균 0°). 즉

1. **공통 모드 회전이 예측·측정 어디에도 없다.** 빔+두 로봇이 함께 +4.7° 도는데(nominal은 0.4°), 쌍 평균 플랜트 모델은 반대칭 결합을 상쇄해 평균 yaw 변화를 0으로 예측하고, 빔 가장자리 측정은 상대 yaw만 본다(공통 모드는 보이지 않는다는 분석 절의 한계와 일치). PF 평균 0° 대 GT +4.7°가 오차의 대부분이다.
2. **b가 셀 평균을 무시한 풀링 값이다.** b = cal 케이스별 (GT − 추정)/시간의 셀 균형 RMS(1.56 mrad/s = 0.09°/s). lat−/opp는 공통 모드 회전율이 약 0.15°/s로 b의 1.7배, nominal은 0.01°/s로 거의 0이다. 즉 편향이 영평균 무작위가 아니라 **셀(파지 오프셋)에 따라 결정되는 한쪽 방향 값**이다. 평균 NEES(2.2)와 커버리지(96 %)는 nominal이 많아 통과하지만 셀 조건부로는 과신이다. cal에 lat−/opp가 1 seed뿐이라 이 조건부 분산을 b가 못 본다.
3. **부분 관측된 상대 성분도 덜 보정된다.** 상대 yaw(r2−r1) GT 6.4° 중 PF는 4.2°(66 %)만 반영: 3 s 정착·중앙값 3·0.03 rad 스텝 한계·증분만 반영하는 설계의 지연·과소 반응이 원인 후보(검증 안 함).
4. **파트너 비대칭.** 쌍 평균 모델은 두 로봇이 거울 대칭으로 움직인다고 본다. lat−/opp에서는 GT 회전율이 r1 0.05°/s, r2 0.26°/s로 거울이 아니다(파지 오프셋으로 결합이 비대칭 — 추정).
5. **영향.** 스윕 가드 여유는 σ_yaw·레버(0.18 m)로 잡는데, 5.7° = 0.10 rad × 0.18 = 1.8 cm가 여유(1.2 cm)보다 커서 이 셀은 가드가 실제 자세 오차를 덮지 못한다. 게이트는 σ만 보므로 오차 5.7°에도 통과한다. hA yaw−/opp r2의 +4.3…+5.1°도 같은 패턴(공통 모드 + 셀 비대칭).

원인 추정이며 새 실험은 하지 않았다. 검증 방법 후보: 셀별 b로 바꾼 오프라인 재생, lat−/opp seed를 늘려 cal 재적합(사용자 결정, 소스 변경 포함).

### TensorBoard (소스 `4fac772d`)
스냅샷 `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6e-yaw2`(cal 40 + hA 10 = 50 run + 집계 2, `collection.json` sha256 `d496e8fd68a24e9a669909878e72a4b3fd53aeeba10394a164d54aeb817ccce9`), 파생 뷰 `outputs/pair-stage-probes-tbviews-0929-v6e-yaw2`. EventAccumulator로 경우별 `offline/stage_pass` 합 39(= cal 35 + hA 4), 집계 `pass_rate` 0.875(cal), 0.40(hA) 확인. `outputs/tensorboard-view.json`에는 키 `pair_stage_probes_v6e_yaw2_20260929` 하나만 추가했다. 대시보드 서버가 떠 있지 않았고 새로 시작하지 않았다(브라우저 표시 미확인). 이전 스냅샷(`…-v6e-yaw`, 소스 `86cdefc9`)은 그대로 두었다.

## y 오차 원인 분리, 일반화 모델 v6g 설계, 사전 등록 계획 (2026-09-29, 조정자 지시: hA 4/10 이후)

**stage probe이며 E2E·제어기·학생 성공이 아니다.** hA 10건은 이미 열어 봤으므로 **held-out 증거로는 소진**됐고 진단 자료로만 쓴다(적합에도 쓰지 않는다). hB·hC는 여전히 열지 않았다. 아래 분석은 기록된 raw만 다시 읽었다(새 물리 0; GT는 평가·분석에만 사용, 로봇 입력 경로에 들어가지 않는다). 등록·push·PR 없음.

### (1) 오프라인 원인 분리: 왜 σ_y ≈ 3 cm인데 y 오차가 5–12 cm였나

도구: `analysis/y_error_decomposition.py`(leg별 PF y 오차 변화를 heading·전진·옆 이동 항으로 분해), `analysis/y_error_phases.py`(steer 단계 6.4–12.3 s와 계획 leg 단계로 나눔), `analysis/y_error_summary.py` → 표 `analysis/y_error_summary.txt`. 입력: `pair-stage-probes-4fac772d-yawcal`(cal 40건, 로봇 80개 leg), `-yawhA`(10건). 부호는 명령 방향을 양으로 맞췄다.

| 배치·셀 | 로봇-leg | y 오차 시작 → leg 끝 (mm, PF−GT) | 변화 = heading + 전진 + 옆 (mm) | steer 단계 몸체 옆 이동 GT / PF (mm) | PF−GT (mm) |
|---|---:|---|---|---|---:|
| cal nominal | 48 | −30.3 → +11.4 | +41.7 = −0.7 −0.0 +42.5 | +9.0 / +42.9 | +34.0 |
| cal lat−/opp | 16 | −22.1 → −0.2 | +21.9 = −13.6 +0.2 +35.3 | +14.6 / +46.2 | +31.6 |
| cal yaw+/same | 16 | −30.1 → −18.1 | +12.0 = −25.0 +0.3 +36.7 | +15.0 / +41.8 | +26.8 |
| hA nominal | 10 | −29.5 → −55.8 | −26.4 = −3.5 −0.0 −22.8 | +33.8 / +68.5 | +34.7 |
| hA yaw−/opp | 10 | −30.1 → −92.4 | −62.3 = −15.9 +0.1 −46.5 | +5.3 / +38.3 | +33.0 |

시작 오차의 −0.03 m는 코스 order sheet(0.1 m·10° 격자 반올림)가 만드는 사전 오차다(배치별 −.03(cal), +.02(cal2), +.01(cal3), −.04(cal4), −.03(hA), +.04(hB), −.02(hC), 0(hD)).

**(a) 실제 y 드리프트의 출처.**
1. **지배 원인: 플랜트 선형 모델이 steer 단계에서 옆 이동을 부풀린다(모든 셀·배치에서 +33 ± 2 mm, 유령 이동).** steer 단계는 5.9 s 동안 아주 작은 옆 명령(|left| 0.0006–0.0145)을 낸다. 적재 플랜트의 옆 축은 정지 마찰 때문에 그 정도 명령에 거의 안 움직인다(GT 5–34 mm). 적합 GT = 0.844·sgn(u)·max(|u|−0.0059, 0)·T_eff, 잔차 rms 2.5 mm(선형 모델 6.3 mm). PF는 선형 게인으로 적분해 34–69 mm를 넣는다. 이 유령 이동은 **분산이 아니라 결정적 편향**이라 σ에 잡히지 않는다.
2. **cal에서 안 보였던 이유 = 우연한 상쇄.** cal은 빔이 경로선 아래(y .03 대 .05)라 steer가 +y로 가고 유령도 +y다. 시작 사전 오차(−0.03)가 반대 부호라 합이 +11 mm에서 0 근처로 상쇄된다. hA는 빔이 경로선 위(y .13)라 steer가 −y로 가서 유령(−35)이 사전 오차(−30)와 **같은 부호로 더해져** −56…−92 mm가 된다. "cal 배치(y = 0.03)에 맞춰져 y = 0.13에서 일반화 안 됨"이라는 앞선 추정은 옳았고 원인은 dr 모델의 y 외삽이 아니라 이 유령 이동의 부호 의존 상쇄다.
3. **yaw → y 결합(2차, 셀 조건부).** 전진 leg에서 PF yaw 오차 × 이동 거리가 y로 샌다. cal lat−/opp −13.6 mm, yaw+/same −25.0 mm, hA yaw−/opp −15.9 mm(nominal은 −0.7…−3.5). 공통 모드 yaw 드리프트가 있는 셀에서만 생기고 빔 가장자리 추적기는 그것을 못 본다.
4. **측방 슬립/지연(3차, 작음).** 축 leg의 몸체 옆 GT 이동 평균은 hA yaw−/opp +5.0 mm(PF −0.4), cal lat−/opp +7.1 mm(PF −0.1), 나머지 셀 −0.3…+0.1 mm다. 진짜 옆 슬립은 회전이 있는 두 셀에만 있고 5–7 mm로 유령 이동(33 mm)의 1/5 이하다.
5. **dr 모델 y 외삽(배치 y = 0.13)은 독립 원인이 아니다.** steer 단계의 유령 이동은 명령 크기(≈ 0.0006–0.0145)가 작다는 것에서 오며 y 배치 자체와는 부호를 통해서만 연결된다.

**(b) PF y 프로세스 노이즈가 이동거리·측방 속도에 비례하는가: 아니다.** 적재 플랜트 프로파일은 `noise_rel` 0, 시간 기반 백색 `noise_abs` y 0.0111 m/s, 옆 명령에만 곱해지는 스케일 표준편차 0.024(6 s steer 43 mm에서 ≈ 1 mm), 입자별 yaw 편향 b(pm+edge 1.56 mrad/s)뿐이다. leg 끝 σ_y 2.4–3.9 cm는 e2e 사전 표준편차 0.03에 거의 그대로 머물고(시작 σ 0.030 → 끝 0.027–0.038) 이동거리 비례 성장이 없다. 그래서 (i) 결정적 편향(유령 이동)은 어떤 입자도 덮지 못하고 (ii) 교차 축 드리프트(전진 leg의 옆 밀림)도 분산에 들어가 있지 않다.

### (2) 참고자료 조사(막힌 뒤 레퍼런스 우선)와 일반화 원칙

- Thrun, Burgard, Fox, *Probabilistic Robotics* (MIT Press, 2005), 5장 odometry motion model: 회전1·이동·회전2 각각의 분산이 α1–α4 곱하기 명령 크기(회전²·이동²)에 비례한다. **잡음은 명령 크기에 비례**하고 상수 시간 잡음이 아니다.
- AMCL `amcl_odom.cpp`(ROS `nav2`·`navigation` 저장소, omni 모델; raw GitHub에서 읽음): 옆(strafe) 분산 = α1·rot² + α5·trans², 이동 분산 = α3·trans² + α1·rot², 회전 분산 = α4·rot² + α2·trans². 즉 옆 이동 잡음이 **전체 이동 거리에 비례**(교차 축 α5)한다. `wiki.ros.org/amcl`은 접근 차단(Anubis)이라 소스 코드로 대신 확인.
- Borenstein & Feng, "Measurement and correction of systematic odometry errors in mobile robots", *IEEE Trans. Robotics and Automation* 12(6):869–880 (1996), UMBmark: 체계 오차(게인·바퀴 비대칭)와 비체계 오차를 나눠 **체계 성분은 소수의 물리 파라미터로 보정하고 잔차만 잡음**으로 둔다.
- 우리 상황에서 얻은 것: 위 셋의 공통 구조 = "**명령 크기에 비례하는 잡음 + 소수의 물리 파라미터(체계 오차)**". 지금 모델은 (i) 체계 오차(정지 마찰 = 옆 명령 비선형)를 선형으로 근사해 편향을, (ii) 잡음이 시간 기반이라 교차 축 성분을 놓쳤다.
- 우리 제약 때문에 바꾼 부분: 표준 모델은 바퀴 엔코더 오도메트리를 쓰지만 우리는 발행 명령(`u`)만 있다(측정 관절·엔코더 금지). 그래서 명령→운동 변환은 적재 플랜트 선형 게인 위에 옆 축 돌파(breakaway) 램프와 거리 비례 교차 축 비율만 얹는다. 게이트 `GATE_LOADED`(3°/2.5°)는 바꾸지 않는다.

### v6g 설계 (`carry_dr_general` 플래그, 기본 OFF, OFF 출력은 v6e와 바이트 동일)

| 요소 | 내용 | 근거 |
|---|---|---|
| 옆 명령 돌파 램프 | r = clip((|u|−c0)/(u1−c0), 0, 1)를 옆 축 명령에만 곱함(전진·회전은 선형). c0, u1은 cal steer 단계에서 최소제곱 | UMBmark의 체계 성분 = 소수 물리 파라미터. 뺄셈 데드밴드는 큰 명령의 보정 게인을 바꾸므로 램프를 쓴다 |
| 교차 축 드리프트 비율 | 입자별 상수 비율(표준편차 `drift_ratio_std`) × 축 이동 거리 | Thrun α, AMCL α5(거리 비례 옆 잡음) |
| yaw b·기울기 비율 | 구조는 v6e 그대로, **새 cal 집합으로 다시 적합** | 셀·배치 일반화 |

구현: `harness/owncam_localizer.py`(`drift` 입자 필드, `predict_to` 램프·드리프트), `harness/owncam_carry_v6e.py`(`GENERAL_FIT`, `load_pair_fit(general)`, `enable_provider(..., general)`), `harness/zone_pair_v6_policy.py`(정책 `b-v6g`, `b-v6g-l7`), `experiments/2026-09-29-pair-v6e-carry/fit_carry_general.py`(적합 → `carry_general_fit.json`). 적합 입력은 cal 배치 raw만이며 hA·hB·hC·hD는 읽지 않는다(hA는 램프의 진단 점수만 계산, 적합 안 함).

### (4) L7 끝점 안쪽 0.10 m (opt-in 경로 계획 변경)

`make_plan(..., end_inset_m)`이 **마지막 경로점만** 안쪽(x = 4.6 → 4.5, `zone_B` 반폭 0.3 안)으로 옮긴다. 분할 뒤에 적용하므로 이전 leg(L6 포함)는 그대로다. 정책 `b-v6g-l7`(`carry_end_inset_m` 0.10) 전용, 기본 0. 가드 문턱(`BASE_MARGIN_M`, `K_SIGMA`)은 바꾸지 않는다. 끝점 정의가 바뀌므로 **L7은 다른 leg와 합산하지 않고 따로 표기**한다.

### (3)(5) [폐기 — 기존 그림자 프로필 기준, 아래 "갱신된 사전 등록 계획"으로 대체] 사전 등록 계획 (측정 전에 고정)

배치(setup variant, `beam_xyyaw`): cal [.93, .03, 0], cal2 [.90, .08, 0], cal3 [.96, −.01, +.03], cal4 [1.05, .14, −.03] = **적합 배치**(y 오프셋 .03/.08/−.01/.14, 헤딩 0/0/+.03/−.03 rad). 적합 자료 수집은 이 README 계획 고정보다 먼저 시작했다(`pair-stage-probes-ba834d02-gcal{2,3,4}`, b-v6e, 소스 `ba834d02`; 기준은 수집 결과를 보기 전에 정했다). held-out = hB [1.13, −.04, 0] (y −.04, 적합 범위 밖), hC [1.03, .12, 0] (y .12), hD [1.00, .10, +.03] (y .10, 적합에 안 쓴 값). hA는 진단.

적합 자료: 이전 cal raw(`ece38792-cal`, `a704ecc6-calB2`, `-calB`, `4fac772d-yawcal`)와 새 `ba834d02-gcal2/3/4`. 적합 수락 조건(측정 전): steer 단계 옆 이동 잔차 rms ≤ 4 mm이고 선형 모델보다 개선. 아니면 여기서 멈추고 보고한다(held-out을 본 뒤 모델 구조를 바꾸지 않는다).

| 단계 | 내용 | 통과 기준 |
|---|---|---|
| 0 스모크 | `b-v6g` cal 배치 4건(nominal L0·L1, lat−/opp L1·L3) + `b-v6g-l7` nominal L7 1건(별도 표기) | 4/4 통과. L7은 결과만 보고 |
| 1 새 cal | `b-v6g`로 cal 35건(이전 사양에서 L7 제외: legs 0–6 × nominal ×3 seed·yaw+/same·lat−/opp) + cal2·cal3·cal4 각 20건(legs 0 1 2 3 6 × nominal·yaw+/same·lat−/opp·yaw−/opp). L7은 `b-v6g-l7`로 cal 배치 5건(nominal ×3·yaw+/same·lat−/opp)을 **따로** 돌려 별도 표기(끝점이 달라 합산하지 않음) | cal 배치: 비 L7 통과 전부(이전 35/35 유지). cal2–4 각 ≥ 18/20. 세 배치 각각 leg 끝 3자유도 평균 NEES ∈ [1.5, 6]. 각 배치에서 x·y·yaw ±2σ 커버리지 ≥ 90 % |
| 2 held-out | hB, hC, hD 각각: legs 0 1 2 3 6 × nominal(seed 914)·yaw−/opp = 10건(hA 사양에서 L7 대신 L2). 동시에 별도 L7 2건(`b-v6g-l7`, nominal·yaw−/opp) | **각 held-out ≥ 8/10**, leg 끝 NEES ∈ [1.5, 6], x·y·yaw 커버리지 ≥ 90 %(표본 20). 정직성(NEES·커버리지)이 통과의 전제: 성공률이 8/10 이상이라도 NEES 또는 커버리지가 기준 밖이면 **그 held-out은 미통과**. |

실행 규칙: 소스·적합 파일·기준은 코호트 중 고정(해시 기록). 각 단계는 앞 단계 통과 뒤에만. 코호트 안에서 재적합·재시도·케이스 제외 없음. 실패하면 그 자리에서 멈추고 원인별(MOTION_ERROR/가드/정직성/PF 편향)로 보고. 세 held-out은 서로 독립이라 hB·hC·hD를 한 번에 돌리며(같은 소스), 하나라도 실패하면 어느 것도 "일반화 통과"로 쓰지 않고, 실패 뒤 그 raw는 진단용이 된다. 정직성 조건은 게이트를 바꾸지 않은 채(σ_yaw 상한 `GATE_LOADED` 유지) 측정하며, σ가 커져 `SELF_POSE_UNCERTAIN`이 나면 그 자체가 결과다. 모델 호출 0, weld OFF, `--workers 2 --omp-threads 1 --pf-track`, driver PID로 agent_lock, 부하 평균 기록, 관련 테스트만.

## 렌더 프로필 전환 `floor_light_v1` (2026-09-29, 사용자 결정) 과 계획 갱신

사용자 결정으로 이 코호트를 기존 그림자 설정이 아니라 새 렌더 프로필 `floor_light_v1`(그림자·반사 끔 + 점광원 0.3배 + 밝은 무채색 바닥, main 병합 PR #272)로 진행한다(렌더 CPU 약 절반, 더 현실적인 밝기). 이에 따라:

- 방금 시작한 `ba834d02-gcal4`(결과 0건)는 내가 자기 프로세스만 정상 중단했다(**렌더 프로필 전환으로 중단**, 잠금 해제; 드라이버 로그에 기록). 이미 끝난 `ba834d02-gcal2`, `-gcal3`(20건씩)와 그 이전 raw(cal 35/40, hA 4/10 등)는 **기존 그림자 설정** 결과로 다른 조건이다. **새 결과와 합산·직접 비교하지 않고**(같은 케이스 비교만 참고), 위 "(1) 원인 분리" 표도 기존 프로필 raw에서 나온 것이다. 새 프로필 raw로 같은 분해를 다시 낸다.
- 위의 "사전 등록 계획" 표와 적합 입력 목록은 **기존 프로필 기준이라 폐기**하고 아래 갱신 계획으로 대체한다(원문은 이력으로 남김). 기준값(≥ 8/10, 커버리지 ≥ 90 %, NEES [1.5, 6])은 그대로다.
- 모든 실행에 `--render-profile floor_light_v1`을 붙이고 manifest·케이스 행에 프로필 이름·해시가 기록되는지 확인한다.
- 소스: main(#272 포함) 병합 뒤 `cb215732`(v6g opt-in 코드; 플래그 OFF는 이전 출력과 같음). 관련 테스트 485 통과, 5 실패는 알려진 봉인 해시(`test_zone_pair_registered_source.py`, 등록 전 예상).

### 단계 R: 새 영상 스모크 (측정 전 고정 기준; 소스 `cb215732`, 정책 `b-v6e`, cal 배치)

영상이 바뀌므로 빔 가장자리(own_beam_edge)·빔 색 검출·영상 검사가 정상인지 먼저 본다. 케이스 5건: nominal L0·L1·L6, lat−/opp L1·L3(기존 프로필 cal 40건의 같은 케이스와 나란히 비교). 판정(모두 만족해야 다음 단계): (1) 5/5 통과, (2) 영상 검사 실패·검은 프레임 0건, (3) 빔 색 검출 픽셀 수가 기존 프로필 같은 케이스 대비 0.7–1.3배, (4) 가장자리 추적기 `no_edge`·`rejected` 0, 가장자리 기울기 대 GT 상대 yaw 비율이 기존 적합 1.008과 ±15 % 안. 어긋나면 전체를 돌리지 않고 원인만 보고한다.

### 단계 R 결과: 통과 (모든 판정 기준 충족)

raw(로컬, 원격 백업 아님): `outputs/pair-stage-probes-cb215732-rsmoke`(nominal L0·L1·L6, 3건), `outputs/pair-stage-probes-7392cb49-rsmoke2`(lat−/opp L1·L3, 2건; 첫 실행이 README 수정으로 "tracked source must be clean" 거부돼 README만 커밋한 뒤 다시 돌림, 코드 동일). 두 manifest 모두 `render_profile floor_light_v1`, sha256 `e3ea8aebc473f99def92fa368f8aaa11e5872dc5b2a8ec8ba9a308641d2b6ec5`가 기록됨. 도구 `analysis/render_profile_smoke.py`(기록된 프레임만 다시 읽음).

| 판정 | 새 프로필 | 기존 프로필(같은 케이스) | 기준 |
|---|---|---|---|
| 통과 | 5/5 | 5/5 | 5/5 |
| 영상 검사: 검은 프레임(평균 V < 8) 비율 | 0.00 (케이스·로봇 10개 모두) | 0.00 | 0건 |
| 빔 색 검출 픽셀 수(프레임 평균, 새/기존) | 62,243–79,458 / 62,122–79,410, 비 1.00–1.01 | | 0.7–1.3배 |
| 빔 가장자리 추적기 | 402프레임 중 `no_edge` 0, `rejected` 0, `applied` 382, `resets` 0 | 같음 | `no_edge`·`rejected` 0 |
| 가장자리 기울기 대 GT 상대 yaw 비율 | 1.010 (n 4) | 1.003 | 1.008 ± 15 % |
| 끝점 오차 / 정지 sim 시간 | 기존과 소수 셋째 자리까지 같음(0.023–0.072 m) / 같음 | | (참고) |
| wall 시간(케이스) | 45–53 s | 96–124 s | (참고) 약 절반 |

해석: 운반 단계 손목 카메라는 빔을 가까이서 보므로 이 프로필은 빔·가장자리 영상에 거의 영향이 없고(픽셀 수 차이 ≤ 1 %), 물리 결과는 sim 시간까지 같다. 바닥이 보이는 단계(랜드마크 관측)는 이 스모크가 다루지 않는다. 합산 금지 원칙에 따라 기존 raw는 적합·판정에 쓰지 않고 새 프로필로 다시 측정한다.

## 갱신된 사전 등록 계획 (새 프로필, 측정 전 고정; 기준값은 기존과 동일)

배치: cal [.93, .03, 0], cal2 [.90, .08, 0], cal3 [.96, −.01, +.03], cal4 [1.05, .14, −.03] = 적합 배치(y .03/.08/−.01/.14, 헤딩 0/0/+.03/−.03 rad). held-out hB [1.13, −.04, 0], hC [1.03, .12, 0], hD [1.00, .10, +.03](적합에 안 쓴 y 값). hA(기존 프로필)는 진단 자료이며 적합·held-out에 쓰지 않는다. 모든 raw는 `--render-profile floor_light_v1`.

| 단계 | 내용 | 통과 기준 |
|---|---|---|
| F 적합 자료 수집 | 정책 `b-v6e`(소스 `7392cb49`, 코드 동일)로 새 프로필 raw: `fcal` = cal 배치 legs 0–6 × nominal ×3 seed·yaw+/same·lat−/opp·yaw−/opp = 42건, `fcal2`·`fcal3`·`fcal4` = 각 legs 0 1 2 3 6 × 4셀 = 20건 (합 102건). L7은 여기서 제외 | 수집만(판정 없음). 적합 수락 조건(측정 전): steer 단계 옆 이동 잔차 rms ≤ 4 mm이고 선형 모델보다 개선, 아니면 멈추고 보고 |
| 적합 | `fit_carry_general.py`(입력 = 위 4개 새 raw만; 기존 프로필 raw·hA·hB·hC·hD는 읽지 않음) → `carry_general_fit.json` → 새 소스 커밋(고정) | |
| 0 스모크 | `b-v6g` cal 배치 nominal L0·L1, lat−/opp L1·L3(4건) + `b-v6g-l7` nominal L7(1건, 별도 표기) | 4/4 통과. L7은 결과만 보고 |
| 1 새 cal | `b-v6g`로 `cal` 42건(legs 0–6 × nominal ×3·yaw+/same·lat−/opp·yaw−/opp)과 cal2·cal3·cal4 각 20건. 별도로 `b-v6g-l7`로 cal 배치 L7 6건(nominal ×3·세 셀) | 배치별 비 L7 통과율 ≥ 90 %(cal ≥ 38/42, cal2–4 각 ≥ 18/20); 배치별 leg 끝 3자유도 평균 NEES ∈ [1.5, 6]; 배치별 x·y·yaw ±2σ 커버리지 ≥ 90 % |
| 2 held-out | hB, hC, hD 각각 legs 0 1 2 3 6 × nominal(seed 914)·yaw−/opp = 10건(`b-v6g`), 별도로 L7 2건(`b-v6g-l7`; nominal·yaw−/opp). 최종 소스에서 각 배치 한 번만 | **각 held-out ≥ 8/10**, NEES ∈ [1.5, 6], x·y·yaw 커버리지 ≥ 90 %(표본 20). NEES·커버리지가 기준 밖이면 성공률이 ≥ 8/10이어도 **그 held-out은 미통과**(정직성이 전제) |

실행 규칙은 위 폐기된 계획과 같다: 소스·적합 파일·기준은 코호트 중 고정(해시 기록), 재적합·재시도·케이스 제외 없음, 실패 시 멈추고 원인별(MOTION_ERROR / 가드 / 정직성 / PF 편향) 보고, 하나라도 실패하면 어느 것도 "일반화 통과"로 쓰지 않고 그 raw는 진단용. 게이트(`GATE_LOADED`) 미변경. 모델 호출 0, weld OFF, `--workers 2 --omp-threads 1 --pf-track`, driver PID로 agent_lock, 부하 평균 기록, 관련 테스트만. 이 단락이 커밋된 뒤에만 단계 F를 시작한다.

## 단계 F 결과와 v6g 적합 (새 프로필 raw만 사용; 소스 고정)

**단계 F 수집** (정책 `b-v6e`, `--render-profile floor_light_v1`, 케이스 행 전부 프로필 기록 확인; 판정 없는 적합 자료). raw(로컬, 원격 백업 아님): `outputs/pair-stage-probes-ece01311-fcal`(42건), `-7cecaf9b-fcal2`, `-fcal3`, `-fcal4`(각 20건). 통과: cal 41/42(가드 1), cal2 19/20, cal3 19/20, cal4 16/20(가드 2, MOTION_ERROR 2). `ece01311`에서 fcal2–4는 내가 적합 스크립트를 수정하는 바람에 "tracked source must be clean"으로 시작하지 못했고(0건), 코드 동일한 `7cecaf9b`에서 다시 돌렸다. 앞의 `ba834d02-gcal4`는 프로필 전환으로 중단, 기존 프로필 gcal2·gcal3는 적합에 쓰지 않았다. 부하 평균은 케이스별 `loadavg_case_*`에 기록.

**적합** (`fit_carry_general.py`, 입력 = 위 4개 raw만; 출력 `carry_general_fit.json` sha256 `9603ce32924b2778943d8232a39ce48237e2881b4d0e2dbdd5310a108fad4a0b`, 행 `carry_general_fit_rows.json` `071341df1dda54584a886f65158b610b79c9e25ad433f66b6942e4da6baa9e77`):

| 항목 | 값 | 수락 조건/참고 |
|---|---|---|
| steer 단계 옆 이동 램프 c0 / u1 | 0.0002 / 0.0292 (사실상 2차 곡선: 작은 명령에서 응답 ∝ u²) | 잔차 rms 3.85 mm ≤ 4 mm, 선형 모델 32.83 mm → **수락**(200 로봇-케이스) |
| hA(적합 안 함, 기존 프로필 raw) 진단 점수 | 램프 모델 rms 4.43 mm, 부호 평균 −0.26 mm | 선형 모델 33.90 mm, +33.85 mm(유령 이동). 즉 hA의 유령 이동이 없어짐 |
| 교차 축 드리프트 비율 `drift_ratio_std` | 0.0159 m/m (셀별 RMS: lat−/opp 0.0245, yaw−/opp 0.0196, nominal 0.0034, yaw+/same 0.0035) | 셀 균형 RMS. 회전이 있는 두 셀이 지배 |
| 기울기→yaw 비율 | 1.0056 (상관 0.9993, n 172) | 이전 1.008 |
| yaw b [mrad/s] | pm 2.28, edge 2.26, pm+edge 2.04, 등록값 e0 2.55 | 이전(pm+edge) 1.56. yaw−/opp 셀과 y 오프셋 배치를 넣어 커졌다(더 정직한 값). 셀별 RMS(pm+edge): nominal 1.21, lat−/opp 2.60, yaw−/opp 2.16, yaw+/same 1.95 |

주의(측정 전 기록): b가 커져 leg 끝 σ_yaw가 커진다. `GATE_LOADED`(3°/2.5°)는 바꾸지 않으므로 `SELF_POSE_UNCERTAIN`이 나면 그 자체가 결과다.

**소스 고정.** 관련 테스트 496 통과, 4 skip, 5 실패 = 알려진 봉인 해시(`test_zone_pair_registered_source.py`, 등록 전 예상). 새 테스트 `tests/test_zone_pair_v6g.py`(11건, 커밋된 적합 파일 로딩 포함). 이 커밋 이후 소스(`harness/`, `scripts/`, `sim/`, `tests/`)를 바꾸지 않고, README만 결과 기록으로 바꾼다.

## v6g 스모크 결과(소스 `f844a373`): **1/4 통과 — 사전 기준(4/4) 미달** — 그리고 held-out으로 직행하는 결정

raw: `outputs/pair-stage-probes-f844a373-gsmoke`, `-gsmoke2`, `-gsmokeL7`(`--render-profile floor_light_v1`, manifest 프로필 해시 기록 확인).

| 케이스 (cal 배치) | 결과 | 원인 |
|---|---|---|
| nominal L0 | 실패 | `PAIR_COLLISION_GUARD` (25.8 s) |
| nominal L1 | 실패 | `SELF_POSE_UNCERTAIN` yaw (31.3 s): σ_yaw 3.01° / 2.94°가 게이트(3°/2.5° 계열)를 넘음 |
| lat−/opp L3 | 통과 | 끝점 오차 0.023 m |
| lat−/opp L1 | 실패 | `PAIR_COLLISION_GUARD` (29.5 s) |
| (별도 표기) `b-v6g-l7` nominal L7 | **통과** | 끝점 오차 0.047 m — 끝점을 안쪽 0.10 m로 옮기면 가드 문제가 사라짐 |

같은 케이스의 `b-v6e`(4fac772d, 기존 프로필)는 모두 통과였다. 원인 분해(leg 끝 σ와 오차, v6e → v6g):
- **PF의 y 편향은 없어졌다.** GT−PF y 오차 leg 끝 v6e −21…−13 mm(유령 이동) → v6g +4…+21 mm(사전 오차 −30 mm는 그대로 남고 σ_y 안). yaw 오차는 거의 같다(예: nominal 0.2→0.2°).
- **그러나 σ가 정직해지며 커졌다.** σ_yaw(leg 끝) nominal L0 1.95→2.36°, L1 2.33→3.01°; σ_xy 0.033→0.036, 0.040→0.047. b가 1.56→2.04 mrad/s로(회전 셀·y 오프셋 배치를 적합에 넣은 결과), 교차 축 드리프트 비율 0.0159가 nominal 셀(실측 0.0034)에도 똑같이 적용된 결과다. 회전이 있는 셀만의 b(2.2–2.8)에 비해 nominal은 0.9–1.2로 작다. **고정 게이트(`GATE_LOADED`, 스윕 가드 여유 = 기본 + 2σ)는 σ가 커지면 통과하지 못한다.** 즉 "정직한 σ"와 "안전 게이트 유지"가 충돌한다(앞서 예고한 긴장). 게이트는 바꾸지 않았다.
- 이것은 사전 기준 4/4 미달이므로 원래 계획(앞 단계 통과 뒤에만 다음 단계)은 여기서 멈추는 것이 맞다. 그러나 조정자(사용자) 결정으로 현재 소스를 **최종으로 고정하고 hB·hC·hD를 한 번씩 실행**한다. 이 경우 성공률은 게이트 실패를 포함하고, **PF 정직성(NEES·커버리지)은 실패한 케이스도 트레이스가 있는 구간까지 포함해 별도로 보고**한다(성공률과 정직성을 분리해 원인별로 보이기 위함). 재적합은 최대 1회이며 그 뒤에는 멈추고 보고한다.

### 작동 범위와 cal4 (측정 전 고정)

- `cal4`(빔 y 0.14 m, 헤딩 −0.03 rad)는 L1(문 통과)에서 4/4 실패하고 가드 2·MOTION_ERROR 2로 16/20이었다. 사용자 결정으로 **작동 범위 밖**으로 기록하고 더 고치지 않는다. 작동 범위(측정 전 고정): 빔 월드 y ∈ [−0.04, 0.12] m, |헤딩| ≤ 0.03 rad. (hB −.04·hC .12·hD .10은 범위 안, cal4 .14는 밖, 범위의 이유는 아래 "배치 분포"에서 참고로만 덧붙임.) 범위 밖 배치는 통과 기준·held-out에서 제외한다.
- **cal4 자료는 적합에 그대로 사용한다**(재적합 없음). steer 단계 램프·드리프트·b는 플랜트 성질이지 배치 성질이 아니다. cal4를 뺀 대체 적합(같은 스크립트 `--exclude fcal4`)도 계산했더니 램프 rms 3.74 mm, `drift_ratio_std` 0.0161, b(pm+edge) 2.16으로 거의 같아서(오히려 b가 큼) 바꾸지 않는다. 최종 적합은 `carry_general_fit.json`(sha256 `9603ce32924b2778943d8232a39ce48237e2881b4d0e2dbdd5310a108fad4a0b`) 그대로다.

### held-out 실행 계획 (측정 전 고정, 기준값 불변)

hB [1.13, −.04, 0], hC [1.03, .12, 0], hD [1.00, .10, +.03] 각각 `b-v6g`로 legs 0 1 2 3 6 × nominal(seed 914)·yaw−/opp = 10건, 별도로 `b-v6g-l7` L7 2건. 소스 `f844a373`의 코드 그대로(README·적합 스크립트 옵션만 이후 커밋). 판정: 각 held-out ≥ 8/10, leg 끝 NEES ∈ [1.5, 6], x·y·yaw ±2σ 커버리지 ≥ 90 %. 통과하지 못하면 어떤 것도 "일반화 통과"로 쓰지 않고 원인별(가드·게이트·모션 오차·정직성) 표로 보고한다. 통과하면 소스 등록·push·PR 절차로 넘어간다.

## 결과: v6g held-out hB / hC / hD (소스 `f844a373`, 새 프로필 `floor_light_v1`, 2026-09-29): **기준 미달 (hB만 통과)**

**stage probe이며 E2E·제어기·학생 성공이 아니다.** 등록·push·PR 없음(기준 미달). raw(로컬, 원격 백업 아님): `outputs/pair-stage-probes-f0716773-ghB`, `-ghC`, `-ghD`(각 10건, `b-v6g`), `-ghBL7`, `-ghCL7`, `-ghDL7`(각 2건, `b-v6g-l7`, 별도 표기). 소스 코드는 `f844a373` 그대로(그 뒤 커밋은 README·적합 스크립트 옵션뿐; `git diff f844a373 f0716773 -- harness scripts sim tests` 비어 있음). cases.jsonl sha256 앞 16자: ghB `ce529e0275abc1b9`, ghC `3c2fd731005de0d9`, ghD `511998aec6d1c733`, ghBL7 `a19295eecdd9cb0a`, ghCL7 `9f904bb50dad4f61`, ghDL7 `3f6664a6dea39c82`. 모델 호출 0, weld OFF, `--workers 2 --omp-threads 1 --pf-track`, driver PID(16199)로 agent_lock, 시작 부하 평균 7–21(SIM 시간 결과 영향 없음), wall 합 446/465/587 s.

### 사전 기준 대비

| held-out (빔 y, 헤딩) | 통과 (기준 ≥ 8/10) | leg 끝 NEES (기준 1.5–6) | ±2σ 커버리지 x / y / yaw (기준 ≥ 90 %) | 판정 |
|---|---|---|---|---|
| hB (−.04 m, 0) | **8/10** | 2.33 | 95 / 95 / 95 % | **통과** |
| hC (.12 m, 0) | 5/10 | 2.38 | 100 / 95 / 100 % | 미달(통과율) |
| hD (.10 m, +.03 rad) | 7/10 | 4.91 | 100 / **80 / 80 %** | 미달(통과율, y·yaw 커버리지) |
| L7 `b-v6g-l7`(끝점 0.10 m 안쪽; 별도 표기) | 2/2, 2/2, 2/2 (6/6) | | | 참고 |

세 held-out이 모두 통과해야 "일반화 통과"이므로 **통과 아님**. 재적합은 하지 않았다(아래 원인은 재적합으로 풀리지 않는다).

### leg별 결과 (P = 통과, G = `PAIR_COLLISION_GUARD`, M = `MOTION_ERROR:end_error`)

| held-out·셀 | L0 | L1(문 통과) | L2 | L3 | L6 |
|---|---|---|---|---|---|
| hB nominal | P | G | P | P | P |
| hB yaw−/opp | P | G | P | P | P |
| hC nominal | G | G | P | P | P |
| hC yaw−/opp | G | G | P | P | M (끝점 오차 > 0.10 m) |
| hD nominal | G | G | P | P | P |
| hD yaw−/opp | P | G | P | P | P |

30건 중 실패 10건: 가드 9건, 모션 오차 1건. **L2·L3·L6은 17/18 통과(실패 1은 모션 오차), L1(문 통과)은 0/6, L0은 hB 2/2 통과, hC·hD(빔 y ≥ 0.10)에서 1/4 통과.** 스모크(cal 배치)에서도 L0 nominal, L1 nominal(`SELF_POSE_UNCERTAIN`), L1 lat−/opp가 같은 이유로 실패했다.

### 원인별 분석

1. **PF의 y 편향은 없어졌다 (개선).** GT−PF y 오차(끝, hB/hC/hD): PF y가 GT를 따라가고(예: hC r2 GT .097 대 PF .082; 이전 `b-v6e` hA r2 GT .100 대 PF .041), 커버리지 y·yaw 95 % 안팎(hB, hC). 시작 사전 오차(−0.03 m)가 남는 것은 σ_y 안에 든다. 즉 원인 분해의 핵심(steer 단계 유령 이동)은 해소됐다.
2. **실패의 지배 원인은 안전 가드이며 σ가 아니라 "정직해진 위치"와 문 여유의 조합이다.** 지도(`zone_wide_door_tags_v2_dock_v3`)의 문은 y ∈ [−0.20, 0.30], 중심 0.05, 폭 0.5 m다. 차체 반폭에 가드 여유(기본 0.02 + 잔차 0.015 + 2σ_xy 약 0.08 + 2σ_yaw·레버)를 더하면 문 중심 기준 허용 오차가 ±1–2 cm 수준이다. 이전 `b-v6e`가 hA(y .13)에서 L0을 통과한 것은 PF y가 GT보다 6 cm 낮게(문 중심 쪽으로) 잘못 믿어서 생긴 우연이었다(r2 PF y .041 대 GT .100). 편향이 사라지자 가드는 실제 위치를 보고 막는다. L0 실패는 빔 y ≥ 0.10인 hC·hD에서만 났다(r2 정지 위치가 hA v6e보다 6 cm 앞).
3. **σ 증가는 2차 원인.** 회전 셀·y 오프셋 배치까지 적합한 b가 1.56 → 2.04 mrad/s, 교차 축 드리프트 비율 0.0159가 nominal 셀에도 적용되어 leg 끝 σ_yaw가 1.95 → 2.36°(L0), 2.33 → 3.01°(L1)로 커졌다. L1의 `SELF_POSE_UNCERTAIN`(σ_yaw > 게이트)과 일부 가드는 여기서 왔다. 게이트는 바꾸지 않았다.
4. **hD 커버리지 미달: 빔 헤딩 +0.03 rad(1.7°)가 PF 헤딩에 남는다.** hD nominal 셀의 끝 yaw 오차가 +2.4…+3.3°로 한쪽 방향(20표본 중 4표본이 ±2σ 밖). 헤딩 오프셋 배치는 적합에 cal3(+.03)·cal4(−.03)만 있고 견고한 헤딩 보정 관측이 없어서 순서 시트 반올림 오차(10° 격자)가 그대로 남는다.
5. **hC yaw−/opp L6 모션 오차**는 끝점 오차 0.10 m 초과 1건(같은 셀 hA L1·L6과 같은 유형).

### 해석 (범위 제한)

- 정직성(NEES·커버리지) 기준은 hB·hC에서 충족, hD에서 미달. 운반 통과율은 hB만 충족. **원인은 (i) 정직한 위치 + 고정 가드 + 0.5 m 문 여유, (ii) 정직한 σ의 증가, (iii) 헤딩 오프셋 미보정**이며 재적합(입력이 같은 플랜트 자료)으로는 바뀌지 않는다. 가능한 개선은 (a) 문 근처에서 새 정보를 넣기(문틀·표식이 앞 카메라에 보이는 구간의 위치 수정; 별도 PR #271의 통과 지도), (b) 가드·게이트 문턱 결정(사용자), (c) 누적 시간 줄이기(steer 5.9 s·L0) 등이며 어느 것도 이 소스에 넣지 않았다.
- `b-v6g-l7`(끝점 0.10 m 안쪽)은 6/6 통과하여 동쪽 벽 가드 문제는 해소된다(끝점 정의가 달라 다른 leg와 합산하지 않음).

## 배치 분포 (참고, 진행의 전제 아님; 기존 raw 재사용, 새 물리 0)

`analysis/placement_distribution.py` → `analysis/placement_distribution.txt`. 기존 align·grasp_lift raw(그림자 있음/없음 모두)의 stage 끝 시점 값. 이 raw들의 빔은 모두 장면 고정 위치(월드 y 0.05, 헤딩 0)에서 시작한다.

| 단계·출처 (n) | 빔 월드 y | 빔 헤딩 | 파지 오차(along / lateral) | 각 로봇 yaw 오차, 쌍 상대 yaw |
|---|---|---|---|---|
| grasp_lift teacher_grid (38) | 0.0492–0.0508 | ±0.05° (p95 0.03°) | ≤ 2.6 cm / ≤ 1.3 cm | ±2.5°, 쌍 ±4.8° |
| grasp_lift tolerance_boundary (244) | 0.0487–0.0506 | ±0.34° | ≤ 1.8 cm / ≤ 0.8 cm | ±2.2°, 쌍 ±0.3° |
| align e2e_checkpoint (44; 기록된 E2E 상태) | −0.02…0.05 | −4.0…0° | (파지 전이라 along 0.3 m) lateral ≤ 5 cm | r1 0.8…5.3°, r2 −3.8…4.4° |

즉 운반 진입 시 실제 빔은 y 0.05 ± 0.001 m, 헤딩 거의 0이고, 파지 오차는 ±2.6 cm 안, yaw 오차 ±2.5°다. cal(.03)·cal2(.08)·cal3(−.01) 범위가 이 분포를 포함하고 cal4(.14)·hC(.12)·hD(.10)는 실제 분포보다 훨씬 바깥의 스트레스 배치다. **작동 범위 밖 기록**: 빔 y 0.14 m(cal4)·헤딩 −0.03 rad은 문 통과 L1에서 4/4 실패, 가드 2·모션 오차 2, 16/20; hC(.12)·hD(.10)도 L0 가드 실패가 나온 것은 같은 문 여유 때문이다.

## 운반 진입 전 배치 검사 설계 메모 (opt-in, 구현 안 함; 입력 경계 준수)

목적: 진입 시점의 배치가 작동 범위를 넘으면 운반을 시작하지 않고 재정렬하게 한다. 사용하는 정보는 자기 카메라·자기 명령 이력·정적 지도뿐이다(GT 없음).
- **검사식**: 진입 시 자기 PF(위치·σ)와 계획 경로(문 중심 y = 0.05, 폭 0.5 m, 정적 지도)로 문 통과 여유를 예측한다. 여유 = 문 반폭 0.25 − (|PF y − 문 중심| + 차체 반폭 + 가드 여유 + 2σ_예측), σ_예측 = 진입 σ에 이 README의 v6g 잡음 모델(steer·L0의 누적)을 진행시킨 값. 여유 < 0이면 `PAIR_ENTRY_OUT_OF_RANGE`로 운반을 시작하지 않고 기존 재정렬/재관측(`relook`) 경로로 돌아간다.
- **입력 경계**: PF 추정과 σ, 발행 명령 이력, 정적 지도(문 위치)만 쓴다. 빔의 진짜 y를 아는 것이 아니므로 "PF y가 계획선에서 얼마나 떨어졌나"만 본다(PF y 편향이 없다는 위 결과가 전제).
- **효과 한계**: 이 검사는 가드와 같은 정보를 더 일찍 쓰는 것이라 통과율을 올리는 것이 아니라 실패를 "운반 시작 전 거절"로 옮긴다. 통과율을 올리려면 문 근처 새 정보(위 (a))가 필요하다.
- **구현 위치 후보**: `PairTeam` 제출 단계(`harness/zone_pair_executor.py`의 readiness/`pair_carry` 수락)에 opt-in 플래그로. 이번 소스에는 넣지 않았다.

## 등록 없음 (기준 미달)

번들 v81 / workflow 2.14.0 / revision v6e는 예약된 채 **사용하지 않았다**. 등록·봉인·push·PR은 하지 않았다. 재적합 1회 권한은 쓰지 않았다(원인이 재적합으로 풀리지 않는다).

## hR: 실제 운반 출발 분포에서 뽑은 held-out (측정 전 고정; 소스·적합은 `f844a373` 그대로)

앞의 hB·hC·hD는 실제 출발 분포(빔 y 0.05 ± 0.001 m, 헤딩 ≈ 0, 파지 오차 ±2.6 cm, 로봇 yaw 오차 ±2.5°)보다 훨씬 바깥이라, 실제로 일어나는 상황에서 통하는지가 본질이다. 그래서 **hR**을 한 번만 실행한다. 컨트롤러·PF·적합 파일(`carry_general_fit.json`)은 바꾸지 않는다(`git diff f844a373 -- harness scripts sim`은 stage probe 스테이징 코드 `pair_stage_probe.py`·`run_pair_stage_probes.py`와 CI 목록뿐; 컨트롤러 파일 변경 0).

- **표본(측정 전 고정).** 적합에 쓴 적 없는 기존 grasp_lift raw 두 개에서 각각 5개: `pair-stage-probes-4714263a-v6d-final-bound-e2e`(정책 `b-v6d`, E2E 사전 σ, 허용 경계 오프셋 23건 중 PASS)와 `pair-stage-probes-b534a9b5-v6c-grasp-grid`(정책 `b-v6c`, 교란 격자 35건 중 PASS). 규칙: category PASS만 case_id 정렬, 인덱스 round(i·(n−1)/4), i = 0…4 (`extract_hR_samples.py` → `hR_samples.json`). 각 표본은 파지·들기 끝 상태의 실제 빔 자세(x, y, 헤딩)와 두 로봇의 실제 베이스 자세를 그대로 쓴다(운반 시작 자세로 스테이징). 빔 y 0.0500–0.0508 m, 헤딩 ≤ 0.12°, 파지 오차 along ≤ 2.6 cm / lateral ≤ 1.2 cm, 로봇 yaw 오차 ≤ 2.2°로 실제 분포 안이다.
- **케이스.** 표본 10개 × 운반 구간 L0–L6 = 70건(`b-v6g`, seed 911, `--setup-variant hR`, `--render-profile floor_light_v1`, 각 구간의 진입 자세는 경로 변위만큼 함께 이동). L7은 `b-v6g-l7`로 별도 10건(합산하지 않음).
- **기준(이미 정한 것 그대로, 다시 적는다).** 통과율 ≥ 8/10 — 표본 10개 각각을 "표본" 단위로 보지 않고 hB·hC·hD와 같이 **케이스 통과율 ≥ 80 %(70건 중 ≥ 56건)** 로 판정하되, 구간별(L0–L6) 통과율도 함께 표로 보이고 어느 구간도 0인 채로 숨기지 않는다; leg 끝 3자유도 평균 NEES ∈ [1.5, 6]; x·y·yaw ±2σ 커버리지 ≥ 90 %(70건 × 로봇 2 = 140표본). NEES·커버리지가 기준 밖이면 통과율이 충족돼도 미통과(정직성이 전제). 가드·게이트 문턱은 바꾸지 않는다.
- **통과 시**: 작동 범위를 "실제 분포 안(빔 y 0.05 ± 0.002 m, 헤딩 ≤ 0.5°, 파지 오차 along ≤ 2.6 cm / lateral ≤ 1.3 cm, 로봇 yaw ±2.5°)"으로 명시해 v81 / 2.14.0 / v6e로 등록·봉인·push·PR(Opus 독립 검토 요청 포함). **미통과 시** 등록하지 않고 구간별·원인별 보고와 L1 가드 여유의 수치 정리.
- **구간별 표시.** 결과는 배치별이 아니라 구간별(L0–L6)로 낸다. 실패는 (a) 원인 코드, (b) 실패 시각의 PF 위치·σ, (c) 문 가장자리(y −0.20, 0.30)까지의 GT 여유와 가드 요구 여유(기본 0.02 + 잔차 0.015 + 2σ_xy + 2σ_yaw × 0.18)를 수치로 정리한다.

## hR 결과 (소스 `495c1173` = 컨트롤러·적합은 `f844a373` 그대로): **기준 미달, 등록 안 함**

**stage probe이며 E2E·제어기·학생 성공이 아니다.** raw(로컬, 원격 백업 아님): `outputs/pair-stage-probes-495c1173-ghR`(70건, `b-v6g`, cases.jsonl sha256 앞 16자 `20dfd8d50a0930e6`), `-ghRL7`(10건, `b-v6g-l7`, `4fbb454920000ef0`). `floor_light_v1`, 모델 호출 0, weld OFF, `--workers 2 --omp-threads 1 --pf-track`, driver PID 21789로 agent_lock, 시작 부하 평균 11–20(케이스별 `loadavg_case_*`). 재적합·재시도·케이스 제외 없음. 도구 `analysis/hR_analysis.py` → `analysis/hR_analysis.txt`.

### 구간별 결과 (L0–L6, 표본 10개 = 케이스 10개)

`STAGING_IK_ENVELOPE` = 표본 hR06·hR07(along 오차 −2.5…−2.6 cm)은 파지 위치가 보정된 파지 범위(14.5–18.0 cm) 밖이라 스테이징 자체가 안 됨(stage probe 규칙상 분모에서 제외). 기록된 자세 그대로는 운반 시작 자세로 놓을 수 없었다.

| 구간 | 통과 / 스테이징된 케이스 | 실패 원인 |
|---|---|---|
| L0 | 2/8 | 가드 6 |
| L1 (문 통과) | 2/8 | 가드 4, `SELF_POSE_UNCERTAIN`(yaw σ) 2 |
| L2 | 8/8 | |
| L3 | 8/8 | |
| L4 | 8/8 | |
| L5 | 8/8 | |
| L6 | 8/8 | |
| 합계 | **44/56** (전체 70건 대비 44/70) | |
| L7 `b-v6g-l7`(별도) | 8/8 (10건 중 IK 2건 제외) | |

### 사전 기준 대비

| 기준 | 결과 | 판정 |
|---|---|---|
| 통과율 ≥ 80 % (70건 중 ≥ 56건로 사전 고정) | 44/70 = 62.9 % (스테이징된 56건 기준 44/56 = 78.6 %) | **미달** (어느 분모로도) |
| leg 끝 NEES ∈ [1.5, 6] | 3.51 (중앙 2.98, 로봇 112표본) | 충족 |
| ±2σ 커버리지 x / y / yaw ≥ 90 % | 99.1 / **86.6** / 99.1 % | **y 미달** |

### 미통과의 수치 원인: 문 통과(L0 끝·L1) 가드 여유

가드 요구 여유 = 기본 0.02 + 잔차 0.015 + 2σ_xy + 2σ_yaw × 0.18 ≈ 0.129–0.148 m(σ_xy 0.040–0.047, σ_yaw 2.1–3.0°). 문은 y ∈ [−0.20, 0.30](중심 0.05, 폭 0.5). 문 가장자리까지의 여유는 차체 반폭 0.10 m를 가정해 쓴 근사값(가드 코드는 바꾸지 않음, 위 `analysis/hR_analysis.txt`의 표):

| 케이스 | 실패 시각 | GT y | PF y | GT 여유 | PF 기준 여유 | 요구 | 해석 |
|---|---|---|---|---|---|---|---|
| L0 hR02 | 23.6 s | .022 | .094 | .122 | .106 | .130 | 진짜 빠듯함(GT 여유 < 요구) |
| L0 hR03 | 24.3 | .045 | .083 | .145 | .117 | .129 | **PF 편향에 의한 오경보**(GT는 충분) |
| L0 hR04 | 24.0 | .052 | .085 | .148 | .115 | .130 | 오경보 |
| L0 hR05 | 23.9 | .086 | .017 | .114 | .117 | .132 | 진짜 빠듯함 |
| L0 hR09 | 24.3 | .043 | .083 | .143 | .117 | .129 | 오경보 |
| L0 hR10 | 24.4 | −.009 | .080 | .091 | .120 | .131 | 진짜 빠듯함 |
| L1 hR01 | 30.8 | −.015 | .024 | .085 | .124 | .140 | 진짜 빠듯함 |
| L1 hR02 | 30.7 | .047 | .069 | .147 | .131 | .145 | 오경보(GT 여유 요구보다 0.002 큼, 사실상 경계) |
| L1 hR08 | 29.9 | .042 | .090 | .142 | .110 | .140 | 오경보(경계) |
| L1 hR10 | 30.8 | −.006 | .028 | .094 | .128 | .144 | 진짜 빠듯함 |
| L1 hR03, hR04 | 31.3, 30.6 | | | | | | `SELF_POSE_UNCERTAIN`: σ_yaw 3.01°, 3.03° > 게이트 3° |

- 가드 10건 중 진짜 빠듯한 경우(실제 여유 < 요구)가 5건, PF 위치 오차에 의한 오경보(경계 포함)가 5건이다. 즉 절반은 "정직한 σ(요구 여유 약 0.13–0.15 m) ≥ 실제 문 여유(0.09–0.15 m)"라 가드가 옳게 막은 것이고, 나머지 절반은 PF y가 실제보다 4–8 cm 어긋나 가드가 잘못 막은 것이다.
- **PF y 어긋남의 원인은 실제 분포의 본질이다.** 실제 빔은 y = 0.05인데 순서 시트는 0.1 m 격자로 반올림되어 y = 0.0이다. 즉 PF 사전 y 오차가 **격자 반올림 범위(±0.05)의 끝값인 0.05**이고, 운반 중에는 위치를 고칠 관측이 없어서 그대로 남는다(사전 σ 0.03 → 1.7σ). 적합에 쓴 cal 배치의 사전 오차는 −0.03, +0.02, +0.01, −0.04라 이 끝값을 덮지 못했다. 커버리지 y 86.6 %가 그 결과다. 이것이 hB(−.04)·hC(.12)·hD(.10)보다 더 본질적인 발견이다: 실제 분포의 y가 시트 반올림의 최악값에 있다.
- L2–L6(문 통과 없음)은 스테이징된 케이스 전부 통과(40/40)했고 L0 끝·L1(문 접근·통과)만 실패한다. 문이 좁고(0.5 m) 정직한 불확실성이 크기 때문이다.

### 결론과 남은 것

- hR은 **기준 미달**이고 등록·push·PR은 하지 않았다. 재적합 권한도 쓰지 않았다(원인이 재적합만으로 풀리지 않음: 사전 y 오차 0.05는 관측이 없으면 못 고친다).
- 가능한 개선(어느 것도 이번 소스에 넣지 않음, 조정자·사용자 결정): (1) 문 접근 전에 y를 고칠 관측 넣기(문틀·표식·통과 지도 PR #271), (2) 사전 y σ를 실제 반올림 범위 ±0.05에 맞춰 넓히기(그러면 σ가 커져 가드가 더 막음), (3) 가드·게이트 문턱(사용자 결정), (4) 시트 격자 반올림 자체를 바꾸는 것은 입력 경계 밖이라 하지 않음.
- 스테이징 참고: 실제 분포 표본 중 along −2.5 cm 이상 어긋난 것(hR06·hR07)은 보정된 파지 범위 밖이라 스테이징되지 않았다. 실제 E2E에서 이런 자세가 생기면 운반 전에 파지 범위 검사(위 진입 검사 메모)가 필요하다.

## TensorBoard

- **스냅샷.** `/Users/changmin/projects/ugrp/outputs/tensorboard/0929-pair-stage-probes-v6e`, run 106개(경우별 98 + 그룹 집계 `ALL-*` 8). `collection.json` sha256 `ec6f3639cf33b470cbda4fea2501bb8b65fae61c9fd9881e2a7bcbce3ad0ae9b`. 파생 뷰 `outputs/pair-stage-probes-tbviews-0929-v6e`(빌더 `scripts/build_pair_stage_probe_views.py`, 변환기 `scripts/export_offline_audit.py`). 기존 스냅샷은 건드리지 않았다.
- **뺀 것.** 중단된 raw `ece38792-cal`(14건, `summary.json` 없음)은 README 규칙대로 뷰에서 뺐다(같은 물리의 cal-1 26건은 `a704ecc6-calB2`, `-calB`로 들어 있다). 그래서 스냅샷의 cal-1은 26건이고 위 표의 cal-1 40건과 다르다.
- **검증.** EventAccumulator로 98개 경우 run의 `offline/stage_pass`·`result/sim_s`·`result/wall_s`를 cases.jsonl과 비교해 불일치 0건, 8개 집계 값을 읽었다. TensorBoard 서버는 실행 중이 아니었고 새로 시작하지 않았다(브라우저 표시 확인은 못 했다).
- **대시보드 설정.** `outputs/tensorboard-view.json`의 `pair_stage_probes_v6e_20260929`(쓰기 직전 다시 읽고 내 키만 추가, 118개 키). 고정 카드는 v6c-carry와 같고 run filter는 `^0929-pair-stage-probes-v6(c(-carry)?|e)/`(v6c 스냅샷을 기준선으로 함께 보임). 링크는 서버를 다시 띄우면 열린다: `python3 scripts/ugrp_session.py run tensorboard-review -- .venv-sim-worker-mac/bin/python scripts/run_tensorboard.py --logdir outputs/tensorboard`.
- **이름.** `E-` = b-v6e, `ca` 운반, `sd` 내려놓기, `-Vcal` cal 배치, `-L<n>` leg, `-Lend` 목적지.
