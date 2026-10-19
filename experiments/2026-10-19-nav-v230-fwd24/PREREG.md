# nav Step B prereg — V≤230 + forward 2.4 m (2026-10-19, 창민 승인)

**상태: 실행 전 동결(FROZEN).** 이 문서는 2026-10-19 창민(팀장)의 조건부 승인
("V≤230 + 전진 2.4 m")을 그대로 사전 등록한다. 아래 조건·수용표·금지·증거 경로는
②③ 렌더 체크와 Step B 실행 **전에** 커밋·푸시된 branch head에 포함된다. 실행
중 조건을 바꾸지 않으며, 바뀐 조건으로 돈 실행은 새 prereg 없이는 수용하지 않는다.

- 작성 시각: 2026-10-19T14:2xZ (로컬, gcp6 부팅 전)
- 작업 디렉터리: `/home/ubuntu/UGRP-wt/nav-v230-fwd24`
- branch: `dsh/nav-v230-fwd24` (새 브랜치, force 아님)
- base: `554f40f0e8d6137737eda71b5d20eaef0454b872` (= light 0.30 neutral floor, `dsh/nav-v6-light30` tip)
- 호스트: **gcp6만** `ugrp-act-l4-gcp6` / project `ugrp-sim-f-1016` / account
  `kcm5781kcm5781@gmail.com` / zone `asia-northeast3-a`
- 실행 source SHA: 이 문서와 코드를 포함한 push된 branch head. `queue.json`,
  `result.json`, `RUN_META.json`의 `source_sha`, VM checkout HEAD, 이 문서가 속한
  commit SHA가 **모두 같은 값**이어야 한다. 이 문서는 자기 commit SHA를 담을 수
  없으므로, push 직후 그 값을 결과 보고서와 VM `host-receipt`에 기록한다
  (preregistration ID = pushed SHA).

## 0. 승인 조건 → 동결 내용

| # | 승인 조건 (창민, 2026-10-19) | 이 prereg의 동결 |
|---|---|---|
| A | v1의 H 110–114 / S≥100 유지, **V 상한만 30–230**으로 확장, min_component 600 | `gpu_calib_v230` = OpenCV H 110–114, S≥100, V 30–230, 최대 4-연결성분 ≥600 px. v1(`gpu_calib_v1`)은 **기본값·코드 불변**. 두 밴드 결과 pooling 금지. |
| B | 스폰(x≈−0.898, y=−2.375)에서 **최대 2.4 m 전진** | `forward_then_search` 모드: 자신이 발행한 명령 + 주입된 own-command odometry로 적산한 전진거리 상한 **2.4 m**. 마지막 pulse는 2.4 m에 맞춰 폭을 자른다. **초과 전진 금지**(cap 후에는 제자리 회전만). |
| C | **목적지 검출 즉시 추종 전환**(추가 회전/지연 없음) | 매 control step `observe()` → `command()` 순서. 검출이 생긴 같은 tick에 `drive_reason=driving`으로 전환하고, 잔여 회전 없이 전진 pulse를 낸다. |
| D | Claude의 기존 1.7 m 상한은 **2.4 m로 대체 확정** | 1.7 m는 어떤 기본값·상수에도 쓰지 않는다. 코드·queue marker·시험 모두 2.4 m만 수용하며, 다른 cap은 admit에서 거부한다. |
| E | 단일 lease, 2 robots, seed 601, peer_en, SIM 60 s cap, static map/cargo/top camera/GT 입력 금지 | §4·§5에 고정. gcp6 lease 1개만 생성하고, 다른 워커 lease는 건드리지 않는다. |
| F | ② zone 없는 프레임 오검출 0 렌더 확인 | §3.1. |
| G | ③ 2.4 m 전진 경로 충돌/경계 위반 없음 확인 | §3.2. |
| H | ②③ 둘 다 깨끗할 때만 같은 prereg로 Step B 1회, 아니면 중단·증거 보고 | §3.3·§6. |

## 1. 조건 / provenance (동결)

| 항목 | 값 |
|---|---|
| 장면 프로필 | `walls_floor_contrast_v6_indigo110_s80_neutral_start`, sha256 `1c57232468d2b7a3e580eb0d3e78ccdccdef7a94161cd7567baa3adee8c39bed` (light_scale 0.30, factor 1.0, `changes_physics=False`) |
| 지도 | `zone_wide_two_doors_final_v3`, sha256 `b6a61f7e748b995f13800aa0e4c3a0ec4a50dcd152fc75815225115d0354a41b` (불변) |
| 시나리오 | `s7_pair_with_solo_v7`, seed **601**, leader `r2` (seed%2), 2 robots r1·r2, nav-only (r3 prune, cargo 미생성) |
| 스폰 | r1 `(−0.8982, −2.375, 0.032355, yaw 0)`, r2 `(−0.8982, −2.875, 0.032355, yaw 0)` (게이트 계약 v1, 이동 금지) |
| 목적지 | zone B, center `(4.6, −2.1)`, half `(0.3, 0.7)` (eval-only) |
| 카메라 | r1/r2 자신의 640×480, gamma 1.0, JPEG q82, 10 Hz |
| 통신 | `peer_en` (LLM 판단 2회, relay 경유) |
| SIM 예산 | `--nav-sim-budget-s 60` (600 tick, rows 1202, commands 1200) |
| 물리 | `mjwarp_batch_v1`, `warp_native_contact_v1`, noslip 0 |
| odometry calib | `runs/e2ewarp-nav1-calib-h/nav-calibration.json` (measured_n 60, forward 0.004024203361827748 m/pct-s, yaw 1.7275488814064257 deg/pct-s). **`calibration_source_sha=d182b67` ≠ 실행 source SHA**: 결과·queue·보고서에 mismatch를 명시한다. 장면은 `changes_physics=False`라 기하가 같아 재사용한다. |
| 금지 입력 | static map(제어 입력), cargo, top camera, GT 좌표/접촉/성공판정. 계획·판단에는 자기 RGB·자기 명령 이력·통신 채널만. |

## 2. 가설 (측정 전 고정)

- **H1 (오검출)**: light 0.30 장면에서 V≤230 밴드는 zone 없는 프레임(벽·픽업 바닥·빈 레인)에서
  최대성분 <600 px로 발화하지 않는다. v1에서 0 px였던 벽(H≈133)·중성 바닥(S=0)은 밴드
  밖이므로 그대로 0이다.
- **H2 (획득)**: 2.4 m 전진(≈17.0 s, 171 pulse × 0.01408 m) 안에 r1/r2가 zone B를 검출해
  즉시 추종으로 전환하고, 60 s 안에 GT 도착 2/2에 도달한다. 전진 없이(in-place SEARCH만)
  스폰에서 발화하지 않는다(기존 A FAIL).
- **H3 (경로)**: y=−2.375/−2.875 두 레인, x −0.898→1.502 구간은 벽·문틀·화물과 겹치지
  않는다. 문(wide door, x=2.2)은 2.4 m 상한보다 0.70 m 앞이라 경로 안에 들어오지 않는다.

H2는 **조건부**다: 검출 후 arrival guard(bottom band ≥0.98, height ≥0.04, area ≤0.65,
solidity ≥0.45, center-span, top 미접촉)가 작동하지 않으면 GT 도착 전에 주행이 계속될 수
있다. 이 경우도 결과는 그대로 기록하며 성공으로 쓰지 않는다.

## 3. ②③ 사전 관문 (Step B 전, render-only)

증거 스크립트는 이 commit에 포함된 `experiments/2026-10-19-nav-v230-fwd24/render_check.py`이며,
push된 source SHA의 clean clone에서만 실행한다. 새 run dir만 쓰고 기존 run dir을 덮어쓰지 않는다.

### 3.1 ② zone 없는 프레임 오검출 0

- 자세(최소 4, r1, setup-only qpos; r2는 게이트 스폰 레인 유지): `wall_south`(x=1.8, yaw −90°),
  `wall_north`(x=1.8, yaw +90°), `pickup_west`(x=−1.4, yaw 180°), `pickup_rear`(spawn x=−0.898, yaw 180°),
  `lane_west`(x=1.5, yaw 180°). 각 자세 tick 0·5, 총 10프레임.
- 측정: 게이트 검출기 경로 `GpuCalibZoneDetector(profile='gpu_calib_v230')` + 같은 HSV·마스크
  함수로 계산한 **프레임 전체 최대 4-연결성분 px**.
- **PASS ⇔ 모든 프레임에서 `detections == 0` 그리고 최대성분 < 600 px.**
  하나라도 detections>0 또는 최대성분 ≥600이면 **② FAIL → Step B 중단**.
- 600 미만의 최대성분(마진)은 그대로 기록하며, 해석 시 리스크로 표기한다.

### 3.2 ③ 2.4 m 전진 경로 충돌/경계 위반 없음

- 자세(최소 5): x ∈ {−0.898, −0.3, 0.3, 0.9, 1.5}, r1 y=−2.375, r2 **같은 x** y=−2.875,
  둘 다 yaw 0, tick 0·5. 실제 두 로봇이 같은 전진거리만큼 나란히 갔을 때의 최근접 조건이다.
- 기하 감사(맵 JSON, eval/setup 전용): 로봇 외곽 반폭 0.081 m·반길이 0.0925 m(제조사
  envelope 0.162×0.185 m), 보수적 외접 반경 0.123 m를 사용해
  (i) 전진 corridor(x −0.898..1.502, 각 레인 ±0.081 m)와 벽/문틀 AABB의 교차 0,
  (ii) r1·r2 corridor 간격 >0, (iii) 장면 XML의 cargo body 수 0,
  (iv) wide door 개구부 안에 두 레인이 들어감(문 x=2.2, 개구 y −3.125..−2.125),
  (v) 입력 경계: 컨트롤러/LLM/GT/top camera/정적지도 제어 입력 0(render-only)을 기록한다.
- **PASS ⇔ (i)~(v) 전부 참이고 경로 5자세·2tick 프레임이 모두 생성·해시됨.**
  벽/문틀/화물과 교차하거나 화물 body가 있으면 **③ FAIL → Step B 중단**.
- 렌더 프레임은 오라클로 회수해 최소 3장을 직접 확인한다.

### 3.3 ②③ 판정과 중단

- ② PASS ∧ ③ PASS일 때만 §5 Step B를 **1회** 실행한다.
- 하나라도 FAIL이면 Step B를 시작하지 않고, 프레임·measure.json·geometries를
  증거 tar로 보존한 뒤 VM 정리(lease 삭제→프로세스 0→GPU 0→stop→TERMINATED)하고 보고한다.
- ②③ 결과는 §4·§5 결과와 pooling하지 않는다(사전 관문, 게이트 성공 아님).

## 4. Step B — 정확한 절차 (②③ PASS 시 1회)

1. VM에서 push SHA clean clone(`/home/ugrp/ugrp-sim/src/nav-v230-fwd24-<sha>`), HEAD 일치·
   `git status --porcelain` 0줄 확인. **기존 src/run 덮어쓰기 금지.**
2. lease **1개만**: `/home/ugrp/ugrp-sim/leases/e2ewarp-v230-fwd24.json`, owner dsh-worker.
   다른 워커 lease/프로세스는 삭제·정지하지 않는다.
3. manifest/admission/execute/recount (환경변수 2개를 prepare·execute 모두에 동일 적용):
   `E2EWARP_NAV_CALIBRATION=<calib>`, `E2EWARP_NAV_GATE_MODE=v230_fwd24`.
   - `python -m scripts.e2ewarp_nav_manifest --out <runs>/e2ewarp-nav-v230-fwd24-components.json --calibration <calib> --source-sha $SHA`
   - `--prepare → <runs>/e2ewarp-nav-v230-fwd24-admission` (존재 금지 dir)
   - `--execute --queue <admission>/queue.json --output <runs>/e2ewarp-nav-v230-fwd24-run`
     `--seed 601 --nworld 1 --round 1 --condition peer_en --nav-sim-budget-s 60`
     `--expected-source-sha $SHA --host-receipt <runs>/host-receipt-nav-v230-fwd24.json`
     `--relay-url http://127.0.0.1:18627/v1/chat/completions`
   - `python -m scripts.e2ewarp_nav_recount --run <run>`
4. relay는 Oracle에서만 띄우고(내 포트, 예: 18646) VM으로 역터널 18627→Oracle로 연결한다.
   **VM에 키를 두지 않는다.** 다른 워커 relay(18626)는 건드리지 않는다.
5. admission/stack-check/ABI 오류는 **우회하지 않고 error 문자열 그대로** 기록·보고하며
   같은 부팅 내 재시도하지 않는다.
6. 60 s SIM 완주 전에 GT 도착으로 조기 종료될 수 있다(정상). 중단·재실행 금지.

## 5. 수용표 (원본 재계수, 요약 JSON 신뢰 금지)

### 5.1 유효성 (VALID)

| 항목 | 요구 |
|---|---|
| source/pin | `queue/result/RUN_META source_sha` == push SHA == VM HEAD, clean |
| 장면·예산 | nav_scene `s7_pair_with_solo_v7`, map `zone_wide_two_doors_final_v3`, spawn y −2.375/−2.875, budget 60.0, robots r1·r2, static_map false, cargo false |
| mode binding | queue `nav_gate_mode=v230_fwd24`, `nav_zone_profile=gpu_calib_v230`, `nav_acquisition=forward_then_search`, `nav_forward_cap_m=2.4`, `nav_zone_min_component=600`; prepare/execute env 일치 |
| stack check | `stack-check.json ok=True`, blocked 0 |
| calibration | queue `nav_calibration.sha256` == 실제 파일 sha, measured_n 60, constants>0, spread<0.20; **calibration_source_sha ≠ 실행 SHA 명시** |
| ticks/rows | ticks 601, localization rows 1202(2 robots), commands rows 1200 |
| 경계 감사 | `input_audit.held_world_reads=0`, `top_camera_control=false`, `static_map_input=false` |
| status | `cap_end`(60 s) 또는 완주/arrival 조기 종료. **cap_end는 성공이 아니다.** |

하나라도 어긋나면 **INVALID**(결과표 제외, pooling 금지). 외부 stop·산출물 미회수는
**NOT_MEASURED**(분모 제외).

### 5.2 PASS / FAIL (VALID에만 적용)

```
PASS ⇔ VALID
      ∧ GT 도착 2/2                 (zone B center (4.6,−2.1), half (0.3,0.7), eval-only 재계수)
      ∧ claim 2/2 ∧ claim_mismatch 0
      ∧ 경계 위반 0
      ∧ source/pin 일치 (위 §5.1)
FAIL ⇔ VALID ∧ ¬PASS
```

- **`detection 0/1202` → FAIL**(획득 실패). 검출 n/1202와 함께 **fresh detection tick 수**,
  첫 검출 tick·위치, drive_reason 분포를 기록한다.
- **`cap_end`만 있는 실행, wheel 400/1200만 있는 실행은 성공이 아니다.**
- r5/gate1/v1 원본 및 v1 밴드 결과와 **pooling 금지**. 이 실행은 독립 조건(v230_fwd24)이다.
- 보고 필드: 검출 n/1202, wheel n/1200, drive_reason 분포, GT 2/2, claim 2/2, mismatch,
  첫 검출 tick, r1/r2 distance_m, wall/SIM, model_calls, 429/5xx, cap_end 여부,
  calibration source mismatch.

## 6. 금지 / 중단

- 금지: 기존 run/checkpoint/src 덮어쓰기, `main`/다른 브랜치 merge, v1 기본값 변경,
  밴드·문턱·min_component·스폰·맵·문 변경, 두 밴드 결과 pooling, Step B 2회 실행,
  admission/stack-check 우회, VM에 모델 키 배치, 다른 워커 프로세스 kill.
- 중단·보고: 테스트 실패, push 실패, ②/③ 실패, admit/ABI 오류, relay 429/잔액 문제,
  120분 초과. 중단 시 증거 보존 후 lease 삭제→stop→TERMINATED 확인.

## 7. 증거 경로 (동결)

VM 원본(새 경로만):
- `/home/ugrp/ugrp-sim/runs/nav-v230-fwd24-render-<TS>/` — ②③ 프레임, `measure.json`,
  `SHA256SUMS`, `render_check.py`, `world-*/scene.xml`, `world-*/eval-geometry.json`
- `/home/ugrp/ugrp-sim/runs/e2ewarp-nav-v230-fwd24-admission/` — queue, stack-check,
  rejection_table, components, host-receipt
- `/home/ugrp/ugrp-sim/runs/e2ewarp-nav-v230-fwd24-run/` — result, nav-evaluation,
  commands, localization, evaluation-state.npz, nav-events, llm_ledger, RUN_META,
  world-00 scene/eval-geometry, review-rgb, terminal-ring
- lease 사본, 로그, VM tar `evidence-nav-v230-fwd24-<TS>.tar.gz` + sha256

Oracle 회수:
- `/home/ubuntu/UGRP/outputs/e2e18-admin/nav-gate/v230-fwd24/<TS>/` — tar.gz, sha256,
  measure.json, 대표 프레임 3장 이상, META, lease 사본, prereg 사본
- 새 보고서: `/home/ubuntu/UGRP/outputs/reports/2026-10-19-nav-stepB-v230-fwd24-dsh-<TS>.md`

## 8. 리스크 / 검증 범위 (사전 명시)

1. **sim 전용**: MJWarp 렌더·물리다. 실제 로봇·실카메라 성능 주장 아님(`domain=sim`).
2. **V≤230 캘리브레이션 출처**: 2026-10-19 한 세션의 light 0.30 프레임 분석(x1.5 2,722 px,
   x2.0 4,407 px)에서 온 값이며, ②가 오검출을 확인한다. ②가 통과해도 다른 자세·조명·화물
   장면의 일반 성능을 주장하지 않는다.
3. **1.7 m → 2.4 m 대체**: 2.4 m는 승인된 상한이며 검출 정지점이 아니다. 검출이 더 이르면
   즉시 추종으로 전환하므로 실제 전진거리는 2.4 m보다 짧을 수 있다.
4. **2.4 m는 own-command odometry 적산**이다(GT 변위 아님). slug·마찰 오차는 기록하지 못한다.
5. **calibration source mismatch**: calib source `d182b67` ≠ 실행 SHA. 물리 불변
   (`changes_physics=False`) 근거로 재사용하며, 결과에 명시한다.
6. **arrival guard**: 검출 후 도착은 기존 bottom-band 가드에 의존한다. 검출 2/2여도
   claim이 0/2면 FAIL이며, 그 원인은 프레임으로 분석한다.
7. **render-only ②③**: 물리 게이트가 아니다. 실제 주행 중 모션 블러·조명 변화는 ②③에서
   재현되지 않는다(nworld=1 배치 렌더).
8. **LLM relay**: 2회 판단 호출. 429/잔액 문제 시 실행 중단·기록.

## 9. 실행 체크리스트

- [ ] 최소 suite 로컬 green(실패 0), push 완료, pushed SHA 기록
- [ ] gcp6 boot → clean clone → HEAD/clean 확인 → lease 1개
- [ ] ② 10프레임: detections 0/10 ∧ max component <600
- [ ] ③ 5자세×2tick: corridor 교차 0, r1/r2 간격>0, cargo 0, door 포함, 입력 경계 0
- [ ] ②③ PASS일 때만 Step B 1회: manifest/admission/execute/recount
- [ ] 판정: VALID ∧ GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ 경계 0 ∧ source/pin 일치
- [ ] 증거 tar+sha256, Oracle 회수, 프레임/measure/SHA256SUMS
- [ ] 프로세스 0·GPU 0 → lease 삭제 → stop → TERMINATED, relay/역터널 종료
- [ ] 보고서: 결론, prereg SHA, ②③ 수치, Step B n/N, VM 종료, 리스크

## 10. Source pin (push 직후 기록)

| 항목 | 값 |
|---|---|
| branch | `dsh/nav-v230-fwd24` |
| pushed SHA (= prereg commit = gate source) | push 직후 결과 보고서·VM receipt에 기록. 이 파일이 속한 commit SHA와 같다. |
| prereg blob sha256 | push 직후 `git show <sha>:experiments/2026-10-19-nav-v230-fwd24/PREREG.md \| sha256sum`으로 기록 |
| base | `554f40f0e8d6137737eda71b5d20eaef0454b872` |
