# release17 — FOV 복구를 한 번의 0.1 s 펄스로, yaw 부호·크기 보정 프로필

기준 `be2d749adb4fd4eb38421fa19aa981e0eb195c4b`, 작업 브랜치 `claude/grasp-act-probes`(PR #491 head는 별도 브랜치).
근거 보고서: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/release16-be2d749a/report.md`와 같은 폴더의 재현 스크립트 11개.
새 선택은 **`--release-profile release17_v1`**, 기본 `off`. 이전 프로필 결과와 합산하지 않는다. 실행 SHA는 이 기록을 포함한 최종 push HEAD와 새 큐에 고정한다.
[저장 원장 재생 결과](release17-replay.json) · [진단 계획](release17-diagnostic-plan.json) · [시드 감사](release17-seed-audit.json) · [시험 출력](release17-tests.txt).
물리 효과는 **미검증**이다(시뮬레이션은 Mac에서 돌리지 않았고 저장 원장만 재생했다).

## 토글 둘 (서로 따로 켠다)

|토글|켜는 법|바뀌는 것|기본|
|---|---|---|---|
|A1 `release_fov_step_pulse_v1`|`--release-fov-step release_fov_step_pulse_v1` (release17 프로필만)|`LineAlign`의 FOV 복구 걸음 4 mm(31 ms) 마이크로 펄스 → 0.1 s·레벨 0.35 한 펄스(공칭 12.9 mm)|off|
|A2 `yaw_cal_v1`|`--command-motion yaw_cal_v1` (release17 프로필만)|오도메트리 yaw 부호·크기(Y>0=반시계, 3.0 rad/(레벨·s)), 회전 계획, 첫 yaw 펄스 뒤 자기 RGB 부호 확인|off (`native_yaw_v1` 그대로)|

네 조합(A1/A2 각각 on/off)을 `tests/test_release17.py`가 실제 실행기(가짜 백엔드)로 통과시킨다. 두 토글이 꺼진 release17은 release16과 같은 31 ms 마이크로 펄스를 낸다(시험으로 확인; 전체 실행 비트 동일성은 증명하지 않았다).
`native_yaw_v1`은 값·주석 모두 바이트 그대로 둔다(옛 실행 재생용). release8 주석의 "부호 검증됨"은 아래 감김 재독으로 대체됐다.

## A2 근거 — 저장 원장 재생 (n/N)

|항목|결과|
|---|---|
|고립 yaw 펄스(r12d–r16d, 0.2 s 창) 부호|`yaw_cal_v1` **11/11**, `native_yaw_v1` 0/11|
|그 펄스의 GT÷예측 크기|중앙 0.93 (0.62–1.02, n=11)|
|회전 열(release7·8, >30°, 감김 푼 GT) 부호|`yaw_cal_v1` **18/18**|
|그 회전 열의 GT÷예측|중앙 1.024 (1.019–1.029); 이는 3.057–3.087 rad/(레벨·s)|
|`rotate_plan(±90°)`|15펄스(native는 45펄스), 모델 적분 90.0°|

크기 3.0은 회전 열 3.07–3.08과 짧은 펄스 중앙 약 2.8의 사이 값으로 고른 반올림이다. 튜플에는 레벨 0.35에서의 rad/s인 **1.05**를 넣는다(3.0×0.35). 별도 PR #510(`drive_model_deadband_v1`)은 같은 요 항을 물리 모델로 1.0146 rad/s로 보며 실측 약 1.03과 맞는다. 두 PR 모두 `sim/visible_belief.py`를 건드리므로 병합 충돌 가능성이 있다(1.05는 3.0의 반올림이고 1.0146은 물리 모델 값이다. 병합 순서·통일은 메인 판단).

**부호 확인(자기 RGB)**: `LineAlign`에서 yaw가 지배적인 첫 펄스(모델이 예측한 빔 중심 이동 ≥10 px, yaw 항이 횡 항의 2배 이상) 뒤 다음 영상의 `center_error` 변화가 예측과 같은 방향이면 확인, 반대로 6 px 이상이면 `release17_yaw_cal_sign_mismatch`로 **실행 중단·제어 실패 기록**(HOST_ERROR 아님). 6 px 미만은 판단 불가로 두고 다음 펄스에서 다시 본다. 이전 저장 펄스 9/9에서 GT yaw와 `center_error` 방향이 일치했다(보고서 `yaw_image_check.py`).
**이 확인이 보지 못하는 것**: 둘러보기 회전(`rotate_plan`)은 빔이 없는 영상도 있어 확인을 붙이지 못했다. 첫 둘러보기 회전의 부호 오류는 이 확인으로 잡히지 않는다.

### yaw_cal_v1을 켜면 같이 바뀌는 곳 (git grep native_yaw / odometry / rates / rotate_plan)

- 바뀜: `LineAlign`(release14 `pulse_for`)의 yaw 펄스, `sim/lookaround_localization.rotate_plan`을 쓰는 둘러보기·`release_nbv_observation`·`release_global_observation`·`release_setdown_lookaround`의 회전 계획, `odometry()`를 쓰는 `CommandPose`·`ReleaseTeacher.belief`·`LookaroundLocalizer.own/command_own`, `RealignRecovery`(`rates()` yaw로 펄스·누적 yaw 상한), `release_axis_correction`(`rates()` yaw).
- 안 바뀜: `release_global_observation`의 `rates()` 기본 호출(축·횡만 사용), 상수 `YAW_RATE_RAD_S`(기록용 그대로, 새 프로필일 때만 `profile_yaw_rate_rad_s`가 추가로 기록됨), `off`·`gcp_probe_v1`·`native_yaw_v1`.
- 위험(미검증): `release_axis_correction`은 yaw 항이 1/3로 줄어 펄스 하한(40 ms) 검사 `axis_correction_pulse_window`로 거절할 수 있다. 쌍 운반 요 이득은 단독 로봇과 다르다(`gcp_probe_v1` 주석: 1.68배). 둘 다 이 토글에서 다루지 않았다.
- `scripts/replay_release15.py:63`, `scripts/replay_release16.py:152`는 `native_yaw_v1`을 고정한다. 옛 실행 재생에는 맞지만 `yaw_cal_v1` 실행 원본 재생에는 쓰지 말 것.
- **알려진 한계(미측정 영역)**: 저장된 `line_ibvs`/`recover_direction` yaw 요청 11개를 `yaw_cal_v1`로 환산하면 가장 긴 바퀴 펄스가 13–39 ms(중앙 24 ms), 11/11이 40 ms 미만이다. 저장된 yaw 펄스 중 가장 짧은 것이 약 40 ms였고 4 mm 병진 31 ms 열은 0.71–0.87배로 불안정했다. yaw 펄스 길이 의존은 측정된 바 없다. 바닥 펄스(40 ms)를 넣으면 한 번에 2.4°가 되어 정렬 허용을 넘길 수 있어 이 토글에는 넣지 않았다.

## A1 근거와 **지시문과 다르게 한 곳**

지시문의 "새 RGB `fov_merit` 감소가 예측의 절반 미만이면 다음 한 번 0.15 s" 규칙은 그대로 쓰면 이 장면에서 정상 이동을 정체로 오판한다. 저장 원장(보고서와 같은 r15d·r16d, 같은 로봇 정렬 7개, `merit_plateau`)에서:

- `fov_merit`은 맡은 끝 띠가 사용 영역 위쪽 경계(행 13, 첫 사용 가능 행)에 잘린 동안 **8978로 고정**이다. 관측 merit이 처음 줄어든 실제 전진은 31.4, 36.1, 35.7, 41.0 mm(완료 3 + 실패 1; 나머지는 해당 없음/미관측 표시)이고 `fov_safe`는 47.4–77.8 mm에서야 참이다.
- 같은 정렬들에서 공칭 평면 모델은 26–28 mm에서 merit 0을 예측한다. 그래서 첫 펄스(12.9 mm) 뒤에는 관측 merit이 그대로여서 "감소 < 예측의 절반"이 되고, 0.15 s 한 번 더(누적 약 32 mm) 뒤에도 같아서 **정상 이동 중에 즉시 실패**한다.
- 대신 잘리지 않은 상자 가장자리(예: 아래쪽 y1)는 이동을 그대로 보인다. 저장 열에서 전진 약 1.5 mm에 +4 px, 약 11 mm에 +28 px, 12 mm에 +33 px였다. 정지 열(74976 r1, 0.7 mm)은 ±2 px였다.

구현한 진척 판정(`edge_progress`, 자기 RGB·발행 명령·고정 카메라 모델만): 펄스 직전·직후 영상의 **사용 영역 경계에 닿지 않은** 상자 가장자리들을, 실제 낸 펄스의 `project_motion` 예측과 비교해 관측 이동 합이 예측 합의 절반 이상이면 진척이다. merit 감소가 예측의 절반 이상이어도 진척이다(merit은 진척을 더할 뿐 정체를 선언하지 못한다). 전부 잘렸거나 예측이 6 px 미만이면 판단 불가로 두고 기존 3 s 무진척 규칙에 맡긴다.
저장 쌍 검증(GT는 쌍 고르기에만 사용): 실제 9–17 mm 전진 쌍 **197/200 진척**(오판 3개는 9.0–9.9 mm 쌍, 점수 0.39–0.47), 실제 정지 쌍 **106/106 정체**(점수 −0.08–0.10).

정체 1회 → 다음 펄스 0.15 s(공칭 19.4 mm), 그것도 정체면 `release17_no_recover_fov_progress`로 즉시 실패. 진척이면 정체 횟수 초기화. 예측이 가장자리를 넘기면 시도하지 않고 기존 `fov_blocked` 실패.
`motion_cap`: 진척한 펄스는 지시량 전체를, **정체한 펄스는 영상이 보여 준 점수만큼만** 누적한다(나머지 환급). 지시량 기준 누적이 74963 r2를 100 mm에서 멈췄던 문제(실제 78 mm)에 대응한다. 한계: 진척 펄스는 공칭(12.9 mm)으로 센다. 전진 필요량이 4–6펄스(47–78 mm)이므로 상한 0.10 m 안이지만 8펄스는 103 mm로 넘는다.

재현 시드 저장 첫 영상 재생(`fov`): 74963 r2(t=91.2)와 74976 r1(t=91.6) 모두 release15 재생이 저장 명령(4 mm, merit 8978→6517)을 그대로 재현했고, release17은 12.9 mm·0.1 s 4바퀴, 예측 merit 8978→2312, 저장 지도 여유 통과, 0.15 s 단계도 후보 존재. 공칭 모델은 2펄스면 안전으로 보지만 위 관측으로 실제로는 4–6펄스 필요하다. 이 재생은 판정 분기이며 물리 결과가 아니다.

## 큐

새 대기열 `20261015-release-gate-<sha8>.json`: 재현 2(74963, 74976) + 새 시드 7(`release17_diagnostic` 78480–78486), 모두 `approved/enabled/ready/stage_ready` false. 관문 40개는 승인되지 않았다. 결과는 이전 프로필과 합산하지 않는다. 새 시드는 `configs/grasp_act_seed_splits.json`에 등록(학습 금지)했다.

## 확인 안 됨

- 물리 효과 전부(0.1 s 펄스가 접촉·정지 상태에서 반복해서 가는지, 0.15 s 단계 효율, 4–6펄스 뒤 실제 `line` 확보).
- yaw 크기의 펄스 길이·레벨·부하 의존(위 알려진 한계), 쌍 운반 요 이득.
- 둘러보기 회전의 자기 RGB 부호 확인(미구현).
- 시드 감사는 원격 이력을 조회하지 않았다(원격 접속 금지).

## 참고 자료 — 확인 범위 (2026-10-15)

아래는 `release16-be2d749a/report.md`가 서지·초록 수준으로 확인한 출처를 옮긴 것이며 **이번 작업에서 본문을 새로 읽지 않았다**. 알고리즘을 이식했다고 주장하지 않는다.

- Corke & Hutchinson (2001), *A new partitioned approach to image-based visual servo control*, IEEE T-RA. [서지](https://experts.illinois.edu/en/publications/a-new-partitioned-approach-to-image-based-visual-servo-control/): 분할 접근(병진과 회전 분리)과 가장자리 퍼텐셜. 복구 구간을 병진만으로 하고 퍼텐셜 대신 `fov_merit`을 쓰는 근거. 수렴 보장은 가져오지 않았다.
- Chaumette & Hutchinson (2006), *Visual servo control, part I: basic approaches*, IEEE RAM. [서지](https://www.irisa.fr/lagadic/publi/publi/Chaumette06a-eng.html): IBVS 기본 구조와 상호작용 행렬. 이 코드의 `image_jacobian`·`project_motion`이 같은 계통.
- Chesi 외 (2004), IEEE T-RO, DOI 10.1109/TRO.2004.829456: 시야 유지를 위한 전환. 퍼텐셜 형태는 **미열람**. 이쪽은 후진으로 시야를 유지하지만 우리는 가까이 가야 시야가 열려 방향이 반대다.
- Armstrong-Hélouvry 외 (1994), Automatica 30(7), DOI 10.1016/0005-1098(94)90209-7: 마찰 보상 조사. 마이크로 펄스 효율이 불안정한 이유(정지 마찰·데드존)와 펄스 길이를 늘리는 쪽 근거. 개별 기법은 **미확인**.
- Tao & Kokotovic (1994) 데드존 역함수: 후속 논문 참고문헌으로만 확인했고 초록도 보지 못했다. **미확인**.
- Jägersand 외 (1997), 온라인 야코비안 추정: 이번에 쓰지 않았다(보고서의 대안 B, 마이크로 펄스에서 반응이 0이면 갱신이 폭주할 수 있어 보류).
- 이 프로젝트 자료: 저장 원장 `/Users/changmin/projects/ugrp/outputs/gcp1-runs/`(r12d–r16d, release7·8)와 재현 스크립트 `scripts/replay_release17.py`.
