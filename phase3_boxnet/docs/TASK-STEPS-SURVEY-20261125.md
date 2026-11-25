# 선행 연구는 "여러 단계가 필요한 협업 과제"를 어떻게 만들었나 (2026-11-25 02:20 KST)

사용자 요청(11-25 01:19, 원문): "BoxNet 외에, 다른 연구에서는 어떻게 복잡하고 스텝이 필요한 걸 했는지를 좀 찾아봐줘. 분명 비슷한 방법으로 뭔가 한 게 있ㅇ르 거 같은데"

읽은 범위: 아래 표의 [원문]은 arXiv HTML 본문에서 해당 문단을 직접 읽음(내려받은 사본으로 확인). [검색]은 검색 요약 수준이고 원문 대조 안 함. 구조 비교 쪽 조사는 `TASK-DESIGN-SURVEY.md`(11-23)에 따로 있음.

| 연구 | 과제 | 여러 단계와 협응이 필요해지는 이유 | 한 번에 계획하는 양 |
|---|---|---|---|
| RoCoBench, Sort Cubes (Mandi 외, arXiv 2307.04738) [원문] | 로봇팔 3대가 큐브 3개를 각자의 목표 판에 놓기 | 팔마다 닿는 판이 3개뿐(Alice 1·2·3, Bob 3·4·5, Chad 5·6·7). 이웃 팔과 판 하나만 겹침. 큐브를 겹치는 판으로 옮겨 줘야 다음 팔이 받음 | 라운드마다 팔마다 하위 작업 하나(PICK … PLACE 판, 또는 WAIT) |
| RoCoBench, Make Sandwich [원문] | 로봇 2대가 샌드위치 쌓기 | 각자 자기 쪽 재료만 닿음. 정해진 순서로 번갈아 쌓아야 함 | 위와 같음 |
| Collab-Overcooked (Sun 외, arXiv 2502.20073) [원문] | 두 에이전트의 조리 과제 30개 | 서로 격리된 구역, 행동 종류도 다름, 자원을 주고받아야만 진행. 난이도 = 필요한 협력 동작의 최소 횟수, 6단계 | 에이전트별 행동 순서. 성공률 1단계 → 6단계: GPT-4o 94 → 4%, DeepSeek-R1 100 → 30%, Claude Sonnet 4 100 → 58% |
| Overcooked Forced Coordination (LLM-Coordination arXiv 2310.03903, ProAgent arXiv 2308.11339) [검색] | 2인 조리 | 한쪽에 재료, 다른 쪽에 냄비와 배식구. 조리대 위로 넘겨야만 완성 | 확인 안 함 |
| Chen 외(arXiv 2309.15943)의 나머지 환경 [원문] | BoxNet2, Warehouse, BoxLift | BoxNet2: 상자는 칸 모서리로만 넘기고 모서리에 하나만(겹치면 실패). Warehouse: 이동 로봇이 정해진 길의 지점만 한 칸씩 이동, 같은 지점이면 충돌. BoxLift: 무게를 모르는 상자를 여러 대가 함께 들어야 함 | 매 단계 로봇마다 다음 행동 하나("planning is performed incrementally … the next action to take for each agent") |
| PARTNR (Meta, arXiv 2411.00081, ICLR 2025) [원문] | 가정 과제 10만 개(사람 + 로봇) | 과제를 네 종류로 만듦: 제약 없음, 공간 제약, 순서 제약(정해진 순서로 실행), 능력 차이(한쪽만 할 수 있는 행동). 사람 93% 대 LLM 30% | 확인 안 함 |
| COHERENT (Liu 외, arXiv 2409.15146) [원문] | 드론, 로봇개, 로봇팔의 긴 과제 100개 | 로봇마다 할 수 있는 일이 달라 물건을 넘겨야 함(예: 로봇개가 사과를 집어 드론 쪽으로 옮김). 과제를 필요한 로봇 종류 수(1·2·3종)로 나눔 | 중앙 배정자가 하위 작업을 배정하고 실행 결과를 받아 고치는 고리를 끝날 때까지 반복 |
| EMOS / Habitat-MAS (Chen 외, arXiv 2410.22662) [원문] | 여러 층 집에서 물건 옮기기 | 로봇 종류(드론, 바퀴, 다리)마다 갈 수 있는 곳과 할 수 있는 일이 다름. 로봇별 능력 설명서("robot resume")를 계획에 넣음 | 확인 안 함 |
| CoELA, TDW-MAT (Zhang 외, arXiv 2307.02485) [원문] | 여러 방에서 물건을 목표 지점으로 운반 | 용기를 도구로 써야 한 번에 여러 개를 나름. 각자 자기 시야만 봄. 3,000프레임 | 확인 안 함 |
| LLaMAR, MAP-THOR (Nayak 외, arXiv 2407.10031) [원문] | AI2-THOR 가정 과제 | 지시의 명시 정도를 4단계로(물건·개수·위치 명시 → 전부 암시). 탐색해야 함 | 확인 안 함 |

## 읽어 낸 것
1. 로봇마다 닿거나 들어갈 수 있는 곳을 다르게 해서 물건이 여러 로봇을 거치게 하는 것은 선행 연구가 가장 많이 쓴 방법이다(RoCoBench Sort Cubes, Collab-Overcooked, Forced Coordination, BoxNet). 사용자의 "방별로 접근 가능한 걸 다르게"와 같다.
2. 넘겨주는 자리는 "두 로봇이 모두 닿는 자리"로 만든다(겹치는 판, 가운데 조리대, 칸의 모서리). 한 로봇이 놓고 다른 로봇이 같은 자리에서 집는다.
3. 난이도는 "필요한 협력 동작의 최소 횟수"처럼 셀 수 있는 값으로 정한다(Collab-Overcooked 6단계). 우리 과제라면 "상자 하나가 거쳐야 하는 로봇 수".
4. 그 밖의 방법: 순서 제약(Make Sandwich, PARTNR), 능력 차이(PARTNR, COHERENT, EMOS), 함께 해야 하는 동작(BoxLift), 좁은 통로와 충돌(BoxNet2, Warehouse), 숨은 정보(BoxLift의 무게, LLaMAR의 암시 지시).
5. 계획하는 양: 원문을 확인한 것(Chen, RoCo, COHERENT)은 모두 "다음 행동 하나씩, 매번 다시 계획"이다. "한 번에 여러 단계를 쓰게 하고 그 길이를 조건으로 고정"한 연구는 이 10편 안에서는 못 찾음(범위가 좁으므로 없다고 단정하지 않음).

## 출처
- RoCo: https://arxiv.org/abs/2307.04738 , https://project-roco.github.io
- Chen 외: https://arxiv.org/abs/2309.15943
- Collab-Overcooked: https://arxiv.org/abs/2502.20073
- LLM-Coordination: https://arxiv.org/abs/2310.03903 , ProAgent: https://arxiv.org/abs/2308.11339
- PARTNR: https://arxiv.org/abs/2411.00081 , https://aihabitat.org/partnr/
- COHERENT: https://arxiv.org/abs/2409.15146
- EMOS: https://arxiv.org/abs/2410.22662
- CoELA: https://arxiv.org/abs/2307.02485
- LLaMAR: https://arxiv.org/abs/2407.10031
