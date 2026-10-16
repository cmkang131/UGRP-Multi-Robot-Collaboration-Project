# act16w native-v1 교사 관문 재계수 (조정자, 2026-10-17 00:20 KST)

원본: gcp2 L4 /home/ugrp/ugrp-sim/runs/act16w-native-gate-r2/ (group-00..06, 세계 12+7+10+6+3+1+1=40). Haiku 독립 재계수(읽기 전용).

- 성공(physical_success, 세계별 result.json.zst): 40/40. 종류별 cyan/green/red/yellow 각 10/10. 제외 0, 커버리지 40/40 seed(87220–87259, 누락·중복 0).
- status complete 40, cap_end 0, host_error 0. input_audit invisible_measurements 0, held_world_reads 0. weld off 40/40.
- 접촉: 그룹별 native-contact.json = warp_native_contact_v1, gpu_noslip 0, cpu_noslip {0}.

## 불일치 (기록 문제, 물리 결과 아님 — 조정자 판단)
1. 세계별 scene.json의 cargo_contact_profile 은 cargo_noslip_v1(noslip_iterations "10") 로 기록됨. 실제 적용은 native-contact.json의 측정값(0). scene 빌더가 기본 프로필 이름을 그대로 적은 것으로 보임 → PR #568(nsoff)에서 장면 기록이 실제 적용 프로필을 적도록 확인할 것.
2. gate_eligible=false 40/40: scripts/run_warp_act_teacher.py 는 --teacher-gate-queue(admission) 없이 돌면 false. 이번 관문은 정식 admission 대기열 없이 실행됨. rejection_table(resume4/native-gate-rejection_table.json)은 있음. 조정자는 이 재계수 근거로 관문 통과를 인정하되 "admission 없이 실행"으로 표시한다.
3. source_sha 세 값: f0db6b1(controller), e40ff44(실행), c27a9d5(독립 감사) — 작업자 보고 줄의 역할 구분과 일치.

확인 안 됨: physical_success 정의의 코드 확인, 8254 파일 전체 해시 대조(표본만), 영상 직접 확인(작업자 검토만).
