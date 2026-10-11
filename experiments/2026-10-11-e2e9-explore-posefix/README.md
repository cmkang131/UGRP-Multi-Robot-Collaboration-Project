# E2E 9차 DEV

- PR #433, 기본 off frontier 진행·innovation pose·원자 종료 기록, 번들 v194.
- A OpenRouter Gemma / B Gemma+Jev, seed61001·61002 짝 실행; 초기 통과 때만 추가2seed(총≤8).
- 판정: 한 실행에서 LLM 정상 응답 / 자기 RGB B 운반 경로 / 물리 시작→끝 운반 모두 충족.
- 8차 재생: r1/r2 132프레임 위치 오차0; 초기 sweep 11.6/12.4 SIM초 완료, 목표1회씩.
- 초기 이동 확인 전에 중단되어 반복 회전·도달 불가를 확정할 수 없었음.
- 탐색 기본 off/on과 pose 기본 off/innovation은 별도 토글; 실제 실행은 두 수정 on.
- 원본·판정·참고 자료·해시는 summary.json. 연구 결과가 아닌 개발 자료.
