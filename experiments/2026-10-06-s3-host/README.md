# S3: 최종 v3 3대 호스트, LLM 없음

## 실행 전 고정 계획 (2026-10-06)

- 기준 main: `da92d91dbf4af193d3aa3559de9efe55653ec5c0` (#392 이후).
- 계획: `../2026-10-05-scenario-e2e-gap/README.md` 6.1–6.4, S3/K2.
- `dev_s1lite`: r3 cyan → A, r1/front + r2/rear 동서 빔 → B. 역할 고정, 사건 없음, LLM/HTTP 호출 0.
- K11(임의 짝/r3 짝)은 후속 s1 전체 범위이며 이번에 졸업으로 표시하지 않는다.
- 로봇 입력은 자기 RGB·공개 정적 지도·자기 발행 명령. 기존 짝 실행기의 고정 enum 동기화는 재사용한다. 평가 정답은 별도 출력으로만 보존한다.
- S1 `scenario_scene`/`ScenarioFinalV3Scene`, #391 v106 단독 Runtime, 기존 highpose 짝 Runtime/벽 경계 OpenCV+PF, IntegratedTrial 및 심판을 재사용한다. 기존 경로 기본값은 수정하지 않는다.
- 예약: `zone-s3-host-v107`, workflow `3.14.0`. origin/main 및 열린 #393/#385/#339 전체 ref의 RUNNABLE_ID·별도 bundle/workflow 상수를 확인했다. 최고 v106/3.13.0.
- DEV seed는 scenario에 이미 선언된 **601, 602, 603**, 순서대로 1회씩. 재시도·튜닝 자료를 새 확증 자료로 세지 않는다.
- 후보 커밋/push 뒤 `launch_dev.zsh <전체 SHA> <기본 checkout outputs 아래 새 절대 경로> --release-s3-simulation`으로 직렬 실행하도록 준비한다. **이 작업에서는 실행 금지**: #393의 잠금이 비어도 시작하지 않는다.
- 졸업 기준: 세 seed 모두 두 주문이 심판의 배달 판정까지 완주. 명령 종료와 심판 배달을 구분한다. 같은 원인 두 번 실패하면 후속 seed 실행을 멈추고 고전/최근 공개 방법과 출처를 조사한다.
- 1800 SIM초/seed, 유한 wall 상한, 독점 잠금, nice 0, ENOSPC=HOST_ERROR, raw는 기본 checkout outputs에 보존한다. 완료 실험이 생기면 실패 포함 TensorBoard 후속 snapshot에 등록한다.
- PR은 DRAFT 유지, 병합 금지. 다른 worktree·PR·프로세스 변경 없음.

## 초기 상태

구현 및 비물리 시험 준비 중. DEV 시뮬레이션·MuJoCo compile/reset/render·모델 호출은 0회다. S2 졸업(#393)과 S3 물리 인수는 아직 확인하지 않았다.
worktree 생성은 기존 Codex 15개로 상한 8개에 걸려, 사용자의 새 전용 worktree 생성/다른 worktree 보존 요청을 이유로 관리 스크립트의 `--allow-over-cap --reason`에 기록했다.
