# PR #246 CI scene receipt 수정

기준 HEAD: `19b3a7b242ccecf63ac5087ba122b1cb559d0991`. 검토 2의 v6 변경 위에 적용한
추가 수정이며 프로젝트 커밋을 만들지 않는다. 수정 코드는 `tests/test_zone_pair_v5.py`뿐이다.
기존 검토 2 기록은 상위 디렉터리에 보존했다.

## 원인과 재현

CI에서 실패한 `current_source_fixture-dev09/dev10`은 subprocess prepare와 바이트 복사를
이미 통과한 뒤, 테스트 마지막의 `validate_scene`에서 실패하는 구조였다. `current_registration()`은
scene/grasp **소스 계약**만 현재 파일로 바꾸며, `scene_instances`는 macOS에서 등록한 원본 그대로다.
그 합성 fixture를 모든 호스트에서 실행 가능한 scene이라고 가정한 테스트가 잘못됐다.

`TaggedCargoZoneScene._resolve`는 `catalogue_record()['sha256']`를 scene config에 포함한다.
카탈로그는 long_beam만이 아니라 tri_frame의 sin/cos 기반 좌표까지 직렬화하며, 플랫폼 libm의
마지막 비트 차이도 카탈로그와 resolved scene 해시를 바꾼다. 기존 `test_zone_start_dock.py`는
이미 이 차이에 따른 거부를 검사하지만 v5 테스트에는 같은 구분이 없었다.

등록 카탈로그 해시는 `89245cca1497da4d6537eeed3dc7160882b006e0922542c2a0a7a3a23f926c6a`다.
`tri_frame.parts[0].center[1]`을 `0.08660254037844388`에서 `0.08660254037844389`로
1 ULP만 바꾼 정적 입력으로 **수정 전 동일한 두 테스트가 309행에서 실패**했다.
[수정 전 로그](before-fix.log)와 [JUnit](before-fix.xml)을 보존했다. 이것은 플랫폼 차이의
통제된 반례이며 Ubuntu libm의 실제 출력값을 측정한 결과로 표현하지 않는다.

[probe.py](probe.py)는 실제 scene 생성의 파일 읽기를 추적한다. 사용한 프로젝트 파일은 모두
존재하고 skip-worktree 파일과 겹치지 않았다. sparse 제외 파일 1,555개/984,923,280 bytes는
미디어·압축 기록·문서이며 Python/JSON 소스 누락은 0개다. 관련 pair-dev/v6 디렉터리의 제외 파일도
없다. 먼저 필수 입력 누락을 배제한 뒤, 아래처럼 제외 파일 전체를 임시 복원한 대조군도 실행했다.
scene 해시 대상은 `config`와 `map`이며 checkout 절대 경로는 포함하지 않는다.
[경로·해시 진단](diagnosis.json)에 실제 읽기 목록과 두 seed의 원본/변형 결과를 남겼다.
Ubuntu 자체 실행과 GitHub CI 재실행은 수행하지 않았다.

추가 대조군에서는 skip-worktree 1,555개 파일을 HEAD blob에서 임시 복원해 추적 파일
**6,743개 전체가 실제로 존재**함을 확인했다. 요청한 `git checkout --ignore-skip-worktree-bits`는
공유 `.git/.../index.lock` 쓰기 제한으로 실패하여, read-only `git archive HEAD -- <누락 경로>`로
기존 파일을 건드리지 않고 같은 바이트를 복원했다. 수정 전 HEAD의 원래 문제 테스트 두 개를
그대로 불러 실행해 macOS 전체 파일 조건에서도 통과함을 확인한다. 따라서 sparse 누락이
문제의 두 테스트를 숨긴 원인은 아니다. [전체 파일 대조군](full-checkout.json),
[원래 테스트 호출](full_checkout_test.py), [로그](full-checkout.log), [JUnit](full-checkout.xml)을 따른다.
테스트 후 제가 만든 복원 사본만 SHA-256 확인 후 제거하고, 원본과 기존 작업 파일은 유지한다.

## 수정 및 보존

- prepare 테스트는 기존 subprocess의 physics/model import 차단, manifest 상태, 원본 바이트 복사,
  model_calls=0 검사를 유지하고 **scene_instances를 재등록하지 않았음**을 추가로 확인한다.
- 별도 scene guard 회귀 6개(dev09/dev10 × native/registered/one_ulp)를 추가했다.
  native 카탈로그 외에 등록 당시 카탈로그와 1 ULP 변형을 모든 호스트에서 각각 통과시킨다.
  고정 카탈로그는 정확히 승인하고 다른 해시는 정확한 오류로 거부해야 한다.
- native mismatch를 허용하는 검사 분기 전에, 카탈로그 이외의 모든 scene 필드가 동결된 해시와
  일치함을 독립적으로 검사한다. 임의 scene 변경을 플랫폼 차이로 숨기지 않는다.
  두 경로 모두 spawn 변조도 별도의 구조 검사에서 거부해야 한다.
- 과거 prereg와 카탈로그는 등록 변경 커밋
  `3ea2edc08e5addafaf3cedc934c463ad8e1635c8`의 `git show <commit>:<path>`로 읽는다.
  기존 provenance 감사는 10개 과거 버전의 소스·지도·입력 blob과 seal을 계속 검증한다.
  과거 Python을 현재 인터프리터로 실행해 역사적 등록을 재해석하지 않는다.
- expected hash, 과거 prereg, `validate_scene`, 카탈로그/직렬화 규칙은 변경하지 않았다.
  다른 플랫폼의 scene을 물리 실행에 허용하거나 해시를 반올림하지 않는다.
  v6 동작/임계값/조건 플래그도 이번 추가 수정에서 그대로다.

## 검증

선행 집중 검증: **102 passed / 0 failed** (v5, registered-source, dock).
최종 전체 관련 검증은 [run_tests.py](run_tests.py), [pytest.log](pytest.log),
[pytest.xml](pytest.xml), [test_execution.json](test_execution.json), [validation.json](validation.json)을 따른다.
`OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`, 물리 step/실제 모델 worker/네트워크 차단과
Python 자식 step tripwire를 사용한다. `.pytest_tmp`는 finally에서 제거한다.
이 기록은 오프라인 코드 회귀이며 물리 실험·provider 검증·새 코호트 성공이 아니다.

최종: **80개 파일, 2793 passed / 0 failed / 2 skipped, 382 subtests passed** (335.26초).
Skip 2개는 물리 step이 필요한 기존 host 테스트다. 전체 파일 존재 대조군은 수정 전 HEAD 테스트
2개를 포함해 **104 passed / 0 failed / 0 skipped** (23.11초)다. 복원한 1,555개 사본은
SHA-256 확인 후 모두 제거했고 원래 sparse 파일 집합으로 복구했다.
양쪽 실행 모두 step·실제 worker·네트워크 sentinel 0, Python 자식 step 시도 0이다.
`.pytest_tmp` 제거와 HEAD 불변을 확인했다. v6 소스 해시 65개와 기존 검토 2 변경을 다시 확인했으며,
prereg SHA-256은 `a12ebaa29d628955f29a968aa68e1b3723996e4f6cb502543ce4bfe4199f2ca5` 그대로다.
