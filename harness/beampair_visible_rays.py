"""Simulation teacher perception boundary; current own-camera visible surfaces.

No evaluator object pose reaches planning. Like the pinned visible measurement
adapter this module confines ray intersections and world-to-base conversion to
perception. It returns only currently visible relative ray segments, with both
source pinhole and raw fisheye checks. Held cargo rays are excluded entirely.
"""
import math
import numpy as np
from harness.beampair_wall_layer import GRID_M


def visible_rays(world, evaluator, rid, wall_top):
    import cv2,mujoco
    # Same 2m local visual range as pinned grasp_act_free_space.RANGE_M; the
    # sample spacing is exactly search23's grid. These are sensor coverage,
    # not success/clearance tolerances, and do not change camera calibration.
    from sim.grasp_act_free_space import RANGE_M
    model,data=world.model,world.data;cid=evaluator.cameras[rid]
    base=world.robot(rid).base_xyz();yaw=float(world.robot(rid).base_rpy()[2]);c,s=math.cos(yaw),math.sin(yaw)
    local=np.arange(-RANGE_M,RANGE_M+GRID_M/2,GRID_M);xx,yy=np.meshgrid(local,local)
    mask=xx*xx+yy*yy<=RANGE_M*RANGE_M
    x,y=xx[mask],yy[mask]
    points=np.column_stack((base[0]+c*x-s*y,base[1]+s*x+c*y,np.zeros(len(x))))
    origin=data.cam_xpos[cid].copy();delta=points-origin
    optical=(delta@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
    valid=optical[:,2]>evaluator.near
    optical=optical[valid];delta=delta[valid]
    uv=optical[:,:2]/optical[:,2,None]*np.diag(evaluator.K)[:2]+evaluator.K[:2,2]
    fisheye,_=cv2.fisheye.projectPoints(optical.reshape(-1,1,3),np.zeros(3),np.zeros(3),evaluator.K,evaluator.D)
    fisheye=fisheye[:,0,:]
    valid=((uv>=(0,0))&(uv<(640,480))).all(axis=1)&((fisheye>=(0,0))&(fisheye<(640,480))).all(axis=1)
    delta=delta[valid]
    if not len(delta):return []
    vec=np.ascontiguousarray(delta/np.linalg.norm(delta,axis=1)[:,None]);N=len(vec)
    hit=np.full(N,-1,dtype=np.int32);distance=np.full(N,-1.,dtype=float)
    mujoco.mj_multiRay(model,data,origin,vec.reshape(-1),evaluator.groups,True,-1,hit,distance,None,N,RANGE_M)
    # Only actual intersections are evidence; a missing/empty ray is unknown.
    # 2-D clearing uses rays below the observed wall's known box top. All
    # authored walls in this unchanged scene run from floor to twice centre z.
    top=wall_top  # observed wall centre above the known floor, never hidden geometry
    rows=[]
    for i in np.flatnonzero((hit>=0)&(distance>evaluator.near)&(distance<=RANGE_M)):
        endpoint=origin+vec[i]*distance[i]
        if not (0<=origin[2]<=top and 0<=endpoint[2]<=top):continue
        name=model.geom(int(hit[i])).name or 'unnamed_visible_surface'
        # Never provide held cargo world locations. Caller disables all rays
        # while held, in addition to the original measurement suppression.
        p=((endpoint-origin)@data.cam_xmat[cid].reshape(3,3))*np.array([1.,-1.,-1.])
        rows.append(dict(optical_end=p.tolist(),hit_wall=name if 'wall' in name else None))
    return rows
