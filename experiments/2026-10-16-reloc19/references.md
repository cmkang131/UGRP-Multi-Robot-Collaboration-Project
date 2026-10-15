# 조사와 상수 근거

2026-10-16 웹 원문을 먼저 확인했다. 아래 문헌은 방법 선택 근거이며 이 장면 성공 보장은 아니다.

- [Chaumette & Hutchinson 2006, Visual Servo Control I](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf): pp82–86, 시각 특징 오차·카메라 보정·IBVS/PBVS와 큰 초기 오차의 국소 수렴 한계 확인. 구현은 명목 바닥 역투영 패치 중심 오차를 사용하는2D 서보이며 논문의6DOF 제어 전체를 구현하지 않았다. 가려진 패치의 중앙을 구역 중심으로 부르지 않는다.
- [Burgard, Fox, Thrun 1997, Active Mobile Robot Localization](https://www.ijcai.org/Proceedings/97-2/Papers/080.pdf): 행동과 센서 방향을 선택하여 기대 불확실성을 줄이는 능동 위치 추정. PDF와 초록 확인. 현재 후보는 공분산-구역 폭 trigger와 유한 회전/타원 격자이며 전체 belief entropy 기대값 최적화는 **미구현**. 다음 라운드에서 관측 가능성과 실제 보정 감소를 본다.
- [Nav2 recovery BT 공식 문서](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/detailed_behavior_tree_walkthrough/detailed_behavior_tree_walkthrough/): RecoveryNode, RoundRobin spin/wait/backup, 유한 retry와 실패 전파 확인. ROS를 설치하거나 costmap을 지우지 않으며 기존 정적/RGB 충돌 거부를 유지한다.

상수: 색은 기존 CarryToZone.place_visible H±5/S,V≥30; 최소600픽셀은 기존 regions.qualified의 바닥 footprint 최소치, 바닥 fit1.2m는 zone_own_perception.SLOT_MAX_RANGE_M. 범위오차 .06+.08*range는 solo_carry_obstacles의 기존 원근 오차다. 이것은 물리 교정 확률이 아니다. 속도(.08/−.05m/s, 좌우.06m/s, 회전.1rad/s), 비례계수.9, 도착.025m는 기존 CarryToZone과 같다. 2π는 완전1회 둘러보기의 기하 정의, 타원5.991464547는2DOF χ²95%의 수학값이며 실제 coverage는 미확인이다. 격자 간격은 목적 구역의 작은 전체 폭, 재관측 재시도 간격도 그 폭이다. 재위치 trigger는95%타원 반경이 구역의 작은 반폭을 넘을 때다. 원본 carry 오차 p95 .85–2.38m가 반폭보다 큰 문제에 대응하는 공간적 설계이며 성공 판정 오차를 바꾸지 않는다. A의 SIM 예산180초는 기존 carry_to_zone 한도, 배치 cap300초는reloc18과 같다. 시간제한은 모두SIM 또는 명령 회전량이다.

B는 원본 위치추정기로 실제 RGB를 계속 처리한다. fix 수나 공분산을 임의 갱신하지 않는다. 반경이 줄지 않으면 실패/기존복구로 남긴다. 목적지B 바닥과 indigo벽 색의 혼동은 추가 원본검증 대상이며 단일 hue만으로 성공을 판정하지 않는다.
