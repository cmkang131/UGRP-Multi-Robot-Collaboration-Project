# mapbuild8 — 이동량 예측·자기 지도·지도 기반 위치 보정

ownership-ack. `mapbuild1` / `codex/mapbuild1` / PR #556, gcp5 단독. mapbuild7 R2는 인수 시 이미 `MAP_REGISTRATION_REQUIRED`(33.3 SIM초, 334장)로 종료했다. 기존 raw·요구표·실패를 유지하고 새 결과와 합산하지 않는다. 자기 RGB·발행 명령·고정 기구/K/D·허용 정적 지도만 추정에 쓴다. 시작 spawn/평가 좌표로 정적 좌표계를 만들지 않는다.

먼저 R2/R3의 `ambiguous_modes` 후보 점수와 모드 수, ±1σ 조건부 창을 gcp5에서 분석한다. 정적 지도에 등록되지 않은 실행에는 유효한 전역 위치 사전이 없다. 모드 자체를 창 중심으로 삼은 결과는 **조건부 진단**이며 실제 이동량 사전이나 올바른 초기 위치가 아니다. 이 차이를 숨겨 창으로 문제가 해결됐다고 주장하지 않는다.

## 채점 전 결정 규칙

같은 실제 운반 녹화·같은 프레임에서 보정 OFF/ON을 비교한다. 차체 중심 SE(2), 시작 자세 정렬만, 척도1이다. 요구표는 mapbuild6의 바이트를 유지한다(인계 XY≤200.751mm, 방향결합≤21.423°, 자리60mm; 문은 방향과 차체/적재 폭을 별도 평가). 실제 문·구역·복귀·내려놓기·둘러보기·적재 구간이 빠지면 전체 NOT_READY다. 일부 접근 구간 통과를 운반 성공으로 보고하지 않는다.

둘 다 요구를 만족하면 단순한 LK를 기본으로 두고 RBPF off, LK만 실패/RBPF 통과면 RBPF, 둘 다 실패면 원인 분포에 따른 다음 수정안을 제안한다. 사용자 최신 결정에 따라 LK 선택과 별개로 **자기 지도 및 정적 지도에 대한 위치 보정은 필요**하다. 이번 새 후보 `selfmap_map_correction_v1`은 기본 off/후보 on으로 검증하고 기존 결과를 소급 변경하지 않는다. GT는 봉인 뒤 별도 오차 평가에서만 읽는다. 잘못된 보정 채택은 평가 전용으로 전후 오차가 악화됐는지를 수치로 보고한다.

## 먼저 확인한 표준 구조·참고 자료

- [Thrun/Burgard/Fox, Probabilistic Robotics](https://mitpress.mit.edu/9780262201629/probabilistic-robotics/): 출판사 서지 확인. 책 전체를 새로 열람했다고 주장하지 않는다.
- [Fox et al. 1999, Monte Carlo Localization](https://robots.stanford.edu/papers/fox.aaai99.pdf), §Markov Localization/MCL: 이동 예측과 관측 갱신, 시작 미상일 때 전역 다봉 분포. [Nav2 AMCL 공식 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/README.md): 알려진 지도 위치 추정과 global localization을 구분한다. lidar 정확도를 색 경계에 승계하지 않는다.
- [Hess et al. 2016, Cartographer](https://research.google/pubs/real-time-loop-closure-in-2d-lidar-slam/), [공식 알고리즘 설명](https://google-cartographer-ros.readthedocs.io/en/latest/algo_walkthrough.html) Local/Global SLAM: 이동량 사전에서 현재 scan→submap 정합, 국소 submap 삽입, 별도의 강한 loop-closure 검증. 완전 Cartographer 포팅이나 pose graph 구현을 주장하지 않는다.
- [Olson 2009, Real-Time Correlative Scan Matching](https://april.eecs.umich.edu/media/pdfs/olson2009icra.pdf), §III-A/B: 관측우도×이동사전, prior가 정한 가능한 SE(2) 창의 상관 탐색. 기존 `CorrelativeMatcher`/거리장/센서분산/관측가능성 코드를 재사용한다.
- [Montemerlo et al. 2002, FastSLAM](https://robots.stanford.edu/papers/montemerlo.fastslam-tr.pdf), Factored Representation: 경로 posterior와 경로 조건부 지도 분해. 기존 RBPF 비교를 유지하며 새 필터를 발명하지 않는다.
- [Campos et al. 2021, ORB-SLAM3](https://arxiv.org/pdf/2007.11898), §III/IV-A/V: local tracking·lost·relocalization·새 지도와 map merging 구분. feature DB/MLPnP 성능을 이번 벽 scan에 승계하지 않는다.

## 보존·운영

분석/물리/렌더는 gcp5. Mac은 코드·요약·몽타주만. `warp_native_contact_v1`, noslip0, idle20/budget-stop 유지, wall 실행 상한 없음. CPU VM 시작/키·에이전트 자격증명 전송/GUI/모델 호출0. 실행 코드는 커밋 후 고정한다. 관문 funnel·모든 실패·raw 위치·SHA·재현 명령을 남긴다. 임대 및 실제 프로세스/GPU를 점검한 뒤 자신만 남았을 때 gcp5를 정지한다.
