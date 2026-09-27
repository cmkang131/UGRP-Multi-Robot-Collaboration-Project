# 공동 운반 능동 재관측·근접 관측 계약 v5 — 2026-09-27

**tags_temporary · dev · 연구 결과 아님. 구현·비물리 회귀만 수행. 물리 step·모델 호출·git 커밋 없음.**

[diagnosis_v5](diagnosis_v5.md)와 [이슈 #221 최신 코디네이터 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5856308924)을 구현한다.
작업 기준 HEAD는 `3790372dfdd8e9de894bad7414657461bc8ba91d`, 기존 PR #240의
`codex/zone-pair-grasp-relook`이다. 과거 prereg·결과·진단·M2 원본은 덮어쓰지 않는다.

## PR #240 review4 반영 — 2026-09-27

현재 준비 등록은 [prereg_v5b.json](prereg_v5b.json)이다. main 병합 후 소스 계약이
맞지 않는 v5는 바이트 그대로 보존하고, 아직 실행하지 않은 dev09/dev10을 현재
scene/grasp 계약으로 다시 등록했다. `docs/execution_versioning.md`의 변경·검증 2–4단계에
따라 새 revision으로 구분하며 이전 결과를 승계하지 않는다. v3/v4/v5와 비교해 seed,
화물/입력, 판정 기준과 한도는 같다. v5b의 `supersedes`는 기존 v5의 정확한 해시다.
workflow 0.4.0·실행기 profile은 유지하고 수정 소스를 계약 해시와 revision으로 식별한다.
`execution_source_sha=null`이며 물리 실행 전 코디네이터의 별도 커밋·소스 고정이 필요하다.

초기화 순서는 **hold → 정지 이후 시각의 유효한 공통 자세 보고·정지 캐시 확보 → PF 초기화**다.
0.16초 지연 제공자의 2.30초 보고(`t_est=2.14`)로는 초기화하지 않고,
2.40초의 보고(`t_est=2.24`)를 확보한 뒤 초기화한다. 기다림도 기존 8초/누적 40초에 포함된다.
자세 유효성·안전 임계값·GT 경계·weld OFF·cargo_noslip_v1은 유지한다.
검증 범위와 준비 영수증은 [review4 반영 기록](review4_fixes.md)을 따른다.

## 버전과 변경 범위

- [prereg_v5b.json](prereg_v5b.json) (이전 [v5](prereg_v5.json) 보존): **dev09/seed905** 정상 시도, **dev10/seed906** carry-GO 후 abort 진단.
  v3/v4 화물 배치·주문서·개입을 유지하고 spawn/PF seed만 새로 고정한다. 실행 전 검토·소스 고정은 owner=claude다.
- 실행기 `zone_pair_executor_v6_dev`, 파지 계약 `zone_pair_grasp_relook_v2`, 기존 workflow `zone-pair-dev` **0.4.0**.
  STATUS는 **zone_pair_status_v5 그대로**이며 enum·필드·readiness TTL·GO 격자는 바뀌지 않는다.
  새로운 RGB dispatch 실행 번들 ID는 할당하지 않았다. 새 align 모듈도 grasp 소스 해시에 포함한다.
  연결 도구로 확인한 열린 PR 12개 head SHA와 로컬 ref가 일치했고, 해당 refs/main의
  pair workflow 최대 버전 0.3.0을 대조해 0.4.0을 사용했다.
- `criteria`, `stage_rules`, `planned_setdown`, `limits`, `timing`, `safety_coverage`, `environment`, `inputs`는 v3/v4와 동일하다.
  평가기는 v4의 pregrasp 세부 단계 동치만 v5에도 적용한다. 바닥 지지·접촉·낙하·재들기·문 통과 기준은 그대로다.
- 장면·카메라/FOV·정적 지도/보정 유지: `zone_wide_door_tags_v2_dock_v3`,
  **cargo_noslip_v1 / noslip 10 / timestep 0.00025 s / weld OFF**.
  GT·접촉·측정 관절·eval_only·상대 pose는 새 제어에 들어가지 않는다.

## align 전·중 능동 재관측

align 진입마다 먼저 hold하고, 아직 발행되지 않은 beam-view 팔 명령을 버린 뒤 **발행한 PWM**에서 시작한다.
정지 이후 시각의 유효한 자세 보고와 guard의 정지 캐시를 확보한 뒤 기존 `LOOK_P20`와 고정 pan 후보를 검사한다. 자기 자세 추정과 정적 태그의 4개 꼭짓점을
기존 어안 카메라 보정/FK로 투영해, 정상 영상 영역의 8 px 이상 태그 면적 합이 큰 방향부터 선택한다.
기존 `PairSweepGuard`의 전체 전환 충돌 검사를 통과한 후보만 쓰며 backoff는 허용하지 않는다.
이 순위는 예상 가시성일 뿐이다. 가림·자기 추정 bias가 있을 수 있으므로 실제 새 태그 수용을 대신하지 못한다.
표식 없는 지도에 가짜 특징을 만들거나 태그 없는 VO로 우회하지 않는다. 이 후보는 tags_temporary 전용이다.

정지 명령이 발행되고 제공자 지연을 지난 유효 보고를 확보한 뒤에만 shared `own.pose.loc`를 새로 초기화하고 자기 RGB로 갱신한다.
guard와 다른 추정기나 `vo_pose`를 사용하지 않는다. 이번 look 시작 **이후** 수용된 태그,
신선한 공통 report·gate OK·기존 5 cm/3° 준비조건·조기 재관측 여유가 모두 충족돼야
원래 beam-view 자세로 돌아간다. 돌아온 뒤에도 조건을 재확인하고 align을 재개한다.
이 과정의 새 상태는 `align_relook_stop`, `align_relook`, `align_relook_return`이며,
팔 보간·복귀도 기존 guard를 거친다. 재관측 중 base 이동은 금지된다.

align 중에는 팔이 움직이는 동안에도 매 제어 tick마다 수용된 태그의 age를 검사한다.
**6 SIM초 공백** 또는 **XY σ ≥5.5 cm / yaw σ ≥2.5°**이면 다음 이동보다 먼저 hold·재관측한다.
후자의 두 수치는 재관측을 앞당기는 스케줄 기준이며 기존 안전 gate를 완화하지 않는다.

| 근거: dev08 r2 자기 보고 | 태그 age | XY σ | 의미 |
|---|---:|---:|---|
| 160.3 s | 0 s | 0.04615 m | 마지막 수용 태그 |
| 166.2 s | 5.9 s | 0.05459 m | 아직 시간 기준 전 |
| **166.3 s** | **6.0 s** | **0.05486 m** | 새 재관측 트리거 |
| 175.6 s | 15.3 s | 0.07004 m | 기존 loaded HIGH 초과 |

저장 입력에서는 **9.3초, XY 15.14 mm**의 여유를 두고 정지한다. 기본 arm 올리기 0.8초와
settle 0.6초, 다음 control tick 0.1초보다 큰 여유다. 이 값은 자기 보고 기반 dev 설계 근거이고
미래 σ 증가율·재위치추정 성공·실제 정지를 보증하는 보정값은 아니다. 급격한 HIGH·낡은/유효하지 않은
입력은 기존 guard가 즉시 중단하며, 그 gate를 지나 look으로 우회하지 않는다.
**loaded HIGH XY 0.07 m, 준비 σ 0.05 m, yaw 3°, 기본 margin 35 mm는 불변**이다.

무한 반복 방지: **작업 전체 8회**, 회당 **방향 3개 / 8초**, 정지·관측·복귀를 합친
**누적 40초** 상한이다. 카메라/충돌 대기도 시간에 포함한다. 원래 align 종료시각도 재관측으로 리셋하지 않는다.
상한·관측 실패·안전 시선 부재는 abort로 끝나며 양쪽 예약 큐가 지워진다. 자기 집게가 닫혔거나
파지 영수증이 있거나 상대가 ready/lift/carry이면 일방 sweep을 시작하지 않는다.
상대에게는 기존 **aligning/abort enum**만 보낸다. 상대는 기존 close READY/GO 장벽에서 열린 채 기다리고,
20초 한도와 0.6초 증거 TTL을 그대로 따른다. 태그·σ·좌표·이미지·자유 텍스트를 교환하지 않는다.

## 근접 preclose 부분 관측

`BAND_CLIPPED`와 함께 **END_CLIPPED + end_visible=false**도 부분 패치 일치 검사에 들어간다.
자기 RGB의 full-band standoff anchor가 먼저 있어야 하며 segment·수명 30초·발행 명령 전파 σ·
동일 camera PWM·신선한 frame·점 수·패치 95% 일치와 전체 빔–벽 여유를 모두 검사한다.
부분 패치의 PCA 축·그립점으로 **위치·방향·anchor 시각·σ를 초기화하지 않는다**.
명령/시간에 따라 불확실성이 계속 증가한다. READY 전과 매 close PWM 전의 문설주 검사도 유지한다.

[회귀 fixture](../../tests/fixtures/zone_pair_v5/manifest.json)는 dev07 r1 2장과 dev08 r2 4장,
212개 dev07 발행 명령과 154개 dev08 자기 보고를 담는다(전체 약 249 KB).
JPEG는 크기 변경·재인코딩 없이 바이트 그대로 복사했다. 원본은 다음 경로에서 읽기만 했다.

`/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v4-8effc2cee5c3534d553adb75a0d82b49097e5286/{dev07,dev08}`

manifest의 `source_input`, `source_input_sha256`, 영상 sha256, `sources`가 원본을 연결한다.
새 테스트에는 eval_only를 복사하지 않았다. dev08 재생은 저장 추정/입력에 대한 **트리거 시점 검사**이며
반사실적인 새 look의 물리 효과를 재현한 것이 아니다. resume/실패 주입은 명시적인 가짜 host/관측 fixture다.

## 코디네이터 실행 명령 — 작성만, 실행하지 않음

코디네이터 **owner=claude**가 검토·커밋한 뒤 깨끗한 SHA를 두 회차 동안 고정한다.
`execution_source_sha=null`은 이 구현 작업이 커밋하지 않았다는 뜻이다.
실행 SHA는 필수 `--expected-source-sha`와 각 manifest에 기록한다.

준비만 확인(물리·모델 호출 없음, 출력은 매번 새 경로):

```sh
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-27-zone-pair-dev/prereg_v5b.json \
  --run-id dev09 --output /tmp/zone-pair-dev09-v5b-prepare-NEW
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-27-zone-pair-dev/prereg_v5b.json \
  --run-id dev10 --output /tmp/zone-pair-dev10-v5b-prepare-NEW
```

검토·소스 고정 후 코디네이터만 실행:

```sh
bash <<'PAIR_DEV_V5B'
set -euo pipefail
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_OWNER=claude
PAIR_BRANCH=$(git branch --show-current)
PAIR_SHA=$(git rev-parse HEAD)
PAIR_PREREG=experiments/2026-09-27-zone-pair-dev/prereg_v5b.json
PAIR_ROOT="/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v5b-$PAIR_SHA"
test "$PAIR_BRANCH" != main
test -z "$(git status --porcelain)"
"$PAIR_PY" scripts/disk_report.py
"$PAIR_PY" scripts/agent_lock.py status
"$PAIR_PY" scripts/agent_lock.py acquire --owner "$PAIR_OWNER" --branch "$PAIR_BRANCH" \
  --purpose "pair-v5b-dev09-dev10 $PAIR_SHA; no model calls" --pid "$$" --expected-minutes 1925
trap '"$PAIR_PY" scripts/agent_lock.py release --owner "$PAIR_OWNER"' EXIT
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
for PAIR_RUN in dev09 dev10; do
  "$PAIR_PY" scripts/ugrp_session.py run "pair-$PAIR_RUN-${PAIR_SHA:0:8}" -- \
    "$PAIR_PY" -m scripts.sim_cli workflow run zone-pair-dev \
    --record "$PAIR_ROOT/$PAIR_RUN-managed" --timeout 57660 -- \
    --prereg "$PAIR_PREREG" --run-id "$PAIR_RUN" --output "$PAIR_ROOT/$PAIR_RUN" \
    --execute --expected-source-sha "$PAIR_SHA" --lock-owner "$PAIR_OWNER"
done
PAIR_DEV_V5B
```

실제 물리 실행은 이번 작업에서 하지 않았다. 잠금 실패·host 오류 시 시작/후속 실행을 중단하고,
기존 출력 덮어쓰기와 자동 재실행을 하지 않는다. 두 실행의 총 SIM/wall 한도·submit 시각·
abort 개입 시점·종료 관찰은 v3와 같다. 이 wall 예산은 완료 예상 시간이 아니다.

## 최초 v5 작성 당시 검증과 남은 확인

아래 수치와 준비 성공은 최초 v5 작성 당시 기록이며 현재 소스 검증으로 승계하지 않는다.
현재 v5b 검증은 위 review4 반영 기록을 따른다.

[검증 기록](grasp_v5_validation.json): **480 passed, 13 skipped, 1 deselected / 21.44 s**.
새 v5 회귀 **35개**가 포함된다. MuJoCo import를 요구하는 13개 fake-world 검사는 import 차단으로
건너뛰었고, sandbox에서 `ps`가 금지된 프로세스 정리 검사 1개는 제외했다.
dev09/dev10 prepare는 둘 다 `prepared_not_executed`, `applied=null`, 모델 호출 0과 prereg 바이트 복사,
setup-only scene hash 일치를 확인했다. 과거 기록/보호 소스 **33개**와 사용한 raw 해시가 일치하고,
`.pytest_tmp` 삭제·AST·`git diff --check`·문서 링크 검사를 마쳤다.
물리·모델 import를 막은 환경에서 `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`,
`--basetemp=./.pytest_tmp`, `-p no:cacheprovider`로 실행하고 `finally`에서 `.pytest_tmp`를 지운다.

검증 범위: dev07 원본 END_CLIPPED→READY(상대 준비 없이 닫기 없음), anchor 비갱신,
문설주·잘못된 색·누락/만료/불일치·σ/PWM/stale 반례, dev08 15.3초 공백의 조기 재관측,
공통 pose·새 태그 요구, 횟수/시간 상한과 양쪽 안전 중단, 기존 STATUS·동기 close·물리 판정 회귀.

**실제 dev09/dev10 운반·재관측 성공·예정 abort는 미검증**이다. 검토·소스 커밋/고정과
코디네이터의 별도 유한 물리 실행이 남는다. 이 작업은 커밋·push·PR 변경·병합을 하지 않는다.
Git fetch는 공유 FETCH_HEAD 쓰기 제한, gh는 네트워크 제한으로 실패했다. 연결된 GitHub 도구로
열린 PR 목록·PR #240 head·이슈 #221 최신 결정을 확인했다. 기본 checkout은 갱신하지 않았다.

새 물리/학습/평가 결과가 없어 TensorBoard 재변환·서버 시작·화면 재개방은 하지 않는다.
코디네이터가 실행한 뒤 성공·실패 모두 새 native snapshot에 추가하고, 영상 등록·실제 데이터 로딩·
핀/HParams·화면을 확인해야 한다. 이전 진단의 공유 표시 미완료를 이번 검증으로 해결됐다고 주장하지 않는다.
UGRP 예외에 따라 Google Drive는 사용하지 않는다. 로컬 fixture 보존은 원격 raw 백업이 아니다.
