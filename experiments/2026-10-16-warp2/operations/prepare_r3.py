"""Six exact C312 assets plus shared-model-array preflight on the existing L4."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time

r=Path('/home/ugrp/ugrp-sim');sha=sys.argv[1];source=r/'src'/('warp2-'+sha[:8])
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==sha, 'full source SHA mismatch'
out=r/'runs/warp2'/('r3-references-'+sha[:8]);out.mkdir(exist_ok=False)
lease=r/'leases/warp2-prepare.json';assert not lease.exists()
deadline=json.loads((r/'runs/warp2/allocation.json').read_text())['started_unix']+10800
write=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
write(lease,dict(task='warp2-prepare',pid=os.getpid(),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    expected_end=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).isoformat(),source=sha,node_budget=6))
env={**os.environ,'MUJOCO_GL':'osmesa','PYTHONPATH':str(source),'OMP_NUM_THREADS':'1',
    'OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
refs={};exports=[]
try:
    for i in range(6):
        target=out/f'export-{i}'
        cmd=[str(r/'runs/simalt3/c-env/bin/python'),str(source/'scripts/run_warp_flow_teacher.py'),
             '--physics-backend','c_pilot_v1','--export-compiled-only','--adapter-source',str(r/'src/warp2-08f12921'),
             '--teacher-source',str(r/'src/warp2-26f84d0f'),'--plan',
             str(r/'src/warp2-08f12921/experiments/2026-10-16-beampair6/short6-plan.json'),
             '--episode',str(i),'--out',str(target),'--vm-hourly-usd','1.096']
        with (out/f'export-{i}.log').open('w') as log:
            subprocess.run(cmd,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,
                timeout=max(1,deadline-time.time()),check=True)
        summary=json.loads((target/'summary.json').read_text())
        xml_sha=hashlib.sha256((target/'runtime-scene.xml').read_bytes()).hexdigest()
        refs[xml_sha]=dict(actuator=str(target/'compiled-312.json'),geometry=str(target/'compiled-geometry312.npz'))
        exports.append(dict(episode=i,status=summary['status'],xml_sha256=xml_sha,
            native_initialization_sim_s=summary.get('native_initialization_sim_s'),
            rollout_physics_steps=summary.get('rollout_physics_steps'),raw=str(target)))
    write(out/'model-references.json',refs)
    probe='''import sys,json,pathlib,hashlib
import mujoco,warp as wp,mujoco_warp as mjw
sys.path.insert(0,sys.argv[1]+'/scripts')
from warp_act_backend import WarpTransport
from simalt_compiled_compat import apply_reference,apply_geometry
from simalt_host import gcp2_identity
root=pathlib.Path(sys.argv[2]);refs=json.loads((root/'model-references.json').read_text());models=[]
for p in sorted(root.glob('export-*/runtime-scene.xml')):
 m=mujoco.MjModel.from_xml_path(str(p));a=refs[hashlib.sha256(p.read_bytes()).hexdigest()]
 apply_geometry(m,p,pathlib.Path(a['geometry']));apply_reference(m,p,pathlib.Path(a['actuator']));models.append(m)
wp.init();t=WarpTransport(gcp2_identity(),sys.argv[3],'mjwarp_batch_v1',root);t.wp=wp;t.mjw=mjw
batch,audit=t.combine_models(models);audit.update(rollout_physics_steps=0,scope='exact XML/compiled model conversion only; no GPU step or closed-loop teacher')
(root/'model-array-preflight.json').write_text(json.dumps(audit,indent=2)+'\\n')
print(json.dumps(audit,indent=2))
'''
    (out/'probe-code.py').write_text(probe)
    with (out/'preflight.log').open('w') as log:
        subprocess.run([str(r/'runs/simalt3/warp-env/bin/python'),str(out/'probe-code.py'),str(source),str(out),sha],
            cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=max(1,deadline-time.time()),check=True)
    write(out/'DONE.json',dict(source_sha=sha,exports=exports,model_N=len(refs),
        preflight=json.loads((out/'model-array-preflight.json').read_text()),
        hashes={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}))
except BaseException as error:
    write(out/'ERROR.json',dict(type=type(error).__name__,error=str(error),exports=exports))
    raise
finally:
    lease.unlink()
