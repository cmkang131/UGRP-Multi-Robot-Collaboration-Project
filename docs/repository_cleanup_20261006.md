# UGRP 정리 기록 — 2026-10-06

## 범위와 기준

사용자 요청("안 쓰는 코드들이나 설명들을 없애서 레파지토리를 정리")에 따라 정리했다. 기준 main은 `b07f33aba278fda7434acaed0974c3d38f7b9ef0`이다. `experiments/`, 실행 코드 경로, 설정, 테스트, 물리 환경, 모델, raw 자료는 변경하지 않았다. 삭제한 파일은 모두 기준 main에서 `git show b07f33ab:<경로>`로 복원할 수 있다.

## 판정 방법

추적 파일 10,082개 중 `harness/`, `sim/`, `scripts/`, `configs/`, `config/`, `maps/`, `examples/`, `notebooks/`, `calibration/`의 각 파일에 대해 파일명·모듈 경로를 다른 추적 파일(코드·테스트·문서·실험 기록)에서 검색했다. `docs/`의 Markdown은 파일명이 다른 곳에서 언급되는지 확인했다.

- 코드에서 참조되지 않는 파일은 31개였다. 대부분 유지했다: `configs/simulation_workflows.d/*.json`은 `sim/workflow_manager.py`가 glob으로 읽고, `configs/zone_study_scenarios_v3`·`v4`는 열린 사전 등록 PR #397이 쓰며, 진단 스크립트(`v98_light_summary.py`, `diagnose_opencv_columns.py` 등)는 최근 실험 기록이 재현 도구로 인용한다. 실물 로봇 설정, Colab·Kaggle 유한 배치 경로(AGENTS.md가 보존 대상으로 명시)도 유지했다.
- `scripts/sim_worker_failover.py`, `scripts/gpu_worker_recover.py`, `scripts/systemd/*`는 퇴역한 클라우드 자동 복구에서 유래했지만 지금도 `harness/web.py`와 `tests/test_gpu_recovery.py`가 Mac 전용 정책으로 사용하므로 유지했다.

## 삭제한 파일

| 경로 | 마지막 변경 | 이유 |
|---|---|---|
| `agent.md` | 2026-09-09 | `AGENTS.md`로 대체된 옛 Claude 진입 지침. 저장소에서 참조하는 곳이 없다(결정 이력의 과거 언급 제외). |
| `scripts/serve_open_webui.sh` | 2026-09-07 | Open WebUI는 결정 이력에서 제품 경로에서 제외됐다. 참조하는 곳이 없다. |
| `docs/PR_failure_self_correction_loop.md` | 2026-09-07 | 구현되지 않은 2026-08-30 제안서(`harness/failure_analysis.py` 미존재). 참조하는 곳이 없다. |
| `docs/coela_fix_progress.md` | 2026-09-07 | 끝난 CoELA 수정의 진행 메모. 참조하는 곳이 없다. |

## 원격 브랜치

로컬 추적 참조 기준으로 `origin/main`에 병합됐고 열린 PR의 head나 등록된 worktree가 쓰지 않는 브랜치 27개를 골랐다. 삭제 직전 `git ls-remote`로 다시 확인하니 23개는 GitHub에서 이미 삭제된 상태(오래된 로컬 추적 참조)였고, 원격 tip이 기록과 같고 main에 포함된 4개만 삭제했다. 강제 push는 하지 않았다. 각 tip SHA는 main에서 도달 가능하므로 `git push origin <SHA>:refs/heads/<브랜치>`로 복원할 수 있다. 목록은 아래 표에 있다.

| 삭제한 브랜치 | 복구용 tip SHA | 마지막 커밋 |
|---|---|---|
| `claude/archive-v6c-fixtest-0929` | `d30381e4dece575f226f73535991312f325732b0` | 2026-09-29 |
| `claude/llm-eye` | `ec0215f37118f8cbb0a656621ac89cc3279d400e` | 2026-10-05 |
| `claude/zone-team-a2-dev` | `64daf56d936466920ca65147604d06502d98d8ac` | 2026-09-26 |
| `codex/act-render-speed` | `074f1ec640661508c37bbb9289fe2b9ea814a420` | 2026-09-22 |

worktree가 쓰는 병합 브랜치 4개(`claude/solo-cyan`, `codex/critb-heldout-new-starts`, `codex/docs-s1-s2-fixups`, `codex/s1-placement`)와 미병합 브랜치는 유지했다.

## 정리하지 않은 것

- 기본 체크아웃 최상위의 추적되지 않는 로컬 파일(`ugrp_budget_repair_*.zip`·`.md`, `work_diff_check.py`, `r1-nav-cam-camera-team-seed41.png`, `AGENTS (1).md`, `MUJOCO_LOG.TXT`, `tmp/`, `work/`)은 GitHub에 없고, 로컬 자료 삭제는 사용자 결정이므로 건드리지 않았다.
- `docs/research_parallel/`과 날짜가 붙은 결과·분석 문서는 접두사 참조나 과거 실패·결과 기록이므로 유지했다.
