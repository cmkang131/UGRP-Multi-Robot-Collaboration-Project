# 조립기(assembler) 프레임 시계 키 수정과 실제 v88 raw 재확인 (2026-10-03)

범위: #351에서 병합한 `scripts/assemble_final_pair_calibration.py`(입출력은 `scripts/final_pair_calibration_io.py`)를 실제 v88 raw에 처음 돌렸을 때 세 수집이 모두 거부된 원인을 찾아 고친다. 보정 방법, 임계값, 고정된 기준 B/B′ 파일, 후보 r4, 번들, 워크플로는 바꾸지 않았다. 물리 시뮬레이션, 렌더링, TensorBoard는 쓰지 않았다. raw는 읽기만 했다.

## 무엇이 틀렸나

1. 프레임 시계 키 (치명적).
   - 실제 실행기(`sim/camera_robot_port.py`의 `capture()` + `sim/final_pair_v3.py`의 `capture()`)가 `robots/<rid>/frames.jsonl`에 쓰는 키는 `actuator_state, camera, commanded_servo, frame_id, path, robot_id, sha256, sim_time`이다. 시간 키는 `sim_time`이다.
   - 조립기는 `t`를 읽었다. 그래서 `r1 frame clock must be a finite numeric time`으로 세 수집이 모두 거부됐다(PARTIAL, 114칸 누락).
   - 합성 시험 자료도 `t`로 써서 이 불일치가 시험에 걸리지 않았다.
   - 수정: 프레임 시계는 `sim_time`만 읽는다. `t`나 둘 중 아무거나를 받지 않는다. `sim_time`이 없거나 숫자가 아니면 거부한다. 고친 곳은 입출력 파일의 시계 검사, 프레임·라벨 일치 검사, 정지 시간 계산과 카메라 파일의 프레임 색인, 빔 가장자리 시간 창이다.
   - 같은 파일의 라벨(`eval_only/*/camera_labels.jsonl`), 자세(`pose.jsonl`), 빔 궤적, 접촉 행은 실제로 `t`를 쓰므로 그대로 둔다.

2. 라벨과 자세 비교 허용 오차 (고침, 검토 요청).
   - 키를 고치자 감사가 다음 검사에서 세 수집 모두 `camera label chassis pose differs from simultaneous pose sample`로 떨어졌다.
   - 라벨의 차체 자세는 렌더링 때 기구학을 갱신한 값이고, `pose.jsonl`은 같은 SIM 시각에 갱신 없이 읽은 값이다. 그래서 실제 raw에서 둘이 조금 다르다(추정 원인: 한 물리 하위 단계 지연).
   - 실제 raw의 최대 차이는 위치 4.7e-5 m, 회전행렬 원소 6.9e-4이다. 기존 허용 오차는 1e-8이었다(비트 단위 일치 가정). 이웃한 50 ms 표본과의 차이는 최대 수 mm 이므로 구분력은 남는다.
   - 수정: 위치 1e-4 m, 회전 2e-3으로 바꾸고 이유를 코드 주석에 적었다. 이 값은 보정 방법이나 기준 B/B′ 임계값이 아니라 입력 감사 검사의 정합 허용 오차이다. 되돌리고 싶으면 이 두 상수만 바꾸면 된다.

## 모든 읽는 필드의 대조

방법: 조립기가 읽는 모든 raw 파일의 키를 실제 세 raw(unloaded, fine, loaded)에서 접근 기록 방식으로 모아 실제로 없는 키가 있는지 확인했고, 작성 코드(`sim/final_pair_v3.py`, `sim/camera_robot_port.py`, `sim/final_environment_checks.py`)의 사전 리터럴과 맞춰 보았다. 읽는 파일은 plan.json, 수집 result.json, 사례 result.json, bundle.json(measurement 포함), inputs/static_map.json, inputs/schedule.json, artifacts.sha256.json, commands.jsonl, frames.jsonl, camera_labels.jsonl, pose.jsonl, trajectory.jsonl, contacts.jsonl, scene.xml이다.

- 실제 raw에 없는 키를 읽는 곳은 `bundle.measurement.initial_hold_s` 한 곳뿐이다. 이는 `.get('initial_hold_s', motion_start_s)`의 첫 후보이고 실제 키 `motion_start_s`로 대체되며, 고정된 기준 B의 `plan_arrays`도 같은 방식이다. 값은 영향이 없어 그대로 둔다.
- 그 밖의 파일은 읽는 키가 모두 실제로 있다.
- 실제 자료에는 서보 2가 없다(`commanded_servo`와 `initial_servo_command.pulses`는 1, 3, 4, 5, 6만). 합성 시험은 2를 넣고 있어 실제에 맞게 뺐다. `frame_id`는 정수(1부터)이고 프레임 파일은 `rgb/NNNNN.jpg`(0부터)이다.
- `trajectory.jsonl`의 `beam_rotation`은 평평한 9개 값이다. 조립기는 이미 reshape하며 맞다.

## 시험 변경

- 합성 시험 프레임 행을 실제 키 집합으로 바꿨다(`robot_id, frame_id(정수), sim_time, sha256, camera, actuator_state{motor_commands, servo_pulses}, path, commanded_servo`). 서보 2도 뺐다.
- 회귀 시험: (a) 시험 자료의 프레임·라벨·자세·빔·접촉 행 키가 작성 코드 소스(ast 추출)의 키와 정확히 같음, (b) 명령 종류별 키와 서보 어휘가 실제 raw와 같음, (c) 예전 `t` 프레임은 거부됨, (d) 라벨-자세 허용 오차가 실제 수준의 지연은 받고 이웃 표본 크기의 차이는 거부함. 시계 변조 시험의 프레임 키도 `sim_time`으로 바꿨다.

## 실제 raw 재확인 (사본 출력, raw는 변경 없음)

실행: 조립기를 합친 링크 raw 루트에 돌리고 새 폴더 `/Users/changmin/projects/ugrp/outputs/final-pair-v88-measured-dryrun-20261003-035426`에 썼다(수정 커밋 d00208ba, 작업 트리 깨끗).

- 세 수집 감사(collection_audit): unloaded PASS, fine PASS, loaded PASS. 적재 선택: lifted 6839, not_lifted 553, missing_bilateral_grip 9.
- 상태 PARTIAL, 누락 42칸(이전 114칸). 사유별:
  - 10칸: 고정 기준 B가 unloaded 축 판정을 모두 null로 둠(`params.motion`). 예상된 한계(두 문 지도가 B의 훈련 지도, 회전 후보 없음)이다.
  - 16칸: 적재(loaded) 운동 식별 실패 `rank 13/13`. 최적화는 수렴했으나 모수 13개 중 5개가 경계에 닿았다(회전 이득 하한, 회전 시간상수 상한, 데드밴드 c0 하한 둘, u1 상한 하나). 입력 형식 문제가 아니라 실제 자료와 고정 모수 범위의 한계이다. 이 방법은 바꾸지 않았다.
  - 5칸: `pair_model` "measurement not available". 적재 운동 평균이 거부돼 쌍 모형 단계가 실행되지 않았다.
  - 1칸: `pan_base_yaw.loaded` 같은 팔 기준 안정 표본 부족.
  - 5칸: 적재 카메라 자세(1269,2052,2494,1500)는 안정 시각의 양손 파지 표본 없음.
  - 5칸: 적재 카메라 자세(807,1897,2187,1500)는 잔차 한계 초과(원점 3.5 mm, 회전 2.1도)로 거부.
- 참고(쌍 모형 읽기 경로 점검): 모수 결과에 영향이 없도록 fine 모수를 빌려 `pair_rows`만 실제 loaded raw에서 돌려 읽기 형식이 맞는지 확인했다. 54개 창이 모두 "edge not observable"로 제외됐다. 적재 수집의 카메라 자세(807,1897,2187)에서는 화면이 거의 균일한 회색이라 빔 띠(노랑-초록, 색상 25-90)가 보이지 않는다(75개 표본 중 r1 2장, r2 5장만 일부 색상 픽셀). 입력 형식 문제가 아니라 시야/조명 문제로 보이며 별도 판단이 필요하다. 이 단계는 고치지 않았다.

## 남은 일 (이 PR 범위 밖)

- 적재 운동 식별이 모수 경계에 닿는 이유(데드밴드 범위, 회전 축 시간상수 범위).
- 적재 수집에서 빔 가장자리가 보이지 않는 문제와 쌍 모형.
- unloaded 고정 기준 B의 한계는 기록대로 유지한다.
