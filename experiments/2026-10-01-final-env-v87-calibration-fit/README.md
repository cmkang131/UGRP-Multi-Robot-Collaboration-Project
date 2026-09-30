# v87/v89 무하중 오프라인 보정 — PARTIAL_UNLOADED_SIM

## v89 후속 식별: 채택 실패, r2도 null

Refs #348. 먼저 정한 기준은 **계단↔PRBS 양방향 NRMSE ≤5%(fit ≥95%)와 정적 함수 식별 가능성**이다.
부호별 deadband+2차 다항식/PWL, 1·2차 선형 동역학, 0–4 control-step 지연을 비교했다.
**전진·측면 모두 실패, 회전은 PRBS가 없어 검증 불가**다. 기존 교정 파일의 바이트를 보존하고
[schema v2 교정 리비전](calibration_partial_r2.json)을 새로 썼다. 세 축 적용 모델은 모두 null이다.

| 축·검증 방향 | 최저 오차 구조 | NRMSE | fit% | RMS | 판정 |
|---|---|---:|---:|---:|---|
| 전진 계단→PRBS | deadband+quadratic, 1차, delay=0 | 27.39% | 72.61% | 4.199 mm | 5% 초과 |
| 측면 계단→PRBS | deadband+PWL, 1차, delay=0 | 31.68% | 68.32% | 3.237 mm | 5% 초과 |
| 전진 PRBS→계단, 식별 가능한 참고 | 부호별 linear, 1차, delay=0 | 35.78% | 64.22% | 43.508 mm | 5% 초과 |
| 측면 PRBS→계단, 식별 가능한 참고 | 부호별 linear, 1차, delay=0 | 44.65% | 55.35% | 37.582 mm | 5% 초과 |
| 전진 PRBS→계단, 비선형 외삽 진단 | deadband+quadratic, 2차 | 12.50% | 87.50% | 15.202 mm | 파라미터 식별 불가·5% 초과 |
| 측면 PRBS→계단, 비선형 외삽 진단 | deadband+quadratic, 1차 | 13.25% | 86.75% | 11.152 mm | 파라미터 식별 불가·5% 초과 |
| 회전 | v89 turn 명령 0개; v87 ±.03 한 크기씩 | — | — | — | 교차검증 불가 |

NRMSE 분모는 구간 평균을 뺀 위치 신호다. #348과 같은 시작점 기준 분모라면
계단→PRBS 전진 **11.83%**, 측면 **13.83%**다. 둘 다 5%를 넘으며 분모를 섞어 비교하지 않는다.
PRBS는 ±.02 한 크기여서 deadband와 크기별 gain을 역방향 훈련으로 분리할 수 없다.
비선형 외삽 진단을 정식 역방향 검증 통과로 취급하지 않았다.

다음은 **계단 훈련**에서 각 구조별로 PRBS 오차가 가장 작은 지연을 고른 표다(전부 0 step).
AIC/BIC는 같은 축·분할의 명목 Gaussian 위치 잔차 점수다. 시간 상관 때문에 확률적 증거로 해석하지 않는다.
양방향 전체 **160후보**, 회전 진단 **10후보**는 [전체 보고서](hammerstein_report.json)에 있다.

| 축 | 정적 구조 | 차수 | PRBS NRMSE | AIC | BIC |
|---|---|---:|---:|---:|---:|
| 전진 | linear | 1 | 36.70% | -14238.1 | -14210.3 |
| 전진 | linear | 2 | 36.73% | -14236.0 | -14202.7 |
| 전진 | deadband | 1 | 27.45% | -23786.8 | -23747.9 |
| 전진 | deadband | 2 | 27.47% | -23769.0 | -23724.5 |
| 전진 | deadband+quadratic | 1 | 27.39% | -23783.9 | -23733.8 |
| 전진 | deadband+quadratic | 2 | 27.41% | -23766.0 | -23710.4 |
| 전진 | deadband+PWL | 1 | 27.39% | -23783.9 | -23733.8 |
| 전진 | deadband+PWL | 2 | 27.41% | -23766.0 | -23710.4 |
| 측면 | linear | 1 | 46.65% | -14413.9 | -14386.1 |
| 측면 | linear | 2 | 46.69% | -14411.9 | -14378.5 |
| 측면 | deadband | 1 | 32.33% | -25078.7 | -25039.8 |
| 측면 | deadband | 2 | 32.35% | -25062.4 | -25017.9 |
| 측면 | deadband+quadratic | 1 | 31.68% | -25160.5 | -25110.5 |
| 측면 | deadband+quadratic | 2 | 31.70% | -25143.6 | -25088.0 |
| 측면 | deadband+PWL | 1 | 31.68% | -25160.5 | -25110.5 |
| 측면 | deadband+PWL | 2 | 31.70% | -25143.6 | -25088.0 |

전진은 BIC가 더 단순한 deadband+1차를 선호한다. PWL/다항식의 작은 CV 개선으로도 기준에는 못 미친다.
회전 v87 진단 최저 BIC 후보는 linear+2차(delay=0), 훈련 NRMSE 6.76%, fit 93.24%,
AIC -592.1/BIC -582.0이다. 이는 0.2초 표본의 **같은 두 계단에 대한 적합**이며 회전 PRBS 검증값이 아니다.

구간 bootstrap 100회에서 전진/측면의 선택 비선형 모델은 완전한 입력 크기 coverage를 유지한 반복이
각 **1/100회**였다. 파라미터 신뢰구간은 null이며 퇴화 적합의 산포를 보고서에 따로 남겼다.
단순 PRBS linear 참고의 조건부 2.5–97.5백분위는 전진 tau **0.505–0.697초**,
측면 **0.474–0.659초**다. 부호별 gain(속도/명령)은 전진 + **0.988–1.098**, − **0.945–1.124**,
측면 + **0.648–0.716**, − **0.619–0.725**다. 모델 실패를 덮는 불확실성 보장이 아니다.
회전도 독립 구간이 부호당 하나뿐이므로 bootstrap 신뢰구간을 보고하지 않는다.

실제 소스에는 **.085초 모터 지연 → 차체 힘·접촉**, 그리고 정지 시 감쇠 **1.4→18** 전환이 있다.
모터 clip은 이번 명령 크기에서 비활성이고, chassis에 별도 slew clamp는 없다.
접촉의 속도 의존성과 감쇠 전환 때문에 고정 LTI Hammerstein 근사는 구조적 한계가 있다.
[명령 경로·수식·모델 선택·bootstrap·schema·소비자 호환 설명](hammerstein_method.md)을 따른다.

현재 소비자는 `gain @ command`+1차 상태만 사용하므로 새 정적 함수·2차 상태를 바로 소비하지 못한다.
schema 로더, 비선형 함수, 상태·정확 적분, 지연/lease·정지 경계와 검증을 별도 변경해야 한다.
제어기·factory·기존 번들·`.github/workflows`는 변경하지 않았다. P03·loaded/fine은 여전히 미완료다.

새 입력의 원본/소스 SHA-256은 [input_manifest_v89.json](input_manifest_v89.json)에 있다.
v89 raw 전체와 사용한 v87 회전 원본, 계획·선행 진단·명령 경로·기존 적합 코드까지 기록했고
로컬 입력의 읽기 전후 동일성을 확인했다. raw는 로컬 보관이며 원격 백업이 아니다.
`/private/tmp` extraction 디렉터리는 만들지 않았다.

재현(기존 시스템 Python의 NumPy/SciPy 사용; 시뮬레이션 환경 생성 없음):

```sh
python3 -m scripts.fit_unloaded_hammerstein \
  --raw /Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001 \
  --v87-raw /Users/changmin/projects/ugrp/outputs/final-env-v87-04eb11c6-20261001/calibration-unloaded \
  --output /Users/changmin/projects/ugrp/outputs/v89-hammerstein-fit-NEW --bootstrap 100
```

### 검증·TensorBoard

관련 오프라인 검사 150개 통과 후, 마지막 지연 주기·출처 설명 변경 범위 20개를 다시 검사했다.
**중복 제외 151개 통과**이며 원본 보존, 합성 응답 회복, control/observation 주기 분리, 식별 불가 거부,
PARTIAL/P03 차단, v84/v87 및 CI 목록 회귀를 포함한다. [검증 기록](validation_v89.json).
새 입력 manifest는 196항목/195고유 경로(v89 raw 162파일 포함)다. 고정 소스와 측정 브랜치의
동일 계획을 각각 확인해 한 항목이 중복되며, 별도 독립 자료로 세지 않았다.

[TensorBoard](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcv_nrmse_percent%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcv_fit_percent%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcv_rmse_mm%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ftrain_nrmse_percent%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fvalidation_pass%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fvalidation_available%22%7D%5D&smoothing=0&runFilter=%5E1001-v89-hammerstein-r2-final%2F#timeseries)에 최종 9 runs(선형 참고·비선형 후보·회전 검증 불가)를 저장했다.
기존 공용 서버의 logdir, **scalar 78개 실제 값·HParams 이벤트 9개**를 원본과 대조했다.
새 영상은 없다. Chrome `cgWindowNotFound`로 고정 카드·HParams 열의 **화면 확인은 미완료**다.
기존 서버는 변경하지 않았다. [대시보드 검증 기록](tensorboard_record_v89.json).

### 참고 자료

- Ljung (1999), *System Identification: Theory for the User*, 2판:
  [저자 서지](https://www.rt.isy.liu.se/en/books/sysid/).
- Schoukens & Tiels (2017), *Identification of block-oriented nonlinear systems starting from linear approximations: A survey*:
  [공개 원문](https://arxiv.org/abs/1607.01217), [DOI](https://doi.org/10.1016/j.automatica.2017.06.044).
- [VIS4 기존 운동 모델](../2026-09-26-vision-loc/vision_motion.py),
  [v2 drive/stop 적합](../2026-09-26-zone-owncam-loop-v2/fit_stop_dynamics.py),
  [수집·선행 진단 #348](https://github.com/kcm0127-dotcom/ugrp/pull/348).

## 이전 v87 적합 기록 (보존)

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
