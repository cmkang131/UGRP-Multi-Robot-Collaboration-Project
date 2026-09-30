# TensorBoard로 UGRP 기록 보기

기존 ACT 학습·로봇 실행 기록을 **읽기 전용 스냅샷**으로 변환한다. 원본 JSON·영상·가중치를 수정하지 않고, 재학습·시뮬레이션·외부 모델 호출을 하지 않는다. 화면은 공식 TensorBoard이며 원본 MP4 링크만 작은 로컬 서버에서 제공한다.

## 설치와 실행

Mac에서는 기존 `.venv-sim-worker-mac`을 사용한다. 별도 시뮬레이션 환경은 만들지 않는다. Ubuntu는 기존 개발 환경 Python으로 같은 명령을 실행한다. TensorFlow와 PyTorch는 변환/뷰어 실행에 필요하지 않다.

```sh
.venv-sim-worker-mac/bin/python -m pip install -r requirements-observability.txt
.venv-sim-worker-mac/bin/python scripts/export_tensorboard.py \
  --source /absolute/path/to/act-training-model \
  --source /absolute/path/to/jev-cohort/rule-straight \
  --source /absolute/path/to/multi-object-run \
  --output outputs/tensorboard/review-NEW-ID --max-images 8

python3 scripts/ugrp_session.py run tensorboard-review -- \
  .venv-sim-worker-mac/bin/python scripts/run_tensorboard.py \
  --logdir outputs/tensorboard/review-NEW-ID
```

[TensorBoard](http://127.0.0.1:6006)을 연다. 원본 영상은 Text의 `media/` 링크에서 열린다. 기본 미디어 포트는 6007이다. 두 서버 모두 127.0.0.1에만 바인딩한다. 사용 후 실행 터미널에서 Ctrl-C 또는 `python3 scripts/ugrp_session.py stop tensorboard-review`로 종료한다. 로그인 시 자동 시작하거나 백그라운드 서비스를 설치하지 않는다.

Mac에서는 `scripts/open_tensorboard.command`를 Finder에서 실행해도 된다. 기본 체크아웃의 Python을 사용하며, `outputs/tensorboard` 아래에 여러 export collection이 있으면 `collection.json` 수정 시각이 가장 최근인 **export snapshot 하나**를 기본으로 연다. 이것은 편의를 위한 뷰어 선택이며 실제 실험 수행 날짜를 뜻하지 않는다. 특정 위치를 열려면 `UGRP_TENSORBOARD_LOGDIR=/path/to/review scripts/open_tensorboard.command`처럼 지정할 수 있다. 모든 collection을 한꺼번에 보려면 `scripts/run_tensorboard.py`를 `--prefer-latest-collection` 없이 직접 실행한다.

TensorBoard의 기존 run selector는 run이 40개를 넘으면 기본 선택을 모두 해제한다. 이 상태에서는 Text 탭에 `decisions`, `evaluation`, `provenance` 같은 그룹 제목만 보이고 실제 카드 내용은 비어 보일 수 있다. Finder launcher가 최신 export collection 하나를 기본으로 고르는 이유가 이것이다. 전체 logdir를 일부러 열었다면 왼쪽에서 run을 명시적으로 선택하거나 특정 collection으로 다시 실행한다.

미디어 포트가 이미 사용 중이면 launcher는 traceback 대신 포트 충돌을 명시적으로 보고한다. 기존 review 서버가 남아 있으면 그 서버를 종료한 뒤 다시 실행한다. 다른 미디어 포트를 사용하려면 이벤트 안의 `media/` 링크도 같은 포트를 가리키도록 해당 snapshot을 그 포트로 다시 export해야 한다.

## 무엇을 어디서 보는가

| TensorBoard 탭 / 태그 | 내용과 경계 |
|---|---|
| Scalars / `training`, `development` | 기록된 학습 step별 loss·개발 오차·완료 분류 지표. 전체 step을 보간하지 않음 |
| Scalars / `result` | 실행별 실제 시간·SIM 시간·발행 명령·호출·토큰·비용. 없는 값은 기록하지 않음 |
| Scalars / `rgb_estimate` | RGB에서 추정한 거리·방향. 정답 좌표가 아님 |
| Scalars / `claims` | 제어기/프로토콜 완료 주장. 사후 성공과 분리 |
| Scalars / `evaluation/reported_success` | result.json의 명시적인 bool 성공 필드. 어떤 필드인지 provenance에 기록. 실험별 판정 범위가 다름 |
| Images / `observations` | 결정에 연결된 자기·TOP 입력. 기본 최대 8개 결정을 균등 표본 추출하며 첫/마지막 포함 |
| Text / `decisions` | 결정 step별 상태·요청·행동/응답. 실행한 명령과 실제 물리 결과를 동일시하지 않음 |
| Text / `result`, `evaluation` | 종료 이유와 사후 판정 원문. 시뮬레이터 정답은 이 사후 평가 영역에만 존재 |
| Text / `provenance` | 원본 폴더·실행 SHA·조건·누락·변환 시각 |
| Text / `media` | 변환하지 않은 원본 MP4를 로컬 재생 화면으로 연결 |
| HParams | 정책·case·SHA·seed·clock·설정 해시와 개별 실행 지표 표. 조건을 필터링한 뒤 비교 |

HParams의 **session status=success는 이벤트 가져오기 완료**를 뜻한다. 로봇 성공은 `evaluation/reported_success`와 그 출처 필드로 확인한다. 서로 다른 조건의 성공률을 자동 합산하지 않는다. 빠르게 실패한 실행의 시간을 성능 개선으로 해석하지 않는다. ACT 설정이 있어도 운반 결정에 진입하지 않았다면 `act_carry_decision_rows=0`이며, ACT 운반 성공률의 분모로 자동 포함하지 않는다.

### ACT 요청 누락 캡처의 외부 감사

과거 실행에서 카메라 캡처 뒤 소유자 오류로 ACT 결정 행이 저장되지 않았다면 `--coverage-audit`로 **원본 밖**의 감사 JSON을 연결할 수 있다. 이 옵션은 반복할 수 있으며 각 JSON의 절대 `source_raw`가 해당 `--source` 하나를 지정한다. 선택한 source와 연결되지 않거나 중복된 감사, 원본 경로·`pair-decisions.json` SHA256·기록된 wire 요청 수·고아 r1/r3/TOP 캡처 해시가 맞지 않는 감사는 오류로 거부한다.

```sh
.venv-sim-worker-mac/bin/python scripts/export_tensorboard.py \
  --source /Users/changmin/projects/ugrp/outputs/dispatch-action-act-20260924/holdout-a-candidate-act \
  --coverage-audit /Users/changmin/projects/ugrp/outputs/act-action-training-20260924/audits/v27-a-act-request-coverage.json \
  --output outputs/tensorboard/action-act-coverage-NEW-ID --max-images 0
```

이 실행에는 **저장된 wire 요청 92행**이 있고, 마지막 고아 캡처의 두 모델 슬롯에서 추가 요청이 실제 전송됐는지는 **0~2건 범위로 미확인**이다. `result/model_calls`는 기록된 92건을 유지하고, `execution/act_possible_unlogged_slots_min/max`와 Text의 `inference_errors/coverage_audit`에 범위를 표시한다. `act_request_verification_complete=false`는 이 누락을 뜻하며 고아 캡처 자체를 모델 호출이나 응답으로 세지 않는다. 외부 감사 파일의 SHA와 연결된 원본 이미지도 새 export manifest에 기록한다. 기존 이벤트 폴더에 추가하지 않고 새 스냅샷을 만든다.

### 시간축

기본으로 **STEP 축**을 사용한다. 학습은 원래 optimizer step, 실행은 기록된 결정 순번이다. SIM 시각은 별도의 `execution/sim_time_s` 곡선으로 제공한다. 화면의 기본 smoothing은 원자료를 시각적으로 평활하므로 정확한 값 비교에는 0으로 설정한다. 뷰어는 태그당 최대 10,000 scalar 표본을 읽고, 이벤트 파일에는 변환한 전체 값을 보존한다.

과거 기록에 실제 시작 시각이 없으므로 **TensorBoard의 WALL/RELATIVE 시간은 변환 시각 기준**이다. 파일 수정 시각에서 실행 시작 시각을 만들어내지 않는다. 연속 영상의 플레이어 시각도 SIM과 자동 정렬하지 않는다.

### 지원되는 원본

- ACT 학습: `report.json`의 `progress` 배열 또는 로봇별 `progress.json`.
- Jev 직접 운동: `result.json` + `turns.json` + 참조 RGB.
- 다중 물건: `result.json` + `actor-static-task.json` + `turn-*.json` + `runtime/<request_id>.json`.
- ACT 공동 운반: `result.json` + `pair-decisions.json`의 `act_carry` 행. 물리 로봇 ID와 모델 슬롯 구분.
- ACT 종료 오프라인 감사: `termination-audit.json`과 해시가 일치하는 `predictions.json`. 예측을 다시 감사해 `offline/episodes`, 조기 정지·종료 누락 횟수, `offline/termination_pass`를 표시한다. `offline_pass`도 물리 성공이나 기본 제어기 채택을 뜻하지 않는다.
- 클라우드 실행: 종료된 `run.json`의 프로세스 종료 코드와 실제 시작/종료 시간. GPU 설치 실패는 로봇 실패로 바꾸지 않는다.
- ACT 최종화 관리 실행 루트: `artifacts/report.json`과 `manifest.json`의 출처·종료 상태를 검증하고 `finalization/*`에 기록한다. 추가 optimizer update가 0인 검증 실행이며 학습 곡선·로봇 실패로 표시하지 않는다.
- `runtime-benchmark-comparison.json`: 직접 파일 또는 부모 폴더를 지정한다. 고정된 4개 ABBA 요청 기록의 해시·모델·입력·측정값을 대조하고 `benchmark/*`에 표시한다. 요청 지연을 전체 임무 시간이나 로봇 성공으로 바꾸지 않는다.
- 기타 `result.json`: 명시된 결과 지표와 출처만 변환. 형식을 모르는 내부 로그를 임의로 해석하지 않음.
- 파생 뷰가 선언한 오프라인 평가 수치: `derived_view_only: true`인 `result.json`이 `offline_scalars`로
  태그와 값을, `offline_source`로 원본 기록의 경로·SHA-256을, `offline_scalar_scope`로 그 수치의 범위를
  적으면 `offline/*` 스칼라로 변환한다. 원본이 없거나 해시가 다르면 변환을 거부하고, 태그 형식(`offline/<이름>`)과
  유한 수치만 허용한다. 어떤 수치를 보여줄지는 변환기가 아니라 파생 뷰가 정하며, 이 값은 오프라인 측정이므로
  로봇 임무 성공·실행 시간으로 읽지 않는다. HParams에는 그 실행이 선언한 태그만 등록된다.

`--source`는 한 실행/학습 폴더를 지정한다. 코호트 상위 폴더의 `results.json`이나 `report.json.runs`를 자동으로 따라가지 않는다. 원하는 하위 실행을 명시적으로 반복 지정한다. 현재 실행 중인 폴더보다 결과가 완성된 폴더를 선택한다.

### 오프라인 감사·채점 기록 (별도 진입점)

`scripts/export_tensorboard.py`는 로봇 실행·학습 기록을 변환한다. **실행이 아닌 평가 산출물**(오프라인 인식 채점, 접촉 프로필 A/B 물리 감사)은 `scripts/export_offline_audit.py`로 변환한다. 읽는 것은 파생 뷰 1폴더의 `result.json` 하나이며, 파생 뷰가 **어떤 수치를 보여줄지 스스로 선언**한다.

```sh
.venv-sim-worker-mac/bin/python scripts/export_offline_audit.py \
  --source /absolute/path/to/derived/<run> ... \
  --output outputs/tensorboard/review-NEW-ID
```

| 선언 키 | 뜻 |
|---|---|
| `derived_view_only`, `offline_source`, `offline_scalar_scope` | 파생 뷰임을 밝히고 원본 파일의 절대 경로·SHA-256과 그 수치의 범위를 적는다. 원본이 없거나 해시가 다르면 변환을 거부한다 |
| `offline_scalars` | `offline/<이름>`·`gate/<이름>` 태그와 유한한 수치. 원본에 있는 값만 옮긴다 |
| `offline_series` | 원본 JSONL의 표본을 태그별로 그대로 옮긴다. step은 표본 순번, SIM 시각은 `execution/sim_time_s`, 선택한 phase의 상대 시각은 `relative_time`. 보간·평활은 하지 않는다 |
| `sim_s`·`wall_s`·`commands`·`model_calls` | 있으면 표준 `result/*` 태그로 옮긴다. 없는 값은 0으로 채우지 않는다 |
| `success`+`success_definition` | `evaluation/reported_success`로 내보내는 bool 게이트 판정과 그 정의. **로봇 임무 성공이 아니다** |
| `hparam_metrics` | HParams 표에 등록할 핵심 태그(전부 등록하면 표가 읽히지 않는다) |

안전 규칙은 표준 변환기와 같다: 기존 출력 폴더 덮어쓰기 거부, 64 MiB 상한, 변환 중 원본이 바뀌면 이벤트 미게시 + 실패 manifest, 인증 필드 가림. 구역 문자(A/B/C)와 로봇 ID는 태그에서도 원본 표기를 유지한다. 선언 키는 파생 뷰가 `export.py`의 `offline_scalars` 형식과 같게 맞춘 것이며, 그 표준 지원이 들어오면 이 모듈을 합쳐 은퇴시킨다. 사용 예는 [2026-09-26 인식·감사 스냅샷](../experiments/2026-09-26-tb-perception-noslip/README.md)을 따른다.

## 저장과 갱신

- 기존 출력 폴더에 덮어쓰기·추가 쓰기를 거부한다. 새 스냅샷 ID로 변환한다.
- `manifest.json`에 변환기 SHA·dirty 여부, 실행 메타데이터, 읽은 원본 파일의 SHA256·크기·mtime, 이미지 누락/해시 불일치를 남긴다.
- 읽은 원본이 변환 도중 바뀌면 이벤트를 게시하지 않고 실패 manifest를 남긴다. 미완성·손상 JSON은 경고 또는 변환 실패로 구분한다.
- 알려진 인증 필드는 가리고, 로그는 HTML을 실행하지 않는 텍스트로 기록한다. 원본 영상 서버는 완료된 export manifest에 등록된 두 파일명만 허용하고 범위 요청을 지원한다. 크기/mtime이 바뀐 영상은 재변환 전 재생을 거부한다.
- JSON은 파일당 64 MiB 상한, 이미지 결정 표본은 `--max-images 0..100`. `0`은 숫자·텍스트만 변환한다.
- 카메라·영상 원본은 로컬에 그대로 있다. manifest의 해시와 TensorBoard 이벤트는 raw 전체의 원격 백업이 아니다. 원본 영상을 다른 컴퓨터로 옮기면 manifest의 로컬 경로도 달라진다.
- TensorBoard 자체의 새로고침은 이벤트 폴더 갱신을 읽는다. **현재 구현은 스냅샷 변환이며 JSON을 자동 감시하지 않는다.** 로봇 실행·학습 중인 소스에 로깅 코드를 삽입하지 않는다.

## 검증

```sh
.venv-sim-worker-mac/bin/python -m pytest -q tests/test_tensorboard_export.py tests/test_tensorboard_launcher.py \
  tests/test_offline_audit_export.py
```

이벤트를 TensorBoard EventAccumulator로 다시 읽어 실제 scalar·text·image, HParams 메타데이터, 원본 불변성, 시간·누락값·완료 주장 분리, 영상 Range/경로 제한을 확인한다. launcher 회귀는 여러 export collection이 있을 때 최신 **export snapshot**만 고르는지와 손상·빈 collection을 무시하는지 확인한다. CI의 `tensorboard-export`가 선택 의존성을 설치해 실행하며 일반 회귀 환경에서는 선택 의존성이 필요한 테스트만 건너뛴다. `tests/test_offline_audit_export.py`는 오프라인 감사 파생 뷰의 선언 검사·시계열 표본 전달·원본 해시 거부·변환 중 원본 변경 거부를 확인한다.

설계 참고: [TensorBoard 시작](https://www.tensorflow.org/tensorboard/get_started), [HParams 비교](https://www.tensorflow.org/tensorboard/hyperparameter_tuning_with_hparams), [PyTorch SummaryWriter](https://docs.pytorch.org/docs/stable/tensorboard.html). 실제 변환은 TensorBoard 2.21.0의 event protobuf를 사용한다.

## Zone-study 통합 실행: 평가 → 원본 → event 계약 (P06)

`ugrp.zone_study_integration_run.v1` 실행 폴더를 `--source`로 지정하면 전용 변환기가
`manifest.json`의 전체 파일 목록·SHA-256과 bundle digest를 검증한다. 필수 파일은
`result.json`, `study/trial_record.json`, `eval_only/evaluation.json`,
`study/frozen_plan.json`, `study/record_index.json`이다. 파일 누락,
미등록 파일, 해시 변조, trial/result/evaluation의 종료 사유·판정·SIM cap 불일치는
변환 실패이며 이벤트를 게시하지 않는다. 변환 중 파일이 바뀌어도 실패한다.

새 기록 후보는 `scripts/zone_study_evidence_writer.py`다. v6e가 봉인한 기존
`run_zone_study_integration.py`는 그대로 보존하며 이 후보를 자동으로 호출하지 않는다.
실제 적용 전 코디네이터가 새 실행기에 연결하고 source/bundle을 고정해야 한다.
종료·예외·중단을 잡는 실행기 책임과 이미 종료된 자료를 쓰는 함수의 책임은 별개다.

- result/manifest/trial/evaluation에 같은 `evidence_identity`를 저장한다.
  논리 `trial_id`와 실제 `run_id`/`episode_id`/양의 정수 `attempt`를 구분하며
  condition·scenario·seed·bundle SHA·order sheet SHA·orders SHA를 연결한다.
  bundle의 공개 scenario 참조, trial의 주문 전체, 요청 원문의 주문서와 provenance,
  study config의 seed/condition/주문서 해시, 심판의 주문별 개체·시각·배송 수를 대조한다.
  모든 파일 해시를 다시 계산해도 다른 시행/주문을 끼워 넣은 자료는 거절한다.
- result의 `terminal`은 반드시 JSON `true`여야 한다. manifest의 `terminal` 객체에는
  end_reason·end_sim_s·failure_class·sim_horizon_s·record_complete가 모두 있어야 하며
  trial/result와 일치해야 한다. `record_complete`는 반드시 boolean이다.
  **표식 없는 구형 자료의 묵시적 호환 수입은 지원하지 않는다.** 실행 schema가 같아도
  identity나 terminal 표식이 빠지면 이벤트를 내지 않는다. 기존 원본에 표식을 덧붙이거나
  다시 봉인하지 않는다. 구형 자료 전환은 별도 출처 검토·버전 명세가 필요하다.

- 시도 1개마다 `cohort/trials=1`이다. 성공·정책실패·API·HOST_ERROR·중단·미평가를
  개별 시도 화면에 남긴다. 이 값을 모아 연구 성공률의 분모를 만들지 않는다.
  `scripts/zone_study_evidence_cohort.py --plan … --plan-sha256 … --source … --output …`는
  실행 전 고정한 admission 수를 분모로 쓰며, 파일이 없거나 거절된 시행도 INVALID/성공 0으로
  남긴다. 논리 시행당 사전 지정한 attempt 하나를 요구하며 사후 재시도 선택은 지원하지 않는다.
  [P06 재설계·참고 자료](../experiments/2026-09-30-e2e-p06-evidence/README.md#두-차례-block-뒤-재설계)에
  복합키·내부 로그 연결·입력 SHA-256·게시 전 수치 재계산과 생성 검사의 범위를 적었다.
- 성공은 주문별 item ID/종류/목적지 충족과 심판 정착 확인, 종료 사유가 함께 맞아야 한다.
  `orders_complete` 문자열이나 로봇 완료 주장만으로 성공하지 않는다. 정착 시작 시각과
  확인 시각을 모두 보존하며 확인이 SIM cap 뒤면 성공으로 소급하지 않는다.
  심판 v3는 이 판정과 누락 truth 표본의 정착 연속성 끊김을 명시한다. 기존 v2 원본은 보존한다.
- 실패의 PAR-2는 `2 × sim_horizon_s`이다. 원래 종료 시간은
  `referee.observed_end_sim_s`, 성공 makespan은 기존 정의인 마지막 정착 창의 시작이다.
  `failure_class`, `record_complete`, `referee_status`, `missing`을 manifest/Text에 남긴다.
  미완료 scheduler 로그의 알려진 호출·시도·토큰·SIM 비용 합계는 `*_lower_bound`로
  남기고 정확한 총계·전체 응답시간 평균은 생략한다. 완전한 모델 정산이 아니다.
- `usage_unknown_calls`/토큰 하한을 보존하고 미상 전체 토큰·없는 USD 비용·없는 명령수나
  응답시간은 scalar로 만들지 않는다. provider 원장 요약은 `provider/*`와 Text에 별도로
  남긴다. 모델 과금 대조는 call ID → 원장 → proxy/upstream/provider의 별도 검사다.
  미평가의 배송 수/배송률, 계측하지 않은 conflict/deadlock/idle/replan도 0으로 채우지 않는다.
- `--max-images`는 TensorBoard 미리보기 표본 수만 제한한다. `request_archive`의 **모든**
  요청 원문과 `study/request_images/<sha256>.jpg`는 보존하고 모두 해시 검증한다.
  `--max-images 0`에서도 원본 이미지 누락을 거절한다.
- `evidence_kind=synthetic` 결과는 Python API의 `convert(..., allow_synthetic=True)`와
  OS 임시 폴더 아래의 새 output을 함께 지정해야 변환된다. 일반 CLI는 이를 허용하지 않는다. 테스트 raw/event는 공용 `outputs/tensorboard`에 게시하지 않는다.

### TOP 설정과 실제 영상

`eval_only/top_camera.json`은 설정·적용값 기록일 뿐 영상 존재 증거가 아니다.
통합 run의 영상 등록에는 원본을 봉인하기 **전** 다음 별도 선언이 필요하다.
이미 봉인한 manifest를 편집하거나 기존 snapshot에 영상을 추가하지 않는다.

```json
{
  "schema": "ugrp.zone_study_media.v1",
  "videos": [
    {"path": "eval_only/overview.mp4", "kind": "top_rgb", "sha256": "<actual-file-sha256>"}
  ]
}
```

파일은 실제로 존재하고 raw manifest 해시와 일치해야 한다. 허용 파일명은
`overview.mp4`, `execution.mp4`, `motion.mp4`이며 `eval_only/` 아래에 둔다.
GT 좌표로 만든 그림/영상은 `kind=gt_visualization`으로 선언한다. TOP RGB와 다른
라벨로 등록하며 `top_rgb_video_registered`를 켜지 않는다. 파일 등록 검사는 디코딩·재생
검사가 아니다. 코디네이터는 실제 영상의 촬영 출처·화면·SIM 시각 대응도 따로 확인한다.

### D1 캡처 계약

D1의 **0.1초/1초 비교창은 1 Hz 저장만으로 재현할 수 없다**. 결정 시점 프레임을
추가로 저장해도 모든 비교창의 양 끝이 존재한다는 보장이 없다. D1 검증 실행은
검출기가 실제 사용한 각 `(t, t-0.1 s)`와 `(t, t-1 s)` 프레임의 원본 바이트·SIM 촬영
시각·프레임 ID·해시·자기 명령/phase 구간을 남겨야 한다. 필요 표본 간격과 시각 허용
오차는 D1 사전 등록(#293)과 일치시킨다. 10 Hz 이상 기록도 실제 쌍의 시각 검사를
대체하지 않는다. 빠진 쌍은 `insufficient_evidence`이며 보간 프레임, 0점, 정상 이동으로
채우지 않는다. 기존 `dev_1hz_decisions_v1`을 이 용도에 자동 적용하지 않는다.
모델 요청 이미지 보존 규칙은 D1/일반 캡처 표본 선택과 독립적으로 적용한다.

### 첫 실제 결과에서 코디네이터가 닫을 검증

P06은 아래 절차의 **synthetic 파일/event 계약만** 검사한다. 실제 결과·공용 logdir·
브라우저 화면·동영상 재생 완료를 주장하지 않는다. 첫 실제 실행에서 다음을 기록한다.

1. terminal attempt 목록을 원장과 대조한다. 성공·실패·중단·미평가의 수, 누락,
   실제 SIM cap, 실행 SHA/bundle/profile, 원문 요청/응답과 이미지 해시를 확인한다.
   P06 후보 writer를 명시적으로 연결하고 실제 scenario/cap/attempt를 전달하는 새
   실행 source/bundle과 전체 admission 계획·해시를 코디네이터가 실행 전에 고정해야 한다.
   writer의 `frozen_plan`·`plan_sha256` 필수 인자로 전달한다. 기존 runner의 KeyboardInterrupt
   처리나 trial 생성 전 실패 기록까지 이 PR로 적용됐다고 간주하지 않는다.
2. 기존 export manifest의 source 경로/해시와 중복 여부를 검사한 뒤, 기본 체크아웃
   `/Users/changmin/projects/ugrp/outputs/tensorboard/<NEW-ID>`에 새 snapshot을 만든다.
   원본과 기존 snapshot은 읽기 전용으로 보존한다.
3. `EventAccumulator(..., size_guidance={'scalars': 0}).Reload()`로 이벤트를 다시 읽는다.
   trial에서 재계산한 성공·PAR-2·SIM cap·배송 수, raw 명령 행 수, 호출·토큰 하한·미상
   usage·응답시간과 scalar **태그 존재 여부 및 값**을 대조한다. 누락값이 0으로 생기지
   않았는지 확인하고 HParams session metadata도 읽는다. 성공/전체 분모를 함께 기록한다.
4. 현재 서버의 세션 소유자·PID·명령·실제 `--logdir`를 확인한다. 공용 viewing root는
   기본 체크아웃의 `outputs/tensorboard`다. 다른 작업 서버를 종료하지 않는다.
   `media_registry(logdir)`에서 새 원본 영상의 경로·종류·해시 등록을 확인한다.
   TOP 설정만 있는 실행은 영상 미확인으로 남긴다.
5. `outputs/tensorboard-view.json`을 쓰기 직전에 다시 읽고 자기 실행 키/링크만 추가한다.
   Chrome `강` 프로필의 기존 TensorBoard 탭에서 snapshot과 비교 baseline/cohort를
   선택한다. `hparams_visible_columns`를 다시 적용하고 조건·seed·SHA·failure class·
   SIM cap·record/usage 완전성 열을 확인한다.
6. 저장된 pin 링크로 성공, SIM makespan/PAR-2, 명령수, 모델 호출수, 응답시간의 **있는
   태그만** pin하고 smoothing=0에서 source 숫자와 대조한다. 원본 영상 링크를 실제로
   열어 올바른 run의 영상인지·재생 가능한지·GT 그림을 TOP RGB로 표시하지 않았는지
   확인한다. source/event/logdir/video/pin/HParams 중 미확인 항목은 각각 남긴다.

검사 기록에는 새 snapshot 절대 경로, raw/export manifest 해시, event readback 비교표,
서버 logdir/PID, 영상 등록/재생 결과, pin 링크와 HParams 열·화면 확인 범위를 적는다.
이 절차는 실제 첫 결과가 나왔을 때 수행하며 자동 주기 점검을 만들지 않는다.
