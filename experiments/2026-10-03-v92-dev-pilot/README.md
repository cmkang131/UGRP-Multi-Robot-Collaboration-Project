# v92 개발용 파일럿 보정 DEV_PILOT_C0_ZERO_v1 (비확증) + B″ v-next 초안 (2026-10-03)

**확증 결과가 아니다.** 상태는 `DEV_PILOT`이며 `MEASURED_SIM`이 아니다. v92 로더(`measured_calibration`)는 `MEASURED_SIM`이 아닌 상태를 거부한다. 조정자 결정(2026-10-03, 사용자 거부권 있음)에 따라, LLM이 제어에 참여하는 공동 운반 개발 파일럿을 먼저 열기 위해 만들었다. 동결 기준 B″는 바꾸지 않았다.

## 왜 비확증인가

동결 조립(#367)은 하중 공통 적합에서 정지 구간 시작값(c0) 세 축이 모두 탐색 하한(0, 0, 0.006)에 붙어 PARTIAL이었다. 이 개발 규칙은 그 결과와 v92 자료를 **본 뒤에** 정했다. 그래서 v92 자료는 이 규칙에 대해 탐색 자료다. 확증하려면 규칙을 먼저 고정한 뒤 새로 수집해야 한다([B″ v-next 초안](B_double_prime_vnext_DRAFT.md)).

## 개발 규칙 (동결 경로와 다른 점은 두 가지뿐)

- D1. 하중 c0를 세 축 모두 0으로 고정한다(정지 구간 없음). 자유 매개변수는 10개다(이득 3, 주행 시간상수 3, 공통 정지 시간상수 1, u1 3). u1 범위는 B″ 그대로다.
- D2. c0=0이므로 정지 구간 지지 검사에서 "c0 아래의 관측 명령" 조건만 뺀다. 두 램프 수준과 한 포화 수준을 부호별·모든 예측 시간에서 요구하는 조건은 그대로 둔다.
- 나머지는 그대로 쓴다. 최적화 설정, 수렴·계수·경계·내부해 검사, B′ 잡음 선택, B″ PRBS 검증, 퍼짐, 쌍 모델 모두 같다. fine 운동·카메라·팬은 측정 조립 출력(`852426d2…`)에서 수락된 값을 프로그램으로 복사했다. 손으로 고친 값은 없다.

## 실행과 결과

- 스크립트 [fit_dev_pilot.py](fit_dev_pilot.py)는 실행 전에 커밋했다(`6a91737c`, 깨끗한 트리). 한 번만 실행했고 rc=0, 27초(10:40:43–10:41:10 UTC)였다. 명령은 [dev_command.sh](dev_command.sh)에 있다. 물리·렌더링·모델 호출은 없었다.
- 출력 위치는 `/Users/changmin/projects/ugrp/outputs/v92-dev-pilot-c0zero-20261003T104043Z/`이다. 해시는 [outputs_dev.SHA256SUMS](outputs_dev.SHA256SUMS)에 있고, `calibration_dev_pilot.json`은 `398372ae…`다(사본: [calibration_dev_pilot.json](calibration_dev_pilot.json)).
- 하중 평균은 수렴했다(`ftol`, 계수 10/10, 모든 매개변수 내부해, 경계까지 최소 거리 0.0016, RMSE 0.00187). B″ 훈련 36/36, PRBS 검증 36/36 통과.
  - 이득 1.355/0.964/0.907, 축 시간상수 0.966/0.968/0.656 s, 공통 정지 시간상수 0.0852 s
  - u1 0.0266/0.0282/0.0319, 측면 noise_abs 0.0160
- 퍼짐 통과: 계단 블록 36개, 하중 이동 배율 퍼짐 0.0154/0.0284, 회전 편향 0.000234 rad/s, 표류 비 0.00101.
- 쌍 모델 통과: 18행, 제외 0, 기울기-회전 비 1.107, b 0.0173(기본)·0.00030(pm)·0.0174(edge)·0.00023(pm+edge) rad/s.
- 채워진 항목 98개(개발 재적합 21 + 측정 복사 77). **빠진 항목 10개는 `params.motion.{gain, tau_s, tau_axis_s, tau_stop_s, noise_rel, noise_abs, scale_std, scale_walk, use_scale, rest_noise}`**(무하중 통합 프로필)다.
- 측정 v92 출력(`final-pair-v92-measured-20261003T091812Z`)은 바꾸지 않았다. 파일 20개가 SHA256SUMS와 일치한다.

## 무하중 통합 프로필: 승인 조건 확인

조정자 쪽에서 측정된 후보 중 하나를 고르는 경로는 **없다**.

- **코드:** v92 조립기는 무하중 구역을 항상 거부한다(`sections[MOTION['unloaded']] = {'accepted': False, ...}`). 받아들이는 분기 자체가 없다. 로더는 무하중 단일 정지 시간상수 `tau_stop_s`를 요구한다.
- **규칙 문구:** 기준 B(`consumer_criterion_B.json`) — overall은 "true only if all axes pass"이고, promotion은 "No MEASURED_SIM promotion or loader/controller modification"이다. B″ — "Frozen unloaded B still runs unchanged and can veto … never replace missing measurements"이고, changes_from_B는 "No averaging of axis stop taus"다.
- **후보 상태:** r4(전진·옆)와 r5(회전)는 축별 후보다. 정지 시간상수가 0.0890/0.0885/0.0374 s로 서로 다르다. v91 held-out 채점에서 전진·옆은 통과했지만 회전은 PARTIAL_MAPS였다(문 지도는 이미 본 자세 바이트라 제외). 그래서 overall은 null이다.
- **fine B′ 통과로는 대신할 수 없다:** fine은 r1 단독의 미세 PRBS 별도 프로필(`motion_profiles.fine`)이다. 무하중 값으로 쓰면 금지된 대체가 된다.
- **필요한 것:** (a) 무하중 공통 정지 시간상수 세 축 재적합(새 후보), (b) 그 후보의 기준 B held-out 검증. 회전은 새 held-out 자료가 필요하다. (c) 조립기 수락 경로 추가. 다른 방법은 B′식 시간 블록 검증을 무하중에도 허용하는 규칙 변경이다. 둘 다 이번 작업에서는 적용하지 않았다.

## TensorBoard

`outputs/tensorboard/1003-v92-dev-pilot-r2`(실행 `dev-fit`, `dev-calibration`). HTTP API로 26개 스칼라를 대조했고 불일치 0이다([tensorboard_api_values.json](tensorboard_api_values.json)). 생성기는 [gen_tb_views.py](gen_tb_views.py)다. 첫 시도인 `1003-v92-dev-pilot`은 뷰 설명 필드가 빠져 일부 변환에 실패했고, 그대로 남겨 두었다. `tensorboard-view.json`에는 자기 키 `v92_dev_pilot_20261003`만 추가했다.

## 참고 자료

- [#219 해시 고정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5967154276), [#367 동결 조립 PARTIAL](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/367), [#361](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361)
- C. L. Lawson, R. J. Hanson, *Solving Least Squares Problems* (1974), 23장. [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)
- 기준 B `experiments/2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json`, B″ `experiments/2026-10-03-v92-loaded-schedule/criterion_B_double_prime.json`, r5 `experiments/2026-10-03-critb-rotation/`
