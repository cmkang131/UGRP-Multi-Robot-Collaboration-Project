# crate12 — 정적 벽·펄스·자리 탐색과 교사 입력 경계 수정

2026-10-15, `claude/act-crate-teacher`, PR #500. 기준 측정 커밋은 `f2eb280a45c4ab51c1dd7f950ae210468bb821fc`; 먼저 `crate11-measure.md`와 `crate11-summary.json` 전체 및 `gt-leak-audit-bf31840f.md`를 읽었다. 최고 물리 기준 `bf31840f`의 **8/10은 이전 결과**다. 이 기록의 실행 소스는 이 파일을 포함하는 커밋이고, push 뒤 작성하는 대기열의 `sha`와 로컬 `outputs/e2e18-admin/crate12-audit/delivery.json`에 전체 SHA를 고정한다.

**이번 결과: 관련 테스트 88 passed, 기존 실패 9개/4,816개 명령의 OFF 재생 일치, 새 분기 확인. 새 물리 실행 0개.** 사각형 차체와 확대 후보를 함께 써도 저장 near_wall 시작의 양쪽 자리 가능성은 **0/11 실행, 0/8 고유 시드**다. near_wall을 제외하지 않았으며, 물리 불가능 또는 해결로 판정하지 않는다. 새 프로필과 이전 결과는 합산하지 않는다.

## 변경 묶음과 기본값

모든 새 동작은 기본 OFF다. `--crate-profile crate12_v1`이 아래 설정을 함께 켠다. 기존 기본값 `held_object=visible_v0`는 유지하되, 새 프로필에서는 명시적 `--held-object hidden_v1`이 없으면 시뮬레이터·출력 디렉터리 생성 전에 거부한다. 기본 카메라 배치·물리·질량 0.25 kg·lug 색·weld OFF는 유지했다. 공용 top 카메라는 제어 입력으로 쓰지 않는다. Mac에서 물리 시뮬레이션이나 렌더링을 실행하지 않았다.

| 설정 | 새 값 | 범위 |
|---|---|---|
| `static_walls` | `persistent_walls_v1` | 이미 가시성 검사를 통과한 정적 벽의 기억 만료 제거 |
| `crate_pulse_safety` | `crate_no_closer_v1` | 펄스 전체에서 초기 여유보다 가까워지지 않는 회전/후퇴 허용 |
| `crate_wall_footprint` | `crate_footprint_v1` | 벽에 대해 185 × 162 mm 차체·바퀴 외곽 사각형 + 5 mm |
| `crate_stances` | `crate_stances_v1` | 각도·거리 확대, 같은 대향 파지·IK·들기 하중 조건 적용 |
| `lookaround` | `setdown_lookaround_own_v2` | 자기 명령 추정 위치 + 같은 좌표계의 정적 벽으로 방향 결정, 자기 RGB 촬영 |
| `assignment` | `fixed_rgb_lugs_v1` | r1=청록, r2=파랑 번호표; 자기 RGB에서 자기 색 확인 |
| `release_channel` | `fixed_signals_v1` | 유한 신호만 전달, 상대 여유값 전달 금지 |
| `value_provenance` | `value_sources_v1` | 허용 출처 태그 검사; 누락/정답 출처 거부 |

개별 항법 토글도 OFF 기본이며, 새 차체/펄스 경로는 기존 `crate_approach_recovery_v1` 및 `crate_antipodal_grasp_v1`을 요구한다. 둘러보기와 고정 놓기 채널은 입력 출처 검사를 포함한 `crate12_v1`에서만 허용한다. 기존 빔/상자 경로는 토글 OFF로 남긴다.

### A1. 벽 기억

`VisibleWorld`에서 kind=`wall`에만 시간 만료 예외를 적용했다. 화물·로봇·손잡이의 기존 기억 수명과 재관측 규칙은 유지한다. 벽은 보였던 상대 측정과 자기 명령으로 만든 **로봇별 local odometry 좌표계**에 남는다. 정답 시작 자세를 사용해 전역 지도에 맞추지 않는다. 새 사각형 모드에서는 lug를 잃은 search/relook 중에도 이 벽 검사로 회전을 제한한다. 아직 보지 못한 벽을 이미 안다고 취급하지 않으며, 재관측/명령 오차로 벽 위치가 흔들리는 문제는 남는다.

`bf31840f/77978/r1`에서 5.2초 된 벽 기억이 유지되고, walls 단독 재생은 grasp 시작 후 12.3초(tick 123)에 이전 전진을 hold로 바꾼다. 벽 기억을 없애며 생겼던 목표 허용 분기를 막았다는 코드 근거이며, 실제 충돌 방지 성공은 미측정이다.

### A2. mm 허용 오차 대신 여유 비감소 규칙

임의로 1–3 mm를 허용하면 연속 펄스가 허용량을 누적해 장애물 안으로 들어갈 수 있다. 따라서 `_no_closer`의 **가까워지지 않는 이동만 허용**하는 원리를 택했다. 초기 중심-원판 거리와 원판+로봇 반경 중 작은 값을 펄스 전체의 하한으로 고정하고, wheel deadline 및 최대 5 ms 간격에서 각 직선 구간의 최소 거리를 계산한다. 수치 비교 오차는 1e-9 m이며 mm 허용량을 반복해서 빼지 않는다. 회전도 같은 검사를 통과해야 한다. 혼합 이동이 거부되면 기존 평행이동 후보 뒤에 목표를 향한 제자리 회전을 검사하고, 그것도 안전하지 않으면 hold다.

Nav2 공식 문서는 비원형 로봇의 실제 polygon footprint와 별도 padding, Collision Monitor의 운동 예측 검사를 설명한다. **Nav2가 `_no_closer` 또는 이 수치 규칙을 표준으로 정했다는 근거는 확인하지 못했다.** 이 선택은 프로젝트의 기존 margin-escape 규칙(`scripts/zone_teacher.py`, `sim/grasp_act_visible_route.py`)을 펄스 전체에 일관되게 적용한 설계 판단이다. Nav2의 padding은 외곽을 키우는 값이지, 장애물 침범을 허용하는 mm 오차가 아니다.

### A3. 차체 사각형과 확대 후보

`sim/crate_navigation_v12.py`가 벽에 대해 회전한 실제 차체·바퀴 외곽 사각형을 검사한다. 후보 선택→경로→waypoint→align/READY→실행 펄스까지 같은 벽 규칙을 사용한다. 원 기반 A*는 경로 제안만 하며, 제안 뒤 사각형 회전·이동 sweep을 다시 검사한다. 다른 화물·로봇의 원판과 여유는 유지했다. 경로 검사는 최대 2 mm/0.5°, 펄스 벽 검사는 1 mm/0.25° 표본이며 5 mm padding을 남긴다. 이는 샘플 기반 기하 검사이고 실제 위치 오차·팔 전체의 3차원 충돌을 검증한 결과가 아니다. peer 우회 일부는 기존 원 검사를 유지하므로 보수적으로 거부할 수 있다.

후보 각도는 0, ±5/10/15/17.5/20/25/30/45/60/75/89°로, 거리는 0.180–0.220 m로 넓혔다(명시 목록은 코드). 반대쪽 lug로 넘어가지 않으며 같은 `visible_grasp`의 집게 벌림·손가락/몸체·하강 IK 검사와 `plan_lift` 하중 검사를 모두 통과해야 한다. 저장 시작에서 각 로봇의 유효 파지 후보는 3개에서 27개로 늘었지만 벽 쪽 로봇의 벽 충돌 없는 후보는 여전히 0개다.

| 평가 전용 저장 시작 기하 | 양쪽 로봇 모두 벽 충돌 없는 후보 보유 |
|---|---:|
| 기존 실행의 고정 거리·0/±15° | 0/11 |
| 사각형만 | 0/11 |
| 후보 확대만 | 0/11 |
| 사각형 + 후보 확대 | 0/11 |

분모는 crate11의 near_wall 실행 11개이며 8개 고유 시드다. c5a76175의 77948/77949, 5644e3dd의 77968/77969, bf31840f의 77978/77979, 49d11b8e의 77988/77989와 재현 77969/77978/77979를 모두 포함한다. 중복 시드를 독립 표본으로 늘리지 않았다. crate11 표의 0.196/0.198/0.203/0.208 m 기하 탐색과 달리 위 `old`는 실제 Cartesian 실행의 고정 거리 `STATION_M`을 재현한다. 새 후보는 그 범위를 포함해 넓혔고 IK/하중을 추가 확인했다. 경로·동적 장애물·실제 통과는 이 표에서 평가하지 않았다.

## B. 정답 누설 감사와 수정 범위

1. **둘러보기:** 새 `OwnLookaround`에는 World·정답 자기 자세·상자 세계 자세를 전달하지 않는다. 이미 관측한 정적 벽의 모서리 방향을 자기 명령 추정 위치에서 계산하고 몸 회전/카메라 pan 후 실제 자기 RGB를 받는다. 정적 벽이 없으면 명시적으로 unlocalized scan을 한다. 예전 `GT + handoff_pose_error` 초기화와 GT 방위에 잡음을 더한 위치 보정은 새 경로에서 사용하지 않는다. 다만 현재는 **관측했던 벽으로 구성한 로컬 정적 지도**이며, authored 전역 지도에서의 영상 위치 추정기는 구현하지 않았다. `identified_landmarks=null`, `pose_updates=0`, RGB 해시와 예상 지형지물만 기록한다. 실제 랜드마크 검출 수나 위치 보정 성공을 만들지 않는다.
2. **놓기 스캔 범위:** strict 경로는 들고 있을 때뿐 아니라 놓은 뒤에도 `end_and_outward()`의 자기 FK/발행 명령/보였던 lug 신념으로 스캔 창을 정한다. 정답 상자 끝·축으로 창을 놓는 기존 분기는 실행하지 않는다. 센서 어댑터 내부의 실제 카메라 자세를 이용한 가시 상대 측정은 교사 예외로 남는다. `Eyes.classify`의 완전한 가시 바닥 분류는 실제 RGB 학생 인식과 같다고 검증되지 않았으며, 측정 z 규약도 이번 범위에서 바꾸지 않았다.
3. **기록 모드:** `--recording-mode training`은 hidden_v1·commands·새 둘러보기·고정 색 배정·고정 신호 채널을 먼저 검사한다. 정답 옵션 조합이면 거부한다. 적법한 조합도 아직 학생 RGB 기록기와 성공률 관문이 없으므로 `training recording not implemented/admitted`로 거부한다. 기록을 만들었다고 표시하지 않는다. 현재 진단은 success_measurement만 준비한다.
4. **배정:** 새 계획 생성/실행 경로에서는 `assign()`의 두 로봇 GT 시작 거리 최소화를 호출하지 않는다. 사전 고정 역할 r1=청록, r2=파랑이면 서로 다른 lug가 보장되므로 교사 배정에 거리 비교나 메시지 조율이 필요 없다. 맡은 색과 상자 몸체 색이 자기 RGB에 있어야 그 tick의 lug 측정을 허용한다. 자기 추정 위치는 이후 접근에 쓰며, 상대 추정 위치를 공유하지 않는다. 역할 배정의 효율·색 임계값은 잠정이다. 재현 3개의 원래 역할도 이 고정 역할과 같음을 확인했다. 새 시드 계획에는 처음부터 이 배정을 넣었다.
5. **PairReleaseCode:** 이전 API는 임의 `margin_m` 실수를 받아 정답으로 만든 값도 구별하지 못함을 확인했다. 새 채널은 `INSIDE/OUTSIDE/UNKNOWN/READY`와 `look/observe/lowered`의 유한 조합만 받는다. 여유·좌표·임의 phase 문자열을 거부하고, 한쪽 부족 신호에는 고정 0.08 m 이동만 제안한다. 현재 스캔 없는 값·부족한 하한값은 UNKNOWN이다. 불충분한 관측을 강제로 lower하지 않는다. 이 진단은 **fixed_signals_v1 통신 조건**이며 통신 없음/자연어 조건에 이 채널을 몰래 추가하는 경로가 아니다.
6. **값 출처 검사:** 이전 `AuditedTeacherInput`은 `robots.pose` 같은 합법 키 아래의 GT 실수를 통과시켰다(테스트 반례). 새 `Sourced`는 입력 생산 지점에서 의존 출처를 붙이고, strict 경계가 누락/`evaluation_gt`/`measured_joint` 및 중첩된 금지 출처를 거부한다. 반환값 복사로 소비자의 사후 수정을 차단하고 허용 출처별 수를 기록한다. held 시점에는 캐시된 상자 입력도 제거한다. **생산자가 GT를 거짓으로 `issued_commands`라고 태그한 경우를 수학적으로 탐지하는 장치는 아니다.** 생산 경로 코드 감사와 함께 써야 한다.

## C. 검증·재생·대기열

관련 파일 세 개만 실행했다. 출력 원본은 `outputs/e2e18-admin/crate12-audit/tests.log`, JUnit은 `tests.xml`; 해시는 `crate12-summary.json`에 있다. 통과 줄을 확인한 뒤 커밋한다. 새 테스트를 기존 CI 파일 목록에도 등록했다. 원격 CI 통과를 이 로컬 검사로 대신 보고하지 않는다.

```text
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_crate12.py tests/test_crate_approach_recovery.py tests/test_grasp_act_goal_set.py \
  --junitxml=/Users/changmin/projects/ugrp/outputs/e2e18-admin/crate12-audit/tests.xml
88 passed in 1.27s
```

`crate12_replay.py`는 저장된 가시 측정과 실제 발행 명령 이력으로 교사만 재생한다. OFF에서 실패 9개의 4,816개 robot-command, phase, done이 일치했다. 새 분기에서 즉시 끊으므로 이후 원본 관측을 반사실적 물리 결과로 쓰지 않는다. 전체 outcome 성공 여부, RGB 색 배정, 놓기·둘러보기는 이 재생에 포함하지 않았다. pulse 모드는 bf31840f에 없던 기존 recovery 토글도 켜므로 그 SHA에서는 순수한 펄스 단일 변수 비교가 아니다.

| 저장 실행 | walls 단독 최초 차이 | pulse/bundle 최초 차이 (grasp 경과초) |
|---|---:|---|
| bf31840f diag 77978 | 12.3 | 12.3, 벽 접근 hold |
| bf31840f diag 77979 | 없음 | 8.9, no_closer_yaw |
| 49d11b8e diag 77981 | 없음 | 10.0, r1 hold→회전 |
| 49d11b8e diag 77982 | 없음 | 11.0, r2 hold→회전 |
| 49d11b8e diag 77988 | 없음 | 13.5, no_closer_yaw |
| 49d11b8e diag 77989 | 없음 | 12.0, no_closer_yaw |
| 49d11b8e 재현 77969 | 없음 | 4.9, no_closer_yaw |
| 49d11b8e 재현 77978 | 없음 | 저장 구간에서 명령 차이 없음 |
| 49d11b8e 재현 77979 | 없음 | 8.9, no_closer_yaw |

재생/near_wall에 사용한 13개 실행의 저장 파일 78개를 각 실행 `SHA256SUMS`와 비교해 불일치 0개, manifest 누락 0개였다. 입력은 `outputs/gcp1-runs/<run>/raw/`. 새 상세 결과는 `outputs/e2e18-admin/crate12-audit/replay.json.zst`; 재해제한 전체 해시도 확인했다. 압축 결과와 입력별 해시는 요약 JSON에 있다. 원본 로그·영상은 Git에 넣지 않았고 별도 원격 백업을 새로 확인하지 않았다.

기존 bf31840f 77978/77979의 저장 contact sheet를 각각 처음·중간·끝 8시점씩 열었다. pair overview는 작아서 양 로봇의 파지 관계를 그것만으로 확정하지 않았다. 49d11b8e의 이번 변경에 대한 새 물리 원인이나 영상 성공을 주장하지 않는다. 이번 분기 판단의 근거는 저장 입력·명령 원장이다.

새 대기열은 `crate12_queue.py --sha <전체SHA>`로 **clean push 확인 후 한 번만** 생성한다:
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-crate-diag-<SHA8>.json`.

- 재현 N=3: 77978(bf31840f), 77981/77982(49d11b8e). 저장 계획을 그대로 복사하고 소스 해시를 보존했다. 개발용 분모이며 새 시드와 합산하지 않는다.
- 처음 쓰는 진단 N=10: 77990–77999, near_wall=77998/77999 **2/10=20%**. 계획 기하만 생성했다. 기존 로컬 계획·대기열 seed 필드와 회수한 GCP 실행 이름에 사용 이력이 없었다. GCP 원격 조회는 SSH ProxyCommand의 `gcloud compute instances describe --project ugrp-act-train-1014` 오류로 실패하여 **원격 미사용/예약 여부는 미확인**이다.
- 새 계획은 start_assigned_los=off이며 LOS/렌더 검증을 Mac에서 수행하지 않았다. 고정 색 배정과 이 시작 분포 차이를 기록한다. 실행 결과를 본 뒤 near_wall이나 실패 시드를 교체하지 않는다.
- 대기열 전체/각 run은 `runs_enabled=false`, 진단 admission 대기다. `coordinator_approval.approved=false`, 관문 작업 0개·관문 미승인. 원격 시드 예약·크레딧 정지·디스크·동시 수·실제 부하 첫 30 SIM초 속도 검사를 운영 담당자가 확인해야 한다. 진단 결과가 좋아도 자동 관문 승격은 없다.
- 기존 대기열을 수정하지 않는다. 생성 전 모든 기존 JSON의 해시를 새 파일에 기록하고 생성 뒤 동일함을 검사한다. 실행은 GCP gcp1 동일 머신 종류에서만, 상한/정지 장치를 유지한다. 이번 작업은 제출·VM 시작·시뮬레이션 실행을 하지 않았다.

## 참고 자료와 미확인 인용

1. [crate11 측정](crate11-measure.md), [crate11 전체 요약](crate11-summary.json), `crate11_table2.py`, 기준 `f2eb280a`: 저장 원본의 층 구분·분모. 숫자를 새 물리 측정으로 재분류하지 않았다.
2. `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gt-leak-audits/gt-leak-audit-bf31840f.md`: bf31840f 읽기 전용 감사. 이 문서의 당시 행 번호는 새 코드와 다르다. 입력 파일 SHA-256은 새 요약에 기록했다.
3. [Nav2 Costmap 2D](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/costmap_2d/), 2026-10-15 조회: footprint polygon, footprint_padding 기본 0.01 m, 상태에 따른 footprint 갱신. 이번 **0.005 m는 자체 진단 후보**이며 Nav2 기본값이나 검증된 실물 오차가 아니다.
4. [Nav2 Footprint 설정](https://docs.nav2.org/rolling/configuration_and_development/first_time_robot_setup_guide/footprint/setup_footprint/), 같은 날 조회: 비원형 로봇의 local trajectory에는 실제 polygon 사용을 권한다. 기존 원 A* 뒤 polygon sweep 검증 설계의 참고다.
5. [Nav2 Collision Monitor](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/collision_monitor/configuring_collision_monitor_node/), 같은 날 조회: stop/slowdown/limit/approach와 운동 예측 timestep 설명. Nav2 실행·벤치마크를 수행한 것은 아니다.
6. `sim/masterpi_geometry_v3.py`의 외곽 185 × 162 mm, `harness/static_keepouts.py`의 polygon/sweep, `scripts/zone_teacher.py`의 `_no_closer`: 로컬 소스 확인. **미확인 인용:** 형상 모듈이 인용하는 제조사 도면의 최신 원본·실물 오차는 이번에 재측정하지 않았다. “Nav2가 mm 비감소 탈출을 표준으로 보증한다”는 인용은 확인되지 않아 사용하지 않았다.

현재 판정은 **코드/오프라인 분기 검증 완료, 물리 효과·near_wall 해결·학생 기록·관문 not-ready**다. authored 지도 위치 추정과 실제 RGB 지형지물 검출, 새 프로필의 GCP 성공률은 남아 있다.
