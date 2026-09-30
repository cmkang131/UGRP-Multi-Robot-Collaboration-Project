# PR #347 독립 검토 — MERGE AFTER FIXES

- 검토 대상: `eaeaaff05553ea02c649b4db9ff82470fe6372b5`, v89.
- 비교 기준: #342 `04eb11c6a001f2a7d2ab916765d59b3661c06efe`, v87.
- 검토 브랜치의 main: `78ce79162d907d88d38ef3afcfc0c62e4a72aaba`.
- 범위: 정적 소스·지도·독립 수식 계산·fake backend 검사. 물리·렌더·모델 호출 0회.
- **현재 head는 병합/수집 인수에 동의하지 않는다.** 아래 세 항목을 한 묶음으로 고친 뒤 변경 범위만 다시 검토한다. 측정용 입력 설계와 실제 gain/τ 식별 성공은 별개다.

## 수정할 항목

### R1 · P1 — 출발점 검사만으로 불확실한 전체 경로를 허용한다

위치: `harness/final_environment_measurement_v2.py:128-134`,
`scripts/check_measurement_v2_identifiability.py:113-122`.

`validate()`는 출발점 여유 0.675 m만 검사한다. 별도 설계 계산도 #346의 최소 격자 후보 하나만 쓴다.
그러나 #346의 확장 격자에서 **그 후보보다 원자료 잔차가 더 작은** 다음 모델들은 배제되지 않았다.
아래는 그 모델로 v89의 실제 명령 전체를 정확 적분한 반례다. 다른 축은 명목 모델로 두었다.
시간은 reset 이후 측정 시작 기준이고, 중단 없이 명령을 모두 따랐을 때의 예측이다.

| 축 | gain / drive τ / stop τ | v1 원자료 RMS | v89 최소 벽 여유 | 0.35 m 인터록 도달 |
|---|---|---|---|---|
| 전진 | 5.529315 / 5 s / 0.05 s | 0.079264 mm | **0.067031 m**, 82 s | 79.25 s |
| 측면 | 21.774201 / 30 s / 0.05 s | 0.054512 mm | **−0.175509 m**, 196 s | 192.90 s |

이는 실제 충돌 관측이 아니라 **현재 불확실성 집합으로 전체 계획의 0.3 m 여유를 증명할 수 없다는 반례**다.
현재 인터록은 정상 작동하면 중간에 수집을 끝낸다. 따라서 230초 전체 식별 입력을 수집한다는 보장도 없다.
사후 substep 이동량 검사와 중단은 실행 전 전체 경로 검사를 대신하지 않는다.

수정: 근거 있는 gain·drive/stop τ·방향 비대칭/횡방향 오차의 허용 집합을 명시하고, 그 집합에서
명령 경계와 경계 사이의 최대 변위까지 포함해 원판–벽 최소 거리를 계산한다. 범위가 없거나
0.3 m와 중단 여유를 만족하지 않으면 backend 생성 전에 거부한다. 실행 중 인터록은 유지한다.
모델 범위를 줄인다면 위 대안을 제외할 독립 근거를 제시하거나 입력·배치를 다시 설계한다.

반례: `test_admitted_path_keeps_30cm_for_unexcluded_v1_models`의 두 축, strict xfail 2개.

### R2 · P2 — 두 번째 이후 형상의 NaN을 놓친다

위치: `sim/final_environment_measurement_v2.py:100-105`.

형상별 반경을 먼저 `max()`로 합친 뒤 합계 하나만 `isfinite()`로 검사한다.
Python에서 `max([0.1, NaN]) == 0.1`이므로, 첫 형상은 정상이고 두 번째 형상의
`geom_rbound` 또는 `geom_xpos`가 NaN이면 `guard(check_geometry=True)`가 **0.675 m를 반환하며 계속 허용**한다.
현재 테스트의 차체 xy NaN 검사는 이 경우를 잡지 않는다.

수정: 선택한 **각 형상의 위치·반경·계산 거리**가 유한하고 반경이 유효한지 먼저 검사한다.
하나라도 잘못되면 hold와 abort 기록을 남기고 종료한다.

반례: `test_every_geometry_must_be_finite_before_admission`, strict xfail 2개.

### R3 · P2 — v1 Fisher 계산이 실제 적합 창과 다르다

위치: `scripts/check_measurement_v2_identifiability.py:100-105`.

주석은 독립적인 4초 창 두 개를 복제한다고 쓰지만, 실제 코드는 양/음 명령을 한 8초 궤적으로
연결하여 위치를 이어 적분한다(41행). #346은 각 창의 시작 위치를 빼고 21행씩 적합했다(42행).
음의 창은 앞 창의 최종 위치를 공유하지 않는다. 올바른 Fisher는 `J_plusᵀJ_plus + J_minusᵀJ_minus`다.

같은 σ=0.1 mm·stop τ 고정 가정에서 독립 재계산한 조건수는 전진 **18,523.6**, 측면 **92,735.1**이다.
현재 문서의 10,032.7 / 50,610.6과 다르다. 같은 stop 격자에서 τ 20% 대안 최소 RMS는
**0.030015 / 0.010292 mm**다. **v1의 실용적 모호성이라는 결론은 그대로 유지된다.**

수정: v1의 독립 창·초기 상태·표본 집합을 원래 적합기와 맞추고 표·JSON·관련 설계 지표를 다시 계산한다.
이미 보존한 설계 기록은 덮어쓰지 말고 수정 근거와 새 결과를 덧붙인다.

반례: `test_v1_fisher_matches_the_two_actual_fit_windows`, strict xfail 2개.

## 식별성의 독립 재계산과 적용 한계

일정 명령 u, 구간 h, 시간상수 q에 대해 `a = exp(−h/q)`라 두면:

```text
v_next = G*u + (v − G*u)*a
x_next = x + G*u*h + (v − G*u)*q*(1−a)
q = drive τ (u != 0), stop τ (u == 0)
J = [∂x/∂log G, ∂x/∂log drive τ]
F = Jᵀ J / σ²
G_hat(q) = <x_unit(q), y> / <x_unit(q), x_unit(q)>
```

프로젝트의 적분기를 호출하지 않은 별도 식으로 검산했다. 기존 적분기와 최대 차이는
4.5e−15 m 미만이다. v2의 조건수 **206.460 / 123.319**, 격자 분리 **3.235968 / 5.323245 mm**는 맞다.
stop τ를 연속 0.005–2초에서 최적화하고 drive τ의 ±20% 밖을 탐색해도,
찾은 최소치는 전진 **3.167259 mm**, 측면 **5.218809 mm**로 분리가 유지됐다.
이는 수치 탐색 결과이며 연속 전역 최솟값의 엄밀한 증명은 아니다.

v1은 무잡음에서 구조적으로 식별 불가능한 모델이 아니다. Fisher는 full rank지만 실제 짧은 입력에서
gain과 τ가 강하게 얽힌다. 독립 42행 창에서 stop τ까지 nuisance로 둔 Fisher의
가상 IID σ=0.1 mm `SD(log drive τ)`는 전진 **12.38%**, 측면 **34.27%**다.
v2를 같은 1차 모델로 놓고 더 큰 잡음과 시간 상관을 넣은 민감도는 다음과 같다.
초기 위치·속도는 알려진 것으로 두었고, AR(1) 상관시간 0.5초는 `ρ=exp(−0.05/0.5)`로 계산했다.

| v2 가상 오차 | 전진 SD(log drive τ) | 측면 SD(log drive τ) |
|---|---|---|
| 1 mm, IID | 0.136% | 0.089% |
| 1 mm, 상관시간 0.5초 | 0.568% | 0.357% |
| 5 mm, 상관시간 0.5초 | 2.839% | 1.785% |

따라서 **후보 1차 모델과 이 가상 잡음 아래에서 v2 입력은 충분히 정보를 준다.** 이 표는 실측 신뢰구간이 아니다.
#346의 0.0898/0.0776 mm 잔차는 무작위 센서 잡음 추정치가 아니다. 첫 1초의 잔차 RMS는
0.1781/0.1552 mm이고, 양/음 궤적은 부호를 바꾸면 최대 0.000061/0.000125 mm 차이뿐이다.
즉 거의 같은 결정적 오차를 반복하며, 이를 20 Hz 독립 잡음 표본으로 세면 안 된다.

실제 모델 구조도 정확한 1차식은 아니다. `sim/multi_masterpi_production.py:1473-1492`에는
별도의 모터 상태 지연과 차체 관성·속도 감쇠·접촉력이 있다. 기본 모터 τ=0.085초
(`sim/masterpi_dynamics_v2.py:127`)는 0.05초 표본당 약 1.7개뿐이다.
소프트웨어 명령은 ±0.03에서 clipping 범위 안이지만, 바퀴 actuator에는 ±0.002 N·m 힘 제한이 있고
바퀴 접촉·마찰은 남는다(`sim/masterpi_dynamics_v2.py:407-437,733-744`).
차체 명령의 명시적 deadband는 보이지 않으며 `servo_deadband_pwm`는 팔용이다.
다만 접촉에 따른 유효 무응답 영역·방향 비대칭·횡방향/yaw slip까지 배제한 것은 아니다.

실측 후 3크기×양음의 정상속도/τ 일치, 정지 구간, 계단으로 적합한 모델의 별도 PRBS 잔차와
잔차–입력 상관, 모터 지연을 포함한 2상태 모델과의 차이를 확인해야 한다.
plateau 부재·격자 경계·체계적 잔차면 기각한다는 기존 제한은 타당하다.
**현재 자료만으로 현실적인 오차 전체에 대한 v2 식별 성공이나 단일 gain/τ 모델의 적합성을 확정할 수 없다.**
이는 측정 설계 검토의 한계이며 물리 실행을 수행한 것처럼 채우지 않았다.

## 나머지 요청 항목

| 항목 | 확인 결과 |
|---|---|
| v87/v1 보존 | base Git blob과 보존 목록 166파일의 실제 바이트·SHA-256 일치. v87 생성 번들 9개도 원래 digest와 동일. v1 JSON SHA-256 `7d19bcc3e88dac4f906d4f0db9b5aef7fb7969e795b3c709a632ea45962d045e`. |
| v89 변경 범위 | 기존 map·v3 모델·contact·floor_light·weld off·센서 설정 유지. 새 측정/실행기/상한/배치/표본/인터록 및 버전 변경만 확인. v89 closure는 상위 161파일 + 신규 5파일. |
| 정적 거리 | 벽 표면과 원판 거리 계산, 벽 합집합 면적, 지도 선택은 맞다. 두 문 지도 28.9675 m², 명목 경로 최소 0.675 m. R1의 불확실성 범위는 빠져 있다. |
| 상한·정렬 | 2 + 2×(6×16 + 31×0.5 + 2.5) = 230초. reset 최대 5초로 235초. 4,600명령·초기 포함 4,601 pose. 모든 경계 0.05초 격자, lease 갱신, 내부 dt 정렬과 reset 포함 cap wrapper 확인. |
| GT 경계 | 새 스케줄에는 pose 인자가 없다. GT는 `eval_only`와 수집 전체 중단만 사용. 실제 실행 경로에서 학생/provider factory를 만들거나 평가값을 반환하는 경로 없음. 번들의 상속 provider 항목은 기존 메타데이터다. |
| 번호 | 조회 시점 main + 열린 PR 19개 head를 확인. v89 선언은 #347 하나, v88은 #344 `zone-final-pair-v88` 하나. 번호 조회 시점의 SHA 목록은 결과 JSON에 보존. |

## 검사·보관

- 관련 오프라인 테스트: **112개 통과 + 27 subtests 통과**. 신규 measurement 파일 자체는 33개 통과.
- 첫 묶음은 110 통과/3 실패였다. 압축 해제본에 Git 이력이 없어 실패한 provider 의존성 2개는
  `GIT_DIR=/Users/changmin/projects/ugrp/.git`로 역사적 fixture 조회만 연결한 재실행에서 통과했다.
- 남은 1개 `WorkflowManagerTests::test_parent_exit_cleans_background_child`는 sandbox의 `ps` 금지로
  검증 불가다. PR 회귀라고 분류하지 않는다. 초기 실패 JUnit도 보존했다.
- 리뷰 검사: **2 passed, 6 strict xfailed**. xfail은 위 세 지적의 재현이며 안전성 통과 수가 아니다.
- GitHub에서 같은 head의 33 checks 성공을 확인했다. CI 성공이 R1–R3을 해소하지 않는다.
- `.github/workflows`, 측정 구현, 기존 raw·스냅샷은 수정하지 않았다. 검토 기록과 테스트만 추가했다.
- 수치·조회 head·검사 기록 위치/해시는 [REVIEW_347_RESULTS.json](REVIEW_347_RESULTS.json)에 있다.
  이 리뷰는 기존 설계의 수식·회귀 검토다. 새 물리/학습 코호트나 TensorBoard 스냅샷을 만들지 않았다.

재현(압축 해제 경로를 지정하고 완료 후 제거):

```sh
UGRP_REVIEW_347_ROOT=/absolute/archive/root \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q tests/test_review_347.py -rx
```

외부 자료는 방법·모델 의미만 확인했다. PR의 수치는 위 독립 계산으로 검증했다.
[MathWorks idinput](https://www.mathworks.com/help/ident/ref/idinput.html)은 PRBS의 clock·대역폭·진폭 설계를 설명한다.
[MuJoCo computation](https://mujoco.readthedocs.io/en/stable/computation/index.html#contact)은 접촉 마찰과 slip의 의미를 설명하며,
noslip 설정이 임의 운동에서 정확한 대각 1차 모델을 보증하지는 않는다.
