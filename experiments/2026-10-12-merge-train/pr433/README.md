# PR #433 병합 검증

- 기존 v195의 원본 blob 6개·런타임 434개 해시를 보존하고 v209 / 7.102.0으로 재등록.
- E2E v210 / 7.103.0: 기본 OFF reviewed_v1, 기존 보정 길이 펄스만 사용·인식 JSON 해시 고정.
- v199/v200 등록·실험 기록은 보존; 과거 워크플로는 원래 SHA에서 실행.
- 실제 Transport 명령 큐→Robot.commanded와 설정 변조 반례를 검사.
- 시뮬레이션·모델 호출 0회, 실행 결과 승계 없음.
- 검토·검증·원본 SHA: summary.json.
- 참고: Git show·pytest 선택 의존성 문서(상세 링크는 summary.json).
