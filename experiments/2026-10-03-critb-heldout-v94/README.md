# v94 새 시작점 held-out 준비

Refs #219 #364. 기준 B·r4·r5·회전 부록·기존 v91 검증기는 `frozen.json`의 바이트를 유지한다.
v94 / workflow 3.6.0은 main과 열린 PR 전체의 등록을 확인한 다음 번호다(`reservation.json`).

## 변경 범위

- 새 검증기 `scripts/validate_consumer_criterion_b_v94.py`는 **채점 전** 운동 내용으로 제외한다. `--v91-raw`는 이 관문을 통과한 경우에만 기존 v91 채점기로 간다. `--pose`는 운동 중복 여부만 판정하며 B PASS가 아니다. 기존 v91 검증기의 바이트와 과거 출력은 재현용으로 보존한다.
- `(t, base_position_m, base_rotation)`만 비교한다. 위치 각 성분 1e-9 m, 회전행렬 각 성분 1e-9, 상대 시각 1e-9 s, 상대 허용오차 0. 임의 시간 원점 이동과 모든 내부 부분 구간을 검사한다. 기본 창은 B 최단 horizon인 0.2 s(0.05 s 기록의 양 끝 포함 5행). 그보다 짧은 이전 기록 전체도 두 공통 표본 이상이면 보수적으로 제외한다. 부가 필드·경로·지도 이름은 중복 정체성에 쓰지 않는다.
- 서로 다른 표본 주기는 정수배 공통 격자에서만 비교하며 보간하지 않는다. 짧거나 거친 과거 기록의 확인 범위는 실제 기록 격자에 한정된다. 비정상 시각·결측·NaN·회전·입력 해시 변경은 오류이며 통과가 아니다.
- 고정 제외 목록은 v87의 이전 카메라 위치 입력, v89 학습과 정지 로봇 위치, v88의 모든 발견된 pose 로그(중단/loaded/fine 포함), v91의 두 지도 r1/r2를 포함한다. r4/r5에 기록된 5개 이전 원본 해시가 전부 포함되는지도 검사한다. v91은 허용된 pose 로그의 세 운동 필드만 사용하며 오차·점수·영상·기타 raw는 읽지 않는다. v91 전체 파일 해시도 계산하지 않는다.
- v94 두 지도에서 r1/r2의 시작 x/y/yaw를 모두 다르게 고정한다. v88 unloaded와 같은 ±0.01/0.02/0.03의 10초 step+1초 coast, ±0.02 PRBS31(0.5초 chip)+2.5초 coast를 사용한다. 축 순서·step 부호 순서·PRBS 순환 위상은 새로 고정하며 두 로봇 모두 구동한다. 카메라/FOV·모델·접촉·weld OFF는 유지한다.
- 지도당 370 SIM s, 두 지도 740 SIM s, reset은 각각 최대 5 SIM s. B의 6개 horizon과 모든 학습 지원 split/axis/sign/level 셀을 각 로봇·지도별 검사한다(지도당 288셀). PRBS 장기 horizon은 부호가 바뀌는 완전한 창이며 셀 부호는 시작 명령의 부호다. PRBS에 학습에 없던 ±0.01/0.03을 요구하지 않는다.

## 사전검사와 수집 경계

`precheck_heldout_v94.py`는 수집과 같은 Scene·reset·schedule·ports·물리 step·두 로봇의 abort guard를 `render=False`로 실행한다. 카메라 capture는 호출하지 않고, 호출하면 오류다. 두 지도×두 로봇의 이전 자료와의 비중복, 새 자료 상호 비중복, 실제 발행 명령/지원 셀, 모든 물리 substep에서 벽 여유 ≥0.35 m와 이동량 상한 0.01 m를 검사한다. 정답은 사전검사/중단 interlock에만 사용하며 명령 보정에 사용하지 않는다. 사전검사에서 후보 예측·오차·점수는 계산하지 않는다.

실행 소스를 먼저 커밋하고 전용 SIM slot 아래 실행한다. 결과는 기본 체크아웃의 새 `outputs/heldout-v94-precheck-<timestamp>/`에 남긴다. `PRECHECK_ONLY`/`PRECHECK_NOT_COLLECTION`, 수집 false, 렌더링 false, B PASS null로 구분한다. ENOSPC는 HOST_ERROR이고 부분 자료를 보존한다. 실패 뒤 자료를 삭제하거나 같은 출력 폴더를 재사용하지 않는다.

수집은 조정자가 `collect.sh`로 실행한다. `V94_SOURCE_SHA`, `V94_PRECHECK_DIR`, `V94_COMMITMENT_COMMENT`가 필요하다. 조정자 슬롯을 빌릴 때만 `V94_SIM_SLOT`을 설정한다. 스크립트는 두 지도를 순서대로 수행하며 실패 시 중단한다. 수집 실행기는 사전검사 전체 SHA256 목록과 현재 번들/일정/소스의 일치, #219의 편집되지 않은 공개 약속 댓글과 해시, 그 댓글이 수집 시작보다 앞섬을 확인한다. 문서만 추가한 SHA는 실행 소스 closure가 같으면 허용하지만 raw에는 실제 수집 SHA를 따로 기록한다. GitHub 시각과 로컬 실행기 시각의 비교이며 암호학적으로 서명된 수집 시각은 아니다.

이번 PR은 새 rendered 자료의 수집·B 채점·모델 승격·실물 성공을 포함하지 않는다. 조정자는 실제 수집 뒤에도 새 검증기의 운동 관문을 반드시 다시 실행해야 한다. v94의 두 로봇을 모두 채점하는 수집 후 B 어댑터/수집 감사는 별도 검토 없이 기존 v91 입력 계약을 우회해 재사용하지 않는다.

## 참고 자료

- [#219 중복 궤적 정정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966843527)
- [#364 기존 회전 어댑터](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/364)
- [고정 기준 B](../2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json)
- [v91 입력 감사](../2026-10-03-critb-v91/README.md)
- [v91 물리 guard](../2026-10-03-calib-fast-guard/README.md)
