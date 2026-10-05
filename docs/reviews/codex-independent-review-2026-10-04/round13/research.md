# R13 — 보정 점수의 생성 이력과 실제 적용값을 따로 검증하기

**지금 선택 V2 경로에서 먼저 확인할 것은 새 물리 정확도가 아니라 두 identity다.** 첫째, 저장된 holdout 점수가 **그 데이터·그 파라미터**의 평가인가? 둘째, 승격한 파라미터가 **실제 consumer에 모두 적용**되는가? 두 합성 반례는 각각 이 연결을 끊는다. 한쪽 수정만으로 다른 쪽이 회복되지 않는다.

이 문서는 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 optional V2 실물 보정/학습 경로 연구 해석이다. coverage 담당의 공식 branch 재조회도 이 SHA였다. 별도 PR 응답의 base SHA798198을 최신 main으로 승계하지 않았다. 현재 pair D5/v98의 calibration 또는 공개 SELF_UNCERTAIN/POSE_UNCERTAIN 원인 판정이 아니다. 실물 자료·raw·heldout 결과·학습·물리를 열거나 실행하지 않았다. 기존 반례와 원본 source를 읽었으며, 아래 추가 검증은 설계안이다.

## 1. 이미 입증된 두 사실과 아직 입증되지 않은 것

| 연결 | 실제 source + 합성 증인 | 연구적으로 가능한 결론 | 이 증거가 주지 않는 결론 |
|---|---|---|---|
| 수정된 측정 → 평가 점수 → promotion | 실제 fitter가 만든0° 점수를 둔 채 공식 `record(force=True)`가 holdout 한 행을90° 정정. 현재20행 재계산 MAE4.5°인데 validator는 저장0°로 통과하고 새 dataset hash와 함께 재승격 | `validated`와 현재 파일 해시만으로 점수의 현재 입력에 대한 적합성을 확인할 수 없음 | 과거 실물 보정에서 발생했는지, 실제 오차가4.5°인지, 모든 stored metric이 틀렸는지 |
| 완전한 promotion → 실제 training consumer | 서로 다른21개 합성 보정값. 기본 CLI가6개 dynamics만 explicit 전달해 manifest loader를 우회.15개는 default; CLI mode와 core status 불일치 | 이 caller의 `CALIBRATED_SIM_TO_REAL` 출력은 완전한 보정 적용의 증거가 아님 | 실제 PPO가 실행됐거나 transfer 성능이 나빠졌다는 결론 |

첫 증인은 [stale metric 감사](stale-metric.md), [독립 QA](validation.md); 둘째는 [consumer 감사](consumer.md), [독립 QA](validation.md)에 분리돼 있다. 소비자 증인은 **올바르게 검증된 complete manifest를 가정해도** 성립한다. 두 증인을 연결해 실제로 잘못된 calibration이 배포됐다고 합성하지 않는다.

원본에서 직접 확인한 범위는 `fit_masterpi_servo.run/metrics/predict`, `record_masterpi_calibration_measurement.record`, `validate_masterpi_digital_twin.validate/promote`, `calibration_schema`, `train_masterpi_v2.calibration_status/main`, 환경 constructor, `MasterPiDynamicsV2` constructor와 loader다. explicit override는 core가 의도적으로 허용하고 상태도 정확히 표시한다. 결함은 그 override를 불완전하게 구성하면서 calibrated라고 설명하는 CLI 연결에 있다.

## 2. 점수는 값 하나가 아니라 무엇을 평가했는지가 있는 결과다

현재 servo fitter에 맞춰 기호로 쓰면 다음과 같다. 이는 일반적인 새 Bayesian 모델을 제안하는 식이 아니라 source의 의존성을 명확히 표시한 것이다.

\[
\theta=F(D_{fit}; C_{fit}, S),\qquad
E=M(D_{hold};\theta,C_{eval},S),\qquad
P=G(E,A;C_{gate}).
\]

`S`는 단위·schema·split·전처리 의미, `A`는 acceptance 기준이다. 실제 사용값은 별도 함수 `θ_effective = Consumer(θ, defaults, overrides, configuration)`의 결과다. `θ_effective=θ` 여부는 promotion 판정만으로 결정되지 않는다. domain randomization이 명시됐다면 비교 대상은 매번 같은 값이 아니라 **같은 baseline과 명시된 변환**이다. 현재 증인은 randomization0이며, reset 전 과정의 추가 재현을 했다고 주장하지 않는다.

W3C PROV-DM은 산출물, 사용 입력, 생성 활동과 derivation을 구별하고, 같은 활동이 입력을 읽고 산출물을 만들었다는 사실만으로 실제 derivation이 확정되지 않는다고 설명한다([P3](primary-sources.md#p3)). UGRP에서 이에 대응하는 좁은 설계 원칙은 **평가 생성 시점**에 데이터/split·파라미터·평가기 identity를 함께 묶는 것이다. validator가 나중에 현재 파일의 hash를 찍는 것으로 이전 점수의 생성 이력이 생기지는 않는다. 이 대응은 우리의 설계 추론이며 PROV 형식 자체의 채택 요구가 아니다.

최소 평가 기록은 평가에 실제 사용한 입력 identity, 파라미터 identity, metric 이름·단위·코드/설정, split과 sample count, 결과를 연결해야 한다. promotion은 이 평가 기록과 현재 candidate가 맞는지 검사하고 acceptance 기준의 버전도 별도로 남긴다. 전체 Git SHA만으로 외부 library·전처리·설정까지 고정됐다고 가정하지 않는다. 구현에 따라 파일 전체 hash를 보수적으로 비교하거나, versioned canonical 의미 표현을 사용할 수 있다. 어느 쪽이든 **같은 행 수**는 같은 측정이라는 증거가 아니다.

## 3. 무엇이 바뀌면 어디부터 다시 확인하는가

아래 표는 새로운 자료를 수집하자는 제안이 아니다. 임시 합성 fixture에서 dependency를 검증할 최소 대조이며, '다시 계산'도 해당 fixture 안의 계산을 뜻한다. 기존 측정 원본은 보존하고 revision과 사유를 남기는 전제다.

| 변화 | 무효화/재검증해야 하는 연결 | 최소 양성 관측 | 음성 대조 / 기각 기준 |
|---|---|---|---|
| holdout 측정값만 정정, fit 자료·정의 불변 | 해당 holdout 평가와 promotion. holdout을 fit에 쓰지 않는 source라면 θ의 재학습은 필수 아님 | old evaluation identity가 거절되고, 고정θ로 새 holdout 평가가 생성됨 | 무변경 입력/θ의 재검증은 통과. 정정 뒤 count가 같다는 이유로 old score 통과하면 미해결 |
| fit 측정값 또는 fit preprocessing 수정 | θ의 생성 이력, 그 θ에 의존한 평가·promotion | 새 fit identity→새 candidate→그 candidate의 평가 연결 | 새 fit이 우연히 같은θ를 내더라도 입력 revision은 구분. 수치 동일을 거짓 실패로 단정하지 않음 |
| 데이터 그대로, 사용θ만 변경 | 변경θ를 사용하는 모든 metric과 promotion | 평가가 다른θ의 결과임을 검출. 현재θ로 새 평가 전 재승격 차단 | θ의 직렬화 형식만 바꿨다면 문서화된 canonical 비교 또는 재평가로 해소; byte 차이를 물리차로 해석하지 않음 |
| metric 단위/정의/평가기 변경 | 해당 metric identity와 이전 기준의 호환성 | 이전 점수를 새 metric인 것처럼 비교하지 않음 | 값과 의미가 보존됨을 별도 검증한 migration은 가능. 단순 이름 변경으로 검증 증거 생성 불가 |
| acceptance 기준만 변경 | **promotion 판정**과 그 기준의 근거 | 고정 evaluation을 새 기준으로 재판정하되 old/new gate 결과 분리 | score를 다시 계산할 필요는 없음. 더 느슨한 기준 통과가 실제 정확도 개선이라는 주장은 기각 |
| complete manifest를 consumer에 제공 | 전체 required key의 effective 값/적용 출처와 mode | nominal과 다른21개 값이 baseline에 적용되거나 명시적 override로 정확히 표시 | 기존 complete loader 정상, unvalidated default 차단, 의도적 override 상태 유지 |

첫째·마지막 행에 대응하는 **현재 구현의 반례**는 실제 함수/source constructor의 합성 실행으로 확인됐다. 표가 제안하는 수정 후 acceptance 대조는 미실행이다. 나머지 행도 설계안이며 실행 완료 목록이 아니다. 행별 의존성만 무효화할 수 있다는 것은 실제 evaluator가 그 입력 분리를 지킬 때의 조건부 판단이다. 모든 영역을 무조건 다시 측정하거나 fit할 필요가 있다는 주장은 하지 않는다.

이미 결과를 본 뒤 acceptance 기준을 바꿨다면 같은 자료의 재판정을 untouched holdout의 새 확증으로 승계할 수 없다. 기준 변경의 수학적 재판정 가능성과 독립 확증의 지위는 별개다.

`validated=false`로만 내리는 방법은 충분하지 않다. 첫 증인은 동일한 old metric으로 다시 validate→promote가 가능하기 때문이다. 반대로 hash 검사를 추가한 것만으로 metric 구현·측정 품질·consumer 적용이 자동 검증되지는 않는다.

## 4. 두 연결을 고친 뒤에도 남는 연구 주장

공식 metrology의 용어는 status flag보다 좁고 구체적이다. VIM은 calibration, 요구 충족의 verification, 특정 용도에 적절한 요구를 확인하는 validation을 구별한다. metrological traceability에는 기준까지의 calibration 연쇄와 각 단계의 불확실성이 관계된다([P1](primary-sources.md#p1)). **저장 파일의 hash 연쇄는 계산 provenance이며 그것만으로 metrological traceability가 아니다.** NIST도 traceability 자체가 용도 적합성을 보장하지 않는다고 명시한다([P2](primary-sources.md#p2)). 이 문서는 UGRP에 인증·SI 소급성·표준 준수 의무를 새로 부과하지 않는다.

NASA-STD-7009B는 모델의 validation domain과 proposed use를 구별하고, 입력/데이터 이력·보정 domain·버전·검증되지 않은 부분을 기록하게 한다([P4](primary-sources.md#p4)). 이를 현재 연구에 좁게 적용하면 **어떤 load·command range·camera pose·응답시간을 평가한 calibration인지**를 실행 조건과 연결해야 한다. 21개 적용 일치는 중요한 구성 검증이지만 해당 domain 밖 성능이나 공동 운반 성공을 입증하지 않는다. NASA 기준이 이 프로젝트에 법적·계약적으로 적용된다는 주장은 아니다.

로봇 calibration 문헌도 '작은 residual'의 의미를 입력/오차모형과 연결한다. Strobl–Hirzinger의 hand-eye 모델은 calibrated forward kinematics와 joint encoder 기반 TCP pose, camera pose와 해당 오차모형을 사용한다. 같은 AX=XB/AX=ZB 표기라도 측정 오차의 위치에 따라 formulation과 weighting 선택이 달라진다([P5](primary-sources.md#p5)). 현재 own-issued-command 기반 view 모델은 이 측정 입력과 같지 않다. 해당 논문의 방법을 그대로 적용하거나 새 joint feedback을 제어기에 넣자는 결론은 나오지 않는다. 적용 가능한 교훈은 **어떤 입력을 실제로 측정했고 어떤 것은 명령/모델로 대체했는지**를 calibration 증거에 명시하는 것이다. R12의 command-layer 불일치는 먼저 해결할 별도 설명이며, calibration 오차로 흡수해 재fit할 이유가 아니다.

## 5. pass인데 기대와 다를 때의 경쟁 설명

| 설명 | 가장 작은 구분 자료 | 그 설명을 약화시키는 관측 | 여전히 주장할 수 없는 것 |
|---|---|---|---|
| H1: 점수가 현재 candidate를 평가하지 않았다 | 평가 생성 입력·θ·metric identity와 현재 candidate의 비교; 합성 동일count 정정 대조 | identity가 맞고 해당 동일자료/θ의 독립 재계산도 일치 | 일치만으로 물리 측정의 진실성·외부 정확도 보장 |
| H2: 점수/manifest는 맞지만 consumer가 일부를 사용하지 않았다 | 실제 constructor가 만든 effective21값과 override 출처; native 실행 직전 중단 가능 | nominal과 다른 모든 값이 적용되고 의도적 변경도 명시됨 | 적용 일치만으로 학습/transfer 개선 |
| H3: 생성·적용은 맞지만 평가 domain/측정모델이 용도와 다르다 | 이미 존재하는 plan/schema/declared domain과 사용 조건 비교; 측정량·단위·frame·timing 의미 | 지목한 domain 차이가 없고 독립된 적합성 증거가 그 차이를 직접 포괄 | 새로운 raw를 읽지 않은 이번 검토에서 실제 model bias의 크기·방향 |

H1과 H2는 각각 이번 합성 반례가 지원하지만 발생 빈도는 모른다. H3는 별도 연구 가설이며 이 검토에서 실제 발생 증거는 없다. H1의 stale 점수가 H2의 기본값 사용을 야기한다거나, H2가 현재 pair uncertainty를 유발했다고 연결하지 않는다.

기존 기록은 **검증 생성 이력 확인 가능**, **적용 구성 확인 가능**, **대상 domain 확인 가능**을 별도 열로 남길 수 있다. 정보가 없으면 unknown이지 자동으로 bad run은 아니다. 정정 전 자료로 적법하게 생성된 과거 평가도 그 당시 버전의 증거로 보존할 수 있다. 현재 자료에 대한 검증으로 재명명하지 않는 것이 핵심이다. [D5/v92 assembly source 경계](assembly.md)는 별도의 hash/support/profile 검사 경로를 확인했으므로 optional V2 반례를 전이하지 않는다.

다음 문서는 현재 pair의 실제 막힘을 줄이는 판단에 집중한다. R8–R13에서 검증한 '명령 완료→frame/scan/fix→gate→행동' 경계를 한 장의 최소 판별 순서로 묶고, optional V2의 이 두 문제는 그 즉시 진단 목록과 분리한다. 새 실제 실험 실행이나 기준 완화는 포함하지 않는다.
