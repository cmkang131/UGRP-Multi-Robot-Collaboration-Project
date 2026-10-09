# egomap55 — 목표 지향 RouteMap P0 (물리 0)

## 사용자 목표 변경과 범위

2026-10-09 사용자 결정에 따라 [설계서](../../docs/selfmap-gtr-research-20261009.md) §3.2/3.4/3.5/3.8/3.9를 따른다. 강제 `unknown_start_reset`은 주 흐름에서 제거할 예정이며 별도 강건성 조건으로만 보존한다. P0와 확인된 버그 3건만 이번 구현 범위다. 연속 추적→자기 상자/B 확인 후 접근→실제 도달 확인→시작↔상자↔B 경로 저장이 P1의 방향이다. **P1 구현/물리 승인으로 해석하지 않는다.** 벽 검출기는 eg34 동결, 설계 §1.3 방식 재시도0, 단서 제거0, 모델 호출0, 새 물리0. GT는 봉인된 예측을 평가하거나 P0-4 합성 센서만 생성하며 추정 함수 입력에는 넣지 않는다.

## 실행 전 고정한 P0 판정

| 항목 | 자료/분모 | 고정 판정 |
|---|---|---|
| P0-1 | 설계 §3.7 경기장 표 | door_geometry/two_doors/corridor와 s1–s8 대응은 설계 그대로 |
| P0-2 | ownmaps2a의 동일 S2 7기록, 기준 PF+two_doors_final_v3 정적 지도 | stdXY≤.05m 최초 선언에서 평가 XY≤.25m·yaw≤15°를 정상으로 센다. 정상 n≤4/7이면 같은 경기장 재구축 필수, n≥6/7이면 불일치 주원인 아님,5/7은 미결정. 진단이며 합격률 아님. 기존 기준7/7 병기 |
| P0-3 | eg49 seed49001–49006 모두, 중단2개 포함 | 경기장 밖≥.5m 점유0,40cm 벽 커버 감소≤5%p,영역P 비감소,경로튜브 내GT unknown0,시작free6/6. 전체 벽 분모와관측거리≤2.5m 분모를 함께. 분모 축소를 개선으로 세지 않음 |
| P0-4 | s1045–1047의 평가 카메라/GT 차체 로그 + 정적 지도→기존 초음파 모델 합성 판독 | 정면평벽/거리≥1m/입사±20°인 자기 관측만 추정에 사용. 자세별 pitch 오프셋 복원 절대오차≤.27°. 프레임수/유효수/제외사유·시퀀스별 오차 보고. 합성 판독은 실측 센서 증거가 아님 |
| P0-5 | eg52 재방문3698시도(복구41은별도) | 기존 CSM 수락 불변+자기 색전이 순서 일치 게이트. 수락 상대XY오차 감소/거짓수락0. 거짓은 기존국소화 허용(.25m,15°) 밖. 수락0이면 정합 성능 성공 아님. 분모/결측·단서부족 모두 보고 |

새 기능은 별도 `route_hygiene=observed_support_v1`, `pitch_bias=ultrasonic_v1`, `place_gate=color_sequence_v1`, 기본off. off는 입력을 그대로 반환해 기존출력bytes유지. 합성 판독/평가기를 제어경로에 연결하지 않는다. 히스토리나 GT로 관문값 재적합0. 프로그램 오류 수정과 결과 튜닝을 구분한다.

지도 위생: 기존 inverse sensor hit/miss·clamping 및 거리 오차 전파 재사용, **끝점 점유는≤2.5m**,더 먼 반환은2.5m까지 free-ray만(OctoMap maxrange 규칙). 같은 cell은 서로 다른 기존 teach keyframe 2개 이상 지지가 있어야 occupied. 기존 d² 거리 표준편차(픽셀→바닥 Jacobian)의 제곱이 분산임을 구분한다. 시작/지나간 footprint는 free, 관측범위 밖은 unknown. 평가 경계로 자르거나 GT 벽에 snap하지 않는다. 이 규칙의 남은 outlier도 그대로 보고한다.

색전이는 기존 색 검출 hue 어휘만 사용한다. 연속 중복색은 압축하고 각 노드 이전의 최근3개 서로 이어진 색 단어를 같은 진행 방향 또는 명시적 역방향으로 비교한다. 단일색/3개 미만은 정보부족으로 거부한다. 이3개는 설계의 시퀀스 구현 선택이며 논문 상수라고 주장하지 않는다. CSM 거부를 색만으로 수락하지 않는다. 기본 CSM 캐시/검색창/점수는 불변.

## P1-b 사전등록 — 실행 승인 대기

같은 경기장 `zone_wide_door_geometry_v3`, 연속 추적·강제loss0. T1 55001–55003: (3.25,.75,π), T2 55004/55005: (−.898,−2.25,0),55006/55007:(−.898,−.85,0),55008/55009:(−.898,.55,0). 설계의x=−.898을 사용(기존 spawn 원값−.8982의 표기반올림 차이. yaw0는 v96표준spawn 원값). 초기자세는 설정에만, 제어에GT전달0. `seed-audit.json`은main+열린11PR에서미사용확인. 각1회,대체/반복0,ENOSPC=HOST_ERROR,새물리실행은감독확인후.

| §3.9 관문 그대로 | 값 |
|---|---|
| T1 B도착 / T2 B도착 |3/3 / ≥5/6 |
| 거짓선언 / 벽·로봇접촉episode 합계 |0 / ≤1(9회) |
| 시작→B,상자경유각구간 SIM시간 |≤270초(늘리지않음) |
| 지도경로/평가GT최단경로 |≤2.0 |
| ±1m경로튜브 안벽커버≤.15m / 점유P / 벽RMSE |≥.70 / ≥.70 / ≤.20m |
| 경기장밖≥.5m outlier / 단서장부 |0 / 9회모두≥1개 |

T1쉬운조건과T2문통과를합산해성공률을부풀리지않는다. 전체분모/영역분모·미실행·제외사유를함께보고. 기존전체지도품질 P≥.90/R≥.70/RMSE≤.15m는별도표유지. P0-4 통과시 P1-a 정차보정≤60SIM초를 제안할 수 있으나 이번 실행0. P1-b는 등록만,실행 승인 대기다.

## 표준 출처/재사용

- VT&R3 Apache-2.0 [원본](https://github.com/utiasASRL/vtr3), 정확한 keyframe/temporal/정합실패zero-command 줄은 [eg53](../2026-10-09-teach-capture/README.md). 기존 CSM/cache를 재사용하며 거리만으로 지름길을 만들지 않는다.
- [OctoMap OccupancyOcTreeBase](https://octomap.github.io/octomap/doc/classoctomap_1_1OccupancyOcTreeBase.html): maxrange ray/free와hit/miss/clamping. 평면 0.1m 기존격자를 유지한다. Thrun 2005 ch9 역센서 및 기존 `wall_confidence.confidence`의 거리 Jacobian을 재사용한다.
- 색시퀀스는 설계§3.4/3.8의 단서게이트로 새로 구현하며 SeqSLAM 완전이식이라 부르지 않는다. OpenSLAM SeqSLAM 페이지는이번조회실패,확인안된수치인용0.
- `ownmap_s2.GridField`의 20,000,000 fine cell 예산(원본148–163행), 현재로컬samePF/카메라/모델을읽기전용재사용. 다른worktree쓰기0.

## 버그/검증

선언terminal화(선언후6프레임),할당전raster예산,복원negative log-odds의snapshot ray provenance유지. RGB바닥직접관측을조작하지않는다. 기존`public_navigation_raytrace`도free ray를floor_frames provenance로썼으므로같은의미로복원한다. 변경2시험파일14통과;새옵션은추가시험후별도기록. CI대기0/PR405 DRAFT 유지.

## 결과

사전등록 시 P0-2~5 미실행. 결과 후 문턱 수정0. raw `outputs/goal-route-p0-v1/`.

### 17:2x 감독 추가 사전등록 — 누적 가상 스캔

`scan_accumulation=keyframe_submap_v1`,기본off. eg49 6개+eg34 seed32002를각각비교한다. 기존RBPF의정합/재표본/삽입시점관문은그대로,그사이에gmapping_motion_gate로스킵된자기벽접점을명령DR상대변환으로버퍼에모은다. 다음기존삽입시점의자기추정pose로옮겨regional submap에한묶음삽입한다. 불일치거부프레임/미정착/4m밖은기존처럼제외하고마지막미flush버퍼는미삽입으로보고. 이는고정기록의지도갱신진단으로,변경지도가후속RBPF정합에미치는폐루프효과는이번결과가증명하지않는다. 단순매프레임삽입eg44와구분한다. 보고:기존삽입keyframe수/실제반영관측frame수/버퍼미반영수,벽커버·점유P·RMSE. 기존P0-3위생과누적단독을분리하고결과후문턱수정0. Cartographer의local submap내연속range data누적구조를따르며GMapping이카메라스캔버퍼를원래지원한다고주장하지않는다.

P0-2는최초내부수렴선언때정지(수렴안하면기록끝),선택규칙에GT사용0. 기준same-map의최초선언까지원본7필드byte동일을확인하고다른지도조건을실행한다. P0-4는카메라명령/보정+자기접점+합성거리만입력,원뿔plane echo역산과pitch±5°root solve(결과전에고정). 실제카메라pitch는오차채점에만사용한다.

누적 삽입은 Cartographer ProbabilityGrid처럼 한 셀당 한 키프레임 묶음에서 strongest hit/miss 한 번(hit 우선)만 반영한다. 각 관측의 ray 원점은 개별 DR로 deskew하며 기존 키프레임의 frozen insertion_weights는 그대로 쓴다. 추가 관측은 기존 confidence와 저장된 자기 covariance를 사용한다. 옵션 모듈 시험6개 통과(off객체/bytes 동일,시퀀스,범위/2노드/swept-free,누적중복 방지,pitch 양·음 부호).

P0-2 초기 다른지도 constructor는 원본 S2의 door_1 작업경로 admission 때문에 프레임0에서 거부됐다. 추정 관문 실패가 아니다. 사용하지 않는 task route만 원본 정적 지도에서 가져오고, PF/likelihood/landmark의 입력은 다른 지도 전체로 유지했다. control/drive는 원본 어댑터의 금지 함수 그대로다. 두 지도 실제 constructor 시험2개 통과. 경기장 ID alias는 보정 admission만 위한 것으로 실제 map_id/hash를 예측 receipt에 따로 남긴다.

P0 지도평가의 영역은 평가 GT 경로±1m이며 전체 P/R도 항상 병기한다. 2.5m/4m 분모는 기존 in_view의 실제 카메라 FOV·벽 가림 기반 potential visibility(물체 가림 미모델링). pitch는 자기 서보 명령 자세별로 유효 range-plane root의 인과적 중앙값을 유지하며, 각 자세의 최종값과 같은 표본의 평가 실제 편향 중앙값을 비교한다(±.27° 불변). 단일프레임·인과적 오차분포도 함께 보고한다. 초음파 합성 난수seed=55000+S2기록번호,기존노이즈/드롭아웃/양자화 그대로.
