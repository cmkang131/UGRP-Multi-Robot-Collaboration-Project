# T13b 실행 인계 추가 — target-aware 후보

#329의 [SIM_CHECKS.md](SIM_CHECKS.md)는 당시 미연결 상태와 최종 환경 기준을 보존한다.
새 `zone-target-v84` / `zone-target-checks` v3.1.0 후보의 정확한 실행 명령·증거 목록은
[통합 PHYSICS_HANDOFF.md](../2026-10-01-t13-target-backend/PHYSICS_HANDOFF.md)에 있다.
T13b는 `--group t13b`로 M-U/M-H/D-H/D-U 각각900초, 합3600 SIM초만 할당한다.
원본30초 이동·62.5초 낙하 사건은 변경하지 않는다.

이 후보는 개발용 v2 환경이며 최종 v3 인수는 미완료다. RGB 추적·holding/resting에서
RecoveryJobs를 실제 하위 backend에 연결했다. 전체 pickup region의 clear-empty 인식은
미구현이므로 M-U absence 항목은 미지원/unknown으로 기록한다. H 불성립과 no-op를
제외하거나 재실행으로 대체하지 않는다. 물리·실제 복구·TensorBoard는 조정자 인수 사항이다.
