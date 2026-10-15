# reloc14 — 등록 뒤 추적과 v7 운반 탐색

시작 `fa215853` / reloc13 물리 `fc11a303`. 질감 장면이 주 조건이다. 이 문서는 실행 전 설계이며 물리 검증 결과는 summary.json과 관문표에 따로 기록한다. 최대 3라운드, 라운드당 4–6회, 실패 시드 우선. 운용 관문/학습 승격은 자세 오류 감소와 실제 목적지 놓기 확인 뒤에만 한다.

## 원본에서 확인한 원인

GCP에서 `scripts/analyze_reloc14.py`로 reloc13 전체 원본을 채점했다. [수정 전 거부 분포·드리프트 표](rejection-table.md), [수치/원본 해시](baseline-summary.json). R3 첫 등록4/4는 3.49–9.85cm, .097–2.483°다. 등록 뒤 제어 오류는 xy127, yaw183, 동시28(합282/626). 정적 보정 직후에도 일부 오차가 있으므로 모든 오류를 순수 추측항법으로 환원하지 않는다. R3 신선한 정적 보정60건은 위치 오류6·yaw오류4이고, 나머지는 이후 전파/ORB 갱신 구간이다. 각 실행의 경과 SIM초·명령 이동거리·누적 회전량 구간별 p50/p95를 관문표에 남겼다. 구간은 보고용이며 제어 임계값이 아니다.

회전 중 actual/command yaw 회귀 비는 R3 .9952–.9992, R2 .9967–1.0039다. carry의 보정 전 residual_rotation_fraction=.4920508은 현재 selfmap 회전 오차율과 다른 층위다. carry의 pure-turn 보정 검증 비 .946–1.042와 혼합 trim/운반을 합산하지 않는다. PF는 이미 .25m/.2rad 또는 새 카메라 뷰마다 갱신되지만, 기존 실행은 등록 후에도 전역3뷰 관문을 반복하고 ORB 보정과 섞였다. PF에 LK로 보정한 delta를 주면서 다중 프레임 기하 증거는 command odometry로 검사했다. 이 경로 차이와 등록 뒤 갱신 누락을 수정 대상으로 잡았다.

## 표준 방법과 기본 off 토글

- `reloc14_continuous_tracking_v1`: 최초 전역 R7(3개 다른 뷰·10cm/5° anchor 안정성)을 유지한다. 이후 알려진 모드의 PF를 계속 갱신하고 실행 자세로 전달한다. 관측 갱신 없는 예측은 새 정적 fix로 세지 않는다. 새로운 관측에서 현재 프레임 선분 기하/PF 관문을 잃으면 LOST로 가고 기존 전역 R7 재지역화로 복귀한다. 추적 중에는 prior로 만든 ORB bank가 독립 절대 보정인 것처럼 다시 자세를 덮지 못한다. 최초 등록 뒤에는 보정된 자기 명령 오도메트리로 PF와 증거의 기준을 통일한다.
- R7 수치 3회·10cm/5°는 전역 획득/재획득에만 적용한다. 이미 알려진 모드의 연속 추적은 새 전역 등록이 아니다. 추적은 기존 현재 뷰 geometry_supported의5cm/5°,2개독립축 및 기존 PF질량.9·rawcov .15m/5°를 그대로 사용한다. 이 기존 상수들이 실제 정확도를 인증한다는 주장은 하지 않으며 새 오프라인 분포와 폐루프로 검증한다. 근거 없는 새 '보수적' 상수는 추가하지 않았다.
- `reloc14_compute_budget_v1`: 자기 지도 A*는 8이웃 격자의 각 정점을 한 번 닫고 최대 pop=1+이웃수×격자셀수로 제한한다(유한 그래프에서 유도). carry A*는 기존 40000노드 상한을 각 호출에 명시한다. 전역 line RANSAC은 기존4096 proposal/3회refit, PF는기존2000입자, 재관측/재탐색·전체cap은 SIM초다. 이 경로에는 계획 결과를 wall 시간으로 결정하는 timeout이 없다. 모든 새 후보에서 켠다.
- `reloc14_carry_budget_v1`: [fit](carry-budget-fit.json). 실패93266 모든3000틱(재탐색·partial epoch포함)을 비음수 선형 상계로 맞췄다. xy=.260783545+.099537834×명령거리(m); yaw(°)=4.522386264+20.584161984×명령회전(rad). 시간 항은 자유 변수로 두었으나 최적해0이다. runtime은 기록된 partial epoch를 빼고 full RGB fix 뒤 새 epoch를 쓴다. 정답은 runtime에 주지 않는다. 기존 과제20°로 트리거하며41°를 새 계수와 섞지 않는다. in-sample yaw≥20° 835/835 포착, holdout93315는고오차0틱이라 일반화 미입증이다. xy holdout940/940 상계 포괄. 이 값은 sigma가 아니며 학생 성공을 뜻하지 않는다.
- `reloc14_scene_v7`: 미병합 PR#519 브랜치의 정확한8개장면JSON을 SHA `34e5deb40caa58317ae9ec5e9ac934c8cf09a941`에서 가져왔다. [출처·파일해시](v7-scenario-source.json). 대상상자·위치·목적지는 같은 v7 order와 대조한다. heavy_crate는 생성되지 않는다. v6와 합산하지 않는다. 전역 기본 장면/기존 v6는 보존한다.

## 참고한 일차 자료

[Nav2 AMCL 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/amcl_node.cpp)의 shouldUpdateFilter, updateFilter, calculateMaptoOdomTransform: 이동 관문마다 필터를 갱신하고 map→odom을 다시 계산한다. 기존 PF의 .25m/.2rad는 이 구현의 기본값과 같다. 이 작업은 RGB 선분/경계 관측을 쓰며 LiDAR AMCL 구현 전체를 이식한 것은 아니다.

[ORB-SLAM2 Tracking::Track](https://github.com/raulmur/ORB_SLAM2/blob/master/src/Tracking.cc): 정상 추적과 LOST 상태의 Relocalization을 구분한다. 이 작업은 이 상태 분리를 적용하며 ORB-SLAM 전체 성능을 주장하지 않는다.

Mac에서는 비물리 단위 회귀만 실행한다. 원본 분석·물리·렌더는 gcp1/n4-highcpu-64에서 수행하며 Mac에는 요약·몽타주·실패 선택 프레임만 회수한다. 모델/학습/공용TOP제어0, weld OFF. 모든 실패/HOST_ERROR/cap_end를 보존한다.
