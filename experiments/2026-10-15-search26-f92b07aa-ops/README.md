# search26 GCP 운영 결과 (2026-10-15)

고정 소스 `f92b07aa869dc3b960d22adb69c01f2b9b8c9eeb`, PR #484, gcp1 / n4-highcpu-64. 지정 대기열 `20261015-grasp-search26-f92b07aa-diag.json`만 처리했다. 조정자 승인은 비교 DEV 진단32회이며 관문40·데이터 기록·학습·승격은 승인되지 않았다.

| 장면 | 완료 성공 | 제어/접근 실패 | cap_end | 감독 중단 | 계획 |
|---|---:|---:|---:|---:|---:|
| base(off) | 5/8 | 3 | 0 | 8 | 16 |
| cargo_v6 | 5/8 | 2 | 1 | 8 | 16 |

seed315709 base: r2가 자기 teal 끝에서 준비 대기하는 동안 r1은 blue 끝 부근에서 최종 명령 안전 검사에 band_blue로71회 거부된 뒤 인계 종료했다. 진행 가능한 안전 대안을 내지 못한 결함을 확인해 본 배치에 SUPERVISOR_STOP.json을 쓰고 확인한 PID에만 SIGINT를 보냈다. 분석 중 다음16회가 자동 시작되어 모두 감독 중단했다. 동일 SHA 재제출·분모 채우기·안전 가드 우회는 하지 않는다.

seed8311723의 후보 막힘은 base can_1 / cargo_v6 red_1에 각각4368개 후보가 거부된 것이다. seed8311711은 서로 다른 끝을 보지만 r2가 안쪽 정렬 방향과 약140.64/138.82도 어긋난 상태에서 safe-prefix 복구 후8초 무진척 인계로 끝났다. 이 두 실행의 하위 경로·기하 원인은 추가 확인이 필요하다. cargo_v6 seed315709는37.1SIM초의 planning_wall_safety_cap이며 결함 실패·HOST_ERROR와 분리했다.

첫30SIM초 wall/SIM 중앙값은 base2.336, cargo_v6 2.347(장면별5회 측정)이다. 완료 전체 wall/SIM 중앙값은 각각2.351/2.340이다. 동시16 설정으로 시작했지만 조기 종료로 실제 동시 수가 줄었으며, 속도 적격 관문이나 전체32회 성공률 근거로 쓰지 않는다.

관찰한 입력 감사는32회 모두 enabled·invisible_measurements=0·held_world_reads=0이다. 최종 결과 감사24회, 마지막 스냅샷만 남은8회(결과가 running7개·빈 파일1개)는 구분한다. 중단16회를 성공/실패로 판정하지 않는다.

실패5·cap_end1·감독 중단16회의 r1/r2 자기 카메라를 각각6시점, 합계264프레임 직접 검토했다. 원본 개요 RGB는 search22 설정으로 기록되지 않았다. 관계 몽타주의 개요는 평가 원장 XY 재구성이며 RGB로 표시하지 않는다. 각 실행 검토 시각은 direct-frame-review.json에 있다.

GCP 원본: `/home/ugrp/ugrp-sim/runs/search26-comparison32-f92b07aa`. 전체 SHA256SUMS 검증 통과. 실패·중단 원본 자기카메라716장을 `/Users/changmin/projects/ugrp/outputs/gcp1-runs/search26-comparison32-f92b07aa/raw/`로 회수하고716/716 SHA-256 대조했다. 성공의 무거운 원본은 GCP에 유지한다.

관문별 누적 통과·거부, 사유별 개수, 원본 경로·재현 명령은 `rejection_table.json`에 있다. 운영 원본 보고 폴더: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/search26-f92b07aa-ops/`. 보고서와 몽타주도 전송 후 해시 검증했다. 자기 예약·lease만 해제했고 유휴 가드는 유지한다.
