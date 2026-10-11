# E2E 10차 RPP lookahead

- PR #433, DEV, 최대 8회: A4 RPP+Gemma / B2 RPP+Jev / C2 off.
- 고정 입력 56프레임: 전진 1→50, 회전 55→6, 회전 부호 반전 11→0. 실제 주행 성공과 구분.
- Nav2 Jazzy 0.6m lookahead·0.785rad 회전 규칙, 기본 OFF; 보정된 단축 펄스/관측 주기는 유지.
- DEV 보수적 중단은 기록만; 물리 실패·실행 오류·실행 시간/저장 예산은 유지.
- [요약·출처·한계](summary.json), VM 영속 원본 → ARM 전체 해시 검증, Mac 가벼운 기록만.
