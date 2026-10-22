# 수집 사전 등록 v8 — Codex v7 4차 중간 판정 '보류' 대응표 (2026-10-22)

대상
- Codex v7 4차 중간 판정 '보류'. core·final manifest 관문이 검사한 wrapper .py(parser 판독·sha256)와 *실제로 실행되는 파일이 다를 수 있음*(검사 경로와 실행 경로가 갈라짐). 최종 보고서는 아직 없어서 팀장 지시의 설계 기준으로 진행했습니다(`collect-v7-review-20261022/REPORT.md`는 그 이전 f6a4489 기준 OK 판정).
- 브랜치 `dsh/pairact-carry-r1-v8`(v7 `7195a59df` 위). v7·v6·v5·main은 무변경.

상태: `COLLECT_PREREG_DRAFT.json` 무변경(READY_FOR_REVIEW, sha256 `e44b090625f718b7b9257ce241cf6d51fe759b565a9304f29f9ad8d2f89c4fbe`, v7과 같음). `RUN_MANIFEST.json`(DRAFT_VM_FILL) 변경: `collector.branch` v8, `collector.file_sha256`의 `harness/pairact_collect.py`·`scripts/run_pairact_collect.py`, `command.episode_template_draft` 앞머리 `python`→`$PY`(절대경로 python). VM 기입 필드 수와 core 계산식은 그대로입니다.
검증은 CPU 단위 시험만 했습니다. 시뮬레이터·GPU·VM은 실행하지 않았고, teacher 실행은 `subprocess.call` stub으로 대체했습니다.

## 핵심 원칙

검사한 wrapper의 *경로+내용 해시*를 하나의 값(pin)으로 고정하고, 관문과 실행이 같은 값을 씁니다. pin = {wrapper 절대경로, wrapper sha256, python 경로·realpath·sha256, WARP_SOURCE_ROOT realpath, cwd, strict}.

## 지적 ↔ 수정 대응표

| # | 반례 | v7 동작 | v8 수정 | 테스트 (`tests/test_pairact_collect_v8.py`) |
|---|---|---|---|---|
| a | 상대 wrapper 경로 + cwd 차이 | 관문은 자기 cwd의 A를 판독, 실행 cwd에선 B 실행 | `resolve_episode_wrapper`: 절대경로만 허용. core 관문·frozen 실행 모두 거부 | `test_a_relative_wrapper_is_refused_by_the_gate_and_the_launch` |
| b | named wrapper 부재 → REPO_WRAPPER 대체 판독 | 레포 사본 parser로 통과, 나중에 그 경로에 생긴 다른 파일 실행 | strict(core/final)는 REPO_WRAPPER 대체 금지. named 파일의 바이트를 해시하고 그 바이트로 parser를 읽음(`wrapper_parser(path, source)`) | `test_b_missing_named_wrapper_is_not_read_through_the_repository_copy` |
| c | symlink(파일·부모·조상 성분), `..`, 관문 후 내용/대상 교체, 실행 중 교체 | 모두 통과·실행 | realpath==토큰 요구(O_NOFOLLOW 열기 + 열기 전후 realpath 재확인), 일반 파일만. runner가 `subprocess.call` 직전 pin 재해시·재확인, 불일치면 실행 안 함(`EpisodePinError`). 실행 후 재해시해 launch binding `pin_post`에 기록, `launch_binding_problems`가 pin≠pin_post·pin 없음·pin_post 없음이면 산출물 거부 | `test_c_symlink_in_any_wrapper_path_component_is_refused`(3), `test_c_dotdot_component_is_refused`, `test_c_wrapper_changed_after_the_gate_is_not_launched`(3), `test_c_wrapper_changed_while_running_refuses_the_output`, `test_c_binding_without_post_pin_or_pin_is_refused` |
| d | bare `python`이 실행 PATH로 다른 인터프리터로 해석 | 통과·PATH의 첫 python 실행 | core/final은 절대경로 python만 허용(템플릿 sha가 경로를 core에 결속). pin에 realpath·sha256 고정, 실행 직전 재확인. pilot은 bare 허용하되 실행 env PATH로 한 번 해석한 절대경로로 argv[0] 치환 | `test_d_bare_python_is_refused_at_core_and_at_a_frozen_launch`, `test_d_pilot_bare_python_runs_the_path_resolved_once`, `test_d_interpreter_swapped_after_the_gate_is_not_launched` |
| e | WARP_SOURCE_ROOT 토큰 vs env | 토큰 우선으로 조용히 통과 | `resolve_episode_root`: 둘 다 있고 realpath가 다르면 거부. 실행 env에 pin의 realpath를 명시적으로 넣고, 아무 데도 없으면 env에서 제거. `check_stack_heads`도 같은 함수 사용(실행 env 전달) | `test_e_root_token_and_env_disagreeing_is_refused`, `test_e_exec_env_carries_the_pinned_root_realpath`, `test_e_root_changed_after_the_gate_is_not_launched` |
| f | 정상 경로 | — | 관문 통과, argv[0]=pin python, argv[1]=pin wrapper, pin==pin_post, 소비 시 수용. verify_assets의 wrapper 해시도 같은 resolver | `test_f_normal_command_passes_the_gate_and_runs_the_pinned_values`, `test_f_verify_assets_hashes_the_pinned_wrapper` |

## 설계 선택

- 인터프리터: *절대경로만 허용*을 골랐습니다. 이유: (1) 템플릿 문자열이 이미 core에 들어가므로 경로가 추가 필드 없이 core에 결속됩니다. (2) PATH 해석 결과를 관문에서 고정하는 방식은 그 값이 core에 들어가지 않아 결속이 launch binding에만 남습니다. venv python은 base 인터프리터로의 symlink이므로 wrapper와 달리 symlink 금지는 하지 않고, argv[0]은 venv 경로 그대로 두고(venv 유지) realpath·sha256을 pin에 고정합니다.
- wrapper 절대경로의 core 결속: strict 규칙상 토큰 = 절대 realpath 이고 템플릿이 core에 포함되므로 core 계산식을 바꾸지 않았습니다. 내용은 기존 `assets.wrapper_sha256`(verify_assets 관문) + runner `gate_pin`(frozen 실행 시 항상 pin sha256 == manifest `assets.wrapper_sha256` 요구)으로 결속됩니다.
- launch binding: 같은 schema 이름에 `pin`·`pin_post` 필드를 추가했습니다. v7에서 만들어진 binding(pin 없음)은 소비 시 거부됩니다(v7 probe 자료는 원래도 재실행 대상).

## 남은 한계 (정직하게)

1. *실행 중 교체(TOCTOU)*: 직전 재해시와 `execve` 사이, 그리고 python이 wrapper 파일을 다시 여는 시점 사이에 파일이 바뀌면 막을 수 없습니다. 실행 후 재해시가 *되돌린 교체*(바꿨다가 원복)는 탐지하지 못합니다. 불변 저장소·읽기 전용 마운트가 아니므로, 수집 중 wrapper/root 수정 금지 운영 규칙이 여전히 필요합니다.
2. wrapper가 import하는 모듈(teacher/adapter/root 체크아웃)의 내용은 pin이 아니라 기존 stack pin(git HEAD·clean)으로만 결속됩니다. 실행 중 체크아웃 변경은 같은 TOCTOU 한계입니다.
3. `--no-verify-assets`(VM 밖) 관문은 manifest의 wrapper sha256과 대조하지 않습니다. 다만 frozen 실행 경로(`gate_pin`)는 항상 대조합니다.
4. python 바이너리 해시는 인터프리터 본체만 덮습니다. 표준 라이브러리·site-packages는 결속하지 않습니다(host.python 문자열 기록 수준).
