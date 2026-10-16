# R13 · 선택 V2 실물 보정에서 측정 정정 뒤 오래된 오차로 다시 승격할 수 있음

**P2, 보존된 V2 digital-twin 보정 경로.** 공식 측정 기록기로 기존 행을 정정한 뒤 최종 validator를 실행하면, 바뀐 자료의 개수와 새 해시는 확인하지만 저장된 오차가 그 자료로 계산됐는지는 확인하지 않는다. 합성 표본에서 실제 servo 평균 오차는 **4.5° > 기준 3°**인데, 이전 오차 **0°**를 사용해 합격하고 `validated=true`로 승격했다.

현재 pair v98/D5의 문제가 아니다. 실제 실물 자료·held-out 결과·과거 승격 기록은 읽지 않았고, 과거에 이 오류가 발생했다고 주장하지 않는다. 코드 기준은 `f2577bb5121748644df31eb0fc5a1c1b94b80d80`; 공식 GitHub compare에서 최신 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`까지 변경은 문서 4개뿐임을 확인했다.

## 정상 공개 caller에서 이어지는 경로

1. [`fit_masterpi_servo.run(write=True)`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/fit_masterpi_servo.py#L44-L54)은 계획된 fit/holdout 행으로 추정하고, 매개변수와 두 servo 오차·개수를 manifest에 쓴다.
2. [`record_masterpi_calibration_measurement.record`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/record_masterpi_calibration_measurement.py#L22-L40)는 `force=True`/CLI `--force`로 이미 측정된 행을 정정할 수 있다. 자료 JSONL만 갱신하고 기존 manifest에는 접근하지 않는다. `--force`가 없을 때의 덮어쓰기 거절은 정상 동작한다.
3. [`validate`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/validate_masterpi_digital_twin.py#L51-L98)는 완료 행·출처 문자열·fit/holdout 개수·servo 집합을 확인한 뒤, 오차 문턱을 **manifest의 `results`**에 적용한다. 평가를 만들 때의 dataset/parameter identity와 현재 입력을 비교하는 검사는 없다. 마지막에 현재 파일의 해시를 새로 계산한다.
4. [`promote`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/benchmarks/validate_masterpi_digital_twin.py#L100-L113)는 그 새 해시와 이전 오차를 함께 provenance로 기록한다. [`load_fitted_parameters`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py#L141-L166)는 모든 매개변수가 finite이고 `validated`가 참이면 `REAL_CALIBRATED_VALIDATED`로 반환한다.

따라서 이는 임의로 `validated=true` JSON을 주입한 검사도, validator의 내부 함수에 조작한 pass 보고서를 직접 건넨 검사도 아니다. 실제 fitter가 쓴 servo 지표, 실제 기록기가 정정한 자료, 실제 `validate → promote` 순서를 연결했다. 다른 보정 영역의 이미 완료된 상태는 기존 `CompleteTwinPromotionGateTests`와 같은 합성 스캐폴드로 제공했다.

## 합성 재현과 대조

`calibration-stale-metric-repro.py` (Mac 전달본 증거)는 임시 디렉터리에서 다음을 실행한다. 모든 관측과 출처 문자열은 단위 테스트용 합성 자료이며 실물 증거가 아니다.

| 단계 | 결과 |
| --- | --- |
| 원래 servo plan 60행(40 fit/20 holdout), 합성 관측, 실제 fitter 실행 | holdout MAE 0°, validator 합격 |
| 정상 최초 promote | `validated=true` |
| 완료된 holdout 한 행을 force 없이 정정 | 기존 보호 규칙으로 거절 |
| 같은 행을 공식 recorder의 force 경로로 90° 정정 | JSONL 변경, manifest 바이트/내용 불변 |
| 실제 `fit_masterpi_servo.metrics`로 현재 20행 재계산 | MAE 90/20 = 4.5°, 기준 3° 초과 |
| 다시 실제 validator 실행 | 저장 MAE 0°로 합격, 현재 dataset 해시는 변경된 값 |
| 위 validator의 실제 반환값으로 promote | `validated=true`, 새 해시와 이전 MAE 0° 기록 |
| 동일 manifest에 재계산한 오차를 반영하는 음성 대조 | 같은 validator가 오차 문턱에서 거절 |

원본의 dependency-free loader 함수는 AST로 그대로 추출해 `REAL_CALIBRATED_VALIDATED` 반환까지 확인했다. MuJoCo 모듈 전체를 import하거나 물리 객체를 생성한 검사가 아니다. 실제 카메라·로봇·모델·학습·렌더·네트워크 실행은 없었다. 기존 실험 원본, 저장소 구현, Mac 파일을 수정하지 않았다.

재현 명령:

```sh
PYTHONDONTWRITEBYTECODE=1 python review-notes/round13/calibration-stale-metric-repro.py --repo /path/to/ugrp
```

출력은 `calibration-stale-metric-result.json` (Mac 전달본 증거)에 보존했다. 실행 전 실제 import/AST 대상 7개 source의 SHA-256을 확인하므로 구현이 바뀐 checkout은 같은 반례로 묵시적 실행하지 않는다. Python 3.12와 NumPy만 썼고 pytest 전체 suite 통과를 주장하지 않는다.

## 수정 수용 기준과 범위

평가 오차를 만들 때 실제 입력 자료 해시·사용 매개변수·평가 코드 식별값을 함께 고정하고, promotion 시 현재 입력과 일치해야 한다. 마지막 validator가 그 시점의 새 해시만 붙이는 방식은 오래된 오차를 현재 자료의 결과로 바꿔 보이게 한다. 측정 정정 또는 fit 갱신 시 영향을 받는 평가를 무효화하고 다시 계산하도록 해야 한다. 단순히 `validated=false`로 내리는 것만으로는 동일한 오래된 오차를 재승격하는 경로가 남는다.

검사는 정상 무변경 재검증은 허용하면서, 행 수가 같은 측정 정정·매개변수 변경·오차 산출물 누락은 재평가 전 거절해야 한다. 정확한 의미와 순서가 있는 새 증거 형식을 적용할 사안이며 이번에는 구현하지 않았다. 과거 연구 결과의 실제 유효성, 실제 servo 오차의 크기·빈도, 현재 pair의 성공 가능성은 이 반례로 판단할 수 없다.
