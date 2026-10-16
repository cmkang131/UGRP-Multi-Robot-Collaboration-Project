"""One-shot Mac-side backup: at DEADLINE deallocate only allowlisted bench VMs (sub 88b7ee7f)."""
import json, subprocess, sys, time, datetime
S='88b7ee7f-f2f3-4a0d-a0ce-cf7306943676'; RG='UGRP-SIM-RG'
ALLOW=('ugrp-vmbench-d16v5','ugrp-vmbench-d16v6','ugrp-vmbench-f16v6')
deadline=datetime.datetime.fromisoformat(sys.argv[1]).timestamp()
while time.time()<deadline: time.sleep(30)
for vm in ALLOW:
    r=subprocess.run(['az','vm','deallocate','-g',RG,'-n',vm,'--subscription',S,'--no-wait'],capture_output=True,text=True)
    print(json.dumps(dict(vm=vm,rc=r.returncode,err=r.stderr[-300:],unix=time.time())),flush=True)
