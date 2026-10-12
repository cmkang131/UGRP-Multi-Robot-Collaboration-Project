#!/usr/bin/env bash
# Coordinator-only example. Run ON the admitted Azure VM after its current jobs finish.
# No VM allocation, source deployment, secret transfer or relay startup is performed here.
# Mac relay: .venv Python -m scripts.s4_proxy_relay --output <OWN_OUTPUT>/relay --seconds 28800 --idempotent --listen-port 18416 --remote-port 18393 --driver-profile study_gemma4_31b_v1 --upstream openrouter_v1 --gemma-state <OWN_OUTPUT>/upstream
# Mac tunnel: ssh -T -n -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -R 127.0.0.1:18393:127.0.0.1:18416 <COORDINATOR_VM> 'sleep 28800'
# Manage both Mac commands with scripts/ugrp_session.py; copy only relay/identity.json to $B/relays/e2e-usstall/a.json.
# Use the new committed relay source: e2e-usstall-[ab]-s61001..61003 is its admitted namespace.
# Initial health at wall 180..300 s EACH: no exception, increasing frames/SIM, actual movement (evaluation-only),
# normal forward commands (not repeated turns/hold), mapping entered. Stop only bad run, preserve EXIT, then repair.
# Save each check in summary.json. On exit remote_run_finish evaluates/hashes/archives to ARM; verify it.
# Retrieve only fetch-lite to Mac. Heavy DEV raw is pruned only at this PR merge/close with cleanup-records.
set -euo pipefail
SHA=${1:?source SHA required}; PR=${2:?PR number required}
test "${3:-}" = --execute
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
python3 - "$B" <<'PYTHON'
import json,sys,time,os,shutil
from pathlib import Path
b=Path(sys.argv[1])
for host in ('x86','arm','mac'):
 p=b/f'e2e-usstall-budget-{host}.json'
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
a=json.loads((Path(sys.argv[1])/'relays/e2e-usstall/a.json').read_text())
with urlopen(url.replace('/v1/chat/completions','/identity'),timeout=10) as r:b=json.load(r)
assert a==b and b['single_model'] and b['upstream']=='openrouter_v1'
validate_receipt(a,now=time.time()+25300,remote_url=url)
PYTHON
export MUJOCO_GL=osmesa OMP_NUM_THREADS=1 LP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
COMMON=(--expected-source-sha "$SHA" --driver-profile study_gemma4_31b_v1 --relay-receipt "$B/relays/e2e-usstall/a.json" --e2e-live --event-driven-llm --compact-prompt --setdown-only-when-relook on_v1 --decider off --exploration-progress frontier_progress_v1 --pose-fix innovation --path-follow rpp_v1 --dev-light --stall-bundle --mapping-budget case_cap_v1 --wall-cap-s 25200 --stall-recovery off --stall-noise off --boundary-views candidate_views_v1 --b-marker-detect contrast_v1)
for seed in 61001 61002 61003; do
  for group in a b; do
    # Admission is checked for every new child; retry later if memory/load cannot admit the pair.
    python3 - <<'PYTHON'
import os
from pathlib import Path
mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert mem>=6*2**30 and os.getloadavg()[0]<51
PYTHON
    NAME=e2e-usstall-$group-s$seed; R=$B/runs/$NAME
    test ! -e "$R"; mkdir "$R"; touch "$B/leases/$NAME"; uptime > "$R/LOADAVG"
    if [ "$group" = a ]; then
      WF=e2e-usstall-v206; X=(--stall-odometry rgb_vo_us_v1 --ultrasonic-front on_v1)
    else
      WF=e2e-combo14-vo2-v205; X=(--stall-odometry rgb_vo_v2 --ultrasonic-front off)
    fi
    python3 - "$R" "$SHA" "$PR" "$group" "$seed" <<'PYTHON'
import json,sys
from pathlib import Path
r,sha,pr,group,seed=sys.argv[1:]
(Path(r)/'RUN_META.json').write_text(json.dumps(dict(class_='dev',pr=int(pr),branch='codex/e2e-usstall',sha=sha,batch='e2e-usstall',group=group,seed=int(seed),wall_cap_s=25200,storage_budget_bytes=4*2**30)).replace('"class_"','"class"')+'\n')
(Path(r)/'SOURCE_SHA').write_text(sha+'\n')
PYTHON
    setsid nohup python3 /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py --source "$S" --run "$R" -- .venv-sim/bin/python -m scripts.sim_cli workflow run "$WF" --timeout 25200 -- "${COMMON[@]}" --seed "$seed" --output "$R/raw" "${X[@]}" --execute </dev/null >"$R/launch.log" 2>&1 &
  done
 done
# Coordinator observes all six now, including initial health, bounded completion and immediate archival.
