# search23 — 격자 연결 계획과 동적 상대 기억

기준 f1acff22, 기본 off search23_v1, run-first·push 전 GCP 최대3라운드.

## 수정 전 원인 선택

|사례|기억 여유|현재 기하|IK|각도|no_path(이중집계)|연결 가시성|
|---|---:|---:|---:|---:|---:|---:|
|episode-000|23|589|1035|1856|296|0|
|episode-001|32|500|1011|1881|278|0|
|episode-002|857|676|2448|4872|516|164|
|episode-003|12|8|29|58|12|0|
|episode-004|0|0|0|0|0|0|
|episode-005|0|0|0|0|0|0|

기억 여유·현재 기하는 거부 범주, no_path는 단계 이유이므로 일부 중복한다. ep2 no_path 516행은 기억 범주에 귀속되고 차단물 r2 516행이다.

후보 시험 단위이며 반복 재검증 포함. IK·각도는 원래 격자의 부적합 조합이다. 이 필터를 통과한 연결 단계의 no_path와 기억 차단을 우선 고친다. 제공된 읽기 전용 오프라인 분석에서 세 칸 모두 실제 비는 자세가 있고 8311709의 8자세 모두 격자 A* 경로가 존재한다. 315709 v6 no_path는 상대 r2 기억이 주원인이다. −15도 규칙은 유지하고 숫자로만 검증한다.

## 참고 자료

- Hart, Nilsson & Raphael (1968), A Formal Basis for the Heuristic Determination of Minimum Cost Paths. 원문 PDF 열람: https://www.cs.auckland.ac.nz/courses/compsci709s2c/resources/Mike.d/astarNilsson.pdf .
- 요청 URL https://docs.nav2.org/configuration/packages/configuring-smac-planner.html 열기 실패. 이전된 공식 문서 본문 확인: https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/planners_plugins/smac/ 및 smac/smac_2d/configuring_smac_2d/ .
- Nav2 inflation 공식 본문 확인: https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/inflation/ .
- 읽기 전용 분석: /private/tmp/claude-501/-Users-changmin-projects-ugrp/4e56a99a-0106-48c9-b04d-d1cd272ae60e/scratchpad/search22_reach_verdict.md 및 사용자 지정 reach/ . 분석 도구·정답은 제어 입력에 넣지 않는다.

## 구현

격자 25mm, 8이웃 cost-aware weighted A*(최종 후보 h 가중2.0), 실제 시작·정확한 목표 연결과 모든 edge를 2mm/0.5도 이하로 검사한다. 몸체는 실제 185×159.9mm 방향성 footprint의 Minkowski 팽창이며 search22의 장애물별 기하 패딩+k·sigma를 보존한다. 원형 circumscribed footprint로 좁은 통로를 새로 막지 않는다. 팽창 경계 밖 지수 비용(exp(-10·slack), 승수1; Smac 2D의 속도 지향 설정)을 쓰고 검색공간은 기존 전체 bounds다. 시한은 기존 틱3초/98304검사를 유지하고 만료를 planning_budget으로 별도 기록한다. 시간 제한 안에 임의 연속공간·임의 yaw 해를 보장하지 않는다. 캐시는 현재 nav 관측 snapshot 내에서만 재사용한다.

상대 로봇은 현재 보이면 최신 관측, 안 보이면 sigma=sqrt(search22_sigma²+(0.05m/s·age)²), 관측 age>2 SIM초면 만료한다. 증가율·TTL은 설계 가정이며 실제 안전 보증이 아니다. 오래된 FreeSpace ghost·재관측 hint/pin도 만료해 재삽입을 막는다. 새 peer 정보나 구조화된 통신은 추가하지 않는다.

no_path는 검색 frontier에서 거부한 장애물 이름·gap·요구 여유·slack·자세, 최선 탐색 prefix의 길이를 기록한다. 승인 경로는 전체 길이와 경로 최소 gap을 기록한다. 거부 frontier 목록은 최소 cut의 증명이 아니다. −15도 가시성은 문턱5를 유지하고 실패 probe 수·자세·PWM·구간을 기록한다. 기본 off는 search22 동작을 유지하고 모드를 실행·admission 매칭에 전달한다.

## 검증과 라운드

관련 오프라인72통과(물리·렌더 없음). 실제 GCP 결과와 원본 해시는 아래에 추가한다.

### 라운드1 ba9ab93b: 2/6, 감독 중단4

|사례|기억/현재/IK/각도/no_path 원장|계획 예산 소진 틱(두 로봇 합)|상태|
|---|---|---:|---|
|episode-000|미저장(unknown)|22|interrupted|
|episode-001|미저장(unknown)|22|interrupted|
|episode-002|미저장(unknown)|16|interrupted|
|episode-003|미저장(unknown)|13|interrupted|
|episode-004|0/0/0/0/0|0|complete|
|episode-005|0/0/0/0/0|0|complete|

중단4회의 후보 진단은 기존 예외 writer가 최종 teacher diagnostics를 저장하지 않아 미회수다. 0으로 채우지 않는다. 실제 발행 원장의 planning_compute를 세었고, 가장 큰 확인 원인은 **연결 후보 하나의 A*가 틱3초를 소진해 다음 자세 후보를 검사하지 못하는 계획 starvation**이다. 두8311709 마지막10틱은10/10 예산 소진, 315709도7/10이었다. 소유 batch PID597197을 확인해 SIGINT를 보냈고, 완료된 성공2회는 보존했다. 전체 VM 원본 SHA256SUMS와 로컬191파일/선택자기프레임72장 검증 완료. 소유6슬롯 해제·임대 제거.

### 라운드2 제출 전 수정·분석

endpoint의 IK·각도·목표/후퇴·팔 검사를 먼저 모두 수행한 뒤 그 목표들을 함께 둔 **역방향 multi-source weighted A***를 한 번 수행한다. 좁은 자세 구역에서 먼저 빠져나와 전체 방을 탐색하다 시한을 쓰는 문제를 줄인다. h 가중2, 팽창 비용 승수1(공식 Smac 2D의 속도 지향 설정)을 쓰며 기하/σ 여유·승인 조건은 그대로다. 동일 snapshot의 body edge·connector view/issued arm 검사만 정확한 입력 키로 재사용한다. 가시성 실패 edge는 그 snapshot에서 제외하고 같은 목표에도 다시 연결하며 문턱5는 유지한다. 이 edge 제외는 보수적이며 PWM까지 포함한 연속 상태공간 완전성을 주장하지 않는다.

중단 원본의 자기 visible_measurements와 실제 발행 명령만 재구성한 네 snapshot에서 완전 stance 승인을 확인했다(분석용 재생, 새 물리 궤적 아님). 첫 구현이 반복3초를 쓴 반면 역방향 후보는 1.38–2.20초였다(측정 시점 수치, 호스트 부하로 달라질 수 있음). 원본−15도만의 문제가 아니라 동일 연결 지점에서 0/−10/−15도 모두 probe2/5 또는4/5로 거부될 수 있음을 확인했다. 문턱은 바꾸지 않았다. 두 snapshot을 허용 입력만의 회귀 fixture로 저장했다. 예외/감독 중단에도 후보 diagnostics를 보존하도록 writer를 보완했다.

라운드1 중단4회의 자기 프레임 각12장 총48장 직접 확인: 두8311709는 같은 자기 시야에서 진전 없이 멈추고 r2는 청록 끝 앞 대기, 315709 두 경우도 r1 접근 중 r2 대기였다. top 영상은 생성·열람하지 않았다.
