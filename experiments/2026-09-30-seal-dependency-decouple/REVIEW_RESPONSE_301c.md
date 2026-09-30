# PR #301 세 번째 검토 답변 — 재현성 확인

검토 원본: [`3abefe23`](https://github.com/kcm0127-dotcom/ugrp/blob/3abefe23dae88dd17976ad4bd237fdcb4281f850/experiments/2026-09-30-seal-dependency-decouple/REVIEW_301c_astra.md).
검토 대상은 `cea627c539873b60775db6df146254ab077cec0c`였다.
2026-10-01 시작 시 main `6f766ecaa590b21d3d4b8763ee88a8c2eea4b67d`를
병합했다(merge `da2d316336c9d0a0ff4a92a04997b73a18136ff6`).
변경은 기존 `codex/seal-dependency-decouple` worktree에서 한 묶음으로 수행했다.
물리·렌더·모델·학습은 실행하지 않았고 공용 호스트 잠금을 사용하지 않았다.
잠금 단위 검사는 임시 경로와 더미 Python 프로세스만 사용한다.

## 지적별 수정

| 지적 | 수정과 재검증 |
|---|---|
| C1 P1: symlink/.. 실제 파일 누락 | `abspath`로 먼저 경로를 줄이는 처리를 없앴다. 절대 위치로 기준을 붙인 사용 경로를 보존하고, 중간 링크와 링크 target 안의 링크를 순서대로 확장한 뒤 `..`을 처리한다. `os.path.realpath`와 최종 결과를 대조하고 사용 경로·실제 경로·전체 링크 binding·파일 hash를 함께 기록한다. open/Path/os.open의 실제 입력 변경 3개와 링크 변경 1개를 거부한다. |
| C1 P2: 무관 파일 차단 | 실제 대상 기준으로 guard를 비교한다. `alias/../payload.txt`와 문자열상 비슷한, 읽지 않은 root의 `payload.txt` 변경은 허용한다. 같은 실제 대상의 다른 경로 표기도 별도 두 사례에서 허용한다. |
| C2 P2: __main__ 의미 변경 | coverage.py와 runpy의 실제 모듈 실행 방식을 적용했다. `ModuleType('__main__')`을 등록하고 그 전역 공간에서 실행한다. 직접 Python 실행과 같은 자기 import·pickle의 2개 검사, 종료 콜백까지 모듈을 유지하는 추가 검사를 통과해야 한다. |
| B1: 디렉터리 이름만 읽는 두 사례 | 이번 요청에 따라 이 부분까지 지원 범위를 넓혔다. `os.listdir`·`os.scandir`를 별도 `directories` 의존성으로 모으고 이름·종류·링크 target·부재를 확인한다. 추가/삭제/종류/링크 변경과 새 디렉터리 조회를 거부하고, 이름만 조회한 파일의 내용 변경은 허용한다. 열거 순서·stat·native read 전체를 지원한다는 뜻은 아니다. |
| 일회 종료 검사 실패 | 기존 코드는 leader의 wait 뒤 process group을 단 한 번 조회했다. 그룹 소멸이 늦게 관측되면 정상 종료도 `cleanup unconfirmed`가 된다. 실제 소멸을 최대 5초 동안 확인하고, 끝내 확인하지 못하면 잠금 유지·오류를 그대로 적용한다. 가짜 시계와 지연된 조회 결과로 이 경로를 결정적으로 재현한다. |

참고 구현과 채택 범위는 [runtime_provenance 참고 자료](../../docs/runtime_provenance.md#참고-자료와-채택한-방법)에
ReproZip 링크 순회, Python realpath, coverage.py 실행기, runpy 공식 문서를 연결했다.
원 도구를 설치하거나 OS 수준 추적을 실행한 결과로 표현하지 않는다.

## 검증

최종 집계와 파일별 hash는 `REVIEW_RESPONSE_301c_validation.json`에 있다.

- 직접 관련 13개 suite: **401 passed / 13 strict xfailed**, 실패·일반 skip·error 0.
  runtime **68/68**, 301c **14/14**(이전 예상 실패 9개 포함), 종료/잠금 **24/24**다.
  원래 종료 코드 7 사례도 통과했으며 어떤 검사도 skip하지 않았다.
- 추가로 넓혀 실행한 **변경 없는** `test_ugrp_session.py`는 **7 passed / 6 failed**다.
  이 환경이 `/bin/ps` 실행을 금지해 두 사례에 `PermissionError`가 직접 기록됐고,
  나머지 네 사례는 같은 세션 시작 경로에서 기록 파일을 기다리다 실패했다.
  별도 최소 실행에서도 `/bin/ps` 거부와 세션 기록 부재를 재현했다. 해당 실행기와
  테스트는 `origin/main`과 동일하며 이번 수정 대상이 아니다. 건너뛰거나 검사 결과를
  바꾸지 않았고, **전체 확장 실행은 408 passed / 6 failed / 13 xfailed**로 보존한다.
  직접 관련 suite의 통과와 환경 제약에 따른 추가 실패를 섞어 전체 통과로 보고하지 않는다.
- frozen fixture **3/3**, bundle v63 정적 검증과 registry 불변 검사 통과.
  CI 목록은 **342 files / 8 shards**이며 301b·301c가 각각 정확히 한 번 들어간다.

- 수정 전 리뷰 14개: **5 passed / 9 failed** (`--runxfail`). 9개 모두 리뷰에서 지적한
  경로·정상 스크립트·디렉터리 사례였다. 원본 로그를 보존했다.
- `tests/test_seal_v2_review_301c.py`는 원본을 가져와 xfail 장식자와 helper를 제거했다.
  원래 본문과 실패 조건은 유지했다. 새 CI 목록에 포함하며 skip으로 바꾸지 않았다.
- `tests/test_seal_v2_review_301b.py`는 `13afa3dc`의 원본 바이트를 그대로 가져왔다.
  정적 API의 기존 13개 strict xfail은 별도 한계로 유지하며, 새 runtime의 수정 성공으로
  세지 않는다. 원래 runtime 56개도 유지하고 경로·종료·디렉터리 검사 12개를 추가했다.
- 런타임 변이: 정상 대조군 **27 passed**, 검사 제거 **11/11 검출**. 각 변이에서
  관련 단언이 실패했고 수집/setup 오류·skip은 없었다. 원래 6개 검사에 `..`, 중간 링크,
  실제 대상 비교, `__main__`, 디렉터리 조회 제거를 더했다.
- 종료 확인 변이: 정상 **2 passed**, 한 번만 조회하는 이전 동작 **2 failed**.
  지연된 소멸을 주입한 0/7 종료에서 같은 오류를 재현한다. 별도로 실제 더미 프로세스의
  0/7 종료를 20회씩 반복해 **40/40** 반환 코드·잠금 해제를 확인했다. 반복 수를 정규
  suite 통과 수에 합산하지 않는다. 원래 리뷰의 일회 실패에는 errno 기록이 없어 OS의
  정확한 순간 상태까지 확정한 것은 아니다.
- 종료 변이의 첫 격리 시도는 복사본에 Git 정보가 없어 branch 조회에서 실패했다.
  이를 검출 성공으로 세지 않고 보존했다. 다음 시도는 독립 임시 Git 저장소를 만든 뒤
  정상/변이 대조를 모두 완료했다. 프로젝트 worktree나 공용 Git 상태는 바꾸지 않았다.

## 보존과 경계

기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0`와 현재 Git blob 및 존재하는 로컬
파일을 비교했다. 기존 등록 5개·RGB JSON 65개·legacy source 6개, **총 76/76 바이트
동일**이다. v6e 등록의 source hash도 **85/85 일치**한다. sparse로 없는 기록은 Git
blob을 사용했다고 검증 JSON에 명시한다. 기존 registration과 runner에는 v2 자동 전환이
없다. 새 CLI만 opt-in이며, 실행 번들·workflow 번호를 새로 만들지 않았다.

`.github/workflows`는 수정하지 않았다. 병합한 `origin/main`과 `tests.yml`이 같다.
원래 소스 고정·봉인 검사 및 CI 분할 검사를 함께 실행한다. PR은 draft로 유지하고
병합하지 않는다. 물리 admission, native/자식 전체 추적, 불변 입력, 모든 metadata,
공용 catalog slice 제공은 여전히 후속 범위다.

원본 로그·JUnit·변이·보존 감사 위치:
`/Users/changmin/projects/ugrp/outputs/seal-review-301c-fix-20261001/`.
이 raw는 로컬 보관이며 원격 백업이 아니다. GitHub에는 변경·검증 집계·hash를 보존한다.
연구 실험 결과가 없으므로 TensorBoard 변환은 없고, UGRP 예외에 따라 Drive 작업도 없다.

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q --tb=short \
  tests/test_seal_runtime_provenance.py tests/test_execution_dependency_contract.py \
  tests/test_seal_v2_review_301.py tests/test_seal_v2_fail_closed.py \
  tests/test_seal_v2_review_301b.py tests/test_seal_v2_review_301c.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_pair_v6.py tests/test_rgb_execution_bundle.py \
  tests/test_ci_sharding.py tests/test_ci_host_lock.py tests/test_agent_lock.py tests/test_ugrp_session.py
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-seal-dependency-decouple/check_runtime_mutations.py --output /absolute/new-results
```
