# 7차 연구 검토 — 재관측 선택·준비의 유효기간·적응적 개발의 평가 대상

2026-10-03. 연구 조사 전담. main 기준 `f2577bb5121748644df31eb0fc5a1c1b94b80d80`, #371 현재성 담당이 제공한 정확한 head `1883c56a749dc89597d57f570d4a2243cbb9595d`의 관련 소스를 직접 읽었다. #363 최신 delta의 연구 영향은 현재성 담당의 보고만 사용하며 물리 성과를 독립 확인하지 않았다.

**새로 제안하는 것은 세 가지 질문의 분리다. (1) 통신과 선택적 재관측의 상호작용, (2) 과거의 준비 사실과 현재 유효한 공동 실행 근거, (3) 최종 후보의 성능과 후보를 고른 개발 절차의 성능.** 기존 통신 내용/호출기회/비용 구분, CRN, observability gauge, force closure, PAR2·McNemar·고정 분모·power 문제를 새 발견으로 반복하지 않는다. 아래 설계는 후보이며 기존 본실험 초안의 수정 또는 새 실험 실행 지시가 아니다.

기존 `research-design`, `literature-communication`, `literature-robotics`, `round2-literature-causality`, `round2-observability-design`, `round3-design-sensitivity`, `round3-claim-redteam`, `final-research-issue`, `final-research-references-comment`의 관련 계약·설계·제한을 대조했다. 특히 “성공한 재관측만 고르면 사후 선택”이라는 경고는 이미 있으므로, 이번 추가는 **무엇을 배정해야 식별되는지와 무엇은 여전히 식별되지 않는지**다.

raw·blind·held-out·실제 outcome 파일은 열지 않았다. 실제/합성 실험, LLM/GPU/physics, 제어 코드 변경, 외부 게시를 수행하지 않았다. 증거는 공개 원문·공식 저자 자료와 소스 읽기다. 원문 접근 범위는 `round7-primary-evidence.md`에 따로 기록했다.

## 0. 이번 판단의 현재 소스 경계

| 확인한 소스 | 이번 연구 해석에 필요한 사실 |
|---|---|
| [#371 prompt 50–87](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_prompts_ko.py#L50-L87) | 자기 wrist RGB·정적 지도·own_commands/belief/status·실제 수신 메시지. claim은 고정 절차의 시작 허가이며 wait/release에는 자기 영상의 위험 근거가 필요. 선택적 `look_around`가 추가됐고 회복은 보장하지 않는다고 명시. |
| [#371 dispatch 183–211,305–340](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_dispatch.py#L183-L211) | look 요청은 자기 executor로 전달되어 busy이면 거절됨. snapshot은 자기 call-start별 상태·영상·이력으로 생성. 다른 로봇 snapshot과 같은 값/시각이라는 뜻이 아님. |
| [#371 own_status](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_status.py) | partner-caused refusal/job-end와 시간은 자기 software feedback으로 양 조건에 같은 규칙으로 노출됨을 새 설명이 인정. raw partner reason 이름은 접음. `pair_job_ended`/`look_around_ended`는 물리 성공 판정이 아님. 허용된 이 경로를 새로운 센서 누수 결함으로 지적하지 않는다. |
| [main status barrier 154–206](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_pair_status.py#L154-L206) | 기존에 frame/source-time, readiness TTL, `ready_until_s`, 두 기록의 최소 expiry, control-grid GO, late/expired GO 거절이 이미 있음. TTL/barrier를 새로 만들라는 제안이 아님. 최신 #363의 해당 경로 연결·동작은 별도 runtime 검토 대상. |
| [main executor 312–376](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_pair_executor.py#L312-L376) | `start_ready` rendezvous, partner GO 소비 확인, 영상/command guard와 실제 control tick은 구별된 단계다. LLM 발화/claim 동시성과 motor 실행 동시성을 동일시할 수 없음. |
| [#371 case 271–308](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/1883c56a749dc89597d57f570d4a2243cbb9595d/harness/pair_llm_case.py#L271-L308) | case별 student/LLM 기록·model_usage·metric·hash 산출물이 있음. 그것만으로 “선택에 사용하지 않은 새 평가 코호트”가 되지는 않음. |

현재 2로봇·1beam DEV와 역사적 4조건·6scenario 확증 초안은 별개다. OpenCV, own-wrist, 정적 지도, 발행 명령, 실제 메시지 경계·weld OFF·grip monitor 기록 전용을 유지한다. 아래 어떤 설계도 controller에 GT/contact/joint feedback을 추가하지 않는다.

## 1. 새 blindspot A — 선택적 sensing을 메시지의 매개효과로 자동 분해할 수 없다

### 원문이 지지하는 구별

[Imai–Keele–Tingley 2010, pp.312–313](https://imai.fas.harvard.edu/research/files/BaronKenny.pdf)는 treatment를 무작위화해도 mediator는 자동 무작위화되지 않는다고 설명한다. 자연 직접/간접 효과에는 추가 식별 가정이 필요하며, treatment 이후 생긴 교란변수를 관측했다는 이유만으로 조건화할 수 없다. [VanderWeele–Vansteelandt–Robins 2014](https://biblio.ugent.be/publication/5765162)는 treatment가 mediator–outcome 교란을 만들 때 자연효과의 비식별 문제와 다른 분해를 다룬다. 후자는 공식 초록까지만 확보했으므로 대안 weighting 알고리즘의 채택 근거로 사용하지 않는다.

[He 등, ICRA 2025 / arXiv v3 §III](https://arxiv.org/html/2404.00769v3)는 계획 당시 expected information gain과 관측 뒤의 specific information gain을 구별한다. UGRP의 `look_around_ended`는 둘 중 어느 정보량도 아니며, PF entropy 감소도 모델 내부의 변화다. 그 논문의 RGB-D·scene representation·online estimator·regret 보장은 현 OpenCV/no-weld 운반에 승계하지 않는다. [공식 README](https://github.com/grasp-lyrl/active-perception-game)는 baseline/improved pipeline과 predictive uncertainty/evaluation error의 별도 저장을 제공한다. 여기서 가져올 것은 **예측·실현된 관측·임무 결과를 별도 기록하는 구조**이지 NeRF/GPU 도입이 아니다.

### UGRP에서 생기는 추가 경로 — 검토자의 인과모형

`통신 허용 C → claim 시점·busy/idle L → 실제 look 실행 A → 새 영상 O → 다음 행동 → Y`이며, `L → Y`와 `C → Y`도 가능하다. 숨은 물리 난도·관측 난도가 A와 Y를 함께 바꿀 수도 있다. C를 episode 시작에 배정했더라도 A/L은 이후 변수다. 따라서 다음 문장은 정당화되지 않는다.

- “look을 한 시행끼리 비교했으므로 정보효과다.”
- “Y를 통신·look 횟수·busy 시간에 회귀한 통신 계수는 직접효과다.”
- “전체 통신효과에서 look-disabled 통신효과를 빼면 관측으로 매개된 비율이다.”

마지막 차이는 아래 **capability 상호작용**으로는 정의할 수 있으나 자연 간접효과가 아니다. 시간·reachability·비용·메시지 해석도 함께 바뀔 수 있다.

### 가장 작은 배정 설계

S는 “기존 fixed skill의 필수 scan”이 아니라 **LLM이 추가 idle-only look을 선택할 권한**이다. 이미 있는 저수준 관측·안전 guard는 네 조건에서 같게 둔다. S=0 정책은 그 선택을 action menu에서 제외하고, 결과 후 invalid-action만 drop하지 않는다. S=1도 모든 look을 강제하거나 busy guard를 무시하지 않는다. 네 정책의 prompt 차이·공통 budget/cost rule·judge·stopping rule을 실행 전에 고정한다.

| 사전 배정 | 선택적 look OFF, S=0 | 선택적 look ON, S=1 |
|---|---|---|
| 고수준 dialogue OFF, C=0 | Y00 | Y01 |
| 고수준 dialogue ON, C=1 | Y10 | Y11 |

`μcs = E[Y | 사전 정책(C=c,S=s)에 배정]`, `ΔC(s)=μ1s−μ0s`, `I=ΔC(1)−ΔC(0)`로 정의한다. I의 부호는 **고정한 outcome 척도**에 의존한다. 높은 값이 좋은 outcome인지 먼저 정하고 PAR2이면 방향을 명시한다. 이 네 평균의 대비는 해당 capability들의 운영상 보완/대체를 묻는다. “상호작용이 있으므로 사적 영상정보가 매개했다”는 결론은 나오지 않는다.

식별에 필요한 것은 treatment 전에 고정된 대상 episode 분포, 각 cell에 양의 확률을 주는 결과 독립 무작위 배정, arm 간 리셋/버전 동일성, 결과를 보고 바뀌지 않는 분모다. 또는 같은 사전 instance block마다 네 정책을 모두 실행하고 순서를 무작위화해 기간/실행 순서 영향을 다룰 수 있다. 네 정책의 전체 bundle 이외 실행 계약을 고정하고, 다른 run의 피드백·상태가 다음 run으로 넘어가지 않아야 한다. 동일 seed가 완전한 pathwise counterfactual을 뜻하지 않는 기존 CRN 제한은 그대로다. 팀 episode를 단위로 삼으며 두 로봇을 독립 표본으로 세지 않는다. 실제 look을 했는지·busy였는지로 사후 표본을 자르지 않는다. 대상 instance가 고정된 좁은 set이면 평균효과의 범위도 그 set에 한정한다.

**네 cell은 상호작용을 묻는 경우의 최소 정책 조합이지, 당장 수행할 최소 표본수나 의무 실험수가 아니다.** 질문이 “현재 S=1에서 peer 정책이 유익한가”뿐이면 Y01↔Y11 두 정책으로 충분하다. 추가 두 cell은 통신 이득이 sensing 권한에 의존하는지 궁금할 때만 필요하다.

### 최소 진단과 읽는 방법

| 필수 항목 | 구체안 |
|---|---|
| **다음 판별질문** | 통신 이득이 새 look 권한이 있을 때만 생기는가, 아니면 기존 claim/timing 경로만으로도 남는가? |
| **비교조건** | 먼저 frozen legal prefix에서 look 요청의 허용/거절·발행까지 source trace를 확인. 정책 효과는 위 episode 배정 2개 또는 4개 cell로 별도 설계. prefix 분석은 그 reached-prefix에 한정. |
| **오류가능성** | C가 만든 busy/idle로 층화하면 무작위성이 사라질 수 있음. 두 cell의 live call·image 수를 사후 같게 잘라내면 정책효과가 달라짐. look 모션 없이 다른 arm의 새 이미지를 삽입하면 실현 가능한 counterfactual이 아닐 수 있음. |
| **무엇을 주장 못하는가** | 자연 직접/간접효과·매개비율, 정보량 증가, 더 좋은 시각 grounding, 모든 task에서 NL 필요성. I의 검정이 비유의하다는 결과는 동등성 아님. |

look의 record-only chain은 `선택/그 근거 → 요청 → accepted/rejected → job end → 새 frame hash/source time → observer/likelihood/fix의 새 증거 → 이후 허용 행동 → episode endpoint`다. **job end, 새 frame, admitted fix, 임무 성공을 네 개의 다른 사건으로 유지**한다. 어떤 단계가 기존 로그만으로 식별되지 않으면 unknown으로 남기며 raw GT를 actor에게 보내지 않는다. 정보량을 새 수치로 발명하거나 새 gate를 먼저 추가할 필요는 없다.

## 2. 새 blindspot B — “각자 준비했던 적 있음”과 “같은 실행 시점에 유효한 근거”는 다르다

### 정리가 주는 것과 주지 않는 것

[Moses, TARK 2015 proceedings / EPTCS 2016, Theorem3.1](https://arxiv.org/html/1606.07525v1)는 주어진 runs model에서 conscious action의 필요조건 ψ가 있으면 Kᵢψ도 필요하다는 정리다. Theorem4.3은 **그 model에서 반드시 동시에 실행되는** 행동들의 필요조건에 common knowledge를 연결한다. 이는 실패도 허용하는 LLM에 “자신감이 있으면 정리가 충족됨”을 부여하는 결과가 아니며, Kᵢψ는 자연어로 “안다”는 발화가 아니다. 충분조건·성공보장·현 UGRP 불가능 정리로 사용하지 않는다.

[Halpern–Moses 1990, §11 pp.572–574](https://groups.csail.mit.edu/tds/papers/Halpern/JACM90.pdf)는 정확한 동시성과 일정 시간 창 안의 조율을 구별한다. 특히 **한때 참이면 계속 참인 stable fact와 일시적인 사실이 다르다.** ε-창에서 각자 사실을 안 적이 있다는 형태는 모두가 지금 그 사실을 안다는 명제가 아니며, 논문은 비안정 사실에서 관련 knowledge axiom의 실패도 설명한다. 이 점이 claim/ready를 해석할 때 새로 유용하다.

UGRP에서는 “r1이 시각 t에 claim했다”는 과거 사건과 “r1이 지금 작업 가능/영상 근거가 fresh하다”를 구별해야 한다. “5초 안에 둘 다 준비를 말했다”만으로 두 준비의 **유효기간이 겹치거나 실제 두 구동이 동기화되었다**고 말할 수 없다. 이는 물리 불가능 주장이 아니라 어떤 사건을 측정했는지의 문제다.

### 기존 구현을 인정한 연구 설계

main의 `zone_pair_status._StatusBarrier`는 이미 `ready_until_s`, 두 ready 기록의 최소 expiry, control-grid GO와 late/expired 방지를 갖고 있다. 따라서 새 의무 ACK·새 강제 grip·TTL gate를 추가할 이유가 아니라, **LLM 발화 → claim 허가 → Team.start 수락 → ready 근거 → software GO → 실제 운동/임무 결과** 중 어디의 개선을 “조율”이라고 부를지 고르는 이유다. 특정 GO에서 쓴 근거의 유효구간과 commit 시점을 현재 로그로 연결할 수 있는지 먼저 묻는다.

| 층 | 허용 증거로 확인할 명제 | 확인되지 않는 상위 주장 |
|---|---|---|
| 발화·intent | 그 sender가 그 source-time/주문에 대해 준비/재관측 의도를 보냄 | 상대가 받음, 받아들임, 지금 물리적으로 준비됨 |
| 자기 software feedback | 자기 claim이 released/refused/submitted, 자기 job이 running/ended | partner 원인의 세부 상태, 물리 배송 성공 |
| 기존 low-level barrier | 같은 task/phase의 현 근거, deadline/expiry 안 software GO·소비 기록 | 실제 joint/contact 상태가 참, 기계적 동시성·force closure |
| 독립 평가 결과 | 고정 judge의 endpoint, 필요하면 별도 평가의 시간 정렬 | 그 결과가 고수준 대화의 common-knowledge 형성 덕분이라는 자동 귀속 |

[Nayyar–Mahajan–Teneketzis 2013, §II/VI](https://adityam.github.io/files/projects/info-structures/journal/partial-sharing.pdf)는 현재 observation, private memory, shared memory를 구분하고 shared memory의 perfect recall을 이용한다. **같은 입력 schema를 양쪽에 주는 것은 같은 realized shared memory를 주는 것과 다르다.** `own_status`의 상대 영향이 양 arm에 같은 규칙으로 공개돼도 각 로봇의 실제 값·call 시각은 다를 수 있다. 또한 sender가 보냈다는 기록과 recipient가 prompt에서 읽었다는 기록은 별개다. 이 논문의 가상 coordinator는 수학적 정책 표현이며, UGRP에 중앙 GT coordinator를 추가하는 제안이 아니다.

### 검증 가능한 작은 질문

| 필수 항목 | 구체안 |
|---|---|
| **다음 판별질문** | peer가 줄인 것은 claim 불일치/유효기간 만료/중복 look 중 어느 것인가? ready 근거가 살아 있는 software 실행 기회를 실제로 늘렸는가? |
| **비교조건** | 같은 사전 legal prefix 집합에서, 현 sender 증거를 source-time 그대로 유지한 fresh 대 expiry-near/stale 전달을 구별. 필요하면 call/전달 기회를 외생 고정한 기존 envelope 진단을 재사용. 이미 공통인 low-level wire·own_status는 유지. |
| **오류가능성** | `since_claim_s`를 readiness age로 오인; job-end를 성공으로 오인; 두 로봇 ready 시각 차이만으로 interval overlap 판정; 한 source의 readiness를 재전송한 것을 새 관측으로 계수; elapsed/absolute SIM clock 혼용. |
| **무엇을 주장 못하는가** | 완전 분산 물리 동시성 보장, 무통신 불가능, LLM이 common knowledge를 보유함, TTL software 통과가 실제 파지·접촉 안정성을 증명함. |

진단 단위는 `task/phase 또는 job 식별자 + 근거 source-time + software 유효기간 + 수신/사용/GO 시각`이다. 이미 존재하는 키/로그로 연결할 수 있는 범위에서만 record-only 분석한다. 분석용 evidence ledger는 actor prompt에 숨은 상태를 더 주는 통로가 아니다. 현재 no_comm을 “명시적 고수준 dialogue-off, 기존 software feedback/저수준 sync 유지”로 부르는 것은 그대로 맞다.

유한한 trace의 통과만으로 모든 indistinguishable run에 관한 Kᵢψ를 입증할 수 없다. 위 표는 **증거가 어느 결정에 실제 사용됐는지의 감사**이며 formal epistemic verification이 아니다. 현재 상황과 같은 local input인데 필요조건이 다른 허용 반례가 발견되면 특정 지식 주장을 반증할 수 있지만, 반례를 못 찾았다는 사실을 일반적 지식 보장으로 바꾸지 않는다.

## 3. 새 blindspot C — frozen SHA만으로 평가 대상의 선택 과정까지 동결되지는 않는다

### 원문과 UGRP로의 제한된 적용

[Cawley–Talbot 2010, §5–6](https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf)는 유한 자료의 noisy selection criterion에 대한 최적화가 성능 추정에 선택 편향을 만들 수 있고, 알고리즘 성능을 평가할 때 selection까지 procedure의 일부로 취급해야 한다고 보인다. UGRP는 학습 weights뿐 아니라 prompt, feature threshold, scan schedule, witness scenario, endpoint와 cost coefficient도 DEV 피드백을 따라 선택할 수 있다. 이 목록은 **가능한 선택 경로**이며 실제 특정 held-out이 오염됐다는 판정이 아니다.

[Blum–Hardt 2015, §2–3/Algorithm1](https://proceedings.mlr.press/v37/blum15.pdf)는 raw label을 공개하지 않아도 이전 점수를 보며 제출을 바꾸는 adaptive evaluation을 다룬다. Ladder는 의미 있는 개선 때만 양자화된 best score를 공개하는 특수 leaderboard 절차이며, 모든 후보의 정확한 점수나 임의 로봇 디버깅을 보장하지 않는다. 현재 UGRP에 Ladder 구현을 선행조건으로 두지 않는다. 가져올 함의는 **raw 비공개와 평가 피드백 비사용은 서로 다른 조건**이라는 점이다.

### 평가할 정책·대상 분포·개발 절차를 구분

F는 평가되는 고정 정책, W는 선택된 조건/target 분포, P는 후보 선택·수정 절차를 가리킨다. **F와 W는 배타적이지 않다.** 고정 artifact F를 선택된 witness 분포 D_W에서 평가할 수 있으며, 이때 두 표지를 함께 명시한다.

| 평가 대상 | 정당한 설계/보고 | 다른 대상으로 확대하면 생기는 오류 |
|---|---|---|
| **F: 최종 고정 artifact** | DEV에서 자유롭게 개발한 뒤 전체 실행 bundle·policy·judge·target distribution·analysis를 고정하고, 그 선택에 사용하지 않은 새 instance에서 평가 | DEV 시도들을 최종 정책의 표본처럼 합침. 이후 patch가 난 뒤 이전 holdout 수치를 그대로 새 후보 성능이라 함 |
| **W: 선택한 실패/witness target 분포** | 실패 사례로부터 선택한 조건·선택 이유·지원 범위를 공개. 새 instance가 독립이면 고정 후보 F도 그 **선택된 조건 분포 D_W**에서 평가할 수 있음 | fresh seed만 있으면 원래 모든 task/맵·관측 난도에 일반화한다고 함. 선택한 사적 정보 witness에서의 통신 이득을 일반 평균효과라고 함 |
| **P: 개발/수정 절차 전체** | 외부 task block마다 후보 선택·튜닝·실패 진단을 포함한 전체 절차를 다시 수행하고, 같은 수정 예산·초기 정보·종료규칙 아래 외부 평가 | 한 번 사람이 여러 실패를 보고 고른 최종 SHA만 평가해 “이 개발 방법이 잘 일반화함”이라 함 |

현재 목표가 F이면 비싼 nested 재개발 실험은 필요하지 않다. **고정 후보 F의 평가와 개발 절차 P의 평가를 구별하는 것이 핵심**이다. F의 새 평가에서도 map/initialization 범위를 DEV 결과를 보고 선택했다면 그 선택된 target을 명시하면 된다. W에서 얻은 결과는 유효한 engineering/기전 진단이 될 수 있지만, 더 넓은 target 분포에서의 F 성능으로 확대할 수 없다.

P의 외부 block 평가에서는 개발 규칙·초기 정보·예산·종료규칙을 미리 고정한다. 앞 block의 외부 평가 피드백을 보고 다음 block의 수정 규칙까지 바꾸면 같은 고정 절차를 반복한 것이 아니다. 이런 cross-block 학습을 허용하려면 그 업데이트 규칙·허용 피드백까지 포함한 별도 adaptive procedure를 평가한다고 명시해야 한다.

### 작고 실행 가능한 동결/개봉 규칙 후보

기존 P06 고정 분모를 새로 만들자는 제안과 다르다. P06에 붙일 **selection lineage**가 이번 추가다.

1. DEV registry에는 후보 bundle, 변경 이유, 의사결정에 사용한 공개 case ID/요약, 후보 폐기까지 남긴다. raw를 다시 열거나 비공개 결과를 registry 작성 목적으로 요구하지 않는다.
2. 결과를 보기 전에 고정 후보 F 또는 개발 절차 P 중 무엇을 평가할지, target이 선택된 witness 분포 W인지 더 넓은 분포인지 함께 적는다. 대상 instance 생성 규칙/고정 scenario weights, 제외·unknown 규칙, horizon/비용/분석을 고정한다. “새 seed” 외에 어떤 물리 초기화/관측 조건이 달라지는지 정의한다.
3. 기존 검사에서 source/배정/정의 계약을 위반했을 때의 invalid 판정과 task 실패를 구분한다. 고정 평가의 실패를 보고 후보를 고치면 새 버전의 DEV로 돌아간다. 이전 평가는 이전 artifact의 유효한 결과로 보존하되 새 후보의 독립 validation으로 재사용하지 않는다.
4. 시험 종료 뒤 수정된 후보는 결과에 맞춰 옛 평가를 소급 무효화하지 않는다. 새 독립 평가의 필요 여부는 **어떤 새 성능 주장을 할지**에 따라 정한다. 버그 수정 사실만 보고하는 경우에 매번 새 물리 코호트가 필수인 것은 아니다.
5. 공개 실패 회귀 suite는 축적해도 좋다. 그 suite를 통과한 횟수를 독립 generalization 표본수로 세지 않는다. 모든 검토자가 완전 블라인드여야 한다는 새 절차를 요구하지 않으며, 실제로 누가 어떤 피드백을 선택에 썼는지만 기록한다.

| 필수 항목 | 구체안 |
|---|---|
| **다음 판별질문** | 다음 결과는 고정 후보 F와 수정 절차 P 중 무엇을 평가하며, 그 target은 선택된 witness 분포 W인가 더 넓은 분포인가? |
| **비교조건** | 같은 고정 artifact/배정에서 사전 target 분포와 선택된 witness 분포를 별도 strata로 보고. F가 목표이면 새 독립 instance만 사용; P가 목표일 때만 전체 선택절차의 외부 반복이 필요. |
| **오류가능성** | commit 직전 test score를 보고 모델/조건을 골랐는데 “freeze 후 실행”만 강조; sealed 점수/pass-fail을 계속 본 뒤 같은 set을 holdout이라 유지; failed run만 바꿔 재실행한 것을 균형 반복이라 합침; scenario weighting을 결과 후 변경. |
| **무엇을 주장 못하는가** | 해시 동결만으로 독립성 보장, DEV에서 가장 잘 된 조건의 평균을 broad task 평균으로 표현, 수정된 pipeline들을 한 stationary policy 표본으로 합산, finite budget의 탐색 실패를 통신 무가치로 일반화. |

## 4. 우선순위와 게시용 축약 문장

현재 DEV를 2×2 본실험 때문에 멈출 필요는 없다. 먼저 최신 고정 경로에서 **look requested/accepted/ended와 fresh visual evidence**, **claim/start/GO의 사건 의미**, **다음 평가의 정책/절차 F·P와 target 분포 W**를 구별해 기록하면 된다. 물리 chain이 통과한 뒤 통신×look 상호작용이 연구 질문으로 남을 때 해당 4개 정책 조합을 선택한다. 기존 historical 본실험의 arm 수나 sample size를 이 표로 소급 교체하지 않는다.

> 추가 연구 질문은 세 가지입니다. `look_around`가 생겼으므로 실제 look을 실행한 시행만 비교하지 말고, 필요할 때 통신 허용×선택적 look 허용의 사전 정책 대비를 사용합니다. 이 상호작용은 정보의 매개효과가 아닙니다. 두 로봇이 준비를 말한 시각 차이와 기존 low-level readiness 근거가 동시에 유효한 software GO는 구분합니다. TTL/barrier는 이미 있으므로 그 trace를 활용하며 물리 파지 보장을 뜻하지 않습니다. 마지막으로 새 평가가 고정 후보와 수정 절차 중 무엇을 시험하는지, 대상이 선택된 witness 분포인지 명시해야 합니다. 고정 후보를 witness 분포에서 평가할 수 있지만 새 seed가 그 밖의 일반화를 자동 보장하지는 않습니다.

독립 검토 완료: `round7-independent-validation.md` §2에서 2×2 식별/interaction의 범위와 KoP의 필요조건·시간 모델 적용을 확인했다. C축 보강 권고에 따라 F와 W의 비배타성 및 P의 outer-feedback 경계를 위에 반영했다. 논문/코드 재현·효과 크기 추정·통계 검정 결과는 이 메모에 없다.
