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

격자 25mm, 8이웃 cost-aware weighted A*(h 가중1.2), 실제 시작·정확한 목표 연결과 모든 edge를 2mm/0.5도 이하로 검사한다. 몸체는 실제 185×159.9mm 방향성 footprint의 Minkowski 팽창이며 search22의 장애물별 기하 패딩+k·sigma를 보존한다. 원형 circumscribed footprint로 좁은 통로를 새로 막지 않는다. 팽창 경계 밖 지수 비용(exp(-10·slack), 승수2)을 쓰고 검색공간은 기존 전체 bounds다. 시한은 기존 틱3초/98304검사를 유지하고 만료를 planning_budget으로 별도 기록한다. 시간 제한 안에 임의 연속공간·임의 yaw 해를 보장하지 않는다. 캐시는 현재 nav 관측 snapshot 내에서만 재사용한다.

상대 로봇은 현재 보이면 최신 관측, 안 보이면 sigma=sqrt(search22_sigma²+(0.05m/s·age)²), 관측 age>2 SIM초면 만료한다. 증가율·TTL은 설계 가정이며 실제 안전 보증이 아니다. 오래된 FreeSpace ghost·재관측 hint/pin도 만료해 재삽입을 막는다. 새 peer 정보나 구조화된 통신은 추가하지 않는다.

no_path는 검색 frontier에서 거부한 장애물 이름·gap·요구 여유·slack·자세, 최선 탐색 prefix의 길이를 기록한다. 승인 경로는 전체 길이와 경로 최소 gap을 기록한다. 거부 frontier 목록은 최소 cut의 증명이 아니다. −15도 가시성은 문턱5를 유지하고 실패 probe 수·자세·PWM·구간을 기록한다. 기본 off는 search22 동작을 유지하고 모드를 실행·admission 매칭에 전달한다.

## 검증과 라운드

관련 오프라인72통과(물리·렌더 없음). 실제 GCP 결과와 원본 해시는 아래에 추가한다.
