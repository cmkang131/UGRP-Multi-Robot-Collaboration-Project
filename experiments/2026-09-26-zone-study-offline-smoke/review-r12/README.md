# PR #194 12차 리뷰 수정 검증 — 2026-09-27

기준 HEAD는 `8544893ee6c5ce88e2c95d7d8e4ed90f127805e4`이다. 이 기록은 그 위의
**미커밋 수정**을 검증한다. 물리 실행·실모델 호출·실제 DB 이관·커밋·push는 하지 않았다.
다른 에이전트의 검증을 합산하지 않았다.

## 수정과 실패 재현

| 항목 | 수정 | 수정 전 → 수정 후 |
|---|---|---|
| P1-1 | `PilotSendLedger`가 같은 budget의 앞 응답을 읽어 `floor(응답 초)+2`까지 벽시계 대기. 목표·실측 ns를 wire 이전에 예약 행, 정산 뒤 ledger에 기록. timeout은 대기 후 시작 | 인위적인 10초 간격을 제거한 4조건 통합 검사에서 `06.3` 응답→`06.5` 다음 호출이 실패. 수정 후 `08.0` 송신·1.5초 대기, 4개 모두 대조 완료 |
| P1-2 | 파일 크기로 고정한 로그 prefix 전체의 시각 순서를 검증한 뒤 추출. prefix hash·inode·크기를 봉인하고 reconcile에서 전체 prefix와 추출 구간 재검증 | `GET :00 → POST :06 → GET :08 → POST :06`에서 수정 전 잘못된 complete, 수정 후 역행으로 미완료 |
| P2-3 | 추출에 봉인 byte 범위 전체를 포함. 봉인 이벤트가 시간 범위 밖이면 미완료 | retry/error × 앞/뒤 경계 4개가 수정 전 잘못된 complete, 수정 후 모두 미완료 |
| P2-4 | 동일 번들 ID·hash·전체 설정을 유지한 실제 소스 변경도 감사 이관 허용. no-op·경로만 변경·같은 ID의 hash 변경은 거절 | v62→v63 뒤 파일럿만 수정한 v63 재이관이 수정 전 거절, 수정 후 체인·지출 보존 및 오래된 객체 차단 |

[수정 전 로그](before.txt)는 위 **7개 모두 실패**한 결과다. production 파일을 고치기
전에 현재 worktree에서 새 반례를 실행했다. [첫 수정 후 로그](after-targeted.txt)는
같은 7개를 포함한 관련 검사 70개 통과다. 이후 prefix 위조/회전/삭제·정상 append,
wire 이전 대기 기록·timeout 분리, 서로 다른 대기량의 SIM trace/호출 비용 일치,
동일 번들 이관 체인 훼손 및 no-op 거절 검사를 추가했다.

최종 검사 **286개 통과**:

- [확장 회귀](after-regression.txt): proxy log, source migration, R8, R9, RGB bundle — 241개.
- [완료 정책 R10 회귀](after-completion.txt): 45개.
- `git diff --check`, v63 `verify-current` 통과.

pytest는 모두 아래 옵션을 사용했다. 테스트 임시 디렉터리는 종료 뒤 삭제했다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  --basetemp=./.pytest_tmp -q \
  tests/test_zone_pilot_proxy_log.py tests/test_zone_pilot_source_migration.py \
  tests/test_zone_study_review_r8.py tests/test_zone_study_review_r9.py \
  tests/test_rgb_execution_bundle.py
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  --basetemp=./.pytest_tmp -q tests/test_zone_study_review_r10.py
```

## 실제 preflight-01 읽기 전용 대조

원본: `/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10/`.
`PilotBudget(..., read_only=True)`로 원본 DB를 열고 설치 프록시 로그도 읽기만 했다.
복사 DB나 fixture로 원본 검증을 대신하지 않았다.

[대조 보고서](preflight-01-readonly/reconciliation.json)와 별도로 다시 호출한
`reconcile` 모두 **complete=true**, 등급 `proxy_log_exclusive_window`다.
POST 1개, retry/error 0개, 실제 시도 계수 1, 최종 응답 usage total 10,622다.
예약 차감은 **2 attempts / 235,408 tokens**, 환불 0이다.

[검증 기록](verification.json)에 DB·요청·응답·trial·기존 manifest의 전후
SHA-256/크기/mtime 일치와 로그 prefix 불변을 남겼다. DB snapshot도 전후 동일하며
실제 DB는 **v62, 이관 0회**다. 기존 실패 manifest는 수정하지 않았다.
완료된 과금 대조는 당시 실패 응답을 정상 채택이나 새 소스 preflight로 바꾸지 않는다.

전체 프록시 로그에는 관련 없는 사적 내용이 있을 수 있어 복제하지 않았다.
고정 prefix의 SHA-256·크기·inode와 필요한 호출 구간만 보존했다. 재검증에는 그
원본 prefix가 필요하고, 로그 회전·삭제·변경 시 미완료 처리한다. 이 등급은 최종 응답
usage의 약한 쿼터 증거이며 upstream ID·STOP·재시도별 토큰을 입증하지 않는다.

## 번들 범위와 남은 작업

수정한 production 파일 4개는 `source_closure()` **174개와 교집합이 없다**.
파일럿 `source_identity.files`에는 모두 포함된다. `load_bundle`과 `verify-current`로
전체 closure 파일 해시를 확인했고 v63 JSON은 바꾸지 않았다.
v63 SHA-256: `ef4fe391e57c145b6625ba052e651542745bfcb6244d8e25736827ee8122aa01`.

실제 운영 이관과 새 4-call preflight는 이 작업에서 실행하지 않았다. 최종 소스
검토·커밋 후 기존 v62 DB를 v63으로 한 번 이관하고, 기존 send 대조 후 새 4조건
preflight를 진행하는 순서를 유지한다.

`git fetch origin`은 공용 Git 메타데이터 쓰기 제한, `gh pr list`는 네트워크 제한으로
실패했다. 원격 최신 PR 상태는 재확인하지 못했고 로컬 기준 HEAD로 수정했다.
기본 checkout과 다른 작업 브랜치는 변경하지 않았다. 이 작업은 오프라인 회귀 및
기존 원본 재대조라 새 실험 TensorBoard snapshot을 생성하지 않았다.
