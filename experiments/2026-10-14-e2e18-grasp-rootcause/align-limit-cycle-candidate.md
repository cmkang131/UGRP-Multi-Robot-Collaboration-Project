# 정렬 limit cycle 수정 후보 (2026-10-14)

상태: UNAPPLIED, base SHA 00c08c7beba85c7534f2aa81f44d95670af03c83. 지정 worktree/공유 Git 쓰기와 GitHub CLI 연결이 차단됐다. 새 커밋, push, 시뮬레이션/물리 실행 없음. 후보 메모리 시험은 worktree 적용 시험이나 물리 성공 근거가 아니다.

## 원인과 근거
- `sim/grasp_act_teacher.py:150-163`: 전체 준비/IK 조건이 참일 때만 정지하며 축별 데드밴드가 없다. IK가 거부한 전진 잔여 오차와 작은 옆/회전 오차를 함께 PI로 출력한다.
- `sim/grasp_act_teacher_v3.py:69-72` → `sim/grasp_act_port.py:62-67`: 출력이 0.35 바퀴의 짧은 duty로 바뀌고 1 ms 미만만 제거한다. `teacher_v3.py:142-143`의 60초 시한 외에는 무진전/반전 탈출이 없다.
- 회수된 73011 명령/평가 원장을 재구성했다. 26-51 SIM초 250샘플에서 전진 오차 6.006-7.164 mm, 옆 오차 -0.642-11.179 mm, yaw -0.0503..-0.0136 rad; 전체 pad/descent IK 거부149/250. 저장 명령 30 SIM초(평가 t=31.8)의 각 바퀴 폭은1.404/12.294/16.979/6.088 ms. 평가 좌표는 이 사후 분석에만 썼고 후보 제어는 VisibleWorld 입력만 쓴다.
- 73009 r1은 첫 acquisition(초기17.7 SIM초/177관측)이 비가시였다(기존 교사 진단은 팔 준비 뒤만 세어17.0초). `teacher_v3.py:98-107`에서 팬1500 고정·두 팔 높이 교대·차체 회전으로 찾는다. 정확한 가림/화면 이탈 원인은 이미지가 로컬 회수돼 있지 않아 미확인이다. 이번 턴 직접 본 영상 프레임0장; 사용자/운영자의6프레임 원인 확인은 독립 검증으로 승격하지 않는다.
- 두 원장의 delivered visible_measurements에서 임계 미달0. 기존 result.json에는 input_audit 필드가 없다(`run_grasp_act_teacher.py:294-302`).

## 후보 변경
`--teacher-stability align_relook_v1`(기본off): 교사에만 축별 정지/재시작 문턱(x2/4mm, y12/18mm, yaw0.02/0.04rad), yaw→y→x 순 단일축 명령,40ms 최소 폭, 연속4회 오차 부호 반전 또는3SIM초 무진전 시 재관측·적분초기화를 적용한다. 2회 재관측 뒤도 실패하면 alignment_no_progress로 끝낸다. 기존 pad IK·준비 기준·pick sequence·학생 포트·물리/FOV는 그대로다. IK가 거부한 작은 x 오차는 준비로 간주하지 않는다.

시야 탐색은 먼저 정지 상태에서 팬/두 팔 높이를 0.6초 간격으로 훑고 전체7.2초 뒤 차체 회전을 허용한다. 숨은 대상 위치를 읽지 않는다. 처음 탐색은search, 보인 뒤만approach/align로 기록한다. 40ms/문턱/탐색 시간은 후보 설계값이며 실물 응답과 개선 성공은 확인 안 됨. 시야 유지의 물리 보장도 미확인이다.

입력 감사는 전달 직전 측정 행 수/임계 미달을 세고 임계 미달이면 즉시 실패한다. 초기·완료·HOST_ERROR 결과에 같은 input_audit 객체를 남긴다. 토글은 batch→episode 및 결과/속도/학습 허가에 함께 묶어off/on 근거를 섞지 않는다.

운영 순서: 같은 GCP n4-highcpu-64/source/toggle로71000→73011→73009 진단(동시3), 진단3/3 뒤 동시16속도30SIM초, 그 뒤 fresh76000..76039(40개). --execution-host gcp1, 학습RGBoff/weldoff. 원인 확인 시 운영자 소유 실행만 즉시 정지하고 원본/분모 보존. 새SHA/적용시험/push확인 전에는 큐ready=false.

## 참고 자료
- MathWorks 공식 Relay: https://www.mathworks.com/help/simulink/slref/relay.html . Description와 switch on/off point 본문 확인. 서로 다른 켜짐/꺼짐 문턱으로 상태를 유지하는 표준 hysteresis 근거.
- MathWorks 공식 Dead Zone: https://www.mathworks.com/help/simulink/slref/deadzone.html . 입력 구간에서 출력0이라는 본문/표 확인. 축별 정지 구간에 적용했다.
- Nav2 공식 SimpleProgressChecker: https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/simple_progress_checker/ . required_movement_radius와movement_time_allowance본문 확인. 여기서는 금지된 측정주행 대신현재보이는대상오차의개선시한으로변형했다. Nav2기본10초/0.5m를그대로쓴것은아니다.
- Nav2 공식 Rotation Shim: https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_rotation_shim_controller/ . 진입/이탈각 문턱 문서 확인. 관측변화 주변의모드왕복방지참고이며 전체제어기재현은아니다.
- wheel effort35와30이하정지 경계는사용자제공실물조건 및기존duty_wheels정의다.40ms최소폭의실물효과는미확인.단일축우선순위와수치는본과제적응설계로표시한다.
