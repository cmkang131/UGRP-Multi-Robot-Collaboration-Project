# v7 롤러 충돌 근사로 시뮬레이션 속도 높이기 (2026-10-06)

**상태: DRAFT / DEV 옵션 / 병합 금지.** [PR #402](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/402)의 v7
(`sim/masterpi_drive_friction_v7.py`) 위에 쌓은 브랜치 `claude/v7-roller-approx`다.
v7은 FUJI 공개 모델의 convex barrel mesh 롤러를 바퀴당 9개 쓴다. S2 한 실행이 2.9 wall초/SIM초로
예전 wrench 구동(약 1.5)보다 느려서, TIAGo 논문과 같은 **롤러 충돌 근사**가 쓸 만한지 확인한다.
기본값·기존 번들·v102/v106·카메라·팔/물체 접촉은 바꾸지 않는다. 새 동작은 모두 명시적 옵션이며 기본은 기존 그대로다.
새 RGB 번들 ID는 예약하지 않았다. 새 진단 workflow `masterpi-v7-roller-approx-probe` 1.0.1
(원격 브랜치의 같은 id 없음, 기존 `masterpi-drive-friction-probe` 7.1.0은 그대로).

## 옵션 이름과 기본값

| 옵션 | 값 | 기본 | 설명 |
|---|---|---|---|
| `roller_collision` (`build_world(..., roller_collision=)`, `transform_xml(xml, params, roller_collision)`) | `mesh` / `sphere6_v1` | `mesh` | `mesh`는 기존 FUJI convex mesh, XML이 바이트 단위로 같다. `sphere6_v1`은 롤러마다 구 6개 |
| `idle_robot_contacts` (`build_world(..., idle_robot_contacts=)`) | `off` / `freeze_v1` | `off` | `freeze_v1`은 MuJoCo 공식 sleeping island: 로봇 트리만 sleep 허용, 다른 free body는 `never`(짐을 잡은 로봇은 안 잠김). 명령·servo ctrl이 바뀌면 월드 스텝이 직접 깨운다 |

기본 `mesh`에서는 구동 기록(`drive_profile_record`)과 XML이 이전과 같다. 옵션을 켠 실행만 기록에
`roller_collision*` 항목(구 좌표, 출처 커밋, 미확인 목록, 해시)이 추가된다.

## 근거 출처 (2026-10-06 조회)

| 항목 | 확인한 내용 | 상태 |
|---|---|---|
| [TIAGo 논문 §III-A, Fig. 3b](https://arxiv.org/html/2510.10273v1) | "각 롤러 collider를 구 6개로 모델링, Isaac Sim에서 매끄러운 움직임을 주면서 mesh/저폴리 collider보다 계산 효율이 높다" | 본문 확인. 속도 수치는 논문에 없음 |
| 논문이 따랐다는 [10] Wiedemann et al., ICRA 2024 ([DOI](https://doi.org/10.1109/ICRA57147.2024.10611459)) | 서지만 Crossref로 확인 | **원문 미확인** |
| [공개 USD](https://github.com/AIS-Bonn/tiago_isaac/tree/812ef55cdca2502dec6044ecddb08991ff41982d) `wheels/mecanum_wheel.usd`(15개 롤러, 링 반지름 .0895, 45°)가 `wheels/roller_link.usd`를 참조하고 `tiago_dual_functional.usd`가 네 바퀴에 이를 쓴다 | `roller_link.usd`: 구 6개(`collision_sphere_00..05`, `physics:approximation=boundingSphere`), 롤러 축(x) 위 위치 ±.02/±.012/±.005 m, 반지름 .01185/.0126/.0129 m, 마찰 .8. 시스템 `usdcat`으로 읽음 | 확인. 파일 해시와 blob은 `sim/assets/masterpi_drive_friction_v7_sphere6/source.json` |
| FUJI mesh 대조 | STL 반경 윤곽(중앙 .0130, 끝 .0110)이 구 반지름과 3% 안에서 맞음(단위 시험). 길이 단위가 미터임을 같이 확인 | 확인(시험) |
| MasterPi 환산 | 공식 바퀴 지름 65 mm / TIAGo 205 mm = **65/205**를 위치·반지름에 곱함(v2 mesh 배율과 같음) | 닮은꼴 가정, 실측 아님 |

AGPL-3.0 저장소이므로 파일을 복사하지 않고 구 6개의 숫자만 옮겼다. 설치된 MasterPi 롤러 형상, 6구가 MasterPi에서
mesh 견인력을 재현하는지, [10]의 원문은 **미확인**이다. 판단은 아래 동등성 표로만 한다.

## 사전 등록한 허용 기준 (실행 전에 고정, 결과를 보고 바꾸지 않음)

같은 조건(새 reset, 같은 HIGH 팔·long-lane/기존 lane, 같은 명령)에서 변형을 기준 `mesh`와 비교한다.
기준 값은 `scripts/probe_v7_roller_approx.py`의 `ACCEPT`와 같다. 변형은 `sphere6_v1`(`roller_collision`)과
`mesh_freeze`(`idle_robot_contacts=freeze_v1`)이며, 둘 다 같은 표로 판정한다.

| 항목 | 조건 | 기준 |
|---|---|---|
| 입력 20/30 정지 | 5 s 명령, 빈 로봇 | 두 변형 모두 명령 중 COM XY 이동 ≤ 1 mm (정지 판정 동일) |
| 입력 35/50/100 지속 주행 | 5 s 명령, 빈 로봇, cyan은 35/100 | 두 변형 모두 마지막 0.5 s 전진 속도 전 표본 > 1 mm/s(주행 판정 동일), 마지막 0.5 s 평균 속도 차 ≤ ±5% |
| 옆 이동 35 | 1.5 s, 빈 로봇 | 두 변형 모두 왼쪽 지속 이동, 총 yaw 차 ≤ ±0.5°, 옆 속도 차 ≤ ±5% |
| 정지 로봇 밀기(깨움 확인) | r1 입력 50 5 s, 멈춘 r2를 0.7 m 앞에 둠 | 두 변형 모두 r2가 > 5 cm 밀림, r1 x 이동 차 ≤ ±5%, r2 x 이동 차 ≤ ±10% |
| 짝 빔 1건 | 기존 v7 짝 빔 비교와 같은 설계 | 두 변형 모두 물리 실패 없음, 빔 world-y 이동 차 ≤ ±10%, 빔 yaw 변화 차 ≤ ±0.5°, 두 로봇 진행량 차이(r1−r2) 차 ≤ ±10% |
| 속도 | 입력 50 5 s 직진, 변형 번갈아 반복 | MuJoCo `mjTIMER_STEP` 기준 물리 전용 wall/SIM이 mesh 대비 **1.2배 이상**이어야 채택 |

기준을 하나라도 넘으면 채택하지 않고 수치 그대로 보고한다. 구 배치·반지름·마찰·질량은 결과를 보고 조정하지 않는다.
mesh 쪽 재측정은 기존 v7 기록(`v7-results.json`)과 값이 같아야 기본 경로가 안 바뀐 것이다.
채택은 "기본값은 off인 옵션으로 쓸 수 있다"는 뜻이며 기본 프로필·기존 번들을 바꾸지 않는다.

## 측정 계획

1. 프로파일(짧은 정지·직진·cyan 하중, 변형 4개 + 롤러 마찰 행 제거 ablation 1개): MuJoCo 단계 타이머, 접촉 수,
   제약 행 수, 풀이 반복, 파이썬/계측 비율. ablation은 `dof_frictionloss`를 런타임에 0으로 하는 원인 추적용이며 옵션이 아니다.
2. 렌더 비율: 운영 경로 `render_jpeg`(robot_cam) 프레임당 시간과 S2 기록의 프레임 수로 추정.
3. 동등성 표와 속도 반복.
4. 모든 실행은 `status == null` 확인 뒤 자기 PID로 잠금(인계 전 `claude`, 인계 후 `codex`), 끝나면 바로 release.

## Codex 인계 및 남은 측정의 사전 고정

`f051e1968c8424ad11eb4a121f1e58f2af1a6bdb`까지 clean/pushed 확인. 기존 12개 profile
(`5a0544d3`)와 30개 equivalence (`f051e196`)는 완료된 Claude 실행으로 분리해 인용한다.
이미 sphere6의 속도/yaw/빔, mesh_freeze의 빔 동등성 실패를 확인했으므로 재튜닝하지 않는다.
인계 후 변경은 실행 소유자, 입력 검사와 결합 옵션의 속도 판정 기록뿐이며 물리 구현은 그대로다.
workflow는 소유자 인계를 나타내는 1.0.1, RGB 번들 추가 없음.

추가 실행 **전에** 아래 범위를 고정한다. 탐색 DEV 진단이며 새 확증 코호트가 아니다.

- 빠진 `sphere6_freeze`에 기존 표의 모든 허용 기준을 그대로 적용하고 mesh와 10건씩 비교한다.
- 네 조합의 input50 5s+stop1s를 각각 3회, 순서를 정방향/역방향/정방향으로 교대한다.
  `mjTIMER_STEP / sim_s`와 Python 계측 포함 wall/SIM을 모두 기록한다. speed gate는 1.2배 그대로다.
- `mesh`와 `mesh_nofl`의 rest/empty50/cyan50만 비교해 롤러 frictionloss 108행 비용을 분리한다.
  이것은 채택 가능한 옵션이 아니며 동등성/속도 phase에서 사용을 거부한다.
- 네 조합의 기존 `robot_cam` JPEG 경로를 5 warmup+40 frames 측정한다. 카메라/FOV/외관 변경 없음.
- `launch_remaining.zsh <SHA>`는 S2 잠금이 `null`일 때까지 `until`로 기다린다.
  각 자식이 원자적 acquire(owner=codex, 자신의 PID) 후 실행하고 finally에서 자기 잠금만 반환한다.
  모든 측정은 직렬·최대 phase당 900초이며 다른 실행을 중지하지 않는다.
  ENOSPC/실행 오류는 HOST_ERROR로 기록하며 완료/동등성으로 세지 않는다.
- TensorBoard는 새 수치 스냅샷을 실제 이벤트 값으로 대조한다. 사용자 요청에 따라 UI는 열지 않는다.

공개 USD 두 파일을 고정 commit에서 다시 받아 기록된 SHA-256 및 기존 원본과 일치함을 확인했다.
구 중심/반지름은 **roller 로컬 좌표**이다. wheel 루트의 추가 `xformOp:scale=0.976`도 확인했다.
이 옵션은 사용자 지정 65/205와 기존 FUJI 배율을 그대로 적용하며, USD 전체 조립체의 world 치수를
그대로 복제했다는 의미가 아니다. 설치된 MasterPi 형상·실물 견인력은 계속 미확인이다.

## 최종 측정 결과 (2026-10-06)

**판정: sphere6_v1, mesh+freeze, sphere6+freeze 모두 미채택.** 기본 mesh/off 유지.
sphere6는 더 많은 접촉·제약 행을 만들며 단독으로는 느려졌다. freeze는 정지 로봇 비용을 줄였지만
짝 빔 동등성을 깨뜨렸다. 기준·구 위치·반지름·마찰·질량은 결과에 맞춰 바꾸지 않았다.

### 시간이 쓰인 곳

`5a0544d3` 원본 12건. 아래 비율은 MuJoCo STEP 시간 분모이며, 단계의 중첩을 중복 합산하지 않았다.
`pos_project`는 제약 공간 관성/행렬 계산, `constraint`는 제약 풀이이다.

| 조합·조건 | 접촉 평균 | 제약 행 평균 | solver[0] 반복 평균 | 충돌 % | 제약 행렬 % | 풀이 % | 물리 wall/SIM | 계측 포함 wall/SIM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mesh / rest | 16.00 | 158.26 | 4.82 | 27.5 | 27.4 | 25.7 | 0.822 | 1.079 |
| sphere6_v1 / rest | 28.00 | 195.00 | 4.00 | 23.2 | 35.1 | 23.1 | 0.929 | 1.183 |
| mesh_freeze / rest | 4.00 | 12.00 | 2.46 | 45.4 | 4.7 | 12.1 | 0.126 | 0.411 |
| sphere6_freeze / rest | 4.00 | 12.00 | 2.45 | 54.1 | 4.0 | 10.2 | 0.145 | 0.421 |
| sphere6_freeze / empty-f050 | 13.18 | 74.65 | 8.13 | 26.0 | 27.0 | 25.7 | 0.442 | 0.732 |
| mesh_freeze / empty-f050 | 9.22 | 62.78 | 5.62 | 29.7 | 24.0 | 21.5 | 0.363 | 0.655 |
| sphere6_v1 / empty-f050 | 29.66 | 199.82 | 8.48 | 21.4 | 35.6 | 25.6 | 1.022 | 1.281 |
| mesh / empty-f050 | 17.62 | 163.42 | 5.00 | 27.5 | 28.7 | 24.9 | 0.868 | 1.142 |
| mesh / cyan-f050 | 21.22 | 173.28 | 7.47 | 23.9 | 31.8 | 27.4 | 0.996 | 1.257 |
| sphere6_v1 / cyan-f050 | 34.11 | 212.34 | 8.82 | 19.4 | 37.2 | 27.7 | 1.160 | 1.424 |
| mesh_freeze / cyan-f050 | 13.23 | 75.70 | 7.41 | 22.6 | 31.6 | 27.0 | 0.508 | 0.797 |
| sphere6_freeze / cyan-f050 | 18.15 | 90.46 | 8.82 | 20.0 | 33.7 | 29.5 | 0.616 | 0.912 |

mesh empty50에서 STEP 바깥 Python·상태/접촉 계측은 wall의 24.0%이다. 렌더는 이 physics 진단에서 꺼져 있다.
solver 반복은 첫 island의 기록값이며 모든 island 총합으로 해석하지 않는다.

### frictionloss 원인 진단

`84e62dd1`의 mesh 대 mesh_nofl. 108개 롤러 joint frictionloss만 0으로 한 ablation이며 채택 옵션이 아니다.

| 조건 | mesh 제약 행 → ablation | 물리 wall/SIM 전 → 후 | 계측 wall/SIM 전 → 후 |
|---|---:|---:|---:|
| rest | 158.26 → 50.46 | 0.815 → 0.512 | 1.064 → 0.756 |
| empty-f050 | 163.42 → 55.38 | 0.834 → 0.527 | 1.079 → 0.772 |
| cyan-f050 | 173.28 → 64.62 | 0.983 → 0.601 | 1.236 → 0.852 |

행 제거는 물리 모델도 바꾸므로 이 속도를 동등한 v7 가속으로 채택하지 않는다.

### 네 조합 wall/SIM 전후

`84e62dd1`, empty input50 5 SIM초 + stop1초, 각 3회 교대, 렌더 off.
물리 전용은 mjTIMER_STEP/6초, 계측 포함은 전체 진단 loop wall/6초다. 초기 모델 생성·staging은 제외한다.
S2 전체 운반(2.9–3.3 wall/SIM)과는 다른 분모/작업이며 S2 가속 실적으로 대체하지 않는다.

| 조합 | 물리 wall/SIM 평균 (범위) | 계측 wall/SIM 평균 (범위) | 물리 가속 mesh/후 | 1.2× 게이트 |
|---|---:|---:|---:|---|
| mesh | 0.819 (0.817–0.822) | 1.070 (1.065–1.075) | 1.000× | 기준 |
| sphere6_v1 | 0.996 (0.994–1.000) | 1.250 (1.246–1.257) | 0.822× | 실패 |
| mesh_freeze | 0.362 (0.357–0.369) | 0.647 (0.634–0.660) | 2.261× | 통과 |
| sphere6_freeze | 0.460 (0.450–0.466) | 0.752 (0.736–0.761) | 1.779× | 통과 |

### 동등성 표

sphere6와 mesh_freeze는 인계된 `f051e196`(Claude), sphere6_freeze는 `84e62dd1`(Codex) 결과다.
각 후보의 같은 실행에서 측정한 mesh를 기준으로 한다. 후속 mesh 10건의 물리 결과는 인계 mesh와 정확히 같다.
기존 v7 기록과 일치하는 기본 8건의 6개 필드 검산도 [결과 JSON](results-summary.json)에 남겼다.
후속 mesh 10건의 전체 trace 해시와 조합별 짝 빔 staging/drive 명령 파일 10개의 동일성은
[작업 기록](work-record.json)에 따로 검증했다.

| 항목 | mesh 기준 | sphere6 | mesh+freeze | sphere6+freeze |
|---|---:|---:|---:|---:|
| empty-f020 | 0.01909 mm | 0.00511 mm / 통과 | 0.00000 mm / 통과 | 0.00000 mm / 통과 |
| empty-f030 | 0.01909 mm | 0.00511 mm / 통과 | 0.00000 mm / 통과 | 0.00000 mm / 통과 |
| empty-f035 | 0.138039 m/s | 0.126756 m/s (-8.17%) / 실패 | 0.137844 m/s (-0.14%) / 통과 | 0.126791 m/s (-8.15%) / 실패 |
| empty-f050 | 0.220861 m/s | 0.208109 m/s (-5.77%) / 실패 | 0.220725 m/s (-0.06%) / 통과 | 0.208118 m/s (-5.77%) / 실패 |
| empty-f100 | 0.496537 m/s | 0.445549 m/s (-10.27%) / 실패 | 0.496352 m/s (-0.04%) / 통과 | 0.452770 m/s (-8.81%) / 실패 |
| cyan-f035 | 0.137329 m/s | 0.126490 m/s (-7.89%) / 실패 | 0.137469 m/s (+0.10%) / 통과 | 0.126493 m/s (-7.89%) / 실패 |
| cyan-f100 | 0.492432 m/s | 0.443704 m/s (-9.90%) / 실패 | 0.494399 m/s (+0.40%) / 통과 | 0.443791 m/s (-9.88%) / 실패 |
| empty-left035 | 0.124627 m/s; -2.488° | 속도 -14.02%; yaw Δ-4.756° / 실패 | 속도 -0.06%; yaw Δ-0.041° / 통과 | 속도 -14.01%; yaw Δ-4.761° / 실패 |
| empty-bump050 | r1 0.803867 m; r2 0.286981 m | r1 -4.850%; r2 -13.606% / 실패 | r1 +0.005%; r2 -0.002% / 통과 | r1 -4.859%; r2 -13.629% / 실패 |
| pair-beam | y 0.030529 m; yaw -3.352°; r1−r2 0.054550 m | y -35.06%; yaw Δ-0.021°; 진행 차 +0.65% / 실패 | y -16.85%; yaw Δ-0.844°; 진행 차 +24.03% / 실패 | y -32.72%; yaw Δ-0.117°; 진행 차 +2.86% / 실패 |

| 후보 | 동등성 통과 항목 | 속도 게이트 | 채택 |
|---|---:|---|---|
| sphere6_v1 | 2/10 | 실패 | 미채택 |
| mesh_freeze | 9/10 | 통과 | 미채택 |
| sphere6_freeze | 2/10 | 통과 | 미채택 |

이는 조건별 동등성 항목 수이며 로봇 임무 성공률이 아니다. 빔 사례는 고정 teacher staging의 작은
perturbation 한 건이며 물리 실패 없이 끝나도 동등성은 실패할 수 있다. weld OFF, 외부 모델 호출 0.

### 렌더 비용

동일 robot_cam 640×480, JPEG 기본 quality82, warmup5 제외 40 frame/조합,
정지 HIGH 자세의 운영 render_jpeg 호출을 측정했다. S2 실제 경로도 CameraRobotPort에서 기본 quality82를 쓴다.

| 조합 | 평균 ms/frame | 최저 ms/frame |
|---|---:|---:|
| mesh | 52.015 | 50.635 |
| sphere6_v1 | 52.113 | 50.758 |
| mesh_freeze | 51.971 | 50.629 |
| sphere6_freeze | 51.855 | 50.843 |

완료된 별도 S2 s1039 기록은 134.85 SIM초 / 386.514 wall초 / 자기 RGB 2612 frames다.
단순 n×mesh 프레임 비용은 135.86초(전체 wall의 35.2%)다.
이는 자세·렌더 프로필·카메라 설정이 다른 실행을 곱한 **추정**이고 S2 내부 타이머 분해가 아니다.
디코드·파일 저장·제어기 비용은 미포함이며, S2 2.9–3.3의 나머지 원인을 이 진단만으로 확정하지 않는다.
[계산 근거와 원본 해시](render-s2-estimate.json).

### 검증·보존 범위

로컬 변경 관련 시험 3파일 **27 passed**. 기본 XML 바이트 동일, 동역학/외관/접촉 속성 보존,
구 배치·반지름, wake-on-command/servo-change, 결합 옵션·판정 함수를 검사했다.
인계 42건 + Codex 42건 = 완료 진단 84건을 분리 기록했다. 무작위 일반화·S2 운반 성공·실물 검증은 아니다.
`78a9e3df` 초기 profile은 타이머 enum 순회 TypeError로 종료한 실패 기록이며 완료 84건에 포함하지 않았다.
그 뒤 고친 `5a0544d3` 및 이후 관리 manifest의 clean SHA/exit0/source unchanged와 모든 raw 파일 해시를 검증했다.

수치·판정·환경·SHA: [results-summary.json](results-summary.json). 원본/관리 로그 목록: [artifacts.sha256.json](artifacts.sha256.json).
원본은 primary outputs에 보존하며 삭제·덮어쓰기하지 않았다. 커밋한 요약/해시는 raw의 원격 백업이 아니다.
새 TensorBoard snapshot: `outputs/tensorboard/1006-v7-roller-84e62dd1`.
[TensorBoard 수치 대조](tensorboard-verification.json), [대시보드](http://127.0.0.1:6006/?runFilter=1006-v7-roller-84e62dd1#timeseries).
84개 기록의 **1,124개 수치**가 원본 → EventAccumulator → 기존 서버 API와 일치했다.
사용자 요청대로 이벤트/서버 수치만 대조하고 UI와 다른 작업 서버는 변경하지 않았다.
[DRAFT PR #407](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/407), PR #402 위에 쌓음. **병합하지 않음.**

후속 제약: freeze 접촉 readout 누락과 짝 빔 오차, sphere6 견인력/옆 회전 오차는 해결되지 않았다.
채택 실패를 우회하는 추가 튜닝·기준 완화·기본 번들 반영은 하지 않았다.

## PR #407 독립 리뷰 반영 (2026-10-09)

- 최신 main을 merge하고 freeze/sphere6/probe 시험 3개를 `scripts/run_ci_tests.py`에 등록했다. workflow 안내를 1.0.1로 바로잡았다.
- 로컬 해당 3파일: **26 passed, 1 deselected**. 시뮬레이션 0 지시에 따라 실제 `mj_step`을 호출하는 `test_timer_snapshot_reads_every_mujoco_stage`만 로컬에서 제외했고 CI에는 전체를 등록했다. XML 컴파일·mock step·기본 OFF 바이트 동일 검사는 통과했다.
- `--shard-count 8 --list-shards`: coverage_verified=true, 새 파일이 각각 정확히 1번 포함된다. v7 소스·sphere6 source.json·camera v3는 수정하지 않았다.
- 참고: [pytest 선택 실행 공식 문서](https://docs.pytest.org/en/stable/how-to/usage.html), [Git merge 공식 문서](https://git-scm.com/docs/git-merge). 기존 CI의 TEST_PATTERNS 등록 방식을 그대로 사용하며 새 물리 방법은 도입하지 않았다.
