# 설계 노트: 짐으로 이어진 구간의 내려놓기·재고정을 LLM 대화로 풀기

상태: **설계만, 코드 없음, 실행 없음.** 작성 2026-10-04(Claude Sonnet 5.5, #371 담당). 조정자가 같은 날 설계를 승인했고
아래 "결정 기록"의 네 가지를 정했다. 이 문서는 #371(`experiments/2026-10-03-pair-llm-viability/`)의 일부이며 연구 결과가 아니다.

사용자 결정(2026-10-04): "두 로봇이 짐으로 이어져 있는 부분은 실제 llm을 써서 해결하는 게 어떨까? 지금 상황에서도 llm통신을 써도 돼."

## 결정 기록 (조정자, 2026-10-04 — 사용자 결정이 아니라 조정자 선택)

- **(a)** 정지 대기는 기존 값 `CHECKPOINT_REOBSERVE_S`(8초)를 그대로 쓴다. 새 문턱은 만들지 않는다.
- **(b)** NL 발화 상한을 로봇당 3 / 전체 6에서 **6 / 12로 올린다. peer_nl에만 적용**한다(no_comm은 글 통로가 닫혀 있어 상한이 의미 없다).
  이유: 정지가 많은 경로에서 3/6이 먼저 닿고, 글 자체가 이 연구가 재는 행동이라 상한이 연구 대상을 깎으면 안 된다.
  이 변경은 레지스트리 `decision_limits`와 번들 해시가 바뀌므로, 조정자가 정한 900초 실제 호출 상한·호출 한도 36/72와 **같은 리베이스 커밋**에서 적용하고
  README·번들에 이유와 함께 적는다. 코호트 토큰 상한(약 1.1M)은 그대로이며 6/12 기준 최악치는 6절에 다시 계산했다.
- **(c)** `grip_event`는 첫 E2E에서 **기록만** 한다(사용자 10/3 결정 "첫 E2E에서 grip 감시는 기록만"). 인터페이스 자리(slot)는 남기되
  제어·LLM 입력으로 승격하지 않는다. 자기 감지 후 신호는 E2E 이후다.
- **(d)** 시험 균형 점검의 규칙 조건 성공률 범위 **5~95%**는 파일럿 기준으로 받아들였다(조정자 선택). 벗어나면 **환경 난이도(경로·문 여유 같은
  사전 등록 값)만** 조정하고, 조건별로 손대지 않는다.

## 0. 먼저 확인한 사실
- **현재 규칙 조건의 성공률은 0%다.** #363 단계 검사에서 두 로봇이 운반 첫 다리 끝 정지에서 멈춘다. σ 예산(50 mm / 3°)을 넘은 뒤에 이어질
  내려놓기→열기→둘러보기→다시 잡기→들기 재고정이 아직 없기 때문이다(다른 작업자가 만들 예정). 이 문서는 그 상태기계 **위에 얹는 결정 층**이다.
  상태기계를 다시 만들지 않고 걸이(hook)만 요청한다.
- 운반은 최대 8개 다리(`MAX_SEGMENTS`=8)다. 다리 끝은 두 로봇이 같이 서는 정지 약속(barrier)이고 고정 상태 채널(20 Hz)로 맞춘다.
- 이 채널의 열거 상태(`uncertain`, `stopped`, `put_down`, `done`, `abort` 등)에는 `RELOOKING`이 없다. 새 상태는 공용 프로토콜 변경이므로
  **새 상태는 만들지 않는 것**을 전제로 한다.
- 봉인된 스터디의 결정 근거에 이미 `own_belief`(자기 위치 추정)가 있다. 자기 σ 요약을 모델에 주는 것은 새 허용이 아니다.
- 기존 LLM 층의 `ClaimGate` 패턴(모델이 요청 → 게이트가 검사 → 거절 이유는 닫힌 `own_status`로 회신)을 새 결정에도 쓴다.

## 1. 조건별 메커니즘 (번들에 명시)

| 조건 | 내려놓기·재고정 결정 | 상대에게 알리는 길 | LLM 호출 |
|---|---|---|---|
| rule | 제어기가 σ 규칙으로 결정(예산 초과면 내려놓기, 둘러본 뒤 σ 안이면 다시 잡기, 아니면 다시 둘러보기, 최대 2회) | 고정 상태 채널(`uncertain` 등) | 0 |
| no_comm | 로봇마다 LLM이 정지 지점에서 자기 σ 요약·자기 영상·자기 `own_status`로 결정 | 고정 상태 채널만, 같은 열거 상태, 글 없음 | 있음 |
| peer_nl | no_comm과 같고 상대에게 글(≤240자, 로봇당 6 / 전체 12)도 보냄 | 고정 상태 채널 + 글 | 있음 |

- **중앙집중(central) 조건**을 넣는다면 조건 하나가 두 로봇의 같은 명령을 내리고 인터페이스는 같다. 이 PR의 세 조건에는 해당 없다.
- 번들에 `carry_decision_mechanism` 필드로 `sigma_rule` / `llm_own_status_fixed_wire` / `llm_own_status_fixed_wire_plus_nl`을 적는다.
- 모든 조건에서 정지마다 "누가 결정했나"(`decided_by`: `llm` 또는 `rule_default`)와, 모델에는 보이지 않는 그림자 규칙의 결정(`rule_would_do`)을 남긴다.

## 2. 시간 규모 (LLM이 닫지 않는 것)
- 50 ms 힘·속도 루프, 100 ms 제어 틱, 50 ms 상태 심장박동은 전부 제어기 몫이다.
- 한 번의 LLM 호출은 SIM 시간으로 약 3.8~4.2초이고, 호출 사이클은 놀 때 약 13.8초, 작업 중 약 64초다(다시 묻기 10초 / 60초 + 호출 비용).
- LLM 결정은 **네 곳에서만** 일어난다.
  - (A) 청구.
  - (B) 다리 시작(GO) 때 "다음 정지에서 내려놓을지 계속할지"를 미리 정해 보관(latch)한다. 정지에서 호출이 막 시작되면 답이 8초 안에 못 오는 문제를 피하기 위해서다.
  - (C) 정지에서 그 결정을 확인하고, 중간에 상대 글이 왔으면 한 번 더 묻는다. 정지 대기는 8초이며 시간이 지나면 `rule_default`가 적용된다.
  - (D) 내려놓고 둘러본 뒤 다시 잡기·다시 둘러보기·포기를 고른다.
- **긴급 정지는 제어기 몫**이다. 중간에 미끄러짐·밀림이 생기면 기존 `abort`/`stopped` 상태가 즉시 처리한다. 글은 "왜 멈췄나"를 알리는 설명일 뿐 정지 수단이 아니다.

## 3. 결정 어휘 (닫힘, 위치 값 없음)
- **정지에서**: `continue` / `set_down` / `wait`
  - `set_down`은 정지에서만 받아들인다. `wait`는 정지당 한 번만 허용한다.
  - 예산 초과면 `continue`는 거절(`OVER_BUDGET`)하고 제어기가 규칙대로 내려놓는다.
- **둘러본 뒤**: `regrasp` / `look_again` / `give_up`
  - `regrasp`는 자기 둘러보기 σ가 예산 안일 때만 제어기가 받는다.
  - `give_up`은 청구를 풀어 작업을 끝낸다.
- **합치기 규칙(OR)**: 둘 중 한 로봇이라도 `set_down`을 내면 같이 내려놓는다. 규칙 조건의 `uncertain`과 같은 동작이다.
- 기존 `ClaimGate`처럼 한 번 쓰는 보관식(latch) 명령이며 거절 이유는 닫힌 어휘로 `own_status`에 돌려준다.

## 4. NL로 위치 추정 공유: 보수적 사용 규칙

**근거**
- 두 로봇은 같은 첫 고정, 같은 명령 경로, 같은 미끄러짐으로 오차가 상관된다. 교차 공분산을 모르는 채 상대 추정을 독립 측정으로 합치면 이중 계산(data incest)이 되고 결과는 과신(inconsistent)이다(Bahr·Walter·Leonard 2009).
- 정석 해법은 교차 공분산을 장부로 관리하는 방식(Roumeliotis·Bekey 2002, Kia 외 2016, Luft 외 2018)이다. 상관을 모를 때는 공분산 교차(CI) 같은 보수적 합치기를 쓴다(Julier·Uhlmann 1997, Li·Nashashibi 2013, Carrillo-Arce 외 2013, Chang 외 2022).
- 글에는 공분산이 없고 출처를 장부로 관리할 수도 없으므로 모델이 말하는 "확실하다"를 σ로 쓸 수 없다. LLM 확신은 과신하기 쉽다는 점은 KnowNo(Ren 외 2023)가 보였다.

**규칙**
1. **합치기 금지**: NL 경로는 LLM 결정에서 끝난다. 추정기(PF)에는 상대 글에서 온 값이 들어가지 않는다. 결정 어휘에 위치 값이 없어서 구조적으로 막힌다.
2. **보수 방향만**: 상대 글은 더 보기·더 기다리기·더 일찍 내려놓기 쪽으로만 행동을 바꿀 수 있다. 확인을 건너뛰는 쪽은 없다. 예산 초과 `continue` 거절과 `regrasp`의 σ 검사가 제어기에 있어서 글이 이를 못 뚫는다.
3. **재확인 계기로만 사용**: 상대 글이 자기 믿음과 어긋나 보이면 `look_again`이나 `set_down`을 고른다. 평균을 내지 않는다.
4. **감사**: 모든 글을 그 시점의 자기 σ 요약과 함께 남긴다. 평가 전용 정답과 나중에 비교해 오보율을 센다. 이 값은 제어로 되돌리지 않는다.
5. **프롬프트**: 구체 숫자보다 "무엇이 보이는지·σ가 어느 수준인지"를 말하게 한다.

**한계(정직하게)**: 이 규칙에서 NL은 정확도를 높일 수 없고 **조율(기다림·재확인 시점)만** 돕는다. 구조화된 위치+σ+출처 ID 메시지를 CI로 합치는 별도 조건은 첫 E2E 이후 과제다.

## 5. 천장·바닥(ceiling/floor) 균형

**분석적 추정 (측정 아님)**
- 규칙 조건은 재고정 사이클 k번을 모두 성공해야 한다. #363 작성자는 전체 경로를 351–517초, 재고정 1회 하한을 약 41.4초로 추정했다(README "사례 시간 상한 300 → 900"). 이를 바탕으로 한 저자(Claude)의 환산은 k≈3–5다.
- 사이클당 성공률 q를 가정한 q^k:

| q | k=3 | k=4 | k=5 | k=7 |
|---|---|---|---|---|
| 0.80 | 0.51 | 0.41 | 0.33 | 0.21 |
| 0.90 | 0.73 | 0.66 | 0.59 | 0.48 |
| 0.95 | 0.86 | 0.82 | 0.77 | 0.70 |

- q가 0.8~0.95이면 규칙 조건이 중간대(약 33~82%)에 놓인다. **q 실측이 없어서 확정은 불가능하다.** 재고정 상태기계가 생긴 뒤 단계 검사로 재야 한다.

**바닥이 구조적으로 0이 되지 않게 하는 장치**
- LLM이 침묵하거나 틀려도 정지 대기(8초) 끝에 `rule_default`가 실행된다.
- 예산 초과는 제어기가 강제로 내려놓는다.
- 상대에게 알리는 길(고정 상태 채널)이 규칙 조건과 같다.
- no_comm이 규칙보다 낮아지는 경로는 LLM이 실제로 해를 끼치는 경우뿐이다. 불필요한 선제 내려놓기로 시간·재고정 위험을 늘리거나, 호출 36회를 소진해 `CALL_BUDGET_EXHAUSTED`가 되는 경우다.

**천장 위험**
- 정지 결정은 σ의 함수에 가까워서 LLM이 규칙을 이길 여지가 작다. 성공률은 세 조건이 비슷하고 시간·호출에서 갈릴 가능성이 크다.
- LLM에게 실제 재량이 남는 곳은 세 곳뿐이다.
  - σ 예산 안의 정지에서 선제 내려놓기를 할지(σ 추세·위치 고정 나이·바닥 영상·상대 글).
  - 둘러보기 결과가 애매할 때 `look_again`과 `give_up` 중 고르기.
  - 한쪽 둘러보기만 실패했을 때 상대를 기다릴지.

**파일럿 기준과 절차(조정자 선택 (d))**
- 단계 검사(재고정 단계, SIM 시간 병렬 격자, seed 20개 안팎)로 규칙 성공률과 q를 먼저 잰다.
- 규칙 성공률이 **5% 미만이거나 95%를 넘으면** 환경 난이도(경로·문 여유 같은 사전 등록 값)만 조정한다. 조건별로 손대지 않는다.
- 첫 E2E(조건당 seed 1개)로는 비율을 알 수 없고 생존 가능성(viability)만 본다.

## 6. 호출·토큰 예산 (Plan A 36회/로봇, 72회/케이스; 발화 상한 6/12 반영)

**로봇당 호출 수 추정**
- 청구 2, 정지 결정 7(다리 8개 기준 정지 최대 7), 재고정 사이클 x2 (기대 4회 = 8, 최악 5회 = 10), 작업 중 60초 다시 묻기 약 8.
- peer_nl은 상대 글 하나가 받는 쪽 호출을 한 번 깨운다(보내는 쪽은 같은 답에 글을 실어 보내므로 추가 호출 없음). 상한 6/12이면 받는 글 최대 6 → 호출 최대 +6(기대 약 +4).
- 합계: no_comm 기대 25 / 최악 27(=2+7+10+8), peer_nl 기대 29 / 최악 33(=2+7+10+8+6). 36 안이지만 peer_nl 최악의 여유는 3회뿐이다.

**케이스·코호트 토큰** (호출당: 기대 6.5k, no_comm 최악 7.0k; peer_nl 최악은 받은 글이 프롬프트에 쌓여 7.5k로 잡음)

| | 호출/케이스 | 토큰 |
|---|---|---|
| no_comm 기대 | 약 50 | 약 325k |
| peer_nl 기대 | 약 58 | 약 400k (6.9k/호출) |
| no_comm 최악 | 54 | 약 378k |
| peer_nl 최악(받은 글 6) | 66 | 약 495k |
| 두 LLM 조건 기대 합계 | | **약 0.73M** |
| 두 LLM 조건 최악 합계 | | **약 0.87M** (코호트 상한 1.1M의 79%) |
| 호출 상한(72)에서 7.5k/호출 | 72 | 540k/케이스, 두 조건 1.08M (상한의 98%) |

- 코호트 상한 1.1M은 호출당 약 7.6k까지 호출 상한에서도 버틴다. 이를 넘으면(약 8k/호출) 1.15M이 되어 상한을 넘는다. 상한은 바꾸지 않는다(조정자 결정).
- 케이스당 토큰 상한 약 500k(72 x 7,000)는 호출 상한 도달 + 최대 프롬프트(540k)보다 약간 낮아, 극단 경우에는 호출 한도보다 토큰 상한이 먼저 닫힐 수 있다. 기록에 남기고 값은 바꾸지 않았다.
- 정지 결정 대기로 SIM 시간이 늘어난다(최대 7정지 x 8초 = 약 56초). 경로 추정(351–517초)에 더해도 900초 안에 들어간다.
- 위 추정은 smoke1 실측(호출 12회, 평균 6,252 토큰, 6,130–6,432)에서 외삽한 것이며 새 설계의 실측이 아니다.

## 7. #363 제어기가 노출해야 할 인터페이스 목록

**이벤트(제어기→LLM 층, 자기 것만, 실행기 이벤트로 `scheduler_trigger` 지정)**
1. `carry_leg_started {seg, n_segs, planned_leg_s}`: 결정 지점 (B)에서 호출을 깨운다.
2. `carry_stop_reached {seg, high, over_budget, sigma_band, receipt}`: 두 로봇이 정지 약속에 선 시점에 발행하고, 보관된 결정을 최대 `CHECKPOINT_REOBSERVE_S`(8초)까지 기다린다.
3. `setdown_started/completed {seg}`, `relook_result {level, sigma_band}`, `regrasp_result`, `carry_resumed`: 재고정 진행 상황.
4. `pose_uncertain`(이미 있음): 닫힌 σ 띠를 같이 준다.
5. `grip_event`(자기 영상으로 감지한 파지 손실): **자리만 둔다.** 첫 E2E에서는 기록만 하고 제어·LLM 입력으로 승격하지 않는다((c)).

**읽기(자기 것만, `own_belief`)**
6. 닫힌 요약 `{sigma_xy_band, sigma_yaw_band, fix_age_bucket, dr_budget_remaining_bucket, over_budget}`: 띠로 준다. 수치 위치·정확한 임계값은 주지 않는다.

**명령(LLM 층→제어기, 한 번 쓰는 보관식, 거절 가능)**
7. 정지에서 `carry_decision(continue|set_down|wait)`.
8. 둘러본 뒤 `post_look_decision(regrasp|look_again|give_up)`.
9. 시간 초과 기본값은 규칙이다(`rule_default`, 기록에 남김).

**상대 알림**
10. 새 상태 없이 기존 `uncertain`·`not_ready`·`stopped`·`put_down`·`done`/`abort`만 쓴다. 두 로봇의 요청은 OR로 합친다.

**기록(평가 전용 포함)**
11. 정지마다 `{조건, decided_by, 결정, σ 띠, rule_would_do, 지연, 본 글 ID}`를 남긴다.
12. 오차는 평가 전용 정답으로 정지마다 따로 기록한다. 모델이나 제어기에는 되돌리지 않는다.

**불변 조건**
- 제어기는 LLM 응답을 기다리며 틱을 멈추지 않는다(한 번 쓰는 보관식).
- 접촉·성공·시뮬레이터 상태는 전달하지 않는다.
- 네 조건의 고정 상태 채널은 동일하다.

## 8. 위험·남은 결정
- #363의 재고정 상태기계가 없으면 LLM 층을 시험할 수 없다. HIGH 내려놓기 작업자가 1f7fb800 이후로 diff를 옮기는 중이다.
- 번들 번호: 리베이스 때 main과 열린 PR 전체에서 최댓값을 다시 확인해 새 ID를 쓴다(AGENTS.md 번호 예약).
- 이 설계의 코드(정지 결정 어댑터, 가짜 제어기 시험)는 #363 새 SHA 리베이스 뒤에 별도 커밋으로 만든다. 지금 이 PR에는 설계 문서만 있다.
- 조건 이름표(`no_comm`/`peer_nl`)가 모델에 보이는 문제는 README 위험 9에 이미 적었다.

## 참고 자료 (확인 단계 표기)
- 확인(서지, 검색 결과 대조): Bahr·Walter·Leonard, "Consistent cooperative localization", ICRA 2009, pp. 3415–3422. 초록 요지는 검색 요약으로 확인했고 PDF는 읽지 못했다(본문 미열람).
- 확인(서지): Kia·Rounds·Martinez, "Cooperative Localization for Mobile Agents: A Recursive Decentralized Algorithm Based on Kalman-Filter Decoupling", IEEE Control Systems Magazine 36(2):86–101, 2016. arXiv 1505.05908.
- 확인(서지): Luft·Schubert·Roumeliotis·Burgard, "Recursive decentralized localization for multi-robot systems with asynchronous pairwise communication", IJRR 37(10):1152–1167, 2018, doi 10.1177/0278364918760698. 본문 미열람.
- 확인(서지): Julier·Uhlmann, "A non-divergent estimation algorithm in the presence of unknown correlations", ACC 1997, pp. 2369–2373.
- 확인(서지): Li·Nashashibi, "Cooperative multi-vehicle localization using split covariance intersection filter", IEEE ITS Magazine 5(2), 2013, doi 10.1109/MITS.2012.2232967.
- 확인(서지): Carrillo-Arce·Nerurkar·Gordillo·Roumeliotis, "Decentralized multi-robot cooperative localization using covariance intersection", IROS 2013, pp. 1412–1417, doi 10.1109/IROS.2013.6696534.
- 확인(서지): Chang·Chen·Mehta, "Resilient and consistent multirobot cooperative localization with covariance intersection", IEEE T-RO 38(1):197–208, 2022(IEEE 온라인 게재 2021). arXiv 2108.08789.
- 확인(서지): Fox·Burgard·Kruppa·Thrun, "A probabilistic approach to collaborative multi-robot localization", Autonomous Robots 8(3):325–344, 2000. Fox·Burgard·Thrun, "Active Markov localization for mobile robots", Robotics and Autonomous Systems 25:195–207, 1998. Howard·Matarić·Sukhatme, "Putting the 'I' in 'team': an ego-centric approach to cooperative localization", ICRA 2003, pp. 868–874.
- 확인(서지): Roumeliotis·Bekey, "Distributed multirobot localization", IEEE T-RA 18(5), 2002(#363 작성자가 확인한 표기를 인용).
- 확인(서지, 요지는 검색 요약): Ren 외, "Robots That Ask For Help: Uncertainty Alignment for Large Language Model Planners"(KnowNo), CoRL 2023, arXiv 2307.01928. Huang 외, "Inner Monologue", CoRL 2022, PMLR 205:1769–1782. Mandi·Jain·Song, "RoCo: Dialectic Multi-Robot Collaboration with Large Language Models", ICRA 2024. Zhang 외, "Building Cooperative Embodied Agents Modularly with Large Language Models"(CoELA), ICLR 2024.
- 제목만 확인(가정에 쓰지 않음): "Large Language Models for Multi-Robot Systems: A Survey", arXiv 2502.03814. "Multirobot cooperative localization based on event-triggered mechanism", Intelligent Service Robotics 2025(Springer).
- 확인 불가: scite 연구 도구는 유료라 쓰지 못했고, 위 서지는 웹 검색 결과로만 대조했다.
- 미확인(인용 안 함): Bar-Shalom 외 2001의 NEES 일관성 검정. 이 설계는 NEES 검정에 의존하지 않는다.
- 우리 코드·기록: `harness/zone_pair_status.py`(고정 상태 열거), `harness/zone_event_scheduler.py`(다시 묻기 10·60초), `harness/zone_study_protocol.py`(결정 근거 `own_belief`), `harness/pair_llm_runtime.py`(`ClaimGate`), #363 `harness/zone_pair_highpose_runtime.py`와 `experiments/2026-10-03-pair-carry-highpose/README.md`(DR 영수증·사례 상한 900초·재고정 추정치), 이 실험의 v99 smoke1 기록.
