# 수집 사전 등록 v7 — Codex v6 재검토 대응표 (2026-10-21)

대상
- Codex v6 재검토: `~/.ductor/codex/workspace/output_to_user/reports/collect-v6-review-20261021/REPORT.md`. v6 코드 수정 OK, 단 *2b가 동결 차단*(per-world 참조 파일·sidecar 내용이 core에 결속되지 않음).
- 브랜치 `dsh/pairact-carry-r1-v7`(v6 `088c88c7b` 위). v6·v5·main 무변경. 2b는 작업 A(`4752bf1a2`)에서 처리했습니다. 1b·리스크 2·XML은 작업 B(`dsh/pairact-carry-r1-v7-1b` `8d9f0a576`)에서 처리했고, merge commit `34eb72ab2`로 병합했습니다(rebase 없음, 텍스트 충돌 없음). 그 위에 보강 a/b를 커밋했습니다.

상태: `COLLECT_PREREG_DRAFT.json` 무변경(*READY_FOR_REVIEW*, sha256 `e44b0906…c36cad3c`, v6와 같음). `RUN_MANIFEST.json` = *DRAFT_VM_FILL*. 바뀐 것은 VM 기입 필드 1개 추가(`assets.per_world_reference_files_sha256`), `collector.branch`(`dsh/pairact-carry-r1-v7`), `collector.file_sha256`의 `harness/pairact_collect.py`·`scripts/run_pairact_collect.py`·`scripts/pairact_r1_freeze.py` 값입니다.
검증은 모두 CPU 단위 시험입니다. 시뮬레이터·GPU·VM은 실행하지 않았습니다.

## 코드에서 확인한 판독 규칙 (2b의 전제)

- per-world JSON 형식: `{scene XML sha256: {"actuator": 경로, "geometry": 경로}}`. gcp6 runner가 `<out>/references/<sha>/compiled-312.json`, `compiled-geometry312.npz`로 쓰고 `<out>/per-world-references.json`에 기록합니다(`experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py:255-262`).
- 실행 판독: wrapper가 `json.loads(read_text())`로 읽고(`run_warp_flow_teacher_gcp6.py:265`), backend가 `Path(ref['actuator'])`·`Path(ref['geometry'])`를 엽니다(`scripts/warp_act_backend.py:115`, `:430-431`). *상대경로는 JSON 위치가 아니라 프로세스 cwd 기준으로 풀립니다.* JSON 위치 기준으로 해석하는 검사기는 다른 파일을 검사하게 되므로, v7은 상대경로를 거부합니다.
- per-world sidecar: `apply_geometry`가 `str(geometry) + '.json'`을 읽고 그 안의 `npz_sha256`·`xml_sha256`으로 npz를 확인합니다(`scripts/simalt_compiled_compat.py:84`). 이 sidecar는 모델 입력이므로 결속 대상입니다. `apply_reference`는 actuator 파일 하나만 읽습니다(`:31`).
- 레코딩 sidecar(`sidecar_check`, `teacher-<rid>.jsonl`/`student-<rid>.jsonl`, `harness/pairact_collect.py:847`)는 에피소드 *출력* 라벨 스트림입니다. 모델 입력이 아니고 실행 전에는 존재하지 않으므로 core 동결 대상이 아닙니다. 사후 결속은 기존 ledger/convert 경로가 맡습니다.
- actuator/geometry 파일은 다른 파일을 참조하지 않습니다(include·mesh 없음, JSON/npz 배열). XML include·mesh 의존은 기존 `assets.mesh_assets_sha256`(v5 `xml_dependencies`)가 맡습니다.

## 지적 ↔ 수정 대응표

| # | 지적 (Codex v6) | v7 수정 | 코드 (HEAD 기준) | 테스트 (`tests/test_pairact_collect_v7.py`) |
|---|---|---|---|---|
| 2b | core에는 per-world JSON 자체 sha256만 결속. JSON이 가리키는 actuator/geometry·sidecar 내용이 같은 core 아래에서 바뀔 수 있음 | (1) *단일 판독 함수* `per_world_reference_files`: JSON에서 wrapper가 여는 파일 목록(actuator, geometry, geometry `.json` sidecar)을 결정적으로 추출. 거부 조건: JSON 경로가 상대경로이거나 symlink, 중복 키(`json.loads`는 마지막 값을 씀), 키가 64-hex가 아님, 항목 키가 정확히 {actuator, geometry}가 아님, 상대경로·`..`·비정규 경로, JSON 디렉토리(루트) 밖 경로, 루트 아래 경로 성분 중 symlink, realpath가 루트 밖. (2) `per_world_reference_digest`: 정렬된 `[[루트 기준 상대경로, sha256], …]`의 canonical sha256. 파일 누락·비정규 파일이면 거부. (3) 새 manifest 필드 `assets.per_world_reference_files_sha256`(VM 기입, `_sha64`). `manifest_core`에 포함되므로 *core_sha256에 결속*. (4) manifest gate: `verify_assets`이면 stage(core/final)와 무관하게 template의 `--per-world-model-references-v1`(v6 `episode_option` 판독)로 digest를 다시 계산해 manifest 값과 비교하고, 판독 거부·불일치면 problems에 넣음. (5) VM 기입 도구 `pairact_r1_freeze.py per-world-refs --refs JSON` | `harness/pairact_collect.py`: `:1216` MANIFEST_SPEC, `:1230` VM_FIELDS(22→23), `:1384-1451` `PER_WORLD_REF_KEYS`·`GEOMETRY_SIDECAR_SUFFIX`·`_no_duplicate_keys`·`per_world_reference_files`·`per_world_reference_digest`, `:1562-1570` gate. `scripts/pairact_r1_freeze.py:91` `per_world_refs`, `:99`·`:109-115` CLI | 정상 대조군: `test_control_is_accepted_at_core_and_final`. 판독 일치: `test_files_are_exactly_what_the_wrapper_opens`(wrapper·`apply_geometry` 판독 행이 레포에 그대로인지도 확인). 변조(모두 core·final 거부): `test_one_byte_change_in_a_referenced_file_is_refused`(actuator·geometry), `test_replaced_file_same_name_other_content_is_refused`, `test_sidecar_content_change_is_refused`, `test_missing_sidecar_is_refused`, `test_added_or_removed_reference_is_refused_even_with_the_json_rehashed`(JSON sha만 다시 등록해도 거부), `test_symlink_swap_with_identical_content_is_refused`(같은 내용 symlink도 거부), `test_symlinked_directory_is_refused`, `test_symlinked_references_json_is_refused`, `test_path_outside_the_root_is_refused`(루트 밖 절대경로, `..`, 상대경로), `test_ambiguous_references_json_is_refused`(중복 키, 추가 키, sha 아닌 키, 배열). 결속: `test_reregistering_the_digest_is_a_different_core`(digest까지 다시 등록하면 core가 달라지고, 원래 core에 묶인 녹화로는 final 거부). 기타: `test_relative_references_json_path_is_refused`, `test_digest_is_independent_of_json_key_order`, `test_digest_field_is_a_vm_field_in_the_core` |

기존 테스트 변경(스펙 변경에 따른 최소 수정, 판정 약화 없음)
- `tests/test_pairact_collect.py`: VM 기입 필드 22→23(`test_run_manifest_draft_has_23_vm_fields_and_blocks_frozen_stages`), `filled_manifest`에 새 필드 값, `test_verify_assets_rehashes_episode_files`의 `refs.json`을 유효 JSON `{}`로 바꾸고 digest 등록.
- `tests/test_pairact_collect_v5.py::_asset_case`: 새 필드에 digest 등록.

## 1b / 리스크 2 / XML (작업 B, 병합)

상세 근거는 `V7_1B_NOTES.md`에 있습니다. 행 번호는 병합 후 HEAD 기준입니다.

| # | 지적 (Codex v6) | v7 수정 | 코드 | 테스트 |
|---|---|---|---|---|
| 리스크 2 | 검사기는 토큰을 읽고 runner는 `shell=True`로 실행. 셸 문법·env·cwd가 검사 밖에 있음 | 명령 형태를 `[WARP_SOURCE_ROOT=/abs] python[3[.N]] wrapper.py --opt ...` 하나로 고정. 셸 연산자, `$`·백틱, `env`/`cd`/`sh`/`exec` 접두, 인터프리터 옵션, standalone `--`, 짧은 옵션은 거부. runner는 같은 함수가 만든 argv를 `shell` 없이 `cwd`를 명시해 실행 | `harness/pairact_collect.py` `episode_command_form`, `episode_argv`, `episode_cmd_audit`; `scripts/run_pairact_collect.py` `shell_episode` | `tests/test_pairact_collect_v7_1b.py` `test_episode_command_form_refuses_shell_syntax`(21), `test_runner_executes_the_checked_argv_without_a_shell` |
| 리스크 1·2 | `--unknown`·값 없는 옵션·`--`를 검사기는 받고 wrapper는 exit 2 | wrapper의 `parser()`를 import 없이 AST로 꺼내 실행 전에 판독(`parse_known_args`, 오류는 예외). 정확한 철자, 남는 인자 없음, 게이트 값 = parser 값 | `wrapper_parser`, `episode_parse_problems`, `episode_command_problems` | `test_real_wrapper_parser_accepts_the_manifest_draft_command`, `test_real_wrapper_parser_refuses_what_the_wrapper_would_exit_2_on`(8), `test_manifest_gate_refuses_form_violations_at_core_and_final` |
| 1b | teacher 단독 실행이 manifest core에 결속되지 않음 | runner가 게이트 통과 후에만 `<out>.pairact-binding.json`(core, manifest·template·argv sha, cwd, out)을 씀. check-rows(core)와 convert-input(final)은 같은 core의 결속을 요구. 수동 실행 자체는 frozen teacher pin 때문에 막지 못하고, 그 산출물을 *사용 거부*하는 데까지 처리 | `launch_binding_path`/`launch_binding`/`launch_binding_problems`; runner `require_launch_bindings` | `test_launch_binding_is_written_before_the_teacher_starts`, `test_direct_teacher_run_with_pairact_env_is_refused_downstream`, `test_copied_launch_binding_is_refused` |
| XML | include·compiler 경로 해석 기준 | teacher는 `--canonical-xml`을 `read_text()` 후 `from_xml_string`으로 컴파일하므로 상대 이름은 *프로세스 cwd 기준*. `xml_dependencies(base=)`를 추가하고, 게이트는 runner 실행 cwd 기준으로 의존집합을 만들어 등록 목록과 같은지, 각 파일이 있는지 확인. `flexcomp file` 추가 | `xml_dependencies`(`:1334`), `episode_xml_problems`(`:2144`) | `test_canonical_xml_relative_names_resolve_at_the_episode_cwd`, `test_repository_scene_export_resolves_its_texture_only_at_the_repository_root` |

A·B 일관성(병합 시 확인): 2b의 per-world 참조 파일은 *정규화된 절대경로만* 받습니다(`per_world_reference_files`, `:1410`). 따라서 wrapper의 cwd와 무관하게 같은 파일을 가리킵니다. B의 cwd 기준 해석은 canonical XML의 상대 이름(include, meshdir/texturedir, 파일명)에만 적용됩니다. 두 판독은 서로 다른 입력을 다루며 `check_run_manifest`의 `verify_assets` 절에서 둘 다 실행됩니다. per-world 참조에 상대경로를 허용하려면 B와 같은 cwd 기준이 필요하지만, v7은 상대경로를 거부하므로 충돌하지 않습니다.

## 병합 후 보강 (작업 C)

| # | 구멍 | 수정 | 코드 | 테스트 (`tests/test_pairact_collect_v7_merge.py`) |
|---|---|---|---|---|
| a | wrapper parser는 모델 입력을 바꾸는 옵션(`--compiled-reference-v1`, `--compiled-geometry-312-v1`, `--physics-backend`, `--export-compiled-only` 등, act teacher의 `--damping-ablation-v1`)도 받습니다. B의 parser 판독은 parser가 아는 옵션이면 통과시키므로, core가 해시하지 않은 파일이 모델에 들어갈 수 있었습니다 | `EPISODE_OPTION_ALLOWLIST`(명시 목록 18개, 각 값의 결속 근거를 함께 기록): 값 옵션 `--flow`·`--cap-s`·`--vm-hourly-usd`(template sha), `--teacher-source`·`--adapter-source`(stack pin), `--canonical-xml`·`--per-world-model-references-v1`·`--rejection-table`(assets 해시), `--cases`·`--indices`·`--out`(runner 자리표시자, 값이 정확히 `{cases}`/`{indices}`/`{out}`이어야 함), 스위치 7개(template sha). core/final 게이트는 그 밖의 `--옵션`(`=` 형태 포함)을 parser가 알더라도 거부 | `:2097` `EPISODE_OPTION_ALLOWLIST`, `:2115` `episode_allowlist_problems`, `:1545` 게이트 호출 | `test_model_input_option_known_to_the_parser_is_refused_at_core_and_final`(6 사례 × core/final: parser는 수용하고 게이트는 거부함을 함께 확인), `test_real_wrapper_options_outside_the_allowlist_are_named`(실제 gcp6 parser 기준, allowlist ⊆ parser 옵션), `test_manifest_draft_command_uses_only_allowlisted_options`, `test_runner_options_must_carry_their_placeholder`(3), `test_allowlisted_command_is_accepted_at_core_and_final` |
| b | (B 잔여 5) wrapper에 parser()가 없으면 형태 검사만 하는 fallback | `episode_command_problems(strict=True)`: core/final 게이트에서 parser()가 없거나 wrapper 파일이 없으면 거부합니다. fallback은 manifest가 없는 pilot 감사(`episode_cmd_audit`)에만 남깁니다. 테스트의 가짜 `wrap.py`는 parser()를 갖도록 fixture를 고쳤습니다(`FAKE_WRAPPER_SOURCE`). 판정 기준은 완화하지 않았습니다 | `:2067` `episode_command_problems`, `:1544` | `test_wrapper_without_parser_is_refused_at_core_and_final`, `test_missing_wrapper_is_refused_at_core_and_final`, `test_pilot_audit_keeps_the_form_only_fallback` |

기존 테스트 변경(fixture만): `tests/test_pairact_collect.py`의 `EP_CMD`가 상대 `wrap.py` 대신 parser()가 있는 임시 가짜 wrapper 절대경로를 씁니다. `test_verify_assets_rehashes_episode_files`의 `wrap.py`와 `tests/test_pairact_collect_v5.py::_asset_case`의 `wrap.py`(`# inert`)도 같은 소스로 바꿨습니다. assert는 바꾸지 않았습니다.

## XML CPU 대조 (MuJoCo 3.16.0, 로드만)

`/tmp/v7-mj-venv`에 CPU wheel 설치에 성공했습니다. 레포의 exporter scene(`experiments/2026-10-17-egonav/raw/far-diag-range-01/scene.xml`)으로 대조했습니다. 의존집합 파일만 복사한 디렉터리에서(VM mesh 1개는 레포 사본으로 치환, 없는 텍스처 6개는 자리표시자) `from_xml_string` 로드가 성공했습니다. 로컬 의존 37개를 하나씩 빼면 37/37 실패했고, 의존집합 밖 파일을 빼는 대조군은 성공했습니다. 즉 `xml_dependencies(base=cwd)` = 실제 로드 필요 집합입니다. 실제 canonical scene은 VM에만 있어 대조하지 못했습니다. 상세: `V7_1B_NOTES.md` 마지막 절.

## 검증

- 작업 A 단독: 208 passed. 작업 B 단독: 225 passed / 4 failed(4건 모두 `RUN_MANIFEST.json` collector.file_sha256 옛 값).
- 병합 + 보강 + manifest sha 갱신 후: `/home/ubuntu/ugrp-e1-venv/bin/python -B -m pytest tests/test_pairact_*.py -q` → *267 passed, exit 0* (A 23 + B 44 + 보강 15 신규, 실패 0).

## 남은 것

- 실행 시점 재검사(TOCTOU): gate 통과 후 실행 전까지 파일이 바뀌는 경우는 막지 못합니다. 실행 직전 gate 재실행(runner의 기존 final 검사)에 의존합니다.
- 실제 VM의 `per-world-references.json`이 이 규칙(절대경로, JSON 디렉토리 아래, symlink 없음)을 만족하는지는 VM에서 `per-world-refs`를 돌려야 확인됩니다. gcp6 runner 생성 규칙상 만족할 것으로 보지만 확인 전입니다(VM 필요).
- 판독 일치 테스트는 *이 레포의* `scripts/warp_act_backend.py`·`simalt_compiled_compat.py` 기준입니다. VM에서 실제로 import되는 teacher-source(stack 고정 SHA)의 같은 파일이 동일한지는 stack 핀 검사에 의존합니다.

### VM 필요 잔여 (v7 기준)

1. 실제 canonical scene(`/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml`)의 실행 cwd 기준 의존집합과 `assets.mesh_assets_sha256` 대조, VM mesh 파일 sha 대조. `scripts/pairact_r1_xml_load_check.py REPO_ROOT SCENE_XML`(구 `/tmp/v7-mj-check/check.py`)는 VM에서 그대로 쓸 수 있고 로드만 합니다.
2. VM teacher checkout(-c5 pin)이 canonical XML을 `from_xml_string`으로 컴파일하는지, teacher 내부에서 `chdir`하지 않는지 확인.
3. `zone_wall_divider_1_*` 큐브 텍스처 6개가 이 checkout에 없는 원인 확인(VM 소스 버전 차이로 추정).
4. v7 이전에 수집한 FROZEN_CORE probe source에는 launch 결속 파일이 없어 check-rows가 거부합니다. probe source·probe를 v7 runner로 다시 실행해야 합니다.
5. (결정 완료, 2026-10-22 강창민) 수동 teacher 직접 실행 차단은 하지 않습니다(frozen pin 변경 필요). *1안: 산출물 사용 거부만* — 결속 파일 없는 run root는 check-rows·convert-input에서 거부. 잔여 차단 아님.
