# Azure CPU 실행 이관 — 2026-10-11

실행·정지·원본 보관의 검증 범위는 [summary.json](summary.json)에 구분했다. S3 설치 스모크는 reset 1.3초·추가 0.5초·3대 RGB 6장·모델 호출0으로 PASS다. 운반/본 연구/실물 성공이 아니다.

소스 SHA 입력 오류, 비용 API 시작 거부, SciPy 누락, 기존 15분 가드에 의한 보관 중 종료를 포함해 실패를 보존했다. 3개 원격 실행 모두 ARM `/home/ubuntu/ugrp-archive/runs/azure-s3-smoke-20261011-{01,03,04}`에 zstd 해제 해시·전체 SHA256·rsync checksum을 확인해 보관했다. 원본은 Azure 영속 디스크에서 생성했으며 Mac 회수는 fetch-lite와 별도 QA용 대표 RGB 1장이다.

CostUSD 정상 조회, 비용 검사 실패 시 두 구독 실제 정지, Action Group 실제 정지, VM 자신의 identity 정지(1201초 유휴 시각 주입)를 확인했다. 미래 만료/매일/실제8시간 발동·이메일 도착·실제 모델 응답은 미검증이다. 비용 집계 지연 때문에 $160 실시간 결제 상한은 아니며 디스크/IP 등 비용은 남는다.

[설정·공식 참고 자료](../../docs/azure_simulation.md), [PR #438](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/438). 정책 독립 검토 전 병합하지 않는다. Oracle x86은 SSH 연결 실패까지만 확인했고 cloud deallocated 상태를 확인하지 않았다.
