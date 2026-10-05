# Windows에서 SIM 팔 명령을 실물 경계에 연결

`scripts/real_robot_link.py`는 유한한 단일 명령 연결 도구다. 기본은 dry-run이다.
SIM의 `{"kind":"arm","servo_id":1,"pulse":1800}` 형식을 기존 Pi의
`masterpi_control.py servo` 명령으로 변환하고, 실물 자기 JPEG와 명령 시도 이력을
보존한다. 모듈의 `RealRobotLink.observe()` / `apply_arm()`을 연결 경계로 재사용할 수 있다.

이 단계는 3대 dispatch 실행기의 REAL backend 완성이 아니다. 기존 dispatch는
MuJoCo 세계, TOP 영상과 SIM 전용 시계를 사용한다. 그 실행기를 이 도구가 자동으로
변경하거나 계획을 재생하지 않는다. 실제 TOP 카메라/보정, 로봇별 이동 보정,
실시간 동기화 및 스킬 검증을 별도로 연결해야 한다. 이동 명령은 변환하지 않는다.
50x 관찰 속도와 SIM 물리 timestep은 실물에 적용하지 않는다.

## 전제

- 기존 카메라 SSH 터널과 호스트 키 검증을 유지한다. 카메라 서비스는 재시작하지 않는다.
- 전용 SSH 키와 known_hosts는 사용자 `.ssh`에 보관한다. Git에 올리지 않는다.
- `--control-sha256`은 직접 검토한 Pi 제어 파일의 해시다. 변경되면 재검토한다.
- Python 표준 라이브러리만 사용한다. 이 도구 자체는 상시 서비스를 시작하지 않는다.
- 명령 성공은 실제 자세 도달/파지 성공이 아니다. HTTP 시각도 촬영 시각이 아니다.
- 자기 영상은 실물 raw 영상이다. SIM 카메라 보정/FOV와 같다고 주장하지 않는다.

## 기본 사용

PowerShell에서 저장소 루트로 이동한다. 아래 값을 자신의 확인된 환경으로 바꾼다.

```powershell
$RobotArgs = @(
    '--host', '<ROBOT_IP>', '--user', '<ROBOT_USER>',
    '--identity', 'C:\Users\<USER>\.ssh\id_ed25519_ugrp',
    '--known-hosts', 'C:\Users\<USER>\.ssh\known_hosts',
    '--control-sha256', '<REVIEWED_REMOTE_SHA256>'
)
python scripts/real_robot_link.py observe @RobotArgs --output outputs/real-link-observe-NEW
$ArmAction = '{"kind":"arm","servo_id":1,"pulse":1800}'
python scripts/real_robot_link.py arm @RobotArgs --action-json $ArmAction --duration-s 0.5 --output outputs/real-link-dry-run-NEW
```

기존 결과는 덮어쓰지 않는다. 각 `result.json`에 실행 소스 SHA, 원격 제어 파일 SHA,
관측, dry-run/명령 전달 여부를 기록한다. 로봇별 결과와 영상은 로컬에 보관한다.

## 실물 동작에는 별도 현장 확인이 필요

`--execute`와 `--safety-profile FILE`을 모두 지정한 경우에만 실물 명령을 보낸다.
profile은 `robot_id`, `servo_id`, `pulse_min`, `pulse_max`, `battery_min_mv`,
`battery_max_mv`, `operator_ready`를 포함한 JSON이다. 안전한 관절 범위와 실제 전지 사양을
현장 담당자가 확인해서 작성한다. 숫자를 추측한 기본 profile은 제공하지 않는다.
팔 전체 자세의 간섭도 현장에서 확인해야 한다. profile 자체는 안전 인증이 아니다.

기존 I2C probe가 실패하거나 잘못된 값을 반환하면 실물 동작을 거부한다. 이전 수동 동작의
성공을 이유로 이 검사를 무효화하지 않는다. 보드 사양·전원·측정 방법을 확인하여
probe 실패 원인을 찾은 다음 별도 변경으로 수정한다. 연결 실패·시간 초과 시 자동 재전송하지 않는다.
dry-run에 사용한 PWM 값도 실물에서 안전하다고 인증된 값은 아니다.
