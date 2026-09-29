# 공동 운반 b-v6e: 운반(단계 4) + 내려놓기(단계 5) 통합 후보 — 코드·사전 등록 (2026-09-29, Claude)

**이 문서는 실행 전 준비 기록이다. 물리 시뮬레이션·stage probe·모델 호출을 한 번도 돌리지 않았다.** 아래의 모든 "결과" 칸은 **미측정**이다.
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

## 결과

**모두 미측정.**

| 코호트 | 정책 | staged 통과 | 기준선 | 비고 |
|---|---|---|---|---|
| 보정 cal (NEES/커버리지) | b-v6e | 미측정 | – | 정직성 판정 미측정 |
| 운반 33셀 L0 (13셀) | b-v6d / -dr / -lag / b-v6e | 미측정 | b-v6c 0/13 | |
| 운반 33셀 L1·L3·L6·L7 (20셀) | 같음 | 미측정 | b-v6c 각 0/5 | |
| 운반 held-out hA·hB·hC | b-v6c / b-v6e | 미측정 | – | |
| 내려놓기 목적지 13셀 | b-v6c / b-v6f-a / b-v6f-b / b-v6e | 미측정 | b-v6c 0/13 | |
| 내려놓기 픽업 위치 | b-v6c / b-v6e | 미측정 | b-v6c 3/3 | |
| 내려놓기 held-out | b-v6c / b-v6e | 미측정 | – | |

raw 위치·sha256·wall·부하: 미측정.
