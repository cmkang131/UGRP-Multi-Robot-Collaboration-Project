# R15 — 절차 완료, 관측에 의한 확인, 평가 성공의 증거 계약

2026-10-04. **새 결함을 주장하는 문서가 아니라 현재 종료 의미와 다음 검증의 범위를 고정하는 설계 검토다.** #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`와 별도 #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`의 source/test만 읽었다. 실제 RGB·trajectory·접촉·GT·heldout 결과는 열지 않았고, 새 실행도 하지 않았다. 공개 stage 진전은 E2E 성공으로 승격하지 않는다.

**최신성 확인:** 작성 중 #363이 `66ff0978a817caa949d2d738b51d7ae89dd17e71`로 바뀌어 이 문서의 6개 #363 근거 파일을 비교했다. 5개는 동일하며 `run_pair_highpose.stage_progress`에 `look_recovery.failures()`를 합치는 변경이 있다. 새 값은 own admission/refusal·bounded re-look 상태에서 나온 `LOOK_RECOVERY_EXHAUSTED`다([새 runner:67–91](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/scripts/run_pair_highpose.py#L67-L91), [recovery:126–182](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_relook.py#L126-L182)). 따라서 최신 probe의 stop 원인에는 recovery exhaustion도 포함한다. `physical_success=None`, done→unconfirmed, 별도 평가의 의미는 그대로다. 새 PF·pan·final veto 성능을 이 좁은 비교로 검증한 것은 아니다. 하단 exact 링크는 처음 읽은 de03을 보존한다.

**공개 결과의 시점도 갱신한다:** 66ff의 [README:31–59](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/experiments/2026-10-03-pair-carry-highpose/README.md#L31-L59)는 `af2f7c2a`에서 실행한 새 DEV stage 세 개가 `PAIR_COLLISION_GUARD` 또는 `ALIGN_RELOOK_NO_FIX`로 끝나 운반에 도달하지 못했다고 보고한다. 작성자는 inspect 전환 중 fix-gap relook hold가 중간 팔 명령을 남겨 미측정 카메라 자세로 닫혔다고 진단한다. 이는 공개 보고만 읽은 상태이며 raw 독립 검증이 아니다. R12 command 취소/모델 identity 증인과 관련은 있으나 동일 인과라고 확정하지 않는다. 앞선 de03의 HIGH/운반 시작 진전을 최신 head의 성공으로 쓰지 않는다.

**우선 확인할 것은 `done`을 더 강한 성공 이름으로 바꾸는 일이 아니라, 절차가 실제로 어디까지 종료했고 어떤 평가 predicate가 별도로 확인됐는지를 한 실행 안에서 연결하는 것이다.** 현재 executor는 양쪽 `done` 메시지를 받은 뒤에도 `unconfirmed / PAIR_SEQUENCE_DONE`으로 종료하고, HIGH runner는 `physical_success=None`을 유지한다. 이 정직한 구분을 보존해야 한다. 외부 평가가 성공을 확인하더라도 그 결과를 현재 정책의 입력·중간 단계 승인·성공 통보로 돌려줄 필요는 없다.

## 1. 현재 source가 보장하는 네 가지, 보장하지 않는 네 가지

| 근거와 exact source | 현재 의미 | 이 사실만으로는 성립하지 않는 주장 |
|---|---|---|
| [#363 executor:386–395](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/harness/zone_pair_executor.py#L386-L395) | 자기 controller가 `done`이고 채널의 양쪽 최신 상태가 `done`이면 job을 `unconfirmed`로 끝낸다. holding은 `unknown`, zone은 unconfirmed다. | 실제 release·정착·목적 구역 도착을 두 카메라가 독립 확인했다. 상대 controller를 직접 검사했다. |
| [#363 stage_progress:67–87](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/scripts/run_pair_highpose.py#L67-L87), [runner:243–256](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/scripts/run_pair_highpose.py#L243-L256) | Stage probe는 등록된 양쪽 terminal event, controller failure, non-look job 종료 또는 cap으로 끝난다. `REACHED`는 정해진 event가 두 로봇에서 관측된 뜻이다. full case는 bounded protocol을 수집한다. | Stage `REACHED`가 full carry 성공이다. controller failure가 없다는 것만으로 끝까지 실행됐다. |
| [#363 checkpoint_record:28–45](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/scripts/run_pair_highpose.py#L28-L45), [result:207–211](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/scripts/run_pair_highpose.py#L207-L211) | Checkpoint는 stop/reobserved와 carried prefix event를 검사하고 `SEQUENCE_OBSERVED_UNQUALIFIED`, physical success unknown, confirmation sample false를 남긴다. | 이름이 같은 receipt/event 하나면 모든 이동 구간의 실제 authorization·물리 통과까지 인증된다. |
| [#371 case._evaluate:333–353](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_case.py#L333-L353), [judge:7–18,26–29](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_eval.py#L7-L29) | 별도 LLM 경로는 loop와 owner close 이후 잠정 beam-geometry evaluator를 호출하며 `judge_status`를 보존한다. | 이 잠정 판정이 #363 최종 심판이다. #371의 success 비율을 #363 stage 기록과 합산할 수 있다. |

마지막 행의 잠정 기준 한계는 [초기 연구설계 검토의 R7 항목](../publication/final-research-issue.md)와 [R11 재확인](../round11/validation.md)에 이미 있다. 이번에는 release·stability·footprint 누락을 새 지적으로 다시 세지 않는다. 최종 lower/open/retreat의 실제 command timing 및 endpoint 완료 증인은 frontier의 별도 R15 제어 검토가 담당한다. 해당 경로의 성공 주장을 여기서 대신 확정하지 않는다.

## 2. 현재 허용 입력으로 확인할 수 있는 것

다음 기호는 새 구현 필드나 실제 측정 결과가 아니라 보고 의미를 분리하는 표기다. `C`는 절차 완료, `K`는 허용 입력으로 만든 명시적 확인 주장, `Y_v`는 **미리 정한 버전 v의 task predicate**에 따른 별도 평가다. 현재 HIGH 경로는 C를 보고하지만 전 과제에 대한 K 또는 Y를 이미 제공한다고 주장하지 않는다.

| 확인하려는 사실 | 현재 허용 증거에서 할 수 있는 말 | 아직 필요한 구분 |
|---|---|---|
| 집게 열기/후퇴 명령 발행 | 자기 발행 명령, 해당 command layer의 완료/취소, controller event를 연결할 수 있다. | 발행 target·저수준 issued setpoint·물리 운동은 서로 다르다. 명령 완료가 실제 파지 해제의 측정은 아니다. R12 command provenance 경계를 그대로 적용한다. |
| 상대 절차 종료 | 실제 수신한 고정 `done` ENUM의 sender·시간·현재 job 문맥으로 상대가 완료 상태를 보냈음을 확인한다. | 메시지 수신은 상대의 물리 접촉/놓기 상태를 직접 측정하지 않는다. 두 개의 `done`을 두 독립 성공 센서로 세지 않는다. |
| 자기 영상에서 물체/목표 관련 변화 | 유효한 frame ID·capture 시각·자기 command-conditioned camera model에 연결한 검출/추정을 사용할 수 있다. | 물체가 가려졌거나 view 밖이면 그 한 영상에 근거한 확인은 unknown일 수 있다. `NONE` 검출이 물리 실패 또는 영상 전체의 무정보성을 뜻하지 않는다. |
| 지정 구역에 안정적으로 놓였다는 전체 주장 | 온라인 확인을 별도로 주장하려면 어떤 RGB evidence와 시간 구간이 그 주장에 필요한지 먼저 정의해야 한다. | 현재 source에 없는 온라인 success detector를 있다고 간주하지 않는다. 새 GT·측정 관절·접촉 입력이나 VLM을 추가하는 제안이 아니다. |

**온라인 확신이 없다는 것과 실제 임무 실패는 다르다.** 반대로 충분히 확신했다는 텍스트나 done ENUM도 별도 물리 판정의 대체물이 아니다. 이 구분은 정책을 불필요하게 확장하기보다 현재 camera-only 실행의 평가 가능성을 지켜준다.

BEHAVIOR의 원문 §4–6은 달성할 상태의 선언적 조건과 행동 계획을 분리하고, 시뮬레이터의 predicate 평가와 로봇 센서/행동 인터페이스를 각각 정의한다. 여기서 취할 설계 원칙은 goal predicate를 명시하고 실행 명령과 독립적으로 검사하는 것이다. **그 논문의 §7 학습은 success score Q를 reward로 주고 RGB·depth·proprioception을 사용한다.** 따라서 이를 현재 UGRP의 GT feedback 금지와 동일한 연구 조건이라고 인용하지 않는다. [원문 및 읽은 범위](primary-sources.md)

## 3. 실행 기록을 구분하는 최소 판별표

아래 표는 **같은 source·bundle·task predicate·평가 시점에 필요한 기록이 회수된 한 실행**에 대한 후속 분석 설계다. 실제 결과 빈도는 계산하지 않았다. #363 stage probe와 #371 잠정 판정을 서로 짝지으라는 뜻이 아니다.

| 가설/확인 질문 | 필요한 최소 기록 | 가설을 지지하는 관측 형태 | 반박 또는 미판정 형태 |
|---|---|---|---|
| A. 절차는 끝났지만 선언한 물리 goal은 성립하지 않았다. | controller/endpoint 종료 event, 실제 done 메시지, 최종 command 이력, **평가 쪽에만** 둔 동일 실행의 predicate별 판정·유효성 | C=완료, Y_v=실패이고 어떤 predicate가 불충족인지 명시됨 | C 미완료면 ‘완료 후 실패’ 설명은 기각. 평가 누락·host-invalid·아직 없는 judge이면 물리 실패로 채우지 말고 미판정 |
| B. 물리 goal은 성립했지만 절차/온라인 확인이 아직 종료하지 못했다. | 위 기록 + timeout/guard/peer-wait의 정확한 종료 분기 | Y_v=성공, C=미완료. 그 시점의 K가 unknown이면 실제 성립과 온라인 확인의 간극을 보여줌 | C도 완료면 이 설명은 해당 실행에 불필요. Y가 provisional이면 결론도 그 좁은 predicate에만 제한 |
| C. 실제 완료를 온라인으로 확인하는 데 terminal view가 부족했다. | 허용 입력만으로 구성한 terminal RGB window, frame/camera-command provenance, 검출 validity, 어떤 확인 주장이 있었는지 | 해당 주장에 필요한 영역이 계속 가려짐/미검출이라 K=unknown. Y는 별도이며 성공/실패 어느 쪽도 가능 | 적절한 영역이 보였다는 것만으로 K가 충분한 것은 아님. 유효한 확인 규칙을 미리 정하고 그 규칙의 반례를 찾지 못했을 때만 강화 가능 |
| D. 단순 referee label이 제어 선택으로 되돌아왔다. | 아래 §4의 고정 허용-history 합성 대조 | 평가 label만 바꿨는데 요청·command·정상 종료 시점이 달라짐 | 대조에서 같은 것은 그 fixture/dataflow에 대한 반박. 모든 OS 오류·wall timing·다른 caller까지 포괄하는 증명은 아님 |

C와 Y가 다를 때 바로 `false positive/false negative`라고 부르지 않는다. 현재 C는 물리 성공 classifier라는 계약이 없기 때문이다. 우선 **절차/과제 판정의 불일치**라고 기록한다. 나중에 명시적인 online detector K를 평가한다면 그때 해당 goal version, coverage/abstention, false confirmation과 missed confirmation을 정의한다. 이 경우에도 표본 수 없는 정확도·성공률·안전 확률은 제시하지 않는다.

## 4. 평가 경계의 최소 검증: 값 비간섭과 protocol abort를 구분

소스에서 #371 `_evaluate`는 loop와 owner close 뒤 호출되고([case:286–309](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/harness/pair_llm_case.py#L286-L309)), 그 뒤 이 함수에서 새 actor 제어가 실행되지 않는다. #363 `capture`는 RGB/obs를 반환하며 실제 camera/body label은 별도 파일로 기록한다([backend:161–198](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/sim/final_pair_v3.py#L161-L198)). 이 좁은 경로는 task verdict를 prompt·permit·wake-up·stage progress로 되돌리지 않는 구조를 지지한다.

다만 **‘모든 GT 값이 어떤 stop에도 영향이 없다’는 더 강한 주장은 틀린 범위**다. 같은 backend의 `super().eval_sample()`은 active weld를 발견하면 `WELD_OFF_VIOLATION`을 내며, `collection_guard`는 calibration-*에 한해 GT geometry로 abort한다([base:136–145](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/sim/final_environment_checks.py#L136-L145), [collection guard:86–95](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/sim/final_pair_v3.py#L86-L95)). 이는 task 성공 여부를 알려주는 정상 정책 feedback과 다른, 명시된 protocol/collection 유효성 경계다. 파일 쓰기 오류도 host 종료를 만들 수 있다. 이 예외를 숨겨 비간섭을 주장하거나, 반대로 이를 임무 성공 oracle이 연결됐다는 증거로 쓰지 않는다.

기존 [test_success_comes_only_from_the_separate_evaluator](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/tests/test_pair_llm_case.py#L326-L340)는 scripted beam에 따라 잠정 verdict가 달라지고 요청 텍스트에 지정한 금칙 문자열이 없음을 검사한다. [FakeBackend](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/a009112ff5fb18c6b64f58d8cd6392c58d4c028c/tests/pair_llm_fakes.py#L23-L85)는 beam script와 RGB 생성을 분리한다. **이 기존 test는 양 대조의 command·요청·stop 전체 동일성을 assert하지 않는다.** 기존 테스트를 실패라고 부르는 것이 아니라 다음 좁은 주장에 필요한 검사를 구체화한다.

후속 최소 대조는 실제 physics/LLM 없이 기존 fake interface에서 (i) 같은 허용 RGB bytes, command input, map, message, SIM schedule과 deterministic response를 고정하고, (ii) 평가 전용 beam label만 달리하여, (iii) 허용 input hash·semantic wire request·issued command·scheduler/control stop event가 동일한지 확인하는 것이다. path/run ID 같은 식별자와 wall duration은 명시적으로 정규화하되 action/SIM timestamp/payload를 제거해서는 안 된다. 예상 양성은 **verdict만 변하고 정상 제어 trace는 동일**한 것이다. 음성은 제어 trace 차이이며, 그때 실제 feedback edge 또는 fixture 차이를 추적한다. 이 label-only 합성 대조는 input plumbing 검사이며, 다른 실제 물리 상태가 같은 RGB를 낸다고 가정한 실험이 아니다. 별도 active-weld/host-error 대조는 정상 값 비간섭의 실패로 합산하지 않고 protocol-invalid 종료 보존을 확인한다. **이 추가 대조는 제안이며 이번에 실행하지 않았다.**

## 5. 다음으로 남는 실질적인 질문

현재 공개 blocker는 아직 terminal task success를 실증한 사례가 아니다. 먼저 [R14 decision memo](../round14/decision.md)의 control branch·issued command·frame/scan/receipt·detector 순서로 원인을 가르는 편이 직접적이다. 최종 구간에 도달한 기존 기록을 나중에 검토할 권한과 적절한 judge가 생기면, **완료 event와 goal predicate를 같은 case identity·SIM 시간축으로 연결하되 평가 verdict를 정책에 넣지 않는 검증**이 이 문서의 다음 작업이다.

관련 신규 receipt/segment authorization 후보는 독립 검증 완료 전 이 결론의 근거로 쓰지 않는다. 명령을 hold했다는 사실, 특정 segment가 승인됐다는 receipt, 실제 beam이 목표에 도달했다는 판정은 서로 다른 질문이므로 하나의 ‘성공’ event로 합치지 않는 것이 검토 기준이다.
