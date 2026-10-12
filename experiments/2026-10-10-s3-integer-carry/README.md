# s3fix19 v167: A+정수 tick 운반 DEV 비교
[summary.json](summary.json)에 판정·20명령(10조건×on/off)·seed·원본/해시·다음3경로 사전 등록.
기준 A와 A+integer_ticks_v1; 기본 off, 크기/시간/계획12펄스·GO·보유 감시 유지.
원본 c0–c5 발행17/17/14/16/17/17: 초과2–5×12.94mm=26–65mm, 관측 끝점16–54mm와 크기 일치.
Oracle-x86 LP4·각60SIM·dev_light, load<51/메모리≥6GiB에서20개 동시; Mac 물리/재생 없음.
180wall초 안에 각 실행 프레임/SIM·실제 이동·단계·명령·예외 확인; 이상은 자기 실행만 STOP_REQUEST/EXIT.
판정: pair12펄스·끝점≤20mm·내려놓기 각n/6, cyan 기존 운반n/4; 낙하·기울기·HOST_ERROR 전부 기록.
전부 통과하면 사전 등록3경로 진행; 경로90° 방향 전환은 공동 crab, 실제 빔 yaw 회전 성공으로 주장하지 않음.
참고: [고정 시간 간격/정밀도](https://www.gafferongames.com/post/fix_your_timestep/), [ROS 시간 경로 샘플러](https://github.com/ros-controls/ros2_controllers/blob/master/joint_trajectory_controller/src/trajectory.cpp).
DEV 비교·확증 아님, PR416 초안; r1 디스크거부20·r2 tmpfs원본소실20(판정불가), SSH단절로 r3 미실행. 관련22시험 통과, 다음3경로는 사전 등록만.
