# 확인한 출처 (2026-10-07)

1. [Hiwonder MasterPi 공식 구성](https://www.hiwonder.com.cn/product-detail/MasterPi.html):
   LD-1501MG/LFD-01M. 관절별 배치는 `sim/masterpi_geometry_v3.py:136–155`의 기존 도면 해석.
   실물 개체의 라벨 확인은 없으며 다른 세대 servo 사양으로 단정하지 않는다.
2. [LD-1501MG 공식 제품](https://www.hiwonder.com.cn/product-detail/LD-1501MG-Single-Shaft-Digital-Servo.html),
   [공식 파라미터 이미지](https://store.hiwonder.com.cn/2020/06/20/1501MG.png):
   0.3° 정밀도,13/15/17kgf·cm @6/6.5/7.4V,500–2500µs=0–180°.
   이미지 직접 확인. 정밀도는 하중별 처짐/기계 backlash/입력 deadband의 별도 보증이 아니다.
3. [LFD-01M 공식 제품](https://www.hiwonder.com/products/lfd-01m):
   1.5/1.8kgf·cm @4.8/6V. 수치 deadband/강성 미공개. 이를 채우려고 LX-15D 등 다른 제품 사양을 쓰지 않는다.
4. [MuJoCo position actuator](https://mujoco.readthedocs.io/en/stable/XMLreference.html#actuator-position):
   kp position gain·kv damping, dampratio=1 critical damping, reference inertia 기반이며 passive damping 별도.
   implicitfast 권고를 따르며 기존 integrator를 확인한다. torque clamp는 그대로 유효하다.
5. [Klimchik et al., stiffness identification](https://arxiv.org/abs/1311.6810):
   탄성 파라미터 식별은 구성별 변위/하중 측정이 필요하다. 이번 kp는 그런 실물 식별이 아니다.
6. PR406 v122 원본 `45b0c173d34f53c2016e2560cdc70c9a908a8325`:
   [pulse predictor](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/45b0c173d34f53c2016e2560cdc70c9a908a8325/harness/zone_solo_cyan_pulse_cal.py),
   [고정 calibration](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/45b0c173d34f53c2016e2560cdc70c9a908a8325/configs/s2_motion_v7_pulse_cal_v1.json).
   profile_key/response 및 초기 pulse body frame 적분과 stopping tail을 재사용한다.
   불확실성은 원 prediction_variance·시간분할을 사용한다. 모델은 기존 DEV fit이며 새 강성에서 재평가한다.

공개 source는 근거로 읽었고 외부 라이브러리/venv 추가0. 제조사 원 이미지/해시는 raw references에 보존.
