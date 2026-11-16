# 파지 재관측·close 동기화 v4 — 2026-09-27

**tags_temporary · dev · 연구 결과 아님. 구현·비물리 회귀만 수행. 물리 실행·모델 호출·커밋 없음.**

[진단 권고안](diagnosis_v4.md)과 [이슈 #221 코디네이터 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5853660231)을 구현했다.
과거 사전등록·결과·번들은 보존한다. dev05/dev06의 실패를 새 성공으로 재판정하지 않는다.

## 버전과 변경 범위

- 사전등록: [prereg_v4.json](prereg_v4.json), dev07/seed903 정상 시도와 dev08/seed904 운반 중 abort 진단.
  v3의 두 화물 배치·주문서·개입을 유지하며 spawn/PF seed를 새로 고정했다.
- 공동 실행기 `zone_pair_executor_v5_dev`, 상태 채널 `zone_pair_status_v5`,
  파지 계약 `zone_pair_grasp_relook_v1`, 공통 workflow `zone-pair-dev` **0.3.0**.
  `grasp_contract`는 구현·평가·workflow 파일 해시를 묶고 prepare/execute 진입 때 검증한다.
- 파지마다 자기 손목 RGB로 다시 둘러본다. 새 태그가 이번 sweep에서 관측되고,
  guard가 읽는 **동일한 `own.pose/last_report`**가 갱신되어야 내려갈 수 있다.
  VO가 있다는 이유로 생략하거나 VO 좌표로 PF를 덮어쓰지 않는다.
- 파지 준비 기준은 **σxy ≤5 cm, σyaw ≤3°**. 기존 gate의 HIGH/LOW·dwell,
  35 mm 기본 여유(20+15 mm)와 불확실성 팽창식을 바꾸지 않았다.
  준비 기준과 기존 loaded HIGH 7 cm를 구분한다. 관측 실패는 기존 두 sweep 및 누적 guard 대기 예산 안에서 중단한다.
  이는 **원본 M2 재관측의 6 cm와 다른 신규 준비조건**이다. 근거는 동결
  `scripts/run_m2_pair.py`의 `PREGRASP_FIX_STD_M=.06` 및 `_pregrasp_look()`이며,
  원본은 initialized·σxy만 검사하고 이 위치에 별도 3° 조건은 없다.
  어댑터 `harness/zone_pair_grasp.py`의 `_grasp_pose_ready()`는 close를 허가하기 위해
  동일 guard 추정·새 태그·freshness·gate OK에 **5 cm/3°**를 추가로 요구한다.
  불확실한 추정에서 닫기를 허가하지 않기 위한 보수적 후보 조건이며, 개선 효과를 물리 검증한 값은 아니다.
  이번 P1 수정은 두 경로의 수치를 모두 유지한다. “임계값 불변”은 v4 준비조건과
  기존 guard HIGH/LOW·35 mm를 이번 수정에서 바꾸지 않았다는 뜻이며 M2 6 cm와의 동일성을 뜻하지 않는다.
- 기존 팔 궤적으로 집게를 **열고** 내려간 후 `wait_close`에 들어간다. 자기 위치·발행 자세·
  신선한 자기 RGB의 grip-view를 검사하고, 양쪽 `close_ready_i`가 모인 뒤 같은 제어 격자의
  `close_go_i`를 소비해야 닫는다. 준비 증거 TTL 0.6 s, heartbeat와 arm/control 주기는 그대로다.
  상대가 늦으면 열린 상태로 최대 20 SIM초 대기하며, 증거 만료·위치 불확실·상대 중단은 안전 중단한다.
- 빔 영역은 `grasp`라는 단계 이름이나 닫힘 PWM만으로 활성화하지 않는다.
  실제로 **발행된 CLOSED 명령 이후**의 자기 RGB 파지 판독이 통과해야 해당 segment의
  관측 영수증을 만들고 전체 빔 영역을 포함한다. OPEN 발행·segment 변경으로 무효화된다.
  이는 guard용 영상 기반 부착 추정이며 물리 파지 성공이 아니다. 기존 lift 후 co-motion 검사는 유지한다.
- **PR #240 P1 수정:** 위 부착 영역과 별개로, close READY 발행 전과 **매 닫기 PWM 직전**에
  자기 RGB의 빔 band 중심·축 방향 추정으로 정지 빔 전체 영역을 만들고 정적 벽·문설주를 검사한다.
  정적 바닥/빔 윗면 평면과 역할별 빔 형상을 사용하며, 미파지 빔을 손목에 붙여 이동시키지 않는다.
  기존 35 mm(20+15 mm)·자기 자세의 2σ 팽창에 RGB fit의 횡방향 scatter와
  `atan2(scatter, visible_length)` 방향 불확실성을 추가로 2배 팽창한다.
  따라서 반환 여유 0 미만은 불확실성 영역과 벽 사이 여유가 35 mm 미만임을 뜻한다.
  clipped/end 미확인·band 중심 없음·비유한/누락 fit·비양수 가시 길이·fit 불확실성 5 cm/3° 초과,
  오래되거나 불확실한 자기 추정은 READY를 거부하고 안전 중단한다. 닫는 중 실패는 양쪽 남은 큐를 취소한다.
  저장된 `grip_base`, 작업지시서 위치 또는 발행 손목 위치로 누락된 RGB 빔 추정을 대신하지 않는다.
  scatter 기반 값은 이 dev 후보의 기하 불확실성 추정이며 통계적으로 보정된 오차 보장은 아니다.
  기존 grip-view가 통과해도 전체 빔 fit이 clipped이면 중단될 수 있다. 실제 카메라에서의 가용성과
  새 조건 파지 성공은 미검증이며, 실패 시 GT·접촉·측정 관절·`eval_only`로 우회하지 않는다.
- 자기 파지가 확인됐거나 상대가 파지/운반 상태를 보낸 뒤에는 일방적인 재관측 sweep을 금지한다.
  GT·접촉 센서·측정 관절·상대 pose를 파지 판단에 넣지 않는다.
- 장면은 `zone_wide_door_tags_v2_dock_v3`, dock x=−0.65 m, 벽 0.10 m·tags_v2 그대로다.
  **cargo_noslip_v1, noslip 10, timestep 0.00025 s, weld OFF**, 카메라/FOV·지도·보정을 유지한다.
- `criteria`, `stage_rules`, `planned_setdown`, `limits`, `timing`, `safety_coverage`, `environment`,
  `inputs`는 v3와 동일하다. v4에서만 새 `pregrasp_descend`/`wait_close`를 기존 `grasp`의
  세부 단계로 읽는다. 원시 상태 이름은 보존하며, 허가된 checkpoint 구간·바닥 지지·재들기·
  낙하·접촉 판정과 수치 기준은 유지한다. ENOSPC는 기존 HOST_ERROR 경로다.

## 번들 번호와 소스 보존

[로컬 ref 목록](grasp_v4_ref_inventory.json)은 main과 조회한 열린 PR 12개의 로컬
remote/head refs를 기록한다. 로컬 RUNNABLE_ID 최댓값은 v63이지만 사용자 전달대로
**v64는 PR #229에서 사용 중인 번호**로 취급한다. fetch는 공용 Git 디렉터리 쓰기 제한으로
실패했고 GitHub 목록/최신 이슈 결정은 connector로 조회했다.

수정한 소스는 RGB dispatch의 `source_closure()`와 겹치지 않는다.
**새 RGB 실행 번들 ID를 만들거나 예약하지 않았다.** 위 공동 실행기·상태·workflow 버전과
사전등록의 source hash 계약으로 후보를 식별한다. 향후 RGB 번들이 필요하면 당시
main/열린 PR의 최대 번호를 다시 검사하고, 최소 v65 이상을 사용한다.
동결 M2 원본과 import manifest의 소스는 바이트 그대로 유지한다.
과거 v3는 이전 실행 소스를 가리키므로 새 코드에서 그대로 실행하려 하면 source hash 검사로 거부된다.

**P2(STATUS v5의 #229 통합)는 이 PR에서 하지 않는다. #229 병합 후 후속 PR에서 새 번들·사전등록으로 반영.**
그때 STATUS enum·실행기/소스/설정 해시와 실제 close 장벽 통합을 함께 검증한다.

## 코디네이터 실행 명령 — 작성만, 실행하지 않음

코디네이터 **owner=claude**가 검토·커밋한 뒤 깨끗한 SHA를 두 회차 동안 고정한다.
`execution_source_sha=null`은 이 구현 작업이 커밋하지 않았다는 뜻이다.
실행 SHA는 필수 `--expected-source-sha`와 각 manifest에 기록한다.

준비만 확인(물리·모델 호출 없음, 출력은 매번 새 경로):

```sh
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-27-zone-pair-dev/prereg_v4.json \
  --run-id dev07 --output /tmp/zone-pair-dev07-prepare-NEW
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 "$PAIR_PY" scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-27-zone-pair-dev/prereg_v4.json \
  --run-id dev08 --output /tmp/zone-pair-dev08-prepare-NEW
```

검토·소스 고정 후 코디네이터만 실행:

```sh
bash <<'PAIR_DEV_V4'
set -euo pipefail
PAIR_PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PAIR_OWNER=claude
PAIR_BRANCH=$(git branch --show-current)
PAIR_SHA=$(git rev-parse HEAD)
PAIR_PREREG=experiments/2026-09-27-zone-pair-dev/prereg_v4.json
PAIR_ROOT="/Users/changmin/projects/ugrp/outputs/zone-pair-dev-v4-$PAIR_SHA"
test "$PAIR_BRANCH" != main
test -z "$(git status --porcelain)"
"$PAIR_PY" scripts/disk_report.py
"$PAIR_PY" scripts/agent_lock.py status
"$PAIR_PY" scripts/agent_lock.py acquire --owner "$PAIR_OWNER" --branch "$PAIR_BRANCH" \
  --purpose "pair-v4-dev07-dev08 $PAIR_SHA; no model calls" --pid "$$" --expected-minutes 1925
trap '"$PAIR_PY" scripts/agent_lock.py release --owner "$PAIR_OWNER"' EXIT
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
for PAIR_RUN in dev07 dev08; do
  "$PAIR_PY" scripts/ugrp_session.py run "pair-$PAIR_RUN-${PAIR_SHA:0:8}" -- \
    "$PAIR_PY" -m scripts.sim_cli workflow run zone-pair-dev \
    --record "$PAIR_ROOT/$PAIR_RUN-managed" --timeout 57660 -- \
    --prereg "$PAIR_PREREG" --run-id "$PAIR_RUN" --output "$PAIR_ROOT/$PAIR_RUN" \
    --execute --expected-source-sha "$PAIR_SHA" --lock-owner "$PAIR_OWNER"
done
PAIR_DEV_V4
```

실제 물리 실행은 이번 작업에서 하지 않았다. 잠금 실패·host 오류 시 시작/후속 실행을 중단하고,
기존 출력 덮어쓰기와 자동 재실행을 하지 않는다. 두 실행의 총 SIM/wall 한도·submit 시각·
abort 개입 시점·종료 관찰은 v3와 같다. 이 wall 예산은 완료 예상 시간이 아니다.

## 검증과 남은 확인

[검증 기록](grasp_v4_validation.json)에 전체 변경 파일·해시·테스트 결과·보존 검사를 기록한다.
회귀는 가짜 world, 저장 RGB, 명시적인 자세/태그 fixture를 사용한다.
관측 fixture의 좌표는 평가 GT가 아니며, fixture 통과로 실제 위치 추정 정확도를 주장하지 않는다.

- dev05의 미파지 가상 빔 벽 여유 약 −0.414 mm를 재현하고, 새 미파지 팔 검사 통과를 확인한다.
  파지 확인 뒤에는 같은 빔-벽 반례가 계속 중단되어야 한다.
- dev06의 yaw 0.05238 rad를 재현한다. 재관측 후 기준 안이면 진행하고, 초과/태그 미획득이면
  닫지 않고 안전 종료한다. VO-only 생략·낡은 추정·한쪽만 준비·이미 파지한 일방 sweep을 막는다.
- 파지 영수증은 발행 close와 그 뒤 자기 RGB를 모두 요구하고 OPEN/segment 변경을 검사한다.
  새 checkpoint 단계에도 실제 낙하·잘못된 구간/위치·GO 누락 반례를 유지한다.
- dev07/dev08 prepare는 MuJoCo import를 차단한 자식 프로세스로 확인한다.
  `prepared_not_executed`, `applied=null`, model_calls=0 및 prereg 원본 복사를 검증한다.
- pytest는 `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`, `--basetemp=./.pytest_tmp`,
  `-p no:cacheprovider`로 실행하고 `finally`에서 `.pytest_tmp`를 지운다.
  MuJoCo step 함수와 모델 라이브러리에 실행 차단장치를 둔다.

실제 새 seed에서 재관측·동시 파지·lift·문·배치·예정 abort는 **미검증**이다.
새 물리/학습/평가 결과가 없어 TensorBoard snapshot은 만들지 않았다. 코디네이터가 실제 실행한 뒤
성공·실패 모두 기존 원본을 보존하며 `docs/tensorboard.md`에 따라 새 native snapshot과 영상 등록,
실제 데이터 로딩·화면·핀/HParams를 확인한다. Google Drive 업로드는 프로젝트 예외에 따라 하지 않는다.

P1 수정 전 비물리 회귀 기록: **581 passed, 2 deselected / 27.25 s**.
제외 항목은 실제 MuJoCo world 테스트와 sandbox에서 `ps`가 제한되는 프로세스 정리 테스트다.
최종 실행의 step 호출 시도는 0회다. 앞선 확장 검사에 실제 world 테스트가 섞였으나
첫 `mj_step`을 차단장치가 거부하여 물리 step 실행은 0회였고, 그 검사와 중간 fixture 수정 이력도
검증 JSON에 남겼다. 최종 `git diff --check`·Python AST 구문 검사 통과,
기존 실험 파일 19개 원본 일치·동결 M2 소스 보존·필요 파일 존재를 확인했다.

### PR #240 P1 수정 후 비물리 검증

[추가 검증 기록](grasp_v4_p1_validation.json): **406 passed / 18.90 s**.
`test_zone_pair_preclose.py`의 23개 검사로 문설주 반례, 35 mm 경계,
RGB 빔 추정 누락·clipped·불확실성·stale 입력, 닫기 첫/중간/마지막 PWM의 양쪽 중단을 확인했다.
동일한 자기 추정 `(1.5, 0.4, 0)`, σxy=1 mm fixture에서 팔 여유 +423 mm,
정지 빔 raw 여유 −27.5 mm를 재현했다. HEAD의 이전 READY/command 검사 두 함수를
적용하면 각 로봇에 1986→1500 닫기 명령 10개, 수정본에서는 위험 로봇 READY 없음·양쪽 **0개**다.
물리 step 시도 0·실행 0, 모델 호출 0, `.pytest_tmp` 삭제를 확인했다.
아직 실행 전인 `prereg_v4.json`의 grasp 계약·소스 해시를 갱신했고,
과거 판정 8개 필드·실험 19개·동결 import 32개는 보존했다. 커밋·push는 하지 않았다.
