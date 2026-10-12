# E2E speed3 DEV — 2026-10-12 (Refs #448 #453)
- v215: 주행2ms·팔 조작 발행 뒤0.25ms, implicitfast/noslip10·가속10개·관측0.4s; 카메라640×480/FOV/배치·weld OFF.
- 이전 성공 승계 없음; v214의1/2ms 고정 후보는 접촉 probe실패로 진단 보존.
- 같은 시각6개(기존3/후보3)×60SIM초: 후보 중앙2.984 wall/SIM(n=3), 기존 종료 대기; summary.json에 전체 실패·원본·sha.
- 단계별 probe4/4: 직진·회전·파지·공동들기, 동적 dt전환은 별도 단위시험(전체 운반 아님).
- [MuJoCo timestep/integrator](https://mujoco.readthedocs.io/en/3.6.0/computation/#numerical-integration); dt출처 dispatch_contact_profile.local_contact_fine=.25ms.
- Gate: 계획동시수×30SIM초 중앙≤4.0, 초과/불완료 SPEED_GATE_FAIL; 6.0초과 연속10분 경고, 우회사유 필수.
- 재시작(조정자, 미실행): VM3 새SHA에서 `bash experiments/2026-10-12-e2e-speed3/restart.sh "$SHA" 454 --execute --speed-gate-limit 4.0` (`--plan`으로 먼저 확인).
- 준비: 새소스·유한relay `~/ugrp-sim/relays/e2e-speed3/a.json`, fresh `e2e-speed3-r3-budget-{x86,arm,mac}.json`; x86/ARM6×4608MiB, Mac6×80MiB.
