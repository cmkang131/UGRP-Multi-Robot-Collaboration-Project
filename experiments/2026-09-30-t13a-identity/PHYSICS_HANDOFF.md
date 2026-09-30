# T13a 실행 인계 추가 — target-aware 후보

#320의 [SIM_CHECKS.md](SIM_CHECKS.md)는 당시 미연결 상태와 최종 환경 기준을 보존한다.
새 `zone-target-v85` / `zone-target-checks` v2.18.0 후보의 정확한 실행 명령·증거 목록은
[통합 PHYSICS_HANDOFF.md](../2026-10-01-t13-target-backend/PHYSICS_HANDOFF.md)에 있다.
T13a는 `--group t13a`로 I1/I2 각각900초, 합1800 SIM초만 할당한다.

이 후보는 개발용 v2 환경이며 최종 v3 인수는 미완료다. 공개 시각 catalogue와 own RGB로
특정 개체를 선택하고 동일 색의 다른 개체가 있으면 명시 거부한다. 이번 PR은 fake/offline
검증만 수행했으며 실제 물리 효과·배송·TensorBoard 결과는 조정자가 실행/회수 후 판정한다.
