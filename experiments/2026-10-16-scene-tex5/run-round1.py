"""Finite remote orchestration; render only on gcp2, five independent arms."""
import datetime,json,os,platform,subprocess
from pathlib import Path
assert platform.node().startswith('ugrp-sim-gcp2')
base=Path('/home/ugrp/ugrp-sim'); source=base/'src/scenetex5-3b36eb9d'
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
lease=base/'leases/scenetex5.json'; info=json.loads(lease.read_text())
info.update(pid=os.getpid(),stage='round1 render',expected_end='2026-10-15T19:00:00Z');lease.write_text(json.dumps(info))
specs=[('v1-native','floor_light_textured_v1','native'),('v1-no_mip','floor_light_textured_v1','no_mip_v1')]+[(f'violet{v}',f'walls_floor_contrast_v5_violet{v}','no_mip_v1') for v in (150,175,195)]
raw=base/'runs'; processes=[]
queue={'task':'scenetex5','round':1,'source_sha':sha,'rejection_table':str(source/'experiments/2026-10-16-scene-tex5/before-change.json'),'own_concurrency':5,'host_limit':40,'raw_budget_mib':6144,'jobs':[]}
for name,material,quality in specs:
    output=raw/('scenetex5-r1-'+name)
    assert not output.exists()
    command=[str(base/'ugrp/.venv-sim/bin/python'),'-m','scripts.probe_scene_tex5','--execute','--source-sha',sha,'--materials',material,'--qualities',quality,'--output',str(output)]
    log=open(str(output)+'.log','w')
    proc=subprocess.Popen(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'MUJOCO_GL':'osmesa','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    queue['jobs'].append({'name':name,'output':str(output),'pid':proc.pid,'command':command});processes.append((proc,log,output))
(raw/'scenetex5-r1-queue.json').write_text(json.dumps(queue,indent=2))
for proc,log,output in processes:
    code=proc.wait();log.close()
    if output.exists():
        (output/'EXIT').write_text(str(code)+'\n')
        (output/'RUN_META.json').write_text(json.dumps({'class':'dev','pr':527,'branch':'claude/scene-tex2','sha':sha,'batch':'scenetex5-r1','keep':['summary.json','SHA256SUMS.json']}))
    print(output.name,code,flush=True)
info.update(stage='round1 raw complete; analysis pending',raw_complete=datetime.datetime.now(datetime.timezone.utc).isoformat());lease.write_text(json.dumps(info))
