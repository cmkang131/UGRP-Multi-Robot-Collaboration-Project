# PR #303 독립 재현 검토 C

**판정: BLOCK.** 검토 HEAD는 `f55662896c310509db32e5ea1e451827ab5b40ab`이다.
이전 calls/actions의 시행 혼합과 terminal·봉인 회귀는 수정됐지만, 원본 심판과
성공 기록의 불일치를 통과시키는 경로가 남아 있다. 고정 분모가 유지돼도 분자가
잘못 올라가므로 P06 증거 연결 완료로 승인할 수 없다.

2026-09-30 착수 / 2026-10-01 최종 기록(KST), 독립 검토자 Codex, `codex/review-303c`.
리뷰 시작 main은 `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`.
물리·렌더·학습·실제 모델 호출은 하지 않았다. PR 생산 코드, 봉인 자료,
`.github/workflows`는 수정하지 않았다. 아래 지적을 한 묶음으로 전달한다.

## C303-1 · P1 — 선택적 집계 필드가 빠지면 실패한 심판 원본도 성공으로 연결

위치: `scripts/zone_study_evidence_contract.py:179–213`, 특히 `:181–182`,
`:194–203`; 호출부 `scripts/tensorboard_tools/zone_study.py:139–143`.

`verify_referee_derivations()`는 evaluation에서 `departures`와
`departed_unsettled_items` 두 필드가 없으면 즉시 반환한다. 이 때문에 핵심
심판 이력·배송 결과의 교차 검증까지 선택적 통계 필드에 종속된다.

독립 반례는 정상 synthetic 성공 raw의 **trial, admission 계획, identity를 그대로**
두고, `eval_only/referee.json`을 같은 주문·시행의 실패한 심판 기록으로 바꿨다.
순수 `Referee.observe()`에 box_00을 목적지 A 대신 C에 정착시킨 표본을 제공하여
만든 기록이며, 그 자체의 history/standing/orders가 일치하고 `orders_complete=false`다.
evaluation에서 위 두 집계 필드만 빼고 파일·파생 입력 SHA를 다시 계산했다.
성공 수치 자체는 고치지 않았다.

**실제 코호트 게시 결과는 admitted=1, successes=1, invalid=0,
TensorBoard `cohort/success_rate=1.0`이었다.** 실패를 판정한 원본과 이전 성공
사본이 섞였는데도 0/1 대신 1/1이 게시된다. 두 필드를 남긴 대조군은 같은 실패
원본을 INVALID, 성공 0/1로 거절한다. 따라서 단순한 임의 원본 위조나
파일 해시 검사의 문제가 아니라 검증 분기의 우회다.

같은 함수에 추가 누락도 있다. 두 필드를 유지해도 다음 6개 반례를 모두 성공
1/1로 게시했다.

- `referee.history[0]`의 `run_id`, `seed`, `condition`을 하나씩 다른 시행 값으로 변경.
  trial 배송 행은 검사하지만 원본 history 행의 선언한 식별값은 검사하지 않는다.
- `standing.box_00.zone`만 C로 변경, `referee.orders`의 주문 ID만 다른 값으로 변경,
  `referee.orders_complete`만 false로 변경. history와 중복 저장된 최종 상태·판정을
  재도출하여 대조하지 않는다. `standing`은 값이 아니라 item 키의 존재만 사용한다.

수정 조건: 성공을 뒷받침하는 필수 심판 원본과 이력 연결을 집계 필드 유무와
독립적으로 검사한다. history의 선언 신원, 시간·개체 키, 최종 standing과 주문별
판정, trial 배송 행을 하나의 원본에서 재도출하고 충돌·누락은 INVALID로 남긴다.
HOST_ERROR 등 실제 심판 생성 전 실패에는 가짜 심판 행을 요구하지 않는다.

재현: `tests/test_review_303c.py`의
`test_failed_referee_cannot_back_a_success_when_counts_are_missing`,
`test_foreign_referee_history_row_is_invalid`, `test_conflicting_referee_state_is_invalid`.
**strict xfail 7개**, 집계 필드를 유지한 거절 대조군 1개 통과.

## C303-2 · P1 — dispatch/입력 표는 ID 일부만 연결하고 내용 충돌·표 전체 누락을 허용

위치: `scripts/zone_study_evidence_join.py:208–224`,
`scripts/zone_study_evidence_contract.py:101–107`,
`scripts/tensorboard_tools/zone_study.py:19–20`.

dispatch와 action은 call ID·actor·시각만, inputs와 request는 request ID·robot만
대조한다. 실제 주문/행동과 이미지 출처는 교차 검증하지 않는다. 두 보조 파일은
존재할 때만 검사하므로 `record_complete=true`이며 실제 calls/actions가 있는
정상 writer 산출물에서도 dispatch 파일 전체를 지우고 inventory를 갱신할 수 있다.

독립 반례 3개는 정상 raw에서 각각 다음 하나만 바꾼 뒤 행 index·입력 해시를
다시 계산했다. frozen plan과 calls/actions/request 본문은 바꾸지 않았다.

1. `dispatch[0].action.order_id`를 같은 admission 안의 다른 유효한 주문 ID로 변경.
2. `inputs[0].frame_sha256`을 존재하지 않는 `000…000` 이미지 SHA로 변경.
3. `study/dispatch.jsonl` 전체를 제거. result에 기록된 dispatch 요약과 action 행은 유지.

**3개 모두 INVALID 0, 성공 1/1 및 실제 이벤트 성공률 1.0으로 게시됐다.**
서로 연결되는 행의 키가 존재한다는 사실과 행동·관측 내용이 같다는 사실은 다르다.
현재 12,000개 생성 검사는 이 원본 파일 계층의 누락을 검사하지 않는다.

수정 조건: 정상 complete 기록의 필수 관계를 명시하고, dispatch의 행동·주문과
action 로그, input의 촬영 시각/프레임/이미지 SHA와 보존한 request/image를 대조한다.
중단·호출 전 HOST_ERROR의 정상적인 부분 기록은 별도 규칙으로 보존하되, 파일 삭제로
완전한 성공 증거가 되지 않아야 한다. provider 실제 과금 대조를 추가로 완료하라는
지적은 아니며, 이미 저장한 로컬 관계의 일관성 문제다.

재현: `test_raw_action_and_camera_receipts_must_match_the_call` **strict xfail 3개**.

## C303-3 · P2 — 같은 시각의 정상 심판 행을 재정렬하면 성공을 INVALID로 낮춤

위치: `scripts/zone_study_evidence_contract.py:190–212`.

최종 상태를 계산할 때는 history를 시각으로 정렬하지만, deliveries는 원본 list
순서로 만들고 trial의 deliveries와 순서가 있는 JSON digest로 비교한다.
서로 다른 개체 3개의 confirmation이 모두 같은 SIM 시각인 정상 fixture에서
history 행 순서만 뒤집으면, 여전히 시간순이며 값·키·배송 판정이 같은데도
`INVALID: referee history/trial/derived numbers conflict`로 거절된다.

코호트는 분모 1을 유지하지만 정상 성공 1/1을 **INVALID 1, 성공 0/1**로 표시한다.
순서를 의미로 쓰지 않는 복합키 조인이라는 재설계 목표와 맞지 않는다.
시각·개체 키로 정규화한 관계를 비교하되, 중복 키 검사는 유지해야 한다.

재현: `test_reordered_simultaneous_referee_rows_preserve_valid_success`
**strict xfail 1개**. 같은 fixture의 receipt만 다시 계산하는 정상 대조군은 통과한다.

## 이전 지적과 생성 검사의 검증 범위

읽은 이전 검토는 `origin/codex/review-e2e-batch-a`의 `REVIEW_E2E_BATCH_A.md`와
`origin/codex/review-fixes-1`의 `REVIEW_FIXES_1.md`다.

제출된 selector 전체를 독립 실행한 결과는 **440 passed / 0 failed / 0 errors /
0 skipped**다. 필수 `tests/test_zone_pair_registered_source.py` **22개 전체**,
`tests/test_zone_study_source_pinning.py` **33개 전체**, door-relax 등록 보존 1개,
4조건 정상 경로·실제 TensorBoard readback·코호트 CLI·12,000개 생성 사례를 포함한다.
12,000 사례는 pytest 항목 4개 안에서 실행하며 440에 더해 세지 않는다.
재설계 전 음성 대조와 아래 독립 반례는 이 통과 수와 별도로 보고한다.

| 이전 지적 | 현재 검증 및 제한 |
|---|---|
| A303-1 외부 trial/scenario/seed/order 혼합 | 제출된 외부 identity·주문·요청 연결 검사는 통과. 파일 hash만이 아니라 frozen admission과 행 키를 대조한다. 원본 심판·dispatch/입력 내용까지의 일반적 보장은 C303-1/2로 미완료 |
| F303-1 내부 calls/actions 6개 및 envelope 재명명 1개 | 현재 7개 통과. `validate_internal()`의 일반 행 루프와 직접 index 반례도 확인. 수정 전 `114349e0` 판독기로 7개 전부 실패하고 성공 event 1.0 readback 재현 |
| A303-2 고정 runner 변경 | 원래 SHA-256 복원, 등록 검사 전체 통과. 옛 `cbac1dfc` runner bytes를 제공한 대조에서 실제 hash assertion 실패 |
| A303-3 terminal 누락/타입 | 필수 true·terminal 객체·boolean completeness 거절 유지. 옛 판독기로 바꾼 A303-1/3 대조의 실패 수는 아래 검증 요약 참조 |

수정 전 음성 대조는 현재 fixture와 assertion을 유지한 채, 옛 **생산 판독기만**
별도 Python 모듈 이름으로 불러왔다. PR archive의 생산 파일은 덮어쓰지 않았다.
`114349e0` 대조는 contract·study adapter·exporter 3개,
`cbac1dfc` 대조는 study adapter·exporter 2개다. 고정 runner 검사는 별도 임시 경로에
추출한 `cbac1dfc` 원본 파일로 읽기 대상을 바꿨다.

| 음성 대조 | 독립 실행 결과 |
|---|---|
| A303-1/3, `cbac1dfc` 판독기 | **34 failed / 1 passed / 0 errors**, 49개는 selector 범위 밖. 이전에도 terminal=false는 거절 |
| A303-2, `cbac1dfc` runner bytes | **1 failed / 0 errors**. 기대 `85508c…`, 실제 옛 파일 `84e900…` 불일치 |
| F303 7개, `114349e0` 판독기 | **7 failed / 0 errors**. 7개 모두 잘못 수락한 성공 1.0을 실제 event에서 확인 |

이 수치는 의도된 결함 검출이며 현재 후보 테스트 실패 수와 합산하지 않는다.
새 독립 반례는 **2 passed / 11 strict xfailed / 0 errors**다. 11개 중 10개는
INVALID여야 할 원본에서 성공 이벤트 1.0을 게시했고, 나머지 1개는 정상 재정렬을
INVALID/0으로 낮췄다. xfail 마커를 뺀 테스트 본문은 모두 assertion에서 실패한다.

봉인 바이트 별도 대조에서도 v6e source **85/85개**, 이전 HEAD에 있던 사전 등록
JSON **53/53개**가 동일했다. runner SHA-256은
`85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`다.

workflow는 비교 방식을 구분한다. 시작 main `6a57435e`와 중간 main `d7ee112e`에
대한 파일 전체 비교는 차이 0개였다. 검토 중 #332가 병합된 main
`26545c2499f94c3f99a5d650f7cc8ea992f24196`과의 전체 비교에는
`.github/workflows/tests.yml`의 Ubuntu 두 job 제한 시간만 차이가 생겼다
(main 15분, 후보 10분). **PR 변경분인 `origin/main...f5566289`에는 workflow diff가
0개지만, 최신 main과의 두 점 비교가 0개라는 요구는 현재 충족하지 않는다.**
검토자가 workflow를 수정하거나 후보에 main을 병합하지 않았다.

최종 GitHub 조회의 PR HEAD는 여전히 `f5566289`, OPEN/DRAFT이며 check 목록은
비어 있고 mergeStateStatus는 UNKNOWN이었다(직전 조회는 DIRTY). 필수 CI 완료나 병합 가능 상태로 보고하지
않는다. 수정 뒤 최신 base와 함께 다시 확인해야 한다.

12,000개 생성 사례는 mix/duplicate/drop/reorder 각 3,000개이며 seed는
`30320260930 + operation_index`다. 성공/실패를 섞은 1–5개 시행·1–3개 주문에서
**정규화된 5개 표의** 6열 키 변경, 행 중복·삭제·재정렬을 검사한다.
이 계층에서 분모 탈락이나 성공 증가 반례는 찾지 못했다. missing source,
중복 source, INVALID source, 빈 source 목록도 고정 분모에 남았다.
그러나 `relation_rows()`에 넘긴 success와 해시는 이미 검증됐다고 가정하므로
12,000 통과가 raw 판독기의 C303-1/2를 검증한 것은 아니다.

## 실행·보존·재현

`git fetch origin`, 열린 PR 조회, `git diff` 뒤 아래처럼 정확한 PR tree를 추출했다.
`git worktree add`는 사용하지 않았다. 시작 checkout과 기본 checkout의 지침,
README, current_status, CONTRIBUTING, P06 문서·관련 테스트·의존성을 확인했다.

```sh
mkdir -p /private/tmp/review-303c-f5566289
git archive origin/codex/evidence-referee | tar -x -C /private/tmp/review-303c-f5566289
cd /private/tmp/review-303c-f5566289
GIT_DIR=/Users/changmin/projects/ugrp/.git \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py \
  --junitxml=/Users/changmin/projects/ugrp/outputs/review-303c-20260930/submitted.xml
```

리뷰 테스트는 이 브랜치의 `tests/test_review_303c.py`를 위 archive의 같은 경로에
복사하여 실행한다. 현재 main에는 P06 생산 모듈이 없으므로 리뷰 브랜치 자체에서의
module skip을 검증 완료로 세면 안 된다. `--runxfail`은 마커를 무시하고 실제
실패를 볼 때 사용한다. strict xfail은 발견한 결함을 숨기는 통과가 아니라
수정 시 XPASS로 검토 갱신을 요구하는 기록이다.

오프라인 잠금 해제 #328에 따라 host lock 없이 실행했다. 기존 Python 3.12 환경을
재사용하고 BLAS/OMP/MKL/VECLIB 스레드는 1로 제한했다. 제출된 driver는 MuJoCo·torch·
실물 worker import를 차단하며, 독립 반례는 writer·순수 심판·synthetic 로그만 사용한다.
전체 referee 테스트 파일의 native 물리 검사는 실행하지 않았다.

정확한 JUnit 집계·소스/로그 SHA·음성 대조 명령은
`review_303c/verification.json`과 `review_303c/negative_control.py`에 보존한다.
원본 로그와 JUnit은 `/Users/changmin/projects/ugrp/outputs/review-303c-20260930/`에,
합성 JSON/event는 OS 임시 폴더에 있다. Git에는 작은 검토·재현 자료만 올린다.

이번 작업은 새 연구 실험 결과가 없는 코드 검토다. 실제 EventAccumulator로 합성
코호트 scalar를 확인했지만 공용 TensorBoard snapshot·서버·화면을 변경하지 않았다.
실제 writer 연결·실행 전 봉인·provider 정산·영상/UI 인수·E2E/PHYSICAL은 승인하지 않는다.
UGRP 예외에 따라 Drive 작업은 없으며 로컬 raw 전체를 원격 백업했다고 보고하지 않는다.
