# Solo carry4 GCP 운영 결과

소스 `870c0c59f3c2eae556abaa809ac1eddf33dce5ca` / PR #505 / gcp1 n4-highcpu-64. 진단 8개 중 1개만 제출, 성공 확인 0/1·감독 중단1·나머지7 BLOCKED. 관문·학습 없음.

자기 명령 위치 오차로 정적 벽 변환이 접근 목표를 막고, 경로 없음에서 0 명령을 반환한 채 20 SIM초 이상 정체했다. 첫30 wall/SIM2.971, 감사 invisible0/held0. 원본 result의 physical_success는 null이며 완료 실패율로 환산하지 않는다.

원본: `gcp1:/home/ugrp/ugrp-sim/runs/solo-carry-93220-870c0c59`. 전체 원격 SHA256SUMS·회수20파일·선택32프레임·압축2원본 해시 검증 통과. 영상은0–53초를 직접 보았고 r2 자체 영상은 저장되지 않았다. 정지 마커/SIGINT 후 소유PID0·임대 해제. 타 작업과 VM 가드는 유지했다.

상세는 summary.json, 운영 증거 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/solo-carry-870c0c59-ops`. 요약 SHA256 `4dd2f79d70ee01d1d096282d70ee549df70ccaae404f7467217febea16edc720`. 새 SHA/계획이 필요하며 원본은 GCP 영속 디스크에 보존했다.
