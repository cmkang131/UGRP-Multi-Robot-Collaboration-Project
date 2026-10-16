# 다음 판단 메모 — 현재 pair에서 무엇을 먼저 기각할 것인가

**우선 작업은 uncertainty 기준 조정이 아니라, 실패한 바로 그 tick의 판정과 관측·명령 이력을 연결하는 것이다.** 현재 source에서 가장 먼저 구분할 것은 gate 이력/현재 σ/stale 여부다. 재관측 경로라면 그 다음은 camera-command 완료 일치다. 이 두 층을 확인하지 않으면 scan의 약한 기하와 명령 취소를 같은 “시각 실패”로 읽을 수 있다.

이 문서는 R8–R13 결과와 R14 checkpoint 경계의 실행 우선순위를 줄인 **검증 설계**다. 새 raw·heldout·실물/physics·모델을 실행하거나 분석하지 않았다. 아래 대조는 기존 합성 증거 또는 다음 source 수정의 수용 기준이며, 새 실험 실행 지시가 아니다. 제어 입력은 own wrist RGB·static map·own issued commands·actual messages를 유지한다. private 진단 상태를 LLM input에 추가하지 않는다.

## 공개 상태를 해석하는 기준

2026-10-04 07:58UTC frontier의 공개 재조회에서도 후속 결과는 없었다. 현재 고정한 #363 head는 `de03fe87d08879abefaa7dac67c7ff313df5df89`이고 구현은6727751과 같다. 공개 DEV 작성자 보고는 dock→raise_high에서 r2 입장 `SELF_UNCERTAIN`101회 뒤 rendezvous timeout, align_to_carry에서는 edge reference88.9s와 GO89.1s를 지나 r1 `POSE_UNCERTAIN`92.2s다. 후자의 실패 tick σ는 공개 보고에 없었다. 이는 source와 공개 요약의 범위이며 실제 trajectory 재분석이 아니다. 과거 edge-reference timeout을 현재 blocker로 유지하지 않는다.

근거: [현재 공개 요약](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5977439315), [23개 실제 predicate 대조](../round10/pose.md). 이후 head/실행이 달라지면 먼저 이 두 identity를 갱신해야 한다.

## 현재 #363에서 우선순위가 높은 판별

| 순서와 경쟁 설명 | 필요한 최소 자료 / 작은 대조 | 지지하는 관측 형태 | 기각·약화 관측과 다음 판단 |
|---|---|---|---|
| **1. 같은 reason이라도 직접 predicate가 다른가?** gate 이력 vs 현재 high σ vs stale/invalid | 기존 admission `failed_checks` 우선. carry는 같은 tick의 direct predicate, phase/profile, gate state/candidate_since, report.t_est와 두σ가 필요. 원본 predicate 합성23cases는 이미 검증됨 | σ가 중간 band인데 gate가 uncertain, 또는 현재 yaw/xy만 high, 또는 report stale가 구별됨 | 해당 branch가 확인되면 다른 직접 predicate 설명은 그 tick에서 기각. 아직 동작/관측 원인은 별도. 실패 문자열·마지막 집계만 있으면 unknown 유지 |
| **2. relook view가 명령 단계에서 끝났는가?** 예정 완료 vs hold 취소 | frame의 command-model servo, upstream target, port issued setpoint, cancel/queue 완료 시각. saved trace 존재 여부부터 확인. 원본 ranked+actual host-phase source fixture를 repair 전후 수용 대조로 사용 | target1230/issued1470, 남은 queue0처럼 예정 종료와 발행값이 불일치. 이 수치는 .002 host-phase command-only 증인의 값 | 동일 view에서 모델이 뜻하는 완료 issued 이력이 일치하고 취소도 없다면 이 **특정 취소 설명** 약화. physical joint 일치·good image까지 증명되지 않음. loaded carry 실패에 자동 적용하지 않음 |
| **3. frame은 왔지만 어느 단계까지 쓰였는가?** 미전달 vs consumed/scan 없음 vs weak scan vs informative receipt | frame id와 capture/available/consumed 시각, 해당 frame의 worker/scan 증가분, **current** quality, last_fix_t. 누적 counts만으로 충분하다고 가정하지 않음 | weak scan은 PF weight/cov를 바꿔도 informative=False/old fix; full fix는 새 receipt. actual source 합성 증인이 각각 있음 | current scan 적용이 보이면 '영상 전혀 미반영' 기각. current informative+새 fix면 'fix 미발생' 기각. 과거 last_fix_quality=True만으로는 둘 다 기각 못함 |
| **4. 정보가 약한 위치는 detector인가 추정모델인가?** NONE/보류 vs 국소 support vs 다중 pose | 허용 RGB의 실제 accepted edge columns, residual/support/current curvature, 필요하면 당시 particle mode 구조. predicted row count와 detector count를 구분 | detector는 unique bottom band 없으면NONE로 보류. 같은 모델 내 서로 떨어진 pose 후보가 양립하면 ambiguity 가설 지원 | detector accepted evidence가 있으면 '검출0' 기각. 하나의 좁은 mode는 그 prior/모델 범위에서만 ambiguity 약화; 실제 pose 정확도 증명은 아님 |
| **5. relative edge가 available여도 충분한 정보인가?** count/RMS vs support geometry·relative 정보 | edge reference 시각, inlier span/Sxx와 count/RMS, available/dyaw, 실제 선택 fallback level을 같은 시각으로 연결 | 같은 count/RMS라도 좁은 x-span에서 yaw 변화 민감도가 커질 수 있음. 별도 synthetic 두 조건에서3배 sensitivity 확인 | span/잔차가 유지되면 **span 변화** 가설 우선순위 하향. relative edge 성공은 absolute xy fix나 loaded gate 회복을 직접 증명하지 않음 |

2번은 [R12 command 의미/host-phase QA](../round12/research.md), 3번은 [R10 partial scan](../round10/vision.md), 4번은 [R12 detector 경계](boundaries.md#vision), 5번은 [R10 edge support](../round10/vision.md)에 근거한다. 4·5는 지금 실패의 원인으로 입증한 항목이 아니다. 현재 OpenCV `NONE`을 “영상 자체에 기하 정보가 없다”로 확대하지 않는다.

phase가 실제 HIGH 중간 checkpoint였음이 확인된다면 한 가지를 더 구분한다. **8초 재관측 timeout은 공통 pose guard의 유예가 아니다.** `wait_carry`에서 `before_control`이 먼저 실패할 수 있고, endpoint/job 실패가 있어도 controller.failure는None일 수 있다. checkpoint stop/reobserved·segment·job reason을 함께 확인해야 하며, 정상 checkpoint 종료도 다음 carry barrier의 전제일 뿐 새 GO가 아니다. [R14 source와 독립 QA](boundaries.md#checkpoint)가 이 순서를 확인했다. 공개92.2s 실패가 checkpoint였다는 증거는 없고, fixture0.1s/실제host0.05s polling의 개별 종료 시각을 일반화하지 않는다.

**이미 얻은 음성 대조를 다시 부풀릴 필요는 없다.** HIGH observer는 현재 synchronous·robot별 instance이고 기본 caller의 cross-robot callback race는 찾지 못했다. robust fit은 outlier 문제에 대응하지만 crop/identity를 인증하지 않는다. receipt144개와 tempered exponent 합 약1.986의 R11 증인은 fresh receipt와 독립 정보량의 의미가 다름을 보여 줄 뿐 fresh-fix 계약 위반이 아니다. ESS 또는 σ 하나로 실제 accuracy를 인증할 수도 없다.

## 한 번의 진단 기록이 답해야 할 질문

기존 기록에 있으면 먼저 그것을 연결한다. 없으면 과거 tick을 합성 값으로 채우지 않는다. 향후 이미 승인된 DEV 진단에서 추가할 최소 private receipt는 다음 네 묶음이다.

1. **결정:** exact source/bundle/calibration identity, robot·phase·now, direct rejection predicate, effective gate profile/state/dwell, report.t_est·σxy·σyaw·finite flags.
2. **명령:** 해당 frame의 camera model이 사용한 issued-command 층/시각, upstream target·port issued setpoint·취소/queue 종료. measured joint 값은 요구하지 않는다.
3. **관측:** frame identity와 capture/available/consumed 시각, 해당 scan 적용 여부, current quality와 마지막 successful quality·fix 시각을 분리.
4. **지원 구조:** accepted columns와 residual/support, edge span/Sxx와 fallback. mode-level 질문이 남는 경우에만 당시 belief를 더 살펴보고, 처음부터 모든 내부 배열을 영구 저장하자는 요구는 하지 않는다.

이 목록에는 검토한 source의 메모리 값과 **제안된 저장 필드**가 섞여 있다. 모두 기존 saved trace에 있다고 가정하지 않는다. 1번이 없으면 현재 uncertainty의 직접 이유를, 2번이 없으면 과거 relook 취소 여부를 확정할 수 없다고 보고하는 것이 완료된 진단이다. 더 낮은 threshold로 통과시키는 것은 이 정보 공백을 메우지 않는다.

## 현재 제어의 원인과 분리해서 처리할 것

| 별도 경로 | 확인된 문제/경계 | 다음 판단의 최소 조건 |
|---|---|---|
| #371 a009 LLM live + v88 provider | R8 post-send failure image SIM undercharge; R9 reply 수락≠frozen prompt 노출; R10 sent/reserved/released/delivered 차이; R12 worker 생성 직후 cleanup 누락 | source/version·failure class·실제 request와 message lifecycle·owned-worker 정리 경계를 확인. #363 synchronous HIGH uncertainty의 원인으로 전이하지 않음. billing .596raw→grid .5/.6는 고정 uncapped call 대조이며 실제 outcome 보정식이 아님 |
| optional Colab collection/reporting | missing phase를 incomplete로 막지 못하는 합성 증인, 일부 보고 의미 문제 | manifest의 요청 phase와 회수 증거를 비교. 현재 pair/P06 전체 결과나 과거 실제 누락 편향으로 확대하지 않음 |
| optional V2 calibration/training | R13 현재 데이터와 old metric의 재promotion, complete21→effective6 caller 연결 | 평가 생성identity와 effective21값을 각각 확인. 두 합성 증인을 실제 하나의 deployment로 합치지 않으며 D5/v98에 전이하지 않음 |

연구 효과 추정으로 넘어갈 때도 단위가 다르다. command/vision repair의 source 대조 통과는 실제 task 성공률 개선이 아니고, cost·message ledger 정정은 변경된 정책 trajectory의 사후 복원이 아니다. 기존 records의 version/validity를 먼저 구분하고, 추가 성과 주장은 그 성과를 직접 비교하는 별도 증거가 있을 때만 남긴다.

**다음 한 가지를 고른다면:** 공개 r2 admission receipts의 직접 실패 항목과 gate 이력을 확인 가능한 범위에서 먼저 분류한다. r1 loaded 실패는 같은 tick의 yaw/xy/pose-validity가 없으면 분기를 미식별로 남긴다. relook 수정의 acceptance는 이미 고정한 host-phase command-only 대조로 검증하고, 그 통과를 vision 또는 carry 성공으로 보고하지 않는다. 이 순서가 어떤 가설을 실제로 제거했는지를 짧게 남기면 이후 관측/모델 개선의 판단 대상이 작아진다.

독립 검토: frontier는 현재성·admission/carry 분기·조건부 relook 연결을, geometry는 current quality/receipt·관측지원과 적용범위를 확인했다. 추가 checkpoint 문장은 원본 source note와 별도 integration 재실행 QA의 범위에 한정했다.
