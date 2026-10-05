# 19차 이후 우선 질문

| 상태 | 다음 질문 | 필요한 근거 |
|---|---|---|
| Active source 문제 유지 | #363 inspect/camera와 attachment, #371 비용/실패의 수정이 실제 수용 경계를 닫았나 | 변경 SHA에서 각 최소 정상/중단/회복 대조. 동일 root cause·전체 mission 성공으로 묶지 않음 |
| Issue 탐색 후 별도 조사 | #6 현재 CI의 간헐 종료 실패는 어떤 실제 workflow·job과 연결되나 | 공식 CI metadata·로그의 해당 실패 경계. 기존 다른 caller의 worker 증인으로 원인을 대신하지 않음 |
| 연구 진단 제안, 미실행 | 재관측 뒤 달라진 것이 정보인가, 시간/hold인가, 동기화인가 | 유효한 commanded posture와 observer 계약을 전제로 decision 또는 observer 수준의 작은 대조. 본실험 arm·새 센서·물리 효과로 자동 승계하지 않음 |
| Optional 도구의 수용 경계 | V2 calibration과 Gemini replay 수정은 해당 도구에서 확인됐나 | 기존 두 identity 관문과 replay physical source closure. HIGH pilot 인수와 분리 |

최신 소스 변경이 없으면 이미 검증한 큰 fixture를 반복해 검토량을 늘리지 않는다. 새로운 수정 확인은 원래 반례의 exact caller가 바뀐 경우에만 기록하며, 이슈 종료나 실험 완료 표시는 별도 근거가 필요하다.
