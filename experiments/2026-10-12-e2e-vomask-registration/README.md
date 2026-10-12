# VO 마스크 정합 감사·v207 준비 — PR #452 DRAFT
- 원인: ARM 원장4개(789,759B, 해시4/4)를 회수해 자기 자세120/124를 연결했으나 정적 world 정합은0/124. 마지막4프레임은 제어기 예외로 원장 없음; 시각 차이1.3s·카메라 FK124/124 정상.
- [summary.json](summary.json): 이동64/120·회전42/120 위치오차합(mm)은 off103.006/113.607, RANSAC86.380/119.915, 지도 단독·결합은 각각 유효0/120·오차null. 정지0/120, 부분미끄러짐14/120.
- 선택 `homography_turn_off`: 이동86.380mm/6.482°·회전113.607mm/6.530°로 off보다 나쁘지 않음. 회전을 명령만 쓰면106.244mm/8.761°라 방향 악화. 선택 자료는 이미 본124프레임으로 과적합 가능.
- v207(`e2e-vomask-turn-v207`,7.100.0)은 v206+비회전 RANSAC이며 지도 투영은 OFF. 정적 지도↔자기 지도 앵커가 없어 요청한 실제 지도 마스크2조건 검증은 미완료; identity·spawn·평가 정답 대입 없음.
- 관련 시험59/59, off 재현오차0, 최종 소스 `1d8bc3ee`; 두 준비 번들 CLI·카탈로그·전체 소스해시 검증. 시뮬·모델·Azure 조작0, PR은 draft 유지.
- Azure 짝 실행 명령(작성만·실행 금지): `bash experiments/2026-10-12-e2e-vomask-registration/azure-pair.sh <SOURCE_SHA> 452 --execute` — v207/v206, seeds61001–61003×2, 7시간; 예산·릴레이·admission 절차는 스크립트 참조. Mac 릴레이18417 현재 미사용, 시작 안 함.
- 재생: `python -m scripts.replay_e2e_vomask --raw-root <기존-fetch-lite> --image-root <기존-e2e-usstall-audit> --ledger-root /Users/changmin/projects/ugrp/outputs/e2e-vomask-registration-20261012 --output <새-기록-경로>`; 실제 경로·sha256은 [입력 목록](replay-final/input-hashes.json).
- [상세 재생](replay-final/replay.json)·[실패 포함 시도](attempts.json)·[선택 판정](bundle-decision.json)·[번호 스캔](registration-scan.json)·[참고 자료](references.json). 큰 예측/평가 JSON은 zstd, 이미지 추가 회수0.
- 남음: 자기 RGB로 앵커가 연결된 원장·정지 표본·새 자료 일반화·실제 v206 초음파/폐루프 검증·독립 검토. 부분미끄러짐 위치합은0.327mm 악화했으며 새 확증/E2E 성공으로 해석하지 않는다.
