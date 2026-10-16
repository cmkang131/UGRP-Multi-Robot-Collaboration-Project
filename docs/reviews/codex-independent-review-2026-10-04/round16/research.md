# R16 — carry-align의 1.96σ 보류 규칙은 무엇을 뜻하는가

2026-10-04. #363 exact `66ff0978a817caa949d2d738b51d7ae89dd17e71`. source와 authored scalar/pose 대조만 사용했다. 실제 calibration 수치·RGB·PF·접촉·운반·heldout·LLM을 실행하거나 열지 않았다. 새 구현 변경 및 새 버그 주장이 아니다. 최신 공개 af2f7c2a stage는 도크 출발 guard 또는 정렬 중 재관측에서 멈춰 carry-align에 도달하지 못했으므로 이 규칙의 현재 폐루프 효과도 관측됐다고 쓰지 않는다([R15 공개 상태](../round15/research.md)).

**결론:** 이 규칙은 불확실한 보정을 보류하는 일관된 정책 선택이다. 그러나 `skip`은 작은 실제 오차의 인증이 아니며, `95%`는 보정의 물리적 안전성·공동 운반 성공률을 뜻하지 않는다. 특히 코드에서 보정 중심과 σ의 출처가 다르므로, 한 Gaussian posterior의 구간이라는 해석은 조건부다. 먼저 `door_align_gate`와 저장 `grasp_pose_estimate`/현재 report를 연결해 **어떤 시점의 어느 residual을 어떤 covariance로 판단했는지** 확인하는 것이 다음 최소 판별이다.

## 1. 실제 규칙, 변수와 시점

| 항목 | 실제 source 계약 | 해석 범위 |
|---|---|---|
| 보정 중심 | [V3Controller.door_schedule:167–184](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_final_pair_skill.py#L167-L184): `dy=clip(route[seg].y−grasp_estimate.y,±.15m)`; `e_yaw=clip(wrap(static heading_rid−grasp_estimate.yaw),±.20rad)` | world y 위치와 world heading에 대한 **이미 clipped된 예정 보정**이다. beam 상대 영상 오차나 두 로봇 사이의 상대 오차가 아니다. |
| 초기 mean 저장 | [PairGraspRelook:181–200](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_grasp.py#L181-L200), [256–277](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_grasp.py#L256-L277) | b-v6g는 `beam_relative=False`, `posterior_relook=True`다. pregrasp는 uncalibrated VO를 지우고 자기 pose report의 world mean을 `grasp_estimate`에 저장한다. 옛 M2 VO 경로를 현재 입력이라고 쓰지 않는다. |
| checkpoint mean 갱신 | [HighController._wait_carry:257–290](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_runtime.py#L257-L290) | post-stop fix, freshness, σ 한도, minimum wait를 통과하면 저장 mean을 현재 report mean으로 다시 쓴다. 매 tick 또는 모든 초기 carry GO에서 자동 갱신하는 것은 아니다. 이후 별도 부모 carry barrier가 있다. |
| σ | [own_sigmas:57–74](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_carry_align.py#L57-L74), [gate:96–114](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_carry_align.py#L96-L114) | schedule 시점 `last_report`의 `sqrt(cov_yy)` [m]와 `std_yaw_rad` [rad]. covariance가 사용 불가하면 `std_xy_m`으로 대체; usable σ가 없으면 부모 명령을 그대로 유지한다. |
| 분산 정의 | [OwnCamLocalizer.estimate:517–531](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/owncam_localizer.py#L517-L531) | particle mean과 wrap한 yaw residual의 보정 weighted covariance; `std_xy=sqrt(cov_xx+cov_yy)`. σ는 미반올림 covariance에서 계산하고 출력 cov는 소수점 8자리로 반올림한다. posterior 표준편차를 particle 수의 제곱근으로 다시 나누는 규칙이 아니다. |
| 행동 선택 | `abs(dy)>Z*sigma_y`, `abs(e_yaw)>Z*sigma_yaw`, `Z=1.959963984540054`를 성분별 적용 | 모두 keep이면 부모 명령 동일, 모두 skip이면 all-zero mecanum, 한 성분만 keep이면 부모 motion-model 식으로 다시 계산. 축간 gain coupling이 있을 수 있어 motor command 성분 하나를 단순 지우는 규칙은 아니다. |

현재 covariance/report 연결은 [독립 source QA](validation.md#carry-alignment)에서 default RobustPF mean 경로부터 base covariance까지 확인했다. VIS3 estimate에는 commanded-pan에 따른 yaw **mean** 보정이 있지만 cov/std는 유지된다. 이를 native provider 생성·실제 uncertainty calibration 검증으로 쓰지 않는다.

`std_xy` fallback은 같은 **미반올림** finite PSD position covariance에서 나온 값이라면 `sqrt(cov_yy)` 이상이므로 **그 수학적 비교에서는** skip을 더 쉽게 만든다. 실제 report의 반올림 cov 원소와 σ 사이에 bit-exact 부등식을 보장한다는 뜻은 아니다. 또한 임의의 불완전/서로 다른 출처 report를 안전한 covariance로 인증하지 않는다. 이번 검토는 고의 invalid covariance fuzz를 하지 않았다.

`HighController.door_schedule`은 부모의 schedule 계산 뒤 gate를 적용한다([runtime:292–295](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_runtime.py#L292-L295)). 부모는 raw command admissibility를 먼저 검사하고 `pair_plan`을 설치한다. 따라서 새 gate는 임의의 큰/무효 부모 명령을 구제하는 전역 validator도 아니다. 검토한 양성 대조에서는 align 6초, 다음 .5초 pause, planned leg와 pair_plan이 모두 유지됐다. 실제 loaded gate·uncertainty abort·guard를 이번 pure fixture로 대신 검증하지 않았다.

## 2. ‘95%’의 정확한 조건

이 표현은 검토자가 덧붙인 것이 아니다. 새 모듈 [docstring:15–23](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/66ff0978a817caa949d2d738b51d7ae89dd17e71/harness/zone_pair_highpose_carry_align.py#L15-L23)은 own Gaussian posterior의 양측 95% 수준이라고 설명한다.

정적 목표와 같은 시점·같은 정보 집합에서 얻은 scalar 위치 오차가 실제로 `δ|H ~ N(μ,σ²)`라면 `|μ|>Zσ`는 그 marginal central 95% interval이 0을 제외하는 것과 같다. 이는 조건부 모델 안의 구간 의미다. frequentist 반복실험 coverage라고 쓰려면 별도의 estimator/error 가정이 필요하다.

현재 적용에서 다음 조건을 확인해야 한다.

1. **center/cov 대응:** 저장 `grasp_estimate`와 현재 `last_report`가 서로 다른 시점이다. 그 사이 평균이 바뀌지 않거나, stored residual에 대해 current σ를 쓰는 명시적 보수적 모델이 있어야 같은 posterior interval이라고 해석할 수 있다. 새로운 report mean이 변해도 이 gate는 그 mean을 읽지 않는다. 이 사실 자체는 의도된 저장 포즈 기반 정책과 모순되지 않는다.
2. **clipping:** 비교 대상은 raw error가 아니라 ±.15m/±.20rad로 잘린 correction이다. 일반적으로 clipped variable은 원래 Gaussian 분포와 같지 않고 그 분산도 자동으로 원래 σ²가 되지 않는다. 다만 cap=L에서 `Zσ<L`이면 `|clip(r,±L)|>Zσ`와 `|r|>Zσ`의 **binary keep 결정은 정확히 같다.** 예컨대 σ_y≤.07m, σ_yaw≤3°이면 이 조건을 만족한다. 이 값들이 실제 schedule 생성 때 강제됨을 이번 pure fixture가 증명하는 것은 아니다. 이번 source 대조는 clipping 사용을 확인했으며 clipping 때문에 실제 운반이 오판됐다고 주장하지 않는다.
3. **모델과 bias:** PF의 spread가 작다는 사실만으로 세계좌표 오차의 bias·calibration/model mismatch가 작다고 인증할 수 없다. 이 gate는 bias를 별도 추정하거나 보정하지 않는다. 실제 calibration failure·현재 bias 크기를 측정한 것은 아니다.
4. **marginal과 joint:** 각 축의 marginal 구간 의미는 축간 상관이 있어도 정의할 수 있다. 두 축 또는 두 로봇을 합친 95% 보증은 아니다. 가상의 독립 95% 구간 두 개의 동시 coverage만 해도 `.95²=.9025`다. 현재 로봇들/축들이 독립이라고 가정한 수치가 아니다.

normal CDF의 수학적 기준은 NIST 공식 분포 문서로 확인했다. 실용적으로 무시할 수 있는 범위와 uncertainty interval을 구분하는 Kruschke(2018)의 원문도 검토했다. 그 논문의 HDI+ROPE를 현재 제어기에 이식하라는 권고는 아니다. **zero가 배제되지 않았다는 판정**과 **작은 허용 오차 안에 있다고 확인했다는 판정**이 다른 질문이라는 근거만 사용한다. [1차 근거/읽은 범위](primary-sources.md)

## 3. 실행한 최소 합성 대조

`carry-align-decision-repro.py` (Mac 전달본 증거)는 66ff 원문 14파일의 hash를 확인하고 실제 `V3Controller.door_schedule`, `motor_command`, `HighController.door_schedule/_wait_carry`, `gate_schedule`, lag와 raw-action validator를 실행한다. AST로 필요한 함수/메서드만 가져오며, motion profile·pose report·정적 짧은 route는 authored 값이다. HIGH의 부모 barrier는 호출 기록용 대역이다. sensor/PF/guard/robot/물리 시간은 실행하지 않았다. `carry-align-decision-results.json` (Mac 전달본 증거)

| 대조 | 관측한 결과 | 반박한 과도한 해석 |
|---|---|---|
| 같은 `dy=.04m`, σ_y=.005 vs .03m | 전자는 lateral keep, 후자는 skip | skip이 residual의 절대 크기만 작은 상태를 의미한다. |
| 양 성분 significant / 양쪽 insignificant / yaw만 significant | 각각 부모 명령 그대로 / all-zero / 실제 부모 motion-model로 yaw-only 재계산. align window·rest·pair_plan 동일 | gate가 반드시 시간표를 단축하거나 전체 planned leg를 지운다. |
| exact `dy=Zσ` / 다음 representable float | 경계에서는 skip, 바로 위에서 keep | rule이 `>=`이거나 별도 숨은 ε를 적용한다. |
| stored mean은 zero, current report mean만 world y 0→−.04m, σ=.005m 동일 | schedule/결정 동일 | 현재 report mean이 바뀌면 자동으로 예정 correction이 바뀐다. |
| 위 report mean으로 `grasp_estimate`를 명시 갱신한 대조 | lateral keep으로 바뀜 | mean provenance 차이가 이 pure gate에서 무관하다. |
| 실제 HIGH checkpoint hook에 fresh post-stop report / old fix / checkpoint 없는 초기 경우 | fresh는 stored mean 갱신 후 parent barrier로 위임; old fix는 갱신·위임 없음; 초기 경우는 저장 mean 유지 후 위임 | checkpoint나 매 초기 GO가 항상 같은 방식으로 center를 새로 읽는다. |
| usable σ 없음 | 부모 schedule 그대로, `NO_OWN_SIGMA` | 이 함수가 missing uncertainty에서 전역 fail-closed 한다. 외부 guard의 별도 의미는 유지된다. |

old-fix fixture에서도 gate 결과를 비교하려고 **분석용으로만** `door_schedule`을 직접 호출했다. 실제 `_wait_carry`는 그 대조에서 부모 barrier에 위임하지 않았다. 그 분석용 schedule을 실제 GO나 발행된 운동으로 세지 않는다. 또 fresh checkpoint fixture는 현재 알려진 endpoint의 더 앞선 guard를 통과할 수 있음을 검증하는 것이 아니라 해당 mean-refresh 분기만 검증한다.

## 4. 보류를 작은 오차 인증으로 읽으면 안 되는 수치 증인

가상의 scalar Gaussian posterior `μ=.04m, σ=.03m`이면 gate는 skip한다. 그 95% interval은 약 `[-.018799,.098799]m`다. **분석용으로만** 허용 오차를 ±.01m라고 놓으면 이 모델에서 밖에 있을 확률은 약 `.889135`다. 이 .01m는 UGRP의 새 허용치도 권고 threshold도 아니며, .889는 실제 로봇의 충돌·실패 확률이 아니다. 오차가 작다고 확인한 상태와 불확실해서 correction을 보류한 상태가 다름을 보이는 조건부 산술이다.

정확한 scalar actuator가 correction `a`를 만들고 제곱 residual만 손실이라고 가정하면 `E[(δ−a)²]=σ²+(μ−a)²`다. hold는 `.0025m²`, `a=μ`는 `.0009m²`여서 이 **단순한** 손실에서는 mean correction이 낫다. 별도 actuation cost `c`를 correction에 부과하면 `μ²>c`일 때만 움직이는 규칙이 된다. `c=Z²σ²`로 두면 현재 deadzone과 같은 scalar 경계를 만들 수 있지만, 이는 하나의 수학적 해석일 뿐 **현재 controller가 이 손실을 실제 최적화한다거나 σ 의존 비용이 검증됐다는 증거가 아니다.** 실제 rigid beam coupling·actuation uncertainty·guard·지연을 무시했으므로 이 계산으로 현재 보류 정책이 열등하다고 판정하지 않는다.

또 같은 표시 μ/σ에서 실제 오차 분포가 가상의 +.04m bias를 갖는다면 위 tolerance 밖 확률은 `.991535`로 달라진다. 이 값도 측정 결과가 아니며, gate 입력만으로 unknown bias를 판별할 수 없다는 논리 대조다.

## 5. 다음 최소 판별과 유지할 기록

먼저 새 물리 실행을 요구하기보다, 향후 검토가 허용된 기존 DEV trace에서 다음 **이미 있거나 출처를 추적할 수 있는** 값의 연결 여부를 확인한다. 아직 raw를 열거나 이 분석을 수행하지 않았다.

- `grasp_pose_estimate` 또는 `checkpoint_high_reobserved`와 그때 report mean/time; schedule의 `door_align_gate`에 든 clipped residual·σ_source·report_t_est·keep flags·parent/new command. 기존 event에 모든 mean/covariance가 보존돼 있다고 가정하지 않는다. 부족하면 해당 판단은 unresolved로 남긴다.
- 같은 시점의 current report mean과 저장 mean 차이, raw residual과 clipped correction 차이. 차이가 관측되면 **한 posterior center/σ라는 설명**을 재검토할 근거다. 차이가 작다는 것만으로 Gaussian coverage가 입증되지는 않는다.
- 의미상 양성 대조는 uncertainty 때문에 보류된 성분과 실제로 정렬이 충분하다고 확인된 성분을 구분할 수 있는 기록이다. 후자의 판정은 별도 task tolerance/근거가 있을 때만 한다. 낮은 z나 새 tolerance를 임의로 골라 통과시키지 않는다.
- 실제 `loaded_gate_check`가 나타나더라도 profile 이름만으로 물리적으로 loaded이거나 axial carry를 이미 시작했다고 판단하지 않는다. phase/segment·`door_align_gate`·actual command와 함께 본다. 최신 README의 loaded-profile 로그가 파지 이전에도 있었다는 공개 보고와도 모순되지 않는 해석이다.

이 연구 검토로 가능한 결정은 규칙을 **uncertainty에 따른 correction 보류 정책**으로 정확히 기술하고, 강한 posterior/정렬완료 주장을 붙일 경우 추가 가정을 밝히는 것이다. 현재 carry 실패를 이 규칙 탓으로 정하거나, 안전 gate를 완화하거나, 새 센서/정답 feedback을 넣는 결론은 나오지 않는다.
