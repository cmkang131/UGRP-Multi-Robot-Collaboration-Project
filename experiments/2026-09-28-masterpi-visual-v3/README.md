# 2026-09-28 MasterPi 모델 v3 (공식 치수도 + SDK 팔, 물리 포함)

- 작업: Claude, 브랜치 `claude/masterpi-visual-v3`, 기준 `origin/main` `d5bd208e`(#240 병합 포함)
- 성격: 모델 버전 추가. 실험 결과가 아니고 성공률도 없다. 물리 step 0회, 시뮬레이션 실행 0회, 모델 호출 0회다. 정지 자세는 `mj_forward`로만 계산했다.
- 1단계(외관 v3)에 이어 2단계에서 사용자 결정(치수도를 물리까지 채택, 다음은 sim2real)에 따라 `build_v3_xml`을 물리 모델로 바꿨다.
- 파일:
  - `sim/masterpi_geometry_v3.py`: 치수, 출처 등급, 실측 목록, 물리 파라미터 한 벌 `PHYSICAL_V3`, 제어기와의 차이 표 `CONTROLLER_VS_PHYSICAL_V3`
  - `sim/masterpi_model_v3.py`(구 `masterpi_visual_v3.py`): `build_v3_xml(hardware, geometry=PHYSICAL_V3)`, 진단용 `build_v2_appearance_xml`
  - `scripts/render_masterpi_model_v3.py`, `tests/test_masterpi_model_v3.py`
  - `switch_wip.patch`: 연구 장면 기본 모델 전환과 제어기 장착 보정의 미완성 패치(아래 할 일)
- v2는 바이트 그대로다. `sim/masterpi_dynamics_v2.py`, `sim/masterpi_geometry.py`, `sim/masterpi_scene*.xml`을 고치지 않았다.

## 할 일 (배터리 부족으로 중단, 이어서 할 순서)

이 커밋까지는 테스트가 통과한다. v3 모델은 완성했고, 연구 장면 전환은 아직 하지 않았다.

1. `git apply experiments/2026-09-28-masterpi-visual-v3/switch_wip.patch`. 내용은 다음과 같다.
   - `sim/multi_masterpi_production.py`: `robot_model`(기본 `masterpi_v3`), 보정되지 않은 wheelbase/track은 치수도 값으로 바꾼다. 상태에 `robot_model`과 `robot_geometry_version`을 넣는다.
   - `harness/visual_arm.py`: `CONTROLLER_GEOMETRY_ID`, `ARM_MOUNT_X_CM = 4.82`, `arm_tool_pose`, `arm_frame_xy`, `chassis_x_for_arm_radius`. `tool_pose`/카메라 외부 파라미터는 차대 좌표로 낸다(장착 위치 더함). `solve_grip_site_ik`는 장착 위치를 빼고 팔 좌표에서 반경·yaw·보정 범위를 검사한다. SDK 링크 상수는 그대로다.
   - 팔 좌표 기준 상수: `sim/zone_cargo.py` `GRASP_RADIUS_M = .155 + 장착`(카탈로그 기록에 `arm_radius_m` 추가), `scripts/zone_teacher.py`, `harness/owncam_pair_beam.py`, `harness/wrist_zone_skill_v7.py`
   - 파지 범위 게이트를 팔 좌표로 바꾼다: `harness/visual_box_skill.py`, `harness/wrist_zone_skill_v2.py`
   - 스윕 가드(`harness/zone_own_guards.py`, `harness/owncam_sweep_collision.py`, `harness/zone_pair_geometry.py`): `arm_tool_pose`를 쓰고 `BODY_MOUNT_XYZ_M`를 v3 장착 위치로 바꾼다. v2 보정 기록은 `V2_BODY_MOUNT_XYZ_M`로 따로 둔다.
2. 패치를 적용하면 영향 테스트 109개 파일에서 기준(main) 대비 새 실패가 134개 생긴다(`mj_step` 가드 아래에서 측정). 주요 원인은 다음과 같다.
   - 47개: 팔 반경을 차대 x로 넘기는 호출(`solve_grip_ik(.155, 0, ...)` 등)이 보정 범위 밖으로 판정된다. 호출부를 `chassis_x_for_arm_radius`로 바꾸거나 테스트 고정값을 갱신한다.
   - 11개 `test_zone_start_dock.py`, 8개 `test_zone_pair_dev.py`: 장면 설정 해시가 바뀐다. 새 번들 ID로 다시 등록해야 한다.
   - 나머지: v2 기하로 고정된 회귀값(가드 여유, 인식 범위, 도킹 판정 등). 값을 새로 맞추지 말고 "v3에서 전원 연결 후 재검증"으로 분리한다.
3. 번들: 등록 직전에 main과 열린 PR 전체에서 최댓값을 다시 확인한다. 2026-09-28 확인값은 main RGB v63, zone study v69, #246 v68이다. `rgb-standard-dispatch-v70-masterpi-v3`(부모 v63), `zone-study-integration-v71-masterpi-v3`(v69 은퇴)를 쓴다. `configs/simulation_workflows.json`, `docs/execution_versioning.md`, 관련 테스트(`test_rgb_execution_bundle`, `test_zone_study_source_pinning`, `test_zone_study_review_r10`, `test_zone_pilot_settlement`)도 함께 갱신한다. #246과 #248에 코멘트로 알린다.
4. 다중 로봇 자기충돌 감사(`mj_forward`): 다중 로봇 장면에서는 로봇 geom끼리 충돌한다(conaffinity |= 2). `CARRY_POSE`, `SEARCH_POSE`, 파지 자세에서 v2와 v3의 자기 접촉 수를 비교한다. nav_cam(0.32 m, 25° 아래) 시야에 팔이 들어오는 비율도 비교한다.
5. 비교 렌더를 다시 만든다(`scripts/render_masterpi_model_v3.py`, 출력 `outputs/masterpi-model-v3`).

## SDK와 치수도 판정 (레퍼런스 우선)

| 항목 | 치수도 | 공식 렌더(185 mm 기준 축척) | SDK | v3 물리값 | 판정 |
|---|---|---|---|---|---|
| 상완(ID5→ID4) | 57.7 | 63.5 | 65.0 | **65.0** | SDK. 렌더가 뒷받침한다. 치수도의 상완 구간만 벗어난다(인쇄된 215/343 mm에도 같은 오차가 있다). |
| 전완(ID4→ID3) | 62.4 | 62.6 | 62.0 | **62.0** | 세 자료가 1 % 안에서 일치한다. |
| 손목→닫힌 끝 | 94.0 | 95.0 | 100.0 | **94.0** | 치수도. SDK l4 = 10.00 cm는 IK 목표 상수다. |
| 손가락 접촉 중심 | 94.0 − 14.3/2 | | | **86.85** | 패드 길이 14.3 mm(치수도) |
| 어깨 축 높이 | 127.7 | 127.0 | 3.25 + 9.30 = 125.5 | **127.7** | 치수도 |
| yaw 축 전방 | 48.2 | 48.8 | (팔 좌표) | **48.2** | 치수도 |
| 바퀴 트랙 / 축간 / 폭 | 129.9 / 118.8 / 30 | | | **같음** | 치수도(v2는 131 / 120 / 31) |
| 초음파 전방 / 높이 | 88.0 / 61.7 | | | **같음** | 치수도 |

(단위 mm.) 실제 로봇은 SDK IK를 쓴다. 시뮬레이터는 물리 팔을 모델링하고, SDK 상수는 제어기 층(`harness/visual_arm.py`)에 따로 둔다. 차이는 `CONTROLLER_VS_PHYSICAL_V3`에 남긴다. 근거: Hiwonder MasterPi SDK `ArmIK`(l1 = 8.00 + 1.30, l2 6.50, l3 6.20, l4 10.00 cm), 공식 문서 렌더 `1.getting_ready/1.6/image4.png`, 제품 치수도. 링크 길이는 `PHYSICAL_V3.with_measurements(...)`로 줄자 실측값으로 바꿀 수 있다.

유지한 우리 보정값: robot_cam 자세·FOV 적합(렌즈 67 mm 전방, 13.6 mm 위, 집게 기준)과 `sim/masterpi_dynamics_calibration.json` 적용 경로를 다시 맞추지 않았다.

## 전원 연결 후 검증 계획

v2 기하에서 적합한 값은 v3에서 모두 다시 확인한다. 명령은 모두 `OMP_NUM_THREADS=2`로 worktree에서 실행한다.

```bash
# 1) v2 기하 테스트(물리 step 사용, v2 파일은 바뀌지 않았으므로 그대로 통과해야 함)
.venv-sim/bin/python -m pytest -q tests/test_masterpi_physical_geometry.py tests/test_masterpi_visual_geometry.py
# 2) v3 모델 테스트 + v3 기하 테스트(물리 step 사용분은 전원 연결 후 추가)
.venv-sim/bin/python -m pytest -q tests/test_masterpi_model_v3.py
# 3) 전환 패치 적용 뒤 영향 테스트 전체(기준 main과 실패 목록 비교)
.venv-sim/bin/python scripts/run_ci_tests.py
```

재검증 목록:

- 주행: 새 트랙·축간 거리에서 전진·측면·회전 이득, 정지 감쇠(`sim/masterpi_dynamics_calibration.json`은 모두 null이고 v2 기본값을 쓴다)
- 파지: SDK 도구점 100 mm와 물리 패드 중심 86.85 mm의 차이(수직 파지 때 패드가 목표보다 13 mm 위), 24 mm 파지 높이, 30 mm 큐브 파지 성공
- 공동 운반: 팔 장착 48.2 mm 전방 이동에 따른 스테이션 자세, 빔 파지, 운반 중 자세
- 카메라: robot_cam 적합은 집게 기준이라 유지된다. 어깨 높이 2.2 mm 차이가 거리 추정에 미치는 영향, 실물 재적합
- 대기·접근 거리와 인식 범위: `harness/wrist_zone_skill_v6.py` `APPROACH_GRASP_STANDOFF_M`, `harness/zone_own_executor.py` `SLOT_STANDOFF_M`, `harness/zone_own_perception_v2.py` `HANDLE_REACH_BAND_M`, `sim/multi_masterpi_production.py` `TEAM_APPROACH_STANDOFF_M`, 팬 목표 방위(차대 기준인지 팔 기준인지)
- 스윕 가드 구 모델 반경과 잔차(v2 몸체로 보정됨)
- 차대 COM(질량·관성은 v2 그대로), 렌더 비용(시각 geom 증가)

## 초음파 장착 (PR #248에 전달)

`SONAR_MOUNT_V3`(robot body 기준, 원점은 차축 중앙이고 z는 차축 높이):
- 송수신면 중심: x = **0.0880 m**, y = 0, z = 0.0617 − 0.0325 = **0.0292 m**. 바닥 기준 높이는 **61.7 mm**다.
- 축은 +x(수평, pitch 0°). 두 송수신기 간격은 26.7 mm, 지름은 16 mm다.
- 사이트 이름은 `v3_ultrasonic_site`(zaxis = 전방).
- v2 대비: 높이 +7.7 mm, 앞 +4.0 mm(면 기준; v2 cylinder 중심은 78 mm, 면은 84 mm), 간격 −7.3 mm.
- 등급: public_measured(공식 치수도를 인쇄된 치수로 축척). 실측이 아니다. 축척 오차는 ±1 %(±1–2 mm)다.

## 출처 표

| ID | 자료 | URL | 라이선스 | 쓴 것 |
|---|---|---|---|---|
| S1 | Hiwonder MasterPi 제품 페이지, 사양표와 "Dimensional Diagram" | https://www.hiwonder.com/products/masterpi · 치수도 https://cdn.shopify.com/s/files/1/0084/2799/5187/files/masterpi_01173667-020d-4baa-8ec8-6ff4a45b6220.jpg?v=1716200111 | 저작권 Hiwonder, 재배포 허가 없음. 수치만 인용했고 이미지는 커밋하지 않았다 | 185×162×343 mm, 1.1 kg, 4DOF+집게, LD-1501MG·LFD-01M. 치수도 라벨 65/30/101/215 mm와 모든 public_measured 값(축척 2.357 px/mm) |
| S2 | 같은 페이지의 서보·카메라 사양 이미지 | 위 페이지(LD-1501MG `1501.jpg`, LFD-01M `LFD-01M.jpg`, HD 카메라 `7e29db14...jpg`) | 위와 같음 | LD-1501MG 40×20×40.5(귀 포함 54.4), LFD-01M 32.5×12×29.85, HBVCAM-V2101 30×25×25 mm |
| S3 | MasterPi 공식 문서 1장(구성품·조립 1–6단계) | https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html | 문서에 "Copyright … Shenzhen Hiwonder … no reproduction" 명시. 링크와 관찰 결과만 기록했다 | 팔 받침 상자에 초음파가 달린 조립 상태, 역U 차체, 배터리 케이스 위치(차체 안), Pi 방향(포트 뒤쪽), 덮개와 기둥 |
| S4 | Hiwonder 발광 초음파 모듈 제품 페이지와 치수도 | https://www.hiwonder.com/products/glowing-ultrasonic-sensor · 치수도 `02_8838c641-...jpg` | 저작권 Hiwonder | 모듈 45.6×28.5 mm, 측정각 15°(반각인지 전체각인지는 적혀 있지 않음), 2–400 cm, 40 kHz, I2C 0x77. 송수신기 간격 26.7 mm는 치수도 축척값 |
| S5 | Hiwonder MasterPi SDK `ArmIK/InverseKinematics.py`(공개 재배포본) | https://github.com/SquirrelRobotics/MasterPi/blob/98b85647eab1614f3fcce28aba959c679cfc72eb/ArmIK/InverseKinematics.py | 저장소에 라이선스 없음. 코드는 재사용하지 않고 상수만 대조했다 | l2 = 6.50, l3 = 6.20, l4 = 10.00 cm(= `harness/real_geometry.py`) |
| S6 | 저장소 기존 값 | `sim/masterpi_camera_profile.py`, `harness/real_geometry.py` | 저장소 | robot_cam 자세(REAL 적합)와 링크 길이는 그대로 뒀다 |

조사했지만 쓸 수 없었던 것:
- MasterPi 공식·공개 URDF, STEP, STL은 찾지 못했다. GitHub `gh search`(masterpi/urdf/stl/xacro, hiwonder urdf)에서 결과가 없었다. GrabCAD도 확인하지 못했다.
- 그래서 메시 자산 재사용은 0이다. 모든 형상은 MuJoCo 기본 도형과, 코드가 만드는 볼록 프리즘 메시로 만들었다.

## 값별 출처 등급

전체 목록은 `sim/masterpi_geometry_v3.py`의 `SOURCES`에 있다(이름 → 값, 등급, 근거). 등급은 다음 다섯 가지다.
- official: 인쇄된 수치
- public_measured: 공식 치수도를 그 도면의 인쇄 치수로 축척한 값
- photo_estimate: 공식 사진이나 렌더에서 눈으로 읽은 값
- controller: SDK나 제어기 값
- real_fit: ugrp1 REAL 적합값

주요 값:

| 값 | v3 | 등급 |
|---|---|---|
| 초음파 면 x / 중심 높이 / 간격 | 88.0 / 61.7 / 26.7 mm | public_measured |
| 초음파 모듈 크기, 측정각 | 45.6×28.5 mm, 15° | official |
| yaw 축 x | 48.2 mm | public_measured |
| 어깨 축 높이 | 127.7 mm(v2 물리 125.5는 유지) | public_measured |
| 상완 / 전완 / 손목→집게 끝 | 57.7 / 62.4 / 94.0 mm(물리는 SDK 65 / 62 / 100 유지) | public_measured vs controller |
| 덮개 윗면 | 101 mm | official |
| 차체 높이 범위 / 전장 | 16.8–50.0 / 185 mm | public_measured |
| 바퀴 지름 / 폭 | 65 / 30 mm(v2 물리 폭 31 유지) | official |
| 윤거 / 축거 | 129.9 / 118.8 mm(v2 131 / 120 유지) | public_measured |
| 롤러 수, 모따기, 색 | 9, 10 mm, RGBA | photo_estimate |
| robot_cam 자세 | 바꾸지 않음(67 mm 앞, 13.6 mm 위, −7.95°) | real_fit |

## 물리 쪽 제안 (1단계 기록, 2단계에서 `build_v3_xml`에 적용)

1. **팔 yaw 축을 +48.2 mm 앞으로 옮긴다.**
   - 근거: 치수도 옆면에서 yaw 혼 767.75 px와 어깨 허브 765 px가 차축 중앙 880 px에서 떨어진 거리.
   - v2에서는 팔 받침이 전자부 덮개와 같은 자리에 있다. 그래서 `appearance_only` 렌더에서 팔이 덮개 앞끝과 겹친다.
   - 이 이동은 다음에 영향을 준다: 몸체 기준 도달 거리, 짝 정렬, 초음파와 집게의 상대 위치, 카메라의 세계 자세.
2. **차체와 덮개 충돌 proxy를 치수도에 맞춘다.**
   - 하부: 116 → 181 mm 길이, 높이 17–47 → 16.8–50 mm.
   - 앞판: x 60 → 91 mm.
   - 덮개: x −60…+4 → −85.6…+3.5 mm, 폭 ±47.2 mm.
   - 팔 받침 상자 proxy를 추가한다.
3. **링크 길이 차이.**
   - 치수도 상완은 57.7 mm이고, SDK와 v2는 65 mm다. 치수도는 인쇄 치수 5개와 1 % 안에서 맞는다(343 mm 전고 = 127.7 + 57.7 + 62.4 + 94.0 = 341.8).
   - v2로 팔을 곧게 세우면 360 mm가 된다.
   - 실측 전에는 바꾸지 않는다. REAL 제어기와 FK가 65를 쓰기 때문이다.
4. **집게 끝 위치.**
   - 치수도 94 mm, SDK 100 mm, v2 접촉 box 중심 100(86–114) mm로 서로 다르다.
   - v3 시각 패드는 물리 접촉 box 중심(100 mm)에 둔다. 영상과 접촉이 어긋나지 않게 하려는 것이다.
5. **카메라.**
   - 기본 제공 카메라(HBVCAM)의 치수도 위치는 렌즈가 손목축에서 53 mm 앞, 공구축에서 28 mm 위다.
   - ugrp1 적합값은 67 / 13.6 mm, −7.95°다. 적합값대로면 기본 브래킷에서는 카메라 기판이 집게 윗판과 겹친다.
   - v3는 AGENTS.md에 따라 적합 자세를 유지한다. 렌즈 시각 geom은 robot_cam 위치에 정확히 둔다(테스트). ugrp1 실측이 필요하다.

## 영향 목록 (1단계 기록, 전환은 할 일 목록 참조)

- **렌더로 학습한 시각 모델**
  - 손목 카메라 영상: `appearance_only`에서는 자기 로봇이 화면에 거의 안 들어온다. `look_down` 자세 비교는 바닥과 그림자 모양만 다르다(`compare_robot_cam.png`).
  - 하지만 동료 로봇, TOP 카메라, 관찰자 영상에서는 외형이 크게 바뀐다. 동료 판별과 짝 인식 모델, 태그 없는 위치 추정(VIS 계열), 화물 인식 v1–v3 가운데 로봇 외형이 들어간 학습 데이터는 다시 확인해야 한다.
  - `drawing_layout_proposal`은 팔 위치가 바뀌므로 손목 영상 자체도 달라진다.
- **pair align과 짝 운반(#240, #246)**
  - 동료 외형(주황 대신 짙은 회색 차체, 받침 상자, 덮개), 몸체와 팔의 상대 위치, 충돌 proxy(제안 프로필)가 달라진다.
  - `peer_visibility_band` 같은 시각 단서는 v2 몸체 높이를 가정하므로 다시 확인해야 한다.
- **초음파(#248)**: 장착값 x 78 → 88 mm, 높이 54 → 61.7 mm, 간격 34 → 26.7 mm. 막대와 상대 로봇 가시성 표도 다시 계산해야 한다.
- **실행 번들**
  - 이 PR은 번들을 새로 쓰지 않는다. v2 파일이 바뀌지 않았으므로 `rgb-standard-dispatch-v63`을 비롯한 기존 번들의 해시도 그대로다.
  - 전환 PR은 `sim/multi_masterpi_production.py`의 `build_v2_xml` 호출을 바꾼다. 이 파일은 `REQUIRED_SOURCE_PATHS`에 들어 있으므로 새 RUNNABLE_ID를 등록해야 하고, 그때 main과 열린 PR의 최댓값을 확인해야 한다.
  - `harness/rgb_communication_scenarios.py`의 고정 파일 목록(770–772행)과 source-pinning 테스트도 다시 검토해야 한다.
- **해시를 고정한 테스트**
  - `tests/test_zone_study_source_pinning.py`, `tests/test_rgb_execution_bundle.py`는 이 PR에서 통과했다.
  - `tests/test_masterpi_physical_geometry.py`, `tests/test_masterpi_visual_geometry.py`는 v2 이름과 크기를 단정한다. 전환할 때 v3 버전을 따로 만들어야 한다. v2 테스트는 v2 모델에 그대로 둔다.

## 사용자 실측 목록 (ugrp1)

`sim/masterpi_geometry_v3.py`의 `MEASURE_ON_ROBOT`과 같다.

1. 초음파 송수신기 중심 높이(바닥에서): 치수도 61.7 / v2 54 mm
2. 차축 중앙에서 초음파 송수신면까지 앞 거리: 88.0 / 84 mm
3. 초음파 기울기(수평 = 0°)
4. 차축 중앙에서 팔 yaw(ID6) 축까지 앞 거리: 48.2 / 0 mm
5. 어깨(ID5) 축 높이: 127.7 / 125.5 mm
6. ID5–ID4 축 거리: 57.7 / 65 mm
7. ID4–ID3 축 거리: 62.4 / 62 mm
8. ID3 축에서 닫힌 집게 끝까지: 94 / 100 mm
9. 렌즈 중심 위치(ID3 축에서 공구축 방향, 공구축 위): 53/28(기본 카메라) vs 67/13.6(적합) mm
10. ugrp1 카메라 모델(HBVCAM 기본인지, icspring인지)
11. 윤거 129.9 / 131, 축거 118.8 / 120, 바퀴 폭 30 / 31 mm
12. 차체 앞판–뒤판 길이: 185 / 120 mm
13. ID5 서보 라벨(LD-1501MG 또는 LDX-218)

## 출력 (로컬 원본, 커밋하지 않음)

위치: `/Users/changmin/projects/ugrp/outputs/masterpi-visual-v3/`. `manifest.json`의 sha256은 `85c0826c…9c03`이다.

주요 비교 이미지:

| 파일 | 내용 | sha256 |
|---|---|---|
| `compare_product_view.png` | v2 / v3 제안 / v3 appearance_only / 공식 렌더(3/4 시점) | `f85b0b7c…0899` |
| `compare_side_ortho.png` | 옆 정사영, 팔 세움, 1 cm 눈금자, 초음파 표시, 공식 치수도 | `8bc67352…1852` |
| `compare_front_ortho.png` | 앞 정사영과 공식 치수도 | `301d70da…f349` |
| `compare_robot_cam.png` | 손목 카메라가 보는 장면(`look_down` 자세) | `ea6c555e…2682` |
| `v3_drawing_layout_side.png` | 옆 정사영 단독(눈금자, 초음파 점과 축) | `c08ef7ec…2597` |

- 참조 이미지(Hiwonder 원본 사본)는 `reference/`에 두었고, 해시는 `reference/SHA256SUMS`에 있다. 저작권 때문에 커밋하지 않는다.
- 로컬 보관일 뿐이며 원격 백업이 아니다.

## 검증 (1단계 기록)

- 당시 `tests/test_masterpi_visual_v3.py` 12개(2단계에서 `tests/test_masterpi_model_v3.py` 11개로 교체): v2 물리 동일성(카운트, body, joint, actuator, camera, 충돌 geom, FK 비트 동일), 추가 geom이 모두 질량 0이고 비충돌인지, 초음파 사이트 값, 제안 프로필 변경 범위, 다중 로봇 prefix 복제 컴파일, 출처 등급, 치수도 축척, 번들 closure 밖 위치.
- 함께 돌린 기존 테스트: `tests/test_rgb_execution_bundle.py`, `tests/test_zone_study_source_pinning.py`.
- 위 테스트는 `mj_step`을 막는 가드 아래에서 돌렸다. 결과는 PR 본문에 있다.
- `test_masterpi_physical_geometry.py`, `test_masterpi_visual_geometry.py`는 `MasterPiDynamicsV2()` 생성 때 물리 step을 쓴다. 배터리 사용 중이라는 지시에 따라 실행하지 않았다(가드에 막힌 것 외의 실패는 없었다). v2 파일을 바꾸지 않았으므로 결과는 바뀌지 않아야 한다. 전원이 연결되면 확인해야 한다.
- TensorBoard: 지표가 있는 실험·학습·평가 결과가 아니어서 새 스냅샷을 만들지 않았다.

## 검증 (2단계)

- `tests/test_masterpi_model_v3.py` 11개를 `mj_step` 가드 아래에서 실행했다. 프레임 위치(yaw 48.2 mm, 어깨 127.7 mm, 링크 65/62 mm, 패드 86.85 mm), 바퀴, 충돌 proxy, 초음파 사이트, v2 동역학·카메라 유지, 보정값 우선, 실측값 교체, PWM→관절 대응에서의 FK, 차이 표, v2 외관 진단 모델의 물리 동일성을 확인한다.
- 전환 패치는 적용하지 않은 상태로 커밋했다. 위 134개 새 실패 목록은 패치를 적용해서 측정한 값이다.
