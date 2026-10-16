# E2E 초음파 stall odometry — DEV 준비, 실행 0회
- 조사 8출처·한계: [references.json](references.json); 기본 off `rgb_vo_us_v1`: VO 우선 → 최신 근거리 5판독 정체·충분한 전진·SEARCH 팔 자세 → 이동 0/Q 증가 → 그 외 v2.
- 후보 `e2e-usstall-v206`(7.99.0) = v205 + 토글 + `sensors.ultrasonic_front=on_v1`; 기존 v205 보존. 번호 근거 [registration-scan.json](registration-scan.json).
- [summary.json](summary.json): 관련 오프라인 시험 68 통과, 저장 RGB 124/124 v2 대체 동일; 초음파 원장 없어 ZUPT 실데이터 재생 불가. 마스크 벽 ROI 수치는 offline-final 기록.
- 사전 판정: seeds 61001–61003, A(v206) vs B(v205) 6 동시, 7시간/1,800 SIM초; 전진 중 벽 앞 odometry 관통 감소·비정지 오탐·E2E n/N·시간/명령/모델/비용을 함께 평가, 탐색 DEV이며 채택 아님.
- Mac 릴레이 18416(13·14·15차 18392/18414/18394와 분리), VM loopback 18393; 할당·기존 실행 종료·수신기 여유·저장 예산·초기 3–5분 점검은 조정자 책임. 현재 VM1–3에는 제출하지 않았다.
- [Azure 짝 실행 명령](azure-pair.sh): 최신 소스를 배치한 선택 VM에서만 아래 명령. 스크립트에 Mac 릴레이/터널·6개 명령·RUN_META·보존 절차가 있다.
```bash
bash experiments/2026-10-12-e2e-usstall/azure-pair.sh "$(git rev-parse HEAD)" 450 --execute
```
