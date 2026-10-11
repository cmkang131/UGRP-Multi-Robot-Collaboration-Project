# egomap71 — 자기 RGB 재확인·공분산 층화 (DEV, 기본 OFF)
기준 `4199f7e1`의 calib_traversed: 거짓귀환3/6·B오인1/6; 동일 체크포인트63001–63006 × off/on12회. 새 seed 확증·LLM·운반 E2E가 아니다.
토글은 독립 기본off: `rgb_reconfirmation=two_view_rgb_v1`, `covariance_inflation=nees_stratified_v1`; 본 비교는 둘을 함께 켜므로 단독 효과를 주장하지 않는다.
RGB는 B·통로정합·복귀 선언 전 다른 각도에서 영상 일치, 최대20초 순수 회전; 원본 home은 고정. [조사·차이](gate_references.md).
공분산은 과거 자기 명령×단계 proxy에 고정 배율; 온라인GT0·평균/입자 직접수정0. [문헌·오프라인 결과](COVARIANCE.md).
확보8run(2seed) 확인NEES χ²99.9초과 raw1747/5084→층화3/5084, pooled1/5084보다 나쁘다. 70c×4.154·41/1260 원자료 미발견·미재현.
관련22시험 통과(초기18통과/1fixture실패 수정 후 최종); Mac물리0. [사전계획](prereg.json): Azure구독88b7ee7f,3worker,90분실행+30분보관/종료,다른lease보존.
실행은 표준 `sim_cli workflow run egomap-reconfirmation-dev`; 기존 azctl/remote_run API로 live VM을 재사용하고 frozen Git object만 보낸다. [실행 조정기](code/launch_azure.py).
결과 원본은 Azure 영속디스크→검증ARM,Mac fetch-lite; 체크포인트 원본은 기존ARM,새입력복원목록은 실행에 기록한다. HOST_ERROR·분모를 summary.json에 모두 남긴다.
이 커밋 시점 신규12회는 미실행, DRAFT 유지. 후속 결과·TensorBoard·보관검증은 같은 기록에 추가한다.
