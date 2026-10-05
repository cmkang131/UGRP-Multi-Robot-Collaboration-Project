# 17차 이후 진행 큐

| 판정 | 범위 | 남은 질문 |
|---|---|---|
| 현재 문제 유지 | checkpoint attachment / interrupted camera failure | 각각15차와16차 수용 기준. 실제 raw 효과와 구현 수정은 별도 |
| 기존 조건부 finding 잔존 | R8 beam ROI crop | 현재 wrapper에서도 수락선 유지. 실제 HIGH 영상 발생 여부는 미확인 |
| 수정 확인 유지 | same-tick final veto |15차에서 검증한 control/arm 두 caller |
| 좁은 음성 검증 완료 | final release와 endpoint done handoff | 명령/절차 완료를 물리 release/task predicate와 구별 |
| source-only 진단 계약 | 현재 trace/record provenance | 기존 동일-capture 명령 필드·guard 상세를 먼저 연결하고, 저장되지 않은 mean/revision은 unresolved로 남김 |
| 후속18차 | 추가 current caller와 issue 관련 범위 | 실제 반례와 목적이 있는 경계만 확인. 동일 원인·음성 대조를 새 버그로 중복 집계하지 않음 |

게시 뒤에도 검토를 계속한다. 새 head가 나오면 이전 본문을 덮지 않고 변경 영향을 별도 분류한다. 실제 실험·raw 결과·센서/GT 입력이나 threshold 정책을 source 감사의 편의를 위해 바꾸지 않는다.
