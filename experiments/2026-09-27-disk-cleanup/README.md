# 2026-09-27 디스크 정리 (무손실 항목만)

작성: 2026-09-27, Claude(`claude/disk-cleanup-0927`). 사용자 요청 "정리 좀 잘 해봐"(2026-09-27). Refs #226, #3.

[디스크 관리 문서](../../docs/disk_management.md) 3절 #3·#4·#11과 [09-26 적용 기록](../2026-09-26-disk-apply/README.md)의 방식을 그대로 썼다. 기존 도구 `scripts/agent_worktree.py`(retire·sparsify), `scripts/disk_report.py`, `experiments/2026-09-26-disk-apply/dedupe_outputs.py`, fclones 0.35.0을 다시 썼다.

- **raw는 하나도 삭제·압축·외부 이동하지 않았다.**
- 지운 것은 두 종류다. 하나는 git이 다시 만들 수 있는 추적 checkout 사본(은퇴·sparse)이고, 다른 하나는 캐시(`__pycache__`, `.pytest_cache`)다.
- 물리 실행, 다른 작업의 프로세스 종료, force push, Google Drive 사용은 하지 않았다.

## 결과

| 항목 | 대상 | `du` 감소 | `df` 변화 | 검증 |
|---|---|---|---|---|
| 1. 병합된 worktree 은퇴 | 10개 (Claude 2, Kiro 8) | 3.99 GiB | +2.95 (16:04:01→16:04:47) | 10/10: 무시 자료 이동 전후 개수·바이트·sha256 일치, `git worktree remove` exit 0 |
| 2. sparse 전환 | 1개 (`ugrp-worktrees/zone-team-a2`) | 0.92 (1.76→0.84) | 항목 3과 합쳐 +0.39. 다른 작업의 쓰기가 섞여 있다 | HEAD 그대로, 추적 변경 없음, `git status --ignored` 전후 동일 |
| 3. 캐시 삭제 | 사용 중이 아닌 worktree 8개, 31개 폴더 | 0.014 | (위와 합산) | 무시된 캐시 폴더만 지웠다([목록](footprint/caches-deleted.tsv)) |
| 4. APFS clone 중복 제거 | 기본 체크아웃 `outputs/`, 09-26 뒤 새 중복 9,310그룹 54,386개 | 0 (`du`는 clone을 전체 크기로 센다) | +0.82 (16:15:32→16:15:46) | 54,386개 경로를 hashlib로 다시 해시해 크기·sha256·mode·mtime을 비교했다. 문제 0 |

전체 측정([전](footprint/disk-report-before.txt)·[후](footprint/disk-report-after.txt), `disk_report.py`):

| 구분 | 15:57 | 16:16 | 비고 |
|---|---|---|---|
| 파일시스템 여유 (`df`) | 105.77 GiB | 109.84 GiB | +4.07. 같은 시간 동안 다른 작업이 쓴 양도 섞여 있다 |
| `outputs/` (`du`) | 75.46 | 75.59 / 예산 40 | +0.13. 영수증·옮겨 온 무시 자료 1 MB와 다른 작업의 새 실행이 늘었다 |
| worktree (`du`) | 23.61 (39개) | 19.96 (31개) / 예산 10 | 이 작업의 감소는 −4.92다. 같은 시간에 새 worktree 2개(`merge-235` 1.06, `codex-pair-grasp` 0.14)가 생겼다 |
| 프로젝트 합계 | 103.65 | 100.12 / 예산 58 | |

- 이 작업의 순수 절감은 항목별 `df` 변화의 합 약 4.2 GiB로 본다. `du` 기준으로는 worktree에서 4.92 GiB다.
- `outputs/` 40 GiB 예산에는 아래 raw 결정이 필요하다. 무손실 항목만으로는 도달할 수 없다.

## 1. 은퇴한 worktree

모두 HEAD가 origin/main의 조상이거나, 병합된 PR의 head(`refs/pull/<N>/head`)와 같았다. 그래서 origin에 없는 커밋은 없다. **push 안 된 커밋 때문에 은퇴하지 못한 worktree는 0개**다.

각 은퇴 직전에 두 가지를 다시 확인했다. 먼저 `git fetch origin`과 `gh pr list --head <브랜치> --state open`을 실행했다. 이어서 `retire`의 기본 검사를 거쳤다: 미커밋·미추적 0, 프로세스 cwd·열린 파일·명령줄, `--idle-minutes 120`.

| worktree | HEAD | 병합 근거 | 옮긴 무시 자료 (→ `outputs/retired-worktrees/claude0927-<이름>/`) | checkout 추정 |
|---|---|---|---|---|
| `ugrp-wt/claude-todo-dr-sim2real` | cd01e170 | main 조상 (#215) | 없음 | 0.13 |
| `ugrp-wt/kiro-disk-rules` | 207586fc | main 조상 (#231) | `MUJOCO_LOG.TXT` 272 B | 0.15 |
| `ugrp-wt/kiro-eval-topcam` (detached) | ead4b970 | main 조상 | `experiments/2026-09-26-zone-eval-topcam/` 40 KB (무시된 폴더) | 1.05 |
| `ugrp-wt/kiro-m2-pair` | 6990a6ed | PR #205 병합 head와 같음 | 없음 | 0.13 |
| `ugrp-wt/kiro-memory-literature` | 3174c2f8 | main 조상 (#230) | 없음 | 0.13 |
| `ugrp-wt/kiro-pilot-records` | 2ff15d93 | PR #238 병합 head와 같음 | 없음 | 1.06 |
| `ugrp-wt/kiro-references-0926` | bdcaf2a3 | main 조상 (#228) | 없음 | 0.13 |
| `ugrp-wt/kiro-vision-loc-v3` | 1aa8f0c7 | main 조상 (#233) | `MUJOCO_LOG.TXT` 136 B | 1.05 |
| `ugrp-wt/kiro-vision-loc-v3src` (detached) | 7cedb049 | main 조상 | 없음 | 0.01 |
| `ugrp-wt/zone-m1-owncam` | 1b836a1d | main 조상 (#201) | `MUJOCO_LOG.TXT`, `outputs/real_traces`(3), `outputs/sim_traces`(3), `outputs/simulation-runs`(4, 0.98 MB) | 0.15 |

- `zone-m1-owncam`의 `outputs/simulation-runs`는 기본 체크아웃에 같은 이름이 이미 있다. 그래서 도구 규칙대로 은퇴 폴더로 옮겼다.
- 파일별 목록은 `MANIFEST.tsv`, 영수증은 `RETIRED.json`이다. 둘 다 각 은퇴 폴더에 있고, `outputs/retired-worktrees/retirements.jsonl`에도 영수증이 추가됐다.

## 2–3. sparse 전환과 캐시

- `ugrp-worktrees/zone-team-a2`(PR #169 병합)는 은퇴하지 않았다. 열린 PR #207의 코드가 이 worktree의 `outputs/zone-team-a2-20260925/a-two-dynamic-s12`를 절대 경로로 읽기 때문이다(`experiments/2026-09-26-zone-teacher-fix/b5_offline.py`, `offline_addendum.py`).
  - 대신 추적 checkout만 sparse로 바꿨다. 무시된 `outputs/`(0.71 GiB)는 그대로다.
  - 이 worktree는 2시간 안에 수정된 파일이 없고, cwd로 쓰는 프로세스도 없다.
- 캐시를 지운 곳은 사용 중이 아닌 8개다: `zone-team-a2`, `kiro-ko-pilot-fix`, `kiro-study-scenarios`, `kiro-m2-pair-s2c-frozen`, `zone-m2-pair-s1/s2/s2b/s3-frozen`.
  - `git status --ignored`에 나온 캐시 폴더만 지웠다. 대상은 `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.pytest_tmp`다.
  - 주의: 이 반복문 안의 "2시간 내 수정" 검사는 제대로 돌지 않았다. 셸의 `find`가 `bfs`여서 `-newermt '-120 minutes'`를 거부했다.
  - 판정은 1분 전 전수 조사(`/bin/zsh` 스크립트, 정상 동작)를 따랐다. 거기서 8개 모두 최근 수정 없음, cwd 0이었다. 그 뒤 검사는 `/usr/bin/find`로 했다.

## 4. 중복 제거

- `fclones group outputs --min 4KiB --hash-fn sha256 -t 2 --exclude 'outputs/disk-cleanup-20260927/**'`로 찾았다. 결과는 151,096그룹, 중복 파일 551,024개(29.5 GB)였다.
- 09-26에 이미 clone한 그룹은 [`drop_done_groups.py`](drop_done_groups.py)로 뺐다. 모든 경로가 09-26 사전 manifest에 같은 sha256·크기·mtime으로 있는 그룹이 대상이며, 140,718그룹이다. 같은 파일을 다시 clone하지 않으려는 것이다.
  - 남은 것은 10,378그룹, 중복 1.21 GiB다.
- `dedupe_outputs.py plan --idle-minutes 60`으로 다음을 뺐다([요약](footprint/dedupe-plan.summary.json)).
  - 60분 안에 수정된 파일 2,635개
  - 하드 링크 3,978개
  - 활동 중인 폴더: `agent-locks`, 이 작업의 영수증, `zone-pair-dev-v3-4a17…`
  - 이 기준은 요청된 30분 규칙보다 엄격하다.
- `fclones dedupe --modified-before 2026-09-27T15:14:34+09:00`가 45,076개를 clone으로 바꿨다. 계획 기준 중복은 0.99 GiB였고, `df`는 +0.82 GiB 늘었다.
- `dedupe_outputs.py verify` 결과는 54,386개 모두 문제 0이다([요약](footprint/dedupe-summary.json)).
- **worktree 파일은 중복 제거하지 않았다.** 남은 full checkout은 대부분 제외 대상이다(아래). 실행 중인 작업 아래에서 파일을 이름 바꾸고 다시 만드는 위험이 절감(추적 미디어 약 0.93 GiB/개)보다 크다고 봤다. 사용 중이 아닌 full checkout은 은퇴하거나 sparse로 바꿨다.

## 제외 목록 (손대지 않음)

| worktree | 상태 | 이유 |
|---|---|---|
| `/Users/changmin/projects/ugrp` | 기본 체크아웃 | 지시로 제외. 182커밋 뒤처져 있지만 갱신도 하지 않았다(병합 담당 에이전트 영역) |
| `ugrp-wt/codex-pair-executor` (#235) | 열린 PR | 지시로 제외(Codex 작업 중). cwd 프로세스 88개, 2시간 내 수정 |
| `ugrp-wt/kiro-study-integration` (#229) | 열린 PR | 지시로 제외. cwd 23개, 2시간 내 수정 |
| `ugrp-wt/codex-vision-loc-v4` | main 조상 | 지시로 제외(Codex 작업 중). 미추적 26개, cwd 7개 |
| `ugrp-wt/merge-235` | detached | 지시로 제외(병합 담당 에이전트) |
| `ugrp-worktrees/zone-hard-routes` (#173 병합) | 은퇴 후보 | cwd: zsh 53386·53824(09-25 시작, `sleep 60` 반복)가 그 `outputs/zone-hard-routes-20260925` 안에 있다 |
| `ugrp-worktrees/zone-team-a2` (#169 병합) | 은퇴 후보 | 열린 PR #207 코드가 그 outputs를 절대 경로로 읽는다. sparse 전환만 했다 |
| `ugrp-wt/codex-memory-v3` (#234), `codex-sim-speed-fix` (#236), `kiro-own-executor` (#206), `kiro-sim-speed` (#209) | 병합 | Codex app-server 세션 프로세스(`aside mcp`, `node_repl`)의 cwd |
| `ugrp-wt/kiro-map-v3` (#208), `kiro-vision-loc` (#227), `kiro-vision-worker` (#237) | 병합 | 2시간 내 수정 파일 |
| `ugrp-wt/kiro-owncam-memory` (#211), `kiro-teacher-fix` (#207) | 열린 PR, full | 2시간 내 수정. sparse 전환 안 함 |
| `ugrp-wt/kiro-study-core` (#194) | 열린 PR, full | cwd 63개, 2시간 내 수정 |
| `ugrp-wt/kiro-own-perception`, `kiro-records-0926b`, `kiro-report-draft`, `kiro-tb-loop`, `kiro-tb-perc`, `zone-m2-pair` | 열린 PR, 이미 sparse | 작업 중 2시간 내 수정이 생겼다(다른 에이전트 활동). 캐시도 건드리지 않았다 |
| `ugrp-wt/zone-m2-pair-s*-frozen`, `kiro-m2-pair-s2c-frozen` | 동결 소스, 미병합 | 이미 sparse. 캐시만 지웠다 |
| `ugrp-wt/codex-pair-grasp` | 새 worktree | 작업 도중 생성됨 |

## raw 정리 제안 (실행하지 않음, 사용자 결정)

### 보존 등급 재측정 (16:16, `du`, 폴더 이름 기반 추정)

[`tiers.py`](tiers.py)가 `disk_report.py`의 보존 행을 문서 4절 등급으로 나눈다([결과](footprint/tiers-after.json)).

- 줄기 등급(T0·T3–T7)은 서로 겹치지 않으며, 합은 75.59 GiB다.
- T1·T2는 이름 기준 교차 분류라 줄기 등급과 겹친다.

| 등급 | GiB (09-26 16:05) | GiB (지금) | 내용 |
|---|---|---|---|
| T0 기반·운영 기록 | 0.47 | 1.03 | TensorBoard 0.39, 디스크 작업 기록 0.57 |
| T1 test 코호트 (교차) | 8.53 | 8.86 | 기록 참조 6.65 / 참조 없음 2.21 |
| T2 dev·진단 (교차) | 12.07 | 13.85 | 기록 참조 8.48 / 참조 없음 5.38. 이미지는 약 11.7 |
| T3 `retired-worktrees/` | 13.07 | 13.09 | 이미지 4.99 |
| T4 실시간·시뮬레이션 속도 | 5.92 | 6.13 | `simulation-realtime-20260923` 3.69, `-20260924-faster` 1.29, `simulation-performance-20260923` 0.94, `sim-speed-20260926` 0.21 |
| T5 9/7 실험 ZIP (유일 사본) | 2.71 | 2.71 | `experiment-archives-20260907` |
| T6 보조 연구선 (9/8–9/24) | 24.4 | 29.40 | Jev 10.49, RGB 복구 2.66, ACT·dispatch 5.1, nav·markerless 등. test 5.61 / dev 6.18 / 미분류 17.22 |
| T7 현재 연구 (9/24–) | 20.0 | 23.24 | zone·owncam·M1·M2·계획·동적·지도·비전. test 3.25 / dev 7.21 / 미분류 12.78 |

- **외부 디스크는 연결돼 있지 않다.** `ls /Volumes`에는 `Macintosh HD`, `Recovery`, `Kiro CLI`(설치 이미지)만 있다.
- 예산 40 GiB까지 `du`로 35.6 GiB 이상 줄여야 한다.
- `du`와 `df`의 차이: clone끼리는 블록을 공유한다. 그래서 한쪽 사본만 옮기거나 지우면 `du`는 줄어도 `df` 확보량은 더 작다.
- `outputs/`는 하루 5–15 GiB씩 는다. 어느 선택지든 문서 5절의 캡처 설정(dev 1 Hz 등)을 함께 정하지 않으면 며칠 안에 다시 넘는다.

### 선택지

| 선택지 | 방법 | `outputs/` 감소 (`du`) | 결과 | **영구히 사라지는 것** |
|---|---|---|---|---|
| A. 외장 디스크 보관 (무손실, 권장) | 외장 SSD/HDD 두 벌을 산 뒤 T3·T4·T5·T6(51.33)을 복사한다. sha256 대조, 새 위치를 기록에 적은 뒤 로컬 삭제 | −51.3 | 약 24.3 GiB | 없음(두 벌·해시 대조 전제). 다만 옮긴 raw는 디스크를 연결해야 재분석할 수 있다. 디스크 구입(1 TB 휴대용 SSD 약 $150–200 × 2, 시세 확인 필요)이 든다 |
| B. 외장 없이 삭제 | T4 전체(6.13), T3 전체(13.09), T6의 test가 아닌 폴더(23.79)를 지운다. 먼저 결과에 쓴 모델 체크포인트는 GitHub Release로 올리고 검증한다(AGENTS.md 모델 보존 규칙) | −43.0 | 약 32.6 GiB | ① 실시간·속도 연구 raw 전부 ② 9/7–9/20 은퇴 worktree의 결과·영상·로그(`retired-worktrees`) ③ 보조 연구선(Jev, RGB 복구, ACT·dispatch, nav·markerless)의 dev·미분류 raw 프레임·결과 JSON·학습 산출물. 그 기록의 `raw_index` 해시는 더 이상 원본과 대조할 수 없다 |
| C. 부분 조치 (구입 전 임시) | T4 삭제(6.13) + T2 dev 프레임 5 Hz→1 Hz 솎기(T4·T6·T7 dev 이미지 약 11.7 중 80%, ≈9.4) | 약 −15.5 | 약 60 GiB (**예산 미달**) | ① 실시간·속도 연구 raw ② dev·진단 실행의 제어 입력 프레임 5장 중 4장(결정·단계 전환 프레임은 남김). 해당 dev 실행을 프레임 단위로 다시 볼 수 없다. test 코호트 raw는 모두 남는다 |

- A와 B는 섞을 수 있다. 예를 들어 T4만 삭제하고(사용자 방침상 현재 연구 대상 아님) 나머지는 외장에 보관하면 약 24.3 GiB가 되며, 사라지는 것은 T4뿐이다.
- T5(9/7 ZIP)는 유일 사본이다. 어느 선택지든 외장 두 벌 보관 전에는 지우지 않는 것을 권한다.
- GitHub Release는 저장소가 PUBLIC이라 raw가 공개된다. 모델·대표 영상처럼 공개해도 되는 묶음에만 권한다(문서 9절).
- T7(현재 연구)과 T1 test raw는 어느 선택지에도 넣지 않았다.

**사용자에게 물을 것:** (1) 외장 디스크를 살지(A) (2) T4 실시간·속도 raw 삭제에 동의하는지 (3) 외장 없이 B 수준으로 삭제할지, 아니면 C로 두고 예산 초과를 받아들일지 (4) dev 캡처를 1 Hz로 줄이는 설정을 러너에 적용할지.

## 추가: raw 선택지 B 준비 (2026-09-27 16:27–16:32) — **삭제는 실행하지 않음**

코디네이터가 "사용자 결정: B(외장 없이 크게 삭제)"를 전달했다. 이 작업은 다음까지 했다: 계획, 제외 판정, 전체 파일 영수증, 실행 도구. **영구 삭제는 하지 않았다.**

- 되돌릴 수 없는 raw 삭제는 에이전트가 전달받은 결정만으로 실행하지 않는다. 사용자가 직접 확인하고 아래 명령을 실행해야 한다.
- 대상 안의 미배포 체크포인트를 공개 저장소의 Release asset으로 올리는 일도 사용자의 직접 승인이 필요하다. 그래서 올리지 않았고, 규칙 2에 따라 그 폴더들은 삭제에서 뺐다.

### 계획 ([`plan_raw_b.py`](plan_raw_b.py) `plan`, [제외 목록](footprint/plan-b-excluded.json))

- 삭제 단위는 세 가지다.
  - T3: `retired-worktrees/<라벨>`
  - T4: 폴더 전체
  - T6: 폴더. 안에 test 이름의 하위 폴더가 있으면 하위 폴더 단위로 나눈다.
- T1 test, T5, T7, T0(`tensorboard*`, `agent-locks`, 모델 설치본, 디스크 기록)은 대상에서 뺐다.
- 제외 규칙
  - `test`: 경로의 어느 단계든 test 이름이 있음
  - `model`: `configs/model_artifacts.json`의 `available` 파일과 sha256이 다른 체크포인트(safetensors·pt·pth·ckpt·onnx·joblib·pkl)가 있음
  - `code_ref`: origin/main이나 열린 PR의 코드·설정(py·sh·yaml·toml·configs json·experiments py)이 그 폴더를 입력 경로로 씀. 예: `tests/test_dispatch_pair_process.py` → `simulation-realtime-20260923/native-v17-repeat`, `configs/dispatch_stage_priors.json` → `post-run-replay-20260924`, `probe_markerless_*` 동결 실행, `sim/workflow_manager.py` → `simulation-runs`
  - `open_pr`: 열린 PR이 추가·변경한 파일(#239 제외)이 그 폴더를 가리킴
  - `active`: 120분 안에 수정됐거나 열린 파일이 있음
  - `archive`: 보관본일 수 있음
- origin/main 기록(README·results)이 raw 위치로만 적어 둔 경우는 B의 정의상 삭제 대상에 남겼다. 그 기록의 raw는 해시로만 남는다.

| | 단위 | 파일 | GiB (`du`) |
|---|---|---|---|
| 삭제 계획 | 936 | 433,653 | 30.38 (T3 10.63, T4 2.23, T6 17.52) |
| 제외 | 1,228 | | 19.15 |

- 제외 사유별 GiB(겹침 있음): test 6.24, code_ref 7.04, model 6.37, open_pr 4.66, archive 0.31, active 0.00.
- 가장 큰 삭제: `retired-worktrees` 10.63, `jev-semantic-motion-20260921-v1` 3.52, `rgb-common-physical-recovery-20260923` 2.66, `dispatch-action-act-refinement-20260924` 1.37, `simulation-realtime-20260924-faster` 1.29, `jev-skills-dev-v4·v6·v5·v3·v2·final` 3.42, `simulation-performance-20260923` 0.94, `navigation-generalization-repair-20260908` 0.84.
- 가장 큰 제외
  - `simulation-realtime-20260923` 3.69: 테스트가 입력으로 씀 + pkl
  - `act-action-training-20260924/model-release-tools` 2.0: 열린 PR #199
  - ACT 체크포인트가 든 은퇴 폴더 4개 2.46
  - `markerless-improvement-20260909` 0.65, `fine-gain-schedule-*` 0.99: 코드 입력
- 예상 결과: `outputs/` `du`는 75.59 → 약 45.2 GiB다. **예산 40에는 약 5 GiB 모자란다.** 제외분을 풀려면 모델을 배포하거나 참조하는 코드를 정리해야 한다.
  - `df` 확보량은 이보다 작다. 삭제 대상 중 남는 파일과 clone을 공유하는 블록은 돌아오지 않는다.

### 배포하지 않은 체크포인트 (삭제에서 뺀 이유, 30개)

| 위치 | 개수 | 크기 |
|---|---|---|
| `retired-worktrees/act-recovery-generalization/outputs/{nominal,aggregated,bootstrap,recovery}-seed16/17-v1/r1·r3/act/model.safetensors` | 14 | 각 43.7 MiB |
| `retired-worktrees/act-feasibility-training/outputs/act-{old20-balanced-3000,old20-uniform-3000-v2,expanded50-balanced-10000-seed16/17}/r1·r3/act/model.safetensors` | 8 | 각 43.7 MiB |
| `retired-worktrees/act-double-speed-generalization/outputs/act-fast-seed16/17-v1/r1·r3/act/model.safetensors` | 4 | 각 43.7 MiB |
| `retired-worktrees/reference-act-baseline/outputs/reference-act-f0ee14d/r1·r3/act/model.safetensors` | 2 | 각 43.7 MiB |
| `act-action-training-20260924/train-seed24{,-deployed-first}-managed/artifacts/resume.pt` | 2 | 각 89.4 MiB. 학습 재개 상태. 배포된 seed24 모델과 sha256이 다름 |
| `simulation-realtime-20260923/v12-carry-beam-baseline.pkl` | 1 | 0.1 MiB |

파일별 sha256은 [제외 목록](footprint/plan-b-excluded.json)에 있다. Release로 올린 모델은 **0개**다.

### 영수증 ([`plan_raw_b.py`](plan_raw_b.py) `receipt`)

- 삭제 계획의 모든 파일을 경로·크기·mtime_ns·sha256(링크는 대상 경로)으로 기록했다: 433,653개, 29.48 GiB(논리 크기).
- 로컬(커밋 안 함, 크기 20.8 MB)
  - `outputs/disk-cleanup-20260927/raw-b/receipt-b.jsonl.gz`: sha256 `9526fcb5e437445bcc10ad4888edb77211e16fb07328718962b72f7517118219`
  - `plan-b.json`: sha256 `0ebfe39e…`
- 단위별 파일 수·GiB·목록 해시: [`receipt-b-summary.json`](footprint/receipt-b-summary.json)(로컬 원본 sha256 `4a2c01d5…`)
- 이 영수증은 삭제 뒤 "무엇이 있었는지"의 증거일 뿐이다. 사본이 아니므로 복원할 수 없다.

### 실행 (사용자가 직접)

```sh
cd /Users/changmin/projects/ugrp-wt/claude-disk-cleanup-0927
python3 experiments/2026-09-27-disk-cleanup/plan_raw_b.py execute \
  --summary /Users/changmin/projects/ugrp/outputs/disk-cleanup-20260927/raw-b/receipt-b-summary.json \
  --log /Users/changmin/projects/ugrp/outputs/disk-cleanup-20260927/raw-b/execute-log.jsonl \
  --i-confirm-permanent-deletion
```

- 단위마다 다시 목록을 만들고 다시 해시한다. 60분 안에 바뀌었거나 목록 해시가 영수증과 다르면 건너뛰고 로그에 남긴다.
- 실행 전후로 `disk_report.py`와 `df`를 기록한다.
- 제외분(모델 30개)을 풀려면 먼저 `docs/model_artifacts.md` 절차를 사용자가 승인해야 한다. 절차는 Release 업로드 → 재다운로드 → 전체 해시 → 로딩이다.

### 캡처 설정

"dev만 1초 1장, test 5장 유지, 결정 프레임 항상"은 [PR #241](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/241)에 버전 고정 프로필 `dev_1hz_decisions_v1`로 넣었다. 공용 기록 계층이 없어 러너는 아직 연결하지 않았다. 러너 목록과 연결 방법은 그 PR의 `docs/disk_management.md` 5.1절에 있다.

## 파일

- 커밋한 기록
  - 이 README
  - `drop_done_groups.py`: 이미 clone한 그룹을 빼는 사전 필터
  - `tiers.py`: 등급 분류(읽기 전용)
  - `footprint/`: 보고서 전·후, `df`, 캐시 목록, 중복 제거 계획·요약, sparse 영수증, 등급 결과
- raw(로컬, 커밋 안 함): `/Users/changmin/projects/ugrp/outputs/disk-cleanup-20260927/`
  - `disk-report-before.json` sha256 d46aae0e…, `disk-report-after.json` 8afd4250…
  - `retire/`: dry run·실행 영수증 10개와 전후 `df`
  - `dedupe/`: `fclones-group.json` 5fbf685d…, `dedupe-plan.json` d21183bb…, `dedupe-manifest-before.tsv` b3b1d248…, 로그, 검증
- 은퇴 영수증: `outputs/retired-worktrees/claude0927-<이름>/{MANIFEST.tsv,RETIRED.json}`
- 도구 실행 방법: 기본 체크아웃이 182커밋 뒤처져 `scripts/agent_worktree.py`가 없었다. 그래서 origin/main의 `scripts/`(`git archive`)와 이 worktree의 사본을 `--primary /Users/changmin/projects/ugrp`로 실행했다. 이 worktree는 claude 상한(8개)을 넘어 `--allow-over-cap`(사유 기록)으로 만들었고, 은퇴 뒤 claude 소유는 이 worktree를 포함해 8개다.

## 참고 자료

- 논문: 없음(운영 작업).
- OSS: fclones 0.35.0, https://github.com/pkolaczk/fclones , MIT. `group`(sha256)과 `dedupe`(macOS `clonefile`)를 그대로 썼다.
- 내부
  - `docs/disk_management.md` 3·4·7·9절
  - `experiments/2026-09-26-disk-apply/`(`dedupe_outputs.py` 재사용)
  - `scripts/agent_worktree.py`, `scripts/worktree_guard.py`, `scripts/tree_manifest.py`, `scripts/disk_report.py`
  - PR #212, #231
- 문서: `man 2 clonefile`, `git help worktree`, `git help sparse-checkout`
