# v87 무하중 오프라인 보정 — PARTIAL_UNLOADED_SIM

Refs #342 #343. **P03 투입 불가.** 원시 자료를 읽어 적합했으며 물리·렌더·모델 호출은 0회다.
loaded/fine은 수집 전이다. 전진·측면의 이득과 지연도 이 짧은 자료로 분리하지 못했다.
학생 factory·기존 보정·v84/v87 번들·`.github/workflows`는 바꾸지 않았다.

## 자료와 재사용

수집 소스: `04eb11c6a001f2a7d2ab916765d59b3661c06efe`, `masterpi_v3`, `floor_light_v1`, seed 911.
원본: `/Users/changmin/projects/ugrp/outputs/final-env-v87-04eb11c6-20261001/calibration-unloaded`.
3지도 × 120 SIM초, 지도마다 r1 명령 145개(초기 1 포함), r2/r3 각 1개,
로봇당 601개 프레임/GT 행이다. PNG 5,409개의 해시·640×480 헤더와 명령/프레임/GT 시각을 대조했다.
원본 전체 5,465파일과 사용한 저장소 파일 12개의 SHA-256·크기는 [input_manifest.tsv](input_manifest.tsv)에 있다.
읽기 전·후 해시가 같다. raw는 로컬 보관이며 원격 백업으로 주장하지 않는다. 압축 해제 폴더를 만들지 않았다.

- 운동: [v2 fit_stop_dynamics.py](../2026-09-26-zone-owncam-loop-v2/fit_stop_dynamics.py)의
  차체 좌표 변위·주행 후 정지 창·1차 지연 모델·최소제곱 이득/지연 격자 탐색을 재사용했다.
  [M1 fit_fine_motion.py](../2026-09-26-zone-m1-owncam/fit_fine_motion.py)의 drive τ 격자(0.05–3.00초, 0.01초 간격),
  v2 stop τ 격자(0.03/0.05/0.08/0.12/0.2/0.3/0.44/1초)를 쓴다.
  [VIS4 lag_integral](../2026-09-26-vision-loc/vision_motion.py)을 **직접 불러** 같은 ODE를 기록 시각에서 정확 적분한다.
  구 v2의 0.01초 bin 선행 오차를 가져오지 않는다. 순수 NumPy 함수만 실행했다.
- 각 축 ±0.03 명령의 연속 0.25초×4회는 **끊김 없는 1초 명령**으로 묶는다.
  시작부터 4초까지 21개 표본(주행 1초+정지 3초), 양/음 2창으로 적합한다. 정지 이동도 관측값이다.
  지연은 1차 응답 시간상수이며 별도 통신 지연은 이 자료에서 식별하지 않는다.
- 카메라/pan: [VIS3 true_camera_in_base·calibrate](../2026-09-26-vision-loc/vision_loc_cli.py)의
  광학축 변환 `diag(1,-1,-1)`, 정착 표본 요약, 같은 팔 자세의 pan=1500 기준 yaw 회귀를 재사용했다.
  v3의 **전체 base_rotation과 3차원 base_position**으로 실제 차체 기준 외부 변환을 계산한다.
  위치는 중앙값, 회전은 원소별 중앙값에 가장 가까운 **실제 기록 회전**을 택해 SO(3)를 유지한다.
  v2 FK·sag·수치는 복사하지 않았다.

## 운동 결과와 v2 비교

아래 v87 수치는 **탐색 격자 최소점**이다. 전진·측면은 채택값이 아니다.
이득은 명령 속도 대비 정상상태 속도 배율, τ는 초, RMS는 표본 변위 잔차다.

| 항목 | 구 v2/M1 무하중 | v87 후보 | 잔차 RMS | 판정 |
|---|---:|---:|---:|---|
| 전진 gain / τ | 1.4655 / 0.30 | 1.78459 / 1.44 | 0.08980 mm | 이득–지연 식별 불가 |
| 측면 gain / τ | 0.9271 / 0.30 | 2.40680 / 3.00 | 0.07759 mm | τ 격자 상한, 식별 불가 |
| 회전 gain / τ | 1.4885 / 0.30 | 1.14996 / 0.17 | 0.00016149 rad (0.00925°) | 탐색 후보, 별도 검증 없음 |
| stop τ (전진/측면/회전) | 명시값 없음, 기본 τ=0.30 | 0.08 / 0.05 / 0.03 | 위 RMS에 포함 | 모두 0.2초 표본 간격 미만, 미확정 |
| pan–차체 yaw | 5.5e-7 rad/PWM | 1.52879e-8 rad/PWM | 절대잔차 p95 0.003774° | 신호가 잔차보다 작음 |

구 값 출처는 [calibration_m1_dev.json](../2026-09-26-zone-m1-owncam/calibration_m1_dev.json)과
[calibration_train.json](../2026-09-26-vision-loc/calibration_train.json)이다. 동일 모델/코호트 성능 비교가 아니다.
구 v2 gain의 축간 항은 이번 대각 모델로 재적합하지 않았다. 실제 축간 이동은 상세 보고서에 보존했다.

**작은 잔차가 gain의 식별을 뜻하지 않는다.** 전진의 RMS 최솟값 +5% 이내에도 gain 1.60–3.47,
τ 1.25–3.00초가 들어간다(신뢰구간 아님). 같은 모델의 추가 τ=3/5/10/30/100초 민감도 점검에서
전진 τ=5초/gain=5.529의 RMS가 0.0793 mm, 측면 τ=30초/gain=21.774의 RMS가 0.0545 mm로 더 작다.
큰 gain과 큰 τ를 맞바꿀 수 있으므로 억지로 그 값을 채택하지 않았다.
`params.motion`의 전진/측면 gain·τ와 모든 stop τ는 **null**, 숫자는 `diagnostic_grid_minima`에만 남겼다.
노이즈·슬립·축간 gain을 새로 검증한 것도 아니다.

| 축 | 한 방향 명령 적분 | 1초 끝 관측 | 정지 3초 뒤 관측 | 정지 drift (양/음 평균 절댓값) |
|---|---:|---:|---:|---:|
| 전진 | ±30 mm | ±15.212 mm | ±17.062 mm | 1.8494 mm |
| 측면 | ±30 mm | ±10.598 mm | ±11.845 mm | 1.2463 mm |
| 회전 | ±0.030 rad | ±0.029007 rad | ±0.029641 rad | 0.00063384 rad |

r1의 **시작 위치 기준 최대 거리**는 16.4806 mm지만, 전진 명령 구간 시작 기준 이동은 17.0617 mm이고
전체 표본 경로 길이는 73.8298 mm다. 왕복 명령과 pan/팔 구간의 차체 이동 때문에 이 세 수치는 다르다.
평가상 최종 이동은 (−0.5854, +0.08157) mm. 1.6 cm만으로 무응답을 단정할 수 없다.
r2/r3는 최대 위치 변화가 각각 1.4e-12/3.9e-12 m 수준이다.

## 지도 간 일치와 카메라

| 지도 | 전진/측면/회전 gain 후보 | 각 τ 후보 | 운동·pan·카메라 지도 간 범위 |
|---|---|---|---|
| door | 1.78459 / 2.40680 / 1.14996 | 1.44 / 3.00 / 0.17 s | 0 |
| two_doors | 동일 | 동일 | 0 |
| corridor | 동일 | 동일 | 0 |

세 지도는 같은 seed·배치·명령이고 저장된 base/camera 궤적도 같다. 지도별 min/max/range/표본 표준편차를
산출물에 기록했지만, **독립 반복의 불확실성이나 환경 일반화 근거는 아니다.** 부동소수점 표준편차 약 1e-16은 계산 잡음이다.

검색/p20/빈 carry마다 pan `1500→1230→970→700→1770→2030→2300→1500`이다.
**8회 방문, 7개 고유 pan**이므로 지도당 24회 방문·21개 고유 외부 변환을 제공한다.
모든 방문의 `origin_m`, optical→chassis `rotation`과 잔차는 [fit_report.json](fit_report.json)의
`camera_visits`, 지도별 요약은 `camera_per_map`, 합친 값은 [calibration_partial.json](calibration_partial.json)에 있다.
방문하지 않은 자세는 추정하지 않았다.

기존 0.3초 정착 기준에서는 전이 프레임이 남아 위치 최대잔차 **52.288 mm**, 회전 **25.448°**였다.
이 결과도 `legacy_settle_diagnostic`에 보존했다. 같은 수집 자료를 보고 **사후 탐색적으로 1.0–3.0초 구간**을 택했다.
이 구간 최대잔차는 위치 **2.71e-7 m**, 회전 **0.000141°**다. 새 확증이나 정착시간 인수 판정이 아니다.

| 팔 자세 (servo3/4/5) | pan=1500 origin_m (차체 몸체 원점 기준) |
|---|---|
| search (740/2320/1320) | (0.131066, ≈0, 0.177464) |
| p20 (1072/2400/1482) | (0.162416, ≈0, 0.171442) |
| carry_empty (777/2053/1646) | (0.167076, ≈0, 0.175651) |

pan 회귀는 지도당 비중앙 198프레임이다. 자세별 기울기는 search 7.34e-9, p20 2.09e-8,
carry_empty 1.76e-8 rad/PWM. pan 2030의 pooled 예측 yaw는 약 **0.000464°**로 잔차보다 작아
정밀한 결합 계수로 확정할 수 없다. 카메라 원점은 지면 z=0이 아닌 실제 몸체 원점(지면보다 약 32.36 mm 높음)이다.
향후 지면 투영 소비자는 이 차이를 명시적으로 처리해야 한다. 이번 PR은 소비자를 연결하지 않는다.

## 산출물·검증·재현

- schema: `ugrp.final_environment_measured_calibration.v1`, status: **PARTIAL_UNLOADED_SIM**.
- `motion_loaded`, `motion_profiles.fine`, loaded camera/pan은 null이며 이유는 정확히
  `loaded collection not yet run`이다. `MEASURED_SIM`으로 승격하지 않았다.
- contract SHA-256: `6666b23b72db5e7243af337b85f87ce469c389709e59852d8fa963dd92c0ebb6`.
- 측정 manifest SHA-256: `ac3c19050985ce833a79f4e638c88394c32cce3a5dfdf8cf267f5d00d7994cb8`.
  지도별 정적 hash, 입력 파일별 hash, 원본 경로, 재사용 소스 hash는 JSON/TSV에 있다.
- 오프라인 회귀 **65개**, CI 분할 회귀 **66개** 통과(총 131개). 합성 양/음 명령 적합, 만료/연속 갱신,
  광학축·차체 높이 변환, 방문 경계, 해시, null 보존, PARTIAL 상태 거부와 v87 P03 실행 차단을 검사했다.
  새 테스트는 `scripts/run_ci_tests.py`에 등록했다. [검증 기록](validation.json).
- TensorBoard에 3지도 후보와 구 v2 참고를 분리한 새 snapshot 4개를 내보냈다. 기존 서버의 공용 logdir와
  **실제 scalar 36개 로딩·원본 값 일치**를 HTTP로 검증했다. 영상은 만들지 않았다.
  [대시보드](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fforward_gain_candidate%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Flateral_gain_candidate%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Frotate_gain_candidate%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fforward_residual_rms%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Flateral_residual_rms%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Frotate_residual_rms%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpan_rad_per_pwm%22%7D%5D&smoothing=0&runFilter=%5E1001-v87-unloaded-fit%2F#timeseries) · [변환/검증 기록](tensorboard_record.json).
  Chrome UI 연결은 `cgWindowNotFound`로 실패해 고정 카드 표시·HParams 열의 화면 검증은 미완료다.
  기존 서버/실험은 건드리지 않았으며 추가 서버를 시작하지 않았다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$PY" -m scripts.fit_final_environment_unloaded \
  --raw /Users/changmin/projects/ugrp/outputs/final-env-v87-04eb11c6-20261001/calibration-unloaded \
  --output /Users/changmin/projects/ugrp/outputs/final-env-v87-unloaded-fit-NEW
"$PY" -m pytest -q tests/test_final_environment_unloaded_fit.py \
  tests/test_zone_final_environment_floor_light.py tests/test_zone_final_environment_runnable.py
```

## 참고 자료

- [#342 수집 경로](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/342),
  [#343 원시 수집 기록](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/343)
- [PHYSICS_HANDOFF.md: v3 보정](../../PHYSICS_HANDOFF.md),
  [고정 측정 계획](../../configs/final_environment_measurement_v1.json),
  [보정 계약](../../configs/calibration/zone_final_v3_floor_light_contract.json)
- [이번 오프라인 적합기](../../scripts/fit_final_environment_unloaded.py),
  [P03 거부·오프라인 회귀](../../tests/test_final_environment_unloaded_fit.py)
