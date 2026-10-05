# 13차 이후 검토 상태

| 범위 | 현재 상태 | 다음에 필요한 확인 |
|---|---|---|
| optional V2 metric 재승격 | 정상 recorder→validator→promote 반례와 독립 QA 완료 | 입력/parameter identity 변경을 재평가 전 차단하고 무변경 재검증은 허용하는 수정 |
| optional V2 CLI calibration 전달 | complete21→effective6 반례와 독립 QA 완료 | default calibrated 경로의 전체 유효값·정직한 mode·unvalidated 거절·explicit override 보존 |
| D5/v92 assembly | source-only 부정 검토 완료, 새 결함 없음 | 실제 완성 산출물의 identity와 등록된 admission을 별도 확인; 빈 측정값을 source 추론으로 채우지 않음 |
| 현재 relook/worker |12차 조건부 현재-path 결함 동결 | 구현 수정이 생기면 narrow delta와 기존 의미 있는 대조만 재검증 |
| shared planner/waypoint 실제 소비 | 후속 coverage 대상 | 현재 지원 지도와 실제 caller가 segment/footprint를 재검사하는 경계 |
| 추가 optional aggregate/paired compare | 계약·caller 검토 중 | 실제 지원 writer가 비교 identity/회수 분모를 깨는 증인이 없으면 새 버그로 올리지 않음 |

AST inventory는 전체 정독률이 아니며 검토 횟수는 새 결함 수가 아니다. 같은 반례를 source 범위만 바꾸어 반복 계수하지 않는다. 새로운 실제 caller·구체 입력/소비 계약·연구 해석에 필요한 증거를 기준으로 다음 일을 선정한다.
