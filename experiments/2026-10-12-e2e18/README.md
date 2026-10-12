# E2E18 DEV
- 진행 중: 후속 PR #461 (기존 #458은 조정자가 일부 SHA를 #460으로 병합 후 닫음).
- v216–v244: 통합·속도·VO·자기 경로/정렬·모델 통신 수정; 모든 실패/재제출은 run-summary.json 및 additional_run_records.
- v233: 모델이 선택한 경로 hash 참조를 검증된 계약으로 확장; B 관측 위치는 자기 RGB 좌표에서 계산.
- v240→v241: 카메라 목표를 취소하던 접근 hold를 바퀴 영속도 명령으로 분리; v240의 wait 오도메트리 미지원도 수정, 물리 임무 성공 미확인.
- 게이트 30 SIM초·VM별 총 6개, 2.5 초과 최적화 후 사용자 승인 fallback 3.0 적용; 초과 실행은 시작하지 않음.
- 새 실행 상한 60분, 인계 후 전체 작업 종료 2026-10-13 01:00 UTC; 종료조건 세 개를 같은 실행에서 확인해야 성공.
- 원본: Azure ~/ugrp-sim/runs → ARM /home/ubuntu/ugrp-archive/runs 해시 검증; Mac은 fetch-lite만.
- 인계·새 후보 상태: summary.json; 기울기 분석: tilt-analysis.md; 기존 v241 12개는 유지.
