추가 연구 검토 — **통신과 선택적 재관측의 상호작용, 준비 근거의 유효기간, 평가할 후보와 선택 절차를 구분합니다.** #371 고정 `1883c56a749dc89597d57f570d4a2243cbb9595d`의 입력·행동 source와 primary 문헌을 대조했고 별도 검토자가 핵심 추론을 확인했습니다. 새 실험·모델·물리·raw/heldout 열람·prereg 수정은 없습니다. 아래는 기존 4조건 초안을 소급 변경하는 지시가 아니라 선택 가능한 연구 설계입니다.

## 1. 실제 look 시행의 단순 비교만으로 통신 효과를 식별할 수 없습니다

v100의 선택적 idle-only look은 통신 이후의 행동입니다. 통신이 claim 시점·busy 상태를 바꾸고, 그것이 look 가능성·새 영상·결과를 함께 바꿀 수 있습니다. 따라서 “look 시행끼리 비교” 또는 “통신과 look 횟수를 함께 회귀”만으로 메시지의 직접/간접 정보효과를 얻지 못합니다. [Imai–Keele–Tingley 2010, pp.312–313](https://imai.fas.harvard.edu/research/files/BaronKenny.pdf)은 treatment 무작위화와 mediator 식별 가정을 구별합니다. 아래 UGRP 적용은 검토자의 인과모형입니다.

현재 선택적 look이 있는 정책에서 peer의 총효과만 묻는다면 no_comm/peer 두 정책이면 됩니다. 그 이득이 **선택적 look 권한에 의존하는가**가 별도 질문일 때만 다음 네 정책을 고려합니다. S는 기존 fixed skill의 필수 scan이 아니라 LLM의 추가 look 선택권입니다. OFF에서는 사전에 action menu에서 제외하며 결과를 보고 look action만 사후 삭제하지 않습니다. ON에서도 busy guard를 무시하거나 모든 look을 강제하지 않습니다.

| 사전 정책 배정 | 선택적 look OFF, S=0 | 선택적 look ON, S=1 |
|---|---|---|
| 고수준 dialogue OFF, C=0 | μ00 | μ01 |
| 고수준 dialogue ON, C=1 | μ10 | μ11 |

고정한 outcome 척도에서 `ΔC(s)=μ1s−μ0s`, `I=ΔC(1)−ΔC(0)`입니다. I는 **두 권한 정책의 상호작용**이며 자연 간접효과·매개비율이 아닙니다. prompt·시간·reachability·비용도 함께 바뀔 수 있습니다. PAR2처럼 작을수록 좋은 척도에서는 방향을 명시합니다.

사전 target episode 분포, 잠재 결과를 보지 않는 무작위 배정, 각 cell의 양의 배정확률, 고정 분모·judge·budget·stopping rule이 필요합니다. 동일 instance block의 네 정책을 모두 실행한다면 순서 무작위화·같은 reset·run 사이 상태/피드백 비전달도 필요합니다. 같은 seed가 완전한 counterfactual을 만들지는 않습니다. 팀 episode가 단위이며 로봇 둘을 독립 표본으로 세지 않습니다. 실제 look/busy 여부로 배정 뒤 표본을 자르지 않습니다. 네 cell은 질문의 최소 정책 조합일 뿐 의무 실험수·권장 표본수가 아닙니다.

다음 record-only 연결이면 무엇이 미확인인지 알 수 있습니다.

`선택 근거 → 요청 → accepted/rejected → job end → 새 frame hash/source time → observer/likelihood/fix → 다음 허용 행동 → episode endpoint`

job end·새 frame·admitted fix·임무 성공은 서로 다릅니다. [He 등, Active Perception Game §III](https://arxiv.org/html/2404.00769v3)도 기대 정보이득과 관측 뒤 정보이득을 구별합니다. 그 RGB-D/scene model·regret 보장을 현재 OpenCV 운반에 승계하지 않습니다. 새 정보량 수치를 발명하거나 NeRF/GPU를 도입하자는 제안이 아닙니다.

## 2. “준비했던 적 있음”과 “같은 실행 시점에 근거가 유효함”은 다릅니다

“r1이 t에 claim했다”는 역사적 사실과 “r1이 지금 작업 가능하고 영상 근거가 fresh하다”는 일시적 사실을 구분합니다. 두 ready 발화가 5초 안에 있었어도 유효기간의 겹침이나 실제 motor 동시성이 자동 보장되지는 않습니다.

[Moses, KoP Theorem3.1/4.3](https://arxiv.org/html/1606.07525v1)은 지정된 runs model·conscious action·필수 동시성에서의 지식 필요조건입니다. LLM의 자신감 발화가 지식이라는 뜻도, UGRP가 불가능하다는 정리도 아닙니다. [Halpern–Moses 1990 §11, pp.572–574](https://groups.csail.mit.edu/tds/papers/Halpern/JACM90.pdf)의 stable fact와 일시적 사실, exact/ε 조율 구별만 제한적으로 적용합니다.

현재 [low-level barrier154–206](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_pair_status.py#L154-L206)는 이미 source-time/TTL·최소 expiry·control-grid GO·늦은 GO 거절을 갖고 있습니다. **새 TTL 결함이나 새 barrier 구현 요구가 아닙니다.** 다음 중 무엇을 “통신이 조율했다”고 부를지 고르는 문제입니다.

| 층 | 확인할 사실 | 자동으로 성립하지 않는 주장 |
|---|---|---|
| intent 발화 | sender가 그 주문·source time의 의도를 보냄 | recipient가 수신/사용함, 지금 준비됨 |
| own software feedback | 자기 claim 허가/거절/제출, 자기 job 종료 | partner 상세 상태, 물리 배송 성공 |
| 기존 barrier | 같은 task/phase에서 유효한 근거·GO·소비 기록 | 접촉/관절/파지의 물리 진실·완전 동시성 |
| 독립 judge | 고정 endpoint 결과 | 대화로 common knowledge가 생겼다는 인과 귀속 |

작은 다음 질문은 claim 불일치·ready expiry·중복 look 중 무엇이 줄었는가입니다. 기존 로그에서 `task/phase/job + 근거 source-time + 유효기간 + 수신/사용/GO 시각`을 연결하고 없는 값은 unknown으로 둡니다. 상위 own_status의 시각 혼용 finding은 별도이며 이 low-level TTL 구현 전체가 깨졌다는 근거가 아닙니다. 유한한 trace에서 정합성을 확인한 것과 모든 구별 불가능한 run에 대한 knowledge 필요조건을 증명한 것은 다릅니다.

[Nayyar–Mahajan–Teneketzis 2013 §II/VI](https://adityam.github.io/files/projects/info-structures/journal/partial-sharing.pdf)가 구분하는 private/shared memory처럼, 양쪽에 같은 status schema를 주는 것과 같은 realized shared history를 주는 것은 다릅니다. own_status의 partner 영향이 양조건 공통 규칙이어도 각 로봇의 값·call 시각은 다릅니다. 수학적 가상 coordinator를 실제 중앙 GT actor로 도입하자는 뜻은 아닙니다.

## 3. 최종 artifact, 선택한 witness 분포, 개발 절차를 구분합니다

SHA 동결은 이후 bytes를 고정할 뿐 그 후보·scenario·threshold·prompt를 고를 때 쓴 피드백을 없애지 않습니다. [Cawley–Talbot 2010 §5](https://jmlr.org/papers/volume11/cawley10a/cawley10a.pdf)는 selection을 포함한 방법 평가를 구분하고, [Blum–Hardt 2015 §2–3](https://proceedings.mlr.press/v37/blum15.pdf)는 raw label 없이 점수 피드백만으로도 적응할 수 있음을 다룹니다. 특정 UGRP heldout 오염을 발견했다는 주장은 아닙니다. Ladder 구현·보장을 이 로봇 과제의 선행조건으로 두지도 않습니다.

| 표지 | 무엇을 평가하는가 | 정직한 범위 |
|---|---|---|
| F: 최종 artifact | 고정된 전체 bundle·정책·judge | 선택에 사용하지 않은 새 instance에서 그 target 분포의 성능 |
| W: 선택한 witness | 실패/기전 진단을 위해 고른 조건 분포 | fresh seed라도 선택한 분포 밖 모든 task 일반화는 아님 |
| P: 개발 절차 | 후보 선택·튜닝·실패 진단을 포함한 방법 | 외부 block마다 같은 초기정보·예산·규칙 아래 절차를 다시 수행한 결과 |

**F와 W는 배타적이지 않습니다.** F라는 고정 artifact를 W라는 선택된 분포에서 평가할 수 있습니다. F는 정책, W는 target, P는 선택절차를 구분하는 표지입니다. P의 외부 block 결과를 보고 다음 block의 수정 규칙까지 바꾸면 같은 고정 절차의 반복이 아니므로 그 cross-block 적응도 별도 방법으로 명시해야 합니다. 현재 목표가 F라면 비싼 nested 재개발을 요구하지 않습니다.

기존 P06 고정 분모에는 다음 selection lineage만 덧붙일 수 있습니다.

1. 후보·변경 이유·의사결정에 쓴 공개 case/요약·폐기를 남깁니다. registry 작성을 위해 raw를 새로 열 필요는 없습니다.
2. 결과 전에 target 생성 규칙/weights·judge·제외/unknown·horizon·비용·분석을 고정합니다. “새 seed”가 무엇을 새로 바꾸는지 설명합니다.
3. 평가 실패를 보고 고친 후보는 새 DEV 버전입니다. 옛 평가는 옛 artifact의 결과로 보존하고 새 후보의 독립 validation으로 승계하지 않습니다.
4. 버그 수정 사실만 보고할 때마다 새 물리 코호트가 필요한 것은 아닙니다. 어떤 새 성능 주장을 하려는지에 따라 평가 필요성을 정합니다. 회귀 suite 통과 횟수는 독립 일반화 표본수가 아닙니다.

지금 DEV를 네 정책 실험 때문에 멈출 필요는 없습니다. 먼저 look의 요청/종료/새 시각 증거, claim/start/GO의 사건 의미, 다음 평가의 artifact와 target·선택절차만 구분하면 됩니다. 본 보충은 표본수·효과크기·실제 로봇 성공을 새로 추정하지 않았습니다.
