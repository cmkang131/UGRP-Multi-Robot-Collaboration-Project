# 23차 이후의 좁은 질문

| 경계 | 확인한 상태 | 다음에 필요한 근거 |
|---|---|---|
| memory 비교 | 실제 selector와 공통 safety, 기본 interim tag provider 연결 | 선택한 provider가 실제 등록 caller에 주입됐는지와 두 호출의 동일 등록 입력. 전체 기억 ON/OFF나 고정 exposure 효과로 확대하지 않기 |
| case 종료 | 마지막 관측에서 기존 own event를 소비하는 caller 순서 | 실제 scheduler·finish 부작용이나 shutdown 신규 사건은 이번 범위 밖. 이미 있는 R7/R8 증거를 보존 |
| 현재 blocker 진단 | 기존 source 판별은 충분하며 빠진 것은 실행 provenance | 같은 capture의 command/model key·취소 이력·mean/report revision을 연결할 수 있는 기록. 새 논문으로 누락된 실행을 대신하지 않기 |
| 실제 trace 지원 경로 | 별도 후속에서 #214 문서→writer→분석→CLI 계약 조사 중 | source와 독립 QA가 닫히기 전 새 finding으로 올리지 않기 |

새 버그를 채우기 위한 가설이나 미검토 caller 전체에 대한 정상 판정은 하지 않는다. 실제 연구 인수·source 변경의 회귀 판정·프로젝트 원본 복구는 각각 별도 증거가 필요하다.
