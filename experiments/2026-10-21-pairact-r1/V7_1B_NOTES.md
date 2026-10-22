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
4. 범위 밖: 수동 실행 자체를 막으려면 frozen teacher가 결속을 읽어야 합니다. 이는 teacher pin 변경이 필요합니다. *오너 결정(2026-10-22, 강창민): 1안 "산출물 사용 거부"만 적용, frozen teacher pin은 바꾸지 않음.*
5. ~~템플릿의 wrapper가 gcp6 wrapper가 아니고 `parser()`도 없으면 형태 검사만 합니다.~~ → *병합 단계(보강 b)에서 해소*: core/final 게이트(`check_run_manifest`)는 `episode_command_problems(strict=True)`로 parser()가 없거나 wrapper 파일이 없으면 거부합니다. 테스트의 가짜 `wrap.py`는 parser()를 갖도록 고쳤습니다(`tests/test_pairact_collect.py` `FAKE_WRAPPER_SOURCE`). 형태 검사만 하는 경로는 manifest 없는 pilot 감사(`episode_cmd_audit`)에만 남습니다.
6. RUNBOOK의 episode 명령 예시는 이미 이 형태(`python <wrapper> --opt ...`)입니다. `export WARP_SOURCE_ROOT`는 부모 환경으로 전달되고, 템플릿 앞 대입도 허용합니다.

## 병합 단계 추가: MuJoCo CPU 로드 대조 (2026-10-21, 작업 C)

- 환경: `/tmp/v7-mj-venv`(레포 밖 별도 venv), `pip install mujoco` → *mujoco 3.16.0 CPU wheel 설치 성공*. 테스트 스위트는 이 venv를 쓰지 않습니다.
- 스크립트: `scripts/pairact_r1_xml_load_check.py`(작성 당시 `/tmp/v7-mj-check/check.py`, 2026-10-22 레포로 이동, 내용은 docstring만 변경 — 레포 사본 재실행 결과가 원 결과와 `seconds` 외 동일), 결과 `/tmp/v7-mj-check/egonav.json`. `MjModel.from_xml_string`으로 *로드만* 했고 `mj_step`은 호출하지 않았습니다. 소요 3.1초.
- 대상: 실제 pairact canonical scene(`/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml`)은 VM에만 있어 로컬에 없습니다. 대신 레포에 있는 같은 exporter 산출물 `experiments/2026-10-17-egonav/raw/far-diag-range-01/scene.xml`(`texturedir="sim/assets/floor_light_textured_v1"` 상대, mesh 1개 VM 절대경로)을 썼습니다.
- 결과
  - 원본 그대로 로드(cwd=레포 루트, cwd=XML 디렉터리): 둘 다 실패. 첫 오류는 VM 절대경로 mesh `/home/ugrp/ugrp-sim/src/41584d3a1-warp10-pool/sim/assets/masterpi_drive_friction_v2/fuji_roller.stl` 열기 실패.
  - `xml_dependencies(base=레포 루트)` = 38개 파일(VM mesh 1 + 로컬 37). 로컬 37개 중 6개(`zone_wall_divider_1_250_14750_2000_{fileright,fileleft,fileup,filedown,filefront,fileback}.png`)는 이 checkout에 없습니다.
  - 대조 방법: 빈 임시 디렉터리에 *의존집합 파일만* 같은 상대 배치로 복사하고, VM mesh는 레포의 같은 꼬리 경로 사본(`sim/assets/masterpi_drive_friction_v2/fuji_roller.stl`)으로 XML 문자열 안에서 치환, cwd=임시 디렉터리에서 로드.
    - 없는 텍스처 6개를 채우지 않으면 실패(`...fileright.png` 열기 실패). 따라서 그 6개는 실제 로드에 필요합니다.
    - 6개를 8×8 회색 PNG 자리표시자로 채우면 *로드 성공*. 의존집합 밖의 파일이 없어도 로드되므로, 필요 집합 ⊆ 우리 의존집합입니다.
    - 로컬 의존 파일 37개를 하나씩 빼면 *37/37 로드 실패*. 따라서 우리 의존집합 ⊆ 필요 집합입니다. 대조군인 의존집합 밖 파일 1개를 빼면 로드 성공.
  - 결론: 이 scene에서 `xml_dependencies(base=cwd)`의 로컬 부분은 MuJoCo 3.16 `from_xml_string`(cwd 기준)이 실제로 여는 파일 집합과 *정확히 일치*합니다. 원본 XML을 XML 디렉터리 cwd로 로드해도 텍스처 경로가 풀리지 않는다는 점(B의 cwd 기준 해석)과도 일치합니다.
- 한계(VM 필요): (1) 실제 canonical-scene.xml과 VM mesh는 로컬에 없어 대조하지 못했습니다. (2) VM mesh는 레포 사본으로 치환했으므로 VM 파일 자체의 sha는 검증하지 않았습니다. (3) 로컬 3.16과 VM mujoco(manifest 예시 3.3.6)의 경로 해석이 같은지는 VM에서 같은 스크립트로 확인해야 합니다. (4) `zone_wall_divider_1_*` 텍스처 6개 부재의 원인(소스 버전 차이)은 미확인입니다.
