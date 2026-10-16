# 추가 정적 원인 검산 — 실행 전 기록

동일 qpos945조건은 위치2.4e-16m 수준으로 일치했다. 북/남 저장 camera+body로 역산한
평가용 joint는 command보다 어깨/팔꿈치/손목 합계 약−.932°이고 camera pose 재구성 잔차<3e-15이다.
실제 encoder qpos로 잘못 표기하지 않는다. 이를 runtime 입력으로 넘기지 않는다.

원인은 유한 kp의 position actuator와 중력 정적 편차인지 검산한다.
MuJoCo 공식 [position actuator](https://mujoco.readthedocs.io/en/stable/XMLreference.html#actuator-position)
의 `gainprm=kp`, `biasprm=[0,-kp,-kv]` 즉 `tau=kp*(qcommand-q)`와,
모델 질량/CoM 및 정기구학으로 구한 중력 모멘트 `axis·Σ((CoM-anchor)×m*g)`를 비교한다.
**mj_step/mj_forward/mj_inverse 없이** mj_kinematics 결과만 사용한다. parameter fit/변경0.
사전 고정 대상은 북/남 두 녹화의 frame35(4.7s, 횡이동 전)와 전181프레임이다.
모든 frame의 실제 qpos가 없으므로 역산값 기반 정적 일관성 검산이며 동적 토크의 실측으로 부르지 않는다.
영상 당시 joint 속도/가속/actuator force가 없어 움직임 구간 잔차를 특정 힘으로 단정하지 않는다.
보존된 실제 camera/body를 같은 역산 qpos로 MuJoCo에서도 재현해 비교한다.
새 FK/운동모델/중력 보상 제어 구현이나 관문 기준 변경은 하지 않는다.
