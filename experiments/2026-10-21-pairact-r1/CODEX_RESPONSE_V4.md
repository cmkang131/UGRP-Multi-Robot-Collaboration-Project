# 수집 사전 등록 v4 — 교차 검토(Claude) + Codex v3s 재검토 통합 대응표 (2026-10-21)

대상
- 교차 검토: `outputs/reports/claude-arch-parallel-20261019/t2-prereg-xreview.md`(HOLD, BLOCKER 3 / 권고 8 / 정보 7), 재현 테스트 `dsh/pairact-prereg-xreview` `b4202e794`(X1–X8, 이 브랜치에 cherry-pick 후 v4 기준으로 뒤집음).
- Codex: `outputs/reports/codex-astra-reviews-20261021-v3shard/SUMMARY.md`, `01-collect-prereg-v3shard-review.md`(HOLD, H1–H5 + other notes). 둘 다 `dsh/pairact-carry-r1-v3-shard` `6a68e4ca8` 대상.
- 오너 결정(2026-10-21): B1·B2 barrier, B3 validation 재큐, 권고 (i) bin_limit 지표 통일, (ii) 제한 구간을 거리 관문 분모에서 제외 + 표기, (iii) 샤드별 STOP_HOST. 나머지 권고 5건은 아래 표에 수용/보류와 사유.

상태: `COLLECT_PREREG_DRAFT.json` v4 = *READY_FOR_REVIEW*, `RUN_MANIFEST.json` = *DRAFT_VM_FILL*. 브랜치 `dsh/pairact-carry-r1-v4`(v3s `6a68e4ca8` 위). 해시·테스트 수는 맨 끝.
모든 재현 수치는 가짜 에피소드(FakeEpisode) 결과입니다. 시뮬레이터 결과나 수집 데이터가 아닙니다.

## BLOCKER (교차 검토 B1–B3, Codex H1)

| # | 지적 | v4 대응 | 코드·문서 | 테스트 |
|---|---|---|---|---|
| B1 | K>1에서 `train_closed`가 최종 판정을 고정하지 못하고, 정지·판정 클래스가 직렬과 달라짐(X1: closed STOP_DISTANCE인데 TRAIN, X7) | *정지 barrier*. 지연된 view에서 정지가 처음 보이면 `train_barrier`(hold)를 쓰고 새 batch를 계획하지 않음(`batch_skipped`, seed 소비 없음). 실행 중 batch가 모두 끝난 view(=전체 원장)에서 같은 `train_stop`을 한 번 평가: 정지면 `train_closed`(그 뒤 train 결과는 오지 않으므로 최종 데이터의 정지와 같음), 정지가 아니면 `train_barrier`(release) 뒤 직렬처럼 계속. `train_stop`은 결과의 순수 함수로 바꿈(`train_closed`를 읽지 않음). `check_train_closed`가 원장 데이터와 다른 `train_closed`를 거부. prereg `sharding.scope`·`what_changes_vs_serial`을 "정지·판정은 K와 무관하게 같은 함수, 구간 배정 순서는 달라질 수 있음"으로 고침 | `pc.stop_control`·`check_train_closed`·`train_stop`·`replay`(barrier), `runner.run_shard`·`blocked_state`, prereg `sharding.stop`·`training_decision.same_for_every_K` | X1(고정된 closed가 클래스를 못 바꿈·K=2/3에서 hold→drain→close, 직렬과 같은 STOP_TARGET·같은 판정), `test_stop_barrier_rows` |
| B2 | K>1 STOP_SEEDS가 실행 중 batch의 HOST_ERROR 재큐를 버림(X2) | barrier로 해결. STOP_SEEDS가 보이면 hold → 실행 중 batch 소진 → 전체 원장에 재큐가 남아 있으면 정지가 아니므로 release → 재큐 batch 실행 → 그 뒤 STOP_SEEDS로 고정 | 위와 같음, prereg `sharding.attempt_cap` | X2(직렬·K=2 모두 재큐 1회, N 같음, 판정 같음, barrier 행 존재) |
| B3 | validation HOST_ERROR 1개로 batch 전체 미채택 → NO_TRAIN_VALIDATION_INSUFFICIENT(X3) | 오너 결정 1: validation unclean batch에서 끝까지 판정된 world도 같은 seed로 1회 재큐(category environment, `unclean_batch_requeue`, 판정 결과는 `judged_outcome`으로 행에 보존, N에 넣지 않음). 재큐 batch도 unclean이면 그 seed는 판정하되 미채택(`success_not_admitted:batch_not_clean`), 더 재큐하지 않음. train batch는 audit 1 그대로 | `pc.validation_unclean`, `runner.ingest`, prereg `seeds.validation.rule`·`status_table.batch.validation_unclean` | X3(재큐 뒤 A 20/20, TRAIN), `test_validation_requeue_unclean_again_is_judged_not_admitted`(두 번째도 unclean → A 0, 세 번째 실행 없음), `test_train_unclean_batch_is_not_requeued` |
| H1 | STOP_HOST가 늦게 끝난 성공 batch로 풀려 host-fix 없이 validation 계획 | barrier(정지는 소진된 원장에서 한 번만) + STOP_HOST를 *순서 성질*로 정의: "batch 순서상 연속 2개 unclean"(직렬에서는 처음 성립하는 경계의 '마지막 2개'와 같음). 나중 clean batch가 지우지 못함. STOP_HOST도 `train_closed`를 쓰고, 플래그 없이는 validation을 계획하지 않음. prereg "writes nothing" 문구는 "train_closed를 쓰고 validation은 계획하지 않음"으로 고침 | `pc.host_unclean_pair`, prereg `stop_rules.list[1]`, `sharding.stop` | `test_stop_host_waits_for_the_host_fix_then_runs_validation`(v4에서 barrier 도입 직후 실패 → 순서 정의로 통과), `test_stop_host_is_a_property_of_the_ordered_results` |

## 권고 — 오너 지시 3건

| # | 지적 | v4 대응 | 코드·문서 | 테스트 |
|---|---|---|---|---|
| R1 (i) | bin_limit은 S/N, 배정은 A_b → handoff 성공 구간이 슬롯 독식(X4) | bin_limit을 A_b/N_b < 0.2로 변경(`bin_range_limit_v2`, `max_admitted_rate`). 행에 `admitted_rate`와 보고용 `success_rate` 함께 기록 | `pc.pending_bin_limits`, prereg `bins.bin_limit` | X4(B5 15/30 성공·0 채택 → 제한, 슬롯 0), 기존 `test_bin_limit_closes_hopeless_bin_and_marks_range_limited` |
| R2 (ii) | B4·B5 둘 다 제한되면 거리 관문 사실상 통과 불가(X5) | 거리 관문 v3: 한 거리 구간의 두 yaw 구간이 *모두* bin_limited이면 그 구간을 관문에서 뺌 — 그 구간 채택 시작점을 분모에서, 0.1 m 칸을 점유 검사에서 빼고, 0.8 m 초과 요구 비율을 남은 범위의 균일 분포 비율로 줄임(25% × u_open/u_full; B4+B5 제외 시 0.094). 결과에 `거리 관문 축소(제한 구간 제외: 0.9-1.2 m, 요구 비율 0.094)` 표기(decision.labels, report distance_gate.label). 한 yaw만 제한이면 제외 없음. *요구 비율 축소는 이 워커의 설계*입니다 — 분모만 빼면 B2·B3만으로 0.8 m 초과가 약 1/6이라 여전히 통과 불가라서, 25%가 균일 분포 44%의 57%라는 원래 근거를 남은 범위에 같은 비율로 적용했습니다. 오너 확인 권고 | `pc.excluded_bands`·`distance_gate`·`decision`, prereg `distance_gate.range_excluded`·`rationale` | X5(제한 전 실패, 제한 뒤 통과 + 표기, B5만 제한이면 제외 없음), `test_distance_gate_label_reaches_the_decision` |
| R3 (iii) | 샤드 하나가 계속 고장나도 STOP_HOST 미발동(X8) | `stop_rules.shard_host`: 샤드별(batch k % K) 자기 train batch가 연속 3개 unclean이거나, 6개 이상인 앞부분에서 unclean 30% 이상이면 STOP_HOST(전체 정지 — batch 소유 규칙상 한 샤드가 멈추면 뒤 batch를 계획할 수 없음). 순서 성질이라 나중 batch가 지우지 못함. K=1이면 전체가 한 샤드(직렬에도 같은 규칙). `decision.host_stop.shards`에 샤드 번호 | `pc.shard_host`, prereg `stop_rules.shard_host` | X8(샤드 1 batch 1·3·5 unclean 뒤 STOP_HOST, N<200), `test_shard_host_consecutive_and_ratio_prefix` |

## 권고 — 나머지 5건 (수용/보류 + 사유)

| # | 지적 | 판정 | 사유·조치 |
|---|---|---|---|
| R4 | bin_limit 지연 효과 비공개(X7: B5 시도 직렬 22, K=4 36) | *수용(공개)* | `sharding.what_changes_vs_serial`에 "제한될 구간이 최대 약 (K−1)×batch_size 시도를 더 받을 수 있음" 추가, RUNBOOK 1-7 보고 항목에 추가. 지연 자체는 샤딩의 성질이라 유지. X7이 고정 |
| R5 | K>1에서 train 실행 중 validation 계획(X6) | *수용(해결)* | barrier 때문에 validation은 `train_closed` 뒤, train batch가 실행 중이 아닐 때만 계획됨. prereg `seeds.validation.rule`·`sharding.stop`(3). X6이 뒤집혀 통과 |
| R6 | K가 FROZEN_CORE에 고정되는데 K 측정은 동결 뒤 | *수용* | RUNBOOK 1-2b 신설: K 경합 측정을 *FROZEN_CORE 전* measurement 모드(pilot seed 8343000–019, 프로세스별 run root, 수율 미보고)로 하고 결과로 `sharding.count`를 정함. 이 측정은 "결정성·경합 측정용"이고 K>1 적응 경로는 가짜 테스트로만 검증됐다고 표기(prereg `known_blockers`). 학습 run root는 다른 K로 다시 열지 않고, 호스트가 K를 못 버티면 STOP_HOST로 멈춤. 같은 train seed 재수집은 새 prereg 개정 + 오너 결정 없이는 하지 않음(prereg `sharding.K`, manifest `sharding.rule`) |
| R7 | merge seed 중복 검사 범위가 좁음, 잘못된 방향 rsync 미검출(Codex H5②와 같음) | *수용* | merge가 `check_seed_history`로 split별 "새 seed는 1회, 재큐는 앞선 환경 실패 뒤 1회"를 전역 검사. `merge.json`에 샤드 원장 바이트 수를 남기고 다음 merge에서 각 샤드 원장이 그 바이트의 append-only 연장인지(sha256 prefix) 확인 |
| R8 | tier 2/3이 yaw 범위를 안 봄 | *보류* | 오너 지시 범위 밖의 새 판정 규칙(yaw 한쪽 3구간 부족 시 NO_TRAIN)이라 넣지 않음. 현재도 구간별 A_b·`데이터 범위 제한(구간 부족: …)` 표기가 facing/away 구간을 이름으로 드러냄. P5 heldout 구간별 보고는 EVAL prereg 개정 때 다룰 항목으로 남김(오너 결정 필요 시 v5) |

## Codex v3s 재검토 H2–H5 · other notes

| # | 지적 | 판정·대응 | 코드 | 테스트 |
|---|---|---|---|---|
| H2 | 미완료 샤드 결과를 학습 데이터로 확정 가능 | *수용*. `convert-input`이 `merged_meta(require_finished=True)`: 샤드 run root 자체 거부, merged 원장 sha256 ≠ `merge.json`이면 거부, `finished` false 또는 `running` 남으면 거부 | `runner.merged_meta`, CLI convert-input | `test_merged_meta_needs_a_finished_matching_merge` |
| H3 | RUNBOOK 순서대로 report를 돌리면 sharding 표시가 사라짐 | *수용*. CLI `report`가 merged root에서 `merge.json`의 sharding 블록을 유지. 샤드 run root에 report를 돌리면 거부 | CLI report | `test_cli_shard_needs_vm_and_merge_writes_the_merged_root`(추가 assert) |
| H4 | generator admission 경로가 manifest -c5 pin에 결속되지 않음 | *수용(부분)*. FROZEN_CORE·FROZEN 단계 collect는 시작 전에 `--dependency-root`(teacher)·`--adapter-root`·`--frozen-root`(root)의 git HEAD == `stack.<role>.sha`이고 추적 파일 clean이어야 함 | `pc.check_stack_heads`, CLI collect | `test_stack_heads_must_match_the_manifest_pins` |
| H4' | 실제 admission 연동 테스트가 c2 스택 | *보류*. `pinned_stack` fixture를 c5로 바꾸려면 -c5 세 브랜치를 sparse clone해 테스트해야 하고 이 워커 범위(수집 prereg 개정)를 넘음. 대신 위 HEAD 검사가 실행 시점에 c5를 강제. DeepSeek가 RUNBOOK 1-0의 -c5 테스트(88/9/12)를 돌릴 때 확인 [확인 필요] |
| H5① | convert-input이 raw 존재를 확인하지 않고 dangling symlink 생성 | *수용*. 채택 world raw 디렉터리가 하나라도 없으면 출력 디렉터리를 만들기 전에 거부 | `pc.convert_input` | `test_convert_input_refuses_missing_world_raw` |
| H5② | merge가 완료 batch 사이 같은 fresh seed 재사용을 놓침 | R7과 같음 | `pc.check_seed_history` | `test_seed_history_audit`, `test_merge_refuses_a_rewritten_shard_ledger` |
| b) | K=1 원장이 직렬과 바이트 동일은 아님(header `shard` 키, `batch_dir`) | *정보 수용*. prereg는 "row for row"(plan/result 행)만 주장, header는 `shard` 키만 다름을 테스트가 고정(`test_one_shard_is_the_serial_ledger`). v4에서 `train_barrier`·`train_closed`도 샤드 전용 행 | — | 기존 테스트 |
| note | RUNBOOK 1-6c `s_wt × P` 기준이 식과 불일치 | *수용*. 처리량 `P ÷ s_wt(P)` 기준으로 고침(`K÷s_wt(K) > (K−1)÷s_wt(K−1)`일 때만 K 증가) | RUNBOOK 1-6c·1-2b | — |
| B3(v3) | `smoke.video_sha256` world 개별 삭제 통과 | *보류*. 이번 개정 범위(정지·판정 규칙) 밖. FROZEN_CORE 전 별도 수정 항목으로 남김 | — | — |

## 교차 검토 정보 항목

- I2(pilot -c4): 오너 지시대로 prereg `reporting.pilot`과 RUNBOOK 1-2에 "pilot 26/40은 -c4 결과라 -c5 수율 근거로 쓰지 않음, 보고에 purpose와 스택 병기"를 넣었습니다.
- I4(STOP_HOST가 STOP_TARGET보다 먼저): 순서는 그대로 둡니다(판정 클래스 같음, 의도).
- I5·I7: 변경 없음. I5의 validation 경로 위험은 B3 재큐로 줄었습니다(exit 파일 누락으로 unclean이 되어도 1회 재큐).

## 오너 결정 D-v4-1–D-v4-4 (2026-10-21, 동결 전)

| # | 결정 | 반영 | 코드·문서 | 테스트 |
|---|---|---|---|---|
| D-v4-1 | STOP_DISTANCE는 원거리 구간(B4·B5)이 모두 A_b≥20이거나 bin_limited일 때만 평가. 그 전에는 거리 관문을 정지 사유로 쓰지 않음(최종 집합의 거리 관문 판정은 그대로). 동결 전 변경이라 사후 변경 아님. 그래도 K=4가 직렬과 다르면 사례 공개 + K 상한 3 | 구현. *X7에서 K=4가 여전히 달라* 상한 3을 넣음: manifest gate(`sharding_problems`)와 CLI `--shard`가 K>3 거부, RUN_MANIFEST 초안 `count` 3(gcp6 [0,1,2]), 두 VM 변형은 합쳐 3(gcp6 [0,1] / gcp2 [2]). 사례는 prereg `sharding.K`에 그대로 공개 | `pc.far_bins`·`far_bins_settled`·`train_stop`·`MAX_SHARDS`, runner CLI, prereg `owner_decisions_v4`·`stop_rules.list[2]`·`distance_gate.when`·`sharding.K_max`·`sharding.K`, RUNBOOK 상단·1-2b·1-3·1-6a/b/c | X7(직렬·K=2·K=3 같은 클래스, K=4 공개 사례), `test_distance_gate_uses_admitted_starts_and_stops`(미정착이면 정지 아님, 정착 뒤 정지), `test_manifest_sharding_binds_count_vm_and_per_vm_recording_check`(K=4 거부), `test_cli_shard_needs_vm_and_merge_writes_the_merged_root`(`--shard 0/4` 거부), `test_draft_manifest_and_prereg_carry_the_sharding_rule` |
| D-v4-2 | 거리 관문 요구 비율 0.25×u_open/u_full 승인 | prereg `distance_gate.required_share_formula`에 식과 예(B4·B5 제외 → 0.094) 기입 | prereg | X5 |
| D-v4-3 | STOP_HOST "batch 순서상 연속 2개 unclean" 승인 | 변경 없음(v4 그대로) | — | `test_stop_host_is_a_property_of_the_ordered_results` |
| D-v4-4 | 보류 3건 유지 | R8(yaw 판정 규칙: 오너 지시 범위 밖 새 판정 규칙), H4'(c5 실제 admission fixture: -c5 세 브랜치 sparse clone 필요, 실행 시점 HEAD 검사로 대체), v3 B3(`smoke.video_sha256` world 개별 삭제 통과: 정지·판정 개정 범위 밖, FROZEN_CORE 전 별도 수정 항목) — 사유는 위 표와 같음 | — | — |

### X7 K별 결과 (D-v4-1 적용 뒤, 가짜 에피소드)

| 실행 | 정지 | 판정 | A | N | B5 시도 |
|---|---|---|---|---|---|
| 직렬 | STOP_TARGET | NO_TRAIN_VALIDATION_INSUFFICIENT | 204 | 480 | 22 |
| K=2 | STOP_TARGET | NO_TRAIN_VALIDATION_INSUFFICIENT | 218 | 420 | 30 |
| K=3 | STOP_TARGET | NO_TRAIN_VALIDATION_INSUFFICIENT | 235 | 460 | 38 |
| K=4 | STOP_DISTANCE | NO_TRAIN_DISTANCE_GATE | 181 | 380 | 36 |

- 판정이 NO_TRAIN_VALIDATION_INSUFFICIENT인 것은 이 가짜의 validation seed 결과 때문이고(직렬도 같음), 비교 대상은 클래스 일치 여부입니다. 스케줄 난수 1·2·3에서 같은 값이 나왔습니다.
- K=4가 다른 원인: 지연된 bin_limit이 B2(2/22)와 B4(2/21)를 닫았습니다. 그래서 원거리 구간(B4·B5)이 정착(제한)되어 거리 관문이 평가되었고, B2·B3 시작점만으로는 0.8 m 초과가 5.7%라 축소 요구 9.4%에 못 미쳤습니다. 이 가짜는 성공이 `seed % 3`에 묶여 있어 batch 안 구간 배치와 주기적으로 겹칩니다. 비주기 가짜(구간별 성공률 0.6/0.5/0.45/0.4/0.35/0)에서는 K=2·3·4 모두 직렬과 같은 TRAIN_DATA_RANGE_LIMITED였습니다(정보, 테스트 미고정).

## 남은 위험

1. K≤3에서도 구간 배정 순서와 소진 원장(N·A·구간별 수)은 직렬과 다를 수 있습니다(공개). 판정 함수는 같고, 교차 검토 가짜에서는 K=2·3의 판정 클래스가 직렬과 같았습니다. 실제 수율에서의 일치는 보장하지 않습니다.
2. 지연된 bin_limit이 운 나쁜 초기 결과로 구간을 닫는 효과는 K가 클수록 큽니다(X7 K=4). K 상한 3은 이 효과를 줄일 뿐 없애지는 않습니다.
3. 거리 관문 요구 비율 축소식은 D-v4-2로 승인되었습니다.

## 해시·테스트 (D-v4-1–4 반영 커밋 `e34bc69ec` 기준; 이 기입은 다음 문서 커밋)

- `COLLECT_PREREG_DRAFT.json` 파일 sha256 `cf045a9f1440f63022dc06539a7988e7beb905739307ed979a6e3d4b68b609e5`, status READY_FOR_REVIEW
- prereg core(status 제외) `7bce6856288a5cc55a77be14ef4abb84b5678716f57ff5fe01a2b510cf09def1`
- `core_sha256`(prereg + DRAFT manifest, 참고값 — VM 기입 뒤 FROZEN_CORE에서 바뀜) `5d7dfec2aa5c4559dabef73283d97706db4ddbeb4d3cd996700ab40fcea257df`
- `RUN_MANIFEST.json` 파일 sha256 `60ea2e63a9a4c04918201a5e335443ab434c5adb24da1717cee388ed0652abaa`
- 테스트(Oracle `/home/ubuntu/ugrp-e1-venv`, 가짜 에피소드·순수 함수만): collect 89 + shard 17 + xreview 8(X1–X8) + v4 11 + r1 14 = *139 passed, skip 0*(108 s). 시뮬레이터·GPU 실행 없음.
- 이전 v4 커밋 `192da476d` 값(prereg `fa337d70…`, core `b271f16b…`)은 D-v4-1–4 이전 것이라 대체되었습니다.
