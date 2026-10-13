# Gemma 작업 판단 재평가와 E2E18 연결 (2026-10-13)

PR #473, draft. 기반 `origin/codex/e2e18` cd456936을 merge했다. v356 접근 개선, PR #474 event_v1 및 r77 `CONFIRMED_SHARED_EVENT_PREPARE_FUTURE_EVENT_OWNER_STATE`의 prepared_v1 수정(v372)을 포함한다. 기본 경로는 그대로이며 `e2e_options.planner=gemma_v1`일 때 v373, 같은 입력의 규칙은 `rule_v1` v374이다. main/열린 PR 최대 v372 확인 뒤 #461 코멘트로 v373/v374를 예약했다. 옛 zone v357 등록은 충돌하므로 `retired/planner_v357.json`에 바이트를 보존하고 옛 실행기는 차단했다. 과거 raw/점수는 그대로 보존했다.

## 구현과 입력 경계

- 기존 multi_object/dispatch 후보·작업 API, task_planner 및 e2e 몸 스킬을 재사용한다. 호출 시작에 자기 RGB/명령 추정 위치/자기 결과/실제 받은 NL/실행 가능 후보를 동결한다. 현재 시뮬레이터·정답·파트너의 사유 상태는 입력이 아니다. r77 반례를 유지한 snapshot 시험이 통과했다.
- 각 로봇이 끝(end_neg/end_pos), 공동 운반, 직접/좌우 접근, 탐색/대기/내려놓고 다시 잡기, 정지와 우회, 자기 지도의 두 가지 유효 직각 경로를 선택한다. r1의 선택 경로를 기존 검증/컴파일기에 그대로 넘긴다. E2E18 주문은 로봇 둘이 필요한 빔 하나이므로 solo는 실행 불가로 표시한다. 단독 화물 목적지·경로·접근은 별도 24개 입력 및 기존 zone 포트에 있다. 이 빔 장면에서 solo 운반 성공을 주장하지 않는다.
- code_v1은 선택한 방향을 다른 우회로로 바꾸지 못한다. 역할 변경은 실제 접근 지점과 운반 펄스 부호에 반영한다. 운반 중 wait/regrip은 미발행 명령을 취소하고 부분 구간을 완료로 계산하지 않으며 새 공동 승인 후 내려놓기/자기 RGB 재관측/새 경로로 이어진다. 들고 있는 동안 경로 변경은 내려놓기부터 하도록 거부한다.
- 시작, 실행 완료·실패·거부, 수신 메시지, 자기 관측의 막힘/점유/물건 소실/파지 이상 및 자기 공동 작업의 15초 지연을 사건으로 사용한다. event_v1이 중복 관측을 억제한다. 한 JSON에 act,args,message,reason; 형식/실행 거부에는 한 번 재질의하고 실패·시한 초과에는 같은 정보의 강한 규칙을 기록한다.
- typed route/peer_go_ref/peer_reports 키는 Gemma 입력에 없다. 안전 실행기는 실제 NL 채널에서 받은 경로 조각과 GO/ACK/승인 문장만 해독한다. 각 조각은 600자 이내이며 실제 메시지 수/비용에 포함된다. 비공개 투표 표만으로 공동 승인할 수 없다. 일반 파트너 문장에 대한 키워드 투표를 하지 않는다. 기존 번들 채널은 변경하지 않는다.
- 기존 Mac OpenRouter Gemma 중계만 사용하며 task-planner-v1 opt-in과 소스 해시를 POST마다 확인한다. rule_v1은 같은 중계/스케줄러를 통하지만 provider 호출은 0이고 LLM_operated=false이다. 키를 읽거나 옮기는 새 경로가 없다.

## 튜닝 자료 재평가 (모든 오류를 분모에 포함)

원자료 384개 중 비애매 331, 애매 53. 같은 입력으로 강한 규칙 123/222/231을 재현했다. `tuning-recount.json`은 저장 scored.json을 직접 다시 셌고 현재 어댑터와 실제 저장 요청 1,536개의 입력 차이는 0이다. 이 자료는 프롬프트/수정에 사용한 **튜닝 자료**이며 확증 결과가 아니다.

| 조건 | Gemma /331 | 같은 입력 규칙 /331 | 애매 /53 | stale /54 | wrong /56 | fallback /384 |
|---|---:|---:|---:|---:|---:|---:|
| no_comm | 142 | 123 | 50 | 21 | 24 | 0 |
| structured | 221 | 222 | 51 | 13 | 1 | 0 |
| peer_en | 225 | 231 | 51 | 7 | 0 | 0 |
| leader_en | 225 | 231 | 51 | 6 | 0 | 0 |

단독 선택 **24/24**. 고정 신호는 목표보다 1개, NL은 6개 부족하다. NL이 더 낫다는 결론은 없다. leader는 r1이 받은 동일 영어 보고의 단일 판단이며 다회 중계 성능이 아니다. 원본의 비애매 stale은 **54개**였다(조정자의 55개와 차이). 동일 규칙 stale은 네 조건 모두17/54, wrong은 none22/56, 나머지0/56이다.

### 원인과 고친 범위

메시지 나이/자기 최근 관측과 충돌/같은 사실의 마지막 직접 관측 시각을 맥락과 미리 보기에 넣었다. 없는 직접 관측은 unknown으로 남긴다. 시간은 참·거짓의 라벨이 아니다. 오래된 보고를 약하게 취급하고 최신 자기 관측 우선/충돌 시 확인을 지시했다. 비용 미리 보기는 공개 대수식에 대한 가설별 예상 비용이며 숨겨진 실제 세계 비용이 아니다. 신뢰 가중치 .95/.35/0과 30초 기준은 휴리스틱으로, 보정된 확률이라고 주장하지 않는다.

wrong의 원자료는 신선한 high-confidence 보고이고 자기 상태는 target_or_partner_out_of_view이다. 반증 관측이 없으므로 허용 입력만으로 틀린 보고를 식별하지 못한다. 규칙도 NL wrong0/56이며 이 한계를 숨겨진 quality/world로 보정하지 않았다. 새 own-observed-fact 시험은 최신 자기 RGB의 blocked와 오래된 clear가 충돌할 때 시각/충돌을 계산하고, 관측을 빼면 unknown으로 돌아감을 확인한다.

peer wait은 **18/38→25/38**, help·uncertain은 **1/7→6/7**. 기존 wait은 오래된 near-arrival에 과하게 의존했고 help 불확실 7개 중6개에서 비용이 큰 verify를 선택했다. 공개 지연/기회/확인 비용을 후보에 주고 비교하도록 고쳤다. 남은 wait 오류에는 stale/wrong의 관측 불확실성과 비용 비교 오류가 섞이며 일반화된 해결을 주장하지 않는다.

옛 no_comm fallback34개(비애매31+애매3)의 실패 시도62개: 루트 필드 오류51(주로 reasoning/condition 추가), length8, 미종결 JSON1, extra-data2. 네 키/짧은 reason을 명시하고 정확한 거부 이유로 한 번 재질의하며 출력 상한320→768로 바꿨다. 새 원자료 no_comm fallback **0/384**. 대체 결과를 모델 정답에 더하지 않는다.

## 새 seed·문장 세트: 실행했으나 인프라 실패

생성 seed2026101302와 새 영어 템플릿을 코드 `31b08666`에 먼저 동결했다. 데이터/문장 생성 해시와 원본은 `outputs/task-planner-r2-confirmation-source-20261013/`에 있다. 모델 요청 후 문장을 바꾸지 않았다. 331+53과 단독24를 모두 시도했지만 기존 OpenRouter 중계가 HTTP402를 반환했다. 오류 969회와 예산 거부227회(단독24 포함)를 보존했다. 결제 상태를 바꾸거나 다른 모델로 대체하지 않았다.

| 조건 | 모델 /331 | fallback 포함 실행선택 /331 | 애매 모델 /53 | fallback /384 |
|---|---:|---:|---:|---:|
| no_comm | 142 | 149 | 49 | 31 |
| structured | 9 | 228 | 1 | 373 |
| peer_en | 0 | 237 | 0 | 384 |
| leader_en | 0 | 237 | 0 | 384 |

단독 모델0/24(모두 대체). 새 자료 동일입력 규칙125/228/237/237. 자세한 stale/wrong 분모는 `confirmation-failed-recount.json`에 있다. **완료된 확증 성능으로 해석할 수 없다. 중계 복구 뒤 같은 동결 자료로 새 디렉터리에 재실행해야 한다.** 실패 묶음도 지우거나 분모에서 빼지 않는다.

## 실행·비용·검증 기록

- r2 probe: 4개 no_comm+단독24, 28요청, 표시비용 $0.00386236.
- r2 전체: 1,536+단독24 판단, 1,563요청, 표시비용 $0.30938774, 미상0. 실행 소스1d01f201.
- 새 자료 실패 묶음: 실제 요청1,333, 알려진 표시비용 $0.06176448, 비용미상969. $1.99976448은 미상 호출 예약액을 포함한 예산 사용량이며 실제 청구액이 아니다. 소스31b08666.
- HTTP402 재확인 응답은 코드와 sha256만 기록했다: e3e27c70186fedb13964f601343c2bcac37205c691c26a8f63c6f8d59ed4f99b. 별도 probe는 평가 정확도 분모에 합산하지 않는다. 청구서 대조는 미확인.
- 관련 시험: native 실제 스케줄러/채널/ledger→act, 경로→역할→GO/ACK, 프레임 시각 동결, 방향 제한, 중단 시 부분 구간 무효화, 데이터 경계. 물리/API 시험이 아니다. 시험 명령·수·해시는 summary.json에 있다.
- 감독자 요청: VM3 한 대만, 다른 VM은 꺼짐 확인, 동시16, gate3.5, seed61006–61013 각각 v373/v374. 첫30SIM초 `planner-first30.json`에 호출수·토큰/SIM초·상한 예상시각·act 분포·fallback을 기록한다. 실행 전 잔액/중계 및 기존 자원/디스크 예산 조건을 감독자가 확인한다. 이 작업에서 VM을 조작하거나 Mac 물리·렌더를 실행하지 않았다. 실제 장면 결과는 아직 미확인이다.

## 참고 자료

초록·공식 프로젝트/문서로 방법을 확인했다. 전체 논문 구현/성능 재현은 미확인이다. 인용의 의미를 우리 결과로 확대하지 않는다.

- [SayCan](https://say-can.github.io/): 유용성·실행 가능성을 분리. 여기서는 코드 후보/안전 검사와 모델 선택을 분리하되 학습된 affordance 성공 확률을 구현했다고 주장하지 않는다.
- [ProgPrompt](https://progprompt.github.io/), [Code as Policies](https://code-as-policies.github.io/): 제한된 행동 API. 여기서는 실행 가능한 자유 코드를 생성하지 않고 닫힌 JSON을 검증한다.
- [RoCo](https://arxiv.org/abs/2307.04738), [CoELA](https://arxiv.org/abs/2307.02485), [SMART-LLM](https://arxiv.org/abs/2309.10062): 대화·배정. 비공개 파트너 상태를 공유하지 않는 기존 채널을 유지한다.
- [Inner Monologue](https://arxiv.org/abs/2207.05608), [Reflexion](https://arxiv.org/abs/2303.11366): 실행 피드백·실패 기억. 짧은 자기 실행 기억만 넣고 평가자 정답 피드백은 넣지 않는다.
- [Uncertainty-of-Information Scheduling](https://arxiv.org/abs/2102.06384): 보고 나이와 정보 불확실성은 구별해야 한다. 나이만으로 참/거짓을 판정하지 않는다.
- [Online Replanning in Belief Space](https://arxiv.org/abs/1911.04577): 부분 관측의 확인·재계획과 기대 비용. 공개 비용 미리 보기에 한정해 적용했다.
- [Confidence is Not Universal](https://proceedings.mlr.press/v306/jang26a.html): 과제에 따른 신뢰 보정의 한계. 가중치가 보정된 신뢰라고 부르지 않는다.
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs): 조사했지만 현재 Gemma endpoint 지원은 미확인이라 response_format을 켜지 않았다. 실제 개선은 프롬프트/출력 여유/닫힌 파서이다.
