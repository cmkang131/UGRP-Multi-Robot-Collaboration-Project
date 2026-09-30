# 무하중 전진·측면 식별 측정 v2 — 설계 검증

## 2026-10-01 독립 검토 반영 — 후속 실행 차단, 명령 보존

[REVIEW_347.md](REVIEW_347.md)의 R1–R3을 한 묶음으로 반영했다. 아래 원래 설계 기록과
`design_before_plan.json`, `identifiability.json`, 기존 TensorBoard snapshot은 그대로 보존한다.
수정 계산은 [identifiability_review_fixed.json](identifiability_review_fixed.json)에 별도로 남겼다.

- R1: 모든 명령 구간과 구간 내부 이동을 덮는 원판–벽 여유 하한을 계산한다. 양/음 gain,
  drive/stop τ, 초기 상태 오차, 횡방향·yaw·slip을 포함한 축별 속도 오차의 범위가 필요하다.
  현재는 이를 뒷받침하는 독립 근거가 없고 #346의 배제되지 않은 대안도 여유를 위반한다.
  따라서 출발점/명목 모델만으로 허용하지 않고 **backend 생성 전 거부**한다. 계획 조회는
  `runnable=false`와 반례를 표시한다. 기존 실행 중 인터록은 유지한다.
- R2: 로봇의 각 형상에서 xyz·반경·계산 거리를 먼저 검사한다. NaN/Inf·음수 반경·범위 초과는
  hold와 abort 기록 후 중단한다. 두 번째 형상의 NaN도 빠뜨리지 않는다.
- R3: v1 양·음의 4초 창을 각각 x=v=0에서 시작한 **21+21표본**으로 계산한다.
  Fisher와 stop τ를 profile한 잔차 모두 같은 독립 창을 사용한다.

| 수정된 v1 | Fisher 조건수 | τ 20% 이상 대안 최소 RMS |
|---|---:|---:|
| 전진 | 18,523.6155 | 0.030015 mm |
| 측면 | 92,735.1010 | 0.010292 mm |

아래 과거 표의 v1 수치는 위 값으로 정정한다. v2 수치와 v1의 실용적 모호성 결론은 유지한다.
Fisher의 σ는 가상 오차이며, 결정적·시간 상관 잔차를 독립 잡음이나 실측 신뢰구간으로 해석하지 않는다.

**이미 수집된 자료와 모델 한계:** [#348](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/348)은
`eaeaaff0`/v89에서 r1 명령 4,600개와 최소 관측 벽 여유 0.675 m를 기록했다. 해당 기록은
입력 크기에 따른 gain 변화와 유효 deadband 때문에 **선형 1차 모델이 부적합**함을 보여준다.
이는 이 설계의 모델 가정에 알려진 한계다. 한 번의 수집으로 운동 범위를 좁히거나 안전을 보증하지 않는다.
`configs/final_environment_measurement_v2.json`은 원래 SHA-256
`bda01f670febea5d5d298ac0e707515f956d25d2cc1c412c8690047bf86ed402`와 바이트가 같고,
4,600개 명령도 보존했다. 새 번호를 만들지 않으며 #348은 같은 v89 명령 등록의 자료로 유지한다.
실행 소스는 계속 `eaeaaff0`로 표시하며 수정 head에서 다시 수집한 것으로 바꾸지 않는다.

이번 작업은 오프라인 수정·검증만 수행했다. 상세 결과는 [REVIEW_FIXES.md](REVIEW_FIXES.md)를 따른다.

## 원래 설계 기록 (eaeaaff0, 위 정정 전)

Refs #342 #346. **물리·렌더·모델 호출은 0회이며, 측정 보정값을 만들지 않았다.**
기준 코드는 #342 `04eb11c6a001f2a7d2ab916765d59b3661c06efe`다.
#346의 적합 보고서와 저장소의 v2 drive/stop 방법을 읽고 순수 NumPy 1차 모델로 입력을 설계했다.
보고서 branch SHA·전체 번호 조회는 [reservation_scan.json](reservation_scan.json)에 있다.

## 변경

새 설정 [measurement v2](../../configs/final_environment_measurement_v2.json)는 지도 1개·r1 무하중의
전진/측면 각각 양·음 3크기 계단(0.01/0.02/0.03, 각 15초)과 31칩 PRBS(±0.02, 칩 0.5초)를 고정한다.
축마다 114초, 초기 정지 2초로 230초, reset 최대 5초 포함 **235 SIM초**다.
PRBS는 `x^5+x^2+1`, 초기 11111의 최대 길이 31주기이며, 출력 bits도 설정에 보존했다.
step·PRBS 경계와 sample은 같은 0.05초 격자다. 큰 입력에서의 비선형성/방향 비대칭은
크기별·양음별 실측으로 확인하며, 대각 선형 모델로 가정해서 숨기지 않는다.

벽 합집합 면적을 정확 계산하면 two_doors의 빈 바닥이 28.9675 m²로 가장 크다
(door 28.9175, corridor 28.7775). r1은 이 지도의 빈 동쪽 바닥 (3.25, −0.85)에 정적 reset한다.
지도·벽·카메라·물체·접촉 파라미터는 그대로다. r1 reset 배치는 새 번들에 명시한 진단 조건이다.
0.35 m 보수적 원판 기준 시작/후보 예측 경로의 벽 여유는 최소 0.675 m다.
실제 수집에서는 벽 여유 0.35 m에서 중단하는 private physics 인터록을 추가했다.
정답은 eval-only 기록과 전체 수집 중단에만 쓰며, 명령·단계 보정이나 학생 입력으로 반환하지 않는다.
모델 예측만으로 실제 벽 간격을 보증하지 않는다.

pose는 `eval_only/r1/pose.jsonl`에 0.05초마다, 초기/종료 포함 4,601행을 저장한다.
RGB는 5초 간격이며 pose 저장 때문에 추가 렌더하지 않는다. pan sweep은 없고 기본 search 자세다.
회전·stop τ는 20 Hz로 10표본/τ를 확보할 수 없어 이번 확정 대상에서 제외한다.

## 계획을 쓰기 전 확인한 식별성

[design_before_plan.json](design_before_plan.json)을 **설정 JSON 작성 전에** 생성했다.
이후 설정에 쓰인 같은 구간을 읽어 [identifiability.json](identifiability.json)으로 다시 확인했다.
기존 v2의 `dv/dt=(G u-v)/τ` 모델에서 drive/stop τ를 나누고 VIS4 `lag_integral`을 직접 호출해
위치를 정확 적분한다. #346 표의 탐색 후보인 전진 `(G=1.78459, τ=1.44, stop=0.08)`과
측면 `(2.40680, 3.00, 0.05)`를 사용한다. 후보값은 실측 확정값이 아니다.

v1의 0.25초×4 연속 갱신은 끊김 없는 1초 입력이다. 양·음 각각 주행 1초+정지 3초를
0.2초 간격으로 관찰한다. 짧은 펄스를 서로 독립인 4회로 세지 않았다.
gain은 각 τ에서 최소제곱으로 profile하고, drive τ=0.05–100초 로그 격자와 후보/±20% 지점,
stop τ=0.03/0.05/0.08/0.12/0.2/0.3/0.44/1초를 함께 탐색했다.
20% 이상 다른 drive τ 중 가장 작은 **위치 RMS 차이**를 비교했다.

| 설계 | 축 | log gain/log τ Fisher 조건수 | τ 20% 이상 대안의 최소 RMS 차이 |
|---|---|---:|---:|
| v1, 0.2초 표본 | 전진 | 10,032.7 | 0.0310 mm |
| v2, 0.05초 표본 | 전진 | 206.5 | 3.2360 mm |
| v1, 0.2초 표본 | 측면 | 50,610.6 | 0.0106 mm |
| v2, 0.05초 표본 | 측면 | 123.3 | 5.3232 mm |

Fisher는 `JᵀJ/σ²`, J는 log gain/log τ에 대한 위치 감도다. stop τ를 고정한 조건부 국소 지표이며,
별도 잔차 격자에서는 stop τ도 profile한다. σ=**0.1 mm**는 #346의 0.0776–0.0898 mm 잔차 수준을
반올림한 설계상 분해능 가정이다. IID 측정 잡음·신뢰구간·물리 불확실성의 추정치가 아니다.
판정은 다른 τ의 최소 RMS 차이가 이 분해능의 5배를 넘는지다. v1은 실패, v2는 두 축 모두 통과한다.
무잡음·무한 정밀도에서 v1이 수학적으로 구조 식별 불가능하다는 주장은 하지 않는다.

15초 계단은 최대 **설계** drive τ=3초의 5배이고, 표본은 후보 τ당 28.8/60개다.
#346에서는 더 긴 τ도 비슷하거나 더 좋은 잔차를 냈으므로 이 계산은 실제 식별 성공을 보장하지 않는다.
실제 plateau 부재·격자 경계·양음/크기별 불일치·PRBS 예측 오차가 남으면 식별 실패로 보고한다.
장시간 τ=30–100초까지 235초 예산 안에서 6개 정상상태 계단으로 모두 보장할 수는 없다.
이 경우 자료를 보존하고 후속 설계를 정하며, gain/τ를 임의로 채우거나 P03에 투입하지 않는다.

## 등록·검증·보존

main + 열린 PR 18개 branch 전체의 RUNNABLE_ID·bundle ID·workflow catalog를 확인했다.
#339 v86, #342 v87, #344 v88 이후의 **v89**를 사용한다. 통합 floor-light 2.x 계열 최대 2.20.0의
다음 **2.21.0**을 쓴다. 독립 pair-v3 workflow의 3.1.0과 구분한다.
새 check는 후속 floor-light catalog ID에 등록했다. 같은 ID 덮어쓰기와 v87 pinned source 수정은 없다.
[v87 보존 목록](v87_preservation.json)은 원래 파일 166개와 9개 생성 번들의 해시를 고정한다.
v1 JSON, `.github/workflows`, 기존 provider/학생 factory는 수정하지 않는다.

테스트는 상한·표본 시각·정상 명령·고정 양음/크기·PRBS·정적 벽 여유·비유한 값·중단/자원 정리·
source SHA/잠금/덮어쓰기 거부·격자 식별성·기존 번들 보존을 검사한다.
MuJoCo/Torch/worker import와 네트워크를 차단하고 fake backend만 사용한다.
관련 회귀 **152개 통과**, 카탈로그 수정 후 새 측정·의존성 재검증 **76개 통과**(일부 중복),
27개 subtest 통과다. 기존 프로세스 정리 테스트 1개는 sandbox의 `ps` 거부로 로컬 확인 불가,
선택 native render 테스트 1개는 건너뛰었다. 원래 실패 2개는 새 catalog 수/예제 누락이었으며
수정 후 재검증했다. 명령·검증 파일 해시는 [validation.json](validation.json)에 기록한다.
정적 실행 계획 확인은 물리 완주, 정상상태 수집 또는 보정 적합 완료를 뜻하지 않는다.

```sh
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$PY" -m scripts.check_measurement_v2_identifiability \
  --config configs/final_environment_measurement_v2.json --output /private/tmp/measurement-v2-check-NEW.json
"$PY" -m pytest -q tests/test_final_environment_measurement_v2.py \
  tests/test_zone_final_environment_floor_light.py tests/test_zone_final_environment_runnable.py
```

수집용 정확 명령·잠금·판정은 [PHYSICS_HANDOFF_MEASUREMENT_V2.md](../../PHYSICS_HANDOFF_MEASUREMENT_V2.md)에 있다.
raw는 코디네이터가 기본 `outputs/`에 새로 수집한다. 이 구현에서 raw를 생성하거나 압축 해제하지 않았다.
설계 수치의 [TensorBoard](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ffisher_condition%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fprofiled_tau20_rms_m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpose_sample_period_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fsamples_per_drive_tau%22%7D%5D&smoothing=0&runFilter=%5E1001-v89-design%2F#timeseries)는 합성 v1/v2 × 두 축 4개 snapshot이며
실제 scalar **16개**를 HTTP로 읽어 원본과 일치함을 확인했다. 기존 서버 logdir는 공용
`outputs/tensorboard`다. [변환·로딩 기록](tensorboard_record.json). Chrome 연결이
`cgWindowNotFound`로 실패해 고정 카드·HParams 열의 화면 검증은 미완료다. 새 서버·영상은 만들지 않았다.

## 참고 자료

- [Ljung, *System Identification: Theory for the User*, 2nd ed., 1999 — 저자 홈페이지](https://www.control.isy.liu.se/books/sysid/).
  입력 설계·정보량·식별 가능성을 구분하는 시스템 식별 방법론을 따른다.
- [MathWorks, idinput](https://www.mathworks.com/help/ident/ref/idinput.html): 동적 범위를 자극하는 대역폭의
  입력 설계, PRBS의 clock period·진폭·최대 길이 주기. 실제 MATLAB 실행이나 라이브러리 의존성은 없다.
- [저장소 v2 drive/stop 적합법](../2026-09-26-zone-owncam-loop-v2/fit_stop_dynamics.py):
  drive+coast 창, 분리된 τ, 최소제곱 gain, τ 격자. 적분은 [VIS4 lag_integral](../2026-09-26-vision-loc/vision_motion.py)을 재사용한다.
- [#346 식별 실패·후보값](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/346),
  [#342 v87 수집 경로](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/342).
