import json,subprocess,os
from pathlib import Path
base=Path('/home/ugrp/ugrp-sim');ops=base/'ops-reviews/mapbuild4';py=base/'ugrp/.venv-warp/bin/python';sha=(base/'ops-reviews/mapbuild4-sha2').read_text().strip();src=base/('src/mapbuild4-'+sha[:9])
rows=json.loads((base/'runs/mapbuild4/pulse-analysis-r1/matrix.json').read_text())
table=dict(raw=str(base/'runs/mapbuild4'),reproduction=str(base/'ops-reviews/mapbuild4-run.sh'),stages=[dict(stage=s,cumulative_pass_n=40,rejected_n=0) for s in ['requested','nonpenetrating','completed_physics','finite_measurements']],prediction_profile_distribution={x:sum(r['prediction_qualification']==x for r in rows) for x in set(r['prediction_qualification'] for r in rows)},note='not a physical success/accuracy acceptance gate; backend rows kept separate')
(base/'runs/mapbuild4/pulse-analysis-r1/rejection_table.json').write_text(json.dumps(table,indent=2))
q=json.loads((ops/'queue-phase-r2.json').read_text());q['rejection_table']=str(base/'runs/mapbuild4/pulse-analysis-r1/rejection_table.json');(ops/'queue-phase-r2.json').write_text(json.dumps(q,indent=2))
cases=','.join(f'{pose}-left-{sign}-{ms}' for pose in ['drive','high'] for ms in [60,400] for sign in ['+1','-1'])
commands=[];pids=[]
for backend in ['cpu','warp']:
 cmd=[str(py),str(src/'scripts/mapbuild4_pulse.py'),'--mapbuild4-pulse-v1','--backend',backend,'--after-forward','--case-filter',cases,'--renderer-source',str(base/'src/drivecheck-renderer-5974a181'),'--renderer-receipt',str(base/'ops-reviews/mapbuild3/renderer-receipt.json'),'--fixture',str(base/'runs/mapbuild3/prepare-r1b'),'--queue',str(ops/'queue-phase-r2.json'),'--output',str(base/f'runs/mapbuild4/phase-{backend}-r2')]
 if backend=='warp':cmd+=['--record']
 log=open(ops/f'phase-{backend}-r2.log','w');p=subprocess.Popen(cmd,env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONUNBUFFERED':'1'},stdout=log,stderr=subprocess.STDOUT,start_new_session=True,stdin=subprocess.DEVNULL)
 commands.append(cmd);pids.append(p.pid)
(ops/'phase-launch.json').write_text(json.dumps(dict(commands=commands,pids=pids),indent=2));print(pids)
lease=json.loads((base/'leases/mapbuild4.json').read_text());lease.update(pid=pids[1],cpu_pid=pids[0],render_pid=2343,concurrency=36);(base/'leases/mapbuild4.json').write_text(json.dumps(lease,indent=2))
