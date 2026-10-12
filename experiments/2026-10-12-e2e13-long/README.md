# E2E 13차 긴 실행

VM2, A seed61001–61004/B seed61001–61002, v199·Gemma OpenRouter·DEV light.
실행당 wall 7시간·SIM 1800초, 미검증 속도 후보 모두 OFF.
릴레이 이름·수명과 명시적 wall 상한만 확장하며 제어기 기본값은 유지한다.
판정: LLM 작동 / 자기 지도 경로 완성 / 시작부터 끝까지 운반.
첫 4분 실제 이동·모델·직진 점검; 이후30분 확인만, 제어 개입 없음.
원본 VM2 영속 디스크→ARM 전체 해시; Mac은 이미지 제외 fetch-lite.
모든 실패·결과·비용·VM 시간은 summary.json; PR #433, 병합 금지.
