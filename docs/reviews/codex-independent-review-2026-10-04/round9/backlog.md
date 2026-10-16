# 체크포인트 9 뒤 이어갈 작업

게시한 source snapshot은 동결하고 다음 결과를 별도 추가 문서로 이어갑니다. 아래 조사 중인 질문은 아직 확정 결함이 아닙니다.

| 경계 | 이번 판정 | 다음에 할 일 |
|---|---|---|
| control permit·STATUS | P3 기록귀속1건, STATUS 표적144조합 한정통과 | guard wait/재관측의 hold·arm target bookkeeping 경계를 fake port로 추적. 기존 same-tick abort 중복 제외. |
| runtime protocol | accepted 예약·reply_to와 실제input provenance의 보증 범위 확인 | request identity·중복JSON key·invalid 응답 정규화를 실제 parser/transport로 대조. |
| vision temporal | command 갱신 표현에 따른 반복감쇠 적용범위 확인; 신규버그0 | timestamp·재초기화·delay queue의 실제 caller invariants를 별도 appendix에서 확인. |
| P06 평가 | 초기실패 frozen horizon mismatch P2 | 별도 회수 경로에서 declared계획과 실제 artifacts의 완결성 확인. 현재pair 실행과 분리. |
| 연구 주장 | 실제 최종request의 정보 가용성과 causal use를 구별, PF 정적이론 한계 계산 | 연구 질문에 필요한 최소 request lineage/판별표를 검토. 실제raw 없이 관찰 결과를 만들어 채우지 않음. |
| 실행identity | 현재 CLI의 단순 source/map/calibration/cap mismatch 허용 가설 한정반박 | 새로운 dynamic module/외부entry가 실제 실행경로에 들어올 때만 source closure 연결을 재검토. |
| CI coverage | 현재pair·새 HIGH edge/PF tests가 목록에 포함됨 | 전체CI 재실행 대신 새 반례의 조합이 기존test에서 빠졌는지 해당범위만 확인. |
| optional Colab/ACT/REAL | 현재 E2E blocker로 승격하지 않음 | 재사용에 의미있는 후보를 별도 낮은우선순위 문서로 검증. 실행/원자료삭제/새환경시작은 하지 않음. |

기존 원고에서의 “현재”는 각 문서의 SHA와 시점입니다. 이미 고친 clock/prompt/start-relief를 새 미해결로 재등록하지 않습니다. 관측하지 않은 실제 발생률·완주·성능은 unknown으로 유지합니다.
