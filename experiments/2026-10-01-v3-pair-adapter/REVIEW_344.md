# PR #344 독립 검토

**판정: BLOCK — 현재 후보의 학생 실행·보정 수집 인계를 그대로 승인할 수 없다.**

- 대상 SHA: `45c4ebc43daa96542cf298cea6f69964e501ec4a` (`codex/v3-pair-adapter`).
- 기준 main: `78ce79162d907d88d38ef3afcfc0c62e4a72aaba`.
- 비교: #342 `04eb11c6a001f2a7d2ab916765d59b3661c06efe`, #346 `a5cc1402049a249253893762e1ca347e448a5f3f`, #292 `266118d2c2337bbf1cff507690da131c63e2db11`.
- 검토자: Codex, 별도 `codex/review-344`에서 검토 문서·검사만 작성. 대상 구현을 수정하지 않았다.
- 물리 step·모델 컴파일·렌더링·실제 모델 호출 **0회**, host lock 사용 없음. 아래 수치는 정적/가짜 backend/NumPy 검사다.
- **P1 2건, P2 2건**을 한 묶음으로 전달한다. 코드 반례와 기록 요건 검사를 합쳐 **strict xfail 7개**다. xfail은 수정 완료가 아니다.

## 한 묶음의 지적

### R1 · P1 — 카메라의 실제 차체 원점을 바닥 원점처럼 투영한다

위치: `harness/zone_final_pair_vision.py:62`, `harness/vision_pose_source_pair_v3.py:78`,
`sim/final_pair_v3.py:85`.

수집기는 `rb.T @ (cam.xpos-base.xpos)`를 저장한다. 계약도 **optical→actual chassis base**라고 명시한다.
그런데 `PairVision.base_rays()`는 그 origin을 그대로 반환하고, 바이트가 보존된 beam 알고리즘은
**바닥 위 0.032 m** 평면과 교차한다(`harness/owncam_pair_beam_v2.py:87`). PF의
`measured_column_model()`도 같은 origin에서 **z=0을 바닥**으로 사용한다
(`harness/vision_pose_source_final.py:51`). 차체의 바닥 위 높이·기울기를 변환하는 단계가 없다.

반례: 수평 차체 원점 높이 0.03236 m, 차체 기준 카메라 `(0.15,0,0.20)`, 아래로 45°인 광선.
실제 바닥 기준 beam top 교점 x는 **0.35036 m**지만 새 beam 경로는 **0.31800 m**로 추정한다.
**32.36 mm 오차**는 새 정렬 허용치 ±3 mm보다 크다. 같은 합성 변환으로 PF 바닥 광선도 틀어진다.
0.03236 m는 합성 반례의 고정 상수이며 실행 중 GT를 학생에게 제공한 것이 아니다.
#346 README도 수집된 origin이 바닥보다 약 32.36 mm 높은 몸체 원점 기준임을 명시한다.

수정 요구: 정적·오프라인 보정에서 floor-aligned 기준으로 변환해 계약과 두 소비자를 맞추거나,
정적 base→floor 변환을 필수 자산으로 넣고 두 투영 경로에 일관되게 적용한다.
실행 중 실제 base 높이/회전을 읽어 보정해서는 안 된다. 지면·beam 평면의 알려진 광선 교차 회귀가 필요하다.

검사: `test_measured_chassis_camera_projects_to_the_floor_and_beam_in_the_same_frame` — strict xfail.

### R2 · P1 — 식별 실패한 운동 자극을 반복하고, loaded gain/deadband를 구별할 수 없다

위치: `harness/zone_final_pair_calibration.py:62`, `scripts/run_final_pair_v3.py:71`.

| 수집 | r1 축별 명령 | 연속 자극 | r1 운동 시작 시각 | 자세/카메라 라벨 |
|---|---|---|---|---|
| unloaded | ±0.03 | 0.25 s×4 = **연속 1 s**, 축당 양/음 각 1회 | 72,77,82,87,92,97 s | 0.2 s |
| fine | ±0.015 | 위와 같은 1 s 패턴 | 위와 같음 | 0.2 s |
| loaded | ±0.03, r2는 반대 부호 | 위와 같은 1 s 패턴 | 12,17,22,27,32,37 s | 0.2 s |

네 번은 정지 사이가 있는 독립 0.25초 펄스가 아니다. 같은 명령의 lease 갱신이다.
모두 원본 `configs/final_environment_measurement_v1.json`의 자극 형태를 재사용하며
fine은 크기만 절반, loaded는 시각만 60초 앞당겼다.

#346의 고정 `fit_report.json`에서 전진/측면 `gain_lag_identified=false`다.
전진 최솟값 gain **1.78459**, τ **1.44 s**, RMS **0.08980 mm**이고,
측면은 gain **2.40680**, τ **3.00 s**, RMS **0.07759 mm**다.
보고서는 더 큰 gain·τ 조합이 비슷하거나 더 작은 잔차를 내므로 적용값을 null로 남겼다.
세 지도의 동일 seed·명령 반복은 새로운 운동 자극을 추가하지 않는다.

추가로 loaded에 필요한 gain/deadband는 이 일정에서 **구조적으로 구별 불가**다.
동일한 lag를 갖는 다음 두 모델은 모든 수집 명령(0, ±0.03)에 완전히 같은 유효 속도를 낸다.

- A: gain=0.5, deadband 없음 → ±0.015.
- B: gain=1, c0=0.01, u1=0.05 → `u*clip((abs(u)-c0)/(u1-c0),0,1)` = ±0.015.

하지만 수집하지 않은 u=0.06에서는 각각 0.03/0.06으로 두 배 차이다. 시간상수가 같으면
전체 시간 응답도 같아서 표본 간격만 줄여도 이 반례를 해결하지 못한다.

범위 구분: v88은 `eval_only/trajectory.jsonl`의 **qpos/qvel을 0.05초**마다 추가 저장한다.
따라서 “모든 평가 자료가 0.2초”라는 주장은 틀리다. 자세/카메라 라벨은 0.2초이고,
전진·측면 gain/lag 재식별은 아직 입증되지 않았다. unloaded의 실패한 설계를 반복하므로
같은 적합법으로 식별 가능한 보정이 나올 것으로 인계할 수 없다. fine/loaded의 실측 gain/lag 실패를
새로 관측한 것은 아니며, loaded의 gain/deadband 반례는 표본 주기와 무관한 별도 증명이다.

수정 요구: 서로 다른 충분한 지속시간·명령 크기·정지 구간을 갖는 새 schedule을 버전 고정하고,
각 필수 parameter의 식별성을 오프라인으로 확인한다. #347은 이미 v89 측정 v2를 따로 예약했으므로
번호·계약을 조정해 중복 구현을 피한다. loaded/fine을 식별 불가 상태에서 MEASURED_SIM으로 채우지 않는다.

검사: `test_collection_changes_the_gain_lag_excitation_that_v87_could_not_identify` 3개와
`test_loaded_schedule_can_distinguish_two_required_gain_deadband_models` 1개 — strict xfail.

### R3 · P2 — 관측·팔 실행 시계의 변경이 번들에 명시돼 있지 않다

위치: `scripts/run_final_pair_v3.py:71`, `harness/zone_final_pair_contract.py:165`.

기존 host의 배경 RGB는 0.2초이고, pair 제어 시점에는 추가로 fresh frame을 요구한다.
새 학생 경로는 상태와 무관하게 **0.05초마다 두 카메라를 capture하고 provider에 전달**한다.
120초에 카메라당 2,401회다. controller 자체는 여전히 0.1초이므로 제어 주기만 기록하면
PF 관측 빈도·추론 호출 수 변화가 보이지 않는다.

기존 팔은 각 physics step에서 `now >= next_arm`을 검사하고 `next_arm=now+0.05`로 갱신한다.
새 경로는 reset 종료를 기준으로 한 0.05초 격자에서만 `arm_step()`을 부른다.
0.00025초를 누적하는 가짜 시계에서도 기존 호출이 0.30025/0.35050/0.40075초,
새 격자는 0.30000/0.35000/0.40000초로 달라진다. 명목상 0.05초가 같다고 바이트 단위 궤적이 같지는 않다.

번들은 source closure를 해시로 고정하므로 코드를 읽어 재구성할 수 있다. 그러나 적용 timing/observation 값과
부모 대비 변화 목록은 없다. 새 변형임을 명시한 것은 옳으며, 이것을 봉인 실행의 재생으로 세면 안 된다.
수정 요구는 이 실효 주기·phase·stabilization·보정 선택과 부모 대비 차이를 bundle/실행 기록에 명시하는 것이다.

검사: `test_bundle_explicitly_records_changed_frame_and_arm_clocks` — strict xfail, 기록 요건 검사.

### R4 · P2 — 기존 “독립 검토”의 원문과 검토자를 확인할 수 없다

위치: `experiments/2026-10-01-v3-pair-adapter/verification.json:49`, 같은 디렉터리 `README.md:54`.

PR 본문의 주장은 이 구현 커밋 안의 `independent_review` 요약과 연결된다.
요약은 standoff projection, 파지 반경, 문 후 envelope, 유한 자세, partner deadband,
축별 lag의 **6개 수정**과 `draft ready within reviewed offline scope`를 기록한다.
별도로 `independent_review_elapsed_s=20.03`도 있으나 **검토자/agent 식별, 검토한 SHA 또는 파일 hash,
원문 report/댓글/리뷰 링크가 없다**. 검토 시작 시 GitHub reviews/comments도 각각 0개였다.

따라서 실제로 독립된 사람이거나 별도 agent가 검토했는지는 공개된 저장소/PR 근거로 확인할 수 없다.
같은 계정/Co-Author라는 이유만으로 자체 검토라고 단정하지 않으며, 비공개 검토가 없었다고도 단정하지 않는다.
하지만 이 요약을 독립 승인 완료 증거로 사용할 수는 없다. 원문·검토 주체·대상 revision을 연결하거나
문구를 “작성자 제공 검토 요약, 독립성 미확인”으로 한정해야 한다. 이번 보고서는 별도의 독립 검토다.

검사: `test_claimed_independent_review_identifies_reviewer_revision_and_original_report` — strict xfail, 감사 가능성 검사.

## 봉인 보존과 동작 차이 전체 대조

`git diff main...45c4ebc4`에서 기존 제어기·localizer·port·render 파일은 변경되지 않았다.
핵심 **17개 파일**을 main/#342/후보의 Git blob과 각각 대조해 모두 byte 일치를 확인했다.
파일별 SHA-256은 [증거](REVIEW_344_EVIDENCE.json)에 있다. 기존 source-pinning/registered-source 검사도 통과했다.
이는 **b-v6g 핵심 파일 보존**이다. #292 b-v6h1 구현 전체와 동일한 실행 바이트라는 뜻은 아니다.
새 모듈이 `FunctionType`의 private globals와 인스턴스 subclass로 함수를 감싸고 실제 동작을 바꾼다.

아래 “해시만”은 구현 소스가 bundle closure에 포함되지만 실효 값/부모 대비 변화가 bundle 필드에 없는 경우다.

| 항목 | 봉인 v6-family / #292 기준 → v88 | bundle 선언 |
|---|---|---|
| 환경·로봇 | v2 계열 → 최종 v3 지도 3개, masterpi_v3, floor_light_v1 | map hash/model/render/contact/weld/sensor 명시 |
| 카메라 물리·원본 변환 | 기존 v3 mount/FOV·fisheye 변환 유지, robot_cam 640×480 JPEG 유지. PIL RGB decode로 provider 전달. 별도 crop/flip/카메라 이동 없음 | contract 크기·mount hash, 나머지 해시 |
| 카메라 기하 | v2 FK/train sag·pan 보정 → 자세·loaded/unloaded별 실측 optical→actual chassis 변환; pan yaw 적용 | contract와 source hash, 실측 파일 hash는 provider record. **R1** |
| 인식·pose | 해당 v6 tag/recovery 경로 대신 VIS3 segmentation/interval likelihood + v3 pair motion; 기존 worker 모델 재사용. 정확도 승계 없음 | variant/input/contract, 내부 config·worker 자산은 source/provider 기록 |
| 첫 prior | seeded robot row 없이 공용 dock 영역 평균, σx=.15, σy=max(.15,row range), σyaw=.174533 | 해시만; README/handoff에 영역 설명 |
| 관측·제어 | 배경 0.2 s+제어 시 fresh → 학생 RGB/provider 0.05 s 고정. pair CONTROL_S=.1, LOOK_EVERY_S=.4 유지 | timing 필드 없음, **R3** |
| 팔 실행 시계 | physics-step 기반 `now+.05` gate → reset 기준 .05 s 격자 | 해시만, **R3** |
| 안정화 | 표준 Scene.setup/constructor 정착 경로 유지. v6 최종 하강 settle .3 s, hover 1 s, 하강 7×.12 s 유지. 일반 relook/close/lift settle은 봉인 함수 상속 | 해시만; 실제 v3 정착 검증 없음 |
| 파지 | 반경 .162→.2032 m, X ±.012/Y ±.008→각 ±.003 m; yaw ±.035 rad 유지. 관측 위치별 연속 IK → 공통 유한 v3 pad IK 자세 | 해시만; handoff 수치 명시 |
| 시점 선택·beam 기하 | 반경 차이만큼 posture-switch 기준 이동; standoff/partial/align/released에 실측 rays, 기존 hue widening 유지 | 해시만 |
| 정적 경로 | v3 mount를 포함한 envelope, 문 전·후 전체 편대+5 cm 여유, leg≤.85 m/최대8 유지; 복도는 [1,1.2,0]→A, 문은 [1,.05,0]→B | map/variant는 명시, task/route 수치는 해시·run plan |
| checkpoint | 기존 realign의 0.15 m backoff 경로 대신 곧바로 stop/relook→RGB align→grasp/lift. 같은 PF/불확실성 유지, old receipt 무효화 | 해시만; handoff에 새 chain 설명 |
| 운동 gain·lag | v2 FORWARD_GAIN=2.2/1.4, LEFT_GAIN=1.65/1.4 및 #292의 0.9483378899463337 보정 대신 실측 3×3 gain/deadband 역산. align·axial/lateral leg에 축별 lag 사용, 불가능 명령은 clip 대신 거부 | calibration requirement와 variant, 실제 숫자는 아직 없음. **R2** |
| PF 운동·yaw | v3 command FK LoadState, loaded scale/bias/drift, 정적 역할에서 유도한 partner 명령에도 deadband 적용; beam-edge fit은 v3 파일 필수 | 해시·calibration requirement; peer live 값은 쓰지 않음 |
| scan/resampling | informative geometry가 없으면 fix 시각 갱신 금지; pose/scale/stuck과 yaw_bias/yaw_extra/drift를 함께 resample | 해시만; 기존 pose-only resampling과 다름 |
| guard | b-v6g의 k=2·loaded yaw3°에서 #292 계열 kxy=kyaw=1, loaded5°/4°, moved-fix p2f. v3 arm mount/pad geometry, residual≥.015 m, 무추정 blind sweep 금지 | family/variant+해시, 수치는 handoff. p2f 미무장 사각은 유지 |
| 메시지·완료 | 기존 pair dispatch/독립 제출/enum STATUS·barrier, rendezvous5 s/heartbeat .15 s 유지. Runtime은 두 actor에 각자 static task 제출; owncam judgments 비활성. 완료는 unqualified receipt | inputs 명시, 세부 해시·student record; physical_success=null |
| 지연·예산 | P03 delay wrapper 한 번, .16 SIM s 유지. 각 reset≤5 s + case120 s, P03 3 checkpoints/나머지3 maps | case/result/handoff 명시. bundle 자체에는 caps/timing 없음 |

실측 camera/gain/lag/불확실성 숫자가 없는 상태여서 적용값의 물리적 타당성을 검증하지 않았다.
정착 .3초의 유지도 v3에 충분하다는 증거가 아니다. #346의 camera 전이 관찰과 후속 실측 인수가 필요하다.

## 학생 경계·환경·예산의 통과 범위

- **입력 경계:** `Runtime`은 world/port/eval 인자를 받지 않는다. 자기 obs/RGB만 해당 actor에 전달한다.
  `CameraRobotPort.capture()`의 actuator_state는 발행 명령이고 실제 관절 측정이 아니다.
  실제 `PhysicsBackend.capture()`에 서로 다른 가짜 body/camera GT를 넣어도 반환 obs·RGB는 같고
  `eval_only` 라벨만 달라졌다. partner의 카메라가 다른 actor에 전달되지 않는 것도 확인했다.
  partner 운동 추정은 공통 정적 경로·역할에서 유도한 명령이며 peer 실제 상태를 읽지 않는다.
  공용 top RGB는 이 실행기에서 사용하지 않는다.
- **교사 분리:** `make_scene()`의 station 재배치는 정확히 `check=='calibration-loaded'`일 때만 수행한다.
  `run_case()`는 모든 calibration check에서 Runtime을 만들지 않는다. p03/carry에서는 dock reset만 사용한다.
  CLI의 check allow-list와 factory 호출을 추적하고 5개 check×3사례를 가짜 backend로 실행했다.
  보정 파일 없는 p03, PARTIAL, v2, loaded profile 누락은 물리 import 전에 거부됐다.
- **GT/성공/weld:** 평가 메서드의 결과가 명령·단계 선택에 반환되지 않는다. 실제 평가 메서드에 active weld를
  주입하면 `WELD_OFF_VIOLATION`으로 중단한다. checkpoint는 old lift/open만으로 달성되지 않고
  `SEQUENCE_OBSERVED_UNQUALIFIED`에도 physical_success는 null이다.
- **floor_light_v1:** #342와 `sim/render_profile.py`, map/robot/camera/접촉의 공통 소스가 byte 동일하다.
  `install()`을 world 생성 전 적용하고 `verify_model()` 실패를 run_case의 HOST_ERROR로 처리한다.
  그림자·반사·spot cutoff·어두운 바닥·바닥 누락 5종을 가짜 model audit으로 주입해 정리를 확인했다.
  #342는 constructor 직후/reset 전 검사, #344는 reset 뒤/학생·수집 loop 전에 검사한다.
  정의는 shadow OFF, reflectance0, cutoff180, 광원 색×.3, ground rgb1=(.36,.35,.34)/rgb2=(.62,.61,.59)로 같다.
  실제 영상 밝기나 컴파일된 MuJoCo 배열을 이번 검토에서 확인한 것은 아니다.
- **v87/v88 관계:** 동일 프로필의 서로 다른 named workflow/bundle이며 덮어쓰는 이중 정의는 발견하지 못했다.
  #342는 빈 team cargo/3로봇 PNG·원본 unloaded protocol이고,
  #344는 beam task/loaded 교사 staging/2로봇 JPEG·수정 schedule이다. 같은 전체 환경·측정 코호트가 아니다.
  계약 hash도 v87 `6666b23b…`와 v88 `c834b8d2…`로 다르다. #346 PARTIAL을 v88 보정으로 자동 승계하지 않는다.
- **caps:** 가짜 reset을 매번 최대 5초로 해도 사례당 종료 125초, P03 및 각 수집 묶음 모두 **최대375 SIM초**다.
  5.00025초 reset은 명령/capture 전에 HOST_ERROR다. 실제 world step cap/advance 구현은 기존 v84 것을 재사용하고
  관련 테스트가 통과했다. ENOSPC·cleanup·미시도 분모 보존은 기존 새 경로 테스트를 재실행했다.
  과거 성공률·physical acceptance·E2E 승인은 이 결과에 포함되지 않는다.
- **번호:** 조회 시 main+열린 PR **20개 전체**의 고정 head에서 harness/configs를 검색했다.
  #339 `zone-target-v86`, #342 `zone-final-environment-v87`, #344 `zone-final-pair-v88`로 충돌 없다.
  #346은 v87을 상속한 적합 PR이고, 이후 #347은 `zone-final-environment-v89`를 예약했다.
  v88의 별도 등록이나 workflow3.1.0의 충돌은 발견하지 못했다. ref/SHA/검색 결과는 증거 JSON에 보존했다.

## 검증·재현·보관

| 검사 | 결과 |
|---|---|
| PR의 관련 9개 offline 파일 | **285 passed, 1 deselected**, 150.28초 |
| 제외했던 기존 자식 정리 검사 별도 실행 | **1 failed, 17 deselected**, sandbox의 `ps` PermissionError. 구현 실패로 합산하지 않음 |
| 독립 검사 `tests/test_review_344.py` | **18 passed, 7 strict xfailed**, 107.63초. 코드 반례5개, 기록 요건2개 |
| 봉인/공통 소스 보존 | 17개 파일×main/#342/후보 hash 일치, `.github/workflows` diff 없음 |
| 대상 PR CI | 조회 시 normal CI 33개 check 모두 SUCCESS. 위 새 반례를 해소하지 않음 |

실행은 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 재사용했다.
테스트에서는 native engine·torch·network·실제 worker를 차단했다. 별도 환경·서버·잠금은 만들지 않았다.
archive의 역사 blob 조회 검사를 위해 scratch 내부 Git의 object alternates를 기존 저장소의 객체에 연결하고
HEAD/index를 대상 SHA로 설정했다. 원래 저장소·대상 branch 소스는 수정하지 않았다.

```bash
REVIEW_TMP=$(mktemp -d /private/tmp/ugrp-review-344.XXXXXX)
git archive 45c4ebc43daa96542cf298cea6f69964e501ec4a | tar -x -C "$REVIEW_TMP"
REVIEW_344_ROOT="$REVIEW_TMP" /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  -m pytest -q tests/test_review_344.py -rxX
# 자신이 만든 위 scratch만, 검사 종료 뒤 제거한다.
```

원래 실행한 관련 파일 목록·로그 hash·PR 조회·보존 hash는 [REVIEW_344_EVIDENCE.json](REVIEW_344_EVIDENCE.json)에 있다.
새 실험 코호트·영상·학습 모델을 만들거나 회수한 작업이 아니므로 TensorBoard 변환/표시는 하지 않았다.
UGRP 예외에 따라 Drive를 사용하지 않았다. 검토 자료는 이 branch로 보존한다. 직접 만든 `/private/tmp/ugrp-review-344.F0Ih7H`는
검사 로그 원문·해시를 증거 JSON에 옮긴 뒤 삭제하고 부재를 확인했다.
수정 후에는 변경 범위를 다시 독립 검토해야 하며, 물리·렌더 인수는 이 검토와 별도다.
