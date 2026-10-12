# E2E speed3 DEV — 2026-10-12
- Refs #448 #453; 새 물리/관측 코호트, 이전 성공/비트등가성 승계 없음.
- 후보: baseline 0.25ms/5Hz, dt1 1ms/5Hz, dt2 2ms/2.5Hz; implicitfast, noslip10 유지.
- dt 출처: sim/dispatch_contact_profile.py local_contact_fine (0.25ms); 4096은 reset 포함 추정.
- [MuJoCo 권고](https://mujoco.readthedocs.io/en/3.6.0/computation/#numerical-integration): timestep은 모델별 안정성 확인, implicitfast 권장.
- 판정: 6개 동시 60 SIM초 wall/SIM 중앙값 목표 ≤3; 정적 probe는 유한 물리 개연성만.
- speed gate: 같은 계획 동시수 30 SIM초, 기본 상한4; 우회 사유와 실패·경고 영구 기록.
- 요약·원본 위치·sha256: summary.json; 연구 재시작은 조정자가 수행.
