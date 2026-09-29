# 공동 운반 하네스의 통로 지도 지원 (코드 준비, 물리 미실행) (2026-09-29, Claude)

**물리 시뮬은 한 번도 돌리지 않았다.** 이 기록은 통로 지도에서 경로·leg를 만들고 stage probe로 "통로 통과" 구간을 지정해 돌릴 수 있게 한 **정적 계획 코드**와 그 단위 테스트, 그리고 물리 측정 계획이다. 통로를 두 로봇이 빔을 들고 실제로 지나가는지는 측정하지 않았다. 통과 성공도, 학생 성공도 아니다.
제어기에는 정답(GT)·시뮬 상태를 넣지 않는다. 계획은 정적 지도 JSON과 코스 주문서(sheet)만 읽는다(AGENTS.md의 정적 지도 예외). 이 PR은 제어기 코드를 바꾸지 않는다.

Refs #221. 배경: [b-v6c 운반 stage probe](../2026-09-29-pair-v6c-carry/README.md)의 "한계"에 통로·지형 조건을 측정하지 못했다고 적혀 있었다.

## 한 줄 요약

- **막는 것 네 가지를 찾았다.** (1) `make_plan`이 `door_1`(0.5 m, x=2.2)만 받는다. (2) `ZoneOwnExecutor`가 door 종류 통로가 없는 지도에서 아예 만들어지지 않는다(통로 지도 `StopIteration`). (3) 고정된 상태 프로토콜의 구간 상한 8. (4) 통로 폭·경로를 검사하는 코드가 없다.
- **통로 지도(`zone_wide_corridor_tags_v3`)에서 영역 A까지는 경로가 만들어진다**(8 leg, 폭 검사·SweepGuard 여유 통과). **영역 B·C는 11·12 leg라서 명시적으로 거절한다**(`PAIR_PASSAGE_TOO_MANY_SEGMENTS`). 프로토콜 상한을 바꾸지 않았다.
- 지형(`terrain`)은 zone 지도에 하나도 없어 실제 지형 통과는 다루지 않는다. 지형 항목이 경로에 걸리면 피하거나(회피 경로가 없으면) 명시적으로 거절한다.
- 기본 동작은 그대로다. 기본 plan·probe case는 골든 해시로 원본 main과 바이트 같음을 테스트한다.

## 버전

| 항목 | 값 | 이유 |
|---|---|---|
| 실행 번들 / workflow | **번호를 쓰지 않았다** | v81 / workflow 2.14.0은 b-v6e 몫. 통로 지원을 제어기에 채택할 때 그 등록에 함께 넣는다 |
| main 기준 | `45a21b23` | 번들 v80, workflow 2.13.0 |
| PROBE_VERSION | **올리지 않았다**(0.5.0 그대로) | b-v6e 브랜치가 0.6.0으로 올린다. 이 PR의 probe 변경은 opt-in 인자·필드뿐이고 기본 case는 바이트 같다. 나중에 병합되는 쪽이 올린다 |
| 실행 소스 | 이 PR의 커밋. 물리 측정 전에 다시 고정한다 | 측정은 아직 없다 |

**executor 파일을 고치지 않았다.** `harness/zone_pair_executor.py`, `harness/zone_own_executor.py`, `harness/zone_own_team_host.py`는 등록된 v6 계열 원천 닫힘(`scripts/zone_pair_v6_contract.py contract()`)이 해시로 고정한다. 하나만 바꿔도 `tests/test_zone_pair_registered_source.py`의 v6d DRAFT 영수증 검사가 깨지고, 그것을 다시 봉인하는 것은 새 번들 등록(b-v6e 몫)이다. 그래서 opt-in을 새 파일에 두고 probe 프로세스 안에서만 켠다(아래 '설계').
executor에 직접 넣을 36줄 패치는 [adopt_in_executor.patch](adopt_in_executor.patch)로 보존했다(`git apply --check` 통과. 적용한 상태에서 `test_zone_pair_executor.py`·`test_zone_own_executor.py`와 이 PR의 테스트가 통과하고, "executor 미수정"·"executor 생성 실패" 두 테스트만 뒤집힌다. 채택 때 그 두 테스트를 고친다).

## 무엇이 막았나 (근거 코드 위치)

| # | 막는 곳 | 증상 | 이번 처리 |
|---|---|---|---|
| 1 | `harness/zone_pair_executor.py` `make_plan` 46–48행: `door_1`, 중심 (2.2, 0.05), 폭 0.5만 | 통로·두 문 지도는 `UNSUPPORTED_PAIR_MAP`. PairTeam은 이를 `INVALID_PAIR_PLAN`으로만 돌려준다 | 새 경로 생성기 `plan_passage_route`. `make_plan`은 안 고치고 opt-in 시 감싼다 |
| 2 | `harness/zone_own_executor.py` 134행 `next(p for p in passages if p['kind'] == 'door')` | door 종류가 없는 통로 지도(kind `corridor`)에서 **로봇 executor 생성이 `StopIteration`으로 실패**한다. 하네스가 통로 지도로는 시작조차 못 한다 | probe 전용 `executor_view`(별칭 door 항목 추가). 테스트가 원인과 회피를 둘 다 고정한다. 근본 수정은 패치에 있음 |
| 3 | `harness/zone_pair_status.py` `MAX_SEGMENTS = 8` (상태 enum이 구간별로 만들어짐) | 통로→A 8 leg, →B 11, →C 12. 초과하면 거절 | 명시적 `PAIR_PASSAGE_TOO_MANY_SEGMENTS`. 상한은 바꾸지 않음 (사용자 결정 필요) |
| 4 | `make_plan`은 문 축 y=0.05를 하드코딩하고 통과 폭을 따로 검사하지 않는다(경로 표본 충돌만 봄) | 통로는 축 y=1.175, 앞에 옆 이동이 필요하고, 뒤 옆 이동은 통로 끝 벽을 지난 뒤에만 가능 | 축 계산, 폭·여유 검사, 탈출 x 계산 |
| — | `SweepGuard`(`harness/zone_own_guards.py`)와 leg별 축 정렬(`M2DoorStudent.door_schedule`) | **막지 않는다.** `static_boxes(static_map)`는 지도 장애물 전부를 읽고, `door_schedule`은 leg 시작 y를 축으로 쓴다(`RoutedM2.door_schedule`이 `axis_y_m = a[1]`로 덮어씀) | 그대로 재사용. 여유는 오프라인으로 같은 객체로 계산해 보고 |

### 통로가 문과 달라지는 점

- 축이 y=1.175이고 빔이 시작하는 y=0과 1.125 m 떨어져 있다. 픽업 쪽에서 **옆 이동 leg 2개**로 먼저 축에 올라간다(문은 y=0.05라서 축 정렬 한도 0.15 m 안이라 옆 이동이 필요 없다).
- 통로는 x 2.2–3.925(1.725 m)이다. 빔+캐리어 봉투가 x ±0.625 m이므로 **빔 뒤 끝이 통로 끝 벽을 벗어난 뒤에야 옆으로 움직일 수 있다**(탈출 x = 3.925 + 0.625 + 0.05 = 4.60 m). 문(0.05 m 두께)은 3.20 m면 됐다.
- 통로 남쪽 벽에 대피소(`bay_1`)가 열려 있다. 대피소는 경로가 아니라(kind `passing_bay`) 제외하고, 빔은 y≥0.975라서 대피소 벽(y≤0.925)과 겹치지 않는다.

## 재사용한 것

| 필요 | 재사용 | 새로 만든 것 |
|---|---|---|
| 장애물·지형·봉투 겹침 검사·경계 | `harness/map_goto.py` `authored_obstacles`(지형은 `unvalidated_`로 회피), `envelope_overlaps`, `interior_bounds`, `MARGIN_M` | — |
| 도달 가능성 | `harness/map_goto.py` `plan_path` (8방향 A*, 고정 자세 봉투). 통로 통과 여부 교차 확인용 오라클 | 얇은 호출 `_astar` |
| 제어기 여유 | `harness/zone_own_guards.py` `SweepGuard.chassis_clearance`·`margin`·`OwnPose` (비행 중 가드가 쓰는 같은 객체) | 통로 위 표본 스캔과 이분법 |
| 계획 조립 | frozen `make_plan` 자체(M2 문 지도에서 호출해 시트 검증·prestation·keepouts·빔 형상 재사용) | 경로·door_plan·map 해시만 교체 |
| leg 실행 | frozen M2 제어기 `RoutedM2`(축 방향·옆 방향 leg, 매 leg 시작 자기 추정 축 정렬, 0.85 m 분할) | — |
| 폭 기준 | `make_plan`의 봉투 `x±0.625, y±0.20`(테스트가 소스와 일치를 고정) | 폭 검사 함수 |

새 코드는 `harness/pair_passage_plan.py` 하나와 테스트다. 기존 파일 변경은 `pair_stage_probe.py`(옵션 인자 3줄), `run_pair_stage_probes.py`(옵션 인자·기본값 동일 분기), `run_ci_tests.py`(테스트 1줄)뿐이다.

## 설계

`harness/pair_passage_plan.py`:

- `traversable_passages(map)` 문·통로만(대피소 제외). `measured_opening(map, passage)`은 지도에 적힌 폭이 아니라 **장애물로 실제 열린 폭**을 통로 구간 전체에서 재고 가장 좁은 곳을 돌려준다(통로는 x=2.2의 divider와 벽 사이 0.5 m).
- `required_width(axis)`: 빔이 통로를 따라가면(축 x) 봉투 y 폭 0.40 + 여유 2×0.02 = **0.44 m**. 통로가 y 축이면(옆으로 가로지름) **빔 길이와 두 로봇 간격**인 봉투 x 폭 1.25 + 0.04 = **1.29 m**.
- `check_passage`: 적힌 폭과 반폭 일치, 실측 폭 ≥ 필요 폭, 중심선이 열린 폭의 가운데인지. 어긋나면 사유 코드로 거절한다.
- `guard_slack`: 빔이 통로 중심선에 있을 때 두 캐리어 차체의 SweepGuard 여유(E2E 사전분포 σ 0.03 m·0.012 rad)와 그 여유가 0이 되는 최대 σ_xy·전체 자세 yaw. 차체만 본다(팔·빔 스윕, 하중 게이트 정지는 모델링하지 않음).
- `plan_passage_route(map, pose, target, passage)`: 정리한 축 경로 = (옆 이동으로 축 진입) → 통로를 따라 탈출 x까지 → (옆 이동, 축 이동)으로 영역까지. 0.85 m로 나눈 뒤 구간 수·봉투 스윕 충돌·가드 여유를 검사한다. 통로가 하나뿐인 `door_1`(M2 문)이면 `None`을 돌려 frozen 경로를 그대로 쓴다. 두 문 지도의 `door_narrow`는 M2 문과 기하가 같아 **frozen 경로와 같은 점열**이 나온다(테스트로 고정).
- `passage_legs(route, info)`: probe `--legs`에 넣을 leg 역할(`lateral_to_axis`, `entry`, `inside`, `exit`).
- `passage_make_plan` / `install(passage)` / `uninstall()`: **프로세스 안에서만** `zone_pair_executor.make_plan`을 바꿔 끼우는 opt-in. 기본은 아무것도 설치하지 않는다. 거절은 `REFUSALS`에 남는다(executor 쪽 ack는 옛 `INVALID_PAIR_PLAN`).
- `executor_view(map)`: 위 2번 막힘의 probe 전용 회피(별칭 door 항목). 계획과 map 해시는 별칭을 무시한다.
- `passage_teacher_cases` / `passage_setup`: stage probe `teacher_cases(setup=…)`용 설정. case에 `map`, `pair_passage`, `target` 필드를 넣고 case id에 `:M<지도>`를 붙인다.

### 사유 코드

| 코드 | 뜻 |
|---|---|
| `PAIR_PASSAGE_NONE` / `_UNKNOWN` | 지도에 문·통로가 없음 / 지정한 id가 없음 |
| `PAIR_PASSAGE_TOO_NARROW` | 실측 폭이 필요 폭(0.44 m, y 축은 1.29 m) 미만. 지형이 통로를 좁혀도 이 코드 |
| `PAIR_PASSAGE_AXIS_UNSUPPORTED` | 폭은 충분하지만 y 축 통로는 아직 경로가 없음 |
| `PAIR_PASSAGE_MAP_INCONSISTENT` | 적힌 폭·중심이 벽과 맞지 않음 |
| `PAIR_PASSAGE_PICKUP_TOO_CLOSE` | 빔이 통로 입구에 너무 가까이 있음 |
| `PAIR_PASSAGE_TOO_MANY_SEGMENTS` | leg가 프로토콜 상한 8을 넘음(통로→B 11, →C 12) |
| `PAIR_PASSAGE_ROUTE_BLOCKED` / `_ROUTE_CROSSES_UNVALIDATED_TERRAIN` | 축 경로의 봉투가 벽 / 지형에 걸림 |
| `PAIR_PASSAGE_GUARD_MARGIN` | 사전분포 σ에서 SweepGuard 여유가 음수 |
| `PAIR_ROUTE_OUTSIDE_MAP` | 봉투가 지도 안쪽 경계를 벗어남 |
| `PAIR_PASSAGE_NONE_USABLE` / `PAIR_NO_PATH_FOR_PAIR_ENVELOPE` | 후보 전부 거절: A*는 길을 찾았다(축 경로만 없음) / 봉투가 어디로도 못 감 |

## 계획 결과 (정적 계산, 물리 아님)

`python -m harness.pair_passage_plan --map zone_wide_corridor_tags_v3 --target A` (시트 빔 (1.0, 0.0, 0)):

| 항목 | 값 |
|---|---|
| 통로 | `corridor_1`, 축 y=1.175, x 2.2–3.925, 적힌 폭 = 실측 폭 0.500 m (구속 구간 x=2.2, 아래 divider·위 북쪽 벽) |
| 필요 폭 / 한쪽 여유 | 0.44 m / 0.030 m |
| 경로 | (1.0, 0.0) → (1.0, 0.5875) → (1.0, 1.175) → 축 방향 5 leg 각 0.72 m → (4.6, 1.175) → (4.6, 0.4) (영역 A 중심) |
| leg | 8 (상한 8), 총 5.55 m. 역할: 옆 이동 0·1, 진입 2, 통로 안 3·4·5, 탈출 6, A로 옆 이동 7 |
| A* 교차 확인 | 봉투 A*가 5.14 m로 `corridor_1`을 지난다(같은 통로) |
| SweepGuard 여유 (σ 0.03 m·0.012 rad) | 최소 0.061 m. 여유가 0이 되는 σ_xy = 0.060 m(σ_yaw 고정), 전체 자세 yaw 오프셋 0.223 rad(σ 0) |
| 참고: M2 문 `door_1` 같은 값 | 최소 0.061 m, σ_xy 0.060 m, yaw 0.229 rad |

- **폭 0.5 m 통로는 문과 같은 폭이라 차체 여유는 문과 같다.** 새로운 위험은 폭이 아니라 **통로가 길다는 것**(1.725 m, 문은 0.05 m)이다: 빔 자세 오차가 쌓일 시간이 길다. σ_xy가 0.060 m를 넘으면 SweepGuard가 세운다(하중 게이트 0.07 m보다 먼저).
- 두 문 지도(`zone_wide_two_doors_tags_v3`): `door_narrow`(0.5 m, 한쪽 여유 0.03)는 자동 선택되고 영역 A·B·C 모두 M2 문 경로와 같다(테스트). `door_wide`(1.0 m, 여유 0.28)는 폭은 되지만 픽업 y=0에서 y=−2.625까지 가는 옆 이동 때문에 leg가 8을 넘어 거절된다.
- 영역 B·C(통로): 각각 11·12 leg. 픽업 옆 이동 2 + 축 방향 5(3.6 m를 0.85 m 이하로 자름) + 영역까지 옆 이동·축 이동.

### 지원 범위

| | 상태 |
|---|---|
| 축 x 통로·문(빔이 통로를 따라감), 빔 요 0 | 지원 |
| 통로 지도 → 영역 A | 지원 (8 leg) |
| 두 문 지도 `door_narrow` → A·B·C | M2 문과 같은 경로 (지원, 6·8·6 leg) |
| 통로 지도 → 영역 B·C | **미지원**: 명시적 거절. 프로토콜 상한 필요 |
| 통로 지도 `door_wide` (두 문) | **미지원**: leg 초과 |
| 축 y 통로(빔이 옆으로 가로지름) | **미지원**: 폭 1.29 m 미만이면 `TOO_NARROW`, 이상이면 `AXIS_UNSUPPORTED` |
| 지형 위 운반 | **미지원**: 지형은 회피 대상으로만 다룬다 |
| 회전한 빔, 대각선 이동 | 미지원(M2 제어기가 축 방향·옆 방향 leg만 안다) |
| 최종 환경(태그 0, 통로 위치 미상) | 이 코드는 정적 지도가 있다고 가정한다. 태그 없는 위치 추정은 별개다 |

## 검증 (물리 없음)

`tests/test_pair_passage_plan.py` 43건 통과. 함께 돌린 관련 테스트 통과: `test_pair_stage_probe.py`, `test_zone_pair_executor.py`, `test_zone_pair_registered_source.py`(v6d 영수증), `test_map_goto.py`, `test_zone_pair_v6c/v6d.py`, `test_zone_pair_admission.py`, `test_zone_pair_review*.py`, `test_pose_provider_boundary.py`, `test_harness.py` (합계 위 두 묶음 562건, 전체 CI는 돌리지 않음).

| 검증 | 테스트 |
|---|---|
| 기본 동작 불변 | M2 문 지도의 plan 해시(B·A)와 probe case 해시(carry L1, setdown end, align)가 수정 전 main에서 계산한 골든과 같다. executor·team host 파일에 `pair_passage` 없음. runner 기본 spec의 order가 이전과 같다 |
| 지원 안 함 → 지원됨 | 통로 지도 `make_plan` = `UNSUPPORTED_PAIR_MAP`, opt-in = 8 leg 경로. `install` 뒤 PairTeam이 통로 지도 주문을 받아들이고, 설치 전에는 `INVALID_PAIR_PLAN`으로 거절한다 |
| 지도 로드·폭 | 통로·두 문·문 지도 로드, 대피소 제외, 실측 폭 = 적힌 폭(0.5, 0.5, 1.0, 0.5), 구속 구간이 대피소 아닌 곳 |
| 폭 검사 경계 | 폭 0.50·0.45·0.44 통과, 0.43·0.40 거절(필요 0.44, 실측 값 함께). y 축 통로 필요 폭 1.29. 적힌 폭 불일치 거절 |
| 경로·leg | 축 정렬, ≤0.85 m, 8 leg, 마지막 점 = 영역 A 중심, 나머지 plan 필드는 frozen plan과 같음, leg 역할, A* 교차, `door_narrow` 경로 = frozen 경로 |
| 거절 코드 | B·C `TOO_MANY_SEGMENTS`, 지형이 경로에 걸림 / 통로 안 / 경로 밖, 후보 전부 거절 시 `NONE_USABLE` 대 `NO_PATH` |
| SweepGuard 여유 | 통로 = 문 값, 통로가 좁아지면 σ 허용·yaw 허용이 줄어듦 |
| probe 지원 | `plan_route`, `passage_teacher_cases`(leg 3: 시작 빔 (1.72, 1.225), 두 캐리어 여유 > 0.05 m, 기본 case에 passage 없음), `--passage-map` 인자, CLI, 오류 코드 |
| executor 막힘 | 통로 지도에서 `ZoneOwnExecutor`가 `StopIteration`, `executor_view`로는 만들어짐. 별칭은 계획·map 해시가 무시 |

또 `run_pair_stage_probes --passage-map … ` 계획 전용 실행(MuJoCo 없음)으로 case 목록이 만들어지는 것을 확인했다(아래 명령 40건). `make_scene`으로 통로 지도의 scene 설정이 풀리고(`static_map` 해시 = 파일) 물리는 만들지 않는 것도 확인했다.

## 다음 stage probe 계획 (실행하지 않음)

**선행 조건:** b-v6e 측정 종료와 `agent_lock` 해제(`python3 scripts/agent_lock.py status`), 이 PR의 소스 커밋을 코호트 동안 고정, 정책 결정(b-v6e 채택 시 그 정책, 아니면 `b-v6d`), 실행 전 `uptime` 부하 기록. 등록 소스에 executor 패치를 넣는 경우(채택)는 새 번들에서 다시 봉인한다.

**"통로 통과" 단계** = carry stage의 leg 지정이다. 통로 지도 → 영역 A에서:

| leg | 역할 | 무엇을 보나 |
|---|---|---|
| 1 | 옆 이동, 축 진입 직전 | 통로 입구 정렬 (참고) |
| **2** | 진입 (빔 동쪽 끝이 통로에 들어감) | 통로 입구 벽 여유. 축 정렬 후 횡 오차 |
| **3** | 통로 안 | 통로 안 직진, 횡 오차 vs 한쪽 여유 0.05 |
| **6** | 탈출 (빔 뒤끝이 통로 끝 벽을 벗어남) | 탈출 뒤 벽 접촉 |
| 7 | 통로 밖 옆 이동 (영역 A로) | 참고 |

셀(`--cells`): `nominal`(seed 911·912·913), `lat+/same`, `lat-/same`, `yaw+/same`, `yaw-/same`, `corner--/same` (v6c 격자의 허용 경계. along 셀과 corner++ 셀은 teacher IK 범위 밖이라 뺀다: `STAGING_IK_ENVELOPE`). 5 leg × 8 셀·seed = **40 case**(seed는 PF 난수만 바꾸므로 독립 증거가 아님).

```
python3 scripts/agent_lock.py acquire --owner claude --branch <브랜치> --purpose "pair passage carry probe" --pid <드라이버 PID> --expected-minutes <분>
python3 -m scripts.run_pair_stage_probes --stage carry --sources teacher \
  --passage-map zone_wide_corridor_tags_v3 --passage-target A --passage auto \
  --legs 1 2 3 6 7 --cells nominal lat+/same lat-/same yaw+/same yaw-/same corner--/same \
  --policies <정책> --seeds 911 --nominal-seeds 911 912 913 \
  --workers 2 --execute --lock-owner claude --output /Users/changmin/projects/ugrp/outputs/pair-passage-carry
python3 scripts/agent_lock.py release
```

- `--stage chain`(main #270, 한 번 staging 뒤 전 leg를 이어서 실행)도 `--passage-map`과 함께 동작한다(계획 전용 확인, 통로→A 8 leg). 개별 leg probe 결과가 나온 뒤의 후속 단계로 둔다.
- 계획 전용(물리 없음)은 `--execute`·`--lock-owner`를 빼면 된다(이번에 실행함: 40 case).
- 러너는 case에 `pair_passage`가 있으면 워커 프로세스 안에서 `harness.pair_passage_plan.install`을 켜고 scene의 정적 지도를 `executor_view`로 바꾼다.
- **판정(사전 기록):** v6c carry 기준을 그대로 쓴다: 든 채 유지(높이 ≥ 3 cm), 기울기 ≤ 10°, 두 집게 접촉, `leg_error` ≤ 10 cm, `end_error` ≤ 10 cm. 통로 전용으로 **통로 벽 접촉 0**(`CONTACT_KINDS`의 `wall`)과 **횡 오차 ≤ 0.05 m**(봉투 한쪽 여유)를 함께 기록한다. 한 leg 미달이 다른 leg에 전파되지 않도록 leg를 하나씩 따로 시작한다(8 leg를 이은 E2E가 아님).
- **비교 기준:** 같은 정책·셀의 문 지도(`zone_wide_door_tags_v2_dock_v3`) leg 1(문 통과)과 leg 3의 v6c/v6e 기존 결과. 통로는 문과 같은 폭이라 차이는 길이(누적 오차)에서 나올 것이다.
- **원인 코드:** `SELF_POSE_UNCERTAIN`(yaw·xy), `COLLISION_GUARD`(SweepGuard 거절: σ_xy > 0.06 m가 이 기록의 예상 임계), `MOTION_ERROR`, `OWN_IMAGE_INVALID`. 통로 안쪽 바닥이 어두울 수 있어(목적지 바닥은 b-v6c에서 r1 영상 검사에 걸렸다) 영상 판정 원인을 별도로 집계한다.
- **알려진 미측정:** 통로 벽에 붙은 AprilTag가 시작 fix를 태그로 준다(`tags_temporary`). 최종 환경은 태그 0개이므로 이 측정은 태그 없는 위치 추정의 증거가 아니다(b-v6c와 같은 한계).
- 로그는 `outputs/`에 절대 경로로 쓰고 sha256을 기록한다. 끝나면 TensorBoard(`docs/tensorboard.md`)에 새 스냅숏으로 넣는다.

## 한계

- **물리를 돌리지 않았다.** 경로·leg·여유는 정적 계산이며 실제 통과를 뜻하지 않는다. 특히 통로 안 빔 yaw 표류, 팔·빔 스윕 여유, 통로 벽과 로봇 접촉은 측정되지 않았다.
- **SweepGuard 여유는 캐리어 차체만 본다**(팔·빔 스윕과 하중 게이트 정지는 제외). σ 0.03 m/0.012 rad은 E2E 진입 시점의 값이며, 운반 중 σ가 자라는 것은 b-v6e의 dead-reckoning 모델이 다루는 별개 문제다.
- **통로 → B·C는 프로토콜 상한 때문에 지원하지 못한다.** 근본 해결은 `MAX_SEGMENTS`와 상태 enum(`harness/zone_pair_status.py`) 확장이거나 더 긴 leg 허용인데, 둘 다 동결된 프로토콜·측정된 재정렬 주기를 건드린다.
- **executor 쪽 두 곳(`make_plan` 문 고정, `ZoneOwnExecutor`의 door 필요)은 여전히 고쳐지지 않았다.** 이 PR은 probe 프로세스 안에서 우회하고, 고칠 패치를 보존했을 뿐이다. LLM이 호출하는 경로(E2E)에서는 통로 지도 주문이 계속 `INVALID_PAIR_PLAN`으로 거절된다. `executor_view`의 별칭 door 항목 때문에 solo `goto`의 door 경유점과 상태 통로 라벨은 통로 중심을 문으로 본다(pair carry와 무관, 다른 용도에는 쓰지 않는다).
- **지형:** zone 지도에는 지형이 없다(`sim/zone_arena.py:261` `'terrain': []`, scene 빌더도 렌더하지 않는다). 지형 통과는 만들지도 측정하지도 않았고, 지형은 `map_goto`와 같이 "적재 통과 미검증: 피한다"로 다룬다. `passable` 필드는 읽지 않는다.
- 참고한 y 축 통로의 폭 검사는 산술뿐이고 경로는 없다.
- 시트 y가 문 축에서 0.15 m 안이면 첫 점을 축에 붙이는(M2 문 경로와 같은) 규칙을 통로가 아닌 문에도 쓴다. 통로에서는 시트 y와 축이 1.175 m 달라 옆 이동 leg 2개가 들어간다. staged probe는 BASE_SETUP의 실제 빔 y 0.05를 그대로 유지하므로 통로 leg의 진짜 빔이 축에서 0.05 m 벽 쪽에 있다(차체 여유 0.075 m, 테스트로 확인). 축 정렬(`door_align`, ±0.15 m)이 첫 제어에서 이를 잡는다.

## 참고 자료

코드(이 저장소):
- 통로·문 지도: `maps/zones/zone_wide_corridor_tags_v3.json`, `zone_wide_two_doors_tags_v3.json`, `zone_wide_door_tags_v2_dock_v3.json`. 최종 환경 카탈로그 `maps/zones_final/catalog.json`.
- 통로 시나리오: `docs/zone_study_scenarios.md` s4 `s4_narrow_door_standoff`(폭 0.5 m 단일 차선 `corridor_1` + 대피소 `bay_1`).
- 경로·충돌 재사용: `harness/map_goto.py`, `harness/zone_own_guards.py`(`SweepGuard`), `harness/zone_pair_geometry.py`(`PairSweepGuard`), `harness/zone_pair_guards.py`.
- 선행 기록: [b-v6c 운반 stage probe](../2026-09-29-pair-v6c-carry/README.md) '한계', [b-v6e 사전등록](../2026-09-29-pair-v6e-carry/README.md)(측정 중, 이 PR과 무관하게 진행).

서지(기억에 따라 적었고 원문을 다시 대조하지 않았다):
- Hart, P. E., Nilsson, N. J., Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. IEEE Trans. Systems Science and Cybernetics 4(2). — 기존 `plan_path`가 쓰는 A*.
- Lozano-Pérez, T. (1983). Spatial planning: a configuration space approach. IEEE Trans. Computers C-32(2). — 고정 자세 봉투를 장애물에 부풀려 점 경로로 바꾸는 방식(`plan_path`·`envelope_overlaps`의 기반).
- Rus, D., Donald, B., Jennings, J. (1995). Moving furniture with teams of autonomous robots. IROS. — 여러 로봇이 물체를 들고 좁은 통로를 지나는 문제 설정(폭을 물체 크기 기준으로 검사).

## 병합 충돌 위험

- 이 PR이 고친 기존 파일은 `harness/pair_stage_probe.py`, `scripts/run_pair_stage_probes.py`, `scripts/run_ci_tests.py`이다. b-v6e 브랜치(`claude/pair-v6e-carry`)도 세 파일을 바꿨다. 겹치는 곳은 (a) `pair_stage_probe.py`의 `plan_route` 시그니처와 `teacher_cases` 안 `plan_route` 호출 한 줄, (b) `run_pair_stage_probes.py`의 `run_case` 시작부 `spec`, `build_cases` 첫 줄, parser의 `--execute` 앞 세 인자, (c) `run_ci_tests.py`는 서로 다른 줄이라 충돌 없음(전자는 `test_zone_pair_admission` 뒤, b-v6e는 v6d 뒤).
- `harness/zone_pair_executor.py`는 **이 PR이 고치지 않으므로** b-v6e와 충돌하지 않는다. 채택할 때는 `adopt_in_executor.patch`를 b-v6e의 executor 변경 위에 적용한다(다른 hunk, `make_plan`·`PairTeam.__init__`·`start`).
- `PROBE_VERSION`은 이 PR이 올리지 않는다. b-v6e(0.6.0)가 병합되면 그 위에서 통로 opt-in을 0.6.1 등으로 올릴지 정한다.
