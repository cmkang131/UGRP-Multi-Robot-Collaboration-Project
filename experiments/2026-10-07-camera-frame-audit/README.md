# egomap18 — 동일 qpos FK·카메라/차체 좌표계 감사 (PR #405)

## 계산·수정 전 사전 등록

시작 `77242f7f`, `claude/ego-wall-map`. 탐색 PR #409는4/5 실패로 종료했다.
사용자2026-10-07 결정: 실물 경기장 벽은 아직 없고, 표준 MasterPi 손목 카메라 마운트를 쓴다.
무늬는 인쇄 가능한 비반복·고대비로 선택할 수 있으나 이번에는 먼저 기구학/좌표계 원인을 분리한다.
기존 tape_v1·parallax_v1·floor_boundary_v1 실패·egomap17 결과는 보존하며 텍스처 재튜닝은 하지 않는다.
카메라가 그리퍼 위 손목에 붙어 앞을 본다는 사용자 사진 설명과 모델 parent chain을 대조한다.
현재 대화에 실제 사진 파일은 없어 치수/각도를 사진에서 새로 실측했다고 주장하지 않는다.

### 입력과 감사 순서

1. 녹화의 원 `scene.xml`을 MuJoCo로 읽고 **mj_kinematics + mj_camlight만** 호출한다.
   dynamics/settling/렌더/모델 호출은0. FK의 fixed transform, joint anchor/axis/ref, PWM→각도,
   robot→arm_base→shoulder→elbow→wrist→gripper→camera를 동일 qpos에서 링크별 대조한다.
   등록된21 PWM 자세 및 각 자세에서 각 arm joint ±0.05rad perturbation,
   base RPY `(0,0,0),(.1,0,0),(0,.1,0),(0,0,.2),(.1,-.1,.2)`를 사전 고정한다.
   joint range 밖 조합은 명시 제외, 동일 qpos 행렬/위치 최대오차1e-10을 정합 판정으로 쓴다.
2. 같은 고정점의 world/body/MuJoCo-camera/OpenCV 변환·픽셀 왕복·floor intersection·DLT를
   비교한다. +yaw는 위에서 반시계, body +x전방/+y좌측/+z위, OpenCV +x우/+y아래/+z앞,
   MuJoCo camera +x우/+y위/−z앞이다. 회전행렬은 local→parent/world, 합성은 parent @ child.
   synthetic exact ray/DLT 오차1e-8m/px 이내를 요구한다. 단순 yaw 부호 반전은 채택하지 않는다.
3. s1045–1047·s1050–1051의 저장 카메라/차체 평가 로그 및 egomap16 북/남 전프레임을 대조한다.
   실제 qpos가 없으면 그 사실을 NA로 기록한다. 명령 각도는 측정각이 아니다.
   body full rotation이 있는 북/남은 차체 기울기와 body-relative 팔/마운트 잔차를 분리한다.
   필요 시 camera pose로 역산한 관절은 **평가용 IK 추정**으로 따로 표기하고 기록된 qpos로 부르지 않는다.
   yaw 로그는 xmat의 atan2(R10,R00)와 대조하고, 발행 turn 및 M1 gain의 횡축→yaw 항을 확인한다.
4. 확인된 규약/FK 버그가 있으면 원인별 새 default-off 옵션을 만들고 단일 수정씩 비교한다.
   버그가 없으면 계수/카메라 각도 fit·GT pose 입력·임의 부호 반전·동일한 FK 옵션 증식은 하지 않는다.
   수정할 수 없는 명령/실제 상태 차이는 시뮬/보정 파이프라인 한계로 기록하며 실물 탓으로 돌리지 않는다.

### 재평가 및 다음 단계 관문

확인된 버그 수정 시만 기존 바닥 투영/시차를 둘 다 같은 봉인 RGB·주석으로 재평가한다.
바닥 투영은 egomap11 기준 그대로: 각 s1042–1047 고정분모≥50, 양의 깊이100%,4m 유효율≥95%,
중앙≤.10m·P90≤.25m·baseline 중앙 비악화. 개발2→동결→확인4, 이미 본 자료임을 명시한다.
시차는 egomap14/16 그대로: 북/남 각 전체 및 주석 P≥.90, 주석 R≥.70, TP≥30·양성≥50,
전체 중앙≤.10m·P90≤.25m·baseline P비악화. GT-only 진단은 관문 통과/채택이 아니다.
입력 경계/off bytes를 포함한 관문이 모두 통과한 경로만 후속 무늬 on 짧은 탐색 녹화에 사용할 수 있다.
후속 녹화는 별도 경로/시간/번들 사전 등록·시험·commit/push 후 agent_lock/ugrp_session으로 한 번,
freeze 없이 실행한다. 여기서 관문 미달이면 새 물리·RBPF100/pose_graph 지도·지도 그림은 실행하지 않는다.
같은 원인 두 번 막히면 중단하며 결과 후 문턱 변경은 하지 않는다.

### 센서·보존

초음파는 기존 모델/site/입력 어댑터를 확인만 한다. 공개 제조사 범위·빔각/불확실성을 기록하고
전방 보조 거리 관측 사용은 제안만 한다. 새 센서 구현/활성화0, #406 파일 및 다른 worktree 수정0.
원본/raw는 `/Users/changmin/projects/ugrp/outputs/camera-frame-audit-v1/`, ENOSPC=HOST_ERROR.
시험 통과 후 Codex trailer commit/push, PR #405 DRAFT·병합/force/reset0.
TensorBoard는 기존 사용자 생략 결정을 유지, Drive는 프로젝트 규칙상 사용하지 않는다.
결과는 [RESULTS.md](RESULTS.md), 표준 근거는 [REFERENCES.md](REFERENCES.md)에 남긴다.
