# PR #316 — Batch E 지적 일괄 수정

대상 검토: [PR #321](https://github.com/kcm0127-dotcom/ugrp/pull/321)의
`REVIEW_E2E_BATCH_E.md`, [#316 검토 댓글](https://github.com/kcm0127-dotcom/ugrp/pull/316#issuecomment-5911327446).
검토 대상 소스는 `8d755a5a69dd03fd9eb202407665b2b0890ed54d`다.
수정 전에 `origin/main` `892e5ae1550baa0790173380f58764cd44157a7a`를 작업 브랜치에
병합했다. 충돌 없이 양쪽 CI 검사 목록을 보존했다.

## 지적 → 수정

- **E316-1:** 중간 end는 `transition`만 허용한다. 마지막 end의 phase·leg·시각은
  terminal과 같아야 한다. 완료는 마지막 leg의 `done`, `sequence_done` end,
  `unconfirmed / PAIR_SEQUENCE_DONE` terminal 조합만 허용한다. 실패는 `failed` end와
  `failed` terminal, 비어 있지 않은 실패 이유를 요구한다. terminal도 다른 row와 같은
  유한·음수 아닌 숫자 시각, 정수 leg 범위 검사를 받으며 bool은 숫자로 받지 않는다.
  손상 기록은 `evidence_incomplete`, 분모 1, 전체 PASS 0으로 남긴다.
- **E316-2:** 모든 receipt에 frame ID·SHA-256·capture 필드를 요구한다. 첫 소비 이전의
  leg 0 `approach`에서는 세 필드가 모두 명시적인 null인 경우만 허용한다. 필드 누락,
  일부 null, 숫자 타입 위장, 비유한 시각은 거부한다. abort가 오래된 마지막 영상을
  보존할 수 있으므로 모든 실패 receipt에 새 영상의 TTL을 강제하지 않는다.
- 재파지 `grasp/start`는 terminal의 성공·실패와 관계없이 해당 시점까지 **실제 소비한**
  자기 leg의 `frames` 항목을 참조해야 한다. ID·SHA·capture·report·fix가 그 소비 기록과
  일치해야 하며, `look 시작 ≤ fix ≤ capture ≤ report ≤ receipt` 순서와 발행 명령 증가를
  검사한다. 지연 fix 시각에 해당하는 이전 소비 capture도 필요하다. 아직 소비하지 않은
  뒤쪽 frame이나 다른 leg의 입력은 참조할 수 없다.

`frames`는 전체 촬영 목록이 아니라 기존 `PairExecution.save`의 소비 목록이다.
따라서 재파지 이외의 receipt는 관찰한 마지막 영상의 메타데이터 형식을 검증하고,
재파지에서는 위의 소비 참조를 추가로 요구한다. 이 검사는 JSON 안의 연결을 감사한다.
실제 JPEG bytes와 provider 추정의 진실성은 별도 raw manifest·boundary audit 대상이다.
실제 provider가 fix 입력을 이 목록에 남기지 못하면 기록 불충분이며 성공으로 승계하지 않는다.

검토의 원래 8개 반례와 더불어 종료 enum·타입·시각, 개별 필드 누락·null,
소비 순서·다른 leg·capture/fix/report 모순을 회귀로 추가했다.
수정 전 38개 fake-port 검사는 유지한다. 초기 null과 정상 완료의 양성 대조,
기존 8종 실패의 양쪽 취소·정지·분모 검사도 유지한다.

## 소스 고정·CI·검증 범위

기존 등록 JSON·봉인·controller/provider/runner 소스는 바꾸지 않았다.
변경 코드는 등록 closure 밖의 선택형 출력 기록기와 그 검사다.
원래 `VERIFICATION.json`, validation-01–04 및 독립 검토 raw는 덮어쓰지 않는다.
새 raw는 `/Users/changmin/projects/ugrp/outputs/p04-chain-contract-20260930/review-fixes-01/`과
`review-fixes-02/`에 로컬 보관한다. 원격 백업이 아니다.

사용자 지시에 따라 README와 P04 과제문의 범위를 바로잡았다. 로컬 물리·렌더·실제 모델
호출은 하지 않고 일반 GitHub CI는 정상 실행한다. CI 취소나 CI 생략 커밋은 사용하지 않는다.
이전 `VERIFICATION.json`의 remote_ci는 이전 제출 이력이며 현재 방침이 아니다.
기존 sparse 규칙에 빠진 frozen fixture 3개는 추적된 원본 그대로 복구했다.

수정 전 소스의 복사본과 기존 validation-04 trace로 검토의 손상 8개를 직접 재현했다.
합성 양성 대조 1개와 손상 8개가 모두 `valid=true`, 분모 1, 전체 PASS 1을 반환했다.
이것은 결함 재현이며 실제 운반 성공이 아니다. `red-counterexamples.json`에 보존했다.

첫 수정 검증(`review-fixes-01`): 관련 11개 모듈 **377 passed / 2 failed**, 338.41초.
두 소스 고정 모듈과 새 손상 반례 46개는 통과했다. 실패는 아래와 같이 보완했다.

- 기존 `drop_phase` 반례: 행을 홀짝 위치로 나눠 end outcome을 읽으면 삭제 뒤 start를
  end로 오인해 `UNCLOSED_PHASE`를 일반 필드 오류로 덮었다. `edge == end`인 행을 직접
  골라 기존 오류 정보를 유지한다. 손상 trace를 PASS로 받아들인 실패는 아니다.
- 새 null 양성 대조: fake 입장 직후 이미 hold 명령으로 첫 receipt가 기록돼 있었으므로
  그 뒤 `last_obs`를 비워도 기존 receipt는 null이 되지 않았다. 명시적 pre-capture JSON
  양성 대조로 바꿨다. 실제 controller/admission 동작을 수정하지 않았다.

실패 JUnit·stdout과 첫 소스 해시는 보존하고 같은 11개 모듈을 새 `review-fixes-02`에서
재검증했다. **최종 결과: 11개 모듈 379 passed / 0 failed / 0 skipped, 336.36초.**
P04 모듈 85개(기존 38 + 새 47)를 포함한다. 필수
`tests/test_zone_pair_registered_source.py` 22개와
`tests/test_zone_study_source_pinning.py` 33개도 모두 통과했다.
검사 전후 소스·fixture **29개 SHA-256이 전부 일치**했다.
등록 JSON 53개에서 찾은 소스 경로 87개와 비교해 이번 수정과 겹치는 경로가 없었다.
기존 등록·소스 pin·봉인을 수정하거나 기대 해시를 새로 계산해 덮지 않았다.

환경·모듈별 결과·실패 이력·소스 및 raw 해시는
[REVIEW_FIXES_VERIFICATION.json](REVIEW_FIXES_VERIFICATION.json)에 보존했다.
공용 잠금 아래 기존 `run_ci_tests.main`의 TEST_PATTERNS를 이 기록에 나열된
11개 모듈로 한정해 실행했다. 잠금 대기로 시작되지 않은 호출은 검사 횟수에 넣지 않았다.
일반 PR CI는 이 변경을 push한 뒤 별도로 확인하며, 로컬 통과를 원격 CI 통과로 표현하지 않는다.

실제 물리·렌더·provider/모델·새 학생 코호트는 실행하지 않았다. 전이 계약과 손상 증거
거부 검사만으로 실제 운반 성공을 주장하지 않는다. 새 실험 코호트가 없어 TensorBoard
변환·서버·viewer는 시작하지 않았다. Google Drive 작업도 없다.
실제 runner의 observer 연결, 최종 provider/평가 합성, 새 출발 물리 인수와 독립 재검토는 별도다.
