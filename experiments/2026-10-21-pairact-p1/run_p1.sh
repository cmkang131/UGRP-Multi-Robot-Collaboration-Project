#!/usr/bin/env bash
# pairact P1: MJWarp teacher gate tournament on gcp6 (r13 + cand-1 + cand-2b + cand-3), same 40 worlds,
# then confirmation (winner + r13) on 40 new worlds (seed 9420000).
# Pre-registration: PAIRACT_P1_PREREG_DRAFT.json. `run`/`confirm` refuse unless status=FROZEN and the
# static exclusion list of that stage is recorded (p1_gate.py check_frozen).
#
#   bash run_p1.sh plan                  # fetch/worktree commands + preflight + tournament commands (default)
#   bash run_p1.sh static                # rule-A static check on the tournament cases (CPU, seconds)
#   bash run_p1.sh run                   # tournament, registered order r13 c1 c2b c3
#   ARMS="c2b" bash run_p1.sh run        # subset (only for a crash restart; report it)
#   CONF_CASES0=... bash run_p1.sh static-confirm        # rule-A static check on the new worlds
#   WINNER=c1 CONF_CASES0=... CONF_XML=... CONF_REFS=... CONF_REJ=... bash run_p1.sh confirm   # r13 + winner
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
PREREG="${PREREG:-$HERE/PAIRACT_P1_PREREG_DRAFT.json}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE=tournament; STATIC_CASES="$CASES0"
case $MODE in
  confirm|static-confirm)
    STAGE=confirmation
    CASES0="${CONF_CASES0:?CONF_CASES0 required [확인 필요: 새 world cases]}"; STATIC_CASES="$CASES0"
    XML="${CONF_XML:-MISSING-CONF_XML}"; REFS="${CONF_REFS:-MISSING-CONF_REFS}"; REJ="${CONF_REJ:-MISSING-CONF_REJ}"
    ;;
esac
if [ "$MODE" = confirm ]; then
  case "${WINNER:-}" in c1|c2b|c3) ;; *) echo "WINNER must be c1|c2b|c3" >&2; exit 2;; esac
  ARMS="${ARMS:-r13 $WINNER}"
  OUT_ROOT="${OUT_ROOT:-/home/ugrp/ugrp-sim/runs/pairact-p1/confirmation-$TS}"
else
  ARMS="${ARMS:-r13 c1 c2b c3}"   # registered order
  OUT_ROOT="${OUT_ROOT:-/home/ugrp/ugrp-sim/runs/pairact-p1/tournament-$TS}"
fi
EXEC=0; { [ "$MODE" = run ] || [ "$MODE" = confirm ]; } && EXEC=1

# arm | candidate | root | adapter | teacher   (root pins adapter+teacher; branches dsh/pairact-p1-cand-N{,-a,-r})
declare -A CAND=([r13]=beamact5_r13 [c1]=pairact_p1c1 [c2b]=pairact_p1c2b [c3]=pairact_p1c3)
declare -A ROOT=([r13]=05046e9d245e46b4ee3d1c43308f7258a9fa41c5 [c1]=6360e972e22401c42ec316883f40e2c485f88005 [c2b]=f2fd635d0020b69b50d09e9878c3924d47c76291 [c3]=7f8bb3c5b950c3743da6aff7ee2ff1eead94c915)
declare -A ADPT=([r13]=d354468a303e1ebc961e58deedd35d05bed40098 [c1]=c25a616c9ebb1a46564b75a7be07a9db394e07b7 [c2b]=63c3b697817b40aab27412917e160e755bd07b78 [c3]=9b4c29108705b157c4a73ab2be8c205ca0f22727)
declare -A TCHR=([r13]=fe6858eca7fa7b2ba6fb518c54f18a071995d5b4 [c1]=ee757b916335dd225723e742f76426bbf9018c21 [c2b]=42fc4eecb6daeef932393235d5d6bf5192f87c66 [c3]=802a19a673bc481c86b8fea26156430ed3082d89)
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
  local b refs=()
  for b in 1 2b 3; do refs+=(dsh/pairact-p1-cand-$b dsh/pairact-p1-cand-$b-a dsh/pairact-p1-cand-$b-r); done
  git -C "$REPO" fetch -q origin "${refs[@]}" || return 1
  for arm in c1 c2b c3; do for sha in ${ROOT[$arm]} ${ADPT[$arm]} ${TCHR[$arm]}; do
    [ -d "$SRC/$sha" ] && continue
    echo "git -C $REPO worktree add --detach $SRC/$sha $sha"
    [ $EXEC = 1 ] && git -C "$REPO" worktree add -q --detach "$SRC/$sha" "$sha"
  done; done
  return 0
}

preflight() {
  mkdir -p "$OUT_ROOT"; local f="$OUT_ROOT/preflight.txt"
  {
    echo "utc=$(date -u +%FT%TZ) host=$(hostname)"
    echo "mode=$MODE stage=$STAGE prereg=$PREREG prereg_sha256=$(sha256sum "$PREREG" | cut -d' ' -f1) status=$(grep -o '"status": "[A-Z_]*"' "$PREREG" | head -1)"
    echo "repo_head=$(git -C "$HERE/../.." rev-parse HEAD 2>/dev/null || echo copied-files) indices=${INDICES:-unset}"
    for p in "$PY" "$RUNNER" "$CASES0" "$XML" "$REFS" "$REJ" "$PREREG"; do [ -e "$p" ] && echo "ok $p" || echo "MISSING $p"; done
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
  if [ $EXEC = 1 ]; then
    "$PY" "$HERE/make_arm_cases.py" "$CASES0" "$cases" "${CAND[$arm]}" | tee -a "$OUT_ROOT/cases.jsonl" || return 1
  fi
  local root; root=$(dir_for $arm root)
  local cmd=("$PY" "$RUNNER" --flow beampair --adapter-source "$(dir_for $arm adapter)" --teacher-source "$(dir_for $arm teacher)"
    --cases "$cases" --indices "$INDICES" --cap-s 60 --out "$out" --vm-hourly-usd 1.096
    --gcp6-isolated-v1 --placement-graspable-filter-v1 --world-model-parameters-v1
    --native-sleep-policy-compat-v1 --full-active-dof-workspace-v1 --warp-native-contact-v1
    --canonical-xml "$XML" --per-world-model-references-v1 "$REFS" --rejection-table "$REJ" --batch-per-world-speed-v1)
  echo "[$arm] cd $root && WARP_SOURCE_ROOT=$root ${cmd[*]}"
  [ $EXEC = 1 ] || return 0
  local t0; t0=$(date +%s)
  ( cd "$root" && env WARP_SOURCE_ROOT="$root" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MUJOCO_GL=osmesa timeout 7200 "${cmd[@]}" ) > "$OUT_ROOT/$arm.log" 2>&1
  local rc=$?
  echo "$arm candidate=${CAND[$arm]} rc=$rc wall_s=$(( $(date +%s)-t0 ))" | tee -a "$OUT_ROOT/arms.tsv"
  sleep 5
}

static_check() {  # rule A (D2): flagged['overlap'] of static_stance_check.py; computes only, never excludes by itself
  local out="/home/ugrp/ugrp-sim/runs/pairact-p1/static-$STAGE-$TS.json"
  local t; t=$(dir_for r13 teacher); local scen; scen="$(dir_for r13 adapter)/experiments/2026-10-15-beampair1/scenario-v7.json"
  local chk="${STATIC_CHECK:-$HERE/static_stance_check.py}"
  echo "git -C $t rev-parse HEAD -> $(git -C "$t" rev-parse HEAD 2>/dev/null || echo no-git) (want ${TCHR[r13]})"
  ( cd "$t" && "$PY" "$chk" --cases "$STATIC_CASES" --scenario "$scen" --teacher-root "$t" --out "$out" ) || return 1
  sha256sum "$out" "$STATIC_CASES"
  "$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print('RULE_A excluded_worlds =',d['flagged']['overlap'])" "$out"
  echo "-> PAIRACT_P1_PREREG_DRAFT.json static_exclusion.$STAGE 에 excluded_worlds/output_path/output_sha256/cases_sha256 기입 후 커밋"
}

case $MODE in
  static|static-confirm) static_check; exit $?;;
  plan|run|confirm) ;;
  *) echo "mode: plan | static | run | static-confirm | confirm" >&2; exit 2;;
esac
if [ $EXEC = 1 ]; then
  INDICES="$("$PY" "$HERE/p1_gate.py" indices "$PREREG" "$STAGE")" || exit 2   # refuses unless FROZEN + list recorded
else
  INDICES="$(python3 "$HERE/p1_gate.py" indices "$PREREG" "$STAGE" 2>/dev/null || echo "<prereg not FROZEN: indices from p1_gate.py at run time>")"
fi
prepare || { echo "prepare failed (fetch)"; [ $EXEC = 1 ] && exit 2; }
preflight || { [ $EXEC = 1 ] && exit 2; }
for arm in $ARMS; do arm_run "$arm"; done
[ $EXEC = 1 ] && "$PY" "$HERE/p1_gate.py" verdict "$PREREG" "$STAGE" "$OUT_ROOT" $ARMS
exit 0
