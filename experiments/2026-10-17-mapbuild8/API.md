# mapbuild8 후보 API — 기본 off, 실제 경로 관문과 구분

구현 소스 `2f7cfacca`(PR #556, `codex/mapbuild1`). 데이터·결과 문서 커밋과 실제 실행 소스 SHA는 별도로 기록한다. 아직 실제 운반/LLM E2E 인수를 뜻하지 않는다. mapbuild7 API는 기본 호출을 유지한다.

```python
from harness.servo_camera_fk import CARRY_OPTION
from harness.mapbuild_camera import CommandCamera
from harness.selfmap_map_correction import SelfMapCorrection, OPTION
from harness.e2e_rgb_vo import compose

camera = CommandCamera(camera_pose=CARRY_OPTION)  # servo_fk_carry_v1
mapper = SelfMapCorrection(authored_static_map, option=OPTION)
# OPTION == 'selfmap_map_correction_v1'

flow, scan = camera.observe(t_sim, previous_own_rgb, own_rgb, own_pwm, colour_state)
own_pose, event = mapper.step(t_sim, frame_id, own_command_delta,
                             own_command_covariance, flow, scan)
# own_pose는 해당 로봇 시작 gauge의 차체 중심 [m,m,rad]. 척도1.
# 관측 불가 = 명령 예측 유지. 정지/성공으로 바꾸지 않는다.

if mapper.static_from_own is None:
    registration = mapper.initialize_static()  # 자기 관측만으로 초기 전역 등록
    # accepted 때만 mapper.static_from_own이 생긴다.
if mapper.static_from_own is not None:
    static_pose = compose(mapper.static_from_own, own_pose)
```

입력은 자기 RGB·자기 발행 PWM/바퀴 명령·고정 기구/K/D·허용 정적 지도다. 제어기에 평가 파일, spawn, 측정 관절, 실제 카메라 자세, 접촉/성공 판정을 전달하지 않는다. `static_from_own=None`은 미등록이며 identity/설정 좌표로 채우지 않는다.

- 매10Hz 프레임에 이동량과 전체3×3 공분산을 전파한다. LK/명령 증분 융합은 기존 `e2e_rgb_vo.fuse`다. 0명령의 정확히0인 잡음을 완전한 정지로 해석하지 않고, 시각 측정이 있으면 기존 VO replace를 쓴다.
- 정합/키프레임 주기는 기존 CSM의1 SIM초다. 현재 자기 관측은 과거 자기 서브맵과 정적 벽 각각에 **같은 이동 사전**으로 정합한다. static 제안이 통과하면 그것을, 아니면 통과한 self 제안을 고른다. 같은 scan을 두 번 독립 관측으로 융합하지 않는다.
- 탐색창은 ±사전1σ를 기존 최대.5m/8° 안에서 검사한다. 1σ의 확률 보장이나 새 GT fitting은 없다. 기존.05m/1° 격자보다 작은 창은 그 창의 양 끝과0도 검사한다. 수치 경계 판정은 실제 격자 간격을 쓰며 작은 창의0이 경계가 되는 오류를 회귀검사한다.
- 기존 점수/중첩/잔차/단일성/관측 가능성 기준을 유지한다. 거부된 자세는 보정하지 않고 분산을 유지한다. 유효 관측은 기존 RBPF motion-proposal 삽입 정책처럼 그 이동 사전/분산과 함께 불변 키프레임으로 남긴다. 이는 위치 보정 성공이 아니다.
- 전역 탐색은 초기 미등록 또는1σ가 기존 국소 탐색 범위를 벗어난 lost 상태에서만 수행한다. 이미 등록되고 국소 사전이 있으면 `initialize_static()`은 `registered_local_tracking_only`로 defer한다. 기존 등록은 객체 속성에 남으며 새 transform을 재채택한 것이 아니다. 장기 pose graph 최적화는 구현하지 않았다.

## 정적 등록의 선택 입력

```python
from harness.mapbuild_static_registration import StaticRegistration, OPTION
result = StaticRegistration(static_map, option=OPTION).register(
    own_segments, camera_origins=segment_camera_origins,
    pose_covariances=segment_pose_covariances, body_origins=segment_body_origins)
```

모두 **같은 own gauge**다. 선분 `[N,2,2]`, 카메라/차체 원점 `[N,2]`, 관측 당시 자세 공분산 `[N,3,3]`이다. `pose_covariances`를 주면 차체 원점도 필수다. 카메라 원점으로 센서 거리를 구하고, 차체 원점으로 yaw 레버 암 `J P Jᵀ/2`를 전파한다. 기존 호출은 두 새 인자를 생략할 수 있다. 새 후보 mapper는 둘 다 제공한다. 시간 상한이나 후보 top-K로 전역 탐색을 자르지 않는다.

## 선택 자기 명령 사전

`harness.mapbuild_command_prior.CommandPrior(..., option='own_command_motion_v1')`은 [동결 입력](calibration/own-command-calibration-r2.json)의 **같은 PWM 자세·같은 바퀴값/시간·같은100ms 간격**에서만 자기 RGB 응답 평균과 예측 공분산을 쓴다. 기본 off이며, 일치하지 않으면 명목6f 사전을 `unqualified_native`로 표시한다. 적재·다른 방향·다른 펄스 길이로 보간하지 않는다. 현재 자격은 빈 FOLDED와 한 종류의 양의 회전뿐이다. 232개 구간은 독립 반복232회나 신뢰구간이 아니다.

## 적재 FK 범위

`servo_fk_carry_v1`은 고정 기구 체인에 집게 슬라이더가 카메라의 조상이 아니므로 닫힌 집게에서도 자기 명령 FK를 계산한다. 가림 마스크에는 실제 발행 grip PWM을 쓴다. 카메라 배치·FOV·기구 치수·PWM 변환은 그대로다. 원래 `servo_fk_v1`의 닫힌 집게 거부는 유지한다.

인수 R2의 닫힘 명령131프레임에서 독립 평가 카메라 오차 P95는.970mm/.280°다. 실제 적재 주행 전 범위나 실물 처짐의 보장이 아니다. 이 구간의 명목 카메라 높이는66.7–138.0mm이며, 기존 CSM의150mm 높이 하한을 하회하는 구간이 있다. 따라서 그 범위의 스캔 공분산 자격은 별도 문제로 남긴다. 높이를 GT로 보정하거나 기본 off 경계를 없애지 않았다.

부품을 소비하는 warp8f/e2ewarp는 자기 실행기·현재 주행 정책에서 오차 관문을 다시 통과해야 한다. 이 녹화기의 운반 경로 커널은 동결6f 교사의 `zone_teacher.plan_path/proportional_drive`다. 현재 heading-first 공용 어댑터의 실제 인수나 ACT 학생/LLM 성공으로 승계하지 않는다.
