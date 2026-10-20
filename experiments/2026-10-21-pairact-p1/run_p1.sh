#!/usr/bin/env bash
# pairact P1: MJWarp teacher gate tournament on gcp6 (r13 baseline + cand-1 + cand-3), same 40 worlds.
# Pre-registration: PAIRACT_P1_PREREG_DRAFT.json (must be committed as FROZEN before `run`).
#
#   bash run_p1.sh plan            # preflight + print commands (default)
#   bash run_p1.sh run             # run arms sequentially in the registered order
#   ARMS="c1" bash run_p1.sh run   # subset (only for a crash restart; report it)
# Every arm writes to a NEW directory; existing results are never reused or overwritten.
set -uo pipefail
MODE="${1:-plan}"
PY="${PY:-/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python}"
SRC="${SRC:-/home/ugrp/ugrp-sim/src}"
REPO="${REPO:-/home/ugrp/ugrp-sim/ugrp}"            # git clone of this repo on gcp6 [확인 필요]
RUNNER="${RUNNER:-$SRC/beamact5-tools/run_warp_flow_teacher_gcp6.py}"
HERE="$(cd "$(dirname "$0")" && pwd)"
CASES0="${CASES0:-/home/ugrp/ugrp-sim/runs/beamact5/wide-start-8420000d-r4/wide-cases-r13.json}"
XML="${XML:-/home/ugrp/ugrp-sim/runs/beamact5/wide-export-old-8420000e/canonical-scene.xml}"
REFS="${REFS:-/home/ugrp/ugrp-sim/runs/beamact5/native-refs-8420000e/per-world-references.json}"
REJ="${REJ:-/home/ugrp/ugrp-sim/runs/beamact5/gate-40-r13/rejection_table.json}"
INDICES="${INDICES:-0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_ROOT="${OUT_ROOT:-/home/ugrp/ugrp-sim/runs/pairact-p1/tournament-$TS}"
ARMS="${ARMS:-r13 c1 c3}"   # registered order

# arm | candidate | root | adapter | teacher   (root pins adapter+teacher; branches dsh/pairact-p1-cand-N{,-a,-r})
declare -A CAND=([r13]=beamact5_r13 [c1]=pairact_p1c1 [c3]=pairact_p1c3)
declare -A ROOT=([r13]=05046e9d245e46b4ee3d1c43308f7258a9fa41c5 [c1]=6360e972e22401c42ec316883f40e2c485f88005 [c3]=7f8bb3c5b950c3743da6aff7ee2ff1eead94c915)
declare -A ADPT=([r13]=d354468a303e1ebc961e58deedd35d05bed40098 [c1]=c25a616c9ebb1a46564b75a7be07a9db394e07b7 [c3]=9b4c29108705b157c4a73ab2be8c205ca0f22727)
declare -A TCHR=([r13]=fe6858eca7fa7b2ba6fb518c54f18a071995d5b4 [c1]=ee757b916335dd225723e742f76426bbf9018c21 [c3]=802a19a673bc481c86b8fea26156430ed3082d89)
# r13 used old directory names src/835ccef2.. (adapter) and src/26f84d0f.. (teacher) [확인 필요]; overridable.
R13_ADAPTER_DIR="${R13_ADAPTER_DIR:-$SRC/835ccef26aa84b08cc8f7e256fd0f43aa1583ef9}"
R13_TEACHER_DIR="${R13_TEACHER_DIR:-$SRC/26f84d0f0ada1c33473c83cca2d3415ce51bd247}"

dir_for() {  # arm kind -> directory
  local arm=$1 kind=$2
  if [ "$arm" = r13 ] && [ "$kind" = adapter ]; then echo "$R13_ADAPTER_DIR"; return; fi
  if [ "$arm" = r13 ] && [ "$kind" = teacher ]; then echo "$R13_TEACHER_DIR"; return; fi
  case $kind in root) echo "$SRC/${ROOT[$arm]}";; adapter) echo "$SRC/${ADPT[$arm]}";; teacher) echo "$SRC/${TCHR[$arm]}";; esac
}

prepare() {  # create detached worktrees for the new SHAs (never touches existing dirs)
  git -C "$REPO" fetch -q origin dsh/pairact-p1-cand-1 dsh/pairact-p1-cand-1-a dsh/pairact-p1-cand-1-r \
      dsh/pairact-p1-cand-3 dsh/pairact-p1-cand-3-a dsh/pairact-p1-cand-3-r || return 1
  for arm in c1 c3; do for sha in ${ROOT[$arm]} ${ADPT[$arm]} ${TCHR[$arm]}; do
    [ -d "$SRC/$sha" ] && continue
    echo "git -C $REPO worktree add --detach $SRC/$sha $sha"
    [ "$MODE" = run ] && git -C "$REPO" worktree add -q --detach "$SRC/$sha" "$sha"
  done; done
  return 0
}

preflight() {
  mkdir -p "$OUT_ROOT"; local f="$OUT_ROOT/preflight.txt"
  {
    echo "utc=$(date -u +%FT%TZ) host=$(hostname)"
    for p in "$PY" "$RUNNER" "$CASES0" "$XML" "$REFS" "$REJ"; do [ -e "$p" ] && echo "ok $p" || echo "MISSING $p"; done
    for arm in $ARMS; do for kind in root adapter teacher; do
      d=$(dir_for $arm $kind); h=$(git -C "$d" rev-parse HEAD 2>/dev/null || echo no-git)
      want=$(case $kind in root) echo ${ROOT[$arm]};; adapter) echo ${ADPT[$arm]};; teacher) echo ${TCHR[$arm]};; esac)
      [ "$h" = "$want" ] && s=ok || s=MISMATCH
      [ -d "$d" ] || s=MISSING
      echo "$s arm=$arm $kind dir=$d HEAD=$h want=$want dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l)"
    done; done
    sha256sum "$CASES0" "$XML" "$REFS" "$REJ" "$RUNNER" 2>/dev/null
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
  } | tee "$f"
  # r13 dirs carry old names; a HEAD mismatch there is reported, not fatal, when MISMATCH only on r13 [확인 필요]
  if grep -E '^(MISSING|MISMATCH)' "$f" | grep -v 'arm=r13' | grep -q .; then echo "PREFLIGHT FAIL" >&2; return 1; fi
  grep -q '^MISSING' "$f" && { echo "PREFLIGHT FAIL" >&2; return 1; }
  return 0
}

arm_run() {
  local arm=$1 out="$OUT_ROOT/$1" cases="$OUT_ROOT/cases-$1.json"
  if [ "$MODE" = run ]; then
    "$PY" "$HERE/make_arm_cases.py" "$CASES0" "$cases" "${CAND[$arm]}" | tee -a "$OUT_ROOT/cases.jsonl" || return 1
  fi
  local root; root=$(dir_for $arm root)
  local cmd=("$PY" "$RUNNER" --flow beampair --adapter-source "$(dir_for $arm adapter)" --teacher-source "$(dir_for $arm teacher)"
    --cases "$cases" --indices "$INDICES" --cap-s 60 --out "$out" --vm-hourly-usd 1.096
    --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1
    --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1
    --canonical-xml "$XML" --per-world-model-references-v1 "$REFS" --rejection-table "$REJ" --batch-per-world-speed-v1)
  echo "[$arm] cd $root && WARP_SOURCE_ROOT=$root ${cmd[*]}"
  [ "$MODE" = run ] || return 0
  local t0; t0=$(date +%s)
  ( cd "$root" && env WARP_SOURCE_ROOT="$root" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa timeout 7200 "${cmd[@]}" ) > "$OUT_ROOT/$arm.log" 2>&1
  local rc=$?
  echo "$arm candidate=${CAND[$arm]} rc=$rc wall_s=$(( $(date +%s)-t0 ))" | tee -a "$OUT_ROOT/arms.tsv"
  sleep 5
}

prepare || { echo "prepare failed (fetch)"; [ "$MODE" = run ] && exit 2; }
preflight || { [ "$MODE" = run ] && exit 2; }
for arm in $ARMS; do arm_run "$arm"; done
[ "$MODE" = run ] && "$PY" - "$OUT_ROOT" $ARMS <<'PYEOF'
import json, sys, hashlib, pathlib
root = pathlib.Path(sys.argv[1]); rows = []
for arm in sys.argv[2:]:
    s = root/arm/'summary.json'
    if not s.exists():
        rows.append(dict(arm=arm, status='NO_SUMMARY')); continue
    d = json.loads(s.read_text())
    rows.append(dict(arm=arm, success_n=d.get('success_n'), completed_N=d.get('completed_N'), planned_N=d.get('planned_N'),
                     cap_end=d.get('cap_end'), HOST_ERROR=d.get('HOST_ERROR'), summary_sha256=hashlib.sha256(s.read_bytes()).hexdigest()))
(root/'tournament-raw.json').write_text(json.dumps(rows, indent=1)); print(json.dumps(rows, indent=1))
PYEOF
exit 0
