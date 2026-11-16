# PR #194 14차 P1 수정 — 2026-09-27

기준 HEAD는 `1e8c5dda23430248b345755538508a39c364d35a`이다. 이 기록은 그 위의
미커밋 변경을 다룬다. 실제 DB 쓰기·물리 실행·모델 호출·프로젝트 커밋·push는 하지 않았다.

## 변경

`scripts/run_zone_study_pilot.py`의 `start_run(expected_state=...)`가 공통
`state_sha256(before)`를 사용한다. 정산 감사 행이 생긴 뒤에도 실행기와 예산 저장소가
같은 상태를 해시한다. 정산 전 해시 호환성과 상태 변경 시 실행 거절은 그대로다.

같은 식을 따로 쓰던 `tests/test_zone_pilot_source_migration.py`의 검토 helper와
`tests/test_zone_study_review_r8.py`의 경합 검사도 공통 함수를 쓴다. 저장소 전체의
상태 해시·호출부를 검색했고, 추적 중인 Python 파일 1,182개를 AST로 확인해
`sends/runs` 목록을 직접 직렬화·해시하는 별도 식이 남지 않았음을 확인했다.
[검색 결과](hash-references.txt), [AST 검사](hash-scan.json).

## 회귀검사

기존 CI 수집 대상인 `tests/test_zone_pilot_settlement.py`에 6개 검사를 추가했다.
합성 DB와 실제 DB의 메모리 복제본에서 각각 다음을 확인한다.

- 정산 후 새 preflight 시작과 fixture 응답 4개 기록.
- 정산 후 기존 preflight의 실제 검증 게이트를 통과해 새 cohort 시작과 fixture 응답 12개 기록.
- 정산 후 소스 이관, 이전 preflight의 cohort 자격 거절, 새 preflight 시작.

모든 경로에서 원래 sends/runs와 정산 감사 체인 보존, 새 예약의 차감 증가를 검사한다.
새 fixture 호출에는 상류 증거를 만들지 않아 CLI 종료 코드는 기존 정책대로 2이며,
`status=recorded`와 `reconciliation_complete=false`를 구분한다. 정산이나 이 검사가
새 모델 호출의 과금 대조 완료 또는 물리 성공을 뜻하지 않는다.

[수정 전 로그](before.txt): 실행기가 원래 식을 사용한 프로세스에서 6개 모두
`pilot state changed since reconciliation; retry preflight checks`로 실패했다.
[수정 후 전체 회귀 로그](after-regression.txt)는 **402 passed, 402.40초**다.
추가한 6개 모두 통과했고 skip은 없다. `git diff --check`도 통과했으며,
각 pytest 종료 후 경로·심볼릭 링크 여부를 확인해 `.pytest_tmp`를 삭제했다.
[최종 검증 요약](verification.json)에 결과와 로그 해시를 남겼다.

재현 명령:

```sh
OMP_NUM_THREADS=1 \
UGRP_ZONE_PILOT_REGRESSION_ROOT=/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  --basetemp=./.pytest_tmp -q -rP \
  tests/test_zone_pilot_settlement.py tests/test_zone_pilot_proxy_log.py \
  tests/test_zone_pilot_source_migration.py tests/test_zone_study_review_r8.py \
  tests/test_zone_study_review_r9.py tests/test_zone_study_review_r10.py \
  tests/test_zone_study_fenced_reply.py tests/test_rgb_execution_bundle.py
```

실제 자료 검사만 위 환경변수로 선택한다. 변수가 없으면 실제 자료 3개는 skip하고
합성 회귀는 항상 실행한다. 변수를 명시했는데 DB·증거가 없거나 검증에 실패하면
skip하지 않고 실패한다. socket 연결은 fixture로 차단한다.

## 원본 보존과 범위

원본은 `/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10/budget.sqlite`다.
WAL·SHM·journal 부재를 확인하고 `mode=ro&immutable=1`로 연 뒤 SQLite backup API로
`:memory:`에 복제한다. 메모리 복제본의 integrity와 원본 snapshot 일치를 확인한다.
테스트의 DB 연결만 메모리에 묶으며 원래 meta/path/pilot ID/소스 이관 체인을 바꾸지 않는다.
운영 DB 복제 허용 옵션은 추가하지 않았다. 정산·소스 이관·새 실행 기록은 메모리에만 쓴다.
세 실제 자료 검사 모두 정상 16건을 정산하고 실패 1건은 제외했다. 복제본의 차감은
34 attempts / 4,085,674 tokens에서 18 attempts / 409,793 tokens로 줄었고,
그 상태에서 각 새 실행 경로가 통과했다. 실제 DB에는 이 정산을 적용하지 않았다.

각 실제 자료 검사의 종료 경로에서 DB·telemetry·요청·응답·trial·manifest·근거 파일
65개의 SHA-256/크기/mtime 일치와 sidecar 부재를 검사한다. 원본 DB SHA-256은
`cc23aa281f44b7989627dd2059ea00b868b43bfec2d59c12cda0cf9042145158`이다.

[v63 정적 검증](bundle-verification.txt)은 통과했다. 변경 파일은 RGB 실행 번들
소스 closure 174개와 겹치지 않으며 번들 ID·JSON·해시는 그대로다.
[변경 소스 해시](source-verification.json)에 기록했다. 실제 실행 전 소스 검토·커밋·이관은
이 작업에서 수행하지 않았다.

`git fetch origin`은 공용 Git 메타데이터 쓰기 제한, `gh pr list`/`view`는 네트워크 제한으로
실패했다. 원격 최신 상태는 재확인하지 못했으며 요청된 로컬 HEAD를 기준으로 수정했다.
기본 checkout과 다른 작업 브랜치는 변경하지 않았다. 새 연구 실험이 없는 오프라인
회귀검사이므로 TensorBoard 변환·새 snapshot·서버 실행은 하지 않았다. 프로젝트 예외에
따라 Google Drive는 사용하지 않았으며 이 기록은 로컬 보관이다.
