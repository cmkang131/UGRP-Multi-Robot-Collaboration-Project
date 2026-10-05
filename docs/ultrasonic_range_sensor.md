# MasterPi 전면 초음파 거리 센서 (자기 초음파 거리 입력)

2026-09-28 사용자 결정(#221 최신 코멘트)으로 로봇 입력에 **자기 초음파 거리**를 추가했다. MasterPi 차체 앞면의 초음파 센서를 쓴다. 네 통신 조건 모두 같게 제공하며 조작 변수가 아니다. 용도는 세 가지다. 정적 지도와 비교해 위치 추정을 보조하고(PF 과신 검출), 충돌 여유를 확인하고, 정렬할 때 전방 거리로 단안 깊이의 모호성을 보완한다. GT 금지와 표식 비의존 원칙은 그대로 적용한다.

이 문서는 센서 모델(v2, `masterpi_ultrasonic_v2`; PR #248 적대적 검토 반영)의 사양, 가정, 한계, sim2real 보정 계획을 기록한다. 이 입력은 허용된 관측이다. 2026-09-29부터 구역 연구 실행기에 **명시적으로 켜는 경우에만** 연결된다(12절, 기본 꺼짐, 켜도 어떤 제어기도 값을 쓰지 않는다). 켠 실행은 기존 baseline과 나눠 비교한다. 실험 기록은 [`experiments/2026-09-28-ultrasonic-range`](../experiments/2026-09-28-ultrasonic-range/README.md)에 있다.

## 1. 실물 사양

| 항목 | 값 | 상태 | 근거 |
|---|---|---|---|
| 모듈 | Hiwonder RGB 발광 초음파 센서(glowy/glowing ultrasonic). MasterPi 구성품 | 확인 | MasterPi 문서 "RGB glowing ultrasonic sensor"·제품 페이지 |
| 측정 범위 | 2–400 cm | 확인(판매 페이지 사양) | Hiwonder 제품 사양 |
| 측정 각도 | 15° | 확인. 단, 반각인지 전체각인지는 **미확인** | Hiwonder 제품 사양 |
| 작동 주파수 | 40 kHz | 확인 | Hiwonder 제품 사양 |
| 인터페이스 | I2C, 주소 0x77 | 확인 | 제품 사양·SDK |
| SDK API | `Sonar.getDistance()`: 레지스터 0에서 2바이트 little-endian을 읽는다. 정수 **mm**를 반환하고 5000 초과는 5000으로 자른다. 읽기 실패 시 99999를 반환한다 | 확인 | Hiwonder 공식 TonyPi SDK `Sonar.py`(같은 모듈), MasterPi SDK 사본 |
| SDK 사용 예 | 장애물 회피 데모는 프레임마다 1회 읽는다. 최근 5개를 평균±표준편차로 걸러 평균하고, 임계값은 30 cm다 | **미확인**(비공식 사본에서만 봄) | `Functions/Avoidance.py`(비공식 사본) |
| 정확도 | — | **미확인** → 가정: 3 mm + 거리의 1 % | HC-SR04 데이터시트 "3 mm"(가정) |
| 갱신 주기 | — | **미확인** → 가정: 60 ms | HC-SR04 데이터시트 "measurement cycle over 60 ms"(가정) |
| 블라인드 존 동작(2 cm 미만) | SDK는 0–19 mm 정수를 그대로 낼 수 있다 | **미확인** → 모델 상태 `blind`(REP 117 −Inf) | SDK 코드, ROS REP 117 |
| 무반사 시 반환값 | SDK는 5000 clamp, 4001–5000 정수 가능 | **미확인** → 모델 상태 `no_echo`(REP 117 +Inf) | SDK 코드 |
| I2C 실패 | 99999 | 확인(SDK 코드) → 상태 `sensor_absent`(REP 117 NaN) | SDK 코드 |
| 장착 위치 x | 차체 중심에서 앞으로 78 mm(소자 중심), 송수신면 84 mm | **미확인**(사진 기반 명목값). ray와 거리는 **송수신면**에서 잰다 | `sim/masterpi_geometry.py` `NOMINAL_ULTRASONIC_X_M`, SIM 소자 원기둥 반길이 6 mm |
| 장착 높이 | 바닥에서 54 mm | **미확인**(사진 기반 명목값) | `sim/masterpi_dynamics_v2.py` ultrasonic geom |
| 송·수신 소자 간격 | ±17 mm(좌우) | 미확인(외형 명목값). 모델 원점은 두 소자의 중점 | 같은 파일 |
| 장착 기울기 | 0°(수평) | **미확인** → 가정 | — |

## 2. 시뮬레이션 모델 (`sim/ultrasonic_range.py`, `harness/ultrasonic_model.py`)

- **원뿔 빔:** 중심 ray 1개와 2.5° 간격의 고리 6개(반각 15°)로 이루어진다. 고리 k에는 ray를 4k개 둔다. 모두 85개다. 위·아래·좌·우 방향 ray는 항상 포함한다. 원뿔 안에서 ray가 없는 가장 큰 빈틈은 반경 약 **2.2°**다. 그래서 약 4.4°보다 작게 보이는 물체는 빠질 수 있다(예: 34 mm 상자는 약 0.45 m 너머). ray 원점은 **송수신면**(소자 중심 +6 mm)이다.
- **에코 세기:** 왕복 방향 이득 `D(α)`와 입사각 이득 `R(β)`를 곱한다. `D(α)`는 축에서 1, 15° 가장자리에서 0.5이고 가장자리 밖에서는 0이다. `R(β) = exp(-½(β/15°)²)`다. SIM 센서는 이 곱이 0.2 이상인 ray만 에코로 인정한다(하드 문턱). 이 기준으로 평평한 벽은 법선에서 약 35°까지 보인다. 40°에서는 경면 반사로 에코를 놓친다. 바닥은 입사각이 커서(75° 이상) 에코가 되지 않는다.
- **최소 반환 거리 모델:** 인정된 ray 중 가장 가까운 거리를 첫 에코로 보고한다.
- **잡음:** 읽을 때마다 누락 2 %와 가짜 값 1 %(구간 전체 균등분포)를 적용한다. 거리 잡음은 가우시안 σ = 3 mm + 1 %다. 그 뒤 1 mm로 양자화한다.
- **판독 상태(REP 117, SDK 대응):**
  - `ok`: 2 cm–4 m 안의 에코
  - `blind`: 2 cm보다 가까움
  - `no_echo`: 4 m 안에 에코 없음. 누락도 실물에서는 무반사와 구별되지 않으므로 `no_echo`로 낸다. 원인 `dropout`은 평가용 진단에만 남긴다.
  - `sensor_absent`: I2C 실패(SDK 99999). SIM은 내지 않고 실물 어댑터 `reading_from_sdk`만 낸다.
- **결정론·공통 난수:** seed는 필수이며 `sensor_seed(episode_seed, robot_id)`(sha256, 64비트)로 정한다. 조건과 호출 횟수는 seed에 들어가지 않는다. 잡음 색인은 측정 tick `round(t / 60 ms)`다. 그래서 네 조건이 같은 시각에 같은 잡음을 받는다. 간섭은 별도 스트림을 쓰므로 간섭을 켜도 잡음열이 밀리지 않는다.
- **주기:** `due(now)`는 직전 측정 뒤 60 ms가 지났는지 알려 준다. 읽기 시각은 측정한 SIM 시각 그대로 기록한다. 과거 상태로 소급해 측정하지 않는다.
- **제외 규칙(2026-09-28 검토 P1 수정):**
  - ray가 건너뛰는 것은 **자기 차체 쪽만**이다. 센서 하우징이 달린 차체 body와 바퀴가 여기에 해당한다. 센서는 자기 면 뒤와 하우징을 볼 수 없다.
  - **자기 팔·손목·카메라·집게·턱은 포함한다.** 실물은 파지·하강 자세에서 자기 집게를 본다(4절 표와 [`own_arm_pose_sweep.json`](../experiments/2026-09-28-ultrasonic-range/own_arm_pose_sweep.json)).
  - **쥔 물체도 포함한다.** 팔이나 짐을 숨기는 API는 두지 않는다.
  - geom group 4(임무 전용 바닥 표시)와 rgba alpha 0 geom(`mj_ray` 의미론)은 건너뛴다. group 5의 숨긴 원형은 모두 alpha 0이다. 로봇 카메라 하드웨어는 v2 모델에서 group 5가 아니다.
  - 차체 원점 높이는 v2 상수가 아니라 모델의 spawn 높이에서 읽는다. 센서 site가 있는 모델(예: #249 v3)은 `site=`로 그 pose를 쓴다.
- **두 로봇 간섭(옵션 `crosstalk`, 기본 OFF, 마주 보는 대형의 평가에서는 ON: `FACING_PAIR_SPEC`):**
  - 적용 조건: 상대 센서가 우리 수신 원뿔 안에 있고, 우리가 상대 송신 원뿔 안에 있으며, 시선이 막히지 않았을 때
  - 상대 펄스의 도착 시각을 겉보기 거리 `(d + c·Δ)/2`로 바꾸고, 자기 에코보다 짧을 때만 판독을 대체한다.
  - **위상 모델(검토 P2-4 수정):** 모듈이 각자 free-running하므로, 쌍마다 초기 위상과 클럭 차(±0.5 %, 가정)로 위상 Δ가 **천천히 표류한다.** 여기에 20 µs 지터를 더한다. 그래서 간섭 창을 연속 판독이 지나가며 **burst로** 나온다.
  - 기본 OFF인 이유: 펌웨어 발사 시점과 수신 필터가 공개되지 않았고, 측정하지 않은 효과를 켜면 모든 실행이 조용히 바뀐다.
- **출력:** `RangeReading(t, range_m, valid, status)`만 내보낸다. `measure_diagnostic`은 맞은 geom 이름, 무잡음 첫 에코, 원인, 자기 팔 여부를 함께 돌려주지만 **평가·테스트 전용**이다. 실행기 모듈이 진단 API를 참조하지 않는지는 AST 테스트로 확인한다.
- 물리 step과 `mj_forward`를 호출하지 않는다. 호출자가 forward한 `data`를 읽기만 한다.

## 3. 로봇 입력 경로 (`harness/range_provider.py`, `harness/ultrasonic_map.py`)

- `OwnUltrasonicRangeProvider.on_reading(reading)`는 자기 판독을 시간 순서대로 받는다. `report(now)`는 `RangeReport`를 돌려준다. 필드는 `t_meas`(raw SIM 측정 시각), `age_s`, `valid`, `status`, `range_m`, `sigma_m`, `min/max_range_m`, `last_valid_t`, `last_valid_range_m`, `source`다. `source`는 `own_ultrasonic_v2:<spec 해시 8자리>`다. PR #240의 표식 무관 자세 제공자 계약(시각·나이·출처·σ)과 같은 형태다. 판독이 유효해도 무엇에 맞았는지는 알려 주지 않는다. `check_range_limits`는 위반한 제한을 모두 돌려준다(`no_reading`, `stale`, `invalid`, `blind`, `sensor_absent`). 실물 SDK 값은 `reading_from_sdk`로 바꾼다(99999 → `sensor_absent`, 20 mm 미만 → `blind`, 4000 mm 초과 → `no_echo`).
- `RangeHistoryWriter`는 실행 출력 폴더에 JSONL로 기록한다. 헤더에는 스키마, 로봇, 센서 모델, spec 해시, **잡음 seed(필수)**와 seed·색인 규칙을 넣고, 행에는 `t, range_m, valid, status`만 넣는다. `sim/workflow_manager.py` 경로로 실행할 때만 `output_receipt`가 출력 폴더 전체를 해시해 공통 실행 기록에 연결한다. 다른 실행기는 직접 연결해야 한다.
- `provider_config_for_condition(name)`은 조건을 무시하고 같은 설정(잡음 seed 규칙 포함)을 돌려준다. 알 수 없는 조건은 거부한다. 주 4조건이 같은 설정을 받는지는 테스트로 확인한다.
- `expected_range(static_map, pose)`는 정적 지도에서 예상 거리를 계산한다. 대상은 지도 장애물·문기둥 상자와 바닥 평면이고, SIM 센서와 **같은** ray 패턴과 에코 규칙을 해석적으로 적용한다. 지도에 없는 물체(상대 로봇·화물)는 포함하지 않는다.
- `range_consistency`와 `range_log_likelihood`는 비대칭이지만 **완만하게** 판정한다(검토 P2-1 수정).
  - 지도보다 **짧은** 판독은 지도에 없는 물체 때문일 수 있어 약한 증거다.
  - 지도보다 **긴** 판독과 무반사도 중간 정도의 증거일 뿐이다. 경면·다중 반사, grazing 면의 가림, 지도 배치 오차가 원인일 수 있다.
  - 우도는 Thrun *Probabilistic Robotics* 6.3의 beam model 혼합이다(hit / short / max / rand + 경면·다중 반사의 긴 쪽 균등 항). hit 폭에는 센서 σ, 자세 σ, 지도 σ(2 cm, 가정)를 넣는다.
  - 검출 확률은 에코 세기의 logistic(문턱 0.2, 폭 0.05)이다. 그래서 가시 경계(약 35°)에서 우도가 **연속적으로** 바뀐다. 예측 원뿔에 에코가 있는 판독과 무반사 판독의 판독당 |LLR|은 2 nats로 제한한다.
  - `blind`와 `sensor_absent`는 자세 정보가 없으므로 LLR 0이다. 가중치·폭·상한은 가설이며, 6절 3단계(입사각 측정) 뒤에 정한다.
- **기존 동작 불변:** 새 모듈(`harness/ultrasonic_{model,map,carry}.py`, `harness/range_provider.py`, `sim/ultrasonic_range.py`, `scripts/analyze_ultrasonic_carry_height.py`)은 기존 코드가 import하지 않는다. `rgb-standard-dispatch-v63`의 source closure와 zone study 실행 번들(현재 main, #240·#242·#243 병합 후)의 `runtime_files_sha256`에 들어가지 않는 것을 테스트로 확인했다. 기존 번들에서 이 입력은 OFF다. 실행기 연결은 12절의 어댑터가 켤 때만 붙는다.

## 4. 공동 운반 막대·자기 팔과 센서 높이 (실제 장면 `zone_wide_door_tags_v2` + `long_beam`)

막대 단면은 40×32 mm다. 바닥에 놓이면 z가 0.5–32.5 mm로, 센서 축(54 mm)보다 21.5 mm 아래에 있다. 기록된 M2 운반 높이(막대 몸체 z 0.061 m)로 들면 z가 61–93 mm로, 센서 축보다 7 mm 위다. 거리는 모두 송수신면에서 잰다. 자기 팔과 짐은 ray에 **포함**한다(검토 P1 수정 뒤 다시 계산).

| 상황 | 결과 (테스트·[`own_arm_pose_sweep.json`](../experiments/2026-09-28-ultrasonic-range/own_arm_pose_sweep.json)) |
|---|---|
| 바닥 막대 측면을 마주봄, 틈 5·7 cm | 안 보임. 원뿔 아래쪽 가장자리가 막대 윗면(32.5 mm)에 닿으려면 약 8 cm 이상 떨어져야 한다 |
| 같은 조건, 틈 10·20·50·100 cm | 보임(오차 < 1 cm) |
| 같은 조건, 틈 150 cm | 안 보임. ray 사이 빈틈(최대 약 2.2°) 때문이다(**ray 해상도 한계**) |
| **파지 자세(보정 IK, grip z 0.024 m)** | **자기 집게(crossbar)가 첫 에코다(0.043 m).** 이전 판의 "상대 로봇이 보인다"는 팔을 기본 자세로 두고 자기 팔을 제외한 테스트에서 나온 것이라 **철회한다** |
| 하강 grip z 0.040 m | 자기 집게 0.048 m |
| 하강·상승 grip z 0.060 m 이상 | 자기 팔은 원뿔 밖이다. 막대가 바닥에 있으면 상대 로봇(0.59–0.69 m)이 보인다 |
| M2 높이로 들어 올린 막대(61–93 mm) | 끝면 0.042 m가 첫 에코다. 실물과 SIM 모두 자기 짐을 본다 |
| 권장 높이(명령 grip z 0.110 m, 막대 76–108 mm) | 막대와 자기 팔은 원뿔 밖이고 상대 로봇(0.688 m)이 첫 에코다(8절) |

결론:
- 파지·하강 구간(grip z 약 0.05 m 이하)에서는 초음파가 **자기 집게**를 본다. 이 구간의 판독은 정렬·충돌 판정에 쓸 수 없다.
- 현재 M2·v6 lift(0.095 m)에서는 자기 짐만 본다. 운반 중 초음파를 쓰려면 8절의 운반 높이를 쓰거나, 짐 존재 확인 용도로만 쓴다.

## 5. 한계

- 장착 위치·높이·기울기, 정확도, 갱신 주기, 블라인드 존과 무반사 때 SDK 반환값은 실측하지 않았다.
- ray 표본화: 원뿔 안의 최대 빈틈이 약 2.2°라, 약 4.4°보다 작게 보이는 물체를 놓칠 수 있다(34 mm 상자는 약 0.45 m 너머). 실물 빔은 연속이다. 음향 회절, 다중 반사, 부드러운 재질의 흡수, 모서리 반사는 SIM에 없다(지도 우도에는 긴 쪽 항으로만 반영).
- 반사율은 재질과 무관하게 같다고 가정한다. SIM의 시각 geom을 반사면으로 쓰므로 투명(alpha 0) 충돌 proxy는 보이지 않는다.
- 막대 아랫면은 grazing 입사(73° 이상)라 v1 모델에서 에코가 없다. 실물에서 아랫면 모서리의 회절 에코가 잡히는지는 미확인이다(8절의 `near_face` 기준이 여기에 기댄다).
- 송·수신 소자가 ±17 mm 떨어져 있는데 단일 점으로 근사했다. 10 cm 이하에서는 부정확하다(파지 구간의 자기 집게 거리 포함).
- 간섭 모델은 표류 위상 가정(클럭 차 ±0.5 %)이며 펌웨어 필터를 모른다.
- 정적 지도 예상값은 지도 장애물·문기둥 상자와 평평한 바닥만 본다. `terrain`과 상자가 아닌 요소는 무시한다. SIM–지도 일치는 `zone_wide_door_tags_v2`에서만 테스트했다.

## 6. sim2real 보정 계획

1. **장착 측정:** 캘리퍼로 센서 중심의 x와 높이, 기울기를 잰다. `UltrasonicSpec`의 새 버전으로 기록한다(v1 값은 덮어쓰지 않는다).
2. **정면 벽:** 3–350 cm를 20점 이상, 점마다 50회 읽는다. 편향, σ(r), 누락률, 블라인드 존과 무반사 때의 반환값(5000 또는 99999)을 적합한다.
3. **입사각:** 50 cm 벽을 0–60°로 5° 간격으로 측정해 최대 가시 각도로 `incidence_sigma_deg`와 `echo_threshold`를 맞춘다.
4. **원뿔:** 지름 2 cm 막대를 좌우·상하로 옮기며 가시 경계를 재서 반각과 방향 이득을 맞춘다.
5. **공동 운반 막대:** 바닥 막대, M2 높이(0.095), 권장 높이(0.110·0.120)로 든 막대의 실제 판독을 기록해 4절·8절 표와 대조한다. 권장 높이에서 아랫면 모서리 회절 에코가 없는지 특히 확인한다.
6. **두 로봇 간섭:** 0.4–1.5 m에서 마주 보게 두고 두 센서를 동시에 켠다. 짧은 판독 비율을 재서 `crosstalk` 기본값을 다시 판단한다.
7. 결과는 `experiments/`의 새 ID에 raw sha256과 함께 남긴다. 보정한 spec은 새 `sensor_model_id`로 등록한다.

## 7. 공동 운반 v6(#246) 연결 제안 (이번 범위 아님, 모두 보정 전 가설)

- **PF 측정 모델:** relook 시점마다 `range_log_likelihood(reading, expected_range(map, particle_pose), status=...)`를 입자 가중치에 곱한다. 판독당 |LLR|은 2 nats 이하이고, 가시 경계에서 연속적이다. 자기 팔·짐·상대 로봇이 원뿔 안에 있을 수 있는 구간(파지·하강·정렬·운반)에서는 쓰지 않는다.
- **과신 검출(guard):** 보고 σ가 작은데 `longer_than_map` 또는 `no_echo_where_map_predicts`가 N회 연속 나오면 relook을 요청한다. 이것은 "강한 증거"가 아니라 **보정 전 가설**이다. 경면·다중 반사와 지도 오차로도 같은 판정이 나올 수 있다. dev14(오차 82 cm, σ 1.9 cm)를 잡을 수 있는지는 재생으로 검증하지 않았다.
- **운반:** 8절의 운반 높이 `recommended_carry_tool_z()`(0.110 m)를 쓴다. `CarrySonarMonitor('above_cone')`는 **후보**다. 마주 보는 두 센서의 간섭이 burst로 나오면 k-of-n 투표로도 걸러지지 않는다. 표류 위상 모델(`FACING_PAIR_SPEC`)에서 10분 운반당 오정지는 20개 seed 중앙값 34회(최대 50회)였다. 6절 6단계(간섭 측정)와 교대 측정 같은 대책 전에는 켜지 않는다.
- **정렬:** 이전 판의 "파지 자세에서 상대 로봇까지의 거리로 단안 깊이를 교차 확인"은 **철회한다.** 실물과 수정된 SIM 모두 파지·하강 자세에서 자기 집게를 본다(4절). 팔을 grip z 0.06 m 이상에 두는 접근 구간에서만 상대 거리 관측으로 쓸 수 있다. 이때도 전역 σ는 초기화하지 않는다.
- **충돌 여유:** 접근 중 `status == ok and range_m < 여유`, 또는 `blind`이면 전진을 막는다. 자기 집게가 원뿔 안에 있는 자세에서는 이 규칙을 쓰지 않는다(항상 막힘). 막은 기록은 자기 판독 이력으로만 남긴다.

## 8. 운반 높이: 짐을 초음파 원뿔 위로 들 수 있는가 (2026-09-28, #221·#246)

사용자 요청은 "짐을 초음파 센서 위로 들어 운반 중에도 앞을 보게" 하는 것이다. 운동학만으로 분석했다(물리 step·시뮬레이션 실행 0회). 코드는 `harness/ultrasonic_carry.py`와 `scripts/analyze_ultrasonic_carry_height.py`, 결과는 [`carry_height_analysis.json`](../experiments/2026-09-28-ultrasonic-range/carry_height_analysis.json)이다.

**기준 기하(M2·v6 facing-pair 운반):**
- 각 로봇은 막대 끝에서 0.03 m 안쪽을 grasp 반경 0.155 m에서 쥔다. 두 로봇은 서로 마주 본다.
- 송수신면에서 가까운 끝면까지 0.041 m, 먼 끝까지 0.641 m다.
- lift는 M2 hover(명령 grip z 0.095 m)다. 기록된 막대 몸체 z는 0.0602–0.061 m(문 통과 31회)이므로 짐 처짐은 약 10 mm다.
- 여유: 짐 처짐 10 mm, 막대 pitch 2°(M2 p95 1.76°, 최대 6.16°는 민감도로만), 높이 5 mm.

**두 기준과 필요한 명령 grip z (장착 54 mm, 송수신면 84 mm):**

| 기준 | 반각 15° | 반각 7.5°(전체각 해석) |
|---|---|---|
| `whole_beam`: 막대 전체가 원뿔 밖 | 0.286 m | 0.198 m |
| `near_face`: 가까운 끝면만 원뿔 밖, 아랫면은 grazing | **0.105 m** | 0.099 m |

**팔 도달(보정된 IK `harness.visual_arm`, 반경 0.155 m):**
- 보정 탐색 범위(pitch −90…−40°)에서 최대 0.161 m(pitch −40°)다. pitch를 0°까지 풀어도 0.239 m다.
- 따라서 `whole_beam`은 **불가능하다.** 15°에서는 기하적으로 닿지 않는다. 7.5°에서도 pitch −20° 부근이 필요해 보정 범위 밖이고, 막대가 턱 안에서 52° 돌아야 한다.
- 반대로 짐을 원뿔 **아래**로 두는 것도 불가능하다. 원뿔 아래 가장자리가 먼 끝에서 바닥 아래로 내려간다.

**권장: `near_face`, 명령 grip z = `recommended_carry_tool_z()` = 0.110 m** (5 mm 단위로 올림; 막대 아랫면은 약 76 mm로, 원뿔 가장자리 65 mm보다 11 mm 위)

kinematics 장면(`zone_wide_door_tags_v2` + `long_beam`, 두 로봇 IK 자세, `mj_forward`만 사용, 자기 팔·짐 포함)에서 확인한 값:

| 명령 grip z | IK pitch (grasp −72.1°에서 변화) | 첫 에코 | 막대–팔 최소 거리(집게 제외) | 전방 tip 가속도 | 손목 카메라 막대 IoU(grasp 대비, pinhole 대리값) |
|---|---|---|---|---|---|
| 0.095 (M2) | −64.1° (+8.0°) | **자기 막대 끝면 0.042 m** | 32 mm(wrist) | 4.1 m/s² | 0.86 |
| **0.110** | −60.0° (+12.1°) | **상대 로봇 0.688 m** | 31 mm | 4.0 m/s² | 0.83 |
| 0.120 | −56.0° (+16.0°) | 상대 로봇 0.688 m | 30 mm | 3.9 m/s² | 0.80 |

- **SIM 관절 범위:** 세 높이 모두 안에 든다. MuJoCo grip site가 FK와 1 mm 안에서 일치한다.
- **자기 팔:** ray가 자기 팔을 포함하는데도 0.110 m에서 첫 에코는 상대 로봇이다. 자기 집게·팔은 원뿔 축에서 33.8° 이상 떨어져 있다.
- **정적 전복:** 로봇 1.10 kg에 짐 몫 0.15 kg을 grip점에 둔다. 앞바퀴 축 기준 복원/전복 모멘트 비는 3.9다. 전방 tip 가속도는 약 4 m/s², 측방은 약 7.9 m/s²다. 운반 속도 0.06 m/s의 가감속보다 한 자릿수 이상 크다. 높이를 15 mm 올린 효과(무게중심 +2.6 mm)는 무시할 만하다.
- **상대 로봇 간섭:** 막대와 양쪽 wrist 사이 최소 거리는 31 mm다(M2 32 mm).
- **grip 변화:** grip 점(반경 0.155 m)은 같다. 다만 tool pitch가 grasp 대비 12.1° 바뀐다(M2는 8.0°). 두 로봇 모두 막대가 턱 축 둘레로 돈다. M2에서 8°는 통과했지만 12°의 마찰 토크 여유는 **미검증**이다(물리 확인 필요).
- **손목 카메라:** 카메라 높이는 0.13 → 0.145 m, 광축은 −56.6 → −52.6°로 바뀐다. 쥔 막대의 이미지 대리 IoU는 grasp 대비 0.86 → 0.83이다. grasp→lift co-motion 검사(`HOLD_MIN_IOU` 0.45, M2 실측 0.735/0.835)의 여유가 약간 줄 수 있다. 렌더링 검증은 하지 않았다.
- **장착 민감도:** 장착 높이 44–64 mm, 소자 중심 전방 68–88 mm에서 `near_face` 필요 높이는 0.092–0.118 m다(보정 IK 도달 범위 안). 로봇을 다시 모델링하면 새 `UltrasonicSpec`으로 `recommended_carry_tool_z(spec)`를 다시 계산한다.

**운반 중 초음파 규칙(`CarrySonarMonitor`, 자기 판독만 사용, 보정 전 후보; 7절의 간섭 결과 참고):**
- lift 직후 자기 판독 5개의 중앙값을 기준값으로 잡는다. 권장 높이에서 이 값은 상대 로봇까지의 거리(≈0.69 m)다.
- **기준값 검증(검토 P2-3):** `above_cone`은 기준값이 12 cm보다 멀고, 예상 대형 거리 ± 0.1 m 안이며, 5개 판독이 서로 맞을 때만 받는다. 아니면 `calibration_failed`(정지)다. 자기 짐 끝면을 기준값으로 잡아 미끄러짐을 영구히 놓치는 것을 막는다. 보정이 1 s 안에 끝나지 않아도 `calibration_failed`다.
- **판정:** 최근 5개 중 3개가 정지 상태면 가장 잦은 정지 상태를 낸다. 3개가 정상이면 정상이다. 둘 다 아니면 `relook`(정지하고 다시 본다)이다. `state(now)`에서 최신 판독이 0.2 s보다 오래되면 `stale`(정지)이다. `blind` 판독은 `blind_zone`(정지)이다.
- 매 판독은 다음 가운데 하나로 판정한다.
  - `formation_ok`: 기준값 ± max(2 cm, 4σ). 대형이 유지되고 막대가 원뿔 밖에 있다.
  - `load_in_cone`: 12 cm 이내의 판독. 막대가 처지거나 미끄러져 원뿔로 내려왔다. 멈추고 파지를 확인한다.
  - `intrusion`: 기준값보다 짧지만 12 cm보다 먼 판독. 로봇 사이, 막대 아래로 물체가 들어왔다. 멈춘다.
  - `beyond_baseline`: 기준값보다 길거나 무반사. 상대가 멀어졌다(대형 붕괴, 상대 쪽 짐 이탈). 멈춘다.
- **한계:** facing-pair 운반에서는 두 로봇의 전면 센서가 서로를 향한다. 그래서 운반 중 "전방 거리"는 사실상 상대 로봇까지의 거리와 두 로봇 사이 공간이다. 대형 바깥의 진행 방향 장애물은 이 센서로 볼 수 없다.
- **짐 확인만 원할 때(대안, 현재 M2 높이 0.095):** `CarrySonarMonitor('load_in_cone')`를 쓴다. 기준값은 자기 짐 끝면(≈0.042 m, 12 cm 이내여야 함)이다. 판독이 이보다 길게 뛰면 `load_lost`(이쪽 끝 이탈)다. **상대 쪽 끝이 떨어지는 것은 못 본다**(가까운 끝면 거리가 같다). 이 모드에서는 전방을 볼 수 없다. 한 센서가 첫 에코만 주므로 두 용도를 동시에 쓸 수 없다.
- 이 판정은 초음파 판독만의 결론이다. 손목 카메라 hold 검사를 대체하지 않고 보조한다. 실제 운반 성공은 따로 검증한다.

## 9. 혼자 운반하는 작은 짐 (2026-09-28, #221)

표의 값은 v2(현재 SIM) 기하다. v3 값은 11절에 있다. 질문: 한 로봇이 혼자 드는 작은 짐(막대 아님)을 원뿔 밖으로 들어, 운반 중에도 앞을 볼 수 있는가. 방법은 8절과 같다(운동학·ray cast만, 물리 step 0회). 결과는 [`solo_carry_height_analysis.json`](../experiments/2026-09-28-ultrasonic-range/solo_carry_height_analysis.json)이다. 로봇은 벽을 송수신면 기준 0.491 m 앞에 두고 선다(정적 지도 예상값; SIM은 벽 태그가 2 mm 튀어나와 0.489 m). 짐은 grip site에 강체로 둔다. 기울기는 수평과 강체(자세 pitch 변화만큼) 두 경우이고, 처짐은 10 mm로 둔다. ray는 자기 팔·집게와 짐을 **포함**하고 차체 쪽만 건너뛴다(실물 센서와 같은 조건, 검토 P1 수정 뒤 다시 계산).

**최종 연구 카탈로그의 solo 종류(`configs/zone_study_scenarios`, `sim/zone_cargo.py`):**
- box: 34×40×32 mm, 30 g, 바닥에서 24 mm 높이를 잡는다. cyan·green·red 색상 복제품이다.
- can: Ø38×50 mm, 80 g, 24 mm 높이를 잡는다.
- tile: 60×40×12 mm, 25 g, 7 mm 높이를 잡는다.

**자세별 결과(반각 15°, 여유: 처짐 10 mm, 흔들림 ±5°, 높이 5 mm):**

| 자세 | 명령 grip z / pitch | box·can 원뿔 여유 | tile 원뿔 여유 | 첫 에코(자기 팔 포함) | 손목 카메라 높이 / 광축 / 보이는 바닥 |
|---|---|---|---|---|---|
| 기존 lift hover 0.095 | 0.095 / −64.1° | −22 / −23 mm | −11 mm | box 0.054 m, can 0.053 m = **자기 짐**. tile은 원뿔 안이지만 에코가 문턱 아래라 벽 0.489 m | 0.13 m / −56.6° / 0.18–0.32 m |
| 직선 lift 최소값 | box·can 0.120 / −56.0°, tile 0.110 / −60.0° | +2.6 / +1.9 mm | +4.5 mm | 벽 0.489 m(지도 0.491과 일치) | 0.155 m / −48.5° / 0.20–0.43 m |
| **기존 운반 자세 `carry_p30`** | 0.180 / −30.1° | **+67 / +66 mm** | **+79 mm** | 벽 0.489 m(지도 일치) | 0.208 m / −22.6° / 0.32–3.80 m |

- 직선 lift 최소값은 `recommended_solo_tool_z(kind)`다. 반각 15°에서 box·can 0.120 m, tile 0.110 m이고, 7.5°에서는 0.110 / 0.110 / 0.095 m다. 여유를 이미 포함한 값이지만 남는 여유는 2–5 mm로 얇다.
- `carry_p30`(`harness/owncam_drive.py`의 `CARRY_POSTURE`)는 `zone_own_executor`가 짐을 든 채 주행할 때 이미 쓰는 자세다. 강체 기울기 42°(box·can)·36°(tile)와 물리 기록의 32°([`2026-09-25-zone-owncam-skill`](../experiments/2026-09-25-zone-owncam-skill/)) 모두 여유 64–79 mm로 원뿔 밖이다.
- **자기 집게·손목·팔:** 위 세 자세에서는 자기 geom이 원뿔 ray에 하나도 맞지 않았다(box·can·tile 전부). 다만 **파지 자세에서는 자기 집게가 첫 에코다**(box·can 0.043 m, tile 0.031 m). 짐을 쥔 채 grip z 0.06–0.095 m에서는 box·can·tile이 자기 짐을 본다(0.04–0.058 m).
- **전복:** 짐이 가벼워(25–80 g) `carry_p30`에서도 전방 복원/전복 모멘트 비는 9.4(can)–30(tile)이고 전방 tip 가속도는 5.1 m/s² 이상이다.
- **grip·IK:** 직선 lift는 grasp 대비 pitch가 +16.1°(box·can)·+6.0°(tile) 바뀐다. `carry_p30`는 +42°/+36°이며, 기존 실행기가 이미 이 변화를 겪는다(기록 32°). SIM 관절 범위는 모두 안이다.
- **내려놓기:** 기존 순서는 운반 자세 → hover 0.095(grasp pitch) → 16단계 직선 하강이다. `carry_p30`에서 hover로 가는 servo 이동(최대 554 pulse) 동안 짐의 가장 낮은 점은 68 mm(box·can)·87 mm(tile)로, 바닥에 닿지 않는다. 하강 IK는 모든 단계에서 가능하다. 직선 lift 0.120을 쓰면 기존 lift 경로(0.095에서 끝남)를 늘려야 한다.

**권장:** 혼자 운반할 때는 **기존 `carry_p30`를 그대로 쓴다.** 모든 solo 종류가 원뿔 밖이고 카메라도 멀리 본다. 코드 변경은 필요 없다. 직선 lift 최소값(0.120/0.120/0.110)은 자세를 바꿔야 할 때의 하한으로만 둔다.

**전진 규칙(`solo_forward_state`, 자기 판독 + 정적 지도):**
- `carry_p30`에서 짐 앞끝은 송수신면보다 0.085–0.086 m 앞에 있다. 정지 거리는 `solo_stop_distance` = 앞끝 + 0.19 m/s × 0.30 s + 0.02 m(`BASE_MARGIN_M`) ≈ 0.163 m다. 감속 거리는 반응 1 s로 ≈ 0.30 m다.
- 판정은 다음과 같다. 지도 예상 거리와의 일치(`range_consistency`)도 같이 돌려준다. 지도보다 짧으면 지도에 없는 물체다.
  - `stop_near_field`: 앞끝 + 2 cm 이내(짐 처짐 또는 접촉 거리), 또는 `blind`
  - `stop` / `slow` / `clear`: 유효 판독의 거리로 정한다
  - `no_reading`: 0.2 s 넘게 판독이 없거나 `sensor_absent`
  - `hold`: 무반사인데 1 s 안에 감속 거리 안쪽의 유효 판독이 있었다. 예: 벽 앞에서 멈춘 뒤 살짝 돌아 벽이 경면이 된 경우
  - `no_echo`: 그 밖의 무반사. **`clear`가 아니다.** 기존 guard 아래 저속으로만 진행한다.
- **무반사나 blind를 `clear`로 보지 않는다**(검토 P2-2 수정). 이 판정은 기존 sweep·충돌 guard를 **대체하지 않고 더하는** 입력이다.

## 10. 공동 운반: ㄱ자 측면 파지로 앞 보기 (2026-09-28, #221·#246)

질문: 두 로봇이 진행 방향을 보고, 팔을 옆으로 돌려 막대를 쥐면 초음파로 앞을 볼 수 있는가. 이 자세는 **9/9 사용자 요청으로 이미 있었다.** `scripts/probe_dual_grasp_sync.py --side-grasp`(commit `9bb41317`), [`2026-09-09-side-grasp`](../experiments/2026-09-09-side-grasp/README.md)과 [`2026-09-09-loaded-transport`](../experiments/2026-09-09-loaded-transport/README.md)에서 몸체 +X, 팔 yaw PWM 2500/500(±90°)으로 비보조 파지·유지 2/2와 50 cm 전진 운반 2/2를 했다. 9/25 zone 카탈로그(commit `87eaac86`, `long_beam` grasp `approach_yaw` 0/π)가 몸체를 막대 축 방향으로 바꿨고, 이 전환의 사용자 결정 기록은 찾지 못했다. M2·v5·v6은 이것을 이어받았다. 막대의 grasp 점은 두 방식이 같고 몸체 방향과 팔 yaw만 다르다. 옛 warehouse teacher(`sim/multi_masterpi_production.py` `_warehouse_inward_formation`)도 같은 방식이다.

v3 값은 11절에 있다. 이번 분석은 9/9 방식을 v6 장면(`zone_wide_door_tags_v2` + `long_beam`, lift 0.110 m)에 다시 놓은 것이다. 결과는 [`side_grasp_pair_analysis.json`](../experiments/2026-09-28-ultrasonic-range/side_grasp_pair_analysis.json)이고, 운동학만 썼다.

| 구간 | 몸체 방향 | 팔 yaw | 초음파 용도 |
|---|---|---|---|
| 횡 이동(막대에 수직, M2 0.30 m) | 두 로봇 모두 진행 방향 | ∓90°(PWM 500/2500) | **전방 장애물 거리 vs 정적 지도** + 기존 충돌 여유. 두 로봇이 각자 본다. 시험 위치에서 2.540/2.541 m로 지도와 일치하고, 자기 팔·짐·상대는 원뿔 밖이다 |
| 축 이동·문 통과(막대 방향, M2 0.60 m) | 그대로(옆으로 strafe) | ∓90° | 앞은 못 본다. 옆 벽·문기둥까지의 거리를 지도와 비교해 **문 중앙 정렬**을 확인한다. 문 안에서 0.166 m로 지도와 일치한다 |
| (비교) 현재 M2·v6 | 서로 마주 봄 | 0° | 서로를 본다(0.688 m). 대형 감시(8절, 후보)만 가능하다 |

- **축 이동에서 앞을 볼 수 있는가:** 앞 로봇이 진행 방향을 보려면 팔 yaw 180°가 필요하다. 관절 한계는 ±100.3°(±1.75 rad)라 최선도 진행 방향에서 79.7° 벗어난다. 원뿔 반각 15°로는 앞을 못 본다. 뒤 로봇은 팔 0°로 앞을 볼 수 있지만 그 앞에는 막대와 상대가 있다. 축 이동의 진행 방향 장애물은 **어느 방식이든 초음파로 못 본다.** top RGB와 정적 지도로 판단한다.
- **문 폭:** 막대에 수직인 대형 폭은 측면 파지 0.1885 m, 현재 방식 0.162 m다(로봇·막대 geom AABB). 0.5 m 문의 한쪽 여유는 0.156 m / 0.169 m, 1.0 m 문은 0.406 m / 0.419 m다. 막대 방향 길이는 1.01–1.04 m라 옆으로는 1.0 m 문도 못 지난다. 문은 두 방식 모두 축 방향으로 지난다.
- **yaw servo 토크:** yaw 축이 수직이므로 짐 무게의 정적 토크는 0이다. 팔은 두 방식 모두 막대 축을 따라 놓이므로 yaw 부하는 **방식과 무관하다.** 막대에 수직인 힘 F가 0.155 m 팔에 τ = 0.155·F를 만든다(횡 이동, 대형 어긋남). SIM `forcerange`는 1.2 N·m(grip 7.7 N)다. 실물은 LD-1501MG 계열 17 kg·cm ≈ 1.67 N·m(grip 10.8 N)로 **가정**한다. 전압 조건과 yaw 관절 servo 모델은 미확인이다. 반쪽 막대를 1 m/s²로 가속하는 데는 0.023 N·m(SIM 한계의 2%)면 되지만, 한 로봇이 마찰 0.5로 밀면 0.84 N·m(SIM 70%, 실물 가정 50%)다. 위험은 대형 어긋남이다. 측면 방식은 막대에 수직인 이동을 전진으로 하므로 strafe보다 어긋남이 작을 것으로 보지만 측정하지 않았다.
- **전복:** 짐 몫 0.15 kg이 측면 바퀴선 밖 0.155 m에 걸린다. 측방 복원/전복 모멘트 비는 4.6이고 tip 가속도는 4.65 m/s²다. 현재 방식의 전방 3.9 / 3.98 m/s²보다 조금 낫다(track 0.131 m > wheelbase 0.12 m).
- **손목 카메라:** 카메라는 팔과 함께 돌므로 막대 이미지는 현재 방식과 같다(대리 IoU 1.0). 다만 ±90°는 보정된 pan 범위(PWM 1300–1700) 밖이다. 이 자세의 카메라 외부 파라미터와 `SERVO_DEVIATION[6]` 64 pulse(≈5.8°)는 실물에서 확인하지 않았다.
- **방향 전환:** SIM에서 팔 yaw 축은 차체 원점과 일치한다(0, 0). 제자리 회전과 팔 yaw 역회전을 같이 하면 grip 점이 운동학적으로 고정된다. 실물 mecanum 회전 중심의 흔들림은 측정하지 않았다. 짐을 든 채 두 로봇이 함께 방향을 바꾸는 것은 물리 검증이 없다. 9/9처럼 **처음부터 측면으로 접근해 파지**하는 편이 안전하다.
- **odometry:** `CARRY_ODOM_SCALE`(`scripts/study_owncam_pair_beam.py`)은 현재 방식에서 axial 0.772(전진), lateral 0.697(strafe)로 보정되었다. 측면 방식에서는 0.60 m 축 이동과 문 통과가 strafe가 되어 나쁜 쪽 보정을 쓴다. 새 보정이 필요하고 값은 미확인이다. 초음파 문기둥 거리는 로봇 전방 축(문을 가로지르는 방향)만 잡으므로 strafe 방향(진행 방향) 오차는 보정하지 못한다.
- **9/9 근거의 범위:** 다른 물체(5×45×4 cm, 0.196 kg), 정답 좌표 바퀴 제어, 50 cm 전진뿐이었다. `long_beam`(0.60 m, 0.300 kg), strafe, 자기 카메라 실행, 문 통과는 검증되지 않았다.

**권장:** 측면 파지를 v6의 **비교 조건 후보**로 둔다. 횡 이동에서는 전방 초음파를 쓰고, 축 이동·문 통과에서는 옆 거리로 중앙 정렬을 확인한다. 채택 전에 확인할 것은 세 가지다. (1) 물리로 `long_beam` 측면 파지·유지와 strafe 운반, (2) 측면 방식의 odometry 보정, (3) ±90° pan에서의 실물 카메라 보정이다. 현재 방식(8절)은 그대로 두고 비교한다.

## 11. 리모델 v3(초안 PR #249) 기하에서 다시 계산 (2026-09-28)

PR #249는 도면 비율로 로봇을 다시 모델링한다(측정값 아님). 이 절은 8–10절의 해석식을 v2와 v3 값으로 다시 계산한 것이다. 결과는 [`geometry_v2_v3_analysis.json`](../experiments/2026-09-28-ultrasonic-range/geometry_v2_v3_analysis.json)이고, 코드는 `RobotGeometry`, `GEOMETRY_V2`, `GEOMETRY_V3`, `arm_links()`다. 이 브랜치에는 v3 MuJoCo 모델이 없다. 그래서 v3는 **해석식만** 썼다. 자기 팔 검사는 v2 SIM 팔 사슬로 자세를 잡은 뒤 v3 팔 축 오프셋만큼 옮겨 계산했다.

| 항목 | v2(현재 SIM) | v3(#249 도면 배치) |
|---|---|---|
| 초음파 위치(전방/높이) | 78 / 54 mm(송수신면 84 mm) | site 88.0 / 61.7 mm, 수평, 팔 base 상자 앞면(차체 고정). 송수신면은 v2처럼 +6 mm로 **가정**(94 mm) |
| 팔 yaw 축(차체 중심 기준) | 0 | 전방 48.2 mm |
| 송수신면 → 막대 가까운 끝면 | 0.041 m | 0.079 m |
| 공동 운반 `near_face` 권장 grip z | 0.110 m (pitch +12.1°) | **0.125 m** (pitch −54.0°, grasp 대비 +18.1°) |
| 막대 전체(`whole_beam`) 필요 z | 0.286 / 0.198 m | 0.304 / 0.211 m (여전히 도달 불가) |
| solo 직선 lift 최소(15°) box·can / tile | 0.120 / 0.110 m | **0.140 / 0.125 m** |
| solo 직선 lift 최소(7.5°) | 0.110 / 0.095 m | 0.120 / 0.105 m |
| solo `carry_p30` 원뿔 여유 | 64–76 mm, 모두 밖 | **47–58 mm, 모두 밖** |
| `carry_p30` 짐 앞끝(송수신면 기준) / 정지 거리 | 0.085–0.086 / 0.162–0.163 m | 0.123–0.124 / 0.200–0.201 m |
| 자기 팔·집게의 원뿔 축 최소각(15° 미만이면 원뿔 안; 운반 자세) | 33.8°(공동) / 60.6°(`carry_p30`) / 측면 파지 0개 | 26.8° / 46.9° / 측면 파지 0개 |
| 측면 파지: 막대 앞면과 송수신면 사이 | 64 mm 뒤 | 26 mm 뒤 |
| 제자리 90° 회전 시 grip 이동(몸체 중심 회전 + 팔 역회전) | 0 | **68 mm** |
| 현재 방식 대형 길이 변화 | 0 | +96 mm |

- **결론은 v3에서도 같다.** 공동 운반은 `near_face`만 가능하고 높이만 0.125 m로 오른다. solo는 `carry_p30`로 원뿔 밖이다. 측면 파지에서는 자기 팔과 막대가 센서 면 뒤에 있다.
- **v3에서 새로 생기는 비용:**
  - 공동 운반 lift의 pitch 변화가 +18°로 커진다(M2 물리 확인은 +8°까지다). 턱 안에서 막대가 도는 마찰 여유는 확인하지 않았다.
  - 팔 축이 앞으로 나와 있다. 짐을 든 채 방향을 바꾸려면 몸체가 **팔 축을 중심으로** 돌아야 grip이 고정된다. mecanum은 회전과 병진을 합쳐 원리상 할 수 있지만 구현·검증은 없다.
  - 측면 파지에서는 로봇 중심이 막대 축에서 48 mm 뒤로 물러난다. 대형 폭은 그대로다.
- **링크 길이 민감도(도면 값, #249에서 물리 미적용):** 위팔 57.7 mm(SDK 65), 집게 끝 94 mm(SDK 100)이다. controller IK를 그 길이로 계산하면 다음과 같다(반경 0.155 m).

  | 링크 | 최대 grip z(보정 pitch −90…−40°) | pitch ≤ 0 최대 | 최소 grip z | grasp pitch |
  |---|---|---|---|---|
  | SDK 65 / 100 | 0.161 m | 0.239 m | 0.001 m | −72.1° |
  | 위팔 57.7 | 0.151 m | 0.231 m | 0.005 m | −67.0° |
  | 집게 94 | 0.161 m | 0.236 m | 0.008 m | −68.9° |
  | 둘 다 | 0.151 m | 0.228 m | 0.013 m | −64.0° |

  권장 높이(공동 0.125, solo 0.140)는 모두 도달 범위 안이다. `carry_p30` FK는 z 0.173–0.183 m로 바뀌지만 원뿔 여유는 40–52 mm로 유지된다. 다만 집게가 94 mm이면 tile의 7 mm grip 높이가 보정 pitch 범위의 최소 grip z(8–13 mm)보다 낮아 **IK가 풀리지 않는다.** 링크를 바꾸면 tile 파지 자세를 다시 보정해야 한다.

## 12. 하네스 입력 연결 (2026-09-29, opt-in, 배선만)

사용자 요청("전면 초음파를 일단 입력으로 쓸 수 있게 하네스 자체를 구성")에 따라 위 센서를 구역 연구 실행기의 **선택 입력**으로 연결했다. 성공 근거가 아니라 배선이다. 어떤 제어기도 값을 쓰지 않는다(사용은 별도 결정).

**켜는 법.** prereg(실행 구성)에 `"sensors": {"ultrasonic_front": "on_v1"}`를 적고 `scripts/run_zone_study_sensors.py`로 실행한다. 키가 없거나 `off`이면 이 스크립트는 원래 실행기(`run_zone_study_integration.py`)를 **그대로** 호출한다. 알 수 없는 키·값은 기본값으로 넘기지 않고 거부한다. 원래 실행기를 직접 쓰면 `sensors` 키는 무시되므로 켠 실행은 반드시 어댑터로 돌린다(열린 질문 1).

| 항목 | 내용 |
|---|---|
| 프로필 `on_v1` | `DEFAULT_SPEC`(`masterpi_ultrasonic_v2`), 두 로봇 간섭(crosstalk) 끔 |
| 번들 기록 | `bundle.sensors`: 프로필, 센서 모델 id, spec 해시, source 라벨, 판독 필드, `baseline_comparable: false`. 번들 해시가 꺼진 실행과 달라진다. 센서 소스 파일(`harness/ultrasonic_*`, `sim/ultrasonic_*`, `range_provider`, 어댑터)이 소스 고정 목록에 들어간다 |
| 로봇 관측 | 로봇마다 **자기** 판독만: `{t, range_m, valid, status}`(`ok`/`blind`/`no_echo`/`sensor_absent`). 무엇에 맞았는지는 없다. `range_m`은 유효할 때만 값이 있다 |
| 위치 | 물리 실행기(호스트)의 로봇별 자기 센서 경로. 물리 step 뒤 매 호출마다 자기 60 ms 시계로 읽는다. 통신 조건(대화 채널, 쌍 상태 채널)보다 아래이며 조건 이름을 받지 않는다. 다른 로봇의 판독은 전달 경로가 없다 |
| 잡음 seed | `sensor_seed(trial_seed, robot_id)`. 조건과 호출 횟수에 무관하므로 네 조건이 같은 SIM 시각에 같은 잡음을 받는다 |
| 물리 영향 | 없음. ray cast는 읽기 전용이고 `mj_step`·`mj_forward`를 부르지 않는다. 직전 step이 남긴 상태를 읽는다(자세는 최대 한 timestep 이전). 렌더 프로필·카메라와 무관하다(충돌 geom group 기준 ray) |
| 정답 누출 | 없음. 어댑터는 `measure`(판독)만 쓰고 `measure_diagnostic`(맞은 geom, 원인)은 쓰지 않는다. 테스트가 제어기·스킬 모듈이 값을 참조하지 않는지, 판독 표면에 대상 이름이 없는지 확인한다 |
| 실행 기록 | `robots/<rid>/inputs/range.jsonl`(헤더: 모델·spec 해시·잡음 seed, 행: `t, range_m, valid, status`)와 `sensors.json`. 둘 다 manifest가 해시한다. 모델 요청 텍스트와 이미지 해시 보존과 같은 방식이다 |
| 제어기 쪽 통로 | 각 로봇 실행기에 `range_provider`(자기 provider)가 붙는다. `harness.ultrasonic_input.range_report(executor, now)`가 최신 보고를 돌려준다. 아무 스킬도 읽지 않는다 |

**끔일 때 동일성.** 어댑터는 고정 소스(`zone_own_executor.py`, `zone_own_team_host.py`, `run_zone_study_integration.py`)를 고치지 않고 감싼다. 그래서 꺼진 실행은 소스·번들·해시·출력이 바이트 단위로 같다(`pair_dev_DRAFT`의 `--bundle` 출력이 main과 동일함을 확인). v6d DRAFT 같은 소스 고정 기록도 깨지지 않는다.

**본 실행기에 합칠 때(조정자가 번들 버전을 등록하는 시점).** 어댑터의 세 가지를 실행기 안으로 옮긴다: `bundle.sensors` 블록, `_physics_until` 뒤 `rig.tick`, `write_outputs` 전에 rig 닫기. 그 밖에는 바꿀 것이 없다.

**열린 질문.**
1. 원래 실행기로 켠 prereg를 돌리면 조용히 꺼진 채 실행된다. 본 실행기에 합칠 때 `sensors`를 아는 실행기만 받게(모르면 거부) 해야 한다.
2. 두 로봇 간섭(crosstalk)은 `on_v1`에서 끈다. 마주 보는 운반 평가는 켜야 하므로(2절) `FACING_PAIR_SPEC`용 프로필이 따로 필요하다.
3. 판독 상태 어휘는 이 문서의 `ok/blind/no_echo/sensor_absent`다. 요청서의 `valid/out_of_range/no_echo`는 `valid=ok`, `out_of_range=blind`(너무 가까움)와 `no_echo`(4 m 안에 없음)로 대응한다.
4. 다른 실행기(카메라 짝 운반, 파이프라인 프로브)에는 아직 연결하지 않았다. 리그(`sim/ultrasonic_input.py`)는 MuJoCo 세계와 로봇 목록만 받으므로 재사용할 수 있다.
5. v3 장면에서는 센서 site(`r*__v3_ultrasonic_site`)를 자동으로 쓰며 정지 상태 판독 생성까지 확인했다. v3 장면의 물리 실행 중 판독은 확인하지 않았다.
6. 이 배선은 한 번도 완전한 실행(로봇·카메라·모델 포함)으로 돌려 보지 않았다(다른 에이전트가 물리 잠금 사용 중). 실행기 통합 검증은 단위 시험과 `--bundle` 출력 수준이다.

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
- 혼자 운반 자세: `harness/owncam_drive.py` `CARRY_POSTURE`, 내려놓기 경로 `harness/wrist_zone_skill_v2.py`, 기울기 기록 [`experiments/2026-09-25-zone-owncam-skill`](../experiments/2026-09-25-zone-owncam-skill/)
- 9/9 측면 파지 기록: [`2026-09-09-side-grasp`](../experiments/2026-09-09-side-grasp/README.md), [`2026-09-09-loaded-transport`](../experiments/2026-09-09-loaded-transport/README.md), `scripts/probe_dual_grasp_sync.py --side-grasp`(commit `9bb41317`); 막대 축 방향 전환 commit `87eaac86`
- Hiwonder LD-1501MG(17 kg·cm 판매 목록, 전압 미확인): <https://www.gie.com.my/shop.php?action=robotics%2Fmotors%2FLD_1501MG>; LFD-01M(집게 servo, 6 V 1.8 kgf·cm): <https://www.hiwonder.com/products/lfd-01m>
- ROS REP 117(거리 측정의 −Inf/+Inf/NaN 구분): <https://ros.org/reps/rep-0117.html>
- Thrun, Burgard, Fox, *Probabilistic Robotics* (MIT Press, 2005), 6.3 beam model(hit/short/max/rand)
- hector_gazebo `gazebo_ros_sonar`(ray 최솟값, min/max clamp): <https://github.com/tu-darmstadt-ros-pkg/hector_gazebo/blob/melodic-devel/hector_gazebo_plugins/src/gazebo_ros_sonar.cpp>
- PR #248 적대적 검토 기록: `outputs/review-248-20260928.md`(로컬 기본 체크아웃)
