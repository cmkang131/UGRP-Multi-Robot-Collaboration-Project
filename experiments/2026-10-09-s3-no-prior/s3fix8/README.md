# s3fix8: 저장 장면의 짧은 정렬 probe와 입자 수 단독 비교

사전 기록: v152 결과를 이미 본 개발 진단이다. 새 확증/E2E가 아니다. 전체 900 SIM초 실행은 반복하지 않는다. speedctrl2의 현재 ABBA 잠금 반환 후 실행한다. CI를 기다리지 않으며 PR416은 병합하지 않는다.

## 범위와 판정 (새 비교 결과 열람 전)

- v152 원본: `/Users/changmin/projects/ugrp/outputs/s3-recovery-981baa95-s14201-v152`, source `981baa95e77aa78e5ffd6bc87c172cbb97aea7ed`. 원본을 덮어쓰지 않는다.
- 저장 파일에는 전체 qpos/qvel checkpoint가 없다. 기록된 차체/화물 자세와 발행 서보로 **재구성한 정지 장면**이며 정확한 물리 재시작이라고 부르지 않는다. 초기화 GT는 setup_only에만, 제어에는 자기 RGB·자기 발행 명령만 전달한다. 재구성 최초 영상과 원본 영상을 비교해 차이를 남긴다.
- r1/r2의 첫 공통 RGB 정렬 시점 532.1초를 pair probe 시작 장면으로 한다. 공동 집기는 실제 상대의 GO가 필요하므로 둘을 같은 장면에서 실행하되 로봇별 결과를 분리한다. 한 probe는 최대60 SIM초, 다른 두 로봇 프로세스와 동시에 돌리지 않는다.
- r3는 v152에서 정렬에 도달하지 않았다. 저장 장면의 cyan과 자기 검출을 이용한 별도 단계 초기화가 필요하며, 합성 접근 완료와 실제 v152 도달을 구분한다. 자기 RGB 정렬→hover→하강→닫기까지만 검증하고 도착/운반 성공으로 합산하지 않는다.
- 먼저 원래 선택기의 짧은 probe를 기록하고, 저장 프레임/명령에서 확인한 원인에 대한 수정만 적용하여 같은 초기화로 한 번 비교한다. 로봇별60초 제한, 원인 동일 실패2회면 추가 실행 중지.
- 통과: 기존 RGB 정렬 허용오차(3mm/축, 빔각도0.035rad)를 바꾸지 않고 hover·하강·닫기 상태에 순서대로 도달, 실행 오류/GO 실패/물리 실패0. 실제 파지의 접촉·상승은 eval_only로 별도 판정한다. probe 모두 통과해야 새 번들 전체 DEV 스모크1회를 허용한다.
- 매 프레임 검출/픽셀과 metric 오차/실제 발행 명령/평가 전용 이동을 남긴다. 실패를 검출, 방향·진동, 명령 해상도, 문턱 불일치, 단계 통합으로 분류한다. 명령은 단일 축·0.10초 이상, 옆걸음은 마지막0.10m/공동운반 예외 유지.

## 입자 수 단독 비교 사전 고정

S3는 전역 KLD와 추적2,000개를 쓰므로 'S3가100개라서 실패'라고 가정하지 않는다. 자기 지도55001 저장 입력1개를 동일 frozen adapter·명령·RGB·seed로 완전 재생한다. B=100개, N=500개만 바꾸고 관측 우도·모델·재표본 조건·문턱·지도 설정은 모두 동일하게 유지한다. 기존6개 후보는 off. 새 후보를 S3에 채택하지 않는다.

보고: 실제 XY RMSE/최종오차, 보고된 공분산에 대한 >3σ 비율과 이차형 오차, 최소 고유값·ESS·입자 수, wall/input-SIM·CPU·부하·피크메모리. 점추정과 혼합분포 공분산의 중심이 다르므로 이차형을 정합된 Gaussian NEES로 주장하지 않는다. 일관성 개선과 RMSE/최종오차 비악화가 모두 충족될 때만 '100개 부족과 양립'으로 판정한다. 한 입력만으로 보편 원인/해결이라고 하지 않는다. 속도비는 같은 잠금에서 새 B,N 직렬 재생으로 측정하며 ABBA 유의성 주장은 하지 않는다.

## 공개 구현 조사

조사 중. 아래 출처의 실제 코드와 설정을 확인한 후 입자 수·관측 상관·KLD를 구분해 기입한다.

| 공개 구현 | 실제 코드의 처리 | 이 작업에 적용 가능한 범위/한계 |
|---|---|---|
| [Loc-NeRF](https://github.com/MIT-SPARK/Loc-NeRF), [global 설정](https://github.com/MIT-SPARK/Loc-NeRF/blob/main/cfg/llff_global.yaml), [PF](https://github.com/MIT-SPARK/Loc-NeRF/blob/main/src/particle_filter.py) | RGB 광도 비교는 무작위32픽셀; 설정600→최소100입자, false convergence 보호용10개 위치 재분산. KLD 대신 분산 기반 annealing. PF 가중치를4제곱하는 코드도 있어 이 자체를 보수적 불확실성 추정이라 부를 수 없다. | RGB가 유일한 외부 감각이나 실시간 경로는 VIO를 사용. NeRF 지도/데이터 초기화에 GT 중심 설정도 존재하므로 그대로 가져오지 않는다. 픽셀 하위표본·복수 가설 보존을 참고하며 우리 과신 해결의 증거는 아니다. |
| [PF-net 공식 구현](https://github.com/AdaCompNUS/pfnet/blob/master/pfnet.py), [논문](https://proceedings.mlr.press/v87/karkus18a/karkus18a.pdf) | 이미지/지도 특징을 함께 CNN에 넣어 입자별 log likelihood 하나를 학습. 독립 픽셀 우도 연속곱과 다르다. soft resampling은 αw+(1−α)/N에서 뽑고 중요도 보정, 고정 N으로 KLD 없음. | 영상+odometry 입력·학습된 관측 모델이라 우리 수작업 wall likelihood와 다르다. α는 우도온도와 혼동하지 않는다. 코드가 통계적 calibration을 자동 보장한다는 주장은 하지 않는다. |
| [Nav2 AMCL](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [likelihood field](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp), [ROS1 설정](https://github.com/ros-planning/navigation/blob/noetic-devel/amcl/cfg/AMCL.cfg) | 현재Nav2 기본500–2000개/max_beams60, ROS1 Noetic 기본100–5000개/max_beams30. KLD가 occupied bins에 따라 min/max 안에서 N 조정. likelihood_field는 확률의 곱 대신1+Σp³, likelihood_field_prob의 beamskip은 별도 선택. | **레이저 구현이며 camera-only 사례가 아니다.** 일반 AMCL의 유일한 기본값이500–5000이라는 전제는 확인되지 않았다. 샘플 수·관측 상관·지도 오차는 별도 가설이며 N만 키워도 모델 편향은 남는다. |

출처는2026-10-10 공식 코드/설정에서 확인했다. 문헌에 나타난 기능과 우리에서 검증된 효과를 구분하며 이 조사로 PF 새 후보는 채택하지 않는다.

저장 기록 915/866 RGB 관측은 모두검출, 마지막10cm 회전 부호 반전은835/841회다. 마지막 residual x18.7/16.5mm, yaw19.98/18.68°로 실제 정렬 미완이다. 0.06초 fine lateral을 제거한 후 `position_heading`이 그립점 오차의 bearing을 계속 따라가는 구조가 확인됐다. 단일축 실제 회전은 마지막 틱에서5.96/6.06°였다. 허용오차를 넓히지 않는다.

수정 후보는 [visual servo PBVS](https://faculty.cc.gatech.edu/~seth/res.php?u=vs)의 물체 상대강체 변환과 [DWB의 이산 궤적 평가](https://github.com/ros-navigation/navigation2/blob/main/nav2_dwb_controller/dwb_core/src/dwb_local_planner.cpp)를 따른다. 근접한 관측 그립점 **전체 좌표**에 SE(2) 회전을 적용하고 합법적 기존 pulse의 유한 horizon을 평가한다. 기존 path bearing 선택기는 far approach에 유지하고, default-off 옵션으로만 비교한다. 새 물리 probe 전 선택기 범위·horizon과 성공 문턱을 코드/시험에 고정한다. 교사좌표·실시간 정답 보정은 사용하지 않는다.

구현 사전 고정: `visual_pose_mpc_v1`, near≤0.10m에서 기존 합법 전진±/회전±0.10초4개만 사용, horizon6개(각 후보 최장0.6초 명령+기존 settle), 허용오차 초과분의 정규화 제곱합을 먼저 최소화하고 동점에서 짧은 명령열을 고른다. 물리 전 kinematic 점검에서 additive 명령 패널티가3mm 바로 밖 정지를 만들 수 있어 lexicographic으로 고쳤다(성공 문턱 유지). 첫 명령만 발행한 뒤 새 RGB를 관측한다. 단독 cyan에는 기존에 없는 yaw 성공 조건을 추가하지 않는다. 이 방식의 실제 수렴은 아직 미검증이며 문턱/모터 최소길이를 바꾸지 않는다. 새 프레임의 검출·고정 카메라와 기존 파지 상태기계를 그대로 사용한다.

probe 제어기 전체 checkpoint도 원본에 없으므로 새 map-uniform PF를 해당 장면의 자기 RGB로 시작한다(저장 GT나 Gaussian pose prior 주입 없음). 미션 dispatcher/접근만 단계 초기화로 생략한다. 이것은 위치 찾기·접근의 재검증이 아니다. 동일 후보의 물리 실패를 먼저 모아 보고하고 통과 전 전체 스모크는 실행하지 않는다.

### 준비 probe 결과와 시작점 정정 (후속 비교 전)

2bb6148d의 첫 pair는60 SIM초/174.82 wall초, r1 검출140/140·hover0, r2는532.1초 장면에서 그립 거리0.784m라 reapproach에 머물렀다. cyan은0.5 SIM초/12.90 wall초에 초기 상자가 화면 아래로 잘려 준비 assert에서 HOST_ERROR였다. 둘 다 raw를 보존하며 통과/유효한 전후 비교에 합산하지 않는다.

근접 정렬을 분리하려고 **560.0초** 저장 장면으로 고정한다(r1/r2 저장 RGB 오차거리23.5/43.2mm). r3 합성 단계는 cyan 전방0.24m와 기존 inspect 자세로 시작한다. r3 양쪽 비교에 기존 `heading_visual_lock`을 명시적으로 켜, 생략한 전역 접근의 map-slot 판정을 새 PF로 대신하지 않고 자기 RGB의 유일 후보를 유지한다. 새 옵션/문턱/GT 제어를 추가하지 않는다. 실제 close 이후1초를 관측하고 더 이상의 lift 행동은 발행하지 않는다. 이 정정된 시작점에서 B/off와N/visual_pose_mpc_v1을 각각1회만 실행하며 같은 실패가 반복되면 중지한다.
