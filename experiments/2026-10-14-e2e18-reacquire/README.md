# 봉 관측 유지·재발견 단계 시험 — 사용자 결정으로 종료
- PR #483; 최종 소스 `2d57788a`; 관련 시험 47/47. 기본 off, 채택 없음.
- 전체 72실행: 게이트60+본12; 최종 v442/v443 12개는 SIM0초 사용자 중단으로 판정 제외.
- 본 v440은 첫 호출부터 릴레이 오류189회, 대체 규칙 실행: 공동 파지0/6. Gemma 비교 아님.
- 반복 대조 v426 공동 파지1/6; 사용자가 채택한 이전 기준1/12와 합산하지 않음.
- 최종 짝 비교 미실행·효과 미확인. 근거리 파지는 #484 교사→ACT 경로로 이관.
- 원본72개+대표2개 ARM 검증: `final-archive-proof.json.zst`, `final-archive-recheck.json`.
- 감시 공백·VM 감시 간격: `supervision-resume.json`, `supervision-final.json`.
- 모델 원장96호출·약$0.01058, Mac 릴레이/터널 정리. VM3는 다음 작업용으로 running 유지.
- 진단·참고 자료·대표 영상 검토·미확인 범위는 `summary.json`, `references.md`, `cohort1-video-review.json`.
