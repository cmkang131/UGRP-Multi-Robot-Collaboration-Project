# P2 — V2 학습 CLI가 완전한 보정 중 6개 동역학 값만 전달함

기준: main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`. **보존된 optional `scripts/train_masterpi_v2.py` 경로**의 구성 연결 결함이다. 현재 pair v98/D5 admission, 연구 주 지표 PAR2, 실제 REAL 검증 결과에 관한 판정이 아니다. 이 문서는 과거 학습의 발생·성능 저하를 주장하지 않는다.

## 결론과 책임 경계

완전한 validated manifest가 있어도 기본 학습 CLI는 chassis 동역학 6개만 명시적 `dynamics`로 넘긴다. `MasterPiDynamicsV2`는 명시적 dynamics가 있으면 manifest 자동 로딩을 건너뛰도록 설계되어 있다. 이 조합 때문에 **정지 감쇠 2개와 hardware 보정 13개를 보정값 대신 기본값으로 구성**하면서 CLI는 `CALIBRATED_SIM_TO_REAL`이라고 출력한다.

core의 explicit override 분기는 그 자체로 결함이 아니다. 보정 피팅 도구가 manifest를 우회하는 용도와 해당 동작을 요구하는 기존 테스트가 있다. 잘못 연결된 부분은 validated 학습을 표방하는 **CLI caller가 전체 보정 대신 불완전한 explicit override를 만드는 것**이다. core는 자신의 상태를 `EXPLICIT_DYNAMICS_OVERRIDE`로 정확히 표시한다.

## 약속과 실제 호출

- [CLI 문서·선별 함수·호출](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/train_masterpi_v2.py#L1-L88): 기본적으로 물리 보정 검증 없이는 실행을 거절하며 `--allow-uncalibrated`를 simulator-only로 구별한다. line59의 주석은 fitted values를 사용한다고 설명하지만, `calibration_status`는 6개 키만 반환한다. `main`은 이 dictionary를 probe와 실제 학습용 두 환경 생성에 동일하게 전달한다. mode 출력은 world의 실제 보정 상태 대신 manifest의 validated flag에 의존한다.
- [완전 보정 schema](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/calibration_schema.py#L1-L26)와 [loader](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py#L142-L176): validated를 인정하는 필수 목록은 dynamics 8개+hardware 13개이며, loader는 전체 목록의 유한한 값이 있어야 `REAL_CALIBRATED_VALIDATED`를 반환한다. 이것이 21개라는 기대의 근거다. 오래된 calibration 문서의 역사적 절차를 현재 계약으로 승계하지 않았다.
- [환경 전달](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_training_env_v2.py#L101-L144): 받은 dynamics를 core에 전달하며 별도 hardware 전달은 없다. 기본 domain-randomization=0에서도 발생한다.
- [core 구성](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py#L774-L850): `use_calibration_manifest and dynamics is None`일 때만 fitted dynamics/hardware를 함께 읽는다. 명시적 6개 dictionary를 받은 경로는 해당 분기를 건너뛰고 nominal defaults 위에 그 6개만 덮어쓴다.

## 합성 반례와 대조

실행 파일: `training-calibration-consumer-repro.py` (Mac 전달본 증거), 보존 결과: `training-calibration-consumer-result.json` (Mac 전달본 증거). 별도 검토자가 재실행하여 전체 JSON 일치와 source 호출 연결을 확인했다([독립 검증](validation.md)).

```bash
python training-calibration-consumer-repro.py --repo /path/to/UGRP-Multi-Robot-Collaboration-Project
```

Python/NumPy와 해당 Git commit object가 필요하다. 5개 source 파일을 pinned Git object와 먼저 바이트 대조한다. 완전한 21개 합성 보정값을 temporary manifest에 쓰고, 원본 AST의 CLI 함수 2개·환경 constructor·core constructor·loader를 실행한다. 최초 native model 생성 표현식에서 sentinel로 멈추므로 MuJoCo 모델·renderer·물리·학습은 실행하지 않는다. `reset`, `check_env`, Gym spaces는 구성 흐름만 이어 주는 대역이다. `--smoke`의 성공 code와 mode는 이 제한된 wiring fixture의 결과이며 실제 smoke 인수 통과가 아니다.

| 대조 | 결과 |
| --- | --- |
| core에 explicit dynamics 없이 같은 complete manifest 제공 | 21개 모두 적용, `REAL_CALIBRATED_VALIDATED` |
| 실제 기본 CLI의 `--smoke` 구성 경로 | 6개 적용/15개 기본값, CLI `CALIBRATED_SIM_TO_REAL`, core `EXPLICIT_DYNAMICS_OVERRIDE` |
| 같은 manifest에서 validated=false | CLI exit2, 환경 생성 0개 |

누락의 구체적 예시는 다음과 같다. 모두 합성값이며 실물 측정이 아니다.

| 항목 | manifest 값 | CLI 경로의 native model 생성 전 값 |
| --- | ---: | ---: |
| servo deadband (PWM) | 18 | 0 |
| servo rate (PWM/s) | 820 | 2000 |
| 정지 선형 감쇠 (N·s/m) | 29 | 18 |
| 정지 yaw 감쇠 (N·m·s/rad) | 1.2 | 0.8 |
| camera link (cm) | 7.0 | 6.7 |

누락된 13 hardware는 wheel radius/base/track, servo deadband/rate/6 center, camera link/z/pitch, block mass/friction, gripper kp/friction이다. 보정값이 우연히 nominal과 같다면 수치 차이는 없다. 반례는 서로 다른 보정값이 있을 때 caller가 이를 사용하지 않는다는 것을 확인한다.

구성값은 단순 metadata만은 아니다. [환경 step](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_training_env_v2.py#L286-L306)은 `move_servos_timed`를 사용하며 [servo plant](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py#L1187-L1208)는 deadband/rate를 참조한다. [정지 dynamics](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/sim/masterpi_dynamics_v2.py#L1290-L1302)는 해당 감쇠를 참조한다. 이 source 연결은 실제 consumer relevance를 보여 주며 trajectory·성공률의 변화 크기를 입증하지는 않는다.

## 수정 기준과 검증 공백

기본 calibrated 경로가 동일 manifest의 **전체** 보정을 사용하도록 구성 전달을 통일하고, mode는 실제 구성과 검증 상태가 일치할 때만 calibrated로 보고해야 한다. 예를 들어 기본 경로를 manifest loader에 위임하거나, 환경 API가 complete dynamics와 hardware를 함께 명시적으로 전달하게 할 수 있다. explicit override 자체를 무조건 validated로 바꾸면 검증되지 않은 override를 승격시키므로 피해야 한다.

수정 수용 기준은 nominal과 다른 complete fixture를 실제 CLI→환경→core에 통과시켜 21개 effective 값과 상태를 확인하는 것이다. unvalidated default 거절과 의도적인 explicit override 상태는 보존해야 한다. domain randomization/환경 재생성에서 같은 기준 보정이 유지되는지는 수정 방식에 따라 별도 확인할 대상이다.

관련 기존 테스트는 [loader·명시적 override](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/tests/test_masterpi_digital_twin_calibration.py#L26-L107), [hardware와 servo의 plant 적용](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/tests/test_masterpi_complete_twin_calibration.py#L17-L55)을 검증한다. 해당 tests의 source를 읽었으며 native 테스트를 실행하지 않았다. 조사한 테스트에는 이 CLI의 완전 보정 전달을 확인하는 검사가 없었다.

이 후보는 measurement 수정 후 옛 metric을 재승격하는 별도 validator 결함과 독립이다. 여기서는 manifest 자체가 올바르게 검증되었다고 가정해도 consumer 연결이 보정 일부를 생략한다. 과거 어떤 학습이 영향을 받았는지, transfer 성능이 얼마나 달라지는지는 확인하지 않았다.
