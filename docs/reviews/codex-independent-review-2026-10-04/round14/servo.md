# R14 — 현재 servo plan에서는 서로 다른 보정값이 같은 점수를 낼 수 있다

**선택 V2 보정에서 provenance와 consumer 연결을 고쳐도, 낮은 holdout 오차가 파라미터의 유일한 식별을 뜻하지는 않는다.** 실제 plan·fitter의 prediction 함수에는 rate의 포화 구간과 deadband의 구간별 동등성이 있다. 이를 원본 함수와 작성한 수치 행으로 확인했다. 새 구현 버그·실물 오차·현재 pair blocker로 세지 않는 연구 설계 경계다.

Source는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 [`masterpi_servo_calibration_plan.py`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/masterpi_servo_calibration_plan.py)와 [`fit_masterpi_servo.py`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/fit_masterpi_servo.py)다. D5/v98의 별도 calibration을 감사한 결과가 아니다. 실물 측정/heldout 파일을 읽지 않고 공식 함수가 만든 빈 plan에 합성값만 넣었다.

## 1. 실제 모델에서 정확히 같은 예측이 되는 이유

plan은 servo3/4/5/6에서 amplitude `Δ={5,15,30,100,500}PWM`, duration `T=max(0.1,Δ/1200)`을 사용한다. fitter의 예측은 다음과 같다. `d`는 deadband, `r`은 rate, `PPD=2000/180`이다.

\[
\hat\alpha(\Delta,d)=\begin{cases}0&\Delta\le d\\\Delta/PPD&\Delta>d\end{cases},\qquad
\hat t(\Delta,T,r)=\max(T,\Delta/r).
\]

모든 행에서 `Δ/T≤1200`이므로 **r≥1200이면 모든 예측 settle time이 T로 같다.** endpoint 예측에는r이 없다. 따라서 이 구간의 서로 다른r은 현재 모든 fit/holdout 행에서 같은 두 예측을 내고, 어떤 측정값이 주어져도 원본 두 metric과 loss가 같다. 이것은 noise가 작으면 해결되는 근사적 상관이 아니라, 이 유한 plan과 모델 안의 정확한 동등성이다.

fitter는 `r∈geomspace(200,3000,80)`을 탐색한다. 그중27개가1230.41961358…부터3000까지 위 구간에 속한다. 이 구간이 실제 최적이라는 결론은 **현재 실측 자료를 보지 않았으므로 내리지 않는다.** 실제 최소점이1200 아래일 수 있고, 그 범위의 모든r이 동등하다는 주장도 아니다.

deadband는 정수0…80을 탐색한다. 현재 amplitude 집합에서는 `[0,4]`, `[5,14]`, `[15,29]`, `[30,80]` 각각이 동일한 endpoint 예측을 낸다. settle 예측은d에 의존하지 않는다. 같은 구간 안의 파라미터를 구분할 관측이 이 모델의 현재 plan에는 없다. 입력의 모든 physical deadband 현상을 이 계단 모델이 표현한다는 보장은 아니다.

## 2. 원본 함수 증인과 구별 가능한 대조

`servo-fit-identifiability-repro.py` (Mac 전달본 증거)는 pinned Git blob2개의 hash를 먼저 검사한 뒤 `make_plan`, `predict`, `metrics`, `fit`의 원문 AST와 상수를 실행한다. 공식60행(40 fit/20 holdout)의 빈 측정칸에 첫 파라미터 벡터의 noiseless prediction을 작성했다. optimizer 실행은 이 authored 숫자에 대한 작은 계산일 뿐 실물 fitting·physics·학습이 아니다.

| 대조 | 실제 source 함수의 결과 |
|---|---|
| `(d=16,r=1230.4196…)` vs `(d=29,r=3000)` | 기존60행의 endpoint/time 예측 전부 동일 |
| 위 두 벡터로 authored20 holdout 계산 | 양쪽 endpoint MAE0°, relative settle error0 |
| 실제 fitter를 authored40 fit에 실행 | `(15,1230.4196…)` 선택, 같은 holdout 두 error0 |
| 동일d에서r800 vs1000 | 기존 plan에서 최대 settle 예측 차이0.125s. rate 전체가 비식별인 것은 아님 |
| 동일r에서d14 vs15 | 기존Δ15행 endpoint 예측 차이1.35°. deadband 전체가 동등한 것도 아님 |

fitter의 `<` tie 갱신 규칙과 탐색 순서는 첫 최소값을 고른다. 이번15/1230.4196은 반환 규칙과 양립하는 한 대표값이며, 참 deadband15·참 rate1230.4196을 측정한 결과가 아니다. 작성에 쓴16도 참 물리값이 아니다. 두 holdout metric0은 해당 합성 모델의 수치일 뿐 전체 digital-twin validator가 통과했다는 주장이 아니다.

`servo-fit-identifiability-result.json` (Mac 전달본 증거)은 SHA256 `32aeeb066973f524fc44023e283a24646b4da933d154786a58231dea4c981063`이며 source hash·split·대조 결과를 포함한다. 새 원본 데이터나 manifest를 생성/승격하지 않았다.

## 3. 더 많은 반복보다 무엇이 달라져야 구별되는가

**같은 amplitude/duration을 반복하는 것만으로 위 동등성은 깨지지 않는다.** 독립 측정 반복은 해당 조건의 noise 평가에 의미가 있을 수 있지만, prediction 자체가 같은 두 파라미터를 이 모델에서 구별하게 만들지는 않는다.

작은 설계 후보를 원본 `predict`에 대입한 산술 대조는 다음과 같다. 실제 로봇 명령이나 측정 계획의 변경은 하지 않았다.

| 구별할 가설 | 한 행의 모델상 후보 | 예측되는 구별량 | 의미/한계 |
|---|---|---|---|
| r1230.4196… vs3000 | Δ500, T0.1s | settle 차이0.23969877s | 이 모델에서는 두r 모두 duration plateau 밖이라 달라진다. 실제 장치 허용 범위·rate limiting·관측 timing 정밀도는 별도라 이 duration을 바로 실행하라는 권고가 아님 |
| d16 vs29 | Δ20, T0.1s | endpoint 차이1.8° | 그 두 후보를 분리한다. 모든0…80 값을 한 행으로 유일하게 식별하는 것은 아님 |

일반 조건은 비교할 `r_low<r_high`에 대해 `T<Δ/r_low`인 행이면 두 settle 예측이 달라진다는 것이다. 두 후보를 모두 rate-limited 영역에 두려면 더 강하게 `T<Δ/r_high`를 만족시키면 된다. deadband 두 후보 `d_low<d_high`는 `d_low<Δ≤d_high`인 amplitude에서 endpoint 예측이 달라진다. 이는 모델 대수이며 비용·실물 안전·새 측정 실행에 대한 승인이 아니다.

실제 설계에 이 구별을 적용할 때 최소 판정은 **원래 후보들의 예상 차이를 측정 절차가 구별할 수 있는가**, 그리고 **선택한 amplitude/duration이 의도한 사용 domain과 맞는가**다. 이번 검토는 그 물리적 측정 불확실성이나 허용 명령 범위를 새로 추정하지 않았다. 기준을 낮추거나 기존 heldout을 fit에 편입할 이유도 없다.

현재 plan의 fit은 양/음 방향20행씩, holdout은 양방향 중 양의 방향20행만이다. 반복별 split 정의의 직접 결과다. 따라서 이 holdout은 현재 모델의 반복 조건에 대한 평가이며, 음의 방향의 독립 holdout이나 방향 비대칭/히스테리시스의 검증으로 확대할 수 없다. 방향 비대칭이 실제 존재한다고 주장하지 않으며, 이 사실을 데이터 누출이나 설계 위반으로 새로 분류하지 않는다.

## 4. 보고해야 할 것

R13의 두 identity 검증에 이어 필요한 세 번째 구분은 **그 파라미터가 어느 해상도/영역에서 구별되는가**다. 같은 prediction을 내는 후보 집합은 parameter confidence interval이 아니다. noise model·실제 관측 없이 통계적 coverage나 식별 uncertainty를 수치화하지 않는다. 특정 반환값의 소수점 자릿수를 늘려도 이 문제는 해결되지 않는다.

또한 plan 안에서 동등한 후보가 실제 consumer의 다른 command range에서도 동등하다는 보장은 없다. 실제 사용 duration/amplitude가 위 plateau를 벗어난다면 두 모델의 예측이 달라질 수 있다는 것이 §3의 정확한 반증이다. 그렇다고 기존 학습/실물 결과가 잘못됐거나 차이가 발생했다는 결론을 내릴 수는 없다. D5/v98 current pair에는 해당 plan/fitter의 적용 caller를 별도로 입증해야 한다.

문헌을 추가로 늘리지 않았다. [R13 primary evidence](../round13/primary-sources.md)의 intended-use/domain·측정입력/오차모형 구별을 배경으로 삼되, 이번 동등성은 위 source와 식에서 직접 증명한다. 이 모델이 충분한지에 대한 최종 목적은 parameter를 모두 유일하게 만드는 것 자체가 아니라, **허용된 사용 domain에서 필요한 예측을 구별하고 검증하는 것**이다.

재현: `python servo-fit-identifiability-repro.py --repo /path/to/ugrp-clone --output /tmp/servo-fit-identifiability.json`. Python/NumPy와 pinned Git object만 필요하다. 결과를 덮어쓰지 않는 별도 위치를 사용한다.
