# 통합 러너의 PairTeam·자기 영상·인식 지연 연결

## #223 다회 결정 감사와 v66 후보 (2026-09-27)

감사 기준은 main `97f91cb040bf382973ce84b24b1ca8399e64a6fb`다. 지정한 네 파일은
GitHub main의 blob과 대조했다. **main에도 메시지 수신 재호출은 있었지만, 실행 중인
자기 작업의 경계를 기다리지는 않았다.** #238의 첫 호출 파일럿은 별도
`run_zone_study_pilot.pilot_call_policy()`가 `trigger_on_message=False`, 재질문 999초를
사용했으므로 통합 러너의 다회 동작과 다르다.

| main v64 경로 | 실제 동작과 한계 |
|---|---|
| `zone_study_protocol.Transport` → `EventScheduler._on_message` | 허용 채널에서 받아 실제 inbox에 commit한 뒤 `report`를 예약한다. `no_comm`은 채널이 닫혀 이 경로가 없다. leader는 hub-and-spoke이며 follower끼리 직접 전달하지 않는다. |
| `_on_call_start` | 로봇당 outstanding 1개, 시작 간격 2초. 사고 중 트리거는 하나로 합쳐 완료 뒤 재호출한다. **실행기 job의 BUSY 여부는 보지 않는다.** |
| `IntegratedTrial.snapshot/build_inputs` | 호출 시작 시 자기 RGB·자기 이력·이미 받은 inbox를 고정한다. 나중에 도착한 메시지가 진행 중 호출의 입력에 소급 삽입되지는 않는다. |
| `IntegratedTrial._on_action` → `executor_plan` | 비용 해제 후 그 로봇 API에 claim을 낸다. 진행 중 작업이 있으면 실행기의 `BUSY` 거절이 가능하다. idle `wait`도 10초 hold job을 만들므로 메시지에 대한 새 claim이 거절될 수 있다. |
| 상한 | 논리 호출 30/로봇, HTTP 시도 30/로봇·90/시행, outstanding 1, scheduler retry 1. `w1` 창 하나만 열며 수락 발화 2/로봇·6/창. 기존 `cap_total`은 미설정이지만 창을 재개하지 않아 사실상 시행 6발화다. horizon은 사전등록 값이다. |
| 공통 깨우기 | 시작·자기 작업 완료/실패·자기 장애 사건·자기 타이머(idle 10초, busy 60초, pending 1개). 관측 1초 tick 자체는 호출하지 않는다. 동료 작업 완료/평가 GT는 트리거가 아니다. |

#229 병합 검사의 `test_pair_and_multiple_real_adapter_calls_use_each_own_camera`는
실제 입력 builder·Gemini client·send ledger와 가짜 wire를 연결해 로봇별 여러 호출,
후속 inbox, `report`, 개별 자기 카메라 JPEG, PairTeam 연결을 검사했다.
5.3/5.4초 follower 결정 → 6.1초 leader 전달이라는 순서와 **수신 후 다른 claim의
실행기 수락**을 검증한 것은 아니다. `FixtureActor`의 선택도 받은 분배문을 이해해
주문을 바꾸는 모델이 아니다.

### v66 결정 기회와 종료

새 후보는 `zone-study-integration-v66-multiturn`이다. 원격 main/열린 PR 6개에서
RGB 최대 v63, integration 최대 v64를 확인했다. #240의 로컬 미push 작업에
`v65-pair-close`가 있어 v65를 건너뛰었다. 확인 SHA·blob·경로는
[번호 감사](../experiments/2026-09-27-zone-study-multiturn/remote-audit.json)에 있다.
v1/v2/v64 기록과 번들 JSON은 그대로 두며, #240의 v65 변경을 이 후보에 합치지 않았다.
동시 작업이므로 push/병합 전 번호와 소스의 재확인이 필요하다.
**#240 병합 후 main 반영하며 v66을 pair v5 기반 합성 버전으로 재검증**한다.
이 병합 충돌(P2)은 이번 수정 범위가 아니며, 현재 후보는 계속 pair v4다.

2026-09-28 검토 4 P1 수정의 정책은 `v64_tagged_event_inputs.v4`다.
`DecisionScheduler`는 사건 원인·자기 작업 가용 시각·예산만 설정하며, 메시지 전용
`_push`·`_on_call_start`·`_submit`·`_resume_deferred`와 대기 사전을 두지 않는다.

- **공통 사건 불변식:** 시작·자기 완료/실패·안전 사건·타이머·재시도는 v64와 같은
  queue 순서, outstanding 보류, 최소 시작 간격과 재시도 경로를 쓴다. `_deferred`는
  원인별 키를 사용해 메시지 사건이 공통 사건을 흡수하지 못한다. 같은 시각의 자기
  완료와 타이머가 v64에서 두 호출이면 여기서도 두 호출이다.
- **수신 사건:** 한 수신은 `EventInput(cause='message', tags=(수신 ID,))` 한 개다.
  자기 작업 중이면 `available_at=inf`(아직 알려지지 않은 자기 작업 경계), 경계 사건에서
  해당 시각으로 바꾼다. 이후의 대기·재개·재시도·정산은 `EventScheduler`가 처리한다.
  사건의 출처는 보존하고 같은 원인만 병합한다. 공통 snapshot이 수신 입력을 사용하면
  해당 사건을 소비하며, 그 snapshot이 0-send이면 **같은 사건**을 환불 경로에서 복원해
  최소 간격 뒤 재개한다. 새 메시지나 메시지 전용 재개 사건을 만들지 않는다.
  inbox 이력은 보존하며 이미 만든 snapshot에 미래 메시지를 넣지 않는다.
- **공통 호출 우선:** 같은 시각에는 모든 공통 시작을 먼저 처리하고 메시지 시작을
  뒤에 처리한다. 추가 호출 뒤 예측하지 못한 공통 사건이 와도 공통 시각을 지켜야 하므로
  공통/메시지의 outstanding·최소 간격 상태를 분리한다. `max_outstanding_per_actor=1`은
  각 경로에 적용한다. 이미 시작한 메시지 호출과 나중의 공통 호출은 겹칠 수 있다.
  메시지 호출은 기존 호출 뒤 최소 간격을 지키지만 공통 last-start를 변경하지 않는다.
- **재시도·타이머:** 공통 재시도는 v64 그대로다. 메시지 재시도는 기존 retry 구현을
  사용하면서 메시지 경로와 원인 ID·`retry_of`를 유지한다. 공통 호출은 보류된 메시지
  재시도도 소비할 수 있다. 메시지 추가 호출의 응답은 공통 re-ask 타이머를 예약하지 않는다.
- **no_comm 기준선:** 메시지 경로에 진입하지 않는다. idle `wait`는 기존
  `hold(10.0)`·`zone_study_action_map.v2_pair` 그대로이며, 자기 명령 이력의
  `duration_s: 10.0`, hold 종료 사건과 공통 타이머를 유지한다.
- 실제 전송 상한은 **30/로봇, 90/시행**이다. 진행 중 예약도 wire 진입을 막는 데
  포함하지만, 0-send 정산은 전액 환불한다. 증가만 하는 call ID serial을 사용하지 않는다.
  시행 상한은 `AttemptBudget`에 적용해 한 호출의 여러 HTTP 전송도 각각 센다.
  v64의 로봇별 논리 호출 상한 30과 HTTP 상한 30도 유지한다.
  수락 발화는 **2/로봇, 6/시행**이고 창은 갱신하지 않는다. 전송 ledger·HTTP/영속 예산과
  SIM 비용 정산은 두 경로가 공유한다. 예산 소진으로 전송이 중단되는 규칙은 유지한다.
  추가 호출도 같은 유한 예산을 소비하므로, 조건 간 스케줄 불변 검사는 동일한 외생 공통
  사건·공통 응답 비용과 예산이 충분한 구간에서 한다. 메시지가 바꾼 실제 행동·작업 종료
  시각이나 소진 이후까지 조건별 전체 실행 시간이 같다는 주장은 아니다.

### 종료 라벨과 종료 상태 (검토 7, 2026-09-28)

코디네이터 결정으로 `no_comm`의 동결 v64 호환을 우선한다.
**end_reason은 v64 호환 라벨이며 과거 거절 이력 기반, 실제 종료 상태는 end_state로 판단한다.**
통합층은 한 번이라도 결정 입장이 예산으로 거절됐으면 `budget_exhausted`, 아니면
`sim_horizon`을 기록한다. 현재 잔여 예산이나 작업 완료를 이 라벨로 추정하지 않는다.
평가 전용 referee가 `orders_complete`로 판정하는 기존 별도 경로는 유지한다.

네 조건 모두 `TrialResult`, 저장 `trial_record.json`, `result.json`의 study 요약과 CLI 출력에
`end_state`를 기록한다. 정산 후 작업 보유 로봇 수, 미완료/censored 호출 수, 확정 HTTP
send 수, 예약 수, 팀/로봇별 HTTP·논리 호출 잔여량, 설정 horizon 도달 여부를 포함한다.
`quiescent`는 확정 예산 소진 상태에서 작업과 미완료 호출이 모두 없는지를 뜻한다.
censored 호출은 shutdown 뒤에도 미완료 결정으로 센다. 잔여량은 스케줄러 장부 기준이며
영속 pilot/upstream provider의 별도 예산·과금 잔액이 아니다. 이 사후 기록을 모델 입력이나
제어/단계 전환에 사용하지 않는다.

예를 들어 HTTP 3회 뒤 작업 3개가 남은 8초 종료와 무작업 8초 종료는 `no_comm`에서
모두 `sim_horizon`이지만, `pending_work_count`는 3과 0, `quiescent`는 false와 true다.
90초 동안 거절을 기록한 뒤에는 작업이 남아도 라벨은 `budget_exhausted`다.
[검토 7 결정·비교 필드 감사·검증 기록](../experiments/2026-09-27-zone-study-multiturn/review7-fix.md)을 따른다.

### SIM 비용과 기록

기본 정상/invalid 시도 비용은 `1 + 0.0002×입력토큰 + 0.02×출력토큰 + 0.3×생성발화수`
초다. error의 기본항은 0.5초, timeout은 20초이며 시도별 비용을 합한 뒤 0.1초 단위로
올림한다. 입력은 기존 고정 토큰 규칙, 실제 adapter의 출력은 응답 원문 tokenizer다.
모델 wall 지연을 SIM 비용으로 대체하지 않는다. 행동·발화 해제는 `시작 + 비용`,
메시지 inbox 도착은 `해제 + 0.1초`다. 동시 호출 비용은 서로 겹치며 로봇별 합산 비용을
에피소드 경과 시간이라고 부르지 않는다. 파라미터는 잠정 모델이며 실측 속도 보정이 아니다.

`study/decision_events.jsonl`에 작업 보류·호출 시작·시행/파일럿 예산 거절과 트리거를
기록한다. 시작에는 `cause=common|message`, 실제 수신 `message_ids`, `retry_of`가 있어
공통 호출과 메시지에서 유래한 추가 호출·재시도를 구분한다. `scheduler_events.jsonl`, `inputs.jsonl`의 inbox ID, `dispatch.jsonl`, 기존
call/message cost 기록을 call ID로 연결하면 **수신 → 경계 → 결정 시작 → 비용 해제 →
새 claim 수락** 순서를 복원할 수 있다. 모델 adapter의 `wire_requests`는 독립 대사 전
`null`로 기록한다(쓰지 않은 fixture wire의 0을 실제 전송 0으로 표시하던 진단 오류 수정).
send ledger 수와 제공자 upstream 시도/과금 대조는 계속 구분한다.

가짜 전송 회귀는 4조건의 첫 결정 5.3/5.4/6.0초와 전달 6.1초를 고정한다. busy follower는
8.0초 합성 자기 작업 경계 뒤 재호출하고 13.3/13.4초 새 주문이 수락된다. idle follower는
6.1초에 시작한다(첫 행동 `continue`, 자기 job 없음). 첫 행동이 명시적 `wait`이면 r1은
15.3초 hold 종료 뒤 재결정한다. 작업 경계가 없을 때도 r1은 네 조건 모두 65.3초 timer에서
결정하고 보류 메시지를 읽는다. `no_comm`에는 메시지·inbox·report가 없다.

v64 기준 SHA `97f91cb040bf382973ce84b24b1ca8399e64a6fb`의 scheduler·offline·integration
원본은 `tests/fixtures/zone_study_multiturn/v64/`에 해시와 함께 고정했다. 시드 300개의
공통 사건·동시각·오류·timeout·재시도 사건열로 no_comm의 전체 호출 기록·입력 해시·실제
요청 해시·dispatch 바이트·censored 기록을 대조한다. 같은 사건열의 통신 3조건에서는
공통 호출 시각·횟수·순서·재시도 계보와 추가 호출의 실제 메시지 원인을 검사한다.

두 반례의 v64 기준 r1 호출은 다음과 같다.

- 6.0초 오류 종료·메시지 전달·타이머: `[0, 5.5, 7.5, 12.8]`. 재검토 당시 no_comm의
  3회 역시 잘못된 공통 병합이었다. 7.5초는 계보가 있는 재시도, 12.8초는 공통 타이머다.
- 65.3초 자기 작업 종료·타이머: `[0, 65.3, 70.6]`. 두 공통 사건을 유지한다.

**응답과 작업 경계는 fixture이며 모델 이해·통신 효과·배송 성공의 증거가 아니다.**
재검토 수정·검증 범위는 [PR #245 재검토 수정 기록](zone_study_pr245_review2.md)을 따른다.
[이전 수정 기록](zone_study_pr245_review1.md)과
[초기 작업 기록](../experiments/2026-09-27-zone-study-multiturn/README.md)은 당시 기록으로 보존한다.

### 실제 LLM 파일럿 계획 — 이번 작업에서는 명령만 기록

2026-09-27 23:27 KST에 기존 `zone-study-adapter-pilot-r10/budget.sqlite`를 `mode=ro`로
읽었다. 17 send 중 정상 16건 정산 후 **18 attempts / 409,793 tokens 차감**, 잔여는
**582 attempts / 4,590,207 tokens**다. 600/5M 상한·실패 1건의 전액 예약은 유지된다.
실제 provider total 185,007과 차감량은 다른 수치다. [DB 해시와 상태](../experiments/2026-09-27-zone-study-multiturn/budget-readonly.json)를
보존했다. 이후 다른 작업의 사용량을 포함해 실행 직전에 다시 확인한다.

현재 DB identity의 `source_root`는 `/Users/changmin/projects/ugrp-wt/kiro-study-core`,
`pipeline`은 `AdapterTrial`이다. 기존 migration은 root/pipeline 변경을 허용하지 않는다.
아래 명령은 기존 어댑터의 소스 검토·preflight 단계에 한정하며, 현재 작업 경로에서 그대로
실행하거나 DB identity를 임의 수정하면 안 된다. 다회 driver 연결 시 이 호환성도 검토한다.

소스를 검토·커밋하고 동결한 뒤 기존 같은 DB에 소스를 이관하고 전체 대사와 새 4조건
preflight를 수행한다. 새 예산 생성, 자동 정산, 설치 프록시 수정은 하지 않는다.
요청/실효 설정은 현재 DB 계약(`REQUESTED`/`EFFECTIVE`, temperature 0.0)을 따른다.
초기 #222의 temperature 0.2 제안으로 기존 예약 계약을 바꾸지 않는다.

```sh
PYTHON=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PILOT_ROOT=/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10
# 아래 명령은 이 작업에서 실행하지 않는다. 모든 출력 이름은 미사용 경로여야 한다.
# 기존 DB의 source_root에서 검토된 소스를 준비한 뒤 수행하는 어댑터 점검 명령이다.
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --reconcile-only \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/multiturn-budget-review-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --migrate-source \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/multiturn-source-migration-01" \
  --migration-reason '#223 reviewed multiturn integration source' \
  --from-identity-sha256 "$REVIEWED_IDENTITY_SHA" --expected-state-sha256 "$REVIEWED_STATE_SHA"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.build_proxy_log_telemetry \
  --budget-file "$PILOT_ROOT/budget.sqlite" --proxy-log "$REVIEWED_PROXY_LOG" \
  --log-timezone Asia/Seoul --output "$PILOT_ROOT/multiturn-telemetry-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --reconcile-only \
  --budget-file "$PILOT_ROOT/budget.sqlite" \
  --upstream-telemetry "$PILOT_ROOT/multiturn-telemetry-01/telemetry.jsonl" \
  --output "$PILOT_ROOT/multiturn-reconcile-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.sim_cli workflow run zone-study-pilot -- \
  --execute --stage preflight --budget-file "$PILOT_ROOT/budget.sqlite" --proxy-pid "$PROXY_PID" \
  --proxy-log "$REVIEWED_PROXY_LOG" --acknowledge-upstream-finish-limitation \
  --upstream-telemetry "$PILOT_ROOT/multiturn-telemetry-01/telemetry.jsonl" \
  --output "$PILOT_ROOT/multiturn-preflight-01"
```

위 preflight는 **기존 첫 호출 어댑터 점검**이다. 현재 `run_zone_study_pilot --stage cohort`도
`trigger_on_message=False`여서 v66 다회 검증 명령으로 쓸 수 없다. 통합 CLI는 여전히
fixture 전용이다. 실제 다회 코호트는 기존 `ModelAdapter` + `run_trial(..., model_adapter=...)`
연결점에 preflight/대사/영속 예산 driver를 연결한 뒤 별도 실행 명령을 고정해야 한다.
이 작업에서는 실제 호출 진입점을 새로 열지 않았다. 로봇별 다른 실제 자기 RGB 입력,
3회/로봇·9회/조건(4조건 최대 36 proxy POST, 재시도 포함 별도 상한), seed 11,
SIM 120초를 초기 계획으로 하고, 같은 DB의 요청별 예약 가능량을 우선한다.
통합 물리 경로를 선택한다면 별도 물리 승인·잠금과 고정 source/bundle이 필요하다.
새 모델/물리 결과가 생긴 뒤에만 기존 TensorBoard 절차로 새 snapshot을 등록한다.

---

아래는 v64까지의 통합 배경이다. 현재 결정 정책은 위 v66 절이 대체한다.

2026-09-27, PR #229의 #194 + #235 통합. `tags_temporary`는 **임시, 표식 사용, 연구 결과 아님**이다. 이 변경은 비물리 테스트로 검증하며 새 물리 성공이나 실제 LLM 코호트를 뜻하지 않는다.

## 결정과 공동 운반

`IntegratedTrial`은 #194의 입력 계약·한국어 프롬프트·메시지 bus·SIM 비용·재질문 스케줄러를 재사용한다. `claim`의 주문이 단독이면 `deliver`, 2인 `long_beam`이면 `pair_carry(order_id, zone, partner_id)`를 호출한다. `HostRobotLink.call`은 #235의 `OwnCamTeamHost.call`을 사용하므로 PairTeam의 독립 제출·짝 매칭·취소·예약 명령 정리가 실제 적용된다. 한 로봇의 claim으로 상대 작업을 자동 시작하지 않는다.

현재 #235가 지원하는 짝은 **r1=end_neg, r2=end_pos**다. 다른 역할·r3 짝·heavy_crate·3인 주문은 거절하며 단독 배송으로 바꾸지 않는다. 이 고정 역할 제한은 네 조건에 동일하다. 일반 역할 할당 연구로 확대하려면 실행기 지원 범위를 먼저 넓혀야 한다.

`zone_pair_status_v4`가 유일한 짝 상태 채널이다. `PairStatusBus`는 실제 `PairTeam.records()`의 감사 기록만 반환하며 별도의 사용되지 않는 채널을 만들지 않는다. 상태 enum과 촬영 시각·프레임 ID·유효시한만 짝 동기화에 사용한다. 모델 입력·연구 스케줄러에는 짝 상태를 넣지 않고, GT·접촉·측정 관절·동료 작업 종료로 깨우지 않는다. 모델 사고 중에는 진행 중인 자기 작업을 계속하고, 유휴 로봇만 대기한다.

`configs/zone_study_integration/i2_pair_long_beam.json`과 `pair_dev_DRAFT.json`은 2대 빔 주문의 실행 설정이다. coarse sheet는 실행 전에 고정하며 runtime 좌표에서 재생성하지 않는다. #235의 표준 `TaggedCargoZoneScene` 준비 함수를 재사용한다. 이 draft는 실행되지 않았고 source/bundle pin과 실행 예산 확정이 남아 있다. 기존 `prereg.json`과 과거 결과는 보존했다. 앞선 `zone-study-integration-v2-pair-delay`의 기록은 그대로 보존한다. 현재 후보는 `zone-study-integration-v64-source-closure`이며 과거 실행의 성공을 승계하지 않는다.

## 실행 소스 고정 (PR #229 P1 수정)

번들의 `runtime_files_sha256`은 러너·지원 모델 transport의 전이 import closure에서 만든다. 함수 안의 import, 상대 import, package initializer도 읽으며 모듈을 실행하지 않는다. `student.skill_module`과 provider `factory`의 설정 선택 모듈도 시작점에 포함한다. provider 등록 파일·추가 source_files·실제 보정·지도·시나리오 해시는 함께 고정한다. `visual_arm.py`, `llm_completion.py`, `session_scenes.py`를 포함한 의존 소스 변경은 번들 해시를 바꾼다.

비-dev 실행은 물리 모듈 import·host 생성·출력 디렉터리 생성 전에 `prereg.source_sha` 또는 `--expected-source-sha`를 Git commit으로 해석하여 HEAD와 대조한다. 둘 다 있으면 모두 일치해야 한다. 누락·미해결/다른 SHA·dirty 실행 소스·번들 불일치를 거절한다. dev는 미등록 배선 진단을 허용하지만 명시한 SHA는 dev에서도 검사한다. `--bundle`은 실행 없이 현재 후보의 해시를 출력한다. 이번 작업은 미커밋이므로 DRAFT의 source/bundle pin을 확정하지 않는다.

번호는 로컬 branch/remote refs 259개에서 공통 RGB 최대 v63·통합 최대 v2를 확인해 v64를 선택했다. fetch/PR 목록 갱신은 sandbox·네트워크 제한으로 실패했으므로 원격의 최신 번호 예약 확인은 별도다. [수정·검증 기록](../experiments/2026-09-27-pr229-source-delay/README.md)에 확인 범위와 번들 후보를 보존한다.

## 실제 M2와 지연 provider의 비물리 회귀 (P2 수정)

`tests/test_zone_study_pair_delay.py`는 실제 `PairTeam`·`M2DoorStudent`·`GuardedPairApproach`·`DelayedPoseSource`·태그 검출기/PF를 가짜 물리 시계에서 연결한다. 저장된 r1/r2 자기 RGB 18장과 발행 서보 명령만 사용하며, 평가 좌표는 fixture에 넣지 않는다. 입장 시 추정과 gate도 영상에서 만든다. 열린 checkpoint부터 M2가 PF를 교체하고 재관측·파지 영상 판정·readiness·동시 GO를 수행하는 구간을 검증한다. 추정·guard·readiness를 stub으로 바꾸지 않는다.

앞선 팔 안정화 대기가 6초 남은 r1 fixture에서는 두 로봇이 새 추정과 유효 readiness를 얻고 같은 시각에 `lift_go_1`을 발행한다. 대기 차가 없는 재생에서는 먼저 준비된 r1의 자세 불확실성이 상대 대기 중 커져 중단하며, 과거 readiness로 GO하지 않는 것도 검사한다. 두 경우 모두 PF 교체 후 0.16초 이전 추정 공개 차단을 확인한다. 이는 저장 영상의 시간·인터페이스 회귀이며 실제 접근·운반·물리 성공이나 네 조건 연구 비교가 아니다.

## 자기 손목 프레임과 다회 모델 호출

각 `HostRobotLink`는 자기 포트의 `robot_cam`만 받는다. robot ID·camera·JPEG SHA-256을 검사하고 호출 시작 시점까지의 최신 자기 프레임을 snapshot한다. `build_inputs`는 이 JPEG를 `CURRENT OWN WRIST RGB`로 실어 #194의 `ModelCallTransport`와 **실제 GeminiProxyCompleter**에 보낸다. 통합 경로는 `FrameLibrary`를 읽을 수 없다. 요청 이미지 원문과 해시는 `study/request_images/`, 요청·호출·입력 기록은 `study/`에, 실행기의 전체 촬영 원본은 `own_frames/<robot>/`에 보존한다.

CLI 기본은 fixture다. 실제 모델을 붙이는 프로그램 연결점은 `ModelAdapter(client_factory, send_ledger)`와 `run_trial(..., model_adapter=...)`다. `gemini_client_factory(..., study_json=True)`와 #194의 **기존 persistent budget을 소유한 PilotSendLedger**를 시행마다 만든다. 일반 live SendLedger는 transport가 거부한다. 새 예산이나 네트워크 우회 경로를 만들지 않는다. 모델·설정 해시는 bundle/provenance에 기록하고, 실제 adapter의 출력 SIM 비용은 응답 텍스트 토큰 수로 계산한다. 이 작업에서 실제 모델을 호출하지 않았다.

통신 3조건은 실제 전달된 메시지에 의한 `report` 호출과 inbox를 사용한다. `no_comm`에는 수신/송신이 없으며 자기 작업 사건과 자기 idle/busy 타이머로 반복 결정한다. 늦게 도착한 리더 메시지가 첫 결정 뒤의 재결정에 들어가는지 네 조건을 검사한다.

## 연구 전체 접촉 프로필

#190의 `s1`–`s6` 설정은 모두 `cargo_noslip_v1`, weld OFF다. 과거 실험 JSON은 덮어쓰지 않았다. 통합 러너는 시나리오·episode 중 어느 쪽이든 이 프로필과 다르면 시작 전에 거절한다.

bundle의 `contact_profile_expected`는 base + cargo XML 변환으로 계산한 `noslip_iterations=10`, `timestep_s=0.00025`와 프로필/소스 해시를 담는다. 물리 host 생성 뒤 실제 적용값과 대조한다. **manifest의 `applied_contact_profile`은 host의 실제 model option에서 읽은 기록**이며 예상값을 복사하지 않는다. host 생성 전 실패하면 null이다. XML 검사와 실제 접촉/운반 검증은 별개다.

## tags_temporary와 #237 교체 연결점

현재 registry의 선택 항목은 `tags_temporary`뿐이다. 모든 pose provider를 `DelayedPoseSource`로 감싸며 **촬영 SIM 시각 + 0.16 s** 이전에는 새 추정을 `report()`와 `loc.estimate()/predict_to()` 어느 쪽에도 공개하지 않는다. 입력 순서를 보존하려고 자기 명령·motion profile·프레임을 같은 지연된 필터 시계에서 재생한다. 추정 시각은 지연된 시각 그대로이며 현재 시각으로 위장하지 않는다. 로봇의 실제 명령 실행이나 LLM의 원시 JPEG 전달을 0.16 s 늦추는 정책은 아니다. provider 추론 wall 시간은 `robots/<id>/inputs/pose_timing.jsonl`에 따로 기록하고 SIM 지연 값으로 쓰지 않는다.

#237 `vision_zero_tag_v1` 교체 전 필요한 조건:

- registry의 factory를 `harness.vision_pose_source:VisionPoseSource`로 등록하고 소스·worker 설정·모델·실제 보정 해시를 고정한다. runner는 student에게 실제 전달한 보정을 provider 기록에도 사용한다.
- `zone_wide_door_walls_v3_notags`와 태그 없는 표준 Scene 연결을 추가한다. 현재 tags 장면 검사를 우회하거나 태그 지도로 비전 성능을 보고하지 않는다.
- 사전 등록 episode의 `pose_priors[robot_id]`에 **자기 출발 도크**의 mean/std/source를 넣는다. `StudyTeamHost`는 provider가 `init_prior`를 지원할 때 이를 호출하고 누락을 거부한다. runtime GT로 초기화하지 않는다.
- `StudyTeamHost.close()`는 각 provider의 `close()`를 호출해 worker를 정리한다. worker 실패 때 report와 loc 양쪽의 fail-closed 동작, 고정 지연, 명령 시간 정렬을 재검증한다.
- #235의 M2 재위치 추정은 태그 PF를 교체하는 경로가 있다. 현재 adapter는 이때도 지연 인터페이스를 유지하고 reset 전 대기 관측을 버린다. 비전 provider에서는 이 교체를 거절하므로, 교체 전에 태그 필터 생성 없이 비전 필터를 재초기화하는 명시적 adapter가 필요하다.
- VIS3 게이트 FAIL과 폐루프 dev 한계를 유지한다. provider 교체는 이 변경에서 하지 않는다.

## 검증과 남은 실행

`tests/test_zone_study_integration_pair.py`는 가짜 물리 시계·응답 wire만 대체하고 실제 연구 scheduler, 입력 builder, Gemini adapter, host API, PairTeam, 짝 상태 채널을 실행한다. 모델 호출과 물리 step은 없다. 기본 통합/격리·실행기/짝 회귀도 함께 검사한다.

남은 물리 검증은 고정 소스·예산·잠금 아래 새 draft의 4조건 전체 실행, 실제 자기 프레임 감사, 0.16 s 지연에서의 위치 불확실도와 짝 readiness/heartbeat, 파지·문 통과·방출·abort·거짓 확인, 실제 적용 프로필과 weld OFF 확인이다. 실제 LLM 파일럿과 태그 0개 provider 검증도 별도다. 물리/모델 결과가 생기면 기존 지침에 따라 새 TensorBoard snapshot으로 전달한다.

## 근거

- [참고 자료](references.md): cargo profile과 재사용 모듈의 출처.
- [이슈 #222](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/222), [#223 fixture/다회 결정 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/223#issuecomment-5852769695).
- [#216 고정 인식 지연 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216#issuecomment-5852229650), [#237 provider 계약과 미완료 게이트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/237).
