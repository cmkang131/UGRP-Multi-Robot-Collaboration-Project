"""R3 native port self-control; no extra Warp candidate or parameter change."""
import json
import os
from pathlib import Path
import subprocess

R=Path('/home/ugrp/ugrp-sim/runs/simalt5');OLD=R.parent/'simalt3'
S=Path('/home/ugrp/ugrp-sim/src/3bd0e1f6')
sha=subprocess.check_output(['git','-C',str(S),'rev-parse','HEAD'],text=True).strip()
cmd=list(map(str,[OLD/'c-env/bin/python','-u',S/'scripts/simalt_step_probe.py',
    '--enabled','--fixture',OLD/'fixture','--out',R/'c312-native-port-selfcontrol',
    '--engine','cpu','--case','grip','--sha',sha,
    '--capacity-reference',R.parent/'simalt4/rev5/dense-capacity.json','--dense-capacity-v1',
    '--backend-mode','legacy-plane-v1','--record-own-rgb',OLD/'runtime/source']))
plan={'round':3,'purpose':'validate C port against its original C312 implementation',
      'rejection_table':str(R/'rejection-before-round3.json'),'command':cmd,'source_sha':sha}
assert Path(plan['rejection_table']).is_file()
(R/'round3-native-selfcontrol-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
with (R/'c312-native-port-selfcontrol.log').open('x') as log:
    subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'},check=True)
print(json.loads((R/'c312-native-port-selfcontrol/result.json').read_text())['status'])
