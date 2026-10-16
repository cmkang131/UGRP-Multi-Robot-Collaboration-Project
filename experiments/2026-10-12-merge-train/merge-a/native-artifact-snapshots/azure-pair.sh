#!/usr/bin/env bash
# E2E17: run ON the admitted VM3 (pair) or VM4 (broad), after prior owner exits.
# No VM allocation, source deployment, secret transfer or relay startup is performed here.
# Mac relay: /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.s4_proxy_relay --output <OWN_OUTPUT>/relay --seconds 28800 --idempotent --listen-port 18424 --remote-port 18393 --driver-profile study_gemma4_31b_v1 --upstream openrouter_v1 --gemma-state <OWN_OUTPUT>/upstream
# Mac tunnel: ssh -T -n -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -R 127.0.0.1:18393:127.0.0.1:18424 <COORDINATOR_VM> 'sleep 28800'
# Manage both Mac commands with scripts/ugrp_session.py; copy only relay/identity.json to $B/relays/e2e-idle/a.json.
# Use the new committed relay source: e2e-idle-[ab]-s61001..61003 is its admitted namespace.
# Initial health at wall 180..300 s EACH: no exception, increasing frames/SIM, actual movement (evaluation-only),
# normal forward commands (not repeated turns/hold), mapping entered. Stop only bad run, preserve EXIT, then repair.
# Save each check in run-summary.json. remote_run_finish hashes; coordinator verifies ARM archive separately.
# Retrieve only fetch-lite to Mac. Heavy DEV raw is pruned only at this PR merge/close with cleanup-records.
set -euo pipefail
SHA=${1:?source SHA required}; PR=${2:?PR number required}
ACTION=${3:?--plan or --execute required}
[[ "$ACTION" = --execute || "$ACTION" = --plan ]]
MODE=${4:-pair}
case "$MODE" in
  pair) VM=ugrp-sim-azure3; SEEDS=(61001 61002 61003); COHORT_ARMS=(a b);;
  broad) VM=ugrp-sim-azure4; SEEDS=(61004 61005 61006 61007 61008 61009); COHORT_ARMS=(a);;
  *) echo 'mode must be pair or broad' >&2; exit 2;;
esac
if [ "$ACTION" = --plan ]; then
  for seed in "${SEEDS[@]}"; do
    for group in "${COHORT_ARMS[@]}"; do printf "%s %s %s\n" "$VM" "$group" "$seed"; done
  done
  exit 0
fi
test "$(( ${#SEEDS[@]} * ${#COHORT_ARMS[@]} ))" = 6
test "$(hostname -s)" = "$VM"
test "$PR" = 453
B=$HOME/ugrp-sim; S=$B/src/$SHA
cd "$S"
test "$(git rev-parse HEAD)" = "$SHA"
test -z "$(git status --porcelain)"
python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit
# Coordinator supplies fresh storage_budget.py receipts after reserving OTHER active jobs' future writes.
# x86: --host x86 --path ~/ugrp-sim/runs --runs 6 --per-run-mb 4096 --reserved-mb <remaining>
# ARM: --host arm --ssh oracle --path ~/ugrp-archive/runs --runs 6 --per-run-mb 4096 --reserved-mb <remaining>
# Mac: --host mac --runs 6 --per-run-mb 64 --reserved-mb <remaining>
# Floors after this batch: x86 8 GiB, ARM 25 GiB, Mac 20 GiB; use current primary storage_budget.py on Mac.
python3 - "$B" "$MODE" <<'PYTHON'
import json,sys,time,os,shutil
from pathlib import Path
b=Path(sys.argv[1])
for host in ('x86','arm','mac'):
 p=b/f'e2e-idle-{sys.argv[2]}-budget-{host}.json'
 assert time.time()-p.stat().st_mtime < 300 and json.loads(p.read_text())['ok']
assert shutil.disk_usage(b).free >= (8+6*4)*2**30
assert float(Path('/proc/uptime').read_text().split()[0])+25860 < 28800
assert os.getpriority(os.PRIO_PROCESS,0)==0
PYTHON
# Check receipt identity URL AND expiration against the full 7-hour run, before all six starts.
.venv-sim/bin/python - "$B" <<'PYTHON'
import json,sys,time
from pathlib import Path
from urllib.request import urlopen
from harness.s4_live_transport import validate_receipt
from scripts.run_e2e_ownmap_live import relay_url
url=relay_url('study_gemma4_31b_v1')
a=json.loads((Path(sys.argv[1])/'relays/e2e-idle/a.json').read_text())
with urlopen(url.replace('/v1/chat/completions','/identity'),timeout=10) as r:b=json.load(r)
assert a==b and b['single_model'] and b['upstream']=='openrouter_v1'
validate_receipt(a,now=time.time()+25300,remote_url=url)
PYTHON
export MUJOCO_GL=osmesa OMP_NUM_THREADS=1 LP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# Publish the native libraries before any of the simultaneous children loads them.
.venv-sim/bin/python -c 'from scripts.run_e2e_azure_batch import prepare_native; prepare_native()'
COMMON=(--expected-source-sha "$SHA" --driver-profile study_gemma4_31b_v1 --relay-receipt "$B/relays/e2e-idle/a.json" --e2e-live --event-driven-llm --compact-prompt --setdown-only-when-relook on_v1 --decider off --exploration-progress frontier_progress_v1 --pose-fix innovation --path-follow rpp_v1 --dev-light --stall-bundle --mapping-budget case_cap_v1 --wall-cap-s 25200 --stall-recovery off --stall-noise off --boundary-views candidate_views_v1 --b-marker-detect contrast_v1 --stall-odometry rgb_vo_us_v1 --ultrasonic-front on_v1 --vo-floor-mask homography_v1 --vo-rotation-policy no_ransac_v1)
for seed in "${SEEDS[@]}"; do
  for group in "${COHORT_ARMS[@]}"; do
    # Admission is checked for every child; wait if memory/load cannot admit it.
    python3 - <<'PYTHON'
import os,time
from pathlib import Path
# The process tree has one actual runner per cell; wrappers are not counted.
active=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  argv=(p/'cmdline').read_bytes().split(b'\0')
  if b'scripts.run_e2e_ownmap_live' in argv and b'--execute' in argv:active.append(p.name)
 except (OSError,ProcessLookupError):pass
assert len(active)<6, f'VM_SIX_RUN_CAP: {active}'
while True:
 mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
 if mem>=6*2**30 and os.getloadavg()[0]<51:break
 time.sleep(15)
PYTHON
    # Also recheck the finite VM lifetime after any admission wait.
    python3 -c "from pathlib import Path; assert float(Path('/proc/uptime').read_text().split()[0])+25860 < 28800"
    NAME=e2e-idle-$group-s$seed; R=$B/runs/$NAME
    test ! -e "$R"; mkdir "$R"; touch "$B/leases/$NAME"; uptime > "$R/LOADAVG"
    if [ "$group" = a ]; then
      WF=e2e-explore-deadlock-v208; X=(--explore-deadlock replan_v1)
    else
      WF=e2e-vomask-turn-v207; X=(--explore-deadlock off)
    fi
    python3 - "$R" "$SHA" "$PR" "$group" "$seed" "$MODE" "$VM" <<'PYTHON'
import json,sys,time,os
from pathlib import Path
r,sha,pr,group,seed,mode,vm=sys.argv[1:]
(Path(r)/'RUN_META.json').write_text(json.dumps(dict(class_='dev',pr=int(pr),branch='codex/e2e-idle',sha=sha,batch='e2e17-'+mode,group=group,seed=int(seed),cohort=mode,vm=vm,submitted_unix=time.time(),wall_cap_s=25200,storage_budget_bytes=4*2**30)).replace('"class_"','"class"')+'\n')
(Path(r)/'SOURCE_SHA').write_text(sha+'\n')
(Path(r)/'resource-admission.json').write_text(json.dumps(dict(loadavg=os.getloadavg(),mem_available_kib=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))))+'\n')
PYTHON
    setsid nohup python3 /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py --source "$S" --run "$R" -- .venv-sim/bin/python -m scripts.sim_cli workflow run "$WF" --timeout 25200 -- "${COMMON[@]}" --seed "$seed" --output "$R/raw" "${X[@]}" --execute </dev/null >"$R/launch.log" 2>&1 &
  done
 done
# Coordinator must observe EACH run within wall 180..300s of its own start (also while admission waits).
# Keep per-run process handles: stop only a failing run, write EXIT, repair and resubmit.
# Keep run names unique; broad is candidate-only and is not a paired comparison.
