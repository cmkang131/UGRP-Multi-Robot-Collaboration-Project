#!/bin/bash
# Reproduction recipe only. This task submitted exactly three DEV rounds.
set -euo pipefail
if [[ "${1:-}" != --execute ]]; then
  echo 'PREPARED_NOT_EXECUTED: bash experiments/2026-10-15-reloc10/reproduce-rotation.sh --execute'
  exit 0
fi
RELOC10_ROOT="$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)"
[[ -z "$(git -C "$RELOC10_ROOT" status --porcelain)" ]] || { echo 'Clean source required'; exit 1; }
RELOC10_PROJECT=ugrp-act-train-1014
RELOC10_STATE="$(gcloud functions describe budget-stop --region us-central1 --project "$RELOC10_PROJECT" --format='value(state)')"
[[ "$RELOC10_STATE" == ACTIVE ]] || { echo 'budget-stop is not ACTIVE'; exit 1; }
RELOC10_EVENTS="$(gcloud logging read 'resource.labels.service_name="budget-stop" AND timestamp>="2026-10-15T00:00:00Z" AND (jsonPayload.costAmount>=1000 OR textPayload:"Stopping" OR textPayload:"STOPPING")' --project "$RELOC10_PROJECT" --limit 1 --format='value(timestamp)')"
[[ -z "$RELOC10_EVENTS" ]] || { echo 'Budget stop observed; do not submit'; exit 1; }
python3 "$RELOC10_ROOT/scripts/gcpctl.py" start gcp1
RELOC10_ACTIVE="$(ssh -o BatchMode=yes gcp1 "ps -eo args | grep -E '[p]ython.*-m scripts\\.(run_|sim_cli)' | wc -l")"
(( RELOC10_ACTIVE < 40 )) || { echo 'Global execution ceiling reached'; exit 1; }
RELOC10_SHA="$(git -C "$RELOC10_ROOT" rev-parse HEAD)"
RELOC10_RUN="reloc10-rotation-repro-${RELOC10_SHA:0:8}-$(date -u +%Y%m%dT%H%M%SZ)"
exec env UGRP_REMOTE_LOCAL_ROOT="$RELOC10_ROOT" LP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 "$RELOC10_ROOT/scripts/remote_run.py" --host gcp1 --class dev --pr 505 --per-run-mb 256 \
  "$RELOC10_ROOT" "$RELOC10_RUN" -- .venv-sim/bin/python -m scripts.run_reloc10_rotation_check \
  --plan experiments/2026-10-15-reloc10/diagnostic-plan.json --expected-source-sha "$RELOC10_SHA" \
  --execution-host gcp1 --out "/home/ugrp/ugrp-sim/runs/$RELOC10_RUN/raw" --execute
