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

아래는 실제 공식 코드/설정 확인 결과다. 영상 기반2개와 레이저 기준1개를 구분했다.

| 공개 구현 | 실제 코드의 처리 | 이 작업에 적용 가능한 범위/한계 |
|---|---|---|
| [Loc-NeRF](https://github.com/MIT-SPARK/Loc-NeRF), [global 설정](https://github.com/MIT-SPARK/Loc-NeRF/blob/main/cfg/llff_global.yaml), [PF](https://github.com/MIT-SPARK/Loc-NeRF/blob/main/src/particle_filter.py) | RGB 광도 비교는 무작위32픽셀; 설정600→최소100입자, false convergence 보호용10개 위치 재분산. KLD 대신 분산 기반 annealing. PF 가중치를4제곱하는 코드도 있어 이 자체를 보수적 불확실성 추정이라 부를 수 없다. | RGB가 유일한 외부 감각이나 실시간 경로는 VIO를 사용. NeRF 지도/데이터 초기화에 GT 중심 설정도 존재하므로 그대로 가져오지 않는다. 픽셀 하위표본·복수 가설 보존을 참고하며 우리 과신 해결의 증거는 아니다. |
| [PF-net 공식 구현](https://github.com/AdaCompNUS/pfnet/blob/master/pfnet.py), [논문](https://proceedings.mlr.press/v87/karkus18a/karkus18a.pdf) | 이미지/지도 특징을 함께 CNN에 넣어 입자별 log likelihood 하나를 학습. 독립 픽셀 우도 연속곱과 다르다. soft resampling은 αw+(1−α)/N에서 뽑고 중요도 보정, 고정 N으로 KLD 없음. | 영상+odometry 입력·학습된 관측 모델이라 우리 수작업 wall likelihood와 다르다. α는 우도온도와 혼동하지 않는다. 코드가 통계적 calibration을 자동 보장한다는 주장은 하지 않는다. |
| [Nav2 AMCL](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [likelihood field](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp), [ROS1 설정](https://github.com/ros-planning/navigation/blob/noetic-devel/amcl/cfg/AMCL.cfg) | 현재Nav2 기본500–2000개/max_beams60, ROS1 Noetic 기본100–5000개/max_beams30. KLD가 occupied bins에 따라 min/max 안에서 N 조정. likelihood_field는 확률의 곱 대신1+Σp³, likelihood_field_prob의 beamskip은 별도 선택. | **레이저 구현이며 camera-only 사례가 아니다.** 일반 AMCL의 유일한 기본값이500–5000이라는 전제는 확인되지 않았다. 샘플 수·관측 상관·지도 오차는 별도 가설이며 N만 키워도 모델 편향은 남는다. |

출처는2026-10-10 공식 코드/설정에서 확인했다. 문헌에 나타난 기능과 우리에서 검증된 효과를 구분하며 이 조사로 PF 새 후보는 채택하지 않는다.

저장 기록 915/866 RGB 관측은 모두검출, 마지막10cm 회전 부호 반전은835/841회다. 마지막 residual x18.7/16.5mm, yaw19.98/18.68°로 실제 정렬 미완이다. 0.06초 fine lateral을 제거한 후 `position_heading`이 그립점 오차의 bearing을 계속 따라가는 구조가 확인됐다. 단일축 실제 회전은 마지막 틱에서5.96/6.06°였다. 허용오차를 넓히지 않는다.

수정 후보는 [visual servo PBVS](https://faculty.cc.gatech.edu/~seth/res.php?u=vs)의 물체 상대강체 변환과 [DWB의 이산 궤적 평가](https://github.com/ros-navigation/navigation2/blob/main/nav2_dwb_controller/dwb_core/src/dwb_local_planner.cpp)를 따른다. 근접한 관측 그립점 **전체 좌표**에 SE(2) 회전을 적용하고 합법적 기존 pulse의 유한 horizon을 평가한다. 기존 path bearing 선택기는 far approach에 유지하고, default-off 옵션으로만 비교한다. 새 물리 probe 전 선택기 범위·horizon과 성공 문턱을 코드/시험에 고정한다. 교사좌표·실시간 정답 보정은 사용하지 않는다.

구현 사전 고정: `visual_pose_mpc_v1`, near≤0.10m에서 기존 합법 전진±/회전±0.10초4개만 사용, horizon6개(각 후보 최장0.6초 명령+기존 settle), 허용오차 초과분의 정규화 제곱합을 먼저 최소화하고 동점에서 짧은 명령열을 고른다. 물리 전 kinematic 점검에서 additive 명령 패널티가3mm 바로 밖 정지를 만들 수 있어 lexicographic으로 고쳤다(성공 문턱 유지). 첫 명령만 발행한 뒤 새 RGB를 관측한다. 단독 cyan에는 기존에 없는 yaw 성공 조건을 추가하지 않는다. 사전 기록 시점에는 이 방식의 실제 수렴이 미검증이며 문턱/모터 최소길이를 바꾸지 않는다. 새 프레임의 검출·고정 카메라와 기존 파지 상태기계를 그대로 사용한다.

probe 제어기 전체 checkpoint도 원본에 없으므로 새 map-uniform PF를 해당 장면의 자기 RGB로 시작한다(저장 GT나 Gaussian pose prior 주입 없음). 미션 dispatcher/접근만 단계 초기화로 생략한다. 이것은 위치 찾기·접근의 재검증이 아니다. 동일 후보의 물리 실패를 먼저 모아 보고하고 통과 전 전체 스모크는 실행하지 않는다.

### 준비 probe 결과와 시작점 정정 (후속 비교 전)

2bb6148d의 첫 pair는60 SIM초/174.82 wall초, r1 검출140/140·hover0, r2는532.1초 장면에서 그립 거리0.784m라 reapproach에 머물렀다. cyan은0.5 SIM초/12.90 wall초에 초기 상자가 화면 아래로 잘려 준비 assert에서 HOST_ERROR였다. 둘 다 raw를 보존하며 통과/유효한 전후 비교에 합산하지 않는다.

근접 정렬을 분리하려고 **560.0초** 저장 장면으로 고정한다(r1/r2 저장 RGB 오차거리23.5/43.2mm). r3 합성 단계는 cyan 전방0.24m와 기존 inspect 자세로 시작한다. r3 양쪽 비교에 기존 `heading_visual_lock`을 명시적으로 켜, 생략한 전역 접근의 map-slot 판정을 새 PF로 대신하지 않고 자기 RGB의 유일 후보를 유지한다. 새 옵션/문턱/GT 제어를 추가하지 않는다. 실제 close 이후1초를 관측하고 더 이상의 lift 행동은 발행하지 않는다. 이 정정된 시작점에서 B/off와N/visual_pose_mpc_v1을 각각1회만 실행하며 같은 실패가 반복되면 중지한다.

### 단계 재개 상태의 누락: 물리 비교 전에 추가 오프라인 수정

560초 재구성 B/N에서도 pair가 각60초 뒤 reapproach에 머물렀다(152.96/152.75 wall초). 이때 `align_start`가 저장 inspect를 search로 다시 바꿔, 자기쪽 띠가 아니라 먼 띠를0.761/0.783m로 읽었다. 새 제어기의 빈 `vo_obs`는 이를 최초 접근 검증으로 간주해 reapproach했다. **수정 선택기가 근접 구간에 한 번도 도달하지 않은 준비 실패**이며 알고리즘 전후 결과로 쓰지 않는다. 같은 준비 문제의 물리 반복은 중지했다.

[MuJoCo state/reproducibility](https://mujoco.readthedocs.io/en/stable/programming/simulation.html#state-and-control)의 전체 상태 보존 원칙과 기존 단계 probe의 상태 주입 경로를 확인했다. physics 적분 상태만으로 외부 제어기의 phase/history가 복원되지 않는 것이 이 경로의 원인이다. 새 단계 재개는 저장된 **자기 RGB69/19행·발행 이동66/17회·inspect 자세**를 `alignment-phase.json`으로 보존하고, 원래 align 상태에서 시작한다. 새 aligned receipt는 만들지 않으며 이전 관측의 시간을 새 단계 시계로 평행 이동한다. 현재 global PF에는 과거 GT/pose prior를 넣지 않는다. 최초 새 영상·기존 문턱·실제 GO·실제 port.apply를 유지한다.

이 수정은 결과 문턱 조정이 아니다. 오프라인 회귀에서 재진입 자세·최초 관측의 재접근 오판·실제 모터 계약을 먼저 고정한 뒤, 수정된 pair 시작점으로 B/N 각각1회만 확인한다. 이 시점에는 cyan 결과 재사용을 계획했으나, 아래 포트 기록 감사에서 이 계획을 철회했다. 번들 내부에 부모의7.45.0이 남은 메타데이터도 카탈로그와 같은7.46.0으로 정정한다; 이전 raw는 바꾸지 않는다.

### 준비 포트 기록 검증 (추가 물리 전)

601cc014의 pair B/N은 align 상태에 머물렀지만 첫 RGB 해석부터 틀렸다. 동일 프레임의 host 발행 자세는 inspect(508/2432)인데 `actuator_state.servo_pulses`는 search(740/2320)였다. 준비 코드가 모터에 직접 서보를 쓰고 카메라 포트의 명령 이력을 갱신하지 않은 결함이다. 그 결과 첫 그립 x를 r1 .226→.409m, r2 .243→.451m로 오독했다. controller extrinsic을 영상에 맞춰 바꾸지 않는다.

초기화 서보를 **host.issue→실제 port.apply**로만 발행하도록 고쳤다. 첫 프레임부터 매 프레임 host 발행 명령과 actuator_state 명령 이력을 대조해 불일치하면 정렬을 시작하지 않는다. 회귀는 기존 결함(모터만 직접 변경)을 실제 포트에서 재현해 거부하고, 동일 포트로 정상 발행한 뒤 기록·적용값 일치를 확인한다. 물리 재시도 전에 이 계약과 phase 재개의 검사부터 통과시킨다. 앞선 준비 실행들은 전부 보존하되 PBVS 효과의 전후 증거에서 제외한다.

## 최종 결과 (소스 9a57581f, 2026-10-10)

**r3 단계 통과, r1/r2 미통과. 후보 `visual_pose_mpc_v1`은 미채택하며 기본off 유지. 전체 스모크0회.** 아래는 개발 단계 probe이며 실제 배송 성공이나 정확한 v152 checkpoint 재시작이 아니다. B=기존 선택기, N=같은 장면/문턱에서 새 선택기만 on이다. B/N 적분 초기 상태와 최초 자기 RGB SHA가 각각 일치한다([입력 대조](probe-initial-inputs.json)). 최종4회는 매 프레임 서보 발행 이력 불일치0, HOST_ERROR0, 혼합축/0.10초 미만 이동0이다.

### 프레임별 근거와 원인 분리

[644행 원본 연결 표](probe-frames.csv)는 검출·픽셀 오차·metric 잔차·명령·평가 전용 실제 이동과 관측 간격을 포함한다. 픽셀 오차는 자기 RGB로 추정한 그립점과 고정 목표의 재투영 차이이며 mask 중심 차이가 아니다. pair는 실제 관측 결정288행/조건, cyan은 정렬 중 모든 프레임26/42행이다. 프레임 간 이동은 사후 GT 계산이고 제어 입력이 아니다. r3 0.05초 행의 이동을 완성된0.10초 pulse 이동으로 해석하지 않는다.

| 조건·로봇 | 검출/관측 (띠 완전 가시) | 마지막 픽셀 dx,dy | 마지막 x,y mm / yaw ° | 반복 명령·실제 이동 | hover/하강/닫기 |
|---|---:|---:|---:|---|---|
| v152 r1 | 915/915 | −7.13,−55.60 | 18.72,2.10 /19.98 | 근접 회전 반전835; 마지막5.96° | 0/0/0 |
| v152 r2 | 866/866 | −18.30,−49.39 | 16.53,5.42 /18.68 | 근접 회전 반전841; 마지막6.06° | 0/0/0 |
| B r1 | 144/144 (144) | −0.79,−15.70 | 5.11,0.22 /6.27 | 회전 반전52; pulse 회전 중앙5.67° | 0/0/0 |
| B r2 | 144/144 (144) | −20.90,−67.81 | 23.09,6.31 /15.40 | 회전 반전138; pulse 회전 중앙5.77° | 0/0/0 |
| N r1 | 144/144 (74) | −148.58,−13.12 | 3.35,43.57 /20.77 | 전후 반전139; pulse 전후 중앙12.04mm | 0/0/0 |
| N r2 | 144/144 (88) | −80.70,−10.82 | 3.28,23.28 /20.21 | 전후 반전98; pulse 전후 중앙12.00mm | 0/0/0 |
| B r3 | 26/26 | −0.66,7.11 | −2.27,0.19 /해당없음 | 전진3회; 정렬 문턱 만족4프레임 | 1/1/1 |
| N r3 | 42/42 | −0.44,7.81 | −2.50,0.13 /해당없음 | 이동5회; 회전 반전1; 문턱 만족7프레임 | 1/1/1 |

원래 pair는 **검출 실패가 아니라 그립점 bearing을 따라 도는 선택기의 진동**이다. 0.10초±0.35 회전은 약5.7°로 허용 yaw2.005°보다 크고, 전진 약11.7mm도 축별3mm보다 크다. r1 B는5.11mm 밖에서 개선 가능한 기존 pulse를 못 골라 hold했고 r2는계속 회전했다. 이는 현재 고정 진폭의 해상도 문제이며 **0.10초 계약 자체가 불가능하다는 증거는 아니다**(진폭별 보정은 미실행). yaw 목표와 그립점 위치를 함께 고려하지 않는 기존 선택기 문제도 존재한다. 기존3mm/축·0.035rad 문턱은 바꾸지 않았다.

후보 N은 전체 SE(2) 그립점 변환으로 회전 진동을 줄였으나 중간 시야 제약을 빠뜨렸다. r1/r2에서 `BAND_CLIPPED` **70/56회**, MPC 관측74/88회와 기존 검색/후퇴70/56회가 번갈아 나타나 전후 진동이 됐다. 모든 프레임에서 빔 일부는 보이므로 단순 `visible=true`를 성공으로 세면 이 실패를 놓친다. **후보의 pair 수렴0/2로 기각**, 재튜닝/추가 동일 원인 물리는 하지 않는다. [동작별 이동 통계](probe-motion-summary.json), [전체 판정](probe-results.json).

[Chaumette/Hutchinson 2006, Part I, p87–89](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf)는 PBVS에서 3D 오차가 줄어도 영상 특징이 시야 밖으로 나갈 수 있음을 보여준다. 이 표의 clipping/후퇴 진동은 그 한계와 양립한다는 해석이며 해당 논문이 우리 비홀로노믹·pulse 제어의 수렴을 보장하지 않는다. 다음 설계에는 특징 가시 영역을 경로 제약으로 넣고, 합법0.10초 명령의 진폭별 응답을 먼저 오프라인/짧은 단계에서 확인해야 한다. 추가 후보는 이번 결과를 보고 사후 채택하지 않았다.

### 단계·정지·시간

| 실행 | hover→하강→닫기 (probe 진입 t=2.85 기준 경과 SIM초) | 평가 전용 양쪽 finger 접촉 | 실제 종료 | wall / SIM초 (비율) |
|---|---|---|---|---|
| pair B | r1/r2 없음 | 각0 | 60초 probe 상한 | 180.583 /60 (3.010) |
| pair N | r1/r2 없음 | 각0 | 60초 probe 상한 | 180.978 /60 (3.016) |
| cyan B | 2.30→3.60→5.25 | 22표본, 닫기 이후21 | 닫기 뒤1초 관측 완료 | 30.406 /6.75 (4.505) |
| cyan N | 3.10→4.40→6.05 | 22표본, 닫기 이후21 | 닫기 뒤1초 관측 완료 | 33.238 /7.55 (4.402) |

r3는 B/N 모두 자기 RGB로 일찍 보고 hover→가려진 하강→닫기까지 실제 port.apply를 통과했다. **물체 상승·운반은 실행하지 않았으며 secure grasp/배송 성공은 미검증**이다. 최대 COM높이는 약0.015894m로 바닥 높이다. 기존 심판 `held`는 손가락 중 하나 접촉도 포함하므로 이를 안전한 파지로 쓰지 않았다. r3의 would_stop은 B/N 각각 `REAL_PREGRASP_UNCONFIRMED`1·`ARM_COLLISION_GUARD`9다. pair B/N은 `SELF_UNCERTAIN`각4, `POSE_UNCERTAIN`2968/2712 hook발생이며 반복 hook를 독립 실패나 I/O횟수로 세지 않는다. GO실패·실제 물리 실패 정지0, 최종4회 HOST_ERROR0이다. 표의 비율은 짧은 준비/종료 비용 포함으로 whole-S3≤3 목표 달성 판정이 아니다.

준비 실행도 숨기지 않는다: **준비8+유효 비교4=총12회**, 개별≤60 SIM초, 합계448.30 SIM초/1354.969 wall초. 준비 HOST_ERROR1(초기 cyan 잘림), 532.1초 먼 시작점·phase/history 누락·모터 직접 쓰기의 포트 기록 불일치를 별도 분류했다. 준비6회에서 발견된 발행 자세 불일치 때문에 6ab2118c의 cyan 단계 통과도 최종 유효 비교에서 제외하고 같은 실제 port 경로로 다시 확인했다. [12회 인덱스](probe-run-index.json). 준비 결함을 물리 전에 모두 잡지 못해 당초 최소 횟수 계획을 넘긴 점을 남긴다. 반복900초 스모크는0이다.

### 입자 수 단독 재생: 자기 지도55001 한 입력

같은1341/1341프레임,270.0 입력SIM초, 고정 adapter에서 **N만100→500**으로 바꿨다. B는 원본 추정/공분산/관측/제안명령과 모두 일치했다. 실행 전후 adapter 전체 Python 해시 `9b83956c3c2df742f99af074e164a46e8028e9f87f2d3f128711a6afd5b49b88`도 같고 예외0이다. N의 제안명령은 달라질 수 있으나 재생에 적용된 발행명령/RGB는 원본으로 고정한다. 실제 실행이 아니다.

| 지표 | N100 | N500 |
|---|---:|---:|
| XY RMSE / 최종오차 m | .30776 / .70789 | .27720 / .39169 |
| 최종σ / RMSσ m | .17560 / .09831 | .26314 / .12931 |
| >3σ 표본 | 651/1341 (48.546%) | 219/1341 (16.331%) |
| 보고 eᵀP⁻¹e 평균 | 2463.28 | 6.596 |
| 최소 XY공분산 고유값 m² | 약1e−10 | .00022513 |
| 재표본 후 최소 고유 입자 / ESS 중앙 | 2 /66.34 | 13 /343.04 |
| wall / CPU초 | 378.483 /389.893 | 730.960 /741.987 |
| wall / 입력SIM | 1.402 | 2.707 |
| peak RSS byte | 1,374,289,920 | 1,689,124,864 |

사전 선택 규칙인 일관성 개선+RMSE/최종오차 비악화를 충족한다. **이 한 입력에서100입자 부족 가설을 지지하되, 잔여16.3% >3σ는 미해결**이다. 최고 가중치 입자와 mixture covariance의 중심이 달라 Gaussian NEES 인증이 아니다. CPU비1.903·wall비1.931이며 B 중 관련 시험17.73초 중첩을 공개한다; clean ABBA 속도 효과로 주장하지 않는다. S3는별도2000입자 handoff이므로 이 결과로 S3 입자를 자동 증가시키지 않았다. [수치·해시·부하·선택](population-comparison.json), [속도 범위](timing-scope.json).

### 보존·검증·재현

- 최종 실행 소스 `9a57581fead861fb27c1b7fe7260eb6d6c0f7337`, 변경 시험 `tests/test_s3_alignment_probe.py` **9PASS/32.10초** 후 커밋·push했다. 실제 모터/카메라 포트의 발행 자세 일치와 기존 결함 거부·phase 재개·기본off 항등·합법 pulse를 포함한다. 앞선 카탈로그 포함26PASS는 이전 소스의 별도 범위다. CI는 기다리지 않고 PR416은 병합하지 않는다.
- 번들 **zone-s3-alignment-probe-v153 / workflow7.46.0**. main+열린PR11개 최댓값 조사/예약은 [기록](bundle-reservation.json)에 있다. 카탈로그는 조각 파일이고 원래 JSON은 변경하지 않았다. 옛 준비 실행의7.45.0 메타데이터는 원본 그대로 보존하며 새 유효 비교는7.46.0이다.
- 원본 루트 `/Users/changmin/projects/ugrp/outputs/s3fix8-20261010`; 최종4회 파일8204개 SHA 모두 일치. 각 `delivery/<run>/report.json`과 `frames/`에 전체 판정·표, `delivery/views/<run>/execution.mp4`에 자기RGB3개4배속 영상이 있다. [대표 pair N](http://127.0.0.1:6007/video/e651192d4a5db9718601)은15.0초/300프레임/20fps, SHA `6284ec734a5792b855d7c83073c0e160cf8e09880f7c0d54333c9aa81ef7e43b`; [cyan N](http://127.0.0.1:6007/video/2fb124db811c57050f89)도 별도 보존한다. raw 로컬 보관을 원격 백업이라 부르지 않는다.
- TensorBoard는 기본 checkout의 새 `1010-s3fix8-probes`(4), `1010-s3fix8-preparation`(8), `1010-s3fix8-population`(2)로 분리했다. 기존 snapshot 불변, 실제 이벤트194개 수치 대조 일치,4영상 manifest/HTTP 등록 확인. Chrome 강에서 probe4개/재생2개·핀8/5·HParams case/policy/seed/source_sha4열을 확인했고 대표15초 영상을 실제 재생했다. HParams는 전역4439그룹이며 condition열이 없어 B/N은 run 이름으로 구분하는 표시 한계가 있다. [필터·핀·서버·UI 검증](tensorboard-verification.json). 모델 호출0, 응답시간은 해당없음이며 없는 태그를 만들지 않았다. `result/commands`는 이 단계 뷰에서 활성 이동 명령 수다.
- speedctrl2 순서 뒤 연구 잠금을 잡아 직렬 실행했고 자기 실행·후처리 종료 후 반환했다. 공통 speedctrl2 소스는 수정하지 않았다. [순서 반환](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/424#issuecomment-6094372137).

**다음 물리 제안:** 시야를 유지하는 상대 영상 정렬과 보정된0.10초 미세 진폭을 먼저 저장 프레임·포트 회귀에 고정한 뒤, 같은560초 장면의 pair 정렬→닫기 ≤60 SIM초 probe만1회 수행한다.
