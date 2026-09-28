# 공동 운반 v7: ㄱ자 측면 파지 설계

2026-09-28 · 브랜치 `claude/pair-v7-side-grasp` · 기반 `origin/main` `d5bd208e` · Refs #221

**설계 문서만 있다.** 코드 변경, pytest, 시뮬레이션, 학습, 모델 호출은 모두 0회다(배터리 전원, 충전 불가). 아래의 수치 임계값은 v6·#248의 기존 값이거나, 이 문서에서 처음 제안하는 개발 가설이다. 가설 값은 "가설"로 표시했다. 어느 것도 물리로 확인하지 않았다.

## 0. 배경과 결정 필요 사항

- 9/9 사용자 요청으로 공동 파지는 **ㄱ자 측면 파지**였다. 두 몸체는 같은 방향(막대에 수직)을 보고, 팔 yaw ±90°로 막대 축을 따라 안쪽을 향한다([`2026-09-09-side-grasp`](../2026-09-09-side-grasp/README.md), [`2026-09-09-loaded-transport`](../2026-09-09-loaded-transport/README.md), `scripts/probe_dual_grasp_sync.py --side-grasp`).
- 9/25 카탈로그(`sim/zone_cargo.py`, commit `87eaac86`, `long_beam` grasp `approach_yaw` 0/π)부터 두 로봇이 **서로 마주 보고 팔을 곧게** 편다. 이 전환의 사용자 결정 기록은 없다. M2·v5·v6(#246)는 이 방식을 이어받았다.
- 막대의 grasp 점은 두 방식이 같다. 몸체 방향과 팔 yaw만 다르다.
- #248 분석(`experiments/2026-09-28-ultrasonic-range/side_grasp_pair_analysis.json`, 운동학만)의 요점:
  - 횡 이동(막대에 수직)은 몸체 전진이다. 초음파가 앞을 본다.
  - 축 이동과 문 통과는 strafe다. 0.5 m 문에서 한쪽 여유는 0.156 m다.
  - ±90°는 손목 카메라 보정 범위(PWM 1300–1700, `harness/visual_arm.py` `CALIBRATED_PAN_MIN/MAX`) 밖이다.
  - lateral odometry(`CARRY_ODOM_SCALE` lateral 0.697)는 마주 보기 방식에서 잰 값이다.
- #249(외관 v3)는 팔 yaw 축을 차체 중심 앞 48.2 mm로 옮기고, 초음파를 전방 88 mm·높이 61.7 mm에 둔다.

**사용자 결정 필요(이 PR에서 정하지 않음):**
1. v7을 연구의 기본 공동 파지로 되돌릴지, v6의 비교 조건으로만 둘지 정해야 한다. 이 문서는 비교 조건으로 설계하고 4절에서 같은 seed로 비교한다.
2. 9/25 전환을 기록하는 방식(decision_log 항목 추가 여부)도 정해야 한다.

## 1. 선행 연구

조사는 2026-09-28에 WebSearch, WebFetch, scite 문헌 검색, arXiv·JPL PDF의 `pdftotext`로 했다. 아래에는 실제로 찾은 자료만 적었다. "읽은 범위" 열은 실제로 읽은 부분이다.

| # | 자료 | 플랫폼·센서 | 몸체 방향 / 짐 / 진행 방향 | 좁은 통로·문 | 읽은 범위 |
|---|---|---|---|---|---|
| L1 | Stroupe et al. 2006, JPL Robot Construction Crew, *Auton. Robots* 20:113–123 | holonomic 로버 2대, 4-DoF 팔, 전방 스테레오, 그리퍼 F/T, fiducial | 두 로봇이 **나란히 같은 방향**을 보고 빔의 좌·우 grasp 점을 쥔다. 빔에 수직 이동은 drive, 빔 축 이동은 **crab(옆 이동)**, 회전은 대형 중심 기준 상보 Ackermann(반경 = grasp 간격/2) | 문은 없다. 정렬은 crab → drive → turn 순서로 "보고 → 짧게 움직이고 → 다시 본다"를 반복한다. 매 이동 시작에 두 로봇을 동기화하고, leader가 동작을 정해 follower에 보낸다 | 본문 3–5절·7절 |
| L2 | Tallamraju et al. 2019, arXiv 1903.07758 | holonomic 3-DoF 베이스 + 6-DoF 팔, 강체 파지, 시뮬레이션만 | 변형 가능한 2D 가상 bounding box(DVB)가 대형 전체를 감싼다. 짐 yaw는 DVB yaw를 따른다. 팔 IK가 베이스–grasp 점 관계를 흡수한다 | 좁은 틈에서는 DVB 크기를 줄여 지나간다 | 본문 II–V절 일부 |
| L3 | Alonso-Mora, Baker, Rus 2017, IJRR 36(9) | 모바일 매니퓰레이터 3대 실험, 강체 물체 | 대형의 크기·방향을 제약 최적화 변수로 둔다 | 장애물 없는 볼록 영역 안에서 대형 파라미터를 최적화한다 | 초록 |
| L4 | Jiao, Cao, Gu 2017, "Transportation by Multiple Mobile Manipulators in Unknown Environments With Obstacles", IEEE Systems J. 11(4) | 여러 모바일 매니퓰레이터 | "주 진행 방향"과 대형 폭, 선두 로봇을 먼저 정한다. 모드는 default / shrink(로봇이 물체 외곽 사각형 안으로) / incline 세 가지다 | 여러 스케일의 통로 폭으로 모드와 진행 방향을 고른다 | 초록(검색 요약) |
| L5 | Alvear, Turkiyyah, Park 2025, arXiv 2509.03638 | Dingo-O omni 베이스 2대 + Kinova Gen3-lite, **모캡** | 각 로봇의 grasp 점과 대응하는 베이스 위치를 짝으로 후보를 만든다. 궤적 계획기가 **실제로 통과 가능한** 쌍을 고른다 | 65 × 50 cm 통로를 63 cm 막대로 통과했다(IRIS-NP 볼록 분해) | HTML 본문(WebFetch 요약) |
| L6 | Zhang et al. 2020, arXiv 2007.09243 | 차동 구동 2대 + 막대 부착, GT 상태, 시뮬레이션 | 막대가 문보다 길어서 문과 평행하게는 못 나간다. **막대 축을 진행 방향으로 돌려** 통과해야 한다 | 분산 DQN, 성공률 0.955 | 본문 1–3절 |
| L7 | Ghosh et al. 2023, arXiv 2305.01614 | 비홀로노믹 베이스 + 팔, 강체 짐 | leader–follower. follower 팔 IK가 짐 길이 제약을 지킨다 | PRM 경로. **Stop-and-Sync**: 한 로봇이 다음 경유점에 먼저 닿으면 멈추고, 상대가 닿으면 함께 출발한다 | 본문 III절 |
| L8 | Liu et al. 2024, arXiv 2406.05613 | omni 베이스 + 6-DoF 팔(HANGFA), 손목 F/T | 분산 제어로 상호작용 wrench를 줄인다. 제어가 없으면 로봇이 짐을 고르게 나눠 들지 못했다 | 없음 | 본문 4절 일부 |
| L9 | Bechlioulis & Kyriakopoulos 2018, *Front. Robot. AI* (PMC7806111) | 추상 6-DoF 모바일 매니퓰레이터, 시뮬레이션만 | 로봇–물체 상대 방향을 고정한다(π/2, π). 통신 없이 짐을 통한 암묵 통신을 쓴다 | navigation function. 대형을 점으로 보고 작업 공간 경계를 부풀린다 | 본문(WebFetch 요약) |
| L10 | Lewis & Tan 1997, "virtual structures", *Auton. Robots* 4:387–403 | 차동 구동 3대 | 로봇을 강체 구조물 안의 점처럼 움직인다. leader가 필요 없다 | 없음 | 초록 |
| L11 | Simetti, Casalino, Wanderlingh 2019, *Robot. Auton. Syst.* 122 | **KUKA youBot 2대**(omni 바퀴 4개 + 5-DoF 팔), 모캡(인용 문장 기준) | 개별 제어기는 그대로 두고, 제한된 명시 정보 교환으로 협조한다 | 초록에 없음 | 초록 + scite 인용 문장(OA PDF 다운로드 실패) |
| L12 | v6 문헌 요약 [`2026-09-28-zone-pair-v6/lit_review.md`](../2026-09-28-zone-pair-v6/lit_review.md)(#246 브랜치) | — | 파지 전 정렬은 물체 기준 상대 측정으로 한다. "짧게 이동 → 정지 → 재관측"을 반복한다. 들기는 READY/GO 단계로 나눈다 | — | 재사용(새로 읽지 않음) |

### 설계에 쓰는 결론

1. **나란히 같은 방향 + 빔 축 crab은 검증된 배치다(L1).** RCC는 우리 측면 파지와 같은 기하다. 빔에 수직으로는 전진하고, 빔 축으로는 옆으로 이동한다. v7은 이 배치를 따른다. RCC도 전방 센서(스테레오)로 진행 방향을 봤다.
2. **문은 긴 축을 진행 방향으로 두고 통과한다(L4, L5, L6).** 측면 파지에서는 그 구간이 strafe가 된다. 대형 폭 0.1885 m가 문 통과 폭이다. L4의 "진행 방향과 대형 폭을 먼저 정하는" 절차를 계획 단계에 둔다.
3. **파지 배치는 전체 경로의 통과 가능성으로 고른다(L5).** v7 계획기는 grasp 점별 "몸체가 보는 쪽(±n)"을 경로로 정한다. 첫 횡 구간의 진행 방향이 몸체 전방이 되게 고른다(2절 P0).
4. **동기 오차는 빔 축 이동에서 가장 위험하다(L1 표 2).** RCC는 F/T 속도 보정 없이 follower를 2초 늦추면 80 cm crab에서 3회 중 2회 실패했다. 보정을 켜면 0회였다. 우리 로봇에는 F/T가 없다. 따라서 축 구간(strafe)은 짧은 조각으로 나누고, 조각마다 READY/GO와 정지·재관측을 둔다(L1, L7). 같은 GO tick에 함께 출발하는 것을 필수로 한다.
5. **대형은 하나의 강체 footprint로 계획한다(L2, L9, L10).** keep-out 검사는 v6의 차체·팔·빔 sweep을 그대로 쓰되, 측면 대형의 footprint(축 방향 1.01–1.04 m × 폭 0.1885 m)를 넣는다.
6. **짐을 든 채 회전하려면 대형 중심 기준 협조 회전이 필요하다(L1).** v7은 짐을 든 회전을 계획하지 않는다(Manhattan 경로만). 회전이 필요한 경로는 계획 단계에서 거부한다.
7. **우리 센서 조건(손목 단안 RGB, F/T·모캡·fiducial 없음)으로 빔을 들고 문을 통과한 선행 사례는 이번에도 찾지 못했다.** L1이 가장 가깝지만 스테레오, fiducial, F/T를 썼다. v7의 성공은 문헌이 보장하지 않는다.

## 2. 단계별 계획

### 좌표와 기호

- 빔 축 단위벡터는 `u`, 빔 수평 법선은 `n`이다. 역할 `end_neg` / `end_pos`는 v6과 같다.
- 몸체 heading은 `h`이다. 측면 파지에서는 `h = s·n`이고, `s ∈ {+1, −1}`은 계획에서 고른다.
- 팔 yaw 축은 차체 중심에서 앞으로 `a`만큼 떨어져 있다. v2 모델은 `a = 0`, v3(#249)은 `a = 0.0482 m`다. 파라미터로 두어 두 모델에서 모두 동작하게 한다.
- 팔 yaw 목표는 역할별로 `+90°` / `−90°`(PWM 2500 / 500, 9/9와 같은 부호 규칙)이다. SIM 한계 ±100.3°까지 남는 여유는 약 10°다.
- grasp 반경은 `R = 0.155 m`(팔 yaw 축 → grip)다.
- 최종 차체 중심 = grasp 점 − `R`·(안쪽 `u` 방향) − `a`·`h`다. v3에서는 막대 축선보다 48 mm 뒤에 선다.

### 공통 규칙(모든 단계)

- 입력: 자기 손목 RGB, 정적 지도, 주문서, 자기 발행 명령과 메시지 이력, 자기 전방 초음파(#248 provider, `own_ultrasonic_v1`)다. TOP 카메라, 정답 좌표, 접촉, 측정 관절은 평가 출력에만 쓴다. weld는 OFF다.
- **READY/GO**는 v6 `PairCarrySync`를 그대로 쓴다. 각 로봇은 자기 조건이 맞을 때 fresh READY를 낸다. 둘 다 READY면 같은 GO tick에 동작한다. 상대가 abort하면 큐를 정리한다. GO를 놓치면 `PARTNER_MISSED_GO`로 멈춘다. 파지한 뒤에는 한쪽만 pan하는 것을 금지한다.
- v6 예산을 유지한다. relook은 8회, 회당 8초, 누적 40초이고, 예정 안전 재관측은 회당 6초·총 240초·80회다. 전역 안전 여유는 35 mm, 예방 relook은 남은 여유 40 mm 미만일 때다.
- 상태 채널(aligning/ready/lift/carry/put_down/abort)은 2026-09-26 결정대로 모든 통신 조건에 들어간다.

### 단계표

| 단계 | 몸체 heading | 팔 yaw | 입력 | 정지·중단 규칙 | READY/GO |
|---|---|---|---|---|---|
| **P0 계획** | — | — | 주문서, 정적 지도 | 경로가 빔 축/법선 구간만으로 이루어지지 않으면(짐을 든 회전 필요) `REFUSE_LOADED_TURN`. 대형 footprint(1.04 × 0.1885 m, v3 값은 V1에서 다시 계산)가 keep-out과 겹치면 거부. 첫 횡 구간의 진행 방향으로 `s`를 정한다(횡 구간이 없으면 문 쪽 벽과 먼 쪽). | 없음(정적 계산, 두 로봇이 같은 입력으로 같은 결과) |
| **P1 접근** | 이동 중 자유. 사전 정류장에서 `h = s·n` | 0°(카메라 전방, v6 PF 둘러보기) | 손목 RGB(PF), 지도, 명령 이력, 초음파(비적재 충돌 guard) | 사전 정류장 = 최종 자세 − 0.30 m·`h`(빔 선 뒤, 9/9 접근 방향). 도착 판정과 허용치는 v6와 같다. **바뀌는 점:** 목표 heading이 빔 축 방향에서 법선 방향으로 바뀌고, 상대 정류장 keep-out이 빔 끝 바깥에서 빔 뒤쪽으로 옮겨진다. 초음파는 #248 `solo_forward_state` 방식의 전방 정지 guard로 쓴다(정지 거리 가설: 0.15 m). | `approach` 장벽(v6, 150 s) |
| **P2 측면 확인·close-in** | `s·n` 유지 | 0° → ±45° → ±90° 단계 pan | 손목 RGB(v6 상대 형상 보고), 명령 이력 | 각 pan 뒤 정지·재관측. ±45°에서 빔 끝이 보이면 v6 **전진 전용 close-in**을 쓴다. 조각 ≤ 0.10 m, 정지 뒤 재관측. 최종 0.10 m는 ±90°에서 한다. 빔이 안 보이면 v6 relook 예산 안에서 pan 스캔하고, 예산을 넘으면 `ALIGN_LOST`. | 없음(각자 비적재 이동) |
| **P3 정렬(align)** | `s·n`, yaw trim은 팔 축 기준 회전 | ±90° | 손목 RGB(v6 a+b 상대 보고), 지도(전역 envelope), 초음파(전방 guard) | **v6 a+b 정렬을 그대로 쓴다.** 수렴 조건은 12 mm / 8 mm / 0.035 rad를 fresh 2회 연속 만족하는 것이다. 카메라 영상은 마주 보기 방식과 같다(#248 대리 IoU 1.0). **바뀌는 점은 명령 사상이다.** 카메라 전방(standoff)은 몸체 strafe(±y)가 되고, 카메라 좌우는 몸체 전·후진(∓x)이 된다. 상대 yaw는 팔 yaw 축 기준 회전이 된다(아래 식). 정렬 deadline과 예산은 v6와 같다. | `align` READY(수렴 + 전역 안전) → GO로 close 준비 |
| **P4 파지(grasp)** | 고정 | ±90°(+ trim ≤ 3°) | 손목 RGB | v6 close 준비 5 cm / 3°(상대 보고의 불확실도 + bias)와 전역 안전을 AND한다. 닫은 뒤 post-close receipt는 v6/M2 경로를 쓴다(band 의존이 남는다, v6 README). receipt가 실패하면 열고 P3로 돌아간다(1회). 두 번째 실패는 `GRASP_FAIL`. | READY/GO로 동시 close. 한쪽만 닫힌 상태로는 P5에 가지 않는다 |
| **P5 들기(lift)** | 고정 | ±90° | 손목 RGB(빔 높이·기울기 영상 확인), 명령 이력 | 목표 grip z는 **M2 높이 0.095 m**다. 측면 파지에서는 팔과 막대가 센서 면 뒤에 있으므로 #248의 `near_face` 0.110/0.125 m가 필요 없다(#248 10·11절). 이렇게 하면 pitch 변화가 M2의 +8°로 유지된다. 2–3단계로 나눠 올린다(v6 문헌 레시피). 단계마다 기울기 영상 검사를 하고, 실패하면 역순으로 내리고 `LIFT_ABORT`. | 단계마다 READY/GO |
| **P6 횡 운반(빔에 수직)** | `s·n`, **몸체 전진** | ±90° | 초음파(전방 vs 정적 지도 예상 거리), 명령 이력(odometry), 손목 RGB(빔·상대 co-motion 영상) | 조각은 ≤ 0.10 m(가설)이다. 속도는 M2 `SPEED_M_S`, 거리 환산은 새 보정값 `side_forward`를 쓴다(V3에서 결정, 사전값 axial 0.772). 초음파 판정은 #248 `CarrySonarMonitor`의 `formation_ok` / `intrusion` / `beyond_baseline`을 3회 연속일 때 낸다. 예상보다 0.05 m 이상 짧은 에코가 3회면 정지한다. 절대 거리 < 0.15 m면 즉시 정지한다(가설). 멈춘 뒤 상대에게 abort를 알리고 재관측한다. | 조각마다 READY/GO. Stop-and-Sync(L7): 먼저 끝난 로봇은 기다린다 |
| **P7 축 운반·문 통과(빔 축)** | `s·n`, **strafe** | ±90° | 초음파(옆 벽·문기둥 거리 vs 지도), 명령 이력(odometry `side_strafe`), 손목 RGB(co-motion) | 앞을 볼 센서가 없다. 두 방식 모두 같다(#248). 진행 방향 안전은 정적 지도와 계획 footprint로만 판단한다. 조각은 ≤ 0.05 m(가설, L1 표 2 근거로 횡보다 짧게)다. **문 진입 전 정지:** 두 로봇의 초음파가 지도 예상 문 옆 거리(v2 0.172 m, v3는 V1에서 재계산)와 `max(0.03 m, 3σ)` 안에서 맞아야 진입한다. 맞지 않으면 몸체 전·후진(`h` 방향)으로 중앙을 맞추고 다시 잰다(2회). 그래도 안 맞으면 `DOOR_ALIGN_FAIL`. 문 안에서는 매 조각 뒤 같은 검사를 한다. 예상 여유가 0.05 m 아래로 내려가면 정지한다. strafe 방향(진행 방향) 오차는 초음파로 보정하지 못한다. | 조각마다 READY/GO. **같은 GO tick 출발은 필수** |
| **P8 내려놓기(place)** | 고정 | ±90° | 명령 이력, 손목 RGB | P5의 역순 단계로 내린다. 단계마다 READY/GO. 동시에 연 뒤 팔을 hover로 올리고, 0.10 m 후진(`−h`)한다. 성공 판정(구역 안, 기울기, 놓음)은 평가 출력에만 적는다. | 하강 단계, 열기, 후진마다 READY/GO |

### 팔 yaw 축 기준 회전(v3 오프셋)

- 차체 중심이 아니라 팔 yaw 축을 중심으로 회전하는 mecanum 명령이다. 부호는 왼쪽 +, 반시계 +로 둔다.
  - `forward = 0`, `left = −a·ω`, `turn = ω`
  - v2에서는 `a = 0`이라 제자리 회전과 같다.
  - v3에서 이 보정이 없으면 90° 회전에 grip이 68 mm 움직인다(#248 11절). 3° trim이면 약 2.5 mm다.
- **파지 전(P3):** 몸체 yaw trim은 이 명령으로 한다. 팔 yaw 축과 손목 카메라의 위치가 거의 고정되므로 v6 상대 보고가 크게 흔들리지 않는다.
- **파지 후:** 기본은 OFF다. 켜면 몸체를 δ만큼 돌리면서 팔 yaw를 −δ만큼 역회전해 grip 점을 운동학적으로 고정한다. 조건은 |δ| ≤ 3°, 조각 사이 정지 중, READY/GO로 알린 뒤다. 실물 mecanum 회전 중심의 흔들림은 측정하지 않았다(#248). 그래서 첫 코호트에서는 진단 플래그로만 둔다.
- 대형 전체의 회전(L1의 상보 Ackermann)은 v7 범위 밖이다.

### 정확히 바뀌는 것

| 항목 | v6 (마주 보기) | v7 (측면) |
|---|---|---|
| 접근 경로 | 빔 끝 바깥, heading = 빔 축 | 빔 선 뒤(법선 방향) 0.30 m 사전 정류장, heading = `s·n`. 상대 keep-out 위치가 바뀐다 |
| 손목 카메라 보정 | PWM 1300–1700 | **500/2500(±90°), 1000/2000(±45°) 추가.** 고정 보정표를 해시로 등록한다(V4). `SERVO_DEVIATION[6]` 64 pulse(≈ 5.8°)도 확인 대상이다 |
| 정렬 명령 사상 | 카메라 축 = 몸체 축 | ±90° 회전 사상과 팔 축 기준 회전 |
| lift 높이 | `near_face` 0.110/0.125 m(#248 권장) 또는 M2 0.095 m | M2 0.095 m(원뿔 조건 불필요) |
| odometry | axial 0.772(전진), lateral 0.697(strafe) | `side_forward`, `side_strafe`를 새로 보정한다. 짐이 옆 0.155 m에 걸려 바퀴 하중 분포가 달라진다 |
| 초음파 용도 | 서로를 봄, 대형 감시만 | 횡 구간 전방 장애물, 축 구간 문기둥 옆 거리 |
| 문 통과 | 전진/후진, 폭 0.162 m | strafe, 폭 0.1885 m |

## 3. 위험과 최소 검증 순서

### 위험(높은 순)

1. **`long_beam` 측면 파지의 물리 유지가 검증되지 않았다.** 9/9 결과는 다른 물체(5 × 45 × 4 cm, 0.196 kg)였다. 0.60 m / 0.30 kg 막대는 yaw servo가 막대에 수직인 힘을 받는다(SIM 1.2 N·m 한계, 한쪽이 밀면 70 %, #248).
2. **strafe 운반의 동기 오차.** F/T가 없고, 빔 축은 강체 방향이다. 늦게 출발하면 바로 압축이나 인장이 된다(L1).
3. **±90° 카메라 외부 파라미터.** 보정이 없으면 v6 상대 보고의 bias bound가 성립하지 않는다.
4. **odometry.** strafe 거리 오차는 초음파로 보정하지 못한다. 문을 지난 뒤 place 위치 오차로 이어진다.
5. **접근 중 팔 sweep.** ±90°로 뻗은 팔이 빔 위를 지나야 한다. 9/9에서는 접촉 0 step이었지만 다른 물체였다.
6. **v3 모델 의존.** #249가 병합되면 `a`, 초음파 위치, 문 여유가 바뀐다. 비교하는 두 조건은 같은 모델에서 돌려야 한다.
7. **post-close receipt의 band 의존**은 v6와 같이 남는다(markerless 주장 불가).

### 최소 검증 순서(전원 연결 뒤에만)

각 단계에는 통과 기준이 있다. 기준을 못 넘으면 다음 단계로 가지 않고 설계를 고친다. 순서는 싸고 결정적인 것부터다. physics 실행은 `scripts/ugrp_session.py run`을 쓰고, 부하 평균을 기록하고, 디스크 여유 10 GiB를 확인한다.

| 순서 | 내용 | 종류 | 통과 기준(가설) | 비용 |
|---|---|---|---|---|
| V0 | 명령 사상, 팔 축 회전, P0 거부, prereg 해시 단위 테스트 | pytest(`mj_step` 가드) | 전부 통과 | 수 분 |
| V1 | 운동학(`mj_forward`만): v2와 v3의 ±90° grasp IK, 대형 footprint, 문 여유, ±45°/±90° 카메라 FK. #248 분석기를 확장한다 | 운동학 | IK 해 존재, 문 한쪽 여유 ≥ 0.10 m, 자기 팔이 원뿔 밖 | 수 분 |
| **V2** | **물리 fixture: `long_beam` 측면 파지 → 3단계 lift → 2 s 유지.** 동시 조건과 2 s 지연 조건, 2 seed. GT 배치 fixture이고 정답 기반 진단이라 학생 성공이 아니다. weld OFF, `cargo_noslip_v1` | 물리 진단 | 4/4 유지, 양쪽 손가락 접촉 유지, 기울기 < 5°, yaw 토크 < SIM 한계의 50 % | 약 4 × 20 SIM s |
| **V3** | **물리 fixture: 적재 상태 전진 0.30 m + strafe 0.60 m(문 통과 포함).** 명령은 개루프 조각 + READY/GO 타이밍이다. GT는 평가에만 쓴다. 이 결과로 `side_forward` / `side_strafe` 보정값을 정한다. 보정 seed는 코호트 seed와 따로 둔다 | 물리 진단 + 보정 | 빔 유지, 미끄러짐 < 1 cm, 문기둥 접촉 0, 보정값 분산 < 5 % | 약 4 × 30 SIM s |
| V4 | 손목 카메라 고정 보정: PWM 500/1000/2000/2500의 외부 파라미터. 정적 표적만 쓰고 실시간 정답은 쓰지 않는다. 보정표를 해시로 등록한다 | 오프라인 보정 | v6 상대 보고 잔차가 1300–1700 범위 수준 | 짧음 |
| V5 | 자기 카메라 학생 1회: seed 911, v7 정책, 900 SIM s | dev 1회 | P6까지 도달, 모든 중단 사유 기록 | 1회 |
| V6 | 사전등록 비교(4절) | 코호트 | 사전등록 기준 | 4–6회 |

**가장 작은 결정적 시험은 V2 + V3다.** 둘 중 하나라도 실패하면 자기 카메라 작업(V4–V6)은 의미가 없다. 반대로 둘 다 통과하면 v7의 남은 차이는 v6와 같은 인식 문제로 좁혀진다. V2·V3는 `scripts/probe_dual_grasp_sync.py --side-grasp`에 `long_beam`, lift 단계, strafe 인자를 더하는 방식으로 재사용한다. 기본 실행 차단과 weld OFF는 유지한다.

## 4. 등록

- **번들 ID:** AGENTS.md 번호 규칙을 따른다. 오늘(2026-09-28) main과 열린 PR 전체의 최댓값은 v70이다(#246 `zone-pair-v70-beam-relative-multiturn`, main v69, #248·#249 ≤ v66). 따라서 v7의 후보는 **`zone-pair-v71-side-grasp`**다. 등록 직전에 `git grep`으로 main과 열린 PR 브랜치 전체를 다시 확인하고, 그다음 빈 번호를 쓴다. 쓴 ID는 PR 본문에 적는다. 이 문서의 v71은 예약이 아니라 현재 후보다.
- **실행 경로:** 새 실행기를 만들지 않는다. v6의 선택 구조(`PairTeam(policy=...)`, `spec.pair_policy`, `--pair-policy`, `configs/simulation_workflows.json`의 `zone-pair-dev`)에 `pair_policy = 'side-v7'`을 더한다. `side-v7`은 `a+b` 위에 측면 기하 묶음을 켠 것이다. 묶음의 내용은 2절 "정확히 바뀌는 것" 표이고, 플래그 정의를 `v7_contract`에 등록한다. workflow 버전도 올린다(현재 2.3.0 → 2.4.0 후보, 등록 시 확인).
- **사전등록 초안 `prereg_v7.json`:** v6 `prereg_v6.json` 스키마를 그대로 쓴다.
  - 같은 seed 911/912, 같은 `setup_beam_xyyaw`, 주문서, scene, 접촉 프로필, 입력 주기, 회당 900 SIM s, 재시도 0, ENOSPC = HOST_ERROR, `execution_source_sha`와 승인은 null(DRAFT)이다.
  - 실행 목록:
    - 주 비교 `v6-a+b` × 2 seed와 `side-v7` × 2 seed, 총 4회.
    - 보조 `side-v7-nosonar` × 2 seed. 측면 기하 효과와 초음파 사용 효과를 나누기 위한 것이다.
  - 초음파 provider는 모든 조건에 같게 연결한다(#248 입력 경계). 각 정책은 자기 기하에 맞게 쓴다.
  - 측정: 단계별 도달(P1–P8), 성공(구역 안 놓기, 평가 전용), SIM 시간, 명령 수, relook 수, abort 사유, 모델 호출 0이다. TensorBoard 스냅샷에 v6 기준선과 함께 올린다(`docs/tensorboard.md`).
  - v6 prereg는 v2 모델이다. #249가 먼저 병합되면 두 조건을 모두 v3 모델로 다시 등록한다. 한쪽만 v3로 돌리지 않는다.
  - 이 비교는 `tags_temporary` 개발 진단이다. 연구 결과(통신 조건 효과)가 아니다.
- **기록:** 이 폴더에 `DESIGN.md`(이 문서), 이후 `prereg_v7.json`, V0–V5 결과, 원본 경로와 sha256을 남긴다. raw는 기본 체크아웃 `outputs/`에 둔다.

## 참고 자료

- [L1] Stroupe, A. et al. (2006). Sustainable cooperative robotic technologies for human and robotic outpost infrastructure construction and maintenance. *Autonomous Robots* 20:113–123. doi:10.1007/s10514-006-5943-4. <https://www-robotics.jpl.nasa.gov/media/documents/Stroupe_Sustainable06.pdf> (본문 3–5, 7절)
- [L2] Tallamraju, R. et al. (2019). Motion Planning for Multi-Mobile-Manipulator Payload Transport Systems. arXiv:1903.07758. <https://arxiv.org/abs/1903.07758> (본문 일부)
- [L3] Alonso-Mora, J., Baker, S., Rus, D. (2017). Multi-robot formation control and object transport in dynamic environments via constrained optimization. *IJRR* 36(9):1000–1021. doi:10.1177/0278364917719333. <https://journals.sagepub.com/doi/10.1177/0278364917719333> (초록)
- [L4] Jiao, J., Cao, Z., Gu, N. (2017). Transportation by Multiple Mobile Manipulators in Unknown Environments With Obstacles. *IEEE Systems Journal* 11(4):2894–2904. doi:10.1109/JSYST.2015.2416215. <https://ieeexplore.ieee.org/document/7084628/> (초록, 검색 요약)
- [L5] Alvear, D., Turkiyyah, G., Park, S. (2025). Cooperative Grasping for Collective Object Transport in Constrained Environments. arXiv:2509.03638. <https://arxiv.org/html/2509.03638> (HTML 본문, 요약 도구로 읽음)
- [L6] Zhang, L., Xiong, H., Ma, O., Wang, Z. (2020). Multi-robot Cooperative Object Transportation using Decentralized Deep Reinforcement Learning. arXiv:2007.09243. <https://arxiv.org/abs/2007.09243> (본문 1–3절)
- [L7] Ghosh, S. et al. (2023). On the Collaborative Object Transportation Using Leader Follower Approach. arXiv:2305.01614. <https://arxiv.org/abs/2305.01614> (본문 III절)
- [L8] Liu, W. et al. (2024). Distributed Motion Control of Multiple Mobile Manipulators for Reducing Interaction Wrench in Object Manipulation. arXiv:2406.05613. <https://arxiv.org/abs/2406.05613> (본문 4절 일부)
- [L9] Bechlioulis, C., Kyriakopoulos, K. (2018). Collaborative Multi-Robot Transportation in Obstacle-Cluttered Environments via Implicit Communication. *Frontiers in Robotics and AI*. <https://pmc.ncbi.nlm.nih.gov/articles/PMC7806111/> (본문, 요약 도구로 읽음)
- [L10] Lewis, M. A., Tan, K.-H. (1997). High Precision Formation Control of Mobile Robots Using Virtual Structures. *Autonomous Robots* 4:387–403. <https://link.springer.com/article/10.1023/A:1008814708459> (초록)
- [L11] Simetti, E., Casalino, G., Wanderlingh, F. (2019). A task priority approach to cooperative mobile manipulation: Theory and experiments. *Robotics and Autonomous Systems* 122:103287. doi:10.1016/j.robot.2019.103287. <http://hdl.handle.net/11567/974770> (초록과 scite 인용 문장)
- [L12] v6 문헌 요약: `experiments/2026-09-28-zone-pair-v6/lit_review.md`(PR #246)
- 저장소 근거: `experiments/2026-09-09-side-grasp`, `experiments/2026-09-09-loaded-transport`, `scripts/probe_dual_grasp_sync.py`(`--side-grasp`), `sim/zone_cargo.py`(commit `87eaac86`), PR #246 `experiments/2026-09-28-zone-pair-v6/{design.md,README.md,prereg_v6.json}`, PR #248 `experiments/2026-09-28-ultrasonic-range/README.md`와 `docs/ultrasonic_range_sensor.md` 10·11절, PR #249(외관 v3), `harness/visual_arm.py`, `scripts/study_owncam_pair_beam.py`(`CARRY_ODOM_SCALE`), `docs/zone_m2_pair.md`
