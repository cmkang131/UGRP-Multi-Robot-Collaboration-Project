# b-v6h1 봉인 절차와 재현 경계 (2026-10-01)

조정자의 재개 결정에 따른 **분석 봉인**이다. 실행 revision v6h / bundle `zone-pair-v83-carry-door-gain` / workflow 2.16.0을 유지한다. `analysis/seal_v2/prereg_v6h.json`의 두 pin 집합과 [PREREG_DRAFT.md](PREREG_DRAFT.md)의 공개 사항이 기준이다. PR #292는 **봉인 — 독립 검토 필요**, 병합하지 않는다.

## P1 수정에 따른 봉인 revision v2

기존 봉인 `266118d2`의 `prereg_v6h.json`과 `analysis/seal/` 바이트는 보존한다. 리뷰 `77b6b94c`의 P1은 분석 시작 전에 바뀐 raw가 당시 inventory와 대조되지 않는 문제다. 새 분석 봉인은 `analysis/seal_v2/prereg_v6h.json`에 별도 pin 집합으로 기록한다. 실행 274파일과 실행 SHA `4c6b439f`는 그대로다.

새 적용기는 봉인된 RUN_MANIFEST의 inventory SHA-256을 확인한 뒤 실제 소비하는 모든 입력을 `EvidenceReader`에서 기록 당시 해시와 비교한다. 목록 누락·미등록 입력·해시 불일치·분석 중 변경은 `INVALID` / `NOT_ANALYSED`와 이유만 남기고 gate 판정을 만들지 않는다. 분류 계산·recorder·48/60·B·안전 기준은 바꾸지 않는다. 새 pin 집합은 입력 경계와 최신 main 병합 차이를 모두 공개하며 독립 재검토가 필요하다.

## 실행 소스와 분석 소스

- EXECUTION은 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`의 274파일과 EXTRA 6개다. 각각 Git blob SHA + SHA-256을 저장하고 `git show 4c6b439f:<path>`로 검증한다. 봉인 작업 트리의 파일로 원본 pin을 다시 계산하지 않는다.
- ANALYSIS는 최종 classifier/registered-recorder·blinded-run-manifest adapter/CLASSIFY_NOTES/분석 gate/의존성과 등록 metadata의 봉인 커밋 바이트다. 겹치는 경로는 별도 해시로 구분한다. 봉인 커밋은 `--seal-commit`으로 전달해 자기 커밋 해시의 순환을 피한다.
- 재실행하려면 `4c6b439f`를 checkout한다. 이 분석 봉인은 새 실행 권한·실행 전 등록 receipt를 만들지 않는다. 실행 당시와 현재 모두 GT→학생 보정, weld, 모델 호출을 새로 허용하지 않는다.
- `probe_all_sweeps`의 σ 1/1 범위와 `not approach`의 yaw/p2f 범위는 동결된 원본 제어기 그대로다. 든 쌍의 신뢰할 만한 정지 감지는 없다.

## 기록이 봉인보다 앞섰다는 공개

커밋 메타데이터 `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`는 72개 case가 **봉인 전에 블라인드로 기록**되었다고 명시한다. source는 `4c6b439f`, 얇은 driver가 같은 `scripts.run_pair_stage_probes` worker를 호출했으며 prereg가 없어서 `--prereg` 없이 **unsealed_stage_probe admission**을 썼다. 이 차이를 삭제하거나 실행 전 봉인으로 표현하지 않는다.

builder의 `build()['cases']`에서 `registration_run_id`만 뺀 바이트는 커밋된 plan의 cases 배열과 같다. 원래 builder와 plan 사이에는 `chain_stop_leg` 키 순서만 달랐고 봉인 builder에서 그 순서를 맞춘다. 필드 값·placement/prior·옵션은 변하지 않는다. 검증기는 정렬·반올림·추가 필드 제거 없이 plan의 literal JSON 배열을 비교한다.

- RUN_MANIFEST.json SHA-256: `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210`.
- plan.json SHA-256: `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026`.
- cases.jsonl SHA-256: `8e7837cbc948abcd7a29a6b81272870ec7ab716c1aba87f018cd3aca655d1836`.
- driver SHA-256: `7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56`.

위 첫 두 해시는 커밋 blob에서 직접 재계산했다. 뒤 두 해시는 manifest 진술이며 raw/driver 본문을 여기서 읽거나 검증하지 않았다. 허용된 메타데이터 3개 이외에 블라인드 raw의 목록·내용을 열지 않고 outcome을 계산/확인하지 않았다. 분류기의 마지막 버전은 블라인드 결과 없이 reviews 299–299g를 거쳐 `1f0e4eb5`에서 고정됐다.

조정자가 승인한 main 4파일(`zone_main_budget.py`, `zone_study_llm_driver.py`, `zone_study_llm_transport.py`, `agent_lock.py`)은 작업 트리에서 main 바이트를 쓴다. 코호트 모델 호출은 0이며 lock은 호스트 도구다. 원본 EXECUTION 검증은 4c6b439f에서 하므로 바뀐 작업 트리를 코호트 소스로 오인하지 않는다. 등록 builder·두 문서·CURRENT_REVISION도 허용된 metadata 변경이다. 모든 차이와 원본/봉인 해시는 prereg의 notes에 남긴다.

## 오프라인 검증 명령 (raw 접근 없음)

다른 작업의 공용 `core.worktree` 설정에 영향을 받지 않도록 이 worktree 경로를 명시한다. 공용 host lock은 획득하지 않는다.

```sh
export GIT_WORK_TREE=/Users/changmin/projects/ugrp-wt/v6h-register
V6H_PYTHON=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$V6H_PYTHON -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --verify
$V6H_PYTHON -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --verify-seal --seal-revision v2 --seal-commit "$V6H_SEAL_V2_COMMIT"
$V6H_PYTHON -m pytest -q -p tests.pose_provider_no_physics tests/test_zone_pair_v6h_seal.py tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py tests/test_zone_pair_v6h.py tests/test_zone_pair_v6h_review_delta.py tests/test_v6h_classify_placements.py tests/test_v6h_classifier_properties.py tests/test_v6h_recorder_contract.py tests/test_v6h_blinded_run_manifest.py
```

`V6H_SEAL_V2_COMMIT`은 PR의 실제 봉인 커밋 SHA다. 커밋 전에는 `--seal-commit`을 빼고 분석 작업 트리 pin을 검사하며, 커밋 뒤에는 반드시 위처럼 Git blob 감사를 한다. `--seal`은 최초 생성에만 쓰고 기존 파일이 있으면 거절한다. 수정이 필요하면 기존 봉인을 덮어쓰지 않고 새 revision으로 등록한다.

## 독립 검토·개봉 결정 뒤 실행할 분석 명령 (이번 작업에서는 실행하지 않음)

먼저 봉인 커밋을 checkout한 별도 작업 경로에서 위 Git blob 감사로 실행/분석 두 집합을 확인한다. 아래 출력 경로는 반드시 새 이름이어야 한다. raw는 읽기 전용이다.

```sh
$V6H_PYTHON -m experiments.2026-09-30-pair-v6h-carry.analysis.apply_sealed_analysis \
  --seal-commit "$V6H_SEAL_V2_COMMIT" \
  --prereg experiments/2026-09-30-pair-v6h-carry/analysis/seal_v2/prereg_v6h.json \
  --raw /Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930 \
  --output /Users/changmin/projects/ugrp/outputs/v6h1-sealed-analysis-v2-NEW
```

이 명령은 내부에서 고정된 `classify_placements.analyse`를 `--recorded-run-manifest`와 그 고정 해시로 적용한다. 실행이 미봉인이었다는 classifier 원보고서를 보존한 뒤, 별도 봉인 gate로 941×60의 48/60·전체 안전·B를 판정하고 943×12를 민감도로 구분한다. HOST_ERROR/ENOSPC/누락은 UNCLASSIFIED이며 분모를 줄이지 않고 통과를 막는다. 원본 분류기는 `--sealed-manifest`와 recorded-run manifest의 혼용을 계속 거절한다.

새 결과의 native TensorBoard 변환·데이터 로딩·뷰 검증은 개봉 뒤 결과 전달 작업에서 한다. 이번 봉인은 raw 분석·물리·렌더·모델 호출·TensorBoard 결과 검증이 아니다.


추가 공개: 병합한 main `f5cd3a2b`에는 기존 4개 외에 `harness/vision_loc_protocol.py`(응답 seq int 검사/bool 거절, `b38c1d59`)와 `sim/workflow_manager.py`(표준 study 실행 전 admission 검사)도 바뀌었다. 최종 작업 트리에서는 총 6개의 main 변경을 구분해 공개한다. 재개 결정 A(1)의 원본 커밋 검증과 B의 정상 main 병합에 따라 main 바이트를 반영했다. 원래 4개 목록에 들어 있던 변경으로 표현하지 않으며, 실행 274파일은 계속 4c6b439f에서 검증한다.

## 참고 자료

[ICH E9(R1)](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf)의 주 분석/민감도 사전 명시와 [CONSORT 2025 item 3](https://www.consort-spirit.org/item3-accesstotrialprotocol)의 분석계획 확정·버전 공개 원칙을 참고했다. 로봇 연구에 대한 유추이며, 기록 후 봉인을 실행 전 등록으로 소급하는 근거로 쓰지 않는다.
