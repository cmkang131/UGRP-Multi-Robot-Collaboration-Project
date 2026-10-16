# mapbuild7 후보 API (기본 off)

실행 소스 `7a16faf44`의 API다. 명령 FK 계산 가능과 실제 적재 카메라·전역 등록·운반 관문 통과는 별개다. 실제 적재 자격과 전체 경로는 아직 검증 중이다. `8dfcd3064` 이전 전역 정합의 거리별 픽셀 분산 누락은 R1 중단 사유이며 해당 정합 점수는 채택 근거로 쓰지 않는다.

```python
from harness.servo_camera_fk import transform_from_commands, CARRY_OPTION
camera, reason = transform_from_commands(own_servo_pwm, camera_pose=CARRY_OPTION)
# CARRY_OPTION == 'servo_fk_carry_v1'
# 원래 servo_fk_v1의 grip<=1600 거부는 그대로다.

from harness.mapbuild_camera import CommandCamera
camera_stream = CommandCamera(camera_pose=CARRY_OPTION)
flow, scan = camera_stream.observe(t_sim, previous_own_rgb, own_rgb,
                                   own_servo_pwm, colour_boundary_state)
# 기존 K/D, 실기/고정 기구 치수, 자기 명령만. 실제 관절·자세·TOP 없음.
# 기존 .25/2.25 SIM초 무하중/적재 명령 정착 간격을 승계한다.
# flow unknown이면 정지로 바꾸지 않고 기존 명령 예측을 쓴다.

from harness.mapbuild_static_registration import StaticRegistration, OPTION
reg = StaticRegistration(authored_static_map, option=OPTION)
result = reg.register(own_gauge_segments, camera_origins=source_camera_origins)
# OPTION == 'mapbuild_static_csm_v1'
# segments: [N,2,2]; source_camera_origins: [N,2], 각 선분을 본 카메라 원점.
# 둘 다 SAME own-map gauge, 미터 단위. 원점을 잃으면 명시적 거부다.
# result['static_from_own']는 accepted 때만 SE(2) [x,y,yaw]이며,
# static_pose = compose(static_from_own, own_pose)로 왼쪽에서 합성한다.
# 척도는 항상 1. 모호·관측 불충분이면 None이며 spawn/평가 좌표 대체 금지.
```

전역 정합은 기존 CSM 거리장·Huber 비용·.05m/1° 격자·센서 분산·관측 가능성·겹침/잔차/모드 문턱을 쓴다. 전역 SE(2)를 내보내려면 세 축이 모두 관측 가능해야 한다. 모든 격자 후보를 검사하고, 메모리 묶음1024는 수용 상수나 탐색 중단 예산이 아니다. wall초 상한·top 카메라·정답 시작 위치·척도 fitting은 없다.

`servo_fk_carry_v1`은 집게 슬라이더가 카메라 기구 체인에 없다는 고정 구조를 사용한다. 집게 PWM은 자기 차체/손가락 투영 가림에는 계속 반영한다. 하중 처짐·차체 roll/pitch·서보 도달을 측정하지 않으며 `servo_fk_nominal_carry_commands` 이유로 구분한다. 기존 코드의 함수 전역을 바꾸지 않고 의존성을 바인딩하므로 다른 작업자의 기본 경로에는 적용하지 않는다.

원격에서 원본은 gcp5에 두고, 호출자는 실제 영상의 필수 지점 오차 관문을 별도로 통과해야 한다. API 존재나 비물리 시험을 학생·실제 운반 성공으로 승계하지 않는다.
