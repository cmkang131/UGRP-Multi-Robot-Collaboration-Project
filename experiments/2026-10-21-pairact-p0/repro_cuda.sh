#!/usr/bin/env bash
# pairact P0: CUDA 700 / SIGSEGV reproduction matrix on gcp6 (diagnostic only, no gate claim).
#
# Background (origin/claude/warp4 experiments/2026-10-16-warp4, origin/codex/warp6, warp8):
#   - warp4 R3 on gcp2 L4: beampair (4 worlds) exit 1 "Warp CUDA error 700 ... wp_memcpy_d2h",
#     release s1/s3 SIGSEGV (-11). Three processes shared one GPU through private MPS,
#     nvmax 128 (no --full-active-dof-workspace-v1). Cause not isolated.
#   - warp8: NVMAX overflow at step 226 (128 allocated, 156 active, nv 222) -> undefined behaviour.
#   - r13 on gcp6 (no MPS, nvmax 222, one process, 39 worlds): 0 CUDA errors.
#   So this matrix varies ONE axis at a time on gcp6: nworld (1/4/16) and nvmax (128 vs 222),
#   always with CUDA_LAUNCH_BLOCKING=1; compute-sanitizer only on 1 world.
#   MPS is NOT reproduced here: --gcp6-isolated-v1 refuses CUDA_MPS_* (fail closed). [확인 필요: MPS 축은 gcp6에서 불가]
#
# Usage (on gcp6, as user ugrp, nothing else on the GPU):
#   bash repro_cuda.sh plan          # print commands only (default)
#   bash repro_cuda.sh run           # run the core matrix sequentially (A1..A4, B1)
#   bash repro_cuda.sh run sanitizer # additionally run S1 (compute-sanitizer memcheck, 1 world)
# Every run writes to a NEW directory under $OUT_ROOT; existing dirs are never reused.
set -uo pipefail

MODE="${1:-plan}"; EXTRA="${2:-}"
PY="${PY:-/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python}"
SRC="${SRC:-/home/ugrp/ugrp-sim/src}"
RUNNER="${RUNNER:-$SRC/beamact5-tools/run_warp_flow_teacher_gcp6.py}"
# r13 frozen stack. root 05046e9d pins adapter d354468a + teacher fe6858ec.
# NOTE: r13 summary.json reproduce lists src/835ccef2.. and src/26f84d0f.. while source_contract
# says adapter d354468a / teacher fe6858ec -> the directory names are old, contents newer. [확인 필요]
ROOT_SHA=05046e9d245e46b4ee3d1c43308f7258a9fa41c5
WARP_SOURCE_ROOT="${WARP_SOURCE_ROOT:-$SRC/$ROOT_SHA}"   # [확인 필요] actual directory on gcp6
ADAPTER="${ADAPTER:-$SRC/835ccef26aa84b08cc8f7e256fd0f43aa1583ef9}"
TEACHER="${TEACHER:-$SRC/26f84d0f0ada1c33473c83cca2d3415ce51bd247}"
CASES="${CASES:-/home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json}"
XML="${XML:-/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml}"
REFS="${REFS:-/home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json}"
CAP_S="${CAP_S:-30}"          # warp8 overflow was at step 226 (~22.6 SIM s); 30 s covers it
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_ROOT="${OUT_ROOT:-/home/ugrp/ugrp-sim/runs/pairact-p0/cuda-repro-$TS}"
W1="${W1:-0}"                                 # 1-world index
W4="${W4:-0,1,2,3}"                           # same as warp4 beampair indices
W16="${W16:-0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,16}"   # world 15 excluded (log blow-up)

COMMON=(--flow beampair --adapter-source "$ADAPTER" --teacher-source "$TEACHER" --cases "$CASES"
  --cap-s "$CAP_S" --vm-hourly-usd 1.096 --gcp6-isolated-v1 --placement-graspable-filter-v1
  --world-model-parameters-v1 --native-sleep-policy-compat-v1 --warp-native-contact-v1
  --canonical-xml "$XML" --per-world-model-references-v1 "$REFS" --batch-per-world-speed-v1)

# id | indices | extra flags | wrapper
MATRIX=(
  "A1|$W1|--full-active-dof-workspace-v1|"      # r13-like control, 1 world
  "A2|$W4|--full-active-dof-workspace-v1|"      # 4 worlds
  "A3|$W16|--full-active-dof-workspace-v1|"     # 16 worlds
  "B1|$W4||"                                    # warp4-like nvmax 128 (flag OFF), 4 worlds
  "B2|$W16||"                                   # nvmax 128, 16 worlds
)
SANITIZER_ROW="S1|$W1||sanitizer"               # compute-sanitizer memcheck, 1 world, nvmax 128

preflight() {
  mkdir -p "$OUT_ROOT"
  local f="$OUT_ROOT/env.txt"
  {
    echo "utc=$(date -u +%FT%TZ) host=$(hostname)"
    for p in "$PY" "$RUNNER" "$CASES" "$XML" "$REFS"; do [ -e "$p" ] && echo "ok $p" || echo "MISSING $p"; done
    for d in "$WARP_SOURCE_ROOT" "$ADAPTER" "$TEACHER"; do
      if [ -d "$d" ]; then echo "src $d HEAD=$(git -C "$d" rev-parse HEAD 2>/dev/null || echo no-git) dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l)";
      else echo "MISSING $d"; fi
    done
    sha256sum "$CASES" "$XML" "$REFS" "$RUNNER" 2>/dev/null
    "$PY" - <<'EOF'
import importlib, sys
print('python', sys.version.split()[0])
for m in ('warp', 'mujoco', 'mujoco_warp', 'numpy'):
    try:
        mod = importlib.import_module(m); print(m, getattr(mod, '__version__', '?'), getattr(mod, '__file__', ''))
    except Exception as e:
        print(m, 'IMPORT_FAIL', type(e).__name__, e)
try:
    import warp as wp; wp.init(); print('warp_cuda_driver', wp.context.runtime.driver_version, 'toolkit', wp.context.runtime.toolkit_version)
except Exception as e:
    print('warp_init_fail', e)
EOF
    "$PY" -m pip freeze 2>/dev/null | grep -i -E "warp|mujoco|numpy|scipy"
    nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
    command -v compute-sanitizer && compute-sanitizer --version | tail -1 || echo "compute-sanitizer NOT on PATH (try /usr/local/cuda/bin)"
    env | grep -E '^CUDA_MPS' || echo "no CUDA_MPS env"
  } | tee "$f"
  if grep -q '^MISSING' "$f"; then echo "PREFLIGHT FAIL: fix paths (env overrides) before run" >&2; return 1; fi
  if [ "$(git -C "$WARP_SOURCE_ROOT" rev-parse HEAD 2>/dev/null)" != "$ROOT_SHA" ]; then
    echo "PREFLIGHT WARN: WARP_SOURCE_ROOT HEAD != $ROOT_SHA (check $SRC for the r13 root tree)" >&2
  fi
}

one() {
  local id="$1" idx="$2" flags="$3" wrap="$4" out="$OUT_ROOT/$1"
  local cmd=("$PY" "$RUNNER" "${COMMON[@]}" --indices "$idx" --out "$out")
  [ -n "$flags" ] && cmd+=($flags)
  if [ "$wrap" = sanitizer ]; then
    # memcheck is ~100x slower (warp6: did not finish the first control step). Bound it.
    cmd=(timeout 3600 compute-sanitizer --tool memcheck --log-file "$OUT_ROOT/$id.sanitizer.log" --print-limit 100 "${cmd[@]}" --diagnostic-ticks 3)
  else
    cmd=(timeout 2700 "${cmd[@]}")
  fi
  echo "[$id] cd $WARP_SOURCE_ROOT && WARP_SOURCE_ROOT=$WARP_SOURCE_ROOT CUDA_LAUNCH_BLOCKING=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa ${cmd[*]}"
  [ "$MODE" = run ] || return 0
  local t0; t0=$(date +%s)
  ( cd "$WARP_SOURCE_ROOT" && env WARP_SOURCE_ROOT="$WARP_SOURCE_ROOT" CUDA_LAUNCH_BLOCKING=1 \
      OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa "${cmd[@]}" ) > "$OUT_ROOT/$id.log" 2>&1
  local rc=$?
  local cuda; cuda=$(grep -c -E "CUDA error|illegal memory|Segmentation|overflow" "$OUT_ROOT/$id.log")
  echo "$id indices=$idx flags='$flags' wrap=$wrap rc=$rc wall_s=$(( $(date +%s)-t0 )) cuda_or_overflow_lines=$cuda" | tee -a "$OUT_ROOT/matrix.tsv"
  (sudo -n dmesg -T 2>/dev/null || journalctl -k --since "-1h" 2>/dev/null) | grep -E "Xid|segfault" | tail -20 > "$OUT_ROOT/$id.kernel.txt"
  sleep 5   # let the CUDA context exit before the next isolated-host admission check
}

preflight || { [ "$MODE" = run ] && exit 2; }
for row in "${MATRIX[@]}"; do IFS='|' read -r id idx flags wrap <<<"$row"; one "$id" "$idx" "$flags" "$wrap"; done
if [ "$EXTRA" = sanitizer ]; then IFS='|' read -r id idx flags wrap <<<"$SANITIZER_ROW"; one "$id" "$idx" "$flags" "$wrap"; fi
[ "$MODE" = run ] && { echo "done -> $OUT_ROOT/matrix.tsv"; (cd "$OUT_ROOT" && sha256sum env.txt matrix.tsv *.log > SHA256SUMS.txt); }
exit 0
