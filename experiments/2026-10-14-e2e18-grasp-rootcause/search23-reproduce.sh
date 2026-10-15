#!/bin/sh
# Tested execution source: 0205485e4ef95b836bc87630a4ab94bde9b1db4b
# NOT EXECUTED. Three-submission allowance exhausted; this queue is BLOCKED.
# Before a separately authorized rerun: restore/verify the required 8h guard,
# budget-stop, idle guard, global <=40, reserve six slots, and match queue source hashes.
set -eu
RUN_NAME=${1:-grasp-search23-reproduction-$(date -u +%Y%m%dT%H%M%SZ)}
export UGRP_RESULTS_ROOT=/Users/changmin/projects/ugrp-wt/e2e18-rootcause
cd "$UGRP_RESULTS_ROOT"
python3 - <<'PYHASH'
import hashlib,json
from pathlib import Path
q=json.loads(Path('experiments/2026-10-14-e2e18-grasp-rootcause/search23-queue.json').read_text())
for p,h in q['source_hashes'].items():
    if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h:raise SystemExit('source hash mismatch: '+p)
PYHASH
/opt/anaconda3/bin/python3 scripts/remote_run.py --host gcp1 --detach --class dev --pr 484 --per-run-mb 1536 /Users/changmin/projects/ugrp-wt/e2e18-rootcause "$RUN_NAME" -- .venv-sim/bin/python -m scripts.run_grasp_act_batch --root "../../runs/$RUN_NAME" --plan experiments/2026-10-14-e2e18-grasp-rootcause/teacher-search23-short6-plan.json --concurrency 6 --cap-s 60 --execution-host gcp1 --speed-gate-limit 6.0 --diagnostic-only --teacher-profile visible_only --teacher-stability align_relook_v1 --teacher-search search_body_scan_v2 --approach-goal-set approach_goal_set_v1 --nominal-blocked-handoff nominal_blocked_handoff_v1 --approach-progress approach_progress_v1 --approach-recovery progress_view_recovery_v3 --approach-coordination off --handoff-observation visible_handoff_v1 --failure-stop-scope repeated_cause_v1 --peer-reobserve peer_reobserve_v1 --obstacle-reobserve obstacle_reobserve_v1 --pregrasp-sampling pregrasp_sampling_v1 --search17-candidates search17_candidates_v1 --search17-escape search17_escape_v1 --search17-odometry search17_fixed_v1 --search18-footprint off --search18-start-plan search18_start_plan_v1 --search18-free-space search18_free_space_v1 --search19-motion search19_motion_v1 --search19-footprint search19_footprint_v1 --search20 search20_v1 --search21 search21_v1 --search22 search22_v1 --search23 search23_v1
