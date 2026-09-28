# MasterPi 물리 모델 v3

2026-09-28. Hiwonder 공식 치수도와 SDK 팔 치수로 MasterPi의 외관과 물리 형상을 다시 만들었다. 값과 출처는 `sim/masterpi_geometry_v3.py`의 `PHYSICAL_V3`(한 벌의 파라미터)에 있다. 조사 기록, SDK와 치수도 판정, 전원 연결 후 검증 계획은 [실험 기록](../experiments/2026-09-28-masterpi-visual-v3/README.md)에 있다.

## 사용

```python
from sim.masterpi_model_v3 import build_v3_xml, build_v2_appearance_xml, SONAR_MOUNT_V3
from sim.masterpi_geometry_v3 import PHYSICAL_V3
xml = build_v3_xml()                          # v3 물리 모델(치수도 형상 + SDK 팔)
xml = build_v3_xml({"track_m": .131})         # 보정값·명시값은 치수도보다 우선
measured = PHYSICAL_V3.with_measurements(version="masterpi-physical-ugrp1-YYYYMMDD", note="줄자", upper_arm_m=.0648)
xml = build_v3_xml(geometry=measured)         # 실측값으로 교체(real_measured 태그)
xml = build_v2_appearance_xml()               # 진단용: v2 물리 그대로 + v3 외관
```

- v3가 바꾸는 것: 팔 yaw 축(전방 48.2 mm, 높이 93.0 mm), 어깨 축 높이 127.7 mm, 상완 65.0 mm와 전완 62.0 mm, 손가락 접촉 proxy와 `grip_site`(손목 축에서 86.85 mm), 바퀴 트랙 129.9 mm·축간 118.8 mm·폭 30 mm, 차대·덮개·팔 받침 상자·yaw 서보·받침대·초음파 충돌 proxy, 초음파 사이트.
- v2와 같은 것: 질량·관성, actuator·관절 범위·감쇠, robot_cam 자세와 내부 파라미터(REAL 적합, 집게 기준), `sim/masterpi_dynamics_calibration.json` 적용 경로.
- 시각 geom은 `v3_` 접두사, `mass=0`, `contype=0`, `conaffinity=0`이다. 카메라 하드웨어 시각 geom은 group 5라 robot_cam 영상에 나오지 않는다.
- 초음파: 사이트 `v3_ultrasonic_site`, 송수신면 전방 88.0 mm, 높이 61.7 mm, 수평.

## 제어기 층

- 실제 로봇은 Hiwonder SDK IK를 쓴다. SDK 상수(l1 9.30, l2 6.50, l3 6.20, l4 10.00 cm)는 `harness/visual_arm.py`에 그대로 둔다.
- 시뮬레이터는 물리 팔을 모델링한다. 남는 차이는 `CONTROLLER_VS_PHYSICAL_V3` 표에 둔다. 어깨 높이는 125.5 대 127.7 mm이고, 도구점은 100 대 86.85 mm(닫힌 끝 94.0 mm)이다.
- 팔 장착 위치(48.2 mm)를 제어기 좌표 변환에 넣는 작업은 아직 이 브랜치에 반영하지 않았다. 패치와 할 일은 실험 기록에 있다.

## 렌더

```bash
.venv-sim/bin/python scripts/render_masterpi_model_v3.py --out outputs/masterpi-model-v3 --reference-dir outputs/masterpi-visual-v3/reference
```

- `mj_forward`와 오프스크린 렌더만 쓴다. 공식 이미지는 커밋하지 않는다.

## 상태

- `build_v3_xml`은 물리 모델로 완성했다. 연구 장면(`sim/multi_masterpi_production.py`)의 기본 모델 전환, 제어기 장착 보정, 새 번들 ID(v70 RGB, v71 zone study 예정)는 실험 기록의 할 일 목록에 있다.
