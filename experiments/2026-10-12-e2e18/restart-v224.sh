#!/usr/bin/env bash
# Coordinator-only E2E speed3 research restart; --plan is the default.
# Run on the already admitted VM3 after source deployment. This never starts a VM or relay.
# Supply current relay identity at ~/ugrp-sim/relays/e2e18/a.json.
# Fresh storage_budget receipts: ~/ugrp-sim/e2e18-r10-budget-{x86,arm,mac}.json.
# Reserve six * 2560 MiB on x86/ARM (2048 cohort + 512 preflight each), plus other jobs;
# Mac: six * 80 MiB (64 cohort + 16 preflight fetch-lite), plus other jobs.
# x86/ARM/Mac floors: 8/25/20 GiB. Preserve raw on persistent disk and archive to ARM.
# EACH run needs the coordinator's initial-health check at wall 180..300 seconds.
# Completion uses <run>/EXIT plus raw/result.json; supervisor process returncode is insufficient.
set -euo pipefail
SHA=${1:?source SHA required}; PR=${2:?draft PR number required}
VM=${3:?VM name required}; ACTION=${4:---plan}
case "$ACTION" in --plan|--execute);; *) echo '--plan or --execute required' >&2; exit 2;; esac
WF=e2e18-v224
case "$VM" in
ugrp-sim-azure3) SEEDS=(61004 61005);;
ugrp-sim-azure4) SEEDS=(61009 61010);;
*) echo 'Only VM3/VM4 permitted' >&2; exit 2;; esac
if [ "$ACTION" = --plan ]; then
  for seed in "${SEEDS[@]}"; do
    printf '%s %s adaptive_v1 %s e2e18-v224-s%s-r10\n' "$VM" "$WF" "$seed" "$seed"
  done
  exit 0
fi
GATE_ARGS=("${@:5}")
test "$(hostname -s)" = "$VM"
B=$HOME/ugrp-sim; S=$B/src/$SHA
cd "$S"
test "$(git rev-parse HEAD)" = "$SHA"
test -z "$(git status --porcelain)"
python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit
# Check explicit gate options, finite lease, all three budgets, load and memory before any probe.
.venv-sim/bin/python - "$B" "$PR" "${GATE_ARGS[@]}" <<'PYTHON'
import argparse,json,os,shutil,sys,time
from pathlib import Path
from scripts.azure_speed_gate import add_arguments
b=Path(sys.argv[1]);assert int(sys.argv[2])>0
p=argparse.ArgumentParser();add_arguments(p);a=p.parse_args(sys.argv[3:])
for host,minimum in (('x86',6*2560*2**20),('arm',6*2560*2**20),('mac',6*80*2**20)):
 path=b/f'e2e18-r10-budget-{host}.json';receipt=json.loads(path.read_text())
 assert 0 <= time.time()-path.stat().st_mtime < 300 and receipt['ok'], f'STALE_STORAGE_BUDGET:{host}'
 checks=[c for c in receipt['checks'] if c['host']==host]
 assert len(checks)==1 and checks[0]['expected_bytes']>=minimum and checks[0]['ok'], f'PROBE_PLUS_COHORT_BUDGET_REQUIRED:{host}'
assert shutil.disk_usage(b).free >= (8+6*2.5)*2**30
assert os.getpriority(os.PRIO_PROCESS,0)==0
required=18000+max(300.,30*a.speed_gate_limit*3)+6*45+600
assert float(Path('/proc/uptime').read_text().split()[0])+required < 28800, 'FINITE_VM_LIFETIME_REQUIRED'
mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert mem>=6*2**30 and os.getloadavg()[0]<51, 'RESOURCE_ADMISSION_FAILED'
active=[r for r in (b/'runs').glob('e2e18-v22[123]-*') if not (r/'EXIT').exists()]
assert len(active)==4, f'FOUR_CONTINUING_RUNS_REQUIRED:{len(active)}'
print('MATCHED_LOAD_GATE: 2 replacement previews + 4 continuing cohorts = 6 total',flush=True)
PYTHON
# A separate speed-gate namespace prevents preview requests being counted/reused as cohort calls.
.venv-sim/bin/python - "$B" "${GATE_ARGS[@]}" <<'PYTHON'
import argparse,json,sys,time
from pathlib import Path
from urllib.request import urlopen
from harness.s4_live_transport import validate_receipt
from scripts.run_e2e_ownmap_live import relay_url
from scripts.s4_proxy_relay import accepted_call_id
from scripts.azure_speed_gate import add_arguments
p=argparse.ArgumentParser();add_arguments(p);a=p.parse_args(sys.argv[2:])
url=relay_url('study_gemma4_31b_v1')
receipt=json.loads((Path(sys.argv[1])/'relays/e2e18/a.json').read_text())
with urlopen(url.replace('/v1/chat/completions','/identity'),timeout=10) as r:live=json.load(r)
assert receipt==live and live['single_model'] and live['upstream']=='openrouter_v1'
validate_receipt(receipt,now=time.time()+18000+max(300.,30*a.speed_gate_limit*3)+370,remote_url=url)
for seed in range(61001,61013):
 key=f'e2e18-v224-s{seed}-r10:call-0001-r1:1'
 assert accepted_call_id(key) and accepted_call_id('speed-gate-'+key), 'RELAY_R10_NAMESPACE_REQUIRED'
PYTHON
export MUJOCO_GL=osmesa OMP_NUM_THREADS=1 LP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
.venv-sim/bin/python -c 'from scripts.run_e2e_azure_batch import prepare_native; prepare_native()'
# Same common options as scripts/measure_e2e_speed3_batch.py at this source SHA,
# with external measurement flags removed and the finite cohort wall cap restored.
COMMON=(--expected-source-sha "$SHA" --driver-profile study_gemma4_31b_v1 --relay-receipt "$B/relays/e2e18/a.json" --e2e-live --event-driven-llm --compact-prompt --setdown-only-when-relook on_v1 --decider off --exploration-progress frontier_progress_v1 --pose-fix innovation --path-follow rpp_v1 --dev-light --mapping-budget case_cap_v1 --wall-cap-s 18000 --stall-recovery off --stall-noise off --boundary-views standoff_fullquad_v1 --b-marker-detect partial_known_size_v1 --b-partial-accept on_v1 --stall-odometry rgb_vo_us_v1 --ultrasonic-front on_v1 --vo-floor-mask homography_v1 --vo-rotation-policy no_ransac_v1 --explore-deadlock replan_v1 --boundary-association extent_v1 --boundary-retry navigation_v1 --boundary-coverage native_v1 --runtime-registration reviewed_v1 --execute)
GATE_ROOT=$B/runs/speed-gate-e2e18-$VM-r10-${SHA:0:12}
GATE_PLAN=$GATE_ROOT-plan.json
test ! -e "$GATE_ROOT"; test ! -e "$GATE_PLAN"
for seed in "${SEEDS[@]}"; do test ! -e "$B/runs/e2e18-v224-s$seed-r10"; done
mkdir -p "$B/leases"
for seed in "${SEEDS[@]}"; do
  NAME=e2e18-v224-s$seed-r10; R=$B/runs/$NAME
  mkdir "$R"; touch "$B/leases/$NAME"; uptime > "$R/LOADAVG"
  python3 - "$R" "$SHA" "$PR" "$seed" "$VM" <<'PYTHON'
import json,os,sys,time
from pathlib import Path
r,sha,pr,seed,vm=sys.argv[1:];r=Path(r)
meta={'class':'dev','pr':int(pr),'branch':'codex/e2e18','sha':sha,'batch':'e2e18-r10',
      'speed_gate_policy':'user_2026-10-12_fallback_3.0_after_four_probes','variant':'integrated_v1','seed':int(seed),'vm':vm,'submitted_unix':time.time(),
      'wall_cap_s':18000,'gate_new_samples':2,'ongoing_other_bundles':4,'total_planned_concurrency':6,'storage_budget_bytes':2*2**30,'execution_bundle_id':'e2e18-v224',
      'cohort':'new adaptive physics; no inherited outcomes'}
(r/'RUN_META.json').write_text(json.dumps(meta)+'\n');(r/'SOURCE_SHA').write_text(sha+'\n')
(r/'resource-admission.json').write_text(json.dumps(dict(loadavg=os.getloadavg(),
 mem_available_kib=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))))+'\n')
PYTHON
  .venv-sim/bin/python -m scripts.azure_speed_gate add --plan "$GATE_PLAN" --name "$NAME" --target "$R" -- .venv-sim/bin/python -m scripts.sim_cli workflow run "$WF" --timeout 18600 -- "${COMMON[@]}" --seed "$seed" --output "$R/raw" --speed3 adaptive_v1 --speed5 lean_v3 --observation-cadence on_v1 --route-guard dev_nominal_v1 --beam-axis undirected_v1 --route-coverage native_v1 --carrier-axes beam_v1 --carrier-approach standoff_v1 --speed4 '{"rbpf_particles":50,"floor_ray_stride":2,"vector_envelopes":true,"vector_door_pairs":true}'
 done
# Two replacement previews run beside four continuing v220 cohorts (six total).
# Initial full-six gate passed; replacement admission still requires median <=3.0.
# Five-hour cap preserves the existing finite relay lease without disrupting eight live cohorts.
.venv-sim/bin/python -m scripts.azure_speed_gate start --plan "$GATE_PLAN" --gate-root "$GATE_ROOT" "${GATE_ARGS[@]}"
