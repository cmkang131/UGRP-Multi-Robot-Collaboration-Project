# #308 독립 검토 B1/B2 일괄 수정

검토 대상은 `5411f5e8d29186c00b44c2731e9915583da39aae`, 근거는
[Batch B 독립 검토 #317](https://github.com/kcm0127-dotcom/ugrp/pull/317)와
[#308 검토 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/308#issuecomment-5911114864)이다.
수정 전에 fetch한 `origin/main` `c12796676802ab54cad2f0635e3e96e911691c76`을 병합했다.
충돌은 없었으며, 아래 수정까지 같은 병합 커밋에 담는다.

## 지적 → 수정

- **B1, 기존 v6e 소스 고정 검사 실패:** 최초 변경의 `zone_study_integration.py` 11줄을
  제거해 main·기존 등록의 원본 바이트로 복원했다. 파일 SHA-256은
  `5997f0b431fa85c4d5df51f96297924c7f0c9df63b052d853f963662ad997d06`이다.
  기존 등록의 소스 85개를 모두 원래 해시와 비교하는 회귀를 추가했다.
  등록 JSON, 기존 소스 해시, 번들·workflow·prompt·동결 fixture는 바꾸지 않았다.
  usage 보정은 현재 v6e 고정 목록 밖의 `zone_study_llm_transport.py`로 옮겼다.
  실제 모델 실행의 source closure에는 이 transport가 이미 포함되어 있으므로,
  새 실행 번들은 변경된 코드 해시를 기록하며 과거 성공/승인을 승계하지 않는다.
- **B2, 정상 usage도 unknown으로 표시:** `known_total`이 `dict`뿐 아니라
  `CallReply`의 읽기 전용 `Mapping`을 허용한다. 기존 정수·음수·누락·총합 검증은
  유지한다. 본연구 원장을 쓰는 transport에서 정상·거절 응답 모두 DB와 같은
  기준을 쓴다. 명시적인 0/0/0도 기존 DB 규칙대로 known이다.
  로컬 billed token/SIM 비용, 일반 fixture 및 기존 pilot의 의미는 보존한다.

## 회귀 범위

- 정상 500/100/600, usage 없음, 총합 불일치, 명시적 0/0/0, 부분 usage ×
  정상·지연(censored)·비정상 finish(length)·오래된 request ID(stale): 20개.
  실제 client/request builder/scheduler/driver를 fake wire에 연결한다.
  raw 응답 → send 행 → SQLite → scheduler → 최종 결과의 값·known 표시·
  exact/lower_bound와 unknown charge를 call/request ID로 연결해 대조한다.
  지연·거절 응답은 행동·메시지를 실행하지 않는다.
- 읽기 전용 `CallReply.provider_usage`를 직접 판정하는 양성 회귀 1개.
- v6e 등록 소스 85개의 바이트 보존 회귀 1개.
- transport의 코드 해시가 바뀌면 실제 실행 번들 해시도 바뀌는 회귀 1개.
- 기존 4조건 × 3 seed × 2 speech profile의 24개 다회 검사에서도
  정상 usage의 scheduler/result known 및 exact 표시를 추가로 대조한다.

## 검증 기록

드라이버·두 source-pin 파일의 1차 검사 **232 passed**, 관련 13개 파일/선택 검사의
최종 결과 **702 passed**, 실패·오류·skip 0이다. 새 회귀는 23개다.
명령·파일 해시는 [review_fixes_verification.json](review_fixes_verification.json)에 기록했다.
수정 전 원본과 중간 테스트 helper의 ID 연결 오류도 삭제하지 않고 보존했다.
최초 helper는 결과의 request ID와 call ID를 혼동했으므로 그 실패는 제품 결함 수에
넣지 않는다. 수정 전 정상·지연·stale 응답의 known 오류, 읽기 전용 매핑 거절,
v6e 소스 해시 불일치는 별도로 재현했다.

공용 `scripts.run_ci_tests.run_locked` 잠금을 사용하고 다른 작업의 잠금·프로세스는
변경하지 않았다. 모든 pytest raw와 새 더미 SQLite/JUnit은
`/Users/changmin/projects/ugrp/outputs/e2e-p05-dialogue/review-fixes-20260930T122615Z/`에
로컬 보존한다. 원격 raw 백업을 뜻하지 않는다.

정상 GitHub CI를 수행하며 취소·건너뛰기 표식은 사용하지 않는다. 최종 HEAD의
CI 상태는 PR 댓글에 별도로 보고한다. 물리·렌더·학습·실제 모델 호출은 없고,
실제 대화 효과·운반 성공·과금 정산을 주장하지 않는다. 새 실험/학습/평가 코호트가
없으므로 TensorBoard snapshot/서버를 만들지 않았고 Drive 작업도 없다.
