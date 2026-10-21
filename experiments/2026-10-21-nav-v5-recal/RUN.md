# nav v5 재보정 (BRANCH_NAV_V5) — 실행 문서 (2026-10-21)

브랜치 `dsh/nav-v5-recal` (base `dsh/nav-v230-r5` `e11efbeb9`). 계기: D4 장면 적합성 시험에서
ACT C2c가 v6 장면에서 G 1/4 → 사전 등록 분기 `BRANCH_NAV_V5`
(`experiments/2026-10-21-act18-scene-fit`, `7aa8c3d87`/`1bb49dcda`). ACT는 학습 장면 v5
(`walls_floor_contrast_v5_indigo110_s80`)에 두고, nav를 v5에서 다시 잰다.

사전 등록: `NAV_V5_RECAL_PREREG_DRAFT.json` (**DRAFT**). 아래 0단계로 동결한 뒤에만 1단계를 돈다.
v5 결과는 v6 r5 PASS(2026-10-20)와 다른 조건이며 합산하지 않는다.

## v5 대 v6 차이 (코드 근거)

| 항목 | v5 `…v5_indigo110_s80` | v6 `…v6_indigo110_s80_neutral_start` | 근거 |
|---|---|---|---|
| 벽 페인트·질감 | rgb 90,75,110, v1_common_mode, v5 질감 파일 | 같음(`assets` = v5 이름) | `sim/scene_contrast_v5.py` `PROFILES` |
| 기본 렌더 | `noshadow_bright_v1`(그림자 off, 반사 0, cutoff 180, 조명 ×0.3) | 같음 | `sim/render_profile.py` |
| 추가 조명 배율 | 없음 | `light_scale` 0.30 ÷ 기본 0.30 = **×1.0**(실질 변화 없음) | `_scale_lights`, `profile_record` |
| 주 바닥 질감 | natural floor v1 | 같음 | `apply_xml` → `v1.apply` |
| **픽업 바닥** | 지도 `zone_pickup` rgba `.12 .36 .70 .14`, MJWarp가 불투명으로 그림: **OpenCV H 107–108, S 중앙 212, V 중앙 90**, 첫 nav 프레임의 57.0 % | `zone_pickup` 제거, 6×10 회색 타일(S=0, α 1) | `sim/neutral_pickup_floor.py`, `experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg` |
| ngeom | 기준 | +59 (참조 1446 대 1387) | scene-fit README §3 |
| zone B 페인트·벽·문·스폰·물리 | rgba `.20 .40 .95 .30`, (4.6,−2.1) 반폭 (0.3,0.7) | 같음, `changes_physics False` | `sim/zone_arena.py` |

결론: 조명은 같고 **차이는 픽업 바닥 하나**다. 위험은 v5 파란 바닥(H 107–108)이 zone 밴드
(H 110–114)와 2–3 단위 차이라 JPEG 번짐으로 (a) 비-zone 오검출 또는 (b) zone 성분과 합쳐져 bbox
하단 행(→ r5 stage-2 1.5 m latch·0.52 m claim)을 옮기는 것이다.

## 코드 (모두 기본 off)

- `E2EWARP_NAV_SCENE_PROFILE=v5` (`harness/e2ewarp_nav_scene.py`): nav prepare가
  `stack_values.scene_profile`만 v5로 바꾸고 deviation(authority coordinator)·queue 표지
  `nav_scene_profile(_selection)`를 쓴다. execute는 env↔queue↔stack_values를 physics import 전에
  재검사한다(양방향 fail closed). nav 외 mode에서 env를 켜면 오류.
- 밴드 후보: `gpu_calib_v5_h111`/`gpu_calib_v5_h112` 와 gate mode `v230_r5_v5h111`/`v230_r5_v5h112`
  (= r5에서 `zone_profile`만 다름). 이 mode들은 장면 v5가 아니면 queue에서 거부된다.
- `build_context(eval_xml_transform=None)`: sweep의 zone-B 지움 참조 렌더 전용 hook.

## 호스트

- **gcp6** (`.venv-warp` = `/home/ugrp/ugrp-sim/ugrp/.venv-warp`, r5가 10/20에 돈 곳)가 기준이다.
  단일 lease. [확인 필요] 현재 gcp6는 pairact P2/pilot 작업이 lease를 잡고 있을 수 있다 — lease 확인 후 실행.
- **gcp2**: nav 스택 설치 여부 [확인 필요]. STATUS(10/21)상 gcp2는 ACT env(`/home/ugrp/ugrp-rl1b-act-env`)만
  확인되고 beamact5 MJWarp 스택은 BLOCKED, nav 복사는 계획 단계다. gcp2에서 돌리려면 새 venv에 설치
  (`.venv-warp` 복사 금지, `experiments/2026-10-16-gcp6setup/setup_guest.sh` 10행과 같은 버전):
  ```bash
  python3.12 -m venv /home/ugrp/ugrp-sim/ugrp/.venv-warp
  /home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/pip install mujoco==3.16.0 warp-lang==1.15.0 numpy==2.5.2 \
    opencv-python-headless==5.0.0.93 pillow==12.3.0 websockets==17.2 glfw==2.10.2 PyOpenGL==3.1.10 \
    scipy==1.17.1 'https://github.com/google-deepmind/mujoco_warp/archive/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148.zip'
  ```
  추가로 필요: clean clone(`git-shared.git` `--reference`), odometry calibration
  `runs/e2ewarp-nav1-calib-h/nav-calibration.json`(gcp6에서 Oracle 경유 복사 + sha256 대조),
  host receipt(`/home/ugrp/ugrp-sim/ops-reviews/e2ewarp-host-receipt.json` 형식), Step B만 relay
  `127.0.0.1:18627`(reverse tunnel). sweep(1단계)은 relay·calibration이 필요 없다.

## 0. 사전 등록 동결 (렌더 전, Oracle 레포에서)

```bash
cd /home/ubuntu/UGRP-wt/nav-v5-recal
python3 - <<'EOF'
import json, datetime
d = json.load(open('experiments/2026-10-21-nav-v5-recal/NAV_V5_RECAL_PREREG_DRAFT.json'))
d['status'] = 'FROZEN'; d['frozen_utc'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
json.dump(d, open('experiments/2026-10-21-nav-v5-recal/NAV_V5_RECAL_PREREG.json', 'w'), ensure_ascii=False, indent=1)
EOF
git add experiments/2026-10-21-nav-v5-recal/NAV_V5_RECAL_PREREG.json
git commit -m "nav v5 recal: freeze prereg (before any render)"; git push
SHA=$(git rev-parse HEAD)   # 이 SHA를 VM에서 그대로 쓴다
```

## 1. render-only sweep (GPU, 예상 수 분; 렌더 200장)

```bash
# VM (gcp6), clean clone at $SHA, cwd = clone root
P=/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python
TS=$(date -u +%Y%m%dT%H%MZ)
$P experiments/2026-10-21-nav-v5-recal/render_sweep_v5.py \
  --out /home/ugrp/ugrp-sim/runs/nav-v5-recal-sweep-$TS \
  --expected-source-sha $SHA \
  --prereg experiments/2026-10-21-nav-v5-recal/NAV_V5_RECAL_PREREG.json
```

- 종료코드 0 = 어떤 밴드가 통과(`measure.json` `selection.gate_mode`), 1 = `NO_BAND_PASSED` → **중단·보고**
  (Step B 없음, 결과 뒤 새 밴드 추가 금지).
- 판정: C1 zone-free 0 / C2 비-zone FP 0(지움 렌더, 두 로봇) / C3 r1 Step A 12/12 검출 /
  C4 검출 bbox 좌·우·하단이 zone-only 성분과 ±3 px. 선택: B0 → B1 → B2 순서로 첫 통과.
- 보고 전용: v6 대조 판정(B0 통과 예상), v6 대조 대 10/19 Step A 표(x1.5 t000 bbox 81,66,379,82 /
  1811 px 등), v5 대 v6 zone-only bbox, path 검출과 하단 행 지면 거리.
- HOST_ERROR → 판정 없음, 고친 뒤 새 `--out`에서 1회 재실행.
- 원본 회수: `measure.json`, `SHA256SUMS`, `frames/` → Oracle
  `outputs/e2e18-admin/nav-gate/v5-recal/sweep-$TS/`.

## 2. Step B 1회 재현 (sweep 통과 + 같은 동결 prereg)

```bash
export E2EWARP_NAV_SCENE_PROFILE=v5
export E2EWARP_NAV_GATE_MODE=<measure.json selection.gate_mode>   # v230_r5 | v230_r5_v5h111 | v230_r5_v5h112
export E2EWARP_NAV_ARRIVAL=odom_projection
export E2EWARP_NAV_CALIBRATION=/home/ugrp/ugrp-sim/runs/e2ewarp-nav1-calib-h/nav-calibration.json
R=/home/ugrp/ugrp-sim/runs
$P -m scripts.e2ewarp_nav_manifest --out $R/nav-v5-recal-components.json \
  --calibration "$E2EWARP_NAV_CALIBRATION" --source-sha $SHA

# ① 단독 r1 (진단, 게이트 아님). 문 통과 실패 또는 벽/문틀 접촉 → ② 중단
$P -m scripts.run_e2e_warp --mode nav --prepare --e2e-warp-batch on_v1 --seed 601 --nworld 1 \
  --condition peer_en --nav-sim-budget-s 60 --components $R/nav-v5-recal-components.json \
  --arrival-odom-projection --nav-solo-robot r1 --output $R/e2ewarp-nav-v5-recal-solo-r1-admission
jq -e '.nav_scene_profile=="walls_floor_contrast_v5_indigo110_s80" and .stack_values.scene_profile==.nav_scene_profile' \
  $R/e2ewarp-nav-v5-recal-solo-r1-admission/queue.json
$P -m scripts.run_e2e_warp --mode nav --execute --e2e-warp-batch on_v1 --nav-solo-robot r1 \
  --queue $R/e2ewarp-nav-v5-recal-solo-r1-admission/queue.json --expected-source-sha $SHA \
  --host-receipt /home/ugrp/ugrp-sim/ops-reviews/e2ewarp-host-receipt.json \
  --components $R/nav-v5-recal-components.json \
  --relay-url http://127.0.0.1:18627/v1/chat/completions --output $R/e2ewarp-nav-v5-recal-solo-r1

# ② 2-robot Step B (--nav-solo-robot 없이, 새 root)
$P -m scripts.run_e2e_warp --mode nav --prepare --e2e-warp-batch on_v1 --seed 601 --nworld 1 \
  --condition peer_en --nav-sim-budget-s 60 --components $R/nav-v5-recal-components.json \
  --arrival-odom-projection --output $R/e2ewarp-nav-v5-recal-stepB-admission
$P -m scripts.run_e2e_warp --mode nav --execute --e2e-warp-batch on_v1 \
  --queue $R/e2ewarp-nav-v5-recal-stepB-admission/queue.json --expected-source-sha $SHA \
  --host-receipt /home/ugrp/ugrp-sim/ops-reviews/e2ewarp-host-receipt.json \
  --components $R/nav-v5-recal-components.json \
  --relay-url http://127.0.0.1:18627/v1/chat/completions --output $R/e2ewarp-nav-v5-recal-stepB

# 분석 (r5 도구 그대로; mode 필터 없음)
$P -m scripts.e2ewarp_nav_recount --run $R/e2ewarp-nav-v5-recal-stepB
$P experiments/2026-10-20-nav-v230-r5/nav_v230_r5_analysis.py --run $R/e2ewarp-nav-v5-recal-stepB \
  --admission $R/e2ewarp-nav-v5-recal-stepB-admission --expected-source-sha $SHA \
  --out $R/e2ewarp-nav-v5-recal-stepB/analysis.json \
  --preflight-render /home/ugrp/ugrp-sim/runs/nav-v5-recal-sweep-$TS/measure.json
```

- 수용표(PREREG_V230_R5와 동일): `GT 2/2 ∧ claim 2/2 ∧ mismatch 0 ∧ FP 0 ∧ 경계 0`.
  eval-only: 로봇 간 최소 거리·접촉, 로봇-씬 접촉, 명령/GT 비율.
- `--preflight-render`: 분석기는 `checks.zone_free.{detections_total,max_largest_component_px,frame_n}`을
  읽는다(`ef5ebcd9`). sweep `measure.json`이 같은 이름으로 선택 밴드의 r1 zone-free + 지움 렌더
  lane 프레임(두 로봇) 합계를 쓴다(분석기 수정 없음).
- [확인 필요] relay `18627`이 10/21 STATUS에서 000(응답 없음)으로 기록됐다. Step B 전 endpoint_watch·잔액 확인 필수.
- 원본 회수: Oracle `outputs/e2e18-admin/nav-gate/v5-recal/stepB-<TS>/`, 보고서
  `outputs/reports/2026-10-21-nav-v5-recal-stepB-dsh-<TS>.md`. 종료 시 lease 삭제 → 프로세스 0/GPU 0 → stop.
