# D4 장면 적합성 시험: 실행 명령 초안 (DRAFT, 10/21 밤 gcp2)

상태: **DRAFT**. 사전 등록(`SCENE_FIT_PREREG_DRAFT.json`)을 FROZEN으로 커밋하고 Codex 검토를 받기 전에는 GPU를 쓰지 않습니다.
목적: ACT C2c 구성(R8 step-100000 + v7 시계, deadband 2)을 nav v6 장면 외관으로 HO4 × N=1(4 world) 평가해 v5 결과와 비교합니다.

## 0. 무엇이 바뀌는가 (코드 근거)
- ACT 장면은 `walls_floor_contrast_v5_indigo110_s80`이고 하드코딩되어 있습니다(`scripts/warp_act_scene.py:2,16`). 장면을 고르는 CLI 플래그는 없습니다.
- nav r5 장면 `walls_floor_contrast_v6_indigo110_s80_neutral_start`는 v5와 벽 rgb·hsv·패턴·텍스처가 같습니다(nav 브랜치 `sim/scene_contrast_v5.py:31-34`). 조명 0.30은 기본 `noshadow_bright_v1`의 0.3과 같아서 배율이 1.0입니다(같은 파일 `:25-29,41-45`, `sim/render_profile.py:53`). 실제 차이는 **픽업 바닥 하나**입니다. 불투명하게 렌더되는 남색 `zone_pickup` 오버레이(rgba `.12 .36 .70 .14`)를 회색 타일 60개(채도 0)로 바꿉니다(`sim/neutral_pickup_floor.py:57-97`).
- 패치(default off)는 env `UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1`일 때만 `sim.scene_contrast_v5.install`을 감쌉니다. v5 장면을 만든 뒤 neutral 타일을 칠합니다(`scripts/act18_scene_fit.py`). 연결 위치는 두 곳입니다.
  - `scripts/act16w_native_run.py`: eval-owner가 이 경로로 시작합니다(`act18_evaluate.py:388-394` → `act16w_native_run.py:46-51`).
  - `scripts/act17_v7_rebuild_compiled_references.py`: C312 참조를 다시 만드는 도구입니다.
  - env 값은 `act18_c2c_stage.py`의 `launch.json` env에 기록됩니다.
- 타일은 contype·conaffinity 0이라 물리 변화는 없습니다. 다만 ngeom이 +59가 되고 XML sha가 바뀌므로 **기존 v5 C312 참조는 fail-closed로 거부됩니다**(`simalt_compiled_compat.py:85-89`, f0db6b1ab). 그래서 v6 참조를 반드시 새로 만들어야 합니다.

## 1. 사전 확인 (gcp2, CPU)
```bash
SRC=/home/ugrp/ugrp-sim/src/act18-scene-v6-fit-<SHA>      # 이 브랜치 clean clone, HEAD=<SHA>
B=/home/ugrp/ugrp-sim
REF5=$B/runs/act17-v7/record-references-r1                   # C2c가 쓴 v5 참조 (launch.json 기록값)
# [확인 필요] case-068/069/070/071 = plans.json의 index 68..71 = seed 88668..88671인지 확인합니다.
python3 -c "import json;e=json.load(open('$REF5/plans.json'))['episodes'];print([(i,e[i]['seed']) for i in (68,69,70,71)])"
git -C $SRC status --porcelain   # 0줄이어야 합니다
```
seed가 다르면 아래 `--cases`를 실제 index로 바꾸고, 그 사실을 사전 등록에 적은 뒤 진행합니다.

## 2. v6 C312 참조 생성 (gcp2, C312 CPU env, GPU 없음)
```bash
TS=$(date -u +%Y%m%dT%H%MZ)
REF6=$B/runs/act18/scene-fit-v6-refs-$TS
cd $SRC && UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1 MUJOCO_GL=osmesa \
  OMP_NUM_THREADS=1 LP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  $B/runs/simalt3/c-env/bin/python scripts/act17_v7_rebuild_compiled_references.py --enabled \
    --plans $REF5/plans.json \
    --teacher-source $B/src/warp1-teacher-snapshot-6f057f7e \
    --qualified-source $B/src/f0db6b1abb842ea65b71c433738210254f300a7c \
    --owner-source $SRC \
    --cases 68 69 70 71 --workers 1 \
    --host-instance ugrp-act-l4-gcp2 --host-machine-type g2-standard-8 --host-zone asia-northeast3-a \
    --out $REF6
# 확인할 것
jq '.status,.scene_fit,.N' $REF6/summary.json                 # "complete", "v6_neutral_pickup_v1", 4
jq '.act18_scene_fit.mode' $REF6/case-068/world-000/scene.json # "v6_neutral_pickup_v1"
grep -c zone_pickup_tile_ $REF6/case-068/runtime-scene.xml     # 60
```
- `--reference-root`는 쓰지 않습니다. v5 참조와 의미 비교를 하면 ngeom 차이로 실패하기 때문입니다. 대신 `model_counts.ngeom`이 v5 대비 정확히 +59인지 사람이 확인합니다.
- [확인 필요] `--host-machine-type`은 기록용 값입니다. 실제 gcp2 machine type으로 바꿉니다.

## 3. 사전 등록 동결
```bash
# SCENE_FIT_PREREG_DRAFT.json -> SCENE_FIT_PREREG.json (status FROZEN, pre_registered_utc 기록), commit+push 후 Codex 검토
```

## 4. 평가 실행 (gcp2 L4, 1 run = C2c-ho4-rep1, 그룹 3개 병렬, 약 15분 wall)
```bash
cd $SRC && UGRP_ACT18_SCENE_FIT=v6_neutral_pickup_v1 \
/home/ugrp/ugrp-rl1b-act-env/bin/python -u scripts/act18_c2c_stage.py --enabled \
  --prereg experiments/2026-10-21-act18-scene-fit/SCENE_FIT_PREREG.json \
  --checkpoint $B/runs/act18/training-r1/R8/step-100000 \
  --run-root $B/runs/act18/scene-fit-v6-$TS \
  --native-gate $B/runs/act17-v7/gate-r1/gate-recount.json \
  --physics-python $B/runs/simalt3/warp-env/bin/python \
  --qualified-source $B/src/f0db6b1abb842ea65b71c433738210254f300a7c \
  --teacher-source $B/src/warp1-teacher-snapshot-6f057f7e \
  --qualification $B/runs/warp3/teacher-gate-qualification-r1.json \
  --references $REF6/per-world-references.json \
  --record-references $REF6 \
  --protocol $B/src/ab89b3c54/experiments/2026-10-17-act18/protocol.json
```
- 드라이버는 사전 등록의 `cross_order`(`['C2c-ho4-rep1']`)만 돕니다(`act18_c2c_stage.py:74`). HO4 그룹은 하드코딩된 `[88668],[88669],[88670,88671]` / `case-068/069/070`입니다(`:86`).
- env는 driver → evaluator → owner Popen으로 상속됩니다(`act18_c2c_stage.py:138`, `act18_evaluate.py:395`의 Popen에는 env 인자가 없습니다).
- 실행 후 확인합니다. `owner/world-*/` 또는 scene manifest에 `act18_scene_fit` 기록이 있는지, `launch.json` env에 `UGRP_ACT18_SCENE_FIT`가 있는지 봅니다. 그리고 review-own JPEG 1장에서 픽업 바닥이 회색 타일로 보이는지 확인합니다(사람이 보는 확인이며, 판정에는 쓰지 않습니다).

## 5. 분석과 판정 (사전 등록)
```bash
/home/ugrp/ugrp-rl1b-act-env/bin/python scripts/act18_c2c_analyze.py --enabled \
  --run-root $B/runs/act18/scene-fit-v6-$TS --prereg experiments/2026-10-21-act18-scene-fit/SCENE_FIT_PREREG.json
```
- [확인 필요] `act18_c2c_analyze.py`가 run 1개짜리 cross_order와 C2c-only arms를 받는지는 아직 확인하지 못했습니다. B0나 TRAIN4 집계를 요구하면 G를 world별 `summary.json`에서 직접 재계산합니다. 정의는 C2c와 같습니다(`C2C_V7CLOCK_PREREG.json` metrics.G).
- 판정은 다음 기준만 씁니다.
  - **UNIFY_V6**: G(v6, 4 world) ≥ 2/4.
  - **BRANCH_NAV_V5**: G ≤ 1/4.
  - HOST_ERROR나 참조 불일치가 나면 판정하지 않습니다.
  - v5 C2c 결과(rep1 4/4, 합계 11/12)는 문맥으로만 보고 합산하지 않습니다.
- release·task·lift·done·Pre는 보고만 합니다. release는 픽업 바닥 위에서 하므로 v6 픽업 타일의 영향을 가장 직접 받는 지표이고, 그 점을 보고서에 적습니다.

## 6. 종료
프로세스 0개와 GPU 0 %를 확인하고, lease를 삭제한 뒤 gcp2를 stop합니다(**TERMINATED** 확인).
