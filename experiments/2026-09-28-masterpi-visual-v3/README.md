# 2026-09-28 MasterPi 모델 v3 (공식 치수도 + SDK 팔, 물리 포함)

- 작업: Claude, 브랜치 `claude/masterpi-visual-v3`, 기준 `origin/main` `d5bd208e`(#240 병합 포함)
- 성격: 모델 버전 추가. 실험 결과가 아니고 성공률도 없다. 물리 step 0회, 시뮬레이션 실행 0회, 모델 호출 0회다. 정지 자세는 `mj_forward`로만 계산했다.
- 1단계(외관 v3)에 이어 2단계에서 사용자 결정(치수도를 물리까지 채택, 다음은 sim2real)에 따라 `build_v3_xml`을 물리 모델로 바꿨다.
- 파일:
  - `sim/masterpi_geometry_v3.py`: 치수, 출처 등급, 실측 목록, 물리 파라미터 한 벌 `PHYSICAL_V3`, 제어기와의 차이 표 `CONTROLLER_VS_PHYSICAL_V3`
  - `sim/masterpi_model_v3.py`(구 `masterpi_visual_v3.py`): `build_v3_xml(hardware, geometry=PHYSICAL_V3)`, 진단용 `build_v2_appearance_xml`
  - `scripts/render_masterpi_model_v3.py`, `tests/test_masterpi_model_v3.py`
  - (`switch_wip.patch`는 전환 1/n 커밋에서 적용하고 지웠다)
- v2는 바이트 그대로다. `sim/masterpi_dynamics_v2.py`, `sim/masterpi_geometry.py`, `sim/masterpi_scene*.xml`을 고치지 않았다.

## Codex 후속 구현 — 2026-09-28 (로컬 변경, 전환 미완료)

Claude가 시작한 PR #249를 Codex가 `961271a44ad34cf17e94f36217589af7cde2fa2a`에서 이어 작업했다. 아래 인계 TODO·착수 차단 기록은 이전 시점의 기록이며 보존한다. 이번 실행 규칙은 `OMP_NUM_THREADS=2`, 지정된 공용 Python, pytest cache OFF다.

### 변경

1. `zone_wide_door_geometry_v3`, `zone_wide_door_geometry_v3_dock_v1`을 새로 등록했다. 기존 표식 없는 `geometry_v2`에서 파생하고 robot_model은 `masterpi_v3`다. 기존 map 파일과 v2/동결 소스의 해시는 `configs/masterpi_v3_scenes.json`에 보존했다. 새 장면만 새 map/robot XML/scene XML 해시를 기록한다.
2. `MasterPiV3ZoneScene`은 기존 표준 `Scene` 계층을 상속한다. zone host의 인스턴스 XML hook에서 환경·접촉 변환 뒤 v3 로봇 변환을 적용하며, 실제 템플릿의 physical_params와 calibration_parameters를 사용한다. 보정된 트랙·축간은 우선하고 나머지는 v3 치수값을 쓴다. 실제 world 생성은 이번에 실행하지 않았고, hook의 정적 컴파일·가짜 world 배선을 테스트했다.
3. 새 `zone_model_conventions`·`zone_team_footprint_v3`·`TeacherStationsV3`가 장면의 robot_model을 읽는다. 스테이션은 팔축 반경 155 mm + 장착 48.2 mm = 차대 기준 203.2 mm다. 시작 도킹의 차대 열도 48.2 mm 뒤로 옮겨 기존 팔축 열을 유지하며 keepout과 같은 값을 쓴다. 교사 모듈은 **스테이션 계산 어댑터**까지이며 전체 교사 상태기계 이관은 아니다.
4. `visual_arm_v3`는 기존 `visual_arm` FK·삼각형 IK를 import해 재사용한다. yaw 장착 48.2 mm, 어깨 높이 차이 2.2 mm, 실제 패드 중심 86.85 mm를 반영한다. 카메라 로컬 자세/FOV는 바꾸지 않았다. 스윕 가드는 기존 표본화 수학에 장착 변환과 보수적 잔차를 적용하며, 자기 자세가 없으면 v3 팔 스윕을 거부한다.
5. v3 장면의 model runtime은 새 팔·가드·발자국 모듈을 선택한다. 기존 v2 손목 스킬/표식 제공자는 **물리 world 생성 전에 거부**한다. 실제 v3 손목 스킬·표식 없는 자세 제공자·짝 운반 소비자 이관은 남아 있으므로 통합 러너의 v3 실행 완료로 보고하지 않는다.
6. 정적 감사 뒤 main과 열린 PR 11개의 head를 커넥터로 읽어 로컬 origin 참조와 모두 대조했다. 전체 origin/*의 등록 bundle 최대가 v73이므로 `zone-study-integration-v74-masterpi-v3`를 선택했고, v69는 은퇴 ID에 보존했다. workflow는 열린 브랜치 최대 2.3.0 다음인 2.4.0이다. **로컬 등록일 뿐, 원격 번호 예약/코드 push는 완료되지 않았다.** SHA 목록은 `codex-bundle-heads.json`에 있다.

### 정적 감사와 검증 범위

- `codex-static-audit-v1.json`과 설명을 보강한 v2를 보존했고, 최종본은 `codex-static-audit-v3.json`이다. v1/v2에서 빠졌던 host의 추가 cargo contact profile을 v3에 적용해 `cargo_noslip_v1`, noslip 10회를 확인했다. 충돌/가림 값은 같으며 이전 원본을 덮어쓰지 않았다. 각 장면 seed 700, 3대, 동일한 시작 PWM에 `mj_forward`만 적용했다. world 초기화/settling/에피소드는 실행하지 않았다.
- 자기충돌·로봇 간 침투 0건. 각 장면 바퀴–바닥 접촉 표본 24건, 최대 약 0.145 mm 침투를 별도로 기록했다. 접촉 없는 완벽한 모델이라는 뜻은 아니다.
- 카메라당 17×13 = 221개 원시 pinhole 광선 표본: 각 robot_cam 자기 형상 가림 0/221, 각 nav_cam 손가락 가림 2/221. nav_cam은 standard host에 없으므로 builder의 `navigation_camera=True`로 추가한 진단 카메라다. fisheye 렌더 전체나 작업 물체 가시성 검증은 아니다.
- 새 정적 테스트는 `mj_step`을 실패 처리한다. v2 기하 두 파일에만 사용자가 허용한 짧은 물리 step이 있었다. 모델/LLM 호출 0, 물리 에피소드 0, weld OFF다. 새 학습/운반 실험·TensorBoard 실험 스냅샷은 없다.
- 최초 v3 IK 테스트는 6개 실패했다. 145 mm 경계는 부동소수점 비교 오차여서 1e-10 cm 비교 여유로 수정했다. 180 mm/높이 24 mm 목표는 실제 패드/서보 제한으로 도달 불가능하여 거부 테스트로 분리했다. 통과한 목표는 반경 145/155/160 mm × yaw -10/0/10도 9점이며, 전 범위/물리 파지 성공 주장이 아니다.
- v2 기하: `tests/test_masterpi_physical_geometry.py tests/test_masterpi_visual_geometry.py` **23 passed in 0.87s**.
- v3/번들/소스 고정 중간 회귀: **80 passed in 57.56s**. 기존 통합 pair/seams 및 입력 경계: **125 passed in 25.60s**. 이후 v64 생성 비교까지 **826 passed in 924.17s**, 감사 접촉 프로필/수집 보완 뒤 관련 **31 passed in 3.73s**를 확인했다. MuJoCo import 금지 상태의 순수 모듈 검사도 통과했다. 명령·통과 결과·최종 파일 해시는 `codex-validation.json`에 기록했고 `.pytest_tmp` 삭제를 확인했다.

### 남은 문제와 게시 상태

- **커밋 0, push 0, 병합 0.** `git fetch origin`은 공용 `.git/.../FETCH_HEAD`, `git add --sparse -A`는 `index.lock` 쓰기에서 `Operation not permitted`로 실패했다. 우회 checkout·강제 변경은 하지 않았다.
- origin의 옛 이름 `kcm0127-dotcom/ugrp`와 요청 저장소 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`는 GitHub 커넥터상 동일 저장소 ID `1359726870`이다. origin 설정은 바꾸지 않았다.
- PR 댓글·본문 쓰기는 모두 `MCP tool call requires approval, but approval policy is never`로 거부됐다. 실제 본문은 갱신되지 않았고 한국어 갱신안을 `PR_BODY_KO.md`에 저장했다. 원격 HEAD는 여전히 `961271a4`이며 여기의 로컬 기능 변경을 포함하지 않는다.
- 남은 구현: 실제 v3 손목 스킬/표식 없는 위치 추정/짝 운반/전체 교사 소비자 이관. 남은 검증: 실제 host 초기화·settling·주행·파지·운반·실물 보정. 현재 스윕/발자국은 보수적 정적 모델이며 v3 실물 보정 완료가 아니다.
- 이후 허용된 세션에서 원격 번호 충돌을 다시 확인하고, 지정 테스트의 최종 통과를 본 뒤 `git add --sparse -A` → 한국어 커밋(마지막에 `Co-Authored-By: Codex <noreply@openai.com>`) → push → PR 본문 갱신을 해야 한다. 병합하지 않는다.

## 할 일 (2026-09-28 인계 당시, 관리자 결정 반영: robot_model은 장면 버전의 일부)
완료:
- v3 물리 모델(`sim/masterpi_model_v3.py`, `PHYSICAL_V3`)
- 기존 장면이 쓰는 코드와 테스트는 main 바이트로 복원했다(3/n). 기존 등록 장면은 robot_model v2, 0.155 m 스테이션 규약, 해시와 동작이 main과 같다. 동결 소스(`owncam_pair_beam` 등)도 바뀌지 않는다.
- 새 코드 `sim/masterpi_robot_models.py`:
  - `station_grasp_convention(robot_model)`: 팔 반경 0.155 m(보정 범위 안) + 모델의 팔 장착 위치. v3의 스테이션 거리는 0.2032 m다.
  - `v3_robot_xml_transform(...)`: `MultiMasterPiProductionV2(xml_transform=...)`로 각 `<rid>__robot`을 v3로 바꾼다. 로봇 자세, nav_cam, 동료 충돌 규칙, actuator·weld 이름은 유지한다.
  - `tests/test_masterpi_robot_models.py` 4개 통과
- 1/n·2/n에서 만든 제어기 장착 구현(`visual_arm` 헬퍼, 가드 장착 위치 호출 시점 해석)은 이력 `4031baa5`, `99ac4ba1`에 있다. 새 코드로 옮길 때 참고한다.

남은 일(순서대로):
1. v3 장면 버전: 다음 빈 버전 이름으로 새 zone 장면 버전을 만들고 `robot_model: masterpi_v3`를 싣는다(`sim.session_scenes.Scene`의 명시적 version/profile 재사용). 그 버전에만 새 해시를 등록한다. 연결 지점은 zone study 장면 구성(`harness/zone_own_team_host.py` 74–80행)이다. `sim/zone_own_scene_provider.own_scene`의 transform 뒤에 `v3_robot_xml_transform(world 템플릿 physical_params, calibrated_keys=calibration_parameters)`을 잇는다. 이 파일들은 zone study closure에 속하므로 새 번들 ID와 함께 바꾼다. 기존 버전 경로의 바이트와 동작은 그대로 둔다.
2. v3 소비자는 새 코드로 만든다. 스테이션(teacher), 시작 도킹, 발자국은 장면의 robot_model에서 `station_grasp_convention`을 읽는다. 기존 `scripts/zone_teacher.py`, `sim/zone_start_dock.py`, `harness/zone_team_footprint.py`의 바이트는 바꾸지 않는다.
3. v3 제어기 층: 팔 장착 48.2 mm를 반영한 FK/IK와 카메라 외부 파라미터를 새 모듈로 만든다(예: `harness/visual_arm_v3.py`, `CONTROLLER_GEOMETRY_ID`). v3 장면의 실행기만 그 모듈을 쓴다. 가드도 같다.
4. 다중 로봇 시작 자세 자기충돌·nav_cam/robot_cam 가림 정적 감사(`mj_forward`만 허용). 이번 세션에서 물리 stepping은 금지한다.
5. 번들은 마지막에 등록한다. main과 열린 PR 전체(#246, #250, #253, #254 포함)의 RUNNABLE_ID를 다시 확인한 뒤 다음 빈 ID를 쓴다. 확인 브랜치와 선택 ID는 PR #249 댓글에 남긴다. 비교 렌더·전원 연결 후 물리 검증은 별도 후속 작업이다.

## Codex 인계 점검 — 2026-09-28 (착수 차단)

- 기준: `claude/masterpi-visual-v3`, 로컬 HEAD와 PR #249 head 모두 `961271a44ad34cf17e94f36217589af7cde2fa2a`. 시작 작업 트리는 깨끗했다.
- 차단: `git fetch origin`이 `/Users/changmin/projects/ugrp/.git/worktrees/claude-masterpi-v3/FETCH_HEAD: Operation not permitted`로 실패했다. 공용 Git 메타데이터가 세션 쓰기 허용 범위 밖이므로 필수 fetch·단계별 커밋·push 절차를 진행할 수 없다. 권한 우회나 다른 checkout 사용은 하지 않았다.
- 추가 확인 필요: 로컬 origin은 `https://github.com/kcm0127-dotcom/ugrp.git`, 요청 저장소는 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`다. 리다이렉트/동일 저장소 여부는 확인하지 못했고 origin은 바꾸지 않았다.
- `gh pr list`와 `gh pr view`는 api.github.com 연결 실패. GitHub 커넥터로 요청 저장소의 PR #249 본문·head는 읽었다.
- 이번 세션 커밋 목록: 없음. 기능 전환·신규 장면/해시·bundle ID 등록: 없음. 동결 소스와 기존 등록 장면은 수정하지 않았다.
- bundle 번호 확인 브랜치: 없음(원격 갱신 차단). #246, #250, #253, #254 및 당시 열린 PR 전체와 main의 `RUNNABLE_ID` 조사는 재개 후 수행해야 한다. 번호를 추정하거나 예약하지 않았다.
- 테스트: 미실행(구현 전 차단). 이번 세션의 pytest 통과 결과는 없다. 기존 통과 기록은 이전 작업의 결과다.
- 시뮬레이션·물리 stepping·mj_forward·모델/LLM API 호출: 모두 0회. 새 실험 결과나 TensorBoard 스냅샷은 없다.
- 저장 범위: 이 점검 기록은 로컬 실험 README에만 저장했다. PR 본문 갱신은 GitHub 커넥터가 `MCP tool call requires approval, but approval policy is never`로 거부하여 반영되지 않았다. README는 미커밋·미push 상태이며 PR TODO 갱신도 남아 있다.

남은 TODO — 이번 사용자 요청 순서, 모두 미완료:
1. [ ] 다음 빈 이름의 v3 zone 장면과 `robot_model: masterpi_v3`, XML transform 연결, 신규 버전에만 해시 등록 및 단일 파일 pytest 통과.
2. [ ] 장면 robot_model 기반 station·dock·footprint 새 소비 경로. `scripts/zone_teacher.py`, `sim/zone_start_dock.py`, `harness/zone_team_footprint.py` 바이트 보존 및 관련 pytest 통과.
3. [ ] 기존 수학을 import/매개변수화해 v3 FK/IK·카메라 자세·collision sweep guard 구현, v3 실행기에만 연결 및 관련 pytest 통과.
4. [ ] mj_forward만 사용하는 시작 자세 다중 로봇 자기충돌·nav_cam/robot_cam 가림 정적 감사와 관련 pytest 통과. mj_step·시뮬레이션 루프 금지.
5. [ ] 마지막에 main과 열린 PR 전체(#246/#250/#253/#254 포함)에서 git grep으로 다음 bundle ID 확인·등록·검증하고 확인 브랜치와 ID를 PR #249 댓글에 기록.

재개 조건: 지정 worktree의 공용 Git 메타데이터에 정상적으로 쓸 수 있고 원격 fetch/push가 가능한 세션에서 origin 대상부터 확인한다. 각 단계는 지정된 OMP_NUM_THREADS=1 단일 파일 pytest의 passing 결과를 확인한 뒤 별도 명령으로 커밋하고 즉시 push한다. main push와 PR 병합은 계속 금지한다.

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
