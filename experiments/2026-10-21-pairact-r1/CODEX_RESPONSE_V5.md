# 수집 사전 등록 v5 — Codex v4 재검토 대응표 (2026-10-21)

대상
- Codex v4 재검토(13:31Z): `~/.ductor/codex/workspace/output_to_user/reports/collect-v4-review-20261021/REPORT.md`, 반례 코드 `parent-verification/admission-probe.py`·`sharding-probe.py`, `admission/verify.py`, `sharding/probe.py`. 대상 `dsh/pairact-carry-r1-v4` `0a6c227fd`.
- 추가: gcp2 샤드 smoke(2026-10-21)의 collector `worlds[].carry_success` 부재 → 25 record_error (`outputs/e2e18-admin/pairact-shardsmoke-gcp2-20261021/`).

상태: `COLLECT_PREREG_DRAFT.json` = *READY_FOR_REVIEW*(v5 문구만), `RUN_MANIFEST.json` = *DRAFT_VM_FILL*. 브랜치 `dsh/pairact-carry-r1-v5`(v4 `0a6c227fd` 위).
모든 검증은 CPU 가짜 에피소드·합성 파일입니다. 시뮬레이터·GPU·VM 실행은 없습니다.

## 지적 ↔ 수정 대응표

| # | 지적 (Codex v4) | v5 수정 | 코드 (파일:라인, HEAD 기준) | 테스트 (`tests/test_pairact_collect_v5.py`) | 커밋 |
|---|---|---|---|---|---|
| 1 | 다른 core에서 만든 녹화 check가 FROZEN 통과 (check-rows `core_sha256` 0*64) | check-rows CLI가 probe source 원장(purpose·core·첫 채택 seed)·`probe-cases.json` sha256을 기록. final gate가 check-rows `core_sha256`·`probe_source.core_sha256` == 현재 core, `probe_cases_sha256` == 옆 파일, probe source seed == probe-cases == baseline == recorded, recording-check `indices`/`N` 일치, case candidate `pairact_p3_collect`를 확인. freeze final은 각 `--vm-recording-dir`도 같은 검사. 거부 시 파일 미기록 | `harness/pairact_collect.py:998` `check_rows_binding`, `:1012` `recording_binding_problems`, `:1467` final gate 호출; `scripts/run_pairact_collect.py:682` check-rows; `scripts/pairact_r1_freeze.py:66` VM 디렉터리 | `test_final_refuses_recording_evidence_of_another_core`, `test_recording_evidence_chain_probe_source_cases_rows_check`(6 case), `test_freeze_final_refuses_stale_primary_and_vm_recording`, `test_check_rows_binding_reads_the_probe_source_ledger` | `fb334dab0` |
| 2 | XML 의존 자산 미동결 (actual.obj 누락 + decoy.obj 등록 → 통과, 변경 뒤에도 통과) | `xml_dependencies`: include(재귀·순환 거부), mesh/skin/hfield(meshdir), texture·cube 6면(texturedir), `<model file>`; assetdir·strippath 반영, 절대경로. `verify_assets`에서 `assets.mesh_assets_sha256` 키 집합 == 참조 집합(누락·무관 등록 모두 거부) + 파싱 불가 거부 + 기존 파일별 재해시. 등록값은 `pairact_r1_freeze.py xml-assets --canonical-xml XML` 출력 | `harness/pairact_collect.py:1286` `xml_dependencies`, `:1325` `xml_asset_problems`, `:1451` 호출; `scripts/pairact_r1_freeze.py:85` `xml_assets` | `test_decoy_mesh_registration_is_refused`, `test_xml_dependencies_follow_include_compiler_dirs_and_cube_textures`, `test_unregistered_include_and_unparsable_xml_are_refused`, `test_freeze_xml_assets_prints_the_registration` | `623d4d65f` |
| 3 | 검사한 stack 경로와 episode 템플릿 소스 경로가 따로 놀아도 통과 (/nonexistent) | `check_stack_heads`가 `command.episode_template`의 `--teacher-source`·`--adapter-source`와 root(`WARP_SOURCE_ROOT`: 템플릿 토큰 > 환경, 또는 wrapper .py가 root 안)를 읽어 존재·realpath 동일을 요구한 뒤 기존 HEAD pin·clean 검사. manifest gate(`verify_assets`, VM)는 템플릿 소스가 존재하고 stack pin·clean인지 검사. probe-episode도 stack 검사 | `harness/pairact_collect.py:1730` `episode_sources`, `:1751` `stack_pin_problems`, `:1763` `episode_source_problems`, `:1780` `check_stack_heads`, `:1448` gate 호출; `scripts/run_pairact_collect.py:658`(probe-episode), `:724`(collect) | `test_correct_pins_with_other_episode_paths_are_refused`, `test_episode_root_source_is_the_checked_root`, `test_manifest_gate_checks_the_episode_sources_on_the_vm`; 기존 `test_stack_heads_must_match_the_manifest_pins`·`test_verify_assets_rehashes_episode_files`를 실제 경로로 갱신 | `aa6f92b33` |
| 4 | 불완전 꼬리 복구 뒤 재merge가 append-only로 거부, 개행 없는 유효 JSON은 reader에 보이고 repair에선 삭제 | `committed_bytes`: 마지막 newline까지가 확정 prefix. `read_ledger`(=`parse_ledger(committed_bytes)`)는 개행 없는 꼬리를 유효 JSON이라도 무시, `repair_ledger`는 그 꼬리만 자름, merge는 같은 바이트로 view를 만들고 그 길이·sha256을 봉인(`ledger_seal: committed_prefix_v1`) | `harness/pairact_collect.py:182` `committed_bytes`, `:193` `read_ledger`, `:197` `parse_ledger`, `:209` `repair_ledger`; `scripts/run_pairact_collect.py:439–481` merge | `test_repaired_torn_tail_then_append_merges_again`(header+8바이트 → merge → repair → plan append → 재merge 성공), `test_committed_prefix_change_is_still_refused`(확정 행 변경·단축 거부), `test_valid_json_without_newline_is_uncommitted_for_reader_and_repair` | `4e45358d0` |
| 5 | 완료 attempt 중복이 merge에서 N=41로 집계 | `check_attempt_identity`: attempt마다 (batch, slot) 1회·그 계획 slot의 seed/split/requeue와 일치, (split, seed, requeue) 1회. merge(원장·report 쓰기 전), CLI report/convert-input/probe-cases, `convert_input`에서 검사 | `harness/pairact_collect.py:1703` `check_attempt_identity`, `:1062` convert_input; `scripts/run_pairact_collect.py:471` merge, `:600` CLI | `test_duplicate_completed_attempt_is_refused_by_merge`(K=2 완료 pilot N=40 → 중복 append → 거부, 이전 report 유지), `test_attempt_identity_audit`, `test_convert_input_refuses_a_duplicated_attempt` | `d3f33f0e8` |
| 6 | (smoke) `worlds[].carry_success` 부재 → 25 record_error, `ks.admitted=16` vs `A.text 0/7` | runner: summary world에 키가 없으면 `result.carry_eval.success`가 단일 진실, 키가 있고 다르면 record_error 유지. `_record_error`가 판정된 성공에 적용될 때 `success/admitted`를 False로(16 admitted의 원인). 레포 gcp6 wrapper가 -c5 root runner처럼 `carry_success`·`carry_failure` 기록 | `scripts/run_pairact_collect.py:104`; `harness/pairact_collect.py:720`; `experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py:336–337` | `test_smoke_summary_without_carry_success_is_not_a_record_error`(실제 smoke summary world + 같은 seed gcp6 raw fixture `tests/fixtures/pairact_c5_shardsmoke_20261021/`), `test_summary_carry_success_that_disagrees_is_still_a_record_error`, `test_gcp6_wrapper_summary_writes_carry_success_like_the_c5_root`, `test_collect_without_summary_carry_success_admits_from_the_result` | `052e19df9` |

문서: `COLLECT_PREREG_DRAFT.json`(revision v5, `status_table.required.summary_world`, `sharding.merge`, changelog), `RUNBOOK.md`(v5 요약, WARP_SOURCE_ROOT·wrapper 갱신, xml-assets, probe-episode stack 인자, 결속 설명) — `9a7306268`. 커밋마다 `RUN_MANIFEST.json` `collector.file_sha256`을 갱신했습니다(단, 첫 커밋 `052e19df9`은 갱신 전이라 그 커밋 단독으로는 shard freeze 테스트 1건이 실패하고 `4e45358d0`에서 맞춰짐).

## 지적 6 근본 원인

- 실제 summary를 쓴 것은 -c5 root runner가 아니라 `beamact5-tools/run_warp_flow_teacher_gcp6.py`(레포 사본 `experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py`, root `3170d909` 기반 포크)입니다. -c5 root runner(`a93082c3` `scripts/run_warp_flow_teacher.py:350–355`)는 `carry_success`를 쓰지만 이 포크는 쓰지 않았습니다. smoke summary `worlds[0]` 키: `world, seed, candidate, success, sim_s, cap_end, input_audit, raw`.
- collector `judge_world`가 `w.get('carry_success')`(None) != `carry_eval.success`(bool)를 불일치로 보고 grasp 성공 25건(carry 성공 16·실패 9)을 모두 record_error로 닫았습니다. 원장 집계 `('record_error', success True) 16, ('record_error', success False) 9`.
- `_record_error`가 이미 판정된 성공 dict 위에 category/outcome만 바꿔 `success/admitted=True`가 남았고, 그래서 KS `admitted=16`과 A.text(record_error 제외) "0/7"이 어긋났습니다.
- VM 조치: VM의 `/home/ugrp/ugrp-sim/src/beamact5-tools/run_warp_flow_teacher_gcp6.py`를 이 브랜치 파일로 갱신하고 `assets.wrapper_sha256`을 새 파일로 채워야 합니다(VM 사본 경로 확인 필요). collector 수정만으로도 키 부재는 record_error가 아니게 됩니다.

## Codex 반례 재생 (v5 HEAD, CPU)

Codex `admission-probe.py`·`sharding-probe.py`의 반례를 v5 경로로 옮긴 스크립트(`~/.ductor/claude/workspace/output_to_user/reports/pairact-r1-v5-20261021/codex_v4_replay.py`, exit 0, `replay.log`):
- R2+R3(core, `--verify-assets`): `episode --teacher-source /nonexistent/review-teacher does not exist; ... misses files the canonical XML references: .../actual.obj` → 거부.
- R1(final, 0*64 check-rows): `recording evidence of vm gcp2: check-rows.json core_sha256 0000… != current core …` → 거부(주 디렉터리 경로는 테스트가 확인).
- R3(stack, 정확한 pin + /nonexistent 소스): `episode teacher source /nonexistent/review-teacher (--teacher-source) does not exist` → 거부.
- R4: 8바이트 복구 뒤 재merge 성공, 개행 없는 유효 행 rows_seen 1 → repair 뒤 1.
- R5: Codex K4 fixture에서 N=40 → 중복 append → `duplicate attempt` 거부.
- 녹화 반례 중 teacher `-c5` admission 재현(`/home/ubuntu/UGRP-wt/p2c5`)은 해당 worktree가 이 호스트에 없어 재실행하지 않았습니다. collector 쪽 결속은 위 테스트가 다룹니다.

## 남은 위험

1. XML 경로 규칙(hfield·skin은 meshdir, include는 주 모델 디렉터리)은 MuJoCo 문서 규칙을 코드로 옮긴 것이며 실제 `canonical-scene.xml`로 확인하지 않았습니다. VM에서 `xml-assets` 출력이 MuJoCo가 실제로 연 파일과 같은지 1회 대조를 권고합니다. per-world references JSON이 가리키는 파일은 이 검사 범위 밖입니다.
2. root 결속은 collect 시점의 `WARP_SOURCE_ROOT`(또는 템플릿 토큰)에 기댑니다. 환경이 episode 실행과 같다는 것은 runner가 같은 `os.environ`에서 env를 만들기 때문이며, 템플릿에 `WARP_SOURCE_ROOT=`를 넣으면 manifest 해시에도 묶입니다(권고).
3. `recording-check.json`은 teacher 함수 출력이라 collector는 indices·N만 대조합니다. 파일 위조는 범위 밖이며 다른 core 증거의 재사용만 막습니다.

## 해시·테스트 (구현 HEAD `9a7306268`, 이 문서 커밋은 그 위 1개)

- `COLLECT_PREREG_DRAFT.json` 파일 sha256 `e44b090625f718b7b9257ce241cf6d51fe759b565a9304f29f9ad8d2f89c4fbe`, status READY_FOR_REVIEW (v4 `cf045a9f…`에서 문구 4곳 변경)
- prereg core(status 제외) `c5299c982b61c365e228d5774023cd269c8165c1cd5b6b02f091b1d424d3b64f`
- `core_sha256`(prereg + DRAFT manifest, 참고값) `32e458c1019976677b78643d33852d640eca99391e8bf01b125d6da5156321b8`
- `RUN_MANIFEST.json` 파일 sha256 `206fc79f296ee26cf71fec5ba79e51eed4d2e5cea04deab40ae44eed02b1b0cc`
- pairact 6파일(Oracle `/home/ubuntu/ugrp-e1-venv`): collect 89 + shard 17 + xreview 8 + v4 11 + v5 26 + r1 14 = *165 passed*, exit 0 (기준 v4 139 passed).
- 전체 `tests/`: 수집 단계에서 v4 `0a6c227fd`와 v5 모두 같은 360 수집 오류(`ModuleNotFoundError: tests.test_zone_study_integration` 등, pairact와 무관한 기존 문제), 수집 수 v4 11334 → v5 11360(+26 = v5 테스트). pairact 외 11k 테스트 전체 실행은 하지 않음.
