# PR #301: 두 번 BLOCK 뒤 실행 관측으로 전환

작업 시작 HEAD: `e25d7509d78af711b9a33ae62bd5c103a425200e`.
기존 기준: `d17ca4345affef8cf027e121cf1f3197b36c23e0`.
작업 브랜치: `codex/seal-dependency-decouple`.

현재 결과는 **오프라인 Python 추적기·검사 실행기와 후속 native 설계**다. 전체 물리
admission 구현이 아니다. 사용자가 허용한 “추적기 + 설계 문서” 범위로 진행했다.
정적 분석기는 추가로 고치지 않았다. 기존 봉인·실행기에 새 경로를 자동 연결하지 않았다. `.github/workflows`는
main을 병합한 뒤 `origin/main`과 바이트 동일하게 유지했다.

## 근거와 변경

[첫 리뷰](https://github.com/kcm0127-dotcom/ugrp/blob/codex/review-301/experiments/2026-09-30-seal-dependency-decouple/REVIEW_301_astra.md)와
[두 번째 리뷰](https://github.com/kcm0127-dotcom/ugrp/blob/codex/review-301b/experiments/2026-09-30-seal-dependency-decouple/REVIEW_301b_astra.md)를
읽고, “두 번 막히면 패치를 멈추고 검증된 참고 방법을 채택”하라는 이번 사용자 지시를
적용했다. 기존 AST 누락을 더 열거하는 방식은 중단했다.

[설계 및 참고 자료](../../docs/runtime_provenance.md)에 ReproZip, Sciunit, CDE,
noWorkflow, PEP 578, Bazel/Nix, CAS 자료와 적용 범위를 연결했다. 원 도구 설치/실행을
새 구현 검증으로 대체하지 않았으며, 새 구현은 별도 테스트 대상이다.

- `trace_contract`: 외부 digest로 정적 v2를 확인한 뒤 canonical 사례를 새 Python
  프로세스에서 실행한다. 성공 사례의 실제 파일 접근 ∪ 정적 목록 ∪ bootstrap을 봉인한다.
- `run_sealed`: 외부 최종 digest, 전체 파일 bytes/realpath/symlink, 환경과 runner를
  대조하고 같은 audit hook으로 실행한다. 새 입력·바뀐 입력은
  `HOST_ERROR(seal-violation)`으로 프로세스를 종료한다.
- 환경: 허용한 비밀 아닌 값만 전달하며 읽은 이름과 값 hash/부재를 기록한다.
  환경·설치 identity 드리프트는 봉인한 abort/warn 정책으로 대조한다.
- CLI: 기존 receipt를 덮어쓰지 않는다. 실패 trace는 `.failed.json`에 기록하고
  usable seal은 생성하지 않는다. 사례 실행 timeout·보고 누락도 실패다.
- 새 suite를 `scripts/run_ci_tests.py`에 추가했다. workflow 파일은 수정하지 않았다.

## 리뷰 사례 대응

다음은 새 `tests/test_seal_runtime_provenance.py`의 통과한 검사 대응표다.
옛 리뷰 원본의 xfail은 별도로 재현했으며 새 경로의 통과 수에 합산하지 않는다.

| 원 지적 | 새 runtime 회귀 |
|---|---|
| R1 wildcard, N6 symlink package | `test_review_wildcard` (2개) |
| R2 네 loader 별칭 | `test_review_loader_reads`의 R2-* (4개) |
| N1 네 모듈 간 재수출 | 같은 검사의 N1-* (4개), static에서 plugin 누락을 명시 확인 |
| N4 importlib.__import__ 두 형태 | 같은 검사의 N4-* (2개), static에서 plugin 누락을 명시 확인 |
| R3 script sibling, N7 symlink script sibling | `test_review_script_folder` (2개) |
| R4 JSON 키 순서 | `test_review_registry_bytes[R4-order]` |
| N2 Decimal 정밀도, N5 schema 부재/null | 같은 검사의 N2/N5 (2개) |
| N3 바이트 동일 source/XML symlink 2개 | `test_N3_same_bytes_source_symlink_target`, `test_N3_declared_xml_link_selects_other_declared_asset` |
| R5 다른 workflow 행의 missing entry/중복 id | `test_review_standard_workflow_consumer[R5-*]` (2개) |
| R6 실제 공통 launcher 변경 | 같은 검사의 R6-launcher (명령 생성만 수행) |
| B1 registry 참조 chain, XML include, 미선언 자산 | registry B1, XML include, 파일 bytes 검사. NPZ는 파일 read 검증이며 NumPy 실행 검증 아님 |
| B1 subprocess, native | 지원을 가장하지 않고 canonical 단계에서 명시 거부; child 실행/물리 없음 |
| B2 환경·설치 버전 | 환경 값 변경의 abort/warn 실제 대조, identity는 mock 비교이며 package upgrade 아님 |

N1(4)+N2(1)+N3(2)+N4(2)+N5(1)+N6(1)+N7(1)=**추가 12사례**다.
원래 R1–R6는 **10사례**(R2 4개, R5 2개)로 검사한다. 지적 종류 수와 테스트 수를
섞지 않는다. 새 분기의 `open`/Path/os.open/exec, 환경 새 이름, shutdown callback,
thread 파일 read, 여러 canonical case 합집합, 부분 실패, 외부 digest, CLI를 별도 검사한다.

## 검증 결과

PR #328을 포함한 main `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`을
병합했다(merge `24205714`). 기존 `run_ci_tests.py` 수정은 임시 patch로 보존한 뒤
다시 적용했다. 공용 호스트 잠금 없이 오프라인 검사를 수행했으며 다른 작업의
잠금·프로세스를 변경하지 않았다. 아래 시간은 속도 비교가 아니다.

- 최종 runtime suite: **56 passed**, 실패·skip·xfail 0. 원래 R1–R6의 10사례와
  N1–N7의 추가 12사례를 모두 포함한다. 첫 56개 통과 뒤 한계 문구만 재현성 표현으로
  바꾸고 최종 소스로 다시 실행했다. 두 실행의 통과 수를 합산하지 않는다.
- 관련 9개 suite **295 passed**, 실패·skip·xfail 0. 새 runtime과 합쳐
  **351 passed**이며, 리뷰 원본과 변이 검사는 이 분모에 더하지 않는다.
  세부 집계는 `RUNTIME_PROVENANCE_validation.json`에 있다.
- 리뷰 원본 `13afa3dc04fa15630248716b580d776a7e6cb1d7`의 suite는 바꾸지 않고
  **14 passed / 13 strict xfailed**를 재현했다. 13개는 정적 v2의 12개 누락과
  B1 참조 경계가 그대로라는 증거다. 정적 v2 자체를 수정 완료로 보고하지 않는다.
- 변이 검사: 격리 복사본의 정상 대조군 **13 passed**, 검사 제거 **6/6 검출**.
  새 파일 읽기·환경값·경로/링크 binding·정적 union·설치 identity·새 환경 이름을
  각각 한 곳씩 바꿨다. 대응한 4/4/2/1/1/1개 단언이 실패하고 수집/setup 오류는
  없었다. 선택한 여섯 검사의 민감도 확인이며 전체 변이 공간의 완전성을 뜻하지 않는다.
- 기준 `d17ca434`와 blob/현재 파일 직접 비교: 옛 등록 **5/5**, RGB JSON **65/65**,
  legacy source **6/6** 바이트 동일. 현재 v6e source **85/85** hash 일치.
  정적 v2 모듈 2개도 작업 시작 `e25d7509` 이후 수정하지 않았다.
- CI 목록 **338 files / 8 shards**, 새 runtime suite 정확히 1회 포함.
  sparse에 빠진 기존 frozen fixture 3개는 Git 원본을 다시 포함했고 preflight가
  **3/3 통과**했다. workflow 변경은 없으며 `git diff --check`도 통과했다.
- 먼저 보존한 `RUNTIME_PROVENANCE_validation_pending.json`은 호스트 잠금 때문에
  pytest가 시작되지 않았던 이전 시도 기록이다. 이번 첫 관련-suite 수집도 외부
  임시 파일과 저장소를 함께 지정해 pytest root가 `/`로 잡히며 실패했다. 저장소
  검사와 원본 리뷰 검사를 분리하고 root/confcutdir를 명시해 해결했다. 실패 로그도
  남기고 성공 분모에는 넣지 않았다.

재현 명령(물리 없음):

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_seal_runtime_provenance.py \
  tests/test_execution_dependency_contract.py tests/test_seal_v2_review_301.py \
  tests/test_seal_v2_fail_closed.py tests/test_zone_pair_registered_source.py \
  tests/test_zone_study_source_pinning.py tests/test_zone_pair_v6.py \
  tests/test_rgb_execution_bundle.py tests/test_ci_sharding.py tests/test_ci_host_lock.py
PYTHONDONTWRITEBYTECODE=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-seal-dependency-decouple/check_runtime_mutations.py \
  --output /absolute/new-mutation-results
```

원본 리뷰는 해당 commit의 `tests/test_seal_v2_review_301b.py`를 별도 임시 폴더로
추출하고, 이 worktree의 절대 경로를 `PYTHONPATH`로 지정해 그 폴더에서
`pytest -q -rx --rootdir=. --confcutdir=. -p no:cacheprovider test_seal_v2_review_301b.py`로 실행했다.

원본 로그·JUnit·변이 결과·파일별 보존 감사는
`/Users/changmin/projects/ugrp/outputs/seal-runtime-provenance-20260930/resume-01/`에 있다.
이 raw는 로컬 보관이다. GitHub에는 코드·문서·검증 집계·해시를 보존하며 raw의 원격
백업을 뜻하지 않는다. 최종 소스·로그 해시는 `RUNTIME_PROVENANCE_validation.json`에 있다.

## 남은 범위

Python hook은 보안 sandbox도 native I/O 추적기도 아니다. OS 수준 ReproZip 계열
trace와 불변 입력 sandbox, 모든 자식 강제, sim_cli/worker admission 연결, coordinator의
canonical 물리 trace와 독립 검토가 남았다. 지금 CLI는 NumPy/MuJoCo와 비표준 native·
자식 실행을 거부하며, 신뢰하는 stdlib 내부의 native 파일·환경 접근까지 추적하지는 못한다.

JSON 전체 read를 관측하면 whole-file hash가 생기므로 무관한 registry 편집의
재봉인 감소를 보장하지 않는다. content-addressed digest만으로 테스트 캐시·과거
성능·실행 승인을 재사용하지 않는다. 물리·렌더·모델 호출·학습·구형 봉인 재작성은
없고 신규 bundle/workflow 번호도 없다. 연구 실험 결과가 없어 TensorBoard 작업은
없으며, 프로젝트 예외에 따라 Drive도 사용하지 않는다.
