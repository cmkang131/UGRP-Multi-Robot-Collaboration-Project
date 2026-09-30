# PR #303 세 번째 독립 검토 수정 — 2026-10-01

시작 HEAD `f55662896c310509db32e5ea1e451827ab5b40ab`, main 병합 대상
`26545c2499f94c3f99a5d650f7cc8ea992f24196`.
검토 원문은 `039bba05387746987ea74e494b0465cc4ec84a7d`의
`experiments/2026-09-30-e2e-readiness/REVIEW_303C.md` 전체를 읽었다.
그 커밋의 반례 파일을 가져와 11개 반례의 xfail을 모두 제거했다.

## 한 묶음으로 수정한 내용

- **C303-1 (P1): 원본 심판에서 성공을 다시 계산한다.** 선택 통계 필드
  `departures`와 `departed_unsettled_items`의 유무로 검증을 건너뛰던 분기를
  없앴다. 필수 원본 필드, 행의 신원·시간·개체 키, confirmation/departure 전이,
  최종 standing, 주문별 결과, 완료 시각과 trial 배송 행을 교차 검증한다.
  원본 이력으로 구성한 trial에서 최종 지표를 도출하고 기존 사본과 비교한다.
  필수 원본 누락·충돌은 INVALID이며 고정 계획의 분모에 비성공으로 남는다.
  심판 생성 전 HOST_ERROR/API 중단·not_evaluated에 배송이 없는 경우에는
  가짜 원본을 요구하지 않으며 성공도 허용하지 않는다.
- **C303-2 (P1): 여섯 열 전체와 내용이 모두 맞아야 연결한다.** 기존 로그의
  논리 run_id와 계획의 실제 run_id 대응은 유지한다. 선언된 run/trial/condition/
  seed/order/attempt 및 명시적 evidence_key를 확인한 뒤 dispatch 행동을 기존
  action 형식으로 투영하여 종류·인자·주문·역할·행위자·시각을 대조한다.
  입력은 request/call과 촬영 시각·프레임 번호·이미지 SHA·요청 시각·명령 이력 수·
  수신 목록을 대조하고, 보존한 이미지의 실제 바이트 해시 검사도 유지한다.
  완전한 정상 기록에는 빈 관계라도 dispatch/input 표가 필요하다. 소비 행이
  있는 부분 기록에서도 표 전체 누락을 무시하지 않는다. 호출 전 실패의 빈
  부분 기록은 별도로 허용한다. dispatch 인덱스는 실제 주문 키로 저장한다.
- **C303-3 (P2): 관계 비교에서 파일 행 순서를 제거한다.** 전체 복합키,
  사건 시각·개체와 행 내용 해시를 사용해 정규화한다. 상태 전이는 시간순으로
  재구성하며 같은 시각은 정규화 순서로 결정한다. 중복 개체·시각 키는 계속
  거절한다. 서로 다른 정상 행을 재배열해도 성공을 INVALID로 내리지 않는다.

## 재현과 검증 범위

정확한 집계·실행 명령·소스 및 로그 SHA는
[review_c303_verification.json](review_c303_verification.json)에 남긴다.

**최종 525 passed / 0 failed / 0 errors / 0 skipped.** 기존 선택 검사 441개,
독립 검토의 13개(반례 11개 + 정상 대조 2개), 추가 일반 검사 71개다.

- 수정 전 반례: **11 failed / 2 passed / 0 errors / 0 skipped**.
  xfail을 무시한 실행으로 기존 결함을 재현했다.
- 기존 선택 테스트를 모두 유지하고 새 검사를 일반 CI 목록에도 추가했다.
  기존 12,000개 생성 사례(mix/duplicate/drop/reorder 각 3,000개)는 그대로다.
  생성 사례 수는 pytest 테스트 항목 수에 더하지 않는다.
- 세 원본 관계의 독립 순열 **216개**, 실제 원본 게시 경로의 6개 순열,
  실패·재배송 이력을 포함한 **256개** 순열을 추가했다. 필수 원본 누락,
  여섯 키 열·명시적 복합키 충돌, 내용 충돌, 빈 필수 표 누락도 검사한다.
- 처음 넓힌 실행에서 새 fixture의 누락 때문에 2개가 실패했다. 원본 심판
  없이 성공을 만들던 이전 fixture에는 순수 심판 기록을 추가했고, 새 테스트의
  재봉인 도우미에 필요한 복제 evaluation도 제공했다. 기존 판정 assertion은
  약화하지 않았다. 최종 실행은 별도 `final.xml`·`final.log`로 보존한다.
- 메모리 안에서 생산 함수의 검사만 끈 변이 5개가 **모두 assertion 실패**를
  일으켰다(각각 1 failed / 0 errors). 선택 통계 우회, dispatch 내용 대조,
  입력 내용 대조, 필수 표 검사, 정규화 정렬이 각각 필요한 검사임을 확인했다.
  소스 파일이나 연구 원본을 덮어쓰지 않았다. 실행기는
  [review_c303_mutations.py](review_c303_mutations.py)다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-p06-evidence/redesign_test_driver.py \
  --junitxml=/absolute/new-final.xml

# 아래 실행은 해당 결함을 되살리므로 pytest 종료 코드 1이 기대값이다.
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-e2e-p06-evidence/review_c303_mutations.py \
  canonical_sort_bypass --junitxml=/absolute/new-mutation.xml
```

기존 Python 3.12 환경을 재사용했다. 오프라인 드라이버는 MuJoCo·torch·물리
worker import를 차단하고 스레드를 1개로 제한한다. #328에 따라 호스트 잠금 없이
실행했다. 연구 물리·렌더·학습·실제 모델 호출·실물 실행은 없다.

## 보존·Git·남은 범위

- v6e 등록 소스 **85/85**, 시작 HEAD의 경로에 `prereg`가 들어가는 JSON
  **57/57**의 바이트가 같다. 목록별 결과는 검증 JSON에 포함한다.
  등록 runner SHA-256은
  `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`다.
- `.github/workflows`는 main 병합으로만 반영했다. 파일 전체가 origin/main과
  같고, #332의 Ubuntu 두 job 15분 제한도 그대로다. 충돌이 난
  `LITERATURE.md`는 main의 더 상세한 CI 해석 정정을 유지했다.
- 합성 TensorBoard 이벤트를 실제 EventAccumulator로 다시 읽었다. 새 연구
  결과가 아니므로 공용 snapshot·서버·대시보드는 변경하지 않는다. 원본 로그와
  JUnit 위치는 `/Users/changmin/projects/ugrp/outputs/p06-review303c-fixes-20261001/`다.
  이 로컬 원본 전체를 원격 백업으로 표현하지 않는다. UGRP 예외에 따라 Drive
  작업도 없다.
- PR #303은 draft를 유지한다. 이 기록은 코드·합성 증거 검증이며 독립 재검토,
  실제 writer의 연구 실행 연결, provider 정산, 영상/UI 인수, E2E·PHYSICAL
  완료를 뜻하지 않는다. GitHub CI는 제출 커밋의 실제 check 상태로 별도 확인한다.
