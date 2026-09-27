# 구역 연구 실어댑터 파일럿 (PR 194, R8–R9)

이 경로는 저장된 자기 wrist RGB·정적 지도·자기 발행 명령 이력으로 실제
`GeminiProxyCompleter`/프로토콜/SIM 스케줄러의 연결을 검사한다. 물리를 실행하지
않으며 수락된 고수준 행동도 실물/시뮬레이터의 이동 성공을 뜻하지 않는다.
기존 v1–v6 기록은 변경하지 않는다. 기본은 **dry-run, 네트워크 0회**다.

## 경계와 예산

- `ModelCallTransport`가 호출별 `SendLedger` opener와 정확한 client 클래스를 확인한다.
  Python 네트워크 가드는 준비·생성·응답 처리 동안 다른 socket/opener와 자식 프로세스를
  거절한다. 허가된 loopback URL로 장부 wire만 한 번 연결할 수 있다.
  TCP 기존 연결의 `send/sendall`도 검사한다. 악의적인 native extension을 격리하는
  OS sandbox는 아니며, 등록된 Python 실행 경로의 우회를 잡는 가드다.
- live opener는 별도 `build_opener(ProxyHandler({}), RefuseRedirects())`다.
  환경 HTTP proxy·전역 urllib opener를 상속하지 않고 HTTP redirect 후속 요청을 거절한다.
- 예약·허가·정산은 생성 스레드만 허용한다. `AttemptBudget`, `SendLedger`,
  `ModelCallTransport` 모두 다른 스레드를 hard error로 막는다. 비동기 전송은 지원하지 않는다.
- 모든 조건·시행·재시도·재시작은 **같은 SQLite 파일**을 사용한다.
  한 POST 직전에 `BEGIN IMMEDIATE`로 **최대 upstream 2 attempts**와
  **2 × (입력 바이트 상한 + 이미지 상한 + 실효 출력/추론 8192)**를 영속 예약한다.
  파일 전체 상한은 **600 attempts / 5,000,000 tokens**다.
  연결 실패·timeout·사용량 미상·알려진 사용량 모두 **환불하지 않는다**.
  따라서 600번의 proxy POST를 허용한다는 뜻이 아니며, 토큰 상한이 먼저 걸릴 수 있다.
- 텍스트 상한은 실제 전송 JSON의 UTF-8 바이트 수 + 1024다(base64까지 포함하는 과대 예약).
  이미지는 JPEG 1–2장, 각각 1024×1024 이하만 허용하고 장당 65,536토큰
  (16 tile × 4096)의 보수적 여유를 추가한다. 이는 제공자 측정값이 아니다.
  실응답 usage가 한 upstream 예약을 넘으면 결과를 폐기하고 이후 전송도 중단한다.
  다른 모델·이미지 규격에는 이 상한을 재사용하지 않는다.
- 요청 원문·이미지는 전송 전에 `xb`+fsync로 저장하고 SQLite에도 call ID, 장부 번호,
  body hash, 경로, 설정, 예약을 남긴다. 응답 저장/정산 실패 시 행동·메시지는 실행되지 않는다.
  프로세스 중단 후 `reserved_unknown`도 그대로 차감되며 실행을 자동 재개하지 않는다.
- SIM 비교용 입력은 기존 고정 프롬프트 보정, 출력은 **실제 응답 문자열의 고정 로컬 tokenizer**다.
  fixture 전용 `40 + 30 × 발화 수`는 실응답에 사용하지 않는다.
  제공자 usage·upstream 상한·SIM 비용은 서로 다른 필드다.

## 설치 프록시의 실효 설정

설치 파일은 읽기만 한다. 현재 감사한 버전은
`sha256:7d4c4e8c2addf9e0dc159de6ba0f4ec4374f876d915a6bc0752d3fd18db3e556`이다.
다른 hash면 실행을 거절하며, 전역 설치 파일을 자동 수정/재시작하지 않는다.
PID·명령 경로·파일 수정 이후의 프로세스 시작 시각·해당 loopback 포트의 listener를
실행 전에 확인하고 manifest에 남긴다. 호출 직전에도 source hash·프로세스 생존·고정 연구
파일 hash를 확인한다. proxy URL에는 인증정보·query를 넣을 수 없다.

| 클라이언트 요청 | 실제 upstream 설정 |
|---|---|
| `gemini-3.8-flash` | `gemini-3.8-flash-low` |
| `reasoning_effort=none` | `thinkingLevel=LOW` |
| `max_tokens=1400` | `maxOutputTokens=8192` (출력/추론 예약에 사용) |
| `temperature=0.0` | `temperature=0.0` |

**9/25 한국어 파일럿도 같은 프록시를 통과했으므로** 위 모델·thinking·출력 상한 변환을
거쳤다. 과거 클라이언트 기록의 `1400`/`none`을 실효 upstream 설정으로 읽으면 안 된다.
이 주석은 과거 실행의 재호출/과금 재검증이 아니며 기존 frozen 기록은 보존한다.

R8 대응은 사용자 지정 **선택 (b)**다. 프록시의 짧은 429 재시도(`range(2)`)를
끄거나 설치 파일에 계측 코드를 추가하지 않고, proxy POST마다 최대 2회분을 선차감한다.
장부 1건이 upstream 1건 또는 과금 1건이라는 주장을 하지 않는다.

## 응답 종료 판정 (R9)

연구 transport는 **proxy 응답의 `finish_reason=stop`**만 프로토콜 파서에 넘긴다.
`length`, `content_filter`, `tool_calls`, 알 수 없는 값·누락은 유효한 행동 JSON과
usage가 있어도 실패 호출이다. 행동·메시지 relay 전에 거절하고 입력·생성 텍스트·
생성 발화의 SIM 비용, 제공자 usage와 최대 2회 예약을 보존한다. 예약 환불은 없다.
`stop`도 빈 본문, 불완전하거나 fenced JSON, 필수 필드 누락/추가, refusal/tool call,
본문에 남은 `finishReason`/`upstream_finish_reason` 비정상 값,
`promptFeedback.blockReason`, `safetyRatings[].blocked`를 발견하면 거절한다.
통과한 본문은 기존 조건별 프로토콜 검증까지 성공해야 행동·메시지로 채택한다.

원래 종료 이유와 거절 사유는 client → transport → scheduler →
`calls[].cost_terms.completion` → `model_evaluation.completion`으로 보존한다.
wire ledger·SQLite 정산·request archive·manifest `call_links`·reconciliation에도
같은 `completion`을 남긴다. 늦게 도착하거나 SIM horizon에서 검열된 응답도
관측한 종료 이유를 잃지 않는다. 파일럿 `successful_calls`는 **call status `ok` +
현재 completion 정책의 정상 판정**을 함께 검사한다. 평가의 기존 `completed_calls`는
검열되지 않은 호출 수로 실패도 포함하며 성공 수가 아니다. 과거 종료 이유 미기록은
`unknown`으로 남기며 성공으로 추정하지 않는다. 코호트 진입 시 hashed trial 원문과
영속 ledger의 정상 종료도 다시 대조한다. 과금 대조 `complete=true` 자체는 응답 성공이 아니다.

**설치 프록시의 남는 한계:** 감사한 `handle_complete`는 upstream `MAX_TOKENS`만
`length`로 보존하고 `SAFETY` 등 다른 이유는 기본 `stop`으로 덮어쓴다.
추가 실패 신호도 사라진 채 완전하고 프로토콜에 맞는 JSON이 오면 이 클라이언트는
원래 비정상 종료를 알아낼 수 없다. 이 수정은 설치 프록시를 변경하지 않는다.
모든 dry-run/실행 manifest와 proxy profile에 `completion_limitation`을 남기며
`upstream_finish_reason_verified=false`로 기록한다. 성공 집계는 **관측된 proxy stop과
유효한 응답의 수**이며 upstream STOP 확인이나 물리 성공의 수가 아니다.
9/25 파일럿도 같은 프록시의 종료 이유 손실 가능성이 있으며 기존 frozen 기록을
수정하거나 소급하여 upstream 정상 완료라고 판정하지 않는다.

## 필수 pre-flight 7항목

1. **실행 경로 고정:** 검토한 소스를 coordinator가 커밋한다. init 시 Git SHA와 연구
   Python·시나리오·지도·wrist fixture·runner hash를 budget에 봉인한다. tracked dirty
   tree, 변경된 source/settings, proxy source/runtime 불일치를 거절한다.
2. **추가 요청 통제:** redirect 거절·단일 ledger opener·Python 네트워크 가드·upstream
   2회 상한 예약을 사용한다. proxy 내부 retry 이벤트는 가능한 로그 구간에서 수집한다.
3. **원자성:** 다른 스레드 전송/예약/정산 금지. 서로 다른 프로세스의 공유 예산 예약은
   SQLite transaction으로 직렬화하며 실행 단계 진입도 상태 hash로 다시 확인한다.
4. **전체 예산:** 초기 4회, 코호트, 실패, 재시도, 재시작까지 동일 `--budget-file`을
   명시한다. 파일이 없으면 실호출을 거절하고 자동 생성/리셋하지 않는다.
5. **실패 주입:** R8 테스트의 429·5xx·전송 후 timeout·깨진 응답·저장 실패·늦은 응답·
   cap 직전 경합을 모두 통과시킨다. 실패가 행동/메시지를 실행하지 않는지도 검사한다.
   R9의 네 조건별 `length`·종료 이유 누락·본문 차단 신호·불완전 JSON 검사와
   성공 집계/코호트 진입 회귀도 통과해야 한다.
6. **4회 실호출 대조:** `preflight`는 `no_comm/peer_ko/leader_ko/structured` 각 1회,
   자동 재시도 0회다. 실패 시 중단한다. 4회 모두 성공하고 아래 연결이 모두 확인된 후
   별도 `--stage cohort`를 허용한다. 코호트는 조건당 3 actor, actor당 최초 1회
   (총 12회), 실패 retry 최대 1회다. idle/message 재질문을 끈 동일 정책을 모든 조건에
   적용하고 각 시도는 동일 전체 예산을 사용한다.
7. **입력·정산 감사:** 실제 wire body/이미지 hash, 저장 archive, 자기 wrist·지도·자기
   명령 경계와 채널 격리를 확인한다. 실제 usage의 `total_tokens`는 숨은 reasoning을
   포함할 수 있으므로 prompt+completion으로 대체하지 않는다. 중단/늦은 upstream
   작업은 terminal 근거까지 대조하고, 미확인 상태로 코호트를 확대하지 않는다.

## coordinator 실행 순서

이 변경을 검토·커밋한 뒤 실행한다. 아래 실호출 명령은 이 수정 작업에서 실행하지 않았다.
`PYTHON`과 `PILOT_ROOT`는 예시이며 결과 raw는 primary checkout `outputs/`에 둔다.
새 budget은 파일럿 시작 때 **한 번만** 만들고 이후 같은 파일을 재사용한다.
R8 소스로 이미 봉인한 budget은 R9 소스와 맞지 않아 실행을 거절한다.
송신 이력이 있는 예산 파일을 새 파일로 바꿔 잔액을 초기화하면 안 된다.
그 경우 기존 비용을 보존하는 별도 검토·이관 전까지 실호출을 중단한다.

먼저 오프라인 회귀를 실행한다(`--basetemp`는 이 worktree 내부 경로).

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_review_r9.py tests/test_zone_study_review_r8.py \
  --basetemp=.tmp/r9-coordinator -q
```

```sh
PYTHON=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PILOT_ROOT=/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r9
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --output "$PILOT_ROOT/dry-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --init-budget \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/init-01"
```

실호출 전 공유 agent lock과 프로세스 소유권을 확인하고, coordinator 드라이버 PID로
잠금을 획득한다. 표준 관리 경로에 `zone-study-pilot`을 등록했다.
공통 manager가 기록/프로세스 수명을 관리하도록 다음을 사용한다.
`PROXY_PID`는 앞서 확인한 실제 프로세스 PID로 설정한다.

```sh
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.sim_cli workflow run zone-study-pilot -- \
  --execute --budget-file "$PILOT_ROOT/budget.sqlite" --proxy-pid "$PROXY_PID" \
  --output "$PILOT_ROOT/preflight-01"
```

실제 CLI의 `workflow` 하위 명령은 `python -m scripts.sim_cli workflow --help`로 확인한다.
직접 runner를 사용할 때는 `ugrp_session.py run`으로 수명을 관리한다.
preflight가 성공해도 대조가 미완료면 exit 2이고 `reconciliation_complete=false`다.

```sh
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --reconcile-only \
  --budget-file "$PILOT_ROOT/budget.sqlite" --upstream-telemetry "$PILOT_ROOT/telemetry.jsonl" \
  --output "$PILOT_ROOT/reconcile-01"
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.sim_cli workflow run zone-study-pilot -- \
  --execute --stage cohort --budget-file "$PILOT_ROOT/budget.sqlite" --proxy-pid "$PROXY_PID" \
  --preflight-manifest "$PILOT_ROOT/preflight-01/manifest.json" \
  --upstream-telemetry "$PILOT_ROOT/telemetry.jsonl" --output "$PILOT_ROOT/cohort-01"
```

`--recover-run <중단된 output 폴더 이름>`은 `--reconcile-only`와 함께 사용한다.
모든 기존 시도의 terminal evidence가 확인된 경우에만 중단된 driver를 닫으며,
예약 차감과 원래 send row를 보존하고 응답의 행동을 재실행하지 않는다.
기존 출력 디렉터리/manifest는 덮어쓰지 않는다.

## 대조 자료와 남는 실제 실행 게이트

manifest의 `call_links`는
`trial_id + call_id → ledger_seq/body hash → reservation_id → proxy correlation header /
response ID → upstream attempts → provider usage`를 보존한다.
proxy request ID와 실제 upstream 목록은 증거가 없으면 `null`이다.
현재 프록시는 `X-UGRP-Call-ID`를 기록하지 않고 일반 POST/429 로그만 남긴다.
로그의 파일 위치·byte 구간·hash·이벤트 종류는 저장하지만 **다른 작업의 호출과
구분할 수 없는 로그를 call별 대조 완료로 간주하지 않는다**.

따라서 기존 로그만으로 연결되지 않으면 coordinator가 실제 provider/proxy trace에서
다음 JSONL을 마련해야 한다. 추정 ID·추정 0 usage를 채우지 않는다.
설치 proxy 변경은 이 작업에 포함하지 않는다. 자료가 없으면 preflight 다음 단계는 계속 차단된다.

```json
{"reservation_id":"...","body_sha256":"...","proxy_request_id":"...","proxy_response_id":"...","upstream_attempts":[{"id":"...","terminal":true,"usage":{"prompt_tokens":100,"completion_tokens":20,"total_tokens":130}}],"evidence":{"path":"/absolute/raw-upstream.jsonl","sha256":"..."}}
```

`evidence`가 가리키는 원본에는 `evidence` 필드를 제외한 같은 행이 있어야 한다.
각 upstream ID는 파일럿 전체에서 유일해야 하며 마지막 usage는 proxy 응답과 같아야 한다.
429의 0 usage도 원본에 `provider_confirmed_nonbillable:true`가 있어야 허용한다.
이 포맷은 coordinator가 수집한 원본을 검증하는 입력이지 제공자 서명을 인증하는 장치는 아니다.

실호출 결과가 새로 생기면 `docs/tensorboard.md`에 따라 원본을 보존하고 새 snapshot으로
등록·재열람한다. 이번 R8–R9 수정의 unit test/dry-run은 새 학습·물리 실험 결과가 아니므로
기존 TensorBoard snapshot을 변환하거나 성공 수치를 추가하지 않는다.
