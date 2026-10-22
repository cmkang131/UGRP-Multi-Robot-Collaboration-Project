# 수집 사전 등록 v9 — 마지막 강화 라운드: 위협 모델(실수로 인한 불일치) + 실행 전후 stack 결속 (2026-10-22)

대상
- 브랜치 `dsh/pairact-carry-r1-v9`(v8 `8cacd2155` 위). v8·v7·v6·v5·main은 무변경.
- 팀장 결정(2026-10-22): 수집은 팀장 본인 VM에서 운영자가 직접 실행하므로 **위협 모델은 악의적 공격자가 아니라 실수로 인한 불일치**다. 이 위협 모델을 prereg에 한 단락으로 명시하고 v9를 **마지막 강화 라운드**로 한다. 다음 Codex 판정이 적대적 환경 항목만 남기면 운영 규칙으로 문서화하고 동결하며, 실제 정확성 버그는 계속 동결을 막는다.

상태
- `COLLECT_PREREG_DRAFT.json` 변경: `threat_model` 단락 추가, `revision` 앞머리에 v9, `audit_outputs.launch_binding`, `codex_review_items`에 v9 항목. 수치·판정·중단·할당·seed·core 계산식은 불변(status는 `READY_FOR_REVIEW` 유지).
- `RUN_MANIFEST.json` 변경: `collector.branch` v9, `collector.file_sha256`의 `harness/pairact_collect.py`·`scripts/run_pairact_collect.py`. VM 기입 필드 수·core 계산식 불변.
- 검증은 CPU 단위 시험과 합성 파일만 사용했습니다. 시뮬레이터·GPU·VM·실제 teacher 실행은 없습니다(`subprocess.call` stub 또는 합성 wrapper).

## 핵심 원칙

검사한 산출물과 실행한 산출물을 하나의 pin으로 결속한다(v8). v9는 그 pin이 덮지 않던 *상태* 두 가지를 실행 전후에 관찰해 launch binding에 남기고, 소비 단계가 불일치를 거부한다: (1) 셸의 `PYTHONPATH`/`PYTHONHOME`, (2) teacher·adapter·root 체크아웃의 HEAD·clean.

## 지적 ↔ 수정 대응표

| # | 지적(출처) | v8 동작 | v9 수정 | 테스트 (`tests/test_pairact_collect_v9.py`) |
|---|---|---|---|---|
| g1 | 셸에 남은 `PYTHONPATH`가 episode import를 바꿈 (감사 v8) | `collect_env`가 보존, pin·binding에 없음 → 조용히 실행 | `episode_pin(strict=True)`가 둘 중 하나라도 설정되면 `EpisodePinError`; `gate_pin`이 `… episode pin refused: PYTHONPATH is set …`으로 즉시 종료(SystemExit). strict `pinned_exec`도 방어적으로 제거 | `test_g_pythonpath_in_the_exec_env_is_refused_by_a_strict_pin_only`, `test_g_launch_refuses_when_pythonpath_appears_after_the_gate`, `test_g_pinned_exec_drops_unbound_env_for_strict_pins_only`, `test_g_gate_reports_pythonpath_once_with_the_command_name` |
| h1 | 관문 뒤 체크아웃이 바뀌어도(장시간 run) 이후 episode가 그대로 실행·소비 (감사 v8: root는 소비 시 재검사 skip) | 관문에서 한 번만 `check_stack_heads` | `observe_stack`(경로 realpath·HEAD·tracked-change) + `stack_manifest_problems`; `stack_gate`가 관문 직후 상태를 관찰해 launch binding `stack`에, 실행 후 `stack_now()`가 `stack_post`에 기록; `launch_binding_problems`가 불일치·`stack` 없음(v8 형식)·`stack_post` 없음·읽기 불가를 거부 | `test_h_stack_changed_during_the_episode_refuses_the_output`, `test_h_a_clean_run_is_accepted_with_pin_and_stack_posts`, `test_h_binding_without_a_stack_pin_or_a_post_stack_is_refused`, `test_h_unreadable_post_run_stack_is_refused`, `test_h_stack_gate_binds_the_manifest_pins_and_sees_a_later_edit`, `test_h_stack_manifest_problems_reports_a_wrong_head` |
| i1 | `pinned_exec`는 argv[0]만 교체하고 argv[1]이 pin wrapper인지 명시 검사하지 않음(pilot 잠재 구멍, 감사 v8) | strict에서는 토큰 규칙으로 등가, pilot은 암묵 | `pinned_exec`가 `argv[1]`을 pin wrapper와 비교(strict: 정확히 일치, pilot: cwd 기준 realpath) — 불일치면 `EpisodePinError` | `test_i_pinned_exec_refuses_a_wrapper_other_than_the_pin` |

## 운영 규칙으로 배제하는 잔여 (v9 문서·RUNBOOK에 명시)

- 수집 중 wrapper 사본·`gcp6_host.py`(호스트 신원 모듈)·세 체크아웃·venv(pip install)·canonical XML·mesh·rejection table·기록 디렉터리 수정 금지. 설치 시점에 `sha256sum beamact5-tools/*.py`를 남긴다(RUNBOOK 1-1).
- 반례: 적대적 `PYTHONPATH` 사전 주입은 코드가 *거부*하지만, 임의의 다른 환경 변수 주입·LD_PRELOAD 등은 다루지 않는다. 검사 직후~execve 사이 교체, 실행 중 교체 후 원복은 적대적 행위로 보고 방어를 주장하지 않는다.
- `--no-verify-assets`는 probe-episode·convert-input·FROZEN 수집에서 쓰지 않는다(자산·stack 재검사를 끔).

## 남은 한계 (정직하게)

1. TOCTOU: 직전 재해시(및 stack 관찰)와 `execve` 사이, python이 wrapper를 다시 여는 시점 사이의 교체는 막지 못한다. 실행 후 재해시가 *되돌린* 교체는 탐지하지 못한다.
2. wrapper가 import하는 모듈: ROOT 체크아웃 모듈은 stack pin(pre-post HEAD·clean)이 덮는다. wrapper 옆 `gcp6_host.py`는 git 검사 밖이라 *설치 시점* stale 사본은 코드가 못 잡는다(운영 규칙: 커밋에서 함께 복사 + sha256 기록).
3. python 바이너리만 해시한다(표준 라이브러리·site-packages 미결속). 수집 중 pip install 금지가 운영 규칙이다.
4. 자산(XML·mesh·rejection table)은 관문에서 해시하고 소비 시 재검사하지만, 수집 중 편집 후 원복은 미탐(운영 규칙).
5. pilot(READY)은 증거 경로가 아니다: launch binding이 없어 소비 단계가 없고, `WARP_SOURCE_ROOT` 기본값은 여전히 pilot 규칙을 따른다.
6. launch binding은 서명 없는 마커다(위조 가능). 위협 모델이 실수이므로 서명은 두지 않는다.

## 동결 판단 기준 (Codex에게)

- **동결 가능(VM 확인 조건부)**: 남은 차단이 위 "운영 규칙으로 배제하는 잔여"뿐이고, 실제 정확성 버그(잘못된 world 결과·잘못된 채택/기각)가 없을 때.
- **보류**: 실행된 파일·모듈·자산이 검사 대상과 갈라져 *잘못된 결과*가 나오는 경로가 하나라도 재현될 때.
- VM 확인 항목(코드 아님): `readlink -f` 결과, `beamact5-tools/*.py` sha256, gcp6 host identity, 자산 경로 존재.

## 검증 (DeepSeek 독립 재실행)

- 전체: `pytest tests/test_pairact_*.py` → **297 passed**(v8 286 + v9 11; v8·v7 1b 파일 각 1개는 normal-path에 stack을 넘기도록 갱신). 로그·junit: `outputs/reports/codex-astra-reviews-20261022-v9/`.
- 반례 프로브: `probe-wrapper-binding.py`(v8 것 그대로) → **8/8**(v8 수정 유지). `probe-v9-hardening.py` → **5/5**(control 수용, stack-edit 거부, pythonpath 게이트 거부, pythonpath-launch 실행 전 거부, stack-no-post 거부).
- GPU·VM·시뮬레이터 실행 0. 실제 수집 성공의 근거가 아닙니다.
