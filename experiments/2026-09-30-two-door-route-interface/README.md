# T09a 두 문 선택용 정적 경로 인터페이스

Refs #219, #221, #223. 요구 출처는 draft PR #302의 T09a다.

## 범위와 판정

`harness/zone_static_door_routes.py`는 정적 지도와 선택한 화물/전체 편대에서 문별 후보를 계산한다. `door_narrow`(0.5 m), `door_wide`(1.0 m)를 첫 원소나 `door_1` 상수로 고르지 않는다. 반환값은 문 ID·방향·화물 기준 XYyaw 경로·각 구간 이동 heading과 거절 이유다. 유효 후보 중 최단 경로를 고르며 길이가 같으면 문 ID 순서다. 실제 통과·배송 완료를 반환하지 않는다.

**정적 API의 검토 후보이며 M1/M2 연결·E2E 실행 준비 완료가 아니다.** 기존 `m1_owncam_delivery.py`, `zone_own_executor.py`, `zone_pair_executor.py`, `pair_passage_plan.py`, P01 지도/provider 등록, P02 재고 계약, 시나리오/seed/성공 기준, 번들/workflow를 변경하지 않는다. 신규 실행 번들 ID는 없다. 본연구 사전 등록은 DRAFT 그대로다.

작업 base: `6594536b1a1afec6d9d109b35dd85a8426142d01`, branch `codex/two-door-route-interface`. 시작 시 fetch 및 열린 PR 확인. 기본 체크아웃은 `d17ca4345affef8cf027e121cf1f3197b36c23e0`의 main이며 source 고정 작업이 진행 중이었다. 이 작업은 병합하지 않으므로 기본 체크아웃도 변경하지 않는다.

## 입력·기하 계약

- `static_map`: 사전 작성한 지도 딕셔너리(`bounds_m`, `obstacles`, `terrain`, `passages`). 지도 로딩·해시 등록은 호출자/P01 책임이다. `eval`, `setup`, `hidden_events`를 섞은 입력은 거절한다. 미래 사건을 지도에 투영하지 않는다. P09 inventory/feasibility 또는 setup placement를 로봇의 시작 pose나 경로로 사용하지 않는다.
- `start_pose`/`goal_pose`: **화물 좌표계의** `(x, y, yaw)`. 시작은 허용된 자기 추정/공개 coarse 입력, 목표는 공개 주문과 정적 지도에서 온 값이어야 한다. 수치 API 자체는 그 측정 출처를 인증하지 못하므로 T09b 어댑터에서 provenance를 고정한다. 초기 양쪽 전체 footprint가 문 반대편에 있어야 하며 mouth 도달은 crossing이 아니다.
- `cargo_kind`, `roles`, `robot_model='masterpi_v3'`: 카탈로그의 완전한 역할 집합만 허용한다. 화물·모든 carrier chassis/arm·0.03 m 여유의 기존 v3 정적 footprint를 사용한다. point/disc 임의 override나 일부 carrier 생략을 허용하지 않는다. 이 envelope는 보수적 정적 정의이며 최종 3D/접촉 검증은 별도다.
- `MotionContract`: 버전 `fixed_heading_xy_v1`, 기본 구간 길이 최대 0.85 m, 최대 8구간. 더 작은 한도는 가능하고 이를 넘겨 상태 채널을 확장하는 override는 거절한다. 네 통신 조건은 동일한 계약을 써야 한다. 역할→로봇 배정은 호출자가 별도로 기록하며 이 API에는 actor 선택·파트너·양보 기능이 없다.
- yaw를 유지하는 동/서 방향 및 정지 후 XY축 이동만 지원한다. 남북으로 놓인 빔의 회전, pivot, 목표 yaw 변경, y축 통로/복도·bay는 명시적으로 지원 밖이다. 현재 axis 후보가 막혔다는 거절은 임의 경로의 불가능성 증명이 아니다.
- 각 선형 이동에서 각 convex part의 시작/끝 꼭짓점 convex hull을 SAT 검사한다. 고정 heading의 연속 병진 sweep이므로 샘플 사이의 얇은 벽·모서리를 건너뛰지 않는다. bounds·외곽 벽·회전된 정적 장애물·미검증 지형도 검사한다. 문 중심선의 폭이 선언과 일치해도 실제 벽에 닿으면 거절한다.
- 미래 private blockage만 바뀌어도 허용 관측 이전의 입력/경로는 같다. API에는 조건·시간·사건·평가·인벤토리·peer 상태 입력이 없다. 자기 RGB에 근거한 장애물 belief와 재계획은 T09b에서 별도 연결한다.

사용 예(정적 계획만):

```python
from harness.zone_static_door_routes import plan_door_routes
result = plan_door_routes(
    authored_static_map, own_cargo_estimate, public_goal_pose,
    cargo_kind='long_beam', roles=('end_neg', 'end_pos'),
    robot_model='masterpi_v3',
)
route = result.selected  # None이면 result.refusals; 물리 완료 신호가 아님
```

함수·footprint·motion 설정의 해시와 실제 역할 배정 해시는 통합 실행의 서로 다른 기록으로 남겨야 한다. 이번 정적 테스트에는 실제 역할 배정·sensor·자기 기억·상태 endpoint가 없고 기존 controller/config를 바꾸지 않는다. 4조건의 동작/통신 효과는 측정하지 않았다.

## 선행 PR의 실제 상태

시작 시 GitHub 조회 및 위 base의 ancestor 검사로 확인했다. 선행 수치는 해당 PR의 기록이며 이번 작업 결과에 합산하지 않는다.

| PR | 실제 병합 SHA/상태 | 근거 범위 |
|---|---|---|
| #202 | `0b7861cc2aa391e74e62dc342177a6163fb32338` MERGED | 정적 feasibility 31건·별도 회귀; 평가 전용, 로봇 성공 아님 |
| #249 | `a1307b73fc11d3c7e7ccdee8336e44eba002137a` MERGED | v3 모델/정적 footprint 정의; 운반 검증을 승계하지 않음 |
| #255 | `1ed1f1e4bd51d1ec4907a6abe564c0635b45e7f1` MERGED | 최종 지도/시나리오 v2, 정적 90건, 물리 없음 |
| #271 | `48f5a868b99113528f24ae36cedb68c630545e6a` MERGED | opt-in pair passage 계획 43건, 물리 없음; 고정 편대/heading/8구간 제약 |
| #302 | `dec67997815e4cdc564a9848ed6020eede45cbfa`, OPEN/DRAFT, 병합 SHA 없음 | 원본 요구·정적 감사·T09a 계약. mouth/중심선 회귀 기준만 테스트에 재사용 |
| #305 (P01) | OPEN/DRAFT, 병합 SHA 없음 | 지도/provider 등록은 독립 작업. 이번 코드의 의존성으로 가져오지 않음 |

## 검증 기록

로컬 관련 검사 **150 passed in 7.93s**, 실패/skip 0, driver exit 0. 새 테스트와 기존 pair passage/formation/keepout/원본 지도 해시 회귀를 함께 실행했다. [verification.json](verification.json)에 파일별 건수·실행 인자·Python 버전·소스/원본 해시·잠금 획득/반환·부하 평균을 보존한다. 커밋 직전 소스 해시가 이 통과 실행과 같음을 확인했다.

새 반례: 각 문 × cyan/crate/beam × 양방향, 두 후보 선택·차단, point/.17/.21 m disc는 통과하지만 편대 모서리는 걸리는 경로, 중심선 접촉/되돌아감, 얇은 벽, 폭 경계, 아주 작은 옆 오프셋의 정확한 시작/끝 보존, 미지원 회전/역할/모델/구간 한도, private 사건·배치 변경 비간섭.

로컬 검사 경계: MuJoCo/torch/모델 SDK import 및 network connect를 차단한 driver에서 공용 잠금을 획득한 뒤 pytest 실행. renderer·장면·physics step·모델 호출을 하지 않는다. 최초 잠금 시도는 다른 작업(`claude/v6h1-acceptance-run`, PID 54614)의 잠금을 발견해 pytest 시작 전에 exit 3이었다. 다른 작업의 잠금/프로세스는 변경하지 않았다.

원본 해시 기준: primary `outputs/2026-09-30-t09a-two-door-route/input-baseline.json`에 원본 시나리오·지도·기존 실행기·registry 40개 파일을 보존한다. 대기 시도 02/03은 테스트 시작 전에 자기 세션을 종료(exit 130)해 확인 간격/검사 목록을 조정했다. 실제 검사 04는 별도 timestamp 디렉터리 `20260930T205232-96899`에 JUnit·환경·소스 해시·부하 평균·잠금 반환을 기록했다. 40개 보호 파일 해시는 모두 불변이다. 로컬 raw 보관은 원격 백업이 아니다. 정적 단위 회귀는 학생 시행/성공률 분모나 TensorBoard 물리 결과로 변환하지 않는다.

일반 GitHub CI는 ACT/local-model 테스트를 포함하여 정상 실행한다. CI 취소 및 `[skip ci]`를 사용하지 않는다. 로컬의 모델 호출 0과 원격 CI의 허용된 모델 시험을 구분한다.

## 코디네이터의 후속 물리 검사

- **T09a cap: 0 SIM초.** 이 PR에서 수행할 물리 검사는 없다.
- **T09b 최소 제안: solo/pair × 정상/막힘 = 4셀, 셀당 staging 포함 900 SIM초, 총 3,600 SIM초.** API를 실제 controller에 연결하고 관측에 기반한 재계획 경계를 검증한 별도 소스에서만 실행한다. 정상/실패 셀마다 cap 도달은 실패/미도달이며 4조건 효과나 확증 코호트가 아니다.
- 원본 s2의 45초 사건을 보존한다. 실제 장애물 발생·자기 RGB 가시/비가시·발견 후 우회·wide 통과를 따로 기록한다. 아직 관측하지 못한 `no_comm` 로봇이 사전 우회해서는 안 된다. 양문 막힘, 한쪽 편대 실패, 구간 한도 초과는 안전 거절한다. 900초 이전 완료하지 못해도 원본 시간을 바꾸거나 결과 파일을 덮지 않는다.
- 최종 3D 로봇·walls_v3·표식 0·weld OFF·cargo_noslip_v1, 실행 전 source/input/config 고정과 공용 잠금. 네 조건의 controller/config/센서/자기 기억/고정 상태 enum을 동일하게 유지하고 역할 배정은 별도 해시로 남긴다.
- raw를 primary `outputs/`에 보존한다. staging 포함 SIM초·명령/관측·실패 이유·성공률 분모·원본 해시를 기록하고 새 TensorBoard snapshot의 데이터/영상 실제 로딩을 확인한다. 이 물리 검증과 대시보드 확인은 아직 미실행이다.

## 참고 자료

- PR #302 `REQUIREMENTS.md` s2 및 `TASKS.md` T09a/T09b, `audit.py::passage_crossings`와 mouth/plane 회귀.
- PR #202, #249, #255, #271; `harness/static_keepouts.py`, `harness/zone_team_footprint{,_v3}.py`, `sim/zone_cargo.py`, `sim/zone_model_conventions.py`.
- 원본 `maps/zones_final/zone_wide_two_doors_final_v1.json` 및 `configs/zone_study_scenarios_v2/s2_unmapped_blockage_v2.json`(읽기만 함).
- `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `docs/current_status.md`. 새 외부 논문/OSS/의존성 없음.

호출자가 구분해야 할 주요 거절 이유:

| 이유 코드 | 호출자가 구분할 의미 |
|---|---|
| `INVALID_STATIC_MAP` / `INVALID_INPUT` / `INVALID_MAP` | 입력 형식·수치 또는 private 정보 경계 위반 |
| `INVALID_FORMATION` / `UNSUPPORTED_CARGO` / `UNSUPPORTED_ROBOT_MODEL` | 전체 v3 정적 footprint를 만들 수 없음 |
| `NO_DOORS` / `UNKNOWN_DOOR` / `UNSUPPORTED_PASSAGE` | 이 API의 문 후보 범위 밖(복도는 T10a) |
| `UNSUPPORTED_ROTATION` | 고정 heading의 XY 이동으로 수행할 수 없는 요청 |
| `FOOTPRINT_TOO_WIDE` | 현재 heading의 전체 편대 폭이 선언 개구부에 맞지 않음 |
| `START_FOOTPRINT_BLOCKED` / `GOAL_FOOTPRINT_BLOCKED` | 시작/끝의 전체 편대가 정적 장애물·경계와 겹침 |
| `ENDPOINTS_NOT_ACROSS_DOOR` | 전체 편대가 문 양쪽에 있는 시작/끝이 아님; mouth/중심선 도달은 완료 아님 |
| `STATIC_SWEEP_BLOCKED` | 이번 축 이동 후보의 연속 swept footprint가 벽/지형/경계와 겹침 |
| `CONTROLLER_SEGMENT_LIMIT` | 경로를 나누면 명시한 구간 수 한도를 넘음; 상태 채널을 몰래 늘리지 않음 |

거절 뒤 다른 경로가 존재하는지는 별도 문제다. 이 API에서 후보가 없다는 이유로 숨은 장애물을 주입하거나 물체/로봇을 옮기지 않는다.
