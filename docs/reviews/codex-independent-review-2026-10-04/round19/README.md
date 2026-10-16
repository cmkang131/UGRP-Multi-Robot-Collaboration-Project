# R19 — 현재 우선순위와 주장 강도의 독립 재검토

**판정: 검토한 핵심 주장은 범위에 맞으며, 새 버그는 0개다.** 최신 R17 전달 README의 **inspect camera/provider → checkpoint attachment → #371 비용·분류** 배열을 유지한다. R18 optional Gemini finding은 해당 replay의 source 동일성 검사에만 추가한다. 새 음성 결과나 많은 검토 문서가 기존 문제의 수정·실제 성공을 뜻하지는 않는다.

고정점은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`, #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`다. 공식 09:02 UTC 현재성은 R18 담당의 확인을 인용하며 이번 담당이 새로 조회한 것은 아니다. 최신 navigation·핵심 보고서를 읽고 R12/R16 취소층만 원본 소스로 좁게 대조했다. 새 재현·물리·모델·학습 실행은 없으며, 이전 QA의 실행을 이번 담당의 재실행으로 세지 않는다. [검토 출처와 범위](validation.md#provenance).

## 지금 결정할 순서

| 실행 경계 | 유지할 우선순위와 이유 | 다음에 판별할 최소 조건 |
|---|---|---|
| 현재 inspect/relook | [R16](../round16/posture.md)을 먼저 진단한다. 현재 함수에서 exact 중간 tuple→missing camera key→failure 지속이 연결됐다. 공개 단계 실패와 맞는 명령 경계지만 raw 인과를 재검증한 것은 아니다. | 지원 자세 전환·취소를 처리한 뒤 관측 가능한 상태인지, 안전한 종료 상태인지 명시한다. 단순 clock 경과나 receipt reset을 새 fix로 해석하지 않는다. |
| carry checkpoint 수용 전 | [R15](../round15/attachment.md)의 같은 close epoch에 대한 beam 형상 유지가 필요하다. 현재 첫 inspect 실패의 설명은 아니지만, carry 도달 뒤에만 수정해도 된다는 뜻도 아니다. 두 작업은 병렬로 진행할 수 있다. | 연속 checkpoint 뒤 attachment 형상 유지, 실제 open 뒤 해제, 새 close epoch 재확립. 기존 loaded uncertainty/progress 검사와 stationary/toward/away 대조를 보존한다. |
| #371 모델 경로의 비용·실패 기록 | [R8](../round8/runtime.md)의 deterministic SIM 비용과 최종 실패 분류, [R12 worker ownership](../round12/runtime.md)을 함께 유지한다. 현재 HIGH synchronous worker와는 별개다. | 정상·전송 뒤 실패는 각 요청에 청구된 image 비용을 반영하고, 전송 전 미요청은 0/refund 대조를 유지한다. final status/원장/분류 일치, provider 사용량 보존·전송 뒤 추가 요청 0·부분 초기화 child 회수도 확인한다. |
| HIGH edge 관측 | [R17 현재성](../round17/beam-currentness.md)으로 R8 ROI 문제는 해소되지 않았다. 현 영상 발생·운반 영향은 미확인이다. | 실제 종료 row와 crop으로 잘린 run을 구분한다. 정상 y299 edge와 잘린 y299를 함께 검사하고, unavailable을 grip 실패로 바꾸지 않는다. |
| 선택 도구 사용 전 | [R13 V2 두 결함](../round13/README.md), [R18 Gemini source 누락](../round18/replay.md)은 해당 도구의 수용 경계다. 현재 HIGH 첫 파일럿 전체의 필수 선행 과제로 합치지 않는다. | V2는 metric provenance와 21개 실제 적용값을 각각 닫는다. Gemini는 기록된 physical dependency 변경을 source mismatch로 잡는다. 실제 다른 궤적의 valid 통과는 입증되지 않았다. |

이 표의 순서는 시간상 진단 순서와 수용 전 요구를 구분한다. 물리 발생률·피해 크기의 순위표나 모든 작업의 직렬 대기 목록은 아니다.

## 합쳐서는 안 되는 두 취소 경계

R12와 R16을 **명령 취소 계열의 후속 증거**로 집계하는 판단은 합리적이다. 그러나 하나의 root cause가 확정됐거나 하나의 회귀 통과로 둘이 해결된다는 뜻은 아니다.

| 증거 | 실제로 다른 경계 | 독립적으로 남겨야 할 회귀 |
|---|---|---|
| R12 | relook tick의 반복 hold가 lower port의 속도 제한 보간을 취소한다. upstream 목표와 port issued setpoint가 다른 채 예정 완료로 진행한다. | 완료 view에서 상위 목표·발행 명령·lower issued setpoint의 계약 일치. 실제 joint 일치로 확대하지 않는다. |
| R16 | relook 진입이 upper ArmSequence의 남은 event를 지운다. upper issued camera tuple 자체가 미등록 자세에 남아, settle 뒤 provider가 fail-closed된다. | 중단된 자세의 camera identity, unsettled 보류, known posture 정상 대조, failure/receipt 수명. camera lookup 통과를 informative fix로 확대하지 않는다. |

원본 `PairAlignRelook._begin_align_relook`은 upper queue를 직접 지우고, `tick`은 relook 중 hold를 반복한다. `CameraRobotPort.hold`는 lower `_servo_targets`를 지운다. 따라서 wheel-only hold로 치환한 R12 음성 대조가 R16의 upper queue 취소까지 해결한다고 추론할 수 없다. 반대로 R16에서 미등록 자세 정지를 피했어도 R12 lower 보간 완료가 자동 보장되지는 않는다.

R16 전달본의 옛 첫 문장에는 “같은 원인”이라는 표현이 있었으나, 최신 R17 top README에서는 제거됐다. 현재 편집 결함으로 재집계하지 않고 이후 요약에도 위 구분을 유지한다. R12의 1230/1470PWM과 완료 시각은 de03 합성 fixture 값으로 남긴다. 이번 source 대조에서 관련 9파일은 66ff까지 동일했지만, 66ff 전체 host 재실행이나 새 8단계 dock sequence(7개 고유 pan) 검증을 대신하지 않는다.

## 수용 조건을 과도하게 넓히지 않기

- **R16에서 provider 재생성은 선택한 회복 정책의 조건이다.** 미등록 정지 상태로 들어가는 조합을 예방하는 수정에 worker 재시작 API까지 무조건 요구하지 않는다. 이미 failed provider를 회복시키겠다면 그때 ownership·fresh frame/receipt·failure 수명을 검증한다. strict camera lookup을 느슨하게 하거나 `failure=None`만 쓰는 것은 근거가 없다.
- **R15의 attachment는 command-held 가정이다.** 이를 물리 파지 인증으로 승격하지 않는다. cancel/abort는 명령 중단이며 자동으로 open/beam 해제를 뜻하지 않는다. unknown을 body-only로 축소하는 정책도 별도 정당화가 필요하다. loaded uncertainty gate가 계속 남는다는 사실은 beam 형상 누락의 해결이 아니다.
- **R17 done·R18 valid의 이름보다 실제 predicate를 따른다.** 양쪽 done은 절차 완료이고, optional replay의 1mm 대조는 정해진 시점의 XYZ다. 어느 쪽도 실제 release·전체 궤적·task 성공을 새로 인증하지 않는다. 음성 대조·reference identity 통과를 추가 버그나 전체 admission으로 세지 않는다.
- **수정된 finding은 닫힌 범위를 유지한다.** same-tick final veto는 검증한 control/arm 두 caller에서 수정됐다. 이를 옛 R8 문구를 근거로 활성 미해결로 되살리거나, 모든 비동기 dispatch의 보편적 보장으로 넓히지 않는다.

다음 체크포인트는 새 검토량보다 **변경된 source에서 어떤 기존 수용 경계가 실제로 닫혔는지**를 먼저 보여 주면 된다. 소스·합성 경계의 통과와 별도로 승인된 실제 인수 증거를 구별하며 검토를 이어간다.
