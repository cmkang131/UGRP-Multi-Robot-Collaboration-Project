# s3fix9: 관측 제안과 정렬 진입 (결과 전 사전 등록)

2026-10-10. 요청은 입자 수를 늘리기보다 자기 관측과 이동 이력에 맞는 후보를 고르는 것이다. 이 파일을 작성하는 시점에는 새 후보 재생·물리 실행을 하지 않았다. 기존 s3fix8의 55001 N100/500 결과는 이미 본 탐색 자료다. 아래 비교도 저장 입력 재분석이며 새 확증 실험이 아니다.

## 선택 규칙

- 55001, 55002, S3 v149/v150의 r1–r3, 총 8궤적 전체를 비교한다. 입력 RGB·발행 명령·seed·카메라/운동 보정·관측 우도·성공 문턱은 고정한다. 후보는 하나(`sensor_mixture_v1`), 기본 off이며 결과를 본 뒤 상수를 바꾸지 않는다.
- 세 열은 100, 500, 새 방법100. 자기 지도는 전체 실행 N이다. **S3 원본은 전역 KLD 최대400000 / 추적2000이며 100이 아니다. S3의 세 열은 같은 원본 전역 초기화를 유지한 뒤 첫 실제 이동에서 추적 입자만100/500/100으로 바꾼 비교**다. 전역 초기화 비용·입자 수는 별도로 기록하고, 이를 전체100입자 전역 위치 찾기라고 부르지 않는다. 원본2000 추적 결과도 참고 행으로 남긴다.
- 채택에는 모든 궤적의 XY RMSE·최종오차 비악화(수치 허용1e-9m), 각 >3σ 비율 비악화, 합친 >3σ 비율의 엄격한 개선, 원본 프레임 전부 처리·예외0이 필요하다. 허위 수렴도 늘면 기각한다. CPU는 새100이 같은 입력500보다 작아야 한다. 하나라도 실패하면 off 유지하고 같은 자료에서 재튜닝하지 않는다.
- 오차/σ 정의는 s3fix6 평가기를 그대로 사용한다. 자기 지도 최고 입자와 혼합 공분산의 중심이 다르므로 eᵀP⁻¹e를 Gaussian NEES 인증으로 해석하지 않는다. 고유 입자 수(좌표 완전 일치 기준), ESS, CPU·wall·부하·peak RSS를 함께 기록한다. 서로 다른 길이의 궤적에서 실패 횟수를 성공률로 바꾸지 않는다.

## 구현 범위

공통 `harness/pf_sensor_proposal.py` 한 곳에 유한 후보 quadrature의 sensor/motion 혼합 제안과 중요도 보정을 둔다. `q=(1−β)p_motion+βp_sensor`, 보정은 `log p_motion + log likelihood − log q`다. 이것은 논문의 kd-tree를 그대로 옮긴 구현이 아니라 기존 격자 관측 모델에 맞춘 **유한 지지집합 근사**이며 그 근사 범위를 기록한다. 저장 프레임의 정답은 선택/가중치/주입/seed에 쓰지 않는다.

자기 지도에는 이미 Grisetti 계열 관측 제안이 있다. 기존 코드가 국소 product를 Gaussian 하나로 요약하는 대신, 같은 관측·명령 공분산이 허용하는 국소 후보를 직접 뽑는다. 자기 지도 입자별 지도/이력을 유지하며 외부 정적 지도나 180도 회전한 가짜 지도는 주지 않는다. S3에는 현재 예측 분포의 국소 후보만 추가한다. 전역에서 이미 표현된 반대 heading 모드는 표본 할당으로 보존하되, 가중치에 할당 확률 보정을 적용하고 관측 후 질량이 사라진 모드를 강제로 살리지 않는다.

지도 자유공간 검사는 S3의 허용된 정적 지도, 자기 지도는 해당 입자에 이미 관측된 지도만 사용한다. 미관측 칸을 자유공간으로 단정하지 않는다. 이동 제약은 직전 예측 분포의 국소 지지집합으로 적용한다. 관측이 맞지 않을 때만 sensor 제안 비율을 올리는 SRL 원칙을 따른다. 모드 할당이 실제 posterior 질량을 인위적으로 늘리면 안 된다.

첫 재생 전 수치 고정: 평상 β=.1, 최고 후보 우도/이동 분포 평균 우도>10일 때만 β=.2. 자기 지도는 기존 coarse/fine 검색과 관측 거부 문턱을 그대로 거친 fine 격자 중 이동 Mahalanobis²≤36·관측된 자유 칸만 사용한다. 지지집합이 없으면 RNG를 추가 소비하지 않고 원래 제안으로 돌아가며 횟수를 공개한다. S3 추적은 예측 입자 분포의 heading 두 반원별 Scott bandwidth(N_eff^−2/7) KDE를3점/축 Gauss-Hermite quadrature(27개 계산 노드/입자)로 근사한다. 계산 노드는 지속 입자가 아니다. 공분산 하한은 없으며 완전히 고갈된 모드를 이 방법으로 복구한다고 주장하지 않는다. 반대 heading 모드의 posterior 질량≥1e−6이면 최소2개를 배정하고 n_mode/N을 포함한 p/q 보정으로 실제 질량을 보존한다. 새 전역 reset이나 가짜 반대 위치를 만들지 않는다. 이 국소 지지집합 밖으로 누적된 편향은 해결 못 할 수 있으며 비교에서 기각될 수 있다.

기존 ESS>N/2 재표본 생략은 유지한다. S3의 새 proposal은 실제 관측 update가 재표본을 필요로 할 때만 실행하고, 건강한 posterior에서 매 프레임 새 노드를 주입하지 않는다. 자기 지도의 기존 selective frame rejection/ESS/입자별 지도 계보도 그대로 유지한다.

정렬 진입은 별도 default-off 옵션으로, `align_start`에서 발행된 현재 카메라 자세와 기존 허용 look 표를 대조한다. 알려진 근접 자세이면 유지하고 알려지지 않은 자세일 때만 기존 search를 쓴다. 성공 receipt/위치 prior는 만들지 않는다. 저장560초 장면의 자기 RGB/명령 이력을 복원한 후 실제 `align_start`를 통과하는 ≤60 SIM초 pair probe 1회와 cyan probe 1회를 수행한다. 종전 실패 MPC는 off다. 세 로봇이 정렬→hover→하강→닫기를 통과하기 전 전체900초 smoke는 하지 않는다. 반복 실패는 원인/영상/실제 이동 표로 남기고 종료한다.

## 참고 자료

- [Thrun, Fox, Burgard, Dellaert, Robust Monte Carlo Localization for Mobile Robots, AI128(2001)](https://robots.stanford.edu/papers/thrun.robust-mcl.html), [원문](https://robots.stanford.edu/papers/thrun.robust-mcl.pdf): §4.2–4.3의 dual sampling과 중요도 보정. 원문은 prior density를 kd-tree로 근사하며 두 sampler의 weight scale도 맞춘다. 관측에 잘 맞는 후보를 균등 가중치로 섞으라는 방법이 아니다.
- [Lenser & Veloso, Sensor Resetting Localization for Poorly Modelled Mobile Robots, ICRA2000](https://www.cs.cmu.edu/~robosoccer/cmrobobits/papers/icra00-srl.pdf): 관측 불일치 때 센서로 후보를 재생성하는 방법. 임의 seed 교체·정답 기반 reset과 구분한다. 우리 적용은 기존 자기 RGB likelihood와 명령 지지집합으로 제한한다.
- [Grisetti, Stachniss, Burgard, Improved Techniques for Grid Mapping with Rao-Blackwellized Particle Filters](https://www2.informatik.uni-freiburg.de/~stachnis/pdf/grisetti07tro.pdf): 기존 자기 지도 구현이 명시한 관측+odometry proposal·ESS 재표본 출처. 이번 변경을 자기 지도 최초의 관측 제안이라고 주장하지 않는다. 이번 원문 재조회는 실패했으므로 신규 원문 검증으로 집계하지 않는다.
- [Coltin & Veloso, Multi-Observation Sensor Resetting, AAAI2011](https://www.cs.cmu.edu/~mmv/papers/11aaai-brian.pdf): SRL의 센서 후보 생성과 관측 불일치 신호를 설명하고, 단일 프레임의 모호한 단서가 잘못된 reset을 유발할 수 있음을 다룬다. 우리 후보는 여러 프레임의 likelihood를 새로 곱하지 않으며, 기존 motion history 지지집합을 유지한다. MOSR 전체 구현이라고 부르지 않는다.
- [SciPy gaussian_kde 문서](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.gaussian_kde.html): 가중 표본의 Scott factor는 N_eff^−1/(d+4), covariance에는 그 제곱을 적용한다. 우리 계산은 입자 모드별 모집단 공분산을 쓰며, SciPy가 특이 공분산에서 자동으로 성공한다는 의미가 아니다.
- [Nav2 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [공식 pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c): KLD의 입자 예산과 resampling은 observation likelihood/모델 편향과 별개다. 500개 비교가100개 후보 배치를 자동 검증하지 않는다.

잠금은 speedctrl2의 진행 중 ABBA 뒤에 사용한다. 재생은 직렬·물리0, 물리는 위 짧은 단계만이며 dev_light/GT eval_only/공유 top 미사용/weld off를 유지한다. 실행 소스 초록→커밋→push, CI 대기0, PR416 병합0. ENOSPC는 HOST_ERROR로 기록하며 원본을 덮어쓰거나 지우지 않는다.

실행 전 검증: 변경3파일30PASS/64.87초. 첫 실제 소비자 시험에서 가상 후보2700개를 실제100개 ESS와 곱하는 진단 decorator의 계약 오류를 발견하여, 후보 점수만 같은 순수 우도로 계산하도록 수정했다. 후보 평가가 active-look 트리거 수를 늘리지 않는 회귀를 포함한다. `align_start`의 자세 보존·unknown 자세의 기존 search 복귀·arm 이동 중 대기·실제 port.apply→발행 자세 일치를 시험했다. 번들v154/workflow7.47.0, 디스크 여유15.26GiB(실행 전 조회), replay+probe 새 raw 예산2GiB. [순번 요청](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/424#issuecomment-6094701715)은55003 ABBA4회 종료 경계이며 다른 실행 중단/잠금 해제는 하지 않는다.
