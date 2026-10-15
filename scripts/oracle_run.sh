#!/usr/bin/env bash
# Historical interface; configured default is gcp2. --host selects another host.
set -euo pipefail
exec python3 "$(dirname "$0")/remote_run.py" "$@"
