# e2ewarp release API 어댑터 (release_factory ABI) — 기본 off, 2026-10-18

Lead 지시("e2ewarp `dependency_status`의 release API(warp8f 계열) 담당")에 따른 설계·구현·Mac 비물리 테스트. **GPU/physics 실행 없음**(Lead가 조율). R4 원본(source `718777118…`)은 변경하지 않았고, 새 파일 2개만 추가했다.

## 1. 계약 (코드에서 확인)

`harness/e2e_warp_mission.IntegratedController`가 요구하는 release ABI와 `harness/e2e_warp_components.MissionRobot`의 factory 호출 방식:

- factory: `factory(components['release_factory'])(robot_id=robot, static=static)` — manifest entry는 `module:attr`
- adapter 메서드: `start(instruction, own_report)` · `observe(OwnFrame)` → report · `command(sim_s)` → issued-command whitelist
- 보고 계약: `relocalized=true` **그리고** `static_map_registered=true` 여야 `navigation.accept_release_fix`가 다음 task를 허용. 어댑터가 이 값을 지어내면 안 됨.

## 2. 구현

- 신규 `harness/e2e_warp_release.py` — `release_factory(robot_id, static, *, option='off', owner=None)` 및 `ReleaseRelocalization`.
  - **기본 off**: `observe()`는 `relocalized=false, static_map_registered=false` + 명시 reason, `command()`는 wheel 0(정지) 유지.
  - **`release_relocalization_selfmap_v1`(실험 옵션, 기본 off)**: 고정 3-view 실제 자기 RGB 둘러보기. pan은 기존 `SEARCH` yaw ±500 PWM(`DiagnosticTask`와 같은 승인 범위), view dwell은 기존 `max(PARAMS['settle_s'])+0.1`, wheel 명령 없음. **settle된 view만** 수집(팬 명령만으로 재획득 세지 않음).
  - **owner 관측/보정 API는 주입식**: `owner(evidence)`가 warp8f 관측 바이트·mapbuild8 정적지도 보정 결과를 반환. evidence는 자기 입력만(`robot_id`, `static_sha256`, `instruction`, `views[{t, rgb_sha256, pwm}]`). 어댑터는 반환값을 검증: `owner=='warp8f'`, `relocalized is True`, `static_map_registered is True`, `static_map_sha256 == sha256(authored static)`, `truth_inputs==0`, `held_world_reads==0`, 유한 3축 pose — 하나라도 어긋나면 fail closed.
  - 새 상수 없음: pan span/dwell/view 수는 기존 SEARCH·PARAMS·3-view 스윕 재사용. float 비교 epsilon만 추가(주석 명시).
- 신규 `tests/test_e2e_warp_release.py` — Mac 비물리 **13개** 테스트(모두 통과):
  1. 기본 off fail-closed(정지·false)
  2. owner 미주입 시 pending
  3. owner 수용 시 true + evidence hash 일치
  4. owner가 금지 입력(`truth_inputs`) 보고 시 거부
  5. static map hash 불일치 거부
  6. owner 예외를 unknown으로 처리(claim 금지)
  7. 팬 명령만으로는 view 미집계(settle·pwm 일치 필요)
  8. cross-robot·비인과 frame 거부
  9. start 인자 검증
  10. 모듈 경계 스캔: 시뮬레이터/평가/GT/top/파일읽기 금지, 허용 import만
  11. hash-bound manifest entry가 `e2e_warp_components.factory`로 로드되고 파일 SHA와 일치
  12. **e2ewarp 미션 ABI 통합**: `IntegratedController(RELOCALIZE)`에 실제 어댑터를 꽂아 `release.start→observe→command` 경로로 owner 수용 시 `accept_release_fix` 통과·완료 기록
  13. 같은 ABI에서 기본 off 어댑터는 수용 없이 RELOCALIZE에 머묾(fail closed)

## 3. 입력 경계 감사 (요청 2)

|대상|확인|판정|
|---|---|---|
|본 어댑터 입력|자기 JPEG/자기 발행 명령(OwnFrame), authored static map, (채널 메시지는 조합 계층만 받고 어댑터는 안 받음)|허용 경계|
|`harness/e2e_warp_components.require_components`|factory entry 파일 SHA 검증 경로 확인 — 본 entry가 그 형식(`module:attr`+sha256)|연결 가능|
|`scripts/e2ewarp_vendor/release_reloc_selfmap.py` (R4 tip 내 유일한 release vendor 관측 모듈)|입력은 own RGB/servo/static calibration, `truth_inputs=0`/`held_world_reads=0` 행 기록, `decision()`은 항상 `accepted=False, reason=owner_static_map_acquisition_api_pending`|경계 위반 없음(단 ABI가 달라 그대로 wiring 불가; 어댑터의 owner 주입 대상으로만 사용)|
|**warp8f 관측/CSM r1** (31657fc91·d8c9ec262)|오프라인 selfmap CSM 큐·artifact-integrity. 관측 전용, `truth_inputs=0`/`held_world_reads=0`, global CSM **채택 0/28**(모호 17·관측부족 11)|경계 위반 없음 / **물리 관문 수치 미승계**(A40/B40 보류)|
|**warp8f opt-in static selfmap API** (a40eb3994, `scripts/release_reloc_static_selfmap.py:StaticReleaseSelfmap`)|own RGB·issued servo·command delta·settled·authored static map(`StaticRegistration`). own-map zero는 gauge(월드/spawn 아님), spawn/legacy 폴백 금지, truth_inputs=0|경계 위반 없음 / **R4 tip에 없음** → merge·재관문 전 `ready=false`. **owner 주입 대상**|
|**release21** (b75b130f2·508fa59af, `sim/release21.py`)|"no world state or measured joints enter"; own camera FK+release15 reprojection, FOV recovery|경계 위반 없음 / **CPU MuJoCo 경로** — e2ewarp ABI 아님이며 DEV6 결과 미승계|
|**release18** (1cb74c366, gate40 plan)|queue/plan만, R4 tip에 코드 없음|증거 없음(비활성 CPU gate40 계획) — 미승계|
|**e2ewarp vendor 관측 모듈** (`scripts/e2ewarp_vendor/release_reloc_selfmap.py`)|own RGB/servo/static calibration; decision은 항상 `accepted=False`(API 대기)|경계 위반 없음(관측 전용, ABI 다름)|

## 4. R4 원본/부품 manifest 연결 형식 (요청 3)

`manifest-entry.json`(이 디렉토리):

- `adapter`: `{"entry":"harness.e2e_warp_release:release_factory","sha256":"<file sha>","options":[...],"default":"off"}`
- `component`: `release_relocalization`, owner 표기(warp8f 관측 + 본 통합)
- `contract`: factory/start/observe/command + claim rule + default-off 동작
- `boundary_audit`: 허용/금지 입력, import scan, owner evidence 검증 항목
- `tests`: `{"path","sha256","cases":11,"result":"pass","scope":"Mac non-physical only"}`
- `integration`: R4 target run 경로·`result.json` sha(`c61ecce4…`)·source sha(`718777118…`), `component_manifest_key="release_factory"`, merge note
- `pending`: warp8f 관측 바이트/전역 CSM, mapbuild8 정적지도 API, 새 물리 release 관문
- `no_pooling: true`, `no_prior_result_inheritance`: rel21/release18/warp8f 기존 물리 관문 수치 미승계 명시

R4 components manifest에 병합할 때는 `components.pending.json`의 `release_factory` 항목에 adapter entry를 넣고, `release_relocalization.ready`는 **새 물리 관문 전까지 false 유지**한다.

## 5. 재현

```
python -m pytest tests/test_e2e_warp_release.py -q      # Mac, 11 passed
```

## 6. 산출물 SHA (이 커밋 기준)

- `harness/e2e_warp_release.py` sha256: `b81c89579eaf7666…` (전체 값은 manifest-entry.json)
- `tests/test_e2e_warp_release.py` sha256: manifest-entry.json의 `tests.sha256`(13 cases)
- R4 원본: source `718777118be41991156b047faff78621969101bb`, run result sha `c61ecce4cc9ae68cc5c859d4a2d6c6f16b7fe51306bd80b527250af26fddbad0` (변경 없음)

## 7. 다음 owner 통합 경로

- 향후 `owner=` 주입 대상: `scripts/release_reloc_static_selfmap.py:StaticReleaseSelfmap`(warp8f, a40eb3994, R4 tip에 미포함). 어댑터 evidence(`views[{t,rgb_sha256,pwm}]`)를 이 모듈의 `observe(now,rgb,servo,command_delta=...,settled=True)`/`register()`로 전달하는 얇은 shim이 필요하며, shim은 `{owner:"warp8f", relocalized, static_map_registered, static_map_sha256, map_pose, truth_inputs:0, held_world_reads:0}`만 반환한다.
- mapbuild8 정적지도 등록·보정 API가 merge·검증되기 전에는 owner조차 `accepted=False`이므로 어댑터는 자동으로 fail closed 상태를 유지한다.

## 8. 남은 것

warp8f 관측 바이트(전역 CSM) + mapbuild8 정적지도 보정 API가 준비되어 어댑터에 주입되고, **새 물리 release 관문**을 gcp6에서 다시 잰 뒤에만 `release_relocalization.ready=true`를 주장할 수 있다. 본 단계는 Mac 단위 테스트·경계 감사·manifest 연결 형식까지다.
