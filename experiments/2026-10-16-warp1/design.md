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

초기화 보강: 동일 plan은 C setup을 한 번만 하고 native `MjData.__copy__`로 세계별 초기 버퍼를 만든다. qpos/qvel/ctrl/act/warmstart/applied-force 배열은 값 일치와 memory 비공유를 실제 런타임에서 검사한다. controller의 motor 배열·PWM dict도 분리하고, C perception mirror의 physics step은 예외로 차단한다. 다른 plan의 모델을 이 cache로 섞지 않는다. 따로 다른 모델을 묶을 때만 exact-XML C312 자산 + `per_world_model_references_v1`의 변환 필드 감사를 쓴다.

조정자가 지적한 warmup 뒤 첫 world state로 덮이는 위험은 `2fd1490a`부터 두 번째 put_data 뒤에도 모든 integration state를 다시 복사하도록 고쳤다. 새 실행은 첫 teacher action 전 expected/actual world qpos 해시와 첫 RGB 해시를 저장한다. `--reset-check-v1`는 서로 다른 시작을 넣은 별도 진단에서 world0만 다른 시작으로 바꿨다가 원래 integration state로 reset하고, 선택하지 않은 세계의 모든 persistent state가 그대로인지 검사한다. 이 진단은 실제 teacher rollout/성공률이 아니며 mid-episode teacher/이력 reset 구현을 뜻하지 않는다.

현재 계획은 ACT11 frozen source의 v4 scenario ID와 floor_light_v1을 사용한다. v6/v7 또는 scenetex5 승계를 주장하지 않는다. 현재와 다른 승인 장면으로 바꾸면 모델 자산과 관문을 다시 만든다.

정확한 위치/원본 해시는 [MjData 접근 목록](mjdata-read-inventory.json)에 있다(`build_read_inventory.py`, git object를 AST로만 읽고 물리를 import하지 않음). frozen teacher runner의28개 직접 상태 후보는 clock/평가와 `read_relative`, `refresh_obstacles`, `look_truth`로 분류된다. `audit_grasp_act_visibility.py`18개는 가시 ray/FOV와 감사/평가 경로다. `sim/grasp_act_solo_teacher.py`, RGB lookback, recorder, 순수 Score에는 직접 MjData 읽기가 없었다. 간접 `base_xyz/base_rpy`, contactForce, camera/physics 호출도 따로 열거했다. AST 목록만으로 전체 프로그램의 입력 비간섭을 증명하지는 않는다.

ACT15 평가 소스 `686cccb6`의 `scripts/run_grasp_act_student.py:227` 이후 clearance/tilt/contact와242–245의 target/base 측정은 평가 전용으로 남겨야 한다. GPU contact/pose 평가 owner로 옮기고 actor에는 전달하지 않는 설계다. `scripts/grasp_act_student_worker.py`는 observation+jpegs whitelist만 받는 별도 과정이며 직접 MjData 접근이 없다. `harness/grasp_act_solo_recording.py`는 observe(동작 전 JPEG/과거 발행 명령)/target(이번 발행 명령)을 받는 구조를 유지할 수 있지만, 기존 C 관문 승인 SHA를 새 backend 승인으로 재사용하지 않는다. 현재 CLI는 training_rgb를 켜지 않으며 학생 실행·새 관문 이후 기록 어댑터는 미완료다.

교사 성능 후보의 최종 상태: 명시 sleep 정책 compact 옵션은 pinned MJWarp가 지원하지 않아 최종 CLI에서 제거했다. 서로 다른 source seed는 `dof_length` 차이로 결합을 거부했다. 같은 물리 seed/모델에 기존 source plan의 r1 시작 위치3종만 넣은 진단은 N16에서 초기 qpos/RGB3종을 보존했고, world0 리셋 뒤10개 persistent field의 selected/untouched 검사가 모두 통과했다. 이것은 성공률 표본이 아니다.
