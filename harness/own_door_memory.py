"""Own RGB-segment Complete Points (Xiang 2004 §2), default-off door memory.

Preregistered constants/adaptations: egomap50 README. No scene/GT/peer inputs.
A free ray is not itself direct floor evidence. Confidence is a support score.
"""
import copy
import math
import numpy as np
from harness.self_odom_grid import transform
from harness.public_navigation_persistent import raytrace_cells

OPTION='complete_points_v1'
RES=.05
ANGLE=math.radians(10)
MERGE=.25


def axis_angle(a,b):
    return math.acos(float(np.clip(abs(np.dot(a,b)),-1,1)))


def candidates(segments,camera=(0.,0.)):
    """Angular scan neighbours -> CP -> Type I/II, excluding FOV terminal ends."""
    origin=np.asarray(camera,float)
    lines=[]
    for raw in segments:
        a=np.asarray(raw,float)
        if a.shape!=(2,2) or not np.isfinite(a).all():raise ValueError('FINITE_OWN_SEGMENTS_REQUIRED')
        if np.linalg.norm(a[1]-a[0])<RES:continue
        order=np.argsort(np.arctan2((a-origin)[:,1],(a-origin)[:,0]))
        lines.append(a[order])
    lines.sort(key=lambda a:float(np.arctan2(*(a.mean(0)-origin)[::-1])))
    cp=set()
    for i,(a,b) in enumerate(zip(lines,lines[1:])):
        pa,pb=a[1],b[0]
        if np.linalg.norm(pa-pb)<=RES:
            cp.update(((i,1),(i+1,0)))
        elif np.linalg.norm(pa-origin)<np.linalg.norm(pb-origin):cp.add((i,1))
        else:cp.add((i+1,0))
    # Camera FOV boundaries have no neighbour and cannot be complete points.
    out=[]
    def add(a,b,kind):
        width=float(np.linalg.norm(b-a))
        if not .25<=width<=1.5 or max(np.linalg.norm(a-origin),np.linalg.norm(b-origin))>4.:return
        out.append(dict(endpoints=np.array([a,b]).tolist(),width_m=width,kind=kind))
    for i,k in sorted(cp):
        a=lines[i];p=a[k];u=(p-a[1-k])/np.linalg.norm(p-a[1-k])
        for j,l in sorted(cp):
            if (j,l)<=(i,k) or i==j:continue
            b=lines[j];q=b[l];v=(q-b[1-l])/np.linalg.norm(q-b[1-l]);gap=q-p
            if axis_angle(u,v)>ANGLE:continue
            if max(abs(u[0]*gap[1]-u[1]*gap[0]),abs(v[0]*gap[1]-v[1]*gap[0]))>.15:continue
            if np.dot(gap,u)<=0 or np.dot(-gap,v)<=0:continue
            add(p,q,'type_I')
        for j,b in enumerate(lines):
            if i==j:continue
            v=(b[1]-b[0])/np.linalg.norm(b[1]-b[0])
            if abs(np.dot(u,v))>math.sin(ANGLE):continue
            matrix=np.column_stack((u,-v))
            dist,along=np.linalg.solve(matrix,b[0]-p)
            # CP outward extension meets the observed part of the other wall.
            if dist>0 and 0<=along<=np.linalg.norm(b[1]-b[0]):add(p,p+u*dist,'type_II')
    return out


def geometry(row):
    ends=np.asarray(row['endpoints']);center=ends.mean(0)
    tangent=(ends[1]-ends[0])/np.linalg.norm(ends[1]-ends[0])
    return center,tangent,np.array([-tangent[1],tangent[0]])


def same(a,b):
    ca,ta,_=geometry(a);cb,tb,_=geometry(b)
    return np.linalg.norm(ca-cb)<MERGE and axis_angle(ta,tb)<=ANGLE and abs(a['width_m']-b['width_m'])<=MERGE


def facing(row,pose):
    c,_,n=geometry(row);delta=c-np.asarray(pose[:2]);distance=np.linalg.norm(delta)
    if not .05<distance<=4:return False
    forward=np.array([math.cos(pose[2]),math.sin(pose[2])])
    return np.dot(delta/distance,forward)>=math.cos(ANGLE) and abs(np.dot(delta/distance,n))>=math.cos(ANGLE)


def floor_connection(row,pose,floor,camera,segments):
    """Direct samples on both banks + measured floor rays cover chassis corridor."""
    c,tangent,normal=geometry(row)
    required=.20+.04  # frozen solo chassis normal crossing width + two margins
    if row['width_m']-2*RES<required:return False,'footprint_too_wide'
    floor=np.asarray(floor,float).reshape(-1,2)
    floor=floor[np.linalg.norm(floor-np.asarray(camera),axis=1)<=4.]
    floor=transform(floor,pose);cam=transform([camera],pose)[0]
    if not len(floor):return False,'no_direct_floor'
    local=np.column_stack(((floor-c)@tangent,(floor-c)@normal))
    in_gap=abs(local[:,0])<required/2+RES
    if not (np.any(in_gap&(local[:,1]>=.4)) and np.any(in_gap&(local[:,1]<=-.4))):
        return False,'far_or_near_floor_unobserved'
    def cell(p):return tuple(np.floor(p/RES).astype(int))
    rays=set()
    for a in floor[in_gap]:rays.update(raytrace_cells(cell(cam),cell(a)))
    corridor={cell(c+tangent*x+normal*y) for x in np.arange(-required/2,required/2+RES/2,RES)
        for y in np.arange(-.4,.4+RES/2,RES)}
    if not corridor<=rays:return False,'floor_corridor_unknown'
    # Reuse current wall observations, never clear a measured obstacle to confirm.
    for a in segments:
        a=transform(a,pose);length=np.linalg.norm(a[1]-a[0])
        pts=a[0]+np.linspace(0,1,max(2,math.ceil(length/RES)+1))[:,None]*(a[1]-a[0])
        if any(abs(np.dot(p-c,tangent))<required/2 and abs(np.dot(p-c,normal))<.4 for p in pts):
            return False,'current_wall_in_corridor'
    return True,'confirmed_floor_connection'


class DoorMemory:
    def __init__(self,robot_id):
        self.robot_id=robot_id;self.tracks=[];self.seen=set();self.events=[];self.raw_candidates=0

    def observe(self,*,robot_id,t,frame_id,pose,observation):
        if robot_id!=self.robot_id:raise ValueError('DOOR_PEER_INPUT_FORBIDDEN')
        if frame_id in self.seen:raise ValueError('DOOR_DUPLICATE_FRAME')
        pose=np.asarray(pose,float)
        if pose.shape!=(3,) or not np.isfinite(pose).all():raise ValueError('FINITE_OWN_POSE_REQUIRED')
        self.seen.add(frame_id)
        proposals=candidates(observation['segments'],observation['camera']);self.raw_candidates+=len(proposals)
        updated=set()
        for p in proposals:
            p['endpoints']=transform(p['endpoints'],pose).tolist()
            matches=[r for r in self.tracks if same(r,p)]
            if matches:r=min(matches,key=lambda r:np.linalg.norm(geometry(r)[0]-geometry(p)[0]))
            else:
                r=dict(p,id=f'{robot_id}:door_{len(self.tracks)+1:04d}',robot_id=robot_id,
                    coordinate_frame=f'{robot_id}/own_odom',first_t=float(t),first_pose=pose.tolist(),
                    confirmed_t=None,observations=[],state='candidate_opening',confirmation_opportunities=0)
                self.tracks.append(r)
            if r['id'] in updated:continue
            updated.add(r['id'])
            # Fixed first geometry avoids accumulating drift into a moving target.
            r['last_t']=float(t);r['observations'].append(dict(frame_id=frame_id,t=float(t)))
            reobserve=(np.linalg.norm(pose[:2]-r['first_pose'][:2])>=.05 or
                abs((pose[2]-r['first_pose'][2]+math.pi)%(2*math.pi)-math.pi)>=math.radians(5))
            fresh=t>r['first_t'] and reobserve
            is_facing=facing(p,pose)
            valid,reason=floor_connection(p,pose,observation['floor_xy'],observation['camera'],observation['segments']) if is_facing else (False,'not_frontal')
            r['last_reason']=reason
            if fresh and is_facing:r['confirmation_opportunities']+=1
            if fresh and is_facing and valid and r['confirmed_t'] is None:
                r['state']='visually_confirmed_passage';r['confirmed_t']=float(t)
                r['confirmation_evidence']=dict(frame_id=frame_id,t=float(t),pose=pose.tolist(),
                    endpoints=copy.deepcopy(p['endpoints']),direct_floor=True,free_connection_observed=True)
                self.events.append(dict(t=float(t),reason='own_door_confirmed',id=r['id']))
            r['confidence']=1. if r['confirmed_t'] is not None else min(.5,len(r['observations'])/10.)
        return [copy.deepcopy(r) for r in self.tracks if r['id'] in updated]

    def snapshot(self,tf=(0.,0.,0.)):
        result=copy.deepcopy(self.tracks)
        for r in result:r['endpoints']=transform(r['endpoints'],tf).tolist()
        return result
