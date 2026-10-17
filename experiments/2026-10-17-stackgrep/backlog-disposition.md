# stackgrep 백로그 처분 — 2026-10-18

`experiments/2026-10-17-stackgrep/table.json`의 `pr_classification` 중 **rework 10 + superseded 11 = 21개**를 대상으로, 2026-10-18 01:42 KST에 gh로 현재 상태를 다시 확인해 처분을 기록했다. 코드 수정·VM/시뮬/LLM 실행·force push·PR 닫기/병합·브랜치 삭제는 하지 않았다. 증거는 삭제하지 않는다.

- 분류 원출처: `table.json` (감사 PR #578, merge `22b80ee81`). 표의 CI 값은 작성 시점 값이므로 아래 CI는 gh 실측으로 대체했다.
- superseded 근거: 2026-10-17 사용자 결정(정적 지도 미사용·자기중심 기억) → `configs/current_stack.json` commit `c43a9f515`. #551만 2026-10-16 공급자 결정(PR #552, merge `dffe4f939`)이 근거다.
- 21개 전부 현재 OPEN(초안 21/21)이므로 merged/closed로 제외된 항목은 **0개**다.
- 권장 처분: rework → `재작업`, superseded → `닫기 보류`(닫기·병합은 조정자 판단).

## 1. 처분 표 (OPEN 21/21)

| PR | 제목 | branch | 분류 | 대체 근거(사용자 결정일·후속 PR/커밋) | 증거 보존 위치(브랜치·experiments) | 권장 처분 | 현재 CI/merge |
|---|---|---|---|---|---|---|---|
| #570 | e2ewarp: MJWarp 배치 LLM E2E 통합 후보와 native first30 검증 | `codex/e2ewarp` | rework | 2026-10-17 사용자 결정(static_map_use=none, selfmap_map_correction=off) · c43a9f515 | origin/codex/e2ewarp · experiments/2026-10-17-e2ewarp/ | 재작업 | draft · CONFLICTING/DIRTY · 33/33 success |
| #557 | warp8f: native 빔 관문·release 정적 자기 지도 CSM 점검 (NOT_READY) | `codex/warp6` | superseded | 2026-10-17 사용자 결정(static_map_use=none, localization_path=egocentric_landmark_memory_v1) · c43a9f515 | origin/codex/warp6 · experiments/2026-10-16-warp8/ | 닫기 보류 | draft · MERGEABLE/UNSTABLE · 29/33 success, 4 fail |
| #556 | mapbuild11: AMCL 긴 경로 오차 비교·DEV 녹화 (NOT_READY) | `codex/mapbuild1` | superseded | 2026-10-17 사용자 결정(static_map_use=none, localization_path=egocentric_landmark_memory_v1) · c43a9f515 | origin/codex/mapbuild1 · experiments/2026-10-17-mapbuild11/ | 닫기 보류 | draft · MERGEABLE/BEHIND · 33/33 success |
| #551 | llmhost: GCP L4 Gemma VLM 자체 서빙 시험 준비 (GPU 미기동) | `codex/llmhost` | superseded | 2026-10-16 사용자 결정(planner_provider=CoreWeave, planner_fallbacks=false) · PR #552 merge dffe4f939 | origin/codex/llmhost · experiments/2026-10-16-llmhost/ | 닫기 보류 | draft · CONFLICTING/DIRTY · 33/33 success |
| #550 | warp10: 호스트 처리량 개선·CPU 접촉 export 3회 중단 (NOT_READY) | `claude/warp5` | rework | 2026-10-17 사용자 결정(static_map_use=none, release 정적 지도 금지) · c43a9f515 | origin/claude/warp5 · experiments/2026-10-16-warp10/ | 재작업 | draft · CONFLICTING/DIRTY · 검사 0 |
| #549 | warp4: 빔 짝·release MJWarp 배치 후보와 HOST_ERROR 근거 | `claude/warp4` | rework | 2026-10-17 사용자 결정(static_map_use=none, release 정적 지도 금지) · c43a9f515 | origin/claude/warp4 · experiments/2026-10-16-warp4/ | 재작업 | draft · MERGEABLE/UNSTABLE · 29/33 success, 4 fail |
| #547 | reloc21: 운반 진행·완전 place 계획 관문 | `claude/reloc21` | superseded | 2026-10-17 사용자 결정(localization_path=egocentric_landmark_memory_v1, static_map_use=none) · c43a9f515 | origin/claude/reloc21 · experiments/2026-10-16-reloc21/ | 닫기 보류 | draft · MERGEABLE/UNSTABLE · 28/33 success, 5 fail |
| #543 | reloc20: 화물 footprint·RGB 막힘·heading drive (NOT_READY, place 0/4) | `claude/reloc20` | rework | 2026-10-17 사용자 결정(static_map_use=none, localization_initial_prior=none) · c43a9f515 | origin/claude/reloc20 · experiments/2026-10-16-reloc20/ | 재작업 | draft · MERGEABLE/UNSTABLE · 28/33 success, 5 fail |
| #541 | reloc19: default-off destination visual acquisition (NOT_READY) | `claude/reloc19` | rework | 2026-10-17 사용자 결정(goal_discovery=visual_search, static_map_use=none) · c43a9f515 | origin/claude/reloc19 · experiments/2026-10-16-reloc19/ | 재작업 | draft · MERGEABLE/UNSTABLE · 27/33 success, 6 fail |
| #538 | reloc18: innovation·map→odom 비교와 place 실패 진단 (NOT_READY) | `claude/reloc18` | superseded | 2026-10-17 사용자 결정(static_map_use=none, selfmap_map_correction=off) · c43a9f515 | origin/claude/reloc18 · experiments/2026-10-16-reloc18/ | 닫기 보류 | draft · MERGEABLE/UNSTABLE · 28/33 success, 5 fail |
| #536 | reloc17: 위치 추정 원인 분리·서보 대기 취소 수정, 2라운드 NOT_READY | `claude/reloc17` | superseded | 2026-10-17 사용자 결정(static_map_use=none, selfmap_map_correction=off) · c43a9f515 | origin/claude/reloc17 · experiments/2026-10-16-reloc17/ | 닫기 보류 | draft · MERGEABLE/UNSTABLE · 28/33 success, 5 fail |
| #535 | release25: fix uncertainty-only north-wall sweep rejection in pinned scene | `claude/release25` | superseded | 2026-10-17 사용자 결정(static_map_use=none, release 정적 지도 금지) · c43a9f515 | origin/claude/release25 · experiments/2026-10-16-release25/ | 닫기 보류 | draft · CONFLICTING/DIRTY · 28/33 success, 5 fail |
| #534 | warp3: MJWarp ACT 교사40/40·기록 및 학생 API (warm 검증 중) | `claude/warp-act` | rework | 2026-10-17 사용자 결정(setdown_lookaround_v1 egocentric 재작성, static_map_use=none) · c43a9f515 | origin/claude/warp-act · experiments/2026-10-16-warp3/ | 재작업 | draft · MERGEABLE/CLEAN · 33/33 success |
| #532 | reloc16: 확정 v5 RGB 경계·Manhattan yaw 후보와 3라운드 NOT_READY 기록 | `claude/reloc16` | superseded | 2026-10-17 사용자 결정(localization_path=egocentric_landmark_memory_v1, static_map_use=none) · c43a9f515 | origin/claude/reloc16 · experiments/2026-10-16-reloc16/ | 닫기 보류 | draft · MERGEABLE/UNSTABLE · 28/33 success, 5 fail |
| #521 | rel22adapt: release 교사 ACT12 관측 전용 RGB 기록기 | `claude/release-record` | rework | 2026-10-17 사용자 결정(static_map_use=none, release 정적 지도 금지) · c43a9f515 | origin/claude/release-record · experiments/2026-10-15-release-record/ | 재작업 | draft · CONFLICTING/DIRTY · 29/33 success, 4 fail |
| #507 | DEV: 기본 off 지도 AMCL·KLD와 #480 동일 80구간 재생 | `claude/map-amcl` | superseded | 2026-10-17 사용자 결정(localization_path=egocentric_landmark_memory_v1, static_map_use=none) · c43a9f515 | origin/claude/map-amcl · experiments/2026-10-15-map-amcl/ | 닫기 보류 | draft · MERGEABLE/BEHIND · 25/33 success, 8 fail |
| #506 | DEV: 자기 지도 pose→점유 격자→frontier 연결과 저장 RGB 평가 | `claude/map-selfmap` | rework | 2026-10-17 사용자 결정(static_map_use=none, egocentric_landmark_memory_v1) · c43a9f515 | origin/claude/map-selfmap · experiments/2026-10-15-self-map/ | 재작업 | draft · CONFLICTING/DIRTY · 29/33 success, 4 fail |
| #505 | DEV: solo 목적 구역 운반·놓기 분리 진단 (기본 off) | `claude/map-carry-zone` | superseded | 2026-10-17 사용자 결정(localization_initial_prior=none, static_map_use=none) · c43a9f515 | origin/claude/map-carry-zone · experiments/2026-10-15-map-carry-zone/ | 닫기 보류 | draft · CONFLICTING/DIRTY · 28/33 success, 5 fail |
| #502 | DEV: 1대 화물 교사 (tile_low_reach_v1, RGB 들기 확인, 공용 둘러보기) | `claude/act-solo-teacher` | rework | 2026-10-17 사용자 결정(setdown_lookaround_v1 egocentric 재작성) · c43a9f515 | origin/claude/act-solo-teacher · experiments/2026-10-14-act-solo-teacher/ | 재작업 | draft · CONFLICTING/DIRTY · 검사 0 |
| #491 | gatesv5: release24 관문 NOT_READY (A31/40·B31/40, 결함 확인 후 중단) | `claude/grasp-act-release` | superseded | 2026-10-17 사용자 결정(static_map_use=none, release 정적 지도 금지) · c43a9f515 | origin/claude/grasp-act-release · experiments/2026-10-16-gatesv5-release/ | 닫기 보류 | draft · CONFLICTING/DIRTY · 검사 0 |
| #473 | DEV: Gemma fp4 계획기와 캐시 순서 검증 (v405/v406) | `claude/e2e18-gemma-planner` | rework | 2026-10-17 사용자 결정(planner own RGB 1, static_map_use=none, cache order) · c43a9f515 | origin/claude/e2e18-gemma-planner · experiments/2026-10-13-e2e18-planner-r4/, experiments/2026-10-14-planner-cache-v2/ | 재작업 | draft · CONFLICTING/DIRTY · 23/33 success, 10 fail |

메모: #570은 표 작성 시 CI 22 success/2 fail이었으나 현재 33/33 success·CONFLICTING이다. #550·#502·#491은 검사가 없는 초안이다. #534는 CI CLEAN이지만 정적 지도 lookaround 때문에 rework다.

## 2. superseded 코멘트 (11개)

본문 형식: `처분: superseded by <근거>. 증거 보존: <브랜치·experiments 경로>. 닫기·병합 보류(조정자 판단).` 2026-10-18 01:4x KST에 11/11 게시했고, gh 재조회로 각 PR이 OPEN이며 코멘트가 1개씩 있음을 확인했다.

| PR | 코멘트 URL |
|---|---|
| #557 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/557#issuecomment-6236892706 |
| #556 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/556#issuecomment-6236893006 |
| #551 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/551#issuecomment-6236893303 |
| #547 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/547#issuecomment-6236893580 |
| #538 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/538#issuecomment-6236893860 |
| #536 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/536#issuecomment-6236894157 |
| #535 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/535#issuecomment-6236894446 |
| #532 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/532#issuecomment-6236894746 |
| #507 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/507#issuecomment-6236895013 |
| #505 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/505#issuecomment-6236895347 |
| #491 | https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/491#issuecomment-6236895650 |

## 3. 제외: 진행 중 (손대지 않음)

| PR | branch | 처분 |
|---|---|---|
| #575 | `codex/act18` | 제외: 진행 중 |
| #582 | `claude/visgoal` | 제외: 진행 중 |
| #585 | `claude/beamact5` | 제외: 진행 중 |
| #586 | `claude/egonav-mem` | 제외: 진행 중 |
| #587 | `claude/egonav-far` | 제외: 진행 중 |

## 4. merged/closed 제외

없음 — 2026-10-18 01:42 KST 기준 대상 21개 전부 OPEN.

## 5. 남은 모호 항목 / 주의

- #551은 정적 지도 결정이 아니라 **2026-10-16 planner 공급자(CoreWeave) 결정**으로 대체된 항목이다. 나머지 superseded와 대체 축이 다르다.
- #473은 rework 근거가 정적 지도(localization)가 아니라 **판단 LLM 입력 경계**(own RGB 1장, cache order)다.
- superseded 코멘트는 "닫기·병합 보류(조정자 판단)" 문구만 남기고 실제 닫기/병합은 하지 않았다.
- 증거 보존 위치는 각 `origin/<branch>` head에서 `experiments/<dir>` 존재를 `git cat-file -e`로 확인했다(21/21 OK).

## 6. 재확인 명령

```sh
gh pr list --state open --limit 100 --json number,isDraft,mergeable,mergeStateStatus,statusCheckRollup
git cat-file -e origin/<branch>:experiments/<dir>
```

검증 시각: 2026-10-18T01:42:03+0900 · 기준 main `5036ae2ecf889628770a39102ae1ea8ba98c6bab`

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
