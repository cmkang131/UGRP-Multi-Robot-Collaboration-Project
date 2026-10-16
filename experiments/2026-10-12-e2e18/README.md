# E2E18 DEV
- PR #461, codex/e2e18; 현재 판정·전체 실행 색인과 해시는 summary.json / run-summary.json.
- 2026-10-13 07:29 UTC: 114시도, 공동 파지13(동일 seed 재현 포함), 시작→끝 운반0; VM4 사용자 중단6개 분모 제외.
- 최원: v320/r65 seg1 grasp_lift831.2 SIM초. 두 번째 실제 공동 파지·최종 B 내려놓기는 미확인.
- v324–v327: 인식 가속·정렬 후보·짧은 GO/ACK; v328–v329: 기존 정렬을 유지한 짧은 GO/ACK 비교.
- VM3만, 최대12개·부하<12.8·메모리≥6GiB·계획 동시 부하30SIM 속도 게이트≤3.0.
- 마감2026-10-13 13:00 UTC(22:00 KST), 원본 보관 해시 확인 뒤 VM3 deallocate·확인.
- 원본: Azure ~/ugrp-sim/runs → ARM /home/ubuntu/ugrp-archive/runs; Mac은 fetch-lite만.
- 결정 모델·Gemma 대화 구조와 기억 보강(v330–v339)은 별도 작업 결과를 통합 비교 예정.
