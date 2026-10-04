연구 이슈의 참고 댓글 2/2 — 가까운 선행의 공식 구현, 반대 설명과 최소 판별 증거. 본문/공식 소스 읽기이며 외부 실험 재현은 아닙니다.

### 3.1 LLawCo: 가장 가까운 최신 경쟁자도 “대화는 항상 이롭다”를 지지하지 않는다

**게재 확인:** [ICML 2026 PMLR](https://proceedings.mlr.press/v306/zhou26i.html). 본문은 [MERL TR2026-081, 2026-06-18](https://www.merl.com/publications/docs/TR2026-081.pdf)의 §§3–5, Tables 1–3, 법칙 개입, Appendix F.1–F.2를 확인했다. arXiv 최초 게시(2026-06-26)와 출판 연도는 구별한다.

Table 1에서 Llama-3.1-8B는 **no-talk ReAct가 LLawCo·RoCo·CoELA보다 높은 success**를 보인다. 다른 backbone에서는 LLawCo가 나은 경우가 있다. 따라서 “communicative baseline들보다 평균 개선”을 “모든 모델에서 대화가 무대화보다 낫다”로 바꾸면 안 된다. SFT와 행동 법칙의 학습도 바뀌므로 channel만의 효과가 아니다. 법칙 문구를 바꿔 Talk 선택률이 변한 실험은 **prompt/law→speaker action**의 근거이고, 수신 메시지가 물리 성공을 개선했다는 개입은 아니다. Appendix F.2는 Talk를 instantaneous action으로 다루며 영상에서는 같은 프레임을 50회 반복해 보인다. 영상의 멈춤을 실제 통신 비용으로 읽지 않는다.

공식 release `0f08a418295840829b9e5aa012ab562912298363`(2026-07-13)를 추가 확인했다.

| 확인 경로 | 직접 확인한 공개 코드 사실 | UGRP 비교에 대한 의미 |
|---|---|---|
| `scripts/run_exp.sh` → `conf/baselines/llawco.yaml` | PARTNR example을 상속하고 partial_obs=True, oracle motor skill + Talk를 선택 | “partial”은 곧 RGB-only actor/executor라는 뜻이 아님 |
| example → `conf/world_model/gt_graph.yaml` | `type: gt_graph`, `update_mode: gt` | 본 공개 경로는 부분관측 GT graph 구성이다. 현재 계약에 그대로 쓸 baseline 아님 |
| `llawco.yaml` 대 `decentralized_zero_shot_react_summary.yaml` | replanning_threshold 50 대 25, constrained_generation True 대 False. run_exp에서 이 둘을 같게 덮어쓰지 않음 | 공개 기본 실험 경로 자체도 모델·법칙·채널 외 설정이 다르다. 논문 Table 1의 모든 run이 이 설정이었다고 역추정하지는 않음 |
| `tools/general/talk_skill.py` | source/content speech를 만들어 즉시 성공 응답 | 전달 인터페이스이지 measured network/physics delay model의 검증은 아님 |

[실행 entry](https://github.com/merlresearch/llawco/blob/0f08a418295840829b9e5aa012ab562912298363/LLawCo_partnr/scripts/run_exp.sh), [LLawCo 설정](https://github.com/merlresearch/llawco/blob/0f08a418295840829b9e5aa012ab562912298363/LLawCo_partnr/habitat_llm/conf/baselines/llawco.yaml), [ReAct 설정](https://github.com/merlresearch/llawco/blob/0f08a418295840829b9e5aa012ab562912298363/LLawCo_partnr/habitat_llm/conf/baselines/decentralized_zero_shot_react_summary.yaml), [GT graph](https://github.com/merlresearch/llawco/blob/0f08a418295840829b9e5aa012ab562912298363/LLawCo_partnr/habitat_llm/conf/world_model/gt_graph.yaml).

### 3.2 MECoBench와 CoCoBench: no_comm에도 남는 공통 정보가 다르다

여기서 발견한 것은 **그 벤치마크가 스스로 택한 정보 계약의 차이**다. 그 논문의 부정행위나 UGRP의 누설 버그라고 부르지 않는다.

**MECoBench** [2026-06 preprint 원문](https://arxiv.org/html/2606.31966v1), 공개 commit `219d429ae663fc9449bbb99fab5eee9fbe314cc7`(2026-07-01):

- `eval/main.py:231–249`는 simulator graph에서 만족 객체 목록을 계산하고, 모든 agent에 observation과 `self.satisfied`를 넘긴다. `VLM.py:293–339`에서 후자는 `task_progress`로, `prompt_tranfer.py:304–306`에서 prompt로 들어간다.
- 같은 driver는 comm phase → 각 agent action planning → `scene.step(scripts)` 순서다. 이 경로에서 대화 wall time 동안 physics가 계속 진행한다고 볼 근거가 없다.
- `no_communication` flag는 single-agent prompt도 선택한다. 단, 문자열 `communication_mode='no_comm'`만 별도로 고른 모든 경로에 동일한 prompt 변화가 생긴다고 일반화하지 않는다.
- sequential broadcast/discuss는 같은 round의 앞 agent 메시지를 뒤 agent가 본다. SharedMemory는 action 뒤 memory를 다음 agent에 전파한다. LeaderWorker에는 text-only와 workers의 composite image를 받는 선택이 따로 있다.

[driver](https://github.com/q-i-n-g/MECoBench/blob/219d429ae663fc9449bbb99fab5eee9fbe314cc7/eval/main.py), [VLM context](https://github.com/q-i-n-g/MECoBench/blob/219d429ae663fc9449bbb99fab5eee9fbe314cc7/eval/agents/VLM.py), [protocols](https://github.com/q-i-n-g/MECoBench/blob/219d429ae663fc9449bbb99fab5eee9fbe314cc7/eval/agents/protocols.py).

**CoCoBench** [2026-08 preprint 원문](https://arxiv.org/html/2608.28266v1), 공개 commit `a12d47a72c5d2ac854a0b9e18056048dba572cce`(2026-09-05):

- distributed policy는 자기 이미지·자기 history를 사용하되 **각 menu에 모든 task object 이름이 있다**고 명시한다.
- none/broadcast 모두 `_build_goal_progress(obs)`를 받는다. 이는 `obs.eval.checks[*].passed`와 predicate를 사람이 읽을 수 있게 만든 simulator goal-progress이다.
- 각 agent가 같은 snapshot으로 병렬 결정하고, AI2-THOR 호출은 순차로 실행된다. 방송은 다음 round에 보인다.

[distributed policy](https://github.com/AgibotGeneral/CoCoBench/blob/a12d47a72c5d2ac854a0b9e18056048dba572cce/benchmark/eval/distributed_policy.py), [goal-progress builder](https://github.com/AgibotGeneral/CoCoBench/blob/a12d47a72c5d2ac854a0b9e18056048dba572cce/benchmark/eval/vlm_policy.py#L333).

**우리 추론:** 이들과 protocol 이름이 같아도 actor가 이미 아는 사실과 시간 모델이 달라 효과 크기를 직접 비교할 수 없다. UGRP의 fixed-enum sync, 자기 command rejection, 지도·주문·역할도 동일하게 “공통/사적/심판 전용/시간·실패 feedback” 정보 출처표에 넣어야 한다. referee-free를 주장하려면 이미지 입력이라는 표면만 볼 수 없다.

### 3.3 CaPo·CoTS: 토론의 가치와 시간 지평은 상호작용한다

[CaPo, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/b07091c16719ad3990e3d1ccee6641f1-Abstract-Conference.html), [원문 v2, 2025-03-01](https://arxiv.org/html/2411.04679v2), [공식 코드](https://github.com/jliu4ai/CaPo). §4, Appendix A.5–A.6/B를 확인했다. designated proposer와 동료 평가, progress-adaptive meta-plan이 선행한다. Appendix A.5의 토론 round 증가는 transport에서 단조 개선이 아니다. A.6의 이동 비용이 통신보다 크다는 논리는 해당 장거리 과제 맥락이다. B의 observation은 RGB-D 외에도 agent world position/rotation, held-object 정보, 선택적 oracle perception을 포함한다. 비용 표의 oracle 조건을 RGB-only에 외삽하지 않는다.

[CoTS, CVPR 2025 게재](https://openaccess.thecvf.com/content/CVPR2025/html/Zu_Collaborative_Tree_Search_for_Enhancing_Embodied_Multi-Agent_Collaboration_CVPR_2025_paper.html), [저자 제공 본문+부록](https://panzhous.github.io/assets/pdf/2025-CVPR-CoTS.pdf), [공식 코드](https://github.com/lz-zu/CoTS). §3–5, Fig.6, Appendix A.2/C를 확인했다. §5.3은 짧은 500-step 구간에서 CoELA보다 낮다가 더 긴 구간에서 높아지는 양상을 보고한다. 이는 방법 전체의 horizon-dependent 결과이지 순수 message latency의 인과 추정은 아니다. tree search·reward·plan evaluator와 CoELA 계열 RGB-D execution이 함께 바뀐다.

**우리 추론:** 한 beam 파일럿은 long-horizon 계획의 상각 이득이 작은 설정일 수 있다. 대화가 한 번 절약한 이동과 그 대화가 초래한 claim 만료를 같은 clock에서 비교해야 한다. 큰 언어모델이나 tree search로 갈아타는 제안은 여기서 나오지 않는다.

### 3.4 AgentComm-Bench: 통신 필요성을 task interface가 만들어낼 수 있다

[원문 2603.20285v1, 2026-03-18](https://arxiv.org/html/2603.20285v1). **preprint**, 게재 확인 없음. §§3–6, Appendix A.1/A.6을 확인했다. 20×20 grid의 네 heuristic agent이므로 물리 로봇·LLM 실험으로 인용하지 않는다.

NAV에서는 coordinator만 waypoint를 알고 noComm agent는 목표를 몰라 random walk를 한다. 이것은 **목표 전달이 필요한 인터페이스**의 결과다. 반대로 CP clean 조건은 noComm과 comm 결과가 같으며 저자가 통신 필요성을 검증하지 못한다고 인정한다. one-hot encoding 때문에 compressed/event-trigger/full이 NAV/SEARCH에서 같아지는 것도 본문이 명시한다. stale/conflicting content는 perception을 해칠 수 있다. 공통 bit budget 아래 redundancy의 이점도 encoding/truncation에 의존한다.

**우리 추론:** 성공 차이가 없으면 task가 나쁜 것이라고 바로 바꾸지도 말고, 큰 차이를 만들기 위해 한쪽에 주문서를 숨기지도 않는다. UGRP의 공통 주문·역할은 보존하고, 필요한 사적 정보가 원래 환경·관측 계약 안에 존재하는지 먼저 증명한다. 이 preprint의 권고를 이미 합의된 학계 표준이라고 쓰지 않는다.

## 결과가 나온 뒤에도 남는 경쟁 설명

| 기여 후보 | 가장 강한 반대 해석 / 반례 | 둘을 가르는 최소 증거 | 음성 결과이면 남길 더 좁은 주장 |
|---|---|---|---|
| **peer가 사적 관측을 공유해 운반을 개선** | 메시지가 새 정보를 주지 않고 추가 호출·새 이미지 시점·5 SIM초 claim 정렬만 바꿨을 수 있다. | 동일한 합법 prefix에서 real / 외생 schedule의 envelope-only / no-delivery를 구분. 정보 출처와 receiver의 허용 행동 차이를 연결. 현재 own-RGB 위험 근거 규칙 유지 | “이 protocol 묶음은 claim/timing을 조율했다.” 정보 공유의 물리 효과는 미입증 |
| **no_comm보다 좋아서 대화가 구조적으로 필요** | no_comm에도 map/order/fixed roles, lower-level fixed-enum pair-status, 공통 규약·물리 결합이 남는다. 약한 noComm LLM의 실패일 수 있다. | 어떤 주체(actor/executor)가 실제로 무엇을 받는지 표기. sender만 구별하는 상태쌍과 receiver의 서로 다른 필수 허용 행동을 증명. 무대화의 필수 주문 정보를 제거하지 않음 | “고수준 dialogue-off 기준선 대비 효과.” zero-information/zero-coordination 우월 또는 NL 필수성은 주장하지 않음 |
| **자유 자연어가 structured보다 낫다** | NL에만 필요한 사실/순서/복구 이유가 허용되거나, reasoning·호출 수·schema coverage가 다르다. | 같은 source evidence·timestamp·uncertainty·fact bank의 두 표현을 먼저 비교. 형식만의 cost-fixed 진단과 각 형식 실제 비용의 운영 비교를 구별 | “이 표현/필드 집합에서 비슷함”, 또는 “정형 정보로 충분함.” protocol 차이는 남아도 언어 일반 우월은 없음 |
| **비용을 상쇄하는 통신** | 더 낮은 PAR-2는 실패 감소, 성공 시간 감소, 비용 계수·horizon·벌점의 혼합이다. scale=0도 reasoning/전달/결정 시점을 함께 바꾼다. | 원래 SIM endpoint·failure 분모 유지. 성공/실패·조건부 완료시간·call/token·SIM wait를 함께 보임. 미리 정의한 비용 계수/시점 범위의 민감도. 실제 wall은 현 초안대로 참고 | “이 SIM 비용 모델·벌점에서 protocol 효용이 개선/악화.” 현실 장비 비용의 상쇄 또는 순수 정보/비용의 가법 분해는 미입증 |
| **공동 하중·연속 physics라 기존보다 새로운 연구** | FurnMove 등 공동 물체 협력은 선행한다. oracle executor가 없다는 것은 더 강한 입력 제약이지 자동 novelty가 아니다. shared scripted skill이 주요 협력을 이미 해결했을 수 있다. | actor·executor·referee의 입력과 중앙성, 실제 contact/weld/물리 가정을 각각 명시. 동일 executor에서 메시지로 달라진 허용 결정과 결과를 추적 | “제한된 camera-only 실행 계약의 구현/측정 연구.” 새로운 협력 알고리즘·완전 분산 제어·최초 공동운반은 아님 |
| **파지가 가능하므로 통신 연구 준비 완료 / 통신이 파지를 개선** | 한 번 lift/접촉한 feasibility와 안정된 배송·통신 treatment 효과는 다른 주장이다. claim 시점만 달랐거나 동일한 downstream 실패가 조건 차이를 가릴 수 있다. | 파지→이동→release→안정 배송의 단계·심판 정의를 연결. 고정 executor의 지원 범위를 별도 확인하고, treatment 차이는 같은 심판/배정 분모에서 비교 | “이 조건에서 파지/부분 chain이 가능했다.” 통신 성능·안정 배송·robustness로 확대하지 않음. grip monitor는 기존 기록 전용 유지 |
| **peer가 RGB-only 위치 모호성을 해결** | 두 RGB histories의 결합까지 같은 common gauge는 메시지로 해소되지 않는다. posterior 평균/합의는 새 측정이 아니다. 반대로 각자 모른다는 것만으로도 불가능은 아님(XOR) | joint-history indistinguishability negative control과 실제 complementary feature positive witness. time/frame/relative transform·증거 중복을 검사하고 남은 행동 가치까지 확인 | “부분 영상 제약/intent 조율.” global pose/force state 복원이나 모든 부분관측 해결은 아님 |
| **메시지가 행동을 바꿨으므로 유용한 통신** | positive listening이 harmful/무익할 수 있다. 동일 prefix drop은 그 prefix의 continuation 효과이며 초기 noComm 전체 효과가 아니다. | next action과 최종 task outcome을 분리. restore 범위를 검증하고 prefix selection·도달률을 표기. 성공/도착 메시지만 사후 추리지 않음 | “수신 결정에 영향을 줬다.” 효율·성공 향상이나 전 분포 인과효과는 미입증 |
| **leader/역할 분담의 새 효과** | v99/v100은 2로봇·고정 역할·one beam·rule/no_comm/peer_nl이다. leader/structured arm과 자유 역할 선택은 없다. MECo·LLawCo 등 해당 조직·대화 선행도 있다. | 그 질문을 실제 포함하는 별도 설계에서 정보 접근·역할 선택권·call/cost를 맞춰야 함. 현재 pilot 결과로 소급하지 않음 | “고정 pair의 gate/시점·허용 재관측 선택” 범위. 네 조건이나 3로봇 확장 결과는 보류 |
| **합성 power가 높으므로 N/본실험 성능이 검증됨** | 합성 DGP의 failure mass, discordance, partial delivery, time dispersion, intra-block dependence, infra mechanism을 가정한 계산이다. endpoint/분석기까지 바꾸면 다른 연구다. | 실제 초안 primary/fallback/secondary를 나눈 패널, 가정·반복단위·비교검정·MC uncertainty 명시. 불안정/퇴화 조건도 출력. 실제 데이터로 calibrate하지 않았음을 분명히 함 | “이 가정 하의 설계 민감도.” empirical power, 예상 UGRP 효과, 최종 N 권고, α 통제 인증은 아님 |

“실질적 차이 없음”은 비유의성과 다르다. 유효한 equivalence margin·구간 정밀도가 없으면 **검출하지 못함/미정**이라고 쓴다. 실행기가 통신 선택 이전에 모두 실패하면 floor effect이며, 통신의 일반적 무가치 증명이 아니다. 반대로 무대화가 잘 되고 대화가 비용만 늘면, 검증한 지원 범위에서 대화를 생략하는 결과를 그대로 보고할 수 있다.

## 인과 측정 구현을 복사하기 전 확인

이 발견은 UGRP 코드 결함이나 해당 논문의 모든 실험을 반박하는 주장이 아니다. **복사하려는 공개 측정식 자체**를 검사한 결과다. 논문의 개입 논리는 여전히 유용하다.

`facebookresearch/measuring-emergent-comm` commit `95e144cc7eacc3407fe1bbef8d26a06095b03bfc`의 [공식 `eval.py` 내 `calc_cic`](https://github.com/facebookresearch/measuring-emergent-comm/blob/95e144cc7eacc3407fe1bbef8d26a06095b03bfc/measuring_emergent_comm/eval.py)는 p_ac를 정규화한 뒤 다음과 같이 marginal을 만든다.

> `p_a = np.mean(p_ac, axis=0)`

전체 message row 수가 함수 인자 n_comm과 같은 C이고, p(c)와 각 q_c(a)=p(a|do(c)) row가 정규화되어 있다고 하자. 정상 marginal은 sum이므로 코드의 p_a는 p(a)/C다. support에서 로그 비가 정의되면, natural logarithm을 쓰는 그다음 합은 다음과 같다(nats).

\[
\sum_{c,a}p(a,c)\log\frac{p(a,c)}{p(c)\,[p(a)/C]}
=I(A;C)+\log C.
\]

즉 independence에서도 양의 상수 floor가 생길 수 있다. **실행 없이 코드 판독과 대수로 도출한 사실**이다. 이 공개 버전의 값과 모든 출판 숫자가 동일 경로에서 계산됐다고 역추정하지 않는다. UGRP의 black-box response로 이 지표를 “그대로 CIC”라 부르지 말고, 고정 prefix의 action-distribution 차이와 최종 outcome 차이를 별도로 측정하자는 이유다.

최신 #3711883c56 v100은 닫힌 own_status와 idle-only look_around를 이미 추가했습니다([현재 prompt](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L65-L87)). 따라서 claim-only라는 e0ad 당시 표현을 현재 전체 권한으로 쓰지 않습니다. 먼저 정보→현재 허용 행동/재관측 witness와 timing/opportunity를 구분하며, 그 재관측의 실제 이득은 아직 검증한 것이 아닙니다. wait/release의 자기 RGB 위험 조건은 유지됩니다. 1883은 own_status에 partner-caused 자기 결과·시간 신호가 양조건 공통으로 남음을 명시하고 look_around 회복 보장 문구를 완화했습니다. 이 설명 정정을 정보 비간섭 증명이나 실제 복구 성능으로 승격하지 않습니다. 역할·목표를 일부러 한쪽에서 숨기거나 현재 허용 범위 밖의 권한으로 통신 이득을 만드는 것은 별도 연구 변경이며 이 글은 그 실행을 지시하지 않습니다.
