# T10a — 복도와 bay 정적 계약

상태: **정적 구현·관련 회귀 78건 통과, draft 전용**. 물리·렌더·로컬 모델 호출은
실행하지 않았다. 이 작업의 SIM cap은 **0초**다. 기존 s1–s6, 지도, 성공 기록,
v6e DRAFT, bundle/workflow ID를 바꾸지 않는다. 연구 성공률과 통신 효과는 미측정이다.

## 기준과 선행 작업

작업 base는 `6594536b1a1afec6d9d109b35dd85a8426142d01`
(`codex/corridor-bay-contract`)다. 시작 때 fetch와 열린 PR을 확인했다.
기본 체크아웃은 당시 main이 origin/main보다 5커밋 뒤였고, 다른 source 고정 작업의
공용 잠금이 있어 갱신하지 않았다. 이 PR에서는 병합하거나 main을 갱신하지 않는다.

| 선행 | 실제 병합 SHA / 상태 | 여기서 재사용하는 범위 |
|---|---|---|
| #202 | `0b7861cc2aa391e74e62dc342177a6163fb32338` | 정적 footprint/keepout 기하의 배경. evaluator와 private inventory 경로는 import하지 않음 |
| #249 | `a1307b73fc11d3c7e7ccdee8336e44eba002137a` | v3 모델과 station/arm mount 계약. 기존 v2 기록 보존; 물리 성공 승계 없음 |
| #255 | `1ed1f1e4bd51d1ec4907a6abe564c0635b45e7f1` | 표식 0·walls_v3 복도 지도. PR에 기록된 정적 지도/시나리오 검사 90건은 선행 결과이며 이번 결과에 합산하지 않음 |
| #302 | **미병합 draft**, `dec67997815e4cdc564a9848ed6020eede45cbfa` | REQUIREMENTS/TASKS의 T10a/T10b 요구. P09 경로·수치를 학생 입력이나 이번 성공 근거로 쓰지 않음 |

관련 이슈: Refs #218, #221, #223, #224. 중복 작업 방지를 위해 #302에 작업 범위를 알렸다.

## API와 반환의 의미

새 모듈은 `harness/zone_corridor_contract.py`다. 입력은 공개 정적 지도,
명시적 `masterpi_v3` 모델, catalogue kind, 호출자가 고른 **전체 역할 배정**,
사전에 제안한 경로/자세뿐이다. 최종 지도 JSON 자체에는 robot_model이 없으므로
`CorridorContract(data, robot_model='masterpi_v3')`처럼 명시한다. 모델을 추측하지 않는다.
자세 단위는 `(x m, y m, yaw rad)`이며 실시간 정답 자세를 넣는 인터페이스가 아니다.

`status`는 `pass/blocked/unsupported`, `static_ok`는 `true/false/null`이다.
`blocked`는 **제출한 경로/자세**가 보수적 검사를 통과하지 못했다는 뜻이다.
모든 가능한 경로의 부존재 증명이 아니다. 입력·경로가 없거나 지원 모델/축 밖이면
unsupported 또는 명시적 예외를 내며, 미검사를 true로 바꾸지 않는다.

| 필드 | 검사 범위 |
|---|---|
| `disc_passage` | 별도 원판의 복도 중심선 sweep. 물건/운반 편대의 통과를 대신하지 않음 |
| `item_rotation` | 물건만의 제자리 회전. `formation_swept_clear`에 모든 carrier를 포함한 별도 결과 |
| `pose_paths.west_to_east/east_to_west` | 제출한 각 방향의 전체 편대 sweep, 양 끝에서 편대 전체가 복도 밖에 있는지, 두 입구·중심선 교차 |
| `bay.stop` | 물건+모든 carrier가 bay 안에 들어가고 벽/지도 경계와 여유를 지키는지. 폭·길이·최소 경계 여유 반환 |
| `bay.evacuation/reentry` | corridor 내부 자세와 같은 bay 정지 자세 사이의 연결·전체 sweep. 한 방향 PASS로 다른 방향을 채우지 않음 |
| `bay.rotation` | 제자리 yaw 변화 중 전체 편대가 bay 내부를 지키는지 |
| `simultaneous_occupancy` | 호출자가 제시한 joint pose의 정적 벽/편대 겹침과 총 로봇 수. `simultaneous_passing`은 계속 unsupported |

회전은 각 구간의 최단 yaw 보간이다. 180°보다 큰 회전은 중간 자세로 나눠야 한다.
샘플 사이 병진+회전 이동량 상한만큼 벽·경계 검사를 더 키워, 끝점만 통과하는
가느다란 장애물/회전 반례를 막는다. 통로 측면도 전체 편대로 검사한다.
기본 footprint 팽창은 3 cm, 추가 벽/bay 경계 여유는 1 cm다. 이는 정적 보수적
v3 envelope이며 실제 관절·짐 흔들림·마찰·3D 접촉을 보증하지 않는다.

전체 catalogue carrier 역할이 필수다. 빔 끝 하나만 넣어 작은 footprint를 만드는
입력은 거절한다. 역할→로봇 배정은 별도 필드이며 제어/기하 소스 해시와 섞지 않는다.
원본 팀의 `r1/r2/r3`만 허용한다. pair+solo는 3대, 2pair는 4대이므로 후자는
`TEAM_SIZE_EXCEEDED`로 표시한다. 양보할 로봇이나 partner를 host가 골라 주지 않는다.
통신 조건 인자·조건별 override가 없으며 네 조건의 private 필드만 바꾸는 fake 검사에서
동일 정적 결과를 요구한다. 센서·자기 기억·상태 enum은 변경하지 않는다.

## 문 없는 지도와 기존 실행기의 경계

새 `CorridorContract`는 `kind=door`를 찾지 않는다. corridor/bay를 ID와 kind로
검사하며 누락을 명시적으로 거절하므로 `StopIteration`이 없다.

새 opt-in `create_own_executor(...)` 진입점은 문 없는 지도에서 기존 실행기를
만들기 전에 `CORRIDOR_RUNTIME_UNSUPPORTED: T10b required`를 낸다.
문이 있는 지도는 기존 실행기에 인자를 그대로 전달한다. 복도를 가짜 door로 바꾸지 않는다.

**기존 `ZoneOwnExecutor` 직접 호출과 현재 runner는 그대로 보존했다.** 이 모듈은
현재 v6e DRAFT의 source hash 대상이므로 직접 수정하거나 봉인을 다시 쓰지 않았다.
기존 호출 경로의 `StopIteration` 자체가 전역으로 사라진 것은 아니다.
T10b가 새로운 실행 버전에서 안전 진입점/복도 제어를 연결해야 한다.
이번 정적 PASS는 runtime admission, 기존 DRAFT의 확장 승인, E2E 준비 판정이 아니다.

## 검증과 보존

`tests/test_zone_own_executor_corridor_contract.py`는 기존 CI의
`test_zone_own_executor*.py` glob에 들어간다. 정상/오류/미지원, 입구만 방문하는 경로,
역방향, bay 경계·내부 장애물·들어가는 길의 벽, 회전 sweep, pair+solo/2pair,
private 변화 비간섭을 검사한다. 새 경로는 P09 evaluator·MuJoCo·모델 SDK를
import하지 않는 subprocess 검사도 포함한다.

로컬 검증은 공용 잠금을 원자적으로 획득한 뒤 수행한다. 물리 host 테스트 한 건은
명시적으로 제외한다. MuJoCo/학습/모델 SDK import와 network connect를 막고
fake와 정적 기하 회귀만 실행한다. 자동 GitHub CI의 ACT/local model 검사는
사용자가 허용했으므로 평소 workflow를 그대로 실행한다. CI를 취소하거나 skip하지 않는다.

로컬 최종 결과: **78 passed, 1 deselected in 45.66s**, driver exit 0.
새 계약 검사, 기존 own-executor 비물리 검사, 기존 봉인 source 검사, 기존 hard-routes
기하 회귀를 함께 실행했다. wall 시간은 테스트 기록이며 시뮬레이터 처리량이 아니다.
검사 전후 기존 입력·소스 40파일과 새 구현/테스트 해시가 동일했고 자기 잠금을 반환했다.
로컬 물리 step·렌더·모델 호출은 0이다. `data/receipt.json`의 base SHA는 검사 전
HEAD이며, 아직 커밋 전인 새 코드의 정확한 bytes는 `new_source_sha256`으로 고정했다.

최종 지도에서 사전에 제안한 **수치 경로**의 결과는 `data/static_proposals.json`에 있다.
빔 편대의 `(1.5,1.175,0) ↔ (4.6,1.175,0)` 경로는 양방향 정적 PASS다.
bay 중심 `(3.1,.625,0)`에서는 편대 길이 1.2064 m, 폭 .2700 m,
경계 여유 −.3282 m로 **blocked**다. solo cyan의 제안 정지 자세 `(3.2,.625,0)`는
경계 여유 .0418 m이고 정지/대피/재진입 정적 검사를 통과했다.
복도의 pair와 bay의 solo가 제안한 joint pose에 동시에 있는 검사도 통과했지만,
**simultaneous_passing은 unsupported**다. 이는 실제 로봇 자세 관측이나 실행 결과가 아니다.

raw는 primary checkout의 `outputs/2026-09-30-cap-t10a-corridor/attempt-01/`에 있다.
검증 driver·pytest 로그·receipt·정적 제안 결과를 `data/`에 복사하고 SHA-256/바이트를
대조했다(`data/checksums.json`). raw 전체가 원격 백업되었다는 뜻은 아니다.
정적/fake 코드 검사이므로 학생 성공률·SIM 시간 그래프를 만들지 않으며 TensorBoard의
물리 결과 snapshot도 생성하지 않는다. Google Drive를 사용하지 않는다.

## 코디네이터 후속 물리 검사

**T10a: 0 SIM초, 물리 실행 없음.** T10b controller와 실행 봉인·사전 조건이
갖춰진 뒤 별도 작업으로 다음 최소 진단을 제안한다.

- solo/pair × 서→동/동→서 × 정상/대치 실패 = **8셀 × 900초 = 7,200 SIM초**.
- 최종 3D 모델·walls_v3·표식 0·weld OFF·cargo_noslip_v1, 최대 3대.
- 실행 전에 코드/입력/설정과 각 셀의 하중·시작/상대 자세를 고정하고 공용 잠금을 잡는다.
- 접근·staging·팔 전이를 포함한 SIM초, 명령/관측, 실패 원인, 성공률 분모를 기록한다.
  cap 도달은 실패/미도달이다. 원래의 s4 seed/주문/성공 기준은 바꾸지 않는다.
- bay에 누가 들어갈 수 있는지 아직 불명한 편대/자세는 unsupported로 남긴다.
  pair 대피를 가정하거나 host가 정답 양보자를 고르지 않는다.
- 복도 통과, bay 정지·후퇴·재진입, 접촉과 재출발을 각각 평가한다.
  static reverse PASS나 joint-pose PASS는 동시 교행 증명이 아니다.
- raw는 primary outputs의 새 경로에 보존한다. 실패 파일을 덮어쓰지 않고 원본 해시와
  TensorBoard 새 snapshot·실제 로딩을 확인한다. 이 8셀은 4조건 효과/확증 코호트가 아니다.

## 참고 자료

- PR #302 `experiments/2026-09-30-scenario-capabilities/{REQUIREMENTS,TASKS}.md`
- PR #249, #255 및 `maps/zones_final/zone_wide_corridor_final_v1.json`
- `harness/static_keepouts.py`, `harness/zone_team_footprint{,_v3}.py`, `sim/zone_model_conventions.py`
- `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `docs/current_status.md`
- 새 외부 논문/OSS/의존성 없음. Python 표준 라이브러리와 기존 정적 기하·pytest 재사용.
