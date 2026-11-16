#!/bin/zsh
setopt NO_BG_NICE
set -eu
cd /Users/changmin/projects/ugrp-wt/s3-host
s3_py=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
[[ $(ps -o nice= -p $$ | tr -d ' ') == 0 ]]
"$s3_py" - <<'PY'
import os,json,pathlib,time
p=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s3run-20261009/launch-priority.json')
p.write_text(json.dumps(dict(pid=os.getpid(),parent_pid=os.getppid(),nice=os.getpriority(os.PRIO_PROCESS,0),method='finite launchctl submit; OS default priority; no nice or renice call',timestamp=time.time()),indent=2)+'\n')
PY
exec "$s3_py" scripts/ugrp_session.py run s3run-v146-3daa830f -- /bin/zsh \
 /Users/changmin/projects/ugrp/outputs/s3run-20261009/launch.zsh 3daa830f65f6ed72b94a95b376accc4949b7b7e6
