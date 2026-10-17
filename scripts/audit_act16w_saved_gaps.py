"""Post-action named geometric gaps from saved MJWarp poses; no physics.

Exact C3.12 compiled geometry is restored before C3.16 kinematic queries.
Distances describe geometry, not MJWarp contact forces or blockage causality.
No new acceptance threshold, action, model selection or success criterion.
"""
import argparse
import json
import math
from pathlib import Path
import sys

from act16w_runtime import require_gcp2, frozen_source, sha256

ROOT=Path(__file__).resolve().parents[1]
Q=Path('/home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    for key in ('world-root','references','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:p.error('saved geometric query default OFF')
    host,source=require_gcp2(training=True),frozen_source(ROOT);frozen_source(Q,Q.name)
    import numpy as np
    import mujoco
    sys.path.insert(0,str(Q/'scripts'))
    from simalt_compiled_compat import apply_geometry
    world=a.world_root;xml=world/'scene.xml';states=world/'states.npz';plan_path=world/'plan.json'
    plan=json.loads(plan_path.read_text());refs=json.loads(a.references.read_text());ref=refs[sha256(xml)]
    model=mujoco.MjModel.from_xml_string(xml.read_text())
    compatibility=apply_geometry(model,xml,Path(ref['geometry']))
    if model.opt.noslip_iterations!=0:raise ValueError('native0 saved scene required')
    data=mujoco.MjData(model);base=model.body('r1__robot').id;root=model.body_rootid[base]
    robot=np.flatnonzero(model.body_rootid[model.geom_bodyid]==root)
    external=np.flatnonzero(model.body_rootid[model.geom_bodyid]!=root)
    explicit={tuple(sorted((int(x),int(y)))) for x,y in zip(model.pair_geom1,model.pair_geom2)}
    pairs=np.array([(int(x),int(y)) for x in robot for y in external
        if ((int(model.geom_contype[x])&int(model.geom_conaffinity[y]))
            or (int(model.geom_contype[y])&int(model.geom_conaffinity[x]))
            or tuple(sorted((int(x),int(y)))) in explicit)],dtype=int)
    if not len(pairs):raise ValueError('no external collidable pairs')
    names={int(i):model.geom(int(i)).name or str(int(i)) for i in range(model.ngeom)}
    # Same floor/ground name exclusion as frozen ACT runner 3f99d58c.
    nonfloor=np.array(['floor' not in names[y] and 'ground' not in names[y] for x,y in pairs])
    plane=np.any(model.geom_type[pairs]==int(mujoco.mjtGeom.mjGEOM_PLANE),axis=1)
    radius=model.geom_rbound[pairs].sum(axis=1)
    extent=float(model.stat.extent)
    closest={};points=[];queries=0;exhaustive_checks=[]
    with np.load(states) as archive:ticks,qpos=archive['ticks'].copy(),archive['qpos'].copy()
    if qpos.shape!=(len(ticks),model.nq):raise ValueError('saved pose dimensions mismatch')
    for frame,(tick,pose) in enumerate(zip(ticks,qpos)):
        data.qpos[:]=pose;mujoco.mj_kinematics(model,data)
        delta=data.geom_xpos[pairs[:,0]]-data.geom_xpos[pairs[:,1]]
        # Official APItypes.html: geom_rbound is the bounding-sphere radius.
        # Planes have no finite sphere, so they always receive an exact query.
        # https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html
        lower=np.linalg.norm(delta,axis=1)-radius;lower[plane]=-math.inf
        result={}
        for label,mask in (('all_external',np.ones(len(pairs),bool)),('non_floor_external',nonfloor)):
            candidate=np.flatnonzero(mask);candidate=candidate[np.argsort(lower[candidate])]
            best=extent;chosen=None
            for i in candidate:
                if lower[i]>=best:break
                x,y=map(int,pairs[i]);gap=float(mujoco.mj_geomDistance(model,data,x,y,extent,None));queries+=1
                if gap<best:best,chosen=gap,(x,y)
            value=dict(tick=int(tick),elapsed_SIM_s=int(tick)*.1,gap_m=best,
                robot_geom=names[chosen[0]] if chosen else None,
                external_geom=names[chosen[1]] if chosen else None,
                censored_at_model_extent=chosen is None)
            if frame in (0,len(ticks)-1):
                exhaustive=min([extent]+[float(mujoco.mj_geomDistance(model,data,int(pairs[i,0]),int(pairs[i,1]),extent,None)) for i in np.flatnonzero(mask)])
                if exhaustive!=best:raise ValueError('bounding-sphere query disagrees with exhaustive distances')
                exhaustive_checks.append(dict(tick=int(tick),kind=label,exact_match=True,pairs=int(mask.sum())))
            result[label]=value
            if label not in closest or best<closest[label]['gap_m']:closest[label]=value
        points.append(result)
    report=dict(status='complete',complete=True,host=host,source_sha=source,seed=plan['seed'],
        assigned_item_id=plan['item_id'],samples=len(points),geometry_queries=queries,
        geometry_compatibility=compatibility,model_extent_distance_ceiling_m=extent,closest=closest,
        exhaustive_first_last_checks=exhaustive_checks,
        API_reference='https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-geomdistance',
        distance_limit='API distances are capped by distmax; legacy CCD may be inaccurate; existing nativeccd flags untouched',
        model_enableflags=int(model.opt.enableflags),model_disableflags=int(model.opt.disableflags),
        floor_filter='existing frozen3f99d58c floor/ground geom-name exclusions; not a new acceptance criterion',
        physics_steps=0,rendered_frames=0,policy_or_scores_changed=False,
        scope='C3.16 distance queries on saved MJWarp poses and exact compiled-reference geometry; no contact-force, blockage-cause, C-physics robustness or policy-input claim',
        raw=[dict(path=str(x),sha256=sha256(x)) for x in (xml,states,plan_path,a.references,Path(ref['geometry']))],
        points=points,reproduce=sys.argv)
    with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('points','raw','reproduce')}))


if __name__=='__main__':main()
