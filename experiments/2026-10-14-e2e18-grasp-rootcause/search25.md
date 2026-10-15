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

### R1 — 호스트 오류, 성공률 미측정

실행 SHA `26f84d0f0ada1c33473c83cca2d3415ce51bd247`, 원본
`/home/ugrp/ugrp-sim/runs/search25-r1-short6-26f84d0f`. 보간 경계의 새 차단물 row에
slack_m이 없어 후속 grid measure에서 KeyError. HOST_ERROR1·동반 interrupted5·완료0.
성공0/6으로 해석하지 않는다. 실행기가20.9wall초 안에 전부 정지했고 별도 정지 기록을 남겼다.
원본 전체 manifest 검증 뒤 임대/예약을 해제했다. R2는 동일 profile에서 필드 누락만 고친다.
R1 거부는 현재기하104·endpoint_feasible76·feasible2, 물리 성공/실패 판정 전 중단이다.
GCP view 검사는1813개 사각 경계/내부 점의 pinhole/fisheye 이탈0/0, 저장상태60개 camera 표본,
실패4개 장면을 실제 renderer로 복원했다. 감지 정확도/새 궤적 성공 검증과 구분한다.
비물리 회귀28통과. budget-stop ACTIVE를 실시간 확인했고 기존 비용/유휴/종료 장치를 변경하지 않았다.

### R2 — 접근 통과 뒤 IK/정렬 deadband 원인 확인

실행 SHA `987af398ce71cd871f6d31b6599fc2e54280070c`, 원본
`/home/ugrp/ugrp-sim/runs/search25-r2-short6-987af398`. 성공2, 완료4(8311709 base/v6는
alignment_no_progress), 동반중단2(315709 두 장면), HOST_ERROR0. 중단2를 물리 실패로 세지 않는다.
실행기가 같은 alignment 원인2회로 남은 실행을 정지했다. 조정자 정지 확인 시 이미 EXIT였으므로
추가 SIGINT 대상0이며 SUPERVISOR_STOP에 원인/확인 시각을 남겼다. 원본 전체 manifest·
실패RGB/몽타주52개 항목 해시 확인, 임대/예약 해제. 현재기하11804·endpoint_feasible559·feasible13,
기억/시야/계산예산 거부0(중단된 비교라 이전 성공률과 합산/직접 개선 주장하지 않음).

평가 정답 없이 자기 visible+issued 원장만으로 마지막15틱의 상대 표적을 재구성했다. v6 마지막
gx=.209663329m, gy=-.003981224m, 목표거리=.2092m, 가시 probe15/15, IK는 도달 불가인데
발행 바퀴0이다. x오차.463mm가 기존 .5mm 재활성 조건보다 작아서 멈추는 결함이다. 재활성만
해도 기존 duty 계산의1ms 미만 제거→3초 진전 시한→적분 reset이 다시0을 만들 수 있다.
R3는 soft 토글에서만 IK가 불가하면 x축을 재활성하고, 그 보정 명령의 비영(非零) 요청을
기존 speed35/40ms 정렬 펄스 바닥 전에 지우지 않는다. 새 수용 오차·IK 범위·펄스 상수는 없다.
기존40ms floor의 실물 반응은 여전히 미측정이며 새로 실기 사양이라고 주장하지 않는다.
ready의 IK/jaw/팔 충돌 및 실제 명령의 전체 안전 검사도 그대로다.
R3는 GCP 렌더 확인을 끝낸 사각 시야 후보도 켠 결합 진단이다. 각각의 효과를 독립적으로
추정하거나 메모리50mm 비교와 합산하지 않는다. 비물리 회귀29통과(원본 .463mm 반례 포함).

기억 상세 재집계:14079행→같은 tick/choice/blocker 중복 제거7345건, tick 제외260조합,
같은 조합 최대106회. 실패4회에서 r2의 시작점 대비 최대 이동은0.195/0.183/0.331/0.621mm다.
따라서 미래 peer 예측은 표준 참고·후속 비교이고 이번 지배 원인 수정은 화물 경로/정렬이다.

### R3 — 최종 NOT_READY_3_OF_6

실행 SHA **`1effa9b266b44ac716b9808b95eb6aa938e42702`**, 원본
`/home/ugrp/ugrp-sim/runs/search25-r3-short6-1effa9b2`. 완료6/6·성공3/6·HOST_ERROR0·
cap_end0. 8311709 v6(38.4SIM초)가 새로 성공했고8312300/8312301도 성공했다. base8311709는
40.2SIM초에 alignment_no_progress,315709 v6/base는21.2SIM초에 approach_blocked_handoff다.

|거부 범주|search24 R2|search25 R1(미완료)|R2(완료4/중단2)|R3(완료6)|
|---|---:|---:|---:|---:|
|현재 기하|26273|104|11804|15622|
|기억 여유|14079|0|0|0|
|연결 시야|1383|0|0|4584|
|계산 예산|24|0|0|3730|
|endpoint_feasible(거부 아님)|983|76|559|1308|
|feasible(거부 아님)|28|2|13|29|

시험 행 수는 같은 후보의 반복 검사이며, 길이·재관측·후보 집합·완료 수가 달라 단순 개선율로
읽지 않는다. R1 실제 HOST_ERROR1+중단5, R2 실제 HOST_ERROR0+중단2다. R2 두 raw result의
status는 running으로 남았지만 root EXIT와 프로세스 종료를 확인했으므로 실행 중/완료로 보고하지
않고 incomplete_stopped로 분리한다. 요약의 기존 host_error_N은 미완료를 포함하는 집계라
별도 actual_host_error_N/stopped_incomplete_N을 함께 기록했다. 세 라운드를 합산하지 않는다.

남은 base 정렬은 visible+issued 재구성 마지막 상대 표적(.208385,.004469)m, 목표5°/.208m,
IK·jaw·끝점 팔/차체 검사 합격, goal 오차8.45mm지만 yaw 오차61.995mrad가 기존60mrad
ready 한계를 넘는다. 실제 원장에는 alignment_axes_blocked가 반복되고 발행 바퀴0이다.
이 재구성은 교사의 모든 cache를 재생한 것은 아니므로 어떤 실제 명령 안전 검사가 마지막
축을 막았는지까지 확정하지 않는다. 한계를 풀지 않았고 추가 라운드도 내지 않았다.
`search25-r3-alignment.json`과 실행 가능한 분석 스크립트에 근거를 남겼다.

315709 두 장면은 grid 경로는 찾지만 connector 검토에서 band probe가 주로3/4(요구5)로
재거부된다. v6/base의 시야 거부2288/2296, 계산 예산1885/1845다. 사각 프레임 투영 확인이
이 동적 gaze/connector 예측과 실제 자기RGB 가시성의 동등성을 증명하지 않는다. 실패 몽타주에서
실제 자기RGB에 파랑 끝이 보이는데 접근이 정지하는 구간을 직접 확인했다. 다음 원인은 단순
기억 여유가 아니라 connector 관측/명령 검증과 재시도 계산 낭비이며, 이번에는 문턱을 추가로
낮추지 않았다. 실패3회의 자기RGB36장+몽타주3개(39개 항목) 해시를 확인하고 직접 검토했다.

전체 wall/SIM 중앙4.552(경고,6.0미만). 첫30SIM초 기록은8311709 두 실행에만 있고
4.420/4.114(중앙4.267)다. 나머지4회는30초 전에 끝났으므로 동시6의 완전한 첫30 검증으로
보고하지 않는다.315709 개별 전체 wall/SIM은11.647/11.065로 계획 검사 비용이 크다.
30wall초 host 안전 cap은 발동0, SIM cap_end도0이다.

최종 입력 감사6/6 활성·invisible_measurements0·held_world_reads0. Mac 물리/렌더0, 모델 호출0,
학습RGB/ACT학습0. 관련 비물리 회귀29통과. baseline과 각 라운드의 후보·프레임·이벤트 funnel은
`search25-*-rejection-table.json`에 별도 모집단으로 저장했다. 예산 중단의 관문 불명 행을
앞 관문 통과로 꾸미지 않았다. source_sha, 원본 경로, 재현 명령과 raw result 해시를 포함한다.

**4/6 미달 →32회 대기열 미생성·미제출.** addendum의 예산·기억50mm·사각 시야 후보는
`search25-candidates.json`에 독립 profile로 남겼고 미측정 조건은 미측정으로 표시했다. 실제
대기열이나 승인된 실행 명세가 아니다. 총3라운드를 소진했으며 별도 성공률≥95% 관문·기록·
학습·기본값 전환은 하지 않았다. 최종 원본은GCP 영속 디스크에 남고 호스트 밖 전체 백업은 없다.
자기 worker0·임대0·예약 해제를 확인했고 다른 작업/VM을 정지하지 않았다.
추가한 supervisor stop 메타데이터는 기존 manifest 해시를 cleanup 기록에 보존한 뒤 manifest에
연결해 다시 전체 검증했다. 최종 결과/해시/위치는 `search25-results.json`, 정지 기록은 로컬
`outputs/e2e18-admin/stop-search25-final-1effa9b2.json`이다.

실행 종료 후의 추가 수정은 **진단 전용**이다. 사각 시야 후보도 legacy camera_view_cone/18°
cone gap을 원장에 쓰던 부분을 camera_frame/사각 경계 최소 틈으로 바로잡았다. R3 원본의
기존 cone gap은 당시 기록 그대로 보존하며 사각 경계 틈이라고 소급 해석하지 않는다.
추가 물리 실행0, 관련 비물리7통과. 마지막 물리 소스는 계속1effa9b2이며 정렬/구동/기하/예산
핵심4파일이 그 SHA와 동일함을 해시로 확인했다. 이후 commit은 기록·분석·공통 규칙과 이
진단 필드 수정이 포함된 별도 HEAD다.
