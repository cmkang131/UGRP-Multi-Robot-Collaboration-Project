# 한국어 자연어 로봇 대화의 팀 효율 효과 — 평가 설계 문헌 조사 (2026-09-28)

- 작성: Claude (Opus 5.5), 브랜치 `claude/nl-dialogue-eval-survey`, 기준 `origin/main` `d5bd208e`
- 목적: 본 연구(무통신 `no_comm` / 자유 한국어 동료 대화 `peer_ko` / 순환 지휘 `leader_ko` / 정형 메시지 `structured`)의 평가 설계를 선행 연구에 맞춰 보강한다. 전역 지침 "막히면 레퍼런스 먼저"에 따른 조사 기록이다.
- **이번 작업은 SIM·pytest·모델 호출을 하지 않았다(배터리 제약).** 새 실험 결과가 없으므로 TensorBoard 스냅샷도 만들지 않았다.
- 숫자 규칙: 논문 숫자는 논문(또는 도구가 추출한 논문 본문)에 있는 값만 옮겼다. 우리가 계산한 값(효과크기 변환, 검정력)은 **[계산]**으로 표시했다. 검정력은 모두 **추정치**다.
- 읽은 수준: 각 문헌마다 **전문**(본문을 직접 읽음), **전문·도구 요약**(arXiv HTML 본문을 WebFetch 요약기로 읽음, 숫자는 요약기가 본문에서 인용한 값), **초록**(초록/소개 페이지만)으로 표시했다. 초록만 본 문헌에서는 설계 세부를 주장하지 않는다.

---

## 0. 요약

### 권고 5개
1. **4조건 본연구 사전 등록을 따로 고정한다.** 주 대비는 세 개로 한다: H1 `peer_ko − no_comm`(자연어 대화 효과), H2 `peer_ko − structured`(자연어 대 정형), H3 `leader_ko − peer_ko`(조직 구조). Holm으로 보정한다. 시나리오별 방향 가설도 함께 적는다(예: s1 대조군은 효과 0 또는 비용 손해, s2·s5는 정보 이득, s6는 H2만 해당).
2. **주 지표는 실패를 분모에 남기는 SIM 시간 지표 하나로 정한다.** 기본은 기존 `par_makespan_sim_s`(PAR-2)다. 성공률은 반드시 같은 표에 함께 보고한다. 파일럿에서 조건을 가린 합산 성공률이 낮으면(예: < 0.3) PAR이 벌점에 지배되므로 `delivery_rate`(CoELA transport rate와 같은 부분 점수)로 바꾼다. 이 전환 규칙은 조건별 결과를 보기 전에 고정한다.
3. **블록은 (시나리오, seed)이고, 짝 비교를 최소 36블록(시나리오당 6 seed, 144 시행)으로 설계한다.** [계산] 18블록(현재 시나리오당 3 seed)의 최소 검출 효과는 dz ≈ 0.70(α 0.05) / 0.84(Holm 3개 최악)다. 문헌의 조직·대화 효과 d ≈ 0.27–0.65로는 부족하다. 18블록은 효과크기와 블록 내 상관 ρ를 추정하는 파일럿으로만 쓰고, 추정한 ρ로 n을 다시 계산한다.
4. **추론은 블록 짝 기반의 정확 검정으로 한다.** 연속 지표는 부호 뒤집기 순열검정과 t 기반 CI, 성공은 정확 McNemar와 시나리오 층화 정확 검정을 쓴다. 보조로 블록 무작위 절편 혼합모형을 쓴다. 효과크기는 dz·순위 이연·개선 확률을 함께 낸다. 백분위 bootstrap은 기술 통계로만 쓴다. 근거: Colas et al.은 N < 50에서 bootstrap 검정의 위양성이 크다고 보고했다.
5. **대화 효과와 교란을 분리하는 진단을 사전 등록한다.**
   - (a) 호출 계기별 호출 수를 매개 변수로 분석하고, 채널 조건의 깨우기 시각을 빈 inbox로 재현한 무통신 `yoked-wake` 진단 팔을 둔다.
   - (b) `scale=0` 비용 없는 대화 진단으로 정보 이득과 대화 비용을 분해한다.
   - (c) 체크포인트에서 핵심 메시지를 전달/차단하는 분기 재실행으로 메시지의 인과 영향을 본다(Lowe et al.의 개입 원칙).
   - (d) 한국어 대화는 한국어 원어민 코더 2명이 독립 코딩하고, κ/α ≥ 0.67(잠정)·≥ 0.8(결론)을 기준으로 삼는다.

### 격차 5개 (현재 prereg·설계 문서 대비)
1. **4조건 본연구의 사전 등록이 없다.** 유일한 사전 등록 초안([ZC3](../2026-09-25-zc3-prereg-draft/README.md))은 은퇴한 조건(`independent`/`plan_first`/`dynamic`)과 교사 실행기 기준이다. `configs/zone_study_integration/multiturn_dev_DRAFT.json`은 dev fixture다. 주 대비·가설 방향·α·다중성·ITT·중지 규칙이 4조건 연구에는 정해져 있지 않다.
2. **표본 수 근거가 없다.** 시나리오당 seed 3개(18블록)는 leader 순환만 맞춘 수다. Codex 설계의 파일럿 60회(5상황 × 4조건 × 3 seed)도 검정력 계산이 없다. 게다가 #222 파일럿 예산 잔여는 4,590,207 토큰이다. 파일럿 첫 호출이 10.5k–12.2k 토큰/호출이었으므로, 본 실험 규모와 예산이 맞지 않는다.
3. **호출 수 교란이 통제되지 않는다.** 다회 결정 경계(v66)에서는 메시지 수신이 재호출을 예약한다. 그래서 채널 조건은 무통신보다 LLM 호출(생각할 기회)이 많아질 수 있다. 호출 수를 매개로 보는 분석이나 yoked 대조가 계획에 없다.
4. **질적 분석의 신뢰도 근거가 없다.** 한국어 행위 라벨의 수동 기준은 20개다. 한 명이 비맹검으로 붙였고, 규칙 v2를 같은 표본에 맞춰 고쳤다([ko 파일럿 §5](../2026-09-25-zone-dialogue-ko-pilot/README.md)). 그래서 코더 간 일치도(κ/α)와 보류 표본 검증이 없다.
5. **추론 규칙이 소표본에 약하다.** [지표 문서](../../docs/zone_study_metrics.md)는 p-value를 만들지 않는다. 짝 차이의 백분위 bootstrap CI와 `small_sample < 10` 표시만 있다. 판정 규칙(무엇을 보면 "효과 있음"이라 말하는가)과 소표본에 맞는 검정이 없다.

---

## 1. 문헌별 추출

표의 "효과"는 논문 숫자다. [계산] 표시는 우리가 논문 숫자로 계산한 값이다.

### 1.1 LLM 다중 로봇·체현 에이전트

| 문헌 (읽은 수준) | 비교 조건 | 지표 | 에피소드·seed | 통계 | 보고된 효과 |
|---|---|---|---|---|---|
| **RoCo** Mandi et al. 2023, arXiv 2307.04738 (전문·도구 요약) | Dialog(전체) / Central Plan(전 관측 oracle 단일 LLM) / Dialog w/o History / Dialog w/o Feedback(에피소드 예산 2배) | 과제 성공률, 성공 실행의 환경 step 수, 라운드당 재계획 시도 수 | 과제당 20회 | ±값만 표기(검정 없음) | Pack Grocery: Central 0.82±0.06, Dialog 0.44±0.06. Move Rope: Central 0.50±0.11, Dialog 0.65±0.11. [계산] Cohen's h 0.82(Pack), 0.31(Rope). 방향이 과제마다 반대다. 실물 사람-로봇: 변형마다 10회(예: 9/10, 8/10) |
| **HMAS-2** Chen et al. ICRA 2024, arXiv 2309.15943 (전문·도구 요약) | DMAS(로봇별 LLM 순번 대화) / CMAS(중앙 단일 LLM) / HMAS-1 / HMAS-2(중앙 계획 + 로봇별 피드백) | 성공률, 계획당 step, API 호출, 토큰. 뒤 셋은 성공 실행만 세고 최솟값으로 정규화 | 2D: 로봇 수별 10회(조건당 40회). 3D: 시나리오당 10회 | 검정·CI·오차막대 없음 | BoxNet1 성공: HMAS-2 82.5%, CMAS 75.0%, DMAS 25.0%. Warehouse: 62.5 / 15.0 / 0.0%. [계산] h(HMAS-2 대 DMAS, BoxNet1) = 1.23. DMAS가 호출·토큰이 가장 많았다. 대화 이력보다 상태-행동 이력이 나았다(긴 대화의 문맥 희석) |
| **CoELA** Zhang et al. ICLR 2024, arXiv 2307.02485 (전문·도구 요약) | CoELA / 규칙·MCTS 계획기 / MAT. 소거: 통신 없음, GPT-3.5 대체, 기억·실행 모듈 제거 | TDW-MAT transport rate(지평 3000 프레임 안의 하위 목표 달성 비율), C-WAH 평균 step(지평 250), 효율 개선 EI = ΔM/M₀ | 테스트 24 에피소드(TDW-MAT)·10(C-WAH). 기준선은 5회, CoELA는 비용 때문에 1회 | 사람 연구에서만 t검정 | AI끼리는 통신을 꺼도 뚜렷한 성능 하락이 없었다고 보고했다(수치는 그림에만 있음). 사람 8명·80시행: 신뢰 7점 척도 6.3 대 4.7(통신 유 대 무), p = 0.0003 |
| **조직된 팀** Guo et al. 2024, arXiv 2403.12482 (전문·도구 요약) | 무조직 / 지정 지휘자 / 선출 / 지휘자 수정 허용 / 사람 지휘자 / Criticize-Reflect가 만든 구조 | 완료 time step, step당 에이전트 간 통신 토큰, 메시지 범주 비율 | GPT 실험 조건당 seed 20개. 사람-에이전트 3 seed. 과제 일반화는 과제당 2 seed | 2표본 t검정 | 3×GPT-3.5: 무지휘 102.95±21.88 → 지휘 92.90±14.70 step, t(38) = 1.71, p < .05. 3×GPT-4: 57.75±13.09 → 54.70±8.92. [계산] d = 0.54(GPT-3.5), 0.27(GPT-4). 1.71×√(2/20) = 0.54이므로 ±는 SD로 보인다. 지휘자 발화의 60% 이상이 명령이었다 |
| **MindAgent** Gong et al. 2023, arXiv 2309.09971 (전문·도구 요약) | 에이전트 2·3·4대, 프롬프트 요소 소거, 사람+LLM 에이전트 1–3대 대 단독 | CoS: 과제 간격 5수준에서 완료/(완료+실패)의 평균 | LLM: 3 에피소드. 사람 12명 피험자 내 설계, 순서 무작위 | ANOVA F(4,55) = 28.11, p < 0.001. Tukey HSD | 메시지 분석은 없다 |
| **SMART-LLM** Kannan et al. 2024, arXiv 2309.10062 (전문·도구 요약) | 과제 분해 + 무작위·규칙 배정, 프롬프트 소거, LLM 4종 | SR, TCR, GCR, RU(로봇 활용: 전이 수를 정답과 비교), Exe | 지시 36개. 변동성은 범주별 무작위 과제 5회 | 평균·SD만 | 실행 중 로봇 간 자연어 통신은 없다(중앙 코드 생성) |
| **COMBO** Zhang et al. 2024, arXiv 2404.10775 (전문·도구 요약) | 세계 모형 기반 협력 대 MAPPO·CoELA·LLaVA·공유 믿음 | 성공률, 성공 에피소드의 평균 step | 주 결과 20 에피소드 | 없음 | 명시적 통신이 없고 의도 추론만 한다. "성공 실행만의 step"이라는 관행의 예 |
| **ReAd** Zhang et al. ACL 2025, arXiv 2405.14314 (초록) | RoCo·Central Plan·ReAct·Reflexion·MindAgent 대비 | 성공률, 환경 step, LLM 질의 라운드 | 초록에 없음 | — | 질의 라운드를 효율 지표로 쓴 예 |
| **PARTNR** Chang et al. 2024, arXiv 2411.00081 (초록) | LLM 계획기-사람, 사람-사람 | step 수 등 | 초록에 과제 10만 개 | — | 사람과 짝지은 LLM은 사람 둘보다 1.5배, 사람 혼자보다 1.1배 많은 step이 필요했다 |
| **Co-NavGPT** Yu et al. 2023, arXiv 2310.07937 (초록) | VLM 전역 계획기가 프런티어 배정 | 성공률, 탐색 효율 | 초록에 없음 | — | 로봇 간 자연어 메시지가 아니다(중앙 배정). 이 연구의 비교 대상이 아니다 |
| **MultiAgentBench** Zhu et al. 2025, arXiv 2503.01935 (초록) | 조정 topology star/chain/tree/graph | milestone KPI, 과제 점수 | 초록에 없음 | — | 연구 과제에서는 graph가 가장 좋았다. star는 `leader_ko` 허브-스포크와 대응한다 |
| **LLM-MRS 서베이** arXiv 2502.03814 v5 (전문·도구 요약) | — | — | — | — | 완전 분산 LLM 대화는 팀이 커지면 격자 다중 로봇 환경에서 성능이 떨어진다고 정리했다(Chen et al. 인용) |

### 1.2 창발 통신과 인과 측정

| 문헌 (읽은 수준) | 핵심 |
|---|---|
| **Lowe et al. 2019**, "On the Pitfalls of Measuring Emergent Communication", arXiv 1903.05168 (초록·요약) | 메시지가 발신자 행동과 상관하는 것(positive signaling)과 수신자가 실제로 그 메시지에 따라 행동하는 것(positive listening)을 구분한다. 보상 증가만으로는 통신의 거친 지표일 뿐이다. 인과 영향 지표 CIC를 제안하고, 메시지를 직접 조작·제거하는 개입 실험을 권한다 |
| **Jaques et al. 2019**, Social Influence as Intrinsic Motivation, arXiv 1810.08647 (초록·요약) | 반사실 행동을 모사해 상대 행동 분포가 얼마나 바뀌는지로 영향력을 잰다(행동 간 상호정보와 동치). 메시지 인과 영향 측정의 계산 틀이다 |
| **GlossoGen** Stengel-Eskin et al. 2026, arXiv 2609.01491 (초록) | 효율 압박을 받는 LLM 에이전트 사이에서 영어 사전분포를 벗어난, 사람이 이해하기 어려운 언어가 생겼다. 발화 예산을 두는 우리 설계에서 한국어 이탈·압축을 감시해야 한다는 근거다 |
| **Balch & Arkin 1994**, Communication in reactive multiagent robotic systems, Autonomous Robots (검색 요약만) | 통신 수준 3종 × 과제 3종, 모의와 실로봇. 과제에 따라 통신이 크게 돕기도 하고 불필요하기도 했다. 도움이 될 때는 가장 낮은 수준의 통신도 복잡한 통신과 거의 같은 효과를 냈다. 우리 `structured` 대 `peer_ko` 비교의 고전적 선례다. 원문을 읽지 못해 수치는 옮기지 않는다 |

### 1.3 사람 팀·사람-로봇 대화

| 문헌 (읽은 수준) | 핵심 |
|---|---|
| **Marlow et al. 2018**, OBHDP 144:145–170 (전문) | 150개 연구, 팀 9,702개의 메타분석. 통신-성과 ρ = 0.31, 95% CI [0.23, 0.30](논문 표기 그대로). 품질 ρ = 0.36, 빈도 ρ = 0.19, 정보 정교화 ρ = 0.52, 객관 빈도 ρ = 0.15. 대면 0.32, 완전 가상 0.10. 위계 지휘 0.33, 공유 지휘 0.27(차이 없음). [계산] d = 2r/√(1−r²): 0.31 → 0.65, 0.19 → 0.39, 0.36 → 0.77. **상관 연구이며 조작 실험이 아니다.** 사람 팀 결과라 LLM 로봇으로 옮기는 것은 가정이다. "빈도보다 품질"이라는 결과는 메시지 수가 아니라 정보 내용을 재야 한다는 근거다 |
| **St. Clair & Matarić 2015**, HRI (초록) | 역할 기반 로봇 언어 피드백이 사람-로봇 짝의 객관적 팀 성과와 주관 평가를 모두 높였다. 수치는 초록에 없다 |
| **Carletta et al. 1997**, Map Task 대화 구조 코딩 신뢰도, Computational Linguistics 23(1) (전문) | move 분할 K = .92(단어 경계 4,079개, 코더 4명). 전체 move 분류 K = .83(N = 563, k = 4). 가장 큰 혼동은 CHECK 대 QUERY-YN. 비전문 코더 K = .69. 본문에서 Krippendorff 기준을 인용한다: α > .8이면 결론, .67–.8이면 잠정 결론. 우리 한국어 행위 코딩의 신뢰도 기준으로 쓴다 |
| **Hawkins, Frank & Goodman 2020**, repeated reference games, arXiv 1912.07199 (초록) | 발화 15,000개 이상. 반복 상호작용에서 짝이 효율적이고 안정된 지칭 관례를 만든다. 긍정 피드백 뒤 구문 단위가 묶음으로 빠진다. 대화 효율(발화 길이)의 시간 변화를 보는 선례다 |
| **MAST** Cemri et al. 2025, arXiv 2503.13657 (초록·요약) | 7개 다중 에이전트 LLM 프레임워크의 추적 1,600개 이상. 150개를 전문가가 분석했고 Cohen's κ = 0.88이다. 실패 14유형을 세 범주(시스템 설계, 에이전트 간 불일치, 과제 검증)로 나눈다. LLM 판정기는 사람 라벨과 대조해 검증했다. 실패를 "통신 때문인가"로 귀속하는 틀이다 |

### 1.4 소표본 통계와 평가 관행

| 문헌 (읽은 수준) | 핵심 |
|---|---|
| **Colas, Sigaud & Oudeyer 2019**, Hitchhiker's Guide, arXiv 1904.06979 (전문) | 비짝 두 표본에서 bootstrap 검정은 N > 40이 아니면 위양성률 α*가 크다. 순열검정과 순위 t검정은 N < 5에서 α*가 크다. 결론은 Welch t검정과 낮은 α를 권하는 것이다. bootstrap(N < 50)과 순열검정(N < 10)을 경고한다. 검정력 0.8에 필요한 N은 상대 효과 0.5에서 약 100, 1에서 약 20, 2에서 5–10이다. 다중 비교는 Bonferroni 등으로 보정한다 |
| **Agarwal et al. 2021**, Statistical Precipice, arXiv 2108.13264 (초록·요약) | 적은 실행 수에서는 점추정 대신 층화 bootstrap 구간, IQM, 성능 프로파일, 개선 확률을 쓴다(rliable) |
| **Miller 2024**, Adding Error Bars to Evals, arXiv 2411.00640 (초록·요약) | 평가 문항을 모집단의 표본으로 본다. 군집 표준오차, 짝 차이, 문항당 반복 응답으로 분산을 줄이고, 검정력 계산을 권한다 |
| **Kress-Gazit et al. 2024**, Robot Learning as an Empirical Science, arXiv 2409.09491 (초록·요약) | 시행 수·초기 조건·성공 기준 명시, 여러 지표, 통계 분석, 실패 유형의 질적 기술을 권한다 |
| **Snyder et al. 2025**, Policy comparison with near-optimal stopping, arXiv 2503.10966 (초록) | 로봇 정책 성공률을 소표본(10–50회)으로 비교하는 순차 검정이다. 고정 n 대비 시행 수를 최대 32% 줄이면서 오류율을 보장한다 |

### 1.5 한국어 대화 분석 도구

| 문헌 (읽은 수준) | 핵심 |
|---|---|
| **Marchisio et al. 2024**, Language Confusion, arXiv 2406.20052 (전문·도구 요약) | 15개 언어(한국어 포함). 줄 단위 통과율 LPR은 fastText 언어 식별로 모든 줄이 목표 언어인 응답의 비율이다. 단어 단위 통과율 WPR은 비라틴 문자 언어에서 영어 사전 단어(대문자 제외)가 섞였는지 본다. LCPR은 둘의 조화평균이다. 우리 "한국어 준수"(literal 제거 뒤 한글 비율 ≥ 0.9)와 같은 목적의 외부 기준이다 |
| **ISO 24617-2** 대화 행위 주석 표준 (검색 요약) | 9개 차원, 56개 의사소통 기능, 확실성·조건성 수식어. DialogBank 등 말뭉치가 있다. 한국어 적용 사례는 찾지 못했다 |
| **Kiwi** 한국어 형태소 분석기, 한국디지털인문학 1(1):109–136, 2024 (검색 요약) | 통계 언어모형과 skip-bigram 기반이다. 중의성 해소 평균 정확도 86.7%이고 Python `kiwipiepy`가 있다. 한국어 어미(-습니다/-세요/-십시오)와 영어 토큰 분리를 규칙이 아니라 형태소 단위로 세는 도구다 |
| 한국어 화행 자동분류 연구(국립국어원 수업 대화 말뭉치, 13개 분류 자질, 정확률 70.03%) (검색 결과 요약만. 원문 미열람) | 한국어 화행 분류가 규칙·자질만으로는 70% 수준이라는 참고치다. 원문을 읽지 않아 설계 근거로는 쓰지 않는다 |

### 1.6 문헌에서 반복되는 관행과 약점

- **지표:** 성공률 + 성공 실행만의 step/시간이 표준이다(RoCo, HMAS-2, COMBO). 이 방식은 빨리 실패한 조건을 유리하게 만들 수 있다. 우리 PAR-2 설계가 이 약점을 피한다. 호출·토큰을 효율 지표로 함께 내는 흐름이 있다(HMAS-2, ReAd, Guo의 통신 토큰).
- **표본:** 조건당 10–40회가 흔하다. seed 20개가 가장 체계적이다(Guo). 비용 때문에 1회만 돌린 경우도 있다(CoELA).
- **통계:** 대부분 검정·CI가 없다(HMAS-2, COMBO, SMART-LLM). t검정·ANOVA는 Guo와 MindAgent뿐이고, 짝·블록 설계를 명시한 논문은 찾지 못했다. 이 분야의 기준이 약하므로 우리는 로봇 평가·RL 통계 문헌(Colas, Agarwal, Miller, Kress-Gazit)을 따라야 한다.
- **통신 효과 크기:** 방향이 일관되지 않는다. AI끼리 통신을 꺼도 차이가 없었고(CoELA), 과제마다 대화와 중앙 계획의 우열이 뒤집혔다(RoCo). 분산 대화는 중앙 조정보다 크게 나빴다(HMAS-2). 지휘자가 있으면 d ≈ 0.27–0.54 정도 빨라졌다(Guo). **"대화가 항상 돕는다"는 사전 가정은 근거가 없다.** 시나리오별 방향 가설과 대조군(s1)이 필요하다.
- **질적 분석:** 행위 범주 분류(Guo: GPT-4 분류기를 사람 라벨 20개로 검증, 91.67%), 실패 유형 서술(CoELA, RoCo의 오류 연쇄, HMAS의 반복 발화), 실패 분류 체계와 κ(MAST 0.88), Map Task의 코더 4명 K.

---

## 2. 권고

### 2.1 주·보조 지표의 조작적 정의

기존 필드명은 [`docs/zone_study_metrics.md`](../../docs/zone_study_metrics.md)와 `harness/zone_study_eval.py`를 따른다.

**주 지표 (하나만):**

| 이름 | 정의 | 근거 |
|---|---|---|
| `par_makespan_sim_s` (PAR-2) | 성공(`end_reason == "orders_complete"`이고 `end_sim_s ≤ horizon`)이면 `end_sim_s − t0_sim_s`, 아니면 `2.0 × sim_horizon_s`. 대화·추론 SIM 비용(`zone_sim_cost`)이 이미 포함된 값이다 | 성공 실행만의 step(RoCo, HMAS-2, COMBO)이 가진 생존 편향을 없앤다 |
| 대체 주 지표 `delivery_rate` | 심판이 확인한 정상 배송 물건 수(물건당 1회) ÷ 주문 물건 수. 시점은 `end_sim_s`, 늦어도 horizon | CoELA transport rate. 부분 점수라 성공률이 낮을 때 민감하다 |

- **전환 규칙(사전 고정):** 파일럿에서 조건을 가리고 네 조건을 합친 성공률이 0.3 미만이면 주 지표를 `delivery_rate`로 바꾼다. 조건별 결과를 보기 전에 판단하고 기록한다. 0.3은 우리 제안값이며 문헌 근거는 없다.
- **성공률은 주 지표와 같은 표에 반드시 싣는다**(짝 위험차와 Newcombe CI).

**보조 지표(기술 통계와 보정 없는 탐색):**
- 효율: `makespan_success_only_s`(단독 비교 금지), `idle_share`와 `idle_by_reason`, `par_sim_s_per_delivered`.
- 조정 품질: `conflicts_by_kind`, `deadlocks`/`deadlock_sim_s`, `replans_by_kind`, 중복 claim 수(같은 주문을 2대 이상이 claim한 횟수. 파일럿 첫 호출 12/12가 order-1에 몰렸다).
- 비용: `model_calls`와 **계기별 분해**(`start`/`own_timer`/`message_received`/`idle_review`/`execution_review`), `http_attempts`, `tokens_input/output/total`, `think_sim_cost_s`, `talk_sim_cost_s`, `wall_latency_ms_mean`(참고만). Guo의 "step당 통신 토큰"에 해당하는 발화 토큰/SIM분도 낸다.
- 통신: 발화 수, 발화당 출력 토큰, 정보 포함 발화 비율(`claims`가 하나 이상 있는 발화), `truthful_share`, 한국어 준수, 채널 위반. Marlow는 빈도(ρ 0.19)보다 품질(ρ 0.36)이 성과와 더 관련된다고 보고했다. 그래서 **메시지 수가 아니라 정보 발화를 주 통신 지표**로 쓴다.
- 통신 효율 **[제안 정의]**: `delivered_items / (발화 출력 토큰 / 1000)`. 비교 대상은 `peer_ko`와 `structured`다.

### 2.2 분석 단위와 표본 수

- **분석 단위는 시행(팀 에피소드)이다.** 로봇은 시행 안에 묶여 있어 독립 표본이 아니다. 로봇·호출 단위 지표를 분석할 때는 시행으로 군집한 표준오차를 쓴다(Miller 2024).
- **블록은 (시나리오, seed)다.** 네 조건이 같은 블록을 공유하고, 블록 안의 실행 순서는 무작위로 한다(ZC3 초안의 규칙을 재사용).
- **seed 수는 시나리오마다 3의 배수로 한다.** `leader_ko`의 지휘자 순환(`seed % 3`)이 r1·r2·r3를 같은 횟수로 포함해야 하기 때문이다.
- **반복:** ko 파일럿에서 같은 입력을 다시 호출했을 때 결정이 같은 경우는 8쌍 중 6쌍뿐이었다. 그래서 블록 안 LLM 변동이 있다. 본 코호트는 (블록, 조건)마다 1회를 돌린다. 무작위로 고른 블록의 1/3에서는 2회째를 돌려 블록 내 분산(ICC)을 추정하고, 짝을 짓기 전에 평균한다. 현재 `compare_conditions`의 규칙과 같다. 반복보다 새 seed가 모집단 추론에 유리하다는 점을 우선한다.

**검정력 추정 [계산, 추정치]** — 정규근사에 Guenther 보정을 더한 값이다. 스크립트는 [`power_estimate.py`](power_estimate.py)이며, 표준 라이브러리만 쓰고 SIM·모델 호출이 없다.
- 짝 연속 지표는 dz = d / √(2(1−ρ))로 계산한다. ρ는 같은 블록의 두 조건 결과 사이 상관이다. 아직 측정하지 않았으므로 0, 0.5, 0.7을 모두 제시한다.

| 효과 출처 | d | ρ = 0 | ρ = 0.5 | ρ = 0.7 | ρ = 0.5, Holm 3개 최악(α 0.0167) |
|---|---:|---:|---:|---:|---:|
| Guo GPT-4 지휘자 효과 | 0.27 | 214 | 108 | 66 | 145 |
| Marlow 빈도 ρ = 0.19 변환 | 0.39 | 107 | 55 | 34 | 73 |
| Guo GPT-3.5 지휘자 효과 | 0.54 | 56 | 29 | 19 | 39 |
| Marlow 전체 ρ = 0.31 변환 | 0.65 | 39 | 21 | 13 | 28 |
| 큰 효과(참고) | 1.00 | 18 | 10 | 7 | 14 |

(표 값은 검정력 0.8, 양측 α 0.05에 필요한 짝(블록) 수다.)

| 블록 수 | 최소 검출 dz (α 0.05) | Holm 3개 최악 |
|---:|---:|---:|
| 18 (시나리오당 3 seed) | 0.70 | 0.84 |
| 36 (시나리오당 6 seed) | 0.48 | 0.57 |
| 54 (시나리오당 9 seed) | 0.39 | 0.46 |
| 72 (시나리오당 12 seed) | 0.34 | 0.39 |

- 성공률(비짝 근사, 팔당 n): 0.825 대 0.25(HMAS-2 대 DMAS)는 6, 0.8 대 0.5는 19, 0.8 대 0.6은 41, 0.65 대 0.5(RoCo Move Rope 수준)는 85다. 짝 McNemar는 불일치 짝 비율에 따라 달라지므로 파일럿 뒤에 다시 계산한다.
- **해석:** 18블록은 d ≥ 1 수준의 큰 효과만 잡는다. 문헌의 조직·대화 효과(0.27–0.65)를 잡으려면 ρ ≈ 0.5일 때 29–108블록이 필요하다. **최소 권고는 36블록(144 시행)이다. 18블록 파일럿으로 ρ·SD·성공률을 추정한 뒤 n을 다시 정한다.** 시나리오별 주장은 시나리오당 6 seed로는 dz ≈ 1.3 이상만 잡으므로 탐색으로만 보고한다.
- **예산 [계산]:** 파일럿 첫 호출이 호출당 10.5k–12.2k 토큰이었다. 시행당 30회 호출을 가정하면 시행당 약 0.3M 토큰, 144 시행이면 약 47M 토큰이다. #222 잔여 4.59M 토큰과 큰 차이가 난다. 실제 시행당 호출 수는 아직 측정하지 않았으므로 파일럿 뒤 다시 계산한다.
- 고정 n 대신 순차 검정(Snyder et al. 2025)을 쓰면 시행을 줄일 수 있다. 쓸 경우 사전 등록에 멈춤 경계를 함께 적는다. ZC3 초안의 "중간에 멈추지 않는다"와 충돌하므로 둘 중 하나를 선택해야 한다.

### 2.3 소표본에 맞는 통계

1. **주 대비 세 개와 Holm 보정:** H1 `peer_ko − no_comm`, H2 `peer_ko − structured`, H3 `leader_ko − peer_ko`. 세 조건 모두와 비교하는 omnibus 검정은 보조로 둔다(Friedman 또는 블록 LMM의 조건 F).
2. **연속 주 지표:** 블록 짝 차이에 대한 **정확 부호 뒤집기(sign-flip) 순열검정**을 쓴다. n ≤ 20이면 2^n을 전부 나열하고, 그보다 크면 고정 seed로 10⁵회 Monte Carlo를 돈다. CI는 짝 t 구간과 BCa bootstrap을 함께 싣고, 두 구간이 다르면 그 사실을 적는다. 현재의 백분위 bootstrap CI는 **기술 통계로만** 남긴다. Colas et al.은 bootstrap 검정이 N < 50에서 위양성이 크다고 보고했다(비짝 설정이지만 짝에서도 같은 이유로 주의).
3. **성공(0/1):** 짝 **정확 McNemar**와 시나리오를 층으로 한 정확 Mantel–Haenszel을 쓴다. 효과는 위험차와 Newcombe CI로 낸다.
4. **혼합모형(보조):** `y ~ condition + scenario + (1 | block)`로 한다. 시나리오는 6수준뿐이라 고정 효과로 둔다. 연속 지표는 log(PAR) 또는 순위 변환을 쓰고, 자유도는 Kenward–Roger로 잡는다. 수 지표(충돌·발화)는 음이항 GLMM, 성공은 로짓 GLMM이다. `condition × scenario`는 탐색으로만 본다.
5. **효과크기:** 짝 dz, 순위 이연(rank-biserial, 이미 구현), **개선 확률** P(변이 < 기준)(Agarwal), 성공 위험차.
6. **판정 문구 규칙(사전 고정):** Holm 보정 p < 0.05이고 CI가 0을 넘지 않으면 "효과 있음"이라고 쓴다. 그렇지 않으면 "이 표본에서 검출하지 못함"이라고 쓰고, **"효과 없음"이라고는 쓰지 않는다.** 동등성을 주장하려면 TOST 경계를 사전에 정해야 한다.
7. **보고:** 블록별 짝 표 전체를 싣는다(Colas: 표본이 작으면 개별 실행을 모두 보인다). 실패는 모두 분모에 넣는다.

### 2.4 대화 효과와 교란 분리

| 교란 | 왜 문제인가 | 권고 |
|---|---|---|
| **LLM 호출 수(생각할 기회)** | 채널 조건에서는 메시지 수신이 재호출을 만든다(v66 `DecisionScheduler`). 그래서 대화 효과와 "더 자주 생각한 효과"가 섞인다. HMAS-2와 ReAd는 호출 수를 비용 지표로 따로 낸다 | (a) 호출 계기별 수를 기록하고 매개 분석을 사전 등록한다. (b) **yoked-wake 진단 팔**을 둔다: 짝 채널 조건 시행의 `message_received` 깨우기 시각을 무통신 로봇에게 빈 inbox 재호출로 재현한다. 블록 일부(예: s2·s5 × 6 seed)만 돌린다 |
| **대화 비용(토큰→SIM 시간)** | 한국어와 정형 메시지는 토큰 길이가 다르다. 비용식 계수는 잠정값이다(`zone_sim_cost.v1`, `provisional=True`) | 주 분석은 비용을 포함한다(생태적 타당도). 진단으로 `scale=0`을 블록 일부에서 돌려 "정보 이득 − 대화 비용"을 분해한다. 이미 구현된 `zc.sweep()`을 쓴다. 계수는 코호트 전에 고정하고, 발화당 출력 토큰을 조건별로 보고한다 |
| **메시지 지연·wall 지연** | 제공자의 느린 응답이 결과를 바꾸면 안 된다 | SIM 비용이 wall과 분리돼 있다(현재 설계 유지). wall 지연은 참고로만 보고한다. HTTP 재시도 수는 조건별로 대조한다 |
| **통신과 무관한 실패** | 자기 카메라 파지·위치 추정 실패, API 오류, 디스크 부족이 조건과 우연히 섞일 수 있다 | 주 분석은 ITT(배정한 모든 시행)다. 실패 원인은 사전 분류한다: 실행기 / 인식 / 인프라(HOST_ERROR·API) / 통신 귀속 / 조정 귀속. 인프라 제외 민감도는 보조로만 쓴다. 실행기 실패율을 조건별 **균형 진단**으로 낸다. 통신 귀속 여부는 MAST식 범주로 2인 코딩한다 |
| **메시지 내용의 인과 효과** | 결정 직전에 메시지가 있었다는 것은 연관일 뿐이다(지표 문서도 명시) | **분기 재실행:** 핵심 메시지(s2 막힘 보고, s5 낙하 보고) 직전 체크포인트에서 전달/차단 두 가지로 재실행한다. 행동 변화와 결과 차이를 본다(Lowe et al.의 개입, Jaques et al.의 반사실 영향). `docs/coela_communication_study.md`의 분기 실험 계획을 4조건 연구로 옮긴다 |
| **조작 확인** | 채널이 열려 있어도 쓰이지 않으면 대화 효과를 검정할 수 없다 | 코호트 관문(사전 고정): 채널 조건 시행 중 정보 발화가 1건 이상 전달된 비율, s2에서 막힘 관측이 동료의 문 선택보다 먼저 전달된 비율, 한국어 준수, `structured`의 자유 텍스트 위반 0건. 관문 미달은 "통신 효과 검정 불가"로 보고한다 |
| **실행 시간 변화** | 모델 버전과 프록시 부하가 시간에 따라 변한다 | 블록 순서와 블록 안 조건 순서를 무작위로 한다. 응답의 모델 문자열이 바뀌면 중단한다(ZC3 초안 규칙 재사용). 실행마다 부하 평균을 기록한다 |

### 2.5 질적 대화 분석(한국어)

선행 연구가 한 것:
- 협력 행동 범주와 실패 유형 서술(CoELA).
- LLM 분류기로 3범주를 라벨링하고 사람 라벨 20개로 정확도를 검증했다. 지휘자의 명령 비율도 냈다(Guo).
- 반복·중복 발화와 문맥 희석을 관찰했다(HMAS-2). 잘못된 추론이 여러 라운드에 걸쳐 전파되는 것을 보였다(RoCo).
- 실패 분류 체계를 만들고 κ와 LLM 판정기를 검증했다(MAST).
- move 코딩에 코더 4명을 쓰고 K를 보고했다(Map Task, Carletta).

권고 절차:
1. **코드북:** 기존 5종(`report`/`request`/`order`/`objection`/`ack`)을 유지한다. 여기에 ISO 24617-2 기능 대응표와 정보 내용 코드(`blocked`/`absent`/`holding`/`delivered`/역할·순서 제안)를 더한다. 한국어 어미 단서(-습니다 보고, -주세요 요청, -십시오 명령)는 이미 규칙에 있다. 형태소 단위 판정에는 Kiwi를 검토한다.
2. **코더:** 한국어 원어민 2명이 독립 코딩한다. 조건을 가릴 수 있는 범위(`peer_ko` 대 `leader_ko`의 발화 본문)는 가린다. 층화 표본은 조건 × 시나리오별로, 최소 200발화 또는 전체의 20% 중 큰 쪽으로 한다. 불일치는 합의로 판정한다.
3. **신뢰도 기준:** Cohen's κ(2인) 또는 Krippendorff α를 쓴다. α ≥ 0.8이면 결론에, 0.67–0.8이면 잠정 결론에 쓴다(Carletta가 인용한 Krippendorff 기준). 범주별 혼동표를 함께 싣는다(Map Task의 CHECK/QUERY-YN처럼).
4. **자동 분류기 검증:** 규칙 v2와 LLM 판정기는 **튜닝에 쓰지 않은 보류 표본**에서 범주별 F1로 검증한다. Guo처럼 20개로 정확도만 보는 수준은 넘어야 한다. 규칙을 고칠 때마다 보류 표본을 새로 둔다.
5. **한국어 준수:** 현재 한글 비율 지표에 더해 Marchisio et al.의 LPR/WPR 방식(줄 단위 언어 식별, 단어 단위 영어 혼입)을 보조로 계산한다. 효율 압박에 따른 압축·이탈(GlossoGen)을 감시하기 위해 발화 길이와 비사전어 비율을 시간순으로 본다.
6. **실패 귀속:** 실패한 시행마다 "통신 귀속(오정보·누락·오해·지시 충돌) / 조정 귀속 / 통신 무관" 중 하나를 붙인다. MAST 범주를 참조하고 2인 코딩한다.
7. **연관과 인과 구분:** 결정 변경 직전 발화 분석(`preceding_inbound`)은 연관으로만 보고한다. 인과 주장은 2.4의 분기 재실행 결과로만 한다.
8. **[우리 제안, 문헌 근거 없음]** 한국어 특유의 주어·목적어 생략 때문에 지칭 대상이 모호해지는 경우(누가 어느 주문을 맡는지)를 별도 코드로 센다. 존댓말 수준의 일관성도 기술 통계로 본다.

---

## 3. 현재 설계와의 대조: 구체적 격차

| # | 격차 | 현재 상태(근거) | 필요한 조치 |
|---|---|---|---|
| G1 | 4조건 본연구 사전 등록 없음 | ZC3 초안은 `independent`/`plan_first`/`dynamic`·교사 실행기 기준([README](../2026-09-25-zc3-prereg-draft/README.md) §0). `multiturn_dev_DRAFT.json`은 dev fixture이고 `source_sha`/`bundle_sha256`이 null. [지표 문서](../../docs/zone_study_metrics.md)는 "사전 고정한 코호트를 실행한 뒤" 판정한다고만 적었다 | 주 대비 3개·방향·α·Holm·ITT·재시도·중지 규칙·주 지표 전환 규칙을 담은 4조건 prereg를 쓰고, 코호트 전에 커밋해 고정한다. ZC3 초안의 실행 순서·재시도·중단 규칙을 재사용한다 |
| G2 | 표본 수·예산 근거 없음 | 시나리오당 seed 3개(`docs/zone_study_scenarios.md`). Codex 설계의 파일럿 60회. 검정력 계산은 ZC3(교사 실행기, 옛 조건)에만 있다. #222 잔여 4.59M 토큰(multiturn README) | 18블록 파일럿 → ρ·SD·성공률 추정 → n 재계산(2.2 표). 최소 36블록과 그에 맞는 토큰 예산 결정 |
| G3 | 호출 수 교란 | v66에서 메시지 수신이 재호출을 만든다. 공통 타이머는 같지만 `message_received` 계기는 채널 조건에만 있다([multiturn README](../2026-09-27-zone-study-multiturn/README.md)) | 계기별 호출 수 매개 분석, yoked-wake 진단 팔 |
| G4 | 질적 분석 신뢰도 없음 | 수동 라벨 한국어 20개·영어 12개, 1인 비맹검, 교차 검토 없음. 규칙 v2를 같은 표본으로 확인(ko 파일럿 §5·§9) | 2인 원어민 코딩, κ/α 기준, 보류 표본 F1 |
| G5 | 소표본 추론 규칙 부족 | p-value 없음, 백분위 bootstrap, `SMALL_SAMPLE_PAIRS = 10` 표시만 있다 | 정확 부호 뒤집기·McNemar·Holm·판정 문구 규칙 추가. bootstrap은 기술 통계로 강등 |
| G6 | 주 지표 민감도 규칙 없음 | PAR-2가 주 시간 지표인데, 자기 카메라 실행기의 성공률이 낮으면 벌점값에 지배된다 | 조건을 가린 합산 성공률 기준의 `delivery_rate` 전환 규칙 사전 고정 |
| G7 | 대화 비용 계수 잠정·분해 계획 없음 | `zone_sim_cost.v1` 전부 `provisional`. `scale=0`은 "진단 조건"으로만 언급된다 | 계수 고정 시점과 근거 기록, `scale=0` 진단 블록을 사전 등록 |
| G8 | 조작 확인 관문 없음 | 채널 격리 검사(P3)는 있지만, 채널이 **쓰였는지**는 관문이 아니다 | 2.4의 조작 확인 관문 |
| G9 | 실패 귀속 분류 없음 | `end_reason` 범주만 있다(`sim_horizon`, `deadlock`, `api_failure` 등) | 통신 귀속 여부 2인 코딩, 실행기 실패율 균형 진단 |
| G10 | 시나리오 이질성 | 6시나리오의 기대 방향이 다르다(s1 대조군, s4 협상, s6 표현력). 합산하면 효과가 희석된다. s6은 H2에만 해당하지만 4조건을 모두 돈다 | 시나리오별 방향 가설, 시나리오 층화 분석, s6을 H2 전용 보조 분석으로 분리할지 결정(Codex 설계도 s6 분리를 제안) |
| G11 | LLM 반복 변동 미추정 | ko 파일럿 재호출 결정 일치 6/8 | 블록 1/3에서 2회째 실행해 ICC 추정 |
| G12 | 메시지 인과 실험 미계획 | `coela_communication_study.md`에 분기 실험 원칙만 있다 | s2·s5 핵심 메시지 전달/차단 분기 재실행 계획 |

---

## 4. 이 조사의 한계

- 초록만 읽은 문헌(ReAd, PARTNR, Co-NavGPT, MultiAgentBench, Lowe, Jaques, Miller, Agarwal, Kress-Gazit, Snyder, St. Clair & Matarić, Hawkins, MAST, GlossoGen)에서는 초록에 있는 주장만 옮겼다. Balch & Arkin, ISO 24617-2, Kiwi, 한국어 화행 연구는 검색 요약만 봤다.
- "전문·도구 요약"은 WebFetch 요약기가 arXiv HTML 본문에서 뽑은 값이다. 표 숫자는 요약기 인용을 옮긴 것이며 PDF와 직접 대조하지 않았다. Marlow, Colas, Carletta만 PDF 본문을 직접 읽었다.
- CoELA의 통신 소거 수치는 그림에만 있어 숫자를 옮기지 못했다.
- 효과크기 변환에는 가정이 있다. Marlow는 상관 연구다. Guo의 ±는 t값 역산으로 SD라고 추정했다. 우리 과제·모델·자기 카메라 실행기로 효과가 옮겨진다는 보장은 없다. **검정력 표는 설계 출발점일 뿐이며, 파일럿 추정치로 반드시 다시 계산해야 한다.**
- 한국어 로봇 간 대화를 효율 관점에서 조작 실험한 선행 연구는 찾지 못했다.

## 5. 참고 자료

읽은 수준: 전문 = PDF 본문 직접 읽음 / 전문·요약 = arXiv HTML 본문(WebFetch 요약) / 초록 = 초록·소개 페이지 / 검색 = 검색 결과 요약만.

- Mandi, Jain, Song. RoCo: Dialectic Multi-Robot Collaboration with LLMs. arXiv 2307.04738. <https://arxiv.org/abs/2307.04738> (전문·요약)
- Chen et al. Scalable Multi-Robot Collaboration with LLMs: Centralized or Decentralized Systems? ICRA 2024. arXiv 2309.15943. <https://arxiv.org/abs/2309.15943> (전문·요약)
- Zhang et al. Building Cooperative Embodied Agents Modularly with LLMs (CoELA). ICLR 2024. arXiv 2307.02485. <https://arxiv.org/abs/2307.02485> (전문·요약)
- Guo et al. Embodied LLM Agents Learn to Cooperate in Organized Teams. arXiv 2403.12482. <https://arxiv.org/abs/2403.12482> (전문·요약)
- Gong et al. MindAgent. arXiv 2309.09971. <https://arxiv.org/abs/2309.09971> (전문·요약)
- Kannan et al. SMART-LLM. arXiv 2309.10062. <https://arxiv.org/abs/2309.10062> (전문·요약)
- Zhang et al. COMBO. arXiv 2404.10775. <https://arxiv.org/abs/2404.10775> (전문·요약)
- Zhang et al. ReAd: Towards Efficient LLM Grounding for Embodied Multi-Agent Collaboration. arXiv 2405.14314. <https://arxiv.org/abs/2405.14314> (초록)
- Chang et al. PARTNR. arXiv 2411.00081. <https://arxiv.org/abs/2411.00081> (초록)
- Yu et al. Co-NavGPT. arXiv 2310.07937. <https://arxiv.org/abs/2310.07937> (초록)
- Zhu et al. MultiAgentBench (MARBLE). arXiv 2503.01935. <https://arxiv.org/abs/2503.01935> (초록)
- Large Language Models for Multi-Robot Systems: A Survey. arXiv 2502.03814 v5. <https://arxiv.org/html/2502.03814v5> (전문·요약)
- Lowe et al. On the Pitfalls of Measuring Emergent Communication. arXiv 1903.05168. <https://arxiv.org/abs/1903.05168> (초록)
- Jaques et al. Social Influence as Intrinsic Motivation for Multi-Agent Deep RL. arXiv 1810.08647. <https://arxiv.org/abs/1810.08647> (초록)
- Stengel-Eskin et al. GlossoGen: Emergent Language in Complex Multi-Agent LLM Interactions. arXiv 2609.01491. <https://arxiv.org/abs/2609.01491> (초록)
- Balch & Arkin. Communication in reactive multiagent robotic systems. Autonomous Robots 1994. <https://link.springer.com/article/10.1007/BF00735341> (검색)
- Marlow, Lacerenza, Paoletti, Burke, Salas. Does team communication represent a one-size-fits-all approach? A meta-analysis of team communication and performance. OBHDP 144 (2018) 145–170. <https://www.sciencedirect.com/science/article/abs/pii/S074959781630125X> (전문)
- St. Clair & Matarić. How Robot Verbal Feedback Can Improve Team Performance in Human-Robot Task Collaborations. HRI 2015. doi:10.1145/2696454.2696491 (초록)
- Carletta et al. The Reliability of a Dialogue Structure Coding Scheme. Computational Linguistics 23(1), 1997. <https://aclanthology.org/J97-1002/> (전문)
- Hawkins, Frank, Goodman. Characterizing the dynamics of learning in repeated reference games. arXiv 1912.07199. <https://arxiv.org/abs/1912.07199> (초록)
- Cemri et al. Why Do Multi-Agent LLM Systems Fail? (MAST). arXiv 2503.13657. <https://arxiv.org/abs/2503.13657> (초록)
- Colas, Sigaud, Oudeyer. A Hitchhiker's Guide to Statistical Comparisons of RL Algorithms. arXiv 1904.06979. <https://arxiv.org/abs/1904.06979> (전문)
- Agarwal et al. Deep RL at the Edge of the Statistical Precipice. arXiv 2108.13264. <https://arxiv.org/abs/2108.13264> (초록)
- Miller. Adding Error Bars to Evals. arXiv 2411.00640. <https://arxiv.org/abs/2411.00640> (초록)
- Kress-Gazit et al. Robot Learning as an Empirical Science: Best Practices for Policy Evaluation. arXiv 2409.09491. <https://arxiv.org/abs/2409.09491> (초록)
- Snyder et al. Policy comparison with near-optimal stopping. arXiv 2503.10966. <https://arxiv.org/abs/2503.10966> (초록)
- Marchisio et al. Understanding and Mitigating Language Confusion in LLMs. arXiv 2406.20052. <https://arxiv.org/abs/2406.20052> (전문·요약)
- Bunt et al. ISO 24617-2 dialogue act annotation, 2nd ed. LREC 2020. <https://aclanthology.org/2020.lrec-1.69/> (검색)
- Kiwi: Developing a Korean Morphological Analyzer Based on Statistical Language Models and Skip-Bigram. Korean Journal of Digital Humanities 1(1):109–136, 2024. <https://accesson.kr/kjdh/v.1/1/109/43508?view=pubreader> / <https://github.com/bab2min/kiwi> (검색)
- 한국어 대화문 화행 자동분류를 위한 언어학적 기반연구. <https://www.dbpia.co.kr/Journal/articleDetail?nodeId=NODE07514224> (검색)

내부 근거:
- [ZC3 사전 등록 초안](../2026-09-25-zc3-prereg-draft/README.md)
- [LLM 어댑터 파일럿](../2026-09-27-zone-study-pilot/README.md)
- [다회 결정 루프](../2026-09-27-zone-study-multiturn/README.md)
- [한국어 대화 파일럿](../2026-09-25-zone-dialogue-ko-pilot/README.md)
- `docs/zone_study_metrics.md`, `docs/zone_study_protocol.md`, `docs/zone_study_scenarios.md`, `docs/zone_sim_cost.md`, `docs/coela_communication_study.md`, `docs/design/2026-09-25-zone-dialogue-study-design-codex.md`, `docs/decision_log.md`(2026-09-25/26 연구 조건 결정)
