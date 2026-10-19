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
- 신규 `tests/test_e2e_warp_release.py` — Mac 비물리 11개 테스트(모두 통과):
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

## 3. 입력 경계 감사 (요청 2)

|대상|확인|판정|
|---|---|---|
|본 어댑터 입력|자기 JPEG/자기 발행 명령(OwnFrame), authored static map, (채널 메시지는 조합 계층만 받고 어댑터는 안 받음)|허용 경계|
|`harness/e2e_warp_components.require_components`|factory entry 파일 SHA 검증 경로 확인 — 본 entry가 그 형식(`module:attr`+sha256)|연결 가능|
|`scripts/e2ewarp_vendor/release_reloc_selfmap.py` (R4 tip 내 유일한 release vendor 관측 모듈)|입력은 own RGB/servo/static calibration, `truth_inputs=0`/`held_world_reads=0` 행 기록, `decision()`은 항상 `accepted=False, reason=owner_static_map_acquisition_api_pending`|경계 위반 없음(단 ABI가 달라 그대로 wiring 불가; 어댑터의 owner 주입 대상으로만 사용)|
|기존 release 후보(rel21/release18/warp8f) 물리 관문|R4 tip 트리에 해당 후보 코드·artifact 없음. design.md 기록: warp8f는 관측 byte vendor만, 오프라인 14세계 418뷰 global CSM **채택 0/28**(모호 17·관측부족 11), 물리 A40/B40 보류. 구 Hough 바닥선 localizer는 **승계 금지**|**승계 안 함** — 본 어댑터는 그 성공 수치를 이월하지 않고, 새 물리 관문 전에는 `ready=false` 유지|

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

- `harness/e2e_warp_release.py` sha256: `43f35ba22083…` (전체 값은 manifest-entry.json)
- `harness/warp8f_memory.py` sha256: `00e507bebff9…` (owner-side memory evidence)
- `tests/test_e2e_warp_release.py` sha256: `b7a5355a443e…`
- `tests/test_e2ewarp_warp8f_memory.py` sha256: `08a4fb5be93e…`
- R4 원본: source `718777118be41991156b047faff78621969101bb`, run result sha `c61ecce4cc9ae68cc5c859d4a2d6c6f16b7fe51306bd80b527250af26fddbad0` (변경 없음)

## 7. 남은 것

warp8f 관측 바이트(전역 CSM) + mapbuild8 정적지도 보정 API가 준비되어 어댑터에 주입되고, **새 물리 release 관문**을 gcp6에서 다시 잰 뒤에만 `release_relocalization.ready=true`를 주장할 수 있다. 본 단계는 Mac 단위 테스트·경계 감사·manifest 연결 형식까지다.

## 8. Contract v1 memory_registered mode (gate 2, default off)

`release_relocalization_memory_v1` 옵션을 추가했다(기본 off). `static`은 사용하지 않고,
`start(instruction, own_report)`에서 navigator 보고의 `memory_registration`을 검증해
`navigator_owner=selfnav_memory_v1`·`memory_sha256`·`evidence_revision`·destination kind를
바인딩한다. owner(`warp8f`)는 그 hash/revision을 그대로 echo하고 `memory_registered=true`와
같은 kind의 memory landmark를 내야 한다. `static_map_registered`/`static_map_sha256` 필드는
값이 false/null이어도 memory 모드에서는 혼합 증거로 거부한다(`map_pose`는 non-null이면 거부).
selfnav가 없거나 `ready`/`destination_registered`가 아니면 바인딩 자체를 만들지 않고
pan·view 수집·주장 없이 `relocalized=false`로 닫힌다.
이 모드의 `pose_estimate`는 항상 self-centric (0,0)이며 `map_pose`는 null이다.

## 9. warp8f owner-side memory evidence (`harness/warp8f_memory.py`)

기존 owner 후보는 정적지도 CSM만 구현하고 memory 증거는 테스트 callable stub이었다.
`Warp8fMemoryOwner`는 navigator의 live `memory_registration`(`memory_source`)을 읽어:

- bound `memory_sha256`/`evidence_revision`을 그대로 echo하고 `memory_registered=true`를 낸다.
- 같은 kind의 **live** destination landmark를 `memory_landmark`로 낸다(정적지도/GT/전역 pose 없음).
- lookaround 중 navigator revision이 전진하는 것은 정상이므로 bound echo와 현재
  `navigator_current_revision`/`navigator_current_memory_sha256`를 분리해 기록한다.
  현재 hash를 강제하면 memory 경로가 영구 fail-closed가 된다.
- snapshot 없음/뒤처짐/같은 revision의 hash 불일치/landmark kind 불일치/미래 landmark는
  `owner_navigator_*` 코드로 닫히고 release 어댑터가 그 코드를 그대로 보고한다.

runner 연결은 아직 없다. gate 2 runner에서 release factory에
`memory_source=navigator.memory_registration`(또는
`owner=warp8f_memory.owner_factory(navigator)`)을 주입해야 실제 release가 이 owner를 쓴다.
단위 테스트는 `tests/test_e2ewarp_warp8f_memory.py`(fake navigator snapshot 11건 + 실제
selfnav revision 전진 통합 1건 = 12건)이며,
물리 release 관문은 아직 실행하지 않았다.
