# 다음 검토와 판정 상태

| 상태 | 항목 | 다음 경계 |
|---|---|---|
| 새 P3 독립 재현 | 선택 report의 error latency alias 중복 | call당 canonical 표본·missing latency·같은값인 별도 call 보존 |
| 운영 제약 확인 | global condition/seed/attempt run key | 연구가 허가한 identity 계약과 preflight 충돌 설명. replay/budget 우회 없음 |
| 설계 의미 확인 | fresh receipt와 marginal repeat weighting | 실제 실패 tick의 quality/age/weight를 같이 보지 않고 정보량·정확도로 해석하지 않기 |
| 의심 반박 | fixed-servo predicted path의 time sample gap | BΔt/2 pad가 존재. start-relief/arm interpolation/실제 plant는 별도 범위 |
| 영향 경계 확인 | 이미지 SIM 비용·finalization·회수/보고 | 고정 record의 산술/operational label과 policy/outcome 미식별을 구분 |
| 조사 중, 확정 발견 제외 | relook hold와 빠른 pan interpolation | 실제 camera-based top3는 확인했고 그 전체 순서를 endpoint state machine에 연결하는 중. 공개 carry 원인 미확정 |
| 후속 조사 | live host/proxy/worker startup lifecycle | 부분 초기화 후 cleanup/retry caller를 actual source로 검증. 새 오류 빈도 추정 없음 |
| 이전 수정 대기 | 8차 active runtime/ROI 및 기존 peer-abort, 9–10차 기록 문제 | 변경 commit이 도착하면 해당 반례와 최소 음성 대조로 재검토 |

이번 전달은 중간 체크포인트다. 새로운 실제 caller 증거가 생긴 항목은 후속 문서로 추가하고, 미확인 mechanism을 발견 수를 채우기 위해 확정하지 않는다.
