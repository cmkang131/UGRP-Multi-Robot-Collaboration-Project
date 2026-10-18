# e2ewarp R4 GPU 4조건 스모크 (2026-10-18, 정정판)

Lead 지시로 R4(peer_en) 이후 나머지 3조건(no_comm·leader_en·structured)을 **동일 동결 소스** `tip 718777118`(`/home/ugrp/ugrp-sim/src/e2ewarp-r4-git`, clean)로 gcp6에서 실행했다. 각 조건은 **별도 실행·pooling 없음**. 라벨: `attempt R4`, `queue.round=3`(tip argparse가 1–3만 허용), `mode smoke`, `nworld 2`, `map_keyframe_admission=elapsed_sim_v1`.

> **정정 이력(2026-10-18T20:05Z, 독립 검증자 중간 보고 반영)**
> 1. structured 클라이언트 타임아웃의 원인 설명을 정정: "relay journal 미도달/터널 단절"은 **철회**. 실제로는 relay journal에 status 200으로 존재하며, 상류 429→502(180.52 s)→200 재시도 때문에 클라이언트가 180 s에서 TimeoutError를 낸 것이다. (이전 초안은 relay가 마지막 줄을 쓰기 전에 journal을 읽은 race였다.)
> 2. wall 기준을 **두 기준 병기**: `result.json` wall_s와 `run-metrics.json` wall_s. 아래 표에 두 열을 모두 적고, 기존 표(수정 전)는 `result.json` 기준이었음을 명시한다.

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
relay: Mac loopback(127.0.0.1:18626) ↔ gcp6 역터널(127.0.0.1:18627), OpenRouter 키는 Mac Keychain에만. 이번 배치 relay journal: `outputs/e2ewarp-relay-r4b-193234` (요청 SHA·call ID·상류 attempts 원본 보존, 요약 `relay-summary-r4b.json`; 54행).

## 4조건 결과 (모두 `status=cap_end`, `mode=smoke`, sim 30.0, nworld 2, source `718777118…`, runtime applied `elapsed_sim_v1`(**간격 10틱**=1.0 s))

|조건|self-map funnel (RGB→measured→keyframes)|LLM|`result.json` wall_s|wall/SIM|wall/(SIM×world)|`run-metrics.json` wall_s|wall/(SIM×world)|cache|
|---|---|---|---|---|---|---|---|---|
|peer_en (R4)|1806→48→**48**|18/18 (200)|374.510|12.4837|**6.2418**|363.643|**6.0607**|23.68%|
|no_comm|1806→48→**48**|18/18 (200)|358.709|11.9570|**5.9785**|346.017|**5.7670**|20.58%|
|leader_en|1806→**128**→**54**|18/18 (200)|380.873|12.6958|**6.3479**|370.598|**6.1766**|37.61%|
|structured|1806→**46**→**46**|17/18 accepted|587.606|19.5869|**9.7934**|577.326|**9.6221**|21.57%|

- **기존(수정 전) 표의 wall·wall/SIM·wall/(SIM×world)는 `result.json` 기준**이다. `run-metrics.json`은 managed record가 남기는 동일 run 계측이며, smoke(cap_end=first30)에서는 first30 wall과 같다. (두 기준 모두 위 표에 병기)
- **keyframe admission은 4조건 모두 >0**: peer_en/no_comm 48/48(qualified 전부 삽입), leader_en 128 measured 중 54 삽입(74는 `keyframe_interval_wait` — elapsed 1 s cadence가 정상 throttle), structured 46/46. R3(`off`, 고정 클럭)의 0과 대비되나 **R3와 합산 금지**(소스·설정 다름).
- 공통 status 분포(peer_en/no_comm): bootstrap 6, unknown_servo_change 90, **unknown_commanded_camera_settling 1662**, measured 48. rejection 잔존: camera settling 1662/1806(92.0%), `null` 48. leader_en은 measured 128로 servo/settling 거부가 85/1587로 감소. structured: `rejection_distribution={"llm_http_0":1}`, measured 46.

## LLM (조건별 클라이언트 ledger + relay journal)

|조건|prompt|캐시|cache ratio|cost(클라이언트 ledger)|응답 중앙|client 429|relay upstream attempts|
|---|---|---|---|---|---|---|---|
|peer_en|78,120|18,496|23.68%|$0.007898|1.357 s|0|200×18|
|no_comm|78,045|16,064|20.58%|$0.007890|1.648 s|0|200×18|
|leader_en|78,623|29,568|37.61%|$0.007947|1.409 s|0|200×18|
|structured|73,303|15,808|21.57%|$0.007411|1.495 s|0|200×18, 429×2, 502×1 (21 attempts)|

### structured 타임아웃 정정 (핵심)

- 대상 call: `e2ewarp-r4-structured:w0:r2:3` (world 0/r2, sim 20.0), request_sha256 `6b63b09d7694a8be22d0bf756fe57fc553ecd55655b9b693ef192c7742b59383`, image_sha256 `9d1122b203b5a33f9219a8b2eac1a96c3defcc90ecfc1f878a934c5933a4a39f`.
- **relay journal 최종 상태 = 200** (18번째 structured 줄, 응답 파일 mtime 2026-10-18 19:56:06 KST): attempts ①429(0.31 s) → ②502(180.52 s) → ③200(0.87 s), latency 183.71 s, retries 2. journal은 클라이언트 타임아웃을 표시하지 않는다.
- 클라이언트 쪽은 **status=0, connected=false, response_wall 180.10 s TimeoutError**로 기록하고 run은 그 뒤 종료(10:55:16Z). actor는 hold 후 cap_end.
- 원인: **상류 429/502 재시도 체인으로 클라이언트 180 s 타임아웃**. 이전 초안의 "relay journal 미도달 → 터널/loopback 단절" 판정은 **철회**한다(초기 보고가 relay의 마지막 줄 기록과 경합한 race).
- 비용 표기 주의: 클라이언트 ledger cost `$0.007411`은 클라이언트가 수신한 17호출 기준이며(타임아웃 호출 usage `{}`), 타임아웃 호출의 상류 사용량(prompt 4,777·completion 14·cost $0.00048246)은 **relay journal에만** 기록되어 있다.
- 같은 structured 실행의 다른 재시도: `e2ewarp-r4-structured:w0:r1:3` = 429(0.49 s)→200(2.93 s).
- 이 타임아웃으로 wall이 180 s 늘어 structured의 wall/SIM이 19.59(result 기준)/9.62(run-metrics 기준)로 커졌다.

## 라벨·검증 범위

- 모든 조건 `E2E_success=false`, `research_result=false`, `student_execution=false`, `dependency_status="waiting for selected ACT / loaded FK / mapbuild8 own+static map correction / release API"` — **smoke이며 성공/학생 실행 주장 없음**.
- 4조건은 동일 소스·설정의 조건별 별도 실행이며 서로 pooling하지 않는다. R3(peer_ko, policy off, source e0e12448)와도 pooling 금지.
- 원본: VM `/home/ugrp/ugrp-sim/runs/e2ewarp-r4-{no_comm,leader_en,structured}(-admission/-managed)` + R4 peer_en `/home/ugrp/ugrp-sim/runs/e2ewarp-r4-run`. SHA: **VM run dir의 러너 원본 manifest는 `sha256.json`**(이 디렉토리 요약 `raw-sha256.json`과 이름이 다름, 아래 8절), 조건 요약 `condition-summary.json`(두 wall 기준·정정 이력 포함), relay `relay-summary-r4b.json`.
- 조건별 소형 원본 JSON은 이 디렉토리에 복사, 대용량 `localization.json`(2.1 MB)·review-rgb는 VM 원본 경로·SHA만 기록.

## 8. 문서 정정·한계 (독립 검증자 최종 판정, 2026-10-18T20:30Z)

추가 GPU 실행 없음. 문서·기록에만 반영한 3건:

1. **run dir의 raw SHA manifest 이름은 `sha256.json`** — VM run dir(`/home/ugrp/ugrp-sim/runs/e2ewarp-r4-<c>/`)에는 `raw-sha256.json`이 존재하지 않고, 러너가 raw 파일 SHA를 기록하는 파일은 **`sha256.json`**이다. `4cond/raw-sha256.json`은 VM 원본 파일 SHA를 인용해 정리한 **실험 디렉토리 요약**이며 run dir 파일이 아니다. 러너 `sha256.json`의 사본은 조건별 `4cond/<condition>/raw-run-sha256.json`으로 보존(이름 혼동 방지).
2. **queue.json `rejection_table` cross-ref(의도된 prior 연결)** — 3조건(`no_comm`·`leader_en`·`structured`)의 admission/run `queue.json` 모두 `rejection_table=/home/ugrp/ugrp-sim/runs/e2ewarp-r4-run/rejection_table.json`(R4 peer_en run)을 가리킨다. 이는 4조건을 **R4 peer_en funnel 뒤에 사슬로 연결**하기 위한 의도된 prior 경로이며 오류·우회가 아니다. 따라서 각 조건의 funnel은 조건별 독립 baseline이 아니라 R4 prior가 붙은 라벨(`attempt R4`) 실행이다.
3. **structured `rejection_table.json` 원거부 원장 누락** — stages는 `world_attempted 2/0`, `first30_complete 2/0`, **`actual_transport cumulative_pass_n=0·rejected_n=2`**인데, `reasons`에는 `llm_http_0` 1건(world 0/r2, sim 20.0)만 있고 **dependency 거부 2건(no_comm/leader_en에 있는 `marked_smoke_dependency_wait` 항목)이 누락**되어 있다. 수치 조작이 아니라 **원본 거부 원장의 기록 누락**이며, 후속 분석/집계 시 structured의 rejection 분포는 1건만 있는 것으로 오인하지 말 것.
   - 참고(원본 값): no_comm/leader_en reasons = `dependency/ marked_smoke_dependency_wait count 2`; structured reasons = `llm/ llm_http_0 1건`(dependency 항목 없음).
