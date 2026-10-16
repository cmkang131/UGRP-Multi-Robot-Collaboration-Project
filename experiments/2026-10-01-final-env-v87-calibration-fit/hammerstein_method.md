# v89 오프라인 운동 식별 방법·schema v2

Refs #346 #348. 이 문서는 `calibration_partial_r2.json`의 규약이다.
기존 `calibration_partial.json`(schema v1)의 바이트는 바꾸지 않는다.
무하중 SIM 자료의 사후 탐색이며 학생 실행·실물 보정·P03 승인이 아니다.

## 먼저 정한 채택 기준

축마다 계단→PRBS와 PRBS→계단 모두 **NRMSE ≤ 0.05, fit ≥ 95%**이고,
같은 구조의 정적 비선형 파라미터를 각 훈련 입력으로 식별할 수 있어야 한다.
비수렴·비단조 정적 함수·정적 설계행렬 rank 부족이면 채택하지 않는다.
회전도 회전 PRBS가 필요하다. 검증값으로 구조를 고르므로 별도 확증 시험은 아니다.

`NRMSE = ||y_hat-y||₂ / ||y-mean_sequence(y)||₂`, `fit%=100(1-NRMSE)`.
위치 표본의 시작점은 각 완전한 계단+정지 구간 및 전체 PRBS 구간의 첫 위치다.
평가 잔차의 평균은 빼지 않는다. 첫 0 표본은 점수·AIC/BIC에서 제외한다.
계단 점수의 분모는 각 구간 평균을 따로 뺀 값을 연결한다.
#348의 시작점 기준 RMS 분모도 `origin_normalized_rmse`에 보존한다.
위치 차분 속도의 NRMSE도 보조 수치로 기록하며 평활하지 않는다.

## 실제 명령 경로에서 얻은 구조

다음 경로는 수집 SHA `eaeaaff05553ea02c649b4db9ff82470fe6372b5`의 **소스 읽기**로 확인했다.
원본 `scene.xml`과 `eval_only/applied.json`도 대조했다. 시뮬레이터를 실행하거나 상태를 재생하지 않았다.

| 단계 | 적용 내용 | 식별에 주는 의미 |
|---|---|---|
| `sim/final_environment_measurement_v2.py:123–147` | 전진·측면만 허용, 0.05초마다 명령, physics substep에서 lease tick | v89 회전 자극 없음. 기록 시각과 4,600명령을 계획에 대조 |
| `sim/camera_robot_port.py:160–174` | `[f-l-t, f+l+t, f+l-t, f-l+t]` ABAB 혼합 | command는 무차원 모터 비율이다. 실제 m/s나 wheel radius를 이용한 역기구학 속도 명령이 아님 |
| `sim/masterpi_dynamics_v2.py:1262–1266` | 모터별 `clip(-1,1)` | v89 단일 축 최대 0.03이므로 이 clip은 작동하지 않음 |
| `sim/multi_masterpi_production.py:1473–1478` | `motor_state += (1-exp(-dt/.085))*(command-motor_state)`; wheel target=`12*state` rad/s; 혼합 역투영 | 명시적 모터 지연 0.085초. 별도 chassis slew-rate clamp·통신 순수 지연은 이 경로에 없음 |
| 같은 파일 `1480–1492` | body force=`(2.2*f,1.65*l)-D*v`, yaw torque=`.12*t-Dyaw*w` | 병진 inertia와 감쇠가 모터 뒤에 있어 2차 모델을 검토할 근거 |
| 같은 파일 `1483–1485` 및 dynamics 상수 | `max(abs(command))<1e-6`이면 D 1.4→18, Dyaw .08→.80 | 정지 때 동역학 자체가 바뀜. 하나의 고정 LTI 블록과 정확히 같지 않음 |
| 저장된 XML wheel actuator | velocity kv=.001, target 범위 ±12 rad/s, force 범위 ±.002 | 입력 clip과 actuator 힘 제한은 별개. wheel 실측 속도/힘이 없어 모든 순간의 force 제한 비활성을 단정하지 않음 |
| 저장된 XML | explicit robot inertia mass 합 1.1 kg, support friction .001, timestep .00025초, global noslip_iterations=10 | contact friction은 정적 command deadband가 아니라 속도·접촉 상태에 작용 |

소스는 `sim/zone_final_v3_scene.py:53–84`에서 v3 형상과 `cargo_noslip_v1`을 구성하고,
`sim/multi_masterpi_production.py`의 기본 wrench 경로로 이어진다. 이 수집 경로는 fast-drive kernel을 설치하지 않는다.
팔의 2,000 PWM/s 제한은 별도 servo 경로이며 chassis 속도 제한과 혼동하지 않는다.

접촉을 단순한 Coulomb 마찰로 **근사하면** 다음 구조를 예상할 수 있다.

```
0.085 * motor_dot + motor = command
1.1 * velocity_dot = F_axis * motor - D(command) * velocity - F_contact(velocity, contact)
position_dot = velocity
```

정속 근사에서 gain `F/D`는 전진 1.5714, 측면 1.1786이고,
`mu*m*g/F`는 각각 0.004905, 0.006540이다. #348의 이득·겉보기 deadband와 가깝다.
주행 차체 시간상수 `m/D=0.7857초`, 정지 `m/18=0.0611초`도 같은 방향이다.
이 계산은 접촉 solver를 완전히 유도하거나 해당 마찰 원인을 새 물리 실험으로 확정한 결과가 아니다.
다만 **모터 지연 뒤의 접촉 비선형성과 정지 감쇠 전환**은 입력 비선형성 뒤에 고정 LTI를 두는
Hammerstein 근사가 왜 반전·정지에서 어긋날 수 있는지 설명한다.
코드에 chassis command deadband가 하드코딩됐다는 뜻도 아니다.

## 비교한 모델과 계산

부호별 정적 함수를 따로 적합한다. `a=|u|/.02`, `x=max(a-d_sign,0)`이며
정적 함수의 계수는 m/s(회전 rad/s), deadband `d_sign`은 내부 정규화 단위다.
JSON `deadband_command`는 실제 무차원 명령 단위다.

| 정적 구조 | 부호별 속도 크기 |
|---|---|
| linear 참고 | `b0*a` |
| deadband | `b0*x` |
| deadband_quadratic | `b0*x+b1*x²` — deadband 이후 이득이 크기에 선형으로 변함 |
| deadband_pwl | `b0*x+b1*max(a-1,0)` — 명령 .02에서 연속 꺾임 |

각 정적 구조에 `G1(s)=1/(tau*s+1)` 및
`G2(s)=1/(tau²*s²+2*zeta*tau*s+1)`를 비교한다.
2차는 실근·복소근·중근 모두 허용하며 `tau=1/omega_n`이다.
LTI의 DC gain을 1로 고정해 정적 블록과의 gain 맞바꾸기를 제거한다.
tau=.005–5초, zeta=.15–5, 부호별 deadband=0–.00998 명령,
순수 지연은 0/1/2/3/4 control steps다(v89: 0–.20초).
v87 회전 진단은 관측 0.2초와 별개로 command lease 0.25초 단위 지연을 사용한다.
모터 .085초는 구조를 설명하는 근거이며 적합값으로 강제하지 않는다.

0.05초 영차 유지 명령을 정확 적분한 위치에 output-error 최소제곱을 적용한다.
정적 선형 계수는 variable projection(선형 최소제곱), 나머지는 세 시작점의 bounded least-squares로 찾는다.
전진/측면 각 방향당 4×2×5=40후보, 양방향 총 160후보다.
모든 후보·지연·계수·수렴 여부·rank·경계값·점수는 `hammerstein_report.json`에 있다.
검증 NRMSE 우선, 소수점 6자리 동률이면 훈련 BIC로 선택한다. 임의 고차 모델은 추가하지 않았다.

계단은 15초 구동+1초 정지 6개, PRBS는 15.5초 연속 칩+2.5초 정지 1개다.
모든 명령은 원본 계획과 정확히 일치해야 한다. 모든 출력 시각·lease·표본 순번도 검사한다.
GT 위치 증분을 인접 두 yaw의 중간 방향으로 body 축에 투영해 적분한다.
처음 yaw만 쓰면 누적 yaw 변화가 측면 이득에 섞일 수 있다.
각 완전한 구간의 동역학 초기 상태는 0이며 GT 속도·holdout 잔차로 초기화하지 않는다.
PRBS 칩마다 위치나 속도를 재설정하지 않는다.

PRBS 입력 크기는 ±.02 하나다. deadband·곡률·서로 다른 크기의 gain은 이 입력만으로 분리할 수 없다.
역방향의 비선형 결과는 최소 노름 계수로 이어 붙인 **식별 불가능한 외삽 진단**이다.
따라서 역방향 표에는 식별 가능한 부호별 linear 참고와 비선형 최저 오차를 구분한다.
비선형 역방향 훈련값이 좋아도 교정 채택 근거가 아니다.

`AIC=n*log(SSE/n)+2k`, `BIC=n*log(SSE/n)+k*log(n)`에서
k는 비선형 파라미터+정적 계수+분산+선택한 지연 1개다.
같은 축·훈련 분할·위치 단위 안에서만 비교한다. 위치 잔차는 시간 상관이 있고 deterministic SIM이다.
따라서 iid Gaussian 가정의 **명목 점수**이며 유의성 검정이 아니다.
rank가 부족한 비선형 역방향 점수도 `information_criteria_regular_model=false`로 표시한다.

## 구간 bootstrap

100회, seed 전진911/측면912/회전913. 계단에서는 완전한 구동+정지 구간을 복원추출하고
원래 구간의 loss에 빈도 가중치를 준다. PRBS는 5칩(2.5초) circular block을 복원추출하여
원래 연속 예측의 loss에 가중치를 준다. 칩을 이어 붙여 가짜 전이를 만들지 않는다.
선택 구조·지연은 고정한다. 모든 반복에서 파라미터는 재적합한다.

정적 선형 rank/수렴 실패 수와 입력 크기 coverage 부족 수를 별도로 남긴다.
필요한 크기를 모두 보존한 반복이 20개 미만이면 `intervals=null`이다.
퇴화 반복의 큰 계수·경계 deadband도 `sensitivity_percentiles`에 남기지만 신뢰구간으로 부르지 않는다.
단 한 deterministic run이므로 충분한 반복이 남아도 독립 실행 일반화의 95% 보장으로 해석하지 않는다.
회전은 부호별 한 구간뿐이라 재표집이 원본 복제 또는 한 부호 누락만 만든다. 회전 구간도 null이다.

## 새 교정 schema와 소비자

| 필드 | v2 규약 |
|---|---|
| `schema` | `ugrp.final_environment_measured_calibration.v2` |
| `status` | `PARTIAL_UNLOADED_SIM` 유지 |
| `revision`, `previous_revision` | r2 식별자와 기존 v1 파일의 경로·SHA-256 |
| `motion_source_sha`, `motion_measurement_manifest_sha256` | v89 소스와 새 입력 manifest. 기존 `source_sha`·manifest는 v87 카메라 자료 출처로 유지 |
| `params.motion` | r2에서는 null. 구 v1의 회전 탐색값이 새 검증을 우회하지 않도록 함 |
| `params.motion_hammerstein.{forward,left,rotate}` | 축별 채택 후보 또는 null. 현재 셋 모두 null |
| 후보 레코드 | `static`, `order`, `delay_steps`, `theta`, `coefficients`, `deadband_command`; 위 함수·단위·정렬 사용. `theta=[log(tau),(log(zeta)),d_plus,d_minus]`, linear는 d 생략. 계수 순서는 양부호 b0,(b1), 음부호 b0,(b1) |
| `motion_identification` | 보고서 상대 경로·채택 기준·판정 이유 |
| `legacy_v87_limitations` | v87의 0.2초 표본·짧은 계단 관련 과거 한계. 새 `limitations`는 v89와의 출처·검증 경계를 설명 |
| loaded/fine·loaded camera/pan | 기존 null·수집 전 이유 유지 |

검증에 실패한 수치를 활성 motion 필드에 넣지 않는다. 모든 수치 후보는 보고서에만 둔다.
`harness/zone_final_environment.py:96–121` 소비자는 schema v1+MEASURED_SIM만 받아 r2를 거부한다.
`experiments/2026-09-26-vision-loc/vision_motion.py:53–63`은 `gain @ u`와
단일 `pf.vel`, 1차 `lag_integral`을 쓴다. `harness/vision_motion_init.py`도 이 형태만 초기화한다.
따라서 현재 소비자는 새 구조를 읽을 수 없다.

향후에는 schema별 명시적 로더, 부호별 비선형 함수·명령 범위 검사, 2차 상태·정확 위치 적분,
control-step 지연 FIFO, lease/정지/반전 경계 처리, 불확실성·축간 오차를 반영한 예측 검증이 필요하다.
기존 `motion_v4.delay_s` FIFO는 재사용 검토 대상이지만 함수·상태 교체를 대신하지 못한다.
실제 plant의 정지 전환·접촉 모델을 추가하면 고정 LTI Hammerstein과 다른 구조로 다시 버전 등록해야 한다.
이 PR에서는 제어기·factory·번들·workflow를 바꾸지 않았다.

## 참고 자료

- Lennart Ljung (1999), *System Identification: Theory for the User*, 2판.
  [저자·대학의 서지 페이지](https://www.rt.isy.liu.se/en/books/sysid/).
  모델 구조 선택, 별도 자료 검증, 잔차와 식별 가능성의 일반 원칙을 참고했다.
- Maarten Schoukens & Koen Tiels (2017), *Identification of block-oriented nonlinear systems starting from linear approximations: A survey*,
  Automatica 85, 272–292. [저자 공개 원문](https://arxiv.org/abs/1607.01217),
  [DOI](https://doi.org/10.1016/j.automatica.2017.06.044).
  정적 비선형/LTI 블록과 gain 모호성, 구조별 식별 한계의 근거다.
- [기존 VIS4 exact lag·FIFO](../2026-09-26-vision-loc/vision_motion.py),
  [v2 drive/stop 적합](../2026-09-26-zone-owncam-loop-v2/fit_stop_dynamics.py),
  [기존 v87 적합기](../../scripts/fit_final_environment_unloaded.py).
- [v89 측정 계획](https://github.com/kcm0127-dotcom/ugrp/blob/eaeaaff05553ea02c649b4db9ff82470fe6372b5/configs/final_environment_measurement_v2.json),
  [수집·선행 진단 #348](https://github.com/kcm0127-dotcom/ugrp/pull/348).
- [수집 SHA의 명령 혼합](https://github.com/kcm0127-dotcom/ugrp/blob/eaeaaff05553ea02c649b4db9ff82470fe6372b5/sim/camera_robot_port.py#L160),
  [실제 multi-robot wrench 경로](https://github.com/kcm0127-dotcom/ugrp/blob/eaeaaff05553ea02c649b4db9ff82470fe6372b5/sim/multi_masterpi_production.py#L1454),
  [모터·감쇠·actuator 정의](https://github.com/kcm0127-dotcom/ugrp/blob/eaeaaff05553ea02c649b4db9ff82470fe6372b5/sim/masterpi_dynamics_v2.py#L124).
