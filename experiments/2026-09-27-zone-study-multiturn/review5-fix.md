# PR #245 검토 5 P1 세 건 수정 — 2026-09-28

기준 HEAD는 `8d25d30aabe2c759e86c79d6089b37508f658ade`다. 사용자가 지정한
`/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-245-review5.md`
를 먼저 읽었다. 변경은 `codex/zone-study-multiturn` worktree에 미커밋으로 남긴다.
실제 모델 호출·MuJoCo 물리 step·커밋·push·병합은 모두 0회다.

`git fetch`는 공유 Git 메타데이터 쓰기 제한, `gh`는 네트워크 제한으로 실패했다.
대신 GitHub 커넥터로 PR #245의 위 HEAD·draft·미병합 상태와 열린 PR 7건을 확인했다.
기본 checkout의 main과 PR base는 모두 `ba0eb4f547996af880de65003442882c5326c71d`다.
기존 origin은 변경하지 않았다. [조회 기록](review5-remote.json)을 보존했다.

## 변경과 반례

수정은 `harness/zone_event_scheduler.py`의 공통 사건 처리에만 넣었다.
`DecisionScheduler`에는 생명주기 메서드를 추가하지 않았다.

1. `_defer`와 `_resume_deferred`가 메시지 재시도의 `retry_of`를 보존한다.
   `EventInput`에도 계보를 저장해 공통 snapshot이 재시도 입력을 임시 소비한 뒤 환불해도
   원래 root를 되찾는다. 0-send 재개는 이미 허용된 재시도의 연속이며 새 retry 한도를 만들지 않는다.
2. `available()`은 active 입력뿐 아니라 pending 호출이 임시 소비한 입력도 자기 작업
   경계 시각으로 갱신한다. 환불 때 해당 경계와 원래 시작 시각 기준 backoff 중 늦은 시각을 쓴다.
3. 예산 거절은 확정 지출과 예약을 구분한다. 확정 지출에는 SIM 정산 전이라도 실제 send
   ledger에 기록된 전송을 포함한다. 에피소드·팀 HTTP·로봇 HTTP·논리 호출 한도가 예약으로
   막히면 사건을 보류한다. 정산/환불의 공통 재개 경로에서 다른 로봇의 예산 대기도 깨운다.
   확정 소진·외부 예산 차단 때는 사건을 폐기하고 inbox/출처는 보존한다.

| 반례 | 수정 전 | 수정 후 |
|---|---|---|
| 6.1 실패 → 8.1 snapshot 0-send → 10.1 실패 | 12.1초 세 번째 전송 | 원래 root 유지, 메시지 전송 2회로 종료 |
| 위 연쇄에 6.2초 공통 호출/준비 실패 겹침 | 12.2초 세 번째 전송 | 공통 최소 간격에 따라 8.2/10.2초, 메시지 전송 2회로 종료 |
| 6.1 작업 중 수신 → 7.0 공통 snapshot → 7.2 자기 경계 → 7.4 환불 → 9.0 snapshot 실패 | 30초까지 메시지 포함 요청 없음 | 11.0초 메시지 포함 요청 |
| 상한 5, 4회 전송 + 마지막 슬롯 예약 → 6.1 수신 거절 → 6.4 환불 | 잔여 1회인데 수신 사건 유실 | 6.4초 수신 로봇 재개, 최종 5회 전송 |

통신 3조건 각각을 실제 study 입력 builder·client·send ledger에 가짜 wire/시계로 연결했다.
수정 전 Git blob을 메모리에 적재한 재검증은 **12/12 실패**했다.
[수정 전 반례](review5-counterexamples-before.json),
[수정 후 시간표와 ledger](review5-exit-traces.json)에 원본 시작 시각과 0-send를 구분해 기록했다.

## 불변식과 종료 표

새 회귀 모듈은 반례 12건, 4조건/v64 대조 4건, 예산 4종 × 환불/전송 대기/이미 전송된
상태 12건, 공통 snapshot 환불 뒤 메시지 retry root 보존 1건으로 **29건**이다.
각 반례의 no_comm은 동결 v64와 호출·요청/입력 해시·명령·ledger·예산을 정확히 비교한다.
통신 조건은 동일 외생 사건·응답 비용에서 첫 예산 거절 전까지 공통 일정을 비교한다.
메시지 추가 호출이 공통 타이머·최소 간격·재질문 일정을 바꾸지 않는 기존 생성 검사도 유지한다.
기본 30/90 상한 생성 1,000건과 기존 통합 property 검사도 함께 통과했다.

기존 `review4-exit-*`의 **155행·88개 종료 지점**은 변경하지 않았다.
새 [종료 표](review5-exit-table.md)는 기존 행 재실행에 새 연쇄 상태 **24행**을 더한
**179행**이다. 기존 88개 지점과 새 예산 처리 함수의 반환 2개를 포함해 현재 소스의
**90/90 지점**에 실제 실행 근거가 있다. 모든 boolean 조합을 증명했다는 뜻은 아니다.
[재현 스크립트](audit_review5.py)는 네트워크와 MuJoCo를 차단한다.
기존 변이 2개와 새 결함 변이 3개가 모두 검출됐다([감사 출력](review5-audit.txt)).

CI multiturn job에 새 회귀 모듈을 추가했다. 실제 원격 CI는 실행하지 않았다.
기존 사건 생산·관측·모델 요청 경계와 물리 설정은 변경하지 않았다.
P2(#240/v65 합성)와 실제 다회 파일럿은 이번 수정의 검증 범위 밖이다.

## 검사 환경과 기록

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac`을 사용했다.
pytest에는 모두 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`를 적용했다.
전체 관련 검사는 `tests/test_zone_study*.py`, `test_zone_event_scheduler.py`,
`test_zone_sim_cost.py`를 선택하고 socket 연결과 실제 MuJoCo import를 차단했다.
모델/물리가 없는 단위 검사이므로 사용자 허용에 따라 잠금 없이 실행했다.

초기 fixture에서 관측 tick을 0.1초로 설정하지 않아 pending 환불이 너무 일찍 일어나는
문제를 바로잡았다. 6.2초 공통 호출과 겹치면 최소 간격 때문에 snapshot 실패 시각도
8.1초가 아니라 8.2초다. 또한 v64 비교의 HTTP 총상한을 동일한 5로 맞췄다.
이 초기 테스트 구성 오류는 [초기 로그](review5-core-initial.txt)에 보존했고,
정확한 수정 전 판정은 위 Git blob 대조 JSON을 따른다.

sparse checkout에 없는 과거 v3/v4/v5 gzip fixture 3개는 HEAD blob에서 복원하고,
기존 `raw_index.json`의 SHA-256과 일치하는지 확인해 검사에 사용했다.
검사 후 이번에 만든 복사본만 제거해 원래 sparse 상태로 돌렸다.
기존 fixture·실험 원본·과거 종료 표는 변경하지 않는다.

이 기록은 단위 회귀의 직렬화이며 새 연구·학습·평가 코호트가 아니다.
TensorBoard 변환과 Google Drive 사용은 하지 않았다.

## 최종 결과

**3,293 passed / 0 failed / 0 skipped**, 29개 모듈, 1,196.41초.
앞선 부분 실행은 이 수에 합산하지 않았다.
[전체 pytest 로그](review5-regression.txt), [JUnit XML](review5-regression.xml),
[최종 소스·기록 SHA-256과 정리 확인](review5-validation.json)을 보존했다.
AST·CI YAML 파싱과 `git diff --check`도 통과했다.
`.pytest_tmp`는 삭제했고 임시 fixture 3개도 해시 재확인 뒤 제거했다.
HEAD는 기준 SHA 그대로이며 변경은 로컬 미커밋 상태다.
