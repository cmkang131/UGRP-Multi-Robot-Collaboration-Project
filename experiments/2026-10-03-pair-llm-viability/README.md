# v100 두 로봇 짝 운반 LLM 판단 층 — 가능성 시험 (배관 단계, 연구 결과 아님)

2026-10-05 스택 갱신: #363 `363f7e2b`의 host clock v2(IntegerClock)를 세 조건에 동일 적용하며, 옛 `sim.final_pair_v3` 누적 float 시계로 실행한 결과와 합산하지 않는다. [스택 기록](stack_363_clock_v2_20261005.md).

번들 `zone-pair-llm-v100`, 워크플로 3.12.0, 상태 `DRAFT_UNSEALED`, `research_result=false`. 이슈 #219 참조.
**#363 `14ba8b5e` 위로 재기반했고 정지 판단 어댑터를 구현했다.** v100은 아직 어떤 실행도 기록하지 않았다. v99(3.11.0)는 3단계 스모크 1회의
번들이므로 그대로 얼려 두었고(소스 `ad1dda73`, 번들 해시 `a8e11294…`; 바이트 그대로 `retired-bundle/v99/`, v97은 `retired-bundle/v97/`에 보존, 아래 5번), 이 문서의 3단계 숫자는 v99 기록이다.
2026-10-03 사용자 결정("일단 지금 상황에서, llm을 쓰고 되는지를 보자 그 다음에 고도화를 해나가자")의
첫 단계다. **이 문서의 어떤 숫자도 운반 성공·모델 성능·조건 간 효율에 대한 결과가 아니다.** 1·2단계는
가짜 모델만 썼다. 3단계(아래 "3단계: 실제 모델 스모크 1회")에서 실제 모델을 한 번의 60 SIM초 실행으로 12번 불렀고,
보정은 합성이며 시각 작업자는 블라인드라 운반은 일어나지 않았다.

## 2026-10-05 구현 갱신

현재 v100은 #363 v98 HIGH 제어기를 세 조건의 기본 경로로 쓴다. 7개 사건·2개 정지 명령과
자기 추정 띠만 연결한다. 입력 스키마 v3, 프롬프트 v4이며 판단 창은 10 SIM초,
호출 상한은 36/36/72, peer_nl 발화 상한은 6/12이다.
조정자 승인 **편차(deviation)**: 자기 판단 창 안에서는 받은 글이 실행 중인 자기 작업과 별개로
모델 호출을 깨운다. 봉인 스케줄러는 수정하지 않았다.
실제 LLM·물리·렌더링은 이번에 실행하지 않았다. 아래 v97/v99 실행 숫자는 과거 기록이다.
현재 변경·가짜 시험·남은 제한은 [구현 기록](implementation_20261005.md)을 따른다.

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

## v100 변경 (2026-10-04 조정자 지시 5건; 아직 실행 기록 없음)

smoke1(v99)에서 드러난 문제를 고친 코드 변경이다. **이 변경 뒤의 실제 모델 실행은 아직 없다**(조정자: #363 새 SHA 준비 전에는 새 실제
호출 없음. 사용자의 실제 호출 승인은 유지되어 있어 그때 다시 묻지 않는다).

### 1. 자기 상태(`own_status`)를 모델 입력에 추가 — 거절이 모델에 보이게 함

smoke1에서 블라인드 제어기가 두 로봇의 시작을 로봇당 1,069회 `SELF_UNCERTAIN`으로 거절했지만 모델은 `command_issued`와
낮은 `self_belief`만 보고 계속 `continue`를 골랐다. 거절은 로봇 **자기 소프트웨어의 응답**(자기 `Team.start` 호출의 확인, 자기 실행기의 작업
이벤트)이지 시뮬레이터 정답이 아니므로 모델에 알려도 입력 경계 안이다. `harness/pair_llm_status.py`가 닫힌 기록 하나를 만든다.

| 필드 | 내용 |
|---|---|
| `last_outcome` | 닫힌 열거: `no_claim`, `claim_released`, `start_refused`, `claim_rejected`, `pair_job_running`, `pair_job_ended`, `look_around_running`, `look_around_ended` (가장 최근 사실이 이긴다) |
| `reason` | 결과별 닫힌 어휘 하나 또는 `null`. `start_refused`: `SELF_STOPPED/BUSY/INCOMPATIBLE/UNCERTAIN/INVALID_IMAGE/OCCUPIED`, `claim_rejected`: 청구 인자 거절 어휘, 끝난 작업: `queue_empty`/`local_timeout`. 어휘 밖은 모두 `other` |
| `since_claim_s` | 이 로봇이 마지막 `claim`을 낸 뒤 흐른 SIM초(자기 결정 시각), 없으면 `null` |
| `refusals_since_last_call` | 이 로봇의 지난 모델 호출 시작 이후 자기 시작이 거절된 횟수 |

- **넣지 않은 것**: 자세·관절·접촉·성공/배달 플래그·상대 상태·원문 이유 문자열·실행기 `detail`. 작업이 끝났다는 사실도 성공 신호가 아니다
  (스터디의 두 부류 `queue_empty`/`local_timeout`만).
- **상대에서 비롯된 사건이 드러내는 것(독립 검토 M1, 조정자가 설계를 받아들임)**: 상대의 대기 중 제출과 다르면(`PAIR_SUBMISSION_MISMATCH`,
  `PAIR_STATIC_INPUT_MISMATCH`) 이 로봇은 거절된 청구(`claim_rejected`)를, 먼저 기다리던 로봇은 자기 작업의 끝(`pair_job_ended`)을 본다.
  `PAIR_RENDEZVOUS_TIMEOUT`(상대가 시작하지 않음)은 시작 거절이 아니라 **기다리던 로봇의 작업 종료 이유**이며 `queue_empty`가 된다. 따라서
  상대에서 비롯된 거절·작업 종료는 **자기 명령 결과를 통해 1비트**(내 청구가 받아들여지지 않았다 / 짝 작업이 끝났다, 그 시각 포함)를 드러낸다.
  이 1비트는 로봇 자기 시작 응답과 자기 작업 이벤트이며(실제 로봇도 받는다; v99부터 `own_command_history`가 이미 거절된 청구를
  `command_rejected`로, 끝난 작업을 `queue_empty`/`local_timeout`으로 바꿔 보였다), **`no_comm`과 `peer_nl`에 똑같이** 적용되므로 두 조건은
  대화 채널만 다르다. 접은 것은 **이유의 이름**뿐이다(상대 때문에 생긴 거절은 `other`). 이 문서·코드 어디서도 "`no_comm`은 상대에 대해
  아무것도 알지 못한다"고 주장하지 않는다. 루프 안 시험(`test_a_partner_submission_mismatch_gives_identical_own_status_in_both_llm_arms`)이 같은
  불일치에서 두 조건의 `own_status`가 호출마다 같음을, 이유 이름이 모델 요청 어디에도 없음을 고정한다.
- **경계**: 입력 페이로드 스키마 v2의 필수 키(`pi.payload_violations`가 닫힌 기록·결과별 어휘·음수/불리언/비유한 값을 거절). 봉인된
  스터디 금지 키와 겹치지 않는 이름만 쓴다. 누수 시험: 적대적 문자열 21종(`GT_CONTACT_SUCCESS`, `SELF_CONTACT`, 공백·대소문자 변형,
  5,000자, `None`/숫자/리스트/dict/bytes)이 빌더를 통과하지 못함, 200회 무작위 입력에도 출력은 항상 닫힌 기록, 빌더 시그니처에 상대 자세·접촉·성공
  입력이 없음.
- **모델이 인용할 결정 근거**: 봉인된 `DECISION_SOURCES`에 `own_status`가 없으므로 프롬프트가 "`own_status`를 근거로 삼았으면
  `own_commands`로 적는다"고 안내한다(PROMPT_VERSION v3).
- **둘러보기/재위치추정 선택지**: 스킬 층에 이미 있다. `ZoneOwnExecutor.look_around()`(자기 카메라 넓은 훑기, 작업 종류 `look_around`;
  자기 작업이 돌고 있으면 `BUSY:<종류>:<id>`로 거절). 행동 `{"kind":"look_around"}`를 더했다. 봉인된 `validate_reply`는 열거형 4종
  (`claim/continue/release/wait`)만 알므로 짝 층의 `pair_llm_dispatch.validate_reply`가 `look_around`를 안전한 자리표시자(`continue`)로 바꿔
  봉인 검증기에 통과시키고 되돌린다(다른 모든 봉인 규칙·오류 문구는 그대로, 시험으로 고정). 이 선택지는 **효과를 검증하지 않았다**:
  블라인드 작업자는 훑은 뒤에도 `LOOKED_POSE_UNCERTAIN`이고(가짜 물리 시험에서 확인), 실제로 위치를 회복시키는 동작은 #363의 회복 동작이
  들어간 뒤에 다시 시험해야 한다. 그때까지 이 선택지는 "배선과 상태 표시만 확인됨"이다. 프롬프트도 사실로 말하지 않는다: "제자리에서 돌며 주변을 둘러보는 동작이며 위치를 다시 추정하는 데 도움이 될 수 있지만 보장되지 않는다"(독립 검토 사소 2; 같은 claim을 반복해도 풀리지 않는다는 단정도 뺐다. v100은 아직 실행 전이라 `PROMPT_VERSION`은 v3 그대로이고 프롬프트 템플릿 해시만 `a1487266` 때와 달라졌다). 끝난 둘러보기는 성공 신호가 아니며, 청구 허가가 남아
  있으면 거절이 계속되므로 한 호출 동안 `look_around_ended` 뒤에 다시 `start_refused`가 나온다.

### 2. 비용 모델: 이미지를 청구한다 (결정적 · 버전 고정)

스터디 규칙(`fixed_prompt_equalized.v1`)은 텍스트 토큰만 `Attempt.input_tokens`에 채워 요청당 이미지 2장이 0토큰이었다. 새 모듈
`harness/pair_llm_billing.py`가 텍스트 청구를 **바이트 그대로 두고** 이미지 몫을 더한다:
`total_billed = total_text_billed + images × 1,490` (`ugrp.pair_image_billing.v2`). 상수는 실행 중 측정이 아니라 고정값이므로 청구는 요청
모양(첨부한 이미지 수)만의 함수다. 비용 모델 `zone_sim_cost.v1`의 계수는 그대로다.

- **도출(smoke1, 실제 12회)**: 감사된 프록시는 `prompt/completion/total_tokens`만 알려주고 제공자의 모달리티별 수는 버린다.
  제공자 입력 5,978~6,169(평균 6,134.5) − 로컬 텍스트 청구 평균 3,147.3 = 요청당 잔차 2,987.2, ÷ 이미지 2장 = 1,493.6 → 10 단위
  반올림 **1,490**. 이미지 2장일 때 SIM 입력 청구가 제공자 입력과 호출마다 약 0.3퍼센트 안에서 맞는다(5,994 대 5,980 등).
- **한계**: 제공자 요율이 아니라 이 요청 모양(손목 JPEG 640x480 + 지도 PNG 757x599, 모델 `gemini-3.8-flash-low`)의 보정이다. 잔차에는
  로컬 토크나이저가 텍스트를 적게 센 몫도 섞여 있고, 적합에 쓴 텍스트 크기 묶음은 두 개뿐이다. 모델·이미지 크기·미디어 해상도 설정이 바뀌거나
  제공자의 모달리티별 수가 생기면 새 버전으로 다시 맞춘다.
- **영향(분석 재계산, 실행 아님)**: smoke1의 호출 10회를 보존된 응답 원문과 요청 청구로 다시 계산하면 v1은 기록된 호출별 비용 10개와
  모두 일치(합 30.1 SIM초 확인)하고, v2는 호출당 +0.6 → **합 36.1 SIM초(+6.0, +20퍼센트)**. 첫 두 호출 4.8/4.7, 나머지 3.3~3.4.
- **버전 이력**: `ugrp.pair_image_billing.v1`(이미지 0)은 v97 가짜 모델 스모크와 v99 smoke1이 썼다. `IMAGE_BILLING_HISTORY`에 남기고
  다시 적용하지 않는다. 요청 기록에는 `image_policy/image_tokens_per_image/image_tokens_billed/total_billed`가 남고
  `billing_problems`가 보관된 요청의 이미지 청구를 **저장된 `image_policy`에 따라** 다시 계산해 검증한다(v2는 장당 1,490이고 이미지 키가 모두 있어야 하며, v1 또는 `image_policy` 키 없음은 장당 0이고 이미지 키가 있으면 0이어야 한다). 현재 번들의 실행은 v2를 요구한다(`require`). 보존된 v99 smoke1 요청 12행이 v1 청구로 문제 0건임을 시험으로 고정했다(보존본이 있을 때). 호출 행의 `input_tokens`는 텍스트/이미지로 나뉘고, 실행 지표에
  `input_tokens_image`, `input_tokens_charged`, `image_billing`이 생긴다. 번들 `cost_model.input_billing`에 도출 근거와 이력 전체를 기록한다.

### 3. ` ```json ` 울타리: 한 번 벗기고, 횟수를 지표로 센다

봉인된 스터디 파서는 이미 응답 **전체**를 감싼 울타리 하나(json 또는 무표시, 각각 별도 줄)만 벗기고 `completion.json_fence_removed`로
표시한다. 이 규칙은 느슨하게 하지 않았다. 더한 것은 지표뿐이다: `metrics.reply_format`(`harness/pair_llm_live.py`)이 응답이 온 POST마다
울타리 표지 줄 수(`fence_marker_lines`)를 세어 `replies`, `fence_removed_calls`, `fenced_calls`, `fence_not_removed_calls`,
`plain_json_calls`, `fence_marker_lines_total`을 낸다. 울타리는 어떤 호출도 실패시키지 않는다.

- **벗길 수 없는 울타리**(앞뒤에 산문이 붙은 경우, 한 줄 울타리, 블록 둘)는 스터디 파서가 그대로 비-JSON으로 거절한다(`model_output_rejected`,
  스터디 호출 표에서는 `http_error`). 그 호출만 거절되고 다음 호출은 이어지며, 다른 정상 응답이 있는 실행은 실패가 아니다(시험: 로봇 하나의 첫 응답만
  산문+울타리/한 줄 울타리). 첫 응답 묶음에서 정상 응답이 하나도 없으면 스터디의 "정상 응답 0" 규칙이 실행을 멈춘다(`infra:API`). 이는 울타리 규칙이
  아니라 봉인된 건강 검사이며, 이때도 울타리 지표는 기록에 남아 원인이 보인다.

### 4. 번들 번호 판단: v100 / 3.12.0

- **재조회(2026-10-04, main과 열린 PR 헤드 전부)**: main 최댓값 v92/3.4.0. 열린 PR: #365와 #372는 v95/3.7.0, #363은 v98/3.10.0, 나머지는 3.0.0~3.1.0.
  v100과 3.12.0은 어디에도 없다(v99/3.11.0은 이 PR의 smoke1 번들).
- **판단**: v99 번들은 소스 `ad1dda73`·번들 해시 `a8e11294…`로 smoke1(실제 호출 12회)을 기록했다. 이번 변경은 프롬프트·입력 스키마·행동 어휘·비용
  청구 정책을 바꾸므로 실행 기록이 있는 번들을 고치지 않고 `docs/execution_versioning.md` 2번(설정을 바꾸면 새 버전)에 따라 새 번들로 올렸다.
  `configs/pair_llm_v99.json`은 `pair_llm_v100.json`으로 이름을 바꿨고 v99 기록(smoke1 요약·해시·원본)은 그대로다.
  병합 순서에 따라 #363(v98)이 먼저 들어가도 v100과 겹치지 않는다. 사용한 ID: `zone-pair-llm-v100`, 워크플로 3.12.0.

### 5. 독립 검토 BLOCK(`a1487266`)에 대한 수정 한 묶음

검토: https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/371#issuecomment-5971079195 (판정 BLOCK: B1, 주요 2, 사소 5).

- **B1 실행 기록이 있는 번들 복원(해결)**: v97(가짜 모델 스모크)·v99(실제 모델 smoke1) 번들 파일이 v100으로 이름만 바뀌어 있었다. 실행한 커밋의
  바이트 그대로 `experiments/2026-10-03-pair-llm-viability/retired-bundle/`에 되살렸다(저장소 경로를 그대로 따른 하위 폴더, 등록된 `configs/`에는
  두지 않음). `docs/execution_versioning.md` 2번과 전례(`retired-bundle/`)를 따른다. v100은 새 파일 `configs/pair_llm_v100.json`이다. 시험
  (`test_the_run_recorded_v97_and_v99_bundle_files_are_kept_byte_identical_and_not_registered`)이 바이트를 고정한다.

| 파일(`retired-bundle/` 아래) | 가져온 커밋 | sha256 |
|---|---|---|
| `v97/configs/pair_llm_v97.json` | `0646677c`(v97 스모크 소스 `b201f777`와 같은 바이트) | `ca0c34b2f7acf904376584ebb2f595b1278275c447e827292666b2e14f01b808` |
| `v97/configs/simulation_workflows.d/pair_llm_v97.json` | `0646677c` | `9077a7dd83bda8123ef6c844827f66c689227465315f99cd4206878d98587eb6` |
| `v99/configs/pair_llm_v99.json` | `ad1dda73`(smoke1 소스) | `284232e5955eb4c0b753497c8e59f81a072506b08d33ff8ad1e9183c496137b4` |
| `v99/configs/simulation_workflows.d/pair_llm_v99.json` | `ad1dda73`(`cf82bc73`의 같은 이름 파일과 바이트가 다르다. smoke1이 쓴 쪽) | `a0d8a41eebd04d2656acdfe622cec5ba3ef5af5baa547192f339fb61900719c3` |

  재현은 기록된 소스 SHA에서만 한다(v97 `b201f777`, v99 `ad1dda73`). **무엇이 실행 기록의 원본인가**: 실행이 낸 `bundle.json`(smoke1은 기본 체크아웃
  `outputs/pair-llm-v99-live/smoke1/peer_nl/bundle.json`, 파일 sha256 `990015876cee0ece369f69dd3bfd79c8d750dc70387a21bca2d2f212f0b6fa35`,
  `result.json`의 `bundle_sha256` `a8e112945fbad67840cb8a2c1495e6268c78a8a92ec80813f7aeaea9c05ea621`)이 그 실행의 기록이고, 되살린 `configs`
  JSON은 그 번들을 만든 등록 입력이다. 둘이 어긋나면 실행 산출물이 우선한다.
- **M1(해결)**: 설계를 받아들임. 위 1번의 문구를 "이유 이름은 숨기지만 사건 자체는 자기 명령 결과로 남는다, 두 조건에 똑같다"로 고쳤고
  루프 안 시험을 더했다.
- **M2(해결)**: `billing_problems`가 저장된 `image_policy`로 분기(위 2번). v99 smoke1 12행은 v1 청구로 문제 0건.
- **사소 1**: `PAIR_RENDEZVOUS_TIMEOUT` 설명과 시험을 실제 경로(작업 종료 이유 → `queue_empty`)로 고쳤다. **사소 2**: 프롬프트 표현(위 1번).
- **사소 3 보존 분류(AGENTS.md "디스크 사용 / 보존", #374)**: 모델 요청·응답 **텍스트**, 원장, 결과·trace 로그, sha256 목록은 항상 보존한다.
  `llm/wire/*-request.json`·`*-response.json`(요청 본문 텍스트 포함)은 통째로 보존한다. 단 요청 본문 안에 base64로 박힌 이미지와
  `llm/request_images/*.jpg`(sha 기준 중복 제거, smoke1은 6장), 바뀌지 않은 v88 실행기가 쓰는 `robots/r*/rgb/`(로봇당 1,201장)는 **이미지 원본**이다.
  이것들은 나중에 10/4 정리처럼 제거할 수 있다: 본문의 이미지를 `{sha256, bytes, removed}`로 바꾼 본문으로 대체하고, 원래 본문·제거한 파일의
  sha256을 `outputs/cleanup-records/`의 매니페스트에 모두 남기며 원본은 휴지통으로 옮긴다(`body_sha256`은 원래 본문의 해시로 보존). 지금은 열린 PR이고
  3일 안의 실행이라 규칙상 남겨 둔다. `llm/map_figure.png`는 고정 입력 자산(요청마다 같은 지도 그림)이라 **보존한다**(제거 대상 아님).
  smoke1은 버전 대표 자료로 지정하지 않았다(플랫폼 개발 과정의 스모크; 대표로 남길지는 조정자 결정).
- **사소 4 두 시계**: 한 기록에 두 시계가 섞여 있었다(smoke1 `dispatch.jsonl`의 `sim_s` 4.1은 시행 기준이고 `ack.sim_s` 5.4는 절대 시간; 차이는 reset
  1.3 SIM초 = `result.json`의 `reset_sim_s`). v100은 `dispatch.jsonl`에 `sim_s_since_reset`(= `sim_s`, 호출·결정·한도의 시계), `sim_s_absolute`
  (= `ack.sim_s`, 백엔드·실행기 시계), `reset_offset_s`를 명시한다. `executor_events.jsonl`에는 `sim_s_absolute`(= 사건 `sim_s`)와
  `delivered_at_sim_s_since_reset`(하네스가 사건을 받은 시각, 사건 뒤 관측 한 틱 이내)을 더했다. 정의는 `llm/study_config.json`의 `clocks`에 있다.
  `own_status.since_claim_s`와 작업 종료 시각은 시행 시계다.
- **사소 5 시험 공백(해결)**: 루프 안 불일치 시험(M1), 두 조건의 프롬프트가 `channel`·`messages` 블록만 다르다는 시험(요청 본문은 `channel`·`condition`·
  `inbox`만 다름), v1 기록 재검증 시험(M2)을 더했다.

### 6. Codex 독립 검토(PR #375, 대상 `1883c56a`)가 찾은 결함 두 건 (해결)

- **`__CHARS__` 자리표시자가 peer_nl 프롬프트에 그대로 남음(해결)**: 메시지 규칙 블록의 "text는 `__CHARS__`자 이내" 자리가 치환되지 않아
  peer_nl 모델이 글자 그대로 `__CHARS__`를 읽었다. 보존된 v99 smoke1 `peer_nl/llm/requests.jsonl` 12행 모두 시스템 텍스트에 이 글자가 있다
  (스모크 기록이며 v99는 동결이라 고치지 않는다; no_comm은 메시지 규칙이 없어 영향 없음). 원인: 봉인된 스터디는 `zp.PROMPT_TEXT_CHARS`로 이 자리를
  채우는데 짝 층의 `KO_PAIR_MESSAGES`는 같은 치환을 하지 않았다. **고침**: 스터디가 쓰는 같은 값(`zp.PROMPT_TEXT_CHARS` = 240)을 그대로 넣는다.
  새 정책 값이 아니다. 이 값은 모델에게 알려 주는 권장 길이고, 전송 계층이 실제로 거절하는 상한은 `zp.MAX_TEXT_CHARS`(600)다(둘 다 봉인된 값).
  `system_prompt`는 `__이름__` 꼴이 하나라도 남으면 `ProtocolError`로 멈춘다(실패 닫힘). 시험은 두 조건 x 두 로봇의 최종 시스템 텍스트(그리고 실제 요청의
  첫 메시지)에 `__`가 없고 peer_nl의 숫자가 240임을 확인한다. v100은 아직 실행 전이라 `PROMPT_VERSION`은 v3 그대로이고 프롬프트 템플릿 해시만 다시 달라졌다.
- **`own_status`가 두 시계를 섞음(P2, 해결)**: 하네스 시계(시행 기준)의 호출 시각·작업 종료 시각과, 청구 게이트가 적은 백엔드 절대 시계의 허가·제출 시각을
  `pair_llm_status.build`가 그대로 비교했다. Codex 반례: 상대 시각 허가 10.0, 둘러보기 종료 10.5이면 reset 원점 0에서는 `look_around_ended`, 원점 1.3에서는
  (게이트 11.3 > 10.5라서) 더 오래된 `claim_released`가 뽑힌다. 원점이 1.3인 실제 SIM에서 상태가 낡은 사건을 가리킬 수 있었다는 뜻이다.
  **고침**: 모델에 가는 사실은 전부 시행 시계로 통일한다. `PairLink.gate_view`가 게이트의 허가·마지막 사건 시각에서 `origin_s`를 빼서 넘기고(게이트 자신의 기록과
  `claim_gate.json`은 절대 시각 그대로, `CLOCKS['claim_gate_log']`에 명시), 작업 종료 시각은 전달 시각(`at_s`, 사건 뒤 한 틱)이 아니라 사건 자신의 백엔드 시각 - 원점으로
  적는다. 후자는 시험이 잡은 같은 종류의 오류다: 전달 시각을 쓰면 종료 뒤에 실제로 온 거절과 동률이 되어 종료가 이겼다(상대 불일치 시험이 `claim_rejected` 대신
  `look_around_ended`를 보여 실패). 시험: 같은 상대 사건열을 원점 0, 1.3, 2.6, 7.0에서 만들어 `own_status`가 모두 같음(세 가지 거절 순서), 변환을 빼면 원점 0과 1.3이
  달라짐(결함 재현), 게이트 자신의 기록은 절대 시각 그대로, 루프 안에서 reset 원점 0 / 1.3 / 4.9인 가짜 물리로 결과 열(`last_outcome`, 이유, 거절 횟수)이
  같음. 원점 7.0은 케이스 러너의 reset 5.0 SIM초 상한(`RESET_SIM_CAP_EXCEEDED`)을 넘어 루프 안에서 돌릴 수 없어 단위 시험으로만 덮는다.

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
   실행은 비트 단위 재현 불가, 요청·응답 원문과 해시가 재생 기록). 프록시 할당량은 스모크 12회에서 429가 없었다는 것만
   확인했다(한도 자체는 모른다). **v99 smoke1의** SIM 비용은 스터디의 `fixed_prompt_equalized.v1`(텍스트 토큰만, 이미지 0)로 계산해
   호출당 2.7~4.2 SIM초이며, 제공자가 센 실제 입력 토큰(약 6,000/호출, 이미지 2장 포함)의 약 절반만 반영했다.
   v100은 이미지 몫(장당 1,490, 위 2번)을 더해 이를 고쳤다.
6. 허가 규칙(위)은 이 층의 설계 결정이다. 다른 규칙(예: 대기 중 허가 만료)은 비교하지 않았다.
7. **(v100에서 해결: 위 1번 `own_status`)** smoke1에서 거절이 모델에 보이지 않았다. 블라인드 제어기는 두 로봇의 `Team.start`를 매 틱 `SELF_UNCERTAIN`으로 거절했지만(로봇당
   1,069회), 모델 입력에는 자기 명령 이력의 `command_issued`와 `self_belief`(confidence low)만 있어 모델은 이후 줄곧
   `continue`만 골랐다. v100은 자기 시작 거절의 닫힌 기록을 모델에 알린다. 알린 뒤 모델이 달라지는지는 실제 실행으로 아직 보지 못했다.
8. 공용 파일 충돌 가능: `scripts/run_ci_tests.py`(패턴 1줄), `tests/test_simulation_workflow_manager.py`
   (카탈로그 개수 +1, 샘플 1줄). 번들 번호는 v100 / 3.12.0(위 4번). 병합 순서에 따라 다시 정해질 수 있다.
9. **조건 이름표가 모델에 보인다**: 모델은 요청 본문의 `condition`(`no_comm` / `peer_nl`, 최상위와 `channel.condition` 두 곳)을 본다. 봉인된 스터디 계약이
   `condition`을 필수 키로 두므로 그 설계를 따른 것이다. 이름표가 더하는 **상태 정보는 없다**(같은 정보가 이미 `channel.can_send_to`와 시스템 프롬프트의
   `channel`·`messages` 블록에 있고, 정답·접촉·성공·상대 상태와 무관하다). 다만 `peer_nl`이라는 이름이 "대화를 많이 하라"는 신호로 읽히는 **작은 단서
   효과(실험자 기대 효과)** 가 있을 수 있고, 이는 처치(말할 수 있음)와 떼어 낼 수 없다. 가능성 시험(`research_result=false`)에서는 무시하고, 본 연구를 사전
   등록할 때 중립 이름표(예: `channel_a` / `channel_b`)를 쓸지 정한다(독립 재검토 2차의 권고).

## 재현

```
python3 -m scripts.run_pair_llm --condition peer_nl --expected-source-sha <커밋 SHA> --output <기본 체크아웃 outputs/ 절대 경로> \
    --cap-s 60 --synthetic-plumbing-calibration --sim-slot <슬롯> --lock-owner claude --execute
python3 -m pytest tests/test_pair_llm_inputs.py tests/test_pair_llm_runtime.py tests/test_pair_llm_case.py tests/test_pair_llm_eval.py tests/test_pair_llm_live.py tests/test_pair_llm_status.py
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

## 3단계: 실제 모델 스모크 1회 (v99, 실제 모델 12회 호출, 연구 결과 아님)

조정자 지시(2026-10-04, 사용자 결정 전달)에 따른 단 한 번의 실행이다. 소스 `ad1dda73`(실행 전 커밋·고정), 번들 `zone-pair-llm-v99`
(해시 `a8e11294…`), 조건 `peer_nl`, 시드 911, 60 SIM초, 헤드리스, 합성 보정(`--synthetic-plumbing-calibration`), `nice -n 10`,
SIM 슬롯 `sim-claude-pair-llm-v99`(종료 뒤 해제 확인). 프록시는 읽기 전용 확인만 했다(PID 1407, 감사된 소스 해시
`7d4c4e8c…`와 일치). 코호트 `pair-live-smoke-1`, 토큰 상한 300,000, 사용 75,029(25%).

| 항목 | 값 |
|---|---|
| 판정 | `COLLECTED_UNQUALIFIED`, `NOT_IN_ZONE`, 성공 false (예상된 블라인드: 운반 없음) |
| 모델 POST | 12회(완료 10 + 60 SIM초 지평선에서 잘림 2), 재시도 0, HTTP 오류 0, `RATE_LIMIT` 0 |
| 파싱·스키마 실패 | 0 (`invalid_json` 0, `model_output_rejected` 0; 응답은 ` ```json ` 울타리로 감싸여 와서 울타리 제거 뒤 통과, 12/12) |
| 토큰(제공자 사용량) | 입력 73,614 / 출력 1,042 / 합계 75,029 (호출당 입력 약 6,000, 출력 66~156) |
| 지연(wall, 호출당) | 합 46.9 s, 중앙값 4.07 s, 최대 5.94 s (아래 표) |
| 청구된 SIM 비용 | 30.1 SIM초(완료 10회: 첫 두 호출 4.1·4.2, 나머지 8회 2.7~2.8). 지평선에서 잘린 2회는 비용이 청구되기 전에 끊김 |
| 실행 시간 | SIM 60.0 s, wall 112.0 s |
| 메시지 | 2건 보냄·2건 수락·2건 전달, 거절 0 |
| 프록시 실제 설정 | 요청 `gemini-3.8-flash` temp 0.2 → 프록시가 `gemini-3.8-flash-low`(thinking LOW, temp 0.0)로 바꿈 |

| 호출 | 로봇 | 시작 SIM s | 지연 s | 입력 | 출력 | SIM 비용 s | 결정 | 요청 해시 | 응답 해시 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | r1 | 0 | 3.81 | 5980 | 156 | 4.2 | claim end_neg | `303bd708f9` | `37cf20aa4a` |
| 2 | r2 | 0 | 4.14 | 5978 | 152 | 4.1 | claim end_pos | `71bf84ecca` | `1ff9655f99` |
| 3 | r1 | 6.55 | 4.28 | 6159 | 81 | 2.8 | continue | `80d05eb445` | `525d388c22` |
| 4 | r2 | 6.55 | 4.23 | 6165 | 66 | 2.7 | continue | `244a82001b` | `8287c57a93` |
| 5 | r2 | 19.25 | 3.64 | 6169 | 66 | 2.7 | continue | `f6c976cf49` | `5819e2c97b` |
| 6 | r1 | 19.35 | 4.07 | 6164 | 81 | 2.8 | continue | `db86cc1de0` | `4a908cca19` |
| 7 | r2 | 31.95 | 3.61 | 6169 | 76 | 2.7 | continue | `b56609bc77` | `7468c71d3d` |
| 8 | r1 | 32.15 | 3.16 | 6164 | 68 | 2.7 | continue | `018e35459b` | `91e09debc2` |
| 9 | r2 | 44.65 | 4.22 | 6169 | 68 | 2.7 | continue | `4de66d57c8` | `3ca5f6cbb5` |
| 10 | r1 | 44.85 | 2.72 | 6164 | 76 | 2.7 | continue | `85a246d30c` | `2477fc83e3` |
| 11 | r2 | 57.35 | 3.09 | 6169 | 76 | - | horizon에서 잘림 | `2239de21e7` | `e27c6c9440` |
| 12 | r1 | 57.55 | 5.94 | 6164 | 76 | - | horizon에서 잘림 | `308cf81008` | `7141aafb85` |

**원문 메시지(응답 파일 그대로)와 결정**

- r1, call-0001: 행동 `claim cargoX end_neg → B`, 메시지(to r2) "cargoX를 B로 운반하기 위해 end_neg로 claim합니다."
- r2, call-0002: 행동 `claim cargoX end_pos → B`, 메시지(to r1) "cargoX 주문에 대해 end_pos로 claim 진행합니다."
- r1, call-0003(상대 메시지 수신 뒤): 행동 `continue`, 메시지 없음. 이후 호출은 모두 `continue`다.

두 로봇이 서로 보완되는 역할(end_neg / end_pos)을 골랐고 상대 메시지를 받았다. 다만 블라인드 제어기는 두 claim이 풀린 뒤(5.4 / 5.5 SIM초)
매 틱 `SELF_UNCERTAIN`으로 거절했고(로봇당 1,069회), 모델 입력에는 그 사실이 없어 `continue`만 반복했다(한계 7).
`language_report`는 두 메시지를 `non_korean`·`code_switch`로 표시했다(한글 비율 0.71 / 0.69, 영어 식별자 `cargoX`·`end_neg`가 섞임).
기록용이며 게이트가 아니다.

**원본·해시**: 기본 체크아웃 `outputs/pair-llm-v99-live/smoke1/`(요청·응답 원문 `peer_nl/llm/wire/`, 24개 파일). `artifacts.sha256.json`의
2,468개 파일을 다시 해시해 불일치 0을 확인했다. 예산 원장 `outputs/pair-llm-v99-live/budget.sqlite` sha256 `f3fd41c3bbc68a8f…`
(원장 ID `17a0b640…`, 요청 12행 모두 `response_received`). 주요 해시: `llm/model_calls.jsonl` `ea7deffd153a2561…`,
`llm/send_ledger.json` `060420a644109be2…`, `result.json` `179d4b4dc4317f5b…`. 전체 해시와 호출별 표는
`live_smoke1_summary.json`(이 디렉터리)에 있다. 이 실행은 보정이 합성이고 시각 작업자가 블라인드라서 모델 성능·운반 가능성에 대한
증거가 아니다. #363의 자기 영상 게이트 수정이 들어간 뒤의 실제 모델 실행은 별도 번들·실행으로 한다.

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
