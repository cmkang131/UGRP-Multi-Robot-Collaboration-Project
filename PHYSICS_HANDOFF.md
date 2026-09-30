# 최종 환경 v87 물리 인계 — DRAFT, 미봉인

**밝은 렌더의 P01 3×30 SIM초 및 unloaded 수집 3×120 SIM초 경로를 등록했다. P03 연쇄는 아직 실행할 수 없다.**
P03 #312에 의존한다. v3 보정 실측과 v3 공동 운반 어댑터가 없으며, 기존
`OwnCamTeamHost`는 `v3 pair executor requires a separately migrated controller`로 거부한다.
이 제한을 우회하거나 기존 제어기를 v3로 표시하지 않았다. 이 문서의 등록/계획 확인은
실제 SIM, 위치 추정 정확도, 파지, 연쇄 완주 또는 사전 등록 봉인이 아니다.

## 고정한 조합

번들 `zone-final-environment-v87`, workflow `zone-final-environment-floor-light-check` 2.20.0.
2026-10-01 main + 열린 PR **16개 전체**를 조회했다. #339는 이미
`zone-target-v86` / `zone-target-checks` **2.19.0**을 사용하므로 다음 번호인
**v87 / 2.20.0**을 선택했다. 별도 M1 memory-v3 workflow의 3.0.0은 통합 2.x 계열이 아니다.
[조회 원본](experiments/2026-10-01-final-env-floor-light/reservation_scan.json)을 보존했다.

2026-09-29 사용자 결정에 따라 연구 코호트는 밝은 무그림자 `floor_light_v1`을 쓴다.
[P01 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)은
v84가 기본 렌더에 고정되어 어둡게 수집됐다고 기록했다. 이 결정은 이미 내려졌으며
이번에는 이를 새 버전으로 연결한다. **그림자가 있는 과거 결과와 합산하지 않는다.**
v84 등록 JSON·workflow·보정 계약·실행 소스 및 9개 생성 번들의 해시는 그대로 보존한다.
기존 `zone-final-environment-check` 2.17.0은 v84 재현용으로 남기며 새 명령은
별도 workflow ID를 명시한다. [기존 handoff 원문](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/5ba853ddc5b0e300e45f8361e98e7f9f16e08c18/PHYSICS_HANDOFF.md).


| P01 사례 | 지도 | 로봇 | 부모 |
|---|---|---|---|
| 문 1개 | `zone_wide_door_geometry_v3` | masterpi_v3 | 기존 geometry_v2, 기존 v3 파일 그대로 사용 |
| 문 2개 | `zone_wide_two_doors_final_v3` | masterpi_v3 | two_doors_final_v1 파일·정적 hash |
| 복도 | `zone_wide_corridor_final_v3` | masterpi_v3 | corridor_final_v1 파일·정적 hash |

기존 지도·catalog·v6e 등록·`configs/simulation_workflows.json`·과거 번들은 변경하지 않는다.
표준 관리자가 `configs/simulation_workflows.d/final_environment_v87.json`을 추가로 읽는다.
같은 ID 덮어쓰기는 거부하며 추가 catalog 파일도 관리 기록의 hash에 포함한다.
추가 장면은 표준 `CargoZoneScene`의 구성/초기화와 기존 v3 robot XML 변환을 재사용한다.
기존 v3 Scene allow-list를 넓히지 않는다.

공통 설정: `cargo_noslip_v1`, weld OFF, 초음파 OFF, `floor_light_v1` 렌더,
walls_v3 0.40 m, 자기 `robot_cam` RGB 640×480, 분할 480×360, seg-v2 해시
`348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9`.
기존 `sim.render_profile`의 밝은 바닥·무그림자 정의를 그대로 적용하고 실제 모델을 검사한다.
카메라/FOV·물체 외관·지도·접촉·명령 궤적·관찰 주기는 v84와 같다. C_mix_rgb는 채택하지 않는다.
P01은 기존 기본 색 상자 reset 구성이다. P02 혼합 주문·긴 빔 임무 배치를 검증하는 실행이 아니다.

## 실행 전 — 코디네이터의 자기 worktree에서

코드를 먼저 커밋하고 아래 SHA를 그 HEAD로 고정한다. 같은 코호트 중 소스를 바꾸지 않는다.
이 작업의 샌드박스에서는 SIM/렌더/학습/실제 추론을 한 번도 실행하지 않았다.

```bash
cd /Users/changmin/projects/ugrp-wt/integ-final-env-v86
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=$(git rev-parse HEAD)
FINAL_BRANCH=$(git branch --show-current)
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-env-v87-NEW-COHORT
git status --short --untracked-files=all
"$PY" scripts/disk_report.py
"$PY" scripts/agent_lock.py status

# 정적 확인만. renderer/worker/물리 시작 없음.
"$PY" -m scripts.run_final_environment_floor_light --check p01 \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p01"
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-check -- \
  --check p01 --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p01"
```

기본 체크아웃에서는 실행하지 않는다. 원격 P03가 갱신되면 먼저 fetch/merge하고
오프라인 검사 후 새 SHA로 고정한다. 아래 명령은 작업 worktree에서 실행하며,
경로명 끝의 v86은 폴더 이름일 뿐 실제 선택 번들은 v87이다. 다른 작업의 잠금은 해제하지 않는다.
디스크 10 GiB 미만은 시작하지 않으며 실행 중 ENOSPC는 `HOST_ERROR`다.

아래 잠금·세션 명령은 코디네이터가 실행한다. `--owner`는 실제 실행 주체로 바꾼다.
명령은 동기 SIM을 사용하고 시간 비교나 속도 결론을 내지 않는다.
각 블록은 잠금 획득 실패 시 즉시 멈추며, 획득한 뒤의 실패에도 자기 잠금을 해제한다.

```bash
(
set -euo pipefail
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v87 P01 reset 3x30 SIM s' --pid $$ --expected-minutes 30
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-env-v87-p01 -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-check -- \
  --check p01 --seed 911 --expected-source-sha "$FINAL_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p01"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
)
```

## P01: 3×30 SIM초, reset 별도 상한

실행기는 위 표 순서로 지도마다 표준 reset → 정지 30초를 수행한다.
학생/LLM/provider 추론/teacher 주행 명령은 0이다. reset은 사례당 **최대 5초**,
정지 관찰은 정확히 **30초**, 총 관찰 **90초**, reset 포함 총 **최대 105초**다.
5초는 측정치가 아니라 초과 시 중단하는 예산이다. 물리 timestep이 0.05초를
정확히 나누지 않으면 거부하며 다음 step이 상한을 넘기 전에 멈춘다.

검토할 파일과 판정:

- 각 사례의 `bundle.json`, `scene.xml`, `scene.json`, `eval_only/applied.json`:
  지도/부모/정적 hash, 실제 robot XML, v3 모델·wall 높이·표식 geom/texture 0,
  timestep·noslip·weld를 대조한다. `bundle.json`의 `render_profile_contract`와
  `scene.json`의 `render_profile`, `eval_only/applied.json`의 `render_profile`/`render_profile_applied`를
  대조한다. profile 이름·hash, 그림자 0, 반사 0, light cutoff 180, 밝은 ground texture 평균을
  검사하며 새 raw 자기 RGB를 눈으로 확인한다. 렌더 적용 검사가 실패하면 HOST_ERROR다.
  코드의 정적 hash는 실제 XML 확인을 대신하지 않는다.
- `eval_only/setup.json`, `eval_only/contacts.jsonl`: seeded 초기 배치,
  robot–wall/cargo/robot 초기 겹침·관통과 정지 drift. 접촉 trace는 0.05초 간격의
  표본이며 모든 내부 substep 접촉을 빠짐없이 기록했다는 근거가 아니다.
- `robots/r*/frames.jsonl`, `robots/r*/rgb/*.png`: t=reset 끝, 이후 5초 간격,
  끝 30초 포함 자기 영상. 실제 배치·FOV·좌우축·팔 가림과 크기/시각/hash를 확인한다.
  이 점검에서는 TOP를 학생에게 전달하지 않으며 추가 TOP 영상도 생성하지 않는다.
- `result.json`의 `COLLECTED_UNQUALIFIED`는 자료 수집 종료다. 환경 적합 PASS가 아니다.
  첫 HOST_ERROR 뒤 나머지는 `unattempted`로 남기고 분모 3을 유지한다.
  초기 관통/카메라 문제는 코디네이터가 실패로 기록하고 해당 조합의 학생 실행을 막는다.

## v3 보정 — 값을 만들지 말고 먼저 측정

`configs/calibration/zone_final_v3_floor_light_contract.json`은 정적 모델/지도/카메라 소스 계약이다.
camera sag/pan, unloaded/loaded/fine motion 및 measurement는 **null**이다.
v2 보정값 복사나 정지 화면의 GT 근처 PF 재시작으로 채우지 않는다.

아래는 코디네이터가 별도 실행하는 **unloaded 보정 수집** 명령이다.
P01 90초나 P03 360초에 합산해 숨기지 않는다. 3지도×120초=360초,
reset 각 5초 포함 최대 375초다. 순서/시각/명령은
`configs/final_environment_measurement_v1.json`에 고정했다.
검색/p20/빈 carry 팔 자세에서 각각 8pan×3초=72초,
전진·측면·회전의 양/음 0.03 명령 0.25초×4회와 정지 관찰,
나머지 시간 정지다. 실행 로봇은 r1, 나머지는 정지하고 3대 자기 영상을 저장한다.

```bash
(
set -euo pipefail
# 정적 확인: 3지도×120 SIM초, 아직 실행하지 않음.
"$PY" -m scripts.run_final_environment_floor_light --check calibration \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/calibration-unloaded"
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-check -- \
  --check calibration --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/calibration-unloaded"
"$PY" scripts/agent_lock.py acquire --owner codex --branch "$FINAL_BRANCH" \
  --purpose 'v87 unloaded calibration collection 3x120 SIM s' --pid $$ --expected-minutes 60
trap '"$PY" scripts/agent_lock.py release --owner codex' EXIT
"$PY" scripts/ugrp_session.py run final-env-v87-calibration -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-check -- \
  --check calibration --seed 911 --expected-source-sha "$FINAL_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/calibration-unloaded"
"$PY" scripts/agent_lock.py release --owner codex
trap - EXIT
)
```

이는 **unloaded 원시 수집만**이다. 제어기가 calibration을 사용하거나 fitting·성공 판정을 하지 않는다.
`eval_only/r*/camera_labels.jsonl`에 실제 base/camera 변환,
`robots/r*/commands.jsonl`과 자기 PNG에 발행 명령/관측을 보존한다.
교사/GT는 오프라인 보정 자료로만 읽는다. 원시 eval 파일은 학생 factory 인자로 넘기지 않는다.

이후 필요한 측정: 실제 v3 무보조 파지 하중에서 같은 팔/pan 목록,
unloaded/loaded/fine의 gain·lag·slip·정지 drift, 실제 명령으로 방문하는 모든 팔 자세의
카메라 외부 보정과 pan–chassis yaw 결합. **loaded/fine 수집 경로는 아직 연결되지 않았다.**
v3 pair 어댑터가 먼저 필요하므로 이 문서는 실행되지 않는 가상의 loaded 측정 CLI를 제시하지 않는다.
이 자료 없이 `MEASURED_SIM` 파일을 만들면 안 된다.

고정 보정 산출물의 schema는 `ugrp.final_environment_measured_calibration.v1`:
`status=MEASURED_SIM`, `contract_sha256`, 지도별 정적 `maps` hash,
`robot_model=masterpi_v3`, `render_profile=floor_light_v1`, `source_sha`,
`measurement_manifest_sha256`, `params`(motion/motion_loaded/motion_profiles.fine),
`pan_base_yaw`(unloaded/loaded), `camera_models`(상태별 `servo3,servo4,servo5,servo6` →
`origin_m`, optical→actual-chassis `rotation`)를 기록한다.
외부 보정에 포함하지 않은 자세는 v2 FK로 추측하지 않고 provider 실패로 닫는다.
P03의 PF/명령 이력·늦은 fix 거절·0.16초 지연 wrapper는 유지한다.

## P03: 문 앞·문 뒤·목적지 전, 3×120 SIM초

P03의 3은 **지도 수가 아니라 체크포인트 수**다. 선택 지도는
`zone_wide_door_geometry_v3`다. 각 체크포인트까지 실제 이전 leg를 이어 실행해야 한다.
teacher staging/GT reseed/새 PF 시작으로 바꾸지 않는다. 접근·lower→open→p20 8장→
새 fix→re-align→grasp→lift를 같은 provider/PF로 잇고, 도달 못 함도 분모 3에 넣는다.
각 120초는 이전 leg를 포함한 전체 check cap이다. reset은 별도 최대 5초로 보고한다.

현재는 다음 **계획 확인**에서 `runnable:false`와 두 선행 조건이 나오는 것이 맞다.

```bash
"$PY" -m scripts.run_final_environment_floor_light --check p03 \
  --expected-source-sha "$FINAL_SHA" --output "$RUN_ROOT/p03"
```

실제 요청 형태는 아래와 같다. **현재 후보에서는 실행하지 말 것**:
보정 인자 누락은 `MEASURED_V3_CALIBRATION_REQUIRED`, 보정 경로/해시 인자가 있어도
`FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED`로 물리/worker import 전에 거부한다.
이것은 실행 명령의 등록 형태이며 P03 인수 실행 완료/가능의 주장이 아니다.

```bash
# 후속 v3 chain adapter와 측정 보정을 등록하고 독립 검토한 새 후보에서만 사용.
CALIBRATION=/absolute/path/to/verified-v3-calibration.json
CALIBRATION_SHA=$(shasum -a 256 "$CALIBRATION" | cut -d ' ' -f 1)
"$PY" -m scripts.sim_cli workflow plan zone-final-environment-floor-light-check -- \
  --check p03 --expected-source-sha "$FINAL_SHA" \
  --calibration "$CALIBRATION" --calibration-sha256 "$CALIBRATION_SHA" \
  --execute --lock-owner codex --output "$RUN_ROOT/p03"
```

후속 어댑터는 평가와 독립인 실행 상한을 구현하고, source/번들/명령 해시,
scan 전후 PF 식별/입자·σ·last_scan_t, own command/servo, capture/release/consumed 시각,
eval-only 위치 오차·빔 이동·재파지 결과를 남겨야 한다. 학생 입력은 자기 RGB·정적 지도·
자기 명령·전달된 메시지만 허용한다. partner의 private state·GT·sim state로 성공/다음 단계를 결정하지 않는다.
v87에서 빈 adapter를 성공으로 처리하는 경로는 없다. 번들의 `provider` 항목은
v84/default의 미활성 P03 메타데이터를 보존한 것이다. 밝은 프로필의 측정값은 새 계약에
속하며 기존 factory에 전달하지 않는다. 후속 P03 후보는 측정 보정과 provider/chain
연결을 함께 등록해야 한다. 이 수집 경로는 학생/provider를 생성하지 않는다.

## 회수·정리

실행 종료/중단 뒤 자신이 만든 세션과 worker 자식 정리를 확인하고 소유 잠금을 해제한다.
다른 작업 프로세스는 종료하지 않는다. raw는 기본 `outputs/` 아래 보존하며 삭제/덮어쓰기하지 않는다.
실제 결과를 얻은 코디네이터는 `docs/tensorboard.md`에 따라 새 snapshot을 만들고
실제 데이터·영상·고정 카드·HParams 로딩을 검증한다. 이번 오프라인 작업은 새 실험 cohort가
없어 TensorBoard 변환이나 화면을 만들지 않았다. Drive는 사용하지 않는다.

## 참고 자료

- [이번 등록·검증 기록](experiments/2026-10-01-final-env-floor-light/README.md)
- [v84 P01 관찰 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)

- [P01 계획](experiments/2026-09-30-e2e-p01-env/README.md), [P03 #312](https://github.com/kcm0127-dotcom/ugrp/pull/312)
- [차단을 발견한 물리 큐 #337](https://github.com/kcm0127-dotcom/ugrp/pull/337)
- [실행 버전 관리](docs/execution_versioning.md), [정적 등록부](configs/zone_final_environment_v87.json)
