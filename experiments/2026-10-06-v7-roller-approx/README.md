# v7 롤러 충돌 근사로 시뮬레이션 속도 높이기 (2026-10-06)

**상태: DRAFT / DEV 옵션 / 병합 금지.** [PR #402](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/402)의 v7
(`sim/masterpi_drive_friction_v7.py`) 위에 쌓은 브랜치 `claude/v7-roller-approx`다.
v7은 FUJI 공개 모델의 convex barrel mesh 롤러를 바퀴당 9개 쓴다. S2 한 실행이 2.9 wall초/SIM초로
예전 wrench 구동(약 1.5)보다 느려서, TIAGo 논문과 같은 **롤러 충돌 근사**가 쓸 만한지 확인한다.
기본값·기존 번들·v102/v106·카메라·팔/물체 접촉은 바꾸지 않는다. 새 동작은 모두 명시적 옵션이며 기본은 기존 그대로다.
새 RGB 번들 ID는 예약하지 않았다. 새 진단 workflow `masterpi-v7-roller-approx-probe` 1.0.0
(원격 브랜치의 같은 id 없음, 기존 `masterpi-drive-friction-probe` 7.1.0은 그대로).

## 옵션 이름과 기본값

| 옵션 | 값 | 기본 | 설명 |
|---|---|---|---|
| `roller_collision` (`build_world(..., roller_collision=)`, `transform_xml(xml, params, roller_collision)`) | `mesh` / `sphere6_v1` | `mesh` | `mesh`는 기존 FUJI convex mesh, XML이 바이트 단위로 같다. `sphere6_v1`은 롤러마다 구 6개 |
| `idle_robot_contacts` | 검토 결과는 아래 | 없음(off) | 아래 "정지 로봇 접촉 축소 검토" 참고 |

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

같은 조건(새 reset, 같은 HIGH 팔·long-lane/기존 lane, 같은 명령)에서 `mesh`와 `sphere6_v1`을 비교한다.
기준 값은 `scripts/probe_v7_roller_approx.py`의 `ACCEPT`와 같다.

| 항목 | 조건 | 기준 |
|---|---|---|
| 입력 20/30 정지 | 5 s 명령, 빈 로봇 | 두 변형 모두 명령 중 COM XY 이동 ≤ 1 mm (정지 판정 동일) |
| 입력 35/50/100 지속 주행 | 5 s 명령, 빈 로봇, cyan은 35/100 | 두 변형 모두 마지막 0.5 s 전진 속도 전 표본 > 1 mm/s(주행 판정 동일), 마지막 0.5 s 평균 속도 차 ≤ ±5% |
| 옆 이동 35 | 1.5 s, 빈 로봇 | 두 변형 모두 왼쪽 지속 이동, 총 yaw 차 ≤ ±0.5°, 옆 속도 차 ≤ ±5% |
| 짝 빔 1건 | 기존 v7 짝 빔 비교와 같은 설계 | 두 변형 모두 물리 실패 없음, 빔 world-y 이동 차 ≤ ±10%, 빔 yaw 변화 차 ≤ ±0.5°, 두 로봇 진행량 차이(r1−r2) 차 ≤ ±10% |
| 속도 | 입력 50 5 s 직진 3회씩 번갈아(A B B A A B) | MuJoCo `mjTIMER_STEP` 기준 물리 전용 wall/SIM이 mesh 대비 **1.2배 이상** 빨라야 채택 |

기준을 하나라도 넘으면 채택하지 않고 수치 그대로 보고한다. 구 배치·반지름·마찰·질량은 결과를 보고 조정하지 않는다.
mesh 쪽 재측정은 기존 v7 기록(`v7-results.json`)과 값이 같아야 기본 경로가 안 바뀐 것이다.

## 측정 계획

1. 프로파일(짧은 직진·정지·cyan 하중): MuJoCo 단계 타이머, 접촉 수, 제약 풀이 반복, 파이썬/계측 비율.
2. 렌더 비율: 운영 경로 `render_jpeg`(robot_cam) 프레임당 시간과 S2 기록의 프레임 수로 추정.
3. 동등성 표와 속도 반복.
4. 모든 실행은 `status == null` 확인 뒤 자기 PID로 잠금(`--owner claude`), 끝나면 바로 release.
