"""Guest safety audit records existence/hash checks only, never credential contents."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def run(*cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


base = Path('/home/ugrp/ugrp-sim')
credentials = []
for home in ('/home/ugrp','/root'):
    for name in ('.config/gcloud/credentials.db','.config/gcloud/application_default_credentials.json',
                 '.codex','.claude','.kaggle/kaggle.json','.env','.ssh/id_ed25519','.ssh/id_rsa'):
        path = Path(home)/name
        if path.exists():
            credentials.append(str(path))
result = dict(python=platform.python_version(), platform=platform.platform(),
              idle_timer=run('systemctl','is-active','ugrp-idle-guard.timer'),
              idle_guard_sha256=hashlib.sha256(Path('/usr/local/sbin/ugrp-idle-guard').read_bytes()).hexdigest(),
              idle_guard=Path('/usr/local/sbin/ugrp-idle-guard').read_text(),
              leases=sorted(p.name for p in (base/'leases').iterdir()),
              execution_processes=run('ps','-u','ugrp','-o','pid,comm,args'),
              disk=run('df','-B1',str(base)), gpu=run('nvidia-smi'),
              known_credential_paths_present=credentials,
              ssh_files=sorted(p.name for p in Path('/home/ugrp/.ssh').iterdir()),
              cpu=run('lscpu'), os_release=Path('/etc/os-release').read_text(),
              shared_git_config=run('git','--git-dir='+str(base/'git-shared.git'),'config','--local','--list'))
Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n')
assert not credentials
assert result['idle_timer']['returncode']==0
