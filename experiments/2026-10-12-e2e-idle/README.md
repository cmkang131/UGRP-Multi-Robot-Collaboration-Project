# E2E explore 무명령 교착 — DEV, draft #453
- 읽기 전용 16실행/32로봇: 종료 latch 22/32, 100 SIM초 무명령 20/32; [정지 시점·사유 표](stops.md), [요약·원본 위치](summary.json).
- 원인: `e2e_exploration.py:55`의 finished가 `public_navigation_persistent.py:212`에서 재탐색을 막음; LLM 48응답은 모두 continue. 세부 분기는 저장 frontier/blacklist/costmap 부재로 미확정.
- 자기 위치를 평가 전용으로 세계 좌표 변환: 추정 경기장 밖17/32·실제0/32, 최대10.29m 오차; 펄스/VO 적분과 지도 보정 누적오차. 제어기로 정답 전달 없음.
- 기본 off `--explore-deadlock replan_v1`: 발행 명령0이30초 → 목표 제외 목록 만료·재계획 → 필요 시 기존 제한시간 회전·목표 재선정; v208(7.101.0)=v207+토글.
- 시험37/37, 저장 종료상태 부분 재현22/22 명령재개(30초); costmap은 명시적 합성 입력이므로 실제 통과·역사 상태 완전 재생 아님. [연구·제약](references.md).
- Azure 짝 명령(작성만): `bash experiments/2026-10-12-e2e-idle/azure-pair.sh 49bffaae7a1cf533fff63d1d4f878f3a8f84edf2 453 --execute` — v208/v207×seed61001–61003, 6동시·각7시간 상한; 지금 실행하지 않음.
- Mac 릴레이18424(조회 시 미사용, 실행 직전 재확인), Azure18393는 해당 배치 전용 수신점 확보 후 사용; 예산·초기3–5분 점검·ARM보관·lite회수 절차는 스크립트. 시뮬레이션0·모델0.
- 판정: 같은 seed에서 baseline 무명령30초가 생겼을 때 후보가 ≤30.2초 내 이동/회전 명령을 발행하고, 추가30초 내 병진·frontier 재선정 여부를 각각 기록; 연속 회전만으로 탐색 성공 인정하지 않음. 위치 오차·B/경로·비용도 비교.
- Refs #446 #450 #452. 기존 원본·다른 worktree 수정0; 새 무거운 원본0. 요약·LLM 응답·명령 문맥·해시 영구 보존; DEV 무거운 원본은 향후 해당 PR 병합/종료 시 cleanup-records와 함께 정리.
