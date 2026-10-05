# R23 — 현재 pair case의 마지막 관측·사건·집계 경계

**새 버그 0건.** 공식 GitHub를 2026-10-04 09:43:57 UTC에 다시 읽었고 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`가 앞선 기준과 같았다. 직접 main branch를 읽었으며 PR metadata의 `base_sha`를 main head로 대신 쓰지 않았다. 이번에 변경된 구현을 발견하거나 기존 finding의 수정을 확인한 것은 아니다. 공개 metadata는 `current-frontier.json` (Mac 전달본 증거)에 고정했다.

기존 coverage와 겹치는 요청 이미지 byte binding(R11), 요청/응답 admission(R9), scheduler 단독 release/censor(R7), finalization 실패 분류(R8), endpoint done 처리(R17)는 재검증 과제로 세지 않았다. 추가한 부분은 **#371의 실제 case caller가 마지막 관측 tick에 이미 생성된 own executor 사건을 소비한 뒤 마무리하는가**다. 현재 #363 HIGH 구현이나 등록된 본 연구의 인수 검사로 범위를 넓히지 않는다.

## 실제 caller 순서

현재 [run_pair_case의 반복문](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_case.py#L223-L270)은 `steps + 1`번 관측한다. 마지막 `i == steps`에서도 `capture → runtime.on_frames → PairLink.observe/tick → drain_events → trial.on_executor_event → trial.step_to → health`가 먼저 실행된다. 그 뒤 break하므로 마지막 시각에는 `runtime.step/arm_step/advance_to`를 한 번 더 수행하지 않는다. 정상 protocol 완료 처리와 `trial.finish(cap_s)`는 그 뒤다.

사건 writer는 [ZoneOwnExecutor._emit/drain_events](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_own_executor.py#L182-L196), shared consumer는 [IntegratedTrial.on_executor_event](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_integration.py#L443-L460)다. `job_id`로 연결된 기존 own-command 항목만 `queue_empty/local_timeout`으로 바꾼다. Pair consumer는 [사건 자체 시각에서 origin을 뺀 종료 시각과 별도 수신 시각](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L339-L354)을 보존한다.

## 저작된 8개 대조

`final-tick-repro.py` (Mac 전달본 증거)는 명시한 Python 소스 7개를 정확 Git object에서 읽고 선택한 AST 몸체를 수정 없이 실행한다. 실제 `run_pair_case`, `PairLink`, `_emit/drain_events`, shared/pair 사건 consumer와 metric writer를 연결했다. Backend·job 발생 일정·시계·adapter·scheduler·trial의 begin/step/finish는 저작한 대역이다. Scheduler와 finish 대역은 호출 순서와 관측된 상태를 기록할 뿐 실제 scheduling/settlement를 실행하지 않는다. 원본 test suite나 전체 source 모듈 import는 실행하지 않았다.

cap 0.20초, 마지막 control tick 0.15초에서 생성한 사건을 다음 0.20초 관측에서 소비하는 경우를 reset origin 0과 1.3에 각각 적용했다.

| 합성 일정 | 마지막 `trial.step_to(0.20)`와 finish에서의 기존 r1 command | Pair의 최신 종료 시각 |
|---|---|---|
| 연결된 job의 done | `queue_empty` | 0.15 |
| 연결된 job의 `LOCAL_TIMEOUT` failure | `local_timeout` | 0.15 |
| 다른 job ID의 done | `command_issued` 유지 | 그 다른 own job의 종료 0.15 |
| 사건 없음 | `command_issued` 유지 | 없음 |

다른 job 대조는 emitter 실행 전에 저작한 job ID를 바꾼다. 원래 writer가 만든 사건 행을 사후 변조하지 않는다. 이 대조는 전체 executor job lifecycle이 아니라 소비자의 job-ID 연결 한계를 확인한다. 모든 경우 control/arm tick은 0, 0.05, 0.10, 0.15까지만 있고 0.20에서는 추가 명령 step이 없다. done/timeout은 마지막 own frame 시각 0.20과 사건 수신 시각 0.20을 보존하며, 사건 자체 종료 0.15와 구별한다. 소비된 outbox는 비어 있다. 결과는 `final-tick-result.json` (Mac 전달본 증거)에 있다.

실제 `_evaluate → trial_metrics`는 trajectory가 없는 이 fixture에서 `NO_TRAJECTORY`, success false를 쓴다. 따라서 `COLLECTED_UNQUALIFIED`라는 protocol 완료 label이나 own `queue_empty`를 물리 success로 올리는 경로는 이 대조에 없다. 이것은 실제 provisional judge의 정확도·실물 상태를 검증한 결과가 아니다.

## 늦은 메시지가 집계되는 창과 분모: source-only 확인

Case 반복문에는 `job_done`이나 `trial.quiescent()`를 읽고 전체 실행을 조기 종료하는 분기가 없다. 따라서 own job이 끝나더라도 등록된 case horizon 안의 후속 대화는 같은 실행의 관측/집계 창에 남는다. 이를 곧바로 작업 이후 메시지 오염이나 terminal의 물리 재활성화라고 판정하지 않는다. 이번 fixture는 실제 후속 call이나 motion을 발생시키지 않았다.

| 현재 writer→consumer | 실제 집계 의미 |
|---|---|
| `PairTrial.finish_call → Transport.send` | Validator를 통과한 발화를 미래 SIM release 시각으로 접수하고 budget을 예약한다. 아직 상대 inbox에 전달됐다는 뜻은 아니다 |
| `Transport.sent_count → OfflineTrial.channel_summary.sent → trial_metrics.messages.sent` | 접수된 발화 수에 channel rejection 수를 더한 수. call이 이미 완전히 끝났거나 상대가 수신한 수와 같다고 가정하면 안 된다 |
| `EventScheduler.messages → OfflineTrial._collect → channel_summary.accepted_messages → trial_metrics.messages.accepted` | `_collect`가 실제 scheduler delivery edges를 모아 만든 message rows 수. 이 필드의 `accepted`는 위 relay receipt의 accepted와 분모가 다르다 |
| `PairTrial.language_rows[accepted] → trial_metrics.language` | relay가 접수한 발화의 언어 기록. 메시지 전달 효과의 분모가 아니고 명시적으로 `gate=false`다 |

근거: [pair relay와 language writer](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_dispatch.py#L396-L428), [접수/pending와 전달 권한 분리](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_protocol.py#L427-L480), [sent_count](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_protocol.py#L609-L611), [delivered message collection와 summary](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/zone_study_offline.py#L577-L615), [최종 metrics](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_eval.py#L91-L139).

R9의 실제 relay/scheduler 합성 검토가 접수와 release의 구분을 이미 보였으므로 동일 overlap/censor fixture를 다시 실행하지 않았다. 위 표는 그 사실을 현재 metric consumer의 정의와 연결한 **source-only 해석**이다. 새 horizon 실험, 실제 로그의 개수 차이, 효과량 편향, 등록 분석의 오용을 발견했다는 주장이 아니다. 향후 통신량을 해석할 때 `sent/accepted/language`를 같은 분모로 합치지 않고 접수·전달·모델 입력에 포함됨을 구분하는 데 쓰면 된다.

## 재현과 남은 한계

```sh
python final-tick-repro.py --repo /absolute/path/to/UGRP-Multi-Robot-Collaboration-Project --output /tmp/final-tick.json
```

Python 표준 라이브러리와 해당 commit을 가진 Git object만 필요하다. 네트워크 socket과 simulator/model 모듈을 차단하며 실제 영상·원자료·held-out 결과·weights·live model·렌더링·물리·학습·CI를 실행하지 않는다. Frame 내용은 decoding하지 않는 저작한 byte placeholder다.

이 작은 대조는 final caller 순서와 기존 own-event의 소비를 확인한다. Scheduler transaction, paid-send 취소/settlement, 실제 `trial.finish`의 부작용, shutdown 때 새로 생성될 수 있는 event, health exception으로 중간에 끊기는 모든 분기, deadline 부근 물리 event 발생 빈도는 검증하지 않았다. R7 scheduler censor와 R8 finalization failure finding을 해결했다고 선언하지 않는다. 현재 active #363 camera/attachment와 #371 비용/분류 finding의 상태도 이 음성 결과로 바뀌지 않는다.
