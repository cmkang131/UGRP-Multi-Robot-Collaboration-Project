# 선행 연구는 난이도를 어떻게 조절했나 (2026-11-25 16:45 KST)

사용자 요청(11-25 16:22, 원문): "난이도 올리는 거는 막 올리지 말고, 기존 연구 들은 어떻게 난이도 조절이 되는지 확인해봐"

계기: 사용자 "엄; '로봇마다'가 왤케 잘 성공하지 문제가 너무 쉬운가"(16:18). 확인한 것: 우리 간단 버전(BoxNet1식)은 칸 용량 무제한,
목표 재사용, 로봇 간 충돌 없음이라 "각 로봇이 자기 칸의 가장 가까운 상자를 가장 가까운 목표 쪽으로 한 칸" 독립 규칙
(`map_events.reference_plan`)이 모든 지도를 5~15단계에 푼다.

읽은 범위: 아래는 모두 arXiv HTML 원문에서 해당 문단을 직접 읽음(사본 scratchpad `arx/`). 원문 인용은 짧게만 옮김.

| 연구 | 난이도를 바꾸는 손잡이 | 원문 근거 |
|---|---|---|
| Chen 외, arXiv 2309.15943 (우리 BoxNet의 원본) | (1) 로봇 수: BoxNet1·2는 4·8·16·32대, Warehouse·BoxLift는 4·6·8·10대. (2) 환경 자체를 제약이 더한 것으로 바꿈: BoxNet1 "We assume no collisions" → BoxNet2 "each box can only be moved between cells by being placed at a corner ..., and a given corner can only hold one box at a time; we treat placing two or more boxes on the same corner as a collision (and thus task failure)" → Warehouse(경로 충돌) → BoxLift(여럿이 함께 들기). 같은 구조 네 가지를 네 환경 모두에 돌림 | IV-A Testing Environments |
| Collab-Overcooked, arXiv 2502.20073 | 6단계. "The task complexity level is determined by the minimum number of collaborative actions, increasing linearly with difficulty." 같은 단계 안에서는 흐름이 같고 재료만 다름. 시간 제한 = 최적 완료 시간 × 계수 | A.2.1 Task complexity level, 본문 3절 |
| COHERENT, arXiv 2409.15146 | 필요한 로봇 종류 수로 3범주: 1종(정답 4~8단계), 2종(8~12단계), 3종(그 이상). 정답 단계 수를 함께 제시 | 벤치마크 절 |
| SMART-LLM, arXiv 2309.10062 | 4범주: Elemental(로봇 1대, 협력 불필요) → Simple(여러 물건, 순차 또는 병렬) → Compound(능력이 다른 로봇, 유연한 실행) → Complex(로봇 한 대로는 하위 작업을 못 함, 연합 필요) | 데이터셋 절 |
| PARTNR, arXiv 2411.00081 | 과제 종류 4가지: 제약 없음 / 공간 제약 / 순서 제약 / 한쪽만 할 수 있는 행동 | 서론 |
| LLaMAR (MAP-THOR), arXiv 2407.10031 | 지시의 모호함 4단계: 물건·개수·위치 모두 명시 → 개수 암시 → … → 전부 암시 | 실험 절 |
| TeamCraft, arXiv 2412.05255 | 새 목표 배치, 처음 보는 로봇 수, 새 능력, 새 배경으로 일반화 난이도. 로봇 수가 늘수록 분산 쪽의 중복 작업이 늘었다고 보고 | 서론, 결과 |
| LLM-Coordination, arXiv 2310.03903 (Overcooked-AI) | 배치(layout)마다 재료·냄비·배식구·조리대 배치가 달라 협응 필요 정도가 다름(Forced Coordination 등) | 환경 설명 |

## 읽어 낸 것
1. 난이도는 "막 올리는" 것이 아니라 계단으로 둔다. 각 계단은 질적으로 다른 제약 하나다(충돌 없음 → 한 자리 한 상자 → 경로 충돌 → 함께 들기;
   제약 없음 → 공간 → 순서 → 능력 차이).
2. 계단마다 셀 수 있는 값을 붙인다: 필요한 협력 동작의 최소 횟수(Collab-Overcooked), 정답 단계 수와 필요한 로봇 종류 수(COHERENT).
3. 우리 간단 버전은 Chen의 가장 쉬운 계단(BoxNet1, "no collisions")이다. 다음 계단은 Chen이 이미 정의하고 같은 구조들로 돌린 BoxNet2다:
   상자는 칸의 모서리(두 칸이 함께 닿는 자리)로만 넘기고, 모서리 하나에는 상자 하나만, 겹치면 충돌. 코드도 우리에게 있다
   (`<work>/20261113-l0-planning-env/refs/hmas/env2_create.py`, `env2-box-arrange.py`, `prompt_env2.py`).
4. BoxNet2의 "모서리"는 우리 3D의 "문 주변 넘김 자리"와 같은 것이다. MuJoCo와 실물의 넘김 자리도 상자 하나만 놓인다.
   즉 새 규칙을 만드는 것이 아니라 원본 논문의 다음 단계를 그대로 쓰는 것이다.

## 차이와 주의
- Chen은 충돌을 "판 실패"로 셌다. 우리는 실패한 쪽 로봇만 쉬는 규칙(`--failed-writer idle`)을 쓰므로, 충돌을 어떻게 셀지는 그 규칙에 맞춰 정해야 한다
  (Chen 그대로: 충돌 = 판 실패 / 우리 규칙: 충돌한 행동만 실행 안 됨). 확인 안 됨: 어느 쪽이 구조 비교에 공정한지.
- BoxNet2에서도 독립 규칙이 실제로 막히는지(협력이 필요해지는지)는 지도마다 세어 봐야 한다(필요한 모서리 통과 수, 독립 규칙의 충돌 수).

## 덧붙임: 로봇끼리 주고받는 방식 (2026-11-25 18:10 KST)
사용자(17:59): "흠; 서로 통신할 수 있게 해야하는 거 아닌가", (18:00): "ㅇㅇ 그럼 그렇게 가봐. 선행 연구 최대한 고려해 보고"
→ 지금 방식(차례로 쓰고 뒤 로봇이 앞 계획을 봄)으로 BoxNet2 18판을 먼저 돌리고, 필요하면 아래 원문 방식으로 대화를 넣는다.

원문에서 확인한 것(arXiv HTML):
- Chen 외 2309.15943, III-B: DMAS는 로봇마다 LLM, 돌아가며 말하고 앞 사람들의 말을 이어 붙여 다음 사람 프롬프트에 넣음. "The dialogue ends once the current agent outputs EXECUTE followed by the action for each agent." 우리 지금 방식은 이 대화의 한 바퀴를 고정 순서로 도는 것과 같고, 뒤로 돌아가는 바퀴가 없다.
- 같은 논문의 HMAS-2: 중앙 LLM이 전원의 행동을 내고, 로봇마다 자기 LLM이 "자기 행동을 확인하고 피드백", 반대하면 중앙이 다시 계획, 모두 동의할 때까지 반복. "only the agents that will take an action participate in the dialogue". 논문 결론에서 로봇이 많을 때 가장 좋았던 방식.
- RoCo 2307.04738, 3.2: 각 에이전트가 말 끝에 "토론 계속"과 "모두의 행동을 요약해 최종 제안" 중 하나를 고름. 최종 제안은 이번 대화에서 모두가 한 번 이상 말한 뒤에만 허용. 정해진 횟수 안에서 다시 계획, 넘으면 그 라운드는 실행 없이 끝남.

우리에게 옮길 때(필요해지면): 세 구조에 같은 형태로 "한 번 더 보고 고치기"를 준다.
- 로봇마다 / 여러 팀: 모두 쓴 뒤 전원의 목록을 보여 주고 한 번 고쳐 쓰기(DMAS의 두 번째 바퀴, 최대 한 바퀴로 고정).
- 팀장: HMAS-2처럼 로봇마다 자기 행동을 확인해 이의를 내고, 이의가 있으면 팀장이 한 번 다시 계획.
- 호출과 토큰은 모두 비용으로 센다. 바퀴 수는 1로 고정(축을 늘리지 않음).
