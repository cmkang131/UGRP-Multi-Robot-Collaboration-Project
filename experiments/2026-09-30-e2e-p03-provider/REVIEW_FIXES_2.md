# PR #312 F312-1 수정과 CI 재검증

2026-10-01 KST. 대상 검토는 `7623f3ca`의
`experiments/2026-09-30-e2e-readiness/REVIEW_FIXES_2.md`다.
PR HEAD `b38c1d5905fdf798dcfd34d215c7e82d0a0cf296`에
main `7e081d7047aa2df737cc1890c963b1d3a14302c0`을 충돌 없이 merge했다.
rebase·강제 push·PR 병합은 하지 않는다. PR은 draft로 유지한다.

## 원인과 수정

기존 GitHub 실행 `36719609772`의 실패 로그에서 shard 6의 유일한 회귀는
`RobotInputBoundaryTests.test_no_robot_side_module_references_the_profiles`였다.
P03 host가 평가 카메라 모듈을 쓰지만, 허용된 orchestration 파일 목록에는
기존 runner만 있어서 실패했다. 로컬에서도 같은 assertion으로 **1 failed, 1 passed**를 재현했다.

`tests/test_zone_eval_top.py`에 P03 host를 추가하고, 기존과 동일한
`assert_eval_only_uses`를 통과하도록 했다. 파일을 검색에서 제외하거나 검사 없이
허용하지 않는다. 기존 host와 P03 host 각각에서 평가용 지도 값을 `self.static`으로,
평가 카메라 기록을 `self.control_camera`로 보내는 **4개 변이**를 검사한다.
파일을 수정하지 않고 읽은 문자열만 바꾸며, 실제 저장소 검색 경로에서 거절되는지 확인한다.

`check_eval_boundary_mutations.py`는 이 회귀 검사 자체도 확인한다.
P03만 검사 생략, 기존 host만 검사 생략, 양쪽 검사 생략의 **3/3 변이**가
각각 **2·2·4개 assertion 실패**로 검출됐다. 정상 대조는 통과했고 import/환경 오류는 없다.

로컬 `offline_checks.py`에 평가 경계의 비물리 검사 세 클래스를 포함했다.
#328과 이번 요청에 맞춰 공용 host lock 없이 실행한다. 기존 MuJoCo·실제 모델·네트워크·렌더
차단 guard와 로컬 제외 범위를 유지한다. 정상 GitHub CI에서는 테스트를 제외하지 않는다.
workflow와 CI 정책 테스트·안내는 main과 이미 일치하므로 추가 수정하지 않았다.

## 직접 검증

기존 `.venv-sim-worker-mac` Python 환경에서 수치 연산 스레드를 1개로 제한했다.

| 검사 | 결과 |
|---|---|
| `offline_checks.py` | **341 passed**, 4 subtests passed, 10 deselected, 실패·오류 0 |
| 지정한 source pin 검사 두 파일 | 위 결과에 포함, **22 + 34 = 56 passed** |
| `test_ci_fast_path.py`, `test_ci_sharding.py`, `test_ci_host_lock.py` | **100 passed**, 280 subtests passed |
| `scripts/check_ci_fixtures.py` | frozen fixture **3개 존재** |
| `check_eval_boundary_mutations.py` | 정상 대조 통과, 검사 생략 **3/3 검출** |
| 보존 대상 해시 | **141/141 불변**, main과 바이트 일치 |
| `git diff --check` | 통과 |

보존 대상은 v6e 고정 소스 85개, 기존 prereg JSON 53개, 지정 테스트 2개,
workflow 1개다. `tests/test_zone_study_source_pinning.py`의 transport 항목 추가는
main 병합으로 받은 내용이며, 두 지정 테스트의 최종 바이트는 main과 같다.
관련 검사 341개와 CI 정책 검사 100개는 별도 실행이다. subtest를 독립 테스트 수에 더하지 않는다.

재실행 진입점은 다음과 같다.

```sh
python experiments/2026-09-30-e2e-p03-provider/offline_checks.py
python experiments/2026-09-30-e2e-p03-provider/check_eval_boundary_mutations.py
python -m pytest -q tests/test_ci_fast_path.py tests/test_ci_sharding.py tests/test_ci_host_lock.py
python scripts/check_ci_fixtures.py
```

## 기록과 남은 범위

파일 해시·JUnit 집계·변이 실패 원문은 `f312_1_verification.json`에 기록했다.
원본 로그·JUnit·실패한 기존 CI 로그는
`/Users/changmin/projects/ugrp/outputs/e2e-p03-f312-1-20261001/`에 로컬 보관한다.
원격 raw 전체 백업으로 표현하지 않는다. 임시 archive 추출 디렉터리는 만들지 않았다.

이 검증 뒤 정상 push로 GitHub CI를 실행하고, 해당 HEAD의 실제 결과를 #312의
한 번의 한국어 댓글에 연결한다. 로컬 통과를 원격 CI 통과로 대신하지 않는다.
로컬 물리·렌더·실제 provider 추론·LLM 호출은 없다. 새 실험 코호트가 없어 TensorBoard
변환·서버도 없으며 Drive 작업은 하지 않는다.
후보의 미등록·미봉인 상태와 `runnable=false`, `physical_ready=false`는 유지된다.
최종 카메라/모델 보정·Release 검증·물리 인수는 여전히 별도 작업이다.
