# 25차 — REAL trace의 host/Pi 시간 경계

**조건부 P2 한 건:** Pi wall clock이 호출 host보다 앞서고 그 차이가 종료·회수 여유를 넘으면, 이미 저장한 사건이 실패 진단 summary의 마지막 관측·명령 선택에서 빠질 수 있습니다. [상세 원고](clock.md)는 main `b23fc087`의 지원 REAL skill trace 경로에 한정합니다. 현재 HIGH SIM의 실제 실패 원인으로 승계하지 않습니다.

| 구분 | 확인한 결과 | 확인하지 않은 것 |
|---|---|---|
| writer→분석 cutoff | Pi event의 wall time과 host span 종료 wall time을 직접 비교함 | 실제 두 장비의 offset·NTP 상태·발생률 |
| 원래 writer/분석기의 4개 대조 | 0/−5초/공통 epoch +50초는 증거 선택 유지; authored +5초가 cutoff 여유를 넘을 때 마지막 frame·명령·visible→lost 선택 누락 | 전체 REAL CLI·SSH/복사·카메라·이미지 decoding·actuator 실행 |
| 보존과 상태 | 원본 event 7개와 `FAILED` 유지; generic 실패의 진단 분류만 `UNCLASSIFIED_FAILURE`로 바뀜 | archive 삭제·원자료 손실·모든 stderr 분류 변화 |
| 최소 수용 기준 | 같은 clock domain의 종료 경계, 명시적 clock mapping/오차 또는 시간 미판정 상태로 근거 보존 | 다른 host의 monotonic 값을 그대로 비교하는 대체, 로봇 guard 완화 |

[독립 QA](validation.md)는 16개 source hash와 4조건 재실행의 golden byte 일치를 확인했습니다. 원래 archive를 유지하면서 summary의 선택만 달라지는 반례입니다. 물리 원인·과거 실행 오류 빈도는 미확인입니다.

[남은 이슈 인수표](acceptance.md)는 R19의 16개 open 이슈에 R20–23의 source 검토를 연결한 작업 선정 기록입니다. 이슈 상태를 새로 조회하거나 닫지 않았고, 실제 영상·실물·등록 연구·프로젝트 복구의 인수를 더 많은 source 검사로 대신하지 않습니다. 현재 주요 camera/attachment 및 #371 비용·분류는 [상위 탐색](../README.md)에 유지합니다.

번호 24의 이론 공백 triage는 추가 문헌 0개로 닫아 [23차 요약](../round23/README.md)에 통합했으므로 독립 게시 묶음을 만들지 않았습니다. 이전 동결 원문은 보존했고 구현·하드웨어·실제 모델·물리·렌더·원자료 재분석은 하지 않았습니다.
