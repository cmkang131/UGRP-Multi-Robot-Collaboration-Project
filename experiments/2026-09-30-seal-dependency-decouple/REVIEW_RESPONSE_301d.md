# PR #301 네 번째 검토 답변 — 재현성 검사

검토 원본은 [`c463b667`](https://github.com/kcm0127-dotcom/ugrp/blob/c463b667c4085b83168244f8582c6d985f551959/experiments/2026-09-30-seal-dependency-decouple/REVIEW_301d_astra.md),
검토 대상은 `b7f53d34e56407d64aea5ef74e41a07b46706911`이다.
2026-10-01에 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`를 먼저 병합했다
(merge `c8e3fe063edd550dd08467defba611ec12cb1603`). 두 P2를 한 묶음으로 수정했다.
모든 로컬 실행은 오프라인 재현성 검사이며 공용 호스트 잠금을 사용하지 않았다.

## 두 항목의 수정

| 항목 | 변경과 재현성 검사 |
|---|---|
| D1: CLI가 저장한 봉인 때문에 첫 재실행 거부 | CLI가 추적 전에 성공 봉인과 실패 보고서의 정확한 두 경로를 `output_artifacts`로 선언한다. 경로·실제 대상·중간 링크를 digest에 포함하고, 디렉터리 의존성과 자식이 보는 열거 결과에서 해당 파일만 제외한다. 이름·확장자 패턴이나 폴더 전체를 제외하지 않는다. |
| D2: 환경 복사 API 누락 | 환경 adapter의 `copy()`가 기존 읽기 hook을 거쳐 독립된 dict를 반환한다. `environ`은 문자열, `environb`는 bytes 키/값을 유지하며 복사한 모든 설정을 기록한다. 복사본 수정은 원래 환경에 영향을 주지 않는다. |

D1은 snapshot에서만 출력을 빼면 `len(os.listdir(...))`를 사용하는 코드의 입력이
달라질 수 있으므로, 자식의 `listdir`·`scandir`·Path 열거에도 같은 규칙을 적용한다.
도구 출력을 입력으로 읽거나 정적 입력으로 겸용하는 것은 거부한다. symlink를 통한
읽기도 거부하며, 출력이 디렉터리/symlink로 바뀌거나 중간 링크가 바뀌면 자식 시작 전에
거부한다. 자세한 계약은 [도구 출력 규칙](../../docs/runtime_provenance.md#도구-출력의-명시적-제외-규칙)에 있다.

## 재현성 검사 결과

결과 집계·환경·파일 해시는 `REVIEW_RESPONSE_301d_validation.json`에 기록한다.

- 기존 관련 13개 suite **401 passed / 13 strict xfailed**, 새 2개 suite **25 passed**.
  합계 **426 passed / 13 strict xfailed**, 실패·error·일반 skip은 0이다.
  13개 xfail은 변경하지 않은 301b 정적 API의 한계이며 runtime 수정 성공으로 세지 않는다.
  관련 검사에서 어떤 사례도 제외하지 않았다. 이번에 변경하지 않은 세션 실행기의
  별도 Mac 권한 제약 검사는 재실행하지 않았으며 이전 기록을 새 통과 수에 합치지 않는다.
- 수정 전 검토 반례: **3 failed / 1 passed / 6 deselected** (`--runxfail`).
  root 안의 CLI 출력 1개와 환경 복사 2개가 의도한 단언에서 실패했고,
  root 밖 출력 대조군은 통과했다.
- 수정 후 검토 301d **10/10**, 추가 출력·환경 복사 재현성 검사 **15/15** 통과.
  원본의 세 xfail을 제거했으며 함수·클래스 16개의 본문 AST는 검토 원본과 같다.
  기존 301/301b/301c 검사와 단언은 바꾸지 않았다.
- 추가 검사는 문자열/bytes 디렉터리 열거, Path 열거, 목록 길이의 동일성,
  비슷한 이름과 다른 폴더의 동명 파일, 출력 종류/링크 변경, 출력의 입력 사용 거부,
  문자열/bytes/한글 환경 복사와 모든 복사 항목의 기록을 확인한다.
- CI 목록은 **346 files / 8 shards**이며 두 새 검사 파일을 각각 정확히 한 번 포함한다.
  frozen fixture **3/3**, bundle v63 정적 재현성 검사와 registry 불변 검사도 통과했다.
- 변이 재현성 검사는 정상 대조군 **41 passed**, 검사 제거 **16/16 검출**이다.
  기존 11개에 출력 예약·열거에서의 출력 제외·출력 읽기 거부·환경 copy API·복사 항목
  기록 제거 5개를 더했다. 모든 변이는 관련 단언 실패로 검출했으며 수집/setup 오류와
  skip은 없다. 대조군과 변이의 반복 수를 정규 검사 통과 수에 더하지 않는다.

## 보존과 남은 범위

기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0`의 Git blob, 현재 HEAD의 Git blob,
존재하는 로컬 파일을 대조했다. 등록 5개·RGB JSON 65개·legacy source 6개,
**76/76 바이트 동일**이며 v6e source hash **85/85 일치**다. sparse로 없는 파일은
Git blob으로 검사했다고 JSON에 구분한다. `.github/workflows` 변경은 없고
`tests.yml`은 origin/main과 바이트가 같다.

기존 등록·runner 자동 전환은 없으며 이번 변경은 opt-in Python 재현성 검사 도구에
한정된다. native/자식 전체 추적, metadata·열거 순서·동시 수정, 불변 입력 강제,
실제 runner 연결은 후속 범위다. PR은 draft로 유지하고 병합하지 않는다.

검사 도중 공용 `.git/config`의 `core.worktree`가 다른 작업 폴더
`cap-t12-r3-delay`를 가리키는 상태를 관측했다. 실제 소스 파일은 이 작업 폴더에
그대로 있었으며 변이 대조군의 소스 해시도 일치했다. 이후 Git 작업에는
`--git-dir`/`--work-tree`로 이 작업 폴더를 명시했고 공용 설정은 수정하지 않았다.
이 관측은 `git-worktree-binding.json`에 따로 보존한다.

원본 로그·JUnit·변이·보존 감사는
`/Users/changmin/projects/ugrp/outputs/seal-review-301d-fixes-20261001/`에 있다.
raw는 로컬 보관이며 원격 백업이 아니다. 임시 변이 소스 복사본은 검사 종료 시 제거한다.
연구 실행 결과가 없는 재현성 검사이므로 TensorBoard 변환·서버 작업은 없고,
UGRP의 프로젝트 예외에 따라 Drive 작업도 없다.

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q --tb=short \
  tests/test_seal_v2_review_301d.py tests/test_seal_runtime_outputs.py
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q --tb=short \
  tests/test_seal_runtime_provenance.py tests/test_execution_dependency_contract.py \
  tests/test_seal_v2_review_301.py tests/test_seal_v2_fail_closed.py \
  tests/test_seal_v2_review_301b.py tests/test_seal_v2_review_301c.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_pair_v6.py tests/test_rgb_execution_bundle.py \
  tests/test_ci_sharding.py tests/test_ci_host_lock.py tests/test_agent_lock.py
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-seal-dependency-decouple/check_runtime_mutations.py --output /absolute/new-results
```
