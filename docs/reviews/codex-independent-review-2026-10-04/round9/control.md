# 9차 제어·허가 생명주기 검토 — 2026-10-04

**새 결과는 #371의 작은 기록 귀속 오류 1건(P3)이다.** #363의 상태 채널은 준비·취소·재준비·만료·task/segment 분리 표적 검사에서 예상대로 동작했다. 기존 same-tick peer-abort 문제를 새 건수로 세지 않았다. 생산 코드·실제 모델·물리·렌더·하드웨어·held-out 원본은 변경하거나 실행·열람하지 않았다.

## 범위와 현재성

| 대상 | 검토 소스 | 공식 확인 |
|---|---|---|
| main | `b23fc0875b72f4b55f399a252a1575b7e8b43cb5` | 06:43:23.576 UTC, commit 2026-10-03 15:39:40 UTC |
| #363 | `6727751b49ce11fb62234bb97274137f22850765` | 초기 확인 06:23:54.044 UTC; updated 06:12:22 UTC |
| #363 후속 | `de03fe87d08879abefaa7dac67c7ff313df5df89` | 06:43:23.576 UTC; updated 06:28:56 UTC. 공식 compare는 README +27행만, 소스 변경 0 |
| #371 | `a009112ff5fb18c6b64f58d8cd6392c58d4c028c` | 06:43:23.576 UTC; updated 06:21:31 UTC |
| #372 | `f676889f39df2de0679cc4e82e067565dcc5a775` | 06:43:23.576 UTC; updated 전일 17:18:46 UTC |

`frontier-checkpoint-heads.json` (Mac 전달본 증거), `frontier-de03-doc-only.json` (Mac 전달본 증거), `frontier-initial.json` (Mac 전달본 증거). #363의 672 소스 검토 결과는 소스가 같은 de03에도 해당한다. de03 문서의 새 실행 보고를 이번 합성 검사의 관측 결과로 합산하지 않는다.

AGENTS·README·current_status·CONTRIBUTING을 읽고 현재 최종 경로를 추적했다. `zone_final_pair_runtime.Runtime` → `zone_pair_highpose_runtime.Execution`의 고정 `PairExecution.step/arm_step` → `zone_pair_status` 및 실제 `run_pair_highpose.run_case`의 issue/on_command/advance 순서를 포함한다. 옛 `PairCarrySync`를 최종 v98 상태 채널과 혼동하지 않았다. 원본에서 추출한 1,731개 소스/설정 파일 전체를 모두 정독했다는 뜻은 아니다.

## R9-C1 · P3 · 새 claim의 retried_ticks에 이전 claim의 거부가 붙는다

대상은 #371 `harness/pair_llm_runtime.py`의 `ClaimGate.grant/revoke/start`. 허가 교체 또는 취소는 `permits`를 바꾸지만 로봇별 `retries`를 초기화하지 않는다. `retries`는 일시적인 `SELF_*` 거부에서 증가하고, 최종 `claim_submitted`를 기록한 뒤에만 0이 된다. 따라서 새 `call_ref`와 새 `released_at_sim_s`를 가진 row에 이전 허가의 횟수가 합쳐진다.

| 실제 action-map/link를 거친 합성 순서 | 마지막 row의 call_ref | 기대한 새 허가 거부수 | 현재 retried_ticks |
|---|---|---:|---:|
| fresh A → 즉시 accept | A | 0 | 0 |
| A가 두 번 거부 → B로 교체 → B 즉시 accept | B | 0 | **2** |
| A가 두 번 거부 → wait/hold로 revoke → 새 B → B 즉시 accept | B | 0 | **2** |
| A가 두 번 거부 → look_around → 같은 A 재시도 | A | 2 | 2 |

`wait_then_new`의 시각은 hold 시작 0.2초, 10초 hold 창이 지난 뒤 새 B 10.3초, accept 10.4초다. hold 완료와 `Team.start`의 준비 판정은 명시적인 fake다. `executor_plan`/`pair_executor_plan`, `PairLink.call`, `GatedRuntime.grant`, own executor의 `_start/hold/look_around`, ClaimGate 메서드는 a009 원문 AST를 그대로 실행했다. 새 허가 경계에서 재시도 카운터만 0으로 놓는 원인 대조에서는 B=0이고 누적 `refusal_total`은 2를 보존했다.

- 재현: `control-permit-repro.py` (Mac 전달본 증거)
- 값·소스 SHA-256: `control-permit-result.json` (Mac 전달본 증거)
- 명령: `python review-notes/round9/control-permit-repro.py --repo /path/to/ugrp-git-clone` (a009 Git object 필요, checkout은 바꾸지 않음)

영향은 **허가별 디버깅·기록 귀속**이다. `PairTrial.on_claim_result`가 이 row를 `claim_results`에 보존하므로 단순 사적인 임시 카운터에 그치지 않는다. 다만 전체 거부수는 맞고, 코드에서 이 수치를 제어 결정이나 모델 토큰/SIM 비용으로 쓰는 증거는 없다. 물리 안전·완주·비용 오류로 확대하지 않는다. 수용 기준은 취소/대체된 A의 재시도를 A의 기록으로 보존하고 새 B의 횟수는 B 생명주기에서 세는 것, 같은 허가의 relook/재시도는 그대로 누적하는 것이다. 생산 수정안은 작성하지 않았다.

## 준비/GO/취소/세대 경계에서 확인한 것

`control-barrier-repro.py` (Mac 전달본 증거)는 672의 실제 `zone_pair_status.py`를 import한다. `control-barrier-result.json` (Mac 전달본 증거)의 정상 행렬은 6개 barrier × segment 0/1/7 × 시작시각 0/.03/.07/1.3 × 첫 소비자 r1/r2 = **144개**다. 모두 두 endpoint가 같은 제어 격자의 GO를 받아 갔고, 그 시각은 원래 증거의 유효기간 안이었다.

재현 명령은 `python review-notes/round9/control-barrier-repro.py --source-root /path/to/exact-6727751-source`다. 복사한 소스 또는 별도 고정 checkout을 넘기며 다른 작업자의 checkout을 바꾸지 않는다.

| 표적 불변식 | 결과 |
|---|---|
| GO 전 준비 철회 | 둘 다 WAIT |
| 철회 뒤 새 준비를 양쪽에서 다시 제출 | 새 시각 0.5초에 둘 다 GO |
| heartbeat만 반복해서 영상 증거 연장 | 불가; 0.6초 만료 뒤 GO 없음 |
| 같은 frame ID의 관측시각 바꾸기 | report 거부 |
| lift@0 기록으로 lift@1 통과 | 불가 |
| 옛 task의 wire row를 새 task에 재생 | publish 거부 |
| abort 뒤 endpoint 재준비 | 거부; 상대 GO 없음 |
| 공통 GO 시각을 놓친 늦은 polling | ABORT |

이는 상태 프로토콜의 오프라인 증거다. 영상이 실제 파지를 입증하거나 네트워크로 독립된 두 물리 제어기의 동시성을 보장한다는 결과가 아니다. 현재 모듈은 공유 append-only 상태 원장에서 각 endpoint가 판단하는 in-process 구성이다. 동일 phase/segment를 같은 task에서 재사용하는 일반 API를 보장하는 것으로도 넓히지 않는다. 정상 호출은 segment를 올리고 새 pair 작업은 새 UUID channel을 만든다.

## 지적하지 않은 후보와 기존 항목

1. **guard→dispatch의 단순 시간 경과:** `run_case`는 control step → 각 명령 issue/on_command → arm_step → 각 명령 issue/on_command → advance 순서다. guard 후 실제 issue 전에는 SIM 시간이 진행되지 않는다. arm_step에도 guard가 있어, 느린 Python wall time만으로 별도 TOCTOU 결함을 주장하지 않는다.
2. **same-tick peer-abort:** `Runtime.step`이 앞 로봇의 명령을 모은 뒤 뒤 로봇 실패와 `team.poll`이 도는 기존 문제는 관련 소스가 그대로다. 이 검토의 신규 finding이 아니며, round8의 실제 port 재현을 참조한다. 공통 GO의 첫 소비 뒤 같은 tick 철회도 이 기존 dispatch 원자성 문제와 분리해 새 건수로 세지 않았다.
3. **취소된 pending claim이 계속 살아나는가:** idle `wait`는 실제 `hold` 승인 후 permit을 revoke한다. `look_around`는 기존 permit을 유지하며 관측 뒤 재시도하는 의도된 동작이다. `release`는 active order job이 없으면 `NO_ACTIVE_JOB_FOR_ORDER`로 명시적으로 거부한다. 이들을 버그로 바꾸어 세지 않았다.
4. **own_status clock / prompt placeholder:** a009에서 고쳐졌다는 round8의 exact-source 대조 결과를 유지한다. 오래된 1883 지적을 현행으로 재발행하지 않는다.
5. **HIGH edge OLS 실패:** 672는 v98 전용 deterministic consensus fallback을 추가했다. 과거 d5ca의 HIGH 전 프레임 None을 최신 코드에서도 그대로 발생한다고 쓰지 않는다. robust fit의 ROI semantic 경계와 PF consistency의 temporal 상태는 별도 geometry reviewer 범위다.

## 현재 열린 과제에서 다음으로 할 일

| 우선순위 | 과제와 근거 | 가장 작은 다음 판별 | 중복 방지/경계 |
|---|---|---|---|
| 높음 | #363의 새 PF consistency로 confidence와 admission의 관계가 바뀜. 672 공개 README는 도크 r2 입장 실패 가능성을 이미 설명 | 같은 view 반복/명령만 있고 실제 이동 없음/재초기화에서 가중치·view identity가 어떻게 바뀌는지 합성 이력으로 검사 | geometry 담당. 입장 5 cm를 임의로 완화하거나 GT를 제어에 넣지 않음 |
| 높음 | #219는 최종 환경 기술 재검증, #224는 no-LLM smoke→LLM pilot→본 실험 순서를 요구. 과거 HIGH 단계 도달은 carry/release 완료가 아님 | 최신 공개 보고에서 첫 실패 phase와 admission/pose/edge/dispatch 중 무엇이 선행하는지 분리 | 공개 보고만 사용. 소스 변경 뒤 오래된 DEV 궤적을 최신 재실행으로 표현하지 않음 |
| 중간 | controller hold는 실제 port의 arm interpolation을 취소하지만 own target bookkeeping과 같은 개념이 아님 | 합법적인 guard wait/재관측 진입에서 실제 발행 setpoint와 다음 sweep의 시작 servo가 달라지는지 fake port로 추적 | 조사 중. measured joint 요구 없음; 입증 전 finding으로 올리지 않음 |
| 중간 | #223은 고정 status wire를 모든 조건에 넣고 조건별 차이는 대화로 제한 | 상태 wire·자기 claim outcome·action schedule을 고정한 채 peer 비공개 상태 변화가 모델 입력을 바꾸는지 | 연구/런타임 reviewer 담당. no_comm을 ‘동료 정보 0’으로 재정의하지 않음 |
| 낮음 | #371 R9-C1 허가별 재시도 기록 | cancel/replace/같은permit relook 3경계의 카운터 소유권을 명시 | 현재 결과는 P3 기록 오류; 비용 오류로 확대 금지 |

이는 checkpoint다. 나머지 할 일을 닫았거나 저장소 전체가 검증됐다는 뜻이 아니다. 실제 실행 권한·자원 사용이나 외부 PR 쓰기는 이 reviewer가 수행하지 않았다.
