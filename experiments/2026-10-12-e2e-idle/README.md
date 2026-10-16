# E2E17 explore deadlock — DEV #453
- 이전 감사: 16실행/32로봇 종료 latch22/32, 무명령100초20/32; [진단](summary.json), [원인·출처](references.md).
- v208= v207 + 기본 off replan_v1: 무명령30초 뒤 제외목록 만료·재계획·제한시간 재관측.
- VM3: v208/v207 × seed61001–61003 짝6개. VM4: v208 seed61004–61009 독립6개(짝 비교 아님).
- [사전 기록](e2e17-registration.json), [실행·실패·재제출·보관 기록](run-summary.json); 실제 SHA는 각 RUN_META와 실행 기록.
- 종료 판정: 같은 실행에서 LLM 작동·자기 지도 완성·시작→끝 운반 모두 확인. 상한은 실행7시간·작업8시간.
- 초기180–300초 응답·프레임·실제 이동·전진·단계 확인, 이후10분 간격; 확정 막힘은 SIGINT 후 수정·새 번들 재제출.
- 원본은 Azure 영속 디스크→ARM 전체 해시 검증; Mac은 이미지 없는 가벼운 기록만. DEV 원본 정리는 해당 PR 종료 때 기록과 함께.
- 2026-10-12 사용자 지시로 속도 해결 위해 중단: 모델29/35, 지도·운반·E2E0/35; EARLY_STOP29·HOST_ERROR6, 잘못된 launch54 별도.
- ARM89/89 보관본 전체 해시 재검증·가벼운 기록3,065파일 회수; [중단·보관 검증](speed-stop-archive.json). VM4는 이미 deallocated 확인, VM3는 speed3 측정에 유지.
