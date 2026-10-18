# e2ewarp R4 — GPU 관문 (attempt R4, queue.round=3) 2026-10-18

Lead R4 실행 지시에 따른 GPU 재검증. **라벨 주의**: `attempt R4`는 작업 라벨이고, tip `718777118`의 `scripts/run_e2e_warp.py` argparse가 `--round` choices=(1,2,3)이라 **queue.round=3**으로 실행했다(코드 동결, 대신 source pin·`map_keyframe_admission=elapsed_sim_v1`·새 dir·R3 raw funnel 연결로 정체성 보존). R3와 **합산 금지**(소스·설정 다름).

## 정체성·스택

- source pin: `718777118be41991156b047faff78621969101bb` (origin/codex/e2ewarp tip, clean clone `/home/ugrp/ugrp-sim/src/e2ewarp-r4-git`)
- attempt R4 / queue.round=3 / mode smoke / nworld 2 / condition `peer_en` / seed 601 / sim_budget 30 SIM s
- `map_keyframe_admission=elapsed_sim_v1` (queue·result·runtime-applied 모두 동일)
- admission: `/home/ugrp/ugrp-sim/runs/e2ewarp-r4-admission` (queue sha `076e…` in artifacts/raw-sha256.json), prior raw funnel `--rejection-table /home/ugrp/ugrp-sim/runs/e2ewarp-r3/rejection_table.json`
- raw run: `/home/ugrp/ugrp-sim/runs/e2ewarp-r4-run` (20M), managed: `e2ewarp-r4-run-managed`
- 실패 attempt 원본 보존: `/home/ugrp/ugrp-sim/runs/e2ewarp-r4` + `e2ewarp-r4-managed` (admission 단계 `HOST_ERROR: OWN_LEASE_REQUIRED`; 이후 `/home/ugrp/ugrp-sim/leases/e2ewarp.json` 생성 후 재실행)

## 재현 명령

prepare:
```
python -m scripts.run_e2e_warp --prepare --round 3 --nworld 2 --condition peer_en \
  --e2e-warp-batch on_v1 --map-keyframe-admission elapsed_sim_v1 \
  --rejection-table /home/ugrp/ugrp-sim/runs/e2ewarp-r3/rejection_table.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-r4-admission
```
run:
```
python -m scripts.sim_cli workflow run e2e-warp-batch-v446 \
  --record /home/ugrp/ugrp-sim/runs/e2ewarp-r4-run-managed -- \
  --e2e-warp-batch on_v1 --mode smoke --execute --round 3 --nworld 2 --condition peer_en \
  --map-keyframe-admission elapsed_sim_v1 \
  --expected-source-sha 718777118be41991156b047faff78621969101bb \
  --queue /home/ugrp/ugrp-sim/runs/e2ewarp-r4-admission/queue.json \
  --host-receipt /home/ugrp/ugrp-sim/runs/e2ewarp-r4-host-receipt.json \
  --output /home/ugrp/ugrp-sim/runs/e2ewarp-r4-run \
  --relay-url http://127.0.0.1:18627/v1/chat/completions
```
relay: Mac loopback(127.0.0.1:18626) ↔ gcp6 역터널(127.0.0.1:18627), OpenRouter 키는 Mac Keychain에만.

## ① self-map funnel (핵심)

|단계|R4 (`elapsed_sim_v1`)|R3 (`off`)|
|---|---|---|
|own RGB frames|**1806**|1806|
|flow status measured|**48**|48|
|wall-contact qualified frames|**48**|48|
|**inserted keyframes**|**48 (관문 돌파, >0)**|**0**|

- flow status 분포(R4): bootstrap 6 · unknown_servo_change 90 · **unknown_commanded_camera_settling 1662** · measured 48.
- R4 policy: `keyframe_due(tick, prev, interval_ticks=round(1.0s*10), elapsed_sim_v1)` = `prev is None or tick-prev>=10` → qualified 48 프레임 전부 삽입(last_map_tick 갱신). R3 `off` = `tick % 10 == 0` 고정 클럭이라 qualified 프레임이 1 s 경계와 안 맞아 0.
- 주된 거부(원인): commanded camera settling `unknown_commanded_camera_settling` **1662/1806 (92.0%)**, servo change 90, bootstrap 6.

## ② queue/runtime-applied

- queue: `map_keyframe_admission=elapsed_sim_v1`
- result.json: `"map_keyframe_admission":"elapsed_sim_v1"`, `runtime-applied.json` 동일, per-frame `self_map.inserted`가 policy에 따라 48 true.

## ③ LLM (실제 호출·SHA·429)

- 모델: `google/gemma-4-31b-it` / provider CoreWeave / quant fp4 / fallbacks off (relay identity 고정).
- 호출: **18/18 status 200**, accepted 18, connected 18, provider attempt 1회씩, http_429 0 · upstream_429 0 · format_errors 0, image_calls 18.
- prompt 78,120 · cached 18,496 (23.68%) · total 78,372 · ledger cost $0.007898; response wall median 1.357 s (min 0.758 / max 3.038).
- request_sha256 18개 unique, image_sha256 15개 unique(18장). relay journal 원본: Mac `/Users/changmin/projects/ugrp/outputs/e2ewarp-relay-r4-190318` (ledger.jsonl 18행, responses 18개; 요약 `relay/relay-ledger-summary.json`).

## ④ wall / SIM

- full: wall 374.51 s / 30 SIM = **12.48 wall/SIM**, **6.24 wall/(SIM×world)**
- first30: wall 363.64 s = 12.12 wall/SIM, 6.06 wall/(SIM×world); batch_wall_per_sim_s 12.1214

## ⑤ 종료 상태·실패 원인

- status **cap_end** (smoke 30 SIM 예산 소진), `E2E_success=false`, `research_result=false` — **smoke는 성공/학생 실행을 주장하지 않는 설계**.
- dependency_status: waiting for selected ACT / loaded FK / mapbuild8 own+static map correction / release API (mission 경로 미완).
- self-map 병목: camera settling/qualification 거부 92% (servo 명령 직후 settle window). keyframe admission 자체는 R4에서 병목이 아니었음(qualified는 전부 삽입).

## 산출·검증 범위

- SHA manifest: `artifacts/raw-sha256.json` (raw 11개 파일 + R3 비교 + source pin). artifacts/로 원본 소형 JSON 복사, 대용량 `localization.json`(2.1MB)·review-rgb는 VM 원본 경로·SHA만 기록.
- no-pooling: 위 R3 열은 참고 비교일 뿐 합산하지 않는다(소스 e0e12448 vs 718777118, condition peer_ko vs peer_en, admission off vs elapsed_sim_v1).
- 검증 범위: gcp6 L4 1회 실행(attempt R4), smoke 30 SIM. 실패 attempt(OWN_LEASE_REQUIRED) 원본도 보존. GPU 재실행은 Lead 조율.
