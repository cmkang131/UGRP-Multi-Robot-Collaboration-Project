# dock-only v3 — 2026-09-27

**tags_temporary, dev, 연구 결과 아님. 물리 step·모델 호출·커밋 없음.**

코디네이터의 [#218 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/218#issuecomment-5853065426)
후속 지시: dev05/dev06은 **기존 tags_v2/0.10 m 벽을 유지하고 dock만 이동**한다.
`walls_v3(PR #208) 적용은 후속 작업`이며 해당 PR의 코드·지도를 이 브랜치에 추가하지 않았다.

## 버전과 변경 범위

- 장면/지도: `zones/zone_wide_door_tags_v2_dock_v3`, map version 3.
- dock 프로필: `zone_start_dock_v3`. x=−0.65 m, y 행 `[-2.25, -0.85, 0.55]` m,
  yaw=0 rad, 원래 z=0.032355118817659255 m. 세 로봇의 seeded 행 배정은 유지한다.
- 정적 idle keepout: 같은 세 중심, 기존 반경 0.17 m. host의 skill·executor가 같은
  지도 프로필에서 읽는다. 현재 peer 위치나 평가 GT를 전달하지 않는다.
- `ORDER`에는 dock 좌표가 없으므로 주문서·개략 빔 주문서·보정은 그대로다.
  새 지도의 `start_dock`과 정적 지도 설명에 출발 규칙을 기록한다.
- 벽·태그/문기둥·카메라·cargo·접촉·guard·LOW/HIGH·dwell·60 s 단일 제출·재시도 없음은 유지한다.
  `cargo_noslip_v1`, noslip 10, timestep 0.00025 s, weld OFF다.
- 사전등록 `prereg_v3.json`은 REGISTERED이며 실행은 `not_run`이다. v2의 `criteria`,
  `stage_rules`, `planned_setdown`, 예산·시간 규칙을 유지한다. 기존 v3 DRAFT에서 추가한
  비공개 admission receipt만 유지하며, 누락은 진단 증거 불완전이지 물리 성공이 아니다.
- 공통 workflow `zone-pair-dev`는 0.2.0. prepare/실행/종료 무결성 검사에서 모두
  선택한 prereg의 새 지도를 사용한다. `prereg_v3_DRAFT.json`은 그대로 prepare-only다.
- 새 `DockTaggedCargoZoneScene`은 기존 `TaggedCargoZoneScene → ZoneScene → Scene`을
  상속한다. `sim/zone_arena.py`와 `sim/zone_landmarks.py`를 포함한 M2 동결 import
  **32개 파일의 원본 해시를 모두 유지**한다. 새 지도 설명은
  `sim.zone_start_dock.static_map_text`로 얻는다.

main + 열린 PR 22개, **23개 로컬 refs의 RUNNABLE_ID 최댓값은 v63**이다.
fetch는 공유 Git 디렉터리 쓰기 제한으로 실패했고, 열린 PR 목록/head는 GitHub connector로
확인했다. 22개 로컬 PR ref가 조회한 head와 일치했다.
[ref 목록](dock_v3_ref_inventory.json). 변경 파일은 RGB dispatch 번들 source closure와
겹치지 않고 closure에 새 파일도 추가되지 않았다. 따라서 **새 RGB 번들 번호는 사용하지 않았다**.
새 장면 계약과 workflow 버전으로 식별한다. v64를 예약한 것이 아니다.

## 정적 계산과 한계

서쪽 벽 중심 x=−1.05, 반두께 0.025 → 안쪽 면 **−1.025 m**.
차체 local x 범위 `[-0.15, +0.10]`, y 반폭 0.09 m. yaw=0의 서쪽 뒤 모서리가 제한점이다.

```text
lever = sqrt(0.15^2 + 0.09^2) = 0.174928556845359 m
margin = 0.020 + 0.015 + 2 min(σxy, 0.15) + 2 min(σyaw, 0.20) lever
σxy=0.05 m, σyaw=0.06 rad -> margin=0.155991426821443 m
raw gap = (−0.65 − 0.15) − (−1.025) = 0.225 m
clearance = raw gap − margin = 0.06900857317855691 m
```

원래 x=−0.85는 σ=0에서도 `0.025−0.035=−0.010 m`로 거부된다.
이 음수는 불확실성을 포함한 안전 여유 부족이며 물리 침투량이 아니다.

dev05 seed901·dev06 seed902의 r1/r2/r3 모두:

- 차체-벽 여유 **69.009 mm**, 초기 발행 팔 자세의 sphere-벽 여유 **188.146 mm**.
- 초기 자세 그대로 동쪽 8 cm 전신 이동 검사 통과(실제 이동 없음).
- 두 로봇 각각의 불확실성까지 팽창한 전신 외접 원으로 모든 쌍을 검사한 최소 여유
  **738.160 mm**. r1–r2, r1–r3, r2–r3 모두 포함한다.
- r3의 같은 전신 원과 초기 빔/정적 운반 경로 사이를 빔 외접 원 + 기존 set-down
  허용 오차 0.12 m로 보수적으로 검사했다. dev05 **898.414 mm**, dev06 **828.414 mm**.
  [정적 검증 기록](dock_v3_validation.json)에 로봇별·쌍별 수치를 둔다.

이는 정적 초기 자세·명시한 경로 경계만의 계산이다. 팔 동작 전체, 접근 중 peer 위치,
PF 수렴·태그 가시성·실제 pickup·문 통과·r3 비간섭을 입증하지 않는다.
GT는 이 정적 검사/평가 전용이며 학생의 추정·명령·단계 전이에 넣지 않았다.

walls_v3 후속은 위 **x/행/z/yaw/keepout 및 계산식**을 새 버전으로 적용한다.
벽 높이 0.40 m는 별도 조건이다. 차체 여유식은 같아도 팔 sweep·가시성을 다시 검증해야 한다.

## 코디네이터 실행 명령 — 작성만, 실행하지 않음

원래 버전의 기록과 출력은 보존한다. `--prereg`는 아래 새 파일을 반드시 명시한다.
소스 SHA는 코디네이터가 검토·커밋한 뒤 두 회차 동안 고정한다.
사전등록의 `execution_source_sha=null`은 아직 커밋하지 않았다는 뜻이며,
실제 SHA는 필수 `--expected-source-sha` 및 각 manifest에 기록한다.

준비만 확인:

```sh
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-27-zone-pair-dev/prereg_v3.json \
  --run-id dev05 --output /tmp/zone-pair-dev05-prepare-NEW
# dev06도 새 출력 경로로 같은 prepare를 수행한다.
```

검토·커밋 후 코디네이터만 실행:

```sh
bash <<'PAIR_DEV_V3'
set -euo pipefail
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_OWNER=codex
PAIR_BRANCH=$(git branch --show-current)
PAIR_SHA=$(git rev-parse HEAD)
PAIR_PREREG=experiments/2026-09-27-zone-pair-dev/prereg_v3.json
PAIR_ROOT="/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v3-$PAIR_SHA"
test "$PAIR_BRANCH" != main
test -z "$(git status --porcelain)"
"$PAIR_PY" scripts/disk_report.py
"$PAIR_PY" scripts/agent_lock.py status
"$PAIR_PY" scripts/agent_lock.py acquire --owner "$PAIR_OWNER" --branch "$PAIR_BRANCH" \
  --purpose "pair-v3-dev05-dev06 $PAIR_SHA; no model calls" --pid "$$" --expected-minutes 1925
trap '"$PAIR_PY" scripts/agent_lock.py release --owner "$PAIR_OWNER"' EXIT
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
for PAIR_RUN in dev05 dev06; do
  "$PAIR_PY" scripts/ugrp_session.py run "pair-$PAIR_RUN-${PAIR_SHA:0:8}" -- \
    "$PAIR_PY" -m scripts.sim_cli workflow run zone-pair-dev \
    --record "$PAIR_ROOT/$PAIR_RUN-managed" --timeout 57660 -- \
    --prereg "$PAIR_PREREG" --run-id "$PAIR_RUN" --output "$PAIR_ROOT/$PAIR_RUN" \
    --execute --expected-source-sha "$PAIR_SHA" --lock-owner "$PAIR_OWNER"
done
PAIR_DEV_V3
```

owner는 실제 코디네이터에 맞춘다. 잠금 획득에 실패하면 시작하지 않는다.
기존 출력 덮어쓰기와 실패 후 자동 재실행은 하지 않는다.

실행 후 결과·실패·영상은 기존 README와 `docs/tensorboard.md`에 따라
코디네이터가 새 native TensorBoard snapshot으로 변환하고 실제 로딩·표시를 검증한다.
이 작업은 정적 구현 검증이며 새로운 물리 실험 결과나 TensorBoard snapshot을 만들지 않았다.

## 파일과 해시

변경·추가 파일 전체, map/dock/scene/prereg SHA256, 테스트 결과와 원본 보존 검사는
[dock_v3_validation.json](dock_v3_validation.json)에 기록한다. 새 장면의 SHA256은
설정 identity이며 물리 적용 XML의 해시가 아니다. 실제 XML은 코디네이터 실행 때 별도로 기록한다.

최종 비물리 회귀: **540 passed, 2 deselected, 23.30 s**.
pair 전체·own executor 전체·새 dock·workflow manager를 검사했다.
제외: 실제 world 생성/물리 테스트 1개, sandbox가 `ps`를 거부하는 기존 프로세스 정리 테스트 1개.
`OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, `--basetemp=./.pytest_tmp`,
`-p no:cacheprovider`를 사용했다. MuJoCo `mj_step/mj_step1/mj_step2`를 예외로 차단했고
물리 step 호출 시도 0회였다. `finally`에서 `.pytest_tmp`를 지우고 부재를 확인했다.
dev05/dev06 prepare는 별도 자식 프로세스에서 MuJoCo import 자체를 차단하여 통과했고,
`prepared_not_executed`, `applied=null`, model_calls=0, 원본 prereg 바이트 동일을 확인했다.
가짜 world 통합 회귀는 두 버전의 정상/abort 경로와 종료 후 새 지도 해시 검사를 포함한다.
