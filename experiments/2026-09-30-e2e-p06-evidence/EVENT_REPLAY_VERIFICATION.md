# PR #303 · 4차 검토 후 이벤트 재생 검증

2026-10-01, Codex. 검토 대상 원본은 `3a46de0b7d3c1c295335355b106e95502839cb87`,
4차 검토는 `origin/codex/review-303d`의 `d7249b8f`다.
시작 지침대로 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`를
`09b7fdf9b00bd65d474f23df4e4fb8ce043c9a06`으로 병합한 뒤 작업했다.

## 원인과 판정 경로

네 번의 검토에서 반복된 문제는 summary를 다른 summary로 검사한 뒤 그 값을 다시
성공 판정에 쓰는 구조였다. 현재 게시기는 원시 주문/지도·평가 표본의 순번/해시 사슬을
검증하고, 고정 심판 전이 함수를 빈 상태에서 재생한다. 배송·취소·재배송은 재생으로
도출하며 `history`, `standing`, 주문별 결과 등 저장된 파생값은 대조용이다.

| 지적 | 수정 및 검증 대상 |
|---|---|
| D303-1 늦은 재배송·관측 종료 불일치 | cap/관측 종료까지의 표본을 재생한다. 취소된 과거 배송은 복구되지 않으며 terminal보다 늦은 raw는 INVALID다. 늦은 재배송 2개·stale terminal 2개, 정상 cap 대조 4개를 유지한다. |
| D303-2 다른 심판 정책 혼입 | frozen plan v2에 코드 closure 99개와 매개변수·재생 규칙의 SHA-256을 고정한다. record 정책 hash·bundle profile·실행 중인 정책을 함께 대조한다. profile 변조 4개 외에 코드 pin 변이도 검사한다. |
| D303-3 짧은 정착 확인 | 저장 confirmation을 판정 입력으로 쓰지 않는다. 원시 표본을 재생해 2초 창과 중간 속도/held/높이/누락에 따른 재시작을 검사한다. 0·0.1·1.9초 위조 confirmation은 INVALID다. |
| D303-4 TensorBoard 의존성 | Writer를 지연 생성하고 순수 검사 완료 뒤 event를 쓴다. offline 반례는 순수 collect/verify를 반드시 실행하며, 선택 의존성이 있으면 실제 event readback도 추가한다. 기존 export CI job에도 16개 D303 사례를 연결한다. |

복합키·외부 admission·ITT 고정 분모·전체 원본 해시·행 재정렬 불변성·게시 직전 재검증은
그대로 유지한다. 정상 생산 fixture는 계획을 고정하기 전에 profile·지도·horizon과 동일한
주문서를 넣는다. 기존 raw나 등록 runner, 과거 snapshot을 수정하거나 새 정책으로 승격하지 않는다.

## 실행 방법과 보존

기존 Python 3.12.13 환경 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을
재사용했다. 별도 환경·host lock 없이 실행했다(#328). `redesign_test_driver.py`가 MuJoCo,
torch, 물리 worker import를 차단하고 스레드를 1개로 제한한다. 모든 합성 JSON/event는
OS 임시 폴더에만 만든다. 로컬 로그·JUnit은
`/Users/changmin/projects/ugrp/outputs/p06-event-replay/`에 보존한다.
소스·로그 해시와 집계는 `event_replay_verification.json`에 기록한다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
$PY experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py -k 'not 12000' --tb=short --junitxml=/Users/changmin/projects/ugrp/outputs/p06-event-replay/related-final.xml
$PY experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py -k 12000 --tb=short --junitxml=/Users/changmin/projects/ugrp/outputs/p06-event-replay/generated-first.xml
$PY experiments/2026-09-30-e2e-p06-evidence/event_replay_mutations.py <변이명> --tb=short
```

수정 전에는 4차 원본 파일을 `--runxfail`로 실행하여 **11 failed / 5 passed**를 재현했다.
새 파일에서는 xfail을 제거했다. 처음 전체 검사에서 실제 admission 주문서와 다른 synthetic
심판 주문서, 선택 profile이 빠진 구형 synthetic fixture를 발견했다. 검사 정책을 완화하지
않고 fixture를 동결 전에 올바르게 구성했다. 초기 조기 거절이 실패 manifest 기록을 건너뛴
문제는 지연 Writer와 try 내부 순수 사전 검증으로 고쳤다. TensorBoard 전용 job에는
OpenCV가 없으므로 D303의 fixture를 순수 JSON/표본 모듈로 추출했다. 실제로 cv2·MuJoCo·
torch·물리 worker import를 막은 별도 프로세스에서 16개 반례/대조와 event readback wrapper를 검사한다. 초기 두 실행은 실패를 확인한 뒤
중단했으며, 로그/JUnit을 최종 통과로 합산하지 않는다.

## 결과

**최종 관련 검사 562 passed / 0 failed / 0 errors / 0 skipped**다.
일반 선택 554개와 생성 검사 8개 항목의 합계이며, OpenCV 없는 선택 의존성 환경의
추가 17 passed는 중복 인수이므로 562에 더하지 않는다. JUnit과 해시는 아래 JSON에 있다.
소스 정책 SHA-256은 `35d83ef8911cbc545b6d794812d0d9443e99e1e8a14feb6499a71c801810271c`다.

작업 중 한 조회에서 P06 파일 대신 다른 작업 파일이 나타났다가 별도 복원 없이 돌아왔다.
HEAD/브랜치는 계속 동일했다. 그때 어떤 외부 작업이 접근했는지는 확인하지 못했다.
다른 파일을 덮어쓰지 않았으며, 복귀한 P06 변경 21개를 별도 소스 복사본과 SHA-256으로
보존했다. 커밋에는 검증한 명시적 파일만 별도 Git index로 넣는다. 정상 CI의 해당 SHA
검증 결과는 PR 답변 및 로컬 CI 기록으로 별도 확인한다.

- 생성 사례: 관계형 **12,000건** + 이벤트 재생/요약 불변식 **12,000건**.
  사례 수는 pytest 항목 수에 더하지 않는다.
- TensorBoard가 없는 새 프로세스에서 A303/F303/C303/D303 전체 묶음이 skip/xfail 없이
  통과했다. 설치 환경에서는 실제 EventAccumulator 수치를 원본 재생 수치와 비교한다.
- 변이 6종 모두 검출: `late_prefix` 2개, `policy_pin` 1개, `code_pin` 1개,
  `settle_window` 4개, `summary_trust` 1개, `eager_tensorboard` 1개가 의도대로 실패했다.
  모든 변이의 수집/실행 error 수는 0이다. 마지막 변이의 실패 원인은 의도적으로 재도입한
  TensorBoard import 오류이며, 이를 정상 코드 통과나 결함 수정으로 합산하지 않는다.
- 이전 CI `36736874190` 원본 로그를 회수했다. offline shard 1·3·4의 5+66+13=84개 실패가
  TensorBoard 미설치 오류였다. `.github/workflows/tests.yml`은 origin/main과 같은 Git blob
  `652a1462e59906feb2aa8a4a40f211f13109c356`이다. 의존성 목록도 변경하지 않았다.

이는 offline 코드·합성 event 검사다. 로컬 물리·렌더·학습·실제 모델 호출은 0회다.
새 연구 결과나 새 실제 snapshot이 없으므로 공용 TensorBoard 서버/UI를 열거나 변환하지 않았다.
Drive 작업·등록 bundle 변경·병합은 없으며 PR #303은 draft로 유지한다.
실제 실행 연결·새 raw 수집·현장 판정과 제3자의 독립 재검토는 별도다.
