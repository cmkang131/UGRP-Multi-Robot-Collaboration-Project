# gcp6 pair GPU 재시도 — 중단

S seed8342000/8342001 시작 후 봉인 실행기의 CPU 물리 초기화를 뒤늦게 발견해 중단했다. GPU 전용 조건 위반이며 유효 재현0, 완료0이다. C는 미실행. 과제 실패율로 집계하거나 기존 cohort와 합산하지 않는다.

새 raw 및 전후 source SHA, 회차별 상태, TERMINATED와 KST 시작/정지는 [summary.json](summary.json)에 기록했다. 상세 보고와 회수한 247개 파일의 해시 검증은 `/home/ubuntu/ugrp-pair-gpu-retry-gcp6-20261027/`에 로컬 보존한다. Git 원격 raw 백업으로 간주하지 않는다. 후속 래퍼는 CPU 초기화 전에 실행을 거부하며 순수 계획/거부 시험 3개 PASS.
