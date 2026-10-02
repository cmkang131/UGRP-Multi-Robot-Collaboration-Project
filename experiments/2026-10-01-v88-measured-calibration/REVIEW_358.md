# PR #358 독립 검토 — MERGE AFTER FIXES

- 검토자: Codex. 검토 대상 `9b8a89c45b94264ff83708e062df04403344b7a0`.
- 비교 기준: fetch한 `origin/main` = `0bf41800272ec4c4bfa035cfc5609af8850e3e48`.
- 비교 명령: `git diff origin/main...origin/claude/calib-assembly-clock`.
- 실행일: 2026-10-03 KST. 본 리뷰 커밋은 검토 대상 뒤에 기록만 추가한다.
- 허용된 v88 raw만 읽었다. v91 held-out raw 열람·채점, 물리·렌더·모델 호출, 기존 프로세스 조작, workflow 수정은 하지 않았다. 새 물리/학습 코호트가 없는 오프라인 재현 검토이므로 TensorBoard 변환·뷰어를 시작하지 않았다. raw와 조립 산출물은 로컬 보관이며 원격 raw 백업을 뜻하지 않는다.

## 지적 한 묶음

**P2 — 50 ms 오정렬을 구분한다는 허용오차의 근거가 성립하지 않으며, 정확한 같은 시각 상태가 이미 raw에 있다.**

위치: `scripts/final_pair_calibration_io.py:20–27, 238–243`, `tests/test_final_pair_calibration_assembly.py:738–751`, `ASSEMBLY_CLOCK_FIX_20261003.md:17–18`.

`1e-4 m / 2e-3`은 실제 0.25 ms 지연을 수용하지만, 실제 **이동 명령 구간에서도** 잘못 고른 50 ms 이웃 자세를 상당수 수용한다. 예를 들어 loaded r1의 `pose[2088]`(SIM 105.6999999992285 s) 위치·회전만 `pose[2089]`(105.74999999922731 s)로 바꾸고 원래 시각·sample_index를 유지하면, 현재 `load_collection()` 전체 감사가 PASS한다. 대응 label과 잘못 가져온 자세의 차이는 위치 `9.967249728859429e-5 m`, 회전 원소 `5.1156940142132665e-6`이다. 파일을 고치지 않고 `Inputs.rows()` 반환값만 바꿔 재현했다([반례 코드](review358-evidence/reproduce_counterexample.py), [결과](review358-evidence/counterexample.json)).

새 회귀시험은 모든 x에 임의의 1 mm를 더해 거부함을 확인할 뿐, 실제 이웃 표본 선택이나 회전 허용오차를 시험하지 않는다. 실제 loaded r1/r2 이동 명령 구간의 label 대 이웃 회전 차이 최댓값도 각각 `3.5672e-4 / 3.5180e-4`로 `2e-3`보다 작다. 따라서 회전 비교만으로 이 구간의 50 ms 오류를 구분하지 못한다. 정지 시의 동일 상태는 원래 `1e-8`로도 시간 식별이 불가능하다.

**병합 전 요청:** 이 PR의 writer/번들/fit을 바꾸지 말고, 이미 저장된 동시각 `trajectory.qpos`의 robot free-joint 위치·quaternion으로 label의 chassis pose를 검증하는 엄격한 감사로 바꾼다. 세 수집에서 이 비교의 위치 오차는 정확히 0, 회전 원소 오차는 최대 `2.3315e-15`로 `1e-8`에 충분히 들어온다. pose.jsonl과의 관계도 검사하려면 아래의 0.25 ms 역산을 별도 검사한다. 실제 오정렬 반례와 회전 반례를 회귀시험에 넣고, 주석·PR 기록의 보장 범위를 바로잡는다. 정지에서 상태값만으로 시각을 증명할 수 없다는 한계는 그대로 명시해야 한다.

P0/P1은 발견하지 않았다. `sim_time` 수정 자체와 재현된 PARTIAL 결과에는 이견이 없다. 위 감사 수정 후 변경 범위를 다시 검증하면 병합 가능하며, 이 판정은 MEASURED_SIM 또는 물리 성공 승인이 아니다.

## 1. raw 스키마와 initial_hold_s

완료 기록이 있는 수집 세 개만 조립했다. 공통 접두사는 `/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001`이다.

| 프로필 | 실제 입력 경로의 접미사 | 수집 source SHA |
|---|---|---|
| unloaded | `/calibration-unloaded` | `747d2b9f1eb43e21804ccef58fff4db241d1a844` |
| fine | `-r6/calibration-fine` | 동일 |
| loaded | `-r8/calibration-loaded` | 동일 |

각 case는 `zone_wide_two_doors_final_v3`이다. 아래 writer와 그 의존 경로 10개는 **수집 SHA와 검토 HEAD에서 바이트 동일**하다. 현재 writer를 옛 raw에 잘못 투영하지 않았다. 실제 키 집합은 [raw_audit.json](review358-evidence/raw_audit.json)의 `collections.*.schema`, writer 동등성은 `writer_matches_acquisition_source`에 보존했다.

| 읽는 raw 파일/필드 | 실제 writer와 대조 |
|---|---|
| 수집 `plan.json`: `execution_bundle_id, check, cases, denominator, runnable, source_sha, bundles_sha256` | `scripts/run_final_pair_v3.py:149–165,187`의 plan 그대로 |
| 수집 `result.json`: `status, source_unchanged, denominator, unattempted, cases` | 같은 실행기 `196–200` |
| case `result.json`: `protocol_complete, status, collection_data_status, check, check_sim_s, case.map_id` 및 case 전체 | 같은 실행기 `54–59,102,122–128`; 수집 result의 cases[0]과 전체 동일성도 검사 |
| `bundle.json`: `execution_bundle_id, check, map_id, measurement, robot_model, render_profile, contact_profile, weld, sensors, source_sha, case, map_sha256, calibration_contract` | `harness/zone_final_pair_contract.py:186–220` + 실행기 `149–150,46`; measurement는 `design()` 전체와 비교 |
| measurement: `motion_start_s, segments[].{axis,duration_s,value,phase}, control_period_s, eval_pose_period_s, check, map_id` | `harness/zone_final_pair_excitation.py:29–51`; `initial_hold_s`만 없으며 명시적 fallback 사용 |
| `inputs/static_map.json`: 지도 전체를 digest/동결 contract와 비교 | `sim/final_environment_checks.py:71`; 개별 실시간 GT 키 추측 없음 |
| `inputs/schedule.json`: `t, robot_id, action`, action의 `kind, forward, left, turn, duration_s, servo_id, pulse, pan_pulse`(kind별), 전체 이벤트 배열 | 실행기 `51–52`; `schedule()`과 전체 동일성 검사 |
| `artifacts.sha256.json`: 상대 파일명 → SHA256 문자열 | 실행기 `127–128`; artifact의 경로 집합·바이트 해시 검사 |
| `commands.jsonl`: `t, kind`; 초기 `pulses`, arm `servo_id,pulse`, look `pan_pulse`, mecanum `forward,left,turn,duration_s` | `sim/final_environment_checks.py:63–67,90–98`; hold는 `sim/final_pair_v3.py:78–84` |
| `frames.jsonl`: 소비하는 키는 `sim_time, frame_id, sha256, path, commanded_servo` | `sim/camera_robot_port.py:100–118`의 obs에서 image 제외 + `sim/final_pair_v3.py:173–174`의 두 키. 실제 추가 키는 `robot_id,camera,actuator_state`; 시간 `t`는 없음 |
| `camera_labels.jsonl`: `t, frame_id, sha256, requested_check, commanded_servo, base_position_m, base_rotation, frame, origin_m, rotation, chassis_to_floor.{origin_m,rotation}` | `sim/final_pair_v3.py:175–186` + `harness/zone_final_pair_camera.py:48–64`의 `measurement_label()` |
| `pose.jsonl`: `t, sample_index, base_position_m, base_rotation, requested_check` | `sim/final_pair_v3.py:199–209`; 위치 3, 회전 3×3 |
| `trajectory.jsonl`: 소비하는 키는 `t, beam_xyz_m, beam_rotation` | 같은 파일 `194–198`; beam_rotation은 평평한 9개이며 reader가 3×3으로 reshape. qpos/qvel도 실제 저장되지만 기존 assembler 감사에서는 미사용 |
| `contacts.jsonl`: `t, active_weld_ids, contacts[].{geom1,geom2,dist_m}` | `sim/final_environment_checks.py:136–143` |
| `scene.xml`: `body[name=cargo_beam]`, geom의 `name,type,size,pos,contype`, 회전 표현 attribute 부재 | reset이 실제 `world.scene_xml`을 저장(`sim/final_environment_checks.py:69`); XML 속성 기본값 fallback은 JSON 키 오류가 아님 |
| JPEG·그 밖의 artifact/수집 보조 파일 | 원본 바이트·파일 집합·SHA만 검사; JSON schema를 읽는 경로가 아님 |

프레임의 `t`만 있는 행은 거부된다. `sim_time`만 시간으로 소비하며 다른 raw의 `t`와 구분한다. 다만 임의의 여분 `t` 키가 함께 존재하는 것까지 금지하는 strict key-set validator는 아니다. 필수 `sim_time` 없는 과거 형식을 받지 않는다는 의미로만 확인했다. 서보 키는 실제 `1,3,4,5,6`, frame_id는 정수이며, fixture의 제거/수정과 일치한다. 카메라 fit/edge 시간 창의 소비 키도 모두 `sim_time`으로 고쳤다.

`initial_hold_s`는 PR에서 새로 교체한 필드가 아니다. 기존 `scripts/final_pair_calibration_io.py:114`와 동결 B의 `scripts/validate_consumer_criterion_b.py:44` 모두 `get('initial_hold_s', get('motion_start_s', 0.))`를 사용한다. 실제 값은 unloaded/fine 74 s, loaded 12 s(각 1480/240번째 50 ms tick). 각 실제 measurement에 같은 값의 `initial_hold_s`를 가상으로 추가한 경우와 현재 fallback의 명령 배열·step/PRBS 구간·required tick 집합이 모두 정확히 일치했다. 따라서 이 세 raw에서 영향 없음이 확인된다. 두 키가 서로 다른 값으로 동시에 주어질 때도 무조건 같다는 주장은 아니다.

## 2. 정확한 writer 시점과 지연의 설명

1. `scripts/run_final_pair_v3.py:78–99`는 매 50 ms tick에 먼저 `eval_sample()`, 매 네 tick에 `capture()`, 그 뒤 해당 tick의 명령 발행과 다음 tick까지의 advance를 한다.
2. v88 advance(`sim/final_pair_v3.py:147–159`)는 `_physics_step_for()`를 호출한다. 그 내부 `sim/multi_masterpi_production.py:1492`가 `mj_step()` 한 번을 실행하며 이후 kinematics를 refresh하지 않는다. 실제 XML과 applied 기록은 세 수집 모두 `implicitfast`, `dt=0.00025 s`이다. 50 ms당 200 substep, frame 간격 200 ms당 800 substep이다.
3. tick의 마지막 `mj_step` 후 time/qpos/qvel은 `t_i`까지 적분돼 있지만 body.xpos/xmat는 마지막 적분 **직전** `t_i−0.00025`의 값이다. pose/beam/contact는 이때 기록한다(`sim/final_pair_v3.py:191–209`, base eval_sample). 따라서 같은 trajectory 행 안에서도 qpos/qvel은 적분 후이고 beam 파생 자세는 적분 전이다.
4. r1 capture → `CameraRobotPort.capture()` → `render_jpeg/render_rgb` → `_render_rgb_direct()`(`sim/multi_masterpi_production.py:840–849`) → `_sync_real_camera_mount()`(`sim/masterpi_dynamics_v2.py:964–968`)에서 **명시적으로 `mj_forward`**를 호출한다. `renderer.update_scene`가 저절로 시간 전진을 시킨 것이 아니다. 이때 현 qpos로 body/camera 자세를 재계산하고, 이후 label을 저장한다. r2도 같은 t_i에서 forward/촬영/label을 반복한다. 사이에 `mj_step`은 없다.

MuJoCo의 forward/적분 분리는 [공식 simulation 설명](https://mujoco.readthedocs.io/en/stable/programming/simulation.html)과도 일치한다. 이 리뷰의 수치 결론은 라이브 엔진 실행 없이 아래 저장 배열의 직접 계산으로 검증했다.

free-joint 주소는 raw XML의 worldbody joint 순서/종류에서 계산했다(두 로봇 qpos 시작 0/17, qvel 시작 0/16). 위치는 `qpos_xyz − dt*qvel_xyz`, 회전은 `R(qpos_quat) @ Exp(−dt*qvel_local_angular)`로 직전 substep을 복원했다. **전체 44,400개 t>t0 pose**에서 실제 pose와의 최대 오차는 위치 `1.1102230246251565e-16 m`, 회전 원소 `2.4424906541753444e-15`다. 초기 reset tick은 별도 집계했으며 최대 회전 오차 `1.1599e-13` 이하이다. **11,106개 label**과 동시각 trajectory.qpos 비교는 위치 0, 회전 최대 `2.3314683517128287e-15`다. 즉 관측된 최대 차이는 한 substep의 시간 차이로 전부 설명된다.

| 수집·로봇 | label 대 같은 timestamp pose의 최대 위치 차이(m) | 최대 회전 원소 차이 |
|---|---:|---:|
| unloaded r1 | 9.85872e-6 | 1.10736e-5 |
| unloaded r2 | 8.10463e-15 | 1.86010e-13 |
| fine r1 | 9.07301e-6 | 1.10736e-5 |
| fine r2 | 8.10463e-15 | 1.86010e-13 |
| loaded r1 | 2.97221e-5 | 6.86451e-4 |
| loaded r2 | 4.67540e-5 | 4.02158e-4 |

**맞는 sample로 바꾸는 방법:** `pose[4*j±1]`는 50 ms 떨어져 있으므로 맞는 대체 sample이 아니다. 기존 raw에서는 `trajectory[4*j].qpos`가 label과 동일한 instant다. 새 수집의 writer를 손볼 때는 공통 snapshot/refresh 후 eval·capture를 기록하고 단계/시각을 명시하는 것이 명료하지만, refresh의 동역학 부수 효과까지 검토할 별도 변경·새 실행 버전이다. 기존 v88 writer/번들을 이 PR에서 바꾸거나 기존 fit용 pose를 몰래 바꿀 필요는 없다.

## 3. 이웃 50 ms 표본: 최소 차이와 감사의 실제 한계

수치는 원 코드 `allclose(rtol=0)`와 같은 **성분별 절댓값 최대**이다. 위치는 Euclidean norm이 아니며 회전은 rad/degree가 아니라 3×3 행렬 원소 차이다. 각 label j와 유효한 pose[4*j−1], pose[4*j+1] 양방향을 비교했다. 각 열의 최솟값은 서로 다른 pair에서 나올 수 있고, 마지막 열은 두 허용오차를 **동시에** 만족한 pair 수다.

구간 정의: 이동 명령은 해당 이웃까지의 50 ms interval에서 자신의 mecanum 명령이 nonzero인 경우이다(명령이 실제 움직임을 보장하지 않음). 정지 명령은 그 interval과 앞선 1초 동안 자기 drive 명령이 0인 경우이다. arm 동작/차체 흔들림은 있을 수 있다. 정지 명령 직후 1초 coast는 별도 집계해 JSON에 보존했다.

| 구간 | 수집·로봇 | 최소 위치 차이(m) | 최소 회전 원소 차이 | 잘못된 이웃도 허용되는 수/전체 |
|---|---|---:|---:|---:|
| 이동 명령 | unloaded r1 | 1.59960e-9 | 7.71030e-11 | 821/2265 |
| 이동 명령 | fine r1 | 2.81691e-10 | 5.22164e-11 | 1218/2265 |
| 이동 명령 | loaded r1 | 6.05560e-8 | 5.77792e-8 | 1250/2865 |
| 이동 명령 | loaded r2 | 1.17043e-7 | 9.87019e-8 | 1251/2865 |
| 정지 명령 ≥1 s | unloaded r1 | 0 | 5.42101e-20 | 1152/1225 |
| 정지 명령 ≥1 s | unloaded r2 | 0 | 3.61772e-17 | 3700/3700 |
| 정지 명령 ≥1 s | fine r1 | 0 | 1.01373e-17 | 1150/1225 |
| 정지 명령 ≥1 s | fine r2 | 0 | 3.61772e-17 | 3700/3700 |
| 정지 명령 ≥1 s | loaded r1 | 0 | 5.03341e-17 | 503/565 |
| 정지 명령 ≥1 s | loaded r2 | 0 | 8.13152e-20 | 503/565 |

unloaded/fine r2에는 이동 명령이 없다. 순수한 pose[i] 대 pose[i+1] 전체 50 ms 간격도 따로 계산했다(`pose_neighbours`). 이동 명령 최소 위치/회전은 unloaded r1 `1.59970e-9 / 3.14869e-11`, fine r1 `2.81748e-10 / 4.95802e-11`, loaded r1 `6.14218e-8 / 5.76727e-8`, loaded r2 `1.06481e-7 / 9.87408e-8`이다. 모든 수집의 정지 구간 최소 위치 차이는 0이다.

이 허용오차가 실제로 막는 것은 **0.1 mm 초과 좌표 오차 또는 0.002 초과 행렬 원소 오차라는 큰 상태 불일치**다. 세 수집 모두 빠른 병진 구간에는 이를 넘는 이웃 pair가 있으므로, 전체 시퀀스를 일괄 ±1 표본 밀면 일부 행에서 거부된다. 그러나 각 행/저속·회전/정지 구간의 올바른 시간 대응을 보장하지 않는다. 정지에서 인접 상태가 거의 같다는 이유로 더 작은 임의 tolerance만 선택하는 것도 해결책이 아니다. 시간/순서/ID/hash 검사와 같은 instant의 qpos 교차검사를 함께 유지해야 한다.

## 4. fit·동결 파일·번들 불변

전체 base→head 변경은 문서 1개, IO, camera reader, 관련 시험의 **4파일뿐**이다. `scripts/final_pair_calibration_camera.py`를 바이트 비교하면 `['sim_time']`을 원래 `['t']`로 되돌리는 치환만으로 base와 정확히 일치한다. 즉 모듈 파일 전체가 바이트 동일하다는 뜻은 아니지만 fit 수식·선별 규칙·숫자 임계값은 그대로다.

`LABEL_POSE_ATOL_M / LABEL_ROTATION_ATOL`의 소비처는 `load_collection()`의 두 입력 감사 비교뿐이다. fit/score/criterion으로 전달하거나 값을 보정하지 않는다. 수집의 수용 여부가 달라져 downstream fit 실행 여부가 달라지는 영향은 있으므로 “출력에 아무 영향 없음”은 아니다.

- B SHA256: `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`.
- B′ SHA256: `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`.
- candidate r4 SHA256: `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071`.
- 위 3파일, r4 report, assembler 본체, motion fit, r4/unloaded fit 및 B validator, bundle registry, v88 contract/excitation/calibration, simulation workflows, calibration contract를 `git show origin/main:<path>` 바이트와 직접 비교해 모두 일치했다. 파일별 SHA는 `raw_audit.json.byte_comparisons`에 있다. `.github/workflows`도 base와 차이 없다.

## 5. 테스트와 실제 조립 재현

검토 worktree를 clean HEAD `9b8a89c4`로 놓고 기존 Python 환경을 사용했다. 테스트/실제 조립은 리뷰 문서를 쓰기 전에 실행했다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_final_pair_calibration_assembly.py tests/test_review_355.py \
  --junitxml=<review-evidence>/tests.xml
```

**406 passed**(367 + 39), exit 0, 453.20 s. 시간은 테스트 도구 출력일 뿐 성능 benchmark가 아니다. [원본 출력](review358-evidence/tests.txt), [JUnit](review358-evidence/tests.xml).

세 완료 수집을 가리키는 임시 symlink root를 만들었고 raw는 수정하지 않았다. 정확한 실행 argv와 exit code는 [assembly_command.json](review358-evidence/assembly_command.json)에 있다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.assemble_final_pair_calibration \
  --raw-root /var/folders/s9/blmccn613zx6k7fdfcczknrm0000gn/T/review358-_auhn_wu/raw \
  --output /Users/changmin/projects/ugrp/outputs/final-pair-v88-measured-review358-20261003-035937
```

**실제 조립 1회: exit 2, PARTIAL, 누락 42개, collection_audit 3/3 PASS**. input_manifest는 실행 SHA `9b8a89c4…`, `working_tree_dirty=false`, `raw_unchanged=true`, Python 3.12.13 / NumPy 2.5.2, 입력·소스 11,360개 파일을 기록했다. writer raw는 50 ms pose 7,401개/robot와 200 ms frame/label 각 1,851개/robot이다.

| 누락 사유 | 필드 수 | 재현 |
|---|---:|---|
| 동결 B의 unloaded forward/left/rotate 판정 null, 완전 3축/scalar-stop 프로필 미승인 | 10 | PR와 동일 |
| loaded `fit convergence/rank/boundary failure: rank 13/13` | 16 | 동일 |
| pair model `measurement not available` | 5 | 동일; loaded mean 예외 후 continue로 pair 단계 미실행 |
| loaded pan의 동일 arm 기준 양부호 정지 표본 부족 | 1 | 동일 |
| loaded camera `1269,2052,2494,1500`: 안정·상승·양손 접촉 표본 없음 | 5 | 동일 |
| loaded camera `807,1897,2187,1500`: residual/count gate 거부 | 5 | 동일 |
| 합계 | **42** | 큰 분류 **10 + 16 + 5 + 11** 동일 |

loaded selection도 lifted **6839**, not_lifted **553**, missing_bilateral_grip **9**로 동일하다. 누락 필드의 전체 이름·이유는 새 `calibration.json`에 있으며, 집계는 `raw_audit.json.assembly`에 보존했다. 이번 기본 assembler 출력은 loaded 최적화 오류 문자열만 보존하므로 PR 기록의 “13개 중 정확히 5개 boundary” 내부 세부값이나 별도의 `pair_rows` 54개 진단을 새로 검증했다고 주장하지 않는다. 요청된 42필드/사유 그룹 재현에는 이 둘이 필요하지 않다.

| 새 산출물 | SHA256 |
|---|---|
| calibration.json | `849371b718f89c9119b152163cf2ea12ceaf69d69f8b07ebab3e0214351c9b58` |
| fit_report.json | `121b870fa52c7357fdfa946aa0f5999c8c209c3cee5830406888fc50685d03b7` |
| input_manifest.json | `ff914a3aab07477002d1b10bf52e2d18312908321b51216dc17d4ee555725364` |

추가 순수 배열 감사는 [reproduce_raw_audit.py](review358-evidence/reproduce_raw_audit.py)로 재현한다. `--repo <검토 checkout> --raw-root <위 세 symlink의 새 root> --output <새 JSON>`을 받으며 NumPy/SciPy quaternion 연산만 한다. raw 입력은 읽기 전용이다. PR의 0.25 ms 지연 설명은 수치적으로 확인됐지만, 이웃 표본 거부 보장은 성립하지 않으므로 엄격한 동시각 감사와 실제 반례 회귀 후 재검토한다.
