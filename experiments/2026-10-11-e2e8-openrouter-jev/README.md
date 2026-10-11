# E2E 8차 OpenRouter / Jev DEV
- A/B: seed61001·61002, 정상 초기 점검 4/4일 때만 61003·61004 추가(총≤8).
- Gemma: 유료 OpenRouter / DeepInfra 고정 / fallback off; Jev: semantic_v2, 행동만 선택.
- 판정: 정상 LLM / 자기 지도 경로 생성 / 시작부터 B 전체 착지까지 운반을 각각 센다.
- 원본: Azure 영속 runs → ARM 검증 보관; Mac fetch-lite.
- summary.json에 실패·초기 점검·호출·불일치·위치 점프·해시를 기록한다.
