# 23차 — 기억 비교와 현재 case 종료의 실제 경계

**새 결함 0개.** 2026-10-04 09:43:57 UTC 공식 조회에서 직접 main `b23fc087`, #363 `66ff0978`, #371 `a009112f`가 이전 source pin과 같았습니다. 변경된 구현이나 기존 문제의 수정을 새로 확인한 것은 아닙니다.

| 확인한 경계 | 얻은 판별 | 남긴 한계 |
|---|---|---|
| [#217 memory-v3](memory.md) | OFF도 공통 추적·안전 기억을 유지하며 재관측 결정의 ablation이다. 공식 CLI는 interim tag provider를 사용한다. | 전체 기억 제거·현재 markerless HIGH 비교·실제 paired 결과 검증 아님. 같은 초기 seed는 이후 exposure·receipt/history 동일성을 보장하지 않음 |
| [#371 마지막 관측](case.md) | 실제 case는 마지막 frame/tick의 기존 own event를 소비한 뒤 step/finish로 넘어간다. 8개 저작 대조에서 job 연결과 발생/수신 시각을 구분했다. | scheduler/finish는 기록 대역. 전체 scheduling·settlement·physics 검증이나 R8 분류 문제 수정 확인 아님 |
| 메시지 집계의 분모 | 같은 문서의 source-only 표에서 relay 접수, delivery message 행, language 행을 분리했다. | 실제 late-message 발생·효과량·분석 오용을 발견한 것은 아님 |

[독립 검증](validation.md)은 source-only memory 감사와 실제 선택 AST를 실행한 case 대조를 구별합니다. [남은 질문](backlog.md)은 등록·provider·시점 provenance의 미확인 부분에만 한정합니다.

현재 다음 판별에 새 이론 근거가 필요한지도 다시 검토했습니다. [12차 명령/물리 상태](../round12/research.md), [15차 segment/epoch](../round15/attachment.md), [16차 camera 및 통계](../round16/posture.md), [17차 기록 공백](../round17/trace.md)이 이미 필요한 구분을 제공합니다. 새 논문으로 빠진 실제 command·receipt·시간 이력을 복원할 수 없으므로 추가 문헌·새 실행은 0입니다. 같은 capture의 command/model key·취소 이력과 stored mean/report revision 연결이 다음 좁은 판별이며, 기록되지 않은 값은 미판정으로 남깁니다.

현재 #363 camera/attachment 및 #371 비용·분류 우선순위는 [상위 탐색](../README.md)에 유지합니다. 이 음성 결과로 해결 판정을 바꾸지 않습니다. 이전 원고는 보존하며 구현·실제 모델·렌더·물리·학습·CI·원자료 재채점은 하지 않았습니다.
