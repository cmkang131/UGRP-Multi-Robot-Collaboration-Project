# PR #245 검토 7 수정 — 2026-09-28

기준 HEAD `b454ad3ce63ac9182248ea751e8224ef13762e89`, 브랜치
`codex/zone-study-multiturn`. 사용자 지정 검토 문서를 읽고, 후속 코디네이터 결정에 따라
수정했다. 실제 모델 호출·MuJoCo 물리 step·커밋·push·병합은 0회다.
물리/모델 없는 단위 검사만 사용자 허용에 따라 잠금 없이 실행했다.

## 결정과 근거

**end_reason은 v64 호환 라벨이며 과거 거절 이력 기반, 실제 종료 상태는 end_state로 판단한다.**

동결 v64(`97f91cb040bf382973ce84b24b1ca8399e64a6fb`)의
`zone_study_integration.py.txt:380–395`를 직접 확인했다. `quiescent()`는 자기 작업
유무를 보지만 `finish()`의 라벨은 `budget_refused` 이력만 본다. 다음 실제 가짜-wire
재현으로 초기 요청의 “항상 작업 상태로 분류”와 “v64와 정확히 일치”가 동시에
성립하지 않음을 확인하고 코디네이터에게 알렸다.

| no_comm, HTTP 상한 3 | 작업 수 | 거절 이력 | 동결 v64 | 검토 6 후보 |
|---|---:|---:|---|---|
| claim, 8초 | 3 | 0 | sim_horizon | budget_exhausted |
| continue, 8초 | 0 | 0 | sim_horizon | budget_exhausted |
| claim, 90초 | 3 | 3 | budget_exhausted | budget_exhausted |
| continue, 90초 | 0 | 3 | budget_exhausted | budget_exhausted |

코디네이터가 **no_comm == 동결 v64를 최우선 불변식**으로 지정했다.
따라서 검토 6의 현재 예산/진행 호출 기반 라벨 계산을 v64의 과거 거절 기준으로
되돌렸다. 네 통신 조건에 같은 라벨 규칙을 적용한다. 추가 메시지가 거절 이력을
바꿀 수 있으므로 통신 조건과 no_comm의 라벨이 항상 같다는 뜻은 아니다.
referee에 의한 평가 전용 `orders_complete` 변경 경로는 유지했다.

[수정 전 대조](review7-counterexamples-before.json)는 검토 SHA의 통합 모듈을
메모리에 적재한 결과다. 작업 3개가 남는 4조건 × horizon 8/12/20초에서
**12/12 잘못된 budget_exhausted → 12/12 sim_horizon**을 확인했다.
추가로 무작업 8초와 작업 보유 90초를 각 4조건에서 기록했다.

## 구현과 독립 명세

`IntegratedTrial.finish()`가 모든 조건에 동일한 `end_state`를 붙인다.
`TrialResult`와 `trial_record.json`, `result.json`의 study 요약, CLI 출력까지 전달한다.
독립 `OfflineTrial`은 기본 빈 필드를 가지며 기존 exported record에 빈 상태를 넣지 않는다.

| 필드 | 사실의 기준 |
|---|---|
| quiescent | 확정 예산 소진, 남은 작업 0, 미완료 결정 0 |
| pending_work_count | 자신의 실행기에 job을 가진 로봇 수; 물체/목표 완료 수가 아님 |
| in_flight_calls | outstanding/interrupted/censored SIM 결정 수; 실제 네트워크 연결 수가 아님 |
| censored_calls | horizon 정산으로 닫혔으나 행동을 해제하지 않은 호출 수 |
| committed_sends | send ledger에 확정된 HTTP 전송 수 |
| reserved | 정산 후 남은 HTTP 예약 수 |
| remaining_budget.http_total / http_per_actor | 예약을 차감한 스케줄러 팀/로봇별 HTTP 입장 가능량 |
| remaining_budget.calls_total / calls_per_actor | 설정한 논리 호출 상한에서 확정 호출 수를 뺀 값; HTTP 상한이 먼저 막을 수 있음 |
| horizon_hit | 종료 인자로 받은 SIM 시각이 설정 horizon 이상인지; 조기 finish는 false |

이 사후 사실은 모델 요청·제어·단계 전환에 전달하지 않는다. 영속 pilot/provider 예산이나
upstream 시도 수는 별도이며, 모델 사용량·실물 성공의 근거로 확대하지 않는다.

독립 참조 모델은 production 모듈을 import/상속하지 않는다. 동결 v64의 규칙을
“입장 요청이 거절된 사건이 한 번이라도 존재하는가”로 도출하고, 독립 agenda의
admission 실패 때 `(시각, actor)` 사실을 남긴다. 최종 잔액에서 거절 이력을 역산하지 않는다.
작업 상태는 외생 `busy/boundary` 사건에서 따로 추적하여 `end_state`를 산출한다.
기존 검토 6의 환불 뒤 과거 거절 사례는 라벨 `budget_exhausted`와 잔여 HTTP 1,
`quiescent=false`를 함께 확인하도록 수정했다. 회계/계보 검증은 유지했다.
종료 규칙 변이 검사는 이제 검토 6의 비호환 규칙을 다시 넣으면 독립 명세가 거부하는지 본다.

## v64 비교 필드 전수 점검

기존 signature의 calls/input·request hashes/dispatch/censored/unsent/budget/trace/metrics/ledger를
유지했다. `end_reason`을 직접 추가하고, `dataclasses.asdict(TrialResult)` 전체 및
평가용 `trial_record` 전체를 비교한다. 따라서 run_id/condition/scenario/seed/leader,
계약 호출/메시지/행동/요청 archive, 종료 시각·report, channel, cost와 토큰·SIM 비용,
send ledger의 수·해시·위반, provenance 및 새로 추가될 공통 결과 필드도 비교 대상이다.
`finish()`가 `_collect()`를 다시 append하지 않도록 테스트는 첫 결과를 보관하여 사용한다.
[기계 판독 필드 목록](review7-signature-audit.json)에 TrialResult 16개, leader 조건의
trial_record 최상위 23개, cost 27개 필드와 제외 이유를 보존했다.

제외는 다음 경로로 한정하고 이유·예상값을 검증한다. 그 밖의 요약 필드 제외는 없다.

| 경로 | 제외 사유와 별도 확인 |
|---|---|
| result.end_state / trial_record.end_state | v64에 없는 코디네이터 요청의 새 사실 필드. 3,000개 독립 생성열 및 작업/호출/예산/시간 회귀에서 전체 값 검사 |
| calls[*].provenance.execution_bundle_id, trial_record.provenance.execution_bundle_id | 동결 v64-source-closure와 후보 v66-multiturn의 출처 ID는 달라야 함. 각 예상 ID를 먼저 assert; 다른 provenance 필드 비교 유지 |
| cost.wire_requests, cost.wire_requests_basis | 쓰지 않은 fixture wire의 v64 `0`을 후보가 `null`/requires_provider_reconciliation로 표시한 기존 교정. 정확한 각 값을 assert; 실제 ledger 수·hash·비용은 모두 비교 |

강화된 비교의 초기 실패가 출처 ID와 wire 미측정 표기 차이를 드러냈다. 그 차이를
검사 없이 통째로 삭제하지 않고 위 경로에만 한정했다. 새 테스트 구성 중 continue의
ack=None 및 통신 조건의 추가 거절을 반영한 뒤 다시 실행했다. 초기 구성 실패를
최종 통과 수에 합산하지 않는다.

## 종료 표와 검증

[audit_review7.py](audit_review7.py)는 기존 검토 6의 194행을 현재 코드로 재실행하고
새 36행을 추가했다. [종료 표](review7-exit-table.md)는 **230행·116/116 반환/raise/except
지점**의 실행 근거와 새 상태의 상세 표를 포함한다. 모든 boolean 조합의 형식 증명은 아니다.
[압축 추적](review7-exit-traces.json.gz)은 고정 mtime과 소스 SHA-256을 보존한다.
과거 검토 4/5/6 기록과 동결 v64 파일은 덮어쓰지 않았다.

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac`을 재사용했다.
모든 pytest는 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`로 실행하며 매 실행 후
`.pytest_tmp`를 제거한다. 실행 wrapper는 socket connect/connect_ex와 MuJoCo import를
차단한다. 관련 검사에 필요한 sparse gzip 3개는 HEAD blob·기존 SHA를 확인하여 일시
복원하고, 검사 후 다시 해시를 확인하여 이번 복사본만 제거한다.

초기 대상 검사: **3,302 passed / 0 failed**, 16.10초. CI 목록과 겹치므로 최종 수에 합산하지 않는다.
전용 CI와 같은 7개 모듈 및 관련 회귀의 최종 측정은 아래에 기록한다.

실행:

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/run_review7_tests.py --scope ci
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/run_review7_tests.py --scope related
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/audit_review7.py
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/audit_review7_before.py
```

`git fetch origin`은 공용 `.git`의 FETCH_HEAD 쓰기 제한, `gh pr list`는 네트워크 제한으로
실패했다. 원격 HEAD와 새 GitHub Actions 결과는 확인하지 못했다. 커밋하지 않는 요청에
따라 이번 변경의 원격 CI를 발생시키지 않았다. CI 30분 판정은 로컬에서 같은 pytest
명령을 측정한 범위이며 Ubuntu runner/checkout/의존성 설치를 포함한 작업 시간 보장은 아니다.
기본 checkout main은 깨끗했으며 변경하지 않았다.

새 연구·학습·물리 평가 코호트가 아닌 코드 단위 회귀이므로 TensorBoard 변환은 하지 않았다.
UGRP 예외에 따라 Google Drive는 사용하지 않고 기록을 이 로컬 프로젝트에 보존한다.

## 최종 측정

| 검사 | passed | failed | pytest 시간 | 로컬 wrapper 총시간 |
|---|---:|---:|---:|---:|
| 전용 CI와 동일한 7개 모듈 | 5,335 | 0 | 1,139.35초 | 1,139.46초 (18분 59.46초) |
| 그 밖의 관련 회귀 25개 모듈 | 1,260 | 0 | 234.68초 | 234.82초 (3분 54.82초) |

전용 CI의 pytest 목록은 `.github/workflows/tests.yml`에서 그대로 읽어 실행했다.
30분(1,800초)보다 **660.54초** 짧았다. 새 검토 7 모듈을 포함한 전체 목록의 실측이다.
준비/의존성 설치를 제외한 로컬 Mac 결과이며 원격 GitHub 작업 전체 시간의 보장은 아니다.
[CI 로그](review7-ci.txt), [JUnit](review7-ci.xml), [시간/환경/부하 기록](review7-ci.timing.json)을 보존했다.

두 목록은 파일 단위로 겹치지 않는다. 최종 합계는 **32개 모듈, 6,595 passed / 0 failed /
0 skipped**다. [관련 회귀 로그](review7-related.txt), [JUnit](review7-related.xml),
[시간·정리 결과](review7-related.timing.json)도 보존했다. 저장 `end_state`와 summary의
일치 및 파일 재열기는 네 조건 모두 통과했다.

`.pytest_tmp` 없음, 임시 sparse fixture 3개 제거, 작업 HEAD 불변을 확인했다.
동결 v64 세 파일은 manifest SHA-256과 원래 commit의 blob까지 일치한다.
AST 검사·`git diff --check`, 종료 표와 gzip JSON의 36개 상태 행/230개 전체 행 재읽기,
116/116 지점 실행 및 추적 소스 해시를 확인했다.
[최종 검증·파일 해시](review7-validation.json)에 근거를 남겼다. 변경은 모두 로컬 미커밋 상태다.
