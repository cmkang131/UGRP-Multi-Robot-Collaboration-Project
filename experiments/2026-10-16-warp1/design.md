# warp1 이식 경계 (DEV, HOLD_SCENE)

기반 PR #524 `142dbf04`; 교사/장면 동결 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`을 별도 읽기 전용 source로 지정한다. 기존 C 파일은 변경하지 않는다. ACT14/15 학생 분석 및 ACT16 미승인 계획은 기존 교사 입력·학습/평가 경계를 확인하는 참고이고 이 작업에서 학습하지 않는다.

|직접 읽기/상태|기존 위치|배치 처리|
|---|---|---|
|장면·초기 qpos/ctrl·카메라 보정|run_solo_grasp_act_teacher setup, make_scene|동일 모델/장면 사용, 세계별 qpos/qvel/ctrl. 초기화는 C scene.setup의 setup이며 온라인 물리는 Warp. 같은 모델 world 복제로 시작, 다른 장면 혼합 금지|
|자기/대상 xpos/xmat|read_relative|가시성+not-held 뒤에만 기존 lazy InputAudit. 상대 xyz/yaw만 교사로 전달. held 구간은 close~open까지 보수적으로 가림|
|가림/7개 표면 probe·주변 장애물|BandVisibility.region_visible, refresh_obstacles|GPU 상태에서 복원한 별도 C MjData의 kinematics/ray. 물리 step 없음. 정답 투영 교사의 기존 가시 조건 유지. 이 초기 adapter는 세계별 Python 비용이 남음|
|RGB640×480·K/D·fisheye·v3 mount|CameraRobotPort.capture, bind_camera|MJWarp batch renderer→readback→기존 OpenCV remap→JPEG encode/decode, 10Hz. 부분 투명도 차이는 별도 미해결 기록. TOP은 제어/지도/위치 추정으로 전달하지 않음|
|Duty wheel 기한·분수 servo 누적값|DutyActPort.tick, CameraRobotPort._advance_servos|[world,4/5] numpy 상태. 0.1초 안의 모든 0.00025초 tick에서 기한·2000PWM/s·nearest-even rounding·v7 sign relay 계산. 측정 관절 입력 없음|
|교사 상태 전환·IK·lookback RGB·route|SoloTeacher.step / SoloLookaround|우선 고정 교사 재사용, 세계별 독립 인스턴스. 완전 numpy 교사 이식 완료라고 보고하지 않음. 상태/IK/가시 ray가 N에 비례하는 병목을 실측|
|접촉 법선력·bottom/tilt/speed·Score|runner 평가 구간, grasp_act_solo_evaluation|GPU contact force를 평가 owner로만 전달. qpos 복원 및 analytic bottom. Score/성공을 teacher에 역전달하지 않음|
|실패 직전 자기 RGB|신규 기록 옵션|학습 카메라와 별도로 10Hz×10SIM초 ring, 크기/개수 기록. 첫 world 상태를 사후 overview 복원용으로 저장|
|학습 recorder/학생 평가|ACT12 SoloRecorder / ACT15 worker|backend transport와 입력 계약 설계만. 새 MJWarp 자체 교사 관문·장면 승인 전 training recording fail-closed. 학생/학습 통합은 이 단계 미완료로 보고|

판정은 C 5mm 동등성이 아닌 MJWarp 자체 ≥95%·최소40회 관문이다. 본 파일럿/처리량과 관문은 별도이며 C·gcp1 결과와 합산하지 않는다. 신규 성공 허용 상수는 넣지 않고 frozen Score를 쓴다. 시간 제한은 SIM tick이며 wall은 L4 자원4시간 감시 전용이다.

현 ACT 장면: `grasp_act_scene_v1`, `floor_light_v1`, camera review v3 runtime binding, `real_v1` servo stiffness, native v7, mesh roller, idle contacts off, end_color_scene off (solo), weld off. scenetex5는 미적용이며 조정자 결정 대기다.
