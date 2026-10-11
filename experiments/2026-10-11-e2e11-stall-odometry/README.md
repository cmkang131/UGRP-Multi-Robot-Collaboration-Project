# E2E11: stall odometry (DEV)
- 상태: 4회 재실행 진행 중; 완료·운반 성공 판정 전.
- 실행 코드: `540193bab171b85069fb5b47333cb292625490bf`, 번들 `e2e-stall-odometry-v198`.
- A: RGB 정지 판정 + 후진/재계획 + AMCL Q; B: RPP만, seed 61001·61002.
- 초기 4회는 릴레이 이름 거부 HOST_ERROR; provider 호출 0, 원본/해시 보존.
- 재실행 초기 점검 4/4; 18·60·120 SIM초 중간 비교는 `summary.json`에.
- 부분 미끄러짐·방향 오차·탐색 경계 고갈은 미해결이며 코드는 고정한다.
- 고정 입력 재생은 시뮬레이션/새 조건 성공 근거가 아니다.
- 원본·회수 범위·검증·출처는 `summary.json`과 `references/`를 따른다.
