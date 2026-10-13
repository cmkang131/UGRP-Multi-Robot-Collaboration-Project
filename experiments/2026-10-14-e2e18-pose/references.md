# 위치 추정 방법 조사 — 2026-10-14

- [ROS 2 mecanum controller](https://control.ros.org/humble/doc/ros2_controllers/mecanum_drive_controller/doc/userdoc.html): 휠 속도 피드백과 기하로 odometry를 계산한다. 현재 입력은 **발행 명령**뿐이므로 encoder odometry와 같은 정확도를 가정할 수 없다. GT로 얻은 이번 gain 수치는 평가 전용이며 제어 보정계수로 사용하지 않는다.
- [robot_localization EKF 원문](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/rolling-devel/src/ekf.cpp): 각도 innovation wrap, Mahalanobis 거부, Joseph covariance update. 큰 innovation을 visual 신뢰의 근거로 바꾸는 현재 `e2e_rgb_vo.fuse` 분기를 별도 기본off 거부 후보 2개로 시험했다. 고정 증분 재생에서는 전체 오차가 악화되어 온라인 제출 대상에서 제외한다.
- [Nav2 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [omni motion 원문](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/motion_model/omni_motion_model.cpp), [likelihood field 원문](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp): 고정 지도에 대한 거리장 관측 likelihood와 확률 운동 모델. 초기 위치를 정답으로 넣지 않고 전역 가설을 유지해야 한다. 본 저장소의 pinned `own_map_amcl_vendor`와 `self_map_relocalize`를 먼저 재사용한다.
- [Seegmiller & Wettergreen, IROS 2011](https://publications.ri.cmu.edu/storage/publications/pub_files/2011/9/Seegmiller_IROS-2011_Optical_Flow_Odometry.pdf): 바닥 광류와 자기 그림자 대응. 현재 `e2e_rgb_vo`가 이 방법 계열이므로 전면 재구현 전에 측정 가능한 구간·고장 구간을 분리한다.
- [OpenCV homography 설명/코드](https://docs.opencv.org/4.5.5/d9/dab/tutorial_homography.html): 평면에서 카메라 변화를 추정하지만 평면 거리/법선과 보정이 필요하다. 바닥-벽 경계는 기존 `active_wall_vision`/`self_wall_segment_points`의 자기 RGB·발행 서보 FK로 가상 거리 끝점을 만든다. 벽 무늬가 바닥 접점이라는 가정은 허용하지 않는다.
- [ORB-SLAM3 논문](https://arxiv.org/abs/2007.11898), [공개 코드](https://github.com/UZ-SLAMLab/ORB_SLAM3): monocular/stereo/RGB-D 및 관성 구성을 제공한다. 자기 단안 RGB 경로는 가능하지만 scale·추적 손실·회전 카메라 외부보정의 통합 검증이 별도로 필요하다.
- [PL-VIWO2, 2025](https://arxiv.org/abs/2509.21563), [PL-VIWO 공개 코드](https://github.com/Happy-ZZX/PL-VIWO): 점·선 특징 및 운동 일관성 검사가 최신 비교 후보다. IMU·wheel encoder를 요구하므로 현재 제한된 입력으로 그대로 실행했다고 주장하지 않는다.

다음 후보는 고정 지도 AMCL + 자기 RGB 가상 거리/바닥 특징이다. 실패한 증분 게이트를 파지 행동 수정과 섞지 않는다. 평가용 위치는 파일 로더에서 분리하고 추정 결과를 만든 후에만 비교한다. 오프라인 성능은 고정 관측/고정 명령에 대한 결과이며 폐루프 파지 성공과 구분한다.
