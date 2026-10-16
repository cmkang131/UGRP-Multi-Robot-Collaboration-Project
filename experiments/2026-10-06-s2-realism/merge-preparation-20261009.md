# S2 #406 main 병합 준비 (2026-10-09)

시작 `4162acc96d6bbb1196c745fcc9fa1936d40217b5`에 fetch한 main
`7ff07d62d21bcdcd5a9874827ae36ee7093c0c78`을 `git merge --no-ff --no-commit origin/main`으로 통합했다.
rebase·force push·시뮬레이션·모델 호출·우선순위 변경·다른 작업 프로세스 종료는 하지 않았다.
DRAFT 유지, 독립 제어기 검토는 감독이 배정한다. PR 병합은 이 작업의 범위가 아니다.

## 해결과 검증

- 내용 충돌 1개: `scripts/run_ci_tests.py`. main의 구동/카메라 시험 16항목을 포함한 CI 목록을 그대로 유지했다.
- 자동 병합된 workflow 계획 시험은 S2 조각과 main의 S3 두 경로를 모두 보존했다.
- `configs/ci_test_durations.json`은 #411 분리 때 남은 이전 시간표를 main 값으로 맞췄다. 퇴역 시험 2개의 오래된 항목도 다시 넣지 않았다. `.github/workflows/tests.yml`, CI 목록·시간표 3파일은 main과 바이트 동일하다. #411의 S2 CI 추가분은 별도 PR에 남는다.
- main의 `AGENTS.md`, `docs/decision_log.md`, `docs/retired_modules.md`를 바이트 그대로 유지했다. #417 퇴역 소스 87개와 시험 2개 모두 부재 확인.
- 기존 S2 실험 기록·template·fixture 507개 Git blob 불변. 각 부모의 기본 catalog·조각·registry 57개/20개 바이트 동일. 공통 경로는 양쪽에서 중복 계산한다. ID 충돌이 없어 새 ID 등록·은퇴 번들 이동은 필요하지 않았다. 저장된 실행 번들을 새 소스로 재생성하지 않았다.
- 기존 Mac 환경에서 `tests/test_ci_sharding.py tests/test_ci_fast_path.py tests/test_simulation_workflow_manager.py`: **96 passed, 280 subtests passed (5.46초)**. workflow 시험은 fake fixture/읽기 전용 plan이며 물리를 시작하지 않았다. `git diff --check` 통과. 넓은 시험은 CI에 맡긴다.
- [기계 판독 검증·로컬 원본 해시](merge-preparation-20261009.json). 원본 로그·JUnit·파일별 보존 대조는 `/Users/changmin/projects/ugrp/outputs/s2-merge-prep-20261009/`에 보존한다.

## S2 판정과 분모

10/9 결정 4에 따른 **조건부 통과·S3 진행**을 유지한다. 아래 조건과 코호트는 합산하지 않는다.

| 조건 | 성공/분모 | 경계 |
|---|---|---|
| v106 시작 사전정보 있음 | 5/5 | 결정 4에 적힌 기존 전 구간 근거; 현재 소스 재검증 아님 |
| v139 시작 prior 없음 | 2/3 | seed 1059–1061, 기존 DEV |
| v140 prior 없음·능동 관측 | 새 seed 3/3, 기존 실패 재현 1/1 별도 | seed 1062–1064와 1060; 실제 회전 상한 문제 보존 |
| v141 prior 없음·RGB 회전 guard | 3/6 | seed 1065–1070 전부 포함, 미집기 1/6·B 밖 2/6; 기존 졸업 관문 미통과 |

v141 독립 채점 6/6 유효, 거짓 양성/음성 0. 능동 회전 7회 최대 40.581°, 90° 위반 0이지만
6/7회가 RGB 합의 부족으로 조기 취소됐다. NEES 초과 54.28–100%, 무경고 25cm 초과 242건은 남아 있다.
DEV log-only 가드·solo freeze 조건이며 정식 E2E·통신 효과·실물 성공으로 승계하지 않는다.
S2를 다시 졸업시키기 위한 실행은 하지 않았으며 후속 수정은 S3에서 확인한다.

## 범위와 후속

S2 v109–v141의 기존 제어기 옵션·실행 계약/조각·검사·보정 자료·성공/실패 기록을 보존한 통합이다.
새 제어 변경·새 실험 결과가 없으므로 기존 TensorBoard snapshot을 재변환하거나 viewer를 재시작하지 않았다.
기존 수치·표시는 `graduation59-result.json`, `graduation59-delivery.json` 및 README의 해당 코호트 절을 따른다.

#406 본문 상단에 조건부 통과 근거·한계·제어기 핵심 독립 검토 파일을 정리한다.
#411에는 #406 병합 뒤 자기 worktree에서 main을 merge하고 CI 3파일 차이와 퇴역 항목을 확인한 뒤
관련 시험 통과·일반 push·base main 전환하는 단계만 코멘트로 남긴다. #411 소스·base는 이 작업에서 바꾸지 않는다.
