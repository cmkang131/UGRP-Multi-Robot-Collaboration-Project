"""Default-off collision compatibility probes; import/enable only on gcp2.

This restores C 3.12's plane/mesh contact selection, not friction or gains.
The algorithm and constants come from engine_collision_convex.c at 3.12.0,
lines 966-1095 (Apache-2.0, Google DeepMind). It is an experiment, not an
assertion that the newer collider is buggy. See simalt4/rejection_table.json.
"""
from typing import Tuple


def install_legacy_plane(m):
    import numpy as np
    import warp as wp
    from mujoco_warp._src import collision_primitive as cp
    from mujoco_warp._src.collision_core import Geom
    from mujoco_warp._src.types import mat43, MJ_MAXVAL
    ids=np.flatnonzero(m.geom_type==7)
    # The wrapper exposes size but not rbound. Refuse unsupported geometry;
    # equality is verified, not replaced by an approximate radius constant.
    if not np.array_equal(m.geom_rbound[ids],np.linalg.norm(m.geom_size[ids],axis=1)):
        raise RuntimeError('legacy plane adapter requires exact rbound == norm(size)')

    @wp.func
    def legacy_plane_convex(normal:wp.vec3, plane:wp.vec3, convex:Geom,
                            margin:float) -> Tuple[wp.vec4,mat43,wp.vec3]:
        dist=wp.vec4(MJ_MAXVAL);pos=mat43()
        direction=wp.transpose(convex.rot) @ (-normal)
        best=int(-1);local_best=int(-1);maximum=float(-1.e10)
        if convex.graphadr<0:
            for i in range(convex.vertnum):
                value=wp.dot(direction,convex.vert[convex.vertadr+i])
                if value>maximum:maximum=value;best=i
        else:
            count=convex.graph[convex.graphadr]
            edges=convex.graphadr+2
            globals_=edges+count
            neighbors=globals_+count
            local_best=0
            maximum=wp.dot(direction,convex.vert[convex.vertadr+convex.graph[globals_]])
            change=int(1)
            while change>0:
                change=0
                edge=convex.graph[edges+local_best]
                while convex.graph[neighbors+edge]>=0:
                    neighbor=convex.graph[neighbors+edge]
                    index=convex.graph[globals_+neighbor]
                    value=wp.dot(direction,convex.vert[convex.vertadr+index])
                    if value>maximum:maximum=value;local_best=neighbor;change=1
                    edge+=1
            best=convex.graph[globals_+local_best]
        if best<0:return dist,pos,normal
        point=convex.pos+convex.rot @ convex.vert[convex.vertadr+best]
        depth=wp.dot(normal,point-plane)
        if depth>margin:return dist,pos,normal
        dist[0]=depth;first=point-0.5*depth*normal;pos[0]=first
        threshold=wp.dot(normal,convex.pos-plane)-margin
        # C3.12's maxplanemesh=3, tolplanemesh=.3, not tuned on this run.
        separation=0.3*wp.length(convex.size)
        n=int(1)
        if convex.graphadr<0:
            for i in range(convex.vertnum):
                vertex=convex.vert[convex.vertadr+i]
                if n<3 and i!=best and wp.dot(direction,vertex)>threshold:
                    point=convex.pos+convex.rot @ vertex
                    if wp.length(point-first)>=separation:
                        depth=wp.dot(normal,point-plane)
                        dist[n]=depth;pos[n]=point-0.5*depth*normal;n+=1
        else:
            count=convex.graph[convex.graphadr]
            edges=convex.graphadr+2;globals_=edges+count;neighbors=globals_+count
            edge=convex.graph[edges+local_best]
            while convex.graph[neighbors+edge]>=0 and n<3:
                neighbor=convex.graph[neighbors+edge]
                vertex=convex.vert[convex.vertadr+convex.graph[globals_+neighbor]]
                if wp.dot(direction,vertex)>threshold:
                    point=convex.pos+convex.rot @ vertex
                    if wp.length(point-first)>=separation:
                        depth=wp.dot(normal,point-plane)
                        dist[n]=depth;pos[n]=point-0.5*depth*normal;n+=1
                edge+=1
        return dist,pos,normal

    cp.plane_convex=legacy_plane_convex
    return {'mode':'legacy-plane-v1','source':'https://github.com/google-deepmind/mujoco/blob/3.12.0/src/engine/engine_collision_convex.c#L966',
            'maxplanemesh':3,'tolplanemesh':.3,'mesh_rbound_size_identity_verified':True,
            'physics_parameters_modified':False}
