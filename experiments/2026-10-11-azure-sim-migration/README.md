# Azure CPU 실행 이관 — 2026-10-11

실행·정지·원본 보관의 검증 범위는 [summary.json](summary.json)에 구분했다. S3 설치 스모크는 reset 1.3초·추가 0.5초·3대 RGB 6장·모델 호출0으로 PASS다. 운반/본 연구/실물 성공이 아니다.

소스 SHA 입력 오류, 비용 API 시작 거부, SciPy 누락, 기존 15분 가드에 의한 보관 중 종료를 포함해 실패를 보존했다. 3개 원격 실행 모두 ARM `/home/ubuntu/ugrp-archive/runs/azure-s3-smoke-20261011-{01,03,04}`에 zstd 해제 해시·전체 SHA256·rsync checksum을 확인해 보관했다. 원본은 Azure 영속 디스크에서 생성했으며 Mac 회수는 fetch-lite와 별도 QA용 대표 RGB 1장이다.

CostUSD 정상 조회, 비용 검사 실패 시 두 구독 실제 정지, Action Group 실제 정지, VM 자신의 identity 정지(1201초 유휴 시각 주입)를 확인했다. 미래 만료/매일/실제8시간 발동·이메일 도착·실제 모델 응답은 미검증이다. 비용 집계 지연 때문에 $160 실시간 결제 상한은 아니며 디스크/IP 등 비용은 남는다.

[설정·공식 참고 자료](../../docs/azure_simulation.md), [PR #438](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/438). 정책 독립 검토 전 병합하지 않는다. Oracle x86은 SSH 연결 실패까지만 확인했고 cloud deallocated 상태를 확인하지 않았다.

## #438 독립 검토 P1 3건 수정

소스 `f566eeefb8b6afd3c041064e1706c9f2e1f8cac3`: 비용 상한은 SIGINT·flush와 최대 10분 checksum 보관 시도 후 반드시 할당 해제한다. 일반 종료는 EXIT만 있는 미보관 원본·실패 lease를 보존하고 시작/부팅 때 재보관한다. 관련 두 시험 파일 38개(모의 PowerShell 실행 포함) 통과. [수정·시험·실배포 범위](review-fixes-20261011.json).

실제 변경은 기존 runbook 내용만 publish했고 바이트/Published 재조회가 일치했다. VM을 켜지 않았으며 두 구독 모두 deallocated다. Run Command 권한·lease-aware 자정 일정/기존 강제 일정 비활성화·게스트 가드/복구 설치는 허용 범위 밖이라 미적용이며, 실제 우아한 정지/ARM 보관은 검증하지 않았다. 이전 스모크 증거를 새 후보의 실배포 검증으로 승계하지 않는다.

## #438 마무리 — P2와 승인된 배포

소스 `9589255c`: 복구/정지의 보관 실패를 종료 코드74로 전달해 `azctl start`가 새 실행을 거부한다. 실패 원본·lease 보존과 실제 복구 CLI→start 차단을 포함해 관련 두 시험 파일 **44개 통과**(PowerShell 모의12개 포함). `origin/main 8d772093`의 #435/#439 저장 자동화·문서와 Azure 내용을 함께 보존했고 충돌한 CI 목록에 양쪽 시험을 등록했다. 새 실행 번들 ID 없음.

사용자가 승인한 Run Command 권한은 Automation·VM identity 모두 구독88b7ee7f의 자기 VM에만 할당했고 PAYG에는 추가하지 않았다. runbook Published/전체 바이트, 일일00:00 KST→Daily 연결, 기존 DevTest 강제 종료 Disabled를 재조회했다. VM identity의 무해한 실제 명령 PUT201·GET200·exit0을 확인했다. 게스트 가드·감독 실행기·복구 서비스는 이미 현재 버전이라 재설치를 건너뛰고 종료 도우미만 백업 후 원자 교체했다. 서비스 재시작·복구/시뮬레이션 실행·VM 시작/정지 없이 활성 lease를 보존했다.

새 소스의 실제 우아한 종료·ARM 보관·미래 자정 발동은 미검증이다. 다른 작업이 사용하는 VM은 running을 유지한다. [배포·해시·CI 상태](finalize-438.json); 이전 P1 기록과 과거 스모크 결과는 별도 이력으로 유지한다.

동시 작업자가 추가한 `1bfa2bde`(반복 start 시 살아 있는 형제 writer 보존)를 포함해 관련 시험45개를 다시 통과했다. 설치 helper 해시 일치와 갱신한 runbook 전체 바이트/Published, 실제 일정 연결의 Daily·Cost·Force도 재조회했다. 이 재확인은 다른 작업의 시뮬레이션/운반 결과를 합산하지 않는다. 이전 후보 CI는 새 push로 취소됐고 최종 CI는 PR checks와 로컬 마무리 원장에 따로 남긴다.
