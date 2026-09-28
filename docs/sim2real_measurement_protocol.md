# 실물 MasterPi 실측·보정 절차 (sim2real, #214)

2026-09-28 작성. 실물 Hiwonder MasterPi(ugrp1, ugrp2)의 치수·센서·구동을 손으로 재는 절차다. 준비물은 자, 버니어 캘리퍼스, 휴대폰 카메라, 노트북이다. 결과는 [`configs/real_measurements_template.json`](../configs/real_measurements_template.json)을 로봇별로 복사해 채운다. 에이전트가 나중에 그 파일을 읽어 SIM 상수에 반영한다.

이 문서는 절차만 정한다. 아직 실측한 값은 없다. 표의 "예상값"은 공식 치수도·SDK·현재 SIM 값이고, 실측값이 아니다.

## 0. 먼저 읽기

### 0.1 왜 재는가

- SIM 몸체는 두 출처가 섞여 있다. v2는 SDK 링크 길이와 사진 추정값을 쓴다. v3(PR #249)는 공식 치수도를 축척해 쟀다. 둘이 5–48 mm까지 다르다. 실물만 답을 정할 수 있다.
- 초음파 모델(PR #248)은 장착 높이, 빔 각도, 갱신 주기, 무반사 값을 가정으로 두었다. 운반 높이 결정은 여유가 1–3 mm뿐이라 이 가정에 민감하다.
- 동역학 보정 파일 `sim/masterpi_dynamics_calibration.json`은 `validated: false`이고 값이 모두 `null`이다.

### 0.2 이미 있는 도구를 쓴다

새 도구를 만들지 않는다. 아래 기존 자산을 그대로 쓴다.

| 자산 | 용도 |
|---|---|
| `calibration/masterpi/README.md` | 보정 증거 파이프라인 1–8단계 |
| `calibration/masterpi/static_measurements.json` | 바퀴 반지름·축거·윤거·블록 질량·마찰 |
| `calibration/masterpi/servo_trials.jsonl` (60행) | 서보 3/4/5/6 PWM 계단 응답 |
| `calibration/masterpi/hand_eye_trials.jsonl` (24행) | 손목 카메라–팔 hand-eye |
| `calibration/masterpi/chassis_trials.jsonl` (108행) | 주행 끝점·정지 거리 |
| `scripts/benchmarks/apply_masterpi_static_measurements.py`, `fit_masterpi_servo.py`, `fit_masterpi_hand_eye.py`, `fit_masterpi_dynamics.py` | 위 자료를 읽어 보정값을 적합 |
| `scripts/benchmarks/analyze_masterpi_overhead_video.py` + `calibration/masterpi/markers/` | 천장 영상·ArUco로 주행 끝점 추출 |
| `scripts/masterpi_control.py` | 실물 구동 CLI(속도 35–40, 옆 이동 35–70, 한 번 최대 2 s) |

이 문서의 새 템플릿은 위 파일에 없는 항목(치수 13개, 초음파, 카메라 자세, 서보 각도표, 집게 폭)을 담는다. 시행 단위 자료는 위 JSONL에 그대로 적는다.

### 0.3 규칙

1. **로봇마다 따로 잰다.** 템플릿을 `calibration/masterpi/real_measurements_<로봇>_<YYYYMMDD>.json`으로 복사한다. 예: `real_measurements_ugrp1_20261001.json`.
2. **모든 측정은 3번 이상 반복한다.** 반복값을 `repeats`에 모두 적는다. `value`에는 중앙값을 적는다.
3. **사진을 남긴다.** 캘리퍼스 눈금이 보이게 찍는다. 원본은 기본 체크아웃 `outputs/real-measurements/<로봇>-<YYYYMMDD>/`에 두고, 파일명과 sha256을 템플릿 `raw_files`에 적는다. 사진·CSV는 Git에 커밋하지 않는다.
4. **`measurement_source`에 `sim`, `mujoco`, `synthetic`, `mock`, `generated`, `fake`가 들어가면 안 된다.** 보정 스크립트가 거부한다. "similar"처럼 단어 안에 들어가도 거부된다. 예: `"caliper and ruler on ugrp1, 홍길동"`.
5. **값을 모르면 `null`로 둔다.** 추정값을 넣지 않는다. 이유는 `notes`에 쓴다.
6. **장치 상태를 적는다.** 배터리 전압(`python3 masterpi_control.py probe`), 바닥 재질, 온도(대략)를 블록마다 기록한다. 주행 속도는 전압에 따라 바뀐다.
7. **이 값들은 고정 보정값이다.** 실시간 정답이 아니므로 학생 제어기에 상수로 줄 수 있다(AGENTS.md 지도 경로 예외의 "고정 카메라 보정"과 같은 성격). 실험 중 위치 정답으로 쓰지 않는다.

### 0.4 안전

- 서보 시험은 로봇을 상자 위에 올려 **바퀴가 뜬 상태**에서 한다.
- 한 사람은 Ctrl-C를 칠 준비를 한다. `masterpi_control.py`는 종료 시 모터를 멈춘다.
- 다른 에이전트나 프로그램이 로봇을 쓰는지 먼저 확인한다. 구동 CLI는 actuator lease(`/tmp/ugrp-masterpi-actuator.lock`)를 잡으므로, 사용 중이면 "busy" 오류가 난다.
- 팔을 크게 돌리기 전에 팔을 위로 접어 몸체와 부딪히지 않게 한다.

### 0.5 좌표 기준

- `x`는 앞, `y`는 왼쪽, `z`는 위다(ROS REP 103과 같음).
- **x 원점은 앞·뒤 차축 중앙**이다. 바닥 위 높이 `z`의 원점은 바닥이다. v3 모듈(`sim/masterpi_geometry_v3.py`)과 같다.
- 차축 중앙을 찾는 법: 로봇을 평평한 책상 위 A3 종이에 올린다. 직각자를 바퀴 허브 나사 중심에 대고 종이에 네 바퀴 중심을 표시한다. 앞 두 점의 중점과 뒤 두 점의 중점을 잇고, 그 선의 중점이 원점이다. 이 종이를 "기준지"라 부르고 모든 x 측정에 쓴다.
- 서보 축 위치는 서보 혼(원판) 중앙 나사의 중심이다.
- 두 축 사이 거리 재는 법: 캘리퍼스로 두 나사 머리의 **바깥쪽 끝–끝** 거리와 **안쪽 끝–끝** 거리를 잰다. 둘의 평균이 중심 간 거리다.

## 1. 정적 치수

### 1.1 측정표

허용오차는 "이보다 크게 다르면 SIM 값을 바꿔야 하는 차이"다. 근거는 표 아래에 있다. 번호 1–13은 PR #249의 `MEASURE_ON_ROBOT` 목록이고, `E`로 시작하는 줄은 추가 항목이다.

| # | 템플릿 키 | 무엇을, 어디서 어디까지 | 도구 | 반복 | 예상값 | 허용오차 |
|---|---|---|---|---|---|---|
| 1 | `sonar_center_height_mm` | 바닥 → 초음파 두 원통(송·수신기) 중심 높이 | 캘리퍼스 깊이봉 또는 직각자+자 | 3 | 치수도 61.7, v2 54 | ±2 mm |
| 2 | `sonar_face_forward_mm` | 차축 중앙 → 송·수신기 앞면(망) | 기준지+직각자+자 | 3 | 치수도 88.0, v2 84 | ±2 mm |
| 3 | `sonar_pitch_deg` | 송·수신기 축의 상하 기울기(수평 0, 위로 +) | 휴대폰 수평계 앱+자 | 3 | 0 | ±1° |
| E1 | `sonar_center_lateral_mm` | 로봇 중심선 → 두 원통 중점(왼쪽 +) | 기준지+자 | 3 | 0 | ±2 mm |
| E2 | `sonar_transducer_spacing_mm` | 두 원통 중심 간격 | 캘리퍼스 | 3 | 26.7, v2 34 | ±1 mm |
| 4 | `yaw_axis_forward_mm` | 차축 중앙 → 팔 yaw(ID6) 축 | 기준지+직각자, 1.3절 | 3 | 치수도 48.2, **v2 0** | ±2 mm |
| E3 | `yaw_axis_lateral_mm` | 중심선 → yaw 축(왼쪽 +) | 같음 | 3 | 0 | ±2 mm |
| 5 | `shoulder_axis_height_mm` | 바닥 → 어깨(ID5) 축 | 직각자+자 | 3 | 치수도 127.7, v2 125.5 | ±2 mm |
| 6 | `upper_arm_mm` | ID5 축 → ID4 축 | 캘리퍼스(바깥+안쪽 평균) | 3 | 치수도 57.7, SDK·v2 65 | ±1 mm |
| 7 | `forearm_mm` | ID4 축 → ID3 축 | 캘리퍼스 | 3 | 치수도 62.4, SDK·v2 62 | ±1 mm |
| 8 | `wrist_to_closed_tip_mm` | ID3 축 → 닫힌 집게 끝(공구 축 방향) | 캘리퍼스 | 3 | 치수도 94.0, SDK 100 | ±2 mm |
| E4 | `straight_up_tip_height_mm` | 팔을 곧게 세운 자세에서 바닥 → 닫힌 집게 끝 | 줄자+직각자 | 3 | 공식 343, SDK 합 352.5 | ±3 mm |
| 9 | `camera_lens_along_mm`, `camera_lens_up_mm`, `camera_lens_lateral_mm`, `camera_pitch_deg` | ID3 축 → 렌즈 앞면 중심(공구 축 방향 / 공구 축에서 위 / 옆), 광축과 공구 축 사이 각 | 캘리퍼스, 옆 사진 | 3 | 순정 치수도 53 / 28; ugrp1 적합 67 / 13.6 / 0, 약 −7.5…−8° | ±2 mm, ±1° |
| 10 | `camera_model` | 카메라 보드 라벨, USB ID | 눈, `lsusb` | 1 | 순정 HBVCAM-V2101 또는 icspring 어안 | 일치 여부 |
| 11 | `wheel_track_mm` | 왼쪽–오른쪽 바퀴 중심 간 거리(바퀴 폭 중앙끼리) | 기준지+자 | 3 | 치수도 129.9, v2 131, SDK 134 | ±2 mm |
| 11 | `wheelbase_mm` | 앞–뒤 차축 거리 | 기준지+자 | 3 | 치수도 118.8, v2 120, SDK 118 | ±2 mm |
| 11 | `wheel_width_mm` | 메카넘 바퀴 폭(롤러 바깥 끝) | 캘리퍼스 | 3 | 치수도 30, v2 31 | ±1 mm |
| E5 | `wheel_diameter_mm` | 바퀴 지름. 1.4절 굴리기 시험으로 확인 | 캘리퍼스+굴리기 | 3 | 65 | ±0.5 mm |
| 12 | `chassis_length_mm` | 짙은 회색 차체 앞판 → 뒤판 | 자 | 3 | 치수도 185, v2 판 120 | ±3 mm |
| E6 | `overall_length_mm`, `overall_width_mm` | 전체 길이·폭(바퀴 포함, 팔 접은 상태) | 자 | 3 | 185 / 162 | ±3 mm |
| E7 | `chassis_bottom_height_mm`, `chassis_top_height_mm` | 바닥 → 차체 아랫면 / 윗면 | 캘리퍼스 깊이봉 | 3 | 16.8 / 50.0 | ±2 mm |
| E8 | `cover_top_height_mm` | 바닥 → 덮개 윗면 | 자 | 3 | 101 | ±3 mm |
| E9 | `arm_box_front_forward_mm` | 차축 중앙 → 팔 받침 상자 앞면 | 기준지+자 | 3 | 76.9 | ±2 mm |
| E10 | `robot_mass_kg` | 로봇 전체 질량(배터리 포함) | 저울(있으면) | 3 | 공식 1.10 | ±0.05 kg |
| 13 | `shoulder_servo_model` | ID5 서보 라벨 | 눈, 사진 | 1 | LD-1501MG 또는 LDX-218 | 일치 여부 |

허용오차 근거:

- **초음파 높이·위치 ±2 mm, 기울기 ±1°:** PR #248의 운반 높이 표는 원뿔 여유가 1–3 mm인 자세가 있다. 기울기 1°는 0.5 m 앞에서 원뿔 축을 9 mm 옮긴다. 센서 잡음 가정은 3 mm+1 %다.
- **yaw 축 ±2 mm:** v2(0)와 v3(48.2)의 차이가 가장 크다. 이 값은 짐을 든 채 회전할 때 grip 점, 짝 정렬, hand-eye 원점을 바꾼다.
- **링크 ±1 mm, 집게 끝 ±2 mm:** 링크 오차는 도달 거리에 그대로 더해진다. tile 파지 높이는 7 mm이고, 집게가 94 mm이면 IK가 풀리지 않는 자세가 생긴다(#248 11절).
- **카메라 ±2 mm, ±1°:** hand-eye 합격 기준이 바닥 위치 오차 2 cm다(`acceptance.held_out_hand_eye_position_mae_m_max`). 높이 13 cm에서 광축 1°는 바닥에서 약 1 cm다.
- **윤거·축거 ±2 mm:** 제자리 회전량이 (윤거+축거)/2에 반비례한다. 2 mm는 약 1 %다.
- **바퀴 지름 ±0.5 mm:** 1 mm 오차가 이동 거리 1.5 % 오차다.

### 1.2 초음파 위치(1–3, E1–E2)

1. 로봇을 기준지 위에 둔다. 팔은 곧게 세우거나 위로 접는다.
2. **높이:** 캘리퍼스 깊이봉을 바닥에 세우고, 위쪽 원통의 아랫면과 윗면 높이를 각각 잰다. 평균이 한 원통의 중심이다. 두 원통 모두 재고 평균을 적는다.
3. **앞 거리:** 직각자를 원통 망 앞면에 대고 기준지에 점을 찍는다. 원점에서 그 점까지 x 거리를 잰다.
4. **옆 위치:** 두 원통 중심을 기준지에 내려 찍고 중점을 표시한다. 중심선에서 떨어진 거리를 잰다.
5. **기울기:** 얇은 자를 두 원통 앞면에 평평하게 댄다. 자 위에 휴대폰을 세로로 붙이고 수평계 앱으로 수직에서 기운 각을 읽는다. 앞면이 위를 보면 +다. 휴대폰 자체 오차를 없애려면 180° 돌려 한 번 더 읽고 평균한다.
6. 사진: 옆에서 한 장, 앞에서 한 장. 자가 보이게 찍는다.

### 1.3 팔 yaw 축 위치(4, E3)

yaw 축은 덮여 있어 직접 보이지 않을 수 있다. 다음 방법을 쓴다.

1. 팔을 위로 곧게 세운다.
2. 흰 종이 띠를 어깨 브래킷 옆면에 붙이고 한 점을 표시한다.
3. yaw를 세 방향으로 돌린다. 예: `masterpi_control.py servo 6 1300 --duration 1.0`, `1500`, `1700`.
4. 매번 위에서 휴대폰으로 사진을 찍는다. 휴대폰을 같은 자리에 고정한다(책 더미 위, 1 m 이상 위, 2배 줌). 기준지 가장자리와 자가 사진에 보여야 한다.
5. 세 사진의 표시점 세 개로 원을 그리면 원 중심이 yaw 축이다. 노트북에서 사진을 겹쳐 좌표를 읽거나, 사진을 출력해 컴퍼스로 찾는다.
6. 간단한 확인: 혼 중앙 나사가 보이면 그 중심에서 직각자로 기준지에 점을 찍어 비교한다.

### 1.4 어깨 높이, 링크, 집게 끝(5–8, E4)

1. **곧게 선 자세를 만든다.** SDK 기준 곧게 선 자세는 "명목 펄스 1500 + 편차"다. ugrp1 편차는 `SERVO_DEVIATION = {3: 54, 4: 53, 5: 89, 6: 64}`(`harness/real_geometry.py`)다. 즉 servo 3=1554, 4=1553, 5=1589다. 한 번에 하나씩 `--duration 1.5`로 보낸다.
2. 링크가 실제로 수직인지 휴대폰 수평계로 확인하고 각도를 적는다(`straight_up_residual_deg`). 수직이 아니면 5.2절의 서보 각도표에서 바로잡는다.
3. **어깨 높이:** 직각자를 바닥에 세우고 ID5 혼 나사 중심 높이를 잰다.
4. **링크:** 0.3절 방법(바깥–바깥, 안–안 평균)으로 ID5–ID4, ID4–ID3 거리를 잰다. 이 값은 자세와 무관하다.
5. **집게 끝:** 집게를 닫는다(servo 1 = 1500). ID3 축에서 두 손가락 끝(주황 고무 끝)까지 공구 축 방향 거리를 잰다.
6. **전체 높이 검산:** 곧게 선 자세에서 바닥 → 닫힌 집게 끝 높이를 줄자로 잰다. `어깨 높이 + 상완 + 전완 + 집게 끝`과 3 mm 안에서 맞아야 한다. 안 맞으면 어느 관절이 굽었는지 사진으로 확인한다.

### 1.5 바퀴와 차체(11, 12, E5–E9)

1. 윤거는 좌우 바퀴의 폭 중앙끼리 잰다. 바퀴 바깥–바깥 거리에서 바퀴 폭 하나를 빼도 같다.
2. **바퀴 지름 굴리기 시험:** 로봇을 뒤집지 말고, 바퀴 하나의 롤러에 테이프 표시를 한다. 로봇을 손으로 천천히 앞으로 밀어 바퀴가 5바퀴 돌게 한다. 이동 거리 ÷ (5 × π)가 유효 지름이다. 메카넘 롤러 때문에 캘리퍼스 지름과 다를 수 있다. 둘 다 적는다(`wheel_diameter_mm`, `wheel_rolling_diameter_mm`).
3. 차체 길이는 짙은 회색 판의 앞 끝과 뒤 끝 사이다. 덮개·팔·바퀴는 넣지 않는다.

## 2. 초음파 센서 시험

PR #248 `docs/ultrasonic_range_sensor.md` 1절의 미확인 항목(반각/전체각, 정확도, 갱신 주기, 최소 거리, 무반사 값)과 두 로봇 간섭을 정한다.

### 2.1 준비

- 평평한 판: 30×30 cm 이상(폼보드나 두꺼운 골판지). 좁은 판: 폭 4 cm, 높이 30 cm 띠(또는 지름 2 cm 막대).
- 바닥에 줄자를 붙여 센서 앞면에서 거리 눈금을 만든다. 0점은 **송·수신기 앞면**이다.
- 두꺼운 담요 1장(무반사 시험용).
- Pi에서 `i2cdetect -y 1`을 실행해 `0x77`이 보이는지 확인한다.

### 2.2 기록 스크립트(Pi에서 실행)

Hiwonder SDK의 `HiwonderSDK/Sonar.py`를 쓴다. 공개 사본 기준 `Sonar().getDistance()`는 I2C 주소 0x77의 레지스터 0에서 2바이트를 읽어 **mm 정수**를 돌려준다. 5000 초과는 5000으로 자르고, 읽기 실패는 99999다. 모터·서보는 움직이지 않는다. SDK 위치가 다르면 `find ~ -name Sonar.py`로 찾는다.

아래를 Pi의 `~/sonar_log.py`로 저장한다. 저장소에는 넣지 않는 스케치다.

```python
#!/usr/bin/env python3
"""초음파 판독을 CSV에 덧붙인다. 모터·서보는 움직이지 않는다."""
import argparse, csv, os, sys, time

for root in (os.path.expanduser('~/MasterPi'), '/home/pi/MasterPi'):
    if os.path.isdir(os.path.join(root, 'HiwonderSDK')):
        sys.path.insert(0, root)
        break
try:
    import HiwonderSDK.Sonar as Sonar
    read_mm = Sonar.Sonar().getDistance
except Exception as exc:  # SDK가 없으면 같은 I2C 읽기를 직접 한다
    print('SDK import 실패, smbus2 직접 읽기:', exc)
    from smbus2 import SMBus, i2c_msg
    def read_mm():
        try:
            with SMBus(1) as bus:
                bus.i2c_rdwr(i2c_msg.write(0x77, [0]))
                msg = i2c_msg.read(0x77, 2)
                bus.i2c_rdwr(msg)
                return min(int.from_bytes(bytes(list(msg)), 'little'), 5000)
        except OSError:
            return 99999

ap = argparse.ArgumentParser()
ap.add_argument('--label', required=True)          # 예: face_d0500_a00
ap.add_argument('--true-mm', type=float)           # 줄자로 잰 거리(없으면 생략)
ap.add_argument('--n', type=int, default=50)       # 읽을 개수
ap.add_argument('--interval', type=float, default=0.10)  # 읽기 간격 s
ap.add_argument('--out', default='sonar_log.csv')
a = ap.parse_args()

new = not os.path.exists(a.out)
with open(a.out, 'a', newline='') as fh:
    w = csv.writer(fh)
    if new:
        w.writerow(['label', 'true_mm', 'i', 't_s', 'read_s', 'dist_mm', 'host'])
    t0 = time.monotonic()
    for i in range(a.n):
        t = time.monotonic()
        d = read_mm()
        r = time.monotonic() - t
        w.writerow([a.label, a.true_mm, i, f'{t - t0:.4f}', f'{r:.4f}', d, os.uname().nodename])
        time.sleep(max(0.0, a.interval - r))
print('saved', a.out)
```

사용 예: `python3 ~/sonar_log.py --label face_d0500_a00 --true-mm 500 --n 50`.

라벨 규칙: `<시험>_d<거리 mm 4자리>_<조건>`. 예: `cone_d1000_yL+130`, `inc_d0500_a35`.

### 2.3 시험 목록

모든 시험에서 로봇은 전원만 켜고 움직이지 않는다. 팔은 위로 접어 원뿔 밖에 둔다.

**U1. 거리 정확도와 잡음(약 30분)**

1. 평평한 판을 센서 정면에 수직으로 세운다.
2. 거리 50, 100, 200, 300, 500, 750, 1000, 1500, 2000, 3000 mm에서 각각 50회 읽는다(`--interval 0.1`).
3. 결과: 거리별 평균 편향, 표준편차, 99999·5000 비율. SIM 키 `noise_sigma0_m`, `noise_rel`, `dropout_prob`, `outlier_prob`에 쓴다.

**U2. 입사각(평평한 판, 약 30분)**

1. 판 중심을 센서 축 위, 거리 300, 500, 1000 mm에 둔다.
2. 판을 세로축으로 0°에서 60°까지 5°씩 돌린다. 판 아래에 인쇄한 각도기를 두고 맞춘다.
3. 각도마다 30회 읽는다.
4. 결과: "판 거리 ±30 mm 안의 판독이 80 % 이상"인 최대 각도. SIM은 약 35°에서 보이고 40°에서 놓친다고 가정한다(`incidence_sigma_deg`, `echo_threshold`).

**U3. 빔 원뿔 반각(좁은 판, 약 45분)**

1. 좁은 판(폭 4 cm)을 세로로 세운다. 판 면이 센서를 향하게 한다.
2. 거리 300, 500, 1000, 1500 mm에서, 판을 축에서 왼쪽으로 1 cm씩 옮긴다. 판독이 판 거리에서 벗어나는(다른 물체나 5000) 첫 위치를 찾는다. 경계 근처에서는 5 mm씩 옮긴다. 위치마다 20회 읽는다.
3. 오른쪽도 같이 한다.
4. 위쪽: 좁은 판을 가로로 눕혀 책 위에 올리고 높이를 1 cm씩 올린다. 아래쪽은 바닥 때문에 생략한다.
5. 반각 = atan(경계 옆 거리 ÷ 판 거리). 거리마다 적는다.
6. **판정:** 약 15°이면 "반각 15°(전체 30°)"다. 약 7.5°이면 "전체각 15°"다. #248 표(반각 15° vs 7.5°)에서 운반 높이가 0.110–0.140 m로 달라진다.
7. 주변 벽·가구가 원뿔 안에 들어오지 않게 넓은 곳에서 한다.

**U4. 최소 거리(약 15분)**

1. 판을 앞면에서 10, 20, 30, 40, 50, 70, 100 mm에 둔다. 각 30회 읽는다.
2. 판을 앞면에 거의 붙이고(5 mm 이하) 30회 읽는다.
3. 결과: 믿을 수 있는 최소 거리(`min_range_m`)와 그보다 가까울 때 나오는 값(0인지, 큰 값인지, 무작위인지).

**U5. 무반사 값(약 15분)**

1. 앞이 5 m 이상 빈 곳(긴 복도, 넓은 강당)에서 100회 읽는다. 조건 라벨 `noecho_open`.
2. 1 m 앞에 담요를 45°로 비스듬히 걸고 100회 읽는다. 라벨 `noecho_blanket`.
3. 결과: 반환값 분포(5000인지, 99999인지, 바닥 반사로 짧은 값이 나오는지). SIM은 둘 다 invalid로 처리하고 있다.

**U6. 갱신 주기(약 15분)**

1. 판을 500 mm에 두고 손으로 천천히(초당 약 5 cm) 앞뒤로 움직인다.
2. `--interval 0.005 --n 2000`으로 읽는다(약 10 s).
3. 노트북에서 값이 바뀐 시각 사이의 간격을 모아 중앙값을 낸다. 이 값이 모듈 갱신 주기다. 모든 읽기마다 값이 바뀌면 모듈이 읽을 때마다 측정하는 것이므로 `read_s` 중앙값을 주기로 본다.
4. 결과: `period_s`(SIM 가정 0.06 s), 한 번 읽기 시간 `read_s`.

**U7. 두 로봇 간섭(약 30분)**

1. 두 로봇을 마주 보게 둔다. 센서 앞면 사이 500 mm, 1000 mm.
2. 조건 세 가지를 차례로 한다. (a) B 전원 끔, (b) B 켬·대기, (c) B도 `sonar_log.py` 실행. A는 매번 `--interval 0.02 --n 500`.
3. 나란히 배치도 한다. 두 로봇을 옆으로 200 mm 떨어뜨리고 같은 벽(500 mm)을 본다. 같은 세 조건.
4. 결과: 조건 (a) 대비 짧은 값·invalid 비율. SIM `crosstalk` 옵션(기본 OFF)을 켤지 정한다. 두 Pi의 시계는 맞지 않으므로 시각 비교는 하지 않고 비율만 본다.

**U8. 장착 확인(약 10분)**

1. 판을 1000 mm에 두고, 판에 가로 띠를 붙여 높이 50–80 mm 구간만 반사하게 한다(띠 밖은 흡음재나 비스듬한 판).
2. 원뿔 축 높이가 1.2절 실측 높이와 맞는지 대략 확인한다. 이 시험은 선택이다.

모든 CSV를 `outputs/real-measurements/<로봇>-<날짜>/sonar/`에 복사하고 sha256을 적는다.

## 3. 손목 카메라

### 3.1 카메라 모델(10)

1. Pi에서 `lsusb`, `v4l2-ctl --list-devices`, `v4l2-ctl -d /dev/video0 --list-formats-ext`를 실행해 출력을 저장한다.
2. 카메라 보드 뒷면 라벨을 사진으로 찍는다.
3. 기록: 모델명, USB vendor:product ID, 지원 해상도. 순정 HBVCAM-V2101(640×480, 170°)인지 icspring 어안인지 적는다.

### 3.2 내부 파라미터(OpenCV fisheye)

현재 SIM은 2026-08-30 ugrp1 값(`sim/masterpi_camera_profile.py`: fx 619.5, fy 622.2, cx 287.7, cy 218.7, D = −0.020, −0.171, −0.257, 0.965)을 쓴다. D의 네 번째 값이 커서 과적합이 의심된다. 다시 재고 비교한다.

1. **보드 인쇄:** 체커보드를 A4에 **100 % 배율**로 인쇄한다. 권장은 내부 코너 9×6(칸 10×7), 칸 25 mm다. OpenCV 문서의 패턴 생성 도구를 쓰거나, Hiwonder SDK 보정 설정(내부 코너 7×7, 칸 21 mm)을 써도 된다.
2. 캘리퍼스로 8칸 길이를 재고 8로 나눠 실제 칸 크기를 적는다. 프린터가 크기를 바꾸는 경우가 많다.
3. 보드를 평평한 판에 붙인다. 휘면 안 된다.
4. **촬영:** 실제 실행과 **같은 경로·해상도**로 찍는다. 우리 코드는 `http://127.0.0.1:8080/?action=snapshot` 또는 `/dev/video0` 640×480을 쓴다(`scripts/red_block/camera.py`). 다른 프로그램이 카메라를 잡고 있으면 `sudo fuser /dev/video0`로 확인한다.
5. 30–40장을 찍는다. 조건:
   - 보드가 화면 네 모서리와 가장자리에 각각 여러 번 오게 한다. 어안 왜곡은 가장자리에서 크다.
   - 보드를 좌우·상하로 0–45° 기울인다.
   - 거리 15–60 cm. 파지할 때 가까운 거리가 중요하다.
   - 흔들림 없이, 조명은 고르게.
6. Pi 촬영 스케치(엔터를 칠 때마다 한 장 저장):

```python
import cv2, time, pathlib
out = pathlib.Path('~/calib_imgs').expanduser(); out.mkdir(exist_ok=True)
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
i = 0
while input('Enter=촬영, q=끝: ') != 'q':
    for _ in range(5): cap.read()          # 오래된 버퍼 버리기
    ok, img = cap.read()
    if ok:
        cv2.imwrite(str(out / f'{i:03d}.png'), img); print(i, img.shape); i += 1
cap.release()
```

7. **노트북 계산 스케치:**

```python
import cv2, glob, json, numpy as np
COLS, ROWS, SQ_MM = 9, 6, 25.0          # 내부 코너, 실측 칸 크기
objp = np.zeros((1, COLS * ROWS, 3), np.float64)
objp[0, :, :2] = np.mgrid[0:COLS, 0:ROWS].T.reshape(-1, 2) * SQ_MM / 1000.0
obj, img, names = [], [], []
for f in sorted(glob.glob('calib_imgs/*.png')):
    g = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
    ok, c = cv2.findChessboardCorners(g, (COLS, ROWS),
        cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok: continue
    c = cv2.cornerSubPix(g, c, (3, 3), (-1, -1),
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6))
    obj.append(objp); img.append(c.reshape(1, -1, 2)); names.append(f)
K, D = np.zeros((3, 3)), np.zeros((4, 1))
flags = (cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND
         | cv2.fisheye.CALIB_FIX_SKEW)
rms, K, D, _, _ = cv2.fisheye.calibrate(obj, img, g.shape[::-1], K, D, flags=flags,
    criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6))
print(json.dumps({'rms_px': rms, 'K': K.tolist(), 'D': D.ravel().tolist(),
                  'n_images': len(names), 'size': g.shape[::-1]}, indent=2))
```

8. `CALIB_CHECK_COND` 오류가 나면 오류 난 사진을 빼고 다시 한다.
9. **검증:** 사진을 3분의 2(적합)와 3분의 1(검증)로 나눈다. 적합한 K, D로 검증 사진마다 `cv2.solvePnP` 후 재투영 오차를 낸다. 합격 기준: 적합 RMS 0.5 px 이하가 좋고 1.0 px 이하면 쓴다. 검증 재투영 평균이 적합 RMS의 2배를 넘으면 과적합이다.
10. 템플릿 `wrist_camera.intrinsics`에 K, D, RMS, 사진 수, 해상도를 적는다.

### 3.3 렌즈 자세(손목 기준)

SIM 값은 `CAMERA_LOCAL_POS_M = (0.0670, 0.0, 0.0136)`(gripper body 기준)이고 광축은 공구 축보다 약 7.5° 아래를 본다. 이 값은 한 자세의 사진에서 적합한 값이라 검증이 없다.

1. 팔을 곧게 세운 자세(1.4절)로 둔다. 공구 축이 수직이 된다.
2. **공구 축 방향 거리:** ID3 축에서 렌즈 앞면 중심까지, 공구 축과 나란한 거리를 캘리퍼스로 잰다(`camera_lens_along_mm`).
3. **공구 축에서 떨어진 거리:** ID3 축과 닫힌 집게 끝을 잇는 선에서 렌즈 광축까지의 수직 거리(`camera_lens_up_mm`). 렌즈가 집게보다 어느 쪽에 있는지 사진에 표시한다.
4. **옆 거리:** 팔 중심면에서 렌즈 중심까지(`camera_lens_lateral_mm`).
5. **광축 각도:** 휴대폰을 팔 옆 1 m 거리에 두고 2배 줌으로 옆 사진을 찍는다. 렌즈 경통 방향과 집게 손가락 방향 사이 각을 노트북 이미지 도구로 잰다(`camera_pitch_deg`, 집게보다 아래를 보면 −). 휴대폰 수평계로 렌즈 앞면 기울기를 재서 교차 확인한다.
6. **hand-eye로 확정:** 캘리퍼스 값은 초기값이다. 확정은 기존 `calibration/masterpi/hand_eye_trials.jsonl` 24행(적합 12, 검증 12)으로 한다.
   - 바닥에 테이프로 격자를 만든다. 원점은 **yaw 축을 바닥에 내린 점**이다(1.3절). x는 로봇 앞, y는 왼쪽이다.
   - 각 행의 서보 자세(servo 3/4/5/6 펄스)로 팔을 움직인다. 3 cm 빨간 블록을 카메라에 보이는 격자 위치에 놓고 사진을 찍는다.
   - 블록 중심 x, y를 줄자로 재서 `true_x_m`, `true_y_m`에 적는다. `nx`, `bottom_ny`(블록 아랫변 중앙의 정규화 픽셀)는 에이전트가 사진에서 뽑아도 된다. 사진 원본을 반드시 남긴다.
   - `python3 scripts/benchmarks/fit_masterpi_hand_eye.py calibration/masterpi/hand_eye_trials.jsonl`로 `camera_link_cm`, `camera_z_offset_cm`, `camera_pitch_offset_deg`, `servo6_center_pwm`을 적합한다. 합격 기준은 검증 위치 오차 2 cm 이하다.

### 3.4 팔 회전(pan, servo 6) PWM → 각도, ±90° 포함

측면 파지(9/9 실험)는 SIM에서 servo 6을 2500 / 500 펄스로 보내 ±90°로 돌렸다. 실물이 그 각에 닿는지, 몇 펄스가 필요한지 모른다.

1. 로봇을 상자 위에 올린다. 팔을 위로 접는다(곧게 선 자세).
2. yaw 축 위에 인쇄한 360° 각도기 종이를 로봇 윗면에 붙인다. 0°를 로봇 앞(x)에 맞춘다. 또는 1.3절처럼 위에서 사진을 찍는다.
3. 집게 방향을 가리키는 막대(빨대)를 집게에 테이프로 붙인다.
4. 500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500 펄스를 **올라가는 순서로** 보낸다. 각각 `--duration 1.5`, 2초 기다린 뒤 각도를 읽는다.
5. 같은 펄스를 **내려가는 순서로** 다시 한다. 두 값의 차이가 되돌림(히스테리시스)이다.
6. 끝 펄스에서 서보가 멈춤 소리(윙윙)를 내거나 떨면 바로 1500으로 되돌리고 그 값을 적는다.
7. 결과(`servo_angle_tables.servo6`): 펄스별 각도(왼쪽 +). 예상은 1500 → 0°, 펄스 11.11개당 1°, 큰 펄스 = 왼쪽(`scripts/red_block/plan.py`의 회전 방향 규칙)이다. 0°가 되는 펄스를 `servo6_center_pwm_caliper`로 적는다. **+90°와 −90°에 필요한 펄스**를 선형 보간으로 구해 `pan_pwm_for_plus90`, `pan_pwm_for_minus90`에 적는다. 허용오차 ±2°(grip 반경 0.155 m에서 5 mm).

## 4. 주행

### 4.1 준비

- 바닥: 실제 경기장을 만들 바닥에서 한다. 재질과 사진을 기록한다(`floor.material`).
- 로봇 몸체 앞·뒤 끝 중앙에 테이프로 표시점 두 개를 붙인다. 두 점 거리를 잰다.
- 바닥에 시작 표시(두 점의 위치)를 테이프로 붙인다.
- 방법은 두 가지다.
  - **간이:** 시작 전후 두 표시점의 바닥 위치를 줄자로 잰다. dx, dy는 두 점 중점의 이동, dyaw는 두 점을 잇는 선의 각 변화다.
  - **정식:** 기존 `calibration/masterpi/chassis_trials.jsonl`과 `analyze_masterpi_overhead_video.py`(ArUco 두 장, 휴대폰을 천장 방향으로 고정 촬영)를 쓴다. peak speed와 정지 거리까지 나온다.
- 배터리 전압을 블록마다 `masterpi_control.py probe`로 기록한다. 첫 블록보다 0.3 V 넘게 떨어지면 충전한 뒤 계속한다.

### 4.2 시험

명령은 Pi에서 `python3 <배포 경로>/masterpi_control.py drive <방향> --speed <속도> --duration <초>`다. 배포 경로는 [네트워크 런북](masterpi_network_runbook.md)을 따른다. 한 번 움직이고, 재고, 제자리로 옮긴 뒤 다음을 한다.

| 시험 | 방향 | 속도 | 시간 s | 반복 |
|---|---|---|---|---|
| D1 직진 | forward, backward | 35, 40 | 0.5, 1.0, 2.0 | 3 |
| D2 옆 이동 | left, right | 40, 65 | 0.5, 1.0, 2.0 | 3 |
| D3 제자리 회전 | rotate-left, rotate-right | 35, 40 | 0.5, 1.0 | 3 |
| D4 하중 | forward, left, rotate-left | 35(옆은 65) | 1.0 | 3 × 하중 3종 |

- D4 하중: 0 kg, 0.2 kg, 0.3 kg(`long_beam` 절반에 해당하는 무게 포함). 두 가지로 싣는다. (a) 차체 위 중앙, (b) 집게로 들고 운반 자세. (b)는 떨어뜨려도 안전한 물체로 한다.
- 기존 `chassis_trials.jsonl`에는 속도 31 행이 있다. 현재 CLI 최소 속도는 35라서 실행되지 않는다. 그 행은 건너뛰고 `notes`에 "below MIN_EFFECTIVE_WHEEL_SPEED 35"라고 쓴다.

### 4.3 결과

- 시간별 이동 거리에 직선을 맞춘다. 기울기가 정상 속도(m/s)이고, 절편이 가속·정지 지연이다. 속도·방향별로 `drive.speed_fit`에 적는다.
- 직진 중 옆으로 샌 거리와 yaw 변화도 적는다(메카넘 미끄러짐).
- 연구 코드는 `SPEED_M_S = 0.06`, 운반 odometry 배율 `CARRY_ODOM_SCALE = {'axial': 0.772, 'lateral': 0.697}`(`scripts/study_owncam_pair_beam.py`)을 쓴다. 이 배율은 SIM 정답으로 정한 값이다. 실물 값을 `drive.odometry_scale`에 따로 적는다. SIM 값을 덮어쓰지 않는다.
- 회전: 명령 시간당 회전각(°/s)을 적는다. 윤거·축거 실측값과 함께 바퀴 미끄러짐을 계산하는 데 쓴다.

## 5. 팔과 집게

### 5.1 링크 길이

1.4절에서 잰다. 여기서는 다시 재지 않는다.

### 5.2 관절 서보 PWM → 각도(servo 3, 4, 5)

1. 로봇을 상자 위에 올린다. 곧게 선 자세(1.4절)에서 시작한다.
2. 한 관절씩 움직인다. 기준 펄스에서 −500, −250, −100, 0, +100, +250, +500을 보낸다. 팔이 몸체나 책상에 닿을 것 같으면 그 단계는 건너뛴다. 이미 쓰던 안전 자세 범위는 `scripts/red_block/poses.py`(예: servo 3 = 650–960, 4 = 2230–2410, 5 = 1215–1920)다.
3. 각 자세에서 휴대폰 수평계 앱을 움직인 링크의 평평한 옆판에 대고 각도를 읽는다. 수직 0°, 앞으로 숙이면 +로 적는다.
4. 올라가는 순서와 내려가는 순서 모두 한다.
5. 결과(`servo_angle_tables.servo3/4/5`): 펄스와 각도 표. 기울기(펄스/도)와 0° 펄스를 에이전트가 적합한다. SDK 가정은 11.11 펄스/도(`PULSE_PER_DEGREE = 2000/180`), 0° 펄스 = 1500 + 편차다. 허용오차는 끝점 3°(`held_out_servo_endpoint_mae_deg_max`)다.
6. **settle 시간(선택):** 휴대폰 슬로모션(240 fps)으로 찍고, 명령부터 멈출 때까지 프레임을 센다. 기존 `servo_trials.jsonl` 60행의 `measured_delta_deg`, `settle_time_s`에 적고 `fit_masterpi_servo.py`로 deadband와 속도를 적합한다.

### 5.3 집게(servo 1) 열림 폭

1. 팔을 곧게 선 자세로 둔다.
2. servo 1을 1500(닫힘), 1600, 1700, 1800, 1900, 2000(열림)으로 보낸다. 이 범위 밖은 보내지 않는다.
3. 각 펄스에서 두 손가락 **끝 안쪽** 간격을 캘리퍼스 안쪽 턱으로 잰다. 고무 끝 바깥 폭(`finger_outer_span_mm`)도 잰다.
4. 3 cm 블록을 열린 집게 사이에 두고 1500까지 50씩 닫는다. 블록이 움직이지 않게 잡히기 시작하는 펄스를 적는다(`gripper_contact_pwm_30mm`). 코드의 "잡힘" 기준은 1700 이하(`GRIPPER_CLOSED_MAX_PULSE`)다.
5. 손가락 고무 끝 길이·폭·두께를 캘리퍼스로 잰다(치수도 끝 길이 14.3 mm, 손가락 판 3.7 mm).
6. 결과(`gripper`): 펄스별 간격 표. 예상: 치수도 열림 외곽 46.7 mm. 허용오차 ±2 mm.

### 5.4 블록·바닥 마찰(정적 파일용)

1. 3 cm 블록과 운반 막대의 질량을 잰다(저울이 있으면).
2. 경기장 바닥재 한 장을 판에 올리고 블록을 얹는다. 판 한쪽을 천천히 들어 블록이 미끄러지기 시작하는 각도를 휴대폰 수평계로 잰다. 정지 마찰계수 = tan(각도). 5회 반복한다.
3. `calibration/masterpi/static_measurements.json`의 `block_mass_kg`, `block_floor_friction`에 적는다.

## 6. 기록 템플릿

템플릿은 [`configs/real_measurements_template.json`](../configs/real_measurements_template.json)이다.

- 모든 측정값은 `null`로 시작한다. 각 항목에 `unit`, `expected`, `tolerance`, `code_constant`(나중에 바꿀 코드 상수)가 있다.
- **정적 치수의 키는 PR #249 `sim/masterpi_geometry_v3.py`의 `MEASURE_ON_ROBOT` 키와 같다.** 단, `camera_lens_offset_mm`은 `camera_lens_along_mm`, `camera_lens_up_mm`, `camera_lens_lateral_mm`, `camera_pitch_deg` 네 키로 나눴다. 추가 항목(E1–E10)은 새 키다. 사람이 읽기 쉽게 mm·도로 적는다. 코드 단위(m)로의 변환은 에이전트가 한다(`code_scale`).
- `ultrasonic.spec` 키는 PR #248 `harness/ultrasonic_model.py`의 `UltrasonicSpec` 필드와 같다(`mount_z_floor_m`, `half_angle_deg`, `period_s` 등). 이 부분은 시험 결과를 요약한 값이라 코드 단위(m, s)로 적는다.
- `dynamics_manifest_static`의 키는 `apply_masterpi_static_measurements.py`가 읽는 키(`wheel_radius_m`, `wheelbase_m`, `track_m`, `block_mass_kg`, `block_floor_friction`)와 같다.
- `wrist_camera.intrinsics`의 키는 `sim/masterpi_camera_profile.py` 상수(`CAMERA_FX_PX` 등)와 같다.
- 시행 단위 자료(서보 계단 응답, hand-eye, 주행)는 `calibration/masterpi/*.jsonl`에 적고, 템플릿에는 파일 경로와 sha256만 적는다.

채운 뒤 할 일:

1. 파일을 `calibration/masterpi/real_measurements_<로봇>_<날짜>.json`으로 커밋하고 PR을 연다(#214 참조).
2. 사진·CSV는 `outputs/real-measurements/`에만 둔다. sha256을 `raw_files`에 적는다.
3. 에이전트가 값과 허용오차를 비교해 바꿀 상수 목록을 만든다. v2 번들 파일은 직접 고치지 않고 새 버전으로 반영한다([실행 버전 관리](execution_versioning.md)).

## 7. 작업 순서

결정에 영향이 큰 것부터 한다. 1–5번은 한나절(약 3시간)이면 끝난다.

| 순서 | 항목 | 절 | 시간 | 이 값으로 정해지는 것 |
|---|---|---|---|---|
| 1 | 초음파 높이·앞 거리·기울기·옆 위치 | 1.2 | 20분 | #248 장착값, 운반 높이(여유 1–3 mm) |
| 2 | 팔 yaw 축 앞 거리 | 1.3 | 30분 | v3 `drawing_layout_proposal` 채택 여부(0 vs 48 mm), 짝 정렬, hand-eye 원점 |
| 3 | 어깨 높이, 링크 3개, 전체 높이 검산 | 1.4 | 30분 | SDK 65 mm vs 치수도 57.7 mm, 집게 94 vs 100 mm, IK·파지 자세 |
| 4 | 카메라 모델, 렌즈 위치·각도 | 3.1, 3.3(1–5) | 30분 | 손목 카메라 자세(67/13.6 적합값 vs 53/28), 시각 모델 |
| 5 | 초음파 빔 반각 | 2.3 U3 | 45분 | 반각 15° vs 7.5°, 운반 높이 표 |
| 6 | pan ±90° 펄스 | 3.4 | 20분 | 측면 파지 가능 여부 |
| 7 | 바퀴·차체 치수, 서보 라벨, 질량 | 1.5 | 30분 | 충돌 형상, 회전 odometry |
| 8 | 초음파 U1, U2, U4, U5, U6 | 2.3 | 1.5시간 | 잡음·주기·무반사 모델 |
| 9 | 카메라 내부 파라미터 | 3.2 | 1시간 | 어안 K, D 재확인 |
| 10 | 관절 서보 각도표, 집게 폭 | 5.2, 5.3 | 1시간 | FK·집게 모델 |
| 11 | 주행 D1–D4 | 4 | 2시간 | 명령 odometry 배율, 하중 영향 |
| 12 | 두 로봇 간섭 U7, 마찰 | 2.3, 5.4 | 45분 | crosstalk 옵션, 접촉 모델 |
| 13 | hand-eye 24행 | 3.3(6) | 2시간 | 카메라 자세 확정(검증 오차 2 cm) |

두 번째 로봇은 1–7번만 먼저 하고 첫 로봇과 다른 값만 나머지를 한다.

## 8. 남은 문제

- 이 절차는 아직 실물에서 해 보지 않았다. 첫 측정 뒤 막히는 단계를 고친다.
- 초음파 모듈의 발사 시점(연속 측정인지 요청 시 측정인지)은 U6 결과로만 추정한다. 펌웨어 문서는 찾지 못했다.
- pan 끝 각도에서 서보를 오래 멈춤 상태로 두면 서보가 상할 수 있다. 3.4절 6번을 지킨다.
- 공동 운반 중 odometry(두 로봇이 막대를 함께 든 상태)는 이 절차의 범위 밖이다. #214 H3에서 따로 잰다.

## 참고 자료

- Hiwonder MasterPi 제품 페이지(사양표, Dimensional Diagram): <https://www.hiwonder.com/products/masterpi>. © Hiwonder. 수치만 인용했다. 사용: 전체 치수, 바퀴 65/30 mm, 덮개 101 mm, 어깨–끝 215 mm.
- Hiwonder MasterPi 공식 문서(1장 준비·조립): <https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html>. 사용: 초음파·팔 받침 상자 조립 위치.
- Hiwonder 발광 초음파 모듈: <https://www.hiwonder.com/products/glowing-ultrasonic-sensor>, wiki <https://wiki.hiwonder.com/projects/Glowing-Ultrasonic-Sensor/en/latest/>. 사용: 측정 범위 2–400 cm, 측정각 15°(반각/전체각 미표기), 45.6×28.5 mm.
- Hiwonder TonyPi SDK `Sonar.py`(공식, 같은 I2C 모듈): <https://github.com/Hiwonder/TonyPi/blob/main/HiwonderSDK/hiwonder/Sonar.py>. 사용: 주소 0x77, 레지스터 0, mm 단위.
- MasterPi SDK 공개 사본(SquirrelRobotics, 라이선스 없음, 코드 재사용 없이 동작만 확인): <https://github.com/SquirrelRobotics/MasterPi/tree/98b85647eab1614f3fcce28aba959c679cfc72eb>
  - `HiwonderSDK/Sonar.py`: `getDistance()`가 5000에서 자르고 실패 시 99999.
  - `Functions/Avoidance.py`: `Sonar.Sonar().getDistance() / 10.0`으로 cm 사용.
  - `HiwonderSDK/Board.py`: 제어 보드 I2C 0x7A, PWM 서보 펄스 500–2500, 각도 = (펄스 − 500) × 0.09.
  - `HiwonderSDK/mecanum.py`: 기본값 a = 67 mm, b = 59 mm, 바퀴 지름 65 mm(반 윤거·반 축거로 보임).
  - `ArmIK/InverseKinematics.py`: l2 6.50, l3 6.20, l4 10.00 cm.
  - `CameraCalibration/CalibrationConfig.py`: 체커보드 내부 코너 7×7, 칸 2.1 cm, pinhole `cv2.calibrateCamera` 사용. 우리는 어안 모델이 필요하므로 fisheye 함수로 바꾼다.
- OpenCV fisheye 모듈: <https://docs.opencv.org/4.x/db/d58/group__calib3d__fisheye.html>. 사용: `cv2.fisheye.calibrate`, 플래그, D 4개 계수.
- OpenCV 카메라 보정 튜토리얼: <https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html>. 사용: 코너 검출, `cornerSubPix`, 재투영 오차.
- OpenCV 보정 패턴 만들기: <https://docs.opencv.org/4.x/da/d0d/tutorial_camera_calibration_pattern.html>. 사용: 체커보드 인쇄.
- OpenCV ArUco 검출: <https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html>. 사용: 천장 영상 주행 측정(기존 스크립트).
- HC-SR04 데이터시트: <https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf>. 사용: #248의 정확도 3 mm, 주기 60 ms 가정의 출처. 실측으로 바꿀 대상.
- ROS REP 103(좌표 규약): <https://www.ros.org/reps/rep-0103.html>. 사용: x 앞, y 왼쪽, z 위.
- 저장소 내부: PR #249(`sim/masterpi_geometry_v3.py` `MEASURE_ON_ROBOT`), PR #248(`docs/ultrasonic_range_sensor.md`, `harness/ultrasonic_model.py`), `sim/masterpi_geometry.py`, `harness/real_geometry.py`, `sim/masterpi_camera_profile.py`, `sim/masterpi_dynamics_calibration.json`, `calibration/masterpi/README.md`, `experiments/2026-09-09-side-grasp/README.md`.
