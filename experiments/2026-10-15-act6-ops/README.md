# ACT6 GCP 운영 결과

2026-10-15 13:25:16 KST, PR #504, ACT `d4abe49fa43c4b7af6145cca3319a5dc5e6bede0`, 교사 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`.

교사 저장 명령 census 50/50 완료: local 17,851행 중 바퀴 정지 9,730행(54.51%), 접근 42/4,288·정렬 208/1,083. 원본 100파일 SHA 일치·교사 입력 감사 inv0/held0 50/50. 이전 교사 성공을 새 ACT6 관문에 합산하지 않았다.

ACT6 관문은 계획40 중 첫1회만 제출했으며 EXIT1 HOST_ERROR로 끝났다. `scripts/run_grasp_act_recovery.py:32`의 의존 패키지 append는 기존 ACT `scripts.zone_teacher`를 가리지 못한다. 교사 `scripts/run_solo_grasp_act_teacher.py:57`이 요청한 `proportional_drive`가 없어 world/result.json/RGB 생성 전에 실패했다. 성공 확인 0, 물리 결과0, HOST_ERROR1, 잔여39 BLOCKED. 입력 감사·noise/clipping/recovery·wall/SIM·검토 프레임은 미생성이고 0으로 간주하지 않았다.

SUPERVISOR_STOP과 정지 원장을 기록했다. 당시 소유PID는 이미0으로 SIGINT 대상0. 회수22파일 해시를 검증했고 원본을 GCP 영속 디스크에 보존했다. 자기 임대/예약/프로세스0, idle20m·8hSTOP 유지. 기록/학습/폐루프 제출0. 수정SHA·새 큐가 필요하다.

운영 요약: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act6-d4abe49f.json`
정지 원장: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/stop-act6-d4abe49f-20261015.json`
상세 근거: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/act6-d4abe49f-ops`
