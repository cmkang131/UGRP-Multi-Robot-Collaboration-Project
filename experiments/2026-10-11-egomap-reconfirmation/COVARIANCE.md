# 공분산 원인별 진단·기본 OFF 후보

`harness/egomap_covariance.py`의 `nees_stratified_v1`은 저장한 XY 오차로 적합한
고정 공분산 배율을 사용한다. 실행 중에는 **현재 프레임 전 단계와 직전 자기 발행
명령**만으로 approach/return × 좌회전/우회전/이동/정지 층을 선택한다.
이 층은 오차 원인의 관측 가능한 대리변수이며, 물리 원인을 식별했다는 주장이 아니다.
온라인 정답·NEES·접촉·성공 입력은 없다. 두 토글을 함께 켠 12회 비교에서는 각 토글의
단독 인과 효과를 주장하지 않는다.

전체 행렬 `P_report = factor * P_raw`를 적용해 교차항과 양의 정부호를 보존한다.
자기 지도 odometry covariance facade이므로 `GoalRoute._localize`의 불확실성 판단,
`own_sample`의 covariance를 받는 정합, 지도 export와 최종 sigma 보고가 소비한다.
RBPF 입자·pending process noise·명령 평균·RNG는 직접 바꾸지 않는다. 따라서 보고 전용
변경은 아니며, 불확실성 재정합을 통한 후속 제어 변화는 새 짝 비교에서 평가해야 한다.
inflation은 시각적 오인이나 평균 편향을 수정하지 않는다.

## 조사와 적용

- 고전: [Anderson & Anderson 1999](https://journals.ametsoc.org/abstract/journals/mwre/127/12/1520-0493_1999_127_2741_amciot_2.0.co_2.xml)의 공분산 multiplicative inflation을 그대로 사용한다. 이 구현은 ensemble filter 자체를 이식하지 않고 기존 RBPF의 보고 공분산에 동일한 배율 연산만 연결한다.
- [Raanes, Bocquet & Carrassi 2019](https://arxiv.org/html/1801.08474v4)는 sampling/model error를 구분하며 오류의 알려진 구조를 활용할 것을 설명한다. 여기서는 기존 실행이 가진 단계·명령 이력을 층화하며 새로운 모델/관측은 넣지 않는다. 논문의 EnKF-N 재구현이라고 표현하지 않는다.
- [Chen et al. 2023, III/V절](https://arxiv.org/html/2306.07225v1)은 `eᵀP⁻¹e`와 χ² 비교를 제시하고, 평균이나 초과율만 맞춰도 올바른 튜닝은 아닐 수 있음을 보인다. 따라서 오차 평균·NEES 평균/분산/분위·층별 초과 개수를 함께 보존한다. 정답은 이 오프라인 평가에만 들어간다.
- 최신 조사: [Jiang et al., CAR-EnKF, 2026-09-16 v2](https://arxiv.org/abs/2604.17343v2)는 비선형 관측의 PSD 보상과 NIS 기반 적응을 다룬다. 현재 RBPF에 해당 Kalman gain/innovation 공분산이 없으므로 이 알고리즘을 억지로 이식하지 않았다. 초록과 구현 연결 개요까지 확인했으며 논문의 성능 수치를 우리 결과로 인용하지 않는다.
- [NIST χ² 표](https://www.itl.nist.gov/div898/handbook/eda/section3/eda3674.htm)의 2자유도 상한을 사용한다. 단측 95%=5.991464547, 99.9%=13.815510558. `3 × sigma_max`의 거리 초과와 정확한 full-matrix NEES는 다르다.

배율 추정은 스칼라 Gaussian scale의 표준 최대우도 식
`factor=max(1, mean(eᵀP⁻¹e)/2)`이다. 긴 상관 궤적이 적합을 지배하지 않게 run별
평균을 같은 가중치로 평균한다. 30표본·2 run 미만인 층은 pooled 배율을 사용한다.
표본수 조건과 단계·명령 층화는 이 프로젝트의 명시적 적용 선택이다. 시간 표본을
독립 시행으로 취급하지 않고, 적합·확인은 seed로 분리한다.

## 확보한 자료와 결과

ARM `egomap70-wave1`의 63001/63002 × baseline/calib/calib_traversed/
calib_traversed_zone 8 run에서 결과·자기 trace·covariance·평가 궤적만 회수했다.
32파일, 8,718,555 bytes, 모든 원격/로컬 SHA-256 일치. 원본은 ARM에 보존된다.
[회수 목록](covariance-fetch-manifest.json), [점수](covariance-offline-v1/summary.json),
[적합값](covariance-offline-v1/calibration.json).

63001은 적합 3,814표본/4 run, 63002는 확인 5,084표본/4 run이다. 이미 관찰했던 DEV
자료이며 독립 확증이 아니다. 동일 seed의 조건들은 독립 위치·장면 표본도 아니다.
한 적합 seed의 baseline에는 이전 회전 모델도 들어가므로 새로운 회전 모델만의
보정으로 해석하지 않는다. 실패 궤적을 제외하지 않았다.

| 확인 63002 | raw | pooled | 원인 proxy 층화 |
|---|---:|---:|---:|
| χ²95% 초과/전체 | 3003/5084 | 3/5084 | 5/5084 |
| χ²99.9% 초과/전체 | 1747/5084 | 1/5084 | 3/5084 |
| NEES 평균 | 20.551 | 0.519 | 0.984 |

pooled 공분산 배율은 39.59948, approach 층은 14.02396–19.14076이다. return은 적합
run 하나뿐이라 pooled fallback이다. 층화는 pooled보다 초과 수가 많았으며 적합
자료에서도 χ²99.9 초과가 556/3814 남았다. covariance 후보는 **DEV 비교용**이고
일관성·위치 정확도·잘못된 복귀 감소가 검증됐다고 판정하지 않는다.

사용자 배경의 `egomap70c ×4.154, 41/1260`은 현재 branch, overview branch/worktree,
Mac egomap70 compact, ARM egomap70 디렉터리에서 원본을 찾지 못했다. 배율이 sigma인지
covariance인지와 초과 기준도 확인되지 않아 이번 full-matrix NEES와 합치거나 임의로
재현했다고 표시하지 않았다. ARM의 wave2/wave3 `.incoming`에는 필요한 로그가 없어
나머지 4 seed의 오프라인 재생은 미완료다.

실행 재현: 프로젝트 Python에서 `python -m scripts.evaluate_egomap_covariance --runs
<Mac fetch-lite run 8개> --fit-seeds 63001 --check-seeds 63002 --output <새 폴더>`.
압축 입력은 기존 `zstd -dc`를 사용한다. 새 물리 실행·LLM·학습은 없다.
