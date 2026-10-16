# E2E 10차 RPP lookahead

- PR #433, DEV, 실행 SHA `e81c817c`, v197 / 7.90.0: A4 RPP+Gemma / B2 RPP+Jev / C2 off.
- 실제 8/8 실행: LLM A4/4·B2/2·C2/2, 자기 지도·운반 모두 0/N; 398.05–499.70 SIM초에서 wall cap(HOST_ERROR).
- 최초 v196 제출 8건은 CLI 등록 오류로 물리·모델 시작 전 실패; 실제 실행과 분리해 모두 기록.
- 같은 2 seed·SIM 구간: off→RPP 전진 583→4,477, 회전 2,563→849, 부호 반전 501→29. 고정 56프레임 반전 11→0.
- 최장 단계는 B 경계 확인 전 mapping; 접촉·명령 위치 누적으로 사후 지도 오차 최대 6.98m. 보수적 health는 중단 없이 기록.
- ARM 실제 원본 55,330/55,330 해시 일치, Mac 경량 118.6MB 회수; 초기 실패 포함 16건 검증. VM deallocated.
- [요약·출처·한계](summary.json), [압축 상세 기록](round10-details.json.zst), [실행별 원본 해시](hashes/); PR 종료 시 DEV 보존 규칙 적용.
