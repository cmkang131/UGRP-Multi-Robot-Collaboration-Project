# S1 혼합 배치와 v4 지도 연결 (2026-10-05)

시작 소스는 main `9b571d5d054d8d084a2053928a2c0fbd67387bff`(PR #390).
작업 브랜치는 `codex/s1-placement`다. 구현 소스는 이 기록을 포함한 PR head로
식별한다. 아래 범위는 초기 구현 당시 기록이며, **2026-10-06 후속 물리 검증은 마지막 절**에 있다. **오프라인만 확인했다. MuJoCo import·모델 생성·렌더·SIM·LLM 호출 0회.**
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

## 2026-10-06 유한 정지·렌더 결과 (후속)

- 실행 소스: `35034c5bb13cc189d70d39c599de3c14c3eea03e` (`codex/s1-placement`, PR #392). 실행 전/후 clean HEAD와 원격 SHA를 확인했다. 두 장면을 직렬로 각 1회 실행했으며 재실행·소스 수정은 없다.
- 환경: 지정된 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`, Python 3.12.13, MuJoCo 3.12.0, macOS, seed 911, `cargo_noslip_v1`, `noslip_iterations=10`, timestep 0.00025 s. DEV 배치 진단이며 시나리오의 연구 seed 601–603 결과가 아니다.
- README의 `scenario_scene → build_world → scene.setup → 30 s while/_physics_step_for → capture → close`를 그대로 실행했다. 사용자 지정 출력 경로로 `out`만 바꾸고, 평가 전용 qpos/quaternion/qvel/접촉 판독·추가 카메라 저장을 붙였다. 읽은 정답은 제어·명령·단계 전환에 전달하지 않았다. 원문/실제 실행 본문/평가 드라이버를 raw에 각각 보존했다.
- 초기란 표준 `Scene.setup` 직후(time=1.3 s)다. setup에는 기존 reset 팔 접기 동작이 포함된다. 이후 30 SIM초(120,000 step, 종료 time=31.3 s)에 새 이동/팔 명령·controller·LLM 호출은 0회다. reset 동작까지 무명령이라고 해석하지 않는다.
- 각 실행 직전 잠금 `status=null`을 확인했고 acquire의 purpose는 `S1 placement settle/render`였다. driver PID dev=97572, s1=97724, expected-minutes=5. `setopt NO_BG_NICE`, 실행 Python nice=0; `ugrp_session.py run s1-settle-35034c5b-dev/s1`이 자식을 관리했다. 둘 다 exit 0, 세션 종료·release 후 `status=null`을 확인했다. 다른 작업의 프로세스·worktree는 수정/종료하지 않았다.
- 여유 공간은 실행 전 약 41.7 GiB였다. raw/영상 삭제·Google Drive 작업·모델 호출은 없다. 물리 실행은 MuJoCo SIM이며 실물 로봇 검증이 아니다.

| 장면 | compile / 정지 / 렌더 | 실제 무명령 SIM초 | 평가 wall초 | inventory | 배치 검사 |
|---|---|---:|---:|---|---|
| `dev_s1lite` | 각 1회 완료; 초기/최종 JPEG 각 8장 | 30.000000000 | 24.867 | 2개 | `placements_match=true` |
| `전체 s1` | 각 1회 완료; 초기/최종 JPEG 각 8장 | 30.000000000 | 34.259 | 7개 | `placements_match=true` |

wall은 평가 판독과 렌더 오버헤드를 포함하므로 속도 비교 근거로 사용하지 않는다.

### 화물별 평가 전용 결과

단위: 위치는 m, Δz와 접촉 침투는 mm, 기울기는 deg. 모든 화물의 XY 변화는 <0.000001 mm, 자세 회전 변화는 기록 정밀도에서 0 deg다. quat 원문·초기/최종 yaw·속도·최저 z·매 step extrema·1 Hz trace는 raw JSON에 있다.

| 장면 / 화물 | 초기 xyz | 30 s 뒤 xyz | Δz | 최대 / 최종 침투 | 최대 기울기 |
|---|---|---|---:|---:|---:|
| dev_s1lite / `cyan_1` (cyan) | [-0.200000000, -2.450000000, 0.015892245] | [-0.200000000, -2.450000000, 0.015892245] | 0.000000 | 0.107755 / 0.107755 | 0.000000 |
| dev_s1lite / `beam_1` (long_beam) | [1.275000000, 0.050000000, 0.000500000] | [1.275000000, 0.050000000, -0.000107755] | -0.607755 | 0.713714 / 0.107755 | 0.000000 |
| 전체 s1 / `cyan_1` (cyan) | [-0.200000000, -2.450000000, 0.015892245] | [-0.200000000, -2.450000000, 0.015892245] | 0.000000 | 0.107755 / 0.107755 | 0.000000 |
| 전체 s1 / `cyan_2` (cyan) | [0.400000000, -2.450000000, 0.015892245] | [0.400000000, -2.450000000, 0.015892245] | 0.000000 | 0.107755 / 0.107755 | 0.000000 |
| 전체 s1 / `red_1` (red) | [1.000000000, -2.450000000, 0.015892245] | [1.000000000, -2.450000000, 0.015892245] | 0.000000 | 0.107755 / 0.107755 | 0.000000 |
| 전체 s1 / `green_1` (green) | [-0.200000000, 0.750000000, 0.015892245] | [-0.200000000, 0.750000000, 0.015892245] | 0.000000 | 0.107755 / 0.107755 | 0.000000 |
| 전체 s1 / `can_1` (can) | [0.400000000, -0.850000000, 0.000500000] | [0.400000000, -0.850000000, -0.000142153] | -0.642153 | 0.725102 / 0.142153 | 0.000000 |
| 전체 s1 / `tile_1` (tile) | [1.000000000, -0.850000000, 0.000500000] | [1.000000000, -0.850000000, -0.000107755] | -0.607755 | 0.713714 / 0.107755 | 0.000000 |
| 전체 s1 / `beam_1` (long_beam) | [1.275000000, 0.450000000, 0.000500000] | [1.275000000, 0.450000000, -0.000107755] | -0.607755 | 0.713714 / 0.107755 | 0.000000 |

- 낙하/전도/지속 이동은 관찰되지 않았다. catalogue 원점의 초기 z=0.0005 m에서 바닥으로 정착하며 can은 0.642153 mm, tile/빔은 0.607755 mm 내려갔다. 색 상자는 setup 과정에서 이미 정착해 30 s 창의 Δz=0이다. catalogue z는 물체 중심 높이가 아니라 바닥 형상의 원점이다.
- **침투 0을 확인한 것은 아니다.** 모든 최심 접촉은 `floor`와 해당 화물 geom 사이였다. 최대 0.713714 mm(dev), 0.725102 mm(s1), 최종 can 0.142153 mm/나머지 0.107755 mm로 유한하게 정착했다. 바닥을 통과해 떨어지는 현상은 없었고, 저장한 1 Hz 접촉 trace와 매 step 최심 접촉에서는 화물-벽/화물-화물 관통이 보이지 않았다.
- 판정은 실행 전 평가 드라이버가 정한 DEV screen(수평 이동·선언 XY 오차 ≤1 mm, tilt ≤1 deg, penetration ≤1 mm, 선언 z 대비 하강 ≤5 mm, 최종 선속도 ≤0.1 mm/s)에서 두 장면 모두 PASS다. 정식 사전 등록이나 S1 졸업 기준을 새로 정의하지 않는다.
- `placements_match` 원함수는 config의 색 `objects`와 `spec.team_cargo`의 선언 XY만 비교한다. runtime 실측은 별도로 비교했으며 두 장면 전 화물의 선언 XY 오차 <0.000001 mm, yaw 오차 절댓값 <0.000001 deg다. dev 빔 yaw=0, 전체 s1 빔 yaw=1.5708 rad(남북)을 유지했다.
- `yellow`, `heavy_crate`, `tri_frame`은 이 두 config에 없다. 녹색 상자는 전체 s1에서만, can/tile은 전체 s1에서만 확인했다. 없는 화물의 검증으로 확대하지 않는다.

### 출력·렌더·해시

- dev_s1lite: `/Users/changmin/projects/ugrp/outputs/s1-placement-settle-35034c5b-dev_s1lite`
  - `summary-eval-only.json` SHA-256: `f144b7da34f608ace3cc6cb5b577a68076bd046e19c62713dc3ca11b98aab111`
  - `files-sha256.json` SHA-256: `985ab2db203d93c36c7324bfb9fac1a993187f6977f30aa62e704313eb0e83a1`; 등록 파일 29개 전체 재계산 일치.
  - `evaluation-driver.py` SHA-256: `a2f7d7cd0b4ed88035e457237674c02c9d23f0bb6f5132eeb1f63cd9c2ff4720`; 원문 `readme-command-original.py`, 실제 본문 `readme-command-applied.py`, `receipt.json`, `environment.json`, `scene.xml`, `setup-private.json` 보존.
- 전체 s1: `/Users/changmin/projects/ugrp/outputs/s1-placement-settle-35034c5b-s1_normal_mixed_v4`
  - `summary-eval-only.json` SHA-256: `3a8437d14e973b3785032e9368c3b4274d5a1c2c736cfb628c5e0c4e59fdecc8`
  - `files-sha256.json` SHA-256: `413801a04838c734e9e0ef2bd04fea7b3dd2dee4564031c040f4c9184e03c870`; 등록 파일 29개 전체 재계산 일치.
  - `evaluation-driver.py` SHA-256: `a2f7d7cd0b4ed88035e457237674c02c9d23f0bb6f5132eeb1f63cd9c2ff4720`; 원문 `readme-command-original.py`, 실제 본문 `readme-command-applied.py`, `receipt.json`, `environment.json`, `scene.xml`, `setup-private.json` 보존.

초기/최종의 기존 warehouse observer, 승인 TOP 4개, r1/r2/r3 자기 카메라를 저장했다. warehouse 전경 초기/최종, TOP, 자기 카메라 대표 이미지에서 배치·남북/동서 빔·렌더 생성 상태를 시각 확인했다. 카메라/FOV/외관/밝기는 바꾸지 않았다.

| 장면 | 대표 파일 | SHA-256 |
|---|---|---|
| dev_s1lite | `initial.jpg` | `16629b1455d62a1166c6e84db1ecd6f855dbf726ed3258e4a097f71e1cef5e58` |
| dev_s1lite | `after-30s.jpg` | `e296a5fe57c9232b21b080a79dc2d441bb2381e95ea0e3f3367d3b9e3317e825` |
| dev_s1lite | `after-30s-cctv_top.jpg` | `ecd4c37d0cb4ede47358db94971dca800dd23645af4e7c4ea5980cff08bb52dd` |
| dev_s1lite | `after-30s-r3-robot_cam.jpg` | `890c5e64f7a06719c02c4b866fc712bf480cc57ecd65b8e50afe089a0d816bda` |
| 전체 s1 | `initial.jpg` | `b51448bcd64dc668e8aeef7a01d0427e1a1650a8606a1ee447abd09c38b11b11` |
| 전체 s1 | `after-30s.jpg` | `e307d17944ca05cda2b8e09c291fcc375433ac53e4134af14816deea159dee96` |
| 전체 s1 | `after-30s-cctv_top.jpg` | `96b8de5d3c898572b2a4b1e4baf21de14de144cfb8e0d923137a53597287c06a` |
| 전체 s1 | `after-30s-r3-robot_cam.jpg` | `8d6140b97f277823faf107afff241087a50140845d48f926fb992d552bfd13e9` |

### 접촉 해석의 조사 근거

- [MuJoCo Computation: soft contact model](https://mujoco.readthedocs.io/en/stable/computation/index.html#soft-contact-model) 및 [Modeling: solver parameters](https://mujoco.readthedocs.io/en/stable/modeling.html#solver-parameters), 2026-10-06 본문 확인: soft constraint의 정지 접촉에는 유한 침투가 가능하며 solver reference/impedance가 영향을 준다. 이번 측정의 작고 유한한 floor 침투와 표준 접촉 설정에 비추어, S1 배치 버그로 판단하지 않았다. 문서만으로 우리 수치를 보증한 것은 아니다.
- 기존 `sim/session_scenes.py:198`의 reset/qpos·팔 접기, `sim/zone_cargo.py:446`의 catalogue z=0.0005 초기화, `sim/zone_cargo_contact.py`의 NoSlip은 마찰 후처리만 추가하고 normal softness를 유지하는 구조를 확인했다. 최소 수정이 필요한 실패가 발견되지 않아 코드/접촉 profile 변경·추가 pytest·재실행을 하지 않았다. 새로운 제어 알고리즘을 제안하거나 논문 성능으로 확대하지 않았다.

### TensorBoard와 남은 범위

- 새 snapshot: `/Users/changmin/projects/ugrp/outputs/tensorboard/1006-s1-placement-settle-35034c5b`, runs `dev-s911`, `s1-s911`; 기존 snapshot 원본 경로 중복 없음 확인 후 변환 2개/실패 0개.
- 파생 뷰: `/Users/changmin/projects/ugrp/outputs/s1-placement-settle-35034c5b-tbviews`. `scripts/export_offline_audit.py`로 gate/침투/기울기/이동과 기록된 SIM·wall·명령·호출만 옮겼다. `evaluation/reported_success=1`은 위 DEV settle screen이며 운반 성공이 아니다. 모델 응답시간은 미기록이라 태그를 만들지 않았다.
- EventAccumulator 재판독과 실제 서버 scalar API에서 2 run × 11개 = 22개 값이 원본/파생 선언과 일치했고 HParams 이벤트도 존재했다. 공유 viewing root `outputs/tensorboard`, 세션 `tensorboard-s1-settle-1006`을 사용했다. JPG 정지 이미지만 요청/저장했으므로 새 MP4 등록/재생은 해당 없음이다. UI 확인 상태는 아래 최종 확인에 별도로 남긴다.
- 이 기록은 raw의 원격 백업이 아니다. Git에는 이 요약·해시/경로를 보존하며 raw는 지정된 로컬 outputs에 유지한다. PR #392는 DRAFT 유지·병합하지 않는다. 실제 운반·접근/파지 도달성·S1 물리 졸업·S2 제어기 연결·본 연구 코호트는 미검증이다.

- 최종 화면 확인: Chrome `강`의 기존 TensorBoard 탭에서 두 run을 선택하고 Time Series의 DEV 판정=1, SIM초=30, 명령=0, 호출=0을 확인했다. pin 5개를 적용했으며 최대 침투 카드의 최종 시각 재판독은 미확인(이벤트/API 값 검증은 완료)이다. 공유-root HParams 화면에는 scenario·새 침투/기울기 열이 없어, 제공된 outcome/seed/source_sha/판정/SIM/명령/호출 열만 적용했다. 새 S1 HParams 행/전체 열 구성은 UI 미확인으로 남긴다. 새 exporter·뷰어 변경으로 확장하지 않았다.
- 저장된 [TensorBoard pin 링크](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation%2Freported_success%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fsim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fmax_penetration_mm%22%7D%5D&smoothing=0&runFilter=%5E1006-s1-placement-settle-35034c5b%2F#timeseries); 표시 설정은 기본 체크아웃 `outputs/tensorboard-view.json`의 `s1_placement_settle_20261006`에 자기 키만 추가했다. 검증 기록은 `/Users/changmin/projects/ugrp/outputs/s1-placement-settle-35034c5b-tb-verification.json`이다. viewer를 다시 열려면 이 worktree에서 `python3 scripts/ugrp_session.py run tensorboard-s1-settle-1006 -- /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python scripts/run_tensorboard.py --logdir /Users/changmin/projects/ugrp/outputs/tensorboard`를 사용한다. 작업 종료 때 이번 viewer 세션만 정리한다.
