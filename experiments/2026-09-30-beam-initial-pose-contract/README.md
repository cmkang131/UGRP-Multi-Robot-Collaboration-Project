# T08a — 남북 빔 초기 자세의 공개 sheet와 정적 계획

Refs #221, #218. PR #302의 T08a만 구현한다. **물리 예산 0 SIM초,
제어기 실행·렌더·새 모델 호출 없음. Draft PR, 병합 금지.**
단위 검사가 통과해도 정식 s1–s6 또는 E2E 실행을 허용하지 않는다.

## 기준과 선행 검증 범위

- 시작 main/작업 base: `6594536b1a1afec6d9d109b35dd85a8426142d01`.
- #235 병합 `141e26e780c3edc70e65f7a80d2110cdc7dfa8e1`: M2 실행기 API·fake
  동기화. 본 PR은 기존 `make_plan`의 거절과 골든 해시를 보존한다.
- #249 병합 `a1307b73fc11d3c7e7ccdee8336e44eba002137a`: v3 모델/정류장/발자국
  규약과 정적 감사. 실제 v3 접근·파지·운반 성공은 선행 증거에 포함되지 않는다.
- #255 병합 `1ed1f1e4bd51d1ec4907a6abe564c0635b45e7f1`: 최종 지도 3종과
  시나리오 v2의 정적 검사 90개. 물리·LLM 실행 없음이라는 원 PR 범위만 인용한다.
- #271 병합 `48f5a868b99113528f24ae36cedb68c630545e6a`: 선택형 동서 빔 통로
  계획과 골든 회귀. 물리 미측정이며 남북 빔 제어 지원으로 확대하지 않는다.
- #302 head `dec67997815e4cdc564a9848ed6020eede45cbfa`: **미병합** P09 정적
  요구/능력 감사. `REQUIREMENTS.md`·`TASKS.md`만 참조하고 inventory·feasibility
  경로를 로봇 입력으로 쓰지 않는다. #302의 CI 취소 방침은 이 작업에 적용하지 않는다.

## 공개 입력과 오차

API는 `harness/beam_initial_pose_plan.py`의
`freeze_public_sheet(static_map, coarse, public_order)` →
`make_initial_pose_plan(static_map, sheet, public_order)`다.
파일·scenario·eval·world·현재 pose·관절·접촉·파트너 입력을 받지 않는다.
`coarse`는 기존 `make_plan`의 3개 키(`beam_xyyaw`, `grid`, `source`) 형식이다.
private 배치를 양자화하는 생성기나 scenario 어댑터는 추가하지 않는다.

setup 담당자가 실행 **전에** 공개 coarse 값을 직접 작성·공개하고 저장해야 한다.
아래 값은 사용자 지시의 세 초기 자세를 위한 공개 선언 예시이며 원본 시나리오를
수정하지 않는다. 반올림은 기존 0.1 m/10°와 소수 여섯 자리 표현을 따른다.

| 적용 대상 | 공개 coarse `(x, y, yaw rad)` | 공개 주문/물건 |
|---|---|---|
| s1, s4 | `(1.3, .4, 1.570796)` | s1 `order-5`, s4 `order-4` / `beam_1` |
| s3 | `(.1, .4, 1.570796)` | `order-1` / `beam_1` |
| s6 | `(1.1, -.8, 1.570796)` | `order-2` / `beam_1` |

초기 허용 범위는 각 XY축 **±0.0500005 m**, yaw **±(5° + 0.0000005 rad)**다.
반 격자와 직렬화 오차를 포함한 닫힌 구간이며, 별도 setup jitter를 더 허용하지 않는다.
이는 초기 빔의 setup 계약이다. 로봇 위치 추정 오차·파지 오차·실행 후 물건 이동을
이 범위로 대신하지 않는다. 실제 배치가 범위를 벗어났다는 평가 정보는 로봇에 보내지
않고 별도 setup/evaluation 위반으로 남긴다. 학생은 이후 자기 RGB로 재확인해야 한다.

sheet는 출처 enum, 전체 오차 범위, 공개 `order_id`와 `item_id`, coarse·전체 공개 주문·
정적 지도 해시를 묶는다. 봉인 뒤 coarse 좌표만 바꾸면 거절한다.
source 문자열·해시는 **출처 진실성을 인증하지 않는다**.
실행 전 공개·봉인 증거는 후속 통합 담당자의 별도 책임이다. 임의 정밀 좌표,
다른 grid·출처, 추가 private 필드, 변조된 ID·주문·지도·오차는 명시적으로 거절한다.
현재 지원 주문은 `long_beam`, `specific_item`, count 1, required_robots 2다.

## 반환되는 기하와 지원 경계

v3 규약의 chassis 기준 파지 반경은 .2032 m이며 빔 중심에서 base까지 거리는
.27 + .2032 = **.4732 m**다. P09 표의 .425 m catalogue 정류장을 v3에 복사하지 않는다.
`end_neg`는 남쪽에서 +π/2, `end_pos`는 북쪽에서 −π/2를 바라본다.
v3 footprint·팔 축 규약을 재사용하며 로봇 모델·카메라/FOV를 바꾸지 않는다.

새 후보의 prestation은 station 뒤 **.25 m**다. 기존 M2의 .30 m를 덮어쓰지 않는다.
북쪽 초기 배치에서 .30 m를 쓰면 SEARCH 발자국과 전체 초기 오차를 함께 넣었을 때
북쪽 벽 간섭 반례가 생긴다. .25 m는 기하 후보일 뿐 실제 재관측·팔 전환·정렬
가능성을 입증하지 않는다.

- 양 역할별 station/prestation/heading과 고정 heading의 local approach를 반환한다.
- 빔과 **두 carrier 모두**를 검사한다. v3 chassis/팔의 접근 양끝, prestation의
  기존 ±.20 m SEARCH 외곽에 v3 팔 축의 전방 .0482 m를 추가한다.
  각 꼭짓점의 yaw 구간 내 삼각함수 극값과
  병진 양끝의 극값으로 연속 sweep을 감싼다. 샘플 사이 충돌을 놓치는 점 검사가 아니다.
- XY 오차와 추가 .02 m 벽 여유를 넣은 AABB를 지도 경계·모든 벽/장애물·지형에
  대조한다. 회전 장애물도 SAT로 검사하며 접촉은 거절한다. 두 carrier의 전체
  접근 envelope가 겹치는 경우도 거절한다. 보수적인 AABB 때문에 가능한 기하를
  거절할 수 있다.
- SEARCH→grasp 자세의 3-D 전환, 다른 물건·동료, spawn→prestation 경로는
  검사하지 않는다. 파지 자세로 접근하는 구간만 기하를 제공하며 전환 검증은 T08b다.
  yaw 오차의 sweep은 불확실성 범위이지 빔을 회전시키는 명령이 아니다.
- `STATIC_INITIAL_GEOMETRY_ONLY`, `executable=false`, `e2e_admitted=false`,
  `sim_cap_s=0`을 반환한다. M2가 받는 `route`·`door_plan`을 제공하지 않는다.
  spawn 접근·carry·pivot·execution 각각에 명시적 미지원 이유가 있다.

`order_sha256`, `sheet_sha256`, `map_sha256`, `geometry_sha256`,
`role_geometry_sha256`, `plan_sha256`을 구분한다. 역할은 로봇 ID와 연결하지 않으며
`role_assignment=null`, `controller_code_sha256=null`이다(실행 제어기를 선택하지 않음).
후속 작업은 공개 고수준 역할 배정 해시와 실제 제어 소스 해시를 따로 기록해야 한다.
4조건별 인자/override는 없고 controller/config/센서/기억/STATUS 채널은 수정하지 않는다.

## 검증 기록

로컬 관련 검사 **60 passed in 0.80s**. 원본 44개 파일 해시 불변과 잠금 반환을 확인했다.
실제 사용한 로컬 드라이버는 `verification_driver.py`에 그대로 보존했다.

관련 fake/정적 pytest의 최종 명령·결과·원본 해시와 파일 보존 감사는
`VERIFICATION.json`에 기록한다. 테스트는 공용 `agent_lock` 아래 기존 Mac 환경을
사용하며 MuJoCo·모델 import와 network connect를 차단한다. 실패 시 새 폴더로
재실행하고 이전 결과를 덮지 않는다.

기존 M2에서 세 coarse 자세가 `PAIR_PICKUP_OUTSIDE_M2_DOOR_ENVELOPE`인 것을
검사한다. s6의 실제 두 문 지도에서는 더 앞서 `UNSUPPORTED_PAIR_MAP`이므로,
자세 자체의 반례는 지원 M2 지도에서도 별도로 검사한다. 최종 문1/문2/복도 지도,
ID·order 분리/변조, 초기 오차 모서리와 내부 yaw, 양 carrier 외곽 장애물,
네 지도 경계 접촉/±epsilon, malformed 입력, private 변화 비간섭을 포함한다.

원본 시나리오·지도·실험·성공 번들·등록 제어기는 그대로다. 새 bundle/workflow ID와
모델 asset은 없다. 정적 API/fake 단위 검사이므로 TensorBoard에 성공률을 만들지 않는다.
이 PR의 실제 실험·훈련·평가 trial은 0회이며, TensorBoard snapshot·표시는 아래
후속 물리 결과를 얻은 작업에서 원본 해시와 함께 확인한다. Drive 작업은 없다.

## 코디네이터 후속 물리 검사 — 여기서는 실행하지 않음

| 후속 | 최소 진단과 SIM cap | 남은 판정 |
|---|---|---|
| T08b | 3초기 자세 × 정상/실패 × 900 = **5,400 SIM초** | 실제 spawn→prestation→정렬, ±오차 경계·팔 전환·자기 RGB posterior/history 연속 인계. teleport 금지 |
| T09b | solo/pair × 정상/관측한 막힘 × 900 = **3,600 SIM초** | T09a 이후 두 문 선택·실제 통과, 비공개 사건 시각 선사용 금지 |
| T10b | solo/pair × 동/서 × 정상/대치 실패 × 900 = **7,200 SIM초** | T10a 이후 복도·후퇴·양보·재출발, 최대3대 |
| T11 | 설계 PR **0**, 후속 controller/사전 등록 후 **물리 총비용 미산정** | s6 can 선행 필요성·pivot 중심·한쪽 실패. 2×900초는 기준 제안일 뿐 확정 예산 아님 |

모두 한 후보의 최소 진단 제안이며 4조건 효과/확증 코호트가 아니다. 실행 전 커밋·
입력·config·최종3D 모델·walls_v3·표식0·weld OFF·cargo_noslip_v1을 고정하고 공용
잠금을 획득한다. staging/팔 전이 포함 SIM초, 명령·관측, 실패 원인, 성공률 분모를
남기며 cap 도달은 실패/미도달이다. primary `outputs/`에 새 raw를 저장하고 원본을
보존한다. 실제 결과의 TensorBoard snapshot·표시·원본 해시는 후속 담당자가 검증한다.
호스트 오류(ENOSPC 포함)와 물리 실패를 분리하며 raw 결과를 덮어쓰지 않는다.

## 참고 자료

- #302 `experiments/2026-09-30-scenario-capabilities/REQUIREMENTS.md`, `TASKS.md`
- #221 로봇별 실행기, #218 최종 환경, #249 v3 모델, #255 최종 지도, #271 통로 계획
- 기존 `harness/zone_pair_executor.py`, `harness/pair_owncam_approach.py`,
  `harness/zone_team_footprint_v3.py`, `sim/masterpi_robot_models.py`,
  `harness/static_keepouts.py`를 참조·재사용한다.
- 새 외부 논문·OSS·의존성 없음. 정적 계획 모듈은 표준 라이브러리와 저장소의
  정적 모델/기하 함수만 사용한다.
