# #223 다회 결정 루프 감사·수정 (2026-09-27)

**가짜 전송·가짜 SIM 시계 회귀만 완료했다. 실제 모델 호출 0회, 물리 step 0회다.**
작업 브랜치는 `codex/zone-study-multiturn`, 기준 SHA는
`97f91cb040bf382973ce84b24b1ca8399e64a6fb`다. 요청대로 커밋·push·PR·병합은 하지 않았다.
언어 이해, 통신의 인과 효과, 운반 성공, 실제 provider 과금은 이 회귀의 검증 범위가 아니다.

## main 감사와 변경

main의 통합 러너는 이미 inbox 수신 시 `report` 재호출을 예약했다. 시작 간격 2초,
outstanding 1개, 로봇별 호출 30회·HTTP 30회, 시행 HTTP 90회였다. 사고 중 수신은
다음 호출에 합쳐졌으나 **실행 중 자기 작업의 경계는 기다리지 않았다.** 따라서 새 claim이
`BUSY`로 거절됐다. idle `wait`가 10초 hold job을 만들어 같은 문제를 일으켰다.

#229의 가짜 전송 검사는 여러 호출·후속 inbox·자기 RGB·PairTeam 연결을 확인했다.
#238 첫 호출 파일럿은 별도 `pilot_call_policy(trigger_on_message=False)`를 썼다.
첫 호출 파일럿의 결과를 통합 경로에 재호출 자체가 없다는 증거로 해석하지 않았다.
파일별 경로·상한·SIM 비용의 자세한 감사는
[통합 문서](../../docs/zone_study_integration.md)에 있다.

- 새 `DecisionScheduler`는 수신 report를 자기 작업이 끝나거나 실패할 때까지 합친다.
  idle은 즉시 호출 자격을 얻되 공통 최소 간격·outstanding·예산을 따른다.
- idle `wait`는 native idle hold를 유지한다. 명시적인 busy wait/release의 abort 동작은 유지한다.
  공통 시작·자기 완료/실패·안전 사건·기존 타이머는 네 조건에 동일하다.
- 기본 논리 호출은 30/로봇·90/시행, HTTP는 30/로봇·90/시행이다.
  발화 2/로봇·6/시행, 창 1개를 명시하며 기존 더 낮은 채널 상한은 유지한다.
  영속 파일럿 예산 거절은 wire 전에 추가 결정을 중단한다. 진행 중 작업은 계속한다.
- `decision_events.jsonl`에 보류·실제 시작·시행/파일럿 예산 거절을 추가한다.
  기존 call/message cost·inbox·dispatch와 연결해 수신→경계→호출→SIM 비용 해제→수락을 확인한다.
- 실제 adapter에서 쓰지 않은 fixture wire의 0을 전송 측정값으로 기록하던 진단 오류를 고쳤다.
  `wire_requests=null`이며 send ledger와 upstream 대조의 구분은 유지한다.

## 소스·번들 확인

`git fetch origin`은 공유 Git 디렉터리의 `FETCH_HEAD` 쓰기 권한 때문에 실패했고,
`gh` 조회는 네트워크 제한으로 실패했다. GitHub connector로 main의 지정 네 파일 blob과
열린 PR 188·239·240·241·242·243의 관련 파일을 대조했다.
[remote-audit.json](remote-audit.json)에 SHA와 blob을 보존했다.

원격 RGB 최대 v63, integration 최대 v64였다. #240 로컬 작업
`/Users/changmin/projects/ugrp-wt/codex-pair-grasp/harness/zone_study_integration.py`의
미push `v65-pair-close`도 읽고 **`zone-study-integration-v66-multiturn`**을 선택했다.
#240의 pair v5 변경을 합치지 않았고 이 후보는 기존 pair v4를 쓴다.
동시 작업의 번호 충돌 가능성은 push/병합 전에 다시 확인해야 한다.

과거 prereg·번들·실험 기록은 변경하지 않았다. 새
[multiturn_dev_DRAFT.json](../../configs/zone_study_integration/multiturn_dev_DRAFT.json)은
미실행 fixture DRAFT이며 source/bundle pin은 `null`이다. 실제 모델 계획과 구분한다.
물리를 import하지 않는 `--bundle`로 [bundle-candidate.json](bundle-candidate.json)을 생성했다.
번들 해시는 `e5109d2785f1808dee22c733ad86c65ef2dbc71ff097646680da47ca6fdec93e`,
runtime closure는 171개 파일이다. 미커밋 후보 해시이며 실행 소스 동결을 뜻하지 않는다.

## 검증

관련 13개 모듈 **502 passed**. [pytest 출력](regression.txt)을 보존했다.
이후 legacy hold 타이머를 반영한 기록 helper 변경 뒤 새 모듈을 다시 실행해
**43 passed**를 확인했다([최종 대상 검사](final-targeted-regression.txt)). 두 수를 합산하지 않는다.
모든 pytest는 `OMP_NUM_THREADS=1 --basetemp=./.pytest_tmp`를 사용했고 종료 후 해당 디렉터리를 지웠다.

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_multiturn.py tests/test_zone_study_integration.py \
  tests/test_zone_study_integration_pair.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_study_integration_seams.py tests/test_zone_study_pair_delay.py \
  tests/test_zone_event_scheduler.py tests/test_zone_sim_cost.py \
  tests/test_zone_study_protocol.py tests/test_zone_study_offline.py \
  tests/test_zone_study_review_r7_transport.py tests/test_zone_study_review_r8.py \
  tests/test_zone_study_review_r10.py --basetemp=./.pytest_tmp -q
```

새 테스트 43개는 실제 입력 builder·Gemini client·send ledger·ZoneOwnExecutor에 가짜
wire를 붙인다. socket과 MuJoCo import는 차단한다. 기존 저장 자기 RGB만 읽으며 물리는
진행하지 않는다. 토큰 비용 fixture로 follower 5.3/5.4초, leader 6.0초 응답 해제와
6.1초 전달을 만든다. 새 응답의 주문 변경은 fixture 규칙이지 LLM 이해 결과가 아니다.

검사 범위는 다음과 같다.

- 4조건의 늦은 메시지: 8.0초 합성 자기 작업 경계에서 호출, 13.3/13.4초 새 claim 수락.
- idle 수신 즉시 6.1초 재호출, leader hub-and-spoke, no_comm의 메시지/inbox/report 없음.
- 메시지가 없을 때 자기 작업 완료·실패의 호출 순서/시각이 네 조건에서 같음.
- 로봇별·시행별 논리/HTTP 상한 도달 시 idle 종료, 발화 상한 거절도 비용 청구.
- 동일 시각 수신/종료 병합, 사고 중 수신 snapshot 격리, 공통 최소 시작 간격.
- 가짜 영속 DB의 attempts/tokens 소진 시 wire 전 차단, 시작한 호출의 비용 정산.
- 기존 채널·평가 격리·source closure·PairTeam/지연 provider 회귀.

초기 검증의 실패는 바뀐 idle/report 의미를 가정한 기존 테스트, 시행 상한이 로봇별 균등
배분을 보장한다는 새 테스트의 잘못된 가정, 채널별 발화 상한을 공통 설정으로 비교한
오류였다. 기대값과 공통 설정 비교 범위를 고친 뒤 위 회귀가 통과했다.

### v64 반례 기록

[build_regression_records.py](build_regression_records.py)는 기준 Git의 integration 모듈을
메모리에 읽어 동일 fixture와 연결했다. 공통 scheduler/client는 작업 트리 버전을 사용한다.
이는 과거 checkout 전체 재실행이나 과거 물리 코호트 재현이 아닌 **소스 단위 대조**다.

[regression-traces-v2.json](regression-traces-v2.json)이 유효 비교 기록이다. 최초
[regression-traces.json](regression-traces.json)은 legacy hold의 가짜 타이머를 만료시키지
않은 진단 기록으로 보존했으며 no_comm 비교 근거에서 제외했다. v2는 hold의 자체 시간만
진행하며 물리 step은 없다. 27 SIM초까지 4조건 × 최초 claim/wait × 2버전을 기록했다.

| 첫 행동 | v64 follower r1 | v66 follower r1 |
|---|---|---|
| claim, 자기 경계 20초 | 6.1초 재호출 → 11.4초 order-2 `BUSY`; 20초 공통 재호출 후 25.3초 수락 | 6.1초 보류 → 20초 재호출 → 25.3초 order-2 수락 |
| wait | 6.1초 재호출 → 11.4초 새 claim `BUSY`; hold 만료 뒤 재호출에서 수락 | 6.1초 재호출 → 11.4초 새 claim 수락 |

no_comm의 호출 `(actor, started_sim_s, finished_sim_s)`는 두 버전에서 claim/wait 모두 같다.
busy 대조에서 채널 조건은 7회→5회로 줄었다. idle 대조는 8회로 같다. v66에도 이후
기존 공통 idle 타이머가 재호출하면 fixture가 같은 claim을 다시 내 `BUSY`로 거절될 수 있다.
모든 BUSY 제거를 주장하지 않으며 호스트가 claim을 자동 보정하지 않는다.

## #222 잔여 예산과 다음 단계

기존 DB를 SQLite `mode=ro`와 `PilotBudget(read_only=True)`로 읽었다.
2026-09-27 23:27 KST 기준 17 send 중 16 settlement, 차감
**18 attempts / 409,793 tokens**, 잔여 **582 attempts / 4,590,207 tokens**다.
원래 예약 34 attempts / 4,085,674 tokens와 실제 provider total 185,007은 별도 값이다.
실패 1건의 전액 예약을 유지했다. DB·state hash와 조회 범위는
[budget-readonly.json](budget-readonly.json)에 있다. 실제 DB 쓰기·정산·이관은 하지 않았다.

DB identity는 `source_root=/Users/changmin/projects/ugrp-wt/kiro-study-core`,
`pipeline=AdapterTrial`이며 현재 migration은 이 두 필드 변경을 허용하지 않는다.
기존 어댑터 점검 명령과 새 다회 driver 실행을 동일한 것으로 취급하지 않는다.

실제 LLM 계획 명령은 [통합 문서](../../docs/zone_study_integration.md)에만 썼다.
기존 `--stage cohort`는 메시지 트리거를 끄므로 v66 다회 실행 명령으로 제시하지 않았다.
현재 통합 CLI는 fixture 전용이고, 실제 다회 코호트는 `ModelAdapter`/`run_trial` 연결점에
기존 preflight·대사·영속 예산 driver를 연결하고 검토한 실행 명령을 확정해야 한다.
초기 상한 3회/로봇·9회/조건, 4조건 총 최대 36 proxy POST이며, 요청별 토큰 예약 가능량이
더 먼저 제한할 수 있다. 실제 호출·물리 실행의 승인이나 준비 완료 판정은 아니다.

이 기록은 단위 회귀의 직렬화로 새 연구/평가 코호트가 아니다. TensorBoard 스냅샷은
만들지 않았다. 실제 모델/물리 결과가 생기면 원본 보존과 기존 TensorBoard 절차를 따른다.

관련 근거: [이슈 #223](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/223),
[PR #238](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/238),
[예산 #222](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/222),
[#229 검증 기록](../2026-09-27-pr229-source-delay/README.md).

## PR #245 검토 3 후속 — 2026-09-28

0-send 환불도 공통 완료 경로에서 보류 메시지를 깨우도록 수정했다.
생성 property 712건, 종료 경로 24종의 표 기반 검사 101건을 포함해 관련 회귀
1,751건을 확인했다. 실제 모델 호출·물리 step·커밋은 0회다.
반례·검증 범위·초기 실패와 수정·원본 해시는 [검토 3 수정 기록](review3-fix.md)을 따른다.

## PR #245 검토 4 후속 — 2026-09-28

메시지 전용 대기·재개 코드를 제거하고 v64 코어의 원인 태그 사건 입력으로 통합했다.
0-send 환불을 실제 전송 상한에 반영했다. 기본 30/90·무작위 실패 생성 1,000건을 포함해
서로 다른 단위 회귀 3,012건 통과, 반환·예외 88개 지점의 실행 추적을 확인했다.
[구조 수정·검증 기록](review4-fix.md), [종료·분기 표](review4-exit-table.md)를 따른다.
모델 호출·물리 step·커밋·push·병합은 0회이며 P2(#240)는 후속이다.

## PR #245 검토 5 후속 — 2026-09-28

재시도 계보, pending snapshot이 지난 자기 작업 경계, 환불 가능한 예산 예약을
보류·재개 중에 보존하도록 수정했다. 새 회귀 29건을 포함한 관련 검사 **3,293건 통과**,
기존 155행·88개 지점 기록을 보존하고 연쇄 상태 24행을 추가했다.
현재 소스는 179행·90/90 종료 지점에 실행 근거가 있고 결함 변이 5개가 검출됐다.
[수정·검증 기록](review5-fix.md), [확장 종료 표](review5-exit-table.md)를 따른다.
실제 모델 호출·물리 step·커밋·push·병합은 0회다.
