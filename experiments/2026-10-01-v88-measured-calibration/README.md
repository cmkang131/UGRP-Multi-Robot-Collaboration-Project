# v88 실측 보정 오프라인 조립

## 자료를 읽기 전에 고정한 기준

- 고정 시각(이 구현 작업 기준): `2026-10-01T01:01:16.006231+00:00`. v88 raw는 아직 읽지 않았다.
- fine·loaded: **계단 + 다음 coast → 적합, PRBS + 다음 coast → 검증**.
- [criterion B′](criterion_B_prime.json) SHA-256: `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`.
- B의 본문을 그대로 포함하고, 위 프로필/시간 블록 분할과 3축·공통 stop tau 제약을 명시했다.
- unloaded는 기존 [동결 criterion B](../2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json)와 검증기를 그대로 쓴다. 두 문 지도는 B의 훈련 지도이며 회전 후보도 없다. 수집 시점 검증 기능도 없어 현재 전체 승격은 불가능하다.
- 이미 시작된 수집보다 먼저 동결했다고 주장하지 않는다. 이 작업의 raw 열람보다 먼저 고정했다.
- 값이 없거나 승인되지 않은 필드는 정확한 경로와 사유를 적고 **PARTIAL**로 저장한다.

물리·렌더·모델 호출 없이 합성 raw로 구현·검사한다. 학생 factory·제어기·워크플로는 변경하지 않는다.

## 실행과 산출물

```sh
python3 -m scripts.assemble_final_pair_calibration \
  --raw-root /Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001 \
  --output /Users/changmin/projects/ugrp/outputs/final-pair-v88-measured-NEW
```

새 출력 경로만 허용한다. 입력 안/입력을 포함하는 출력, 기존 출력은 거부한다.
종료 0은 모든 필드 승인과 세 지도 로더 검증 완료, 2는 PARTIAL이다.
완료 기록이 없는 수집은 내부 자료를 읽지 않고 누락으로 남긴다.
완료 기록이 있는 경우 plan/bundle/result, 전체 artifact 파일 집합·SHA-256,
지도·계약·소스·물리 구성, 전체 명령/lease/팔 명령, 50 ms 위치와 200 ms 프레임·JPEG·label을 대조한다.
입력·소스 의존성을 읽기 전 해시하고 출력 직전에 다시 검사한다. 원본·기존 산출물은 변경하지 않는다.

- `calibration.json`: schema `ugrp.final_environment_measured_calibration.v1`.
  승인되지 않은 값은 null, `missing`에 **필수 필드마다 정확한 경로와 이유**를 저장한다.
- `fit_report.json`: 적합 후보, 블록별 모든 horizon/component의 포함률·p95·NEES,
  카메라 잔차, 실제 하중 선택/제외 수와 거부 사유. 실패도 남긴다.
- `input_manifest.json`: 실제 읽은 모든 입력·이미지·소스의 경로/바이트/SHA-256,
  criterion B/B′ 해시, 실행 HEAD와 작업 트리 수정 여부. 이 파일의 바이트 해시가
  `measurement_manifest_sha256`다. 로컬 보관이며 원격 raw 백업이 아니다.

현재 동결 B는 두 문 지도를 훈련 지도로 제외하고, 회전 후보·수집 선후관계 검증도 없다.
따라서 **이번 세 수집만으로 실제 MEASURED_SIM을 발행할 수 없다**.
이를 바꾸려고 B/후보 해시·지도·승인 상태를 치환하지 않는다. 합성 전체 필드의 로더 통과 검사는
조립/형식 검사이며 실제 승인 산출물을 뜻하지 않는다. 필요한 후속 수집/기준 결정은 코디네이터 몫이다.

## 방법과 보수적 거부

운동은 r4의 부호 공통 gain/run tau/stop tau와 끝 속도 Euler 적분을 사용한다.
축별 후보를 보존하고, 실제 로더가 소비할 **세 gain + 세 run tau + 공통 scalar stop tau**를
계단 자료에서 다시 적합한다. 축별 stop tau 평균이나 벡터를 로더에 넣지 않는다.
초기 속도는 기록 처음의 0에서 명령만으로 누적하며 PRBS 표적은 적합·잡음 선택에 쓰지 않는다.
loaded는 v6g breakaway ramp를 함께 적합하고 실제 적용될 ramp 포함 평균을 다시 채점한다.
네 크기가 아래/중간 두 수준/포화 영역을 식별하지 못하거나 rank/경계/부호/창 수가 부족하면 거부한다.

잡음은 B의 하한과 사전식 순서, 95% 계단 포함률을 그대로 사용한다. 회전이 있는 경우에도
기존 선형화 공분산을 이차식으로 전개하고 순서통계량으로 최소 absolute noise를 구한다.
아직 최소화하지 않은 계수가 해당 창 분산에 기여하면 그 제약은 뒤로 넘긴다.
B에는 잡음 상한이 없으며, 순서에 조건부인 최솟값이다. 별도 공분산 계산과 합성 비교한다.
검증은 각 로봇/축/PRBS/horizon/component별 p95(|error|/sigma) ≤ 2 및 2σ 포함률 ≥ 90%다.
겹치는 시간 창은 독립 반복이나 새 지도 일반화 증거가 아니다.

하중은 기록된 beam box 형상·위치·회전으로 최하단 높이를 계산한다.
높이 ≥ 1 cm, 두 운반자 각각 양 집게 접촉, 외부 지지 없음, weld 없음인 표본만 쓴다.
단 한 표본이라도 조건이 깨지면 그 지점을 가로지르는 창을 제거한다. 요청한 `loaded` 표시는 근거가 아니다.
알 수 없는 beam geometry·누락 접촉은 거부한다. 표본별 실패 원본은 지우지 않는다.

- load_transition/yaw spread: v6e의 NNLS 분산식과 leave-one-step-out 최댓값.
  translation `e² = a*T + s²*d²`, yaw `e² = a*T + b²*T²`.
  같은 블록의 두 로봇을 함께 제외한다. yaw scale 0은 별도 bias로 표현하는 구조적 값이며,
  unloaded scale 0은 B의 `use_scale=false` 제약이다. 측정한 모집단 slip=0이라고 주장하지 않는다.
- drift: v6g의 축간 잔차/진행 거리(≥ 0.3 m), 축·명령 크기 cell을 같은 가중치로 RMS 계산.
- pair: 기록 RGB에 기존 `BeamEdgeTracker`만 적용한다. 신경망/모델 호출은 없다.
  step의 상대 yaw 변화에 대한 smoothed slope 변화의 원점 회귀, 네 estimator의 cell별 균형 RMS rate를 구한다.
  `pm`은 v6 코드의 계획상 mirrored command 평균이며 측정한 partner 상태를 예측에 넣지 않는다.
  PRBS에서 ratio/네 rate를 별도 검사한다. edge 불가/무여기/관측 누락이면 해당 보정은 미측정이다.
- 카메라: r1의 origin 중앙값과 원소별 중앙 회전에 가장 가까운 실제 SO(3) 회전을 사용한다.
  v88 label에 이미 들어 있는 optical→actual chassis와 chassis→floor를 각각 요약한다.
  1초 정착·정지 구간만, loaded는 그 동안의 실제 상승/접촉도 요구한다.
  pan은 같은 로봇·팔·연속 정지 그룹의 pan=1500 yaw 중앙값 기준 회귀다.
  `required_camera_poses()` 중 미방문/미정착/하중 불성립 자세는 보간하지 않는다.

학생 factory·제어기·동결 B/r1–r4·실행 번들은 변경하지 않는다.
이번 구현은 **실제 v88 raw를 읽지 않고 합성 자료만 사용**했다.
새 물리/학습/평가 코호트가 없어 TensorBoard 변환·뷰어는 시작하지 않았다.
`/private/tmp` extraction 디렉터리는 생성하지 않았다. 로더 임시 파일은 context manager로 정리한다.

## 참고 자료

- [v88 인계: 보정 수집·필수 필드](../../PHYSICS_HANDOFF.md)
- [r1–r4, criterion B와 독립 검토 후 검증기 제한](../2026-10-01-final-env-v87-calibration-fit/README.md)
- [동결 B 검증기](../../scripts/validate_consumer_criterion_b.py), [r4 적합/잡음](../../scripts/fit_consumer_criterion_b.py)
- [v88 실제 수집 형식](../../sim/final_pair_v3.py), [수집 실행기](../../scripts/run_final_pair_v3.py)
- [r1 카메라](../../scripts/fit_final_environment_unloaded.py)
- [v6e spread](../2026-09-29-pair-v6e-carry/fit_carry_dr.py),
  [v6g deadband/drift](../2026-09-29-pair-v6e-carry/fit_carry_general.py),
  [v6e pair yaw](../2026-09-29-pair-v6e-carry/fit_carry_pair_yaw.py)
- [v88 로더](../../harness/zone_final_pair_contract.py), [새 합성 회귀](../../tests/test_final_pair_calibration_assembly.py)

## 검증 결과

[검증 기록](validation.json): **중복 제외 283개 통과**(새 합성 검사 134 + 기존 관련 회귀 149).
새 suite 132개 전체 통과 후, 마지막 IO 변경 79개와 방법 검사 3개(새 2개 포함)를 다시 통과했다.
모든 필수 필드별 누락 차단, 세 지도 로더의 완전 합성 산출물 수용, 계단 적합/PRBS 오염 분리,
회전 포함 공분산 일치, 최소 잡음을 줄인 실패 반례, loaded ramp/상수 yaw bias 복원,
접촉·높이·weld·프레임/명령·해시 변조 차단, 실제 조립 CLI의 PARTIAL/manifest 연결을 포함한다.
CI 목록에 새 테스트를 등록했고 frozen fixture 3개, shard 목록, `git diff --check`를 확인했다.
Junit 원본은 기본 체크아웃 `outputs/v88-calibration-pipeline-offline-20261001/`에 로컬 보존했다.
원격 CI 결과는 PR에서 별도로 확인하며, 이 기록은 물리 성능이나 MEASURED_SIM 승인이 아니다.
