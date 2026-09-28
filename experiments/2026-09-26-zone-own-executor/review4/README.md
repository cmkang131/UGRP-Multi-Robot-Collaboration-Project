# PR #206 4차 리뷰 수정 검증 — 2026-09-27

기준 HEAD: `6fde26071b602f56770047a4838820b93b876559`.
리뷰 원문: `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-206-review4.md`.
커밋·push·물리 실행 없이 작업 트리에서 수정했다. 아래는 비물리 회귀검사 결과이며 운반 성공·속도 측정이 아니다.

## 수정과 반례

| 항목 | 수정 | 수정 전 → 수정 후 |
|---|---|---|
| P1 후퇴 전 게이트 대기 | `SweepRecheck`의 같은 누적 10 SIM초 예산을 사용한다. 소진 시 `SWEEP_GATE_TIMEOUT`과 gate·waited_s 진단으로 1회 종료한다. 게이트가 열릴 때 대기 시간을 정산하여 이동 시간은 제외하고, 이후 arm/pan/restore 재관측에 남은 예산만 쓴다. | 직접 look·배송 전 look, 이후 arm 대기와 합산, 게이트 재진입: 4 실패 → 4 통과 |
| P2-1 화물–벽 접촉 | 실행기의 `loaded`를 평가 집계에서 사용한다. 활성 driver의 load 상태와 기존 goto의 보수적 적재 판정을 공유하므로 abort·대기·loaded goto 종료 뒤에도 배정 화물의 접촉을 센다. 평가 접촉을 제어나 사건 입력에 전달하지 않는다. | abort·goto 시작 전/중/종료 뒤 × 접촉 순서 양방향: 8 실패 → 8 통과. 방출·미배정 화물 제외 대조군 2개는 전후 통과 |
| P2-2 leg 진단 소실 | leg 제거 전에 `sweep_failure`를 깊은 복사로 archive에 저장한다. `CARRY_LEG_*` 실패는 해당 outcome과 일치하는 마지막 leg에서 진단을 회수하여 `detail.guard`와 작업 결과에 남긴다. | 실제 GuardedDriver와 M1 carry 종료 경로의 archive·외부 사건·작업 기록: 3 실패 → 3 통과 |

신규 테스트: `tests/test_zone_own_executor_review4.py`.
기존 review3 접촉 fixture에는 적재 여부를 나타내는 `box.held`를 추가했다. 기존 기대값·assertion은 유지했다.

## 실행 기록

- `before.txt`: 구현 변경 전 신규 테스트 **15 failed, 2 passed**.
- `baseline.txt`: 구현 변경 전 기존 관련 비물리 테스트 **155 passed, 85 subtests passed, 1 deselected**.
- `after.txt`: 구현 변경 후 신규 테스트 **17 passed**.
- `regression.txt`: 기존 + 신규 **172 passed, 85 subtests passed, 1 deselected**.
- 제외한 검사는 `test_team_host_isolation_abort_and_horizon_on_the_real_world`다. 다른 검사는 scripted pose·fake host·정적 지도·저장 fixture를 사용했다.

모든 pytest 호출에 `OMP_NUM_THREADS=1`과 `--basetemp=./.pytest_tmp`를 적용했다. Python은 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 재사용했다.

최종 명령(독립 테스트 사본을 cwd로 실행):

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_boundaries.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_host.py \
  tests/test_zone_own_executor_review3.py tests/test_zone_own_executor_sweep_start.py \
  tests/test_zone_own_executor_review4.py tests/test_m1_owncam.py \
  -k 'not real_world' --basetemp=./.pytest_tmp --tb=short
```

## 환경·보존 범위

공용 `outputs/agent-locks/physics`에 대한 쓰기가 sandbox에서 거부되어 작업 worktree의 pytest는 시작하지 않았다. `CONTRIBUTING.md`의 별도 clone 실행 경로에 따라 `/private/tmp`에 독립 소스 사본을 만들고 위 비물리 검사만 수행했다. 실제 물리·학습 프로세스나 공용 서버는 시작하지 않았다.

검사 사본과 작업 트리의 파일 일치·변경 파일 SHA-256·로그 SHA-256 및 정리 상태는 `test_workspace.json`에 기록했다. 검증 로그는 이 폴더에 남기고 임시 사본과 `.pytest_tmp`는 삭제했다. UGRP 규칙에 따라 Google Drive는 사용하지 않았다.

`git fetch origin`은 공용 Git 메타데이터의 쓰기 권한, `gh pr list`는 GitHub 연결 제한으로 실패했다. 원격 HEAD·PR 상태·CI는 재확인하지 않았으며, 이 기록은 위 로컬 HEAD에 대한 미커밋 수정과 로컬 검사 범위다.
