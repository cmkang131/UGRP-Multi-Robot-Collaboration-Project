# v99 두 로봇 짝 운반 LLM 판단 층 — 가능성 시험 (배관 단계, 연구 결과 아님)

번들 `zone-pair-llm-v99`, 워크플로 3.11.0, 상태 `DRAFT_UNSEALED`, `research_result=false`. 이슈 #219 참조.
2026-10-03 사용자 결정("일단 지금 상황에서, llm을 쓰고 되는지를 보자 그 다음에 고도화를 해나가자")의
첫 단계다. **이 문서의 어떤 숫자도 운반 성공·모델 성능·조건 간 효율에 대한 결과가 아니다.** 이 문서가
기록하는 실행에서 모델 호출은 한 번도 하지 않았다(가짜 모델만 사용).

## 2026-10-03 사용자 결정 (두 건) — 이 문서의 변경 이력

사용자 말: **"걍 한국어 조건 뺴주라. 그리고, llm 실제로 연결해서 써도 돼"** (조정자 전달).

1. **한국어 요구 조건을 뺀다.** 조정자의 해석(사용자에게 알려 정정 가능): 한국어 *언어 요구*를 없애고
   자연어 동료 대화를 통신 조건으로 유지한다. 이에 따라
   - 조건 이름 `peer_ko` → **`peer_nl`**(`rule` / `no_comm` / `peer_nl`);
   - 프롬프트에서 `KO_LANGUAGE`와 "한국어 발화" 요구를 뺐다. 메시지 언어는 자유이며 영어도 된다
     (`harness/pair_llm_prompts_ko.py`, `PROMPT_VERSION=...v2`). 지시문 자체는 재사용한 스터디 한국어 문장이라
     한국어로 남는다(영어 프롬프트는 별도 결정거리);
   - `language_report`(한글 비율·표시)는 **기록용 지표**로만 남긴다(`metrics.language`, `gate=false`).
     어느 메시지도 언어 때문에 거절·재작성되지 않는다(봉인된 스터디 전송 코드가 이미 "전달하고 표시만" 한다).
     게이트가 아니고 통과/실패 필드도 아니다;
   - 봉인된 스터디 코드는 열린 자유 대화 채널을 `peer_ko`라는 이름으로 등록해 두었다. 그래서 `pair_llm_prompts_ko.STUDY_SPEC`
     한 곳에서 `peer_nl → peer_ko`로 옮겨 봉인 코드(`zp.spec`·`zp.Transport`·`validate_reply`·`zc.condition`)를 부르고,
     짝 층의 기록·번들·CLI·프롬프트·로봇이 보는 `condition`/`encoding`(`free_text`)은 `peer_nl`을 쓴다. 받은 메시지
     봉투의 `encoding` 필드만 봉인된 값 `free_ko`로 남는다(봉인 검증기가 요구).
2. **실제 LLM 호출 허용.** 조정자 지시(2026-10-04 재개): 기존 프록시 경로로 켠다. 아래 "실제 모델 경로(`--live`)"에
   구현을 적는다. 한 번의 짧은 스모크만 허용되었고(peer_nl, 60 SIM초, 시드 911), 코호트 토큰 상한은 300,000이다.

**번들 번호**: 기존 v97 가짜 모델 스모크(소스 `b201f777`, 한국어 `peer_ko` 조건)가 이미 `bundle.json`과 해시를
남겼으므로 실행 기록이 있는 번들로 보고 `docs/execution_versioning.md` 2번(설정을 바꾸면 새 버전)에 따라
**v99 / 워크플로 3.11.0**으로 올렸다. 조회: main + 열린 PR에서 최댓값은 v98 / 3.10.0(#363)이며 v99·3.11.0은 비어 있었다.
v97은 폐기된 가짜 모델 배관 초안이다. `outputs/pair-llm-v97-smoke/` 원본은 그대로 두었다. 아래 2단계 표는 v97
기록이며 v99의 증거가 아니다.

## 무엇을 만들었나

스크립트 기술(v88 짝 운반: 집기·들기·문 통과·내려놓기, 고정 열거형 짝 상태 통신)은 **그대로** 두고,
그 위에 LLM이 "무엇을 할지"를 정하게 했다. 한 실행기에 세 조건이 있다.

| `--condition` | 이름 | 내용 |
| --- | --- | --- |
| `rule` | C-rule | 모델 없음. 두 로봇이 한가해지면 곧바로 같은 청구(claim)를 낸다(기존 `Runtime`, 수정 없음) |
| `no_comm` | C-llm-nocomm | 각 로봇의 모델이 자기 RGB·정적 지도·주문서·자기 명령 이력만 보고 판단. 메시지 없음 |
| `peer_nl` | C-llm-nl | 위와 같고 r1↔r2 자연어 자유 대화 채널이 추가됨(언어 요구 없음) |

세 조건 모두 고정 열거형 짝 상태(스크립트 기술 내부)는 켜져 있고, 지도·주문·300 SIM초 한도·평가기가 같다.

- **자리(seam)**: `Runtime.step`이 한가한 로봇마다 `team.start`를 부른다. LLM 조건에서는 그 앞에
  `ClaimGate`를 둔다(`harness/pair_llm_runtime.py`). 모델의 `claim`이 *허가(permit)*를 풀어야만 실제
  `Team.start`가 호출된다. 허가 없으면 `CLAIM_NOT_RELEASED`로 거절하고 아무 일도 없다.
  허가가 있으면 **모델이 낸 청구의 인자**(주문·구역·상대)로 원래 `Team.start`를 부른다. 그래서
  잘못된 구역(`WRONG_PAIR_DESTINATION`)·역할·제출 불일치(`PAIR_SUBMISSION_MISMATCH`)도 스크립트 경로와
  같은 곳에서 같은 이유로 거절되고 측정된다.
- **허가 규칙**: `SELF_*`(아직 자세 불확실 등) 거절이면 허가를 유지하고 다음 틱에 다시 시도한다(스크립트
  조건도 매 틱 재시도). 수락·되돌릴 수 없는 거절이면 소진한다. 허가 대기 중 `abort`/`hold`가 받아들여지면
  허가를 취소한다. 짝 작업 도중 중복 청구는 `BUSY:pair_carry:<job>`로 거절한다.
- **재사용**: 존-스터디의 `DecisionScheduler`/`EventScheduler`, SIM 비용 모델 `zone_sim_cost.v1`(잠정),
  `SendLedger`(요청·응답 원문 보존), `GeminiProxyCompleter`, 메시지 전송·`language_report`(기록만 하고
  전달·표시한다). 스터디 계약이 세 로봇(`ROBOTS`, `team_size=3`)에 고정되어 있어 봉인된 코드를
  고치지 않고 **두 로봇용 프롬프트·입력·시도(trial)를 따로** 두었다(`harness/pair_llm_*.py`).
  "세 로봇 r1, r2, r3" 문구는 두 로봇 문구로 바꾸고 `r3`/`세 로봇`이 남지 않음을 시험으로 고정했다.
- **입력 경계**: 자기 `robot_cam` RGB 1장 + 정적 지도 그림 1장(요청당 정확히 2장), 정적 지도 투영, 주문서,
  자기 발행 명령 이력·자기 판단, 조건이 전달한 메시지뿐이다. 정답 좌표·측정 관절·접촉·성공 신호·공용 top
  카메라·상대 상태 내부는 없다. 평가기(`harness/pair_llm_eval.py`)는 로봇 쪽 어떤 모듈도 가져오지 않는다.
- **번들 기록**: 모델 ID·온도·프롬프트 템플릿 해시·"시드 없음" 문구(프록시 요청에 seed 필드가 없다)·비용
  모델 버전/다이제스트·조건 라벨·v88 기술 번들 해시·소스 해시를 `bundle.json`에 남긴다.
- **시간**: 모든 조건 같은 300 SIM초(`--cap-s`, 스모크는 60). LLM 조건은 토큰 기반 결정적 SIM 비용을
  낸다. 응답 wall 시간은 기록만 하고 SIM에 넣지 않는다.

## 감사 3건 닫음 (시험으로 고정)

- (a) `holding()`/`box.held`는 자기 RGB 추정이다: `visual_box_skill.py`/`zone_own_status.py`는 시뮬레이터를
  직접 가져오지 않고, `held=True`는 양쪽 자기 카메라 부착 점검 통과 뒤에만, `False`는 시각 확인된 해제
  뒤에만 설정된다(`tests/test_pair_llm_inputs.py`).
- (b) `map_bundle('zone_wide_door_geometry_v3')` 공개 투영에는 landmark·tag·pose 키가 없다.
- (c) 전송선 수준 보관: 보존된 모든 요청 본문에서 이미지가 정확히 2장(`CURRENT OWN WRIST RGB` jpeg,
  `STATIC MAP FIGURE` png)이고 해시가 자기 프레임·지도 그림과 일치한다(`tests/test_pair_llm_case.py`).

## 1단계: 배관 시험 (가짜 모델, 물리 없음)

`tests/test_pair_llm_{inputs,runtime,case,eval}.py` 60개(v97에서 58개 + `peer_nl` 이름·번들 기록 2개). 핵심:

- 메시지가 r1↔r2로만 흐르고 전달은 보낸 호출의 SIM 비용 뒤에 일어난다. 영어 메시지는 전달하되 표시한다.
  `no_comm`에서 `messages`가 있으면 검증 단계에서 거절한다.
- 청구가 `team.start`를 게이트한다: 허가 없이는 시작되지 않고, 가용 자세(시험용 주입)에서는 청구 뒤 스크립트
  짝 기술이 실제로 시작된다. 청구 안 하는 모델은 시작을 막는다(같은 조건 `rule`은 첫 한가한 틱에 시작).
- 원장이 모든 요청·응답을 바이트 그대로 보존하고 보관 요청이 디스크에서 다시 해시된다.
- `rule` 조건의 발행 명령은 `scripts/run_final_pair_v3.run_case`와 같은 런타임·같은 120 SIM초에서
  **바이트 단위로 같다**(2401 캡처, 동일 `actions`).
- 성공은 별도 평가기에서만 나온다. 같은 가짜 빔 궤적에서 세 조건이 같은 판정을 받는다.
- ENOSPC는 `HOST_ERROR`(`failure.class=ENOSPC`)로 분류하고 부분 기록을 남긴다.

## 2단계: 짧은 SIM 스모크 — v97 기록 (렌더링 물리, 가짜 모델, 실제 모델 호출 없음)

소스 `b201f777`(커밋·깨끗한 트리), SIM 슬롯 `sim-claude-pair-llm-v97`(owner claude, 비타이밍), `nice +10`,
조건마다 60 SIM초, 시드 911, 지도 `zone_wide_door_geometry_v3`. 원본은 기본 체크아웃
`outputs/pair-llm-v97-smoke/<조건>-60s/`(로컬 보관이며 원격 백업이 아님).

| 조건(v97 이름) | 결과 상태 | 명령(r1+r2) | 모델 호출 | 모델 SIM 비용 | 입력/출력 토큰 | 메시지 | 한국어 | 청구 허가 | wall(s) | 평가기 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rule | COLLECTED_UNQUALIFIED | 191+191 | 0 | 0 | 0/0 | 0 | - | - | 93.8 | NOT_IN_ZONE |
| no_comm | COLLECTED_UNQUALIFIED | 191+191 | 12 | 30.8 s | 35970/528 | 0 | - | 2 | 84.2 | NOT_IN_ZONE |
| peer_ko | COLLECTED_UNQUALIFIED | 191+191 | 14(12 완료·2 중단) | 36.2 s | 45008/826 | 4 | 4/4 (1.0) | 2 | 107.9 | NOT_IN_ZONE |

**읽는 법(중요)**: 스모크는 **합성(가짜) 보정과 모든 프레임을 거절하는 시각 작업자**로 돌렸다
(`harness/pair_llm_plumbing.py`, 번들에 `synthetic_plumbing_only`로 표시). v3 측정 보정이 아직 없어
(`measured_calibration`이 PARTIAL을 거절) 제어기가 자기 위치를 모른다. 그 결과 두 로봇은 `look_around`
(7.8 SIM초에 종료)만 하고, `Team.start`는 매 틱 `SELF_UNCERTAIN`(조건당 로봇마다 1069회)로 거절되어 짝
작업이 시작되지 않는다. `rule`도 같은 이유로 시작하지 못한다. 따라서 스모크가 보여주는 것은
**배관**(프레임→호출→응답→청구→게이트→스크립트 기술→물리→평가기, 원장·이미지 2장·비용·한국어 판정 기록,
`rule`/LLM 조건의 같은 한도·같은 평가기)이지 운반이 아니다. 청구가 받아들여져 짝 기술이 시작되는 경로는
1단계 시험(가용 자세 주입)에서만 확인했다.

원본 해시(각 조건 `artifacts.sha256.json`의 sha256): rule `708effbc20cd…`, no_comm `3b3a01aaeb21…`,
peer_ko `306ca258f6fa…`. 번들 해시: rule `9de77e7fb751…`, no_comm `b7cbb28bebc4…`, peer_ko `561cadc29880…`.
10 SIM초 rule 사전 점검(`probe-rule-10s`) 해시 `937f9663d3f9…`. 렌더링 물리 실행은 이 Mac에서 약 0.6배속
(부하 평균 13~40).

## 알려진 한계·위험 (결과 해석 전에 읽을 것)

1. **블라인드 제어기**: 측정 보정·실제 시각 작업자 없이는 어떤 조건도 운반하지 못한다. 진짜 시험은 #363(v96)
   쪽 OpenCV 위치 추정과 측정 보정이 준비된 뒤다.
2. **작업 한도 120 vs 300 s**: 실행기 `job_sim_limit_s=120`이라 짝 작업은 120 SIM초에 `LOCAL_TIMEOUT`으로
   끝날 수 있다. 300초 한도의 의미는 재시도·재청구에 있다.
3. **평가기는 잠정**(`PROVISIONAL_GEOMETRIC_JUDGE_NOT_THE_363_JUDGE`): 빔 궤적만으로 구역 안·들림·내려놓음을
   본다. v88 경로는 `physical_success: None`을 유지한다. #363 판정기가 확정되면 교체한다.
4. **호출 예산 소모**: `pose_uncertain` 이벤트가 `failure` 촉발이 되어 호출 한도(로봇당 12)를 빨리 쓸 수
   있다(가짜 모델 30초 시험에서 확인). 스터디 스케줄러 규칙이라 고치지 않았고, 실제 모델 시험 전에 정할 일이다.
5. **비용 모델 잠정**(`zone_sim_cost.v1` provisional), **시드 없음**(프록시 요청에 seed 필드 없음 → 실제 모델
   실행은 비트 단위 재현 불가, 요청·응답 원문과 해시가 재생 기록), 프록시 할당량 미확인.
6. 허가 규칙(위)은 이 층의 설계 결정이다. 다른 규칙(예: 대기 중 허가 만료)은 비교하지 않았다.
7. 공용 파일 충돌 가능: `scripts/run_ci_tests.py`(패턴 1줄), `tests/test_simulation_workflow_manager.py`
   (카탈로그 개수 +1, 샘플 1줄). 번들 번호는 v99 / 3.11.0(위 설명). 병합 순서에 따라 다시 정해질 수 있다.

## 재현

```
python3 -m scripts.run_pair_llm --condition peer_nl --expected-source-sha <커밋 SHA> --output <기본 체크아웃 outputs/ 절대 경로> \
    --cap-s 60 --synthetic-plumbing-calibration --sim-slot <슬롯> --lock-owner claude --execute
python3 -m pytest tests/test_pair_llm_inputs.py tests/test_pair_llm_runtime.py tests/test_pair_llm_case.py tests/test_pair_llm_eval.py tests/test_pair_llm_live.py
```

실제 모델 스모크(조정자 승인 뒤): 위 명령에 `--live --proxy-pid <프록시 PID> --budget-db <절대 경로>/budget.sqlite --create-budget \
--cohort-id <이름> --cohort-token-cap 300000`을 더한다.

## 실제 모델 경로 (`--live`)

새 전송 계층이 아니다. 스터디의 실제 모델 경로를 그대로 쓴다: `GeminiProxyCompleter` → `MainStudySendLedger`(요청을 보내기
**전에** 내구성 예산 행을 쓰고, 요청·응답 원문 바이트와 sha256, 제공자 토큰 사용량, wall 지연, 실패 분류를 남김) → 감사된 로컬
구독 프록시(`127.0.0.1:8391`, 읽기 전용 확인: 감사된 소스 해시 + PID 수신 소켓, 프록시를 시작·수정하지 않음) → 리다이렉트를
거부하는 전용 opener(`NetworkFence`). 이 PR이 더한 것은 `harness/pair_llm_live.py` 한 모듈이다.

- `--live`: LLM 조건만(`rule`은 모델이 없어 거절), 한 케이스 60 SIM초 이하, `--proxy-pid`, 절대 경로 `--budget-db`
  (`--create-budget`으로만 생성), `--cohort-id`, 명시적 `--cohort-token-cap`이 모두 필요하다. 더 긴 실제 케이스는 별도 결정거리다.
- **예산 원장**(`harness/zone_main_budget.py`, SQLite): 요청마다 보내기 전 행, 응답 뒤 정산. 코호트 상한(스모크 300,000 토큰,
  사용량을 모르는 요청은 12,000 토큰으로 계산)에 닿으면 다음 요청 전에 멈춘다.
- **재시도 층(전부 문서화된 기존 규칙, 새 규칙 없음)**: (1) 스케줄러 `max_retries=0`: 실패한 호출을 새 POST로 다시 보내지
  않는다. (2) 실행 단위: `llm_driver.json`의 `once_in_place_only_if_host_error_before_first_model_request`
  (`llm.run_attempts`): 첫 모델 요청 전의 HOST_ERROR만 제자리에서 1회. 429·API 오류·첫 요청 뒤의 호스트 오류는 재시도하지 않는다.
  (3) 감사된 프록시: 한 POST 안에서 업스트림 429를 내부 재시도(업스트림 시도 최대 2회). 번들(`model.retry_layers`)에 기록한다.
- **429 / 쿼터**: HTTP 429, 또는 오류 본문에 quota / rate limit / resource exhausted 문구가 있으면 실패 라벨 `RATE_LIMIT`
  (스터디 분류 `infra:API`)로 **명시 기록**하고 다음 틱에 실행을 멈춘다. 그 실행은 무효이며 어떤 것도 재시도하지 않는다.
  오류 응답의 본문 해시·발췌·`Retry-After`를 원장 행과 `llm/wire/*-error.json`에 보존한다(스터디 원장은 이를 버린다).
  그 밖의 API 오류(500·시간 초과 등)는 스터디 규칙대로 기록하고 실행은 이어가되 시행은 `infra:API`(무효)다. 응답이 한 번도
  정상이 아니면 멈춘다.
- **기록**: 요청 본문(텍스트 + 이미지 2장)·응답 바이트는 `llm/wire/`, POST별 행(토큰, 지연, 모델, 완료 사유, 실패 분류, 해시)은
  `llm/model_calls.jsonl`, 사용량 요약은 `metrics.model_usage`, 프록시 신원·예산 원장·코호트 사용량은 `llm/live_driver.json`,
  시도 목록은 `attempts.json`에 있다. 모두 `artifacts.sha256.json`에 해시된다.
- 시험 25개(`tests/test_pair_llm_live.py`): 네트워크만 가짜 프록시로 바꾸고 나머지는 실제 live 사슬이다(제공자 모양 응답,
  429·403·503 쿼터, 500, 전부 실패, 코호트 상한, 재시도 규칙, CLI 거절).

## 참고 자료

- 같은 저장소: `harness/zone_study_integration.py`(`IntegratedTrial`), `zone_study_offline.py`(`OfflineTrial`),
  `zone_event_scheduler.py`, `zone_study_decisions.py`, `zone_send_ledger.py`, `zone_study_llm_transport.py`,
  `zone_study_prompts_ko.py`(채널·메시지 블록 재사용, `KO_LANGUAGE`는 사용하지 않음), `zone_study_protocol.py`(`language_report`),
  `zone_final_pair_runtime.py`/`zone_final_pair_skill.py`(v88), `scripts/run_final_pair_v3.py`(`run_case`).
- 설계 기록: 이 세션의 `llm_pair_design.md`(옵션 A: 얇은 두 로봇 층, 기존 스케줄러·비용·원장 재사용).
- #363(v96) 실험 README `experiments/2026-10-03-pair-carry-highpose/README.md`: "`run_camera_pair_transport.py`는
  이전 LLM 두 로봇 경로이며 … 새 LLM 제어기로 대체하지 않는다" — 이 PR은 v88 어댑터를 대체하지 않고 그 위에
  결정 층만 얹으므로 일치한다.
- 외부 방법론을 새로 도입하지 않았다(기존 스터디 스케줄러·ledger 재사용). 같은 문제로 두 번 막힌 일은 없었다.
