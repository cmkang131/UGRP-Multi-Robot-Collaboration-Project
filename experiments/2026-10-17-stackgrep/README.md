# 2026-10-17 stackgrep: 정적 지도 모순 전수 감사 + 열린 PR 분류

- 작업자: `stackgrep` / worktree `/Users/changmin/projects/ugrp-wt/stackgrep` / branch `claude/stackgrep`
- 기준: `configs/current_stack.json` (`as_of=2026-10-17`, commit `c43a9f515`), main `79a4918d0`, open PR 51개 head ref
- 범위: **기록 전용**. 코드 수정·VM·시뮬레이션·렌더·LLM 호출·학습·PR 닫기·브랜치 삭제·증거 정리 없음.
- 산출: 이 README + `table.json`(기계 판독 55개 감사 행, 51개 PR 분류).
- 열린 PR 51/51개의 로컬 head ref가 GitHub live head OID와 일치함을 확인했다(stale ref 없음).
- 코드·토글·workflow/manifest·대기열 변경 없음. 새 실행/대기열을 만들지 않았으므로 `check_current_stack.py`/`rejection_table` 대상이 아니다.

## 0. 3줄 요약

1. 2026-10-17 결정(정적 지도 없음·자기중심 기억·시각 목적 발견·시작 prior 없음)과 모순되는 정적 지도 사용을 main 25개, 열린 PR 브랜치 13개 위반 지점에서 확인했다(감사 행 전체 55개).
2. 판단 LLM 입력(zone-study·rgb-communication·dispatch·Gemma planner), 주행(pair/known-map/dispatch), 둘러보기(`setdown_lookaround_v1`), release/beam 재위치가 모두 정적 지도에 직접 결합되어 있어 **대체 필요**다.
3. 열린 PR 51개는 keep 30 / rework 10 / superseded 11로 분류했고, CI·충돌이 깨끗한 merge-ready 후보는 #537·#533(비초안), #563·#545·#539(초안)다. superseded/rework PR의 마일스톤·study 증거는 삭제하지 말고 보존해야 한다.

## 1. 최신 결정과 판정 기준

`AGENTS.md:26`의 사용자 결정과 `configs/current_stack.json`을 유일한 기준으로 삼았다. 이전 `AGENTS.md:27-28`의 “지도 경로 예외”·“시작 구역 사전 정보”, 9/25의 “정적 지도도 계속 llm이 볼 수 있게”는 최신 결정이 명시적으로 대체한다.

| 항목 | 현재 값 | 이 감사의 판정 |
|---|---|---|
| `localization_path` | `egocentric_landmark_memory_v1` | 자기 위치 0,0·정면, 지도가 움직이는 ego frame만 허용 |
| `static_map_use` | `none` | 로봇 입력/제어/판단 어디에도 정적 지도 금지 |
| `selfmap_map_correction` | `off` | map→odom/정적 지도 보정 금지 |
| `localization_initial_prior` | `none` | 시작 구역·pickup 서쪽 0.25m 같은 prior 금지 |
| `goal_discovery` | `visual_search` | 목적지는 자기 카메라로 보고 찾음 |
| `setdown_lookaround_v1` | 현행 이름 유지 | **방향 계산을 egocentric memory로 재작성**해야 함 |
| 판단 LLM | `google/gemma-4-31b-it` @CoreWeave fp4, fallback off, own RGB 1장, cache system→static→dynamic→image | 정적 지도·top RGB·2장 이미지 금지 |
| 입력 경계 | 자기 RGB + 자기 명령 이력 | top camera 제어 금지, 평가 칸만 |
| 근거리 | ACT, weld OFF, 손으로 짠 경로 금지 | 정적 지도 경로 계획으로 대체 금지 |

판정 표기: `violation`(현재 경로에서 즉시 대체), `superseded`(결정으로 폐기), `setup-only`(physics 이전 evaluator setup, 런타임 action 입력 금지), `provenance-only`(해시/기록), `diagnostic`(평가·진단 문자열), `compliant`(정적 지도 아님), `legacy`(현재 경로에서 미사용).

## 2. 정적 지도 감사: 흐름별 요약

전체 55행은 `table.json`의 `static_map_audit`에 있다. 아래는 흐름별 대표 지점과 대체 방향이다.

### 2.1 판단 LLM 입력 (가장 직접적인 위반)

| file:line | 흐름 | 정적 지도 사용 | 대체 |
|---|---|---|---|
| `harness/zone_study_inputs.py:365,385,408-410,513-515` | zone-study LLM | 매 호출 `static_map` payload 복사·검증 | own RGB 1장 + command history로 대체, 키 삭제 |
| `harness/zone_study_prompts_ko.py:52,174-189,328,359,412,449,655-656,788-791` | zone-study prompt/cache | `static_map`/`order_sheet` 텍스트 + `STATIC MAP FIGURE` 이미지 | 지도 텍스트·그림 제거, 자기 RGB만 |
| `harness/zone_study_integration.py:193-196,538-540` | zone-study runtime | pose provider + LLM 요청에 static map | egocentric pose + static_map 인자 제거 |
| `harness/zone_study_offline.py:159,203,303,373` | offline replay | decision_sources에 static_map 포함 | own RGB/commands replay로 재정의 |
| `harness/rgb_communication_planner.py:26-28,178-184,193-196` | RGB communication | system prompt가 shared top RGB + static task/map, 이미지 own+top | top RGB/static map 제거, own RGB 1장 |
| `harness/rgb_communication_runtime.py:478-496,544-545,804-808` | RGB communication runtime | `static_context` 필수, channels own_rgb+top_rgb | static_context 제거, own_rgb만 |
| `harness/dispatch_plan_guidance.py:13,67-76,248-249` | dispatch LLM guidance | authored static map으로 passage/objective 문장 생성 | 시각 관측/자기 기억 문장 |
| `harness/dispatch_execution.py:97,148-152` | dispatch execution | SYSTEM prompt + `compile_programs(static_map)` | static 인자 제거 |
| `harness/pair_llm_inputs.py:48-50,133-143,194,278-282,321,352` | pair LLM | required key `static_map`, map figure | 키/그림 제거 |
| `harness/task_planner.py:99,223-227` (PR #473) | Gemma planner | source=static_map_and_own_estimate, context에 static_map | own RGB 1장·명령 이력으로 교체 |
| `harness/task_planner_model.py:57,68`; `scripts/evaluate_task_planner.py:82,109` (PR #473) | planner serialization/eval | `STATIC_KEYS`/key order/static context | static_map 제거 |

### 2.2 주행·항법

| file:line | 흐름 | 정적 지도 사용 | 대체 |
|---|---|---|---|
| `harness/known_map_navigation.py:1-8,42-64,208-213,239-255,336-358` | known-map navigation | top RGB pixel→world, static map localization, static goal/route | 전면 퇴역, ego memory + own RGB |
| `harness/dispatch_goto.py:31-36,39-58,64-98,108-145,157-176,249-255` | dispatch driving | top beam center, static keepouts/route/park, map→pixel | ego memory/own RGB, top은 평가만 |
| `harness/dispatch_navigation_map.py:20,39-43,49-52,68-100,126-134` | pair navigation | static map + top camera world projection | ego memory 기반 |
| `harness/dispatch_pair_navigation.py:1` | pair navigation | “authored static map” 명시 | ego memory 기반 |
| `harness/dispatch_skill_binding.py:104,111,179,193,198,210,217,243-245,267,310,318,346-347,371-373,396` | skill binding | static map/top camera/route/resource | 자기 기억/자기 RGB |
| `harness/map_goto.py:68-73,81-84,94-111,119-125,179-228,304-316,322-355` | path planning | places/bounds/obstacles/regions/A* | ego frame 경로 계획 |
| `harness/pair_passage_plan.py:78-117,139-161,176-224,295-299,338-372,383-425,443-461,479-481` | pair route | static passage/opening/A*/SDF/guard/target | own 관측 기반 passage/route |
| `harness/pair_navigation.py:52-56,221-260,315,350,399-441,504-514` | pair navigation | map_id/top_camera/start_zone/goal, top RGB decide | ego memory + own RGB, start prior 제거 |

### 2.3 위치 추정·자기 지도

| file:line | 흐름 | 정적 지도 사용 | 대체 |
|---|---|---|---|
| `harness/zone_solo_cyan_landmarks.py:1-7,40-53,73-124,162-196` | own-RGB localization | static regions/doors/edges landmark likelihood | 상대 landmark memory |
| `harness/zone_solo_cyan_likelihood_field.py:1-9,24-41,81-82` | particle filter | static wall occupancy field | ego/own-map occupancy |
| `harness/zone_solo_cyan_amcl_update.py:60-61` | AMCL update | `Field(static)` | 제거 |
| `harness/own_map_amcl_vendor/landmarks.py:31-42`; `field.py:14-21` | AMCL vendor | static regions/passages/walls | own-map/egocentric |
| `harness/e2e_static_rgb_localizer.py:3-4,12,15,18` (PR #480/#506/#507) | global localization | static free geometry + landmarks global init | egocentric memory |
| `harness/self_map_relocalize.py:45-57,94-120` | self-map relocalize | optional `landmark_map`으로 정적 landmark 주입 가능 | 현재 경로에서 `None` 강제/토글 off |
| `harness/active_wall_mapping.py:25-26,114-117`; `own_map_navigation.py:3`; `ego_pose_continuity.py:1-7,14-21,286-288` | own-map/ego pose | 정적 지도 아님(자기 지도/자기 pose) | 유지 |

### 2.4 둘러보기 방향 계산 (`setdown_lookaround_v1` 포함)

| file:line | 흐름 | 정적 지도 사용 | 대체 |
|---|---|---|---|
| `sim/lookaround_localization.py:1-26,38,76-126,163-189,192-256,278-330,333-432` (release25/#535/#491) | **setdown_lookaround_v1** | static wall faces/zone edges/door jambs, `visible_fn_for(static)`, `Field(static)`, `MapFeatures(static)`, `plan_views` | 자기 RGB LK + 자기 명령 이력의 egocentric memory; 미확인 landmark/next-best-view |
| `sim/active_lookaround.py:1-8,47-59,116-159` | lookaround view planning | map-frame `OwnPose` + static landmark 정보이득 | ego frame memory/불확실 landmark 기반 NBV |
| `sim/global_landmark_localization.py:1-6,89-108,110-138` | global SE(2) | static edges/walls/regions consensus | 전역 정합 폐기, 상대 기억 |
| `sim/grasp_act_solo_lookaround.py:1-26,39-83,107,123-133` (PR #502) | solo lookaround | `SoloLookaround(static)` → `LookaroundLocalizer(static)` | `truth_free_v1` pan sweep을 egocentric memory로 승격 |
| `scripts/warp_act_episode.py:49,149-152,330-337,395` (PR #534/#549/#570) | warp ACT episode | `SoloLookaround(static)`, live-truth estimate 경로 | static 인자/경로 제거 |

### 2.5 release·beam 재위치

| file:line | 흐름 | 정적 지도 사용 | 대체 |
|---|---|---|---|
| `sim/release_zone_servo.py:1-8,19-20,97-108,133-150` | release centering | static destination hue/half extents, `global_localized_release_v1` | 자기 RGB zone fit만 |
| `sim/grasp_act_release_teacher.py:1-13,149-186` | release teacher | static zone_rect prior, `map_pose_known`/`map_prior`, reanchor | 자기 RGB 재관측 + 명령 이동 기억 |
| `scripts/run_grasp_act_release.py:30,34-36,209-224,250-252,282,328,363-372,589-635,928-933,990-1003` | release runner | static slots/bounds/keepouts, `LookaroundLocalizer(static)`, reanchor | static 인자 제거 |
| `harness/beam_initial_pose_plan.py:1-7,77-106,127-140,170-179,182-243`; `beam_approach.py:127-146,313-319` | beam initial pose/approach | static bounds/obstacles/pickup region | setup-only 라벨 또는 대체 |
| `scripts/run_beampair1.py:117-145` (PR #537/#533) | beam setup admission | `resolve(map_id)`, static keepouts/bounds, `blocked_object=static_map` | physics 이전 authored setup으로만 유지; action 입력 금지 |
| `scripts/release_reloc_selfmap.py:6,79-89`; `release_reloc_static_selfmap.py:1-3,78-80` (PR #557) | release relocalization | static map/CSM map pose/correction | superseded |

### 2.6 워크플로·정책 텍스트

- `configs/simulation_workflows.json`: `navigation`(정적 지도·RGB 단독 주행), `zone-study-integration-run`(static map + order sheet + top RGB), `rgb-communication`(planner static context/top RGB) 등록이 그대로다. 새 실행/대기열은 `check_current_stack.py`가 거부해야 한다.
- `AGENTS.md:90`은 `setdown_lookaround_v1`을 “정적 지도와 자기 추정 위치로 방향 계산”으로 설명하고, `:104`는 고정 프롬프트/cache에 “정적 지도”를 넣는다. 최신 결정과 모순이므로 조정자가 문구를 갱신해야 한다(이 작업은 코드/정책 파일 수정 금지).

## 3. 열린 PR 51개 분류

분류 기준: `keep`=현재 경로에 필요/정합, `rework`=부품 재사용 가능하나 입력 경계·정적 지도 경로 수정 필요, `superseded`=최신 결정/다른 PR이 대체. `merge-ready`는 CI all-success + mergeable CLEAN + 정책 위반 없음까지 본 별도 플래그다.

| PR | branch | class | superseded_by | evidence | merge-ready | CI |
|---:|---|---|---|---|---|---|
| #575 | `codex/act18` | keep | - | study | no | MERGEABLE/UNSTABLE, S22 F2 |
| #574 | `codex/egomem1` | keep | - | dev | no | MERGEABLE/BEHIND, S25 F1 |
| #570 | `codex/e2ewarp` | rework | configs/current_stack.json @ c43a9f515 (static_map_use=none, selfmap_map_correction=off) | dev | no | CONFLICTING/DIRTY, S33 F0 |
| #566 | `codex/mast3rcmp` | keep | - | study | no | MERGEABLE/BEHIND, S33 F0 |
| #564 | `codex/drivecheck` | keep | - | dev | no | CONFLICTING/DIRTY, S33 F0 |
| #563 | `codex/beamact4` | keep | - | study | **yes** | MERGEABLE/CLEAN, S33 F0 |
| #562 | `codex/warpfit` | keep | - | study | no | MERGEABLE/BEHIND, S29 F4 |
| #557 | `codex/warp6` | superseded | 2026-10-17 static_map_use=none / egocentric_landmark_memory_v1 | study | no | MERGEABLE/UNSTABLE, S29 F4 |
| #556 | `codex/mapbuild1` | superseded | 2026-10-17 static_map_use=none / localization_path=egocentric_landmark_memory_v1 | study | no | MERGEABLE/BEHIND, S33 F0 |
| #555 | `codex/macprune` | keep | - | infra | no | MERGEABLE/BEHIND, S33 F0 |
| #551 | `codex/llmhost` | superseded | planner_provider=CoreWeave / planner_fallbacks=false | study | no | CONFLICTING/DIRTY, S33 F0 |
| #550 | `claude/warp5` | rework | 2026-10-17 static_map_use=none / release static map 금지 | dev | no | CONFLICTING/DIRTY, S0 F0 |
| #549 | `claude/warp4` | rework | 2026-10-17 static_map_use=none / release static map 금지 | dev | no | MERGEABLE/UNSTABLE, S29 F4 |
| #547 | `claude/reloc21` | superseded | 2026-10-17 localization_path=egocentric_landmark_memory_v1 / static_map_use=none | dev | no | MERGEABLE/UNSTABLE, S28 F5 |
| #545 | `codex/beamact3` | keep | - | study | **yes** | MERGEABLE/CLEAN, S33 F0 |
| #544 | `codex/actdiag` | keep | - | study | no | CONFLICTING/DIRTY, S30 F3 |
| #543 | `claude/reloc20` | rework | 2026-10-17 static_map_use=none / localization_initial_prior=none | dev | no | MERGEABLE/UNSTABLE, S28 F5 |
| #542 | `claude/beampair9` | keep | - | dev | no | CONFLICTING/DIRTY, S31 F2 |
| #541 | `claude/reloc19` | rework | 2026-10-17 goal_discovery=visual_search / static_map_use=none | dev | no | MERGEABLE/UNSTABLE, S27 F6 |
| #540 | `codex/beamact1` | keep | - | study | no | CONFLICTING/DIRTY, S0 F0 |
| #539 | `claude/act16w` | keep | - | study | **yes** | MERGEABLE/CLEAN, S33 F0 |
| #538 | `claude/reloc18` | superseded | 2026-10-17 static_map_use=none / selfmap_map_correction=off | dev | no | MERGEABLE/UNSTABLE, S28 F5 |
| #537 | `claude/beampair8` | keep | - | milestone | **yes** | MERGEABLE/CLEAN, S33 F0 |
| #536 | `claude/reloc17` | superseded | 2026-10-17 static_map_use=none / selfmap_map_correction=off | dev | no | MERGEABLE/UNSTABLE, S28 F5 |
| #535 | `claude/release25` | superseded | 2026-10-17 static_map_use=none / release static map 금지 | milestone | no | CONFLICTING/DIRTY, S28 F5 |
| #534 | `claude/warp-act` | rework | 2026-10-17 setdown_lookaround_v1 egocentric 재작성 / static_map_use=none | milestone | no | MERGEABLE/CLEAN, S33 F0 |
| #533 | `claude/beampair7` | keep | - | milestone | **yes** | MERGEABLE/CLEAN, S33 F0 |
| #532 | `claude/reloc16` | superseded | 2026-10-17 static_map_use=none / localization_path=egocentric_landmark_memory_v1 | dev | no | MERGEABLE/UNSTABLE, S28 F5 |
| #530 | `claude/rl-act` | keep | - | dev | no | CONFLICTING/DIRTY, S0 F0 |
| #527 | `claude/scene-tex2` | keep | - | study | no | CONFLICTING/DIRTY, S33 F0 |
| #522 | `claude/beam-pair-teacher` | keep | - | dev | no | MERGEABLE/UNSTABLE, S31 F2 |
| #521 | `claude/release-record` | rework | 2026-10-17 static_map_use=none / release static map 금지 | milestone | no | CONFLICTING/DIRTY, S29 F4 |
| #510 | `claude/drive-model-deadband` | keep | - | study | no | CONFLICTING/DIRTY, S30 F3 |
| #507 | `claude/map-amcl` | superseded | 2026-10-17 static_map_use=none / localization_path=egocentric_landmark_memory_v1 | study | no | MERGEABLE/BEHIND, S25 F8 |
| #506 | `claude/map-selfmap` | rework | 2026-10-17 static_map_use=none / egocentric memory | study | no | CONFLICTING/DIRTY, S29 F4 |
| #505 | `claude/map-carry-zone` | superseded | 2026-10-17 localization_initial_prior=none / static_map_use=none | dev | no | CONFLICTING/DIRTY, S28 F5 |
| #502 | `claude/act-solo-teacher` | rework | 2026-10-17 setdown_lookaround_v1 egocentric 재작성 | study | no | CONFLICTING/DIRTY, S0 F0 |
| #499 | `claude/sim-speed` | keep | - | infra | no | CONFLICTING/DIRTY, S28 F5 |
| #493 | `codex/robot-clock-sync` | keep | - | infra | no | MERGEABLE/BEHIND, S26 F7 |
| #491 | `claude/grasp-act-release` | superseded | 2026-10-17 static_map_use=none / release static map 금지 | milestone | no | CONFLICTING/DIRTY, S0 F0 |
| #484 | `claude/e2e18-grasp-rootcause` | keep | - | dev | no | CONFLICTING/DIRTY, S30 F3 |
| #483 | `codex/e2e18-end-assignment` | keep | - | study | no | MERGEABLE/UNSTABLE, S27 F6 |
| #480 | `codex/e2e18-pose-diagnosis` | keep | - | study | no | MERGEABLE/UNSTABLE, S27 F6 |
| #475 | `claude/e2e18-grasp1` | keep | - | dev | no | CONFLICTING/DIRTY, S30 F3 |
| #473 | `claude/e2e18-gemma-planner` | rework | 2026-10-17 planner_own_rgb_count=1 / static_map_use=none / cache order system→static→dynamic→image | study | no | CONFLICTING/DIRTY, S23 F10 |
| #461 | `codex/e2e18` | keep | - | milestone | no | MERGEABLE/UNSTABLE, S28 F5 |
| #459 | `claude/e2e-bcones` | keep | - | study | no | MERGEABLE/BEHIND, S30 F3 |
| #440 | `codex/ego-pose-continuity` | keep | - | study | no | CONFLICTING/DIRTY, S31 F2 |
| #437 | `codex/egomap70-overview` | keep | - | milestone | no | MERGEABLE/BEHIND, S33 F0 |
| #385 | `codex/real-robot-link` | keep | - | dev | no | CONFLICTING/DIRTY, S31 F2 |
| #339 | `codex/integ-target-backend` | keep | - | policy | no | MERGEABLE/BEHIND, S33 F0 |

### 3.1 merge-ready 후보

- **#537 beampair8** — non-draft, `MERGEABLE/CLEAN`, 33 SUCCESS. 검증된 ACT 빔 짝 185쌍/370로봇 기록. 정적 지도는 `run_beampair1.py:117-145`의 physics 이전 authored setup admission에만 쓰이고 “no setup coordinates enter actions” 주석이 있다. **최우선 merge-ready 후보**이나, `beam_pose`가 런타임 action으로 새지 않는지 독립 검토가 필요하다.
- **#533 beampair7** — non-draft, `MERGEABLE/CLEAN`, 33 SUCCESS. 새 장면 빔 짝 교사 gate40 40/40, 목적 자세 예약·시작 연결. #537과 같은 setup-only 조건.
- **#563 beamact4**, **#545 beamact3**, **#539 act16w** — draft, `MERGEABLE/CLEAN`, 33 SUCCESS. ACT 학습/교사 인수/실패 진단 연구. draft→ready 전환은 조정자 판단.
- **#534 warp-act** — CI/merge는 깨끗하지만 `SoloLookaround(static)` 때문에 **merge-ready 아님**. 교사 40/40·MJWarp 물리/기록은 재사용하고 lookaround만 교체해야 한다.
- **#570 e2ewarp** — all-success지만 DIRTY, `selfmap_map_correction=on`/정적 지도 보정 필수라 **merge-ready 아님**.
- CI all-success + BEHIND: #339, #437, #555, #556, #566 (rebase 필요). #555는 non-draft infra 정리 도구.
- CI 실패/충돌: 나머지. 특히 #491/#502/#530/#540/#550은 check rollup 자체가 없다.

### 3.2 rework 10개: 재사용 부품 vs 반드시 바꿀 부분

| PR | 재사용 | 반드시 바꿀 부분 |
|---|---|---|
| #570 | MJWarp 배치 E2E 통합; native first30; Gemma CoreWeave fp4 중계; ACT/release 어댑터 연결 | 정적 지도 보정 인수 필수 제거; selfmap_map_correction=on 제거; 정적 지도 기반 주행/릴리스 제거; 구 stackaudit 45623168 vendor 교체 |
| #550 | 호스트 처리량 개선; CPU 접촉 export/funnel | 정적 지도 release 경로; 중단된 3회 HOST_ERROR 재현 조건 |
| #549 | MJWarp 배치 빔 짝/release 후보; HOST_ERROR 원인 기록 | SoloLookaround(static) 경로; 정적 지도 release 보정 |
| #543 | 화물 footprint·RGB 막힘·heading drive 기본off 후보; 입력 경계 감사 | 정적 초기 빔/지도 기반 위치추정; 시작 prior 의존 |
| #541 | 목적지 시각 획득·운반 중 재관측 경로; RGB 벽 마스크/장애물 폐기 | 지도/추정 공분산을 검색 목표로 쓰는 부분; 정적 지도 pose 결합 |
| #534 | MJWarp ACT 교사 40/40; 7 exact-model 그룹; warp batch 물리·기록 API | scripts/warp_act_episode.py:49,149-160 SoloLookaround(static); lookaround estimate/map pose 기록 |
| #521 | ACT12 관측 전용 RGB 기록기; off/on 동일성·해시 검증 | frozen release runner의 정적 지도 위치추정; release14 record 경로 |
| #506 | pose→점유격자→frontier; RGB 벽/바닥 관측만으로 점유 갱신; 정답 pose 평가 분리 | 정적 landmark map/static map 조건; start prior가 있는 평가 |
| #502 | solo 화물 교사(tile_low_reach_v1); RGB 들기 확인; ACT 기록/시드 계획 | 공용 LookaroundLocalizer(static); 정적 지도 기반 둘러보기 방향 |
| #473 | Gemma 31B fp4 번들; JSON strict/reask; 캐시 순서·비용 계측; 400+40+5 실행 | task_planner.py:99,223-227 static_map; task_planner_model.py:57,68; evaluate_task_planner.py:82,109; 프롬프트의 static map/order sheet 의존 |

### 3.3 superseded 11개: 대체 결정/PR

| PR | 대체 결정/PR | 보존할 증거 |
|---|---|---|
| #557 | 2026-10-17 static_map_use=none / egocentric_landmark_memory_v1 | study; release static selfmap NOT_READY. CI shard 실패. 게이트/원본 보존. |
| #556 | 2026-10-17 static_map_use=none / localization_path=egocentric_landmark_memory_v1 | study; 정적 지도 위치추정 계열. BEHIND, all-success. 비교 근거 보존. |
| #551 | planner_provider=CoreWeave / planner_fallbacks=false | study; DIRTY, all-success. 서빙 하네스는 참고 보존. |
| #547 | 2026-10-17 localization_path=egocentric_landmark_memory_v1 / static_map_use=none | dev; place 0/6, pose 악화. CI shard 실패. 부정 결과 보존. |
| #538 | 2026-10-17 static_map_use=none / selfmap_map_correction=off | dev; NOT_READY. CI shard 실패. 진단 근거 보존. |
| #536 | 2026-10-17 static_map_use=none / selfmap_map_correction=off | dev; CI shard 실패. 수정 조각은 재사용 가능하나 현재 위치추정 기반은 폐기. |
| #535 | 2026-10-17 static_map_use=none / release static map 금지 | milestone; A/B 40/40, raw 22,544, CI shard 실패. 마일스톤 증거 보존; 현재 경로에는 정적 지도라 대체. |
| #532 | 2026-10-17 static_map_use=none / localization_path=egocentric_landmark_memory_v1 | dev; CI shard 실패. RGB 검출 조각만 재사용. |
| #507 | 2026-10-17 static_map_use=none / localization_path=egocentric_landmark_memory_v1 | study; BEHIND, CI 실패. 비교/재생 방법은 보존, 런타임 채택 금지. |
| #505 | 2026-10-17 localization_initial_prior=none / static_map_use=none | dev; 초기 prior가 명시적으로 결정 위반. DIRTY, CI shard 실패. 테스트/진단 보존. |
| #491 | 2026-10-17 static_map_use=none / release static map 금지 | milestone; DIRTY, no checks. NOT_READY 마일스톤 증거는 반드시 보존; 현재 경로에는 대체. |

## 4. 증거 등급과 보존

- `milestone`: 실제 물리/시뮬 실행과 raw/funnel/영상이 있는 결과. **삭제·이동 금지**, state만 coordinator가 결정. 해당: #537, #533, #535, #534, #521, #491, #461, #437.
- `study`: 체계적 비교·분석. 원본/요약/해시 보존. 해당 다수.
- `dev`: DEV 진단/부정 결과. 성능 주장으로 승격하지 말고 그대로 보존.
- `infra`/`policy`: 도구/계약. 실험 증거는 아니지만 계약 텍스트는 보존.
- superseded/rework로 분류해도 **원 증거 등급은 유지**한다. “현재 경로에서 대체”와 “과거 증거 삭제”는 다른 결정이다(삭제는 조정자).

## 5. 조사·출처

이 작업은 새 외부 논문을 호출·다운로드하지 않았고, 저장소의 기존 PR/실험 기록에서 이미 확인된 공개 방법을 승계했다. 새 구현을 만들지 않는 감사이므로 “그대로 쓸 공개 방법”은 대체 대상의 근거로만 인용한다.

| id | 방법/출처 | 확인 위치 | 이 감사에서의 용도 |
|---|---|---|---|
| R1 | [ROVIO (Bloesch et al., IJRR 2017) / ROVIO FeatureStatistics.hpp (BSD-3-Clause)](https://github.com/ethz-asl/rovio) | PR #574 / experiments/2026-10-17-egomem2 | 자기 RGB/LK+자기 명령의 예측→관측 순서; 정적 지도 없는 상대 위치 갱신 |
| R2 | [OpenCV Lucas-Kanade optical flow tutorial (official docs)](https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html) | PR #574 body (LK 사용) | 자기 RGB feature tracking; map 없이 frame-to-frame 상대 변위 |
| R3 | [ROS REP-105](https://ros.org/reps/rep-0105.html) | PR #440 / #507 | 기존 map→odom 보정이 왜 정적 지도 경로였는지 설명; 새 경로는 ego frame |
| R4 | [Nav2 nav2_amcl (pinned b58a7573) and Probabilistic Robotics](https://github.com/ros-navigation/navigation2/tree/b58a7573f44a984fdc5f3eaa80c4b62ac529ab9d/nav2_amcl) | PR #507 / #440 | 정적 지도 위치추정의 공개 표준 구현; 대체 대상 비교 기준 |
| R5 | [Moravec & Elfes 1985; Elfes 1990; Yamauchi 1997; slam_toolbox/gmapping](https://biorobotics.ri.cmu.edu/papers/sbp_papers/integrated1/yamauchi_frontiers.pdf) | PR #506 | 자기 관측 점유 격자/frontier; 정적 지도 대신 자기 지도 |
| R6 | active visual search / next-best-view literature (Connolly 1985; Bajcsy 1988) — 원문 미열람, 프로젝트 기존 참고 목록 | PR #502 참고 목록 | 둘러보기 방향을 정보이득/미확인 영역 기준으로 선택; static landmark 대신 ego memory |

추가로 각 PR 본문의 참고 자료를 그대로 보존한다: #473(SayCan, ProgPrompt, Code as Policies, RoCo, CoELA, SMART-LLM, Inner Monologue, Reflexion; Gemma/OpenRouter 공식 문서), #507(Nav2 AMCL 고정 소스, Fox 2001 KLD, Probabilistic Robotics), #506(Moravec & Elfes 1985, Elfes 1990, Yamauchi 1997, gmapping, slam_toolbox), #440(REP-105, Nav2 AMCL, robot_localization, NIST χ²), #533(Silver 2005, PIBT 2019, ORCA, Nav2 NavFn), #563(ACT §IV, DAgger).

## 6. 한계와 다음 조치

- 이 감사는 main `79a4918d0`과 51개 open PR head ref의 **코드 grep/열람** 기준이다. PR 브랜치가 main보다 뒤처져 있어 “브랜치에 파일이 있음”과 “이 PR이 그 파일을 변경함”을 구분했다.
- PR 본문의 성공/실패 수치는 재실행 검증하지 않았다. 표의 `evidence_grade`는 원 기록의 주장 등급이다.
- CI는 2026-10-17 수집 시점의 GitHub rollup이며, 이후 갱신될 수 있다.
- **조정자 결정 필요**: (a) #537/#533의 setup admission static map을 “평가 전용”으로 허용할지, (b) `AGENTS.md:90,104` 문구 갱신, (c) superseded PR의 증거 보존/아카이브 방식, (d) #574를 egocentric 기준 구현으로 승격할지(오프라인 NOT_READY 해소 후).
- 다음 구현 작업(다른 작업자): `setdown_lookaround_v1`의 방향 계산을 `egocentric_landmark_memory`로 바꾸고, 판단 LLM 입력에서 static map/top RGB를 제거하며, `check_current_stack.py`에 `static_map_use=none`/`goal_discovery=visual_search`/`localization_initial_prior=none` rejection을 등록한다.

## 7. 재현

```bash
python3 - <<"PY"
import json
o=json.load(open("experiments/2026-10-17-stackgrep/table.json"))
print(o["counts"]); print(o["ci_summary"])
PY
```

`table.json` 필드: `baseline`, `decisions`, `research`, `static_map_audit`(55), `adjacent_boundary_findings`, `pr_classification`(51), `ci_summary`, `counts`, `limitations`.
