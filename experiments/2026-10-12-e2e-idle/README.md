# E2E17 explore deadlock — DEV #453
- 이전 감사: 16실행/32로봇 종료 latch22/32, 무명령100초20/32; [진단](summary.json), [원인·출처](references.md).
- v208= v207 + 기본 off replan_v1: 무명령30초 뒤 제외목록 만료·재계획·제한시간 재관측.
- VM3: v208/v207 × seed61001–61003 짝6개. VM4: v208 seed61004–61009 독립6개(짝 비교 아님).
- [사전 기록](e2e17-registration.json), [실행·실패·재제출·보관 기록](run-summary.json); 실제 SHA는 각 RUN_META와 실행 기록.
- 종료 판정: 같은 실행에서 LLM 작동·자기 지도 완성·시작→끝 운반 모두 확인. 상한은 실행7시간·작업8시간.
- 초기180–300초 응답·프레임·실제 이동·전진·단계 확인, 이후10분 간격; 확정 막힘은 SIGINT 후 수정·새 번들 재제출.
- 원본은 Azure 영속 디스크→ARM 전체 해시 검증; Mac은 이미지 없는 가벼운 기록만. DEV 원본 정리는 해당 PR 종료 때 기록과 함께.
- v211: 부분 영역-전체 경계 연결 / 접근 실패 재시도 / 둘의 조합; [후보11개](boundary-repair-registration.json), 관련35시험+raw재생1 통과. 초기11개 종료·ARM 검증, seed61004 계속.
- v212: DEV 미관측 footprint 정지를 기존 native 경로 검사+기록으로 전환; [후보6개](boundary-native-registration.json), [원인·출처·검증](boundary-native-references.md), 관련24시험 통과.
