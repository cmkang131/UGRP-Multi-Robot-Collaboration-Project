"""gcp2 finite static batch; no model credentials, no VM lifecycle mutation."""
from pathlib import Path
import datetime,json,os,subprocess,sys
base=Path('/home/ugrp/ugrp-sim')
source=base/'src'/sys.argv[1]
round_name=sys.argv[2]
lease=base/'leases/scenetex4.json'
prior=json.loads(lease.read_text())
prior.update(pid=os.getpid(),phase=round_name,source_sha=sys.argv[1],expected_end='2026-10-15T20:30:00Z')
lease.write_text(json.dumps(prior,indent=2)+'\n')
processes=[]
for material in ('walls_floor_contrast_v4_dark','walls_floor_contrast_v4_light','walls_floor_contrast_v4_skirt'):
 for quality in ('native','no_mip_v1'):
  output=base/'runs'/(round_name+'-'+material.rsplit('_',1)[1]+'-'+quality)
  command=[str(base/'ugrp/.venv-sim/bin/python'),'-m','scripts.probe_scene_tex4','--execute','--source-sha',sys.argv[1],'--materials',material,'--qualities',quality,'--output',str(output)]
  env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
  log=open(str(output)+'.log','w')
  p=subprocess.Popen(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
  processes.append((p,output,log,command))
  print(json.dumps({'pid':p.pid,'output':str(output)}),flush=True)
rows=[]
for p,out,log,cmd in processes:
 code=p.wait();log.close()
 row={'pid':p.pid,'output':str(out),'exit':code,'command':cmd}
 rows.append(row)
 if out.exists():
  (out/'RUN_META.json').write_text(json.dumps({'class':'dev','pr':527,'branch':'claude/scene-tex2','sha':sys.argv[1],'batch':round_name},indent=2)+'\n')
 print(json.dumps(row),flush=True)
(base/'runs'/(round_name+'-batch.json')).write_text(json.dumps(rows,indent=2)+'\n')
prior.update(phase=round_name+' render complete; Mac owner analysing')
lease.write_text(json.dumps(prior,indent=2)+'\n')
sys.exit(any(r['exit'] for r in rows))
