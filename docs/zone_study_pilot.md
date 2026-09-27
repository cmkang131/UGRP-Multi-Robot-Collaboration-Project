# 구역 연구 실어댑터 파일럿 (PR 194, R8–R10)

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

## 응답 종료 판정 (R10, 이슈 #222 코디네이터 정책)

설치 프록시는 수정하지 않으며 사본 프록시도 만들지 않는다. 코디네이터가 정한
정책에 따라 **proxy `stop` + 완전한 조건별 스키마**를 통과한 응답만 채택한다.
모든 채택은 `upstream_finish_verified=false`다(기존 호환 필드
`upstream_finish_reason_verified=false`도 유지). 가려진 upstream `SAFETY`,
`RECITATION`, 종료 이유 누락을 정상 `STOP`과 구별할 수 없다는 한계를 인정한 정책이다.

연구 transport는 **proxy 응답의 `finish_reason=stop`**만 프로토콜 파서에 넘긴다.
`length`, `content_filter`, `tool_calls`, 알 수 없는 값·누락은 유효한 행동 JSON과
usage가 있어도 실패 호출이다. 행동·메시지 relay 전에 거절하고 입력·생성 텍스트·
생성 발화의 SIM 비용, 제공자 usage와 최대 2회 예약을 보존한다. 예약 환불은 없다.
`stop`도 빈 본문, 불완전하거나 fenced JSON, 필수 필드 누락/추가, refusal/tool call,
본문에 남은 `finishReason`/`upstream_finish_reason` 비정상 값,
`promptFeedback.blockReason`, `safetyRatings[].blocked`를 발견하면 거절한다.
통과한 본문은 기존 조건별 프로토콜 검증까지 성공해야 행동·메시지로 채택한다.

관측된 proxy 종료 이유와 남아 있는 거절 사유는 client → transport → scheduler →
`calls[].cost_terms.completion` → `model_evaluation.completion`으로 보존한다.
wire ledger·SQLite 정산·request archive·manifest `call_links`·reconciliation에도
같은 `completion`을 남긴다. 늦게 도착하거나 SIM horizon에서 검열된 응답도
관측한 종료 이유를 잃지 않는다. 파일럿 `successful_calls`는 **call status `ok` +
현재 completion 정책의 정상 판정**을 함께 검사한다. 평가의 기존 `completed_calls`는
검열되지 않은 호출 수로 실패도 포함하며 성공 수가 아니다. 과거 종료 이유 미기록은
`unknown`으로 남기며 성공으로 추정하지 않는다. 코호트 진입 시 hashed trial 원문과
영속 ledger의 정상 종료도 다시 대조한다. 과금 대조 `complete=true` 자체는 응답 성공이 아니다.

파일럿 manifest의 전체/조건별 `accepted_upstream_unverified_calls`와 평가의
`completion.accepted_upstream_unverified_calls`는 **정상 채택(상류 미검증)**을 따로 센다.
CLI 보고에도 이 필드와 한국어 라벨을 출력한다. `successful_calls`는 같은 채택 수의
호환 필드다. `failed_or_unadmitted_calls`에는 스키마 위반·검열·기록 미상도 포함한다.
완료 메타데이터만 정상이어도 최종 호출 상태가 `ok`가 아니면 채택 수는 0이다.

**설치 프록시의 남는 한계:** 감사한 `handle_complete`는 upstream `MAX_TOKENS`만
`length`로 보존하고 `SAFETY` 등 다른 이유는 기본 `stop`으로 덮어쓴다.
추가 실패 신호도 사라진 채 완전하고 프로토콜에 맞는 JSON이 오면 이 클라이언트는
원래 비정상 종료를 알아낼 수 없다. 이 수정은 설치 프록시를 변경하지 않는다.
모든 dry-run/실행 manifest와 proxy profile에 `completion_limitation`을 남기며
`upstream_finish_reason_verified=false`로 기록한다. 성공 집계는 **관측된 proxy stop과
유효한 응답의 수**이며 upstream STOP 확인이나 물리 성공의 수가 아니다.
9/25 파일럿도 같은 프록시의 종료 이유 손실 가능성이 있으며 기존 frozen 기록을
수정하거나 소급하여 upstream 정상 완료라고 판정하지 않는다.

코호트 진입에는 preflight manifest의
**`upstream_finish_limitation_acknowledged`가 JSON boolean `true`**여야 한다.
실행자가 preflight에 `--acknowledge-upstream-finish-limitation`을 명시하면 기록된다.
누락·`false`·문자열·숫자는 거절한다. 기본 dry-run/미인정 preflight는 `false`이며,
이미 저장된 manifest를 편집해서 인정할 수 없다(공유 예산에 원본 manifest hash가 봉인됨).
코호트 manifest는 진입 검사에서 확인한 preflight의 인정을 계승한다.
인정 필드는 과금 대조나 4조건 각각의 성공 호출·장부 검사를 생략하지 않는다.

## v62와 파일럿 manifest의 고정 목록

`rgb-standard-dispatch-v62`는 v61을 부모로 등록했다. v61 JSON은 바이트 그대로
은퇴 목록에 남는다. RGB 번들의 물리·카메라·명령 설정은 v61과 같으며,
새 공통 `llm_completion.py`를 포함한 전체 Python closure 174개와 파일 hash를 고정한다.
v62 등록 당시 `RUNNABLE_ID`, CI `verify-current`, dispatch/dispatch-skills workflow는
v62/1.62.0, 파일럿 workflow는 1.1.0이었다. 아래 펜스 수정 후에는 v63/1.63.0,
파일럿 workflow 1.2.0을 사용한다. manifest schema는 `ugrp.zone_study_adapter_pilot.v2`다.

| 고정 대상 | 저장 위치 |
|---|---|
| 최종 실행 SHA·전체 소스/입력 파일 hash | `source_identity.source_head`, `source_identity.files`; RGB closure의 scripts도 포함하고 실제 실행 전 커밋·깨끗한 tracked 소스를 강제 |
| 실행 번들 ID·JSON hash·물리/카메라/명령·미검증 상태 | `source_identity.rgb_execution_bundle`; bundle의 `effective`, `status`, `zone_study_pilot` |
| 완료 정책·가려진 upstream 종료 이유·인정 | `completion_policy`, `completion_limitation`, `upstream_finish_limitation_acknowledged` |
| 요청/실효 모델·프록시 hash·실행 PID | `requested_settings`, `effective_settings`, `proxy`, `proxy_runtime`; client timeout 180초, upstream timeout 300초, POST당 내부 attempts 최대 2회 |
| 네 조건·시나리오·seed·지휘자 | `pilot_contract.conditions`, `seed`, `leader_rule`; seed % 3으로 r1/r2/r3 순환, 허브-스포크 |
| wrist 원본·지도·주문서·프롬프트·프로토콜·전처리 | `pilot_contract.conditions[].wrist_originals`, `scenario`, `initial_inputs`, `registry_sha256`, `preprocessing_files_sha256`; 프로토콜 소스도 포함 |
| 실제 모델 입력 | 조건별 `trial.json.request_archive`와 wire 원문/hash; `initial_inputs`는 고정 `contract-*` 요청 ID의 최초 입력 템플릿이며 실요청을 대체하지 않음 |
| 호출·비용 | `pilot_contract.calls`, `sim_cost`; 조건당 1 POST, client retry 0, 실제 scheduler 정책, 고정 tokenizer/SIM 비용, 2 attempts 예약, 공통 600 attempts/5M tokens, 환불 0 |
| 검증 범위 | `pilot_contract.validation_scope`, `physical_success=null`; 저장 영상 어댑터만 검증, 물리·실모델·상류 STOP·과금 검증은 별도 |

등록 시점의 미커밋 작업 HEAD는 최종 실행 SHA가 아니다. 이 수정 작업은 커밋하지 않으며,
코디네이터의 검토·커밋 뒤 생성하는 manifest가 그 최종 SHA를 기록한다.
dry-run은 네트워크 호출/실행 PID 검증 없이 `proxy_runtime=null`을 기록한다.

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
   자동 재시도 0회다. 실패 시 중단한다. 4회 모두 정상 채택(상류 미검증)이고 한계를
   명시적으로 인정했으며 아래 연결이 모두 확인된 후
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
R8/R9 소스로 이미 봉인한 budget은 R10 소스와 맞지 않아 실행을 거절한다.
송신 이력이 있는 예산 파일을 새 파일로 바꿔 잔액을 초기화하면 안 된다.
그 경우 아래 `--migrate-source` 절차로 같은 파일의 비용을 보존해 이관한다.
기존 청구 대사가 미완료라면 소스 이관 뒤에도 실호출은 차단된다.

먼저 오프라인 회귀를 실행한다(`--basetemp`는 이 worktree 내부 경로).

```sh
OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_zone_study_review_r10.py tests/test_zone_study_review_r9.py tests/test_zone_study_review_r8.py \
  --basetemp=./.pytest_tmp -q
rm -rf ./.pytest_tmp
```

```sh
PYTHON=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
PILOT_ROOT=/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10
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
  --acknowledge-upstream-finish-limitation \
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

## v63 단일 JSON 펜스와 예산 소스 이관

### 원문 재현과 파서 경계

실제 R10 `preflight-01`(HEAD `1adfeff01884b308352918a4488c31258adaf478`)은
첫 `no_comm` 응답이 `stop`이고 request_id도 일치했지만 JSON을 ` ```json `
블록으로 감싸 `study_reply_incomplete_or_non_json`으로 중단됐다.
`tests/fixtures/zone_study_preflight_r10/response.json`은 해당 wire 응답 568바이트의
동일 복사본이다. 출처와 SHA-256은 옆 `provenance.json`에 있다. 원본은 수정하지 않는다.

ZC2/zone coordination과 study 프로토콜이 이미 사용하던 `three_robot_plan.parse`를
completion 검사에서도 재사용한다. `unwrap_json_fence`는 앞뒤 공백 외에 정확히 하나의
완전한 펜스 블록만 벗긴다. 시작 줄은 소문자 `json` 또는 언어 표시 없음이고, 닫는 줄은
백틱 3개다. LF/CRLF를 지원한다. 펜스 밖 설명·복수/중첩 블록·미완성 펜스·잘린 JSON·
객체가 아닌 JSON·잘못된 조건별 스키마는 거절한다. `length`/차단 신호·request_id·메시지
채널 검사를 우회하지 않는다. 네 조건에 동일하게 적용한다.

`calls[].cost_terms.completion.json_fence_removed`에 bool을 기록한다. 같은 completion은
scheduler·request archive·send ledger·SQLite 정산에도 남는다. 완전한 펜스를 벗겼어도
내용이나 종료 이유가 잘못되면 채택하지 않는다. 이 bool 자체는 성공 판정이 아니다.
`model_evaluation.completion`, manifest의 조건별 행과 전체 `json_fence_removed_calls`로
집계한다. 구형 completion의 미기록 값은 `json_fence_unknown_calls`로 구별한다.
wire 원문은 바꾸지 않고 SIM 출력 토큰은 펜스를 포함한 실제 원문으로 계산한다.

### 같은 파일에 이관하는 계약

기존 `PilotBudget(..., identity=...)`는 소스가 달라지면 그대로 재개를 거절한다.
새 `--migrate-source`만 명시적으로 봉인을 갱신한다. **원래 budget.sqlite 경로·pilot_id·
600 attempts/5,000,000 tokens 한도·모든 sends/runs 행을 그대로 유지**한다.
실패·미확인 예약에도 환불은 없다. 실제 R10 파일은 2 attempts/235,408 tokens를 예약
차감했고 provider가 보고한 total은 10,622 tokens였다. 두 숫자는 다른 회계 값이다.

`BEGIN IMMEDIATE` 안에서 기존 identity 해시와 sends/runs 상태 해시를 다시 비교하고,
`running`인 시행이 없을 때만 `source_migrations` 행 추가와 meta 봉인 변경을 함께 커밋한다.
감사 행은 이전 meta 전체, 새 identity, 사유·UTC 시각, 예약 차감량, 원본 SQL 행 개수·해시,
이전 이관으로 이어지는 해시를 보존한다. provider·요청/실효 설정·SIM 비용/입력 정책 변경은
이 절차로 허용하지 않는다. RGB effective 설정이 같은 **새 번들 ID**가 필요하다.
오래된 객체의 추가 예약·정산·시행 시작은 거절한다. 기존 소스/기존 preflight로 코호트에
진입할 수 없으며, 새 소스에서 4조건 preflight를 다시 해야 한다.

소스 이관은 과금 대사가 아니다. `reserved_unknown`·실패 응답과 미해결 근거는 보존되고,
새 전송 직전 기존 `reconcile` 게이트를 그대로 통과해야 한다. R10 원본은 현재
`reconciliation_complete=false`이므로 원본에 대한 terminal upstream 근거 없이 재전송할 수 없다.
추정 ID·0 usage로 대체하거나 새 budget을 생성해 우회하지 않는다.

### 코디네이터 실행 절차 (이 수정 작업에서는 미실행)

1. 모든 파일럿 드라이버가 종료됐는지 확인한다. `running` 기록이 남았다면 기존
   `--reconcile-only --recover-run` 절차를 먼저 따른다. 실제 upstream 작업도 terminal
   근거로 확인한다. 수정된 소스와 v63을 검토·커밋하고 소스 worktree를 고정한다.
2. 같은 budget을 `--reconcile-only`로 읽어 새 디렉터리에 보고서를 만든다.
   보고서의 `source_identity_sha256`과 `state_sha256`을 검토한 뒤 아래 인자로 넘긴다.
   이 명령은 미대사 상태에서는 exit 2여도 보고서를 저장한다.
3. 원래 budget 파일에 `--migrate-source`를 한 번 실행한다. 이 명령은 모델을 호출하지
   않으며 tracked dirty/미추적 실행 소스는 거절한다. 새 출력 경로를 사용한다.

```sh
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --reconcile-only \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/review-v63-01"
# REVIEWED_IDENTITY_SHA와 REVIEWED_STATE_SHA는 위 보고서에서 검토한 값이다.
OMP_NUM_THREADS=1 "$PYTHON" -m scripts.run_zone_study_pilot --migrate-source \
  --budget-file "$PILOT_ROOT/budget.sqlite" --output "$PILOT_ROOT/migrate-v63-01" \
  --migration-reason 'PR #194 실제 펜스 응답 회귀 수정, v62에서 v63으로 이관' \
  --from-identity-sha256 "$REVIEWED_IDENTITY_SHA" \
  --expected-state-sha256 "$REVIEWED_STATE_SHA"
```

4. `source-migration.json`과 DB의 `source_migrations` 마지막 행이 같고, 이관 전후 예약
   차감·pilot_id·기존 sends/runs가 같은지 확인한다. DB 커밋 뒤 receipt 저장이 실패해도
   이관 행은 DB에 남는다. **다시 초기화/이관하지 말고** 새 `--reconcile-only` 보고서의
   `source_migrations`로 커밋 여부와 원본 감사 행을 회수한다. 상태/identity 해시가
   바뀌어 거절됐다면 새 보고서를 검토한다. 기존 proposal/receipt를 덮어쓰지 않는다.
5. 이전 요청들의 실제 upstream 근거를 마련해 대사를 완료한 뒤 `preflight-02-v63` 같은
   새 출력 경로로 같은 budget의 `--execute --stage preflight --upstream-telemetry ...`를
   실행한다. 한계 인정 인자를 다시 명시한다. 기존 첫 실패에서 중단 정책은 유지한다.
   새 호출들도 대사하고 4조건 모두 정상 채택된 뒤에만 새 manifest로 코호트에 진입한다.

오프라인 검사는 실제 원문 회귀, 네 조건 반례/기록/집계, 원자적 이관·실패 복구,
한도 유지, 기존 preflight 차단과 새 소스의 재개 경로를 다룬다. 주입 wire·합성 대사
근거의 테스트 결과를 실제 provider 대사 완료나 물리 성공으로 해석하지 않는다.

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
