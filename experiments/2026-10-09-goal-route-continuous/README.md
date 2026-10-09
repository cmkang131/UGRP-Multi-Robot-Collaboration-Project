# egomap56 — 연속 추적·목표 지향 RouteMap, P1

2026-10-09 사용자/감독 승인. egomap55 P0는 이미 보고한 그대로: 경기장 대조7/7, 위생0/6·누적스캔RMSE .520→.780·색게이트 미달은 **미채택/off**. 벽 검출기 egomap34 동결. 강제 unknown_start_reset은 사용하지 않는다. 과거 egomap54는 사용자 중단으로 결과 분모 제외이며, egomap53 HOST_ERROR 2건을 성공으로 바꾸지 않는다.

## 실행 전 사전등록

[설계 §3.2–3.9](../../docs/selfmap-gtr-research-20261009.md), [egomap55 등록](../2026-10-09-goal-route-p0/README.md)의 값 그대로다. 경기장 zone_wide_door_geometry_v3; T1 55001–55003 시작(3.25,.75,π), T2 55004/5(−.898,−2.25,0),55006/7(−.898,−.85,0),55008/9(−.898,.55,0). 각1회, 총9회. 시작은 물리 설정용, 제어는 자기 원점0으로 시작하며 GT는 평가만. T1/T2 별도 표, 실패/HOST_ERROR/ENOSPC 모두 분모, 임의 제외·재시도·사후튜닝0.

| 기준 | 고정 값 |
|---|---|
| B 도착 선언 + 평가 GT 중심 B 내부 | T1 3/3, T2 ≥5/6 |
| 거짓 선언 / 벽·로봇 접촉 episode | 0 / 9회 합계≤1 |
| 시작→상자/B, 다음 목표, 귀환 | 구간별 최대270 SIM초; 확인만으로 시간 초기화 금지 |
| 지도 경로 / GT 최단(평가만) | ≤2.0 |
| 실제 경로±1m 튜브 벽 커버(15cm) / 점유P / RMSE | ≥.70 / ≥.70 / ≤.20m |
| 경기장 밖≥.5m 점유 / 단서 장부 | 0 / 모든 실행≥1개 |

목표를 먼저 확인하면 그 목표로 바로 접근하고, 상자·B 둘 다 접근 후 자기 RGB 재확인 때 탐색 종료. 목표 중심은 자기 관측만. B 도착은 eg43의 위치≤.20m·연속5프레임을 유지하고 **현재 RGB의 하단1/3에서 기존 v3 최소화소수 이상**을 추가 요구한다(설계3.4의 근접 색 확인, 새 검출기 적합 아님). 상자는 기존 zone own cyan cuboid 검출,3프레임·.10m 일관성(기존v3 기준 재사용),접근거리≤.20m와 현재 RGB 재관측. 상자 파지/운반 성공으로 보고하지 않는다. 둘 다 도달하면 저장된 시간 엣지만 역으로 따라 시작으로 귀환,거리≤.20m·5프레임을 자기 선언하고 GT 오차는 별도 평가한다. 귀환에 새 shortcut/색 gate는 없다.

각 구간270초를 넘으면 그 실행은 예산 실패. 최악 세 구간810 SIM초(상자/B의 순서는 첫 확인 순),기존 HOST상한60분/회. B에 도달해도 상자를 못 찾으면 B도착과 임무미완료를 구분한다. 녹화·추적·지도갱신은 귀환까지 지속한다. 보수적 σ/충돌 가드 정지는 dev_light 'would_stop' 기록, 실제 물리 오류/접촉 경계는 기존 실행기 유지. 실행 순서: S3 재시험 완료 증거 → 잠금null → agent_lock 획득 → 9회 순차. CI 대기0,물리 중 설정 변경0.

| 옵션 | 기본 | 이번9회 |
|---|---|---|
| goal_route | off | continuous_v1 |
| pitch_calibration | off | **off**: P1-a 별도≤60SIM초 옵션은 구현하되 이번 행렬과 혼합 안 함 |
| heading_mode | off(기존 흐름) | path_tangent_v1 on(새 흐름 기본): 회전 후 전진 |
| route_hygiene / scan_accumulation / place_gate | off | off/off/off |
| wall detector/contact rule | off(eg34 원형) | 그대로 |
| servo_stiffness / texture / motion | 기존 | real_v1/tape_v1/s2_pulse_v122_rotL_v1 |
| RBPF/graph | 기존 |100입자·selective·삽입수정·Manhattan·±20°·switchable,eg48 결과동일 캐시/광선 가속 |

정차 pitch는 own 초음파(명시on)와 현재 명령자세·자기 벽 관측만,정지≤60초 인과적 중앙값;P0-4 root 그대로. 실제 미검증이므로 이번P1b는off. heading 공통브랜치 origin/codex/s2-heading b60acdca는 현재 S2 전용 default-off만 push됨; 공통 변경이 준비되면 실행 전 병합,그 전에는 기존 ego TraversalReturn의10° 회전/전진 함수를 재사용한다(중복 알고리즘 작성0). 최종 적용SHA는 동결 기록에 남긴다.

## 표준·출처와 제약

- [Furgale & Barfoot 2010 저자 원문 설명](https://asrl.utias.utoronto.ca/~ptf/JFR_VTnR/): teach의 영상·겹치는 지역지도·위상연결,repeat의 지역위치맞춤. 이번에도 본문 전문 미확인; 출처의32km 결과는 우리 증거가 아니다.
- [VT&R3 Tactic, 고정 bdb40d8a](https://github.com/utiasASRL/vtr3/blob/bdb40d8ad22f02094507cc0924af8622e1ed796c/main/src/vtr_tactic/src/tactic.cpp#L985-L1008): 직전vertex temporal edge. 카메라 YAML의 .30m/3° keyframe, 후보승격/실패처리는 [eg53 출처/Apache2 원문보존](../2026-10-09-teach-capture/README.md)과 `own_teach_capture.py`를 재사용. 단안 wrist/저텍스처 때문에 stereo 대신 기존 own-submap CSM, 회복 엣지는 uncertain 표기. 관측이 부족한 정합은 보정하지 않는다.
- [Nav2 RPP 원본](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/src/regulated_pure_pursuit_controller.cpp): rotate-to-heading 후 전진. 기존 ego forward-only pulse/10° 국소 방향 추종을 재사용하며 새 이득 적합 없음. 공통 S2 전용 마지막 east정렬은 이식하지 않는다.
- 기존 σXY≥.15m 또는σyaw≥5°(active information trigger)에 도달했을 때만 저장 노드 가까운5개 CSM으로 재정합을 시도한다. 강제 loss/전체경기장 uniformPF0. 정합 거부 시 통계와 would_stop을 기록하고 dev_light에서는 연속DR 유지. 성공시 모든RBPF입자에 같은SE2 보정을 적용하며 상관된 지역지도 측정으로 공분산을 인위축소하지 않는다. 일반 귀환에서도 노드 정합은 같은 기준,실패는 새360°를 요구하지 않는다.

## 진행 기록

- 코드 작성 전: supervisor 파일 확인, 다른 S2 heading 실행 잠금 확인. 물리0. 현재 source cc522cae.
- 중간/최종 결과는 아래에 추가하며 문턱은 바꾸지 않는다.

### 구현 전/후 오프라인 연결 확인

기존49002 RGB150프레임+원래 발행 명령으로 실제 factory를 재생했다(새 물리0,반사실 경로 성능 점수 아님). 탐색→B확인→접근 전환이 기록되었고 최종오류0. 최초 긴 재생에서 hold 명령에 forward 필드를 요구하던 변환 오류1건을 발견해 hold=zero twist 계약으로 수정했다. 해당 실제 factory 회귀도 추가했다.

P1 표준 single-door 지도는 기존 two-door FinalV3Scene registry와 다르므로 등록된 MasterPiV3ZoneScene을 사용하도록 새 실행기에서만 의존성을 바인딩했다. 카메라/물리/스폰 훅은 기존 함수 그대로 재사용한다. T1/T2 네 시작 배치 정적 구성 시험(물리0) 통과. 기본 off identity,기존 heading100입력의 float bytes 동일,선언 후6번째 프레임,목표관측≠도달,지속명령,실패시에만 재정합,60초 보정상한을 검사했다.

실행 전 정적 배치 검증에서 seed55006의 r3 지정행에 r2가 이미 배정됨을 발견했다. S2 원형은 seed별 로봇ID를3개시작행에 순열배정한다. 지정한 r3 시작행의 기존로봇과 r3의 기존행을 **교환**하는 설정 규칙으로 모든9개 시작배치를 미리 검증한다. 시작/예산/목표값 변경0,로봇 삭제·freeze0,접촉 결과를 본 뒤 제외0. T1 동쪽시작은 기존명시좌표 그대로다.

### 구현 동결(물리 전)

바뀐2시험파일 **25 passed**, `offline-smoke.json`의150RGB프레임 오류0(탐색→접근 포함). 기본off기존객체/출력 그대로,공통으로추출한기존heading100입력float bytes동일. `freeze.json`에 실행의존파일SHA를 고정했다. P1-a `StationaryPitch`는 자기센서입력·명령정착·자세별인과적중앙값·60초상한·hold출력과 기존프런트엔드보정 API를 제공한다. 실제60초보정/효과검증은미실행이며 이번P1-b는off다.

S3의 새 지시(s3next.txt)를 읽어 **공통heading push 후 S3 재시험**이 아직 선행대기임을 확인했다. 현재 물리0/9,잠금은S2 heading이사용중. 순서승인완료사실이기록된 queue-admission.json 없이는 실행기가물리를 시작하지 않는다.

### 실행 전 설계 누락 보완: 자기 초음파 여유

물리0/9인 상태에서 §3.2의 "오도메트리+전면초음파 여유" 연결을 보완한다. **sensors.ultrasonic_front=on_v1**,기존OwnUltrasonicRig/OwnRangeInput을재사용해r3의시각·거리·상태만5Hz로받고(무엇에맞았는지없음),기존Nav2 1.2초충돌시간과CAD전면offset/footprint로would-stop을기록한다. P1-a pitch보정은계속off,초음파로지도/pose/목표를맞추지않는다. sensors-off과별도조건표시. 일반adapter의dev_light기본false에서는정지,이번9회실행기만명시dev_light=true. 결과를본수정이아닌실행전설계연결완료다.

관측채널 보완 후 바뀐2시험 **26 passed**. range 입력은 정확히 {t,range_m,valid,status} 4필드,off일때센서접근0. 명시 dev_light와 일반모드의정지계약을구분했다. 물리는계속0/9,사후문턱변경0.

### 18:25 KST 선행 의존성 확인

구현 `5714ea66`은 원격과 동일하고 PR #405는 DRAFT다. #419의 최신 `fddc2f67`은 S2 비교 결과 기록이며 공통 heading 기본 on 변경은 아직 없다. S3 #416의 `7f2675ac`도 해당 변경 대기를 명시한다. 잠금은 null이지만 사용자가 지정한 **S3 재시험 다음** 순서를 건너뛰지 않는다. 따라서 P1-b는 **시작 0/등록 9, 결과 미측정**이며 실패율·성공률을 계산하지 않는다. 준비된 유한 실행기는 완료 증거를 담은 `queue-admission.json` 없이는 시작하지 않는다. 공통 변경 병합·바뀐 시험 검증 후 S3 종료 증거를 확인해야 다음 단계로 진행할 수 있다. CI 대기나 관문 미달로 중단한 것이 아니다.


## egomap57 — main 병합·공통 heading host 연결 (실행 전)

사용자 승인 main `6813f8a1`(#419/#420)을 merge한다(rebase0). 공통 `own_map_heading.command` → `zone_solo_cyan_path_heading.select_waypoint`를 새 host에 연결하며 v145의 .06rad/.10m/측정 pulse·coast 규칙을 그대로 쓴다. 자기 pose/계획만 전달하고 S2 정적 지도/PF factory를 자기 제어에 넣지 않는다. rotL 보정 자료는 eg56 그대로. 기존10° ego heading은 역사적 host=off 경로에만 보존,새 주행 알고리즘/이득0. 공통 명령은 본 적 있는 시간순 경로를 따르며 귀환 지름길0. graph 최단화/재방문 shortcut0.

번들 `egomap57-goal-route-<seed>-v1`에 heading_mode/host/shared v145 출처와 실제 result에 동일 적용값을 기록한다. #420의 기본 relay-cache-v1 실제 적용 여부·모듈해시는 v7-speedups/runtime-bundle/result에 기록한다. 원 결과동일성 근거는 main의 #420 기록을 참조하며 이번에 속도 시험/물리 추가0. 캐시 해제 환경변수는 이번 실행에서 사용하지 않는다.

55001–55009·T1/T2·270초 구간예산·판정은 eg56 등록 그대로. P1-a off,실패P0옵션off,추적 연속,새 문턱0. **S3 v146 스모크 종료 기록 + 잠금 반환** 이후9회 순차(dev_light). 매 회차 직후 아래에 B/귀환/실패와 각 구간 자기 경로 길이·실제 이동거리(평가만)·SIM초·270초 예산실패를 추가한다. 미관측/미도달/HOST_ERROR도9분모,제외/재시도0.

실행 전 통합시험 첫회32 PASS/6 FAIL: egomap9의 ColumnModel 확장이 VIS3 원본 해시를 바꾼 과거 충돌이었다. VIS3 원본을 main 바이트로 복원하고 카메라 인자를 `wall_column_calibration`의 인스턴스 어댑터로 분리했다(검사 완화0). 보존49002 RGB의 벽 검출출력106354문자 byte동일,원본 VIS3 전체해시 검사통과. 바닥/벽 검출 설정변경0.

S3 v146 `3daa830f`는45.25SIM초 `DEV_NOT_DELIVERED`로 종료했고 `lock.json.status_after=null`을 확인했다. 이는 선행 실행 완료 증거이며 자기 지도 성공 근거가 아니다. 출력과해시를 `outputs/goal-route-continuous-v1/queue-admission.json`에 기록했다.

최종 관련3파일 **38 PASS**,원형off/명령선택/기록/구간보고 검사 통과. 394 실행의존 파일을 freeze로 고정하며 회차별 README·평가결과 추가만 허용한다. 여유29.91GiB 확인,시뮬 동시0·nice0·등록9회만. CI대기0.

### 회차별 결과 (호출9/9, HOST_ERROR9, 유효 물리0)

|seed/조건|B 도착·거짓 선언|귀환|종료 상태/원인|구간 길이·SIM초·예산실패|
|---|---|---|---|---|
|55001/T1|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55002/T1|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55003/T1|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55004/T2|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55005/T2|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55006/T2|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55007/T2|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55008/T2|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|
|55009/T2|선언0/평가불가|평가불가|HOST_ERROR/tape 기하 불일치|미진입: 거리·SIM초·270초 실패 모두 N/A|


### egomap57 결과·한계 (설정 변경/재실행0)

소스 `1afd7e24ac106bb262d858173906dfb36d34871b`, 등록9개를 순차 호출했다. **9/9 HOST_ERROR**, 제외0, RGB0·실제 물리 프레임0·모델호출0이다. B 도착수는 등록 분모로 T1 **0/3**, T2 **0/6**지만 전부 초기화 실패이므로 주행/귀환 성능의 성공률로 해석할 수 없다. 종료위치·σ·P/R·덮음·경로길이·구간SIM·270초 예산 판정은 모두 **표본0/측정불가**다. 접촉0/거짓선언0 성공근거도 없다. 영상은 입력 프레임0이므로 만들 수 없으며 이전 영상으로 대체하지 않는다. [`cohort-audit.json`](results/cohort-audit.json)에9원본manifest해시와 적용 heading을 보존했다.

원인은 `sim/goal_route_continuous.py`가 P1의 단일 문 지도에 egomap16 고정 tape 배치표를 연결한 host 구성 오류다. `wall_texture.py:132–133`의 정상 기하 일치 검사가 막았다. 양쪽6개벽 중 divider_1이 다르다: 테이프표 중심 y=−1.1625m/길이1.925m,현행P1 중심 y=−1.675m/길이2.950m(차이1.025m). 원래 더 짧은 칸막이 아래로 남았던 공간을 단일 문 지도에서는 벽이 채운다. 벽/검출/지도 문턱 문제나 heading 물리 실패로 분류하지 않는다. 기존 사전 시험이 장면 **구성만** 확인하고 최종 XML+asset 변환을 확인하지 못했다.

운영상 한계도 기록한다: 유한 순차 실행기가 실패도 등록 분모에 남기며9개를 계속 호출했고, 동일 초기화 원인2회에서 다음 슬롯을 차단하는 분기가 없었다.9건이 수초 안에 종료하여 배치 종료 후 확인했다. 반복 원인 중단 규칙을 자동 실행기에 충분히 반영하지 못한 점이며 추가재시도/물리/튜닝은 하지 않는다. 세션 종료·공유 잠금null 확인.

다음 권고는 **주행 튜닝 없이** 기존 tape 생성기(`generate_assets`)로 P1 기하에 맞는 별도 고정 배치표를 사전생성하고, MuJoCo 시작 전 최종 XML/asset 일치 검사를 등록하는 것이다. 옛 배치표·벽 기하를 변경하거나 검사를 무시하지 않는다. 동일HOST_ERROR 반복 차단도 다음 실행 전 필요하다. 이번 결과 이후에는 어느 수정도 물리 실행하지 않았다.
