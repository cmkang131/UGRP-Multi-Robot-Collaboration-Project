# v87/v89 무하중 오프라인 보정 — PARTIAL_UNLOADED_SIM

## r4 / criterion B — 2026-10-01, CANDIDATE_UNVALIDATED

### r3 이후 코디네이터 결정 (2026-10-01)

**r3 전에 고정한 criterion A는 FAILED이며 계속 실패로 남는다. A를 다시 채점하지 않는다.**
소비자는 영상 위치 보정 사이에 추측 항법을 하는 자기 카메라 PF
(`harness/owncam_localizer.py`)다. 이 용도에서는 덜 모델링된 동역학에 대한 PF의 강건성을 위해
보수적인 과정 잡음을 쓰는 것이 허용되며 표준적인 접근이다
([Thrun·Burgard·Fox, 2005, ch. 4–5; noise inflation](https://robots.stanford.edu/probabilistic-robotics/)).
따라서 **r3를 본 뒤, 새 자료를 얻기 전인 지금 새로운 criterion B를 정의한다.**
B는 앞으로 #344에서 수집할 **다른 지도의 새로운 v88 무하중 held-out 자료로만 검증**한다.
그 수집에서 어느 축에 계단/PRBS 운동이 없으면 그 축은 미검증이다.

- 평균은 기존 소비자 필드로 표현할 수 있는 부호 공통 gain·주행 tau·정지 tau의 단순 3파라미터
  모델이다. v89의 계단과 PRBS 모두로 적합한다. **모든 v89 자료는 이제 훈련 자료다.**
- 잡음은 기존 `sigma_velocity = noise_rel*|v| + noise_abs` 형식을 쓴다.
  M1 PF 예산 이상인 가장 작은 값으로, v89 훈련의 0.2–3.2초 모든 예측 시간·성분에서
  2σ 포함률 95% 이상을 맞춘다. 잡음 확대는 허용하고 포함률 상한은 두지 않으며 NEES를 보고한다.
- 새로운 held-out 자료에서 모든 시간·성분의 `p95 |error| <= 2σ` 및 2σ 포함률 90% 이상일 때만
  통과다. 1σ 포함률과 NEES는 참고로 보고한다. **미검증 축의 판정/적용값은 null이다.**

[고정 criterion B](consumer_criterion_B.json)의 SHA-256:
`74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`.
수치 판정은 0.2/0.5/1/2/3/3.2초에서 지도·축·계단/PRBS·성분을 각각 검사한다.
σ가 창마다 다르므로 p95 조건은 `p95(|error_i|/sigma_i) <= 2`로 고정했다.
오차 p95와 σ p95를 따로 비교하지 않는다. 모든 시작점을 포함하고 잔차 평균을 빼지 않는다.
서로 겹치는 창의 포함률은 독립 표본의 통계적 보증이 아니다.

### 훈련 후보와 잡음의 최소값

[r4 후보](calibration_candidate_r4.json)는 **CANDIDATE_UNVALIDATED**이며 `MEASURED_SIM`이 아니다.
전진·측면 숫자는 `candidate_axes`에만 있고, 회전 후보·세 축 `axis_validation`·활성
`params.motion`은 null이다. r1/r2/r3 파일과 criterion A는 바이트 그대로 보존했다.
후보 SHA-256: `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071`.

| v89 전체로 적합한 축 | gain | 주행 tau (s) | 정지 tau (s) | 모든 훈련 그룹 중 최저 2σ 포함률 |
|---|---:|---:|---:|---:|
| 전진 | 1.23714309 | 0.79779096 | 0.08897856 | 100% |
| 측면 | 0.85096032 | 0.78771022 | 0.08846192 | 95.0065% |
| 회전 | null | null | null | null |

기존 PF와 같은 0.05초 **끝 속도 Euler 적분**을 적합·채점했다. r3의 연속시간 정확 적분과 다르다.
시작 pose만 이상적인 영상 보정 기준으로 사용하고, 숨은 속도는 기록 처음부터 발행 명령으로만
누적한다. 실제 속도·접촉·미래 pose는 예측 입력이 아니다. 공분산은 heading 결합을 포함하는
선형화된 white process 예산이며, 위치 보정/scale/roughening 잡음으로 통과를 보충하지 않았다.

두 축 후보가 공유하는 `[forward,left,yaw]` 잡음은 다음과 같다.

| 필드 | M1 하한 | r4 후보 |
|---|---|---|
| `noise_rel` | [0.3176, 0.4438, 0.1116] | 동일 |
| `noise_abs` (m/s, m/s, rad/s) | [0.01538, 0.00504, 0.01406] | [0.01538, **0.012767691858458299**, 0.01406] |

relative/absolute 사이에는 교환관계가 있어 유일한 성분별 최솟값이 일반적으로 존재하지 않는다.
이를 숨기지 않고 B에 **relative 세 값 → yaw absolute → forward absolute → left absolute**의
사전식 최소화 순서를 명시했다. relative는 M1 하한을 유지하고, 각 창의 이차 분산식에서 필요한
absolute 하한을 풀어 그룹별 `ceil(0.95*n)`번째 순서통계량의 최댓값을 택한다.
확대한 값에만 수치 오차 여유 `1e-12`를 더했다. 이 순서에서의 정확한 최소값이며 Pareto 최소값이다.
다른 relative/absolute 조합보다 모든 계수가 동시에 작다는 주장은 아니다.

제약을 결정한 것은 측면 계단 3.2초의 **1,542창 중 1,465창**이다.
확대 전 M1 하한은 이 그룹에서 66.67%였다. 확대 후 모든 그룹·성분이 95% 이상이다.
PRBS 3.2초(축별 297창)의 구동 성분 p95는 전진 5.829 mm·측면 4.799 mm이고,
1σ/2σ 포함률은 두 축 모두 100/100%, 구동 성분 평균 NEES는 0.2152/0.1952다.
**이것은 훈련 결과이며 B의 held-out 통과가 아니다.** 각 성분의 NEES·공동 NEES·σ 범위와
모든 시간/구간 수치는 [전체 훈련/스모크 보고서](consumer_report_r4.json)에 있다.

### 기존 로더가 받아들여야 하는 것 — 이번에는 수정하지 않음

후보의 `loader_requirements`에 정확한 요구사항을 저장했다. 현재 로더의 r4 거부도 회귀로 확인한다.

1. schema v1의 새 `CANDIDATE_UNVALIDATED` 상태를 명시적인 무하중 후보 경로에서만 인정하고,
   B/후보 해시와 미검증 상태를 보존해야 한다. `MEASURED_SIM`으로 이름만 바꿔서는 안 된다.
2. null인 `params.motion` 대신 `candidate_axes.<axis>.consumer_fields`를 선택해야 한다.
   그 안의 `gain`, `tau_s`, `tau_stop_s`, `noise_rel`, `noise_abs`, `scale_std`, `scale_walk`,
   `use_scale`, `rest_noise`는 기존 소비자 필드다. 선택 축 이외 gain은 구조적 0이며 미측정 축을
   보정한 값이 아니다. 특이 gain 행렬을 허용하되 **그 축의 단독 명령만 허용**해야 한다.
3. 정지 tau는 축마다 다르지만 현재 소비자는 스칼라 `tau_stop_s`만 처리한다.
   축별 프로필 선택 없이 벡터 stop tau나 혼합 명령을 넣을 수 없다. 회전은 null이고
   M1/v87 값을 몰래 채워 넣지 않는다. 전체 3축 프로필 적용은 별도 문제다.
4. 채점과 같은 0.05초 끝 속도 적분·기존 잡음식·`rest_noise=true`, `use_scale=false`,
   `scale_std=scale_walk=0`를 사용해야 한다.
5. 기존 최종환경/P03 및 #344의 pair 로더는 완전한 loaded/fine/카메라/pair `MEASURED_SIM`
   산출물을 요구한다. 제한된 무하중 후보 경로만 누락을 허용할 수 있으며 P03/carry 승인은 아니다.
   상속한 v87 카메라/pan·계약 해시와 v89 운동 훈련·향후 v88 검증 출처를 분리해야 한다.
   계약 해시를 v88 값으로 단순 치환해서도 안 된다.

### 새 raw 검증과 #344 회전 일정 확인

[검증기](../../scripts/validate_consumer_criterion_b.py)는 재적합하지 않는다. 완료된 수집의
bundle/measurement 일정과 발행 명령·lease·시계·pose 개수/행렬을 대조하고, 입력 해시를 실행 후
다시 확인한다. 이미 본 pose 바이트·훈련 지도는 held-out에서 제외한다.
새 자료가 실제 B 고정 뒤 수집됐는지는 수집 기록으로도 확인해야 하며, 해시만으로 시점을 증명하지 않는다.

```sh
python3 -m scripts.validate_consumer_criterion_b \
  --raw /absolute/path/to/NEW-v88-unloaded-collection \
  --output /absolute/path/outside-raw/criterion_B_result.json
```

종료 코드는 전체 통과 0, 실패 1, 미검증 축/훈련/부적격 2다. 잘못되거나 미완료인 raw는 오류로 거부한다.
v89 실제 raw 스모크는 `TRAINING_SMOKE`, 세 축 판정 null, 종료 2를 확인했다.
step/PRBS가 없는 축뿐 아니라 **고정 후보가 없는 회전축도 계속 null**이다.
새 회전 수집으로 회전 평균을 적합하려면 그 자료는 훈련이 되며, 회전 검증에는 다시 독립 자료가 필요하다.

`origin/codex/v3-pair-adapter`의 지정 SHA `b7bc885a27aa5ab242e9f3710a3cd7090efe9f3a`를
직접 확인했다. `harness/zone_final_pair_excitation.py`의 `AXES`에는 turn이 있으며,
무하중 일정은 ±.01/±.02/±.03 각각 10초 계단+1초 coast, ±.02 PRBS 31칩×0.5초,
마지막 2.5초 coast를 포함한다. 회전 구간은 242–326초다.
**이미 회전 입력이 있으므로 50초 회전안을 추가하라는 #344 댓글은 쓰지 않았다.**
다만 현재 #344는 `zone_wide_two_doors_final_v3` 한 지도만 수집하도록 제한되어 있어
**그대로 수집하면 B의 ‘다른 지도’ held-out 조건을 충족하지 못한다.** 수집 측의 별도 변경이 필요하다.

재현용 [적합기](../../scripts/fit_consumer_criterion_b.py), [입력/소스 해시](input_manifest_r4.json),
[검사](../../tests/test_consumer_criterion_b.py), [검증 기록](validation_r4.json),
[TensorBoard 기록](tensorboard_record_r4.json)을 함께 남긴다. 원본과 스모크 JSON은
로컬 `outputs/v89-consumer-r4-final-20261001`에 보존한다. 원격 raw 백업은 아니다.
물리·렌더·모델 호출은 0회이며 제어기·`.github/workflows`를 수정하지 않았다. draft를 유지한다.

관련 오프라인 검사 **중복 제외 284개**가 통과했다(새 검증기 파일 33개).
합성 raw의 CLI 판정, 실제 consumer 메서드에서 생성한 3파라미터 복원, 잡음 최소값을 조금 낮춘
실패 반례, 누락/변조 입력 거부, A 바이트 보존과 기존 로더 거부를 포함한다.
[TensorBoard](http://127.0.0.1:6006/?runFilter=%5E1001-v89-consumer-%28r3%7Cr4-final%29%2F#timeseries)에
새 훈련 결과 24 runs·실제 scalar 288개·HParams 이벤트 24개를 등록하고 서버 값과 대조했다.
r3는 실패한 A의 별도 기준선으로 유지한다. [고정 카드·열 설정](tensorboard_record_r4.json)은 저장했지만
Chrome `cgWindowNotFound`로 화면 검증은 미완료다. 새 영상/서버는 없고 기존 서버는 변경하지 않았다.
`/private/tmp`에 이 작업의 extraction 디렉터리를 만들지 않았고 잔여 디렉터리도 없다.

## r3: 짧은 예측은 개선, 잡음 검증 실패로 적용값 null

**기준 A 미통과.** [r3 교정](calibration_partial_r3.json)의 전진·측면·회전 적용 모델은 모두 null이다.
회색상자 모델의 3.2초 위치 오차 p95는 전진 **0.370 mm**, 측면 **0.433 mm**로 작지만,
계단 자료에서 맞춘 잡음이 PRBS 오차의 크기·분포를 설명하지 못했다. 작은 평균 오차와 잡음 보정 통과는 다르다.
기존 [r1](calibration_partial.json)·[r2](calibration_partial_r2.json) 바이트는 유지했다.
제어기·`.github/workflows`를 변경하거나 물리·렌더·모델 호출을 실행하지 않았다. **draft 유지, 미병합**이다.

### 소비자와 먼저 고정한 기준 A

검증 전에 [기준 파일](consumer_criterion_r3.json)을 저장하고 해시
`49b7ffbbc07425dda3d2f2410c480ea6ee1315a1c831f97e75efc6989164391c`를 고정했다.
이미 r1/r2에서 본 v89 탐색 자료를 다시 분석한 것으로, 새 확증이나 실제 PF 위치 추정 성능 시험이 아니다.

| 소비자 근거 | 실제 사용 방식 | 이번 검증 범위 |
|---|---|---|
| `scripts/run_m1_owncam.py:30`, `scripts/run_m2_pair.py:65` | own RGB 기회 간격 0.2초, 제어 tick 0.1초 | 영상마다 위치 보정 성공을 가정하지 않음 |
| `harness/owncam_drive_shared.py:51`, `owncam_drive.py:55` | 무하중은 마지막 보정 후 **3초 초과** 때 다시 보기 시작 | 0.2·0.5·1·2·3·3.2초를 모두 검사 |
| `harness/zone_final_environment.py:93` | 최종 환경의 지각 지연 설정 0.16초 | 3.2초는 지연/tick 주변 스트레스 구간이며 성공한 보정 간격의 상한 보장이 아님 |
| `harness/vision_pose_source_p03.py:95–113` | M1 보정과 `22c84842`의 hash-frozen PF 사용 | frozen `predict_to`와 오프라인 비교식의 수치 일치 검사; 모델/영상 추론 없음 |
| `harness/owncam_localizer.py:270`, frozen PF `:188` | 0.05초마다 gain 행렬·1차 속도, 끝 속도로 위치 적분, 속도 잡음·지속 scale 오차 | 새 후보 평균과 기존 소비자 평균을 따로 계산 |
| `vision_pose_source_p03.py:232–267` | 자세가 정착되고 영상 관측이 유효해야 보정 | 이번 분석은 정확한 시작 위치·방향을 준 이상적인 보정 후 예측만 측정 |
| `owncam_drive_v2.py:30` | 하중 주행은 거리 0.5 m 기준으로 다시 보기 | loaded/fine·조작·혼합축/회전·장시간 무관측은 대상 밖 |

기존 무하중 잡음은 [M1 보정](../2026-09-26-zone-m1-owncam/calibration_m1_dev.json)의 다음 값이다.
`sigma_velocity = noise_rel * abs(velocity) + noise_abs`이며 매 step 위치 잡음 분산은
`sigma_velocity² * dt²`다. `dt`를 곱하는 연속 백색잡음과 혼동하지 않았다.
방향 오차가 다음 위치 오차에 미치는 영향도 공분산에 전파했다.

| 파라미터 | 전진 | 측면 | 방향 |
|---|---:|---:|---:|
| noise_rel | 0.3176 | 0.4438 | 0.1116 |
| noise_abs (m/s, m/s, rad/s) | 0.01538 | 0.00504 | 0.01406 |
| scale_std | 0.2148 | 0.2148 | 0.2148 |
| scale_walk (/√s) | 0.01 | 0.01 | 0.01 |

실제 보정 직후 scale의 사후 분산은 이 자료에 없다. 따라서 **매 step 백색잡음만으로 만든 보수적인 예산**을
채택 기준으로 삼았다. 초기 scale_std와 scale_walk까지 더한 분산도 보고하지만 통과를 구제하는 데 쓰지 않는다.
지도 가중치·재초기화·영상 측정 잡음도 예산에 더하지 않았다. 이 비교는 PF 전체의 안전 보장이 아니다.

| 항목 | 검증 전에 정한 기준 |
|---|---|
| 훈련 | 축별 부호·크기 6개의 계단+정지, 평균 모델과 잡음 모두 여기서만 적합 |
| 검증 | 축별 연속 PRBS+정지 1개; 분할 경계를 넘지 않는 **모든 0.05초 시작점** |
| 위치·방향 오차 | 각 시작점의 실제 위치·방향을 이상적인 영상 보정으로 사용; 끝점만 채점에 사용 |
| 숨은 속도·모터 상태 | 전체 기록 시작부터 명령으로만 누적; 창마다 0 또는 측정 속도로 재설정하지 않음 |
| 기존 PF 예산 | 세 성분 각각 p95 절대오차 ≤ 기존 백색잡음 2σ; 새 σ/기존 σ의 p95 ≤ 1 |
| 잡음 보정 | 각 구간·성분별 1σ 포함률 60–76%, 2σ 90–99%, 평균 정규화 제곱오차(NEES/성분) 0.5–2 |
| 선택 | 3개 자유변수의 gain+1차부터, 다음 5개 변수 회색상자; 모든 구간에서 통과한 가장 단순한 모델 |
| 실패 처리 | 수렴·rank·경계 확인; 최소 100창/구간; 하나라도 실패하면 그 축 적용값 null |

1σ/2σ 기준은 Gaussian의 68.27%/95.45%, NEES/성분=1 주위에 정한 공학적 허용폭이다.
겹치는 창과 한 번의 결정론적 SIM 기록은 독립 표본이 아니므로 통계적 신뢰구간으로 해석하지 않는다.
잡음을 과하게 키워 100%를 덮는 경우도 실패로 처리한다.

### 평균 모델과 알려진 구조

단순 모델은 부호 공통 gain·주행 tau·정지 tau 3개다. 기존 VIS4의 정확 1차 적분 형태를 사용하되
기존 scored P03의 끝 속도 적분과 같다고 주장하지 않는다.
회색상자는 ABAB 혼합과 `wheel_target=12*motor_state`, **0.085초 모터 지연**, **질량 1.1 kg**을 고정한다.
`1.1*v_dot = drive_sign*wheel_target - D(command)*v - Fc*tanh(v/0.002)`로 접촉을 근사하고
양/음 drive·주행 감쇠·정지 감쇠·마찰력 5개만 적합한다.
0.002 m/s는 고정한 마찰 평활 근사값이며 MuJoCo의 알려진 상수가 아니다.
차체 힘과 실제 바퀴 접촉의 효과는 유효 drive 계수에 함께 들어가므로 바퀴 힘 자체를 식별했다고 주장하지 않는다.
무하중 단일 축·clip 비활성 자료에서만 ABAB 역투영을 스칼라로 줄였다.

| 축 | 단순 gain | 주행 tau (s) | 정지 tau (s) | 회색상자 drive ± (N/(rad/s)) | 주행 감쇠 (N·s/m) | 정지 감쇠 (N·s/m) | 마찰력 (N) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 전진 | 1.24175 | 0.83581 | 0.06439 | 0.186160 / 0.186160 | 1.42138 | 17.92046 | 0.0109704 |
| 측면 | 0.85477 | 0.83097 | 0.06194 | 0.139397 / 0.139397 | 1.41855 | 18.47390 | 0.0108043 |

두 모델 모두 계단의 다중 구간 위치 잔차만 최소화했다. 네 적합 모두 수렴·full rank·경계 비접촉이다.
회색상자의 적분 허용오차를 100배 줄여도 위치 변화는 전진 7.2e-9 m, 측면 6.3e-9 m 이하다.
이는 수치 적분 확인이며 새 물리 실행이 아니다. 후보 수치는 [전체 보고서](consumer_report_r3.json)에만 있다.

### 모든 시작점에서 얻은 PRBS 예측 오차

아래는 위치 오차 크기의 p95다. 방향 평균 예측은 0으로 두고 관측된 표류를 빠짐없이 별도 채점했다.
같은 축의 두 후보는 방향 예측이 같으므로 방향 오차도 같다.

| 예측 구간 (s) | 축별 창 수 | 전진 단순 (mm) | 전진 회색상자 (mm) | 측면 단순 (mm) | 측면 회색상자 (mm) | 측면 구동 중 방향 p95 (°) |
|---|---:|---:|---:|---:|---:|---:|
| 0.2 | 357 | 0.784 | 0.101 | 0.582 | 0.047 | 0.02294 |
| 0.5 | 351 | 1.838 | 0.191 | 1.351 | 0.095 | 0.05017 |
| 1.0 | 341 | 2.695 | 0.259 | 2.171 | 0.164 | 0.08987 |
| 2.0 | 321 | 4.534 | 0.296 | 3.651 | 0.290 | 0.13572 |
| 3.0 | 301 | 6.530 | 0.362 | 5.277 | 0.416 | 0.13796 |
| 3.2 | 297 | 6.795 | 0.370 | 5.501 | 0.433 | 0.14287 |

전진 구동의 방향 p95는 구간별 1.45e-6–6.51e-6°로 사실상 수치 수준이다. 이를 회전 정확도 검증으로 세지 않는다.
계단은 축별 10,368창, PRBS는 축별 1,968창(구간별 창의 합, 중복 시각 포함)이다.
전체 분포의 bias·RMS·p50/p90/p95/p99/max, 정지 포함·반전 포함 창, 기존 PF 평균 예측 오차도 보고서에 있다.
각 시작점의 오차·분산·분류는 로컬 `outputs/v89-consumer-r3-final-20261001/window_residuals_r3.npz`에 저장했다.
파일 해시와 열 정의는 보고서의 `windows_artifact`에 있다. 이 로컬 파일은 원격 백업이 아니다.

### 잡음 적합·포함률: 채택을 막은 근거

Thrun·Burgard·Fox 5장의 이동량 비례 오차를 유한 구간의 mecanum 예측에 맞춰 사용했다.
성분은 **구동 방향/직교 방향/방향각**이다. 명령으로 예측한 절대 이동거리 L과 구간 h에 대해
`variance_j = q_j*h + alpha_j*L²`를 쓰고, 평균을 빼지 않은 계단 잔차에 비음수 Gaussian 준최대우도를 적합했다.
alpha1은 구동 방향, alpha3는 방향각의 이동거리 제곱 계수이고 alpha_lateral은 mecanum 직교 성분 확장이다.
회전에 비례하는 alpha2/alpha4는 **회전 명령 0개로 식별 불가 → null**이다.
책의 전체 6-alpha velocity sampler를 그대로 구현했다고 주장하지 않는다.

| 후보 | q (구동/직교/방향, 분산/s) | alpha1 | alpha_lateral | alpha3 | alpha2/alpha4 |
|---|---|---:|---:|---:|---|
| 전진 단순 | 1.225e-5 / 1.574e-19 / 1.885e-17 | 2.263e-9 | 1.743e-22 | 5.264e-21 | null / null |
| 전진 회색상자 | 7.329e-10 / 1.574e-19 / 1.885e-17 | 1.097e-13 | 3.466e-22 | 5.352e-21 | null / null |
| 측면 단순 | 1.111e-5 / 8.398e-20 / 1.314e-7 | 5.522e-10 | 3.012e-7 | 0.002540 | null / null |
| 측면 회색상자 | 3.753e-9 / 6.033e-20 / 4.017e-7 | 8.843e-13 | 3.376e-7 | 0.001651 | null / null |

다음은 **3.2초 PRBS**의 진단이다. 각 셀은 구동/직교/방향 순서다. 전체 여섯 구간이 모두 통과해야 한다.

| 후보 | 1σ 포함률 (%) | 2σ 포함률 (%) | 평균 NEES/성분 | 새 σ/기존 PF σ p95의 최댓값 | A |
|---|---|---|---|---:|---|
| 전진 단순 | 90.2 / 12.1 / 4.0 | 100 / 19.2 / 20.5 | 0.38 / 25.54 / 38.84 | 0.812 | 실패 |
| 전진 회색상자 | 20.2 / 12.1 / 4.0 | 32.0 / 19.2 / 20.5 | 17.30 / 25.54 / 38.84 | 0.0063 | 실패 |
| 측면 단순 | 100 / 71.0 / 60.3 | 100 / 91.6 / 94.9 | 0.28 / 1.04 / 1.14 | 1.704 | 실패 |
| 측면 회색상자 | 39.1 / 72.4 / 70.0 | 61.3 / 92.6 / 100 | 4.62 / 0.98 / 0.82 | 0.309 | 실패 |

회색상자는 기존 PF 잡음 예산보다 훨씬 작은 위치 오차를 내지만, 계단의 작은 잔차로 맞춘 σ가 반전이 있는
PRBS의 구동 오차를 과소평가한다. 단순 모델의 구동 잡음은 PRBS를 과하게 덮고, 측면은 기존 예산도 넘는다.
전진의 직교·방향 잔차는 수치 수준이어서 큰 NEES를 실제 로봇 위험의 크기로 읽으면 안 된다.
그 성분을 제외해도 회색상자의 **구동 성분**이 실패한다. PRBS를 보고 잡음을 재조정하지 않았다.

**기존 소비자는 r3를 변경 없이 사용할 수 없다.** 최종 환경 로더는 schema v1+MEASURED_SIM만 받고,
현재 r3는 schema v3+PARTIAL이다. 선택된 평균/잡음 모델도 없다.
향후 통과한 단순 gain·tau는 기존 필드로 표현할 수 있으나, 정확 적분 적용 여부와 새 구간별 공분산 규칙은
별도 구현·검증해야 한다. 회색상자는 모터/차체 상태와 비선형 힘도 필요하다. 이 PR은 소비자를 바꾸지 않는다.

### 회전 추가 수집 제안 — 실행하지 않음

v89 turn 명령은 0개다. v87 ±0.03 두 계단으로 회전 gain·잡음·반전 검증을 대신하지 않는다.
다음은 최소 회전 식별/검증 입력 제안이며 새 실행 번들 등록이나 실행 승인이 아니다.
같은 v3 환경·팔 자세·무하중·weld OFF를 유지하고 turn 이외 두 축은 0, 명령 lease와
eval_only 위치/방향 표본은 0.05초다. 기존 v89 수집기의 turn 금지를 풀 별도 수집 변경·검토가 필요하다.

| SIM 시각 (s) | 명령 | 용도 |
|---|---|---|
| 0–2 | hold | 초기 정착 |
| 2–7 | turn +0.01, 4초 → hold 1초 | 계단 훈련 |
| 7–12 | turn −0.01, 4초 → hold 1초 | 계단 훈련 |
| 12–17 | turn +0.02, 4초 → hold 1초 | 계단 훈련 |
| 17–22 | turn −0.02, 4초 → hold 1초 | 계단 훈련 |
| 22–27 | turn +0.03, 4초 → hold 1초 | 계단 훈련 |
| 27–32 | turn −0.03, 4초 → hold 1초 | 계단 훈련 |
| 32–47.5 | turn ±0.02, 31칩×0.5초 PRBS | 따로 보존할 검증 입력 |
| 47.5–50 | hold | 정지 검증 |

합계 **50 SIM초**, reset 준비를 최대 5초 따로 잡아도 **55초 ≤60초**다.
PRBS 부호는 수집 전에 다음 31칩으로 고정한다(+는 +.02, −는 −.02):
`+++++---++-+++-+-+----+--+-++--` (v89 전진 입력의 31칩 순서를 회전축에 적용).
0.05초 전체 pose 1,001개와 명령/적용 설정/소스 해시를 남긴다.
이는 회전 계수 식별을 위한 최소 1회 자료이며 독립 반복의 잡음 일반화·혼합 이동·loaded 보정을 완료하지 않는다.

### r3 산출물·재현·참고 자료

[적합기](../../scripts/fit_unloaded_consumer.py), [기준](consumer_criterion_r3.json),
[모든 후보·판정](consumer_report_r3.json), [입력 해시](input_manifest_r3.json),
[r3 교정](calibration_partial_r3.json), [오프라인 검사](../../tests/test_unloaded_consumer.py)를 함께 보존한다.
입력은 v89 수집 SHA `eaeaaff05553ea02c649b4db9ff82470fe6372b5`이며 v87 카메라 출처는 이전 리비전대로 유지한다.
적합 당시 HEAD는 `8feab578`이고 새 적합 소스·기준·소비자·검사 파일의 정확한 바이트는 manifest 해시로 고정했다.
원본 읽기 전후 불변을 확인했다. `/private/tmp`에 extraction 디렉터리를 만들지 않았다.

```sh
python3 -m scripts.fit_unloaded_consumer \
  --raw /Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001 \
  --output /Users/changmin/projects/ugrp/outputs/v89-consumer-r3-NEW
python3 -m pytest -q tests/test_unloaded_consumer.py tests/test_unloaded_hammerstein.py \
  tests/test_final_environment_unloaded_fit.py
```

관련 오프라인 검사 **중복 제외 251개 통과**(새 검사 17개 포함). frozen PF 실제 메서드와 예측식 일치,
독립 행렬 지수와 회색상자 적분 일치, 숨은 상태의 GT 비의존성, 잡음 계수 회복·과대/과소 포함률 거부,
r1/r2 바이트 보존·null 판정·CI 목록을 검사했다. 첫 r2 해시 검사 실패는 과거 소스를 새 작업 트리와
비교하던 문제였으며, 과거 커밋을 검사하도록 고친 뒤 변경 범위 168개와 해당 검사 단독 1개가 통과했다.

검증·TensorBoard 상태는 [validation_r3.json](validation_r3.json), [tensorboard_record_r3.json](tensorboard_record_r3.json)에 기록한다.
[TensorBoard r3](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fposition_p95_mm%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fold_mean_position_p95_mm%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fheading_p95_deg%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Falong_1sigma_percent%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Falong_2sigma_percent%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22gate%2Fcriterion_A%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0&runFilter=%5E1001-v89-consumer-r3%2F#timeseries)에서 24 runs·스칼라 264개·HParams 이벤트 24개를 실제 읽어 원본과 대조했다.
기존 PF 평균 예측 오차를 같은 구간의 비교 태그로 함께 표시하며 새 영상은 없다. 공용 서버는 변경하지 않았다.
Chrome `cgWindowNotFound`로 고정 카드·HParams 열의 화면 확인은 미완료다.

| 참고 자료 | 이번 적용 |
|---|---|
| Thrun, Burgard, Fox (2005), *Probabilistic Robotics*, ch. 5 Robot Motion — [저자 자료](https://robots.stanford.edu/probabilistic-robotics/), [motion models 강의](https://robots.stanford.edu/probabilistic-robotics/ppt/motion-models.ppt) | 이동·회전량에 비례한 오차 계수와 확률 운동 모델. mecanum 및 유한 구간 확장은 위에 명시 |
| Ljung (1999), *System Identification: Theory for the User*, 2판, 물리 파라미터 모델 pp. 95–97·ch. 16 검증 — [출판사 목차](https://www.informit.com/store/system-identification-theory-for-the-user-9780132440530), [해당 쪽을 인용한 공식 회색상자 예](https://www.mathworks.com/help/ident/ug/estimating-nonlinear-grey-box-models.html) | 알려진 상태방정식을 고정하고 적은 유효 파라미터만 적합, 소비 목적에 맞는 별도 입력 검증 |

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
