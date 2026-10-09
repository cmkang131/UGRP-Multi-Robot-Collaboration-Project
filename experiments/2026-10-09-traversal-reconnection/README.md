# egomap52 — 자기 지역 정합으로 복구 구간 재연결

## 사전등록 (결과 전)

감독 승인: egomap51의 47성분·B 경로0/4를 복구 양끝/장소 재인식으로 연결한다. 문·벽 검출기·모션·기존 도착 수치 동결. 기존 seed49001–49006 **동일6녹화의 개발 재생**, 확증 자료 아님. 옵션 `return_policy=traversal_graph_reconnect_v1` 기본off; `traversal_graph_v1` 보존. raw는 `/Users/changmin/projects/ugrp/outputs/traversal-reconnection-v1/`. 모델0, 관문 전 물리0, timing 측정0/잠금 미취득, NI=0·NO_BG_NICE.

### 변경하는 조건

- egomap51 .30m/20° 노드와 연속 이동 엣지를 유지. 복구의 직전·직후 노드를 명시적으로 저장하고, 버렸던 중간 자기 추정 자세/관측 ID를 보존한다. 양끝의 정합이 수락될 때만 그 기록된 구간을 엣지로 채택한다. GT 접촉으로 구간을 고르거나 엣지를 제거하지 않는다.
- 정합은 `self_pose_graph.match_loop`와 egomap48 `self_graph_cache.GraphCache`를 **직접 호출**. `GraphOptions()` 전체 불변: ±1m/±15°, .1m/1° 탐색, score≥.55, overlap≥.60(.20m), residual≤.15m, mode gap≥.02, Hessian ratio≥.03, 최소6점, refinement·경계 검사 그대로. 결과/거리장 캐시는 동일 내용 키, 로봇별 격리.
- 복구 양끝은 명시된 연속 구간의 재확인으로 `match_loop`를 호출한다(장기 루프 후보 생성의5초 separation은 적용하지 않음; 수락 수치 변경 없음). 자기 입력에 포함된 같은 scan을 참조-질의 양쪽에 넣지 않는다. 일반 재방문은 기존5초 separation을 유지하고, 기존 노드 간격 .30m 안의 가까운 과거 노드 **k=5**를 후보로 비교한다. k는 계산 예산 사전 선택이며 결과로 바꾸지 않는다. 같은 장소 연결은 matching constraint/출처를 기록하며 거리만으로 연결하지 않는다.
- 지역 submap은 기존 노드의 최근15초/12스캔으로 기존 log-odds inverse model을 재사용. 센서 입출력/좌표계 어댑터 외 새로운 정합·지도 적합0. 수락 연결의 전역 좌표 왜곡은 숨기지 않고 GT 벽 교차 관문에 그대로 포함한다.
- 첫 귀환 정합은 egomap51 **동일 CSM** 수락 규칙에 가장 가까운 k=5 후보를 적용한다. 순서는 거리, node ID. 모두 실패하면 저장 노드의 시야 방향으로 **카메라 v3 반 FOV(27.25°) 이하의 부분 회전1회**, 기존 회복10초 상한; 360° 금지. 귀환 중 다른 노드 정합에도 동일1회 제한. 측면/후진 금지·회전 후 전진·B blacklist 금지는 유지.

### 판정 — egomap51 기준 그대로

1. 6/6 인과적 prefix 생성, 손실 프레임/이후 관측을 그래프에 넣지 않음.
2. B를 관측한 모든 회차(기존4/6)의 마지막 탐색 노드→B 관측 노드 경로 존재.
3. 그 경로의 저장 중간 추정 좌표에 시작 GT 변환만 적용해 중심선 벽 교차0 **및** 기존 footprint0.28×0.24m 겹침0. 실제 GT 경로는 별도 참고. 빈 경로/미관측을 통과로 세지 않음.
4. B 관측+귀환 기록 모든 회차의 **첫 return 프레임**에서 지역 정합 수락 및 B까지 연결.

부분 회전 이후 관측은 첫 프레임 관문에 합산하지 않는다. 녹화는 새 회전 명령을 실제 실행하지 않으므로 단위 시험으로 각도·시간 상한만 검증하고 물리 효과를 주장하지 않는다. prediction·경로를 SHA 봉인한 후에만 별도 GT score. 새 조건 평가1회, 결과 뒤 문턱/설정 변경0. 실패하면 원인·선택지를 기록하고 물리 없이 종료. 모두 통과할 때만 egomap49 동일6seed의 360+270초/dev_light/agent_lock 물리 순차1회씩(다른 잠금은 대기), 도착/6·거짓 선언·벽 접촉·회전 시간비·귀환 시간 비교. ENOSPC=HOST_ERROR, 제외도 전부 표기.

## 참고 자료·기존 코드 대조

- [Kuipers 2000 SSH §4.4/4.6](https://www.cs.cmu.edu/~motionplanning/papers/sbp_papers/k/Kuipers-aij-00-elsevier.pdf): 같은 장소의 다른 표상을 관측/지역 metric 근거로 식별하고, 확인된 위상 연결에서 Dijkstra 경로 선택. 같은 위치 가설과 확인을 구분한다.
- [Hess et al. 2016, Real-Time Loop Closure in 2D LIDAR SLAM](https://research.google/pubs/real-time-loop-closure-in-2d-lidar-slam/), [ConstraintBuilder2D](https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/internal/constraints/constraint_builder_2d.cc): 후보 scan-submap 정합과 score 승인, submap matcher 재사용. 기존 Olson 계열 correlative 탐색의 프로젝트 구현 `self_pose_graph.py:137–203`/`self_graph_cache.py:39–81` 직접 사용. 새로운 라이브러리·원문 코드 복사0.
- [egomap48 캐시 동일성](../2026-10-08-graph-runtime/README.md): immutable submap의 field/동일 pair 결과를 내용 해시로 재사용, 장기 graph solver 변경0. 이번에는 속도 측정을 새로 하지 않는다.
- 부분 회전과 k=5는 논문이 우리 카메라에 제시한 최적 수치가 아니다. 후보 탐색·능동 시야 확보 구조만 표준을 따르고, 단안 좁은 FOV의 계산/행동 상한을 위처럼 고정했다. geometry acceptance는 한 값도 재적합하지 않는다.

## egomap51 첫 정합 진단 (이전 봉인 결과, 새 결과 아님)

|seed|최근접 노드 거리 m|노드 heading 차이 절대°|현재/지역조각 선분 수|기존 overlap|기존 사유|
|---|---:|---:|---:|---:|---|
|49001|.016|138.24|7/75|.952|accepted|
|49002|.105|137.42|4/26|0|unobservable|
|49005|.395|100.30|5/79|0|unobservable|
|49006|.234|102.77|1/3|미계산|insufficient_points|

거리 자체는 모두 기존 .5m 범위 안이다. heading 차이만으로 실제 시야 overlap을 단정할 수는 없으나, 실패2건의 정합점 overlap0/Hessian0, 나머지는2끝점이라 최소6점 미달이다. 노드의 과거 여러 시야를 가진 지역 조각 중 다른 후보가 도움이 되는지는 이번 재생으로 판정한다.
