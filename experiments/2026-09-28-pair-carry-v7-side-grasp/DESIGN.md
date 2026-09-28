# 공동 운반 v7: ㄱ자 측면 파지 설계

2026-09-28 · 브랜치 `claude/pair-v7-side-grasp` · 기반 `origin/main` `d5bd208e` · Refs #221

**설계 문서만 있다.** 코드 변경, pytest, 시뮬레이션, 학습, 모델 호출은 모두 0회다(배터리 전원, 충전 불가). Claude 서브에이전트가 시작한 설계를 Codex가 적대적 리뷰(`outputs/review-250-20260928.md`, PR #250 댓글)에 따라 수정했다. 아래 임계값은 실행 전 고정할 개발용 판정 계약이며 물리적 안전성이 검증된 값이 아니다. 이 개정에서도 코드·실험 실행은 없다.

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

**PR #250 매니저 댓글 반영:** v7은 먼저 비교 후보로 진행한다. 9/25 `87eaac86`의 전환은 사용자 결정 없이 이뤄진 에이전트 설계 기본값으로 기록한다. 기본 파지 채택은 비교 결과와 별도 사용자 결정 사항이다. 이 개정은 V2/V3를 SIM 필요조건으로 한정하며 실물 채택에는 #251의 별도 검증이 필요하다.

## 1. 선행 연구

Claude 초안의 조사는 2026-09-28에 WebSearch, WebFetch, scite 문헌 검색, arXiv·JPL PDF의 `pdftotext`로 했다. 아래에는 실제로 찾은 자료만 적었다. "읽은 범위" 열은 초안의 열람 범위다. 아래 L1·L4–L6·L8·L9·L11 정정은 리뷰어가 확인한 원문·메타데이터를 반영했으며 Codex가 모든 원문을 재열람했다는 뜻은 아니다.

| # | 자료 | 플랫폼·센서 | 몸체 방향 / 짐 / 진행 방향 | 좁은 통로·문 | 읽은 범위 |
|---|---|---|---|---|---|
| L1 | Stroupe et al. 2006, JPL Robot Construction Crew, *Auton. Robots* 20:113–123 | holonomic 로버 2대, 4-DoF 팔, 전방 스테레오, 그리퍼 F/T, fiducial | 두 로봇이 **나란히 같은 방향**을 보고 빔의 좌·우 grasp 점을 쥔다. 빔에 수직 이동은 drive, 빔 축 이동은 **crab(옆 이동)**, 회전은 대형 중심 기준 상보 Ackermann(반경 = grasp 간격/2) | 문은 없다. 정렬은 crab → drive → turn 순서로 "보고 → 짧게 움직이고 → 다시 본다"를 반복한다. 매 이동 시작에 두 로봇을 동기화하고, leader가 동작을 정해 follower에 보낸다 | 본문 3–5절·7절 |
| L2 | Tallamraju et al. 2019, arXiv 1903.07758 | holonomic 3-DoF 베이스 + 6-DoF 팔, 강체 파지, 시뮬레이션만 | 변형 가능한 2D 가상 bounding box(DVB)가 대형 전체를 감싼다. 짐 yaw는 DVB yaw를 따른다. 팔 IK가 베이스–grasp 점 관계를 흡수한다 | 좁은 틈에서는 DVB 크기를 줄여 지나간다 | 본문 II–V절 일부 |
| L3 | Alonso-Mora, Baker, Rus 2017, IJRR 36(9) | 모바일 매니퓰레이터 3대 실험, 강체 물체 | 대형의 크기·방향을 제약 최적화 변수로 둔다 | 장애물 없는 볼록 영역 안에서 대형 파라미터를 최적화한다 | 초록 |
| L4 | Jiao et al. 2017, "Transportation by Multiple Mobile Manipulators in Unknown Environments With Obstacles", IEEE Systems J. 11(4) | 여러 모바일 매니퓰레이터 | "주 진행 방향"과 대형 폭, 선두 로봇을 먼저 정한다. 모드는 default / shrink(로봇이 물체 외곽 사각형 안으로) / incline 세 가지다 | 여러 스케일의 통로 폭으로 모드와 진행 방향을 고른다 | 초록(검색 요약) |
| L5 | Alvear, Turkiyyah, Park 2025, arXiv 2509.03638 | Dingo-O omni 베이스 2대 + Kinova Gen3-lite, **모캡** | 각 로봇의 grasp 점과 대응하는 베이스 위치를 짝으로 후보를 만든다. 학습된 CE 모델이 grasp 쌍을 고르고, 계획기는 그 쌍의 경로를 계산한다 | 65 × 50 cm 통로를 63 cm 막대로 통과했다(IRIS-NP 볼록 분해) | HTML 본문(WebFetch 요약) |
| L6 | Zhang et al. 2020, arXiv 2007.09243 | 차동 구동 2대 + 자유 회전 hat으로 막대 연결, GT 상태, 시뮬레이션 | 막대가 문보다 길어서 문과 평행하게는 못 나간다. **막대 축을 진행 방향으로 돌려** 통과해야 한다 | 분산 DQN, heterogeneous 학습 성공률 0.955(homogeneous 0.966) | 본문 1–3절 |
| L7 | Ghosh et al. 2023, arXiv 2305.01614 | 비홀로노믹 베이스 + 팔, 강체 짐 | leader–follower. follower 팔 IK가 짐 길이 제약을 지킨다 | PRM 경로. **Stop-and-Sync**: 한 로봇이 다음 경유점에 먼저 닿으면 멈추고, 상대가 닿으면 함께 출발한다 | 본문 III절 |
| L8 | Liu et al. 2024, arXiv 2406.05613 | omni 베이스 + 6-DoF 팔(HANGFA), 손목 F/T | 분산 제어로 상호작용 wrench를 줄인다. 무보정에서 상호작용 wrench가 크게 변하고 모바일 플랫폼의 정지·출발에서 충격이 발생했다 | 없음 | 본문 4절 일부 |
| L9 | Bechlioulis & Kyriakopoulos 2018, *Front. Robot. AI* (PMC7806111) | 추상 6-DoF 모바일 매니퓰레이터, 시뮬레이션만 | 로봇–물체 상대 방향을 고정한다(π/2, π). 명시 통신 없이 F/T 기반으로 짐을 통한 암묵 통신을 쓴다(우리에게 없는 센서) | navigation function. 대형을 점으로 보고 작업 공간 경계를 부풀린다 | 본문(WebFetch 요약) |
| L10 | Lewis & Tan 1997, "virtual structures", *Auton. Robots* 4:387–403 | 차동 구동 3대 | 로봇을 강체 구조물 안의 점처럼 움직인다. leader가 필요 없다 | 없음 | 초록 |
| L11 | Simetti, Casalino, Aicardi, Wanderlingh 2019, *Robot. Auton. Syst.* 122 | **KUKA youBot 2대**(omni 바퀴 4개 + 5-DoF 팔), 모캡 사용 여부 미확인(원문 근거 없음) | 개별 제어기는 그대로 두고, 제한된 명시 정보 교환으로 협조한다 | 초록에 없음 | 초록 + scite 인용 문장(OA PDF 다운로드 실패) |
| L12 | v6 문헌 요약 [`2026-09-28-zone-pair-v6/lit_review.md`](../2026-09-28-zone-pair-v6/lit_review.md)(#246 브랜치) | — | 파지 전 정렬은 물체 기준 상대 측정으로 한다. "짧게 이동 → 정지 → 재관측"을 반복한다. 들기는 READY/GO 단계로 나눈다 | — | 재사용(새로 읽지 않음) |

### 설계에 쓰는 결론

1. **나란히 같은 방향 + 빔 축 crab은 검증된 배치다(L1).** RCC는 우리 측면 파지와 같은 기하다. 빔에 수직으로는 전진하고, 빔 축으로는 옆으로 이동한다. v7은 이 배치를 따른다. RCC도 전방 센서(스테레오)로 진행 방향을 봤다.
2. **문은 긴 축을 진행 방향으로 두고 통과한다(L4, L5, L6).** 측면 파지에서는 그 구간이 strafe가 된다. 대형 폭 0.1885 m가 문 통과 폭이다. L4의 "진행 방향과 대형 폭을 먼저 정하는" 절차를 계획 단계에 둔다.
3. **파지 배치는 전체 경로의 통과 가능성으로 고른다(L5).** v7 계획기는 grasp 점별 "몸체가 보는 쪽(±n)"을 경로로 정한다. 첫 횡 구간의 진행 방향이 몸체 전방이 되게 고른다(2절 P0).
4. **READY/GO만으로 slip·제어 이득 차이를 해결하지 못한다(L1 §4–5, 표 1·2).** RCC는 이미 매 이동 시작을 동기화했다. F/T 없는 crab의 −2 s 지연 실패는 **6회 중 2회**, drive −2 s는 5회 중 1회, −5 s는 **5회 중 5회**다. 원인은 slip과 control mismatch였고 해결책은 **follower만 바꾸는 연속 F/T PI 속도 보정**이었다. 축 이동이 항상 더 위험하다는 결론은 삭제한다. 우리에게 F/T가 없으므로 아래의 영상·초음파 대형 오차 제어를 새로 검증해야 한다. 조각화는 출발 지연·개루프 지속시간을 제한할 뿐이다. 5% 이득 차이는 0.60 m에서 30 mm 누적될 수 있고, 반복 정지·출발은 L8의 충격 위험을 늘린다.
5. **대형은 하나의 강체 footprint로 계획한다(L2, L9, L10).** keep-out 검사는 v6의 차체·팔·빔 sweep을 그대로 쓰되, 측면 대형의 footprint(축 방향 1.01–1.04 m × 폭 0.1885 m)를 넣는다.
6. **짐을 든 채 회전하려면 대형 중심 기준 협조 회전이 필요하다(L1).** v7은 짐을 든 회전을 계획하지 않는다(Manhattan 경로만). heading을 바꿔야 하는 경로는 거부한다. 이동 벡터는 지도 좌표에서 정하고 전진·strafe를 합성한다.
7. **장기 목표 센서 조건(손목 단안 RGB, F/T·모캡·fiducial 없음)으로 빔을 들고 문을 통과한 선행 사례는 이번에도 찾지 못했다.** L1이 가장 가깝지만 스테레오, fiducial, F/T를 썼다. v7의 성공은 문헌이 보장하지 않는다. 현재 비교는 tags_temporary와 band에 의존하므로 이 장기 목표를 달성한 조건이 아니다. L6의 수동 yaw 순응은 후속 대안이며 이 설계에 몰래 도입하지 않는다.

## 2. 단계별 계획

### 좌표와 기호

- 빔 축은 `u`, 수평 법선은 `n`, 역할은 `end_neg/end_pos`다. 목표 몸체 heading `h = s·n`, `s ∈ {+1, −1}`이나 실제 heading은 별도로 관측한다. 상대 grip yaw 수렴을 몸체 heading 수렴으로 간주하지 않는다.
- 팔 yaw 축 전방 오프셋 `a`는 v2 0, v3(#249) 0.0482 m, 축–grip 반경 `R = 0.155 m`다. 모델별 값·해시를 고정한다.
- **명목 팔 yaw는 ±85°**, 중심 1500 기준 PWM 약 **556/2444**다. ±90°=500/2500은 하드웨어 안전 경계이며 SIM 관절 한계 ±100.3°를 PWM 여유로 쓰지 않는다. nominal ±85°에서 ±3° trim이면 최외측 PWM 약 522/2478로 약 22 pulse(2°)가 남는다. 비적재 relook ±2°도 이 범위에서 양방향 검사하되 trim과 합산한 각도는 ±88°를 넘지 않는다.
- 실물 중심 보정 64 pulse(5.76°)를 그대로 더하면 명목 ±85°만으로도 한쪽이 2500을 넘는다. **V1은 중심·보정·잔여 오차·trim·relook의 합성 PWM을 검사하고 불합격이면 중단한다.** clip으로 통과시키지 않는다. #251 보정 후에도 ±3° 양방향 trim과 ±2° 양방향 relook을 각각 확보하지 못하면 이 명목 설계는 실물 진입 불가이며 새 기하·계약 개정이 필요하다.
- `q ∈ {−1,+1}`를 몸체 좌표에서 안쪽 팔 방향 부호, `l`을 몸체 왼쪽 벡터로 두면 `g_body=(a+R cos85°, q R sin85°)`이고, `body_target = grasp − (a+R cos85°)h − q R sin85° l`이다. 기존 ±90° 대비 h 방향으로 약 **13.5 mm 뒤로**, 안쪽 성분은 약 0.6 mm 달라진다. footprint·grip 상대 yaw(명목 5° 차이 포함)·카메라 사상을 V1에서 다시 계산한다. 기존 2° align 기준을 5° 명목 오차로 우회하지 않는다. 별도 손목 방향 자유도로 보상 가능한지 V1에서 검사하고 불가능하면 V2 전에 기하를 재설계한다.

### 공통 규칙과 입력 경계

- 제어 입력은 자기 손목 RGB, 정적 지도·카메라 보정, `coarse_order_sheet`, 자기 발행 명령·메시지 이력, 자기 전방 초음파 `own_ultrasonic_v1`(#248)다. P0은 `setup_beam_xyyaw`를 읽지 않는다. TOP·실시간 GT·접촉·측정 관절·토크는 평가에만 쓴다. weld OFF를 유지한다.
- READY/GO는 v6 `PairCarrySync`의 fresh READY, 같은 GO tick, abort 시 큐 정리 규칙을 유지한다. GO 누락은 `PARTNER_MISSED_GO`다. 동기화가 힘 제어를 대신하지 않는다. 적재 후 일방 pan·팔 yaw 역회전·대형 회전은 금지한다.
- 상태 채널은 모든 조건에 같다. 이 개발 비교에는 양 로봇이 자기 영상·sonar로 구한 **시각·bound가 붙은 대형 측정 요약**을 교환하는 공통 기하 안전 채널도 명시 등록한다. 호스트가 GT를 주입하거나 결정을 대신하지 않는다. 이는 무통신 연구 결과가 아니다.
- 모든 숫자는 실행 전 prereg로 고정한다. 미관측·보정 범위 밖·bound 초과는 안전함으로 추정하지 않는다. 입력 없는 `side-v7-nosonar`는 아래 계약상 carry를 허용하지 않는 음성 대조군이며 완주율 공정 비교 조건으로 해석하지 않는다.

### 단계표

| 단계 | 몸체 heading / 팔 yaw | 입력 | 정지·중단 및 동작 규칙 | READY/GO | tags_temporary / black-band 의존 |
|---|---|---|---|---|---|
| **P0 계획** | 목표 `s·n` / ±85° | coarse 주문서, 지도, 보정 | 두 s 후보의 사전 정류장·팔 sweep·상대 keep-out·전체 경로 검사. ±10° 빔 yaw envelope를 포함해 지도상의 문 법선 경로를 전진+strafe로 합성한다. loaded turn 필요, 공통 수직 벽이 신뢰 거리 밖, 불확실 footprint 여유 <50 mm, 시간 예산 초과면 거부 | 정적 동일 계산 | 직접 의존 없음; 이후 tags/band 필요 조건을 예약 |
| **P1 접근** | 이동 중 자유 → `s·n` / 0° | wrist PF, 지도, 이력, sonar | 사전 정류장=`body_target −0.30h +0.08u_out`(역할별 바깥 방향). PF 도착만으로 close-in 허가하지 않는다. 전방 echo <0.15 m면 정지 | approach 장벽, 150 s | PF·RecoveryLocalizer tag 검출; band 필수 아님 |
| **P2 측면 확인·close-in** | `s·n` / 0→역할별 ±45→±85° | 물체 상대 RGB, 이력, sonar | 먼저 빔 끝·차체 sweep의 상대 bound를 확인한다(아래). 손가락 최저점은 32 mm 빔 윗면보다 ≥10 mm 높은 hover, 팔 전체 sweep 비접촉. 바깥쪽에서 전진(조각 ≤0.05 m), 빔 선에 도달한 뒤 **비적재** 안쪽 strafe(≤0.02 m)로 파지 위치에 들어온다. 정지·재관측 후 하강. 미검출은 ALIGN_LOST | 각자 비적재, 상대 keep-out 유지 | 원거리 >약 0.43–0.47 m의 v6 fit fallback은 band 의존; 직접 빔 끝 bound는 band만으로 대체 불가 |
| **P3 align** | 관측된 heading / ±85° | 상대 형상 fit, tag 전역 envelope, sonar | grip 기준 trim. 목표 대비 12 mm(standoff)/8 mm(폭)/0.035 rad의 오차+bound를 fresh 2회 만족. 몸체 heading 오차+bound ≤2°도 별도 확인. v6 a+b 구조만 재사용하고 측면 fit 범위·bias는 V1b에서 확인 | align READY=상대 정렬 AND 비적재 전역 안전 | 전역 envelope는 tag, 상대 fit fallback은 band |
| **P4 grasp** | 고정 / 명목 ±85°, trim 총 ≤3° | wrist RGB, carry 초기 인증 | P3의 엄격한 수렴 기준을 유지한 채 v6 close 준비 5 cm/3°와 AND. close 후 receipt 실패 시 열고 P3 1회 복귀, 이후 GRASP_FAIL. 양측 band-free slip 기준 영상을 확보하지 못하면 lift 금지 | 동시 close | post-close receipt는 band; 신규 slip 관측은 band-free 별도 필수 |
| **P5 lift** | 고정 / 보정된 side 자세 고정 | RGB, sonar, 이력 | grip z 목표 0.095 m, 3단계 상승. ±85° 재계산에서도 팔·빔이 sonar 원뿔 밖임을 V1에서 확인해야 이 높이를 허용. 매 단계 tilt·slip·carry certificate 확인, 실패 시 등록된 역순 하강 | 매 단계 | hold 영상은 band; slip 측정은 band-free |
| **P6 지도 횡 구간** | heading 고정 / yaw 고정 | 공통 벽 sonar, RGB slip/co-motion, 보정 odometry | 지도 벡터를 몸체 축에 투영. ≤0.05 m **및 ≤2.5 s** 중 먼저 도달한 조각마다 정지·대형 측정·follower-only 보정. 아래 carry 계약 미충족 시 다음 조각 금지 | 매 조각 및 보정 | co-motion은 band; slip은 band-free; tag 재획득 필수 아님 |
| **P7 문 통과** | heading 고정 / yaw 고정 | pose 집합, 지도, 먼 벽/문기둥 sonar, RGB | 진입 전 먼 수직 벽으로 n 중앙 정렬. 대형 yaw bound 포함 ≤5°, 개별 heading ≤2°, 모든 가능한 footprint 여유 ≥50 mm. 같은 조각 상한과 follower 보정 적용. 예상 echo는 pose 영역의 **집합**으로 판정(아래) | 진입·조각·보정 | co-motion은 band; slip은 band-free; tag fix를 강제하지 않음 |
| **P8 place** | 고정 / side 자세 유지 | RGB, sonar, 명령 이력 | P5 역순 하강·동시 open·hover 후 비적재 0.10 m 후진. abort도 사전 검사된 하강 영역을 쓴다. 위치/기울기/놓음의 실제 성공은 평가 전용 | 하강·open·후진 | 하강 hold/receipt는 band; 재이동 전 v6 전역 인증 복귀 시 tag 필요 |

### 접근 안전과 grip 기준 trim

- 기존 측면 경로의 빔 끝 여유 약 44 mm는 coarse 주문서 ±50 mm/±5° 및 PF 과신(dev14)을 견디지 못한다. +80 mm outboard는 초기 분리만 늘린다. P2 전진 전 빔 끝 윤곽·상단 모서리를 실제 자기 영상에서 관측하고 정적 치수·카메라 보정으로 물체 좌표계의 상대 위치 구간을 만든다. **끝 위치 bound ≤10 mm, 물체 좌표계 swept-body/arm 최저 여유 ≥35 mm**를 동시에 요구한다. PF σ만으로 이 bound를 줄이지 않는다. 가림·대응 모호성은 멈춤이다. 마지막 안쪽 strafe·하강도 매 조각 같은 검사를 하며 의도한 손가락 접촉만 close에서 허용한다.
- 왼쪽 +, 반시계 +, 몸체 기준 grip 위치 `(x_g,y_g)`일 때 grip을 순간 회전 중심으로 하는 **물리 속도**는 `v_x=y_g·ω`, `v_y=−x_g·ω`다. ±90° 극한은 `v_x=±R·ω`, `v_y=−a·ω`, ±85°는 위 `g_body`를 대입한다. 팔 축만 고정하면 손목 카메라는 반경 최대 0.155 m에서 3°에 약 **8.1 mm** 움직인다. grip 기준 회전도 카메라–grip 오프셋 및 시선 변화가 남으므로 매 trim 후 재관측한다.
- 이를 원시 command에 그대로 넣지 않는다. 로봇 i의 `K_f,i=FORWARD_GAIN·side_forward_i`, `K_l,i=LEFT_GAIN·side_strafe_i`, `K_ω,i`(rad/s per turn command)를 쓰면 `c_turn=ω/K_ω,i`, `c_forward=y_g K_ω,i c_turn/K_f,i`, `c_left=−x_g K_ω,i c_turn/K_l,i`다. SIM의 출발값은 FORWARD_GAIN=2.2/1.4, LEFT_GAIN=1.65/1.4, 기존 axial=0.772/lateral=0.697이며 v7·실물 보정값이 아니다. 회전 이득도 실측/별도 보정 없이 1로 두지 않는다. 포화 시 세 명령을 같은 비율로 줄이거나 거부하여 회전 중심을 보존한다.
- SIM 렌치는 복합 무게중심 기준이므로 이 운동학 식만으로 실제 grip 고정을 보장하지 않는다. V1에서 무게중심/FK를 계산하고 V3의 비적재 trim 사전 구간에서 실제 회전 중심·grip 잔차를 평가한다. 적재 yaw trim은 이번 계약에서 금지한다.
- ±85° 입력은 기존 `grasp_pose`의 calibrated pan 1300–1700 범위 밖이다. 후속 구현은 명시 `side_ik_v1` 플래그·외부 파라미터 해시·PWM 검증을 갖춘 별도 허용 경로로 등록한다. 기존 IK의 ValueError를 우회하거나 전체 보정 범위를 묵시 확대하지 않는다.

### 조각별 대형 오차와 follower-only 보정(F/T 없음)

1. 로봇별·방향별 `side_forward_i/side_strafe_i/K_ω,i`를 보정 데이터에서 먼저 고정한다. SIM 보정과 #251 실물 보정은 분리한다. 명령/시간으로 얻은 이동량을 실제 이동으로 단정하지 않는다. leader=`end_neg`, follower=`end_pos`를 한 실행 내 고정한다.
2. 매 조각 전후 정지 상태에서 양측이 동일한 **전방 광축에 수직인 공통 벽**을 보는지 지도와 허용 pose 집합·영상으로 확인한다. sonar 3표본, 표본 나이 ≤0.5 s, 양측 시각 차이 ≤0.1 s를 요구한다. 각 로봇의 heading·센서 오프셋·입사각을 보정한 벽 법선 거리 `d_i`로 `e_n=(d_F−d_L)−Δd_target`를 구한다. 서로 다른 벽이면 차이를 대형 오차로 쓰지 않는다.
3. 몸체 간 빔 축 간격 `B`는 보정 기하와 관측된 axial slip 구간으로 유지한다(약 0.85 m). `atan2(e_n,B)`는 목표 대비 **대형 yaw의 관측 성분**이다. 거리차 하나로 두 몸체 heading·빔 yaw·n offset을 독립 추정할 수 없다. 각자의 빔 상대 yaw+보정 팔 yaw와 map/tag heading 또는 비적재 다중 시점 벽 관측으로 heading bound를 얻고 교차 검사한다. 모든 가능한 pose로 yaw 구간을 전파한다. 한 거리차를 두 독립 측정처럼 중복 사용하지 않는다.
4. axial slip `s_i(t)`는 close 직후 기준 대비 **집게 좌표계 안에서 빔의 u축 이동량**이다. beam 끝–jaw 상대 위치와 자연 모서리/표면 특징을 고정 카메라 보정으로 추적한다. band를 마스킹한 V1b/V3에서 검증한다. 균일한 옆 모서리만 보이면 u 이동은 관측 불가능하므로 끝/고유 특징이 없을 때 0으로 채우지 않고 `SLIP_UNOBSERVABLE`로 중단한다. metric scale은 알려진 빔 단면·길이와 보정에서 얻는다. band receipt·co-motion이 이 새 관측을 대신하지 않는다.
5. 조각 내에도 최대 0.1 s 간격의 이용 가능한 센서 관측으로 중단을 감시한다. 목표 속도 ≤0.02 m/s, 가감속 램프 각각 ≥0.2 s; 조각 상한은 2.5 s(≤50 mm)다. 관측 공백은 최대 0.5 s이므로 그 사이 명령 변위는 ≤10 mm다. 0.5 s 안에 fresh 관측이 없으면 정지한다. 이는 연속 F/T 제어와 동등한 힘 제한을 보장하지 않으며 #251에서 정지거리·관측 지연을 검증해야 한다.
6. **사전 고정 중단값:** 각 `abs(s_i)+bound ≤10 mm`, slip bound ≤3 mm, `abs(e_n)+bound ≤10 mm`, e_n bound ≤5 mm, 개별 heading 오차+bound ≤2°, 대형 yaw+bound ≤5°. 한 항목이라도 초과·미관측이면 함께 정지하고 다음 carry를 금지한다. slip은 조각별 영점 재설정 없이 close 기준 누적값이다. 영상상 높이 감소+bound ≤5 mm, tilt+bound ≤5°도 요구한다.
7. 허용 범위 안에서 `abs(e_n)+bound >5 mm` 또는 상대 axial 오차+bound >3 mm이면 leader는 정지, follower만 보정한다. `Δn_F=−clip(e_n, ±3 mm)`, `Δu_F=−clip(e_u, ±3 mm)`이며 e_u는 두 slip 및 보정 grasp 간격에서 얻는 **관측 가능한 상대 오차**로 정의하고 부호는 V0 fixture에서 확인한다. 속도 ≤5 mm/s, 한 축씩 최대 2회, 매 회 정지 재측정한다. 잔차 상한이 감소하지 않거나 위 hard bound를 넘으면 중단한다. 공통모드 slip/leader의 grip 이탈은 follower 이동으로 고치려 하지 않는다. 목표 잔차(n ≤5 mm, u ≤3 mm) 미도달 시 재출발 금지. 보정도 READY/GO로 알리되 leader 명령은 0이다.

### P7 sonar: 먼 벽 중앙 정렬과 예상값 집합

- 문 진입 전 두 센서는 문 측벽과 평행할 수 있어 0.172 m 문기둥 echo를 동시에 요구할 수 없다. P0에서 `s`와 접근 위치를 골라 **같은 먼 수직 벽**(기존 v2 예시 north 약 1.297 m)이 각 센서의 보정된 신뢰 거리·입사각 범위에 들어오게 한다. 없는 경로는 거부한다. 진입 전 평균 벽 거리로 공통 n 위치를, 거리차로 상대 n 오차를 구분한다. 공통 n 중앙 정렬은 동일한 지도 목표로 두 로봇이 동기 이동하며, 상대 대형 오차 보정은 follower만 한다(최대 2회).
- 로봇 i의 pose 불확실 영역 `E_i` 전체(위치·heading·sensor extrinsic·원뿔 폭 포함)에서 정적 지도의 첫 반사 후보를 계산하여 `S_i(E_i)=union {range interval(p, ray, map)}`를 만든다. echo가 없는 경우도 별도 후보로 보존하고, 서로 떨어진 구간 사이를 하나의 넓은 연속 구간으로 메우지 않는다. 판정은 **각 로봇의 측정이 자기 집합과 양립하는가**이며 단일 예상 거리와 3σ 비교가 아니다.
- 문기둥 에코는 그 로봇이 에코 창 안에 있을 수 있을 때만 후보에 넣는다. 경계에서는 0.172 m 부근과 1.297 m 부근이 둘 다 가능한 집합이 될 수 있다. 이 모호성만으로 DOOR_ALIGN_FAIL을 내지 않는다. 반대로 ambiguous echo를 공통 벽 측정으로 잘못 사용하지 않는다. 공통 벽 관측을 잃는 짧은 구간은 아래 envelope 성장만 적용하고, 허용 bound를 넘으면 멈춘다.
- 집합 밖 echo 3회면 정지; 예상 집합 최솟값보다 50 mm 이상 짧거나 실제 range <150 mm면 즉시 정지한다. 안전 여부는 집합 중 유리한 pose가 아니라 **모든 pose의 swept footprint**로 판정한다(여유 ≥50 mm). 문기둥 echo 출현/소실은 u 위치 단서이나 약 0.14 m 창과 원뿔 폭 때문에 cm 수준이다. V1/V1b에서 창·불확실도를 검증한 경우만 등록된 u 관측으로 쓰며 그렇지 않으면 u bound를 줄이지 않는다.

### `v7_contract`: 적재 중 안전 근거와 예산

- **v6 anchor의 30 s 수명을 늘리거나 guard를 생략하지 않는다.** P1–P4는 v6 비적재 `global_certificate`를 유지한다. P4에서 fresh(≤30 s) global anchor와 객체 상대 bound·양측 sonar·검증된 gain으로 초기 pose 영역을 만든다. P5–P8 loaded 명령은 별도 `carry_certificate_v7`로 명시 dispatch한다. 기존 `GlobalEnvelope.pose()`가 만료된 값을 그대로 호출하는 경로가 남으면 V0 실패다. 새 인증서 미구현·미등록이면 loaded 명령은 차단한다.
- 인증서는 정적 지도에 대한 pose 집합 전파, 실관측과의 교집합, 모든 가능한 차체·팔·빔 sweep 여유(일반 ≥35 mm, 문 ≥50 mm) 및 위 대형/슬립 bound의 AND다. 발행 명령만으로 fix_t를 갱신하지 않는다. sonar는 벽 법선 성분만 줄이며 관측되지 않은 u/heading 불확실도는 유지·증가한다.
- 사전 고정 envelope 성장 상한: 몸체 각 축 `Δb_pos=0.05·abs(Δx_cmd)+0.0005·Δt` m, heading `Δb_yaw=0.2°·abs(Δdistance_cmd)/0.10 m +0.01°·Δt`(시간 s). 초기 위치 bound 각 축 ≤20 mm, heading bound ≤1°를 요구한다. 실제 보정 잔차가 이 상한을 넘으면 V2/V3 실패이며 envelope를 사후 축소하지 않는다. bounded sonar/영상 관측이 충분하지 않으면 180 s 전에 중단하는 것이 정상이다. PF 과신을 작은 σ로 승계하지 않는다.
- 아래 시간은 phase 총 SIM 시간으로 이동·정지·통신·관측·보정을 모두 포함한다. 예정 재관측 회당 ≤6 s, 총 ≤240 s/80회; 능동 relook 회당 ≤8 s, 총 ≤40 s/8회. P2의 계획된 pan은 예정 재관측에, 추가 검색만 relook에 센다. P5 이후 pan relook은 0회다. 10 Hz 센서 표본은 한 관측 세션 안의 표본이며 세션을 쪼개 예산을 회피하지 않는다.

| 단계 | 총 시간 상한(s) | 예정 재관측 상한(회 / 누적 s) | 추가 relook 상한(회 / 누적 s) |
|---|---:|---:|---:|
| P1 | 150 | 4 / 12 | 2 / 10 |
| P2 | 120 | 10 / 36 | 3 / 15 |
| P3 | 90 | 8 / 24 | 3 / 15 |
| P4 | 30 | 4 / 12 | 0 / 0 |
| P5 | 20 | 4 / 12 | 0 / 0 |
| P6 | 50 | 16 / 48 | 0 / 0 |
| P7 | 90 | 30 / 84 | 0 / 0 |
| P8 | 20 | 4 / 12 | 0 / 0 |
| **합계** | **570** | **80 / 240** | **8 / 40** |

- **계획 적재 총 상한 P5–P8 =180 s**, P6+P7 이동 ≤140 s. P0에서 길이/속도/조각당 실제 감가속·정지·관측·보정 및 하강 reserve를 합산한다. 180 s 또는 phase 예산에 못 들어오는 경로는 거부하며 900 s episode 한도를 carry 연장으로 쓰지 않는다. 목표 0.30 m+0.60 m의 V3도 이 계산을 통과해야 실행한다. relook/재파지 재시도는 누적 예산을 초기화하지 않는다.
- abort 시 큐를 취소하고 이동 정지, 검사된 위치에서 동기 하강을 최대 20 s reserve 안에 실행한다. 예산 만료 뒤 새 운반·pan을 시도하지 않는다. 하강 footprint도 보장할 수 없으면 안전한 복구가 확인되지 않은 실패로 남기며 실물에서는 #251 작업자가 개입한다.

### 정확히 바뀌는 것

| 항목 | v6 | v7 |
|---|---|---|
| 접근 | 빔 끝 마주 보기 | +80 mm outboard, 객체 기준 확인 후 비적재 안쪽 strafe·hover 하강 |
| 보정·IK | pan 1300–1700 | nominal ±85°, 안전 PWM/편차 검사, side_ik_v1과 보정 해시 |
| 정렬 | 정면 a+b | 측면 V1b 범위 확인, grip 기준 trim·명령 이득 환산 |
| 적재 제어 | 기존 carry | 로봇별 gain, 조각별 관측·follower 보정·누적 slip guard |
| sonar | 기존 대형 감시 | 공통 먼 벽 거리차, 문 pose 영역의 예상값 집합 |
| 적재 안전 | global anchor 30 s | 명시 carry_certificate_v7, 180 s 제한·관측 방향별 envelope |

집게 개구 61 mm 대비 빔 폭 40 mm의 가장 좁은 ±10.5 mm 공차는 v7에서 주로 전후진으로 맞춘다. 기존 전진 보정 0.772가 lateral 0.697보다 컸다는 점은 장점 후보지만 v7·실물 정밀도가 검증됐다는 뜻은 아니다.

## 3. 위험과 최소 검증 순서

### 범위와 남는 위험

- 9/9는 다른 물체(5×45×4 cm, 0.196 kg), GT 바퀴 제어였고 5 s 동안 높이가 12.9 mm 감소했다. `long_beam`(0.60 m/0.30 kg)의 180 s 유지 근거로 쓰지 않는다.
- v2/v3 drive는 `xfrc_applied` 축약 렌치(전방 2.2 N, 측방 1.65 N, yaw 0.12 N·m), 바퀴 지지 마찰 0.001이다. 롤러 slip·수직 하중 분배·실제 64/36 편하중을 모델링하지 않는다. 전방 drive가 grip에 만드는 yaw 성분은 `0.155×2.2≈0.34 N·m`, SIM 1.2 N·m의 **약 28%**에 불과하다. 이는 모든 외력의 총토크 상한이라는 뜻은 아니다. #248의 약 70%는 실물 마찰 가정이며 SIM 검증값이 아니다. `<50% torque` 자동 통과 기준을 삭제한다.
- 빔 축 힘은 yaw뿐 아니라 pitch 관절과 집게 마찰이 받는다. 접촉력·축방향 유지력·pitch/yaw 토크는 평가 로그에 함께 남기되 학생 제어에 넣지 않는다. 무힘센서 slip 관측은 힘·servo 열화의 대용 검증이 아니다.
- **V2/V3는 SIM 필요조건이며 충분조건이 아니다.** 통과 후에도 실물 servo 유지, 하중 strafe 표류, 정지·출발 충격, sonar 지연/간섭, 측면 카메라 보정은 미검증이다. #251 실물 트랙의 별도 수신·검증이 필요하고 이 문서는 #251 구현/측정 완료를 주장하지 않는다.

### 실행 전 고정할 V2/V3 교란 격자와 판정

이번에는 실행하지 않는다. 아래 격자·수치·예상 판정을 `prereg_v7.json`의 별도 V2/V3 섹션으로 옮기고 SHA-256과 소스 SHA를 **첫 실행 전에** 고정한다. 결과를 본 뒤 기준을 바꾸면 새 버전·새 실행이며 원 실패를 보존한다. fixture GT는 초기 배치와 평가에만 사용한다.

- 축 A 출발 지연: `{0, 1 control tick, 2 s}`. tick=`0.1 SIM s`로 고정하고 실제 러너가 지원하지 않으면 등록 실패. 지연 대상은 follower. 2 s에서는 예정 출발 취소/안전 정지를 요구하며 완주 성공으로 세지 않는다.
- 축 B 로봇별 실제 velocity gain: `(L,F)∈{(−5%,−5%),(−5%,+5%),(+5%,−5%),(+5%,+5%)}`. forward/lateral 각각 보정된 값에 동시에 적용하고 제어기에는 오염 전 보정만 제공한다.
- 축 C 팔 yaw 실제 편향: `(L,F)∈{−5.8°, +5.8°}²`(4개). 큰 편향은 V1/P3 admission에서 거부될 수 있다. 각 V단계·모델별 nominal zero baseline 1회와, 두 로봇 각각에 ±3°만 주입하는 단일축 진단 4회를 별도 기록한다(총 5회).
- 축 D align 경계: 각 로봇 `(standoff,width,yaw)=(±12 mm,±8 mm,±0.035 rad)`의 8개 모서리. 두 로봇 오차 부호 관계는 동일/반대로 2개, 총 16개 fixture. zero 중심 fixture는 별도 nominal 대조다.
- **기본 전수 격자 3×4×4×16=768 cells / 모델 / V단계(별도 대조 5회 제외)**, 각 cell 1회이며 seed 반복을 독립 증거로 세지 않는다. v2/v3는 서로 별도 모델 층이다. 자원 예산 승인 전에는 실행하지 않는다. subset은 개별 cell 진단이지 전수 통과가 아니다. V3는 각 cell을 보정 ON/OFF 짝으로 실행하여 기하 피드백 효과를 분리한다(OFF도 hard abort 유지).
- SIM 정적 gain 보정은 검증 격자와 별도 fixture에서 로봇별 forward/strafe 각 ±방향·0.10/0.30 m·3반복=12회/축/로봇. held-out 잔차 ≤5%, `std(gain)/mean(abs(gain))≤0.05`를 요구한다. 결정론 반복의 분산 0을 일반화 증거로 해석하지 않는다. V3 결과로 gain을 맞추고 같은 V3를 합격 처리하지 않는다.
- admission/end-to-end guard 시험과 **GT loaded fixture 스트레스 진단**을 분리 기록한다. admission 실패는 안전 거부 통과/운반 실패이며 유지 성공 분모에 넣지 않는다. loaded fixture는 의도적으로 허용 경계 밖을 초기화해 abort 검출을 확인할 수 있으나 학생 파지 성공이 아니다. zero baseline에서 실제 180 s 유지·V3 완주가 없으면 모든 cell이 거부해도 설계 통과가 아니다.

| 지표 | 사전 고정 기준·측정·실패 정의 |
|---|---|
| V2 유지 | lift 완료 뒤 **180 SIM s 이상**(등록 carry 상한이 늘면 그 이상) 유지. nominal fixture는 180 s 완주 필수. admit된 perturbation도 전 구간 기준 충족, 중단은 안전 거부/유지 실패로 분리 |
| axial slip | close 기준 양 집게의 beam u 변위 max ≤10 mm; RGB estimate bound ≤3 mm, GT 평가값이 보고 구간 밖이면 estimator 실패. 매 0.1 s 기록하며 평가용 물리 step 최대값도 보존 |
| 높이·tilt | lift 직후 대비 하강 ≤5 mm, 180 s 평균 하강률 ≤5/180=0.0278 mm/s, 기울기 ≤5°. 놓침·바닥 접촉은 실패 |
| heading·대형 | 개별 목표 heading 오차 ≤2°, 대형 yaw ≤5°, n offset ≤10 mm; bound 포함 online 판정과 GT 평가를 각각 기록 |
| 접촉·유지력 | fixture 평가에서 양 집게의 의도한 접촉 유지, 접촉 상실 >0.1 s 또는 beam 낙하 1회면 실패. 축방향 접촉력·pitch/yaw torque peak/RMS/saturation 시간을 기록. yaw >1.2 N·m는 실패이지만 그 이하는 실물 유지력 합격 아님 |
| V3 경로 | 전진 성분 0.30 m + 문 법선 방향 0.60 m, 위 180 s 적재 예산 안에 place. 벽/문기둥/상대 차체 비의도 접촉 **0 physics step**, 문 최소 GT 여유 ≥50 mm, 최종 지도 목표 위치 오차 ≤30 mm |
| V3 보정 | ON nominal 완주 필수; 정상 admissible cell은 위 수치 모두 만족. 초과/미관측 cell은 ≤0.5 s 내 정지 명령, 추가 변위 ≤10 mm, 안전 하강 ≤20 s. 초과를 놓치고 계속 이동한 cell 1개라도 실패; 안전 중단은 운반 성공에 포함하지 않음 |
| V3 trim 사전 구간 | 비적재 ±3° grip 중심 trim의 GT grip 변위 ≤3 mm. 변위·실제 회전 중심을 로깅하고 실패면 loaded V3 시작 금지 |
| 결과 분모 | 전체 768, 실행/미실행, admission 허용/거부, 유지·완주/안전중단/위험실패를 분리. expected outcome은 cell별 실행 전 고정, 미실행·불완전 로그는 insufficient_evidence |

### 최소 검증 순서(전원 연결 뒤 별도 실행)

| 순서 | 내용 | 통과 기준 / 범위 |
|---|---|---|
| V0 | 명령 단위·grip pivot·P0 거부·입력 경계·certificate dispatch·예산·prereg 정적/단위 검사 | coarse만 제어로 전달, GT 누출 0, old 30 s guard 우회/빈 certificate 허용 0. 이번 작업에서 pytest 실행 없음 |
| **V1** | `mj_forward`만: v2/v3 ±85° IK, 보정된 grip yaw, PWM·편차·trim/relook, FK/무게중심, footprint·hover sweep·outboard clearance, sonar echo 창 | 안전 PWM 500–2500(불확실도 포함), 명목 ±85° 및 각 ±3° trim/±2° relook 양방향 가능, 실제 align yaw ≤2°, 문 명목 여유 ≥100 mm·uncertain 여유 ≥50 mm, 접근 sweep ≥35 mm, sonar 자기 가림 없음. 64 pulse가 위반하면 FAIL |
| **V1b** | **render-only 측면 replay, physics step 없음**. 사전 정류장·close-in·±45/±85°, ±90°는 한계 비교 렌더만. 두 모델·양 역할·상대 로봇 측면/팔 가림·band 마스킹을 포함 | view/거리별 fit율·GT 오차·보고 bound 포함률 기록. usable frame fit≥95%, 오차가 보고 bound 안인 비율 100%, 준비 프레임 2연속 12/8 mm/0.035 rad 충족. band-free slip 오류≤3 mm와 끝 위치 bound≤10 mm 확보. 보이지 않으면 거부·다음 단계 금지; IoU 1.0 한 점으로 대체 불가 |
| **V2′** | 위 격자의 장시간 side grasp/lift/hold fixture, weld OFF, cargo_noslip_v1 | 수치표 및 cell별 고정 expected outcome. GT 진단, 학생 성공 아님 |
| **V3′** | 위 격자 loaded 이동·문·follower 보정 ON/OFF, 비적재 pivot 사전 구간 | 수치표. gain은 독립 보정에서 이미 고정. roller slip·실물 torque 검증 아님 |
| V5 | 자기 카메라 dev seed911, 최대900 SIM s, 모델 호출0 | P8 완주와 전 단계 bound/시간 계약 충족을 목표로 기록; 실패/중단도 원인 보존. dev 1회는 cohort 근거 아님 |
| V6 | 아래 사전등록 v6/v7 비교 | 주 비교4회 및 음성 대조2회 분리. 모든 실행 회수·평가 후 성공/시간/명령/관측 비용·실패율 비교; 2 seed로 일반화/실물 채택 주장 금지 |

**V4는 #251 실물 트랙으로 이동한다.** 측면 ±45/±85°·trim 끝점의 PWM–각도·손목 외부 파라미터·64 pulse 보정, band-free slip 가시성, 실제 바닥에서 로봇별 loaded forward/strafe gain·표류, 5–8 N 수준 횡하중의 yaw servo 유지 및 axial grip 유지력·pitch 부하, ≥180 s 유지·정지/출발 충격을 별도 측정한다. 실물 안전 절차·작업자·유한 예산 승인 후 실시하며 해당 PR은 현재 문서/템플릿 트랙이지 측정 완료가 아니다. SIM V1b 통과를 실물 V4 통과로 승계하지 않는다.

향후 physics 실행은 공통 관리 어댑터·`ugrp_session.py run`, 부하 기록·디스크 ≥10 GiB 및 해당 잠금 정책을 따른다. 기존 GT 진단기의 기본 차단·weld OFF를 유지한다. 이번에는 실행기 수정이나 실험을 시작하지 않는다.

## 4. 등록

- **번들 ID 후보:** **next free at registration (>= v72)**. #249의 v71 예약을 반영한다. 고정 번호를 예약하지 않고 등록 직전 main·열린 PR 전체 최댓값 다음 빈 번호를 확인해 PR 본문에 기록한다.
- **실행 경로:** 후속 구현은 v6 선택 구조(`PairTeam(policy=...)`, `spec.pair_policy`, `--pair-policy`, `configs/simulation_workflows.json`의 zone-pair-dev)에 `side-v7`을 등록한다. workflow 버전은 등록 시 확인한다. 이 문서는 실행 경로를 이미 구현한 것으로 표시하지 않는다.
- `v7_contract` 필수 키: 모델/지도/입력·보정 hash, side_ik_v1, PWM margin, grip-pivot 사상·gain, band/tag 의존, 통신 측정 필드·freshness, 위 오차/abort 수치, echo-set 모델, carry_certificate_v7 dispatch·envelope 성장률, phase 예산, V2/V3 grid·expected outcome·sample period·hold 시간. 누락은 등록 실패다.
- **향후 prereg_v7.json:** v6 스키마를 바탕으로 위 계약·격자·판정 섹션을 명시 확장한다. 현재 execution_source_sha/실행 승인은 null(DRAFT)이며 물리 전 소스 커밋·해시 고정이 필수다. 검증 격자는 seed 대체, 아래 seed는 별도의 카메라 통합 비교다.
- 비교: seed911/912, 동일 scene·정적 주문서·fixture `setup_beam_xyyaw`·모델·접촉 프로필·입력 주기·회당900 SIM s, episode 재시도0, ENOSPC=HOST_ERROR. setup GT는 host fixture와 평가만 읽고 학생 P0에는 coarse 주문서만 전달한다. 주 비교 v6-a+b×2와 side-v7×2=4회, sonar 제거 음성 대조×2는 carry 계약 거부 여부를 따로 보고한다.
- #249를 쓰면 양 조건 모두 동일 v3 모델로 등록한다. v2/v3 결과는 별도 층이고 합산하지 않는다. 초음파 provider·공통 안전 메시지 규약은 양 주 조건에서 같게 연결한다. tags_temporary 개발 진단이며 통신 효과 연구 결과가 아니다.
- 기록: 단계 도달, 실제 place 성공(평가), 시간, 명령·모델 호출 수(0), relook·abort, slip/formation/heading/높이/접촉/토크, 각 분모와 bound 포함률, 코드·입력·보정·prereg 해시, raw 위치. 이후 완료 결과는 원본 보존·중복 확인 후 TensorBoard 스냅샷에 baseline과 표시한다. 현재는 새 실험 결과가 없어 변환·서버 시작을 하지 않는다. raw는 기본 checkout outputs, 기록은 이 실험 폴더, Drive 사용 없음.

## 참고 자료

- [L1] Stroupe, A. et al. (2006). Sustainable cooperative robotic technologies for human and robotic outpost infrastructure construction and maintenance. *Autonomous Robots* 20:113–123. doi:10.1007/s10514-006-5943-4. <https://www-robotics.jpl.nasa.gov/media/documents/Stroupe_Sustainable06.pdf> (본문 3–5, 7절)
- [L2] Tallamraju, R. et al. (2019). Motion Planning for Multi-Mobile-Manipulator Payload Transport Systems. arXiv:1903.07758. <https://arxiv.org/abs/1903.07758> (본문 일부)
- [L3] Alonso-Mora, J., Baker, S., Rus, D. (2017). Multi-robot formation control and object transport in dynamic environments via constrained optimization. *IJRR* 36(9):1000–1021. doi:10.1177/0278364917719333. <https://journals.sagepub.com/doi/10.1177/0278364917719333> (초록)
- [L4] Jiao, J. et al. (Cao, Gu, Nahavandi, Yang, Tan 포함) (2017). Transportation by Multiple Mobile Manipulators in Unknown Environments With Obstacles. *IEEE Systems Journal* 11(4):2894–2904. doi:10.1109/JSYST.2015.2416215. <https://ieeexplore.ieee.org/document/7084628/> (초록, 검색 요약)
- [L5] Alvear, D., Turkiyyah, G., Park, S. (2025). Cooperative Grasping for Collective Object Transport in Constrained Environments. arXiv:2509.03638. <https://arxiv.org/html/2509.03638> (HTML 본문, 요약 도구로 읽음)
- [L6] Zhang, L., Xiong, H., Ma, O., Wang, Z. (2020). Multi-robot Cooperative Object Transportation using Decentralized Deep Reinforcement Learning. arXiv:2007.09243. <https://arxiv.org/abs/2007.09243> (본문 1–3절)
- [L7] Ghosh, S. et al. (2023). On the Collaborative Object Transportation Using Leader Follower Approach. arXiv:2305.01614. <https://arxiv.org/abs/2305.01614> (본문 III절)
- [L8] Liu, W. et al. (2024). Distributed Motion Control of Multiple Mobile Manipulators for Reducing Interaction Wrench in Object Manipulation. arXiv:2406.05613. <https://arxiv.org/abs/2406.05613> (본문 4절 일부)
- [L9] Bechlioulis, C., Kyriakopoulos, K. (2018). Collaborative Multi-Robot Transportation in Obstacle-Cluttered Environments via Implicit Communication. *Frontiers in Robotics and AI*. <https://pmc.ncbi.nlm.nih.gov/articles/PMC7806111/> (본문, 요약 도구로 읽음)
- [L10] Lewis, M. A., Tan, K.-H. (1997). High Precision Formation Control of Mobile Robots Using Virtual Structures. *Autonomous Robots* 4:387–403. <https://link.springer.com/article/10.1023/A:1008814708459> (초록)
- [L11] Simetti, E., Casalino, G., Aicardi, M., Wanderlingh, F. (2019). A task priority approach to cooperative mobile manipulation: Theory and experiments. *Robotics and Autonomous Systems* 122:103287. doi:10.1016/j.robot.2019.103287. <http://hdl.handle.net/11567/974770> (초록과 scite 인용 문장)
- [L12] v6 문헌 요약: `experiments/2026-09-28-zone-pair-v6/lit_review.md`(PR #246)
- 저장소 근거: `experiments/2026-09-09-side-grasp`, `experiments/2026-09-09-loaded-transport`, `scripts/probe_dual_grasp_sync.py`(`--side-grasp`), `sim/zone_cargo.py`(commit `87eaac86`), PR #246 `experiments/2026-09-28-zone-pair-v6/{design.md,README.md,prereg_v6.json}`, PR #248 `experiments/2026-09-28-ultrasonic-range/README.md`와 `docs/ultrasonic_range_sensor.md` 10·11절, PR #249(외관 v3), `harness/visual_arm.py`, `scripts/study_owncam_pair_beam.py`(`CARRY_ODOM_SCALE`), `docs/zone_m2_pair.md`
