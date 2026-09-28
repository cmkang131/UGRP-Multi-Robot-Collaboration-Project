# MasterPi 전면 초음파 거리 센서 (자기 초음파 거리 입력)

2026-09-28 사용자 결정(#221 최신 코멘트)으로 로봇 입력에 **자기 초음파 거리**를 추가했다. MasterPi 차체 앞면의 초음파 센서를 쓴다. 네 통신 조건 모두 같게 제공하며 조작 변수가 아니다. 용도는 세 가지다. 정적 지도와 비교해 위치 추정을 보조하고(PF 과신 검출), 충돌 여유를 확인하고, 정렬할 때 전방 거리로 단안 깊이의 모호성을 보완한다. GT 금지와 표식 비의존 원칙은 그대로 적용한다.

이 문서는 센서 모델(v1, `masterpi_ultrasonic_v1`)의 사양, 가정, 한계, sim2real 보정 계획을 기록한다. 실험 기록은 [`experiments/2026-09-28-ultrasonic-range`](../experiments/2026-09-28-ultrasonic-range/README.md)에 있다.

## 1. 실물 사양

| 항목 | 값 | 상태 | 근거 |
|---|---|---|---|
| 모듈 | Hiwonder RGB 발광 초음파 센서(glowy/glowing ultrasonic). MasterPi 구성품 | 확인 | MasterPi 문서 "RGB glowing ultrasonic sensor"·제품 페이지 |
| 측정 범위 | 2–400 cm | 확인(판매 페이지 사양) | Hiwonder 제품 사양 |
| 측정 각도 | 15° | 확인. 단, 반각인지 전체각인지는 **미확인** | Hiwonder 제품 사양 |
| 작동 주파수 | 40 kHz | 확인 | Hiwonder 제품 사양 |
| 인터페이스 | I2C, 주소 0x77 | 확인 | 제품 사양·SDK |
| SDK API | `Sonar.getDistance()`: 레지스터 0에서 2바이트 little-endian을 읽는다. 정수 **mm**를 반환하고 5000 초과는 5000으로 자른다. 읽기 실패 시 99999를 반환한다 | 확인 | Hiwonder 공식 TonyPi SDK `Sonar.py`(같은 모듈), MasterPi SDK 사본 |
| SDK 사용 예 | 장애물 회피 데모는 프레임마다 1회 읽는다. 최근 5개를 평균±표준편차로 걸러 평균하고, 임계값은 30 cm다 | 확인(MasterPi SDK 사본) | `Functions/Avoidance.py` |
| 정확도 | — | **미확인** → 가정: 3 mm + 거리의 1 % | HC-SR04 데이터시트 "3 mm"(가정) |
| 갱신 주기 | — | **미확인** → 가정: 60 ms | HC-SR04 데이터시트 "measurement cycle over 60 ms"(가정) |
| 블라인드 존 동작(2 cm 미만) | — | **미확인** → 모델에서는 invalid로 처리 | — |
| 무반사 시 반환값 | — | **미확인**(5000 clamp인지 다른 값인지 모름) → 모델에서는 invalid로 처리 | — |
| 장착 위치 x | 차체 중심에서 앞으로 78 mm | **미확인**(사진 기반 명목값) | `sim/masterpi_geometry.py` `NOMINAL_ULTRASONIC_X_M` |
| 장착 높이 | 바닥에서 54 mm | **미확인**(사진 기반 명목값) | `sim/masterpi_dynamics_v2.py` ultrasonic geom |
| 송·수신 소자 간격 | ±17 mm(좌우) | 미확인(외형 명목값). 모델 원점은 두 소자의 중점 | 같은 파일 |
| 장착 기울기 | 0°(수평) | **미확인** → 가정 | — |

## 2. 시뮬레이션 모델 (`sim/ultrasonic_range.py`, `harness/ultrasonic_model.py`)

- **원뿔 빔:** 중심 ray 1개와 2.5° 간격의 고리 6개(반각 15°)로 이루어진다. 고리 k에는 ray를 4k개 둔다. 모두 85개다. 위·아래·좌·우 방향 ray는 항상 포함한다. 한 번 읽을 때 `mj_multiRay`를 한 번 호출하고, 제외 물체에 맞은 ray만 `mj_ray`로 다시 쏜다.
- **에코 세기:** 방향 이득 `D(α)`와 입사각 이득 `R(β)`를 곱한다. `D(α)`는 축에서 1, 15° 가장자리에서 0.5이고 가장자리 밖에서는 0이다. `R(β) = exp(-½(β/15°)²)`다. 이 곱이 0.2 이상인 ray만 에코로 인정한다. 이 기준으로 평평한 벽은 법선에서 약 35°까지 보인다(가장자리 ray의 입사각 20.3°까지). 40°에서는 경면 반사로 에코를 놓친다. 바닥은 입사각이 커서(75° 이상) 에코가 되지 않는다.
- **최소 반환 거리 모델:** 인정된 ray 중 가장 가까운 거리를 첫 에코로 보고한다.
- **잡음:** 읽을 때마다 누락 2 %와 가짜 값 1 %(구간 전체 균등분포)를 적용한다. 거리 잡음은 가우시안 σ = 3 mm + 1 %다. 그 뒤 1 mm로 양자화한다. 2 cm 미만, 4 m 초과, 무반사는 invalid다.
- **결정론:** 읽기마다 `(seed, robot_id, seq)`로 독립 난수열을 만든다. 호출 순서가 다른 로봇이나 다른 코드에 영향을 주지 않는다.
- **주기:** `due(now)`는 직전 측정 뒤 60 ms가 지났는지 알려 준다. 읽기 시각은 측정한 SIM 시각 그대로 기록한다. 과거 상태로 소급해 측정하지 않는다.
- **제외 규칙:**
  - 자기 로봇의 운동학 트리 전체(차체·바퀴·팔·집게)는 `body_rootid`로 제외한다.
  - **쥔 물체는 제외하지 않는다**(2026-09-28 정정, PR #248). 실물 센서는 원뿔 안에 들어온 자기 짐을 보므로 SIM도 그대로 본다. 쥔 물체를 숨기는 API는 두지 않는다.
  - geom group 4(임무 전용 바닥 표시)와 5(자기 카메라 하드웨어·숨긴 원형)는 로봇 카메라와 같은 규칙으로 제외한다.
  - rgba alpha 0인 geom도 제외한다(`mj_ray` 의미론).
- **두 로봇 간섭(옵션 `crosstalk`, 기본 OFF):** 상대 센서가 우리 수신 원뿔 안에 있고, 우리가 상대 송신 원뿔 안에 있으며, 시선이 막히지 않았을 때만 적용한다. 이때 상대 펄스의 도착 시각을 겉보기 거리 `(d + c·Δ)/2`로 바꾼다. Δ는 매 주기 독립인 위상 차로 ±30 ms 균등분포다. 이 값이 자기 에코보다 짧을 때만 판독을 대체한다. 기본값을 OFF로 둔 이유가 있다. 모듈 펌웨어의 발사 시점과 수신 필터가 공개되지 않았다. 측정하지 않은 효과를 켜면 모든 실행이 조용히 바뀐다. 로봇 두 대가 마주 보고 첫 에코가 0.634 m일 때 ON으로 400회 읽으면 16회(4 %)가 짧거나 invalid였다(seed 5, 테스트 범위 5–60회).
- **출력:** `RangeReading(t, range_m, valid)`만 내보낸다. `measure_diagnostic`은 맞은 geom 이름과 무잡음 첫 에코를 함께 돌려주지만 **평가·테스트 전용**이다. 이 값은 제어기·provider·모델 요청에 넣지 않는다.
- 물리 step과 `mj_forward`를 호출하지 않는다. 호출자가 forward한 `data`를 읽기만 한다.

## 3. 로봇 입력 경로 (`harness/range_provider.py`, `harness/ultrasonic_map.py`)

- `OwnUltrasonicRangeProvider.on_reading(reading)`는 자기 판독을 시간 순서대로 받는다. `report(now)`는 `RangeReport`를 돌려준다. 필드는 `t_meas`(raw SIM 측정 시각), `age_s`, `valid`, `range_m`, `sigma_m`, `min/max_range_m`, `last_valid_t`, `source`다. `source`는 `own_ultrasonic_v1:<spec 해시 8자리>`다. PR #240의 표식 무관 자세 제공자 계약(시각·나이·출처·σ)과 같은 형태다. 판독이 유효해도 무엇에 맞았는지는 알려 주지 않는다. `check_range_limits`는 위반한 제한을 모두 돌려준다(`no_reading`, `stale`, `invalid`).
- `RangeHistoryWriter`는 실행 출력 폴더에 JSONL로 기록한다. 헤더에는 스키마, 로봇, 센서 모델, spec 해시를 넣고, 행에는 `t, range_m, valid`만 넣는다. `sim/workflow_manager.py`의 `output_receipt`가 출력 폴더 전체를 해시하므로 공통 실행 기록에 자동으로 연결된다.
- `provider_config_for_condition(name)`은 조건을 무시하고 같은 설정을 돌려준다. 알 수 없는 조건은 거부한다. 주 4조건이 같은 설정을 받는지는 테스트로 확인한다.
- `expected_range(static_map, pose)`는 정적 지도에서 예상 거리를 계산한다. 대상은 지도 장애물·문기둥 상자와 바닥 평면이고, SIM 센서와 **같은** ray 패턴과 에코 규칙을 해석적으로 적용한다. 지도에 없는 물체(상대 로봇·화물)는 포함하지 않는다.
- `range_consistency`와 `range_log_likelihood`는 비대칭으로 판정한다. 지도보다 **짧은** 판독은 지도에 없는 물체 때문일 수 있어 약한 증거다. 지도보다 **긴** 판독, 그리고 지도가 벽을 예측하는데 무반사인 경우는 자세가 틀렸다는 강한 증거다. 우도는 hit 가우시안, 짧은 쪽 지수분포, 균등 가짜값을 섞은 beam model이다. 가중치는 v6 연결의 시작값이며 적합하지 않았다.
- **기존 동작 불변:** 새 모듈(`harness/ultrasonic_{model,map,carry}.py`, `harness/range_provider.py`, `sim/ultrasonic_range.py`, `scripts/analyze_ultrasonic_carry_height.py`)은 기존 코드가 import하지 않는다. `rgb-standard-dispatch-v63`의 source closure와 zone study 실행 번들의 `runtime_files_sha256`에 들어가지 않는 것을 테스트로 확인했다. 기존 번들에서 이 입력은 OFF다.

## 4. 공동 운반 막대와 센서 높이 (실제 장면 `zone_wide_door_tags_v2` + `long_beam`)

막대 단면은 40×32 mm다. 바닥에 놓이면 z가 0.5–32.5 mm로, 센서 축(54 mm)보다 21.5 mm 아래에 있다. 기록된 M2 운반 높이(막대 몸체 z 0.061 m)로 들면 z가 61–93 mm로, 센서 축보다 7 mm 위다.

| 상황 | 결과 (테스트) |
|---|---|
| 바닥 막대 측면을 마주봄, 틈 5·7 cm | 안 보임. 원뿔 아래쪽 가장자리가 막대 윗면(32.5 mm)에 닿으려면 8.2 cm 이상 떨어져야 한다 |
| 같은 조건, 틈 10·20·50·100 cm | 보임(오차 < 1 cm) |
| 같은 조건, 틈 150 cm | 안 보임. 2.5° 고리 간격 때문에 약 1.2 m 너머의 32 mm 띠는 ray 사이로 빠진다(**ray 해상도 한계**) |
| 파지 자세(막대 끝면 47 mm 앞, 바닥) | 막대는 안 보이고 **상대 로봇**(r2)이 보인다 |
| M2 높이로 들어 올린 막대(61–93 mm) | 끝면 47 mm가 첫 에코다. 실물과 SIM 모두 자기 짐을 본다 |
| 권장 높이(명령 grip z 0.110 m, 막대 76–108 mm) | 막대는 원뿔 밖이고 상대 로봇(0.694 m)이 첫 에코다(8절) |

결론: 현재 M2·v6 lift(명령 grip z 0.095 m)에서는 초음파가 자기 짐만 본다. 운반 중 초음파를 쓰려면 8절의 운반 높이를 쓰거나, 짐 존재 확인 용도로만 쓴다.

## 5. 한계

- 장착 위치·높이·기울기, 정확도, 갱신 주기, 블라인드 존과 무반사 때 SDK 반환값은 실측하지 않았다.
- ray 표본화: 2.5° 간격이라 먼 거리의 작은 물체(1.2 m 너머의 32 mm 띠)를 놓친다. 음향 회절, 다중 반사, 부드러운 재질의 흡수, 모서리 반사는 모델에 없다.
- 반사율은 재질과 무관하게 같다고 가정한다. SIM의 시각 geom을 반사면으로 쓰므로 투명(alpha 0) 충돌 proxy는 보이지 않는다.
- 막대 아랫면은 grazing 입사(73° 이상)라 v1 모델에서 에코가 없다. 실물에서 아랫면 모서리의 회절 에코가 잡히는지는 미확인이다(8절의 `near_face` 기준이 여기에 기댄다).
- SIM은 자기 팔을 제외한다. 권장 높이에서는 자기 집게·팔도 원뿔 밖이다(진단으로 확인). 하지만 더 낮은 자세에서는 실물이 자기 집게를 볼 수 있다.
- 간섭 모델은 자유 위상 가정이며 펌웨어 필터를 모른다.

## 6. sim2real 보정 계획

1. **장착 측정:** 캘리퍼로 센서 중심의 x와 높이, 기울기를 잰다. `UltrasonicSpec`의 새 버전으로 기록한다(v1 값은 덮어쓰지 않는다).
2. **정면 벽:** 3–350 cm를 20점 이상, 점마다 50회 읽는다. 편향, σ(r), 누락률, 블라인드 존과 무반사 때의 반환값(5000 또는 99999)을 적합한다.
3. **입사각:** 50 cm 벽을 0–60°로 5° 간격으로 측정해 최대 가시 각도로 `incidence_sigma_deg`와 `echo_threshold`를 맞춘다.
4. **원뿔:** 지름 2 cm 막대를 좌우·상하로 옮기며 가시 경계를 재서 반각과 방향 이득을 맞춘다.
5. **공동 운반 막대:** 바닥 막대, M2 높이(0.095), 권장 높이(0.110·0.120)로 든 막대의 실제 판독을 기록해 4절·8절 표와 대조한다. 권장 높이에서 아랫면 모서리 회절 에코가 없는지 특히 확인한다.
6. **두 로봇 간섭:** 0.4–1.5 m에서 마주 보게 두고 두 센서를 동시에 켠다. 짧은 판독 비율을 재서 `crosstalk` 기본값을 다시 판단한다.
7. 결과는 `experiments/`의 새 ID에 raw sha256과 함께 남긴다. 보정한 spec은 새 `sensor_model_id`로 등록한다.

## 7. 공동 운반 v6(#246) 연결 제안 (이번 범위 아님)

- **PF 측정 모델:** relook 시점마다 `range_log_likelihood(reading, expected_range(map, particle_pose))`를 입자 가중치에 곱한다. 짧은 판독은 약하게, 긴 판독은 강하게 반영한다. 적재 중과 상대 로봇이 원뿔 안에 있을 수 있는 구간(파지·정렬)은 hit 항을 끈다.
- **과신 검출(guard):** 보고 σ가 작은데 `range_consistency`가 `longer_than_map` 또는 `no_echo_where_map_predicts`를 N회 연속 내면 PF가 과신한 것이다. 이때 relook이나 lost 처리로 보낸다. dev14처럼 오차 82 cm에 σ 1.9 cm인 경우를 잡는 용도다.
- **운반:** 8절의 운반 높이 `recommended_carry_tool_z()`(현재 0.110 m)와 `CarrySonarMonitor('above_cone')`를 쓴다.
- **정렬:** 파지 자세에서 판독은 상대 로봇까지의 전방 거리다. 빔 상대 정렬(`BeamRelativeReport`)의 단안 깊이를 교차 확인하는 데 쓴다. 이 값은 **상대 거리 관측일 뿐이므로 전역 σ를 초기화하지 않는다**(v6 규칙과 같다).
- **충돌 여유:** 접근 중 `valid and range_m < 여유`이면 전진 명령을 막는다. 지도에 없는 물체도 막을 수 있다. 막은 기록은 자기 판독 이력으로만 남긴다.

## 8. 운반 높이: 짐을 초음파 원뿔 위로 들 수 있는가 (2026-09-28, #221·#246)

사용자 요청은 "짐을 초음파 센서 위로 들어 운반 중에도 앞을 보게" 하는 것이다. 운동학만으로 분석했다(물리 step·시뮬레이션 실행 0회). 코드는 `harness/ultrasonic_carry.py`와 `scripts/analyze_ultrasonic_carry_height.py`, 결과는 [`carry_height_analysis.json`](../experiments/2026-09-28-ultrasonic-range/carry_height_analysis.json)이다.

**기준 기하(M2·v6 facing-pair 운반):**
- 각 로봇은 막대 끝에서 0.03 m 안쪽을 grasp 반경 0.155 m에서 쥔다. 두 로봇은 서로 마주 본다.
- 센서에서 가까운 끝면까지 0.047 m, 먼 끝까지 0.647 m다.
- lift는 M2 hover(명령 grip z 0.095 m)다. 기록된 막대 몸체 z는 0.0602–0.061 m(문 통과 31회)이므로 짐 처짐은 약 10 mm다.
- 여유: 짐 처짐 10 mm, 막대 pitch 2°(M2 p95 1.76°, 최대 6.16°는 민감도로만), 높이 5 mm.

**두 기준과 필요한 명령 grip z (장착 54/78 mm):**

| 기준 | 반각 15° | 반각 7.5°(전체각 해석) |
|---|---|---|
| `whole_beam`: 막대 전체가 원뿔 밖 | 0.287 m | 0.199 m |
| `near_face`: 가까운 끝면만 원뿔 밖, 아랫면은 grazing | **0.107 m** | 0.100 m |

**팔 도달(보정된 IK `harness.visual_arm`, 반경 0.155 m):**
- 보정 탐색 범위(pitch −90…−40°)에서 최대 0.161 m(pitch −40°)다. pitch를 0°까지 풀어도 0.239 m다.
- 따라서 `whole_beam`은 **불가능하다.** 15°에서는 기하적으로 닿지 않는다. 7.5°에서도 pitch −20° 부근이 필요해 보정 범위 밖이고, 막대가 턱 안에서 52° 돌아야 한다.
- 반대로 짐을 원뿔 **아래**로 두는 것도 불가능하다. 원뿔 아래 가장자리가 먼 끝에서 바닥 아래로 내려간다.

**권장: `near_face`, 명령 grip z = `recommended_carry_tool_z()` = 0.110 m** (5 mm 단위로 올림; 막대 아랫면은 약 76 mm로, 원뿔 가장자리 66.6 mm보다 9 mm 위)

kinematics 장면(`zone_wide_door_tags_v2` + `long_beam`, 두 로봇 IK 자세, `mj_forward`만 사용)에서 확인한 값:

| 명령 grip z | IK pitch (grasp −72.1°에서 변화) | 첫 에코 | 막대–팔 최소 거리(집게 제외) | 전방 tip 가속도 | 손목 카메라 막대 IoU(grasp 대비, pinhole 대리값) |
|---|---|---|---|---|---|
| 0.095 (M2) | −64.1° (+8.0°) | **자기 막대 끝면 0.048 m** | 32 mm(wrist) | 4.1 m/s² | 0.86 |
| **0.110** | −60.0° (+12.1°) | **상대 로봇 0.694 m** | 31 mm | 4.0 m/s² | 0.83 |
| 0.120 | −56.0° (+16.0°) | 상대 로봇 0.694 m | 30 mm | 3.9 m/s² | 0.80 |

- **SIM 관절 범위:** 세 높이 모두 안에 든다. MuJoCo grip site가 FK와 1 mm 안에서 일치한다.
- **자기 팔을 포함한 진단:** 0.110 m에서도 첫 에코가 상대 로봇이다. 자기 집게와 팔도 원뿔 밖이다.
- **정적 전복:** 로봇 1.10 kg에 짐 몫 0.15 kg을 grip점에 둔다. 앞바퀴 축 기준 복원/전복 모멘트 비는 3.9다. 전방 tip 가속도는 약 4 m/s², 측방은 약 7.9 m/s²다. 운반 속도 0.06 m/s의 가감속보다 한 자릿수 이상 크다. 높이를 15 mm 올린 효과(무게중심 +2.6 mm)는 무시할 만하다.
- **상대 로봇 간섭:** 막대와 양쪽 wrist 사이 최소 거리는 31 mm다(M2 32 mm).
- **grip 변화:** grip 점(반경 0.155 m)은 같다. 다만 tool pitch가 grasp 대비 12.1° 바뀐다(M2는 8.0°). 두 로봇 모두 막대가 턱 축 둘레로 돈다. M2에서 8°는 통과했지만 12°의 마찰 토크 여유는 **미검증**이다(물리 확인 필요).
- **손목 카메라:** 카메라 높이는 0.13 → 0.145 m, 광축은 −56.6 → −52.6°로 바뀐다. 쥔 막대의 이미지 대리 IoU는 grasp 대비 0.86 → 0.83이다. grasp→lift co-motion 검사(`HOLD_MIN_IOU` 0.45, M2 실측 0.735/0.835)의 여유가 약간 줄 수 있다. 렌더링 검증은 하지 않았다.
- **장착 민감도:** 장착 높이 44–64 mm, 전방 68–88 mm에서 `near_face` 권장값은 0.095–0.120 m다(보정 IK 도달 범위 안). 로봇을 다시 모델링하면 새 `UltrasonicSpec`으로 `recommended_carry_tool_z(spec)`를 다시 계산한다.

**운반 중 초음파 규칙(`CarrySonarMonitor`, 자기 판독만 사용):**
- lift 직후 자기 판독 5개의 중앙값을 기준값으로 잡는다. 권장 높이에서 이 값은 상대 로봇까지의 거리(≈0.69 m)다. 판정은 같은 상태가 3회 연속(60 ms 주기) 나올 때만 낸다.
- 매 판독은 다음 가운데 하나로 판정한다.
  - `formation_ok`: 기준값 ± max(2 cm, 4σ). 대형이 유지되고 막대가 원뿔 밖에 있다.
  - `load_in_cone`: 12 cm 이내의 판독. 막대가 처지거나 미끄러져 원뿔로 내려왔다. 멈추고 파지를 확인한다.
  - `intrusion`: 기준값보다 짧지만 12 cm보다 먼 판독. 로봇 사이, 막대 아래로 물체가 들어왔다. 멈춘다.
  - `beyond_baseline`: 기준값보다 길거나 무반사. 상대가 멀어졌다(대형 붕괴, 상대 쪽 짐 이탈). 멈춘다.
- **한계:** facing-pair 운반에서는 두 로봇의 전면 센서가 서로를 향한다. 그래서 운반 중 "전방 거리"는 사실상 상대 로봇까지의 거리와 두 로봇 사이 공간이다. 대형 바깥의 진행 방향 장애물은 이 센서로 볼 수 없다.
- **짐 확인만 원할 때(대안, 현재 M2 높이 0.095):** `CarrySonarMonitor('load_in_cone')`를 쓴다. 기준값은 자기 짐 끝면(≈0.048 m)이다. 판독이 이보다 길게 뛰면 `load_lost`(짐 이탈)다. 이 모드에서는 전방을 볼 수 없다. 한 센서가 첫 에코만 주므로 두 용도를 동시에 쓸 수 없다.
- 이 판정은 초음파 판독만의 결론이다. 손목 카메라 hold 검사를 대체하지 않고 보조한다. 실제 운반 성공은 따로 검증한다.

## 참고 자료

- Hiwonder Glowing Ultrasonic Sensor 제품 페이지: <https://www.hiwonder.com/products/glowing-ultrasonic-sensor>
- Hiwonder Glowy RGB Ultrasonic Sensor 제품 페이지: <https://www.hiwonder.com/products/glowy-rgb-ultrasonic-sensor>
- Hiwonder Glowing Ultrasonic Sensor wiki: <https://wiki.hiwonder.com/projects/Glowing-Ultrasonic-Sensor/en/latest/>
- MasterPi 문서(Getting Ready): <https://docs.hiwonder.com/projects/MasterPi/en/latest/docs/1.getting_ready.html>
- Hiwonder SDK `Sonar.py`(공식 TonyPi 저장소, 같은 I2C 모듈): <https://github.com/Hiwonder/TonyPi/blob/main/HiwonderSDK/hiwonder/Sonar.py>
- MasterPi SDK 사본 `Sonar.py`, `Avoidance.py`(비공식 저장소): <https://github.com/SquirrelRobotics/MasterPi>
- HC-SR04 데이터시트(가정값 출처): <https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf>
- MuJoCo `mj_ray`/`mj_multiRay`(3.12): <https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-ray>
- MuJoCo `mj_geomDistance`: <https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-geomdistance>
- M2 운반 기록(lift 높이·기울기): [`experiments/2026-09-26-zone-m2-pair`](../experiments/2026-09-26-zone-m2-pair/), lift 자세 `scripts/study_owncam_pair_beam.py` `HOVER_Z_M`
- 초음파 특성(원뿔 반사, 경면 반사로 인한 가시 각도 한계): Siegwart, Nourbakhsh, Scaramuzza, *Introduction to Autonomous Mobile Robots*, 2nd ed., 4.1.6 (MIT Press, 2011)
