# PR #245 검토 6 구조 수정 — 2026-09-28

기준 HEAD `9fb47846b4bbb35be5692345843aadd896b6e3eb`, 브랜치
`codex/zone-study-multiturn`, 작업 경로 `/Users/changmin/projects/ugrp-wt/codex-multiturn`.
사용자가 지정한 검토 5·6 원문을 읽고 수정했다. 실제 모델 호출·MuJoCo 물리 step·
커밋·push·병합은 모두 0회다. 단위 검사만 잠금 없이 실행했다.

`git fetch origin`은 공용 `.git` 쓰기 제한, `gh pr list`는 네트워크 제한으로 실패했다.
GitHub 커넥터도 기존 저장소 주소의 301 이전 응답을 반환했고, 반환된 숫자 repository
endpoint는 도구의 허용 URL 범위 밖이었다. 따라서 원격 PR HEAD/CI를 새로 확인했다고
주장하지 않는다. 로컬 HEAD는 검토 6의 SHA와 같고 기본 checkout은 깨끗한 main
`ba0eb4f547996af880de65003442882c5326c71d`였다. 원격·브랜치·Git 메타데이터는 변경하지 않았다.

## 구조 변경

- `RetryRoot(cause, call_id)`로 공통 root와 사건 root를 구분한다. 사건의 계보는
  `EventInput`이 소유하고, 지연 큐의 오래된 `retry_of`나 공통 호출의 계보를 빌리지 않는다.
  0-send 환불과 자기 작업 경계 갱신은 같은 사건을 보존한다.
- 여러 사건이 한 호출로 합쳐져도 각 입력의 root별 재시도 허용량을 유지한다.
  실패한 메시지 재시도에 새 메시지가 합쳐지면, 소진된 옛 root를 되살리지 않고 새
  메시지에만 자기 재시도를 허용한다. 이 추가 반례도 발견·수정·회귀 고정했다.
- `AttemptBudget`이 HTTP·논리 호출의 예약과 확정 사용을 함께 조회한다.
  `remaining()`은 예약까지 차감한 현재 입장 가능량,
  `remaining(confirmed_only=True)`와 `confirmed_usage()`는 실제 send ledger의
  되돌릴 수 없는 사용량이다. SIM 정산 전 실제 전송도 확정 사용이다.
  기존 `used`/`reserved` 직렬화는 v64 비교를 위해 보존한다.
  논리 호출의 admission/확정 한도도 이 객체에서 계산하고, `metrics`는 보고용이다.
- 공통 재질문은 동결 v64처럼 확정 논리 호출 상한·자기 작업 상태·horizon으로 생성한다.
  HTTP 잔여/임시 예약 때문에 미래 타이머를 없애지 않는다. 타이머 발화 시 실제 입장
  예산을 검사한다. HTTP 상한과 episode 상한이 같을 때 거절 로그까지 v64 경로를 유지한다.
- 종료 사유는 현재 확정 소진·잔여·진행/censored 호출에서 계산한다.
  `budget_refused`와 과거 진단 카운터는 종료 사유에 쓰지 않는다. 미완료 SIM 호출이
  horizon에서 censored되면 `sim_horizon`이다. 별도 영속 pilot 예산의 차단 계약은 유지한다.

입력 builder·자기 RGB/지도/자기 명령 경계·물리 설정·모델 요청에는 새 상태를 넣지 않았다.
DecisionScheduler에는 생명주기 override를 추가하지 않았다.
검토 5에서 유예한 #240/v65 합성과 실제 다회 파일럿은 계속 검증 범위 밖이다.

## 반례와 실행 명세

수정 전 HEAD를 메모리에 적재하고 같은 가짜 wire로 다시 실행했다.
[수정 전 대조](review6-counterexamples-before.json):

| 연쇄 | 수정 전 | 수정 후 |
|---|---|---|
| 공통 실패 → 메시지 도착 → 공통 retry 0-send → 첫 메시지 실패 | 18/18에서 메시지 retry 누락 | 새 메시지 root로 retry 허용 |
| 마지막 슬롯 예약 → 5.3/5.4 재질문 → 환불 | 32조건 중 16에서 세 번째 send 누락 | 모든 조건에서 v64의 15.3초 send 유지 |
| 임시 예산 거절 → 환불·수신자 0-send → 6.7초 horizon | 통신 3/3에서 budget_exhausted 오기 | 3/4 사용·잔여 1·진행 없음 → sim_horizon |
| 옛 메시지 실패 → .4초 공통 호출 → .6초 새 메시지 → 합쳐진 실패 | 새 메시지 retry도 누락 | 2.4초 합쳐진 호출 뒤 새 입력만 4.4초 retry |

검토 5의 12개 연쇄 반례와 4종 예산의 환불/전송 대기/이미 전송 상태를 포함한
기존 29개 회귀도 유지했다. 기존 종료 표의 예산 고갈 주입은 reporting metrics 변경에서
회계 객체의 상한 주입으로 옮겼다.

`tests/zone_multiturn_reference.py`는 production 모듈을 import하지 않는 순수 Python
실행 명세다. 정수 시각·독립 agenda·사건/호출 사실 테이블로 전송·환불·root별 재시도·
종료 상태를 산출한다. 실제 스케줄러를 상속하거나 production 예산/시간 함수를 사용하지 않는다.

`tests/test_zone_study_multiturn_model.py`는 기본 **3,000개** 사건열을 시드
`2456000 + seed`로 생성한다. 공통 실패, 메시지, 자기 작업 보류/경계, snapshot 0-send,
지연 환불, 추가 예약, 즉시/정산 전 전송, 상한, 최소 간격, 재질문과 horizon을 조합한다.
동시각·±1 ns·±1 μs를 포함한다. 사건 시각의 기존 1 μs 반올림 규약과 raw horizon
비교를 구분한다. 호출/시각/원인/계보, 실제 send, 환불 수량, 입력 snapshot,
active/claimed 사건, censored 및 종료 사유를 차등 비교한다.

추가 200개 생성열은 no_comm의 ledger·trace·예산·metrics·censored를 동결 v64와
정규 JSON **바이트 단위로** 비교한다. 기존 실제 study 요청·입력 해시·명령 비교도
강화해 예산 refusal/trace/metrics 제외를 없앴다. 동결 소스 및 해시는 수정하지 않았다.
통신 3조건의 공통 일정·메시지 추가성과 입력 경계는 기존 통합 생성 검사와 새 연쇄
검사로 확인한다. 공통 일정 비교는 동일 외생 사건·응답 비용, 공유 예산의 첫 거절 전
범위다. 추가 전송이 유한 공유 예산을 먼저 소진한 이후까지 같은 호출 수를 주장하지 않는다.

결함 변이를 넣으면 참조 검사가 반드시 실패한다: 공통 계보 혼입 시드 30,
예약에 의한 타이머 제거 1235, 과거 거절 종료 판정 1, 합쳐진 입력의 root 혼입 479.
새 두 테스트 모듈을 `.github/workflows/tests.yml`의 v64 비교 단계에 추가했다.

## 종료 표와 검증 기록

[audit_review6.py](audit_review6.py)가 기존 179행과 새 검토 6 연쇄 12행,
회계 precondition/재질문 확정 상한 2행과 합쳐진 새 사건 계보 1행을 재생한다. 새 [종료 표](review6-exit-table.md)는
**194행·114/114 반환·raise·except 지점**의 실제 실행 근거를 포함한다.
코어/DecisionScheduler 외에 회계 객체와 통합 재질문/종료 함수도 열거한다.
모든 boolean 조합의 형식 증명이라는 뜻은 아니다.
[압축 추적](review6-exit-traces.json.gz)은 고정 mtime으로 재현 가능하게 저장했고,
과거 review4/review5 원본·종료 표는 수정하지 않았다.

기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac`을 재사용했다.
모든 pytest는 `OMP_NUM_THREADS=1`과 `--basetemp=./.pytest_tmp`를 사용한다.
전체 검사에서는 socket connect/connect_ex와 MuJoCo import도 차단했다.
누락 sparse gzip fixture 3개는 HEAD blob에서 해시 검증 후 임시 복원하고, 검사 뒤
해시를 다시 확인해 이번 복사본만 제거한다. `.pytest_tmp`도 종료 때 제거한다.

초기 테스트 구성 오류(동결 클래스에 없는 조회 메서드, 참조 모델의 busy timer label)는
초기 로그에 보존했다. 강화한 바이트 비교가 드러낸 episode/HTTP 거절 진단 차이도
수정했다. 추가 메시지 root 반례를 발견해 첫 전체 실행을 중단했고, 중단 기록을
별도 보존했다. 부분 실행 결과를 최종 전체 검사 수에 합산하지 않는다.

이 기록은 단위 회귀 결과이며 새 연구/학습/물리 평가 코호트가 아니다.
TensorBoard 변환과 Google Drive 사용은 하지 않았다.

## 최종 결과

**6,552 passed / 0 failed / 0 skipped**, 31개 모듈, 1,301.81초.
[전체 로그](review6-regression.txt)와 [JUnit XML](review6-regression.xml)을 보존했다.
전체 실행 중 새 병합 사건 회귀의 메시지 ID를 서로 다른 고유 값으로 명시했다.
그 변경이 있는 두 테스트 모듈은 종료 후 **313 passed / 0 failed**로 다시 확인했다
([최종 부분 검사](review6-final-targeted.txt)). 겹치는 검사 수는 합산하지 않았다.

`.pytest_tmp` 없음, 임시 sparse fixture 3개 제거, 기준 HEAD 불변을 확인했다.
동결 v64 3개 파일은 manifest SHA-256뿐 아니라 원래 Git commit의 blob과도 바이트가 같다.
AST·CI YAML·새 모듈 등록·종료 표 재읽기/해시·`git diff --check`가 모두 통과했다.
[최종 검증/파일 해시](review6-validation.json)를 보존했다. 원격 CI는 미실행·미확인이다.
변경은 모두 로컬 미커밋 상태다.

재현(프로젝트 root, 기존 환경):

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/run_review6_tests.py
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/audit_review6.py
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-multiturn/audit_review6_before.py
```
