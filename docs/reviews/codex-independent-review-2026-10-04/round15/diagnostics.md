# 15차 진단 경계 — 행 수, 방향, 작은 probe

두 검토 모두 새 버그0개다. Source가 달라지거나 실제 영상·동작이 추가되면 별도로 확인할 부분을 남긴다. 상세 원고·script·golden·독립 JSON은 Mac의 `round15/evidence/`에 보존했다.

## Row support

de03 opening의 실제 카메라·지도 모델을 두 authored own pose에서 분석했다. 실제 `LOOK_P20/WIDE_LOOK_PANS` 다섯 unique pan과 admitted calibration hash `398372…82f5`를 고정한다. **66ff는700/2300 방향을 추가했으므로 아래 값은 최신 전체 목록의 분석이 아니다.**

| 동일한 authored pose B의 예측 모델 | 남은 행 | 국소 rank | 해석 |
|---|---:|---:|---|
| pan1230 |177|2|world-y 변화에 대한 해당 열이 정확0 |
| 같은 pan 모델 행 복제 |354|2|비영 singular value만 √2배; null 방향 유지 |
| 기존 목록의 pan1230+1770 |275|3|두 방향의 모델은 이 국소 null을 보완 |

`J diag(.01m,.01m,π/180rad)`의 선택한 좌표 척도다. Guard sigma, observation noise whitening, Fisher information, posterior covariance가 아니다. 같은 wall identity·paired-bottom·finite row 및 step-halving 조건으로 남긴 **예측 행**이며 actual detector 열이 아니다. 독립 h/4 차분도 기존 retained 행에서 일치했다. Global ambiguity나 실제 base 변화·latency·가림·보정 잔차는 이 계산 바깥이다.

따라서 “행이 많으니 모든 위치 축을 안다”는 해석을 기각할 수 있지만, 현재 robot의 실패를 이 null로 설명하거나 새 pan/ROI/threshold 처방을 정당화할 수는 없다. 먼저 실제 pan 완료→frame→detector→scan이 어느 방향까지 수행됐는지를 확인해야 한다. 원고 `opening-row-sensitivity.md`, 재현/결과/독립 QA/quarter-step 대조를 함께 보존했다.

## M1 handoff

보존된 optional M1/v9 경로(main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`)의 작은 probe를 독립 재실행했다. 실제 `_tick_probe/_arm_steps`, command bookkeeping, LoggingPort/CameraRobotPort, observation gate와 V6 hook을 연결했다. 60 PWM 단계는30ms 보간으로 다음 hold 전에 끝나며 pan1500→1560→1440→1500이 발행된다. 이 때문에 R12의 다른 caller·큰 pan 취소를 모든 probe에 일반화할 수 없다.

Attachment collaborator=True는 anchor 갱신, False는 기존 anchor 유지와 `CARRY_REANCHOR_UNCONFIRMED` 종료를 만든다. Frame 재사용/hash/robot ID/arm posture/pan delta/time 위반 여섯 대조도 anchor 이전에 거부된다. 영상 decoder나 실제 attachment 판정, 실물 joint·하중 유지, pickup부터 전체 경로는 실행하지 않았다. 원고 `m1-reanchor-handoff-audit.md`, script/result와 독립 QA는 Mac evidence에 있다.

판단 출발점은 [최신 현재성](currentness.md)과 [14차의 증거 단계 구분](../round14/decision.md)이다. 해당14차 메모의 공개 실패 값은 de03 당시 보고이며, 66ff 새 stage 결과와 섞지 않는다.
