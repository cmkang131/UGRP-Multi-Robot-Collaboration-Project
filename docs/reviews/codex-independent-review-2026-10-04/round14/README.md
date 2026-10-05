# 14차 체크포인트 — 현재 pair에서 먼저 기각할 설명

2026-10-04. **새 버그 수를 늘리기보다 지금 실패를 구분할 증거를 정리했다.** 첫 문서는 [현재 pair 판단 메모](decision.md)다. 같은 `UNCERTAIN`이라도 gate 이력·현재 sigma·stale report가 다르고, relook의 예정 완료·실제 발행 command·frame·scan·informative fix도 서로 다른 단계다. 자료가 없는 분기는 unknown으로 남긴다.

| 이번에 좁힌 질문 | 확인한 경계 | 활용 |
|---|---|---|
| HIGH 중간 정지의8초는 pose guard 유예인가? | 아니다. endpoint 공통 pose guard가 먼저 종료할 수 있고 checkpoint50mm와 common70mm 조건도 다름 | [checkpoint 순서](boundaries.md#checkpoint)에서 timeout·POSE_UNCERTAIN·edge 대기를 분리. 다음 carry barrier 전제 통과를 GO로 보고하지 않음 |
| predicted edge 수가 실제 detector 정보인가? | top-only 예측 credit과 actual bottom 기반 관측 형식이 다름. 작은3pose×7pan 대조에서는 top3가 같음 | [관측 경계](boundaries.md#vision). 실제 정보량·오탐률·현재 실패 원인으로 확대하지 않음 |
| pursuit waypoint 생략이 무검사 wall motion인가? | 실제 pair caller에는 마지막 명령 guard가 남음. planner keepout과 static wall guard 집합은 다름 | [접근 caller](boundaries.md#approach). 실제 route 반례 없는 추가 keepout 범위는 미해결로 보존 |
| 낮은 calibration score가 유일한 파라미터인가? | optional V2 plan의 rate plateau/deadband 구간에서 서로 다른 값이 정확히 같은 예측을 냄 | [식별가능성](servo.md). 같은 입력 반복만으로 동등성은 깨지지 않지만 실제 물리 최적값·현재 pair 오차를 추정하지 않음 |

이번 묶음의 신규 구현 결함은0개다. 현재 수정 후보는 [12차 relook/worker](../round12/README.md), 기존 [8차 image SIM/failure 분류](../round8/runtime.md), optional V2의 [13차 두 연결 결함](../round13/README.md)에 보존했다. 이미 입증한 결함을 다른 대조로 다시 계수하지 않는다.

Source: #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`, optional V2 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`. 공개 작성자 보고는 실측 raw 재분석과 구별했다. 실제 physics/render/model/학습, 구현 변경이나 guard threshold 완화는 하지 않았다. [독립 검증](validation.md) · [backlog](backlog.md).

상세 checkpoint/observer/approach source 원고는 Mac evidence에 보존하고, GitHub에서는 [짧은 경계 요약](boundaries.md)으로 모았다. Checkpoint 증인은 `beam_grasp_confirmed=True`를 collaborator로 두므로 grip receipt가 segment를 넘어 어떻게 인정되는지나 loaded geometry 전체를 검증한 결과가 아니다.
