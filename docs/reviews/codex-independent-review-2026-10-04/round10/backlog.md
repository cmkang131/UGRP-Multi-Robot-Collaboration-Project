# 완료된 판별과 다음 검토

10차는 전달 중간점이다. 발견 수를 늘리기 위한 중복 검토 대신 실제 caller와 수정·판별 기준이 생긴 항목만 남긴다.

| 상태 | 검토 항목 | 이어질 일 |
|---|---|---|
| 신규 재현·독립 확인 | 선택 Colab 회수 기대 집합 누락 → 잘못된 complete/cleanup | 누락 phase/trial을 완료 분모에서 제거하지 않는 수용 기준. 실제 cloud stop은 수행하지 않음 |
| 신규 재현·독립 확인 | 선택 report의 authoritative 시도 원장과 lifecycle 불일치 | marker 없는 종료 실패와 실제 미시작을 구분하는 수용 기준 |
| 현재 소스 진단 | uncertainty 입장/운반 분기와 gate 이력 | 공개 요약에 없는 거부 tick predicate는 미확정. 기존 허용 기록의 유무부터 구분 |
| 설계 범위 확인 | partial likelihood update와 informative fix 분리 | current quality·last successful quality·age를 서로 다른 필드로 읽기 |
| 설계 범위 확인 | 같은 count/RMS에서 support span 차이 | 기존 자기 영상의 span/Sxx로 좁은 가설 판별; 새 threshold나 실제 GT 오차 추정으로 확대하지 않음 |
| 음성 반증 | timestamp/reset, schema/role/ID, censor 후 실행 | 이 fixture가 검사한 경계만 통과. 전체 system safety 인증 아님 |
| 이전 활성 | 8차 비용/종료 기록/ROI, 기존 peer-abort | 수정 commit이 나오면 해당 경로와 기존 음성 대조로 좁게 재검토 |
| 이후 source 검토 | core evidence aggregation/eligibility, artifact identity와 missing-data 분모 | 실제 caller가 있는 입력만 후보로 승격. optional 경로는 별도 표시 |
| 이후 연구 검토 | dialogue metric의 가용성/자기보고/인과 사용 | 지표별 분모·입력 provenance·검증 가능한 결론을 유지 |

실제 실패 원인, 오류 빈도, 통신의 인과적 성공 효과, 실환경 센서 calibration은 이번 source/synthetic 감사로 정하지 않는다. 새로운 증거가 없는 같은 가설의 반복 실행보다 미확인 경계를 명시하는 쪽으로 다음 작업을 배정한다.
