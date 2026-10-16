# warp6 작업 인수 기록 (2026-10-16, 종료)

현재 NOT_READY이며 실행 중인 warp6 작업은 없다. [README](README.md)·[최종 진단](final/diagnosis.json)·[거부표](final/rejection_table.json)가 판정 기준이다. CUDA 수정·교사40회 관문·학생 성공은 미완료다.

1. 현행 README/current_status/CONTRIBUTING/AGENTS와 warp4 기록·endpoint 경보·호스트·저장 여유를 확인했다. Drive/GUI/gcp1은 사용하지 않았다. 기존 untracked COORDINATOR_NOTE.md는 보존하고 커밋하지 않는다.
2. MJWarp/Warp/NVIDIA 일차 자료를 먼저 읽고 R3 거부 분포를 저장했다. gcp2 L4에서는 원본·커널 로그만 조회했다. Xid31 PID는 빔, 같은 시각 SIGSEGV 두 개는 release로 분리했다.
3. gcp3의 승인된 VM·8h/idle20/budget-stop을 확인하고 소스와 R3 입력/compiled refs를 준비했다. 공유 Git cache가 처음 shallow여서 reference clone이 거부됐다. cache에만 ancestry를 받아 이후 source clone은 직접 cache를 reference했다. alternates 사슬·gc/prune은 만들지 않았다.
4. 소스를 먼저 커밋하고 memcheck→debug→verify를 단독 실행했다. 앞 둘은 도구 비용으로, verify는 기존 오류 시점 prefix를 넘긴 뒤 정리했다. 상속된 SIGINT 무시는 자기 child만 TERM으로 정리한 뒤 driver에서 정상 SIGINT를 복원하도록 고쳤다. 동일 CUDA 결함3회로 세지 않는다.
5. 원래 graph 빔4/release S1 6/S3 2세계 각각15틱을 단독 실행했다. 모두1.5SIM prefix/exit0·완주0이다. 빔 원래60SIM 설정을 연장했으나25.3SIM/1,372.735wall초로 첫30SIM 속도 기준 초과가 확정되어 감독 INT했다. cap_end0·HOST_ERROR와 외부 receipt를 분리 보존했다.
6. 폐기 warmup 커널 비용은 NoSlip 세 커널73.17%·broadphase0.15%였다. SAP 후보는 실행하지 않았고 물리·수용 상수도 바꾸지 않았다. 최초 CUDA 커널·버퍼는 여전히 모른다.
7. gcp2 CPU 분석은 자기 warp6-analysis lease를 생성/해제하며 실행했다. 기존 warp7 lease는 보존하고 CPU를 정지하지 않았다. stale alias 대신 저장 호스트키를 검증하는 HostKeyAlias=gcp2로 접속했다. release 영상은 고정 release 소스의 asset root를 썼고 실패한 derived 폴더도 보존했다.
8. 기존 실패2·CPU 성공1·새 prefix2·연장1개를 파일로 봤다. 새 gcp3 성공은 없다. 연장은2Hz51장+10Hz100장 전부 직접 봤다. 큰 원본과 학습 데이터는 Mac에 복사하지 않았다.
9. 종료 후8개 receipt와 원본4,882파일 SHA를 확인했다. 큰 로그12개는 lossless zstd→해제SHA 확인 뒤 대체했다. 최종 요약·거부표·압축 매핑·해시 인덱스와 회수SHA를 저장했다. command metadata의 옛 디렉터리 별칭 대신 실제 소스 SHA는 final/diagnosis.json에 정규화했다.
10. 관련 비물리37PASS, CI 목록8shard/674파일 완전성·새 테스트 정확히1회 포함을 확인했다. 자기 lease/PID가 끝났고 타작업/GPU client가 없음을 확인한 뒤 gcp3를 정지했다. 비용 알림·8h·idle20은 변경하지 않았다.

## 재개 위치

- raw: gcp3:/home/ugrp/ugrp-sim/runs/warp6/
- ops/final: gcp3:/home/ugrp/ugrp-sim/ops-reviews/warp6/final/
- 원래 graph /home/ugrp/ugrp-sim/src/warp6-prefix=82a623ee37c166ac7a9f8eaef7216c905ac1c816; profile /src/warp6-profile=400cdb0da18b538ae94e6bd42c8b0c45d7091d9f.
- adapter835ccef26aa84b08cc8f7e256fd0f43aa1583ef9, beam teacher26f84d0f0ada1c33473c83cca2d3415ce51bd247, release8e81b7d96c0c73171635348c90631462adfe1eb0.
- future cases(준비만): /ops-reviews/warp6/warp6-beam-gate-cases.json40, release-gate-cases.json A40/B40. 이 입력으로 실행0이며 미래 compiled refs export도 필요하다.
- gcp3 lifecycle: /Users/changmin/projects/ugrp-wt/gcp3setup/scripts/gcpctl.py. 모든 gcloud에 account changmin5781@gmail.com/project ugrp-sim-c-1016를 명시한다.
- gcp2 L4는 다른 작업 중이므로 재현 자원으로 쓰지 않는다. CPU 분석도 lease/프로세스 확인 후에만 한다. gcp1 금지다.

다음에는 CUDA 원인과 속도 문제를 근거로 해결해야 한다. 임의 버퍼 배율·NoSlip 생략·solver 반복 축소·CPU 교사 대체로 관문을 통과시키지 않는다. 그 뒤 알려진 실패 시드→40/A40/B40 순서이며 원본 거부표·cap_end 분리·held 감사·weld off를 다시 확인한다.
