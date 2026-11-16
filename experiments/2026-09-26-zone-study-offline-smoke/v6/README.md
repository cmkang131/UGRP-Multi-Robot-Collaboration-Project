# v6 — Codex 7차 검토 수정(전송 장부) 뒤 재실행 (2026-09-27)

- **상태:** 완료. 30회 모두 통과했다(`results.json` `ok: true`). 디스크 재해시는 1871/1871, 비공개 절 역류 검사는 30/30이며 actor 격리도 통과했다.
- **실행 소스:** `9484173871ea9971784561e5ed759d5fbddc7e3a` (브랜치 `kiro/zone-study-core`, PR 194). 추적 파일 변경이 0개인 자기 worktree(`ugrp-wt/kiro-study-core`)에서 실행했다.
- **실행기:** `scripts/run_zone_study_offline_smoke.py` → `harness/zone_study_offline.py`. 보고서·TensorBoard 변환은 `scripts/zone_study_report.py`로 했다.
- **모델 호출·네트워크 요청·물리 실행·시뮬레이터 import는 모두 0회다.** fixture 응답은 `GeminiProxyCompleter`가 만든 요청 그대로 전송 장부를 지나 오프라인 `FixtureWire`에 닿는다. 에이전트 잠금은 잡지 않았다(물리·학습·wall 시간 비교 없음).
- **v1~v5는 그대로 둔다.** 이 폴더는 새 버전이다.
- **부하 평균:** 실행 직전 `49.69 50.77 55.13`, 실행기 시작 시(`environment.json`) `74.81 62.91 58.36`, 종료 뒤 `72.41 67.53 60.89`다. 공유 Mac(8코어)에 다른 작업 부하가 컸고, 같은 시각에 이 작업의 변이 검사도 돌았다. 지정 grep은 9개였다. 실제 시뮬레이션 프로세스는 다른 작업의 렌더링 2개뿐이라 상한(6) 아래에서 시작했다(`source.json` `machine_sim_cap`). 가짜 SIM 시계만 쓰므로 결과는 wall 시간의 영향을 받지 않는다.

## 왜 새 버전인가

7차 수정(`94841738`, [`../review-r7/`](../review-r7/README.md))은 청구 기준을 바꿨다. 스케줄러는 이제 어댑터의 신고 대신 전송 장부가 센 요청 수로 청구한다. 오프라인 루프도 실제 모델 경로와 같은 `ModelCallTransport` → `GeminiProxyCompleter` → `SendLedger`를 지나도록 바뀌었다. 그 결과 기록이 세 가지 달라졌다. 실행 번들 ID는 `zone_study_offline_v2`에서 `v3`로 바뀌었다. 호출 provenance의 `model_settings_sha256`은 null에서 `2334d86b…`가 됐다. trial record에는 `send_ledger` 절이 새로 붙었다. SIM 동작은 같지만 기록 바이트가 다르므로 v5를 덮어쓰지 않고 v6으로 남긴다.

## v5와의 대조 (`control_runs.json`)

| 조건 | 시행 | SIM trace 동일 | 요청 입력 동일 | 호출 v5 → v6 | 장부 전송 | 장부 = 호출 기록 |
|---|---:|---:|---:|---:|---:|---:|
| `no_comm` 무통신 | 6 | 6/6 | 6/6 | 411 → 411 | 411 | 6/6 |
| `peer_ko` 자유 한국어 | 6 | 6/6 | 6/6 | 447 → 447 | 447 | 6/6 |
| `leader_ko` 지휘 겸임 | 6 | 6/6 | 6/6 | 429 → 429 | 429 | 6/6 |
| `structured` 정형 | 6 | 6/6 | 6/6 | 447 → 447 | 447 | 6/6 |
| `reference_R` 참조 상한 | 6 | 6/6 | 6/6 | 137 → 137 | 137 | 6/6 |

- `smoke.json`은 v5와 **바이트 단위로 같다**(`d61b7e9b…`). 1871개 호출 기록은 provenance 세 필드(`code_sha`, `execution_bundle_id`, `model_settings_sha256`)만 다르다.
- 30/30 시행에서 다음 값이 모두 같다: 장부 전송 수, 호출 기록 `http_attempts` 합, 예산 사용, wire 수신 수. 막힌 요청, 신고 위반, 환불 호출은 모두 0이다. fixture 전송 계층은 신고를 틀리게 하지 않으므로 이 코호트에서 장부와 신고는 항상 일치한다. 반례 경로는 회귀 테스트가 덮는다(`../review-r7/`).
- 조건별 호출 수, 사고·발화 SIM 비용, 토큰, 종료 이유는 v5와 같다. 수치는 [v5 README](../v5/README.md)의 표를 따른다. **이 수치는 통신 효과가 아니다.** fixture 응답 규칙, 청구 규칙, 재질문 규칙이 만든 배선 수치다.

## 보고서 (`report_summary.md`)

`zone_study_report.py`로 보고서를 만들고 TensorBoard로 변환했다. 입력 경계 판정은 clean 24건, unverified 6건이다. unverified 6건은 설계상 모든 로봇 카메라를 받는 참조 상한 `reference_R`이다. 새 감사 항목인 기록 계약 버전 위반은 0건이다. 각 기록은 자기 registry 해시(v2 `c9bb5556…`)로 버전이 정해지고, 저장 요청 1871건이 그 버전으로 재검증된다.

## TensorBoard (`tensorboard.json`)

- **스냅샷:** `/Users/changmin/projects/ugrp/outputs/tensorboard/0927-zone-study-offline-smoke-v6`. run은 35개(시행 30 `<condition>/<trial_id>` + 코호트 5)이고 scalar는 789개다. 원본·보고서 해시는 `collection.json`에 있다. v4·v5 스냅샷은 건드리지 않았다.
- **보기 키:** `zone_study_offline_smoke_v6_20260927` 하나만 `outputs/tensorboard-view.json`에 추가했다. 쓰기 직전에 파일을 다시 읽었고, 다른 102개 키의 값·순서·형식이 같은지 확인했다. 필터 `^(0926-zone-study-offline-smoke-v5|0927-zone-study-offline-smoke-v6)/`는 v5 기준선을 함께 보여 준다. 값이 같아서 두 버전의 점이 겹친다. 고정 카드는 8개다: 성공, makespan, 호출 수, 사고·발화 SIM 비용, 토큰, 사용량 미상 호출, 발화.
- **확인:**
  - 기존 공용 서버(PID 9291, 다른 작업 소유, 재시작하지 않음)가 v6 run 35개를 목록에 올렸다.
  - scalar 789개를 `scalars.json`과 대조했고 불일치는 0건이다. raw 시행 기록의 `result/model_calls`도 30/30 같다. 시행 run 30개에 고정 태그 8개가 모두 있다.
  - 저장 링크를 headless Chrome으로 열어 두 장을 캡처했다. `tensorboard-pinned-v6.png`는 v5+v6, `tensorboard-pinned-v6-only.png`는 v6만 보여 준다. 두 장 모두 고정 카드 8개가 표시되고 run이 선택되어 있다.
  - v6 캡처의 첫 행(`leader_ko-s1`) 값은 `scalars.json`과 같다: 호출 72, 사고 243.6, 발화 1.6, 토큰 601,917, 발화 수 4, makespan 300, 성공 0.
- **한계:** v4·v5와 같다. 공용 logdir의 병합 HParams 실험은 다른 스냅샷의 9개 열만 보여 주므로, 설정한 열을 고를 수 없다. v6 세션 35개는 session_groups API로 확인했다. 수치는 Time Series로 본다.

## 이 결과가 뜻하지 않는 것

v1~v5와 같다. 이 결과는 언어 이해, 조건 간 우열, 물리 운반 성공, 자기 카메라 인식을 입증하지 않는다. 물리가 없으므로 성공 시행은 0이다. 장부가 실제 프록시 요청을 모두 센다는 것은 코드 경로와 소켓 차단 테스트로 확인했다. 실제 공급자 청구와의 대조는 파일럿에서 따로 해야 한다.

## 파일

| 파일 | 내용 |
|---|---|
| `results.json` | 30회 전체 결과(`smoke.json` 원문 바이트 복사, v5와 동일 바이트) |
| `cohort_summary.json` | 조건별 집계(raw 바이트 복사) |
| `config.json` | v5 설정값을 94841738 코드로 다시 계산해 같음을 확인한 값, 전송 경로(어댑터·completer·장부·wire), 모델 설정 해시, v5 대비 변경 |
| `source.json` | 코드 SHA, 명령, 부하 평균, 시뮬 수 상한 확인, wall 시간, 새 버전 이유 |
| `control_runs.json` | v5 대조(조건별·시행별, 장부 = 호출 기록 검사) |
| `report_summary.md` | 보고서 원문 복사 |
| `tensorboard.json` | 스냅샷·링크·고정 태그·서버/UI 대조 |
| `example_trial_record.json.gz` | `peer_ko-s1_normal_mixed-s601` 전체 기록(`send_ledger` 포함). 결정적 gzip이며, 풀어서 `reopen_trial_record`로 열면 재해시 75/75다 |
| `environment.json`, `sha256.json` | 실행기 환경과 실행기가 계산한 산출물 해시(raw 바이트 복사) |
| `raw_index.json` | raw·보고서·스냅샷의 위치·해시와 이 폴더의 커밋 파일 해시 |

raw 30건(요청 원문 포함)은 처음부터 기본 체크아웃의 `/Users/changmin/projects/ugrp/outputs/zone-study-offline-smoke-v6/`에 썼다. 보고서와 캡처는 `…/outputs/zone-study-offline-smoke-v6-report/`에 있다. 로컬 보관이며 원격 백업이 아니다.

## 참고 자료

- 논문: 이번 버전을 위해 새로 찾은 논문은 없다. 짝 비교·결측 처리 근거는 v4와 같다(Efron 1979, Kerby 2014, Rubin 1976 — [v4 README](../v4/README.md#참고-자료)).
- OSS
  - TensorBoard 2.21.0 (Apache-2.0), https://github.com/tensorflow/tensorboard — 기존 `write_events`의 이벤트·HParams 기록과 HTTP API(`/data/runs`, `/data/plugin/scalars/*`, `/data/plugin/hparams/*`) 대조
  - websockets 16.0 (BSD-3-Clause), https://github.com/python-websockets/websockets — `tb_capture.py`의 Chrome DevTools Protocol 연결
- 내부 모듈·PR
  - `harness/zone_study_offline.py`(`run_smoke`, `reopen_trial_record`), `harness/zone_study_llm_transport.py`, `harness/zone_send_ledger.py`, `harness/gemini_proxy.py`, `scripts/run_zone_study_offline_smoke.py`, `scripts/zone_study_report.py`, `scripts/ugrp_session.py`
  - PR #229 `experiments/2026-09-26-zone-study-integration/tb_capture.py`(캡처 도구, /tmp 복사 사용)
- 문서·웹
  - `docs/tensorboard.md`, `docs/zone_sim_cost.md`, `AGENTS.md`
  - Chrome DevTools Protocol `Page.captureScreenshot`, `Runtime.evaluate`: https://chromedevtools.github.io/devtools-protocol/tot/Page/
