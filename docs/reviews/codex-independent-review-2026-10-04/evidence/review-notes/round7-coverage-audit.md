# 7차 coverage audit — tool schema, observer replay, SIM slot admission

2026-10-03. 코드 기준은 main `f2577bb5121748644df31eb0fc5a1c1b94b80d80`이다. 이번 작업은 **덜 검토된 세 경계를 실제 caller와 작은 오프라인 반례/대조군까지 읽은 것**이다. 전체 저장소 완독이나 현재 E2E 재검증을 뜻하지 않는다.

확정 신규 항목은 보존된 SIM tool adapter의 **catalog 기본값과 실제 validator 불일치 1건**이다. 최신 pair #363/#371의 필수 실행 경로가 아니므로 현재 E2E 차단 원인으로 승격하지 않는다. observer/replay와 SIM slot admission에서는 아래 확인 범위의 추가 결함을 확정하지 않았다.

소스 구현, Git 상태, 외부 서비스에 쓰지 않았다. 실험/raw/blind/heldout 원본, 모델 가중치, 실제 호스트 lock은 열거나 수정하지 않았다. 물리·GPU·모델·네트워크·실물 실행은 없었다. 합성 temporary tree와 fake transport만 사용했다. `git status --short`는 작업 전후 모두 빈 출력이었다.

## 1. 이전 검토와 중복하지 않은 선택

먼저 `AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`를 읽고 기존 architecture/config-docs, round2–6, final-independent-triage, final execution/optional/research issue 및 publication manifest의 범위/반증을 대조했다.

| 영역 | 기존 coverage의 근거 | 7차 실제 선택/판정 |
|---|---|---|
| 공통 CLI·config·모델 packaging | `round4-source-contracts.md`가 `sim/session_config.py`, `session_extensions.py`, `scripts/sim_cli.py`, 모델 ZIP 전체 읽기와 override 재검증을 이미 기록 | generic config drift, ZIP traversal, env omission을 재발견으로 반복하지 않음 |
| 도구 catalog·serialization | `round4-source-contracts.md`의 “다음 미심층” 4번은 `harness/registry.py`, `catalog.py`, `can_skill_registry.py`, `sim/bridge_client.py`를 명시 | 네 파일 전체 + 실제 `loop.dispatch`/CLI/REAL·SIM adapter의 default와 범위 적용까지 연결 |
| observer/native/replay | 같은 문서의 “다음 미심층” 3번은 `dispatch_native_process.py`, `dispatch_replay.py`와 `sim_dispatch.py` caller를 명시 | observer 두 구현/recorder/loader/zone wrapper 전체 + 현재 dispatch setup/finalization caller + fake 종료와 합성 replay 검사 |
| 운영 ownership/admission | `round2-architecture.md` 미심층 4번에 `agent_sim_slots.py`, `agent_lock.py`가 명시 | 두 파일 및 두 test 파일 전체 + `run_final_pair_fast.py`, `run_final_pair_loaded.py`의 admission caller 구간 검토 |
| disk dedupe 후보 | 4차 후속 목록과 `tree_manifest.py` 주석이 `disk_dedupe.py`를 가리킴 | 이 SHA의 `git ls-tree -r --name-only HEAD scripts`에는 해당 파일 자체가 없음. sparse 미수신으로 가정하거나 없는 구현의 결함을 주장하지 않고 SIM slot으로 전환 |

Root의 최신성 담당은 이후 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`가 정책/문서 4커밋만 추가됐다고 전달했다. 이 보고서의 실제 소스 검토/재현 SHA는 여전히 위 f2577bb다. 최신 이미지 보존/정리 정책을 과거 규칙으로 대체하지 않았으며, 정리 도구 실행이나 보존 정책의 새 오류 판정은 하지 않았다.

known finding인 directory symlink receipt, ENOSPC tee, legacy late usage, ACT pipe timeout, train/dev overlap, Kaggle refresh reuse, 실물 stop/servo, RL reset, WS idempotency, pack_frames는 신규 개수에 포함하지 않았다. runtime_round7가 맡은 own_status/look_around/message/control causal 경계도 확장하지 않았다.

## 2. C7-1 — SIM tool catalog의 정상 기본 횡이동이 실행 전에 거절됨

**우선순위/경로:** 해당 보존 adapter를 재사용할 때의 P2 correctness, 전체 현재 작업에서는 낮은 우선순위다. `docs/browser_ui_retirement_20260923.md:8–15`는 구형 UI/표준 `--chat`을 제거하고 내부 API·상태 처리만 보존했다고 명시한다. 이 finding을 현재 표준 native dispatch 또는 pair v100의 장애로 연결하지 않는다. `harness/cli.py:38–48`의 명시적 `--actions scripts/sim_actions.py`와 보존된 내부 caller에서 선택 가능한 코드 경계다.

### Source 흐름

1. [scripts/robot_actions.py:92–105](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/robot_actions.py#L92-L105)는 `move_left`, `move_right`에 `speed=65`, `duration=.65`를 선언한다.
2. [scripts/sim_actions.py:18–29](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/sim_actions.py#L18-L29)는 REAL의 ACTION_PARAMETERS를 그대로 복사한다. 주석도 동일 action+arguments 계약이라고 한다.
3. `harness/catalog.py:_action_parameters/default_registry`(118–164)는 이 default를 Tool에 넣고, [harness/registry.py:169–174](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/registry.py#L169-L174)는 모델이 args를 생략하면 실제 handler 인자에 default 65를 채운다.
4. [scripts/sim_actions.py:_validate_params:191–205](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/scripts/sim_actions.py#L191-L205)는 모든 non-stop primitive에 31≤speed≤40만 허용한다. 횡이동 분기가 없다.
5. 같은 파일 `run_for_robot:334–337`는 validator를 `_bridge_health`와 POST보다 먼저 부른다. `harness/loop.py:1777–1801`은 이 ValueError를 `TOOL_EXCEPTION`, `ok=false`로 돌려준다. 무인자 횡이동의 실패는 실제 SIM 가용성/하드웨어와 무관하게 결정된다.

### 합성 반례와 대조군

`round7-coverage-repro.py:catalog_contract`는 실제 catalog, `validate_args`, `loop.dispatch`, `sim_actions.run/run_for_robot`를 사용한다. fake를 넣은 곳은 `_bridge_health`, `_post_bridge_action`, observer용 `team_bus.record_event`뿐이다. catalog에는 실제 SIM run 함수를 명시적으로 runner로 넣어 patched function과 동일한 구현을 호출한다. 물리 동작은 없다.

| 호출 | 정규화된 speed/duration | 결과 | fake bridge POST |
|---|---:|---|---:|
| `move_forward({})` | 35 / .30 | ok=true | 1 |
| `move_backward({})` | 35 / .30 | ok=true | 1 |
| `turn_left({})` | 35 / .30 | ok=true | 1 |
| `turn_right({})` | 35 / .30 | ok=true | 1 |
| `move_left({})` | 65 / .65 | TOOL_EXCEPTION | 0 |
| `move_right({})` | 65 / .65 | TOOL_EXCEPTION | 0 |
| 양 횡이동에 speed=35 명시 | 35 / .65 | ok=true | 각각 1 |

두 실패의 reason은 `ValueError: primitive speed must be between 31 and 40; values <=30 do not move this chassis`다. 대조군의 ok는 fake bridge 왕복을 뜻하며, speed=35의 실제 횡이동 성공이나 추천값을 뜻하지 않는다.

같은 schema drift의 부수 확인: REAL prompt의 speed description은 `31..40`/`31..70`지만 REAL `run:585–586`은 최소35를 적용한다. 실제 `robot_actions.run('move_forward', speed=31, duration=.30)`는 파일/프로세스 접근 전에 ValueError다. 이것은 별도 버그 건수로 나누지 않았다.

### 기존 테스트가 놓친 조합

- `tests/test_real_primitives.py:31–76`은 REAL catalog default/metadata, fake runner forwarding, wrong primitive type을 검사한다. SIM의 실제 `_validate_params`와 default 횡이동을 연결하지 않는다.
- `tests/test_planner_input_parity.py:7–28`은 REAL/SIM 이름 집합과 prompt의 존재를 검사하고, 같은 파일의 61–79는 search에 fake bridge를 연결해 GT geometry projection을 검사한다. 횡이동 default의 실행 가능성은 검사하지 않는다.
- 해당 catalog/parity 테스트들이 통과하는 상태에서 위 두 반례가 재현된다. 모든 catalog 검사가 잘못됐다는 뜻은 아니며, schema의 default를 해당 backend의 validator까지 보내는 조합이 빠진 것이다.

**최소 수용 기준:** 지원할 REAL/SIM primitive 계약의 default/range/description을 한 버전으로 맞추고, 양 adapter에 모든 public primitive의 default를 보내어 validation까지 통과하는지 검사한다. REAL 최소35 제한을 prompt에 맞추려고 낮추는 수정은 요구하지 않는다. 별도 SIM 제약이 의도라면 SIM catalog에 명시적으로 다른 default/range를 노출해야 한다. 기존 frozen bundle bytes를 묵시적으로 수정하지 않고 재사용하는 경로의 새 버전에 적용할 사안이다. 이번 작업에서 수정은 하지 않았다.

## 3. Observer/replay — 확인된 방어와 남은 범위

**경로 구분.** `scripts/sim_dispatch.py:83–108`는 기본 desktop 실행에서 계산 후 replay를 선택하고, live/realtime 실행에서는 viewer를 선택한다. `run_dispatch_skills.py:1593–1607`가 native observer 또는 ReplayRecorder를 연결한다. 둘은 로봇 입력/심판 경로가 아니다. `configs/simulation_workflows.json:41–74`의 등록된 일반 RGB dispatch이며 현재 own-camera pair control과 별도다.

| 경계 | 소스/실제 검사 | 판정 |
|---|---|---|
| 상태 mailbox | `dispatch_native_process.StateMailbox.transact:34–43`의 LOCK_NB, owner가 `_exchange:96–108`에서 state를 복사하고 observer가 `observe:185–201`에서 별도 state copy를 읽음 | 실제 temp mmap에 다른 descriptor의 flock을 잡으면 callback을 실행하지 않고 None. 기존 coherence 테스트도 통과 |
| observer cleanup | `IsolatedDispatchNativeView.close:135–158` | fake Process의 두 번 TimeoutExpired 뒤 terminate→kill→wait→mailbox close→scratch/log close, repeated close는 재호출 없음. 실 OS process kill은 실행하지 않음 |
| 기록 identity | `ReplayRecorder.close:61–90`, `load:93–116` | 합성 model bytes와 2프레임 배열을 실제 NumPy 압축/해시/manifest로 기록. fake model loader로 정상 roundtrip. `labels.json`만 변경하면 실제 load가 model loader 앞에서 거절 |
| 관측/제어 방향 | recorder.sample은 owner state에서 copy, replay.play는 별도 model/data에 kinematic forward; native observer는 별도 process·model·data | GUI state가 actor/control state로 역전송되는 경로를 찾지 못함. pause/quit 명령은 의도된 operator control로 구별 |
| caller finalization | `run_dispatch_skills.py:1786–1793`은 team/video/replay/scene cleanup을 각 try로 호출 | 하나의 cleanup 실패가 뒤 callback의 시도를 생략한다는 일반 가설은 이 caller에서 반박됨 |

**새 finding으로 올리지 않은 것:** replay manifest를 임의로 재작성해 hash key를 없애는 공격은 정상 recorder가 만드는 산출물이 아니며, 적대적 signed artifact 검증을 제공한다고 문서가 주장하지 않는다. 이 조건만으로 current provenance 결함을 추가하지 않았다. zone replay의 `view.json`과 dialogue overlay가 replay motion files의 해시에 없다는 사실도 observer framing/text의 범위이며, 제어 입력 변조로 표현하지 않는다.

**미검증:** MuJoCo binary model 호환성/GUI/실제 viewer close 지연, 실제 렌더·동역학, OS parent PID 재사용, abrupt process death 시 recording 복구, 고장 난 storage의 모든 finalization 조합은 실행하지 않았다. mailbox가 fail-fast라는 것은 실시간 성능 인증이 아니다. 정상 model parse/physics roundtrip 테스트는 이번 선택에 포함하지 않았다.

## 4. SIM slot admission — 확인된 방어와 남은 범위

`agent_sim_slots.py`는 같은 non-timing-sensitive coordinator PID/owner 아래 SIM slot을 묶는 선택 경로다. `run_final_pair_fast.py:123–157`와 `run_final_pair_loaded.py:154–188`은 명시적인 `--sim-slot`일 때 owner+branch를 검사한다. 이들 runner source의 admission 구간만 읽었고 해당 heldout/loaded 입력 파일이나 실행 결과는 열지 않았다. 기본값은 exclusive lock 경로다.

| 검사 | source | 실제 결과 |
|---|---|---|
| preview 불변 | `sim_snapshot:64–75` | root가 없는 temp 경로를 조회해도 root가 생기지 않음 |
| writer atomic publish/중재 | `_admission:26–34`, `_write_owner:91–95`, `_acquire:98–109` | 기존 동시 contender/부분 JSON 테스트 통과. lock dir mkdir와 admission flock의 책임을 구분 |
| owner/branch/coordinator binding | `_identity:78–79`, `_require_physics:82–88`, `require_sim_slot:138–148` | temp-root의 owner/branch 불일치 거절; 기존 다른 coordinator/replaced coordinator tests 통과 |
| 마지막 slot 전 physics 보존 | `release:151–164` | 두 slot 중 첫 release 뒤 physics bytes 유지, 마지막 release 뒤만 managed physics 해제 |
| incomplete owner/slot | `sim_holders:52–55`, `acquire_sim_slot:120–130` | owner가 없는 physics directory에서 새 slot을 만들지 않음; partial legacy JSON/incomplete slot 회귀도 통과 |

**반증/범위:** incomplete lock의 자동 삭제를 하지 않는 것은 다른 작업을 보호하는 fail-closed 설계다. 명시적 복구가 필요하다는 모듈 계약을 임의 cleanup 누락으로 바꾸지 않았다. `agent_lock`은 사용자가 지정하는 cooperative owner 문자열·PID 기반 도구이며 보안 인증 서비스가 아니다. 허가되지 않은 lock 파일 편집이나 다른 process kill을 가정한 finding을 추가하지 않았다.

**미검증:** PID start identity가 저장되지 않으므로 OS PID 재사용을 구별하지 못하는 일반 한계는 남는다. 이번에는 재사용까지 이어지는 현재 실제 driver 부작용을 입증하지 않았고 confirmed bug로 올리지 않았다. coordinator가 모든 worker보다 오래 살아야 한다는 전제/명시적 legacy release의 운영 위반, host reboot, fsync 전 machine crash도 검증하지 않았다. 실제 공용 host lock에는 접근하지 않았다.

## 5. 실행 기록과 재현

자립 재현: `/workspace/scratch/21cbee94d5d2/review-notes/round7-coverage-repro.py`.

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/ugrp-review-cv/bin/python /workspace/scratch/21cbee94d5d2/review-notes/round7-coverage-repro.py
```

이 스크립트의 catalog 반례와 observer/slot 대조군은 모두 통과했다. NumPy만 필요하며 MuJoCo와 네트워크가 없어도 실행된다. observer의 `load`에는 명시적인 fake model loader를 넣으며 physics API를 호출하지 않는다.

기존 표적 테스트 명령:

```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/ugrp-review-cv/bin/python -m pytest -q -p no:cacheprovider \
 tests/test_agent_sim_slots.py tests/test_agent_lock.py tests/test_dispatch_native_process.py \
 tests/test_real_primitives.py::PrimitiveCatalogTests \
 tests/test_harness.py::RegistryTests \
 tests/test_planner_input_parity.py::PlannerInputParityTests
```

첫 실행은 **53 passed, 1 failed (0.50s)**였다. 실패는 `test_pause_counter_quit_and_graceful_stop_protocol`의 publish=false `_exchange`가 무조건 `import mujoco`를 수행하는데 기존 review venv에 MuJoCo가 없기 때문이다. 구현 결함/테스트 성공으로 숨기지 않았다. 해당 1개만 `sys.modules['mujoco'] = types.ModuleType('mujoco')`를 주입한 별도 실행에서 **1 passed (0.14s)**를 확인했다. 이 test 경로에서는 MuJoCo 속성이나 physics/viewer API를 사용하지 않으며 새 의존성을 설치하지 않았다. 실제 MuJoCo 환경에서 54개 전체가 통과했다고 주장하지 않는다.

## 6. 이번에 읽은 소스와 다음 범위

전체 읽기: `harness/{registry,catalog,can_skill_registry}.py`, `sim/bridge_client.py`, `scripts/{dispatch_native_process,dispatch_native_view,dispatch_replay,zone_replay,agent_sim_slots,agent_lock,sim_dispatch}.py`, `harness/cli.py`, 대응 native/replay/slot/lock/parity/primitive test 파일. `harness/zone_e2e_manifest.py`는 구조·re-derivation/blocked 상태를 확인했으나 실제 draft 생성은 과거 evidence 파일을 열 수 있어 실행하지 않았다.

caller/validation 중심 부분 읽기: `harness/loop.py`의 queue-call 구성/fused gate/dispatch, `scripts/robot_actions.py`의 public schema/run_program/run/main, `scripts/sim_actions.py`의 schema/validator/run/result projection, `scripts/red_block/primitive.py` 검증/드라이버, `scripts/run_dispatch_skills.py` observer setup/close/finalization, `run_final_pair_{fast,loaded}.py` lock admission. 대형 loop/runner의 전줄을 읽었다고 세지 않는다.

추가 탐색이 필요하면 현재 실행 path에 걸리는 contract migration을 먼저 선택해야 한다. `zone_e2e_manifest`가 명시적으로 DRAFT/runnable=false이고 전체 proposal을 다시 계산한다는 이유만으로 최신 runtime 인수를 대체하지 않는다. 이번 legacy schema drift를 고치는 일보다 runtime_round7의 현재 pair contract 결과가 우선이다. observer와 slot은 이번 확인 범위의 한정 통과로 남긴다.
