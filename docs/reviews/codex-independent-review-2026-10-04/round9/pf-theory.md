# R9 — PF 반복 관측 감쇠의 좁은 이론 계약

검토 대상: PR #363 `6727751b`의 `harness/zone_pair_highpose_pf_consistency.py` (원문 사본 `vision-source/`). 실제 주행·영상·held-out 결과를 재실행하거나 열람하지 않았다. 아래 수치는 정적 1차원 Gaussian 해석 증인이며 현재 PF의 경험적 오차나 성공률이 아니다.

**먼저 확인할 것:** 현재 감쇠를 “등상관 관측의 정확 Bayesian update”라고 설명하는지, “앞 관측을 우선하는 순차적 generalized-likelihood heuristic”이라고 설명하는지 구별한다. 후자라면 순서 민감성은 설계 선택일 수 있다. 전자의 근거로 `c_K`만 제시하기에는 충분하지 않다. 실제 view reset/lease renewal/accepted scan 수는 `vision.md`의 별도 코드 검증에 맡긴다. 소스는 design effect를 설명하지만 exact Bayesian 보장을 명시하지 않으므로, 이 문서는 구현 버그 건수를 추가하지 않는다.

## 1. 소스가 실제로 하는 일

`cumulative(K,rho)=K/(1+(K−1)rho)`, `exponent(k,rho)=c_k−c_(k−1)`이다. `view_apply`가 정한 scan 번호 k에서 `scan_loglik` 전체를 이 지수로 곱한다. 과거 scan의 likelihood를 다시 균등하게 재가중하는 코드는 이 wrapper 안에 없다. 별도로 column cap 비율도 곱한다. 이 관찰은 해당 wrapper의 코드 사실이며, 원래 PF의 prediction/resampling을 없앤다는 뜻이 아니다.

`sum(a_k)=c_K`라는 항등식은 맞다. 특히 같은 x에 대해 모든 scan의 log-likelihood 함수가 정확히 같다면 누적합은 `c_K log L(x)`가 된다. 하지만 같은 view에서 나왔다는 이유만으로 서로 다른 영상의 likelihood 함수가 동일하지는 않으며, 총 지수의 합과 올바른 posterior는 별개의 조건이다.

## 2. 등상관 Gaussian과 비교할 수 있는 조건

오직 이 절에서만 다음 모델을 가정한다.

- 하나의 **변하지 않는 scalar latent x**를 K번 측정: `z_i=x+ε_i`.
- 오차는 zero-mean 공동 Gaussian, 모두 같은 분산 σ², 알려진 동일 상관 0≤ρ<1.
- `R=σ²[(1−ρ)I+ρ11ᵀ]`, process noise·prediction·resampling·view reset 없음.
- flat prior로 likelihood 모양만 비교한다. 따라서 이 계산은 실제 다차원 PF를 모사하지 않는다.

이 모델에서 `R⁻¹1 = 1/[σ²(1+(K−1)ρ)] 1`이다. 정확한 likelihood의 x 관련 부분은

\[
\log L(x)= -\frac{c_K}{2\sigma^2}(x-\bar z)^2+\mathrm{const},\quad
c_K=\frac{K}{1+(K-1)\rho}.
\]

따라서 총 precision은 `c_K/σ²`, 중심은 **동일 가중 평균**이다. 반면 sequential power likelihood의 중심은

\[
\tilde\mu_K=\frac{\sum_{k=1}^K a_k z_k}{c_K},\qquad
\tilde V_K=\frac{\sigma^2}{c_K}.
\]

ρ>0이면 a_k가 서로 다르므로 일반적으로 중심이 다르다. 공통된 총 precision을 갖는다고 정확한 likelihood와 같아지지 않는다. 정확한 등상관 모델은 앞선 측정으로부터 다음 측정의 조건부 평균도 바뀐다. 독립 likelihood에 양의 지수만 붙이는 방식은 그 조건부 innovation과 자동으로 같지 않다.

## 3. 재현 가능한 최소 증인

K=3, ρ=0.5, σ²=1이면 `a=[1,1/3,1/6]`, `c_3=1.5`이다.

| 고정 관측 집합의 순서 | wrapper 지수로 만든 중심 | 정확 등상관 Gaussian 중심 | 두 likelihood의 표시 분산 |
|---|---:|---:|---:|
| [0,0,3] | 1/3 | 1 | 2/3 |
| [3,0,0] | 2 | 1 | 2/3 |
| [2,2,2] | 2 | 2 | 2/3 |

역순 비교의 정당성은 **동일 정적 x·교환가능 오차**라는 위 가정에만 있다. 움직이는 로봇의 실제 시간순 관측을 역순 처리해 같아야 한다는 요구가 아니다. 동일 관측 행은 이 설명에 대한 반증 대조: 모든 likelihood가 같을 때는 합의 항등식으로 두 결과가 일치한다.

더 좁게, 이 모형에서 wrapper 중심의 정규화 가중치는 `w=[2/3,2/9,1/9]`다. 그 추정량의 실제 sampling variance는

\[
\operatorname{Var}(w^Tz)=\sigma^2[\rho+(1-\rho)\sum w_i^2]=61/81\approx0.753086,
\]

반면 power likelihood가 표시하는 분산은 `2/3≈0.666667`이다. 그러므로 **이 명시 모형에서도 c_K를 맞췄다는 사실만으로 보수적 uncertainty가 보장되지는 않는다.** 실제 PF의 coverage·NEES·ρ 추정 품질에 대한 수치 판정으로 사용하지 않는다.

`pf-tempering-math.py`와 `pf-tempering-math.json`은 fractions만으로 위 항등식과 수치를 계산한다. UGRP import·시뮬레이션·난수·데이터 접근은 없다.

## 4. 최신 blocker에 적용하는 범위

1. wrapper가 시간상 **첫 valid scan을 신뢰하고 후속 반복을 약하게 반영**하려는 것이면 그 의미를 그대로 보고할 수 있다. calibrated heuristic의 유용성은 이 수학만으로 부정할 수 없다.
2. view 변경 판단과 통계적 독립성은 다르다. own command는 허용된 view 변경 후보이나 실제 이동의 측정은 아니다. 실제로 움직여도 같은 camera/map/model bias는 공유할 수 있다. 반대로 정지 중에도 일부 픽셀 잡음은 새 정보일 수 있다.
3. first scan이 atypical할 때 이후 scan이 얼마나 만회할 수 있는지는 별도 설명할 만하다. **0<ρ<1일 때** 무한 반복에서 `c_K→1/ρ`이고 첫 scan의 정규화 비중은 ρ로 남는다(동일 static likelihood 모형). ρ=0은 `c_K=K`인 별도 경계다. 이를 실제 beam 오차의 원인으로 단정할 자료는 읽지 않았다.
4. 가능한 최소 검토는 기존 허용 trace에서 view key/reset 원인, applied-scan k/α, likelihood 요약의 시간 순서를 함께 읽는 것이다. 새 physics 실행이나 ground-truth를 policy에 넣을 필요가 없다. trace가 없는 상태에서는 “실제 first-scan anchoring 발생”을 보고하지 않는다.

## 5. 분산 센서 문헌과 연결할 때의 한계

Ong et al., *Decentralised Data Fusion with Particles* (ACRA 2005), §4.1 Eq.(5)는 두 센서의 posterior를 합칠 때 공통 정보를 제거해야 하는 상황을 다룬다: [저자 소속기관 원문](https://www-personal.acfr.usyd.edu.au/tbailey/papers/acra2005particleddf.pdf). 이는 **노드 간 같은 정보의 재전송** 문제이고, 여기 wrapper는 **한 필터의 시간상 반복 관측** 문제다. 같은 정보의 중복을 경계한다는 논리만 연결하며 알고리즘 동등성을 주장하지 않는다. 해당 논문은 현재 `a_k` 또는 column cap의 보장 근거가 아니다.

이론 계산은 이 리뷰의 직접 유도이다. 소스 주석의 Kish 1965 책 본문은 확보하지 않았으므로 인용 확인을 했다고 표시하지 않는다. Nav2 movement gate와도 동일 구현/같은 보장을 주장하지 않는다.
