"""Linux/L4-only noslip import-and-step gate; no option overrides or training.

A failed import, ignored noslip, NaN or overflow stops the probe before batch
expansion. The reference MjModel XML is loaded intact; a passing import/step
is not a physics-equivalence result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
import warnings

COMMIT='57b4692f4d3cdf4d27d916b4b8c4759ba36e9148'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xml',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--enabled',action='store_true')
    a=p.parse_args()
    if not a.enabled or platform.system()!='Linux':p.error('explicit Linux-only opt-in required')
    a.out.mkdir(parents=True,exist_ok=False)
    result={'engine':'mjwarp','commit':COMMIT,'attempted':1,'completed':0,'HOST_ERROR':0,
        'failure':0,'status':'running','xml_sha256':hashlib.sha256(a.xml.read_bytes()).hexdigest(),
        'training':False,'option_overrides':{},'stage':'C0 intact-scene compatibility gate',
        'rejection_table':str(a.out/'rejection_table.json')}
    start=time.perf_counter()
    def save():
        (a.out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    save()
    try:
        import socket
        if socket.gethostname().split('.')[0]!='ugrp-act-l4-pilot1':raise RuntimeError('wrong host')
        import numpy as np
        import mujoco
        import warp as wp
        import mujoco_warp as mjw
        warnings.filterwarnings("error", message=".*overflow.*", category=RuntimeWarning)
        wp.init()
        result.update(mujoco_version=mujoco.__version__,warp_version=wp.__version__)
        m=mujoco.MjModel.from_xml_path(str(a.xml))
        result['model']={k:int(getattr(m,k)) for k in ('nq','nv','nu','ngeom','nbody','neq')}
        result['options']={k:float(getattr(m.opt,k)) for k in ('timestep','iterations','ls_iterations','noslip_iterations','solver','integrator','cone')}
        if m.opt.noslip_iterations!=10 or np.any(m.eq_active0):raise RuntimeError('noslip=10/weld OFF required')
        d=mujoco.MjData(m);mujoco.mj_forward(m,d)
        result.update(status='converting_model',reference_ncon=int(d.ncon),reference_nefc=int(d.nefc));save()
        model=mjw.put_model(m)
        if model.opt.noslip_iterations!=10:raise RuntimeError('noslip ignored by model conversion')
        result.update(status='allocating_data',noslip_preserved=True,model_import_s=time.perf_counter()-start);save()
        data=mjw.put_data(m,d,nworld=1)
        result.update(status='compiling_step',capacities={'naconmax':int(data.naconmax),'njmax':int(data.njmax)});save()
        # First step is a compatibility check only, with original reset state.
        mjw.step(model,data);wp.synchronize()
        if np.any(data.overflow.numpy()):raise RuntimeError('MJWarp overflow: '+str(data.overflow.numpy().tolist()))
        if not np.isfinite(data.qpos.numpy()).all() or not np.isfinite(data.qvel.numpy()).all():raise RuntimeError('MJWarp nonfinite state')
        result.update(status='import_step_pass_only',completed=1,step_sim_s=float(m.opt.timestep),
            equivalence_passed=False,expansion_admitted=False,
            note='No endpoint/slip/task equivalence is inferred from one step')
    except Exception as error:
        result.update(status='rejected',failure=1,error_type=type(error).__name__,error=str(error))
    finally:
        result['wall_s']=time.perf_counter()-start
        result['rejections']=[] if result['completed'] else [{'category':'engine_compatibility',
            'reason':result.get('error','incomplete'),'blocking_object':result.get('error_type','unknown'),
            'minimum_gap_m':None,'minimum_gap_status':'not_geometric'}]
        (a.out/'rejection_table.json').write_text(json.dumps({'funnel':[
            {'gate':'source_noslip_present','passed':1,'rejected':0},
            {'gate':'intact_model_step','passed':result['completed'],'rejected':1-result['completed']}],
            'rejections':result['rejections'],'raw_path':str(a.out)},indent=2)+'\n')
        save()
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
