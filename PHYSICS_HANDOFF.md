# 최종 v3 공동 운반 v88 인계 — DRAFT, 미봉인

v88은 `floor_light_v1`의 세 최종 v3 지도에 공동 운반을 연결한다. 보정 수집은 두 문 지도 한 곳이다.
**v88은 한 번도 실행되지 않아 REVIEW_344 수정은 같은 번들에서 개정했다.** 과거 실행을 다시 이름 붙이지 않았다.
**이번 검증은 fake/offline만 수행했다. 물리·렌더·모델 추론·P03·운반 성공 결과는 없다.**
학생 실행은 실측 v3 보정 파일의 해시·조합·필수 자세 coverage가 없으면 시작하지 않는다.
아래 v87 인계와 v84 기록은 각 번들의 당시 지침으로 보존한다. v88 실행에는 위쪽 v88 명령만 쓴다.

## v88 조합과 검증 경계

- 번들 `zone-final-pair-v88`, workflow `zone-final-pair-v3` **3.1.0**.
  최초 조회 최댓값은 #339의 v86 / zone workflow 2.19.0이었다. 커밋 전 재조회에서
  #342/#343의 v87 / 2.20.0을 확인해 이 미실행 후보를 v88로 등록한다.
  전체 workflow 최댓값 3.0.0 다음인 3.1.0을 사용한다.
  [최초 조회](experiments/2026-10-01-v3-pair-adapter/reservation_scan.json)와
  [최종 조회: main + 열린 PR 15개](experiments/2026-10-01-v3-pair-adapter/reservation_final.json)를 보존한다.
- 표준 `sim_cli`/workflow manager가 `configs/simulation_workflows.d/final_pair_v88.json`을 읽는다.
  봉인된 기본 catalog·v2 제어기·기존 번들·봉인 검사는 수정하지 않는다.
  `FinalV3Scene`은 표준 `Scene`의 구성·reset·물체 생성과 v3 robot 변환을 재사용한다.
- `masterpi_v3`, `cargo_noslip_v1`, weld OFF, 초음파 OFF, `floor_light_v1`.
  자기 `robot_cam` 640×480만 제어기에 들어간다. 카메라/FOV·로봇·물체 외관은 유지한다.
  기존 seg-v2 인식망 재사용은 새 밝은 바닥에서의 정확도 검증이 아니다.
- `b-v6h1-v3-measured`는 등록된 b-v6g skill의 인스턴스 wrapper에 #292 b-v6h1 계열의
  kxy=kyaw=1 sweep margin, loaded yaw 5°/4° gate, moved-fix p2f, 축/횡 lag 모델을 연결한
  **새 변형**이다. v2의 0.948 gain 보정·v2 카메라/FK·운동 fit·성공 판정을 승계하지 않는다.
  p2f는 움직인 뒤 새 fix가 없으면 baseline을 잡지 못하는 기존 한계가 있다.
- v3 파지 목표는 arm 모델의 정적 station radius 0.2032 m, 정렬 X/Y 허용치는 각각 ±3 mm다.
  열린 하강/파지/상승 PWM은 유한한 공통 목록 `grasp_postures()`를 사용한다.
  RGB에서 이 범위를 벗어나면 파지를 거부한다. 허용 오차 내 실제 파지는 물리 인수 대상이다.
  보정되지 않은 중간 PWM에서 정지하면 provider는 명시적으로 실패하며 v2 FK로 대체하지 않는다.
- 문 지도 두 개는 정적 빔 배치 `[1,.05,0]`에서 B로, 복도 지도는 `[1,1.2,0]`에서 A로 간다.
  coarse order는 실행 전에 고정한다. seeded robot→dock row 정보는 학생에게 주지 않으며,
  초기 PF는 공용 지도에 공개된 dock 영역으로만 한 번 초기화한다.

## 보정 수집 — 모델/기존 loaded fit 없이 실행 가능

세 수집 종류는 각각 **한 지도 × 370 SIM초 + reset 최대 5초 = 최대 375초**다.
지도는 `zone_wide_two_doors_final_v3`로 고정한다. P03/운반의 3×120초는 유지한다.
기존 세 지도 반복 분모를 한 지도 장시간 자극으로 바꾼 것이며, 지도 간 보정 검증을 뜻하지 않는다.
원본 `final_environment_measurement_v1.json`과 #347의 실행된 v89는 바꾸지 않는다.
#347 `eaeaaff0`의 계단·PRBS/50 ms 평가/전체 경로 중단 설계를 v88에 적용했다.
#348 `dba873d4`는 선형 1차 모델 부적합, 크기별 gain, deadband와 약 0.84초 drive tau의 근거다.
그 실측값을 loaded/fine 보정값으로 복사하지 않는다.

- 모든 축(forward/left/turn)에 각 크기의 **양·음 10초 계단 + 1초 coast**,
  x^5+x^2+1 PRBS31(0.5초 chip, 중간 크기) + 2.5초 coast를 넣는다. 실제 lease는 0.05초다.
- `calibration-unloaded`: 크기 .01/.02/.03, 74–326초 운동.
  0–72초 원본 자세/pan, 330–342초 hover·grasp·p45·inspect·search. r1 고정 시작 `[3.25,-.85,0]`.
- `calibration-fine`: 크기 .004/.016/.028, 같은 시각; 70초 p45로 바꾸고 운동 중 유지한다.
- `calibration-loaded`: 크기 .006/.015/.025/.04. 데드밴드 아래·중간 두 수준·포화 영역을
  구별하는 설계이며, 실제 deadband 범위가 다르면 적합을 거부하고 새 설계가 필요하다.
  **교사 전용** 빔 시작 `[3.55,-.85,0]`의 정적 양끝 station에 두 로봇을 둔다.
  0초 open/grasp, 2초 close, 4초 hover, **12–330초 운동**, 334–355초 pan, 362초 open.
  r2는 세 축 모두 반대 부호인 고정 공동 진단이다. 하중 유지·강체 회전을 보장하지 않는다.
- 매 물리 substep 전후, 명령 직전, 0.05초 평가에서 로봇/팔·loaded 빔의 실제 geom 경계를 검사한다.
  벽 여유 0.30 m + 중단 buffer 0.05 m, 로봇 반경 bound 0.40 m,
  substep geom 이동 bound 0.01 m. 누락·NaN·초과는 hold 후 **HOST_ERROR로 중단**한다.
  GT는 이 교사 진단의 중단에만 쓰고, 명령 수정/경로 보정이나 학생에게 전달하지 않는다.
  전체 경로의 실제 여유와 loaded 성공은 실행 전 확정할 수 없다.

[오프라인 식별 결과](experiments/2026-10-01-v3-pair-adapter/identifiability_v2.json)는
#347의 정확 lag 적분·gain 해석적 적합·drive/stop tau profiling에 정적 비선형을 추가했다.
세 profile×세 축의 subtractive deadband 모델은 rank 3, loaded runtime ramp 모델은 rank 4다.
전진/측면에서 20% 다른 drive tau 대안의 최소 잔차는 fine 0.797–1.167 mm,
loaded 1.112–1.583 mm; loaded ramp는 0.833 mm다. 가정한 잔차 바닥 0.1 mm의 5배를 넘는다.
**조건부 설계 결과**다. #348 실제 잔차 약 1.8 mm 및 PRBS 잔차 3.4–4.24 mm보다
낮은 합성 잡음 가정이며, 물리 데이터에서 같은 식별성을 보장하지 않는다. stop tau는 nuisance로
profile했고 20 Hz에서 검증된 보정값으로 채택하지 않는다. 실제 fit의 모델 형태·잔차를 다시 검토한다.

교사 위치·카메라 실제 transform·qpos/qvel·빔 궤적·접촉은 `eval_only/`에만 기록한다.
**요청한 loaded 상태가 실제 하중을 뜻하지 않는다.** 접촉·빔 상승·유지 구간을 오프라인에서
판정하고, 실패/낙하/정지 표본을 함께 남긴 뒤 적합할 loaded 표본을 선택해야 한다.
수집 완료 상태는 `COLLECTED_UNQUALIFIED`이며 보정 적합/물리 성공을 뜻하지 않는다.
각 own JPEG·발행 명령·frame metadata·요청 schedule·전체 artifact hash를 보존한다.
카메라 label은 optical→실제 chassis의 origin/rotation과 `chassis_to_floor`를 함께 저장한다.
후자는 world xy/yaw를 제거하고 차체 높이·roll/pitch를 보존한다. 유효한 정착 자세별/하중별로
오프라인 적합한 고정 변환만 학생에게 준다. beam/PF는 두 변환의 합성을 함께 사용한다.
실행 중 GT 높이·기울기 또는 nominal wheel radius로 보정하지 않는다. 이전 frame 계약 파일은 거부한다.

```bash
cd /Users/changmin/projects/ugrp-wt/integ-v3-pair-adapter
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
FINAL_BRANCH=$(git branch --show-current)
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-pair-v88-review344-NEW-COHORT
git status --short --untracked-files=all
"$PY" scripts/disk_report.py
"$PY" scripts/agent_lock.py status

# 정적 계획: 물리/renderer/model worker를 시작하지 않는다.
"$PY" -m scripts.sim_cli workflow plan zone-final-pair-v3 -- \
  --check calibration-loaded --expected-source-sha "$FINAL_SHA" \
  --output "$RUN_ROOT/calibration-loaded"

# 아래부터는 물리 담당 코디네이터가 수행한다. 기존 잠금이 있으면 실행하지 않는다.
(
set -euo pipefail
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v88 revised calibration 3 profiles x (370+5) SIM s, teacher only' --pid $$ --expected-minutes 90
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
for CHECK in calibration-unloaded calibration-loaded calibration-fine; do
  "$PY" scripts/ugrp_session.py run "final-pair-v88-$CHECK" -- \
    "$PY" -m scripts.sim_cli workflow run zone-final-pair-v3 -- \
    --check "$CHECK" --map-id zone_wide_two_doors_final_v3 --seed 911 --expected-source-sha "$FINAL_SHA" \
    --execute --lock-owner codex --output "$RUN_ROOT/$CHECK"
done
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
)
```

`RUN_ROOT`는 매번 새 경로로 바꾼다. 소스는 커밋·고정한 자기 worktree에서 실행한다.
ENOSPC는 `HOST_ERROR`; 이미 존재하는 출력·raw는 덮어쓰거나 삭제하지 않는다.
수집/적합 후 승인된 실측 파일은 schema `ugrp.final_environment_measured_calibration.v1`,
status `MEASURED_SIM`, 새 contract hash, 세 map hash, `floor_light_v1`, source SHA와 measurement
manifest hash를 포함해야 한다. `params.motion`, `params.motion_loaded`, `params.motion_profiles.fine`의
3×3 gain·lag·noise·scale, loaded load_transition/deadband/drift/yaw spread,
`pair_model.slope_to_yaw_ratio`·`b_rad_s` 네 조건, `pan_base_yaw`와 unloaded/loaded
`camera_models`의 `frame=optical_to_actual_chassis`와 `chassis_to_floor`가 필수다. `required_camera_poses()`의 모든 settled 자세를 실제로 측정한다.
이 PR은 fitting·정확도 승인·실측 파일 생성을 자동으로 수행하지 않는다.

## 실제 관측·팔 실행 시계 (bundle.timing / result.timing)

- 기준 시각은 표준 reset 종료 `t_start`. eval pose/qpos/qvel은 `t_start+n×0.05초`.
- 학생 RGB 두 대 capture/provider 전달은 **0.05초 고정**, 처음/끝 포함 120초에 대당 2401장.
  기존 배경 RGB 0.2초 + 제어 시 fresh capture에서 바뀌었다. settled/initialized 조건에 따라
  실제 inference 수는 달라지며 모든 전달 frame이 추론 1회라는 뜻은 아니다.
- 수집 RGB/camera label은 기존 **0.2초** 유지(370초에 대당 1851장), pose는 독립 0.05초(7401개).
  #347의 5초 RGB보다 촘촘하며 v89와 같은 관측 코호트로 합산하지 않는다.
- 순서는 eval → capture/provider → 고정 수집 명령 또는 Runtime.step → arm_step → advance.
  제어 gate 0.1초, LOOK_EVERY 0.4초, P03 지연 0.16초는 유지한다.
- 팔 dispatch는 **reset 기준 0.05초 격자**다. 기존 physics-step `now>=next_arm`,
  `next_arm=now+0.05`와 위상/반올림 궤적이 다르다. 봉인된 실행의 동일 재생이 아니다.
- constructor 0.30초와 표준 Scene.setup은 reset≤5초 안에 포함한다. hover 1초,
  하강 7×0.12초, 최종 settle 0.3초와 나머지 상속된 arm queue의 duration/settle은 유지한다.
  이 값이 v3에 충분하다는 물리 승인은 없다. 자세별 보정 선택은 새 contract/hash로 고정한다.

## P03 — 독립 reset 세 번, 각 120 SIM초

각 사례는 dock에서 같은 실제 pair chain을 시작하며, 목표 checkpoint 도달 전까지 teacher staging,
PF 교체/재초기화, 빔 순간이동을 하지 않는다. 도달하지 못한 사례도 분모 3에 남긴다.
checkpoint는 lower→open→정지 재관측→RGB 재정렬→grasp→lift를 실행한다.
재관측은 같은 PF의 입자·불확실성을 보존하고 이전 fix receipt만 무효화한다.
새 capture의 pose는 고정 0.16 SIM초 뒤 전달되며 old fix를 새 fix로 사용하지 않는다.

문 지도에서 전체 v3 pair envelope와 5 cm 여유로 계산한 checkpoint는 다음과 같다.
문 전 x=1.4518(다음 segment 1), 문 후 x=2.9482(segment 3), 목적지 전 x=3.7741/y=-2.1(segment 7).
판정은 등록된 `checkpoint_segments`와 자기 제어기의 open/relift receipt로 남긴다.
`SEQUENCE_OBSERVED_UNQUALIFIED`도 실제 파지·위치오차·충돌 없음 또는 E2E 성공을 뜻하지 않는다.
평가자는 별도의 raw 궤적·접촉·영상으로 물리 판정을 해야 한다.

```bash
(
set -euo pipefail
CALIBRATION=/Users/changmin/projects/ugrp/outputs/REVIEWED-V88-CALIBRATION/measured.json
CALIBRATION_SHA=$(shasum -a 256 "$CALIBRATION" | cut -d ' ' -f 1)
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v88 P03 3 x 120 SIM s' --pid $$ --expected-minutes 90
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-pair-v88-p03 -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-pair-v3 -- \
  --check p03 --seed 911 --expected-source-sha "$FINAL_SHA" \
  --calibration "$CALIBRATION" --calibration-sha256 "$CALIBRATION_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p03"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
)
```

세 지도 E2E 시도는 같은 명령의 `--check p03`을 `--check carry`, 출력과 세션 이름을 `carry`로
바꾼다(세 지도 각 120초). 단일 지도 진단만 할 때 `--map-id`로 선택하며 분모도 1로 기록한다.
P03는 지도 필터로 세 checkpoint 분모를 줄일 수 없다.
`plan.json`, case별 `bundle.json`, `student_record.json`, `eval_only/`, `result.json`,
`artifacts.sha256.json`을 함께 회수한다. host error 뒤 남은 사례는 `unattempted`로 보존한다.
작업 끝에 자신이 만든 worker/세션 종료와 잠금 해제를 확인한다. 실제 결과 회수 후 코디네이터가
`docs/tensorboard.md`의 새 snapshot·영상·HParams·고정 카드 표시를 검증한다. Drive는 사용하지 않는다.

---

# 최종 환경 v87 물리 인계 — DRAFT, 미봉인

**밝은 렌더의 P01 3×30 SIM초 및 unloaded 수집 3×120 SIM초 경로를 등록했다. P03 연쇄는 아직 실행할 수 없다.**
P03 #312에 의존한다. v3 보정 실측과 v3 공동 운반 어댑터가 없으며, 기존
`OwnCamTeamHost`는 `v3 pair executor requires a separately migrated controller`로 거부한다.
이 제한을 우회하거나 기존 제어기를 v3로 표시하지 않았다. 이 문서의 등록/계획 확인은
실제 SIM, 위치 추정 정확도, 파지, 연쇄 완주 또는 사전 등록 봉인이 아니다.

## 고정한 조합

번들 `zone-final-environment-v87`, workflow `zone-final-environment-floor-light-check` 2.20.0.
2026-10-01 main + 열린 PR **16개 전체**를 조회했다. #339는 이미
`zone-target-v86` / `zone-target-checks` **2.19.0**을 사용하므로 다음 번호인
**v87 / 2.20.0**을 선택했다. 별도 M1 memory-v3 workflow의 3.0.0은 통합 2.x 계열이 아니다.
[조회 원본](experiments/2026-10-01-final-env-floor-light/reservation_scan.json)을 보존했다.

2026-09-29 사용자 결정에 따라 연구 코호트는 밝은 무그림자 `floor_light_v1`을 쓴다.
[P01 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)은
v84가 기본 렌더에 고정되어 어둡게 수집됐다고 기록했다. 이 결정은 이미 내려졌으며
이번에는 이를 새 버전으로 연결한다. **그림자가 있는 과거 결과와 합산하지 않는다.**
v84 등록 JSON·workflow·보정 계약·실행 소스 및 9개 생성 번들의 해시는 그대로 보존한다.
기존 `zone-final-environment-check` 2.17.0은 v84 재현용으로 남기며 새 명령은
별도 workflow ID를 명시한다. [기존 handoff 원문](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/5ba853ddc5b0e300e45f8361e98e7f9f16e08c18/PHYSICS_HANDOFF.md).


| P01 사례 | 지도 | 로봇 | 부모 |
|---|---|---|---|
| 문 1개 | `zone_wide_door_geometry_v3` | masterpi_v3 | 기존 geometry_v2, 기존 v3 파일 그대로 사용 |
| 문 2개 | `zone_wide_two_doors_final_v3` | masterpi_v3 | two_doors_final_v1 파일·정적 hash |
| 복도 | `zone_wide_corridor_final_v3` | masterpi_v3 | corridor_final_v1 파일·정적 hash |

기존 지도·catalog·v6e 등록·`configs/simulation_workflows.json`·과거 번들은 변경하지 않는다.
표준 관리자가 `configs/simulation_workflows.d/final_environment_v87.json`을 추가로 읽는다.
같은 ID 덮어쓰기는 거부하며 추가 catalog 파일도 관리 기록의 hash에 포함한다.
추가 장면은 표준 `CargoZoneScene`의 구성/초기화와 기존 v3 robot XML 변환을 재사용한다.
기존 v3 Scene allow-list를 넓히지 않는다.

공통 설정: `cargo_noslip_v1`, weld OFF, 초음파 OFF, `floor_light_v1` 렌더,
walls_v3 0.40 m, 자기 `robot_cam` RGB 640×480, 분할 480×360, seg-v2 해시
`348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9`.
기존 `sim.render_profile`의 밝은 바닥·무그림자 정의를 그대로 적용하고 실제 모델을 검사한다.
카메라/FOV·물체 외관·지도·접촉·명령 궤적·관찰 주기는 v84와 같다. C_mix_rgb는 채택하지 않는다.
P01은 기존 기본 색 상자 reset 구성이다. P02 혼합 주문·긴 빔 임무 배치를 검증하는 실행이 아니다.

## 실행 전 — 코디네이터의 자기 worktree에서

코드를 먼저 커밋하고 아래 SHA를 그 HEAD로 고정한다. 같은 코호트 중 소스를 바꾸지 않는다.
이 작업의 샌드박스에서는 SIM/렌더/학습/실제 추론을 한 번도 실행하지 않았다.

```bash
cd /Users/changmin/projects/ugrp-wt/integ-final-env-v86
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
FINAL_BRANCH=$(git branch --show-current)
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-env-v87-NEW-COHORT
git status --short --untracked-files=all
"$PY" scripts/disk_report.py
"$PY" scripts/agent_lock.py status

# 정적 확인만. renderer/worker/물리 시작 없음.
"$PY" -m scripts.run_final_environment_floor_light --check p01 \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p01"
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-check -- \
  --check p01 --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p01"
```

기본 체크아웃에서는 실행하지 않는다. 원격 P03가 갱신되면 먼저 fetch/merge하고
오프라인 검사 후 새 SHA로 고정한다. 아래 명령은 작업 worktree에서 실행하며,
경로명 끝의 v86은 폴더 이름일 뿐 실제 선택 번들은 v87이다. 다른 작업의 잠금은 해제하지 않는다.
디스크 10 GiB 미만은 시작하지 않으며 실행 중 ENOSPC는 `HOST_ERROR`다.

아래 잠금·세션 명령은 코디네이터가 실행한다. `--owner`는 실제 실행 주체로 바꾼다.
명령은 동기 SIM을 사용하고 시간 비교나 속도 결론을 내지 않는다.
각 블록은 잠금 획득 실패 시 즉시 멈추며, 획득한 뒤의 실패에도 자기 잠금을 해제한다.

```bash
(
set -euo pipefail
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v87 P01 reset 3x30 SIM s' --pid $$ --expected-minutes 30
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-env-v87-p01 -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-check -- \
  --check p01 --seed 911 --expected-source-sha "$FINAL_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p01"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
)
```

## P01: 3×30 SIM초, reset 별도 상한

실행기는 위 표 순서로 지도마다 표준 reset → 정지 30초를 수행한다.
학생/LLM/provider 추론/teacher 주행 명령은 0이다. reset은 사례당 **최대 5초**,
정지 관찰은 정확히 **30초**, 총 관찰 **90초**, reset 포함 총 **최대 105초**다.
5초는 측정치가 아니라 초과 시 중단하는 예산이다. 물리 timestep이 0.05초를
정확히 나누지 않으면 거부하며 다음 step이 상한을 넘기 전에 멈춘다.

검토할 파일과 판정:

- 각 사례의 `bundle.json`, `scene.xml`, `scene.json`, `eval_only/applied.json`:
  지도/부모/정적 hash, 실제 robot XML, v3 모델·wall 높이·표식 geom/texture 0,
  timestep·noslip·weld를 대조한다. `bundle.json`의 `render_profile_contract`와
  `scene.json`의 `render_profile`, `eval_only/applied.json`의 `render_profile`/`render_profile_applied`를
  대조한다. profile 이름·hash, 그림자 0, 반사 0, light cutoff 180, 밝은 ground texture 평균을
  검사하며 새 raw 자기 RGB를 눈으로 확인한다. 렌더 적용 검사가 실패하면 HOST_ERROR다.
  코드의 정적 hash는 실제 XML 확인을 대신하지 않는다.
- `eval_only/setup.json`, `eval_only/contacts.jsonl`: seeded 초기 배치,
  robot–wall/cargo/robot 초기 겹침·관통과 정지 drift. 접촉 trace는 0.05초 간격의
  표본이며 모든 내부 substep 접촉을 빠짐없이 기록했다는 근거가 아니다.
- `robots/r*/frames.jsonl`, `robots/r*/rgb/*.png`: t=reset 끝, 이후 5초 간격,
  끝 30초 포함 자기 영상. 실제 배치·FOV·좌우축·팔 가림과 크기/시각/hash를 확인한다.
  이 점검에서는 TOP를 학생에게 전달하지 않으며 추가 TOP 영상도 생성하지 않는다.
- `result.json`의 `COLLECTED_UNQUALIFIED`는 자료 수집 종료다. 환경 적합 PASS가 아니다.
  첫 HOST_ERROR 뒤 나머지는 `unattempted`로 남기고 분모 3을 유지한다.
  초기 관통/카메라 문제는 코디네이터가 실패로 기록하고 해당 조합의 학생 실행을 막는다.

## v3 보정 — 값을 만들지 말고 먼저 측정

`configs/calibration/zone_final_v3_floor_light_contract.json`은 정적 모델/지도/카메라 소스 계약이다.
camera sag/pan, unloaded/loaded/fine motion 및 measurement는 **null**이다.
v2 보정값 복사나 정지 화면의 GT 근처 PF 재시작으로 채우지 않는다.

아래는 코디네이터가 별도 실행하는 **unloaded 보정 수집** 명령이다.
P01 90초나 P03 360초에 합산해 숨기지 않는다. 3지도×120초=360초,
reset 각 5초 포함 최대 375초다. 순서/시각/명령은
`configs/final_environment_measurement_v1.json`에 고정했다.
검색/p20/빈 carry 팔 자세에서 각각 8pan×3초=72초,
전진·측면·회전의 양/음 0.03 명령 0.25초×4회와 정지 관찰,
나머지 시간 정지다. 실행 로봇은 r1, 나머지는 정지하고 3대 자기 영상을 저장한다.

```bash
(
set -euo pipefail
# 정적 확인: 3지도×120 SIM초, 아직 실행하지 않음.
"$PY" -m scripts.run_final_environment_floor_light --check calibration \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/calibration-unloaded"
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-check -- \
  --check calibration --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/calibration-unloaded"
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v87 unloaded calibration collection 3x120 SIM s' --pid $$ --expected-minutes 60
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-env-v87-calibration -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-check -- \
  --check calibration --seed 911 --expected-source-sha "$FINAL_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/calibration-unloaded"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
)
```

이는 **unloaded 원시 수집만**이다. 제어기가 calibration을 사용하거나 fitting·성공 판정을 하지 않는다.
`eval_only/r*/camera_labels.jsonl`에 실제 base/camera 변환,
`robots/r*/commands.jsonl`과 자기 PNG에 발행 명령/관측을 보존한다.
교사/GT는 오프라인 보정 자료로만 읽는다. 원시 eval 파일은 학생 factory 인자로 넘기지 않는다.

이후 필요한 측정: 실제 v3 무보조 파지 하중에서 같은 팔/pan 목록,
unloaded/loaded/fine의 gain·lag·slip·정지 drift, 실제 명령으로 방문하는 모든 팔 자세의
카메라 외부 보정과 pan–chassis yaw 결합. **loaded/fine 수집 경로는 아직 연결되지 않았다.**
v3 pair 어댑터가 먼저 필요하므로 이 문서는 실행되지 않는 가상의 loaded 측정 CLI를 제시하지 않는다.
이 자료 없이 `MEASURED_SIM` 파일을 만들면 안 된다.

고정 보정 산출물의 schema는 `ugrp.final_environment_measured_calibration.v1`:
`status=MEASURED_SIM`, `contract_sha256`, 지도별 정적 `maps` hash,
`robot_model=masterpi_v3`, `render_profile=floor_light_v1`, `source_sha`,
`measurement_manifest_sha256`, `params`(motion/motion_loaded/motion_profiles.fine),
`pan_base_yaw`(unloaded/loaded), `camera_models`(상태별 `servo3,servo4,servo5,servo6` →
`origin_m`, optical→actual-chassis `rotation`)를 기록한다.
외부 보정에 포함하지 않은 자세는 v2 FK로 추측하지 않고 provider 실패로 닫는다.
P03의 PF/명령 이력·늦은 fix 거절·0.16초 지연 wrapper는 유지한다.

## P03: 문 앞·문 뒤·목적지 전, 3×120 SIM초

P03의 3은 **지도 수가 아니라 체크포인트 수**다. 선택 지도는
`zone_wide_door_geometry_v3`다. 각 체크포인트까지 실제 이전 leg를 이어 실행해야 한다.
teacher staging/GT reseed/새 PF 시작으로 바꾸지 않는다. 접근·lower→open→p20 8장→
새 fix→re-align→grasp→lift를 같은 provider/PF로 잇고, 도달 못 함도 분모 3에 넣는다.
각 120초는 이전 leg를 포함한 전체 check cap이다. reset은 별도 최대 5초로 보고한다.

현재는 다음 **계획 확인**에서 `runnable:false`와 두 선행 조건이 나오는 것이 맞다.

```bash
"$PY" -m scripts.run_final_environment_floor_light --check p03 \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p03"
```

실제 요청 형태는 아래와 같다. **현재 후보에서는 실행하지 말 것**:
보정 인자 누락은 `MEASURED_V3_CALIBRATION_REQUIRED`, 보정 경로/해시 인자가 있어도
`FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED`로 물리/worker import 전에 거부한다.
이것은 실행 명령의 등록 형태이며 P03 인수 실행 완료/가능의 주장이 아니다.

```bash
# 후속 v3 chain adapter와 측정 보정을 등록하고 독립 검토한 새 후보에서만 사용.
CALIBRATION=/absolute/path/to/verified-v3-calibration.json
CALIBRATION_SHA=$(shasum -a 256 "$CALIBRATION" | cut -d ' ' -f 1)
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-check -- \
  --check p03 --expected-source-sha "$FINAL_SHA" \
  --calibration "$CALIBRATION" --calibration-sha256 "$CALIBRATION_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p03"
```

후속 어댑터는 평가와 독립인 실행 상한을 구현하고, source/번들/명령 해시,
scan 전후 PF 식별/입자·σ·last_scan_t, own command/servo, capture/release/consumed 시각,
eval-only 위치 오차·빔 이동·재파지 결과를 남겨야 한다. 학생 입력은 자기 RGB·정적 지도·
자기 명령·전달된 메시지만 허용한다. partner의 private state·GT·sim state로 성공/다음 단계를 결정하지 않는다.
v87에서 빈 adapter를 성공으로 처리하는 경로는 없다. 번들의 `provider` 항목은
v84/default의 미활성 P03 메타데이터를 보존한 것이다. 밝은 프로필의 측정값은 새 계약에
속하며 기존 factory에 전달하지 않는다. 후속 P03 후보는 측정 보정과 provider/chain
연결을 함께 등록해야 한다. 이 수집 경로는 학생/provider를 생성하지 않는다.

## 회수·정리

실행 종료/중단 뒤 자신이 만든 세션과 worker 자식 정리를 확인하고 소유 잠금을 해제한다.
다른 작업 프로세스는 종료하지 않는다. raw는 기본 `outputs/` 아래 보존하며 삭제/덮어쓰기하지 않는다.
실제 결과를 얻은 코디네이터는 `docs/tensorboard.md`에 따라 새 snapshot을 만들고
실제 데이터·영상·고정 카드·HParams 로딩을 검증한다. 이번 오프라인 작업은 새 실험 cohort가
없어 TensorBoard 변환이나 화면을 만들지 않았다. Drive는 사용하지 않는다.

## 참고 자료

- [이번 등록·검증 기록](experiments/2026-10-01-final-env-floor-light/README.md)
- [v84 P01 관찰 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)

- [P01 계획](experiments/2026-09-30-e2e-p01-env/README.md), [P03 #312](https://github.com/kcm0127-dotcom/ugrp/pull/312)
- [차단을 발견한 물리 큐 #337](https://github.com/kcm0127-dotcom/ugrp/pull/337)
- [실행 버전 관리](docs/execution_versioning.md), [정적 등록부](configs/zone_final_environment_v87.json)

---

# 최종 환경 v84 물리 인계 — DRAFT, 미봉인

**P01 3×30 SIM초 reset 경로는 등록했다. P03 3×120 SIM초 연쇄는 아직 실행할 수 없다.**
P03 #312에 의존한다. v3 보정 실측과 v3 공동 운반 어댑터가 없으며, 기존
`OwnCamTeamHost`는 `v3 pair executor requires a separately migrated controller`로 거부한다.
이 제한을 우회하거나 기존 제어기를 v3로 표시하지 않았다. 이 문서의 등록/계획 확인은
실제 SIM, 위치 추정 정확도, 파지, 연쇄 완주 또는 사전 등록 봉인이 아니다.

## 고정한 조합

번들 `zone-final-environment-v84`, workflow `zone-final-environment-check` 2.17.0.
main과 열린 PR 27개를 조회한 결과 RGB RUNNABLE_ID는 v63, 전체 관련 번들은
#292의 v83, 통합 workflow는 2.16.0이 최대였다.
[조회 원본](experiments/2026-10-01-final-env-runnable/reservation_scan.json)을 보존했다.

| P01 사례 | 지도 | 로봇 | 부모 |
|---|---|---|---|
| 문 1개 | `zone_wide_door_geometry_v3` | masterpi_v3 | 기존 geometry_v2, 기존 v3 파일 그대로 사용 |
| 문 2개 | `zone_wide_two_doors_final_v3` | masterpi_v3 | two_doors_final_v1 파일·정적 hash |
| 복도 | `zone_wide_corridor_final_v3` | masterpi_v3 | corridor_final_v1 파일·정적 hash |

기존 지도·catalog·v6e 등록·`configs/simulation_workflows.json`·과거 번들은 변경하지 않는다.
표준 관리자가 `configs/simulation_workflows.d/final_environment_v84.json`을 추가로 읽는다.
같은 ID 덮어쓰기는 거부하며 추가 catalog 파일도 관리 기록의 hash에 포함한다.
추가 장면은 표준 `CargoZoneScene`의 구성/초기화와 기존 v3 robot XML 변환을 재사용한다.
기존 v3 Scene allow-list를 넓히지 않는다.

공통 설정: `cargo_noslip_v1`, weld OFF, 초음파 OFF, 기존 authored/default 렌더,
walls_v3 0.40 m, 자기 `robot_cam` RGB 640×480, 분할 480×360, seg-v2 해시
`348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9`.
밝은 바닥/C_mix_rgb를 몰래 채택하지 않는다. 카메라/FOV·물체 외관을 바꾸지 않는다.
P01은 기존 기본 색 상자 reset 구성이다. P02 혼합 주문·긴 빔 임무 배치를 검증하는 실행이 아니다.

## 실행 전 — 코디네이터의 자기 worktree에서

코드를 먼저 커밋하고 아래 SHA를 그 HEAD로 고정한다. 같은 코호트 중 소스를 바꾸지 않는다.
이 작업의 샌드박스에서는 SIM/렌더/학습/실제 추론을 한 번도 실행하지 않았다.

```bash
cd /Users/changmin/projects/ugrp-wt/integ-final-env
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
FINAL_BRANCH=$(git branch --show-current)
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-env-v84-NEW-COHORT
git status --short --untracked-files=all
"$PY" scripts/disk_report.py
"$PY" scripts/agent_lock.py status

# 정적 확인만. renderer/worker/물리 시작 없음.
"$PY" -m scripts.zone_environment_bundle --map-id zone_wide_door_geometry_v3 --check p01
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-check -- \
  --check p01 --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p01"
```

기본 체크아웃에서는 실행하지 않는다. 원격 P03가 갱신되면 먼저 fetch/merge하고
오프라인 검사 후 새 SHA로 고정한다. 다른 작업의 잠금은 해제하지 않는다.
디스크 10 GiB 미만은 시작하지 않으며 실행 중 ENOSPC는 `HOST_ERROR`다.

아래 잠금·세션 명령은 코디네이터가 실행한다. `--owner`는 실제 실행 주체로 바꾼다.
명령은 동기 SIM을 사용하고 시간 비교나 속도 결론을 내지 않는다.

```bash
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v84 P01 reset 3x30 SIM s' --pid $$ --expected-minutes 30
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-env-v84-p01 -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-check -- \
  --check p01 --seed 911 --expected-source-sha "$FINAL_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p01"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
```

## P01: 3×30 SIM초, reset 별도 상한

실행기는 위 표 순서로 지도마다 표준 reset → 정지 30초를 수행한다.
학생/LLM/provider 추론/teacher 주행 명령은 0이다. reset은 사례당 **최대 5초**,
정지 관찰은 정확히 **30초**, 총 관찰 **90초**, reset 포함 총 **최대 105초**다.
5초는 측정치가 아니라 초과 시 중단하는 예산이다. 물리 timestep이 0.05초를
정확히 나누지 않으면 거부하며 다음 step이 상한을 넘기 전에 멈춘다.

검토할 파일과 판정:

- 각 사례의 `bundle.json`, `scene.xml`, `scene.json`, `eval_only/applied.json`:
  지도/부모/정적 hash, 실제 robot XML, v3 모델·wall 높이·표식 geom/texture 0,
  timestep·noslip·weld를 대조한다. 코드의 정적 hash는 실제 XML 확인을 대신하지 않는다.
- `eval_only/setup.json`, `eval_only/contacts.jsonl`: seeded 초기 배치,
  robot–wall/cargo/robot 초기 겹침·관통과 정지 drift. 접촉 trace는 0.05초 간격의
  표본이며 모든 내부 substep 접촉을 빠짐없이 기록했다는 근거가 아니다.
- `robots/r*/frames.jsonl`, `robots/r*/rgb/*.png`: t=reset 끝, 이후 5초 간격,
  끝 30초 포함 자기 영상. 실제 배치·FOV·좌우축·팔 가림과 크기/시각/hash를 확인한다.
  이 점검에서는 TOP를 학생에게 전달하지 않으며 추가 TOP 영상도 생성하지 않는다.
- `result.json`의 `COLLECTED_UNQUALIFIED`는 자료 수집 종료다. 환경 적합 PASS가 아니다.
  첫 HOST_ERROR 뒤 나머지는 `unattempted`로 남기고 분모 3을 유지한다.
  초기 관통/카메라 문제는 코디네이터가 실패로 기록하고 해당 조합의 학생 실행을 막는다.

## v3 보정 — 값을 만들지 말고 먼저 측정

`configs/calibration/zone_final_v3_contract.json`은 정적 모델/지도/카메라 소스 계약이다.
camera sag/pan, unloaded/loaded/fine motion 및 measurement는 **null**이다.
v2 보정값 복사나 정지 화면의 GT 근처 PF 재시작으로 채우지 않는다.

아래는 **추가 예산**을 승인한 코디네이터가 실행할 unloaded 수집 명령이다.
P01 90초나 P03 360초에 합산해 숨기지 않는다. 3지도×120초=360초,
reset 각 5초 포함 최대 375초다. 순서/시각/명령은
`configs/final_environment_measurement_v1.json`에 고정했다.
검색/p20/빈 carry 팔 자세에서 각각 8pan×3초=72초,
전진·측면·회전의 양/음 0.03 명령 0.25초×4회와 정지 관찰,
나머지 시간 정지다. 실행 로봇은 r1, 나머지는 정지하고 3대 자기 영상을 저장한다.

```bash
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v84 unloaded calibration collection 3x120 SIM s' --pid $$ --expected-minutes 60
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-env-v84-calibration -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-check -- \
  --check calibration --seed 911 --expected-source-sha "$FINAL_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/calibration-unloaded"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
```

이는 **unloaded 원시 수집만**이다. 제어기가 calibration을 사용하거나 fitting·성공 판정을 하지 않는다.
`eval_only/r*/camera_labels.jsonl`에 실제 base/camera 변환,
`robots/r*/commands.jsonl`과 자기 PNG에 발행 명령/관측을 보존한다.
교사/GT는 오프라인 보정 자료로만 읽는다. 원시 eval 파일은 학생 factory 인자로 넘기지 않는다.

이후 필요한 측정: 실제 v3 무보조 파지 하중에서 같은 팔/pan 목록,
unloaded/loaded/fine의 gain·lag·slip·정지 drift, 실제 명령으로 방문하는 모든 팔 자세의
카메라 외부 보정과 pan–chassis yaw 결합. **loaded/fine 수집 경로는 아직 연결되지 않았다.**
v3 pair 어댑터가 먼저 필요하므로 이 문서는 실행되지 않는 가상의 loaded 측정 CLI를 제시하지 않는다.
이 자료 없이 `MEASURED_SIM` 파일을 만들면 안 된다.

고정 보정 산출물의 schema는 `ugrp.final_environment_measured_calibration.v1`:
`status=MEASURED_SIM`, `contract_sha256`, 지도별 정적 `maps` hash,
`robot_model=masterpi_v3`, `render_profile=default`, `source_sha`,
`measurement_manifest_sha256`, `params`(motion/motion_loaded/motion_profiles.fine),
`pan_base_yaw`(unloaded/loaded), `camera_models`(상태별 `servo3,servo4,servo5,servo6` →
`origin_m`, optical→actual-chassis `rotation`)를 기록한다.
외부 보정에 포함하지 않은 자세는 v2 FK로 추측하지 않고 provider 실패로 닫는다.
P03의 PF/명령 이력·늦은 fix 거절·0.16초 지연 wrapper는 유지한다.

## P03: 문 앞·문 뒤·목적지 전, 3×120 SIM초

P03의 3은 **지도 수가 아니라 체크포인트 수**다. 선택 지도는
`zone_wide_door_geometry_v3`다. 각 체크포인트까지 실제 이전 leg를 이어 실행해야 한다.
teacher staging/GT reseed/새 PF 시작으로 바꾸지 않는다. 접근·lower→open→p20 8장→
새 fix→re-align→grasp→lift를 같은 provider/PF로 잇고, 도달 못 함도 분모 3에 넣는다.
각 120초는 이전 leg를 포함한 전체 check cap이다. reset은 별도 최대 5초로 보고한다.

현재는 다음 **계획 확인**에서 `runnable:false`와 두 선행 조건이 나오는 것이 맞다.

```bash
"$PY" -m scripts.run_final_environment_checks --check p03 \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p03"
```

실제 요청 형태는 아래와 같다. **현재 후보에서는 실행하지 말 것**:
보정 누락은 `MEASURED_V3_CALIBRATION_REQUIRED`, 보정이 있어도
`FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED`로 물리/worker import 전에 거부한다.
이것은 실행 명령의 등록 형태이며 P03 인수 실행 완료/가능의 주장이 아니다.

```bash
# 후속 v3 chain adapter와 측정 보정을 등록하고 독립 검토한 새 후보에서만 사용.
CALIBRATION=/absolute/path/to/verified-v3-calibration.json
CALIBRATION_SHA=$(shasum -a 256 "$CALIBRATION" | cut -d ' ' -f 1)
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-check -- \
  --check p03 --expected-source-sha "$FINAL_SHA" \
  --calibration "$CALIBRATION" --calibration-sha256 "$CALIBRATION_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p03"
```

후속 어댑터는 평가와 독립인 실행 상한을 구현하고, source/번들/명령 해시,
scan 전후 PF 식별/입자·σ·last_scan_t, own command/servo, capture/release/consumed 시각,
eval-only 위치 오차·빔 이동·재파지 결과를 남겨야 한다. 학생 입력은 자기 RGB·정적 지도·
자기 명령·전달된 메시지만 허용한다. partner의 private state·GT·sim state로 성공/다음 단계를 결정하지 않는다.
v84에서 빈 adapter를 성공으로 처리하는 경로는 없다.

## 회수·정리

실행 종료/중단 뒤 자신이 만든 세션과 worker 자식 정리를 확인하고 소유 잠금을 해제한다.
다른 작업 프로세스는 종료하지 않는다. raw는 기본 `outputs/` 아래 보존하며 삭제/덮어쓰기하지 않는다.
실제 결과를 얻은 코디네이터는 `docs/tensorboard.md`에 따라 새 snapshot을 만들고
실제 데이터·영상·고정 카드·HParams 로딩을 검증한다. 이번 오프라인 작업은 새 실험 cohort가
없어 TensorBoard 변환이나 화면을 만들지 않았다. Drive는 사용하지 않는다.

## 참고 자료

- [P01 계획](experiments/2026-09-30-e2e-p01-env/README.md), [P03 #312](https://github.com/kcm0127-dotcom/ugrp/pull/312)
- [차단을 발견한 물리 큐 #337](https://github.com/kcm0127-dotcom/ugrp/pull/337)
- [실행 버전 관리](docs/execution_versioning.md), [정적 등록부](configs/zone_final_environment_v84.json)
