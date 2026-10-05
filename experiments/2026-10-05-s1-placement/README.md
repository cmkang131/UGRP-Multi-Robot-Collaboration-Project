# S1 혼합 배치와 v4 지도 연결 (2026-10-05)

시작 소스는 main `9b571d5d054d8d084a2053928a2c0fbd67387bff`(PR #390).
작업 브랜치는 `codex/s1-placement`다. 구현 소스는 이 기록을 포함한 PR head로
식별한다. **오프라인만 확인했다. MuJoCo import·모델 생성·렌더·SIM·LLM 호출 0회.**
정지 30 SIM초, 낙하·관통, 실제 운반, S1 물리 졸업 판정은 코디네이터에게 남긴다.
단위 시험은 학습/평가 결과가 아니므로 TensorBoard snapshot을 만들지 않았다.

## 구현과 경계

- `harness.zone_final_env.FINAL_MAPS`에 최종 로봇 v3 지도 3개를 등록했다.
  기존 v1 catalog와 v2/v3 시나리오·지도·장면 구현은 그대로다.
  v3 지도 정의는 기존 부모 지도 + version 5 + robot_model + parent hash로 재현한다.
- `harness.zone_environment_registry.load_scenario()`는 명시적인 `_v2/_v3/_v4`
  suffix를 해당 디렉터리로 연결한다. 기본 legacy 시나리오 목록은 바꾸지 않는다.
  두 문·복도 v3 조회는 기존 v84의 지도/부모/보정 계약 해시를 검증한다.
  기존 door v3 factory를 유지하고 새 지도에 v2 provider를 허용하지 않는다.
- `sim.zone_environment_scene_provider.scenario_scene(scenario_or_id, seed)`와
  `sim.zone_scenario_scene.ScenarioFinalV3Scene`을 추가했다.
  표준 `sim.session_scenes.Scene`/`FinalV3Scene`의 벽·로봇 v3·reset·접촉 경로를
  재사용한다. 부모의 pair-only placeholder 제거 후 명시적인 색 상자 inventory를
  복원하며, catalogue 화물과 같은 장면에 둔다.
- 색 상자는 기존 production box의 형상·질량·마찰을 그대로 복제하고
  `cargo_<item_id>`/`cargo_<item_id>_free` 이름을 쓴다. cyan/red/green/yellow 모두
  지원한다. 높이는 기존 `BOX_HALF[2]`; 정확한 x/y는 config의 `eval.setup.placements`다.
  빔·can·tile·crate·frame은 기존 catalogue 좌표와 yaw를 그대로 쓴다.
- 맵/해시·주문 수·slot·벽/화물 여유를 기존 검증기로 먼저 검사한다.
  명시적인 초기화에만 private 좌표를 쓰며 공개 지도/주문에는 전달하지 않는다.
  숨은 사건을 작동시키거나 로봇 역할을 배정하는 기능은 추가하지 않았다.
  색 상자의 nonzero yaw와 `arena_default` 외의 시작 배치는 명시적으로 거절한다.
  전체 v4 8종의 현재 설정은 이 제약을 충족한다.
- 새 host는 `scene.config['setup_only']['objects']`와 `scene.spec['team_cargo']`를
  기존 `placements_match`에 전달하면 된다. 기존 검사 함수를 수정하지 않아도
  선언 좌표와 일치한다. S3의 다중 주문 호스트 연결은 별도다.

## dev_s1lite

`configs/zone_study_dev/dev_s1lite.json`: 같은 문 지도, 3대, cyan 1→A,
동서 빔 1→B, 사건 없음. 고정 역할 r1/r2 빔·r3 cyan은 향후 DEV 호스트의 정책이며
이 loader 자체는 배정하지 않는다.

기존 짝 스택의 `TASK_POSE=[1.0,0.05,0]`는 빔 전체가 P2 slot 경계 안에 들지 않아
기존 검증기에 거절된다. **x만 1.275로 옮겼다**(y=0.05, yaw=0 유지, P2-3).
cyan은 s1의 `[-0.2,-2.45,0]`다. 바뀐 시작 좌표에 과거 완주 성공을 승계하지 않는다.
s1 전체는 v4의 화물 7개·남북 빔 자세를 변경 없이 배치한다.

## 검증

| 실행 | 결과 | 범위 |
|---|---|---|
| `.venv-dev/bin/python -m pytest ...` | pytest 미설치로 시작 못 함 | 환경 실패, 시험 실행 0개 |
| `.venv-sim-worker-mac/bin/python -m pytest -q tests/test_zone_final_env.py tests/test_zone_environment_registry.py tests/test_zone_scenario_scene.py` | 191 passed | 지도 정의·frozen catalog·v4 조회·좌표·slot/겹침·해시·공개 입력·기존 장면 동작 |
| 같은 Python으로 `-m pytest -q tests/test_zone_scenario_scene.py` | 32 passed | 위 파일 28개 + 추가 XML 시험 4개 |

추가 XML 시험은 상위 로봇/dispatch template만 가짜로 넣고 실제 색 replica,
catalogue XML, 접촉 profile·finger pair 변환을 검사했다. MuJoCo model compile이나
실제 production 로봇 XML의 물리 검증은 아니다. `git diff --check`도 통과했다.

## S2 작업과 연결

[PR #391](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/391)의
`harness/zone_solo_cyan*_v106.py`, `sim/solo_cyan_v106.py`,
`scripts/run_solo_cyan.py`와 그 시험·설정을 수정하지 않았다.
S2의 위치 추정·cyan 제어 성공은 이 작업의 증거가 아니다.
S3에서 S2 제어기를 이 mixed scene의 `cyan_1`에 연결한다.
공통 `scripts/run_ci_tests.py`에는 각 PR의 추가 시험 행을 함께 유지하면 된다.
새 실행 번들 ID·workflow 버전은 사용하지 않았다. 기존 번들의 manifest를 재봉인하지 않았다.

## 코디네이터 명령

이 worktree에서 오프라인 초기화를 확인한다:

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -c 'from sim.zone_environment_scene_provider import scenario_scene; s=scenario_scene("dev_s1lite",911); print(s.record())'
```

다음은 **코디네이터가 sandbox 밖에서만** 수행할 유한 30 SIM초 정지·렌더 확인이다.
시뮬레이션 순서를 조정하고 공용 물리 잠금을 잡은 뒤 실행한다. 기본 체크아웃의
`outputs/`에 새 폴더를 만들며 덮어쓰지 않는다. controller/LLM은 없다.
다른 지도 확인은 `UGRP_SCENARIO`를 `s1_normal_mixed_v4`,
`s5_moved_dropped_item_v4`, `s2_unmapped_blockage_v4`,
`s4_narrow_door_standoff_v4`로 바꿔 **한 번에 하나씩** 한다.
새 물리 결과의 기록·TensorBoard 전환은 수행한 코디네이터의 후속 작업이다.

```sh
UGRP_SCENARIO=dev_s1lite PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python - <<'PY'
import hashlib, json, os, subprocess
from datetime import datetime
from pathlib import Path
from sim.zone_environment_scene_provider import scenario_scene
from sim.zone_final_v3_scene import build_world

assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip(), 'commit/freeze first'
name = os.environ['UGRP_SCENARIO']
out = Path('/Users/changmin/projects/ugrp/outputs/s1-placement') / (name + '-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
out.mkdir(parents=True, exist_ok=False)
scene = scenario_scene(name, 911)
world = build_world(scene, 'cargo_noslip_v1', seed=911, width=640, height=480,
                    render=True, warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None)
try:
    scene.setup(world)
    (out / 'scene.xml').write_text(world.scene_xml)
    (out / 'setup-private.json').write_text(json.dumps(scene.record(), indent=2))
    def capture(label):
        (out / (label + '.jpg')).write_bytes(world.render_team_jpeg(camera='cctv_warehouse'))
        poses = {item: world.data.body('cargo_' + item).xpos.tolist() for item in scene.inventory}
        (out / (label + '-eval-only.json')).write_text(json.dumps(poses, indent=2))
    capture('initial')
    start = float(world.data.time)
    world._final_environment_deadline = start + 30.
    dt = float(world.model.opt.timestep)
    while float(world.data.time) < start + 30. - dt / 2:
        world._physics_step_for(world.controllers['r1'])
    capture('after-30s')
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    receipt = {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'scenario': name, 'seed': 911, 'sim_s': float(world.data.time) - start,
               'loadavg': list(os.getloadavg()), 'files_sha256': files,
               'qualification': 'DEV setup check; no controller or delivery result'}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    print(out)
finally:
    world.close()
PY
```

## 참고 자료

- [구축 계획](../2026-10-05-scenario-e2e-gap/README.md) 3.1·6.1·S1·7절,
  [v4 생성 기록](../2026-10-05-scenarios-v4/README.md), PR #390.
- 기존 `sim/session_scenes.py`, `sim/zone_scene.py`, `sim/zone_cargo_scene.py`,
  `sim/zone_final_v3_scene.py`: 표준 reset와 box prototype/contact pair 재사용.
- [MuJoCo 3.2.6 XML reference, joint/freejoint](https://mujoco.readthedocs.io/en/3.2.6/XMLreference.html#body-joint):
  본문 확인. freejoint는 전역 위치와 quaternion을 초기화한다. 위치 설정과
  런타임 관측을 구분하는 기존 방식에 따른다.
- [robosuite PickPlace 공개 소스](https://github.com/ARISE-Initiative/robosuite/blob/master/robosuite/environments/manipulation/pick_place.py):
  `_reset_internal` 본문 확인(2026-10-05). initializer에서 얻은 개별 object pose를
  reset 때 joint qpos에 적용한다. 여기서는 난수 sampler를 추가하지 않고
  고정 scenario 좌표를 기존 reset에 공급한다. 관측용 object pose sensor는 가져오지 않는다.
  정적 초기화 구현이므로 별도 논문 방법·제어기 변경은 사용하지 않았다.
