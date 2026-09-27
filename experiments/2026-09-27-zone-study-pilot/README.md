# 2026-09-27 구역 대화 연구 실제 LLM 어댑터 파일럿 (첫 호출만, 물리 없음)

PR #194(`kiro/zone-study-core`)의 연구 어댑터로 실제 모델을 부른 첫 파일럿 기록이다. 호출은 17회(preflight 5 + cohort 12)였다. v63 호출 16/16은 정상 채택(상류 미검증)이고, v62 preflight-01의 1회는 JSON 코드 펜스 때문에 거절됐다. 과금 대조는 17/17 complete이며 증거 수준은 `proxy_log_exclusive_window`다. **물리 실행은 0회다.** 행동은 채택된 고수준 명령일 뿐 배송 성공이 아니다. Refs #222 #194.

## 실행 식별

| 항목 | 값 |
|---|---|
| 실행 소스 | `c684e6aaef6dc7ee8cd62ce9e18e4034f78146f6`(preflight-02-v63, cohort-01-v63). preflight-01만 `1adfeff01884b308352918a4488c31258adaf478` |
| 실행 번들 | `rgb-standard-dispatch-v63` (sha256 `ef4fe391…aa01`). preflight-01은 v62 `6601192a…7b69`. 둘 다 `experimental_unqualified`, weld OFF, 물리 미실행 |
| runner / 스키마 | `ugrp.zone_study_adapter_pilot.v2`, 입력 `stored_wrist_rgb_and_static_map_no_physics`, 프롬프트 `ugrp.zone_study_prompts_ko.v2`, SIM 비용 `zone_sim_cost.v1` |
| 시나리오 | `s1_normal_mixed`, seed 11, 주문 6건(order-1 cyan×2→A … order-5 long_beam 2대→A). leader_ko의 leader는 r3(seed 순환) |
| 요청 설정 | `gemini-3.8-flash`, temperature 0.0, reasoning_effort none, max_tokens 1400, timeout 180 s |
| 실효 설정 | `gemini-3.8-flash-low`, thinking LOW, 출력(추론 포함) 상한 8192, temperature 0.0. 프록시가 매핑한 값 |
| 프록시 | `~/.local/bin/gemini_subscription_proxy.py` sha256 `7d4c4e8c2addf9e0dc159de6ba0f4ec4374f876d915a6bc0752d3fd18db3e556`, PID 1407(2026-09-22 13:03:27 시작, listener·소스 mtime 확인), 127.0.0.1:8391. 내부 429 재시도 있음. POST당 상류 시도 상한 2 |
| 예산 | pilot_id `cbb840c2…f3fe`, 상한 600 attempts / 5,000,000 tokens, 무환불 2-attempt 예약(option B) |
| 부하 평균(1/5/15분) | preflight-01 7.10/7.51/10.67 · preflight-02-v63 15.75/13.92/11.57 · cohort-01-v63 7.41/11.89/11.04 (`*.load.txt`, 시작 직전 `uptime`) |

## 실행 순서 (실패 포함)

| run | 시각(KST) | 결과 |
|---|---|---|
| init-01 · dry-01 | — | 예산 DB를 만들었다. dry run은 네트워크 호출 0회로 4조건 계획만 확인했다 |
| **preflight-01** (v62) | 12:07 | POST 1회, **거절**: `study_reply_incomplete_or_non_json`. 응답이 ```` ```json ```` 펜스로 감싸져 있었다. 종료 코드 2. 예약 2 attempts / 235,408 tokens |
| review-v63-01 | — | 이관 전 대조: unresolved |
| migrate-v63-01 | 13:28:06 | 펜스 1개 허용 수정(`3251f482`) 뒤 v62→v63 소스 이관(revision 1). 기존 전송 1행을 보존했고 예약 합계는 바뀌지 않았다 |
| log-evidence/reconcile-v63-01 | — | preflight-01 대조 complete |
| **preflight-02-v63** | 13:28:20–13:28:42 | 4조건 × r1 1회: **4/4 채택**, 펜스 제거 4/4. 종료 코드 2(대조 미완료 상태로 끝나 관리 기록은 `process_failed`) |
| log-evidence/reconcile-v63-02 → 03 | — | 02는 call-0001-r1의 로그 증거 누락으로 incomplete, 03은 complete. 코호트 관문 통과 |
| **cohort-01-v63** | 13:29:51–13:31:11 | 4조건 × r1/r2/r3 첫 호출: **12/12 채택**, 펜스 제거 12/12. 종료 코드 2(같은 이유) |
| log-evidence/reconcile-v63-04 → 05 | — | 04는 call-0003-r3 증거 누락으로 incomplete, 05는 **17/17 complete**(`proxy_log_exclusive_window`, 상류 시도 17, retry 줄 0) |

## 호출별 결과

토큰은 프록시 응답의 provider `total_tokens`다. 응답 s는 전송 시작부터 응답 수신까지의 wall 시간이며 SIM 비용에 쓰지 않는다. preflight-01 v62 장부에는 이 시각이 없다. SIM 해제는 결정론적 비용 모델로 계산한 행동 해제 시각이다. 행동은 모두 `claim_order`다.

| run | 조건 | 로봇 | 역할 | 토큰 | 응답 s | SIM 해제 s | 펜스 제거 | 채택 | 행동 |
|---|---|---|---|---:|---:|---:|---|---|---|
| preflight-01 | no_comm | r1 | peer | 10,622 | — | 3.6 | 아니오 | **거절** | — |
| preflight-02-v63 | no_comm | r1 | peer | 10,594 | 3.846 | 4.1 | 예 | 예 | order-1 west A |
| preflight-02-v63 | peer_ko | r1 | peer | 10,977 | 3.634 | 5.4 | 예 | 예 | order-1 west A |
| preflight-02-v63 | leader_ko | r1 | follower | 10,871 | 2.918 | 5.4 | 예 | 예 | order-1 west A |
| preflight-02-v63 | structured | r1 | peer | 10,871 | 4.491 | 6.6 | 예 | 예 | order-1 west A |
| cohort-01-v63 | no_comm | r1 | peer | 10,673 | 4.293 | 4.1 | 예 | 예 | order-1 west A |
| cohort-01-v63 | no_comm | r2 | peer | 10,595 | 5.450 | 4.1 | 예 | 예 | order-1 west A |
| cohort-01-v63 | no_comm | r3 | peer | 10,512 | 4.537 | 4.1 | 예 | 예 | order-1 west A |
| cohort-01-v63 | peer_ko | r1 | peer | 10,873 | 3.563 | 5.4 | 예 | 예 | order-1 west A |
| cohort-01-v63 | peer_ko | r2 | peer | 10,645 | 7.066 | 5.4 | 예 | 예 | order-1 west A |
| cohort-01-v63 | peer_ko | r3 | peer | 10,642 | 3.641 | 5.4 | 예 | 예 | order-1 west A |
| cohort-01-v63 | leader_ko | r1 | follower | 10,678 | 3.645 | 5.4 | 예 | 예 | order-1 west A |
| cohort-01-v63 | leader_ko | r2 | follower | 10,662 | 3.906 | 5.3 | 예 | 예 | order-1 west A |
| cohort-01-v63 | leader_ko | r3 | leader | 10,949 | 3.856 | 6.0 | 예 | 예 | order-1 west A |
| cohort-01-v63 | structured | r1 | peer | 11,823 | 5.638 | 6.5 | 예 | 예 | order-1 west A |
| cohort-01-v63 | structured | r2 | peer | 10,852 | 3.414 | 6.6 | 예 | 예 | order-1 west A |
| cohort-01-v63 | structured | r3 | peer | 12,168 | 7.459 | 6.5 | 예 | 예 | order-1 west A |

run별 토큰 합계는 preflight-01 10,622, preflight-02-v63 43,313, cohort-01-v63 131,072, 전체 **185,007**이다(prompt 177,917 + completion 2,747, 나머지는 프록시가 보고한 추론분). 기계 판독용 전체 행은 [`calls.json`](calls.json)에 있다.

## 한국어·정형 메시지 원문

| run | 조건 | 보낸 로봇 → 받는 로봇 | 생성/전달 SIM s | 본문 |
|---|---|---|---|---|
| preflight-02-v63 | peer_ko | r1 → r2, r3 | 5.4 / 5.5 | 현재 cyan 물건을 확인하여 order-1을 맡고 destination_zone A로 배송을 진행하겠습니다. |
| preflight-02-v63 | leader_ko | r1 → r3 | 5.4 / 5.5 | 현재 위치에서 cyan 물품을 확인하여 order-1(구역 A) 작업을 진행하겠습니다. |
| preflight-02-v63 | structured | r1 → r2, r3 | 6.6 / 6.7 | `{"act":"propose","confidence":"high","item":"order-1","location_ref":"P1-1","observed_at_sim_s":0.0,"passage":null,"reply_to":null,"role":"west","state":"present","zone":"A"}` |
| cohort-01-v63 | peer_ko | r1 → r2, r3 | 5.4 / 5.5 | cyan 물품을 확인하여 order-1 작업을 맡고 destination_zone A로 이동합니다. |
| cohort-01-v63 | peer_ko | r2 → r1, r3 | 5.4 / 5.5 | 현재 cyan 물품을 확인하여 order-1(A 구역)을 맡겠습니다. |
| cohort-01-v63 | peer_ko | r3 → r1, r2 | 5.4 / 5.5 | 현재 cyan 물품을 확인하여 order-1(목적지 A)을 담당하겠습니다. |
| cohort-01-v63 | leader_ko | r1 → r3 | 5.4 / 5.5 | 현재 cyan 상자를 확인하여 order-1(A 구역 배송, role west) 작업을 시작합니다. |
| cohort-01-v63 | leader_ko | r2 → r3 | 5.3 / 5.4 | 현재 cyan 물품을 확인하여 order-1을 맡고 구역 A로 운반하겠습니다. |
| cohort-01-v63 | leader_ko | r3(leader) → r1, r2 | 6.0 / 6.1 | r3는 order-1(cyan, 목적지 A)을 담당합니다. r1은 order-2(red, 목적지 B), r2는 order-3(can, 목적지 C) 확인 후 진행해 주세요. |
| cohort-01-v63 | structured | r1 → r2, r3 | 6.5 / 6.6 | `{"act":"inform","confidence":"high","item":null,"location_ref":"P1-1","observed_at_sim_s":0.0,"passage":null,"reply_to":null,"role":"west","state":"present","zone":"A"}` |
| cohort-01-v63 | structured | r2 → r1, r3 | 6.6 / 6.7 | `{"act":"inform","confidence":"high","item":"cyan","location_ref":"P1-1","observed_at_sim_s":0.0,"passage":null,"reply_to":null,"role":"west","state":"present","zone":"A"}` |
| cohort-01-v63 | structured | r3 → r1, r2 | 6.5 / 6.6 | `{"act":"propose","confidence":"high","item":null,"location_ref":"P1-1","observed_at_sim_s":0.0,"passage":null,"reply_to":null,"role":"west","state":null,"zone":"A"}` |

12건 모두 delivered, 거절 0건이다. leader_ko의 follower끼리 보낸 메시지는 0건이다. no_comm은 송수신 0건이다. 원문은 [`messages.json`](messages.json)에 있다.

## 예약과 실제 사용량 불일치

- 무환불 예약은 POST마다 상류 2회 × (텍스트 상한 + 이미지 65,536 + 출력 8,192)를 차감한다. 17 POST에서 **34 attempts / 4,085,674 tokens**(호출당 235,408~246,120)가 예약됐다. raw 대조 결과 실제 상류 시도는 17회, provider total은 **185,007**로 예약의 약 1/22이다.
- 브리프의 "약 172,839"는 raw에서 재현하지 못했다. v63 16회만 합하면 174,385, prompt+completion은 180,664다. 이 기록은 raw 합계 185,007을 쓴다.
- 남은 토큰 한도는 914,326이다. 지금 규칙이면 호출을 약 3회만 더 할 수 있어서 본 실험이 불가능하다. 정산 방식 변경(complete·exact 대조 호출만 실제 사용량으로 settle, 감사 행 보존, 상한 유지)은 #222의 코디네이터 결정이다. 이 PR은 `budget.sqlite`를 읽기만 했고 정산하지 않았다(`reconcile-v63-05`의 `budget_settlements: []`).

## 연구 관찰 (첫 호출만)

- 12/12 첫 호출과 preflight 4/4가 모두 **order-1(cyan, west, A)**을 claim했다. 조건마다 3대가 같은 주문을 겹쳐 가져갔다.
- leader_ko에서는 leader r3가 SIM 6.0 s에 "r1은 order-2, r2는 order-3"으로 분배했다. 하지만 동시에 호출된 follower r1·r2는 5.4/5.3 s에 이미 order-1을 claim했고, 지시는 6.1 s에 도착했다. 스케줄러는 `trigger_on_message=false`, 재질문 999 s로 설정돼 두 번째 호출이 없었다. 그래서 충돌이 해소되지 않은 채 끝났다(`stop_reason=quiet`). **대화의 효과는 메시지를 받은 뒤 다시 결정하는 다회 루프에서만 드러날 수 있다. 본 실험에는 다회 결정이 필요하다.**
- 저장 손목 RGB는 로봇별로 한 장씩이다. r1 `0245`, r2 `0250`, r3 `0266`으로, 모두 `tests/fixtures/markerless_box/blue_floor_release/`에서 왔다. 확인한 `0245`는 파란 바닥 위의 cyan 상자 한 개를 보여 준다. 세 로봇이 모두 cyan을 "확인"했다고 말한 이유가 이 입력일 수 있다. 입력 영상이 s1 장면의 실제 시점이 아니라서 동시 호출 효과와 분리되지 않는다. `0250`·`0266`은 육안으로 보지 않았다.
- SIM 해제 시각(첫 행동 기준)은 no_comm 4.1, peer_ko 5.4, leader_ko 6.0, structured 6.6 s다. 발화 출력 토큰이 SIM 사고·발화 비용에 들어간 결과다. 첫 호출만 본 값이라 임무 효율 비교가 아니다.

## 한계

- **상류 finish reason 미검증:** 채택 기준은 프록시 `stop` + 연구 응답 스키마 통과다. 프록시는 MAX_TOKENS만 `length`로, SAFETY 등은 `stop`으로 매핑한다. 완전한 JSON을 가진 상류 실패는 감지할 수 없다.
- **로그 창 증거:** 과금 대조는 프록시 로그의 배타적 시간 창(`proxy_log_exclusive_window`)에 근거한다. 요청 ID 대조보다 약하고, 최종 응답의 사용량만 본다.
- **물리 실행 없음:** 행동은 채택된 고수준 명령이다. 이동·파지·배송 성공, 조건 우열, 통신 효과를 주장하지 않는다.
- **첫 호출만:** seed 1개, 시나리오 1개, 로봇당 1회 호출. 입력 RGB는 저장 fixture다.
- preflight-01은 v62 소스라서 v63 코호트와 합산하지 않는다. TensorBoard에서도 별도 run이다.

## TensorBoard

스냅샷은 `/Users/changmin/projects/ugrp/outputs/tensorboard/0927-zone-study-pilot/`이다. run은 9개(`<파일럿 run>/<condition>`)이고 scalar는 115개다. [`build_records.py`](build_records.py)가 기존 `scripts/zone_study_report.write_events`로 만들었으며, 이 함수는 기존 run 덮어쓰기를 거부한다.

- 고정 카드: `evaluation/accepted_calls`(정상 채택 수, 배송 성공 아님), `result/release_sim_s`, `result/commands`, `result/model_calls`, `result/model_response_s_mean`, `result/tokens_total`, `result/reserved_tokens`. 응답 시각이 없는 preflight-01에는 응답 s scalar를 만들지 않았다(0으로 채우지 않음).
- HParams: `condition`, `stage`, `bundle`, `model_effective`.
- 검증: EventAccumulator로 115/115 일치를 확인했다. 기존 공유 서버(PID 9291/9293, `--logdir outputs/tensorboard`, 재시작하지 않음)의 `/data/plugin/scalars/scalars`에서도 115/115 일치했다. `session_groups`는 9개 세션과 4개 HParams를 반환했다. 브라우저에서 열어 카드 값을 눈으로 확인하지는 않았다. 공유 logdir의 병합 HParams 표는 다른 스냅샷의 열을 보여 주므로 Time Series를 쓴다.
- 링크: <http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation%2Faccepted_calls%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Frelease_sim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_response_s_mean%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Ftokens_total%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Freserved_tokens%22%7D%5D&smoothing=0&runFilter=%5E0927-zone-study-pilot%2F#timeseries>

재생성(원본 읽기 전용, 기존 스냅샷이 있으면 거부): `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python experiments/2026-09-27-zone-study-pilot/build_records.py --tb --verify`

## 원본 위치와 해시

raw는 로컬 전용이며 원격 백업이 아니다. 위치는 `/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10/`이다. 매니페스트·trial·대조·telemetry·부하 기록·`budget.sqlite` 등 28개 파일의 SHA-256은 [`sha256.json`](sha256.json)에 있다. 주요 값:

| 파일 | SHA-256 |
|---|---|
| `preflight-01/manifest.json` | `c4a90d960e4bf333b99ee369136e943bcc5f919f203edf244fd1c335ba028f86` |
| `preflight-02-v63/manifest.json` | `91637a7c13a016cc67ff5a170fd769f3ff9e8c1061bc63f98be8a7cce3b344f5` |
| `cohort-01-v63/manifest.json` | `a003faa1013a7e556293cb75cc30848d364bbe450bc3105690723dd69ed99e64` |
| `reconcile-v63-05/reconciliation.json` | `d265db4a6747159ed300b7bbd19cf4a4902fbc11d1a41c1494aa892b5bbdee3e` |
| `log-evidence-v63-05/telemetry.jsonl` | `e298a4bbe3c0ce949b59e77a4110411c5cc0d6dcf5d8ceef2519dbc3c2b9bb41` |
| `migrate-v63-01/source-migration.json` | `397bb81dce354de1c65f2c4d535854a55039ed1848ba387fd2e6e814a3d9686c` |
| `budget.sqlite` (읽기 전용 `mode=ro`로만 열었다) | `cc23aa281f44b7989627dd2059ea00b868b43bfec2d59c12cda0cf9042145158` |

예산 상태 해시(`state_sha256`)는 대조 05 기준 `64a05562984e6891c9b1d8aca3e5ebba52fee0ffe89cf291f3c81deb1ccfc2c7`이다. 파일 해시는 2026-09-27 13:50 KST 기록 시점의 값이다. 이후 #222의 정산(`--settle-reconciled`, `kiro/zone-study-core` `1e8c5dda`)을 적용하면 `budget.sqlite` 해시가 바뀐다. 소스 이관 기록은 `e32686a490860cd1a304dc09ec6cdf4cb7f58e24a7569939a75082e9cf2c0a82`, v63 identity는 `af4a978bbbf793a70785fced6da10c2cb81d7469d1ca2ead092c52c4b4d4b142`다.

## 참고 자료

- 논문: 이 기록 작업에서 새로 참고한 논문은 없다(연구 설계 문헌은 PR #194·설계 문서 참조).
- OSS: TensorBoard 2.21.0(Apache-2.0). `EventAccumulator`로 재적재를 검증했고, event protobuf는 기존 `write_events`가 사용한다. 새 의존성은 없다.
- 내부 모듈·PR:
  - `scripts/zone_study_report.py`의 `write_events`·`_run_paths`를 재사용했다. run 경로 검사와 덮어쓰기 거부가 여기에 있다.
  - raw는 PR #194의 `scripts/run_zone_study_pilot.py`, `harness/zone_pilot_budget.py`, `harness/zone_pilot_reconcile.py`, `harness/zone_send_ledger.py`가 만들었다. 이 PR은 이 파일들을 수정하지 않았다.
- 채택하지 않은 대안:
  - `scripts/export_tensorboard.py`: 파일럿 `trial.json` 형식을 지원하지 않아 파생 뷰가 따로 필요하다.
  - `zone_study_report.py --tb-events` 전체 경로: 시행 단위 PAR 요약만 내고, 호출별 채택·예약 지표가 없다.
- 문서: `docs/tensorboard.md`, `AGENTS.md`, #222 코디네이터 결정 코멘트(정산 방식 변경, 종료 정책).
