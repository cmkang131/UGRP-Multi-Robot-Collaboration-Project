# PR #301 독립 검토 일괄 답변

대상은 기존 PR HEAD `2ff92e9fbeff1b90b0aa35104a9766753e67f94e`다.
검토 원문과 테스트는 `codex/review-301`의
`d21e0147fbc0829da3c9878877b4c5f5c83f865f`에서 읽었다.
원본 테스트 SHA-256은 `802873685f94d6ae23eb8a1dd3e261e1c43c1e1f159c2105c7a7ce5504086e3f`다.
제품 변경은 이 브랜치의 v2 구현에만 적용하며 기존 제어기·사전 등록·물리 설정은 유지한다.

## 지적 → 수정

| 지적 | 수정 | 검증 |
|---|---|---|
| R1 BLOCKER: wildcard가 `__all__` 하위 모듈 누락 | 새 `harness/python_source_closure_v2.py`에서 wildcard 대상의 로컬 Python 하위 트리를 전부 고정한다. 계산된 `__all__`나 미선택 자식도 제외하지 않는다. 기존 closure 파일은 수정하지 않는다. | 원본 STOP→MOVE 반례, 계산된 `__all__`, 상대 wildcard/namespace package, 새 자식 파일 추가 |
| R2 BLOCKER: 동적 loader의 대입/getattr/builtins 별칭 누락 | import 별칭·대입 연쇄·문자열 getattr·builtins loader·키워드 name을 추적한다. loader의 객체 저장·함수 전달·비상수 getattr 등 미해결 참조는 거부한다. 비상수/상대/fromlist 호출은 파일당 1개에만 기존 선언을 허용하며, 여러 미해결 호출에 한 선언을 재사용할 수 없다. | 원본 4개 STOP→MOVE 반례, 별칭 연쇄/키워드/대입식, fromlist, 선언으로도 허용되지 않는 미해결 참조 |
| R3 MAJOR: 파일 실행 시 같은 폴더 import 누락 | root와 모든 선언 진입점의 부모 폴더에서 가능한 로컬 후보를 모두 포함한다. 이 검색 규칙의 코드와 진입점 목록도 digest에 포함한다. `-m`/파일 실행 양쪽에 대해 보수적으로 고정한다. | 원본 `jobs/entry.py` 반례, root와 jobs에 같은 helper가 있는 경우 및 전이 sibling import |
| R4 MAJOR: JSON 객체 순서 의미 손실 | 선택 값의 hash는 중첩 객체 키 순서까지 보존한다. 외부 digest에 그 hash를 포함하며 receipt의 값/hash 일치도 재검사한다. schema는 문자열/null만 허용한다. | 원본 첫 명령 STOP→MOVE 반례, receipt 자체의 키 재정렬 거부, 기존 공백/선택 행 밖 재정렬 허용 |
| R5 MAJOR: 실제 runner는 비선택 행에도 의존 | 표준 catalog 선택 시 실제 `sim.workflow_manager.catalog` validator를 build/verify에서 그대로 사용한다. validator 소스도 필수 pin한다. 유효한 무관 행 편집만 허용한다. | 원본 missing-entry/duplicate-unused-id 2개, 비선택 행 필수 필드·id·entry 파일 삭제 |
| R6 MAJOR: 공통 launcher 누락 | `workflow_spec`에 manager·`sim_cli.py`·`ugrp_session.py`·`open_simulation.command`를 필수 추가한다. Python 전이 의존성도 고정하며 파일이 없으면 실패한다. | 원본 communication 명령 변경 반례, 공통 launcher 4개 각각의 변경/삭제 거부 |

실행 입력인지 불명확한 로컬 Python 후보는 빼지 않고 추가 고정한다. 소스 수 축소나
과거 검증 성공의 승계를 목표로 하지 않는다. catalog/launcher/기존 AST의 실제 파일은
수정하지 않으며 v2가 이 파일들을 더 정확하게 검사하도록 바꾼다.

## 선언·환경 경계 5개

[실행 버전 관리](../../docs/execution_versioning.md)의 **선언·환경의 명시적 제외 범위**에
각 항목과 실제 필요한 선언/별도 인수 조건, 테스트명을 적었다.

1. 문자열 subprocess worker: 미선언은 범위 밖, `entry_points` 선언 후 변경 거부.
2. MJCF include/mesh/texture: 부모만 고정하면 참조 자산은 범위 밖, 자식 `inputs` 선언 후 거부.
3. 선택 행 밖 defaults: 미선택은 범위 밖, 별도 selector 선언 후 거부.
4. live 환경 변수: v2가 캡처/비교하지 않음. 비밀이 아닌 실행 설정을 외부 등록/admission에서 비교해야 함.
5. Python/NumPy/MuJoCo 버전: 실행 기록·번들의 환경 identity로 기록하며 v2 digest로 고정/거부하지 않음. 기록과 환경 승인 검사는 구분함.

5개 xfail은 정상 통과하는 **제외 경계 테스트**로 바꿨다. 처음 3개에는 선언한 경우의
양성 대조를 추가했다. 기존 JSON/map/YAML/XML/MJCF/NPZ와 runner 주입의 선언/미선언
대조도 유지한다. 설치 버전 시험은 identity 응답 교체이며 실제 패키지 교체가 아니다.
이 경계를 고쳤거나 전체 환경 봉인을 구현했다고 주장하지 않는다.

## 테스트 파일 수용 범위

리뷰 파일을 복사하고 R1–R6의 **결함 재현 10개에서 xfail을 제거**했다. 행동 변경을
확인하고 원래 외부 digest가 이를 거부해야 한다는 핵심 단언은 유지했다.
표준 launcher가 이제 필수이므로 sandbox에 그 파일들을 넣었고, 실제 communication
fixture에는 전체 catalog가 존재 검사하는 entry 파일도 복사했다. 어떤 workflow 명령도
실행하지 않으며 `_runner_command`의 생성 결과만 비교한다.

기존 `test_execution_dependency_contract.py`의 fixture는 실제 표준 catalog schema·
필수 필드·존재하는 entry 파일을 갖추도록 수정했다. 기존의 무관 행 편집 허용 시험은
**유효한** 행을 추가하도록 바꿨다. schema 변조는 전체 catalog validator의 더 이른
거부 메시지를 기대한다. 검증 대상이나 기존 회귀 테스트를 삭제/skip하지 않았다.
검증기 소스가 2개 추가되어 해당 매개변수 검사도 2개 늘어난다.

리뷰 파일과 추가 `test_seal_v2_fail_closed.py`를 CI의 `TEST_PATTERNS`에 등록했다.

## 최종 검증 기록

최종 결과: **274 passed / 118.47 s**, 실패·오류·skip·xfail **0**.
기존 204개 + 검증기 소스 추가 검사 2개 + 리뷰/경계 검사 41개 + 추가 보강 27개다.
집중 검사 **103 passed / 49.79 s** 후 같은 소스로 전체 묶음을 실행했다.
두 실행에서 겹치는 검사를 중복 합산하지 않는다. 시간은 검사 기록이며 성능 비교가 아니다.

| 테스트 파일 | 최종 통과 수 |
|---|---:|
| `test_execution_dependency_contract.py` | 35 (기존 33 + 검증기 2) |
| `test_zone_pair_registered_source.py` | 22 |
| `test_zone_study_source_pinning.py` | 33 |
| `test_zone_pair_v6.py` | 43 |
| `test_rgb_execution_bundle.py` | 7 |
| `test_ci_sharding.py` | 66 |
| `test_seal_v2_review_301.py` | 41 (원본 38 + 선언 양성 대조 3) |
| `test_seal_v2_fail_closed.py` | 27 |

환경: 기존 Mac `.venv-sim-worker-mac`, Python 3.12.13, NumPy 2.5.2,
MuJoCo 3.12.0, pytest 9.1.1, macOS 27.2 arm64. 패키지 버전은 metadata로 조회했다.

모든 pytest 실행은 `scripts.run_ci_tests.run_locked`로 공용 잠금을 획득했다.
다른 작업이 점유한 동안은 테스트를 시작하지 않았다. 첫 전체 실행 요청(`full-01`)은
잠금 대기만 하다가 종료 코드 3으로 끝났고 실제 검사는 `full-02`에서 수행했다.
완료 후 자기 테스트 프로세스와 잠금을 반환했다. 다른 작업을 중단하거나 잠금을 풀지 않았다.

재현 명령:

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PYTEST'
import os, sys
from scripts.run_ci_tests import local_lock_root, run_locked
files = [
    'tests/test_execution_dependency_contract.py',
    'tests/test_seal_v2_review_301.py',
    'tests/test_seal_v2_fail_closed.py',
    'tests/test_zone_pair_registered_source.py',
    'tests/test_zone_study_source_pinning.py',
    'tests/test_zone_pair_v6.py',
    'tests/test_rgb_execution_bundle.py',
    'tests/test_ci_sharding.py',
]
env = {k: v for k, v in os.environ.items()
       if not k.endswith('_API_KEY') and k != 'GOOGLE_APPLICATION_CREDENTIALS'}
env.update(CI='true', PYTHONDONTWRITEBYTECODE='1')
raise SystemExit(run_locked([sys.executable, '-m', 'pytest', '-q', *files],
                            env, local_lock_root()))
PYTEST
```

추가 확인:

- 기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0` 대비 v6~v6e 등록 JSON **5/5**, RGB
  registry JSON **65/65**, 기존 closure/검증기/실행기 6개가 바이트 동일하다.
- 현재 v6e의 소스 **85/85 hash 일치**. 기존 역사 감사·현재 계약·RGB 검사도 위 묶음에 포함했다.
- 리뷰의 결함 함수 6개(매개변수 포함 10개)의 AST 본문은 원본과 동일하다.
  R6의 catalog entry fixture 복사 루프 1개만 추가했으며 원래 검증 단언은 그대로다.
- `git diff --check` 통과. CI 분할 목록 **331개 파일 / 8 shard / coverage_verified=true**;
  v2 기본 검사와 새 두 테스트 파일은 각각 한 번 포함된다.

[검증 JSON](REVIEW_RESPONSE_301_validation.json)에 실행별 집계·환경·검사 소스 hash·
원본 보존 hash·raw 로그/JUnit hash를 남겼다. raw는
`/Users/changmin/projects/ugrp/outputs/seal-301-fix-20260930/`의 로컬 보관이며 원격 백업이 아니다.
기존 `VALIDATION.md`/`validation.json`은 최초 구현 당시 기록으로 그대로 보존한다.

로컬 물리·렌더·모델 호출·학습·raw 삭제·과거 봉인 재작성·#292 수정은 없다.
새 연구 결과가 없으므로 TensorBoard 변환/서버와 Drive 작업은 하지 않는다.
최종 변경의 독립 재검토와 새 커밋의 GitHub CI는 별도 확인 대상이다. 수정자의 로컬 통과로
원래 BLOCK 판정이나 #292의 실행 승인을 대신 해제하지 않는다.
