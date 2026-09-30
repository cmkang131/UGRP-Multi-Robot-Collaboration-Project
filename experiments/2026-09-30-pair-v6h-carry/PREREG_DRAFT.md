# b-v6h1 분석 사전 등록 봉인 — 독립 검토 필요 (2026-10-01)

조정자(등록 소유자)의 2026-10-01 재개 결정으로 `prereg_v6h.json`의 `state=sealed`, `sealed=true`, `CURRENT_REVISION=v6h`를 고정한다. 번들은 `zone-pair-v83-carry-door-gain`(v83), workflow는 2.16.0이다. 이 파일명은 기존 링크를 보존한다. PR #292는 독립 검토 전이며 병합하지 않는다. **코호트 기록 뒤, 결과를 보지 않은 상태에서 분석을 봉인했다. 실행 전에 봉인한 것으로 소급 표시하지 않는다.**

## 고정한 질문과 판정

teacher가 한 번 만든 시작 자세에서 L0→내려놓기→재파지→L1의 연쇄를 검사한다. 자기 RGB·공용 top RGB·자기 발행 명령·허용된 정적 지도에 의한 제어이며 평가 정답은 제어 입력이 아니다. SIM, weld OFF, 모델 호출 0, floor_light_v1, PF/contact ON, L1 정지, 800 SIM초/1500 wall초, workers 4/OMP 1이다. E2E·실물·정지 대응 성공으로 확대하지 않는다.

- **A:** seed 941의 고정 C01–C60 60곳 중 `PASS_CLEAN` + `PASS_CONTACT_RECOVERED` ≥48곳. seed 943의 **첫 12곳**은 민감도 분석이며 주 분모에 합치지 않는다. 관측된 고정 코호트 80% 기준이지 모집단 성공률 ≥80%의 증명이 아니다. 주 시드가 모두 분류된 경우에만 배치 단위 Wilson 95% 구간을 보고한다.
- **안전:** teacher 준비를 포함한 연쇄 전체의 알려진 penetration >5 mm 또는 tilt >15°는 먼저 `FAIL_HARD_LIMIT`로 보존한다. 주·보조 시드와 모든 시도를 합쳐 하드 위반 0건을 요구한다. 관측하지 않은 접촉 cadence나 coverage를 소급 생성하지 않는다.
- **B:** 도달한 주 시드 L0/L1 끝점에서 x/y/yaw 각각 ±2σ 포함률 ≥90%, 평균 z² ≤1.3의 여섯 검사를 모두 요구한다. 로봇 두 개의 같은 배치 표본과 도달하지 못한 배치를 구분한다. PF가 빠지면 평가 불가다. σ가 정확히 보정되었다는 주장은 하지 않는다.
- **C:** 과보수 진단은 보고만 하며 채택 관문이 아니다.
- **HOST_ERROR·ENOSPC·missing-primary·INVALID는 UNCLASSIFIED:** 실패로 대치하거나 60곳 분모에서 빼지 않는다. 미분류는 통과를 막으며 주 시드 미분류는 Wilson 구간도 막는다. 앞서 관측한 실패·하드 위반은 HOST나 재시도로 지우지 않는다. 완전하고 안전하며 과제 실패가 없던 원본(`HOST_SAFE`)에 한해 동일 배치·시드·설정으로 재시도 1회까지 선택할 수 있다. 이 코호트의 커밋 메타데이터는 재시도 0을 기록한다.

세부 분류·recorder·HOST 전이·teacher/termination 창·재파지 정의는 최종 [CLASSIFY_NOTES.md](analysis/CLASSIFY_NOTES.md)의 D1–D5와 `analysis/classify_placements.py`, `analysis/recorder_v4c6b.py`를 그대로 봉인한다. 과거 초안의 `INVALID→FAIL` 정의는 사용하지 않는다. 기계 판독 gate는 [analysis_gate.json](analysis/analysis_gate.json), 봉인 후 분석 적용은 [apply_sealed_analysis.py](analysis/apply_sealed_analysis.py)다. 기존 분류기 보고서의 `unsealed_stage_probe` 표시는 유지하고 별도 `sealed_analysis.json`에 나중 분석 봉인의 판정을 기록한다.

## 제어기와 두 pin 집합

`b-v6h1`은 `b-v6g` + κ=0.9483378899463337, σ 배수 1/1, yaw 5°/4°, p2f, axial lag ON이다. σ의 `probe_all_sweeps`는 짐 없는/든 팔·차체·접근·후진·preclose 자기 위치 여유에 적용한다. 별도 빔 불확실성과 GlobalPairSweepGuard/정합의 K_SIGMA=2는 유지한다. yaw와 p2f는 모든 `not approach` 단계(align·재파지 포함)다. 든 쌍에는 신뢰할 만한 정지 감지가 없다(fail-open). D1 검출기는 이 등록에 포함하지 않는다.

1. **EXECUTION:** `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`의 274파일(기존 `V6H_EXTRA_SOURCE_PATHS` 6개 포함)을 Git blob SHA와 SHA-256으로 고정한다. 검증은 `git show 4c6b439f:<path>`를 읽는다. 작업 트리와 비교해 실행 해시를 다시 만들지 않는다. 같은 등록의 재실행은 **4c6b439f checkout**이 필요하다.
2. **ANALYSIS:** 최종 분류기·adapters·정의·gate·그 의존성 및 봉인 메타데이터를 이 `prereg_v6h.json`을 담은 봉인 커밋에서 고정한다. JSON에 자기 커밋 SHA를 넣는 순환을 피하기 위해 `--seal-commit <SHA>`로 그 커밋을 명시하고 해당 커밋의 등록 바이트와 모든 분석 blob을 대조한다. 겹치는 경로도 두 커밋의 해시를 따로 보존한다.

`build()`는 여전히 현재 트리 preview이며, `--seal`은 위 두 집합을 묶어 새 파일을 한 번만 쓴다. 기존 봉인 파일이 있으면 덮어쓰기를 거절한다. 새 실행 승인은 없고 `runnable=false`, `execution_authorization=null`이다. 봉인 트리의 표준 실행 admission은 원본 실행 계약과 달라 거절된다.

## 공개 사항: 기록 시점·드라이버·블라인드

코호트는 **봉인 전에**, source `4c6b439f`에서 블라인드 상태로 기록됐다. 커밋 메타데이터는 별도의 얇은 driver가 동일한 `scripts.run_pair_stage_probes` worker entry point를 호출했다고 기록한다. 당시 `prereg_v6h.json`이 없어서 `--prereg` 대신 **unsealed stage-probe admission**을 사용했다. 등록 receipt가 없었다는 사실을 보존한다.

허용된 `origin/claude/v6h1-confirm-run`의 메타데이터 커밋은 `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`이다. `RUN_MANIFEST.json`, `plan.json`, `placements_seed943_first12.json`만 읽었으며 **블라인드 raw는 목록·내용 모두 열지 않았다.** 명령 동등성이나 driver 본문은 여기서 직접 검증하지 않았다. 전체 driver/cases.jsonl 해시는 아래 메타데이터의 진술이다.

| 항목 | SHA-256 |
|---|---|
| RUN_MANIFEST.json | `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210` |
| plan.json | `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026` |
| cases.jsonl (메타데이터 진술) | `8e7837cbc948abcd7a29a6b81272870ec7ab716c1aba87f018cd3aca655d1836` |
| driver (메타데이터 진술) | `7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56` |
| seed 943 첫 12곳 | `9c2cc220901084f4211952b57ccb4779570d61c926cc8bbbbf9c1f25be310b0a` |

builder의 72개 cases에서 `registration_run_id`만 뺀 결과를 커밋된 `plan.json`의 literal cases 배열과 **바이트 단위**로 대조한다. driver가 저장한 순서에 맞게 builder의 `chain_stop_leg` JSON 키를 마지막에 배치했으며, 값·배치·prior·worker 옵션은 바꾸지 않았다. 과거 builder도 값은 같지만 이 키의 순서는 달랐다는 사실을 숨기지 않는다.

최종 classifier/adapter/정의는 블라인드 결과를 보지 않고 reviews 299–299g를 거쳐 `1f0e4eb501a8f1b87077df943382fc1f0777dc69`에서 고정됐다. 이 작업은 그 바이트를 보존하고 별도 분석 gate를 봉인한다. 공개/합성 fixture 검사는 블라인드 코호트 결과가 아니다.

조정자가 승인한 main의 `zone_main_budget.py`, `zone_study_llm_driver.py`, `zone_study_llm_transport.py`, `agent_lock.py`는 작업 트리에서 main 버전을 사용한다. 앞의 세 파일은 모델 usage/전송 검증 변경이며 코호트의 모델 호출은 0이다. agent_lock은 호스트 도구 변경이다. 실행 검증은 계속 4c6b439f blob을 사용하므로 이 변경을 실행 바이트로 소급하지 않는다. 봉인 metadata 파일(builder·이 문서·REGISTRATION_PLAN·CURRENT_REVISION)의 변경도 실행 pin과 구분한다. 정확한 차이 목록과 두 해시는 JSON의 `notes.working_tree_differences`에 기록한다.

## 검증과 이후 분석 명령

[REGISTRATION_PLAN.md](REGISTRATION_PLAN.md)의 명령을 따른다. 지금은 등록·오프라인 테스트만 수행하며 개봉·물리·렌더를 하지 않는다. 결과 개봉 뒤에는 실패·미분류·비용·시간·명령 수와 raw 위치/해시를 보고하고 `docs/tensorboard.md`의 native TensorBoard에 새 스냅샷으로 등록한다. 이번에는 새 실험/분석 결과가 없으므로 TensorBoard를 변환하거나 열지 않는다. raw 로컬 보존을 원격 백업으로 표현하지 않는다.


추가 공개: 병합한 main `f5cd3a2b`에는 기존 4개 외에 `harness/vision_loc_protocol.py`(응답 seq int 검사/bool 거절, `b38c1d59`)와 `sim/workflow_manager.py`(표준 study 실행 전 admission 검사)도 바뀌었다. 최종 작업 트리에서는 총 6개의 main 변경을 구분해 공개한다. 재개 결정 A(1)의 원본 커밋 검증과 B의 정상 main 병합에 따라 main 바이트를 반영했다. 원래 4개 목록에 들어 있던 변경으로 표현하지 않으며, 실행 274파일은 계속 4c6b439f에서 검증한다.

## 참고 자료

- [ICH E9(R1): Estimands and Sensitivity Analysis (2019)](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf): 주 분석과 민감도 분석을 사전에 명시하는 원칙을 참고한다.
- [CONSORT 2025 item 3: protocol and statistical analysis plan](https://www.consort-spirit.org/item3-accesstotrialprotocol): 분석 전에 분석 계획을 확정하고 계획의 버전과 변경을 공개하는 원칙을 참고한다.

이는 로봇 연구의 블라인드 분석 관리에 대한 유추이며 임상시험 규정 준수 주장이 아니다. 특히 두 참고 자료가 **기록 뒤 봉인을 실행 전 사전 등록으로 바꿔 주지는 않는다.** 과거 탐색·표본수 계산과 초안은 Git `4c6b439f` 및 #285 이력에 보존돼 있다.
