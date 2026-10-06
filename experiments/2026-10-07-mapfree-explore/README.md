# 자기 지도 B·C·E: 2D 오프라인 탐색 (2026-10-07)

## 1. 범위와 동결

설계 `/Users/changmin/projects/ugrp/outputs/mapfree-design-20261006/DESIGN.md` §4/5/7/9를 따른다.
B 색 검출 v3는 부모 `91e60811`에서 동결했다. precision 100%, recall 79.41% **기준 미달**,
녹화 거짓 확인 0이다. 시간 누적이 미달을 보완한다는 것은 아직 가설이다. 자기 지도 구 녹화 튜닝도 중단한다.
이 작업은 MuJoCo/렌더/물리/모델 호출 없이 **NumPy 2D 센서·운동 모사**만 한다. 임무·실물 성공과 구분한다.
`claude/mapfree-goal-floor` 위 `claude/mapfree-explore`; 부모 #408과 새 PR 모두 DRAFT, 병합하지 않는다.

## 2. 구현 전 사전 등록 (이 절의 커밋 뒤 구현)

### 코호트와 변경 금지

- 현행 `configs/zone_study_scenarios_v4/s1..s8*.json`의 8개 배치. 벽 지도는 3종을 공유한다.
  해당 map JSON의 벽/문, setup의 물체 footprint를 환경만 읽는다. s2의 45 s 통로 막힘과 s5의
  30 s 물체 이동도 환경에서만 적용한다. 다중 로봇 hold/파지/낙하 사건은 이번 빈손 단독 탐색 범위 밖이다.
- 고정 시작 `(x,y,yaw)`: A=(-.65,-2.8,0), B=(-.65,.95,0), C=(1.65,-2.8,π/2), D=(1.65,.95,π).
  기하 충돌인 시작은 HOST_SETUP_ERROR로 남기며 다른 시작으로 바꾸거나 분모에서 빼지 않는다.
- 개발: s1–s8 × A/C × seed1701 =16쌍. 확인: s1–s8 × B/D × seed2701/2702 =32쌍.
  각 쌍은 **static_map / own_frontier** 두 조건. 개발 결과 후 설정·소스 해시를 커밋하여 고정한 뒤 확인을 연다.
  확인 후 재튜닝 금지. 이미 본 녹화는 센서 모형의 개발 근거이며 새 실제 녹화 확증으로 부르지 않는다.
- 에피소드 예산: modeled time 600 s, 300 관측/행동, 이동 40 m 중 먼저 도달. 충돌 시 종료;
  evaluator가 충돌/정답 B 신호로 경로를 고쳐 주지 않는다. 첫 확인 후 종료. 실패도 분모에 남긴다.
- 새 옵션은 각각 `exploration=own_frontier_v1`, `door_detection=own_gap_v1`,
  `partial_planning=own_astar_v1`, 기본 `off`. 전부 off는 기존 출력 객체/직렬화 바이트 동일.
  B v3/기존 지도 보정 코드·설정은 수정하지 않는다. D* Lite와 LLM·지도 공유는 이번에 넣지 않는다.

### 센서·위치 모델의 출처와 한계

- 카메라 v3 명령 FK와 실제 K/D (`harness/floor_goal.py`/`sim/masterpi_camera_profile.py`) 재사용.
  640×480, SEARCH 명령 자세; 유효 양의 깊이 바닥 광선, 4 m 컷, 첫 장애물 가림.
  초기 제자리 관측은 중첩 시야로 회전하며 시간/회전 명령 비용을 포함한다. 실제 RGB 렌더는 하지 않는다.
- 벽은 기존 `wall-bias-fix/options/{main,s912,s913}-D-step3-sag/columns.npz`의
  mask_on 검출 누락·행 정오·**부호 있는 거리 잔차**를 재표본한다. 가시 접점 분모/범위/필터와
  원본 sha256을 추출 파일에 남긴다. precision을 독립 FP 확률로 잘못 쓰거나 두 번 잡음을 넣지 않는다.
  개발 센서 자료는 main(s911), 확인 센서 자료는 s912/s913을 분리 사용한다. 모두 **구 카메라/구 구동**이다.
- B는 동결 v3 새 정적 자료의 TP/FN·투영 잔차와 v3 녹화 음성 FP를 쓴다. 개발/확인 원자료를 분리한다.
  면적≥256 px의 조건부 recall이며 범위/가림으로 보이지 않는 B를 확률만으로 출현시키지 않는다.
  확인 precision100%를 임의 환경의 FP확률0으로 치환하지 않는다. 녹화 14/527 거짓 component를 별도 모사한다.
  시간 확인은 ≥3회/≥2 s/병진≥.05 m/최초 중심≤.20 m/겹침≥.35/gap≤3 s의 동결 규칙을 따른다.
- 운동은 `V7CommandOdometry`의 명령 평균/과정 공분산을 재사용한다. 평균 M1 보정, 잡음은
  `e7b229b6:sim/masterpi_drive_friction_v7.py`의 구조 사전값이다. **실측 v7 분산이 아니다.**
  환경만 해당 잡음을 실제 이동에 표본하며 actor는 자기 명령으로 적분한다. GT pose 보정은 없다.
- 실제 RGB 바닥 free 검출기의 오류 통계는 아직 없다. 모사 센서는 가려지지 않은 바닥의 광선만
  별도 `floor_visible` 관측으로 내보내며 벽 미검출을 free로 만들지 않는다. 거리 오차는 벽의 측정 잔차로
  근사한다. 낮은 물체/바닥 segmentation의 일반화는 **미검증 모델 가정**으로 표시한다.
  자기 몸 밑 초기 footprint의 기하 support만 예외로 둔다(관측 free/coverage에는 합산하지 않음).

### 기준선·지표·성공 기준 (확인 전에 변경하지 않음)

기준선에는 기존 정적 지도·B 좌표만 허용한다. 양 조건의 운동/센서 모형, 명령 DR, footprint/예산은 같다.
static map에는 초기 지도 정렬을 알고 있다는 별도 정보 이점이 있다. 숨은 사건/실시간 GT pose는 제공하지 않는다.
기존 RGB/top-camera 현행 제어기를 실행한 결과가 아니라 **같은 2D 실행기의 정적 지도 정보 기준선**이다.

| 기준 | 사전 통과 조건 |
|---|---|
| 입력/회귀 경계 | off 골든 바이트 동일; actor GT/타 로봇 지도/MuJoCo/모델 접근 0 |
| B 확인 | 확인 32건 중 참 B 첫 확인 ≥80%, 거짓 확인 0 |
| 효율 | 두 조건 모두 참 확인한 쌍의 거리·modeled time 비율 중앙 각각 ≤2.0; 공통 성공 0이면 실패 |
| 탐색량 | 참 확인 또는 종료 시 직접 본 reachable free 면적 커버리지 중앙 ≥40% |
| 문·이동 안전 | 잘못된 문 통과 시도 0, 충돌 0; 실제 문 통과 시도 ≥1건(무시도 통과 금지) |

거리=환경 이동 궤적 XY 길이(m), 시간=명령·회전·정착 포함 modeled s, 미발견은 null + 검열 이유/예산을 기록한다.
coverage는 시작에서 도달 가능한 GT free 셀 중 **센서가 실제 보았던 셀**의 비율; actor의 허위 free와 별개다.
잘못된 문 시도는 발행 경로가 GT 통로 단면을 가로지르며 요청 footprint가 당시 GT 장애물과 겹친 사건이다.
가짜 gap 후보에서의 crossing도 별도 FP passage 시도로 센다. 문 후보/수락/거절 사유와 시도 수를 함께 남긴다.
각 배치/시작/seed를 표로 남기고 배치별 동일 가중 요약만 부가한다. 성공 사례만의 수치로 실패를 숨기지 않는다.
HOST_ERROR/ENOSPC는 실패로 보존한다. 시간 측정은 modeled time이며 CPU 속도 benchmark가 아니므로 잠금을 쓰지 않는다.

## 3. 표준 방법·출처와 적용 범위

- [Yamauchi 1997](https://www.robotfrontier.com/papers/cira97.pdf): free/unknown 경계의 연결 frontier.
  검색 초록 확인, 원문 재접속은 실패했다. [explore_lite 공개 코드](https://raw.githubusercontent.com/hrnr/m-explore/master/explore/src/frontier_search.cpp)
  `searchFrom`, `isNewFrontierCell`, `frontierCost`를 확인했다. 도달성·군집·거리/효용 원리를 독립 구현한다.
- [FUEL 2021 공개 코드](https://raw.githubusercontent.com/HKUST-Aerial-Robotics/FUEL/main/fuel_planner/active_perception/src/frontier_finder.cpp):
  frontier 군집, 관측점의 FOV/가림 검사를 참고한다. 2D 좁은 시야의 visible-unknown 면적/이동 비용을 쓴다.
  FUEL 전체 계층 최적화나 entropy 기대값을 재현했다고 하지 않는다. 다중 로봇 map merge는 없다.
- [Area Graph 2019](https://arxiv.org/abs/1910.01019): metric free에서 영역/통로 위상 요약의 근거.
  초록 확인; 공개 코드 재조회는 실패하여 구현 세부 인용은 하지 않는다. 이번 C는 벽 gap·다시 본 양 jamb·
  free 연결·거리장 폭 하한의 최소 단계이며 논문의 전체 Voronoi/room segmentation 이식은 아니다.
- [Smac 논문 v2(2025)](https://arxiv.org/abs/2401.13078v2),
  [Nav2 footprint 검사 코드](https://api.nav2.org/nav2-humble/html/collision__checker_8cpp_source.html):
  unknown 차단·footprint 전체 충돌 검사와 cost-aware A* 근거. A*는 기존 `harness/map_goto.py`와 같은
  격자 탐색 원리로 구현하며 narrow corridor에서 대각선 corner cut 금지. 운반 footprint는 기존
  `pair_passage_plan.PAIR_ENVELOPE`(±.625×±.20 m) 전체를 사용하고 회전은 circumscribed sweep으로 보수 검사한다.

새 패키지/venv 설치 없음. 결과는 로컬/실험 기록에 남긴다. 이전 사용자 결정대로 TensorBoard 변환은 생략한다.
