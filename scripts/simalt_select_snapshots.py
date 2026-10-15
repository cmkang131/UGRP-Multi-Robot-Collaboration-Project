"""gcp1 evaluation-only frozen-state projection/ray audit and snapshot selection."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for x in ('source','plan','states','out'):p.add_argument('--'+x,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source))
    # No rendering or physics stepping: only mj_forward of stored evaluation states.
    import cv2
    import mujoco
    import numpy as np
    from simalt_pilot import runtime,world_for
    runtime(a.source,'legacy')
    from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
    plan=json.loads(a.plan.read_text());index=json.loads((a.states/'state-index.json').read_text())
    states=np.load(a.states/'states.npz');world,scene=world_for(plan,False)
    m,d=world.model,world.data;cid=m.camera(index['camera']).id;K=scaled_camera_matrix(640,480);D=np.array(CAMERA_FISHEYE_D)
    near=float(m.vis.map.znear*m.stat.extent);gids=index['target_geoms'];target=set(gids)
    groups=np.array([1,1,1,1,0,0],dtype=np.uint8);audit=[]
    try:
        for row,value in zip(index['rows'],states['states']):
            mujoco.mj_setState(m,d,value,int(states['spec']));mujoco.mj_forward(m,d)
            d.cam_xpos[cid]=row['camera_pos'];d.cam_xmat[cid]=row['camera_rot']
            points=[]
            for g in gids:
                center=d.geom_xpos[g];axes=d.geom_xmat[g].reshape(3,3);points.append(center.copy())
                for axis in range(3):
                    for sign in (-1,1):points.append(center+sign*.8*m.geom_size[g,axis]*axes[:,axis])
            points=np.asarray(points);optical=((points-d.cam_xpos[cid])@d.cam_xmat[cid].reshape(3,3))*[1,-1,-1]
            uv=optical[:,:2]/np.maximum(optical[:,2:3],1e-12)*np.diag(K)[:2]+K[:2,2]
            raw,_=cv2.fisheye.projectPoints(optical.reshape(-1,1,3),np.zeros(3),np.zeros(3),K,D);raw=raw.reshape(-1,2)
            inside=(optical[:,2]>near)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(raw[:,0]>=0)&(raw[:,0]<640)&(raw[:,1]>=0)&(raw[:,1]<480)
            seen=0;blockers=Counter()
            for j in np.flatnonzero(inside):
                delta=points[j]-d.cam_xpos[cid];distance=np.linalg.norm(delta);direction=delta/distance
                origin=d.cam_xpos[cid]+near*distance/optical[j,2]*direction;hit=np.array([-1],dtype=np.int32)
                ray=mujoco.mj_ray(m,d,origin,direction,groups,True,-1,hit)
                if int(hit[0]) in target:seen+=1
                else:blockers[m.geom(int(hit[0])).name if hit[0]>=0 else 'no_hit']+=1
            audit.append({'index':row['index'],'phase':row['phase'],'probe_N':len(points),
                'in_frame':int(inside.sum()),'visible':seen,'occluders':dict(blockers),
                'edge':0<int(inside.sum())<len(points),
                'occluded':bool(inside.any() and blockers and any(k!='no_hit' for k in blockers)),
                'scope':'evaluation only; no actor reads'})
    finally:world.close()
    picks=[];used=set()
    def choose(name,ids):
        ids=[i for i in ids if i not in used]
        if len(ids)<5:return False
        selected=[ids[k] for k in np.linspace(0,len(ids)-1,5).round().astype(int)]
        picks.extend({'stratum':name,'index':int(i)} for i in selected);used.update(selected);return True
    # Rare strata first so common phases do not exhaust them.
    choose('edge',[r['index'] for r in audit if r['edge']])
    choose('occlusion',[r['index'] for r in audit if r['occluded']])
    for name,phases in [('approach',['approach']),('align',['align']),('grasp',['descent','close']),('held',['lift','hold','verify_lift'])]:
        choose(name,[r['index'] for r in audit if r['phase'] in phases])
    result={'selection':picks,'audit':audit,'evaluation_only':True,'training':False,
        'counts':{'candidates':len(audit),'edge':sum(r['edge'] for r in audit),'occluded':sum(r['occluded'] for r in audit),
            'selected':len(picks),'strata':dict(Counter(r['stratum'] for r in picks))},
        'raw_paths':[str(a.states)],'reproduce':sys.argv,
        'probe_basis':'same seven center/0.8-face probes as frozen BandVisibility.region_visible; inherited geometry, no new acceptance tolerance'}
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(result['counts'])


if __name__=='__main__':main()
