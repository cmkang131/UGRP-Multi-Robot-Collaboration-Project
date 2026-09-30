# PR #303 다섯 번째 독립 재현 검토

검토 대상: `567038c2563d3d6fb4c653ebc7f797b7e35fe79f`.
2026-10-01 KST, 독립 검토자 Codex, `codex/review-303e`.
기준 main과 리뷰 브랜치 시작은 `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`다.

**판정: BLOCK.** 이전 네 차례 지적의 수정은 확인했다. 다만 원시 재생/정책 검사가
거절한 원본을 다른 시행에 귀속하여, 이미 중복 때문에 INVALID였던 시행을 성공으로
되살리는 P1 한 건이 남았다. 같은 입력 집합에서 원본 하나를 더 손상시키면
성공이 **0/2 → 1/2**, 실제 TensorBoard 성공률도 **0.0 → 0.5**로 올라간다.
분모 자체는 2로 유지된다. 아래 E303-1과 전체 검증을 한 묶음으로 전달한다.

이전 네 차례 원문과 [4차 지적에 대한 작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/303#issuecomment-5915477784)을 대조했다.
현재/기본 checkout의 `AGENTS.md`, README, current_status, CONTRIBUTING과 P06 문서·변경 코드·의존성·관련 검사를 읽었다.
물리·렌더·학습·실제 모델 호출은 0회다. PR 생산 코드, 봉인 자료, `.github/workflows`는 수정하지 않았다.

## 이전 지적의 재현과 수정 확인

| 지적 | 현재 코드에서 확인한 내용 |
|---|---|
| A303-1 외부 trial/scenario/seed/order 혼합 | 동결 admission, envelope, 주문서, 요청과 내부 행을 연결한다. 특정 반례 문자열에 의존하지 않는 키·타입·중복 검사다. |
| A303-2 등록 runner 변경 | runner의 원 등록 SHA-256 `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`와 v6e 고정 파일 85/85를 직접 대조했다. |
| A303-3 terminal 생략/타입 | 정확한 boolean true, 필수 terminal 객체, completeness의 타입·일치가 필요하다. |
| F303 내부 혼합 7건 | call/action의 run·seed·condition, envelope만 바꾸는 재명명 반례를 거절한다. 같은 요청의 request/dispatch/input/transport 관계도 검사한다. |
| C303-1 요약 필드 생략·심판 충돌 | 선택 통계 유무와 무관하게 원시 표본을 재생한다. history/standing/주문 판정·저장 수치가 재생과 다르면 INVALID다. |
| C303-2 dispatch/입력 내용·전체 표 누락 | 행 존재뿐 아니라 행동·주문·역할, 이미지·촬영/요청 시각, 필수 표를 연결한다. |
| C303-3 정상 행 재정렬 | 관계는 키로 정규화하고, 원시 표본은 seq로 재생한다. history·deliveries·events의 독립적인 배열 순열도 결과를 유지한다. |
| D303-1 늦은 재배송·종료 창 | `min(observed_end, t0 + horizon)`까지만 빈 심판 상태에서 재생한다. 취소된 배송을 cap 뒤 재배송으로 되살리지 않으며, terminal 뒤 raw 표본도 거절한다. |
| D303-2 다른 정책 | 외부 계획의 정책 hash, 코드 closure 99개, profile, bundle의 지도·horizon을 연결한다. 정책/코드 pin을 제거한 변이를 실제 검출했다. |
| D303-3 짧은 정착 | confirmation 요약 대신 표본의 2초 창을 재계산한다. held·높이·이탈·누락에 따른 취소/재정착과 cap 경계를 추가 검사했다. |
| D303-4 TensorBoard 미설치 | 순수 검증 뒤 첫 event 작성 때만 의존성을 불러온다. 미설치 대조는 반례를 skip하지 않으며, 설치 환경은 실제 EventAccumulator로 값을 읽는다. |

수정 전 코드는 별도 archive 또는 독립 모듈 이름으로 불러왔다. 현재 fixture/assertion을 유지한 A/F 판독기 대조와,
해당 당시 archive에서 원본 리뷰 테스트를 `--runxfail`로 실행한 C/D 대조를 구분한다.
수집 오류를 결함 검출로 세지 않았다.

| 수정 전 음성 대조 | 실제 결과 |
|---|---|
| A303-1/3, `cbac1dfc` 판독기 | 34 failed / 1 passed / 0 errors. terminal=false는 옛 코드도 거절한다. |
| A303-2, `cbac1dfc` runner bytes | 1 failed / 0 errors. 원 등록 해시 assertion이 실패한다. |
| F303, `114349e0` 판독기 | 7 failed / 0 errors. 모두 잘못된 기록을 수락한 데 대한 실패다. |
| C303, `f5566289` tree | 11 failed / 2 passed / 0 errors. |
| D303, `3a46de0b` tree | 11 failed / 5 passed / 0 errors. 11개 모두 성공 2/2와 실제 event 성공률 1.0을 잘못 게시한다. |

## E303-1 · P1 — 재생에서 거절된 중복 원본을 폴더 이름의 다른 시행으로 돌려 성공이 되살아남

위치: `scripts/zone_study_evidence_cohort.py:54`, `:62–68`(특히 `:66`).
새 거절 경로: `scripts/zone_study_evidence_contract.py:202–204`, `:231–232`.

정상 원본은 내부 evidence key로 연결하지만, `inspect_study()`가 정책/재생 불일치로
예외를 내면 그 key를 잃는다. `collect()`는 해당 원본의 **디렉터리 basename만** 보고
INVALID를 배정한다. basename이 다른 admission의 run ID이면 그 다른 시행만 거절한다.
그 전에 정체성·외부 계획 검사를 통과한 내부 run ID와 비교하지 않는다.
거절된 원본은 관계 표에도 들어가지 않아, 실제 소유 시행의 중복 검사가 사라진다.

독립 반례는 고정 계획의 시행 A/B와 원본 3개를 사용한다.

1. A 성공 원본과 B의 정상 HOST_ERROR 원본을 만든다.
2. 동일한 **A의 key·identity·plan**을 가진 실패 원본도 만든다. 이 사본의 디렉터리만
   `duplicate/run-1`로 둔다. basename `run-1`은 B의 run ID이며, 원본 내부의 A 신원은 바꾸지 않는다.
3. 손상 전에는 두 A 원본 모두 검증을 통과하고, 중복 A는 INVALID, B는 정상 실패다.
   따라서 **성공 0/2, A INVALID/B VALID**다. 폴더 이름으로 정상 원본을 배정하지 않는 현재 동작을 그대로 사용한다.
4. 실패 사본 A의 `policy_sha256`만 다른 값으로 바꾸고 파일 영수증을 갱신한다.
   frozen plan, 성공 원본, B 원본, 모든 identity와 성공/실패 요약은 그대로다.
5. 정책 검사는 이 사본을 올바르게 거절한다. 그런데 집계가 폴더 이름 때문에 B를 INVALID로
   처리하고 A의 두 번째 원본을 조인에서 빼 버린다. A는 이제 단독 성공으로 남아
   **성공 1/2, A VALID/B INVALID**를 게시한다.

같은 현상은 profile 불일치, events 누락, 재생과 충돌하는 `orders_complete` 요약에서도
재현된다. 네 손상 × 입력 목록 정방향/역방향 **8개 모두** 위 0.0 → 0.5를 실제
EventAccumulator로 확인했다. 정책을 바꿔 성공을 새로 만든 반례가 아니다.
**실패 사본을 손상시켜 기존 중복 성공의 거절만 해제하는 반례**다.

수정 조건: 심판 재생 전에 검증한 시행 key를 오류 경로에도 보존하여 그 시행을 INVALID로
남겨야 한다. key와 경로 이름이 충돌해 소유가 모호하면 관련 시행 또는 전체 코호트를
보수적으로 거절할 수 있다. 읽을 수 있는 내부 소유 key를 버린 뒤 다른 시행의 폴더명만
확정 소유자로 쓰면 안 된다. 실패 원본 추가·손상이 기존 INVALID 시행을 성공으로 바꾸지
않는 불변식도 raw → collect → publish 경계에서 검사해야 한다.

현재 폴더명이 A인 대조와 어느 admission에도 속하지 않는 이름인 대조는 모두
성공 0/2를 유지한다(2 passed). 따라서 출처 불명 고아의 보수적 거절 선택을 바꾸라는
요청이 아니다. 정책/재생에서 거절된 **알려진 A의 원본**을 B에만 귀속하는 누락이다.
`test_invalidating_duplicate_replay_cannot_increase_cohort_success` 8개는
`strict=True, raises=AssertionError` xfail로 남겼다.

## 추가 일반화 검사

저장된 요약의 success를 그대로 분자로 쓰는 경로는 찾지 못했다.
`verify_referee_derivations()`가 원시 표본의 전체 재생과 cap까지의 재생을 각각 수행하고,
재생 수치와 trial/evaluation의 수치가 일치할 때만 관계 표를 만든다.
집계는 발견한 파일 수가 아닌 외부 계획의 admission 수를 사용한다. 분모는 유지됐지만,
거절된 원본의 시행 귀속은 E303-1 때문에 아직 안전하지 않다.

독립 추가 검사 [tests/test_review_303e.py](../../tests/test_review_303e.py)는 **58 passed**다.

- 목적지 A/B/C × 취소 방식 held/lifted/left_zone/missing × 재방출 시각 8/10/10.0002/11.3초: 48개.
  두 번째 주문을 첫 배송 취소 뒤에만 채워, 재확인이 12초 cap을 넘으면 과거 confirmation으로 성공할 수 없게 했다.
  cap 전과 정확히 cap인 정상 기록은 성공으로 남고, cap 뒤는 성공으로 남지 않는다.
- 시작·중간·마지막 이벤트 각각의 삭제/중복/변조: 9개. 저장 요약과의 모순 또는 해시 사슬 손상을 거절한다.
- 정상 오배송 복구 뒤 events/history/deliveries/trial deliveries를 서로 독립적으로 섞는 128개 순열: pytest 항목 1개, 판정·수치 동일.

위 58개 통과 검사는 정상 대조와 수정 일반화 검사이며, E303-1의 xfail 및 대조 2개와 구분한다.
고정 분모, 논리 trial/물리 run 구분, 사전 지정 attempt 하나, 출처 불명 고아의 보수적 거절,
정착 시작을 배송 시각으로 표시하는 기존 선택은 다시 문제 삼지 않았다.
원시 자료 자체의 진실성·완전한 위조 방지나 실제 물리 성공을 이 코드 검사로 인증하지 않는다.

## 검사 결과와 보존

| 검사 | 독립 실행 결과 |
|---|---|
| 제출된 selector 전체 | **562 passed / 0 failed / 0 errors / 0 skipped** |
| 새 검토 파일 전체 | **60 passed / 8 strict xfailed / 0 errors** |
| 새 반례에 `--runxfail` 적용 | **8 failed / 0 errors**, 모두 성공 수가 증가한 판정 assertion 실패 |

562개에는 지정한 `test_zone_pair_registered_source.py` **22개 전체**와
`test_zone_study_source_pinning.py` **34개 전체**, D303 반례/정상 대조 **16개**, 실제
TensorBoard readback, TensorBoard를 막은 별도 프로세스의 검사가 포함된다.
관계형 **12,000건**과 이벤트 재생 **12,000건**은 pytest 항목 8개 안에서 실행되며,
이 사례 수를 562에 더하지 않는다. 단순 관계 표 생성 검사를 raw 게시 경계의
E303-1 검증으로 확대할 수 없다는 것이 이번 반례의 의미다.
정확한 JUnit 집계·초기 실행·로그 SHA-256은 [verification.json](review_303e/verification.json)에 있다.

해당 HEAD의 GitHub CI [36743836479](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36743836479)는
**33/33 SUCCESS**였다. PR은 OPEN/DRAFT이며, 이 CI 통과가 E303-1을 해소하지 않는다.
검토자는 PR을 병합하거나 CI/workflow를 변경하지 않았다.

변이 6종도 독립 재실행했다. cap 제한 제거 2개, 정책 pin 제거 1개, 코드 pin 제거 1개,
정착 창 단축 4개, 요약 대조 제거 1개, 즉시 TensorBoard import 복원 1개가 의도대로 실패했다.
수집/실행 error는 0이다. 마지막 변이는 미설치 import 실패를 재도입한 대조다.
음성 대조와 변이의 의도된 실패 수는 현재 후보의 통과 수에 합산하지 않는다.

초기 추출 때 연구 미디어와 함께 테스트 JPEG도 제외한 검토자 오류가 있었다.
그 실행은 252 passed / 6 failed 뒤 중단했고, fixture를 정확한 PR bytes로 복원했다.
관련 17개가 다시 통과한 뒤 전체 묶음을 새 프로세스에서 재실행했다.
초기 실패·중단 로그도 보존했으며 코드 결함이나 최종 통과로 세지 않는다.

`f5566289`에 있던 파일명 `prereg*.json` 53/53도 그대로다.
`prereg`를 포함한 경로의 관련 JSON까지 넓히면 57/57이며 모두 바이트가 같다.
지정한 등록 소스 검사 두 파일은 PR tree에서 전체 실행하며 기대 해시를 바꾸지 않았다.
`origin/main`과 `.github/workflows`의 두 점·세 점 diff는 모두 0개다.
최종 fetch의 main은 `26bfcf8e2977e85132845d7704fe1070f277dd13`로 진행됐고,
PR HEAD는 그대로다. 이 최신 main에 대해서도 workflow diff가 0개임을 다시 확인했다.
검토 파일의 해시·환경·등록 바이트 대조는 [source_verification.json](review_303e/source_verification.json)에 있다.

`git fetch origin`, 열린 PR 조회와 diff 후 `git archive`로 정확한 PR tree를 추출했다.
추가 worktree/가상환경은 만들지 않았다. 기존 Python 3.12 환경을 사용하고 #328에 따라 host lock 없이 실행했다.
driver에서 MuJoCo·torch·물리 worker import를 막고 스레드를 1개로 제한했다.

```sh
# 정확한 PR archive에서 실행; 등록 이력 검사는 기존 Git object DB를 읽는다.
GIT_DIR=/Users/changmin/projects/ugrp/.git \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py --tb=short
# 이 리뷰 테스트를 archive의 tests/에 복사한 뒤:
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  /path/to/review_303e/offline.py /path/to/archive tests/test_review_303e.py
```

이전 판독기 대조용 [negative_control.py](review_303e/negative_control.py)는 archive 루트에 복사한 뒤
`cbac1dfc`, `114349e0`, `old-runner` 중 하나와 해당 selector를 넘긴다.
C/D는 각 검토 대상 SHA archive에 원래 리뷰 테스트를 복사하여 `offline.py ... --runxfail`로 재현한다.
변이는 PR의 `event_replay_mutations.py <변이명>`으로 재현한다.

원본 로그/JUnit은 `/Users/changmin/projects/ugrp/outputs/review-303e/`에 로컬 보존한다.
작은 보고서·재현 코드·해시 집계만 Git으로 보존하며 전체 로그의 원격 백업을 주장하지 않는다.
새 연구 코호트가 없는 코드 검토이므로 합성 event readback만 수행했다.
공용 TensorBoard snapshot·서버·UI와 Drive는 변경하지 않았다.

검사 종료 뒤 이번에 만든 `/private/tmp/ugrp-review-303e-FulwqV`와 그 안의 이전 C/D
추출본을 모두 삭제하고 경로 부재를 확인했다. 실제 raw와 기존 snapshot은 삭제하지 않았다.
최종 보고는 이 SHA의 P06 합성 코드 계약에 대한 **BLOCK**이며, E2E·PHYSICAL·실제
provider 정산·새 runner 연결·영상/공용 UI 인수에 대한 판정이 아니다.
