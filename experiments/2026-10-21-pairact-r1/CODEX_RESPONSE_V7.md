# 수집 사전 등록 v7 — Codex v6 재검토 대응표 (2026-10-21, 초안)

대상
- Codex v6 재검토: `~/.ductor/codex/workspace/output_to_user/reports/collect-v6-review-20261021/REPORT.md`. v6 코드 수정 OK, 단 *2b가 동결 차단*(per-world 참조 파일·sidecar 내용이 core에 결속되지 않음).
- 브랜치 `dsh/pairact-carry-r1-v7`(v6 `088c88c7b` 위). v6·v5·main 무변경. 1b/XML은 `dsh/pairact-carry-r1-v7-1b`(작업 B)에서 별도 진행 후 병합 예정.

상태: `COLLECT_PREREG_DRAFT.json` 무변경(*READY_FOR_REVIEW*). `RUN_MANIFEST.json` = *DRAFT_VM_FILL*. 바뀐 것은 VM 기입 필드 1개 추가(`assets.per_world_reference_files_sha256`), `collector.branch`, `harness/pairact_collect.py`·`scripts/pairact_r1_freeze.py` sha256입니다.
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

## 1b / XML (작업 B 병합 예정)

_작업 B(`dsh/pairact-carry-r1-v7-1b`, `V7_1B_NOTES.md`) 병합 시 이 자리에 대응표를 채웁니다._

## 검증

- `/home/ubuntu/ugrp-e1-venv/bin/python -B -m pytest tests/test_pairact_*.py -q` → *208 passed*, exit 0 (v6 185 + v7 23).

## 남은 것

- 실행 시점 재검사(TOCTOU): gate 통과 후 실행 전까지 파일이 바뀌는 경우는 막지 못합니다. 실행 직전 gate 재실행(runner의 기존 final 검사)에 의존합니다.
- 실제 VM의 `per-world-references.json`이 이 규칙(절대경로, JSON 디렉토리 아래, symlink 없음)을 만족하는지는 VM에서 `per-world-refs`를 돌려야 확인됩니다. gcp6 runner 생성 규칙상 만족할 것으로 보지만 확인 전입니다(VM 필요).
- 판독 일치 테스트는 *이 레포의* `scripts/warp_act_backend.py`·`simalt_compiled_compat.py` 기준입니다. VM에서 실제로 import되는 teacher-source(stack 고정 SHA)의 같은 파일이 동일한지는 stack 핀 검사에 의존합니다.
