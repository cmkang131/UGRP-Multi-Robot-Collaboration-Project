# e2ewarp R4 GPU 4조건 스모크 (2026-10-18)

Lead 지시로 R4(peer_en) 이후 나머지 3조건(no_comm·leader_en·structured)을 **동일 동결 소스** `tip 718777118`(`/home/ugrp/ugrp-sim/src/e2ewarp-r4-git`, clean)로 gcp6에서 실행했다. 각 조건은 **별도 실행·pooling 없음**. 라벨: `attempt R4`, `queue.round=3`(tip argparse가 1–3만 허용), `mode smoke`, `nworld 2`, `map_keyframe_admission=elapsed_sim_v1`.

## 실행 패턴 (조건별 새 경로, 덮어쓰기 없음)

```
cd /home/ugrp/ugrp-sim/src/e2ewarp-r4-git
python -m scripts.run_e2e_warp --prepare --round 3 --nworld 2 --condition <c> \
  --e2e-warp-batch on_v1 --map-keyframe-admission elapsed_sim_v1 \
  --rejection-table /home/ugrp/ugrp-sim/runs/e2ewarp-r4-run/rejection_table.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-r4-<c>-admission
python -m scripts.sim_cli workflow run e2e-warp-batch-v446 \
  --record /home/ugrp/ugrp-sim/runs/e2ewarp-r4-<c>-managed -- \
  --e2e-warp-batch on_v1 --mode smoke --execute --round 3 --nworld 2 --condition <c> \
  --map-keyframe-admission elapsed_sim_v1 \
  --expected-source-sha 718777118be41991156b047faff78621969101bb \
  --queue /home/ugrp/ugrp-sim/runs/e2ewarp-r4-<c>-admission/queue.json \
  --host-receipt /home/ugrp/ugrp-sim/runs/e2ewarp-r4-host-receipt.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-r4-<c> \
  --relay-url http://127.0.0.1:18627/v1/chat/completions
```
relay: Mac loopback(127.0.0.1:18626) ↔ gcp6 역터널(127.0.0.1:18627), OpenRouter 키는 Mac Keychain에만. 이번 배치 relay journal: `outputs/e2ewarp-relay-r4b-193234`(요청 SHA·call ID·상류 attempts 원본 보존, 요약 `relay-summary-r4b.json`).

## 4조건 결과 (모두 `status=cap_end`, `mode=smoke`, source `718777118…`, `map_keyframe_admission=elapsed_sim_v1`)

|조건|self-map funnel (RGB→measured→keyframes)|LLM 호출|wall_s|wall/SIM|wall/(SIM×world)|cache|
|---|---|---|---|---|---|---|
|peer_en (R4)|1806→48→**48**|18/18 (200)|374.51|12.484|6.242|23.68%|
|no_comm|1806→48→**48**|18/18 (200)|358.71|11.957|5.978|20.58%|
|leader_en|1806→**128**→**54**|18/18 (200)|380.87|12.696|6.348|37.61%|
|structured|1806→**46**→**46**|17/18 accepted, 1 client timeout|587.61|19.587|9.793|21.57%|

- **keyframe admission은 4조건 모두 >0**: peer_en/no_comm 48/48(qualified 전부 삽입), leader_en 128 measured 중 54 삽입(74는 `keyframe_interval_wait` — elapsed 1 s cadence가 정상적으로 throttle), structured 46/46. R3(`off`, 고정 클럭)의 0과 대비되나 **R3와 합산 금지**(소스·설정 다름).
- 공통 status 분포(peer_en/no_comm): bootstrap 6, unknown_servo_change 90, **unknown_commanded_camera_settling 1662**, measured 48. rejection 잔존: camera settling 1662/1806(92.0%), `null` 48. leader_en은 measured 128로 servo/settling 거부가 85/1587로 감소.
- structured: `rejection_distribution={"llm_http_0":1}`, measured 46.

## LLM (조건별 원본 ledger·relay journal)

|조건|prompt|캐시|cache ratio|cost(ledger)|응답 중앙|429|
|---|---|---|---|---|---|
|peer_en|78,120|18,496|23.68%|$0.007898|1.357 s|client 0 / upstream 0|
|no_comm|78,045|16,064|20.58%|$0.007890|1.648 s|client 0 / upstream 0|
|leader_en|78,623|29,568|37.61%|$0.007947|1.409 s|client 0 / upstream 0|
|structured|73,303|15,808|21.57%|$0.007411|1.495 s|client 0 / **upstream 1**|

**structured 이상 1건(원인 기록):** call `e2ewarp-r4-structured:w0:r2:3`(world 0/r2, sim 20.0)가 **status=0, connected=false, response_wall 180.1 s**(client timeout)로 실패. request_sha256 `6b63b09d7694a8be22d0bf756fe57fc553ecd55655b9b693ef192c7742b59383`, image_sha256 `9d1122b203b5a33f9219a8b2eac1a96c3defcc90ecfc1f878a934c5933a4a39f` — **relay journal에 이 요청이 도달하지 않음**(요청 SHA 부재) → 터널/loopback 일시 단절로 판정. 같은 실행의 다른 구조화 호출은 정상. relay 저널에는 structured 17행(전부 200) + `e2ewarp-r4-structured:w0:r1:3` 1건에서 **upstream 429 후 재시도 성공**(attempts 2). 이 실패로 actor는 hold 후 cap_end(추가 wall 180 s → wall/SIM 19.6 상승).

## 라벨·검증 범위

- 모든 조건 `E2E_success=false`, `research_result=false`, `student_execution=false`, `dependency_status="waiting for selected ACT / loaded FK / mapbuild8 own+static map correction / release API"` — **smoke이며 성공/학생 실행 주장 없음**.
- 4조건은 동일 소스·설정의 조건별 별도 실행이며 서로 pooling하지 않는다. R3(peer_ko, policy off, source e0e12448)와도 pooling 금지.
- 원본: VM `/home/ugrp/ugrp-sim/runs/e2ewarp-r4-{no_comm,leader_en,structured}(-admission/-managed)` + R4 peer_en `/home/ugrp/ugrp-sim/runs/e2ewarp-r4-run`. SHA는 `raw-sha256.json`, 조건 요약은 `condition-summary.json`, relay는 `relay-summary-r4b.json`.
- 조건별 소형 원본 JSON은 이 디렉토리에 복사했고, 대용량 `localization.json`(2.1 MB)·review-rgb는 VM 원본 경로·SHA만 기록했다.
