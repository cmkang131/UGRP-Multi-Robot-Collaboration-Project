# E2E18 r76 호출 폭주: event_v1 후보 (2026-10-13)

기반 `f0907d7ff02441357b8cd0259b3cc21c8ee91777`, 작업 브랜치 `claude/e2e18-callrate`.
최신 base `b9d6e2a3` 통합 후 관련 시험 **78/78 통과**(4파일; 기존 3파일+충돌한 speech_context 시험).
물리·렌더·새 모델 호출·VM 접속 0. 이 기록은 호출/프롬프트 오프라인 검증이다.
실제 600 SIM초에서 40호출·20만 토큰 이하 달성 및 공동 파지/운반은 미확인이다.

## 변경과 경계

- `e2e_options.dialogue_call_policy=event_v1`, CLI `--dialogue-call-policy event_v1`.
  off는 기존 호출·프롬프트·채널 동작이다. 네 조건 모두 같은 admission 함수를 사용한다.
- 스케줄러가 시간·예산을 확인한 뒤, 호출 생성·hold·HTTP 이전에 사건을 검사한다.
  처음 상태, 현재 경로 제안/승인·claim·GO/ACK 참조/창 변화, 자기 단계/접근 상태·RGB 파지 가설 변화,
  실제 수신된 새 내용만 호출할 수 있다. 시간·이미지 ID·명령 횟수·메시지 ID 증가 자체는 사건이 아니다.
- 자기 상태 hash와 지난 호출에서 본 사실이 같으면 skip. 관찰 사건은 로봇마다 **15 SIM초** 간격이다.
  시간 제한 중 변화는 예정 시점에 재검사하며, 그때 상태가 돌아왔으면 호출하지 않는다.
  프로토콜·새 위험/명시적 WAIT와 열린 투표 창의 자기 파지 가설 변화는 이 15초 제한을 우회한다.
  기존 공통 스케줄러의 최소 간격/한 로봇 outstanding 1개는 유지한다.
- 15초는 r76의 2–4초 반사적 주고받기를 줄이는 DEV 설계값이다. 10초 RGB 유효기간보다 길므로
  GO/ACK·안전은 반드시 예외로 둔다. 문헌에서 보장한 최적값이 아니며 빈번한 실제 새 사건이 있으면
  40호출을 넘을 수 있다. 40회는 호출을 잘라내는 cap이 아닌 검증 목표다.
- 영어 단순 확인/관찰 filler와 content 중복을 제거한다. 반복 메시지가 번갈아 와도 새 사실로 세지 않는다.
  새 숫자·방향·부정은 보존한다. 일반적인 모든 자연어 동의어의 의미 동등성은 미확인이다.
  모르는 내용은 새 사실 후보로 남기는 보수적 어휘 필터이며 다른 모델로 분류하지 않는다.
- 송신 관찰에도 중복·15초 제한을 적용한다. 경로 계약, 승인, claim, GO/ACK, 새 위험/WAIT는 보존한다.
  억제된 생성 문장에는 rejection receipt를 하나씩 남겨 호출/생성 토큰·SIM 비용을 지우지 않는다.
- sent IDs는 `sent_count`, 명령·결정 이력은 각각 최대 최근 8개, 수신 대화는 최대 최근 6개+나이.
  승인 대기 중인 실제 수신 경로 제안이 최근 창 밖이면 `active_route_report` 하나로 별도 보존한다.
  중복 예시/피드백/경로 계약 예시는 제거하고, 승인 후 자기 경로 제안은 재전송하지 않는다.
- system+user 텍스트 상한은 **14,000 UTF-8 bytes 및 frozen tokenizer 4,500 tokens**다.
  오래된 선택적 기록부터 줄이며, 필수 계약/규칙만으로 초과하면 명시적 오류로 중단한다.
  이미지와 출력 토큰은 이 텍스트 상한에 포함되지 않는다. upstream Gemma speech에도 상한을 검사한다.
- `e2e-progress.json.token_progress`에 누적 charged/known tokens, unknown 건수, tokens/SIM초,
  현 누적 평균 속도에서 cap 도달 SIM 시각을 기록한다. 600초 미만이면 `TOKEN_RATE_WARNING.json`을 쓴다.
  unknown usage는 기존 보수적 예산 charge로 남는다. 실행당 **800,000 cap 유지**.
- 모든 admission/skip와 송신 억제 이유는 실시간 `dialogue-call-policy.jsonl`, 최종
  `llm/dialogue_call_policy.json` 및 scheduler decision events에 남는다. 정답/평가 상태는 입력으로 쓰지 않는다.

## 재생 결과

로컬에는 r76 **2/32 실행**의 원장이 있으며 요청 본문은 **21/205 호출**만 있다.
`r76-sample-replay.json`에 파일별 SHA-256, 판정, 원래/새 프롬프트 크기와 원장 합계가 있다.
표본에는 자기 제어기 단계가 없으므로 이를 만들어 넣지 않았다. 표본 간 빠진 호출/사건이 있고,
이전 실행에서 받은 응답을 유지한 반사실 입력 재생이므로 전체 호출 절감률로 외삽하지 않는다.

| 로컬 실행 | 전체 원장 호출 / known provider tokens | 요청 표본 | 허용 / 표본 | 기존 → event+compact 텍스트 proxy tokens |
|---|---:|---:|---:|---:|
| v353 seed61006 | 109 / 805,876 | 11 | 5/11 | 74,530 → 14,311 |
| v355 seed61010 | 96 / 652,195 | 10 | 4/10 | 65,167 → 12,284 |

합계 표본 **21→9호출(57.1% 감소)**, 텍스트 **139,697→26,595(81.0% 감소)**.
새 provider 청구량이 아니다. 위 proxy 토큰은 이미지·출력을 제외한다.
전체 205회 원장 합계는 1,458,071 known provider tokens이며 32회 전체 합계가 아니다.

600 SIM초 실제 스케줄러+프로토콜 fixture는 같은 사건열에서 off/event_v1을 각각 실행한다.
반복 report trigger는 3초마다 들어가고, route/claim/GO/ACK는 기존 검증기를 통과한다.
토큰은 fixture의 고정 응답 계량값(호출당 3,170)이며 실제 Gemma 토큰 측정과 구분한다.

| 조건 | off 호출 → event_v1 | fixture tokens off → event_v1 |
|---|---:|---:|
| no_comm | 61 → 3 | 193,370 → 9,510 |
| structured | 61 → 17 | 193,370 → 53,890 |
| peer | 61 → 17 | 193,370 → 53,890 |
| leader | 62 → 18 | 196,540 → 57,060 |

비용 목표 통과 **4/4**, 경로 제안·승인 및 양쪽 claim **3/3 통신 조건**,
GO/ACK **12/12 투표** 보존. no_comm은 경로 승인 불가를 유지한다.
off 호출 수는 기존 actor당 30회 시험 한도에 제한됐으므로 무제한 기준선으로 해석하지 않는다.
별도 시험으로 경로 제안 창 밖 보존, 위험/WAIT 예외, 부정어, 교대 중복,
송신 억제 receipt, health 경고 파일과 upstream 상한을 확인한다.

재생 명령:
```sh
PYTHONPATH=. python3 scripts/replay_e2e18_callrate.py --raw outputs/e2e18-callrate/r76 --output /tmp/r76-sample-replay.json
python -m pytest -q tests/test_e2e_dialogue_call_policy.py tests/test_e2e_dialogue_decider.py tests/test_zone_event_scheduler.py
```
원본은 지정 로컬 `outputs/e2e18-callrate/r76/` 경로에 유지한다. 원격 보관 여부를 새로 확인한 것은 아니다.

## 번들 및 감독자 인계

main과 열린 PR 원격 브랜치들의 `harness/rgb_execution_bundle.py` 및 workflow 등록 파일 전체를 확인했다.
최댓값 v356(접근/동작 개선 #471)을 보존하고 #461 코멘트로 **v357–v360**을 처음 예약했으나 동시 작업의 speech_context 등록이 먼저 들어왔다.
`b9d6e2a3`의 최신 base를 통합하고, 재검사한 최댓값 v360 다음 **v361–v364**로 옮겼다.
초기 후보는 실행 0회이며, 기존 v357–v360의 파일을 그대로 보존했다.

| 새 번들 | 부모 |
|---|---|
| v361 | v352 |
| v362 | v353 |
| v363 | v354 |
| v364 | v355 |

각 부모 인자에 `--dialogue-call-policy event_v1`만 추가한다. 4개 모두 표준 workflow에 등록했다.
부모의 나머지 옵션과 모델/물리 구성을 그대로 검증한다. 새 실행 성공으로 과거 결과를 승계하지 않는다.
감독자 요청: **각 번들 × seed61006–61013 = 32개**, VM3·VM4 각16개,
30 SIM초 속도 게이트 **3.5**, 같은 80만 cap. 이 작업은 제출 요청만 남기며 VM을 직접 조작하지 않는다.

## 참고 자료

2026-10-13 원문/저자 공개 자료 열람. 아래 절감률을 우리 시스템에 적용한 값으로 사용하지 않는다.

- [Nowzari, Garcia, Cortes: Event-Triggered Communication and Control of Networked Systems for Multi-Agent Consensus](https://arxiv.org/abs/1712.00429): 필요 사건에서 통신하는 표준 접근의 개요 확인. 여기서는 연속 상태 오차 임계값 대신 허용된 자기 단계·프로토콜·수신 내용 변화로 구현한다. 논문의 합의 안정성 보장을 가져온 것은 아니다.
- [CoELA 논문](https://arxiv.org/abs/2307.02485), [저자 구현 LLM.py](https://github.com/UMass-Embodied-AGI/CoELA/blob/master/tdw_mat/LLM/LLM.py): 최근 action 10개·dialogue 3개 사용과 직전 행동이 message일 때 새 message 생성 생략, usage 누적 코드를 확인했다. 이번 후보는 최근 8/6개와 별도 필수 경로 보존으로 조정했다.
- [RoCo 논문](https://arxiv.org/abs/2307.04738), [저자 프로젝트](https://project-roco.github.io/): 협의→하위 계획→실행/피드백 구조를 확인했다. 우리의 15초 간격·토큰 절감률을 검증하는 자료는 아니다. dialog_prompter.py 직접 열람은 실패해 해당 구현 세부는 미확인이다.
- [AgentDropout (ACL 2025)](https://arxiv.org/abs/2503.18891), [AgentPrune (ICLR 2025)](https://arxiv.org/abs/2410.02506): 초록에서 중복 에이전트/통신 그래프 제거를 통한 토큰 비용 관리 접근을 확인했다. 네 조건의 topology를 유지해야 하므로 그래프/로봇 제거는 채택하지 않고 반복 사건 억제만 적용했다. 해당 벤치마크 성능과 재현은 미확인이다.
