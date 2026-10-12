# 읽기 전용 정지 감사: 16실행 × r1/r2 = 32개

진행 중 스냅샷이며 실행 완료·성공 판정이 아니다. 정지는 발행된 병진·회전 명령 모두 0인 연속 구간; 자세 반올림 정지는 별도다. B 경계·경로는 모두 0/16. 전체 frontier 수/blacklist/costmap은 원장에 없어 복원 불가. 종료 이벤트의 사유는 후보 없음/차단/방문/계획실패를 합친 코드 경로다.

| 호스트/실행 | 로봇 | 관측 SIM초 | 종료 이벤트 SIM초 | 연속 무명령 SIM초 | 최근100초 이동/회전 명령 | 원인 | 자기위치 오차 m(평가전용) |
|---|---|---:|---:|---:|---:|---|---:|
| azure/e2e14-b-s61001-r2 | r1 | 1069.0 | 83.2 | 985.2 | 0 | finished_latch | 1.77 |
| azure/e2e14-b-s61001-r2 | r2 | 1069.0 | 906.4 | 162.2 | 0 | finished_latch | 3.16 |
| azure/e2e14-b-s61002-r2 | r1 | 1004.0 | 478.4 | 525.8 | 0 | finished_latch | 0.57 |
| azure/e2e14-b-s61002-r2 | r2 | 1004.0 | 600.2 | 403.8 | 0 | finished_latch | 0.96 |
| azure/e2e14-b-s61003-r2 | r1 | 729.0 | 128.0 | 601.2 | 0 | finished_latch | 1.38 |
| azure/e2e14-b-s61003-r2 | r2 | 729.0 | — | 0.0 | 499 | moving_or_short_hold | 8.40 |
| azure/e2e14-b-s61004-r2 | r1 | 839.0 | 620.8 | 218.0 | 0 | finished_latch | 5.13 |
| azure/e2e14-b-s61004-r2 | r2 | 839.0 | 57.0 | 782.2 | 0 | finished_latch | 0.71 |
| azure2/e2e13-long-a-s61001 | r1 | 703.0 | 83.2 | 619.2 | 0 | finished_latch | 1.77 |
| azure2/e2e13-long-a-s61001 | r2 | 703.0 | — | 0.0 | 494 | moving_or_short_hold | 9.68 |
| azure2/e2e13-long-a-s61002 | r1 | 707.0 | 478.4 | 228.8 | 0 | finished_latch | 0.57 |
| azure2/e2e13-long-a-s61002 | r2 | 707.0 | 600.2 | 106.8 | 0 | finished_latch | 0.96 |
| azure2/e2e13-long-a-s61003 | r1 | 663.0 | 128.0 | 535.2 | 0 | finished_latch | 1.38 |
| azure2/e2e13-long-a-s61003 | r2 | 663.0 | — | 0.0 | 500 | moving_or_short_hold | 9.15 |
| azure2/e2e13-long-a-s61004 | r1 | 694.0 | 620.8 | 73.0 | 130 | finished_latch | 5.13 |
| azure2/e2e13-long-a-s61004 | r2 | 694.0 | 57.0 | 637.2 | 0 | finished_latch | 0.72 |
| azure2/e2e13-long-b-s61001 | r1 | 692.0 | — | 0.0 | 500 | moving_or_short_hold | 1.79 |
| azure2/e2e13-long-b-s61001 | r2 | 692.0 | — | 0.0 | 500 | moving_or_short_hold | 5.31 |
| azure2/e2e13-long-b-s61002 | r1 | 743.0 | — | 0.0 | 467 | moving_or_short_hold | 9.12 |
| azure2/e2e13-long-b-s61002 | r2 | 743.0 | — | 0.0 | 497 | moving_or_short_hold | 7.01 |
| azure3/e2e15r2-a-s61001 | r1 | 668.0 | 475.6 | 192.6 | 0 | finished_latch | 7.60 |
| azure3/e2e15r2-a-s61001 | r2 | 668.0 | 437.4 | 230.2 | 0 | finished_latch | 6.59 |
| azure3/e2e15r2-a-s61002 | r1 | 616.0 | 224.6 | 391.0 | 0 | finished_latch | 1.61 |
| azure3/e2e15r2-a-s61002 | r2 | 616.0 | 175.4 | 440.4 | 0 | finished_latch | 0.47 |
| azure3/e2e15r2-a-s61003 | r1 | 609.0 | — | 0.0 | 501 | moving_or_short_hold | 1.08 |
| azure3/e2e15r2-a-s61003 | r2 | 609.0 | 294.8 | 314.2 | 0 | finished_latch | 1.93 |
| azure3/e2e15r2-b-s61001 | r1 | 669.0 | 83.2 | 585.2 | 0 | finished_latch | 1.79 |
| azure3/e2e15r2-b-s61001 | r2 | 669.0 | — | 0.0 | 494 | moving_or_short_hold | 10.29 |
| azure3/e2e15r2-b-s61002 | r1 | 609.0 | 478.4 | 130.8 | 0 | finished_latch | 0.57 |
| azure3/e2e15r2-b-s61002 | r2 | 609.0 | 600.2 | 8.8 | 449 | finished_latch | 0.96 |
| azure3/e2e15r2-b-s61003 | r1 | 601.0 | 128.0 | 473.2 | 0 | finished_latch | 1.38 |
| azure3/e2e15r2-b-s61003 | r2 | 601.0 | — | 0.0 | 500 | moving_or_short_hold | 7.46 |
