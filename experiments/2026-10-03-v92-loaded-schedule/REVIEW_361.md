# PR #361 독립 검토 — MERGE AFTER FIXES

2026-10-03, Codex. 검토 대상은 **`a9481446d9c7c503bdbc53941d3538cd5ec5ee12`**,
시작 기준 main은 `7cd729416fc04dfc4633cb4da5c4cd9435dd582d`다.
진단 #359는 `f2fc0cc3d2315e8b4441028a1713a1ba5af23175`의 기록과 코드를 읽었다.
작업 브랜치는 `codex/review-361`; 대상 구현은 수정하지 않았다.

**판정: MERGE AFTER FIXES.** 수집 설계의 범위·물리 보존·번호 예약은 적절하다.
아래 P1의 카탈로그 회귀 2개를 수정하고 새 SHA의 필수 CI를 통과시켜야 병합할 수 있다.
이는 **UNQUALIFIED 교사 수집 경로의 병합 검토**다. 현재 학생 보정 승인, 높은 자세 채택,
720초 전체 수집 성공이나 실물 운반 승인은 아니다. P0는 발견하지 않았다.

**게시 직전 소스 변경 주의:** 이 검토서를 처음 커밋·push한 뒤 PR head가
`0db84afc73bdfce848f1e797622d8a1b1b94979c`로 바뀌었다(추가 구현 `83032b6d`).
새 head는 모든 loaded 측정을 HIGH로 바꾸고 B″ 기준·일정 해시·측정 구간을 변경한
**다른 후보**다. diff의 변경 범위와 카탈로그 테스트가 그대로임을 확인했지만,
이 문서의 수치·자세 보존 PASS·조정자 권고·MERGE AFTER FIXES 판정은 요청된 **a9481446 전용**이다.
새 HIGH/B″ 후보의 독립 검토·물리 인수로 승계하지 않는다. 새 head의 CI는 조회 당시 진행 중이었다.

## 병합 전 수정 사항 — 한 묶음

### P1. 새 workflow가 기존 카탈로그 회귀에 반영되지 않아 필수 CI 실패

- 위치: `configs/simulation_workflows.d/final_pair_v92.json:5`,
  `tests/test_simulation_workflow_manager.py:188`, `tests/test_simulation_workflow_manager.py:250`,
  `tests/test_simulation_workflow_manager.py:255`.
- 재현: 아래 두 테스트를 대상 SHA에서 실행하면 **2 failed in 0.36s**.
  첫 테스트는 workflow 수 **48 != 47**, 두 번째는
  **`KeyError: 'zone-final-pair-loaded-v92'`**다. 신규 workflow가 등록되었지만
  기존 개수 단언과 `samples` 사전은 갱신되지 않았다.
- 원격에서도 [동일 shard 2 실패](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37100818291/job/111139910234).
  해당 shard는 `2 failed, 1412 passed, 18 skipped, 10 xfailed, 7 subtests passed`;
  최종 집계 **`offline-regressions=FAILURE`**. 단순 대기나 환경 오류가 아니다.
- 수정 조건: 카탈로그 기대값과 v92 plan 입력을 함께 갱신한다. 입력에는
  `--check calibration-loaded`, `--map-id zone_wide_two_doors_final_v3`, 정확한 소스 SHA 형식을
  포함한다. 두 테스트와 workflow 관리 관련 회귀, 새 SHA의 필수 CI를 다시 확인한다.
  `.github/workflows` 변경이나 테스트 제외로 해결하지 않는다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_catalog_has_thirty_selectable_workflows_and_distinct_adapters \
  tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_every_catalog_workflow_has_a_read_only_explicit_plan
```

## 요청한 여섯 검사

### 1. 번호 예약 재검색 — PASS

처음 작업으로 `git fetch origin`을 수행했다. GitHub의 **열린 PR 9개 전체**의 head SHA가
fetch한 ref와 같은지 확인한 뒤, 각 SHA의 `harness/`, `configs/`, `scripts/`에서
`RUNNABLE_ID`, final-pair ID와 다른 접두사의 v92 이상 ID도 검색했다.
기본 workflow 목록과 모든 `configs/simulation_workflows.d/*.json`의 버전을 읽었다.

| ref | 확인한 SHA | 최대 final-pair / workflow |
|---|---|---|
| main | `7cd729416fc04dfc4633cb4da5c4cd9435dd582d` | v91 / 3.3.0 |
| #361 | `a9481446d9c7c503bdbc53941d3538cd5ec5ee12` | **v92 / 3.4.0**, 이 PR에만 존재 |
| #360 | `c3af0783e8d05b40c9e859657e7f6ecae0928aed` | v91 / 3.3.0 |
| #359 | `f2fc0cc3d2315e8b4441028a1713a1ba5af23175` | v91 / 3.3.0 |
| #358 | `576bf4dad2d1fa1d6d8613564929d0f4b7b455bf` | v91 / 3.3.0 |
| #356 | `352a2389b30b6e95025e375beec0ec9eb68c2355` | v91 / 3.3.0 |
| #353 | `6fc4b415634c9b2d5362a419bb1a1b5b50b6c37f` | v88 / 3.1.0 |
| #339 | `9912bb15bb492bab0f9278fc493feed1547ff8ee` | final-pair ID 없음 / 3.0.0 |
| #309 | `c8379bbe16492687af9d7b2d04f85e4ae4c610cc` | final-pair ID 없음 / 3.0.0 |
| #293 | `d86cc82eedbe0c6693eaf808c54ce43387723f1d` | final-pair ID 없음 / 3.0.0 |

모든 ref의 `harness/rgb_execution_bundle.py` 기본 `RUNNABLE_ID`는 v63이다.
다른 PR의 v92 / 3.4.0 충돌은 없다. 조정자가 실행·병합할 때 ref가 바뀌면 다시 확인한다.

**최종 재검색(2026-10-03 15:15 KST 이후):** 다시 fetch하니 main은
`db37ee4aae073dbd1c2d1a206b31dd64412fbea5`, #356은
`d4694309d13da8fd562d62ce809a22eeb5bdc065`로 바뀌었고 #360은 열린 목록에서 빠졌다.
나머지 SHA는 표와 같았다. **최신 main과 열린 PR 8개 전체를 다시 검색**했으며 여전히
#361 밖 최대 v91 / 3.3.0, v92 / 3.4.0 충돌0이다. 원래 검색은 보존하고
`reservation_final_check.json`, `reservation_final_rescan.json`에 새 ref와 조회 결과를 남겼다.
검토·물리 재현 소스는 계속 a9481446으로 고정했다.

### 2. 물리·영상·안전 경계 보존 — PASS, 실제 영상·실물 검증과 구분

`preservation.json`의 **29개 파일**을 대상 SHA와 시작 main의 실제 바이트로 재해시해 모두
일치시켰다. 전체 diff에서도 기존 물리·카메라·학생·기준 파일 변경은 없다.
`sim/final_pair_loaded.py:11–31`은 v88의 `make_scene`/backend와 v91의 `FastGuard`를 사용한다.
`reset`, `issue`, `capture`, `eval_sample`, `advance_to`, `collection_guard` 메서드는
v91 클래스가 사용하는 것과 Python 객체 수준에서도 동일하다.

독립 자세 재실행의 아래 **6개 실제 산출물**을 허용된 v88 r8 loaded raw와 비교해
바이트가 모두 같았다: `scene.xml`, `scene.json`, `eval_only/applied.json`,
`eval_only/render.json`, `eval_only/setup.json`, `inputs/static_map.json`.
v88 원본은 `outputs/final-pair-v88-cal-747d2b9f-20261001-r8/calibration-loaded/zone_wide_two_doors_final_v3/`다.

- `cargo_noslip_v1`, noslip iterations **10**, 실제 적용 timestep **0.00025 s**.
- `floor_light_v1`, 로봇 `masterpi_v3`, 빔·로봇 외관·기하 동일, weld OFF·초음파 OFF.
- 카메라 위치 `[0.067, 0, 0.0136]` m, 동일 quaternion, 640×480,
  기록된 `fovy=42.18818995586325°`, 동일 fisheye intrinsics·왜곡·near plane.
  기존 mount는 소스상 `CENTERED_STRUCTURAL_MOUNT_UNVALIDATED`이며,
  **기존 설정 보존을 실물 hand-eye 검증 완료로 해석하지 않는다**.
- 명령 lease/pose 평가 **0.05 s**, RGB **0.2 s**, 시작·종료 프레임, 명령 전 캡처 순서 동일.
- 최소 벽 여유 **0.30 m + abort buffer 0.05 m**, 몸체 bound **0.40 m**,
  substep 변위 한계 **0.01 m**, 명령 전·substep 전후·0.05 s 평가 검사 동일.
- scene XML SHA-256: `24a4c1d00b01e50f2a3c53d503459dd85d08c420056f828ab792e642c5a063de`.

v91은 unloaded held-out 경로이므로 동일한 loaded 시작 장면을 실행했다고 주장하지 않는다.
v91과의 비교는 공통 소스·프로필·FastGuard·샘플링 계약으로 했으며 **v91 held-out raw는 전혀 읽지 않았다**.
바뀐 것은 새 일정·측정 구간, 720초 cap, 교사 수집 identity와 이를 등록하는 wrapper다.

### 3. #359의 각 막힘 — 해결 시도와 미해결 결정을 명확히 구분

| #359 막힘 | v92 변경·독립 확인 | 판정 |
|---|---|---|
| `807,1897,2187,1500`에서 빔 경계 없음 | 이 숫자는 3개 자세가 아니라 **한 서보 자세**다. 기존 hover 유지, 높은 후보 `896,2035,1894,1500` 추가. 실제 XML 기반 무렌더 기하에서 hover 양쪽 **0열**, 높은 후보 양쪽 **90열**, 40픽셀 연속 경계와 midpoint 가림 검사도 90열. 후보 색 면 깊이 약 **27.8 mm > near 22.225 mm** | 후보의 필요 기하 조건 확인. 학생 hover 문제는 미해결이며 명시된 조정자 결정 |
| 일부 자세에 lifted bilateral-grip 표본 없음 | 바닥 파지 24 mm 자세를 방문하지만 그 자세의 상승 10 mm를 주장하지 않음. 떠 있는 hover/높은 후보에서는 아래 짧은 검사로 네 집게 접촉·무지지 상승 확인 | 바닥 지지 상태 계약은 조정자 결정. 누락값을 다른 자세로 대체하지 않음 |
| 초기 팔 과도응답 | 4초 들기 뒤 12초부터 측정, 각 새 자세/팬 뒤 8초 준비. 원본 준비 구간은 보존 | 새 구간 정의는 합리적. frozen B′의 1초 선택은 그대로여서 **새 분석기 결정 전에는 자동 해결 아님** |
| 큰 팬 전이 중 grip loss | 700→1770 대신 1500→1480→1500→1520→1500, 최대 20 PWM(1.8°) 전이. 아래 hover/높은 후보 짧은 검사 모두 파지 유지 | 작은 범위에서 물리 재현 PASS. 470초 운동 이후의 누적 상태·전체720초는 미검증 |
| 13개 중 5개 모수 경계 | 회전 gain/tau/u1의 원인이었던 반대 회전을 공동 회전+접선 명령으로 분리. 실제 양·음 공동 회전 재현. 전진·옆 c0에는 .001/.002/.004 계단 추가; 원래 288개 명령 수준 조합 보존 | 회전 여기 개선 확인, 새 13계수 적합은 미실행. c0 범위/모형은 조정자 결정 |

회전 부호의 근거: 180° 마주 보는 로봇은 전진·옆 local 부호를 반대로 해야 같은 세계 방향으로
이동하지만 yaw 부호는 반전되지 않는다. `action_vector`(`harness/zone_final_pair_loaded_schedule.py:97–108`)의
공동 회전은 양쪽 같은 `turn=u`, 같은 `left=-0.4732u`다. 0.4732는 정적 빔 반길이와
파지 반경의 합이며 속도 보정값이 아니다. 실제 동역학 등가나 회전 계수 수락으로 과장하지 않는다.
높은 자세의 반대 yaw 구간은 쌍 상대각 측정용으로 따로 표시되어 있다.

### 4. 실제 학생 자세와 누락 여부 — PASS, 미측정 요구는 유지

`harness/zone_final_pair_vision.py:23–45`의 `grasp_postures()`와 `required_camera_poses()`를
직접 대조했다. loaded 필수 자세는 바닥 파지와 hover **2개**이고,
v92의 `floor_grasp`, `controller_hover`가 PWM까지 정확히 같다.
`harness/zone_final_pair_skill.py:128–143`의 학생 하강 중간 7단계는 open descent 전이이며
loaded 정착 카메라 키로 요구하지 않는다. 기존 unloaded 자세 목록과 수집 경로도 삭제하지 않았다.
새 110/130 mm는 수집 준비 전이, 150 mm는 별도 후보다. 바닥 자세는 방문하지만
lifted 표본이 없는 상태로 남으며, 이를 필수 목록에서 몰래 제거하지 않았다.

### 5. FastGuard·SIM-slot·수집 명령 — PASS (실행 준비 경로)

등록된 표준 CLI가 `scripts.run_final_pair_loaded`로 연결되고
`scripts/run_final_pair_loaded.py:24–93`의 루프는 고정 일정을 따라 720초를 유한 실행한다.
명령 **22,326개**, pose **14,401개**, 로봇당 RGB **3,601장**이라는 계획을 fake backend로 검증한다.
`COLLECTED_UNQUALIFIED`, `physical_success=None`, `research_result=False`를 유지한다.
GT/접촉은 eval 출력과 abort-only 안전 검사에만 있고 일정 보정에 사용되지 않는다.

`collect.sh:4–43`의 worktree·branch·정확한 SHA·clean tree·새 출력·디스크·슬롯 확인,
같은 owner/PID의 SIM 조정자 규칙, 자식 종료 후 슬롯 해제가 맞다.
셸 구문 검사와 아래 **execute 없는 실제 CLI 계획 경로**도 통과했다.
720초+reset 최대5초=725초이며, 90분은 잠금 예상 메타데이터다.

```sh
cd /Users/changmin/projects/ugrp-wt/v92-loaded
V92_SOURCE_SHA=a9481446d9c7c503bdbc53941d3538cd5ec5ee12 \
  bash experiments/2026-10-03-v92-loaded-schedule/collect.sh
```

위 명령은 **대상 SHA의 조정자 명령 확인**이며 이 검토에서 실행하지 않았다.
P1 수정 뒤에는 새로 검증한 40자리 SHA로 인계를 갱신해야 한다. 다른 브랜치·다른 조정자의
슬롯을 빌려 실행하지 않는다. 단순 plan 경로 확인은 전체 수집 완료가 아니다.

### 6. 조정자 결정 항목과 권고

| 결정 | 권고와 완료 조건 |
|---|---|
| 전진/옆 c0 하한과 정지/램프 모형 | **훈련 자료만으로 새 모형/범위를 사전 등록**한다. .006에서 이미 움직인다는 반례 때문에 c0≥.006을 유지한 채 같은 fit을 수락하면 안 된다. 새 낮은 계단을 미리 정지로 분류하지 말고, 축별 내부해·잔차·식별성을 확인한다. PRBS는 validation으로 남기고 v91 held-out으로 튜닝하지 않는다 |
| 바닥 파지의 loaded 카메라 계약 | **floor-supported grasp와 lifted carry를 다른 상태로 분리**하는 계약을 권고한다. 현재 24 mm 자세의 바닥 접촉과 lifted≥10 mm 요구를 동시에 참으로 만들 수 없다. unloaded 값을 복사하거나 상승 gate를 삭제하지 않는다 |
| 학생의 보이지 않는 hover와 높은 후보 채택 | 현 hover의 edge 소비를 승인하지 않는다. 실제 RGB/BeamEdgeTracker와 전체 전이·운반 검증 후 별도 학생 자세·번들·계약으로 채택 여부를 결정한다. 높은 후보의 카메라/쌍 모형을 hover에 복사하지 않는다 |
| 8초 준비·측정 구간 | **v92 전용 사전 구간 선택을 허용하되 1 mm/0.1° 잔차·최소 표본 기준은 유지**하는 방안을 권고한다. 전체 raw를 보존하고 경계 시각/명령 전 캡처 규칙을 명시한다. 기존 v88/B′를 소급 변경하지 않는다 |
| v92 조립기와 혼합 명령 | 기존 v88/370초/반대부호 가정의 reader를 우회하지 말고 별도 v92 감사 경로를 만든다. ID·720초·일정 해시·샘플 수·역할을 확인하고 common-orbit와 relative-yaw를 분리한다. 입력 rank 3만으로 새 13계수 식별/내부해가 보장되지는 않는다 |
| 팬 범위와 자세별 모형 범위 | loaded pan 적용은 우선 **1480–1520**으로 한정한다. 더 넓은 runtime 사용은 별도 수집이 필요하다. 높은 후보에서도 motion 모델이 필요한 쌍 적합이라면 hover motion fit의 전용 가능성을 따로 검증하거나 후보 자세에서 측정한다. 어느 방향의 자세 간 복사도 자동 허용하지 않는다 |
| 전체 수집 진행 순서 | 이 PR은 탐색용 수집 설계로 보존할 수 있다. 보정 승인에 쓸 reader/구간/상태/모형 결정은 먼저 고정할 것을 권고한다. 이후 조정자가 전체720초의 접촉 선별, 실제 RGB, 높은 상대회전과 복귀, 288개 **선별 후** 지지, 새 적합을 검증한다. 현재 짧은 재현을 그 인수로 대체하지 않는다 |

## 독립 실행·검증 증거

대상 SHA에 커밋된 `probe_headless.py --mode posture`와 `--mode motion`을 기존 Python 환경에서
**각각 새로 실행**했다. 이는 작성자의 숫자를 재인용한 것이 아니라 같은 seed·같은 짧은
진단의 재현 확인이며, 독립 확증 코호트나 실제 720초 일정 재생은 아니다.
`render=False`, 외부 모델 호출0. 제 `sim-codex-review361` 슬롯만 사용했고 정상 종료·해제를
확인했다(`concurrent_holders=[]`, `physics_holder=null`). 기존 실행 프로세스는 변경하지 않았다.

| 점검 | 전체 표본(초기 구간 포함) | 지정 구간의 유효 접촉/상승 | 추가 관찰 |
|---|---|---|---|
| posture, 66 SIM초, 52명령 | 1,321: lifted 1,239, not_lifted 82 | **1,160/1,160**, [8,66) s | hover→110→130→150 mm, 높은 자세 ±20 팬; 최소 빔 바닥 63.013 mm |
| motion, 70 SIM초, 908명령 | 1,401: lifted 1,319, not_lifted 82 | **1,240/1,240**, [8,70) s | hover 공동회전 ±.04와 hover ±20 팬; 최소 빔 바닥 62.998 mm |

모든 유효 표본은 빔 바닥≥10 mm·네 집게 접촉·외부 지지 없음·active weld 없음이다.
커밋된 요약기와 별도로 frozen B′ `loaded_selection`을 넣은
`scripts.final_pair_calibration_io.loaded_mask`로 두 raw를 다시 분류해 전체 카운트가 같음을 확인했다.
실패/초기 82개를 삭제하거나 성공률 분모에서 숨기지 않았다.
motion 끝 5초의 빔 yaw 속도는 **+0.03632125 / −0.03629047 rad/s**;
두 로봇도 각각 같은 부호였다. 13개 계수 적합 결과는 아니다.

부하 평균(1/5/15분)을 각 실행에 보존했다. posture 시작 `[28.378,20.442,17.130]`,
종료 `[14.246,21.508,18.650]`; motion 시작 `[13.585,21.250,18.576]`,
종료 `[21.784,21.484,19.089]`. wall 속도 비교는 하지 않았다.

추가 로컬 회귀는 다음 **103 passed in 214.67s**. 이 통과와 앞의 카탈로그 **2 failed**는 별개다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_final_pair_loaded.py tests/test_zone_final_pair_fast.py \
  tests/test_final_pair_fast_guard.py tests/test_agent_sim_slots.py
```

`git diff --check`, `bash -n .../collect.sh`, `sim_cli workflow run zone-final-pair-loaded-v92 -- ...`
(`--execute` 없음), 원본 gzip↔생성 schedule 바이트 일치, 보존29개 해시 대조를 확인했다.
렌더링·모델 호출·전체720초·새 fitting·학생 인수·실물 시험은 하지 않았다.

## 보존 위치와 TensorBoard

검토 raw·로그·재검색·대조 JSON은 모두
`/Users/changmin/projects/ugrp/outputs/review-361-a9481446-20261003/`에 있다.
로컬 보관이며 raw 원격 백업을 주장하지 않는다. UGRP 예외에 따라 Google Drive 작업은 없다.

| 기록 | SHA-256 |
|---|---|
| `posture/artifacts.sha256.json` | `564be6c4241d2cb3ac48ded45b312b63ece8137306c50bb121cca63022e967ed` |
| `motion/artifacts.sha256.json` | `f1cbfcd5d3ef60f5eedf51de93db8751e380a4a93a9a1ab272831459a2fabc32` |
| `reservation_rescan.json` | `9bbfd7294a204a594ef2a0da3a17442ada74e62686889985a769872ff8c6eabe` |
| `reservation_final_rescan.json` | `3d89f7f318a2119b1c67a7c1a5981dbdf444c0e45b02a2471125f0fccb14b618` |
| `preservation_check.json` | `2d44265ba58cc0209ef076204a0f117c3329f4c48b1a99e7d4f04b27f6e368a0` |
| `v88_scene_comparison.json` | `9ed87539d2c3a3c0a316ba1290e3bc24a03ec31511fe1376b6c19945327d3ab5` |
| `workflow_failures.log` | `371538766573e1dde0b6ea827126f4319f467d08d3ade683841d430318686c3a` |

새 native TensorBoard snapshot은 공용 루트의 `1003-v92-review361/{posture,motion}`이다.
EventAccumulator와 기존 서버의 run별 API에서 모든 scalar를 원본과 대조했다.
기존 `1003-v92-loaded-design-r2`와 구분해서 표시하며 합산하지 않는다. 새 영상0개,
운반 성공·wall 시간·모델 응답 시간은 값이 없으므로 만들지 않았다.
서버 PID 54928과 HTTP의 공용 logdir를 확인했으며 재시작/변경하지 않았다.
`ps` 명령줄 조회는 sandbox가 거부했다.
Chrome `강`의 기존 탭에서 기준/검토 run 4개, 경계 열0/90, 명령52/908,
SIM66/70초, 모델 호출0 표시를 확인했다. HParams는 설정 파일의
`outcome`, `result/wall_s`, `result/commands`, `result/model_calls` 네 열로 다시 맞추고
헤더를 확인했다. 새 HParams 행 자체는 개별 화면 검증하지 않았다.

대시보드의 정확한 pin 링크·UI 검증 범위는 검토 raw의 `tensorboard_verification.json`,
공용 `outputs/tensorboard-view.json`의 **`v92_review361_20261003`** 키에 보존한다.
[검토와 기준 run 보기](http://127.0.0.1:6006/?runFilter=%5E1003-v92-%28review361%7Cloaded-design-r2%29%2F&scalarSmoothing=0#timeseries).

**남은 조건:** P1 수정 및 새 SHA CI, 새 HIGH/B″ 후보의 변경 범위 독립 재검토,
위 조정자 결정, 전체 RGB 수집·보정·학생 인수.
이번 검토에서 PR 병합과 기본 checkout 갱신은 수행하지 않았다.
