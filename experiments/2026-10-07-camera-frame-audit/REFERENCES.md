# 표준 방법·읽기 전용 출처

- [MuJoCo mj_kinematics/mj_camlight](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-kinematics):
  qpos 정기구학 후 카메라 좌표를 갱신한다. mj_step이나 dynamics 계산과 구분한다.
- [MuJoCo camera frame](https://mujoco.readthedocs.io/en/stable/XMLreference.html#body-camera):
  고정 body camera의 local transform, optical 전방은−Z. OpenCV 변환은 오른쪽에 diag(1,−1,−1).
- [robot_state_publisher](https://github.com/ros/robot_state_publisher/blob/rolling/src/robot_state_publisher.cpp):
  joint position으로 segment.pose를 계산해 parent→child TF를 발행한다. 명령 목표가 실제 joint state와
  같음을 보장하지 않는다. ROS를 설치하거나 runtime에 측정 GT 관절을 연결하지 않는다.
- [OpenCV calibration/projection/triangulation](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html):
  world→camera extrinsic `[R|t]`, homogeneous projection/DLT. 이미 쓰는 API를 모델 자체 pose로 대조한다.
- [Hiwonder Glowing/Glowy Ultrasonic 공식 제품 사양](https://www.hiwonder.com/products/glowing-ultrasonic-sensor):
  2026-10-07 확인:2–400cm, measurement angle15°,40kHz,5V,I2C0x77.
  15°의 반각/전체각 구분은 해당 표에 없다. 빔 전체각을 확정한 실측으로 쓰지 않는다.

기존 구현은 `harness/servo_camera_fk.py`, `sim/masterpi_dynamics_v2.py`,
`sim/masterpi_camera_review_v3.py`, `harness/wall_parallax.py`, `harness/self_odom_grid.py`를 읽는다.
현재 camera v3의+10° tool pitch는 사용자의 가시성 목표 후보로 기록돼 있으며 표준 마운트 실측값이 아니다.
이번에는 모델/카메라/서보 계수를 바꾸지 않고 동일 모델의 FK 일치 여부부터 검사한다.
센서 모델/과거 사양의 출처 구분은 `docs/ultrasonic_range_sensor.md`를 재확인한다.
외부 코드 복사/새 패키지 설치 없이 기존 MuJoCo/OpenCV/NumPy/SciPy만 사용한다.
