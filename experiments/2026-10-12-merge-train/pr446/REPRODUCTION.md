# PR446 후속 재현 안내 (원본 실행 기록 보존)

과거 README/PREPARATION의 예시는 당시 기록이다. v202–v208 비교는 각 실행에 기록된 원래 SHA에서만 재현한다. 현재 수정 소스는 `e2e-reviewed-runtime-v210`을 명시적으로 선택하며, 과거 성공/속도/정지 판정을 승계하지 않는다. 아래 명령은 준비용 예시이며 이번 merge train에서 VM·중계·실험을 실행하지 않았다.

Gemma + `--decider off`는 Azure loopback **18393**을 요구한다. 로컬 listen 18394를 사용할 때 중계 `--remote-port`, SSH reverse destination, receipt의 `remote_url`, identity 점검은 모두 18393이어야 한다. 포트가 이미 사용 중이면 기존 실행을 건드리지 않고 그 작업의 중계를 그대로 두어야 한다.

중계 인자는 다음처럼 주석과 분리한다. 예시 자체는 실행하지 않았다.

```bash
# 실제 실행은 별도 작업의 자원/종료 조건 아래에서만 수행한다.
python3 -m scripts.s4_proxy_relay \
  --output "$OUT/relay" --seconds 28800 --idempotent \
  --listen-port 18394 --remote-port 18393 \
  --driver-profile study_gemma4_31b_v1 --upstream openrouter_v1 \
  --gemma-state "$OUT/upstream"
# reverse destination: -R 127.0.0.1:18393:127.0.0.1:18394
# identity endpoint: http://127.0.0.1:18393/identity
```

현재 후보의 준비 JSON은 새 어댑터로 만든다. `--execute`는 포함하지 않는다. `SHA`, `OUT`, `RECEIPT`는 검토할 커밋과 작업별 고유 경로다.

```bash
python3 -m scripts.run_e2e_reviewed \
  --expected-source-sha "$SHA" --expected-workflow-id e2e-reviewed-runtime-v210 \
  --output "$OUT/raw" --relay-receipt "$RECEIPT" --seed 61001 \
  --driver-profile study_gemma4_31b_v1 --e2e-live \
  --event-driven-llm --compact-prompt --decider off \
  --setdown-only-when-relook on_v1 --exploration-progress frontier_progress_v1 \
  --pose-fix innovation --path-follow rpp_v1 --dev-light --stall-bundle \
  --mapping-budget case_cap_v1 --wall-cap-s 25200 \
  --stall-odometry rgb_vo_v2 --stall-recovery off --stall-noise off \
  --boundary-views candidate_views_v1 --b-marker-detect contrast_v1
```

관리자가 선택한 workflow ID는 실행기의 생성 bundle ID와 준비 출력 전에 일치해야 한다. 예전 v202를 선택하면서 현재 v204 구성을 생성하는 명령은 오류로 거부한다. v210의 full pulse/현재 GO 허가/입력 해시는 기존 번들과 구별해 기록한다.
