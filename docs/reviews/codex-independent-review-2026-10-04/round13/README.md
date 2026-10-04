# 13차 체크포인트 — 선택 V2 보정의 재승격과 실제 설정 전달

2026-10-04. **보존된 optional V2 경로에서 두 개의 독립적인 P2를 확인했다.** 현재 pair v98/D5의 결함으로 합치지 않는다. source는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`이며 실제 실물 측정·물리·학습·과거 결과를 분석한 것이 아니다.

현재 개발 경로의 우선 수정 대상은 [12차 relook](../round12/control.md)과 [worker 초기화](../round12/runtime.md), 기존 [image SIM·failure 분류](../round8/runtime.md)다. 이번 두 항목은 해당 optional 보정/학습 도구를 사용할 때의 추가 수정 대상이다.

| 단계 | 확인한 결함 | 직접 재현과 수정 기준 |
|---|---|---|
| 측정 정정→검증→승격 | 공식 recorder가 holdout 한 행을 정정해도 validator는 현재 자료로 산출됐는지 확인하지 않은 옛 metric을 승인하고 새 dataset hash와 묶음 | 합성 재계산4.5°>3°인데 저장0°로 통과. metric 생성 시 입력/매개변수 identity를 고정하고 현재 입력과 일치시켜야 함. [producer/validator](stale-metric.md) |
| validated manifest→학습 CLI→core | CLI가 complete21개 중6개만 explicit override로 전달해 나머지15개가 기본값이 되면서 calibrated mode를 표시 | 같은 complete manifest를 core가 직접 읽으면21개 모두 적용. CLI 실제 구성과 mode를 일치시켜야 함. [consumer](consumer.md) |

두 반례는 서로를 전제하지 않는다. validator 반례는 consumer 버그가 없어도 생기고, consumer 반례는 manifest가 올바르게 검증되었다고 가정해도 생긴다. 따라서 하나를 고쳤다는 이유로 다른 경계가 보장되지는 않는다. 실제 과거 사용 여부·오차 빈도·transfer 성능 변화·현재 pair의 성공률은 확인하지 않았다.

[D5/v92 조립기](assembly.md)는 완료·출처·step/PRBS support·PARTIAL/HIGH-only 조건을 source로 검토했으며 새 결함을 확정하지 않았다. 이 부정 결과를 full measured calibration 승인이나 전체 tests 통과로 읽지 않는다. [coverage](coverage.md)는 AST 목록·부분 함수 읽기·전체 모듈 읽기·실행 증거를 분리한다.

[연구 해석](research.md)과 [공식 1차 근거5개](primary-sources.md)는 계산 provenance·검증 domain·실제 적용값의 증거를 구별한다. [독립 검증](validation.md) · [계속할 일](backlog.md). 원래13개 manuscript와1–12차 본문은 보존하며, GitHub는 Markdown만 추가한다. 재현 code/작은 JSON은 Mac 전달본에 있다.
