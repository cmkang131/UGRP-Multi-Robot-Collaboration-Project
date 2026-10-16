"""Version bisection only; untouched XML, tape and existing C virtualenv."""
from pathlib import Path
import subprocess,os,json
p=Path('/home/ugrp/ugrp-sim/runs/simalt4');old=p.parent/'simalt3'
subprocess.run([str(old/'c-env/bin/python'),'-m','pip','install','--no-deps','--target',str(p/'mujoco313'),'mujoco==3.13.0'],check=True)
probe=p/'scripts/simalt_step_probe.py'
cmd=[str(old/'c-env/bin/python'),str(probe),'--enabled','--fixture',str(old/'fixture'),'--out',str(p/'c313-grip'),'--engine','cpu','--case','grip','--sha','e2c2a4c4','--capacity-reference',str(old/'cpu-n1/result.json')]
(p/'c313-command.json').write_text(json.dumps(cmd,indent=2)+'\n')
subprocess.run(cmd,check=True,env={**os.environ,'PYTHONPATH':str(p/'mujoco313'),'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'})
