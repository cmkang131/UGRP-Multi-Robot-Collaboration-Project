# v92 전용 조립기와 HIGH 로더 계약

2026-10-03. 조정자 D2·D5에 따라 별도 오프라인 조립기를 추가한다. v88 무하중(unloaded, 두 문 훈련 지도), v88 미세 이동(fine, r6 수집), v92 높은 운반 자세의 하중(loaded) 자료를 **각각 명시한 완료 수집 경로**에서 읽는다. v88 조립기·공유 분석 모듈·기존 로더·B/B′/r4/r5·v88/v90/v91 등록은 바꾸지 않는다. 실제 수집·렌더·v91 채점·학생 인수는 이번 구현 작업에서 실행하지 않는다.

## 입력과 출력

```bash
python -m scripts.assemble_final_pair_calibration_v92 \
  --unloaded-root /absolute/v88-training/calibration-unloaded \
  --fine-root /absolute/v88-r6/calibration-fine \
  --loaded-root /absolute/v92-collection \
  --yaw-candidate /absolute/PR360/calibration_candidate_r5_yaw.json \
  --criterion-b-result /absolute/coordinator-results/v91-B.json \
  --output /absolute/new-v92-assembly
```

`--yaw-candidate`와 반복 가능한 `--criterion-b-result`는 선택 인자다. r5는 #360의 고정 SHA-256을 확인한다. 기준 B 결과는 #356의 `ugrp.consumer_B_validation.v91` JSON을 받고, 회전 부록이 포함되면 JSON 전체를 함께 보존한다. 결과 JSON에 적힌 원본·공개 기록 경로를 다시 열거나 해시하거나 채점하지 않는다. 원본 열람 금지 경로에 놓인 JSON은 받아들이지 않으므로 조정자는 결과 JSON을 별도 위치에서 제공한다. 누락된 선택 입력은 승인이 아니다.

새 출력 폴더에 `calibration.json`, `fit_report.json`, `input_manifest.json`을 만든다. 입력과 출력의 상하위 중첩·심볼릭 링크 중첩·기존 출력 덮어쓰기를 거부한다. 읽은 자료는 완료 뒤 다시 해시하며 각 수집의 소스 SHA를 따로 보존한다. 서로 다른 수집 SHA를 하나의 실행으로 표시하지 않는다. 산출물 `source_sha`는 조립 소스이고 `collection_sources`는 세 수집 소스다.

## 원본 감사와 적합 범위

- 프레임은 실제 writer의 `sim_time`, 명령·자세·라벨·trajectory는 `t`를 쓴다. 프레임의 가짜 `t` 키를 허용하지 않는다. 완료 기록·지도·등록·일정·명령 순서와 lease·artifact 전체 해시를 대조한다.
- #358 `368903e6377eb34e714fd5cc33f13c5b4304703f`의 동일 시각(same-instant) 감사를 새 모듈에 이식했다. 장면 XML의 free-joint 주소로 `trajectory.qpos`를 읽어 같은 timestamp 카메라 라벨과 `atol=1e-8, rtol=0`으로 비교한다. 원래 자세 표본은 qpos/qvel의 직전 0.25 ms 하위 스텝(substep)과 따로 대조하고 **적합 입력을 교체하지 않는다**.
- v88은 370 SIM초·7,401 자세·로봇당 1,851프레임, v92는 720 SIM초·14,401 자세·로봇당 3,601프레임이다. v92의 역할·seed·시계·HIGH 설계·일정 바이트·B″도 감사한다.
- 운동 적합은 40–490초 HIGH 계단과 다음 coast, 검증은 해당 PRBS와 coast다. 공동 회전(common orbit)의 두 로봇은 같은 `turn`과 같은 접선 `left` 명령을 받는다. 원시 명령 전체로 상태를 예열하며, 상대 회전(relative yaw, 570–676초)은 운동 적합에서 제외하고 쌍 적합에만 쓴다. 상대 로봇의 예측에는 실제 기록된 상대 명령을 쓴다.
- B″의 전진/옆 c0 하한 0, 회전 하한 .006, 나머지 범위·초깃값·내부해·계수 식별(rank) 검사를 유지한다. 적합된 c0/u1을 실제 계단 수준과 비교해 양수 정지 수준·두 램프 수준·포화 수준의 양·음 지지와 모든 예측 시간의 유효 창을 요구한다. 작은 명령을 사전에 정지로 지정하지 않고 관측 변화율도 기록한다. B′의 잡음 선택·PRBS 판정·spread 계산은 기존 함수를 그대로 호출한다.
- loaded 카메라는 사전에 등록한 반열린 8초 창만 사용한다. 마지막 팔/팬 변경과 마지막 비영 이동 lease 뒤 8초 이상 정지, 준비 구간을 포함한 상승·네 집게 접촉·외부 지지 없음·weld OFF를 요구한다. 프레임 수와 광학/바닥 변환 및 팬 잔차 기준은 B′ 그대로다. unloaded/fine은 기존 1초 조건이다.

## 새 로더 계약과 남는 미충족 항목

계약은 `configs/calibration/zone_final_pair_v92_contract.json`, 검증 함수는 `harness.zone_final_pair_calibration_v92_contract.measured_calibration`이다. 출력 스키마는 **`ugrp.final_environment_measured_calibration.v92`**, `loader_contract_version=2`다. loaded 키는 **`896,2035,1894,1500` 하나만** 요구한다. 바닥 파지·낮은 hover·경유 자세에 loaded 카메라/운동 보정을 요구하거나 HIGH 값을 복사하지 않는다. unloaded의 기존 자세 요구는 유지한다.

`loaded_measurement_bundle_id=zone-final-pair-v92`, `loaded_pose_id=masterpi-v3-pair-high-150mm-minus40-v1`, `loaded_camera_scope=high_only`, 일정·B″·조립기·입력 명세·계약 해시를 보존한다. 기존 v88 로더는 이 새 산출물을 거부한다. D1 학생 브랜치의 초안 스키마 `ugrp.final_pair_highpose_measured_calibration.v1`와는 다르므로 **학생 담당자는 이 계약에 명시적으로 연결해야 한다**. 이번 작업은 v93 학생의 등록/코드를 수정하지 않는다.

r4/r5 및 v91 결과는 축별 무하중 후보의 근거다. 서로 다른 정지 시간상수(tau)를 평균하거나 임의로 벡터화해 `params.motion`으로 만들 수 없다. 모든 축이 통과한 외부 결과라도 새 통합 프로필을 검증한 결과가 아니다. 따라서 **현재 실제 조립 경로는 무하중 통합 프로필을 PARTIAL로 남긴다**. 별도 승인된 통합 운동 모델과 그 정확한 모델의 검증 없이는 `MEASURED_SIM`으로 승격하지 않는다. 이 미충족 항목을 카메라/loaded 적합 실패와 별도로 기록한다. 합성 완전 증명서의 새 로더 통과는 이 실제 근거 부족을 해소하지 않는다.

## 검증 기록

최종 관련 검사 **53개 통과**: 새 v92 **`44 passed in 238.22s (0:03:58)`**, 기존 v88 수치·로더 회귀 **`9 passed, 354 deselected in 15.61s`**. 파일 끝 공백만 정리한 뒤 해당 카메라·로더 6개도 **`6 passed, 38 deselected in 16.47s`**로 재확인했다. 통과 줄을 확인한 뒤 커밋한다. [검증 기록](validation.json)에 환경·실행 소스 해시와 로그/JUnit을, [보존 확인](preservation.json)에 보호 파일 35개의 동일 해시를 남겼다. [등록 기록](registration.json)은 조립기 의존 소스 188개와 일정·B″·새 계약 해시를 묶는다. 실제 r5 파일의 고정 해시 및 전진/옆 동일성도 [확인](r5-input-check.json)했다. 합성 자료는 실제 writer의 사전(dictionary) 키를 AST로 읽어 대조하며, 실제 수집 자료를 합성으로 위장하지 않는다. 신규 물리/학습/평가 결과가 없는 코드 회귀 작업이므로 TensorBoard snapshot을 만들거나 기존 결과를 재변환하지 않는다. 전체 수집과 실제 적합 결과를 조정자가 회수한 뒤 별도로 등록해야 한다.

수집 전 조정자는 B″·일정·새 조립기 및 의존 모듈 해시를 #219에 공개 고정하고 변경분 독립 검토를 완료해야 한다. 이 구현은 렌더/학생/P03/물리 임무 승인이 아니다.

## 참고 자료

- [D1–D5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204)
- [실제 프레임 시계와 qpos 감사 #358](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/358)
- [회전 후보 r5 #360](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/360), [v91 기준 B 검증 #356](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/356)
- [B″](../criterion_B_double_prime.json), [v92 일정·설계](../README.md), [B′ 조립 원본](../../2026-10-01-v88-measured-calibration/README.md)
- [실제 프레임 writer](../../../sim/camera_robot_port.py), [평가·라벨 writer](../../../sim/final_pair_v3.py)
