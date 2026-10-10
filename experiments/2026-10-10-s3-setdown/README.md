# s3fix18 v166: 첫 공동 내려놓기 DEV 비교
사전 판정·후보·seed·명령 목록은 [summary.json](summary.json); oracle-x86/LP4, 10개 동시·각≤60SIM·dev_light.
기준과 A(하강 목표 계약), B(A+최종 하강2.4s), C(A+바닥 정착1.2s), 기본 off.
공통 c2/c5 8회와 C c0/c3 스트레스2회; 이전10조건 전체 확증으로 주장하지 않는다.
v165: 하강 높이 차이0.8–5.5mm, 최고 속도60–80mm/s, 조기 개방0; 낙하 가드4건 모두 집게 접촉 유지.
바닥 자세2건: 실제 하강 pan1500과 저장 집기 pan1540–1680 비교; 하강 경로의 실제 목표로 계약 수정.
지원된 하강의 평가 분류만 수정; GT·접촉은 제어 입력 아님, 무지지 낙하/기울기/GO/실행 오류 정지 유지.
[ROS 시간 지정 관절 경로](https://control.ros.org/jazzy/doc/ros2_controllers/joint_trajectory_controller/doc/userdoc.html), [MoveIt 하강→개방→후퇴](https://docs.picknik.ai/how_to/robotics_applications/pick_and_place_using_mtc/): 개방 전 경로 완료·정착; 실측 관절 제어로 주장하지 않음.
180wall초 초기 점검(프레임/SIM·실제 팔/차체 이동·단계·명령/예외), 이상은 해당 실행만 협력 중단·EXIT 보존.
DEV 후보 비교라 TensorBoard 변환 없음; 결과·원본 위치·해시는 summary.json, PR416 초안·병합 없음.
