# M2 공동 운반 executor 연결 — 2026-09-27

이슈 #221 / PR #235의 `zone_pair_executor_v2_dev` 설계다. 기준 커밋
`6bda018b`의 독립 적대 리뷰(P1 4건, P2 1건)와 코디네이터의 랑데부 결정을
반영했다. M2 물리 성공을 새 executor에 승계하지 않는다.

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
제출한 로봇은 `job_failed`, 아직 작업이 없는 상대는 `pair_refused`를 받는다.
이 알림에는 거절 코드와 의미 없는 rendezvous ID만 들어가며 상대 작업 내용을
전달하지 않는다. 늦게 도착한 제출도 timeout으로 거절한다. 자기 busy/stopped/
불확실한 pose/짐 보유/잘못된 영상은 자기 제출을 거절하며, 대기 중인 짝도 종료한다.
`enable_pair_carry(..., rendezvous_timeout_s=5., heartbeat_timeout_s=.15)`로 한도를 설정한다.

## 제어·영상 경계

- 동결된 `M2DoorStudent(version='v3')`, `PairApproachDriverV2`, `fullframe_v3`,
  `ArmSequence`를 import한다. 원본 CLI와 동결 import 파일은 편집하지 않았다.
- 입력은 자기 wrist RGB·발행 명령, 정적 지도·보정·개략 주문서와 STATUS뿐이다.
  endpoint 객체 그래프에 host/world/상대 executor·controller가 없다.
- `zone_pair_vision.valid_frame`이 수락·STATUS readiness·운반 유지 판정보다 먼저
  자기 영상의 소유자/시각/hash, JPEG 시작·종료/디코드/크기, 유효 FOV의 검정 비율과
  대비를 검사한다. 검정·넓은 검정 가림·균일 영상·손상/잘린 JPEG는 즉시 거절/중단한다.
  어두운 grip band와 저조도 v3 기록은 유지한다. 임의의 질감 있는 가림까지 검출한다는
  뜻은 아니며, 임계값은 물리 검증 전 dev 방어 조건이다.
- controller는 0.1초, arm과 안전 점검은 0.05초로 분리했다. 새 영상 요청 중에는
  controller timer를 진행하지 않는다. 1.2초 arm queue의 24개 명령을 원본
  `ArmSequence.tick(0.05)` 실행과 비교해 시각·순서·내용 일치를 검사한다.
- 원본 종점 `(3.2, .05)`에서 목적 구역 중심까지 정적 횡방향/축방향 구간을 추가한다.
  구간은 최대 0.85 m, 총 8개 이하이며 기존 M2 내려놓기·위치 재추정·재파지를 쓴다.
  정적 footprint 검사는 계획 검사다. 추가 횡방향 운반·B 배치는 아직 물리 미검증이다.

## STATUS와 안전 종료

`zone_pair_status_v3`는 네 조건에서 동일하다. 고정 enum과
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
기록한다. 상대가 같은 GO를 소비하지 않았으면 다음 0.05초 점검에서 arm의 첫
명령 전에 `PARTNER_MISSED_GO`로 중단한다. 시간표를 늦은 소비 시각으로 이동시키지 않는다.

abort·timeout·상대 소실·controller 예외·영상 이상·낙하는 STATUS abort를 통해
양쪽 arm queue, carry schedule, host macro를 지우고 hold한다. 상세 이유는 로컬
기록에만 남긴다. 접근 재시도 1회, 위치 재초기화 2회, 파지 전 sweep 2회와
job deadline을 유지하며 낙하 후 자동 재파지는 없다.
완료는 양쪽 done 뒤 `PAIR_SEQUENCE_DONE / unconfirmed`다. GT 성공을 전달하지
않으며, 운반 이후 holding은 확인 전 unknown이다.

## 적대 리뷰 재현과 검증

`tests/test_zone_pair_review.py`의 같은 24개 사례에 대해 기준 커밋은
**21 failed / 3 passed**였다. `git show 6bda018b:<path>`로 읽은 생산 모듈 6개를
import loader로 대체해 비교했으며 checkout/index를 쓰지 않았다.
수정 후 24개가 모두 통과했고, 기존 executor/M2/프로토콜/workflow 회귀를 포함한
최종 실행은 **293 passed / 3 deselected**였다. 대기 중 abort/episode 종료 알림과
0.1초 격자 사이에서 시작한 host의 동일 GO 시각도 검사했다.
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
생성하지 않는 것과 최종 STATUS transcript 동일성도 검사한다. 응답은 테스트용
고정 fixture이며 실제 LLM 호출이나 통신 효과 실험은 아니다.

최종 명령은 스레드 1개, worktree 임시 경로를 사용한다. 코디네이터가 확인한
MuJoCo 없는 계약·단위 검사 범위이므로 agent_lock과 공용 잠금 파일은 건드리지 않았다.

```sh
mkdir -p .pytest_tmp_env
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.pytest_tmp_env" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_review.py tests/test_zone_pair_executor.py tests/test_zone_pair_status.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_host.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_boundaries.py \
  tests/test_pair_owncam_approach.py tests/test_m2_pair_door_v3.py \
  tests/test_simulation_workflow_manager.py tests/test_zone_study_protocol.py --basetemp=./.pytest_tmp \
  -k 'not test_team_host_isolation_abort_and_horizon_on_the_real_world and not test_source_fingerprint_includes_calibration_requirements_and_sparse_absence and not test_parent_exit_cleans_background_child'
```

실제 MuJoCo world 검사, 임시 `.git` 쓰기 검사, sandbox에서 `ps`가 차단되는 자식
종료 검사 3개는 제외했다. 새로 CI에 등록한 cargo scene 물리 검사는 이 로컬 실행에
포함하지 않았다. 물리 smoke/cohort와 LLM 호출은 없고 TensorBoard 실험 결과도
새로 만들지 않았다. 원본 구현 당시 기록은 182 passed / 3 deselected였다.
workflow 양쪽 항목을 보존한 33개와 동결 import 32개 해시·M2 원본 3개는 유지한다.
코디네이터는 변경 파일을 commit하고 전체 CI 및 별도 dev 물리 검증을 수행해야 한다.

## 참고 자료

- 코디네이터 제공 독립 리뷰: `codex-235-review.md` (기준 `6bda018b`, P1 4건/P2 1건)
- [M2 경로·검증 범위](../zone_m2_pair.md), [동결 제어기](../../scripts/run_m2_pair.py)
- [M2 동결 import](../../experiments/2026-09-26-zone-m2-pair/imports.json)
- [executor](../../harness/zone_own_executor.py), [STATUS](../../harness/zone_pair_status.py)
- [조건별 프로토콜](../../harness/zone_study_protocol.py), [적대 회귀](../../tests/test_zone_pair_review.py)
- [개발 지침](../../CONTRIBUTING.md), [프로젝트 지침](../../AGENTS.md)
