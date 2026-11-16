# beampair4 — 접근 진행 감시와 오래된 막힘 재관측

PR #522, claude/beam-pair-teacher. beampair1/2/3와 합산하지 않는 새 교사 후보.
현재 문서의 사전 분석은 beampair3 소스 e645b34beb4fa693ab4ddedfe77045ae26b46388,
고정 의존성26f84d0f0ada1c33473c83cca2d3415ce51bd247의 원본32회(성공30·실패2)다.

수정 전 gcp1 스크립트로 [접근 관문표](baseline-rejection-table.json)를 만들었다.
[8318620 시간축](8318620-one-second-timeline.csv),
[8318626 시간축](8318626-one-second-timeline.csv)은 1 SIM초 요약이며,
원래0.1초 표·접촉·명령 원장은 `/home/ugrp/ugrp-sim/ops-reviews/beampair4/baseline/`에 보존한다.
스크립트 `scripts/analyze_beampair4.py`, 원본은
`/home/ugrp/ugrp-sim/runs/beampair3-gate-<seed>-e645b34b/raw`.

|관측·원인|8318620 r1|8318626 r2|
|---|---:|---:|
|마지막6 SIM초 이동명령/행|60/61|0/61|
|자기 관측 거리 시작→끝 m|0.16547→0.43549|0.96743→0.96636|
|실제 순이동 m(평가만)|0.273035|0.001632|
|명령 누적 세계 dx,dy m(평가만)|−0.269005,+0.076893|0,0|
|명령↔실제 방향 cosine 중앙값|0.998094|이동명령 없음|
|현재 자기 band 관측|청록61/61|파랑60/61,비가시1|
|해당구간 접촉행(바닥 제외)|0|0|
|해당구간 빔 이동 m|0|0|
|상대와 최소 거리 m|0.680315|0.510315|
|직접 종료 원인|no_goal_error_progress|all_goals_blocked_handoff|

저장된 허용 관측·발행 명령을 넣은 비물리 교사 재생은 두 실패 모두 명령 불일치0.
재생 스크립트/전체 trace는 `/home/ugrp/ugrp-sim/ops-reviews/beampair4/replay_routes.py`,
`replay-8318620.json`, `replay-8318626.json`; 자기 좌표와 평가 좌표를 분리했다.
8318620은 빔을 돌아 청록 바깥 자리로 가는 기존 경로상 진행이0.340193m인데,
직선 목표오차는0.239659→0.477547m로 늘어3초×2 감시가 종료했다.
접근 자체가 역방향 명령을 내렸으며 물리 구동의 반전·충돌·대상 전환이 아니다.
[경로 근거](8318620-route-evidence.json).
8318626은 후보6643개가 모두 blocked_goal. 각 후보에 서쪽 memory_margin과 북쪽
current_geometry 거부가 함께 있어13286개로 중복 집계하면 안 된다.
서쪽 기억22.3초·최소 틈 약1.71m/팽창 약1.81m,
북쪽 기억6.1초·틈0m/팽창 약0.051m이다. 이는 관측 모델의 막힘이며 실제 접촉이 아니다.
기존 일반 빈후보 재관측은 이 오래된 벽을 특정하지 못했다.

성공30회 같은 approach 프레임7563개 중 명령·이동 방향 계산가능6750,
cosine p05/중앙/p95=0.97507/0.99964/0.999998. 방향 반대38행,
명령이 band에서 멀어지는739행, 실제로 멀어지는1024행이다.
실패2회는556프레임/계산가능444, 방향 반대23행이다.
성공에도 필요한 우회가 있어 거리 증가 자체를 실패/충돌로 판정할 수 없다.
이 분포로 새 임계값을 맞추지 않았다. 후보·프레임·사건 모집단은 구분한다.

## 전체 영상 직접 검토

공통 규칙8/9: 기존 gcp1 ffmpeg 개요+r1+r2 3배속 MP4를 재사용하고,
현재 ffprobe로 각960×272·338/231/487프레임을 확인했다(각0.45/0.15/0.38MB).
Mac 화면 앱·open·osascript·computer use는 사용하지 않았다.
원본 자기 JPEG는1Hz, 저장 평가 qpos는10Hz라 카메라 보정을 복구한 평가 재렌더링이다.
물리·제어 재실행/보간이 아니며 저장 몸체 위치 차이0m. 원래 촬영10Hz로 주장하지 않는다.
Mac `/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/beampair3-gate-<seed>-e645b34b/`.

- 실패8318620: 전체0–33.7초2Hz69프레임·끝23.7–33.7초10Hz101프레임 전부.
  0–10초 양측 탐색·접근,10–20초 서로 지나가며 각기 다른 끝 접근,
  20–27초 r2 파랑 가까워짐/r1 청록 옆에서 방향 전환,
  27–33.7초 r1은 청록에서 물러나며 우회·r2 파랑 READY 후 정지.
- 실패8318626: 전체0–23초2Hz47프레임·끝13–23초10Hz101프레임 전부.
  r1은0–5.2초 청록에 정렬·READY. r2는 처음 뒤쪽에서 파랑을 찾으며 돌아가고,
  8–17초 여러 시선 변경 뒤17–23초 파랑이 보이나 차체 이동 없이 정지.
- 성공8318604: 전체0–48.6초2Hz99프레임·끝38.6–48.6초10Hz101프레임 전부.
  양쪽에서 서로 다른 끝을 찾아 우회, 약30–36초 정렬,
  약36–41초 양쪽 READY, 이후 공동 닫기·들기·유지로 완료.

듬성한 프레임 검토와 달리,8318620은 단순 정지가 아니라 연속 후진 우회였고,
8318626은 상대와의 몸싸움 없이 카메라만 바뀐 뒤 정지한 것이 확인됐다.
같은 끝 집중·끼임·빔 밀림으로 해석하지 않는다. 접촉0은 저장10Hz 기하 표본 범위다.

## 후보·경계·짧은 시험

기본off `beampair_approach_v1` 한 후보가 두 결함을 한 묶음으로 고친다.
1. 비몸체 우회에도 기존 search21의 단조 경로 arc 진행 감시를 재사용한다.
   기존1cm/3SIM초를 유지하고, 경로가 없으면 기존 목표오차 감시로 돌아간다.
2. 후보 검사에 실제 기록된 stale wall/cargo를 ActiveReobserve에 지정한다.
   기존2encounter·2.8SIM초만 쓰며 미관측 장애물을 지우거나 통과 허가하지 않는다.
   관측이 갱신되면 기존 IK·몸체·팔·경로 검사를 다시 통과해야 한다.

held_object_hidden_v1, 보이는 것만 아는 교사, weld OFF, 카메라, 성공 판정과
60SIM초 상한을 유지한다. search24_checks_v1/search25_checks_v1 계산량 예산은 계속on.
새 수용 상수 없음. 사용자 공통규칙10의 기록전용 failure-tail 옵션은 기본on:
원래 자기 카메라의 마지막10SIM초를10Hz 링에 남겨 실패·감독중단 때만 저장하고
프레임sha256·개수·바이트를 별도 원장에 적는다. 학생 학습 카메라는off다.

8318620·8318626을 먼저 직렬 시험하고 성공8318600/04/11/31을 같은 대기열로 비교.
원 관문과 동일 장면·pan·역할·교란9/3/1/5/12/8틱, 최대3라운드.
실패 원인 확인 시 같은 후보 실행을 즉시 정지하며 원본과 cap_end/HOST_ERROR도 보존.
6/6일 때만 새40회 미승인 큐(8318620·8318626 먼저·최대16·학습off)를 만든다.

## 표준 방법 조사

- [Nav2 Regulated Pure Pursuit 공식 구현 설명](https://api.nav2.org/nav2-humble/html/md_nav2_regulated_pure_pursuit_controller_README.html),
  Pure Pursuit Basics: 최근접 경로점과 남은 경로를 기준으로 추종.
  전면 이식이 아니라 이미 있는 arc 관찰기를 비몸체 경로에도 쓰는 근거다.
- [Nav2 Obstacle Layer 공식 문서](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/obstacle/):
  observation persistence와 marking/clearing 분리. 만료를 빈 공간으로 간주하지 않는다.
- [Nav2 대기 뒤 다른 경로 재계획](https://docs.nav2.org/jazzy/getting_started/nav2_behavior_trees/trees/nav_to_pose_and_pause_near_goal_obstacle/nav_to_pose_and_pause_near_goal_obstacle/).
  원 조사 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/research/pair.md`와 함께 읽었다.
- Coulter1992 원PDF는 이번 접속에서 timeout으로 본문 미확인. 해당 논문의 임계값이나
  완전성 보장을 이 후보에 인용하지 않는다.

로컬 비물리28개 통과. GCP 새 후보 결과는 아직 미측정.

## R1 종료와 R2 수정

실행3640e010:8318620 하나가14.4SIM초에r2 handoff,0/1·미시작5.
입력0/0·HOST_ERROR0·cap_end0. [R1 요약](r1-summary.json),
[관문표](r1-rejection-table.json), [런타임](r1-runtime.json).
기존 고정경로 arc 관찰기를 비몸체 경로에 그대로 쓰면 탐색 전 기준 경로가 남고,
목표/회전 개선이 인정되지 않았다. 기존 GoalProgress의 credit을 잃은 회귀다.

R1 전체0–14.4초2Hz30프레임·끝4.4–14.4초10Hz101프레임 직접검토:
r1은 청록 재탐색 중, r2는 반대 파랑을 보며r1 근처를 지나 이동했으나14.4초 종료.
같은 끝/충돌로 보이는 완주는 없고 과도하게 이른 진행 handoff다.
원래10Hz 자기RGB202장(1,410,346bytes)을 링 버퍼에서 보존했다.
평가 개요와 함께3배속182,068bytes 영상·ffprobe145프레임, 몸체 위치차이0.
Mac playback/beampair4-r1-8318620에 회수. 원본 촬영 영상은 검은 렌즈 마스크가 있고
이전 qpos 재렌더링과 영상 형성이 다름을 확인했으며 카메라 설정은 바꾸지 않았다.
SHA256SUMS 전부 검증 뒤 본 예약·lease 해제, 다른 작업은 유지했다.

기본off `beampair_approach_v2`는 기존 목표·회전 개선 감시를 그대로 두고,
연속 두 자기 발행좌표를 **현재 같은 경로**에 투영한 signed arc만 누적한다.
경로 갱신 자체는 진전이 아니며 역행을 빼므로 같은 자리 진동에도 credit이 없다.
기존1cm만큼 새 최고 arc를 넘으면 원래3SIM초 창의 진전을 갱신한다.
수용/시간 상수 변경 없음. stale blocker 재관측과 recording-only 링은 그대로다.
R2는 동일6개·동일교란·첫두개직렬, 두 번째 탐색 라운드다. 비물리29개 통과.

## R2 HOST_ERROR와 마지막 R3

f6c2830e:19.7SIM초·8318620 하나에서HOST_ERROR, 나머지5 미제출.
[R2 요약](r2-summary.json), [관문표](r2-rejection-table.json), [런타임](r2-runtime.json).
traceback는 progress.reset 뒤 best_distance=None인데 arc credit이 since부터
채워 원래 observe_goal의 초기화를 건너뛴 TypeError다. 물리 실패와 합산하지 않는다.
R3는 원래 관찰기를 먼저 호출해 기준값을 초기화한 뒤 추가 arc credit을 적용한다.
실패/진행 사건에는 reason_category·none:progress_window 또는 none:HOST_ERROR와
기하가 아닌 min_gap=null 범위를 명시한다. 새 수용 상수 없음.

R2 전체0–19.7초2Hz41프레임·끝9.7–19.7초10Hz101프레임 직접검토.
초반r2 파랑 탐색, 약12초 재접근,16초쯤 양측 자기 끝이 보이며r1/r2가 지나간다.
19초r1 영상은 가까운 상대 차체가 차지하고,19.7초 예외로 양측 새 명령 없이 끝난다.
같은 끝으로 바꾼 실패나 공동 들기 물리 실패로 분류하지 않는다.
원래10Hz 자기RGB202장1,642,257bytes, MP4 278,230bytes/198프레임,
평가 몸체 위치차이0. Mac playback/beampair4-r2-8318620에 회수했다.

R3는 세 번째이자 마지막 라운드다. 같은6개·같은 장면과 교란, 첫두개직렬.
6/6 전에는 gate40을 만들지 않으며 학습off·held 숨김on·weld off를 유지한다.

실행 전 비물리 원본 재생: 수정off는8318620 338명령·8318626 231명령 모두
원본과 불일치0. 수정on도 전 구간 예외0,8318620의 마지막 handoff가 사라졌다.
원본과 첫 명령 차이는 경과30.9초(기존 재계획 뒤),8318626은17.1초의지정 재관측PWM이다.
8318626도 저장구간 종료 때handoff 없음. 새 관측을 생성하지 않는 재생이므로
이 결과를 물리 완주·교사 성공률로 간주하지 않는다.
기존32회 [프레임·사건 순차 표](baseline-input-funnels.json)도 별도 보존한다.
