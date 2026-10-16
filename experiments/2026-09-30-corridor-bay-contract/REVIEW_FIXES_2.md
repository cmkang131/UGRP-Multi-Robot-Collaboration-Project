# PR #310 — F310-1 수정 (2026-10-01)

검토 원문은 `7623f3ca:experiments/2026-09-30-e2e-readiness/REVIEW_FIXES_2.md`의
#310 절이다. 검토 대상 `5d363335a286247a58d19652771b7ecddb21ef05`에
main `7e081d7047aa2df737cc1890c963b1d3a14302c0`을 충돌 없이 병합했다.
rebase·강제 push·PR 병합은 하지 않는다. 관련 검사가 끝난 뒤 병합 커밋을 만든다.

## 원인과 수정

F310-1은 기존 corridor admission의 결함이 아니라 workflow 복원 뒤 남은
CI 정책 테스트와 현재 개발 안내의 모순이다. 이전 GitHub run `36719543454`의
`ci-preflight`와 로컬 수정 전 unittest 모두
`test_new_push_preserves_queued_and_running_ci`에서 같은 assertion으로 실패했다.
로컬 수정 전 결과는 11개 중 1개 실패다.

`tests/test_ci_fast_path.py`와 `CONTRIBUTING.md`를 병합한 main의 바이트로 복원했다.
PR 범위 밖의 취소 방지 정책 테스트를 제거하고, 같은 PR의 새 커밋이 이전 CI를
취소한다는 현재 안내를 복원했다. 기존 CI 분기·실패 시 거절·집계 검사는 유지한다.
`.github/workflows/*`는 직접 수정하지 않으며 main과 바이트가 같다.
이전 `REVIEW_FIX.md`, 실행 로그와 receipt는 당시 기록으로 그대로 보존한다.

## 검증 범위

정상 코드의 관련 검사 결과는 **258 passed, 3 deselected, 280 subtests passed**다.
CI 분기·분할·선택적 host 잠금, corridor, executor·fake host, hard routes,
workflow manager와 지정한 두 소스 고정 테스트를 포함한다. 실패·오류·skip은 0개다.

로컬 검사는 기존 Python 3.12 환경을 재사용하고 PR #328에 따라 공용 잠금 없이 실행한다.
물리·렌더·모델 import 및 네트워크를 차단했다. 물리 테스트 두 개와 기존 sandbox에서
`ps` 권한 오류가 확인된 자식 정리 테스트 한 개는 로컬에서만 제외한다.
GitHub workflow와 CI의 테스트 선택은 변경하지 않는다.

실제 CLI의 corridor 거절 경로에 다음 메모리 변이를 대입했다. 소스 파일은 수정하지 않았다.

| 검사 | 결과 | 실패 의미 |
|---|---|---|
| 상위 `require_study_runtime` 검사 제거 | 22 failed / 1 passed / 31 deselected | 잘못된 선택 또는 복도가 기록·실행 단계에 도달함 |
| `require_door_runtime` 검사 제거 | 17 failed / 6 passed / 31 deselected | 문 없는 지도가 거절되지 않음 |

두 변이 모두 수집 오류·환경 오류·skip은 0개다. 정상 문 지도 양성 대조는 유지된다.
반복 실행의 검사 수를 서로 합산하지 않는다.

v6e 등록 소스 85개는 등록 SHA-256과 일치한다. 지정한
`tests/test_zone_pair_registered_source.py`, `tests/test_zone_study_source_pinning.py`는
병합한 main과 바이트가 같고, 이 수정에서 테스트 본문·assertion을 바꾸지 않았다.
main이 추가한 transport 소스 고정 사례도 그대로 검사한다.

원본 위치는 primary checkout의
`outputs/2026-10-01-cap-t10a-f310-1/`이다. 명령·Python 버전·검사 파일 해시·JUnit·로그와
변이 driver를 보존한다. 검증 요약과 원본 해시는 `review-fixes-2/verification.json`에 둔다.
raw 로컬 보관을 원격 백업으로 표현하지 않는다.

이 작업은 정적·fake 계약과 CI 회귀 검증이다. 물리 실행, 새 cohort, 모델 호출과
TensorBoard snapshot은 없고, UGRP 예외에 따라 Drive 작업도 없다.
`/private/tmp`에 archive 추출 디렉터리를 만들지 않았다.
PR은 draft로 유지하고 원격 CI 결과는 최종 PR 댓글에서 구분해 보고한다.
