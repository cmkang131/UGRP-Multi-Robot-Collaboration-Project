# PR #310 — CI 의존성 봉인 회귀 수정 (2026-10-01)

F310-1 수정 커밋 `8033d78deb1134b61277a31684accfd6dbc9c81b`의 정상 CI
`36750153176`에서 `ci-preflight`는 통과했다. 이후 offline shard 7/8의
`test_real_communication_workflow_omits_standard_launcher`가 실패했다.
원문은 `ValueError: undeclared dynamic import: harness/zone_own_team_host.py`이고,
로컬의 같은 검사에서도 1 failed로 재현했다. 이전 로컬 통과 258개에 이 신규 main
봉인 회귀 검사는 포함되지 않았으며, 그 결과를 전체 CI 통과로 확대하지 않는다.

## 원인과 수정

공용 관리자의 정적 의존성 검사는 함수 안의 lazy import도 보수적으로 따라간다.
`sim/workflow_manager.py → sim/zone_study_admission.py → harness/zone_corridor_contract.py`
경로에서 사용하지 않는 `create_own_executor` factory까지 따라가면
`zone_own_executor`의 lazy host import에 도달한다. 이 때문에 별개 `communication`
workflow에도 로봇 host의 동적 import 선언을 요구하게 됐다.

문 존재 검사와 `UnsupportedCorridor` 예외를 작은
`harness/zone_corridor_admission.py`로 옮겼다. 관리 경로는 이 모듈을 직접 사용하며,
기존 corridor 계약 모듈은 같은 함수·예외를 다시 노출하여 factory와 호출부의
인터페이스를 유지한다. 문 없는 지도 거절과 오류 문자열은 그대로다.
의존성 검사에서 도달 가능한 소스를 제외하거나 동적 import 검사를 약화하지 않았다.

새 회귀 검사는 실제 `communication` workflow의 의존성 계약을 만들고 재검증한다.
관리 입구 검사 소스는 포함되고, 무관한 corridor factory·executor·host는 포함되지
않아야 한다. 기존 pair workflow 검사는 실제로 사용하는 host·교사·provider 의존성을
계속 포함하도록 검사한다. 기존 main의 봉인 테스트는 수정하지 않았다.

## 검증과 보존

정상 코드의 확장 검사는 **400 passed, 3 deselected, 13 xfailed, 280 subtests passed**다.
이전 관련 검사에 `test_execution_dependency_contract.py`와 `test_seal_v2_*.py` 전체를
추가했다. `xfail` 13개는 main의 기존 명시적 한계 사례이며 새 통과로 세지 않는다.
로컬 제외 3개는 앞선 기록의 물리 host 2개·sandbox `ps` 제한 1개와 같다.

factory 모듈을 다시 참조하도록 AST 입력 바이트만 메모리에서 바꾼 변이는
새 회귀 검사와 기존 CI 실패 검사 **2개 모두 실패**했다. 수집 오류·skip은 없다.
상위 admission 제거 변이는 **22 failed / 2 passed**, 문 검사 제거 변이는
**17 failed / 7 passed**이며 각각 31개를 deselect했다. 소스 파일에는 변이를 쓰지 않았다.

원본은 primary `outputs/2026-10-01-cap-t10a-f310-1/closure-fix/`에 보존하고,
수정 전 GitHub job 로그·로컬 재현은 그 상위 폴더에 둔다.
같은 GitHub 실행의 Ubuntu runtime은 약 15분 뒤 취소됐다. 해당 로그에는
assertion 실패가 없으며 console 종료 직후 취소가 기록됐다. 이 작업에서 수동 취소하지
않았고 workflow 제한 시간도 바꾸지 않는다. 새 HEAD의 정상 CI 결과와 구분해 남긴다.
명령·Python·파일 해시·JUnit·로그·변이 driver와
`review-fixes-2/closure-verification.json`을 연결한다. 과거 기록은 덮어쓰지 않는다.

새 번들이나 cohort를 등록하지 않았고 물리·모델·렌더 실행은 없다.
워크플로는 main 그대로, v6e 고정 85개와 지정한 두 소스 고정 테스트도 그대로 유지한다.
오프라인 테스트에는 공용 host 잠금을 사용하지 않는다.
`/private/tmp` archive 추출 디렉터리는 만들지 않았다. PR은 draft로 유지하며 병합하지 않는다.
