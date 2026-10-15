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

## 전체 NumPy 교사로 옮길 배열 계약 (아직 미구현)

현재 scalar frontend를 최종 벡터 교사로 표시하지 않는다. 다음 경계로 옮기며 기존 C 교사와 새 배열 교사는 별도 토글/코호트로 검증한다.

|배열|owner/shape|갱신과 금지|
|---|---|---|
|phase, skill, result, active|교사 `[N]` enum/int/bool|SIM tick과 허용 관측 mask로만 전환. Score/contact/성공 정답을 상태 전환에 연결하지 않음|
|phase_start, skill_start, deadline|교사 `[N]` float64 SIM초|고정 SIM clock. 계획은 frozen40000 노드와 같은 계산량 예산. wall은 VM 자원 감시에만 사용|
|issued_pwm, servo_target, fractional_pwm, servo_deadline|명령 `[N,5]`|측정 관절이 아닌 발행 상태. 현재 `control_tape`가 N을 벡터화하며400 물리 tick만 고정 루프|
|issued_wheels, wheel_deadline, relay|명령 `[N,4]`|세계별 lease/정지/reversal 독립. 반환한 명령을 다음 이력에 기록|
|visible_count, probe_count, holding, measurement_valid|관측 `[N]`|`~holding & probes>0 & visible>=ceil(probes/3)` mask부터 계산. 금지 행의 위치 getter를 호출하지 않음|
|relative_xyz_yaw|관측 `[M,4]`, M=허용 world 수|전체 `[N]` 정답 배열을 교사에 건네지 않음. 허용 world index와 상대량만 전달. 현재 pure lazy vector helper는 있으나 실제 frontend는 frozen InputAudit 사용|
|approach/align target, stable_count, last_command|교사 `[N,k]`|각 phase mask에 동일한 frozen 산술을 적용. reset 때 해당 행/이력/RGB buffer를 함께 지워야 하며 현재 physics-only reset과 구분|
|IK inputs/outputs/validity|교사 `[M,k]`|같은 종류/스킬의 masked 목표를 모아 기존 기구학을 배열식으로 이식. 임의 보간 표나 새 허용 오차를 넣지 않고 기존 solver 입출력과 대조. 현재 scalar IK 유지|
|RGB history, lookback/localizer state|로봇별 `[N,T,H,W,C]` + 발행 이력|world index를 함께 보존. RGB/명령뿐인 observer와 pose-free lookaround를 유지. 현재 per-world observer 유지|
|clearance, tilt, speed, finger_force, Score state|평가 `[N,k]`|GPU 상태/접촉 owner. 교사·학생 입력 객체에 넣지 않음. 현재 force 합산 kernel은 배치화, Score는 scalar|

가시 ray는 현재 C kinematic mirror에서 기존 FOV/7-probe/가림 규칙을 유지했다. 다음에는 동일한 ray 원점·끝점·geom group·self 제외를 `[N,K]`로 묶어 pinned MJWarp ray kernel로 옮겨야 한다. ray 결과를 RGB와 동등한 관측이라고 새로 주장하거나 held target 위치를 넘기지 않는다. OpenCV remap/JPEG는 현재 세계별 처리이며, GPU remap로 바꿀 때는 같은 K/D/grid 및 실제 RGB 차이·teacher 결과를 별도 확인한다.

ACT 학습 자체는 물리 엔진을 호출하지 않는다. 새 MJWarp 자체 관문 뒤 생성된 world별 recorder 자료를 같은 학생 관측 계약으로 학습하되 manifest에 backend·scene/model hash·host·teacher/adapter SHA를 붙이고 C 자료와 합산하지 않는다. 학생 평가 runner의 물리 step/RGB/evaluator만 같은 transport로 연결하고, isolated actor의 observation+jpegs whitelist와 TRAIN-only 정규화 계약을 유지하는 것이 후속 이식이다. 이번에는 학습·학생 평가를 실행하거나 완료했다고 표시하지 않는다.
