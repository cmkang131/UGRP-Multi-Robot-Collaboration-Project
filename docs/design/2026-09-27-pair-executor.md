# M2 공동 운반 executor 연결 — 2026-09-27

이슈 #221 / PR #235의 `zone_pair_executor_v4_dev` 설계다. 1·2차 리뷰,
`69dd0f0b`의 3차 리뷰와 Kiro 실행기 병합 `8f4fb676`을 반영했다.
코디네이터가 정한 독립 랑데부·통신 경계는 유지한다.
M2 물리 성공을 새 executor에 승계하지 않는다.

## API와 독립 제출

```python
# 사전에 고정하는 설정. 실행 중 world 좌표에서 만들지 않는다.
spec['team_cargo'] = [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': [1., .05, 0.]}]
spec['order_sheet'] = {'orders': [{
    'order_id': 'cargoX', 'kind': 'long_beam', 'count': 1, 'required_robots': 2,
    'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P2', 'slot': 'P2-3'}}]}
spec['pair_order_sheets'] = {'cargoX': coarse_order_sheet([1., .05, 0.])}
spec['contact_profile'] = 'cargo_noslip_v1'
# OwnCamTeamHost(..., frames_dir=<기본 checkout outputs 아래 새 경로>)

# 아래는 각 로봇의 독립적인 결정이다. host가 두 번째 호출을 만들지 않는다.
r1_ack = host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
# r1만 waiting_partner. r2의 job/API 호출/목적지를 생성하지 않는다.
r2_ack = host.call('r2', 'pair_carry', 'cargoX', 'B', 'r1')
# 두 제출이 일치할 때 STATUS start_ready를 각자 소비하고 시작한다.
# 중단: host.call('r2', 'abort', 'caller_abort')
```

`coarse_order_sheet`는 기존 `harness.pair_owncam_approach` 함수다. 이 버전은
r1/r2, long_beam 1개, M2 문 지도와 문 앞 개략 주문서 범위만 지원한다.
화물의 end_neg/end_pos 역할은 ID 순서와 정적 화물 기하에서 각자 계산한다.
각자의 지도·주문서로 계획을 만들며 host는 제출 명세와 정적 입력의 일치만
검사한다. 상대의 busy/pose/주문을 미리 읽어 대신 선택하지 않는다.

`accepted=True`는 자기 제출의 수락이다. 상대 제출 전에는 `waiting_partner`로
hold하며, 기본 5 SIM초 안에 같은 화물·상대·목적지를 제출해야 한다.
불일치는 `PAIR_SUBMISSION_MISMATCH`, 만료는 `PAIR_RENDEZVOUS_TIMEOUT`이다.
제출한 로봇의 timeout은 자기 `job_failed`로만 알린다. 미제출 상대에게는
이벤트·알림을 전혀 보내지 않으며, abort 자유문과 제출 시도·시점도 노출하지 않는다.
명세 불일치 때는 실제 제출한 양쪽에만 고정 거절 코드를 준다. host의 임의 상대
알림 함수는 제거했다. 거절·timeout에는 자유문 예외 내용을 붙이지 않는다.
자기 busy/stopped 검사가 상대 명세 비교보다 먼저라 일치 여부를 조회할 수 없다.
자기 불확실한 pose/짐 보유/잘못된 영상으로 거절된 호출도 상대에게 알리지 않는다.
상대의 과거 timeout 때문에 새로운 자기 제출을 거절하지 않으며, 새 제출은 자기
5초 창에서 기다린다. STATUS task ID는 host의 전역 시도 횟수가 없는 임의 UUID다.
`enable_pair_carry(..., rendezvous_timeout_s=5., heartbeat_timeout_s=.15)`로 한도를 설정한다.

## 제어·영상 경계

- 동결된 `M2DoorStudent(version='v3')`, `PairApproachDriverV2`, `fullframe_v3`,
  `ArmSequence`를 import한다. 원본 CLI와 동결 import 파일은 편집하지 않았다.
- 접근은 `GuardedPairApproach(GuardedDriver, PairApproachDriverV2)`로 연결했다.
  Kiro의 불확실도 히스테리시스·dwell, 3-D sweep, 명령 거리 기반 정체 확인과
  최대 2회 후진/재계획 복구를 재사용하며 M2의 최종 heading·재위치추정 정책을
  유지한다. 해당 로봇의 pose source 하나가 영상·명령을 한 번씩 처리한다.
  M2가 localizer를 재생성해도 같은 자기 source에 연결하며, 실행기와 pair 보정이
  다르면 `PAIR_CALIBRATION_MISMATCH`로 거절한다.
- 접근 이후 readiness·단계 전환 전에 자기 gate와 추정 freshness를 검사한다.
  controller 직접 명령과 arm queue 모두 발행 전에 같은 `SweepGuard`로 팔·집게의
  3-D 전이와 차체 이동 여유를 검사한다. 공동 파지 이후에는 한 대만 후진하지 않는다.
  정체가 확인되면 `PAIR_blocked`, 추정 확인이 안 되면 `POSE_UNCERTAIN_PROGRESS`로
  STATUS abort를 보내 양쪽 queue를 지우고 hold한다. 재개에는 새 독립 제출이 필요하다.
  접근 정체·추정 실패도 공통 `blockage_seen`/`pose_uncertain`·`job_failed` 이벤트로 끝낸다.
  이 검사는 전체 빔의 동적 변형·기울기까지 검증한 충돌 모델이 아니다.
- 입력은 자기 wrist RGB·발행 명령, 정적 지도·보정·개략 주문서와 STATUS뿐이다.
  endpoint 객체 그래프에 host/world/상대 executor·controller가 없다.
- `zone_pair_vision.valid_frame`이 수락·STATUS readiness·운반 유지 판정보다 먼저
  자기 영상의 소유자/시각/hash, JPEG 시작·종료/디코드/크기, 유효 FOV의 검정 비율과
  대비를 검사한다. 검정·넓은 검정 가림·균일 영상·손상/잘린 JPEG는 즉시 거절/중단한다.
  어두운 grip band와 저조도 v3 기록은 유지한다. 임의의 질감 있는 가림까지 검출한다는
  뜻은 아니며, 임계값은 물리 검증 전 dev 방어 조건이다.
- controller는 공통 0.1초 격자, arm은 원본 CLI의 별도 0.05초 시계를 쓴다.
  새 영상 요청 중에는 controller timer를 진행하지 않는다. arm 시계는 초기 0부터
  idle/초기 대기 중에도 매 physics 시각에서 `now >= next_arm`으로 검사하고
  `next_arm = now + .05`로 갱신한다. epsilon·반올림·제출 때 시계 초기화가 없다.
  controller 처리 후 arm을 발행하며, 사이에도 STATUS·영상 유효성을 먼저 확인한다.
  같은 queue에 대해 원본 발행 조건과 비교한 범위이며 전체 물리 궤적 일치를 뜻하지 않는다.
- 원본 종점 `(3.2, .05)`에서 목적 구역 중심까지 정적 횡방향/축방향 구간을 추가한다.
  구간은 최대 0.85 m, 총 8개 이하이며 기존 M2 내려놓기·위치 재추정·재파지를 쓴다.
  정적 footprint 검사는 계획 검사다. 추가 횡방향 운반·B 배치는 아직 물리 미검증이다.

## STATUS와 안전 종료

`zone_pair_status_v4`는 네 조건에서 동일하다. 고정 enum과
`robot_id, task_id, seq, state, sent_at_s, observed_at_s, frame_id, ready_until_s`만
전달한다. frame ID는 `로봇-정수번호-12자리해시` 형식이다. 작업명·목적지·역할 지시·
좌표·영상·자유문은 없다. 동결 v1 STATUS 모듈은 그대로 둔다.

heartbeat는 0.05초 주기로 보내고, 기본 0.15초(설정 가능: 0.1–0.5초)에
상대 생존 신호가 없으면 양쪽을 hold한다. 영상 readiness는 별도로 관측 시각과
frame ID에 묶이며 TTL은 0.6초다. heartbeat 재전송은 같은 증거와 만료 시각을
유지한다. 같은 frame ID에 새 관측 시각을 붙이는 재발행도 거절한다.

접근/들기/운반/내리기/방출마다 `<phase>_ready_<0..7>`을 보고한다. 공통 GO는
양쪽 준비 후 0.2초 이상 지난 공통 0.1초 격자 시각이다. 늦거나 만료된 GO는
`LATE_OR_EXPIRED_GO`로 중단한다. 정상 소비는 `<phase>_go_<0..7>` enum으로
기록한다. host의 다음 wake를 heartbeat와 다음 제어 격자 중 이른 시각으로
잡으므로 t=0.03 제출도 격자에서 실행한다. 상대가 같은 GO를 소비하지 않았으면 arm의 첫
명령 전에 `PARTNER_MISSED_GO`로 중단한다. 시간표를 늦은 소비 시각으로 이동시키지 않는다.

abort·timeout·상대 소실·controller 예외·영상 이상·낙하는 STATUS abort를 통해
양쪽 arm queue, carry schedule, host macro를 지우고 hold한다. 상세 이유는 로컬
기록에만 남긴다. 명시적 abort는 readiness TTL 만료와 같은 시각에도 우선한다.
호출자의 자유문 abort 사유는 자기 API 기록에만 남고 pair 종료 코드는 `ABORTED`다.
접근 재시도 1회, 위치 재초기화 2회, 파지 전 sweep 2회와
job deadline을 유지하며 낙하 후 자동 재파지는 없다.
완료는 양쪽 done 뒤 `PAIR_SEQUENCE_DONE / unconfirmed`다. GT 성공을 전달하지
않으며, 운반 이후 holding은 확인 전 unknown이다.

## 1차 리뷰 당시 재현과 검증

`tests/test_zone_pair_review.py`의 같은 24개 사례에 대해 기준 커밋은
**21 failed / 3 passed**였다. `git show 6bda018b:<path>`로 읽은 생산 모듈 6개를
import loader로 대체해 비교했으며 checkout/index를 쓰지 않았다.
수정 후 24개가 모두 통과했고, 기존 executor/M2/프로토콜/workflow 회귀를 포함한
당시 실행은 **293 passed / 3 deselected**였다. 당시 미제출 상대 알림과 반올림된
0.05초 시계 검사는 통신 경계·원본 시각 일치를 충분히 검증하지 못했다.
아래 2차 검증으로 대체하며 과거 통과를 물리/전체 타이밍 보증으로 쓰지 않는다.
동결 import 32개 SHA-256, M2 원본 3개 바이트 동일성, Python 10개 구문 검사와
`git diff --check`가 통과했다. 영상 gate는 기록된 저조도 JPEG 5개를 모두 수락했다.

| 항목 | 수정 전 실패를 재현한 검사 |
|---|---|
| P1-1 독립 제출 | 단독 호출 시 상대 job 생성, 명세 불일치 3종, 미제출 timeout, 역순 제출 |
| P1-2 영상 이상 | 검정·가림·균일·손상·잘림 수락 및 실제 M2 carry의 검정 영상 이동 |
| P1-3 GO·상대 소실 | 실제 M2 lift의 늦은 GO, 0.15초 heartbeat 한도, 상대 GO 미소비 |
| P1-4 readiness TTL | 새 관측 없는 heartbeat 3.2초 뒤 GO, 동일 frame의 관측 시각 변경 |
| P2 CI 누락 | glob 결과에서 M2 lift/approach/tagged-cargo 테스트 3개 미포함 |
| arm 시점 | 원본 0.05초 arm 발행 목록과 host 발행 목록 불일치 |
| 네 조건 통합 | 실제 prompt → reply validator → Transport → 독립 API 제출 → fake-host 완료 |

네 조건 통합은 no_comm의 채널 차단, 자유 한국어 mesh, 지휘자 3개 순환/star,
정형 schema·자유문 거절을 실제 구현으로 통과한다. 메시지 전달이 상대 job을
생성하지 않는 것과 UUID만 정규화한 STATUS transcript 동일성도 검사한다. 응답은 테스트용
고정 fixture이며 실제 LLM 호출이나 통신 효과 실험은 아니다.

## 2차 리뷰 재현과 검증

`tests/test_zone_pair_review2.py`의 같은 14개 반례는 `9fd4cf14` 생산 모듈에서
**14 failed**, 수정 후 **14 passed**다. 기준 소스는 `git show`로 읽고 import
loader에서만 대체했다. checkout/index 변경은 없다.

| 항목 | 수정 전 → 수정 후 검증 |
|---|---|
| NEW P1-1 host 우회 | 네 조건 × abort/timeout 8개: 상대 event/outbox/API/status/command 변화 → 모두 0건. 실제 prompt·reply validator·조건별 Transport 거절 경로 사용. BUSY 일치 조회·과거 timeout의 새 제출 거절도 차단 |
| NEW P1-2 GO 시계 | t=0.03에서 실제 M2 lift와 단계 fake 모두 늦은 GO 실패 → 양쪽 공통 격자 GO 소비 |
| NEW P2-3 abort 우선 | t=0.6 readiness 만료와 abort 동시 입력: not_ready·상대 이동 가능 → abort 패킷·양쪽 queue 제거·즉시 hold |
| NEW P2-4 arm 시계 | 2 ms를 반올림 없이 누적하고 t=3.0에 같은 1.2초 queue: 첫 명령 3.050/3.092 차이 → 양쪽 24개 명령의 전체 시각 `float.hex()`, 순서·payload 일치(첫 3.092, 끝 4.236 근방) |

2차 수정 당시 회귀는 **307 passed / 3 deselected**였다. 새 테스트는 CI 목록에
등록했고 기존 M2 lift/approach/tagged-cargo 3개 등록도 유지했다. 미제출 알림을
기대하던 기존 검사는 새 명세로 바꾸고, 기존 반올림 시계 arm 검사에도 원본 outer
loop 조건을 적용했다. 동결 import 32개 SHA-256 일치, M2 원본 3개 바이트
동일성, 수정 Python 8개 구문 검사와 `git diff --check`를 확인했다.

## 3차 리뷰와 병합 실행기 검증

공용 최소 wake에서 모든 로봇의 이벤트를 배달하던 경로를 제거했다. host는
모든 고정 physics 시각을 방문하되 로봇의 제어·macro·deadline은 자기 timer가
도래할 때만 처리하고, 이벤트는 해당 로봇의 outbox에 자기 사건이 있을 때 배달한다.
상대의 제출·polling으로 자기 시계의 부동소수 반올림이나 배달 시각이 달라지지 않는다.
arm은 기존 epsilon 없는 전역 시계를 유지하고, dead slot의 API도 즉시 거절한다.

`test_zone_pair_review3.py` 20개를 같은 fixture로 비교했다. 병합 직후 `8f4fb676`은
**19 failed / 1 passed**, 수정 후 **20 passed**다. 통과하던 1개는 main #201에서
이미 README 경로로 수정된 workflow 문서 검사다. 기준 소스는 `git show`와 import
loader로만 읽었으며 checkout/index를 쓰지 않았다.

- 네 조건 × 2 ms/10 ms 누적 시계 8개: r1만 t=2.412에 제출하는 경우와 제출하지
  않는 경우의 r2 전체 입력·poll·이벤트 배달·API·명령 목록을 내용·시각·순서까지 비교했다.
  2 ms 수정 전 반례는 같은 2.602초 `pose_uncertain`이 2.622/2.614초에 배달됐다.
  수정 후 두 경우의 전체 trace가 같고 Transport 전달은 0건이다.
- 공통 guarded driver 연결, 자기 관측·명령 1회 처리, 보정 불일치 거절,
  불확실·stale 추정·충돌 시 양쪽 중단, 접근 복구 2회 뒤 실패, 운반 중 정체,
  arm queue의 3-D 검사, dead robot 거절을 검사했다.
- 동결 `run_m2_pair.py` SHA-256은
  `3432df1fbefd4779921dc89a20f60fb67299fcdd02aa4568c6ecd14e27978783`이다.
  인자 파싱 전 MuJoCo import를 변경하지 않고 help 검사에 명시적 `importorskip`을
  넣었다. MuJoCo import를 차단한 별도 실행은 **27 passed / 1 skipped**이며
  skip 사유는 `frozen M2 CLI imports MuJoCo before parsing --help`다.
- 관련 최종 회귀는 **364 passed / 3 deselected**다. 동결 import 32개 해시와 M2
  원본 3개 바이트, Python 8개 구문, workflow 문서 실재성과 항목 33개를 확인했다.

최종 명령은 스레드 1개, worktree 임시 경로를 사용한다. 코디네이터가 확인한
MuJoCo 없는 계약·단위 검사 범위이므로 agent_lock과 공용 잠금 파일은 건드리지 않았다.

```sh
mkdir -p .pytest_tmp_env
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.pytest_tmp_env" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_review3.py tests/test_zone_pair_review2.py tests/test_zone_pair_review.py \
  tests/test_zone_pair_executor.py tests/test_zone_pair_status.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_host.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_boundaries.py \
  tests/test_pair_owncam_approach.py tests/test_m2_pair_door_v3.py \
  tests/test_simulation_workflow_manager.py tests/test_zone_study_protocol.py \
  tests/test_simulation_scenes.py --basetemp=./.pytest_tmp \
  -k 'not test_team_host_isolation_abort_and_horizon_on_the_real_world and not test_source_fingerprint_includes_calibration_requirements_and_sparse_absence and not test_parent_exit_cleans_background_child'
```

실제 MuJoCo world 검사, 임시 `.git` 쓰기 검사, sandbox에서 `ps`가 차단되는 자식
종료 검사 3개는 제외했다. 새로 CI에 등록한 cargo scene 물리 검사는 이 로컬 실행에
포함하지 않았다. 물리 smoke/cohort와 LLM 호출은 없고 TensorBoard 실험 결과도
새로 만들지 않았다. 원본 구현 당시 기록은 182 passed / 3 deselected였다.
workflow 양쪽 항목을 보존한 33개와 동결 import 32개 해시·M2 원본 3개는 유지한다.
코디네이터는 변경 파일을 commit하고 전체 CI 및 별도 dev 물리 검증을 수행해야 한다.

## dev PHYSICAL 점검 게이트 — 3차 리뷰에서 이관

아래는 실행 전 충족할 조건이며 이번 작업에서 물리 실행을 완료했다는 뜻이 아니다.

1. **코드:** 네 조건에서 미제출 상대의 입력·이벤트·API·명령 내용·시각·순서 전체가
   동일한 회귀와 두 CI 차단 사항을 해결한다. 로컬 검사는 위 결과이고 전체 CI는 별도다.
2. **실행 경로:** 새 `PairTeam`/`OwnCamTeamHost`를 실제 사용하는 dev 드라이버를
   커밋하고 표준 workflow에 연결한다. 기존 `run_m2_pair.py` 단독 실행은 새 adapter의
   검증으로 인정하지 않는다.
3. **환경:** r1/r2, long_beam 1개, `zone_wide_door_tags_v2`, weld OFF,
   `cargo_noslip_v1`, 실제 `noslip_iterations=10`, timestep 2 ms를 확인한다.
   현재 host는 세 로봇을 생성한다. 실제 장면이 두 대여야 하면 이를 먼저 지원하고,
   참여자만 두 대라면 r3의 존재와 비간섭을 명시한다.
4. **입력:** tagged 위치추정 provider를 임시 dev 조건으로 표시하고 지도·보정·정적
   주문서 해시를 고정한다. 제어에는 자기 wrist RGB·자기 명령·허용 정적 입력·STATUS만
   제공하며 GT는 평가에만 기록한다.
5. **운영·종료:** 자기 worktree에서 실행 소스를 고정하고 실행 수·seed·SIM/wall
   상한을 사전 기록한다. 잠금 규칙과 부하 기록을 준수한다. 정상/중단 경로의 GO 동시
   소비, abort·영상 이상·상대 소실 뒤 양쪽 queue 제거와 추가 동작 명령 0건을 확인한다.
6. **판정·증거:** 접근→공동 파지→들기→문 통과→목적 구역 배치·방출을 영상과 별도
   평가로 확인한다. `PAIR_SEQUENCE_DONE / unconfirmed`만으로 성공 처리하지 않는다.
   새 B 구역 경로의 도착·낙하·접촉 기준을 실행 전에 고정하고, 실패 포함 원본 입력·
   명령·STATUS·평가·영상·해시를 보존한 뒤 TensorBoard 실제 로딩까지 확인한다.

## 참고 자료

- 코디네이터 제공 독립 리뷰: `codex-235-review.md` (기준 `6bda018b`, P1 4건/P2 1건)
- 코디네이터 제공 2차 리뷰: `codex-235-review2.md` (기준 `9fd4cf14`, NEW P1 2건/P2 2건)
- 코디네이터 제공 3차 리뷰: `codex-235-review3.md` (기준 `69dd0f0b`, P1 1건/P2 2건)
- [공통 guarded driver](../../harness/zone_own_driver.py), [공동 운반 가드](../../harness/zone_pair_guards.py), [3차 회귀](../../tests/test_zone_pair_review3.py)
- [M2 경로·검증 범위](../zone_m2_pair.md), [동결 제어기](../../scripts/run_m2_pair.py)
- [M2 동결 import](../../experiments/2026-09-26-zone-m2-pair/imports.json)
- [executor](../../harness/zone_own_executor.py), [STATUS](../../harness/zone_pair_status.py)
- [조건별 프로토콜](../../harness/zone_study_protocol.py), [적대 회귀](../../tests/test_zone_pair_review.py)
- [개발 지침](../../CONTRIBUTING.md), [프로젝트 지침](../../AGENTS.md)
