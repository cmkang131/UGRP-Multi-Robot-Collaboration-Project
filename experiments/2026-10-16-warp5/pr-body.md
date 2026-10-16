자기 지도·운반·E2E의 MJWarp 배치 이식을 위한 렌더 관문과 어댑터입니다. reloc20 위 공통 warp-act를 병합했고 공유 backend/core 파일과 CPU 비교 경로는 보존했습니다.

**Draft / NOT_READY. 전체 이식은 미완료입니다.** 동일 자세88개에서 RGB MAE 중앙38.47→0.804/255, ORB FAST7 바닥53→126.5(CPU107.5), 경계2364→4104(CPU4087), 거짓 경계0을 확인했습니다. 최종 색 결과는59/88만 같아 전체 렌더 관문은 실패했습니다. 재보정 후보59/88, 주황색 열 제외 후보54/88도 미채택입니다. CPU/MJWarp 결과는 합산하지 않습니다.

변경은 기본 off alpha/spot180/texture-modulation 렌더 후보, 자기 지도·운반 AST 배치 장벽과 다중 카메라/명령 포트, reloc21 반복 제거 수정의 이식, E2E 비동기 경계 원형·workflow 등록입니다. 공유 설치 MJWarp 파일·물리·카메라는 바꾸지 않았습니다.

N16 운반/place/완주·xy/yaw·실제 입력 감사0회, E2E 실행기/ACT·교사 연결·규칙 물리 검증은 미완료입니다. Mac 약16GiB가 AGENTS의20GiB 제출 바닥 아래여서 새 물리 배치를 보류했습니다. Gemma+50% 경보로 실제 LLM0. Mac 물리·렌더·GUI0입니다.

검증: 관련 비물리30 passed, 표준 workflow 목록 확인. 과거 frozen-source baseline 실패1건을 별도 기록했으며 전체 CI/병합 통과는 아닙니다. 원본 manifest1,868파일 및 회수4파일 해시 일치. 자기 프로세스/lease0, 타 작업·L4 VM과 기존8h/idle20/budget-stop 보존.

결과·원본·한계: experiments/2026-10-16-warp5/README.md, summary.json, e2e-design.md, references.md. raw는 gcp2 /home/ugrp/ugrp-sim/runs/warp5/에 보존합니다. Drive 제외를 따릅니다.
