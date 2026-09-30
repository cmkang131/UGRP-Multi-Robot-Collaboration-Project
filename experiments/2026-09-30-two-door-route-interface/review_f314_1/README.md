# PR #314 F314-1 수정과 main 통합

2026-10-01 KST. 기준 PR HEAD `994b269d97d05dd2159c1a78f2b9eae9955790f9`에
main `7e081d7047aa2df737cc1890c963b1d3a14302c0`을 merge했다. rebase/force push는 없다.
검토 원문은 `7623f3ca:experiments/2026-09-30-e2e-readiness/REVIEW_FIXES_2.md`의 #314 절이다.

## 원인과 수정

`tests/test_ci_fast_path.py`에 남은 PR별 자동 취소 금지 assertion이 main workflow와
모순되어 `ci-preflight`가 실패했고, 집계 `offline-regressions`도 실패했다.
[기존 실패 CI](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36724382660)의
로그와 같은 실패를 로컬에서 재현했다(11개 중 1개 실패, `preflight-before.txt`).

- `tests/test_ci_fast_path.py`와 `CONTRIBUTING.md`를 main 원본으로 복원했다.
  현재 안내는 PR의 새 커밋이 이전 실행을 자동 취소하는 main 정책을 그대로 설명한다.
- 충돌한 `experiments/2026-09-30-process-review/LITERATURE.md`도 main의 사용자 정정을
  보존했다. 로컬 실행 제한과 정상 GitHub CI를 구분한다는 양쪽 문서의 취지는 같다.
- `.github/workflows/*`는 편집하지 않았다. 병합된 workflow는 위 main과 바이트가 같다.
- T09a 계산 구현·기하 테스트·기존 실행 등록은 수정하지 않았다. 이전 검증 로그는 보존했다.

## 직접 검증

Python 3.12.13 기존 환경에서 `verify.py`로 물리·렌더·모델 import와 네트워크를 차단했다.
오프라인 테스트에는 PR #328에 따라 host lock을 잡지 않았다.

| 검사 | 결과 |
|---|---|
| 관련 회귀 전체 | **230 passed, 280 subtests passed**, 실패·오류·skip 0 |
| 두 문 경로 / 기존 passage / team jobs | 76 / 44 / 41 passed |
| keepout·고정 지도·catalog | 3 passed |
| 지정한 두 source-pinning 테스트 | 22 + 34 = **56 passed** |
| main 원본 CI preflight | 10 passed, frozen fixture 3개 확인 |
| end_neg 형상 제거 변이 | **8 failed / 68 passed**, 오류·skip 0 |
| end_pos 형상 제거 변이 | **9 failed / 67 passed**, 오류·skip 0 |

변이는 `_formation` 결과를 프로세스 메모리에서만 바꿨다. 실패는 누락한 운반자의
벽 충돌·문 통과 후 옆 이동·잘못 허용한 경로 assertion으로 검출됐다. 정상 코드에서는
동일한 검사들이 통과했다. 새 제어 로직은 없으며 D1의 독립 형상 검사 강도를 재확인했다.

v6e 봉인 소스 **85/85**가 등록 SHA-256과 일치한다. workflow와 지정 테스트를 포함한
**88개 파일**의 검사 전후 해시는 모두 같다. 지정한 두 테스트는 main과 바이트가 같고
직접 편집하지 않았다. `test_zone_study_source_pinning.py`에는 main이 추가한 transport
의존성 1개가 병합되어 이전 PR의 33개보다 검사 수가 1개 늘었다.

## 기록과 범위

- 원본: `/Users/changmin/projects/ugrp/outputs/2026-10-01-t09a-f314-1/`.
  `verification.json`에 부모 SHA, Python, 대상별 결과, 실패 검사 이름, 보호 파일과 raw 해시를 기록했다.
- 재현: 기존 Python으로 `verify.py --output <새 절대 경로> <pytest 대상...>`를 실행한다.
  변이는 `--mutation end_neg` 또는 `--mutation end_pos`와
  `tests/test_zone_own_executor_door_routes.py`를 지정한다. 두 변이의 종료 코드 1은 예상 결과다.
- push 후 정상 GitHub CI를 확인하고 그 최종 SHA·결과를 PR 댓글에 별도로 남긴다.
  위 로컬 통과는 원격 CI 통과를 대신하지 않는다. PR은 draft로 유지하고 병합하지 않는다.
- 로컬 물리·렌더·학습·모델 호출은 0회다. 새 실험/평가 코호트가 없어 TensorBoard 변환은
  하지 않았으며 정적 검사 수를 물리 성능 지표로 등록하지 않는다. 실제 두 문 통과·E2E는 미검증이다.
- Google Drive 작업은 없다. `/private/tmp`에 추출 디렉터리를 만들지 않았다.
