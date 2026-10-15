# search25 — 원본 거부 분석 뒤 footprint와 inflation 분리

시작 소스 `14a6056f` (search24 push). baseline 실행 소스 `ec8752a1e72d9a1bd1c01c0a292467e75039e75b`.
분석은 gcp1 원본으로 실행했고 Mac에는 요약만 회수했다. 후보별 전 물체 이름·틈은
`/home/ugrp/ugrp-sim/outputs/search25-analysis-v2/candidates/`에 남긴다.
재현 명령·원본 해시는 `search25-analysis.json`, 순차 관문 원장은 `search25-baseline-rejection-table.json`.
평가 정답은 분석 스크립트에만 들어가고 제어기에는 전달하지 않는다.

## 수정 전 거부 분포

|범주|원본 후보 시험 행|
|---|---:|
|현재 기하|26273|
|기억|14079|
|연결 시야|1383|
|계산량 예산|24|
|각도 / IK|0 / 0|

현재 기하26273은 전부 다른 화물(tile_1 9893, red_2 9646, yellow_1 2392, can_1 4342)이다.
벽·상대 로봇의 현재 기하 거부는0. 다만 현재 기하 분류는 fresh이면 여유에 의한 거부도 포함한다.
기하/기억의 **차단물 발생 건수**를 다시 나누면 실제 추정 형상 겹침22477, fresh 여유1352,
기억 여유16523이다. 한 행에 여러 차단물이 있거나 반복 재계획하면 중복하므로 후보 행 수와 합산하지 않는다.

기억14079는 새 물체14079개가 아니다. 같은 ID의 화물/로봇을 여러 후보·여러 틱에서 반복 검사한다.
8311709에서 can_1/yellow_1은 마지막 관측 후6.7/6.5초에도 남고, 현재 로봇 시작점과의 틈
165/168mm를 요구167/169mm가 막는다. tile_1/red_2도3.2/3.3초 된 관측을 반복 검사한다.
315709 v6의 peer r2 기억 거부273행은 틈217mm 대 최대 요구303mm, 마지막 관측 후1.9초다.
peer는 search23의2초 TTL과 나이별 σ 팽창만 있고 속도/미래 경로 예측은 없다.
움직일 예정이라도 현재 추정 원을 장애물로 취급한다. 그러나 이 6개에서는 지배 원인이 아니다.

## 평가 전용 장면 기하

시작 장면, r1 파랑 끝, IK·각도 합격 IRM91개. zero는 추가 여유0·화물의 저작 landing 원,
peer는 기존 계획기의0.17m 원을 명시적으로 유지했다. current는 같은 정답 위치에서 현재 추정
여유를 적용한 반사실 비교다(전체 교사 cache 재생 아님). 후퇴는2mm 샘플, 팔은 기존 전체
issued pick cloud 검사다. 연속공간 완전성이나 시작점부터의 경로 존재를 증명하지 않는다.

|episode/seed/장면|차체 zero|팔+후퇴 zero|현재 여유|zero 최적 최소 틈|
|---|---:|---:|---:|---:|
|episode-000/8311709/off|39/91|39/91|26/91|35.3mm|
|episode-001/8311709/cargo_v6|39/91|39/91|39/91|45.1mm|
|episode-002/315709/cargo_v6|65/91|65/91|52/91|91.5mm|
|episode-003/315709/off|65/91|65/91|52/91|90.9mm|
|episode-004/8312300/off|91/91|91/91|91/91|96.7mm|
|episode-005/8312301/off|91/91|91/91|91/91|96.7mm|

zero에서도 자세가0인 에피소드는 없으므로 이번 표본을 장면 생성 불가능 사례로 표시하지 않는다.
실패4회의 대상-다른화물 표면 거리는182/192/268/268mm, 성공2회는712/1322mm다.
벽은 실패에서1.12/1.25m 이상 떨어져 있고 성공은0.49/1.00m로 오히려 가깝다.
r2는 대부분 대상에서약0.743m이고 성공8312301만 시작1.335m다. 실패의 차이는 화물 근접과
기억 팽창이며 벽이나 peer 중심 배치가 아니다. 마지막 프레임에서 가능한 현재 여유 자세는
8311709 두 장면0,315709 v6 52/base13으로 줄어든다. 이 수는 끝점 검사이고 접근 성공이 아니다.

## 표준 방법과 후보

- [Nav2 inflation](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/inflation/): 충돌 반경 안은 lethal, 바깥은 지수 감쇠 traversal cost. 기본 cost_scaling_factor10.0을 본문 확인.
- [Nav2 footprint·potential field](https://docs.nav2.org/jazzy/configuration_and_development/tuning_guide/): 비원형 로봇의 실제 SE2 footprint와 넓고 연속적인 비용장 권장. 저자의 parameter 기본값이 실물 오차 보장이라는 뜻은 아니다.
- [Nav2 대기·재계획](https://docs.nav2.org/rolling/getting_started/nav2_behavior_trees/): goal 부근 장애물이 비워지기를 기다린 뒤 우회하는 behavior tree. 임의로 peer를 삭제하는 방법이 아니다.
- [ORCA 저자 자료](https://gamma-web.iacs.umd.edu/ORCA/): 상대 속도와 상호 책임에 의한 충돌 회피. 우리 visible-only 관측에는 신뢰 가능한 속도가 없으므로 이번에 ORCA 구현/안전 보장으로 보고하지 않는다.
- [Reuleaux 저자 논문](https://arxiv.org/abs/1710.01328): reachable map으로 가능한 기지 자세를 구해 재배치. 기존 search24 IRM을 유지하고 경로를 선택한다. full SE2 Hybrid-A* 구현은 아니다.

`search25_inflation=search25_soft_v1` 기본off: 가장 큰 화물 기하 문제에서 실제 겹침과
불확실성 비용을 분리한다. 관측 화물의 중복5mm padding을 제거하고 실제 footprint는 유지한다.
σ 여유는 A* 비용에 남기고 hard collision은 관측 형상 경계다. 이동 중에는 고정5mm 대신
(샘플간 이동거리 + footprint 모서리반경 × 회전각)/2를 요구한다. signed distance의
1-Lipschitz 성질로 가까운 샘플부터의 최대 움직임을 덮는 수학적 경계이며 새 경험 상수가 아니다.
정답 위치/관절/접촉 보정·jaw/IK 완화·weld는 넣지 않는다. 관측 오차 자체를 보장하지 않는 진단 후보다.

같은 대기열의 독립 비교 후보(합산 금지):
- `search25_budget=search25_checks_v1`: 기존98304 검사 한도, wall30초는 별도 host 안전 cap_end만. 후보 선택 예산으로 쓰지 않는다. 숫자는 사용자 addendum 요청이며 성능 최적값 주장이 아니다.
- `search25_memory=search25_memory50_v1`: 기억 여유50mm, 상수 감사의 평가전용 N5287 p90/초과5.4% 근거. fresh는 유지. soft 후보와 별개로 측정한다.
- `search25_view=search25_frame_v1`: 가로±24/세로±18°,640×480 pinhole 반화각27.2/21.1°에서 사용자 addendum의3° reserve. ≥5/15·차폐 검사는 유지한다. GCP 저장 상태 렌더/왜곡 투영을 확인한 뒤 켠다.

모든 후보는 기본off이고 search24 IRM+계산량 예산을 요구한다. 교사·batch·recording admission의
프로필과 gate match에도 기록한다. 학습RGB/ACT/모델 호출0. 실행 코드는 커밋·push한 SHA에 고정한다.

## 짧은 탐색

실패 seed8311709 base/v6,315709 v6/base를 먼저 둔 기존6개 계획, 동시6·60SIM초 상한,
최대3라운드. 원본 재계수·실패 프레임·입력 감사·funnel·전체 raw manifest를 검증한다.
4/6 이상인 최종 소스만32회 비교 대기열 후보가 되며, 대기열은 비활성·검토용이다.
