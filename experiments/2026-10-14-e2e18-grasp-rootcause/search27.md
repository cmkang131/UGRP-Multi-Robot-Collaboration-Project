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

## R1 — 초기화 HOST_ERROR, 물리 분모 없음

실행41f8b652e1726a85d2b0b90876226c9ff473bc57,
`gcp1:/home/ugrp/ugrp-sim/runs/search27-r1-short6-41f8b652`.
성공8312300의 v6 복사에 scenario ID/hash가 base로 남아 초기화에서 거부됐다.
HOST_ERROR1·감독중단5, 완료0·물리0·후보/프레임0. 외곽EXIT0은 성공 판정이 아니다.
먼저 만든 `search27-r1-rejection-table.json`은 이0개 관문과 전체 manifest 검증을 남긴다.
계획의 별도v6 ID/hash를 고치고 비물리 사전검사에6장면 전부를 추가했다.
R2부터는 endpoint와 full 검사 로그를 병합하지 않고 실제 passed_gates를 단계마다
기록한다. budget/cap으로 중단된 불완전 행은 이미 통과한 관문만 남긴다.

## R2 — 강제 IRM 전환의 회귀, 수정 전 표 보존

83479cc4f9caad813d53eec8077ce64ca36f4a44, 원본
`gcp1:/home/ugrp/ugrp-sim/runs/search27-r2-short6-83479cc4`.
성공1·교사실패3·cap_end1·감독중단1. 확정 완료5/6, base1/3·v6 0/2 완료,
v6 1건은 감독 중단이다. 원본 manifest 검증. 별도 렌더 분석 스크립트의 host_error_N1은
미완료를 포함하는 옛 분류라 재사용하지 않고 search27-r2-rejection-table.json의
supervisor_stop으로 분리한다. 이 표와 거부분포를 만든 뒤 R3를 수정했다.
blocked_goal8736 > unsafe_body_sweep1469 > blocked_retreat546 > first_command_invalid10.
첫 명령 필터가10개를 선택 전에 거부했지만 일반 성공률 개선 근거는 없다.

모든 정상 경로를 IRM으로 강제하면8312300/315709 v6에서도 −15도/.1932m를 선택해
정렬 무진전으로 끝났다. R3는 정상 경로 선택을 기존대로 복원하고 실제 최종 명령이
막힌 때만 동일 checker의 IRM fallback을 활성화한다. IK/jaw/ready를 완화하지 않는다.
315709 base는26.8s start invalid −3.110mm에서 검사된 단조 이탈1회를 발행했다.
그 뒤 시작 yaw 연결이 여전히 막혀26.9s에 전역 grid를 다시 채우다30wall초cap으로 끝났다.
기존98304 논리검사까지 간 결과가 아니며 checks53738, last_stage=body_edge였다.
R3는 invalid-start 복구 뒤에만 기존 cardinal .025 펄스로 yaw blocker 틈이 양 모형에서
증가하는 안전한 짧은 연결을 만든다. yaw를 향할 제자리 검사 통과 시 전역 계획에 복귀한다.
연결은 기존3SIM초 접근 인계로 제한하며, 실제 좌표는 수정하지 않는다.

매틱 중복 RGB 렌더는 첫 invalid-start의 같은 틱 자기 RGB 원본을 필요할 때 캡처하는
방식으로 줄인다. 해시·원본 경로·admitted band와 마지막 안전 명령은 유지한다.
평소 자기 검토 프레임은 기존 주기 그대로다. 시야 예측 행동은 바꾸지 않는다.

R3 추가: issued-arm sweep의 동일 PWM 기구학 cloud는 기존 cached_capsules를 재사용한다. 같은 입력의 거부·틈 동등성을 비물리 검사한다.

## R3 최종 — NOT_READY, 32회 대기열 없음

실행 **38dbd82e7ea5872452435c8142f9bf17e6534d7c**, 원본
`gcp1:/home/ugrp/ugrp-sim/runs/search27-r3-short6-38dbd82e`.
수정 소스9개는 이 실행 SHA와 바이트가 같다. 이후 변경은 분석/결과 기록뿐이다.
확정 완료5/6: **성공2, 교사실패2, SIM60초 cap_end1**; 나머지1은 감독 중단이다.
HOST_ERROR0이며 미완료를 성공/실패 분모에 소급하지 않는다. 외곽 EXIT0은 판정이 아니다.

|seed|장면|결과|SIM초|
|---|---|---|---:|
|315709|base|60SIM초 cap_end, episode_timeout|60.0|
|315709|cargo_v6|alignment_no_progress|47.1|
|8311709|base|approach_blocked_handoff|32.9|
|8311709|cargo_v6|repeated-cause 감독 중단, 최종 판정 없음|마지막 snapshot38.0|
|8312300|base|성공|22.5|
|8312300|cargo_v6|성공|22.6|

315709 base의37.3s 음수 틈 **−0.240247mm →37.4s +2.032812mm**를
발행 명령/보이는 대상만 재구성해 확인했다. 양 모형 body/arm 검사를 통과한 뒤로
최소 이탈 펄스1회를 발행했고, 이후 같은 음수 시작 상태의 반복 재탐색은 없었다.
이는 관측 기하 복구 결과이며 물리 접촉 해소/파지 성공 판정이 아니다.
같은 틱 원본 자기 RGB를 별도 보존·회수·해시 확인했다.
추가 yaw connector는 이번 물리 실행에서 발행되지 않았다(비물리 검사만 통과).

남은 문제: 그 뒤 실제 첫 발행 펄스가 band_blue 몸체 sweep에117회 거부돼
시간 안에 접근/파지를 끝내지 못했다. 98304 계산 예산 소진도53행 기록됐다.
v6는 정렬 무진전이다. 8311709 base는 후보가 blocked_goal/unsafe_body_sweep에
막혀 접근 인계, v6의 미완료 snapshot도 같은 기하 거부가 많다.
R3 전체 행(미완료 snapshot 포함): blocked_goal6214, unsafe_body_sweep2146,
first_command_invalid245, blocked_retreat130, planning_budget53, budget_incomplete1.
endpoint_feasible3042/feasible15는 거부가 아니며 독립 에피소드 수도 아니다.
단계별 실제 누적 통과·거부 수, 원본/재현 명령은
`search27-r3-rejection-table.json` 및 읽기 쉬운 `.md`, 상세는 `search27-r3-failure-causes.json`.

현재 관측/미래 예측은 원장만 분리했다. 새 NBV 행동·ready/jaw/IK 완화는 하지 않았다.
실패4장면 몽타주48개 자기 영상 표본을 직접 확인했다. 끝 색은 서로 다르며,
영상만으로 충돌/성공을 재판정하지 않았다. R3 회수 몽타주/실패 프레임52항목,
별도 최초 음수 RGB1장의 해시를 확인했다. R2 65항목도 확인했다.
GCP 세 라운드 전체 원본 manifest를 각각 검증했다. Mac에는 요약/몽타주/실패 프레임만 있다.
원본은 GCP 영속 디스크에 보존되며 호스트 밖 전체 raw 백업을 뜻하지 않는다.

입력 감사: 최종5건 invisible_measurements=0·held_world_reads=0,
감독중단1건은 unfinished snapshot까지0/0이다. GT 자기위치 비교off.
첫30SIM초 측정4건 wall/SIM 중앙3.538879(3.5 초과 기록 경고,6.0 미만).
성공2건은30초 전에 끝나 동시6 전체의 완전한 첫30 측정은 아니다.
비물리23통과, Mac 물리/렌더0·모델 호출0·학습RGB/ACT학습0·실물검증0.

**4/6 및315709 최소1성공 조건 모두 미달.** 3라운드를 소진해 추가 탐색을 내지 않는다.
32회 대기열·교사40회 관문·학습·기본 전환은 없음. 실험 결과를 이전 프로필이나
base/v6와 합치지 않는다. 최종 구조화 기록은 `search27-results.json`이다.

자기 search27 worker0·자기 임대3개 제거 확인. 공유VM 정지는 gcpctl의 다른 임대/프로세스 보호로 보류됐고 타 작업은 건드리지 않았다. 원본 삭제 없음. `search27-cleanup.json` 참조.
