"""Own-host zero-step MJWarp contact geometry audit of saved warm pulse states.

This is reconstruction, not recorded live forces. It never calls step/forward,
advances SIM time, changes a command, or supplies measurements to a controller.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from scripts.warpfit import host,load,dump,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();host();run=a.run.resolve();out=a.output.resolve()
    sys.path.insert(0,str(Path(__import__('scripts.warpfit',fromlist=['__file__']).__file__).resolve().parent))
    if run.parent.parent!=Path('/home/ugrp/ugrp-sim/runs/warpfit2'):raise ValueError('own run only')
    r=json.loads((run/'result.json').read_text())
    if not r['completed'] or r['cap_end']:raise ValueError('completed primitive only')
    import numpy as np
    import mujoco
    import warp as wp
    import mujoco_warp as mjw
    from sim.warp_native_runtime import collision
    from scripts.simalt_physics_compare import unused_efm
    m,d,f,meta,xml,_=load(SimpleNamespace(fixture=Path(r['fixture']),profile='warp_native_contact_v1',engine='warp'))
    s=np.load(run/'states.npz');names=meta['groups']['warm6'];n=len(names)
    wp.init();wm=mjw.put_model(m);adapter=collision(r['runtime_profile'],m)
    # Reuse the measured run's already admitted workspace. No new fitted cap.
    capacity=r['capacity'];nc=capacity.get('nconmax') or capacity['naconmax']//r['nworld']
    with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=n,nconmax=nc,njmax=capacity['njmax'])
    geoms=[m.geom(i).name or f'geom#{i}' for i in range(m.ngeom)]
    roller={i for i,name in enumerate(geoms) if name.startswith('r1__') and 'roller' in name.lower()}
    rows=[];selected=[]
    out.mkdir(parents=True,exist_ok=False)
    for index,t in enumerate(s['t']):
        wd.qpos.assign(s['qpos'][index,:n]);wd.qvel.assign(s['qvel'][index,:n])
        mjw.kinematics(wm,wd);mjw.collision(wm,wd);wp.synchronize()
        if np.any(wd.overflow.numpy()):raise ValueError('snapshot geometry overflow; no inference')
        count=int(wd.nacon.numpy()[0]);gs=wd.contact.geom.numpy()[:count]
        worlds=wd.contact.worldid.numpy()[:count];distance=wd.contact.dist.numpy()[:count]
        for w,name in enumerate(names):
            contacts=[dict(geoms=[geoms[int(g)] for g in gs[i]],minimum_gap_m=float(distance[i]))
                for i in np.flatnonzero(worlds==w) if any(int(g) in roller for g in gs[i])]
            row=dict(t=float(t),world=w,case=name,roller_contact_points=len(contacts),
                touching_points=sum(c['minimum_gap_m']<=0 for c in contacts),
                minimum_gap_m=min((c['minimum_gap_m'] for c in contacts),default=None),
                gap_status='MJWarp_collision_reconstruction_at_saved_qpos; not_original_live_force',contacts=contacts)
            rows.append(row)
            case=meta['cases'][w]
            boundaries=[case['settle_s'],case['settle_s']+case['duration_s'],
                        case['settle_s']+case['duration_s']+case['tail_s']]
            if any(round(t/float(m.opt.timestep))==round(b/float(m.opt.timestep)) for b in boundaries):selected.append(row)
    dump(out/'contacts.json',dict(rows=rows,run=str(run),source_states_sha256=digest(run/'states.npz'),
        physics_steps=0,SIM_time_advanced=0,force_estimation=False,worlds=list(range(n)),
        scope='first representative lane per fixed tape; collision geometry reconstructed in same MJWarp profile, not original live forces',
        collision=adapter,script_sha256=digest(Path(__file__))))
    dump(out/'summary.json',dict(run=str(run),profile=r['runtime_profile'],round=r['round'],
        source_states_sha256=digest(run/'states.npz'),physics_steps=0,boundary_rows=selected,
        scope='MJWarp geometry reconstruction; no live force or causal roller-phase conclusion'))
    dump(out/'SHA256.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(run=run.name,snapshots=len(rows),physics_steps=0,roller_geoms=len(roller))))


if __name__=='__main__':main()
