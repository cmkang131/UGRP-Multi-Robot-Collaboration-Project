# 다음 단계의 인수 계약 (교사 관문 통과 전 구현/기록 본실행 금지)

근거: act16w 수신 기록과 기존 rl1b `scripts/rl_act_env.py`, `rl_act_rpc.py`를 읽었다. warp3 2단계 성공 뒤에만 다음 어댑터를 구현·실행한다.

- `reset(plans, indices=None)`: 첫 reset은 전체 world, 이후 선택 world만. 서로 다른 시작을 지원하고 모델 구조가 맞지 않는 계획은 명시적으로 거부한다. 물리 integration/solver warmstart/접촉·명령 relay/PWM 보간·동작 chunk·RGB와 명령 이력·RNG·done latch를 모두 격리한다. 선택되지 않은 world의 상태와 이력은 바이트 그대로 둔다.
- `step(actions)`: world별 `{command, done}`를 입력받아 기존 0.1 SIM초 제어 주기를 실행한다. 종료 world는 reset 전까지 정지하고 시뮬레이션·명령 시계와 actor 이력이 진행하지 않는다. done은 발행 done과 SIM 상한만으로 정하며 정답 성공으로 바꾸지 않는다.
- `read_actor(i)`: 검증된 observation과 자기 JPEG history만 반환한다. 입력은 자기 RGB/자기 발행 명령/스킬·물건 종류·자리 번호표. 자기 RGB의 네이티브 640×480/10Hz/K,D/FOV/마운트는 교사/학생 모두 그대로다. 모델 내부 resize와 혼동하지 않는다.
- `read_training(i)`: 명시적 학습 인스턴스에서만 reward/critic 전용 정답 lane. actor/deployment에서 호출을 차단하고 actor canary 감사로 분리를 확인한다. 정답 성공·접촉은 actor로 보내지 않는다.
- 기록: 관문 승인과 별도의 기록 승인에 연결한다. 학생 입력·교사 표적·평가 출력·체크포인트 출처를 구분하고 실패/상한/오류를 전부 남긴다. 기존 SoloRecorder의 학습 카메라 해상도/주기/화각과 exact JPEG를 재사용한다.

정적 계약을 작성한 것은 API의 실행 준비 완료가 아니다. `RECORD_API_READY`는 부분 reset/새 시작/종료 world 정지와 실제 actor RGB step을 gcp2에서 검증한 뒤에만 쓴다.

소스 고정 주의: 기존 `SoloRecorder.validate_approval`은 관문과 기록 controller SHA가 같아야 한다. 따라서 새 adapter 때문에 통과한 교사의 동작 소스를 바꾸고 과거 관문을 소급 승인하면 안 된다. 우선 검토할 방식은 f0db6b1a의 교사/물리 코드를 그대로 재사용하고, 별도 opt-in capture hook으로 **동일 controller JPEG**를10Hz 저장한 뒤 기존 command trace로 SoloRecorder 관측/표적을 구성하는 것이다. gate controller SHA와 새 기록 adapter SHA를 따로 남기고, 첫 프레임의 실제 발행 PWM/hold를 bootstrap으로 보존한다. `previous`/phase-before/skill-before와 trace의 phase-after를 정확히 맞추는 검증이 필요하다. 이것은 설계 후보이며 아직 구현·검증된 API가 아니다.

Actor 쪽은 기존 교사 객체를 만들지 않는 별도 backend subclass/RPC 경계를 우선 검토한다. `read_actor`는 observation/JPEG만, privileged reward/critic은 학습 lane만 허용한다. 기존 rl1b 코드의 partial reset 즉시 바이트 비교만으로 충분하다고 하지 말고, reset하지 않은 world의 **다음 실제 물리 step**도 paired GPU replay로 대조해야 한다. public `reset_data`가 공유 contact counter에 미치는 영향, tree/sleep/solver/command interpolation/time/history/RNG를 모두 확인한다. 종료 world는 발행 done/SIM cap으로만 정하고 reset 전까지 물리·명령·history clock을 고정한다.

후속 구현 시 확인할 사항(아직 구현하지 않음):

- 기록 hook은 f0db controller의 `capture`가 돌려주는 JPEG를 그대로 저장한다. 첫 `previous`는 실제 `DutyActPort` 초기 발행 PWM/hold에서 얻고, command trace의 phase-after/context-after와 다음 관측의 phase-before를 맞춘다. 원래 success-measurement 결과는 보존하고 외부 기록 결과/승인에 controller SHA와 adapter SHA를 구분한다. gate 시드는 학습 기록에 쓰지 않는다. API 검증과 bulk dataset admission은 별개다.
- actor Owner는 교사 객체 없이 같은 scene/sleep/command/physics/RGB 코드를 재사용한다. 기존 rl1b의 직접 scene 생성은 새로운 native-sleep/scene-v5 초기화와 다르므로 그대로 복사하지 않는다. reward/critic만 private 프로세스 lane에 두고 실제 ACT 체크포인트의 own-RGB step과 canary 거부를 확인한다.
- partial reset은 초기화된 호환 모델 안의 새 시작을 명시적으로 지원한다. 모델·질량·geometry를 몰래 버리거나 다른 모델로 reset하지 않는다. 지원 모델 배열 pointer/shape가 바뀌면 capture된 CUDA graph도 다루어야 한다. prototype cache는 현재 world가 쓰는 항목만 유지하여 episode마다 계속 쌓이지 않게 한다.
- 종료 world는 GPU integration뿐 아니라 sleep/tree/solver warmstart와 port relay·PWM 보간·명령/RGB 이력·public clock/RNG까지 유지한다. derived/shared contact cache는 다음 step에서 다시 계산되는지 paired GPU replay로 검증한다. source `sync_render`는 모든 C mirror의 시간을 전역 tick으로 쓰므로 비활성 world의 시간/actor snapshot도 별도로 보존해야 한다. reset하지 않은 world의 다음 실제 step을 baseline branch와 비교한다.
