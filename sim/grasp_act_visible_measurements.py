"""Simulation-only perfect perception adapter; never gives a controller self GT.

Only currently unoccluded regions become relative object-pose measurements.
The full simulator remains confined to this boundary and the evaluator.
"""
import math
import numpy as np


def measurements(world,evaluator,rid,role,object_bodies):
    data=world.data;model=world.model
    # Coordinate conversion belongs to privileged visual measurement creation.
    # No world self coordinates leave this adapter.
    base=world.robot(rid).base_xyz();yaw=float(world.robot(rid).base_rpy()[2]);co,si=math.cos(yaw),math.sin(yaw)
    def relative(point):
        x,y,z=point;dx=x-base[0];dy=y-base[1]
        return [co*dx+si*dy,-si*dx+co*dy,float(z)]
    rows=[]
    for end,gid in evaluator.bands.items():
        v=evaluator.measure(data,rid,end)
        if v['visible_probes']<5:continue
        r=data.geom_xmat[gid].reshape(3,3)
        rows.append({'id':'band_'+end,'kind':'band','xyz':relative(data.geom_xpos[gid]),
            'yaw':math.atan2(r[1,0],r[0,0])-yaw,'visible_n':v['visible_probes'],'probe_N':v['probe_N']})
    bodies={**{key:(body,'cargo') for key,body in object_bodies.items()},
            **{p:(p+'__robot','robot') for p in ('r1','r2','r3') if p!=rid}}
    for key,(body,kind) in bodies.items():
        bid=model.body(body).id;gids=evaluator._body_geoms(bid)
        visible,total=evaluator.region_visible(data,rid,gids)
        if not total or visible*3<total:continue
        point=data.body(body).xpos;r=data.body(body).xmat.reshape(3,3)
        radius=max((float(np.linalg.norm(data.geom_xpos[g][:2]-point[:2]))+float(model.geom_rbound[g]) for g in gids),default=.2)
        top=max((float(data.geom_xpos[g,2]+model.geom_rbound[g]) for g in gids),default=.5)
        rows.append({'id':key,'kind':kind,'xyz':relative(point),'yaw':math.atan2(r[1,0],r[0,0])-yaw,
                     'radius':radius,'top_z_bound_m':top,'visible_n':visible,'probe_N':total})
    # Static walls are visual obstacles in the same unanchored odometry frame.
    for gid in range(model.ngeom):
        name=model.geom(gid).name or ''
        if 'wall' not in name or not evaluator.groups[model.geom_group[gid]]:continue
        visible,total=evaluator.region_visible(data,rid,[gid])
        if not total or visible*3<total:continue
        r=data.geom_xmat[gid].reshape(3,3)
        rows.append({'id':name,'kind':'wall','xyz':relative(data.geom_xpos[gid]),
            'yaw':math.atan2(r[1,0],r[0,0])-yaw,'radius':float(np.linalg.norm(model.geom_size[gid,:2])),
            'half_extents':model.geom_size[gid,:2].tolist(),
            'top_z_bound_m':float(data.geom_xpos[gid,2]+model.geom_rbound[gid]),'visible_n':visible,'probe_N':total})
    return rows
