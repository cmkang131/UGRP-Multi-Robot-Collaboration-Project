# v7-1b 메모: 1b, 리스크 2, XML 기준 디렉터리 (2026-10-21)

대상은 Codex v6 재검토 `~/.ductor/codex/workspace/output_to_user/reports/collect-v6-review-20261021/REPORT.md`의 잔여 항목입니다(리스크 2, 리스크 3의 1b·XML).
작업 브랜치는 `dsh/pairact-carry-r1-v7-1b`(base `088c88c7b`)이고, 나중에 `dsh/pairact-carry-r1-v7`로 병합합니다.
2b 영역(episode_assets 해시, verify_assets 자산 재해시)은 건드리지 않았습니다. 새 함수는 모두 `harness/pairact_collect.py` 끝의 v7 절에 모았습니다.
`CODEX_RESPONSE`·`RUN_MANIFEST.json` sha는 갱신하지 않았습니다(병합 단계에서 처리). 검증은 CPU 단위 시험만 했고, 시뮬레이터·GPU·VM은 실행하지 않았습니다.

## 지적 ↔ 수정 ↔ 코드 ↔ 테스트

| 지적 | 수정 | 코드 (HEAD 행) | 테스트 (`tests/test_pairact_collect_v7_1b.py`) |
|---|---|---|---|
| 리스크 2: 검사기는 토큰을 읽고 실행은 `shell=True` | 명령 형태를 하나로 고정: `[WARP_SOURCE_ROOT=/abs] python[3[.N]] wrapper.py --opt ...`. 다음은 거부: 셸 연산자(`; && \| > & ( )`), `$`·백틱, `env`/`cd`/`sh`/`exec`/`nohup` 접두, 다른 환경변수 대입, 인터프리터 옵션(`-I`/`-c`/`-m`), standalone `--`, 짧은 옵션. 실행은 같은 함수가 만든 argv를 `shell` 없이 `cwd`를 명시해 실행 | `harness/pairact_collect.py:1882` `episode_command_form`, `:2008` `episode_argv`, `:271` `episode_cmd_audit`(형태와 parser 선검사); `scripts/run_pairact_collect.py:547` `shell_episode`(argv 실행) | `test_episode_command_form_refuses_shell_syntax`(21 사례), `test_runner_executes_the_checked_argv_without_a_shell` |
| 리스크 1·2: `--`·값 없는 옵션·`--unknown`을 검사기는 받고 wrapper는 exit 2 | 실제 wrapper(`experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py`)의 `parser()`를 import 없이 AST로 꺼내, 오류 시 종료 대신 예외를 던지게 하고 `parse_known_args`로 실행 전에 판독. 철자가 정확하지 않은 옵션(약어 포함), 읽히지 않고 남은 인자, parser 오류는 거부. 게이트 값과 parser 값이 같아야 함. 판독 대상은 템플릿의 wrapper 파일이고, 그 파일이 없으면 이름이 gcp6 wrapper일 때 레포 사본을 씀. manifest 게이트(core/final, verify_assets 유무와 무관)에서 정적으로 호출 | `:1922` `wrapper_parser`, `:1946` `episode_parse_problems`, `:1985` `episode_command_problems`, `:1472` gate 호출 | `test_real_wrapper_parser_accepts_the_manifest_draft_command`, `test_real_wrapper_parser_refuses_what_the_wrapper_would_exit_2_on`(8 사례), `test_manifest_gate_refuses_form_violations_at_core_and_final`(4 사례 × core/final) |
| 1b: teacher 단독 실행이 manifest core에 결속되지 않음 | frozen teacher(`75929e771`)와 wrapper는 stack pin·`assets.wrapper_sha256` 대상이라 고칠 수 없습니다. 따라서 수동 실행(PAIRACT_P3_* 환경변수를 직접 설정) 자체는 막을 수 없습니다. 대신 runner가 manifest 게이트(core는 `frozen_gate`, 학습은 final)를 통과한 뒤에만 실행 직전에 `<out>.pairact-binding.json`(core, manifest sha, template sha, argv sha, cwd, out)을 씁니다. teacher 산출물을 쓰는 지점은 이 결속을 요구합니다: check-rows의 baseline·probe raw는 stage core와 같은 core, convert-input의 학습·검증 admitted raw는 stage final과 같은 core. 결속 없이 만든 산출물은 쓰이지 않습니다 | `:2046`–`:2062` `launch_binding_path`/`launch_binding`/`launch_binding_problems`; runner `:563` `require_launch_bindings`, `:681` probe-episode 결속, `:691` check-rows, `:640` convert-input, collect의 `run_episode` 결속(freeze core가 있을 때) | `test_launch_binding_is_written_before_the_teacher_starts`, `test_direct_teacher_run_with_pairact_env_is_refused_downstream`(반례: collector env로 직접 실행 → check-rows 거부), `test_copied_launch_binding_is_refused` |
| XML: include/compiler 경로 의미 | teacher는 `--canonical-xml`을 `read_text()`로 읽어 문자열로 컴파일합니다(wrapper `:189`, `sim/natural_scene_texture.py:65` 주석 "from_xml_string resolves relative directories from the scene's cwd"). 그래서 상대 include, meshdir/texturedir/assetdir, 파일명은 XML 디렉터리가 아니라 *프로세스 cwd* 기준으로 해석됩니다. v5 검사기는 XML 디렉터리 기준이었습니다. `xml_dependencies(base=)`를 추가했고, 게이트는 runner의 실제 실행 cwd(`os.getcwd()`, 실행 시 같은 값을 `cwd=`로 명시)로 의존집합을 만듭니다. 등록 목록과 같아야 하고 각 파일이 존재해야 합니다. `flexcomp file`도 meshdir 아래 의존으로 추가 | `:1332` `xml_dependencies(base)`, `:1328` flexcomp, `:2017` `episode_xml_problems`, `:1504` gate(episode_cwd가 있을 때); runner `:523` | `test_canonical_xml_relative_names_resolve_at_the_episode_cwd`, `test_repository_scene_export_resolves_its_texture_only_at_the_repository_root`(레포 실제 내보낸 scene: 텍스처는 레포 cwd 기준으로만 존재, XML 디렉터리 기준으로는 0개) |

## 회귀

`/home/ubuntu/ugrp-e1-venv/bin/python -B -m pytest tests/test_pairact_*.py -q`의 결과는 **225 passed, 4 failed**(exit 1)입니다.
- 실패 4건은 모두 `RUN_MANIFEST.json`의 `collector.file_sha256`(harness/runner 파일 sha)가 이 변경 전 값이라서 생깁니다: `test_run_manifest_file_hashes_match_this_checkout`, `test_freeze_script_core_then_final_keeps_core_sha`, `test_freeze_final_fills_the_second_vm_recording_check_without_moving_core`, `test_freeze_final_refuses_stale_primary_and_vm_recording`.
- 원인 확인: sha 두 개만 임시로 고치고 4건을 다시 돌리면 4 passed였고, 그 뒤 `git checkout`으로 되돌렸습니다(커밋하지 않음). 병합 단계에서 manifest sha를 갱신하면 실패는 0이 됩니다.
- 기존 185개 테스트는 변경 없이 그대로입니다(181개 통과, 위 4건은 sha 때문). 새 테스트는 44개입니다.

## 남은 것 / VM 필요

1. *VM 필요*: 실제 `canonical-scene.xml`(`/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/`)의 의존집합을 실행 cwd 기준으로 추출해 `assets.mesh_assets_sha256`와 대조해야 합니다. 로컬 venv에 mujoco가 없어 CPU 모델 로드 대조는 하지 못했습니다. 레포에서 내보낸 scene에도 절대 VM 경로 mesh(`/home/ugrp/ugrp-sim/src/41584d3a1-warp10-pool/...stl`)가 있습니다. 해당 scene의 `zone_wall_divider_1_*` 큐브 텍스처 6개는 이 checkout에 없습니다(소스 버전 차이로 보이며 확인이 필요합니다).
2. *VM 필요*: frozen teacher/adapter(-c5 pin)가 canonical XML을 정말 `from_xml_string`으로 컴파일하는지, 그리고 실행 cwd가 collector cwd 그대로인지(teacher 내부에서 `chdir`하지 않는지)는 고정 checkout에서 확인해야 합니다. 이 레포의 wrapper 사본은 `chdir`하지 않습니다.
3. 운영 영향: v7 이전에 수집한 FROZEN_CORE probe source에는 결속 파일이 없어 check-rows가 거부합니다. probe source·probe를 v7 runner로 다시 실행해야 합니다.
4. 범위 밖: 수동 실행 자체를 막으려면 frozen teacher가 결속을 읽어야 합니다. 이는 teacher pin 변경이 필요하므로 오너가 결정할 사항입니다. 현재는 "산출물 사용 거부"까지입니다.
5. 템플릿의 wrapper가 gcp6 wrapper가 아니고 `parser()`도 없으면 parser 판독 없이 형태 검사만 합니다(테스트 fixture의 가짜 `wrap.py` 때문). 실제 수집 템플릿은 gcp6 wrapper입니다.
6. RUNBOOK의 episode 명령 예시는 이미 이 형태(`python <wrapper> --opt ...`)입니다. `export WARP_SOURCE_ROOT`는 부모 환경으로 전달되고, 템플릿 앞 대입도 허용합니다.
