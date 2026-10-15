"""Finite remote orchestration; render only on gcp2, five independent arms."""
import datetime,json,os,platform,subprocess
from pathlib import Path
assert platform.node().startswith('ugrp-sim-gcp2')
base=Path('/home/ugrp/ugrp-sim'); source=base/'src/scenetex5-3724052a'
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
lease=base/'leases/scenetex5.json'; info=json.loads(lease.read_text())
info.update(pid=os.getpid(),stage='round2 render',expected_end='2026-10-15T19:00:00Z');lease.write_text(json.dumps(info))
specs=[(n,'walls_floor_contrast_v5_'+n,'no_mip_v1') for n in ('indigo100','indigo85','indigo100_flat')]
raw=base/'runs'; processes=[]
queue={'task':'scenetex5','round':2,'source_sha':sha,'rejection_table':str(source/'experiments/2026-10-16-scene-tex5/round2-plan.json'),'own_concurrency':3,'host_limit':40,'raw_budget_mib':6144,'jobs':[]}
for name,material,quality in specs:
    output=raw/('scenetex5-r2-'+name)
    assert not output.exists()
    command=[str(base/'ugrp/.venv-sim/bin/python'),'-m','scripts.probe_scene_tex5','--execute','--source-sha',sha,'--materials',material,'--qualities',quality,'--output',str(output)]
    log=open(str(output)+'.log','w')
    proc=subprocess.Popen(command,cwd=source,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'MUJOCO_GL':'osmesa','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    queue['jobs'].append({'name':name,'output':str(output),'pid':proc.pid,'command':command});processes.append((proc,log,output))
(raw/'scenetex5-r2-queue.json').write_text(json.dumps(queue,indent=2))
for proc,log,output in processes:
    code=proc.wait();log.close()
    if output.exists():
        (output/'EXIT').write_text(str(code)+'\n')
        (output/'RUN_META.json').write_text(json.dumps({'class':'dev','pr':527,'branch':'claude/scene-tex2','sha':sha,'batch':'scenetex5-r1','keep':['summary.json','SHA256SUMS.json']}))
    print(output.name,code,flush=True)
info.update(stage='round2 raw complete; analysis pending',raw_complete=datetime.datetime.now(datetime.timezone.utc).isoformat());lease.write_text(json.dumps(info))

if all(json.loads((p/'summary.json').read_text())['status']=='MEASURED' for _,_,p in processes):
    cmd=[str(base/'ugrp/.venv-sim/bin/python'),'-m','scripts.score_scene_tex5','--inputs',str(raw/'scenetex5-r1-v1-native'),str(raw/'scenetex5-r1-v1-no_mip'),*[str(p) for _,_,p in processes],'--output',str(raw/'scenetex5-r2-analysis')]
    with open(raw/'scenetex5-r2-analysis.log','w') as log:
        code=subprocess.call(cmd,cwd=source,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    print('ANALYSIS_EXIT',code,flush=True)
