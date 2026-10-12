#!/usr/bin/env bash
# Historical interface; ORACLE_HOST defaults to oracle. --host azure/azure2 is opt-in.
set -euo pipefail
exec python3 "$(dirname "$0")/remote_run.py" "$@"
