# 실물 MasterPi 명령 연결

노트북이 ACT·접근·놓기를 돌리고, 로봇의 Raspberry Pi 는 명령을 받아 시간을 지켜 보드에 쓰는 일만 한다. 명령은 시뮬레이션 포트가 받는 것과 같은 한 줄(바퀴 4, 펄스 길이 4, 서보 5)이다. 2026-11-19 작성, **실물에서 아직 돌려 보지 않았다**(가짜 보드 시험만).

## 왜 Pi 에서 시간을 지키나

MasterPi 확장 보드의 모터 레지스터에는 속도만 들어가고 시간 칸이 없다. 한 번 쓰면 다음 쓰기까지 계속 돈다. 시뮬은 0.1초마다 받은 명령으로 네 바퀴를 한꺼번에 덮어쓰고, 바퀴마다 `받은 시각 + 펄스 길이`에 저절로 선다. 이 정지를 노트북에서 보내면 Wi‑Fi 지연이 그대로 펄스 길이 오차가 되므로(0.1초에 11–12 mm, 10 ms 지연이면 약 1 mm), Pi 가 직접 쓴다. 펄스가 최대 0.15초라 연결이 끊겨도 바퀴는 마지막 명령 뒤 0.15초 안에 선다.

| 시뮬 | 실물 (이 폴더) |
|---|---|
| 새 명령이 네 바퀴를 한꺼번에 덮어씀 (`run_grasp_act_student.py` 의 `_set_motors`) | 같은 순간 네 모터를 모두 씀 |
| 바퀴마다 `받은 시각 + duration_s[i]` 에 정지 | Pi 가 그 시각에 0 을 씀, 늦은 시간을 기록 |
| 서보는 PWM 이 바뀔 때만, 2000 PWM/초 (`camera_robot_port.py`) | 바뀔 때만, 이동 시간 = 차이/2000 초를 보드에 줌. 보드 최소 시간보다 짧으면 최소 시간으로 쓰고 `duration_raised` 로 기록 |
| 범위 밖 명령은 계약에서 거부 | 명령 전체를 거부하고 아무것도 쓰지 않음. 몰래 자르지 않음 |
| 바퀴 값 ±0.31–0.40 | 보정 파일의 실측 표로 보드 정수(35–100)로 바꿈 |

## 파일

| 파일 | 하는 일 |
|---|---|
| `calibration.py` | 시뮬 바퀴 값 → 보드 정수, 바퀴 → 모터 번호·방향, 동작별 `pulse_scale`, 서보 `offset_pwm`/안전 범위, 카메라 워프·비전 설정을 한 JSON에서 로드 |
| `adapter.py` | 로봇 JSON에서 `SimCameraWarp` + 비전 임계값(`UGRP_*`) + 시작 전 `preflight_check()`를 제공하는 통합 Sim2Real 어댑터 |
| `camera_warp.py` | 실기 640×480 프레임을 시뮬 카메라 `(K_SIM, D_SIM, -18°)`로 3축 회전(`pitch`/`yaw`/`roll`)·초점거리 리맵 |
| `executor.py` | 명령 적용(`pulse_scale`, `servo_pwm`), 펄스 끝 정지, 거부, 기록 |
| `boards.py` | 가짜 보드(시험용), 실제 I2C 보드(smbus2 로 버스를 한 번 열어 둠. 프레임은 `scripts/masterpi_control.py` 와 같은 바이트) |
| `server.py` | Pi 쪽 TCP 서버(JSON 한 줄씩), 노트북 쪽 `RobotLink` |
| `camera.py` | Pi → 노트북 카메라 프레임(640×480 JPEG, V4L2 백그라운드 드레인 스레드로 최신 프레임 유지) |
| `pi_check.py` | 로봇에서 도는 읽기 전용 점검(배터리, 카메라, I2C, 카메라·I2C를 잡은 프로세스, 제조사 서비스, 온도, 시계 동기). 아무것도 움직이지 않음 |
| `../scripts/masterpi_robot_server.py` | 실행 진입점. `--camera-port` 를 주면 카메라 전송도 같이 켬 |
| `../scripts/calibrate_real_robot.py` | 로봇별 보정 도구: `sync-runtime`, `trim-straight`(직진 대각 트림), `fit-camera`(큐브 프레임 기반 카메라 워프 피팅), `verify-motions`, `set-profile` |
| `../scripts/masterpi_fleet_check.py` | 노트북에서 여러 로봇에 SSH 로 `pi_check.py` 를 돌려 표로 보여 줌 |
| `../configs/real_robot/calibration_template.json` | 보정 파일 양식. 채우기 전에는 읽히지 않음 |

## 로봇별 통합 Sim2Real 보정 워크플로우

브레인(`PickBrain`, `SignBrain`, `ACT`)은 항상 시뮬레이터 규약만 보고 동작하고, 로봇마다 다른 물리 특성(바퀴 배선·대각/요 트림·동작별 펄스 스케일·서보 오프셋·카메라 각도/초점거리·색상 필터)은 `configs/real_robot/<robot_id>.json` 한 파일에서 흡수합니다.

```bash
# 1) Pi에 최신 런타임과 로봇 프로파일 동기화
python3 scripts/calibrate_real_robot.py sync-runtime --host ras2 --calibration configs/real_robot/ras2.json

# 2) (신규 로봇) 30 mm 큐브를 정면 거리 2곳에 두고 촬영한 이미지로 카메라 워프 자동 피팅
python3 scripts/calibrate_real_robot.py fit-camera --calibration configs/real_robot/ras2.json \
  --sample 0.25:near.jpg --sample 0.45:far.jpg --apply --host ras2 --sync

# 3) 빨간 큐브를 정면 45~50 cm에 두고 직진 대각 바퀴 트림 자동 보정
python3 scripts/calibrate_real_robot.py trim-straight --host ras2 --calibration configs/real_robot/ras2.json --apply --sync

# 4) 단일 프로파일 플래그(--calibration) + 시작 전 안전 검사(--preflight)로 Pick 실행
python3 scripts/real_skill_test.py pick --side real --host ras2 --kind red \
  --calibration configs/real_robot/ras2.json --preflight \
  --model <actor_dir> --actor-python <venv_python> --actor-threads 2 --out runs/ras2-pick
```

## 쓰는 법

```bash
# Pi (보정 파일의 measured=true 일 때만 --board i2c 허용)
python3 scripts/masterpi_robot_server.py --calibration configs/real_robot/ugrp1.json --board i2c --log run.jsonl
```

```python
# 노트북
from real_robot.server import RobotLink
link = RobotLink('<pi 주소>', 8765)
link.init_servos({'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}, duration_s=2.0)
reply = link.send(command_row)   # 시뮬 포트에 주던 그 행. reply 에 Pi 수신 시각
```

Pi 에서 Hiwonder 기본 서비스(앱 제어, 카메라 스트림)는 끄고 돌린다. I2C 와 카메라를 두 프로그램이 같이 잡으면 충돌한다.

## 로봇을 켜면 먼저

```bash
python3 scripts/masterpi_fleet_check.py ugrp1 ugrp2 ugrp3 --json fleet.json   # SSH 이름은 각자 ~/.ssh/config
```

배터리 전압, 카메라 한 장, smbus2 설치 여부, 카메라·I2C 를 이미 잡고 있는 프로그램(Hiwonder 앱 등)을 한 줄씩 보여 준다. 모터·서보 명령은 보내지 않는다.

Pi 와 노트북의 시계는 다르다. 프레임의 `t_capture` 는 Pi 시계, `t_arrival_laptop` 은 노트북 시계다. 두 값을 바로 빼지 않는다. 지연은 명령 서버 응답의 왕복 시간처럼 한 기기 안에서 잰다.

## 아직 없는 것

- 보정 파일 실측값(T03 바퀴, T04 서보).
- 실물 확인: 바퀴 띄운 상태에서 정지 시각·연결 끊김 정지부터 본다([안전 체크리스트](../docs/sim2real/README.md#구동-전-체크리스트)).

시험: `python3 -m pytest tests/test_real_robot_link.py`.

## 실물 평가

천장 카메라 보정·기록, 사건 기록, 지표 추출은 [EVALUATION.md](EVALUATION.md).
