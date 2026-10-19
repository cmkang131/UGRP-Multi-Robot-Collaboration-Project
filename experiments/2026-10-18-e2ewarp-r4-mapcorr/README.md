# e2ewarp map correction + loaded FK 어댑터 — 기본 off, 2026-10-18

Lead 지시("e2ewarp GPU E2E의 map correction/loaded FK 부품 담당, 사용자 정정: 모두
GPU/MJWarp, R4 self-map 키프레임 48 성공 뒤 남은 차단 부품")에 따른 설계·구현·Mac
비물리 테스트. **GPU/physics 실행 없음**(Lead가 gcp6에서 조율). R4 원본(source
`718777118…`)은 변경하지 않았고, R4 self-map 48키프레임 수치도 승계하지 않는다.
새 worktree `/Users/changmin/projects/ugrp-wt/egonav-e2ewarp`,
브랜치 `claude/egonav-e2ewarp-mapcorr`.

## 1. 계약 (코드에서 확인)

- `harness/e2e_warp_components.REQUIRED = (navigation, loaded_camera_fk,
  static_map_registration, selfmap_map_correction, release_relocalization)`.
  `selfmap_map_correction`은 `mode='on'`, `own_and_static_map=true`,
  `spawn_anchor_used=false`를 요구한다.
- `harness/e2e_warp_mission.IntegratedController`는 navigation ABI
  `observe(OwnFrame) / task_candidates(completed) / start(instruction, phase) /
  command(sim_s) / confirm_act(frame, skill) / on_messages(rows) /
  accept_release_fix(report)`를 요구하고, 매 observe 보고에
  `map_correction_active=true`가 아니면 `HOST_ERROR`로 멈춘다. 이 값은
  "자기/정적 지도 보정이 켜져 있다"는 뜻이며 매 프레임 수용을 뜻하지 않는다.
- factory 호출: `factory(components['navigation_factory'])(robot_id=..., static=...)`.

## 2. 구현

### 2.1 owner 모듈 byte-pin (수정 없음)

mapbuild 소유 모듈을 `origin/codex/mapbuild1` tip
`95769da0e12326e41b71d29843c4da75c5b10a00` 바이트 그대로 가져왔다(파일별 sha256:
`owner-assets.json`). 기존 브랜치에 없던 `selfmap_map_correction.py`·
`mapbuild_static_registration.py`·`mapbuild_camera.py`·`mapbuild_command_prior.py`는
추가, `servo_camera_fk.py`(carry `CARRY_OPTION` 추가)·`self_map_csm.py`(prior_window
선택 인자)·`mapbuild_rbpf.py`(moving-camera 인자)는 owner 최신 바이트로 교체했다.
모두 하위 호환 변경이며 기존 테스트 83개가 통과한다. owner 결과 수치(mapbuild11/12)는
승계하지 않는다.

### 2.2 신규 `harness/e2ewarp_mapcorr.py`

기본 off 토글 3개(+선택 1개):

| 토글 | 기본 | 내용 |
|---|---|---|
| `e2e_warp_navigation_v1` | off | navigation_factory 조합 어댑터 활성화 |
| `loaded_camera_fk_v1` | off | 운반 자세(grip PWM<=1600) 카메라 FK 허용 |
| `selfmap_map_correction_v1` | off | 자기 지도·정적 지도 보정 |
| `own_rgb_zone_visdet_v1` | off | (선택) 구역/도착 자체 RGB 근거 |

- **`LoadedCameraFK`** — 자기 발행 servo PWM만으로 카메라 FK를 구한다. off면
  기존 fail-closed(`loaded_or_unknown_load_not_qualified`), on이면 owner의
  `servo_fk_carry_v1`을 명시적으로 쓴다. 이 모델은 **명령 기반 kinematic**이며
  하중/처짐/정착을 측정하지 않는다(`command_only=true`, `load_measured=false`).
  gripper slider가 카메라 ancestry에 없으므로 grip PWM은 가림(occlusion)만 바꾼다.
- **`OwnStaticMapCorrection`** — 자기 발행 명령으로 이동량 prior(owner
  `UncertainCommandOdometry`)를 만들고, 자기 RGB ground-pair VO + 벽 스캔
  (owner `ground_pair`/`virtual_scan`)을 측정으로 써서 owner `SelfMapCorrection`
  (CSM scan-to-submap + `StaticRegistration`)을 ±1 prior-sigma 창 안에서 돌린다.
  - **odometry-only 금지:** `perception_available=false` 프레임은 pose를 갱신하지
    않고 `own_rgb_perception_unavailable`로 거부한다. `map_correction_active`도
    false가 되어 mission이 HOST_ERROR로 막는다.
  - **GT/spawn 금지:** 입력 API에 GT/spawn/앵커가 없고, 원장에
    `truth_inputs=0`, `spawn_anchor_used=false`, `odometry_only=false`를 남긴다.
  - 정적 지도 등록은 계산 상한(시도 3회·최소 8 세그먼트)만 새로 두고, 수용
    점수·창·공분산은 owner 상수를 그대로 쓴다. ±1σ prior 창은 사용자 요청
    진단 후보 창(owner docstring)이며 새 신뢰도 보장이 아니다.
  - 거부 원장은 항상 `category/reason/blocked_object/minimum_gap_m/gap_status`
    (+`static_map_sha256`)를 남긴다.
- **`E2EWarpNavigation`** — navigation ABI 조합. `observe`는 매 프레임 위 두 부품의
  증거와 자기 RGB 구역 근거를 보고한다. **경로/주행은 소유자 navigation 부품이
  아직 없으므로 기본은 wheel 0 hold**이며, `owner_navigation=` 주입 시에만 위임한다
  (release 어댑터와 같은 owner-injection 패턴). `confirm_act`는 자기 RGB 근거만
  쓰고(grasp/regrasp는 holding 측정이 없어 False), `accept_release_fix`는
  (a) 보정 on·정적 지도 등록됨 (b) release 보고의 relocalized/static_map_registered
  true (c) truth/held_world_reads 0을 모두 요구한다.

## 3. 입력 경계 감사

|대상|확인|판정|
|---|---|---|
|어댑터 입력|자기 JPEG(`OwnFrame.jpeg`), 자기 발행 명령(`OwnFrame.issued`), authored static map/orders(`static`), 자기 servo PWM 기반 owner FK/색상 상수|허용 경계|
|금지 입력|world/model/data, evaluator/GT/접촉/성공, top camera, 측정 관절, spawn 앵커, odometry-only, cross-robot frame, 비인과 frame|차단|
|import 검사|`sim.*`·`mujoco`·`warp`·`torch`·`scripts.e2e_warp_physics` 없음(테스트 AST 검사)|통과|
|상태 보고|매 observe `map_correction_active`, `static_map_registered`, `truth_inputs=0`, `spawn_anchor_used=false`, `odometry_only=false`, `input_audit`|통과|
|owner 증거 검증|보정 수용은 자기 RGB 측정이 있는 프레임에서만, 정적 지도 sha256 고정, release fix는 보고 4조건 확인|fail-closed|

## 4. 테스트

```
python -m pytest tests/test_e2ewarp_mapcorr.py -q      # Mac, 24 passed
```

주요 범위: 기본 off fail-closed, loaded FK carry/unloaded, 보정 odometry-only 차단,
원장 필수 필드, 비인과/교차 로봇 프레임 거부, ABI 보고 키, `confirm_act` 자기 RGB
한정, `accept_release_fix` 조건, 채널 메시지 한정, owner 주입 위임 및
`map_correction_active` 강제, hash-bound manifest entry 일치.

## 5. Hash-bound 부품 manifest 형식 (`manifest-entry.json`)

- `adapter`: `navigation_factory` / `loaded_camera_fk` / `selfmap_map_correction`
  각각 `entry`(`harness.e2ewarp_mapcorr:<name>`)·`sha256`(모듈 파일)·`options`·`default=off`.
- `component_records`: e2ewarp components manifest에 넣을 레코드 원형.
  - `selfmap_map_correction`: `mode="on"`, `own_and_static_map=true`,
    `spawn_anchor_used=false`, **ready=false**(새 물리 관문 전까지).
  - `loaded_camera_fk`: `command_only=true`, `load_measured=false`, **ready=false**.
- `boundary_audit`, `tests`(sha256·24 cases·Mac only), `owner_assets`,
  `integration`(R4 run result sha `c61ecce4…`, source `718777118…`), `pending`,
  `no_pooling=true`, `no_prior_result_inheritance`.
- e2ewarp 쪽 병합: `components.pending.json`의 해당 키에 entry를 넣고
  `navigation_factory` entry를 추가하되, 위 ready는 **gcp6 새 물리 관문 전까지
  false 유지**한다.

## 6. 산출물 SHA (이 커밋 기준)

- `harness/e2ewarp_mapcorr.py` sha256: `76960c6de1ef…` (전체 값은 manifest-entry.json)
- `tests/test_e2ewarp_mapcorr.py` sha256: manifest-entry.json의 `tests.sha256`
- owner 자산 7개: `owner-assets.json`의 파일별 sha256, origin `95769da0e123…`
- R4 원본: run result sha `c61ecce4cc9ae68cc5c859d4a2d6c6f16b7fe51306bd80b527250af26fddbad0`,
  source `718777118be41991156b047faff78621969101bb` (변경 없음)

## 7. 남은 것

1. 소유자 navigation(경로·주행 명령) 부품 — 현재 어댑터는 wheel hold만 하고,
   `owner_navigation` 주입 시 위임한다. 경로 성공 주장은 새 물리 관문 뒤에만.
2. gcp6 새 물리 관문: `selfmap_map_correction=on` + `loaded_camera_fk_v1=on`으로
   보정 수용/오차/재획득 원장 확인. 기존 R4 30 SIM smoke(보정 off, motion 0)와
   합산하지 않는다.
3. ACT artifact·release 어댑터 readiness와 함께 components manifest에 연결.
4. 실제 실행에서 정적 지도 등록 수용/거부 원장(모호·관측부족 상태 포함) 기록.

## 8. Contract v1 self-centric binding (gate 2, default off)

`memory_registered_v1` 토글을 추가했다(기본 off, `selfmap_map_correction_v1`과 상호배타).
이 모드에서 `navigation_factory`는 `static_map`을 요구하지 않고 order-sheet 메타데이터만
받으며, `OwnStaticMapCorrection`은 생성하지 않는다. 등록·pose 추정은 주입된
`harness.e2ewarp_selfnav` navigator의 `memory_registration`
(`ugrp.e2ewarp.selfnav.v1`, owner `selfnav_memory_v1`, robot (0,0) 상대 landmark,
`memory_sha256`+`evidence_revision`)에서만 온다. selfnav가 없거나 `ready`가 아니면
`memory_registered=false`/`map_correction_active=false`로 닫히고 command는 hold다.
`accept_release_fix`는 memory 증거(owner/hash/revision/destination landmark)만 수용하며
`static_map_registered=true`는 혼합 증거로 거부한다. 새 단위 테스트 15개는
`tests/test_e2ewarp_selfcentric.py`(비물리, mujoco 미사용)에 있고 manifest
`tests.selfcentric`에 sha256이 고정되어 있다. 물리 관문은 아직 실행하지 않았다.
