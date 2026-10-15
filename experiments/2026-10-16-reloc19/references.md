# 조사와 상수 근거

2026-10-16 웹 원문을 먼저 확인했다. 아래 문헌은 방법 선택 근거이며 이 장면 성공 보장은 아니다.

- [Chaumette & Hutchinson 2006, Visual Servo Control I](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf): pp82–86, 시각 특징 오차·카메라 보정·IBVS/PBVS와 큰 초기 오차의 국소 수렴 한계 확인. 구현은 명목 바닥 역투영 패치 중심 오차를 사용하는2D 서보이며 논문의6DOF 제어 전체를 구현하지 않았다. 가려진 패치의 중앙을 구역 중심으로 부르지 않는다.
- [Burgard, Fox, Thrun 1997, Active Mobile Robot Localization](https://www.ijcai.org/Proceedings/97-2/Papers/080.pdf): 행동과 센서 방향을 선택하여 기대 불확실성을 줄이는 능동 위치 추정. PDF와 초록 확인. 현재 후보는 공분산-구역 폭 trigger와 유한 회전/타원 격자이며 전체 belief entropy 기대값 최적화는 **미구현**. 다음 라운드에서 관측 가능성과 실제 보정 감소를 본다.
- [Nav2 recovery BT 공식 문서](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/detailed_behavior_tree_walkthrough/detailed_behavior_tree_walkthrough/): RecoveryNode, RoundRobin spin/wait/backup, 유한 retry와 실패 전파 확인. ROS를 설치하거나 costmap을 지우지 않으며 기존 정적/RGB 충돌 거부를 유지한다.

상수: 색은 기존 CarryToZone.place_visible H±5/S,V≥30; 최소600픽셀은 기존 regions.qualified의 바닥 footprint 최소치, 바닥 fit1.2m는 zone_own_perception.SLOT_MAX_RANGE_M. 범위오차 .06+.08*range는 solo_carry_obstacles의 기존 원근 오차다. 이것은 물리 교정 확률이 아니다. 속도(.08/−.05m/s, 좌우.06m/s, 회전.1rad/s), 비례계수.9, 도착.025m는 기존 CarryToZone과 같다. 2π는 완전1회 둘러보기의 기하 정의, 타원5.991464547는2DOF χ²95%의 수학값이며 실제 coverage는 미확인이다. 격자 간격은 목적 구역의 작은 전체 폭, 재관측 재시도 간격도 그 폭이다. 재위치 trigger는95%타원 반경이 구역의 작은 반폭을 넘을 때다. 원본 carry 오차 p95 .85–2.38m가 반폭보다 큰 문제에 대응하는 공간적 설계이며 성공 판정 오차를 바꾸지 않는다. A의 SIM 예산180초는 기존 carry_to_zone 한도, 배치 cap300초는reloc18과 같다. 시간제한은 모두SIM 또는 명령 회전량이다.

B는 원본 위치추정기로 실제 RGB를 계속 처리한다. fix 수나 공분산을 임의 갱신하지 않는다. 반경이 줄지 않으면 실패/기존복구로 남긴다. 목적지B 바닥과 indigo벽 색의 혼동은 추가 원본검증 대상이며 단일 hue만으로 성공을 판정하지 않는다.

R2는기존 `sim.active_lookaround`의정보량(logdet),15도후보격자·최대3뷰·MIN_GAIN, `sim.lookaround_localization`의정적지형지물·12px영상여유·.03m벽끝절단·.8SIM초settle을재사용한다. 현재닫힌집게의발행PWM에서명목fisheye투영을계산한다. 유효시점이없으면기존내려놓기/둘러보기복구를요청한다. 현재경로위치에서의뷰선택이며미래경로전체에대한정보이득최적화는미구현이다.

R2벽제외는 `harness.reloc16_floor_mask.floor_clear`의기존고정v5 RGB분류를그대로재사용한다. H133벽이C의H143±(기존band5포함)와겹치는원본오검출이근거다. 새색상수/분할상수는없다. 모델정답segmentation이나실시간물체좌표를제어입력으로쓰지않는다.

R3 추가후보 `destination_camera_pan_v1`(기본off): 기존pan끝500/2500을발행서보로훑고원래pan으로복귀한다. 카메라배치·FOV·장면은바꾸지않는다. 2000pulse/s와.3SIM초settle은기존lookaround의서보이동계약이다. 차체2π회전대신관측자세를바꾸고,원래자세에서다시기존RGB가시성을확인한다. 팬중검출한바닥점의기억은기존SoloTeacher.MEMORY_S=5.2초까지만자기명령으로전파하며새RGB없이는나이를갱신하지않는다. 원래pan복귀전에는place수용하지않는다. R1에서차체회전중yaw p95가165–176도로커진것과반복한48.3SIM초sweep3회의new_fixes=0이근거다.

R3 B는기존 `CarryTracker`가 `loaded_or_unknown_prediction_only`로알리는경우XY metric fix가금지됨을그대로따른다. 정보량예측과관측수용은별개이므로이상태에서는기존내려놓기/둘러보기로즉시전환한다. 새로운측정상수나집게폐쇄관문완화는없다. 이기존카메라자격제약으로들고있는상태의XY재위치는여전히미지원이다.
