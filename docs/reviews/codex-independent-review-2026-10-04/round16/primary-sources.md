# R16 — 보정 보류와 통계적 판정의 1차 근거

2026-10-04. source/math 검토는 `carry-align-statistical-contract.md`와 exact synthetic 결과에 있다. 다음 문헌은 그 의미를 제한하는 근거이며 UGRP 성능 검증이나 새 제어 방식 채택 근거가 아니다.

## P1. John K. Kruschke (2018)

- 제목: *Rejecting or Accepting Parameter Values in Bayesian Estimation*, Advances in Methods and Practices in Psychological Science. DOI: 10.1177/2515245918771304.
- 원문: https://journals.sagepub.com/doi/full/10.1177/2515245918771304
- 저자 대학 보관본: https://scholarworks.iu.edu/dspace/items/bada026d-fe1b-4f53-ad5b-db6e8bf99711
- 읽은 범위: publisher full text의 abstract, Bayesian Parameter Estimation, HDI/ROPE 및 그 관계에 따른 판정, Figure 1 설명, ROPE limits/decision threshold 논의까지 직접 읽었다. supplementary decision-theory 증명이나 제공 R code를 실행/전수 검토하지 않았다.
- 직접 지지하는 주장: posterior interval의 폭과 실용적 동등성 범위는 다른 개념이다. interval이 zero를 포함/배제한다는 사실만으로 practical equivalence가 결정되지 않는다. 실용적 범위와 decision threshold에는 목적에 맞는 선택이 필요하다.
- UGRP 적용: 1.96σ gate의 skip을 ‘정렬 오차가 실용적으로 무시할 수 있음’으로 승격하지 않는다. 실제 제어에는 행동을 선택해야 하므로 논문의 통계적 undecided와 robot hold가 동일한 최적행동이라고 보지도 않는다.
- 적용하지 않음: HDI+ROPE가 유일한 적절한 통계/제어 방법이라는 주장, UGRP에 새 ROPE threshold를 지정하는 권고, 이 논문으로 현재 covariance calibration이나 물리 안전성을 인증하는 주장.

## P2. NIST/SEMATECH e-Handbook — Normal Distribution

- 공식 문서: https://www.itl.nist.gov/div898/handbook/eda/section3/eda3661.htm
- 읽은 범위: 페이지 전체의 normal density/CDF/percent-point-function 정의와 location/scale 설명. 정규 quantile는 재현 코드의 `erf` 및 실제 source Z로 산술 확인했다.
- 지지하는 범위: 정규분포에서 location/scale과 CDF를 이용해 확률 구간을 계산한다는 수학적 정의.
- 적용하지 않음: PF가 정규 또는 calibrated하다는 근거, particle 표준편차를 표본평균의 표준오차로 대체하는 근거, 실제 태스크 성공률/충돌 확률의 인증.

## 독립적으로 유도한 부분

scalar Gaussian의 tolerance 밖 확률, 두 독립 marginal의 곱, 완전한 scalar actuator 가정 아래 제곱 손실 비교는 이 검토의 명시 가정에서 직접 유도·계산했다. 논문에서 보고된 로봇 실험 결과가 아니며, UGRP에 측정된 posterior/오차 분포가 아니다. 기존 R8–11의 covariance/bias/tempering 설명을 그대로 새 논문 성과로 세지 않고, 새 66ff의 실제 center·σ·clip·caller 연결에만 사용했다.
