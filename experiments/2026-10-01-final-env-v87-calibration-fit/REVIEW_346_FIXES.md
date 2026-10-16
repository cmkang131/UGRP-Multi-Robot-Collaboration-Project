# PR #346 독립 검토 대응 — R1–R4 한 묶음

대상은 `65ce28cf7da3c8c33de97a03b19cd1665b45f831`, 검토 원본은
`origin/codex/review-346`의 `612e7cbc28cfead3d26782897573da374fb7bb2e`다.
[검토 문서](REVIEW_346.md)와 [수치 대조 기록](REVIEW_346_VERIFICATION.json)은 원본 바이트로
가져왔다. 검토 테스트의 일곱 strict xfail은 일반 회귀 검사로 전환했다.

| 지적 | 수정 | 확인 |
|---|---|---|
| P1 R1: 수집 시점 증명 없이 held-out 통과 | 수집 확인 기록을 검증하는 기능이 마련되기 전에는 v88도 `INELIGIBLE` 수치 진단으로 제한한다. 축별·전체 검증 판정은 null이다. 소스 SHA나 날짜를 수집 시점 증명으로 쓰지 않는다. | 완전한 합성 명령/pose에서 `numerical_pass=true`여도 검증 판정은 null이고 시점 미확인 이유를 출력한다. 예외로 통과시키지 않는다. |
| P1 R2: 수집 조건 모순과 상위 실패 우회 | bundle·measurement·case result·pose의 check/지도/기록된 하중을 대조한다. v89 measurement는 고정 일정과 비교한다. case 경로도 상위 status·source_unchanged·전체 분모·case 완료 목록을 검사한다. 상위 목록과 실제 case 결과가 같아야 한다. | 검토의 조건 모순 세 가지와 상위 HOST_ERROR 반례, 완료 기록 누락·불일치, 개별 case 신원 검사를 별도로 확인한다. |
| P2 R3: 0 명령 누락을 0으로 보충 | 일정에 명시된 tick 집합이 실제 발행 tick에 모두 있는지 값 비교 전에 확인한다. coast의 0 명령도 필수다. | coast 명령 90개 삭제 반례를 거부한다. 일정 밖 초기 hold 명령을 모두 제거한 정상 자료는 허용하고, 첫 coast 명령 하나를 더 빼면 거부한다. |
| P2 R4: 상위 완료 기록의 해시 누락 | 상위 완료 기록과 수집 전체의 case 결과를 입력 manifest에 담아 재검사한다. CLI가 읽는 동결 B·후보·후보 해시 근거도 재검사한다. | root/case 진입 모두 상위 기록 변경·삭제를 검출한다. CLI 출력에도 상위 result 해시가 들어간다. |

## 보존과 판정 범위

- criterion A/B와 r1–r4 산출물 등 기존 기록 24개의 SHA-256과 바이트를 대상 HEAD와 비교해 보존한다.
  수치 적합·기준·후보 정정이 아니라 입력 검증 수정이므로 r5를 만들지 않는다.
- A는 실패로 유지한다. 코드가 A를 먼저 읽은 사실과 독립적으로 시점이 고정된 사전 등록 증거를
  구분하도록 README를 바로잡았다. A는 r3와 함께 `bedcc99d`에 처음 커밋됐으며 이전 시점의
  독립 확인 기록은 없다. 동결 파일 안의 과거 문구는 바꾸지 않았다.
- r1의 `params.motion`은 전체 null이 아니라 회전 탐색치가 남은 PARTIAL 객체다.
  전진/측면 및 stop 누락 때문에 기존 로더 사용은 계속 차단된다. r2–r4의 `params.motion`은 null이다.
- r4는 `CANDIDATE_UNVALIDATED`다. 회전 후보·실제 새 held-out 자료·수집 확인 기록 검증·학생 로더
  연결은 여전히 없다. 이번 변경은 수집 확인 기능을 완성했다고 주장하지 않는다.
- 최신 main `2c45b137c480eecff3dac871277cf48914dd5cf4`는 이미 대상 HEAD의 조상이라 추가 병합이
  필요 없었다. 기본 체크아웃의 다른 작업 변경은 건드리지 않았다. PR #346은 병합하지 않는다.
- 제어기·`.github/workflows`·CI 시간표 변경, 로컬 물리·렌더·모델 호출은 없다.
  새 테스트를 `scripts/run_ci_tests.py`의 기존 CI 목록에 추가했다.

## 검증 기록

수정 전 검토 검사는 **10 passed / 7 strict xfailed**였다.
최종 관련 오프라인 검사·해시·원본 위치는 [검증 요약](REVIEW_346_FIX_VERIFICATION.json)에 남긴다.
기존 v89 raw의 새 CLI 출력은 `TRAINING_SMOKE`, 세 축/전체 null, 종료 코드 2이며
저장된 r4의 모든 축 수치와 판정이 정확히 같다. 재적합하지 않았다.

로컬 로그는 `/Users/changmin/projects/ugrp/outputs/pr346-review-fixes-20261001/`에 보존한다.
원본 raw를 수정하거나 원격 백업한 것이 아니다. 새 실험·학습·평가 코호트가 없고 기존 보고서의
채점 회귀만 확인했으므로 TensorBoard를 중복 변환하거나 새 snapshot으로 등록하지 않았다.
기존 [r3/r4 TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1001-v89-consumer-%28r3%7Cr4-final%29%2F#timeseries)는
참고 링크이며 이번 작업에서 다시 열거나 화면 확인하지 않았다.
`/private/tmp` extraction 디렉터리는 만들지 않았다.

이 기록의 검증은 수정 작성자의 오프라인 검사다. 수정 후 독립 재검토·수집 시점 확인·held-out
성공이나 물리 성공을 대신하지 않는다. 푸시 뒤 같은 HEAD의 CI가 끝난 결과와 지적별 대응은
PR #346의 한국어 댓글 한 건에 기록한다.
