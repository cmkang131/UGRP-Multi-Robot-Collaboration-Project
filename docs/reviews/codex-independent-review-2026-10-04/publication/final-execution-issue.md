2026-10-03 독립 검토. **현재 DEV의 좁은 실행 경계와 결과를 신뢰할 수 있게 하는 기록 경계를 분리합니다.** 이 항목 전부가 현재 영상 실패 원인이라는 뜻은 아닙니다. 관련 #216 #219 #221 #222 #223 #224 #226.

기준 main은 `f2577bb5121748644df31eb0fc5a1c1b94b80d80`. PR #363/#371의 최신성은 해당 절에 따로 표시합니다. 코드 변경·새 물리/렌더·실제 LLM·학습·실기기 접속은 없었으며 heldout raw/outcome은 열지 않았습니다. 재현은 원본 함수/AST, fake transport·worker·작은 임시 입력으로 한정했고 독립 검토자가 주요 반례를 다시 확인했습니다. 게시 전 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`은 보존 규칙 관련4문서만 바뀌었으며 아래 공통 코드 재현은 그대로인 범위입니다.

## 먼저 닫을 실행 경계

### E0. 최신 DEV는 합류 이후로 이동 — 과거 rendezvous 진단은 이력으로 보존

[17:01Z 공개 DEV 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5971355260)은 코드 `3358372e`/기록 head `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`에서 두 로봇의 opening look이 7.8초에 끝나 합류를 통과했다고 보고합니다. `raise_high`는 approach의 `PAIR_COLLISION_GUARD`, `raise_high_align`은 `wait_close`까지 진행한 뒤 `BEAM_UNCERTAIN → PREGRASP_NOT_READY`로 멈췄습니다. HIGH staged 두 경로는 적재 상태 오류가 사라졌으나 `gate_ok=false`/명령0으로 입장 전 미도달입니다. floor staged 두 경로는 폐기하고 정상 opening look을 유지하는 align 진입으로 바꿨습니다. P03은 미시작입니다. **저자의 공개 요약이며 raw 독립 검증·운반 성공 확인이 아닙니다.**

[#363 당시 공개 DEV 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5970568489)의 raise_high는 accepted measurement 139/23 이후 12.1 SIM초에 PAIR_RENDEZVOUS_TIMEOUT을 보고했습니다. raw는 열지 않았습니다. 실행7623→기록81db의 차이가 README16줄인 것을 확인하고 코드의 의미만 교차검토했습니다.

**이전 7623/81db 당시의 구분은 r2가 아직 opening look으로 busy였는지, 이미 idle인데 pair admission에 거절됐는지였습니다.** 두 경우 모두 보고된 종료와 양립합니다. 측정 count는 이 질문을 답하지 않습니다.

| source에서 확인된 의미 | 다음 한 행 기록 |
|---|---|
| [Runtime](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_final_pair_runtime.py#L56-L74)은 각 opening job이 끝난 다음 tick에 각자 submit. [start](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_pair_executor.py#L563-L599)의 첫 accepted submit에 now+5 deadline | 로봇별 opening 시작/종료/종료이유, accepted/rejected API ACK·reason/failed_checks |
| [check](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_pair_executor.py#L312-L340)는 같은 task 양측 start_ready가 없을 때 rendezvous deadline을 검사. 이후 heartbeat의 PARTNER_SILENT/PARTNER_ABORT와 별개 | 동일 task ID·양측 첫 start_ready·deadline·abort의 absolute SIM time. 다른 session ready를 합산하지 않음 |
| [status publish](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_pair_status.py#L117-L132)는 동기적 | 이미 수락됐지만 비동기 status가 늦었다는 설명을 기본가정으로 삼지 않음 |
| [runner](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/scripts/run_pair_highpose.py#L192-L223)는 양측 동일 backend.now, tick당1회50ms advance. elapsed는 reset/preroll 이후이고 종료는 advance 뒤 읽음 | command kind별 수·unique timestamp·tick·case start. 한 tick 여러 명령이나 absolute/elapsed 차이를 clock skew라고 하지 않음 |

원본 check AST+실제 PairStatusChannel/Endpoint의 별도 합성에서는 첫 제출8.3/deadline13.3을 두고 peer 미제출13.25엔 no abort,13.3엔 RENDEZVOUS_TIMEOUT, 양측 ready 후 stale peer엔 PARTNER_SILENT, fresh peer엔 no abort였습니다. 실제 DEV trace 재현·원인 확정이 아닙니다. floor staged의 gatefalse/명령0은 입장 전 미도달이며 파지 제어 실패로 바꿔 부르지 않습니다. HIGH unloaded 표기와 E2 메커니즘의 일치도 수정만으로 전체 성공을 보장하지 않습니다.

과거 공개 요약의 ‘두 배 hold’와 양립하는 당시 source 경로도 있습니다. 새 v98는 전용 wrapper로 중복 hold를 제거했습니다. [_sweep_steps/_tick_sweep](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_own_executor.py#L703-L755)는 stationary reobserve의 hold에 기본 hold를 붙여 한 tick에 `[hold, hold]`를 낼 수 있습니다. 원본 두 메서드+실제 SweepRecheck의 합성에서 t1.95/t2.00에 각각 두 hold지만 누적 대기는0/.05초였습니다. **실제 r2가 그 분기였다는 증명이나 중복 hold의 성능 결함 판정은 아닙니다.**

opening look의 원인이 필요하면 sweep stage/target PWM/transition result/waited_s/pose std·time을 기록합니다. sweep_guard 상세는 own executor `_summaries`에 있으나 [Runtime.record](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_final_pair_runtime.py#L83-L86)에 직접 export되지 않으므로 전부 이미 saved result에 있다고 가정하지 않습니다. 기존 audit의 전환부터 요약하고 빠진 이유만 향후 private DEV receipt에 노출하는 범위이며 actor 입력/peer 메시지에 상대 pose를 추가하지 않습니다.

실제 [admission 불리언](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/81dbb3eb5c0a915b6b314e3c4898ea253f890267/harness/zone_pair_admission.py#L52-L65)을 그대로 설명하고 fix-age를 새 입장 문턱으로 추가하지 않습니다. 총 case cap 증가만으로 이미 timeout된 pair가 자동 재결합하지 않으며, timeout/영상 문턱 완화는 이 진단의 결론이 아닙니다.

### E1. 같은 tick의 peer abort 뒤 이미 모은 non-hold 명령이 dispatch됩니다 — P1, 현재 공통 final runtime

**결론:** final-pair scheduler는 각 actor의 명령을 모은 뒤 pair abort를 전파한다. 이 과정에서 이미 모은 명령을 취소하지 않아, 두 actor가 terminal이 된 다음에도 앞 actor의 새 이동 명령을 backend로 전달한다. 현재 정상 루프에서는 다음 **0.05 SIM s tick**의 pending hold까지 살아 있다. 재현 명령의 0.15 s는 lease 길이이며 정상 루프의 잔존시간으로 주장하지 않는다. 물리적 이동거리, 접촉, 실험 실패 원인은 측정하지 않았다.

고정 코드:

- [Runtime.step 56–74](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_pair_runtime.py#L56-L74): actor 순서대로 `issued`에 복사한 뒤 `team.poll(now)`, 그대로 return.
- [Team의 cancellation 235–249](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_pair_skill.py#L235-L249): `cancel_scheduled = lambda *a: None`.
- [PairExecution.abort / clear 295–310](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_pair_executor.py#L295-L310)와 [poll 602–614](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_pair_executor.py#L602-L614): 내부 queue는 지우고 양쪽을 terminal로 만들지만 Runtime의 지역 `issued` list는 접근하지 않는다.
- [runner 92–99](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/run_final_pair_v3.py#L92-L99): 반환 batch를 terminal 재검사 없이 `backend.issue → runtime.on_command`로 보내고 다음 SIM tick으로 advance.
- [v3 backend 78–84](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/final_pair_v3.py#L78-L84) → [base backend 90–107](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/final_environment_checks.py#L90-L107): 학생 task에서는 collection guard가 꺼져 있고, non-hold는 실제 port.apply로 간다. physics advance는 각 port.tick을 부른다.
- [OwnExecutor on_command 197–215](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_own_executor.py#L197-L215): 종료 뒤 command receipt를 전달할 뿐 새 명령을 거부하거나 hold로 바꾸지 않는다.
- [PR #363 runner210–217](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/scripts/run_pair_highpose.py#L210-L217)도 최종 veto 없이 발행합니다. 81db→73429982에서 shared Runtime.step/executor/skill/backend는 그대로이고 [HIGH Runtime431–445](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_runtime.py#L431-L445)는 그 step을 상속합니다. 새 Execution.step은 frame-gate import를 바꾼 기존 code object이며 actor 명령 수집 뒤의 최종 veto를 추가하지 않습니다. 이전 반례를 현재 source 경계에 연결한 확인이며 새 head에서 재현/물리를 실행한 것은 아닙니다.

**작은 반례와 도달 조건:** 이미 입장 완료·fresh frame·guard 통과한 pair tick에서 r1이 `mecanum(forward=.1, left=turn=0, duration=.15)`을 만든 뒤, r2의 local controller가 실패한다. 이런 순서는 r2의 이미지/pose gate 실패나 controller failure가 첫 actor 처리 이후 판명되면 실제 호출 흐름에서 가능하다. 반례는 특정 실제 사진이 실패를 유발한다고 주장하지 않고 실패 상태 전환을 boundary에서 주입했다.

검토용 scheduler 반례 결과:

```text
issued_same_tick = [(r1, mecanum(.1, 0, 0, .15)), (r2, hold)]
terminal_after_poll = {r1: True, r2: True}
r1 job_failed reason = PARTNER_ABORT
pending_hold_after_poll = {r1: True, r2: True}
next_tick(.05) = [(r1, hold), (r2, hold)]
```

독립 후속 확인은 exact `BaseBackend.issue`, `Runtime.on_command`, `ZoneOwnExecutor.on_command`와 실제 `CameraRobotPort`까지 실행한다. fake robot은 setpoint만 기록하며 MuJoCo를 만들지 않는다. 양쪽 terminal 이후 r1 motor setpoint는 `[.1,.1,.1,.1]`, own-command receipt도 그 이동 명령이다. `port.tick(.049)`에는 그대로이며 `.05` hold에서 `[0,0,0,0]`이 된다. 따라서 단지 반환 list에 명령이 남는 문제를 넘어서, 현재 adapter의 액추에이터 명령 경계까지 dispatch 가능함을 확인했다. 종료로 `own._pair=None`이 되어 이어지는 `Runtime.arm_step`도 같은 tick에 r1 hold를 추가하지 않는다. stage probe가 실패를 보고 loop를 끊는 경우 역시 advance 뒤 break이며 backend.close에서 hold한다.

**재현 범위:** cv2/pytest가 없는 환경이므로 원본 class 전체 import 대신 exact AST 메서드 몸체를 사용했다. scheduler / own executor job lifecycle / pair abort·check·poll은 원본이고 PairStatusChannel/Endpoint와 CameraRobotPort는 실제 모듈이다. frame validity, bootstrap, controller의 합성 출력, collision guard만 boundary fake다. 정상 진입이나 물리 성공에 대한 full integration test는 아니다. tests 담당이 독립 작성·실행했고 control 담당이 재실행 및 dispatch 확장을 했다.

**기존 테스트가 놓치는 지점:** `tests/test_zone_final_pair_v3.py`의 full-protocol 테스트는 `FakeRuntime.step()`이 매번 r1 hold만 반환한다. runner plumbing을 검증하지만 실제 Runtime의 actor 순서→poll→dispatch race가 없다. pair executor 단위 테스트나 old host의 cancel_scheduled 검사도 final adapter의 no-op cancellation과 지역 list를 함께 실행하지 않으면 이 경계를 놓친다. `command.t > abort.t`만 검사하면 같은 시각의 새 명령을 놓치므로 시간값뿐 아니라 dispatch/abort 순서도 검증해야 한다.

**최소 수용 기준:**

1. 실제 final Runtime의 같은 tick에서 뒤 actor가 실패한 뒤에는 affected pair의 앞서 생성된 non-hold command가 backend까지 도달하지 않고, 필요한 hold는 **다음 tick 전에** 발행되어야 한다. actor 순서와 실패 actor를 바꾼 대조군도 확인한다.
2. abort 판정·batch 취소·receipt 순서를 함께 검사하고, 이미 완료된 task에는 정상 hold만 허용한다. controller/vision/geometry의 gate를 완화하거나 grip monitor를 gate로 바꾸지 않는다. 실제 command-only port를 sink로 하는 작은 offline regression이면 이번 결함을 직접 판정할 수 있다.

### E2. 과거 staged HIGH loaded 이력 소실 — 최신 source에서 해소 인정

81db의 initial-only handoff에서 같은 최종 PWM인데 loaded=False/순서 이력은True였던 pure-method 재현은 당시 증거로 보존합니다. 현재 결함으로 반복하지 않습니다.

`73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`의 [own_history132–157](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_staging.py#L132-L157)와 [initial_commands318–333](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/harness/zone_pair_highpose_staging.py#L318-L333)는 pre-close 자세→close→raise를 자기 명령으로 순서대로 넘깁니다. 따라서 과거 ‘최종 PWM만 전달해 loaded=False가 된다’는 지적은 현재 잔존 결함으로 게시하지 않습니다. [새 test555–583](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/tests/test_highpose_dev_pilot.py#L555-L583)는 fixed delay 뒤 loaded=True/최종 PWM과 구 single-row 반례를 비교합니다. 소스만 읽었고 새 test를 실행하지 않았습니다. 모든 이력 row를 같은 `now`에 넣으므로 원래 prefix와 motion/camera/HIGH settle epoch까지 완전히 동등하다고 새로 검증한 것은 아닙니다.

최신 공개 HIGH staged가 여전히 gate 입장 전 멈춘다는 사실은 위 코드 개선과 양립하며, loaded 복원만으로 운반 성공을 보장하지 않습니다.

### E3. sub-grid lease expiry에서 PF prediction이 호출 분할에 의존합니다 — P2, 해당 duration/partition

[owncam_localizer.py:270–299](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/owncam_localizer.py#L270-L299)는 `dt=min(STEP_S,t-self.t)`로 구간을 정하고 시작 clock의 명령을 선택하지만 `cmd_expires`에서 구간을 자르지 않습니다. [raw port 44–49](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/camera_robot_port.py#L44-L49)는 0–1초 범위의 임의 duration을 허용하며 [물리 tick 198–208](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/camera_robot_port.py#L198-L208)에서는 만료를 검사합니다.

원본 `predict_to` 메서드의 순수 상태 전이 반례(identity gain, tau=.12, forward=.1, expiry=.02, 초기 velocity=0): `predict_to(.05)`의 velocity는 **.03407593698 m/s**, `.02`에서 나누어 `.05`까지 예측하면 **.01195601529 m/s**이며 후자가 구간별 해석해와 일치했습니다. 같은 명령 이력과 최종 시각인데 prediction 호출 분할이 결과를 바꿉니다. 합성 메서드 확인이며 물리 실행이 아닙니다.

**P2, sub-grid expiry 또는 다른 prediction partition에 한정합니다.** 현재 .05초 격자에 맞는 모든 lease가 틀렸다는 뜻이나 현재 E2E 실패의 원인을 입증한 것은 아닙니다. 닫는 기준은 expiry 경계마다 구간을 나누고 동일 command stream/최종 clock에서 velocity와 pose의 허용 오차를 확인하는 것입니다.

### E4. PR #371 v100의 prompt 잔존과 비용·입력·행동 개선

검토 동결 head는 `1883c56a749dc89597d57f570d4a2243cbb9595d`(v100)입니다. 기존 e0ad→a148 검토에 이어 a148 이후2commit/12file 중 관련 pair_llm/billing/status·문서·test 소스를 좁게 대조했습니다. 새 테스트·실제 모델·물리·smoke 원자료 실행/열람은 없습니다.

**유지: peer_nl system prompt의 `__CHARS__` 미치환 — P2.** [template113–117](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L113-L117) 및 [최종 문자열150–173](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L150-L173)에 literal→strip→join 기전이 남습니다. e0ad에서 실제 system_prompt 호출은 no_comm r1/r2에는 없고 peer_nl r1/r2에는 남았고, a148와1883에서는 해당 생성 기전의 source 동등성을 확인했습니다. 최신 prompt 함수를 새로 실행한 것은 아닙니다. parser 상한 우회가 아니라 지시 명세의 모호함입니다. 최종 request에서 선택한 cap을 숫자로 치환하고 2로봇×2조건을 검사하면 됩니다. 240자를 새 정책으로 확정하라는 요구는 아닙니다.

**개선 인정: 전체 live 비용 소실 주장은 철회 상태를 유지합니다.** [case296–303](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L296-L303)의 `metrics.model_usage`와 [live_records185–198](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_live.py#L185-L198)는 SendLedger 전체 POST의 known/unknown·failure 요약을 유지합니다. 아래는 e0ad의 실제 원장/transport/scheduler와 합성 wire 재현이며 a148와1883은 집계 코드 유지로 연결한 것입니다.

| e0ad 합성 입력2호출 | 구 provider_usage.total_tokens | model_usage | 판정 |
|---|---:|---|---|
| known reject200 + success100 |100|known300, complete=true, unknown0|실패 비용 보존|
| timeout unknown + success100|100|known100, complete=false, unknown1|미상을0으로 확정하지 않음|

구 evaluator alias가 request archive 부분합인 것과 canonical live completeness를 구분합니다. 실제 reader의 구 alias 오용을 새로 입증하지 않았으므로 광범위 비용 결함을 재등록하지 않습니다. 후속은 필드 이름/의미와 reader의 completeness 사용을 확인하는 좁은 정합성입니다.

**새 이미지 청구 연결도 인정합니다.** [billing65–80](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L65-L80)은 `1490×images`를 text bill에 더하고 [inputs362–364](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_inputs.py#L362-L364)→[dispatch356–377](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L356-L377)가 정상/파서 거절 Attempt에 total_billed를 넣습니다. 호출 row는 text/image/input_tokens_charged를 분리합니다. 두 이미지면2980의 추가 항입니다. 1490은 provider가 보고한 순수 이미지 토큰 수가 아니라 문서상 request-shape 잔차 보정 상수입니다. 보정 타당성·새 실패경로 전체를 실험 검증한 것은 아니지만, 이미지 비용 미연결이라는 옛 지적은 최신에 적용하지 않습니다.

**own_status와 idle-only 재관측은 실제 새 계약입니다.** [status40–110](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L40-L110)는 자기 claim/제출·거절 누계와 자기 job 상태/종료에서 `last_outcome/reason/since_claim_s/refusals_since_last_call`을 만듭니다. 좌표·측정 관절·접촉·성공 판정 입력이 아닙니다. 닫힌 reason/sanitization은 인정하되 timing/count를 포함한 완전한 정보 비간섭까지 증명했다고 하지 않습니다. [look dispatch196–199](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L196-L199)→[기존 executor start263–271](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/zone_own_executor.py#L263-L271)은 stopped/busy일 때 거절하며 busy pair를 끊고 look을 강제하지 않습니다. loaded 자체의 별도 금지는 아니고 기존 loaded sweep guard를 따릅니다. 실제 loaded 안전·위치 회복·운반 효과는 미검증입니다. 최신 [status 설명23–33](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L23-L33)은 partner 때문에 생긴 자기 결과·시간 신호가 양조건에 공통으로 남음을 명시합니다. builder의 의미가 새로 바뀐 것은 아니며 닫힌 reason을 완전 정보 차단으로 해석하지 않습니다. [prompt76–87](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L76-L87)도 재관측의 회복효과를 보장하지 않도록 문구를 좁혔습니다.

1883의 [billing83–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_billing.py#L83-L119)는 과거 저장행의 v1/v2 정책을 구분해 검증하고, [case130–133](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L130-L133)는 현재 writer에 v2를 요구합니다. [event delivery시각321–328](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L321-L328)과 [dispatch시각449–458](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L449-L458) 추가는 시각 의미를 명시하며 scheduler 자체를 바꾼 것은 아닙니다. 기록 필드 명시가 model-facing 비교의 시계 정규화까지 보증하지는 않습니다. 과거 실제 archive·새 tests를 독립 실행한 확인은 아닙니다.

새 reply_format은 fence/unwrap 진단 지표입니다. 기존 whole-reply fence 해제와 unwrappable 호출 거절을 구분하며 fenced reply 하나를 run 전체 실패로 단정하지 않습니다. 기본 H300/live smoke≤60·research_result=false·PROVISIONAL judge·v88 skill/physical_ready=False와 #363 rebase 대기는 유지됩니다. own_status와 별도로 #363 staged provider의 loaded 이력 복원은 E2처럼 개선을 인정합니다. 본실험 P06 연결도 별도 승격 계약입니다.

### E4a. own_status가 absolute/relative SIM 시각을 섞어 과거 사건을 최신으로 선택합니다 — P2, #371 두 LLM 조건

고정 `1883c56a749dc89597d57f570d4a2243cbb9595d`에서 새 clock 기록 필드의 추가와 별개로 model-facing 사건 선택에 시각 혼용이 남습니다. **no_comm·peer_nl 공통 LLM 입력 경로이며 rule arm에는 해당하지 않습니다.** 실제 운반 실패나 LLM 행동 변화는 측정하지 않았습니다.

- [case200–213,225–245](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L200-L245)는 reset 뒤 `origin_s=backend.now`를 두고 own event에는 relative elapsed를 전달합니다. [PairLink138–171,183–195](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L138-L195)는 claim에 absolute `_abs_now`를 쓰고 `gate_view()`를 정규화하지 않습니다.
- [ClaimGate64–119](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_runtime.py#L64-L119)는 permit/거절 timestamp를 그대로 보관합니다. [snapshot305–328](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L305-L328)의 `last_end.sim_s`는 reset-relative event 전달(delivery) 시각인 반면 gate view는 absolute입니다.
- [status89–105](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py#L89-L105)는 둘을 한 facts 목록에서 `max(time, rank)`로 비교합니다. [inputs335–354](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L335-L354)로 이어져 모델 입력에 들어가므로 로그 이름만의 문제는 아닙니다.

실제 함수/클래스의 원문 AST와 fake own-link·event·SIM clock으로 동일한 상대 history를 대조했습니다. look job 중 relative10.0에 claim permit을 받고10.5에 look 종료가 전달된 **idle snapshot**입니다. running job일 때의 우선 분기는 이 반례가 아닙니다.

| reset origin | 저장된 permit 시각 | 저장된 look end | 현재 last_outcome | 한 시간축 대조군 |
|---:|---:|---:|---|---|
| 0 | 10.0 | 10.5 | look_around_ended | look_around_ended |
| 1.3 | 11.3 | 10.5 | **claim_released** | look_around_ended |

일반적으로 `0 < end_relative − gate_relative < origin`이면 실제로 나중인 end보다 오래된 gate가 선택됩니다. 두 결과 모두 status schema는 통과합니다. 독립 검토자가 실제 caller 시간축과 비교 조건을 확인했습니다. nonzero origin은 [backend.reset57–62](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/final_environment_checks.py#L57-L62)와 [Scene.setup227–228](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/session_scenes.py#L227-L228)이 초기화에 SIM 시간을 쓰는 경로에서 가능하지만, 표의1.3/10.0/10.5는 합성 timing이며 실제 native 발생 빈도를 측정한 것이 아닙니다.

look 중 permit은 현재 API에서 허용되고 runtime은 own job이 끝난 뒤 pair 시작을 시도합니다. case loop가 종료 event와 trial.step을 먼저 전달하므로 새 submission 이전에 이 snapshot을 읽는 경로가 있습니다. 실제 초기 look 지속시간·모델 응답 시점의 모든 조합을 검증한 것은 아닙니다.

**수용 기준:** model-facing 비교 전에 gate와 job-end를 동일 시간축으로 정규화하고, origin0/nonzero에서 같은 상대 history의 last_outcome/reason이 같아야 합니다. absolute 원본 로그를 지우거나 사건 분류 정책을 바꿀 필요는 없습니다. 구현은 수정하지 않았으며 새 모델·물리·raw 열람 없이 확인한 계약 반례입니다.

별도 음성 대조도 보존합니다. 기존 executor는 busy/stopped look 재진입을 거절하고 job identity를 유지했습니다. shared scheduler+ReplayTransport의 합성에서는 cost release 전 action/message0, release 뒤 action·추가 delivery 지연 뒤 message, horizon censor 후 재개에도 방출0이었습니다. 이는 실제 loaded sweep 안전성·provider 원장 전체·물리 회복의 인증은 아닙니다.

## 기록·분석 산출물의 확정 결함

### E5. directory receipt의 내부 symlink target bytes가 빠집니다 — P2, 공통 workflow

[workflow_manager.py:56–71](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L56-L71)는 `p.is_file() and not p.is_symlink()`만 수집합니다. **디렉터리 내부** 모델/데이터 링크의 실제 대상 bytes를 바꾸어도 receipt에 반영되지 않습니다. 입력 루트 자체가 파일인 경우 resolve 후 해시하므로 그 경우까지 일반화하지 않습니다.

임시 디렉터리 `models/weights.bin -> 외부 weights.bin`에서 대상 내용을 `model-v1`에서 `model-v2`로 바꾸었을 때, 소비되는 bytes는 달라졌지만 두 receipt의 `files=[]`와 SHA가 동일했습니다. [종료 시 비교:519–527](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L519-L527)도 이를 검출하지 못할 수 있습니다. 특히 source fingerprint 밖의 입력일 때 재현성에 영향이 있습니다. 확인자는 서로 독립적으로 반례를 재현했습니다.

**닫는 기준:** directory 내부 link를 명시 거부하거나, 사용 경로→link binding→최종 target bytes를 고정합니다. directory link·깨진 link·cycle도 같은 계약으로 다룹니다. 특정 물리 PR의 성공 여부와는 별개의 공통 영수증 결함입니다.

### E6. console 저장 오류가 정상 recording completion으로 남습니다 — P2, 공통 launcher

위치: [`sim/workflow_manager.py:590–601`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L590-L601), [`:610–612`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L610-L612), [`:648–654`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/workflow_manager.py#L648-L654).

도달 경로: `sim_cli workflow run` → `run_workflow` → 자식 stdout/stderr PIPE → daemon `tee` → `console.log`. Python 스레드의 `log.write`/`flush` 예외를 owner thread로 전달하는 채널이 없다. `output_thread.join()`도 예외를 반환하지 않는다. 부모는 자식 exit code만 보고 `process_completed`로 정하고 `_finish`가 빈 파일의 정상 해시를 기록한다.

오프라인 재현: 기존 `WorkflowManagerTests`의 임시 root/fixture subprocess를 그대로 사용하고, 부모의 `console.log` 쓰기만 `OSError(ENOSPC)`로 주입했다. fixture는 문자열 출력과 작은 JSON 파일 기록만 하며 physics/model을 import하거나 실행하지 않는다.

```json
{
  "thread_errors": [{"type": "OSError", "errno": 28}],
  "status": "process_completed",
  "exit_code": 0,
  "failure": null,
  "finalization_errors": [],
  "console_bytes": 0,
  "child_result_exists": true
}
```



영향: 공통 실행 기록의 console 완결성을 잃었는데 그 사실이 manifest에 없다. 물리 성공을 조작했다고 주장하는 발견은 아니다. child가 계속 많은 출력을 쓰면 dead tee로 인해 pipe가 채워져 추가로 멎을 수 있다는 정적 경로도 있지만, 이번 실행은 그 hang을 따로 재현하지 않았다. 실제 전체 디스크 full이면 다른 저장도 실패할 수 있으므로, 반례는 console-specific 또는 일시적 저장 실패가 최종 manifest 작성보다 먼저 발생하는 조건이다.

최소 수용 기준:

- tee의 read/write/flush 실패를 owner에 전달하고, console 보존 실패를 명시적 기록/infra failure로 표시한다.
- 이미 존재하는 자식 결과·부분 console을 보존하며, 원래 child exit와 logging failure를 둘 다 남긴다.
- 실패 이후 stdout을 계속 drain하거나 소유한 process group을 유한 시간 내 종료하여 pipe 대기를 만들지 않는다.
- 같은 ENOSPC 반례에서 정상적인 recording completion을 보고하지 않는다. 다른 실행/프로세스는 건드리지 않는다.

독립 검증: `control_review`가 재현 파일을 따로 실행해 동일한 여섯 결과 필드와 errno28을 확인했다.

### E7. 표준 TensorBoard exporter가 외부 원본의 최종 변경을 놓칩니다 — P2, 선언형 offline view

**경로와 조건.** `scripts/export_tensorboard.py`가 호출하는 표준 변환기는 [offline_scalars:276–314](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/tensorboard_tools/export.py#L276-L314)에서 선언된 외부 원본 파일의 SHA를 처음 확인한다. 그러나 이 파일은 `Source.read`로 등록하지 않고 `metadata.offline_scalars.original`에만 넣는다. [게시 직전:1080–1102](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/tensorboard_tools/export.py#L1080-L1102)의 일반 루프는 `src.files`만 재해시한다. 별도 coverage 파일 재검사는 있으나 `offline_scalars.original`에 대한 검사는 없다.

**합성 반례.** 외부 원본 `{"accuracy":0.75}`에 맞는 해시와 파생 뷰를 제공한다. 첫 검증을 지난 뒤 sink.close 단계에서 외부 원본만 `{"accuracy":0.25}`로 바꾼다. 표준 `convert`는 다음을 반환한다.

```json
{"complete":true,"source_changed":true,"published_marker":true,"error":null}
```

동일 실험을 [별도 `offline_audit.convert`:239–253](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/tensorboard_tools/offline_audit.py#L239-L253)에 적용하면 외부 원본을 재해시하여 `Original changed during export`로 거절하고 `complete:false`, 게시 파일 없음이 된다. 입력 숫자가 잘못됐다는 일반적인 신뢰 논쟁 없이 두 실제 게시 경로의 차이로 재현된다.

**영향.** 숫자가 자동으로 다른 수치로 바뀌는 문제가 아니라, 게시 당시 원본이 manifest의 해시와 불일치하는데도 완전한 스냅샷으로 표시되는 계보 문제다. [문서:105–111](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/docs/tensorboard.md#L105-L111)의 ‘변환 중 원본 변경 → 미게시/실패 manifest’ 약속에 반한다. 초기에 검증한 해시와 출력 수치는 여전히 같은 이전 bytes에 대응합니다. 문서가 약속한 변환 중 원본 변경 거절이 누락된 범위입니다. 실제 과거 자료 변경이나 잘못된 기존 결론은 관측하지 않았다. 완료된 원본을 불변으로 보관하면 이 실패 조건은 발생하지 않는다.

**테스트가 검증하는 범위.** [표준 오프라인 scalar 테스트:66–98](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/tests/test_tensorboard_offline_scalars.py#L66-L98)는 함수 호출 전의 잘못된 해시와 정적인 정상 변환을 검증한다. [도중 변경 테스트:193–212](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/tests/test_offline_audit_export.py#L193-L212)는 이미 존재하지만 별도 offline-audit 경로에만 적용된다. 전용 P06의 publication 검사 부재로 확대하지 않는다.

**수용 기준.** 표준 exporter도 등록된 외부 원본을 게시 직전에 다시 검증하고, 변경·삭제 시 실패 manifest 및 이벤트 미게시를 보장한다. 동일한 도중 변경 fixture를 두 exporter에 적용하면 둘 다 거절하고, 정상 입력은 그대로 통과해야 한다. 기존 완료 스냅샷의 자동 덮어쓰기는 필요 없다.

### E8. 단계 진입 분모 0을 0%로 표시합니다 — P2, 개발 stage-probe view

**경로.** 개발용 [pair_stage_probe.summarize:918–926](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/pair_stage_probe.py#L918-L926)는 `STAGING_IK_ENVELOPE` 원인을 별도 집계하고, `staged_cases=0`이면 `staged_pass_rate=None`을 기록한다. 현재 [뷰 생성기:183–199](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/build_pair_stage_probe_views.py#L183-L199)는 동일한 분모가 0일 때 `offline/staged_pass_rate=0.0`을 만든다. 이 태그는 HParams 핵심 지표에도 들어간다.

**합성 반례.** align/teacher_grid 시행 1개, `passed:false`, `cause:STAGING_IK_ENVELOPE`를 만든 뒤 실제 `summarize → summary.json → build_pair_stage_probe_views.main`을 실행한다.

```json
{"source_staged_pass_rate":null,"view_scalars":{"offline/cases":1,"offline/passed":0,"offline/pass_rate":0.0,"offline/staging_infeasible":1,"offline/staged_cases":0,"offline/staged_pass_rate":0.0}}
```

전체 계획 대비 성공률 `offline/pass_rate=0`은 맞다. 잘못된 값은 **진입한 단계 중 성공률**이라는 별도 지표다. 진입 자체가 없었던 정책과 실제 진입 후 전부 실패한 정책이 같은 0% 카드로 표시된다. 전체 `cases` 분모를 바꾸자는 지적이 아니며 단계탐침을 확증/독립 물리 표본으로 승격하지 않는다.

**테스트 경계.** [기존 summary 테스트:531–542](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/tests/test_pair_stage_probe.py#L531-L542)는 3개 중 staging 1개 제외 후 1/2를 확인한다. [뷰 테스트:644–662](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/tests/test_pair_stage_probe.py#L644-L662)는 개별 태그의 형식만 확인하며, 집계의 분모 0 전달을 검증하지 않는다.

**수용 기준.** `staged_cases=0`인 집계는 해당 비율 태그를 생략하고 Text/metadata에 미정의 이유를 남긴다(현재 exporter는 선언 scalar의 null을 거부하므로 단순 null 대입만으로는 부족). `cases=1`, `staging_infeasible=1`, `staged_cases=0`, 전체 pass rate 0은 유지한다. `staged_cases>0`이면 기존 비율을 그대로 계산한다.

### E9. provenance 미상을 단일 bundle 확인으로 출력합니다 — P2, permissive pilot report

**경로.** [zone_study_eval:1819–1828](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_study_eval.py#L1819-L1828)는 모든 시행에서 **존재하는** 필드의 값 집합만 만든다. 어느 시행에서 필드가 빠졌는지 세지 않는다. 각 집합에 서로 다른 값이 없고 전체 필드가 하나라도 있으면 `single_bundle=True`다. [보고서:240–249](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/zone_study_report.py#L240-L249)는 이를 그대로 단일 번들 여부로 번역한다.

**합성 반례.** 두 조건 시행 모두 `code_sha=same`을 갖지만 no_comm에만 `map_sha256=map-A`, `cost_profile_sha256=cost-A`가 있고 peer_ko에는 없다. 실제 parser/summary/markdown 결과는 다음과 같다.

```text
mixed_fields=[]; single_bundle=true
- 실행 번들 단일 여부: 예
```

실제로 다른 map/cost가 실행됐다는 증거는 없다. 지금 확인된 것은 **확인 불가가 확인됨으로 표현되는 것**이다. permissive pilot API에 완전한 확증 admission을 강요하는 지적이나 P06 연결 문제의 재탕이 아니다. 자유로운 pilot 입력을 유지하더라도 보고서의 확신 수준은 입력에 맞아야 한다.

**테스트 경계.** [test_mixed_provenance_is_flagged:635–642](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/tests/test_zone_study_eval.py#L635-L642)는 명시적으로 다른 code SHA를 가진 사례를 혼재로 표시한다. loader가 시행을 거절한다는 뜻은 아니며, 일치하는 일부 필드와 누락된 나머지 필드를 구분하는 사례가 아니다.

**수용 기준.** `mixed`, `complete-and-consistent`, `incomplete/unknown`을 구분하거나 보고 문구를 ‘기록된 값에서 충돌 발견 여부’로 정확히 좁힌다. 필요한 bundle 필드와 시행별 누락을 표시한다. 현재 loose loader를 막거나 unknown 시행을 성공률 분모에서 제거하는 방식으로 해결하지 않는다.

E7–E9는 원본 검증/summary/markdown 함수를 이용한 합성 반례이며 독립 재검증했습니다. E7은 protobuf sink만 게시 확인용 파일로 대체했고 TensorBoard UI를 돌리지 않았습니다. 최초 값 0.75와 최초 hash는 일치했으며, 확인한 것은 변환 중 원본 변경의 최종 거부 누락입니다. 수치 조작·과거 실제 데이터 오염을 발견한 것이 아닙니다.

### E10. 최신 상태 문서의 연결 절이 없습니다 — P3, 현황 탐색

[docs/current_status.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/docs/current_status.md#L1-L7)는 7줄입니다. 마지막 문장은 아래에 9/30·9/29 절을 보존한다고 하지만 해당 절이 없고, [research_todo의 9/29 anchor](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/docs/research_todo.md#L1-L5)와 README의 9/30 요약 안내도 이를 기대합니다.

역사 기록을 일괄 덮어쓸 필요는 없습니다. current entrypoint에 `후보/고정 SHA/보정·provider/지원·차단 상태/다음 인수/관련 최신 결정` 표를 두면 됩니다. 날짜가 명시된 과거 inventory/TODO 자체를 오류로 세지는 않습니다. v2 구성 지원, static inspector의 runnable, SIM 측정 보정, 실물 twin validated, 실제 학생 운반 성공은 서로 다른 상태입니다.

## 통과한 경계와 테스트 해석

- 기존 P06은 frozen plan, 시행 identity, referee replay, 고정 분모와 publication 재도출을 이미 제공합니다. E7의 일반 exporter나 E9의 loose pilot 표시 문제를 P06 전체 결함으로 확대하지 않습니다. 현재 SendLedger의 unknown usage와 유료 요청 후 자동 재시도 금지도 기존 방어입니다. E4는 그 데이터를 새 consumer가 요약하는 연결을 봅니다.
- fake 테스트는 계약을 검사하는 데 유효합니다. 다만 v99 ReadyRuntime/스크립트 beam trajectory의 통과는 영상 위치추정→실제 운반 성공의 증거가 아닙니다. test 함수 정의 수·직접 import·CI 선택 수를 실행 횟수, branch coverage 또는 물리 시행 수로 표현하지 않았습니다. branch protection 전체도 확인하지 못했습니다.
- E1의 fake full-protocol runner는 실제 actor 순서→poll→dispatch 경계를 함께 실행하지 않습니다. 반면 별도 일반 RGB detached-worker 결함은 **기존 portable process 테스트가 이미 검출**합니다. 두 상황을 구별합니다.
- `measured=0`은 informative absolute-fix receipt 0이며 likelihood weighting/resampling 0이 아닙니다. relative beam-yaw가 common yaw spread를 줄이지 않는 것은 인정된 관측 한계입니다. camera optical 변환·nominal yaw 이중 적용 의심은 반박됐습니다.

**종료 기준:** E1은 선택한 DEV 실행 경계를 닫고, E2의 loaded 복원은 인정하되 완전 시간동등성은 미검증으로 구분합니다. E3는 실제 duration이 해당할 때 조치합니다. E4의 prompt 미치환과 E4a의 model-facing 시각 혼용은 실제 비교 전 닫고, 새 live 비용 completeness를 사용합니다. E5–E9는 해당 기록/게시 경로를 결과 근거로 쓰기 전에 명시적인 완결성·미상 상태를 보존합니다. 모든 레거시 문제 해결을 현재 DEV의 선행조건으로 두지 않습니다.
