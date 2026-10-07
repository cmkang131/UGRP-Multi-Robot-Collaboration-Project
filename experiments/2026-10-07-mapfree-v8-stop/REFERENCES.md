# 정지·재개 원문과 어댑터 경계

원본 Nav2는 기존 v8과 같은 `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`로 고정했다.
추가3파일은 [references/SOURCES.json](references/SOURCES.json)에 URL/SHA256과 원문을 보존한다.
Apache-2.0, 저작권 헤더 유지. 기존 monitor 원문은 `third_party/mapfree_navigation_monitor`에 있다.

|원문|확인한 동작|v8 수정 범위|
|---|---|---|
|[CollisionMonitor L431–465](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/collision_monitor_node.cpp#L431)|매 입력 DO_NOTHING/요청속도에서 시작, invalid source면3축0 STOP|기존 filter 유지. 대기 중에도0입력/timeout 처리|
|[publishVelocity L231–253](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_collision_monitor/src/collision_monitor_node.cpp#L231)|STOP0속도 발행. stop_pub_timeout 후 발행 중단, 비영 속도 자동 재개 없음|2D 마지막0명령을 유지. 새 안전한 controller 요청만 재개|
|[ControllerServer L935–953](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_controller/src/controller_server.cpp#L935)|publishZeroVelocity의 모든 twist 축0, 종료/강제 정지에서 발행|최종0출력 뒤2D 적분기 잔류 속도가 남지 않게 정지 포트 연결|
|[TimedBehavior L313–324](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behaviors/include/nav2_behaviors/timed_behavior.hpp#L313)|stopRobot이 x/y/yaw0 발행|관측 대기 zero twist 및 접촉 stop에도 적용|
|[Wait L31–50](https://github.com/ros-navigation/navigation2/blob/235fc5ce55bdf94d9be360fdbca39d89dc0e4f74/nav2_behaviors/plugins/wait.cpp#L31)|시간 만료 전 RUNNING, 이후 SUCCEEDED. Wait 자체가 매 tick stop을 발행하는 코드는 아님|기존2초 관측 일정 유지, navigator를 대기 중 전진시키지 않음|

[공식 collision monitor 구성 안내](https://docs.nav2.org/rolling/tutorials/general_tutorials/using_collision_monitor/using_collision_monitor/)
는 monitor가 속도 처리의 **마지막 단계**여야 하며, stop 영역 설계에는 실제 반응시간과0명령 때의
감속 실측이 필요하다고 설명한다. 원문 cmd_vel0은 실물 순간 정지를 보장하지 않는다.
따라서 이번 수정의 내부 vel0은 **2D 평가기의 이상적 정지 어댑터**이며 Nav2의 물리 브레이크
모델을 복사했다는 주장이 아니다. 실물/현실 감속은 여기서 적합·변경하지 않는다.

센서 입력 없으면 정지, 유효한 새 입력과 안전한 polygon 판정이면 다음 요청 속도 통과라는
기존 filter를 그대로 사용한다. 새 restart threshold·시간·speed gain·안전 다각형은 추가하지 않는다.
venv/패키지 변경 없음. 문헌 확인에 쓰인 일부 GitHub web fetch가 실패해 pinned raw 원문을
직접 내려받아 SHA를 기록했고 공식 rolling 문서로 동작 경계를 교차 확인했다.
