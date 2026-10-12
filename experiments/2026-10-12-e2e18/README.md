# E2E18 DEV 통합
- PR #458, base `codex/e2e-speed3`; merge 통합 이력 보존.
- v216 부분 B 2시점 합의 → v217 정적 캐시 → v218 제곱 거리/OpenCV1 → v219 float32 격자 → v220 VO/초음파 관측주기 정렬.
- VM3 seed61001–61006, VM4 seed61007–61012, 각 6개·7시간 상한.
- 속도 30 SIM초: v216 5.17/5.37 → v217 3.02/3.23 → v218 2.78/2.67 → v219 2.90/2.83.
- 초기 상한2.5 실패 후 상한3.0 재측정: v220 2.963/2.866 통과·12개 실행 중.
- 실제 결과/실패/재제출/출처/해시: `run-summary.json`, `gate-*.json`, `initial-health-*.json`.
- 원본: Azure 영속 `~/ugrp-sim/runs` → ARM 전체 파일 해시 보관; Mac 가벼운 회수.
