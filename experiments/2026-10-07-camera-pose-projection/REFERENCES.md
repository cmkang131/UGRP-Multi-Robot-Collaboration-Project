# 방법·출처·입력 경계

## 표준 정기구학

[ROS robot_state_publisher](https://github.com/ros/robot_state_publisher/blob/9bcf8fcf38c7096612f7ecbc2c195bd9318171a5/src/robot_state_publisher.cpp)
원본을 직접 확인했다. `publishTransforms` L268–291은 joint position별 KDL `segment.pose(position)`을,
`publishFixedTransforms` L296–317은 고정 segment의 `pose(0)`을 전달한다. callback L362–374는
JointState의 이름·position을 모아 갱신한다. [공식 개요](https://index.ros.org/p/robot_state_publisher/).
revision·원문·LICENSE(BSD-3-Clause) SHA256은 [references.json](references.json)에 있다.

여기서는 ROS/KDL 라이브러리를 새로 설치하지 않고 같은 homogeneous transform 곱을 NumPy로 구현한다.
각 관측의 자기 PWM → 기존 구동기의 joint target 각 → fixed parent translation/rotation × joint axis rotation
→ 다음 link → 카메라 고정 mount 순서다. `sim/masterpi_dynamics_v2.py:1134`의 PWM 각 변환을 그대로 따르며
servo6은 raw centre1500, servo3/4/5 deviation54/53/89, 2000/180 PWM/deg다.

고정 chain은 `sim/masterpi_model_v3.py:590` 부근의 v3 기구 정의와 실제 녹화6건 scene.xml의 공통 몸체 계층이다.
arm base x=.0482m, base→yaw z=.0605m, yaw→shoulder z=.0347m, 링크 .065/.062m,
v3 camera mount=(.0529820,0,.0281522)m, tool 대비 optical pitch+10°.
6개 scene에서 chain이 byte-equivalent한 JSON으로 같음을 확인했다([geometry-source.json](geometry-source.json)).
scene의 world xy/yaw, 물체, 실제 joint, 카메라 world pose는 **runtime 기하 파일에 없다**.
바닥→차체는 기존 nominal level z=.0325m이며 실제 roll/pitch/height를 알 수 있다는 뜻이 아니다.

`harness/visual_arm.py`의 기존 명령 FK는 옛 mount(67mm/13.6mm/+7.46°)와 이전 shoulder 높이를 사용한다.
이번 옵션은 명시한 v3 chain에만 적용하며 그 공유 함수를 바꾸지 않는다. 원21자세 PnP 표도 보존한다.
고정 TF 갱신 자체로 명령과 실제 관절 사이 처짐/지연이 사라지지 않는다. 현재 로그는 encoder를 제공하지 않아
ROS JointState measured input 대신 **명령 target만** 쓴 차이를 명시한다. GT로 bias를 fit하지 않는다.

## 투영·오차 분해

[OpenCV PnP 문서](https://docs.opencv.org/4.12.0/d5/d1f/calib3d_solvePnP.html)의
optical x-right/y-down/z-forward 관례를 따른다. 기존 undistort K를 유지하고 평면 교점은
`ray=R K^-1 [u,v,1]`, `t=-origin_z/ray_z`, `point=origin+t ray`로 구한다. t>0·optical z>0 조건 불변.
Euler 비교는 `R=Rz(yaw) Ry(-pitch) Rx(roll) R_optical_to_forward_left_up`로 명시한다.
단일항 치환은 평가용 민감도이며 독립적인 인과 기여율이나 합산 가능한 오차 예산이 아니다.

PR #406 S2 기록은 읽기 전용으로 확인했다. 인용 수치는 drive-friction README가 아니라
[2026-10-06-s2-realism README의 HIGH 진단](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/codex/s2-realism/experiments/2026-10-06-s2-realism/README.md)
현재 L1032–1040에 있다. 예전 rigid-composition HIGH 예상−36.59168° vs 실제약−32.7°,
160s 예상높이.179896m vs 실제.187288m, 픽셀잔차52.315→.550px는 별도 **loaded HIGH** 비교다.
egomap의 무하중 PnP table/SEARCH 비교와 같은 숫자로 섞지 않는다.

실제 camera-pose의 cached/from-body 둘 다 비교하며, body라는 필드명에도 이 기록의 값은 **world 좌표**다.
저장 robot xyz/yaw를 이용해 floor-heading frame으로 옮긴다. 실제 카메라 로그에 관절·차체 roll/pitch가
없어서 pitch 잔차를 팔 처짐과 차체 기울기로 나누는 것은 식별 불가다. 새 물리나 실물 성능으로 승계하지 않는다.
