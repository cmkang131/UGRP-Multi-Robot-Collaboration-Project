# 참고 자료와 적용 범위

2026-10-14 열람. 다른 과제의 성공률을 봉 파지의 성능 근거로 쓰지 않는다.

| 자료 | 확인 범위와 재사용 | 우리 입력 경계 |
|---|---|---|
| Chen et al., [Learning by Cheating](https://arxiv.org/abs/1912.12294), 2019 preprint | 초록: privileged agent로 시각 학생을 학습하는 두 단계. [공개 코드](https://github.com/bradyz/learning-by-cheating)는 웹 도구 접근 실패, 코드 미확인 | 교사만 정답 사용 원칙 적용 가능. 자동차 정책 자체를 로봇 교사로 쓰지는 않음 |
| Lee et al., [Learning Quadrupedal Locomotion over Challenging Terrain](https://arxiv.org/abs/2010.11251), 2020 | 논문 정보/초록 확인. 교사–학생과 제한 관측 이력의 동기 참고; 상세 학습 구현 미확인 | 관절·접촉 센서를 쓰는 원 학생을 그대로 쓰지 않고 자기 RGB/명령에 제한 |
| Zhao et al., [ALOHA / ACT](https://arxiv.org/abs/2304.13705), 2023; [저자 코드](https://github.com/tonyzhaozh/act) | 논문 정보 및 저장소 README 열람. 행동 청크·CVAE를 쓰는 공개 구현 | 측정 관절 입력은 사용할 수 없음. 명령 이력으로 바꾼 차이를 명시 |
| [LeRobot ACT 공식 문서](https://huggingface.co/docs/lerobot/act), [고정 설정 코드](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/configuration_act.py) | 공식 문서와 저장소의 기존 adapter/CI를 확인. 네트워크를 새로 복제하지 않고 고정 ACTPolicy 재사용 | 현재/이전 자기 RGB와 자기 발행 명령만. 교사 좌표·접촉은 표적/평가로 분리 |
| Laskey et al., [DART](https://proceedings.mlr.press/v78/laskey17a.html), 2017; [저자 해설](https://bair.berkeley.edu/blog/2017/10/26/dart/) | 초록과 저자 설명: 감독자의 행동에 잡음을 넣어 학생의 상태 분포 차이를 줄임 | 시연 전용 잡음과 원래 교사 라벨을 분리. 잡음 규모를 임의로 정하면 원 DART 재현이라고 부르지 않음 |
| Ross et al., [DAgger](https://proceedings.mlr.press/v15/ross11a.html), 2011 | 초록: 자신의 행동이 만든 상태 분포에서 반복 학습하는 reduction | 학생 방문 상태에 교사가 라벨링. 교사 개입 평가와 독립 학생 평가를 분리 |
| [Chaumette & Hutchinson 연구 목록](https://faculty.cc.gatech.edu/~seth/res.php?u=vs), Visual Servo Control I/II | 저자 목록 확인. PBVS/IBVS의 지각→오차→제어 분해를 감사 틀로 사용; 전문 미확인 | 정답 교사와 영상 학생을 구분하는 데 사용, 기존 시각 가드 추가의 근거로 삼지 않음 |
| [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | 공개 API 실제 응답 보존: Korea Central Linux T4 NC4as $0.647/h, NC8as $0.925/h; NV6ads A10 $0.613/h | 일반 종량제 표시 가격이며 디스크/네트워크/세금·실제 청구는 별도. 할당량/공급 가능성을 뜻하지 않음 |

## 기존 저장소 근거

- `experiments/2026-09-24-action-act/README.md`, `refinement.md`, `reviewed-results-v1.md`: 0/2와 종료 누락·후속 조기 종료를 구분한다. 8,000 update 완료는 성공 증거가 아니다.
- `experiments/2026-09-16-reference-act/README.md`: 축소 ACT 물리 0/3, 종료 누락; 기존 커널 3/3. 이 결과를 현재 물리·봉 모델의 기준 성공률로 승계하지 않는다.
- `harness/reference_act.py`, `scripts/patch_reference_act.py`, CI `reference-act-smoke`: 고정 LeRobot SHA와 두 줄 device 호환 패치를 재사용할 기반.
- `scripts/cargo_formation_teacher.py`, `scripts/zone_teacher.py`, `harness/visual_arm_v3.py`: 정답 전용 교사·명령 IK. v2와 v3의 팔 장착 위치 및 손가락 중심 차이를 확인해야 한다.

## 2026-10-14 추가 결정의 근거

- Lin et al., [Data Scaling Laws in Imitation Learning for Robotic Manipulation](https://arxiv.org/abs/2410.18647), 2024 최초 공개/2026 v4; [공식 구현](https://github.com/Fanqi-Lin/Data-Scaling-Laws). 초록과 README를 확인했다. 환경·물체 다양성의 효과와 동일 설정 반복의 포화를 근거로 시작 상태를 층화한다. 공식 공개 모델은 32개 환경–물체 쌍 × 환경당 50회였다. **100/200/400은 우리 실험의 크기 곡선이며 논문이 보장하는 최소 수가 아니다.** 봉 하나·외관 고정인 우리 설정에서는 주로 배치·지도·가림 다양성만 늘리므로 물체 범주 일반화 주장과 구별한다.
- Codevilla et al., [End-to-end Driving via Conditional Imitation Learning](https://arxiv.org/abs/1710.02410), ICRA 2018; [저자 코드](https://github.com/carla-simulator/imitation-learning). 논문 정보·초록 및 저장소 설명 확인. 고수준 이산 명령으로 시각 행동을 조건화한다는 근거다. 그 논문의 분기망을 복제하는 대신 고정 ACT의 ENV 입력 투영에 스킬·끝 one-hot을 함께 넣는다. 이는 우리 adapter의 변경이며 원 ACT의 언어 추론 기능이 아니다.
- [Kaggle 실행 규칙](../../docs/kaggle_simulation.md): private Dataset 생성 후 서버 메타데이터로 확인하고, 인터넷 OFF GPU kernel에 필요한 고정 의존성·체크포인트를 미리 넣는다. 자격 증명은 Mac에만 둔다. 기존 인터넷 ON GPU 점검과 이번 학습 경로를 구분한다.

### 첫 교사 진단의 접근점/수집 비용 수정

- [MoveIt 공식 pick/place 예제](https://github.com/moveit/moveit_tutorials/blob/master/doc/pick_place/src/pick_place_tutorial.cpp): 접근 거리의 최소/희망 값을 구분한다. [MoveIt Grasps](https://moveit.picknik.ai/main/doc/examples/moveit_grasps/moveit_grasps_tutorial.html)는 도달 가능성 필터와 접근/들기/후퇴 경로를 설명한다. 우리 교사도 고정0.5m 점 하나 대신 지도 차체 여유를 만족하는 후보 접근점을 선택한다. MoveIt 전체를 도입한 것은 아니며 기존 A*와 v3 IK를 재사용한다.
- [MuJoCo 공식 렌더 샘플](https://mujoco.readthedocs.io/en/3.15.0/programming/samples.html): 물리 진행과 저장 영상의 fps를 따로 설정한다. 이를 따라 명령10Hz·영상5Hz로 수집하며 화각/배치/화면비는 고정한다. 640×480→320×240는 별도 관측 표본 조건이며 실제 개선은 16동시 게이트에서 측정한다.

- 교사 재사용: `scripts/zone_teacher.py:_drive_to/_grasp_targets`, `experiments/2026-09-25-zone-cargo-catalogue/README.md`. 옛 pair_beam 52.3 SIM초는 seed11 빈 바닥·구형 구동·local_contact_fine의 전체 이송 1/1이며 현재 무작위 v7 파지 성공으로 승계하지 않는다.
- [WPILib feedforward 공식 문서](https://docs.wpilib.org/en/stable/docs/software/advanced-controls/controllers/feedforward.html), 2026-10-14 열람: kS 마찰 보상과 단위 일치. 본 v7 relay 대응은 고정 시뮬레이터 명령 모델에서 도출한 포트 보상이며 WPILib를 그대로 설치한 것이나 실물 보정 완료가 아니다.

### 관문 접근 불가 분석

[MoveIt Grasps 공식 문서](https://moveit.picknik.ai/main/doc/examples/moveit_grasps/moveit_grasps_tutorial.html)와 [PDDLStream, ICAPS 2020](https://ojs.aaai.org/index.php/ICAPS/article/view/6739), [저자 공개 코드](https://github.com/caelan/pddlstream)를 확인했다. IK·충돌·접근 경로의 가능 조건과, 방해 물체를 치우는 작업 순서를 구분한다. 현재 교사는 기존 A*와 고정 끝 자세를 쓰며 PDDLStream을 설치하거나 작업 재배치를 구현하지 않았다. 이 자료는 원인 분류 근거이며 실패를 성공/제외로 바꾸는 근거가 아니다.

이전 320×240·5Hz 수집 제안은 철회됐다. 현재 성공 관문은 자기 RGB 0장, 검토용 네 정적 카메라 모음 1Hz다. 게이트 통과 뒤 학습 수집은 실제 학생 입력 640×480·10Hz로 별도 실행한다.

### 기본 off 교사 후보 pi_geometry_v1

[Nav2 footprint 설정](https://docs.nav2.org/rolling/configuration_and_development/first_time_robot_setup_guide/footprint/setup_footprint/)은 원/다각형 외곽과 상태별 외곽 변경을 설명한다. [Nav2 voxel layer](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/voxel/)는 3D 높이를 반영한 2D 계획 표현의 근거다. 우리 후보는 기존 A*를 유지하고, 접힌 팔보다 낮은 화물에 한해 모델에서 계산한 차체 반경을 쓴다. Nav2 전체를 도입한 것은 아니다. 벽·경계·다른 로봇·높이를 모르는 물체의 기존 총 여유는 유지한다. [수치 근거](teacher-v2-geometry-basis.json).

[WPILib PID 문서](https://docs.wpilib.org/en/stable/docs/software/advanced-controls/controllers/pidcontroller.html)의 적분 기여 상한/정지 시 초기화를 참고한다. 기존 P·마찰 포트에도 남은 71033의 잔여 오차에만 기본 off PI 후보를 평가한다. WPILib는 더 정확한 feedforward로 해결할 수 있으면 적분을 피하라고 권하므로, 불안정/과도 동작 여부를 새 물리 진단에서 확인한다.

### 정보 비대칭과 보고 가는 교사 (2026-10-14 추가)

- Chen et al., [Learning by Cheating, CoRL 2019](https://arxiv.org/pdf/1912.12294), 본문 1–2절 확인. 정답 교사를 학습한 뒤 영상 학생의 실제 방문 상태에서 교사 라벨을 받는 DAgger형 학습을 명시한다. 교사의 모든 동작이 제한된 영상으로 모방 가능함을 보장하는 논문은 아니다.
- Warrington et al., [Robust Asymmetric Learning in POMDPs, ICML 2021](https://proceedings.mlr.press/v139/warrington21a.html), 공식 초록 확인. Adaptive Asymmetric DAgger(A2D)는 학생의 제한된 관측에서 모방한 정책의 성과를 고려해 교사와 학생을 함께 갱신한다. 이번 팬/관찰 자세 제약은 그 문제의식을 따른 수동 제약이며 A2D 알고리즘을 구현한 것이 아니다.
- Walsman et al., [Impossibly Good Experts and How to Follow Them, ICLR 2023](https://openreview.net/forum?id=sciA_xgYofB), [저자 공개 코드](https://github.com/aaronwalsman/impossibly-good), [공저자 연구실 목록](https://portal.cs.cornell.edu/publications/)에서 제목·저자·학회·코드 존재 확인. 논문 본문은 웹 접근 확인 화면으로 열리지 않았다. 세부 정리와 ELF 알고리즘 주장은 **미확인**이며 구현 근거로 사용하지 않는다.
