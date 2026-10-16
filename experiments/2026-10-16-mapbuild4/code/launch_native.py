import json,os,subprocess
from pathlib import Path
base=Path('/home/ugrp/ugrp-sim');ops=base/'ops-reviews/mapbuild4';sha=(base/'ops-reviews/mapbuild4-sha4').read_text().strip();src=base/('src/mapbuild4-'+sha[:9]);py=base/'ugrp/.venv-warp/bin/python';env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONUNBUFFERED':'1'}
basecmd=[str(py),str(src/'scripts/mapbuild4_pulse.py'),'--mapbuild4-pulse-v1','--contact-profile','warp_native_contact_v1','--renderer-source',str(base/'src/drivecheck-renderer-5974a181'),'--renderer-receipt',str(base/'ops-reviews/mapbuild3/renderer-receipt.json'),'--fixture',str(base/'runs/mapbuild3/prepare-r1b'),'--queue',str(ops/'queue-native-r3.json')]
allcmd=[];pids=[]
def launch(backend,phase):
 name=('native-phase-' if phase else 'native-pulse-')+backend+'-r3';cmd=basecmd+['--backend',backend,'--output',str(base/'runs/mapbuild4'/name)]
 if phase:
  cases=','.join(f'{pose}-left-{sign}-{ms}' for pose in ['drive','high'] for ms in [60,400] for sign in ['+1','-1'])
  cmd+=['--after-forward','--case-filter',cases]
 log=open(ops/(name+'.log'),'w');p=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL);allcmd.append(cmd);pids.append(p.pid);return p
# First only20 Warp worlds alongside the remaining8 baseline worlds.
p=launch('warp',False);p.wait()
if p.returncode:raise SystemExit(p.returncode)
# At most8 old+8 new Warp+20 CPU=36 worlds on this dedicated host.
w=launch('warp',True);c=launch('cpu',False);c.wait()
if c.returncode:raise SystemExit(c.returncode)
c=launch('cpu',True);c.wait();w.wait()
(ops/'native-launch.json').write_text(json.dumps(dict(commands=allcmd,pids=pids,status='COMPLETE' if c.returncode==w.returncode==0 else 'HOST_ERROR'),indent=2))
