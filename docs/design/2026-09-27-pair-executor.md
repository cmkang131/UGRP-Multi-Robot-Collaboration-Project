# M2 공동 운반 executor 연결 — 2026-09-27

이슈 #221, PR #203/#205의 M2와 PR #206의 개별 executor를 연결한
`zone_pair_executor_v1_dev` 구현이다. 새 물리 성공 기록이 아니다.
Git index·commit·merge·fetch는 건드리지 않고 코디네이터에게 변경 파일을 인계한다.

## API와 지원 범위

```python
# 설정 시 고정하는 자료. world의 현재 좌표에서 만들지 않는다.
spec['team_cargo'] = [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': [1.0, .05, 0.]}]
spec['order_sheet'] = {'orders': [{
    'order_id': 'cargoX', 'kind': 'long_beam', 'count': 1, 'required_robots': 2,
    'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P2', 'slot': 'P2-3'}}]}
spec['pair_order_sheets'] = {'cargoX': coarse_order_sheet([1.0, .05, 0.])}
spec['contact_profile'] = 'cargo_noslip_v1'
# OwnCamTeamHost(..., frames_dir=<기본 checkout outputs 아래 새 경로>)
# 각 로봇의 look_around / 자기 위치 추정이 확보된 뒤:
ack = host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
# r2에도 같은 작업을 배정하고, 둘 중 하나의 abort로 양쪽을 중단한다.
host.call('r2', 'abort', 'caller_abort')
```

`coarse_order_sheet`는 기존 `harness.pair_owncam_approach`의 함수다.
단일 long_beam, 고정 역할 r1=end_neg/r2=end_pos, M2 문 지도와 문 앞
개략 주문서 범위만 지원한다. 다른 로봇 조합·물체 종류·목적 슬롯·문 밖
초기 배치는 명시적으로 거절한다. `target_zone`은 주문의 목적 구역이어야 한다.
기존 `deliver`는 계속 M1 청록 상자용이다.

`PairTeam`은 host 쪽에서 각 로봇에 같은 정적 작업을 전달한다. 각 로봇은
자신의 busy/stopped/불확실한 위치/짐 보유 여부/주문 일치를 고정 enum으로
응답한다. 양쪽이 수락한 뒤에만 `pair_carry` 작업이 시작된다. 로봇 endpoint는
자신의 executor와 자기 명령 buffer만 가지며 host·상대 executor를 참조하지 않는다.
잘못된 호출 인자는 `accepted=False`로 돌려준다. 별도 구성 없이 직접 호출한
`ZoneOwnExecutor.pair_carry`는 `PAIR_REQUIRES_TEAM_DISPATCH`를 반환한다.

## 제어와 입력 경계

- `scripts/run_m2_pair.py`의 `M2DoorStudent(version='v3')`,
  `PairApproachDriverV2`, `fullframe_v3` 유지 검사를 import한다. 원본 CLI와
  `imports.json`의 동결 파일은 편집하지 않는다. arm 보간기는 기존
  `ArmSequence`만 재사용하며 교사의 좌표 제어기는 호출하지 않는다.
- 로봇 입력은 자기 `robot_cam`, 자기 발행 명령, 정적 지도·보정,
  개략 주문서와 STATUS뿐이다. `_OwnPort`는 자기 executor의 검증된 최신
  JPEG만 읽는다. M2 tick 전에 같은 SIM 시각의 새 프레임을 요구해 arm 이동
  이전 영상을 재사용하지 않는다. M2에는 자체 위치 추정기가 있으며 M1 executor의 기존
  위치 추정기는 수락 gate/자기 상태 보고용으로 유지한다. 둘 다 자기 입력만 받는다.
- 기존 M2 종점 `(3.2, .05)`는 B 구역이 아니다. 어댑터가 문 뒤의 정적
  횡방향·축방향 구간을 덧붙여 목적 구역 중심까지 계획한다. 0.85 m 이하
  구간마다 M2의 내려놓기·위치 재추정·재파지를 그대로 쓴다. 최대 8구간,
  고정 방향의 두 로봇+beam footprint로 정적 벽과 경계를 검사한다.
  계산 경로는 실제 통과 증거가 아니다. 추가 횡방향 운반은 미검증 후보다.
- M2 문 정렬에 필요한 자기 grasp pose가 없으면 양쪽이 실패한다.
  한쪽만 정렬 시간을 생략하는 기존 선택 경로는 이 어댑터에서 거절한다.
- host에는 catalogue cargo를 배치하는 `TaggedCargoZoneScene` 선택 경로와
  평가 전용 cargo 좌표·접촉 기록을 붙였다. 이 정보는 endpoint에 전달하지 않는다.

## 상태 채널과 종료

`zone_pair_status_v2`의 wire field는 `robot_id, task_id, seq, state, sent_at_s`뿐이다.
task_id는 의미 없는 실행 번호다. 작업명·역할 지시·좌표·영상·자유문·frame id는
전송하지 않는다. 무통신/자유 한국어/순환 지휘자/정형 네 조건에서 동일하다.
동결된 v1 STATUS 모듈은 변경하지 않는다.

시작은 `start_ready`, 각 구간의 접근/들기/운반/정지/방출은
`<phase>_ready_<0..7>`의 유한 enum으로 동기화한다. 기존 M2의
`PairCarrySync` 인터페이스에는 이 STATUS transcript만 읽는 로컬 어댑터를
넣는다. 공유 barrier 객체나 상대의 비공개 controller 상태는 쓰지 않는다.
양쪽 readiness 이후 0.2 SIM초에 GO가 가능하며 수락 취소·재전송·다른 task·
오래된 heartbeat·미래 시각 메시지를 방어한다. host는 두 로봇을 같은
0.1 SIM초 control cadence로 호출한다. arm 명령도 이 cadence에서 내보내므로
기존 CLI의 0.05초 arm tick과 다르며 과거 성공 판정을 승계하지 않는다.

abort, 로컬 timeout, controller 예외, episode 종료, 상대 abort/2초 초과 침묵,
자기 RGB의 낙하/들림 실패는 `abort` enum을 거쳐 양쪽 arm queue·운반 schedule·
host macro를 지우고 즉시 hold한다. 자신의 실패 이유는 로컬 로그에만 남긴다.
각 수락 작업은 종료 이벤트를 정확히 한 번 낸다. M2의 접근 재시도 1회,
위치 재초기화 2회, 파지 전 look sweep 2회와 job deadline을 유지한다.
낙하 후 자동 재파지는 하지 않는다.

`pair_progress`는 로컬 단계 이벤트이며 추가 LLM 호출 trigger는 없다.
두 로봇의 `done` enum이 모여야 `job_done`을 낸다. 결과는
`PAIR_SEQUENCE_DONE / unconfirmed`다. M2의 release 영상과 시간표만으로
요청 구역 안의 배치를 확인할 수 없으므로 `own_camera_confirmed`를 선언하지 않는다.
종료 후 holding은 보수적으로 unknown이며, 자동으로 다음 운반을 수락하지 않는다.

## 검증과 인계

- workflow 충돌은 양쪽 항목을 보존해 33개로 정리했다. Git의 unmerged index
  해제(`git add`)와 merge commit은 코디네이터가 해야 한다.
- `tests/test_zone_pair_executor.py`, `tests/test_zone_pair_status.py`를 CI 목록에
  추가했다. 수락/거절, 채널만을 통한 rendezvous, 양쪽 abort·timeout·침묵·예외·
  낙하·episode 종료, 비공개 상태 격리, v3 실제 클래스/기록 JPEG, bounded recovery,
  네 조건의 동일 wire 기록과 동결 import 해시를 검사한다. 실제 host scheduler를
  fake world로 구동해 10개 체크포인트의 양쪽 GO 시각과 공동 완료를 확인했다.
  실제 M2 factory와 첫 제어 tick은 MuJoCo import 자체를 차단한 자식 프로세스에서도
  통과했다. 물리 실행은 없다.
- 위 신규 테스트는 **55 passed**, 관련 executor/M2/workflow 회귀까지 합친 최종
  실행은 **182 passed, 3 deselected**였다. 체크포인트 통합 검사에서 발견한
  `3.2 + 0.2` / `3.4` 비교 오차를 고쳤다. 첫 소비자의 GO 이후 상태 전환을
  상대가 readiness 철회로 잘못 처리하던 문제이며, 같은 GO 시각을 양쪽이 소비한다.
- AST 구문 검사와 동결 import 32개 SHA-256 일치를 확인했다. 실행기·접근·v3
  들림 모듈도 merge index의 원본과 바이트가 같다.
- 코디네이터가 짧은 MuJoCo 없는 계약·단위 검사는 agent_lock 대상이 아니라고
  확인했다. 스레드 수를 1로 제한하고 worktree 내부 임시 경로를 사용했으며,
  이 테스트 실행에서 공용 잠금 파일을 건드리지 않았다.
- 첫 관련 회귀는 127 passed / 1 failed / 2 deselected였다. 실패한
  `test_parent_exit_cleans_background_child`는 sandbox가 `ps` 실행을
  `PermissionError: [Errno 1] Operation not permitted`로 차단해 자식 종료 확인을
  마치지 못했다. 제품 코드를 바꿔 우회하지 않았고 최종 실행에서는 제외했다.
  다른 제외 2개는 실제 MuJoCo world 검사와 임시 `.git`에 쓰는 source-fingerprint
  검사다. 세 검사는 코디네이터 환경에서 별도 확인해야 한다.
- 물리 smoke/cohort·LLM 호출·실제 목적 구역 배치 확인은 미실행이다.
  실험 결과를 새로 생성하지 않아 TensorBoard 변환/기동도 하지 않았다.
  GitHub 조회는 네트워크 연결 실패로 최신 PR 상태를 확인하지 못했다.

최종 실행 명령(성능 비교가 아닌 계약·회귀 검사):

```sh
mkdir -p .pytest_tmp_env
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 GIT_OPTIONAL_LOCKS=0 PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.pytest_tmp_env" \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_pair_executor.py tests/test_zone_pair_status.py \
  tests/test_zone_own_executor.py tests/test_zone_own_executor_host.py \
  tests/test_zone_own_executor_guards.py tests/test_zone_own_executor_boundaries.py \
  tests/test_pair_owncam_approach.py tests/test_m2_pair_door_v3.py \
  tests/test_simulation_workflow_manager.py --basetemp=./.pytest_tmp \
  -k 'not test_team_host_isolation_abort_and_horizon_on_the_real_world and not test_source_fingerprint_includes_calibration_requirements_and_sparse_absence and not test_parent_exit_cleans_background_child'
```

코디네이터는 파일 검토·stage 후 진행 중인 merge를 commit하고 전체 CI를 확인한다.
별도 물리 검증은 커밋한 소스를 고정하고 물리 잠금·스레드 제한·dev 표기 아래
수행하며, 추가 횡방향 운반과 B 배치를 실행 번들·raw·TensorBoard로 검증해야 한다.

## 참고 자료

- [M2 경로·검증 범위](../zone_m2_pair.md), [원본 제어기](../../scripts/run_m2_pair.py)
- [M2 동결 import](../../experiments/2026-09-26-zone-m2-pair/imports.json)
- [개별 executor](../../harness/zone_own_executor.py), [host](../../harness/zone_own_team_host.py)
- [기존 STATUS 계약](../../harness/team_carry_status.py), [study-core 계약](../../harness/zone_study_contract.py)
- [개발·공용 잠금 규칙](../../CONTRIBUTING.md), [프로젝트 지침](../../AGENTS.md)
