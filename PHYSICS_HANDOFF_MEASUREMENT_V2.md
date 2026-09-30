# 무하중 운동 측정 v2 인계 — DRAFT, 물리 미실행

Refs #342 #346. 새 번들 **zone-final-environment-v89**, floor-light 후속 workflow
**zone-final-environment-floor-light-v2-check 2.21.0**, 새 check **calibration-motion-v2**.
v87의 측정 v1·실행 소스·catalog와 생성 번들 9개를 그대로 보존한다.
같은 workflow ID 중복 등록은 관리자가 거부하므로 후속 ID로 확장했다.
후속 실행기의 기존 `p01/calibration/p03` 모드는 v87 실행기·차단 조건으로 위임한다.
이 문서는 새 check만 인계한다. P03, loaded/fine, 학생 실행 승인이나 보정값 채택이 아니다.

## 수집할 것

- 지도 1개: `zone_wide_two_doors_final_v3`. 정적 벽 직사각형의 합집합을 바닥 경계에서
  잘라 계산한 빈 바닥은 **28.9675 m²**로, 문 1개 28.9175·복도 28.7775보다 넓다.
- 명령 로봇 r1, 무하중, 표준 search 팔 자세. r2/r3와 기존 상자는 정지/기존 배치를 유지한다.
  표준 Scene의 setup-only r1 reset만 정적 위치 **(3.25, −0.85), yaw=0**으로 등록했다.
  기존 서쪽 dock은 0.3 m 여유가 없으므로 여기서 긴 입력을 시작할 수 없다.
  이 배치는 진단용 reset이며 학생 주행·도착이 아니다. 중간 재배치는 없다.
- 초기 정지 2초. 전진, 측면 순서로 각각 ±0.01/0.02/0.03을 **15초씩** 유지하고 각 계단 뒤
  1초 정지한다. 각 축의 6계단 96초 + 31칩 PRBS(±0.02, 칩 0.5초) 15.5초 + 정지 2.5초 = 114초.
  총 **230초**, reset 최대 5초 포함 **235 SIM초**. 다음 substep이 상한을 넘기기 전에 거부한다.
- 각 명령은 기존 정상 mecanum 범위 안의 **0.05초 lease**로 연속 갱신한다. turn=0.
  별도 pan/팔 sweep은 없다. yaw는 축간 운동 진단으로 기록하며 이번 식별 대상은 전진·측면이다.
- `eval_only/r1/pose.jsonl`: 초기와 이후 **0.05초마다**, 끝 포함 4,601개 실제 base pose.
  v1은 contact 표본만 0.05초이고 pose는 camera에 묶여 0.2초였다. 새 pose 로그는 렌더와 독립이다.
  자기 RGB는 초기/5초마다/끝에 3대 각각 47장, camera label도 이 시각에만 보존한다.
  `robots/r1/commands.jsonl`은 reset 이력과 4,600개 발행 명령을 남긴다.

## 간격과 중단

정적 지도 벽 **표면** 및 바닥 경계에서 로봇의 보수적 원판 반경 0.35 m를 뺀 간격을 쓴다.
시작 간격은 0.675 m이고 #346 후보 1차 모델의 전체 예측 경로에서도 최솟값은 0.675 m다.
예측은 안전 보증이 아니다. 물리 소유자가 reset 후 첫 명령 전에 검사하고, 수집 중 매 내부
physics substep 전후 실제 차체 위치와 정적 지도로 검사한다. **0.3 m + 중단 여유 0.05 m**
미만, 비유한/누락 값, substep 이동 0.01 m 초과, 실제 geom 경계가 원판을 벗어나면 모든
포트를 hold하고 그 실행을 `HOST_ERROR`로 끝낸다. 원판 포함 검사는 reset과 0.05초 표본마다 한다.
이는 진단 수집의 **중단 전용 인터록**이다. pose를 명령 스케줄에 반환하거나 경로/행동/단계를
보정하지 않는다. 학생/provider를 생성하지 않는다. 미수집 뒤 구간은 완료로 세지 않는다.

이상적인 1차 모델에서 15초는 최대 설계 drive τ=3초의 5배(약 99.3% 응답)다.
0.05초 표본은 후보 τ=1.44/3초당 28.8/60개다. #346의 더 긴 τ 대안은 배제된 실측 사실이 아니다.
실제 마지막 계단 구간에 plateau가 없거나 격자 경계 해/잔차 구조가 남으면 **식별 실패**로 보고한다.
정지 τ=0.05/0.08초와 회전 τ=0.17초는 이 주기의 10배 조건을 만족하지 않으므로 확정하지 않는다.

## 코디네이터 명령 — 실행 주체 claude

구현 작업이 끝난 이 worktree의 PR head를 코디네이터가 인계받은 뒤 실행한다.
PR에서 검토한 head와 아래 remote head가 같은지 확인하고 코호트 중 소스를 고정한다.
실행 중 다른 checkout을 자동 갱신하지 않는다. 출력 디렉터리는 항상 새 이름을 쓴다.

```bash
cd /Users/changmin/projects/ugrp-wt/calib-measure-v2
set -euo pipefail
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
MEASUREMENT_SHA=$(git rev-parse origin/codex/calib-measure-v2)
test "$(git rev-parse HEAD)" = "$MEASUREMENT_SHA"
test -z "$(git status --porcelain --untracked-files=all)"
MEASUREMENT_BRANCH=$(git branch --show-current)
RUN_ROOT="/Users/changmin/projects/ugrp/outputs/measurement-v89-${MEASUREMENT_SHA:0:8}-$(date +%Y%m%d-%H%M%S)"
"$PY" scripts/disk_report.py
"$PY" scripts/agent_lock.py status

# 정적 계획 확인: 물리·렌더·모델을 시작하지 않는다.
"$PY" -m scripts.run_final_environment_measurement_v2 \
  --check calibration-motion-v2 --expected-source-sha "$MEASUREMENT_SHA" --output "$RUN_ROOT"
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-v2-check -- \
  --check calibration-motion-v2 --expected-source-sha "$MEASUREMENT_SHA" --output "$RUN_ROOT"

(
set -euo pipefail
"$PY" scripts/agent_lock.py acquire --owner claude --branch "$MEASUREMENT_BRANCH" \
  --purpose 'v89 unloaded steps and PRBS, <=235 SIM s including reset' --pid $$ --expected-minutes 45
trap '"$PY" scripts/agent_lock.py release --owner claude' EXIT
"$PY" scripts/ugrp_session.py run measurement-v89 -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-v2-check -- \
  --check calibration-motion-v2 --seed 911 --expected-source-sha "$MEASUREMENT_SHA" \
  --execute --lock-owner claude --output "$RUN_ROOT"
"$PY" scripts/agent_lock.py release --owner claude
trap - EXIT
)
```

잠금/소스/출력/디스크 검사 실패는 물리 import 전에 거부한다. 10 GiB 미만은 시작하지 않고
ENOSPC는 HOST_ERROR다. 다른 작업의 잠금을 해제하거나 프로세스를 종료하지 않는다.
종료·실패 뒤 자기 세션/자식 정리와 잠금 해제를 확인하고 raw를 보존한다.

## 회수와 판정

`plan.json`, 지도별 `bundle.json`, `scene.xml/json`, `eval_only/applied.json`, pose·contact·command·RGB,
`result.json`, `artifacts.sha256.json`을 회수한다. root 결과 분모는 **1**이다.
`COLLECTED_UNQUALIFIED`는 고정 수집이 끝났다는 뜻이며 gain/τ 식별 성공이 아니다.
0.05초 누락·중복·시계 불일치, v1 camera 시각과 혼동, 인터록 중단을 먼저 감사한다.

이후 v2의 drive+coast 적합법으로 gain/drive τ를 적합하고 stop τ는 nuisance로 profile한다.
계단 마지막 3초 정상상태·양/음/크기별 일치와 PRBS 예측 잔차를 따로 확인한다.
PRBS를 검증용으로 남길 경우 계단만으로 먼저 적합하고 그 결정·해시를 고정한다.
τ 격자 확장에도 해가 경계로 달리거나 gain–τ 잔차 곡선이 평평하면 값을 채택하지 않는다.
이번 자료로 loaded/fine, 회전/정지 τ, 카메라 외부 보정이나 P03 상태를 승격하지 않는다.
실제 결과의 TensorBoard 변환·영상 등록·화면 확인은 코디네이터가 `docs/tensorboard.md`에 따라 수행한다.

[설계 근거·오프라인 검증·참고 자료](experiments/2026-10-01-final-env-measurement-v2/README.md)
