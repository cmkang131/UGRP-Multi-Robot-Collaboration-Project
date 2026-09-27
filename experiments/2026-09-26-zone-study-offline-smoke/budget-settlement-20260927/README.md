# PR #194 예산 정산 변경 검증 — 2026-09-27

기준은 `c684e6aaef6dc7ee8cd62ce9e18e4034f78146f6`이다. 변경은 미커밋이며,
[이슈 #222 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/222#issuecomment-5852643473)을
구현했다. 실제 DB는 변경하지 않고 임시 SQLite 복사본에서만 정산을 적용했다.
모델 호출·물리 실행·소스 이관·커밋·push·병합은 하지 않았다.

## 구현

- `--settle-reconciled`와 `--dry-run`: 명시적 명령만 예산을 정산한다.
- `BEGIN IMMEDIATE` 안에서 검토한 보고서 파일 해시·state·source를 확인하고 telemetry와
  요청/응답/원문 로그를 재대조한다. 원래 manifest → trial 해시로 정상 호출과 exact usage도 확인한다.
- SQL `sends.attempts/tokens`는 현재 차감, 원래 JSON의 `reserved_*`는 예약 이력이다.
  `budget_settlements`는 send UNIQUE·순번·해시 체인으로 이전/이후 차감과 근거를 보존한다.
  기존 sends/runs JSON과 source_migrations는 불변이다. 신규 예약은 감사 행과 차감의 일치를 검사한다.
- 실패·unknown·미대조·usage 누락·예약 초과는 반환하지 않는다. 로그 등급에서 재시도한
  호출은 앞 시도 usage가 unknown이므로 전액 유지한다. ID 등급은 모든 실제 시도의 provider
  `total_tokens`를 합산한다. 600 attempts / 5M tokens 상한은 그대로다.
- 전체 보고서가 미완료여도 개별 send가 대조 완료이고 나머지 조건을 충족하면 정산할 수 있다.
  전체 대조 완료를 요구하는 코호트 진입 게이트는 그대로다. 개별 ID를 명시해 부적격 행의
  정산을 시도하면 명령 전체가 실패한다. 정산은 실제 provider 청구서 인증이나 물리 성공이 아니다.

## 실제 17 send 복사본

최종 근거: [verification.json](final/verification.json), [dry-run.json](final/dry-run.json),
[reconciliation.json](final/reconciliation.json), [복사본 적용 감사 행](final/copy-applied.json).
루트의 같은 이름 파일은 첫 확인 기록이며 덮어쓰지 않았다. 최종 소스의 기록은 `final/`이다.

시작 때 v63-05가 없어 v63-04(16/17 대조 완료)를 확인했다. 복사본 검증 전에
v63-05가 생성됐으므로 **최신 `log-evidence-v63-05/telemetry.jsonl`**을 사용했다.
17/17 대조 완료이며, 모두 `proxy_log_exclusive_window` 등급이다.

| 분류 | send 수 | 정산 후 attempts | 정산 후 tokens |
|---|---:|---:|---:|
| 정상 + exact + 대조 완료 | 16 | 16 | 174,385 |
| 실패 preflight-01, 무환불 | 1 | 2 | 235,408 |
| 합계 | 17 | **18** | **409,793** |

원래 차감 **34 attempts / 4,085,674 tokens**에서 **16 attempts / 3,675,881 tokens**를
반환한다. 정산 후 여유는 **582 attempts / 4,590,207 tokens**다.

17건 provider total은 **185,007**이다. 배경의 172,839는 마지막 12,168을 제외한
16건 합계다. 첫 실패의 usage 10,622는 확인되지만 예약 235,408을 유지한다.

원본 DB SHA-256:
`cc23aa281f44b7989627dd2059ea00b868b43bfec2d59c12cda0cf9042145158`.
DB 크기 229,376 bytes. DB·telemetry·요청·응답·trial·manifest·증거 파일 총 **65개**의
SHA-256/크기/mtime이 전후 같았다. 설치 프록시·로그는 읽기만 했으며 로그 전체는 복제하지 않았다.

`PilotBudget`는 운영 DB 경로를 고정하므로 일반 생성자는 복사본을 거절한다. 검증 스크립트
[verify_copy.py](verify_copy.py)는 **테스트 안에서만** 객체의 연결 경로를 임시 복사본에
연결했다. meta의 원래 경로·pilot ID·소스 이관 체인은 수정하지 않았다. 운영 CLI에 copy
우회 옵션을 넣지 않았다. 복사본의 실제 정산 16행·차감 합계·중복 거절까지 확인했다.
임시 복사본 경로와 정산 후 해시는 verification에 남겼으며 Git에는 DB를 넣지 않는다.

## 자동 검사

첫 정산 테스트 **33 passed**, 관련 확장 회귀 **394 passed**. 이후 정산 뒤 source migration과
신규 예약의 attempts 한도 검사를 추가해 최종 정산 테스트 **35 passed**를 확인했다.
중복을 제외하면 **396개 검사**다. 모델·socket 연결을 거절하는 fixture만 사용했다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  --basetemp=./.pytest_tmp -q \
  tests/test_zone_pilot_settlement.py tests/test_zone_pilot_proxy_log.py \
  tests/test_zone_pilot_source_migration.py tests/test_zone_study_review_r8.py \
  tests/test_zone_study_review_r9.py tests/test_zone_study_review_r10.py \
  tests/test_zone_study_fenced_reply.py tests/test_rgb_execution_bundle.py
# 394 passed in 130.36s
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  --basetemp=./.pytest_tmp -q tests/test_zone_pilot_settlement.py
# 35 passed in 1.18s
```

중복 정산(이전·새 보고서), 미대조 정산, report/state/telemetry/원문/응답/trial/manifest 해시
불일치, 예약 초과 usage/attempts, 부분 usage, 실패·unknown·진행 중 run, 재시도 usage 미상,
감사 행 훼손, SQL 롤백, 커밋 뒤 receipt 쓰기 실패 복구, 정산 후 신규 예약과 소스 이관을 검증했다.
`scripts/run_ci_tests.py` 수집에 새 모듈을 추가했다. `.pytest_tmp`는 종료 후 삭제했다.

RGB `source_closure()` **174개와 수정 파일의 교집합은 0개**다. `load_bundle` 및
`verify-current --id rgb-standard-dispatch-v63`로 전체 소스 해시를 검사했다.
v63 JSON/ID/SHA는 그대로다:
`ef4fe391e57c145b6625ba052e651542745bfcb6244d8e25736827ee8122aa01`.
새 `zone_pilot_settlement.py`는 파일럿의 `source_identity.files`에 포함되므로 새 모델
호출 전에 소스 이관·재preflight가 필요하다. 정산 자체는 모델 호출을 허가하지 않는다.

## 운영 경계

GitHub 커넥터로 PR #194 HEAD와 이슈 #222 결정, 열린 PR을 확인했다. `git fetch origin`은
공용 Git 메타데이터 쓰기 제한으로 실패했고, `gh pr list`는 네트워크 제한으로 실패했다.
기본 checkout은 변경하지 않았다. 이번 변경은 요청한 기존 worktree 안의 미커밋 수정이다.

실제 DB 적용은 하지 않았다. 새 학습/물리/모델 실험이 없는 기존 자료의 예산 검증이므로
TensorBoard snapshot을 추가하거나 원래 결과를 변환하지 않았다. Google Drive는 프로젝트
예외에 따라 사용하지 않았다. 기록은 로컬이며 원격 업로드/백업/PR 반영으로 표현하지 않는다.
