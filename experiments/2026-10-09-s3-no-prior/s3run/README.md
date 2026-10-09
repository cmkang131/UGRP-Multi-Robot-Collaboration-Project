# S3 heading smoke: pre-smoke r1 diagnosis (2026-10-09)

**원인 한 줄:** 보정한 저장 영상에서 r1은 유한한 초기 입자와 초기 재표본화로 정확한 가설의 세밀한 표본이 부족해져, 약 180° 반대 방향의 근사 가설이 우세해졌다. 관측 순서 자체나 다른 로봇 가림을 주원인으로 지지하지 않는다.

아래는 **오프라인 진단**이다. 원본 s14201, own RGB/명령만 필터 입력이며 `legacy_centered_replay_v1`은 옛 렌더 영상과 맞추는 진단용 합성이다. 실제 스모크는 제어기 보정 변경 없이 호스트 `v3_persistent_v1`로 렌더한다. GT는 저장 posterior 평가에만 사용했다. 카메라 보정 적용을 공통 조건으로 고정하고 각 비교에서 한 요인만 바꿨다.

| r1 재생 조건 | 첫 σ 기준 수렴 | 마지막 XY 오차 | yaw 오차 | σxy | 판정 |
|---|---:|---:|---:|---:|---|
| 원래 seed14201·관측 순서, 43.55s | 없음 | 4.262512m | 179.6025° | 0.270649m | 실제 오위치 |
| S2 pan 순서만 적용, 14.00s | 없음 | 4.262616m | 179.5867° | 0.215436m | 순서 교환으로 해결 안 됨 |
| 필터 seed만1065, 14.00s | 10.30s, 오차0.032042m | 0.032074m | 0.2050° | 0.042933m | 정확 σ 수렴; seed 진단이지 채택/확증 아님 |

관측 순서 비교는 같은 body-frame 측정 packet의 순서만 S2의2030→1500→1770→1230→970으로 바꿨다. 새 pan 물리 실행은 아니다. 세 조건 모두 6개의 관측(2.25,3.75,5.25,6.75,8.25,10.10s)이며 원래 몸체 이동 명령은0이다. 첫 σ 기준은 기존 XY≤0.05m·yaw≤5°, 정확성은 별도 eval_only XY≤0.25m·yaw≤15°이다.

- 원래 r1에서 고유 입자 수는100,000→540→27로 줄었다. 정확 영역(0.25m·15°)의 고유 입자는34→17→9로 줄고 이후 복제593개가 유지됐다. 따라서 **정답 영역 입자 전멸은 아니다**.
- 정확 영역 posterior 질량은 첫 두 관측0.054095→0.287643에서 마지막0.004276으로 감소했다. 살아남은 가장 강한 정확 영역 표본은 실제 시작보다0.13433m·3.33867° 벗어나 있었다. 정지 명령 동안 새로운 위치 표본은 생성되지 않는다.
- 최종 반대 방향 가설/정확 GT 위치의 여섯 관측 결합 우도 비는0.042558(정확 위치가23.50배 유리)이다. 이는 완전한 관측 대칭보다는 유한 표본 근사의 문제를 지지한다. GT 점수는 **사후 진단**이며 필터에 주입하지 않았다.
- seed1065만 바꾸면 정확 영역 질량이 두 번째 관측에서0.974669, 마지막0.999970으로 증가한다. seed 교체가 초기 표본 및 이후 resampling 난수를 함께 바꾸므로 둘의 개별 기여는 아직 분리하지 않았다.
- 기존 시작 자세 비교는 S2와 약24µm·0.001° 차이이며, r1 타 로봇 마스크는 측정 변화0이었다. 본 결과는 같은 저장 입력에 대한 개발 진단이며 새 물리 성능이 아니다.

## 스모크 전 결정

seed14201·원래 관측 정책·v141 입자 및 σ 문턱 유지, **추가 회복 옵션 off**. 기존 필터에 augmented recovery가 이미 있고 정확 영역 지원도 남아 있으므로 무작위 주입이나 우도 바닥값을 추가하는 것이 적절한지는 아직 실증되지 않았다. 올바른 호스트 v3 렌더와 능동 관측을 먼저 한 번 관찰한다. 이 결정은 물리 실행 전에 고정했다. 결과를 보고 seed/문턱을 고르지 않는다.

표준 방법 조사: [Doucet–Johansen particle filtering tutorial](https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF.pdf)의 재표본화에 따른 다양성 감소와 rejuvenation, [Nav2 AMCL pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c)의 KLD 및 random recovery를 확인했다. 현재 어댑터는 stationary global KLD 최소2000/최대100000, ESS≤N/2 resampling, slow/fast recovery를 이미 사용한다. 새 kernel·주입률의 적합성을 검증하지 않은 상태에서 본 스모크에 추가하지 않는다.

원본/분석 raw: `/Users/changmin/projects/ugrp/outputs/s3run-20261009`; 원본 replay 도구와 corrected baseline은 `../s3diag/` 및 해당 raw 폴더. `r1-support-analysis.json`에 입력 경로·명령·seed·simulation_runs=0·GT 경계가 있다. 큰 particle cloud는 로컬 raw에 보존하며 삭제하지 않았다.

검증: 호스트 렌더 회귀2 passed, 새 물리 실행0. TensorBoard `1009-s3run-r1` 3조건/18스칼라를 EventAccumulator로 대조했고, 기존6006 서버의 실제 UI에서3개 run·6개 pin과4.2625/4.2626/0.0321m 값을 확인했다. HParams 열은case/family/outcome/evaluation로 적용했다. [대시보드](http://127.0.0.1:6006/?runFilter=%5E1009-s3run-r1%2F#timeseries), 전체 pinned URL은 `tensorboard-verification.json`에 보존한다.

## 실행 전 고정: v146 / workflow7.39.0

18:47:53 fetch에서 #419 공통 기본 on `d89912703432117e47b5306bbe50ec9c31a0663c` 확인 후 merge했다. main#420 `1ba3668b`의 exact relay cache도 포함한다. [번호 예약](reservation.json)은 main/열린 PR 전부의 최대v145/7.38.0 확인이다. 미실행·미승인 준비 번들v144를 퇴역하고 **v146**을 새로 등록한다. v144 물리 결과는 없으며 그 사전 기록은s3next와Git이력에 보존한다.

[실행 등록](registration.json): seed14201 혼합 주문1회,1800 SIM초/10800wall초,dev_light,host v3 persistent binding on,공통 heading 기본 on,heading visual lock off,추가 입자 회복off,기존 수렴 문턱. 원본 예산2.125GiB+10GiB reserve,agent_lock 획득 후 실행. host는 실제 적용된 `relay-cache-v1`/enabled를 확인한다. 결과의 heading 및speed 적용값은 공통 writer가 기록한다.

heading 적용 범위를 구분한다: 세 S2 계열 startup localizer에 동일한 기본 on을 연결하고 실제 회전→전진 생성과 기록을 시험한다. **r3의 단독 경로 주행**이 그 제어기를 계속 사용하며, r1/r2 handoff 이후의 공동 빔 자세·GO 합의는 #419의 명시적 설계대로 기존 공동 제어기를 유지한다. 공동 빔의 독립 로봇 회전을 검증했다고 보고하지 않는다. 과거v142의 옵션 누락은 명시적 off로 해석해 기존 재생을 보존한다. 새로운 물리 실행에는 v146의 명시적 on을 쓴다.

실행 직전 디스크 갱신: 여유12.23GiB로 감소하여 raw 상한을2.125GiB로 사전 조정했다. 옛 실행 실측 비율의1800초 투영1,721,403,567bytes+추가eval허용536,870,912bytes=2.103GiB보다 크다. 이는 추정이며 보장하지 않는다.10GiB 또는raw 상한에 도달하면 ENOSPC HOST_ERROR로 기록하고 자동 재시도하지 않는다. 기존raw 삭제0.

실행 소스 검증: S3/공통 heading/workflow 관련3개 파일41 passed(115.19s). raw 예산 조정 뒤 계약 시험1 passed(42.76s). 실제 S3 factory의 각 localizer에 `path_tangent_v1` 적용, 자기 추정 stub에서 회전→전진 생성, result 적용값 및v142 누락 옵션off 보존을 확인했다. 기존 호스트 첫 렌더 mount 회귀는2 passed. 시험은 물리 실행 성공 근거가 아니다. CI는 기다리지 않는다.
