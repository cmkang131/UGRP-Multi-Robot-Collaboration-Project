# beamact3 오프라인 비교

고정 final20000, 동일 TRAIN166/60023행·validation19/6908행·seed20261015. wheel은 명령 단위의 MAE다. persistence는 투영/양자화 전 실제 직전 자기 발행 명령이다. A/B/beamact2 결과를 합산하지 않는다.

| 분할 | 재추론 방식 | 구간 | A | B | persistence |
|---|---|---|---:|---:|---:|
| train | all_h0 | all | 0.018939 | 0.022320 | 0.022883 |
| train | all_h0 | stable | 0.008604 | 0.013837 | 0.000000 |
| train | all_h0 | transition | 0.117264 | 0.103026 | 0.240583 |
| train | refresh_h0 | all | 0.018354 | 0.021611 | 0.025583 |
| train | refresh_h0 | stable | 0.007761 | 0.013139 | 0.000000 |
| train | refresh_h0 | transition | 0.113982 | 0.098093 | 0.256542 |
| validation | all_h0 | all | 0.022876 | 0.030805 | 0.023129 |
| validation | all_h0 | stable | 0.011423 | 0.021875 | 0.000000 |
| validation | all_h0 | transition | 0.126417 | 0.111537 | 0.232231 |
| validation | refresh_h0 | all | 0.020701 | 0.030093 | 0.022809 |
| validation | refresh_h0 | stable | 0.008529 | 0.019795 | 0.000000 |
| validation | refresh_h0 | transition | 0.144055 | 0.134451 | 0.253963 |

검증 all_h0의 단계별 wheel MAE:

| 단계 | 행 | A | B | persistence |
|---|---:|---:|---:|---:|
| align | 1142 | 0.024978 | 0.025208 | 0.045359 |
| approach | 2968 | 0.041834 | 0.048349 | 0.034729 |
| complete | 38 | 0.000000 | 0.000000 | 0.000000 |
| pick | 2166 | 0.000000 | 0.000000 | 0.000000 |
| ready | 38 | 0.009211 | 0.009211 | 0.000000 |
| search | 556 | 0.008970 | 0.072235 | 0.008813 |

검증 all_h0 전체의 pulse MAE(ms): A4.291982 / B6.212963 / persistence2.961032. PWM MAE: A20.130486 / B19.706513 / persistence8.301765. wheel 개선을 전체 명령 개선으로 넓히지 않는다.

해석: 최근 wheel/pulse를 남긴 A는 B보다 전체·안정 구간 오차가 작다. B는 전환 구간 wheel 오차가 A보다 작으므로 마스크 해제가 모든 구간을 개선했다고 주장하지 않는다. 한 seed의 A/B 비교이며 통계적 확증이나 폐루프 성공을 뜻하지 않는다.

전체 지표·행 수·phase×stable/transition·pulse/PWM·원본 경로/SHA: [A](A-offline-summary.json), [B](B-offline-summary.json). 평가 source5ad43e1e0, 학습 source4747c4144.
