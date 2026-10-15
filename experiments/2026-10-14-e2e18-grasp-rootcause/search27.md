# search27 — 현재 자세/실제 발행/의존성별 실패 certificate

기준 소스 09a44ffa2a1c0a62ed3da21fac53dd6c3a2f209d, search26 실행
f92b07aa869dc3b960d22adb69c01f2b9b8c9eeb. 조사 보고서
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/research/search.md`의 1→2→3순서를 따른다.
수정 전 분포/순차 후보·프레임·이벤트 관문은 `search27-baseline-rejection-table.md`.
원본 gcp1 `/home/ugrp/ugrp-sim/runs/search26-comparison32-f92b07aa`.
base 완료8/예정16: 성공5, blocked_goal13858, unsafe_body_sweep8489.
v6 완료8/예정16: 성공5, cap_end1. 두 장면·미완료 감독정지 분모를 합치지 않는다.

GCP에서 visible+issued만 재구성한 `search27-baseline-first-invalid.json`:
315709/base r1 최초 음수는37.3s, −0.240247mm. 직전37.2s에는 band가 기억 창에서
사라졌고 yaw 6.434607→6.475498의 최소 회전 펄스가 발행됐다. 새 band 형상을
직전 자세에 놓으면 +1.334040mm, 현재 자세에서는 음수다. 이전 형상에는 beam이 없어
현재 자세도 +242.742559mm다. 새 관측/발행 yaw 둘 다 관여하며, 물리 접촉 확정이나
teacher hint/free-space 전체 재생은 아니다. 좌표를 고쳐 쓰지 않는다.

## 기본 off 후보

- `search_command_feasible_v1`: 현재 body/arm 상태를 IRM 루프 밖에서 검사한다.
  음수는 start_geometry_invalid로 분리하고 last-safe 발행·발행 자세·새 RGB hash·
  admitted band·실제 footprint/proxy를 함께 기록한다. IRM endpoint 단계에서
  아직 없는 경로의 중복 start→start 목표응시 회전을 검사하던 결함을 제거한다.
  endpoint→연결 경로→첫 wheel pulse→최종 발행에 같은 몸체/팔 함수를 쓴다.
  무효 start는 기존 .025 속도 cardinal 이탈 펄스만 비교한다. 양 issued 모형,
  wheel deadline 전체에서 기존 blocker 틈의 단조 증가와 다른 장애물의 기존
  sampling envelope 및 팔 sweep을 요구한다. disc/box 거리의 초기 방향도함수를
  검사한다. rectangle 겹침·회전 이탈·팔 겹침은 복구하지 않고 기존 SIM 인계로 끝낸다.
- `search_dependency_cache_v1`: 같은 body 입력/edge, connector view/arm의 통과·실패를
  정확한 의존 키로 재사용한다. world t만 제거하고 freshness, 관측 세대(seen_t),
  geometry, margin, PWM와 입력을 포함한다. 새 관측·장애물 추가·profile 변화에 재개방.
  입력 반올림·임의 TTL 없음. 캐시 상한4096은 기존 search20 용량을 재사용한다.
  몸체 grid/edge, connector, pick cloud 호출·hit를 남기고 cold/warm logical charge를 유지한다.
- `search_view_evidence_v1`: 현재 admitted observation·미래 prediction·아직 오지 않은
  실제 다음 observation을 별도 원장에 쓴다. 새 NBV 행동은 넣지 않는다.
- `search27_frame_v1`: 카메라의 실제 비대칭 K-pinhole와 fisheye 프레임 교집합을 쓴다.
  내부값은 sim/masterpi_camera_profile.py의 기존 실측값이며 임의3도 여유를 더하지 않는다.
  GCP saved-state render/OpenCV parity 뒤에만 후보에서 켠다.

새 후보는 기존 기본off `search25_checks_v1`(98304 논리검사, wall30초는 cap_end만),
`search25_memory50_v1`(평가전용 N5287의 p90 반올림50mm, 초과5.4%)도 켠다.
soft inflation의 기억50mm는 경로 비용 여유이며 실제 겹침을 허용하는 문턱이 아니다.
집게각·IK pulse·60mrad ready·카메라 배치/화각·ACT 학생은 변경하지 않는다.

## 검증/예산

비물리 관련 파일만 최소 검사. GCP n4-highcpu-64에서 실패315709 base/v6,
8311709 base/v6, 기존 성공8312300 base/v6 순서6회, 동시6·서버전체≤40,
60SIM초·최대3라운드. 각 라운드 결과/관문표/거부분포를 먼저 만들고 다음 수정을 한다.
학습RGB·모델호출·ACT학습·Mac 물리/렌더는0. 4/6 이상이면서315709 하나 이상 성공일 때만
동시16·실패시드우선32회 검토 대기열을 쓴다. 전체 source_sha와 존재하는 절대경로
rejection_table 필수. 교사95%/40 관문·본 연구·실물 성공과 별개다.

## 조사 출처 (2026-10-15 직접 열람)

- https://moveit.picknik.ai/humble/api/html/fix__start__state__collision_8cpp_source.html
  MoveIt Humble FixStartStateCollision: invalid start를 먼저 분리. 좌표 perturb는
  issued pose에 적용할 수 없어 실제 검사한 이탈 명령만 발행하도록 바꿨다.
- https://docs.nav2.org/jazzy/configuration_and_development/tuning_guide/
  Jazzy footprint/inflation 분리. 로봇 footprint를 실제 실행 검사에도 동일하게 적용.
- https://ompl.kavrakilab.org/classompl_1_1geometric_1_1LazyPRM.html
  LazyPRM 유효성/graph 분리. 새 관측에서 validity 재개방, 정확한 의존성만 재사용.
위 방법의 외부 성능을 우리 성공률·물리 안전 보장으로 옮기지 않는다.
