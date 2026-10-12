# E2E18 DEV
- 진행 중: 후속 PR #461 (기존 #458은 조정자가 일부 SHA를 #460으로 병합 후 닫음).
- v216–v233: 통합·속도·VO·자기 경로/정렬·모델 통신 수정; 모든 실패/재제출은 run-summary.json 및 additional_run_records.
- 최신 v233: 모델이 선택한 경로 hash 참조를 검증된 계약으로 확장; B 관측 위치는 자기 RGB 좌표에서 계산.
- v233 관련 오프라인 시험 22개 통과; 물리 임무 성공은 미확인.
- 게이트 30 SIM초·VM별 총 6개, 2.5 초과 최적화 후 사용자 승인 fallback 3.0 적용; 초과 실행은 시작하지 않음.
- 새 실행 상한 2시간, 전체 작업 종료 2026-10-12 21:03 UTC; 종료조건 세 개를 같은 실행에서 확인해야 성공.
- 원본: Azure ~/ugrp-sim/runs → ARM /home/ubuntu/ugrp-archive/runs 해시 검증; Mac은 fetch-lite만.
