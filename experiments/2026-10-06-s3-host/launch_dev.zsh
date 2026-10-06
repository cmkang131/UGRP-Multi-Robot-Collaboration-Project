#!/bin/zsh
# Preparation only: do not launch while PR #393 owns the simulation reservation.
setopt NO_BG_NICE
set -eu
s3_root=${0:A:h:h:h}
cd "$s3_root"
s3_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
s3_sha=${1:?full committed and pushed source SHA required}
s3_out=${2:?new absolute directory under primary outputs required}
[[ ${3:-} == --release-s3-simulation ]] || { print -u2 'S3 reserved for PR #393; coordinator release required'; exit 2; }
[[ $(git rev-parse HEAD) == "$s3_sha" ]]
[[ $(git rev-parse origin/codex/s3-three-robot-host) == "$s3_sha" ]]
[[ $(git branch --show-current) == codex/s3-three-robot-host ]]
[[ -z $(git status --porcelain) ]]
[[ ! -e "$s3_out" && "$s3_out" == /Users/changmin/projects/ugrp/outputs/* ]]
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
[[ $("$s3_py" scripts/agent_lock.py status) == null ]]
"$s3_py" scripts/agent_lock.py acquire --owner codex --branch codex/s3-three-robot-host \
  --purpose 'S3 DEV seeds 601 602 603' --pid $$ --expected-minutes 570
s3_pid=''
cleanup() {
  if [[ -n "$s3_pid" ]] && kill -0 "$s3_pid" 2>/dev/null; then
    kill -TERM "$s3_pid" 2>/dev/null || true
    wait "$s3_pid" 2>/dev/null || true
  fi
  "$s3_py" scripts/agent_lock.py release --owner codex
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$s3_out"
typeset -A s3_causes
s3_rc=0
for s3_seed in 601 602 603; do
  s3_case="$s3_out/s$s3_seed"
  "$s3_py" -m scripts.sim_cli workflow run zone-s3-host-v107 \
    --record "$s3_out/managed-s$s3_seed" --timeout 10800 -- \
    --execute --release-s3-simulation --expected-source-sha "$s3_sha" \
    --output "$s3_case" --seed "$s3_seed" --speedups v98-exact-v6 &
  s3_pid=$!
  s3_case_rc=0
  wait "$s3_pid" || s3_case_rc=$?
  s3_pid=''
  s3_cause=$("$s3_py" - "$s3_case" "$s3_seed" "$s3_case_rc" "$s3_out" <<'PY'
import json, pathlib, sys
case, seed, rc, out = pathlib.Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), pathlib.Path(sys.argv[4])
path = case/'result.json'
result = json.loads(path.read_text()) if path.exists() else {'status': 'HOST_ERROR', 'failure': {'class': 'MISSING_RESULT'}}
if result['status'] == 'DEV_DELIVERED' and rc == 0:
    cause = 'PASS'
elif result.get('controller_failures'):
    cause = '+'.join(sorted(set(result['controller_failures'].values())))
else:
    cause = result.get('failure', {}).get('class', result['status'])
with (out/'batch.jsonl').open('a') as f:
    f.write(json.dumps({'seed': seed, 'exit_code': rc, 'status': result['status'], 'cause': cause, 'output': str(case)})+'\n')
print(cause)
PY
)
  if [[ "$s3_cause" != PASS ]]; then
    s3_rc=1
    s3_causes[$s3_cause]=$(( ${s3_causes[$s3_cause]:-0} + 1 ))
    if (( ${s3_causes[$s3_cause]} >= 2 )); then
      print -r -- "STOP_RESEARCH_REQUIRED: repeated cause $s3_cause" | tee "$s3_out/stop-reason.txt"
      break
    fi
  fi
done
exit "$s3_rc"
