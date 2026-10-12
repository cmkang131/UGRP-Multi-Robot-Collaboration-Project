# Azure VM4 / E2E 16차
- Standard_D16as_v6·16 vCPU AMD EPYC 9V74·128 GiB SSD, 구독 고정.
- 전체 cores 64/65, Dav6 32/65; 새 NIC/IP/NSG·host key·machine-id·보관 키.
- VM4 자기 범위 IAM과 live Run Command 통과; 초기 동일 VM3 역할 재요청은 summary.json에 기록.
- 유휴20분/8시간 가드·boot recovery/native archive 활성; 미래 일정·실제 유휴 종료는 별도.
- 스모크 EXIT0, 0.5 SIM초·카메라6; ARM 해시36/36.
- 관련 시험8통과; [구성 결과](summary.json), [작업 스크립트](operations.json).
- 16차6개 실행 소스 f92abe14; PR #450의 run-summary.json에 별도 결과.
