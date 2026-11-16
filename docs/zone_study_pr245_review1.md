# PR #245 P1 수정 기록 — 2026-09-28

검토·작업 기준 SHA는 `894de3dbf42b3dffa9fcc695d2b4f5a45e48f1a3`이다.
검토 원문은 `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-245-review1.md`다.
모델 호출·물리 step·Git 커밋·push·병합 없이 해당 worktree에서 수정했다.

## P1-1: 메시지 보류와 공통 결정 기회 분리

기존 후보는 작업 중 받은 `report`를 core scheduler의 `_deferred`에 넣고,
나중의 timer에도 합쳤다. 합친 집합에 report가 있으면 다시 작업 경계까지 보류해
타이머 결정과 후속 예약이 사라졌다. 수정 전 회귀에서 경계가 없는 r1은 no_comm만
65.3초에 호출했고, 통신 3조건은 첫 호출 뒤 150초까지 추가 호출이 없었다.

수정 정책 `own_job_boundary_or_common_trigger.v2`는 작업 때문에 기다리는 report를
로봇별 `_job_reports`로 분리한다. 작업 중 **report만** 있으면 보류하며, timer·idle·시작·
안전 사건·재시도 등 공통 트리거가 있으면 메시지를 함께 읽되 공통 자격을 그대로 따른다.
core `_deferred`는 기존처럼 outstanding 호출 때문에 기다리는 트리거만 보관한다.
최소 간격으로 미뤄진 payload에도 공통 트리거와 report가 함께 남는다.

따라서 같은 자기 작업 상태·사고 상태·예산에서 공통 트리거 결정 시점이 네 조건에서 같다.
메시지는 자기 작업 경계와 timer 중 먼저 오는 기회에 반영된다. 사고 중에는 no_comm과
동일하게 outstanding 해제/최소 간격을 기다리며, 이미 시작한 입력 snapshot은 바뀌지 않는다.
동시각 전달·경계·timer는 한 번의 호출로 합친다. 예산 소진·horizon 제한은 그대로다.
inbox는 감사용 이력으로 유지하되, 다음 허용 결정에서도 읽지 않는 보류 문제를 제거했다.

작업 중 timer가 허용하는 새 claim은 실행기에서 `BUSY`로 거절될 수 있다. 이는 no_comm과
같은 동작이며, 호스트가 기존 작업을 자동 중단하거나 모델 행동을 보정하지 않는다.

## P1-2: v64 기준선 보존 선택

**기준선을 유지한다. 새 idle wait 기준선을 등록하지 않는다.** 연구 질문은 통신 효과이며
대기 실행 방식까지 바꿀 필요가 없다. 최초 후보의 native idle 변경은 90초 반복 wait 대조에서
r1 호출을 9회에서 6회로 줄이고 명령 이력을 빈 인자로 바꾸는 혼입을 만들었다.

네 조건 모두 v64의 `hold(10.0)`, 자기 명령 이력 `duration_s: 10.0`, hold 종료 사건,
busy/idle 재질문 예약을 복원했다. `action_map`도 `zone_study_action_map.v2_pair` 및
`wait_hold_s=10.0`으로 돌렸다. 명시적 wait로 만든 hold 중에는 메시지 때문에 자동 abort하지
않고 경계/공통 timer를 따른다. 자기 job이 없는 idle 상태에서는 기존처럼 즉시 재결정할 수 있다.

90초 대조는 네 조건 모두 무발화·반복 wait, 동일 자기 RGB/시계/응답 비용을 쓴다.
v64 통합 모듈을 고정 SHA `97f91cb040bf382973ce84b24b1ca8399e64a6fb`에서 메모리로 읽어
생성한 [고정 fixture](../tests/fixtures/zone_study_multiturn/v64_wait_90s.json)와 비교한다.
[생성기](../tests/fixtures/zone_study_multiturn/build_v64_wait_control.py)는 기존 파일을 덮어쓰지 않는다.
공유 scheduler·입력 builder·가짜 wire/시계는 작업 트리 버전을 쓰는 **소스 단위 대조**이며,
과거 checkout 전체 재실행이나 물리 코호트 재현이 아니다.

조건별 전체 입력 해시, 호출 시작/종료·트리거, dispatch 해시를 대조한다. 조건 간에는
condition·channel·inbox·dialogue_window·leader_id·role만 제외하고 공통 입력 해시를
비교한다. 제외된 필드도 조건별 v64 전체 입력 대조에는 포함한다.
첫 두 입력만 검사하지 않고 90초 동안 발생한 모든 요청을 검사한다.

| 대조 | r1 호출 시작 SIM 초 |
|---|---|
| v64와 수정 후보, 네 조건 모두 | 0, 15.3, 30.6, 45.9, 61.2, 66.5, 71.9, 81.8, 87.2 |
| 수정 전 후보, 네 조건 모두 | 0, 15.3, 30.6, 45.9, 61.2, 76.5 |

두 번째 요청의 자기 명령 인자는 다시 `duration_s: 10.0`이다. 과거 v64 번들·prereg·
실험 기록과 이전 v66 후보의 JSON/로그는 그대로 보존했다. 이전 27초 비교의 no_comm 불변
주장은 90초와 입력 전체로 일반화할 수 없었으며, 현재 판단은 새 회귀 범위로 제한한다.

## 비물리 검증과 기록

새 회귀는 65.3초 반례와 130.6초 재예약, 경계가 먼저/동시에 오는 경우, 사고 중 도착한
메시지와 공통 timer/경계, 최소 시작 간격, 동시각 전달+timer, 명시적 wait/실제 idle의
차이, 4조건 90초 대조를 검사한다. 기존 ledger·SIM 비용·예산·입력 경계·pair v4·
source-pinning 검사도 실행한다. 실제 모델/물리 성공·provider 정산·통신 효과 검증이 아니다.

검증 로그와 수정 후보 번들은
[새 기록 폴더](../experiments/2026-09-27-zone-study-multiturn/review1-20260928/)에 별도로 둔다.
실행별 결과는 다음과 같다. 중복 실행의 검사 수를 합산하지 않는다.

- 수정 전 반례: **7 failed / 9 passed**. 90초 wait 대조 네 조건과 작업 경계 없는 통신
  3조건의 timer 검사에서 실패해 두 P1을 재현했다.
- 수정 후 관련 13모듈: **537 passed / 1 failed**. 새 다회 결정 모듈의 79개는 모두
  통과했다. 실패 1개는 idle timer 테스트가 명시적 wait를 job 없는 idle로 취급한 fixture였다.
- 해당 fixture를 실제 idle인 `continue`로 고친 뒤 통합 모듈 전체 **66 passed**.
  두 실행 사이 제품 소스는 바꾸지 않았다. 관련 13모듈 전체를 마지막에 재실행한 것은 아니다.

초기 대상 검사에서 생긴 기대값 수정도 로그로 보존했다. wait를 job 없는 idle로 가정한
테스트는 hold 경계 검사와 idle continue 검사로 구분했다. 조건 간 공통 입력의 비교에서는
dialogue_window와 leader 역할 메타데이터를 명시적으로 제외하도록 고쳤다. 조건별 v64
전체 요청 해시 비교에서는 어떤 필드도 제외하지 않는다.

관련 검사 실행 범위:

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_multiturn.py tests/test_zone_study_integration.py \
  tests/test_zone_study_integration_pair.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_study_integration_seams.py tests/test_zone_study_pair_delay.py \
  tests/test_zone_study_protocol.py tests/test_zone_study_offline.py \
  tests/test_zone_study_review_r7_transport.py tests/test_zone_study_review_r8.py \
  tests/test_zone_study_review_r10.py tests/test_zone_event_scheduler.py \
  tests/test_zone_sim_cost.py --basetemp=./.pytest_tmp -q --tb=short
```

pytest는 모두 `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`로 실행하고 실행 뒤 임시
디렉터리를 삭제했다. 모델·물리가 없는 테스트만 실행하므로 사용자 지시에 따라 잠금은 잡지 않았다.
이는 단위 회귀 기록이므로 새 실험 코호트나 TensorBoard snapshot으로 등록하지 않았다.
UGRP의 로컬 보존 예외에 따라 Drive 작업은 수행하지 않았다.

`--bundle`로만 생성한 수정 후보의 해시는
`84769cc9a1ac0d70af5fd1711b944f55e05eda65676603b0c57d29e478bd96dc`다.
직렬화한 JSON을 다시 읽고 런타임 파일 **171개 SHA-256**을 실제 파일과 대조했다.
현재 source/bundle은 미커밋 후보이며 prereg의 null pin을 확정하지 않았다.
[검증 메타데이터](../experiments/2026-09-27-zone-study-multiturn/review1-20260928/verification.json)에
수정 소스·fixture·로그 해시와 각 실행의 범위를 기록했다.

## P2와 남은 범위

**#240 병합 후 main 반영하며 v66을 pair v5 기반 합성 버전으로 재검증**한다.
이번에는 #240/v65를 합치거나 충돌을 해결하지 않았다. 현재 v66 후보는 계속 pair v4이며
이 회귀로 pair v5·합성 버전·물리 실행 준비 완료를 선언하지 않는다.

GitHub connector로 #245 원격 HEAD가 작업 기준 SHA와 같고 #240 HEAD가
`3ea2edc08e5addafaf3cedc934c463ad8e1635c8`임을 확인했다. 기본 checkout은 main이며
로컬 HEAD/origin/main이 `ba0eb4f547996af880de65003442882c5326c71d`로 같았다.
`git fetch origin`은 공유 `.git/worktrees/.../FETCH_HEAD` 쓰기 제한, `gh pr list/view`는
네트워크 제한으로 실패했다. origin 설정이나 다른 checkout을 바꾸지 않았다.
수정은 미커밋이며 원격 PR·CI에 반영되지 않았다.
