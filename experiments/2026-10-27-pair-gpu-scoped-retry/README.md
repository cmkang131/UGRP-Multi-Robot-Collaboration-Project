# Pair GPU scoped CPU-init retry (SIM)

기존 gcp6 Tokyo에서 S20·C20을 각각 정상 종료했다. 두 arm 모두 과제 성공0/20, 원본 CPU 감사 오류0·무결성PASS다. 기존 cohort와 합산하지 않으며 REAL 검증은 없다.

CPU init/reset만 허용·계측하고 recorder 설치 후 해당 MjData 및 GPU batch 시작 후 모든 CPU mj_step을 거부하는 가드를 추가했다. 두 arm 각각146960 init step(episode당7348, template0), rollout denial0이다. Oracle 단위시험8개PASS, 실제 GPU 진행·L4 물리 프로세스·시간 기록 확인. 원본 source33대상/HEAD·운영10 및 새ops6 SHA 전후 일치, 원본 speed/pilot/host/디스크 가드 유지.

- S 누적 funnel20→1→0→0→0→0→0→0, C20→0→0→0→0→0→0→0. C 첫4 pilot 원본/재계수 모두PASS. first30 speed S1.992081391965 / C1.977615831258334 PASS.
- GCE 2026-10-27T20:09:50.392000+09:00 → 2026-10-28T00:10:58.049000+09:00, TERMINATED. 전체 할당4.018793611 GPU-h. 22:04 KST 사용자 승인으로 누적20→25.3GPU-h, 기존5.3h host budget·credit-stop 유지.
- 회수65007파일 전수SHA/크기/목록 일치. archive SHA `c6dd9c6038ca314ede122cb0eb029b2a3a7ed1a9a4d6f254ba5bffa583928425` (687748009bytes). IAP 첫전송중단은 byte offset 이어받기로 복구하고 전체SHA 재확인, 물리 재실행0.
- guard `cecfe2516`, ops `8880e81e8`. branch codex/pair-gpu-retry-gcp6-20261027만 사용. main/기존결과/preregistration v3 변경·강제push·merge 없음.
- [회차별 요약](summary.json): 모든40개 seed의 성공/종료 사유·순차funnel·CPU init count·원본 위치·archive SHA. 자세한 보고 `/home/ubuntu/ugrp-pair-gpu-scoped-retry-gcp6-20261027/REPORT.md`, 실행 메타 `/home/ubuntu/ugrp-pair-gpu-scoped-retry-gcp6-20261027/RUN_META.json`, 원본 `/home/ubuntu/ugrp-pair-gpu-scoped-retry-gcp6-20261027/results/pair-gpu-scoped-20261027`. 원격 원본은 `/home/ugrp/ugrp-sim/runs/pair-gpu-scoped-20261027`에 남겼다.
- 근거 없는 실제 장애물/최소 틈 추정은 하지 않았다(UNKNOWN/null). S current-stack artifact는 postlaunch, C는 prelaunch의 historical_replay 검사이며 이 차이를 소급 수정하지 않는다. 원본 cap_s60+carry_cap120=180SIM·정상종료 판정·처치 표현식은 유지했다. 과거 감사기의 confirmatory 필드를 이번 진단의 확증 결과로 채택하지 않는다.

검증: `python3 -B -m unittest tests.test_pair_gpu_cpu_guard tests.test_pair_gpu_retry_subset tests.test_pair_gpu_scoped_vm_watchdog -v` (8PASS). 새 GPU실행은 전용 wrapper와 original infrastructure/future driver를 사용하고, 분석은 원본 VM CPU에서 original summarize_arm.py를 실행했다. 새 체크포인트 학습·배포는 없다.
