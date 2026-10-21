# 수집 사전 등록 v6 — Codex v5 재검토 대응표 (2026-10-21)

대상
- Codex v5 재검토: `~/.ductor/codex/workspace/output_to_user/reports/collect-v5-review-20261021/REPORT.md` (VERDICT HOLD). 반례 `parent-verification/replay-*/duplicate-source-proof.json`, `ledger/bin-merge-results.json`, `parent-verification/bin-stop-results.json`. 대상 `dsh/pairact-carry-r1-v5` `8a155bd5f`.
- 브랜치 `dsh/pairact-carry-r1-v6`(v5 `8a155bd5f` 위). v5·main 무변경.

상태: `COLLECT_PREREG_DRAFT.json` 무변경(*READY_FOR_REVIEW*), `RUN_MANIFEST.json` = *DRAFT_VM_FILL*(`collector.branch`, `harness/pairact_collect.py` sha256만 갱신).
모든 검증은 CPU 단위 시험·가짜 에피소드입니다. 시뮬레이터·GPU·VM 실행은 없습니다.

## 지적 ↔ 수정 대응표

| # | 지적 (Codex v5) | v6 수정 | 코드 (`harness/pairact_collect.py`, HEAD 기준) | 테스트 (`tests/test_pairact_collect_v6.py`) |
|---|---|---|---|---|
| 3 (잔여) | 검사기는 첫 `--teacher-source`/`--adapter-source`(및 자산 옵션)를, 실제 wrapper argparse는 마지막 값을 사용 → 앞 정상·뒤 `/nonexistent` 경로가 stack/verify_assets/CORE/final 통과 | 공통 판독기 `episode_option`: 옵션이 2회 이상(`--f v`·`--f=v` 혼용 포함), 축약(`--teacher-sour`, argparse가 받아주는 접두어), 값 없음이면 거부. 이 함수만 쓰도록 `episode_cmd_audit`(`--rejection-table`·`--cap-s`), `episode_assets`(`--canonical-xml`·`--per-world-model-references-v1`·`--rejection-table`), `episode_sources`(`--teacher-source`·`--adapter-source`)를 교체. `WARP_SOURCE_ROOT=` 토큰 2개 이상, `.py` 토큰 2개 이상도 거부. manifest gate는 stage(core/final)·`verify_assets` 여부와 상관없이 정적 단계에서 `episode_option_problems`를 problems에 넣고, 모호하면 자산·소스 재해시를 건너뜀(첫 값으로 검사하는 경로 자체가 없음) | `:234` `EPISODE_VALUE_FLAGS`, `:238` `episode_option`, `:255` `episode_option_problems`, `:270` `episode_cmd_audit`, `:1306` `episode_assets`, `:1461`·`:1480` gate, `:1773` `episode_sources` | `test_episode_option_refuses_what_argparse_would_resolve_differently`, `test_accepted_option_is_the_value_argparse_runs`(받아준 값 == argparse 실제 값), `test_duplicate_episode_source_is_refused_by_stack_check`(teacher·adapter, Codex 반례), `test_duplicate_warp_source_root_is_refused`, `test_duplicate_episode_option_is_refused_by_core_and_final`(6 옵션 × core/final × verify_assets 유무), `test_episode_cmd_audit_reads_the_same_single_value` |
| 신규: bin 결속 | `check_attempt_identity`가 계획 slot bin과 attempt.bin을 비교하지 않음 → 최초 merge가 B0→B5 변경을 N40·finished=true로 수용, `far_bins_settled`/`train_stop` 판정 변경 | 계획 slot과 attempt의 (seed, split, requeue, *bin*)이 모두 같아야 함. merge(원장·report 쓰기 전)·CLI report/convert-input/probe-cases·`convert_input`의 기존 호출 지점이 그대로 적용 | `:1744` `check_attempt_identity` | `test_attempt_bin_must_be_the_planned_slot_bin`, `test_first_merge_refuses_a_relabelled_bin`(K=2 완료 pilot에서 attempt 1개 bin 변경 → merge 거부, merged report 미생성) |

## 이번에 고치지 않은 것 (Codex 리스크·즉시 조치 2)

- 2b: per-world JSON이 참조하는 actuator/geometry 파일·sidecar 내용의 전이 해시 동결. 현재는 JSON 자체 sha256만 core에 결속. 별도 작업으로 남깁니다.
- XML include/compiler 경로 의미의 실제 VM canonical scene 대조, 원시 baseline/recorded rows provenance 전체 — VM 원본이 필요해 CPU 범위 밖.
- 1b: teacher 단독 실행 경로의 manifest-core 결속(정상 collector 경로는 final 검사 선행).
