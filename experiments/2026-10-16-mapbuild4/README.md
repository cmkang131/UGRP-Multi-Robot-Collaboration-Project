# mapbuild4 — 횡펄스 원인 분리 (진행 중)

ownership-ack: 필수 `agent-ownership.md` 확인. `codex/mapbuild1` / PR #556,
gcp5 단독, CPU 비교·분석도 gcp5. gcp2 시작0. 지도·새 진단 모듈만 소유한다.
접촉 프로필은 warpfit 소유, 장면·공용 backend 수정0. 모든 새 본 실행은 MJWarp,
C 적분은 같은 모델 비교 전용이며 결과를 합산하지 않는다. 관문4 WITHHELD.

수정 전 분포는 [prechange-distribution.json](prechange-distribution.json)에
mapbuild3의 서로 다른 분모를 구분하여 고정했다. 새 진단은 같은 비관통 시작의
좌/우 × 60/100/200/400ms × FOLDED/HIGH = 16조건, 전진·회전100ms 4조건이다.
각각 정지1 SIM초 뒤35출력 펄스, 총2 SIM초. 시계 기반 행동 상한은 없다.

## 구동·예측기 조사

`sim/masterpi_dynamics_v2.py`는 원래 reduced body-wrench 모델이며 롤러가 시각 전용이다.
현재 장면의 `build_model → masterpi_drive_friction_v7.transform_xml → v6 → v2 → v1`은
이 경로를 대체한다. 모터는 네 wheel hinge에 토크만 가하고, 45° 수동 roller hinge와
FUJI convex mesh의 접촉이 횡력·전진력을 만든다. 차체에 별도 횡 wrench를 더하지 않는다.
v7의 명령 relay는 |u|>.325에서 켜지고 u−sign(u)/12, T0=.1176798Nm가 적용된다.
35출력에서 .03138128Nm/휠, 정지 시 능동토크0·DC 속도 감쇠는 남는다.
실물 motor/floor/질량분포는 여전히 미보정이다. 이번에 이 상수들을 바꾸지 않는다.

v122는 s1042/43/45의 과거 CPU S2 주행20Hz 궤적에서 후향적으로 맞춘 응답곡선이다.
`harness/data/s2_motion_v7_pulse_cal_v122.json`의 입력 경로와 SHA를 보존한다.
무하중 왼쪽35/60ms는17개, 오른쪽21개 학습; HIGH/loaded fine은 직접 학습0개로
무하중 fine에 coarse65/650ms 비율을 곱한 미확증 전이다. 100/200/400ms lateral35
프로필은 없다. loaded 분류는 집게 명령이지 실제 하중·자세 일반화의 증거가 아니다.
과거 freeze·CPU·이전 장면의 응답을 현재 MJWarp/FOLDED 고정 시작의 보정값으로
간주하지 않는다. mapbuild3 원본의17.040mm/0.0902mm/5.1587°도 원격에서 재확인한다.

## 참고 자료 (2026-10-16 열람)

- [Menagerie Robot Soccer Kit 원본 MJCF](https://github.com/google-deepmind/mujoco_menagerie/blob/main/robot_soccer_kit/robot_soccer_kit.xml):
  free base, 3개 구동휠 velocity actuator, 여러 passive wheel parts, noslip1. 3륜 omni이며
  MasterPi 메카넘의 수치 복사 근거가 아니다. [설명](https://github.com/google-deepmind/mujoco_menagerie/blob/main/robot_soccer_kit/README.md).
- [MuJoCo contact mixing 공식 문서](https://mujoco.readthedocs.io/en/stable/modeling.html#contact-parameters):
  geom 우선순위가 마찰·condim·solref/solimp를 선택한다. geom friction3개는 접선등방이며
  이방성은 명시 contact pair에서만 지원한다. 무작정 한 방향 마찰을 낮추지 않는다.
- [MJWarp 공식 README](https://github.com/google-deepmind/mujoco_warp/blob/main/README.md),
  [MJX 공식 문서](https://mujoco.readthedocs.io/en/stable/mjx.html): 배치 상태·모델로 적분하고
  batch renderer를 제공한다. 최신 main은 noslip을 지원하지만 discrete integrator에는 제한이
  있다. 설치 버전·실제 opt를 별도 기록한다. 검토한 공식 예제에서 메카넘 전용 보정법은 찾지 못했다.
- [Matsinos 2012, §§2.4–3](https://arxiv.org/html/1211.2323v1): 롤러 방향별 힘과 저항,
  휠별 정상력·무게중심·동적 마찰을 구분한다. 논문의 다른 로봇 마찰계수는 이식하지 않는다.
- [현재 roller 형상의 원본](https://github.com/DaiGuard/fuji_mecanum/tree/646431a5e107448e0e2bdeeba4575db9aa3665ff),
  `sim/assets/masterpi_drive_friction_v2/source.json`: 205→65mm 비례축소,15→9롤러,
  50g 휠 질량 분배. 일반적인 힘 모델 조사와 현재 실제 활성 경로를 구분한다.

모델 호출·키 전송·Drive·Mac GUI0. 아직 실행 완료/수정 효과/지도 확장을 주장하지 않는다.

## 1차 분리 측정 (새 코호트, 이전 결과와 합산0)

gcp5 C3.16과 MJWarp는 같은 scene XML SHA `6c4c907c…`·NoSlip10·20조건 각2SIM초,
세계당8,000step을 완료했다(cap_end). 전체 수치는 [pulse-matrix.json](pulse-matrix.json).
MJWarp20세계720.16초, CPU20조건 순차176.28초는 이번 진단의 소요 시간이며,
첫30SIM초 속도 관문이나 성능 우위의 근거가 아니다.

| 같은 깨끗한 시작 | MJWarp FOLDED 좌/우(mm) | CPU FOLDED 좌/우(mm) | MJWarp HIGH 좌/우(mm) |
|---|---:|---:|---:|
| 60ms | +7.036 / −7.201 | +7.696 / −7.538 | +7.512 / −7.399 |
| 100ms | +11.201 / −13.203 | +11.274 / −13.233 | +11.071 / −13.140 |
| 200ms | +25.867 / −25.787 | +25.857 / −25.791 | +25.883 / −26.211 |
| 400ms | +47.485 / −48.267 | +47.696 / −48.228 | +48.395 / −48.844 |

표는 횡 성분이며 전진 드리프트·yaw는 원본 표에 별도 기록했다. FOLDED 좌100ms의
MJWarp 전진 드리프트6.083mm 대 CPU0.694mm도 포함한다. 고정 시작 각1회로 일반화·실물 자격은 없다.
v122의 정확히 일치하는 펄스 없음24/40, 과거CPU fit12/40, HIGH fine 미확증 전이4/40이다.
분모는 새20조건×2backend이며 추적 성공률·물리 성공률이 아니다.

mapbuild3처럼 전진100ms를 먼저 주는2차 진단은 좌우60/400ms×2자세, 각3SIM초다.
CPU는 FOLDED60ms 순변위0.0084/0.0789mm 대400ms44.33/44.16mm를 재현했다.
MJWarp 쪽은 진행 중이다. 접촉 profile은 바꾸지 않고 warpfit에 ops-alert로 점검을 요청했다.

준비한 기본off 후보는 `mapbuild4_frontier_v1`, `mapbuild4_pulse_prediction_v1`이다.
기존 LK·관측 floor 근거 grid·frontier/A*를 재사용하고, 기존 heading-first 방식으로
전진/회전100ms만 발행한다. 횡60ms를76배 하는 보정은 넣지 않는다.
새 예측은 깨끗한 시작의 MJWarp 전진/회전0.3초 응답을 고정한 탐색용 prior이며, 시각unknown을
실제 이동0으로 보지 않고 unknown frame은 지도에 넣지 않는다. 3명령 연속 시각 미회복은 중단한다.
[보정값](motion-calibration.json)의0.3초 뒤 잔여 이동은 전진0.792mm, 회전0.132mm/0.012°다.
자기 RGB로 덮어쓰는 기존 방식을 쓰며 예측 일반화·독립 검증은 미완료다. 기존 production 경로 변경0.
후보 장시간 물리는 아직 실행하지 않았다. 새 bundle ID/workflow 버전 추가0.
