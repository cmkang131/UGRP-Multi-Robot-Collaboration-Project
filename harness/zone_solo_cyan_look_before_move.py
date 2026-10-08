"""Default-off S2 look-before-lateral-motion with own-RGB unknown-space veto.

Ulrich/Nourbakhsh AAAI2000 floor appearance + inverse perspective, Nav2's
unknown-space collision convention. No depth/peer/GT handle. A missing robot
detection is never used as a free-space observation. The conservative ground
projection retains the appearance method's same-colour obstacle limitation.
"""
import copy
import math
from collections import deque
import cv2
import numpy as np
from harness.zone_solo_cyan_floor_contact import floor_pixels
from harness.zone_solo_cyan_pulse_cal import profile_key,response,action_of,select_pulse
from harness.zone_solo_cyan_flow_fusion import compose,rot
from harness.zone_solo_cyan_v106 import ENVELOPE,LOOK_P20
from harness.zone_solo_cyan_side_scan import arm_actions
from harness.zone_solo_cyan_visibility import K,robot_boxes,shadow_depths,pixel_rays
from harness.zone_solo_cyan_scene_change import cyan
from harness.zone_solo_cyan_bias_tempering import group,scaled

OPTION='rgb_sweep_v1'
PARAMS=dict(recent_s=3.,margin_m=.02,grid_m=.025,frame_interval_s=.25,
    max_range_m=3.,settle_s=2.,observe_s=.75,wait_s=1.,communication_condition_invariant=True)


def lateral(action):
    return action['kind'] in ('drive','mecanum') and bool(action.get('left',0))


def swept_points(profile,margin=PARAMS['margin_m']):
    """All occupied grid cells on the pulse curve, minus CURRENT own footprint.

    Nav2 footprint clearing excludes the robot itself, not the padded margin.
    Add half a cell diagonal to padding; no endpoint-only certificate.
    """
    cell=PARAMS['grid_m'];pad=margin+cell/math.sqrt(2)
    x=np.arange(ENVELOPE['x_m'][0]-pad,ENVELOPE['x_m'][1]+pad+cell,cell)
    y=np.arange(ENVELOPE['y_m'][0]-pad,ENVELOPE['y_m'][1]+pad+cell,cell)
    pts=np.array(np.meshgrid(x,y)).reshape(2,-1).T;out=[]
    for d in profile['mean_curve']:
        q=pts@rot(d[2]).T+np.array(d[:2]);out.append(q)
    q=np.unique(np.round(np.vstack(out)/cell).astype(int),axis=0)*cell
    current=((q[:,0]>=ENVELOPE['x_m'][0])&(q[:,0]<=ENVELOPE['x_m'][1])&
             (q[:,1]>=ENVELOPE['y_m'][0])&(q[:,1]<=ENVELOPE['y_m'][1]))
    return q[~current]


def classify(rgb,table):
    from harness import vision_loc_protocol as vp
    image=vp.load_vis3()[0].mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    orange=cv2.inRange(hsv,(5,100,60),(25,255,255))>0
    valid=np.max(image,axis=2)>10
    nonfloor=(~floor_pixels(image,table)|orange|cyan(image))&valid
    # Paper section3: nearest (lowest) obstacle on a column hides more distant
    # ground. Black lens borders are UNKNOWN and do not invent an obstacle.
    bottom=np.max(np.where(nonfloor,np.arange(480)[:,None],-1),axis=0)
    free=valid&~nonfloor&(np.arange(480)[:,None]>bottom[None,:])
    return free,nonfloor,valid


class Memory:
    def __init__(self,table):
        self.table=copy.deepcopy(table);self.views=deque();self.active=None
        self.odom=np.zeros(3);self.last_frame=-math.inf;self.settle_after=0.
        self.depth_cache={};self.stats=dict(frames=0,unsupported=0,unsettled=0)

    def at(self,now):
        if self.active is None:return self.odom.copy()
        return compose(self.odom,response(self.active[1],max(0.,now-self.active[0])))

    def command(self,now,action,profile=None):
        if action['kind'] in ('arm','look'):
            self.settle_after=now+PARAMS['settle_s']
        if profile is not None:
            self.odom=self.at(now);self.active=(now,copy.deepcopy(profile))
            self.settle_after=max(self.settle_after,now+profile['times'][-1])
        elif action['kind']=='hold' and self.active is not None and now<self.active[0]+self.active[1]['duration_s']-1e-8:
            self.odom=self.at(now);self.active=None;self.views.clear()

    def add(self,now,rgb,camera,servo,image_sha):
        if now<self.settle_after-1e-8:self.stats['unsettled']+=1;return False
        if now<self.last_frame+PARAMS['frame_interval_s']-1e-8:return False
        if camera is None:self.stats['unsupported']+=1;return False
        free,blocked,valid=classify(rgb,self.table)
        key=(tuple(sorted(servo.items())),camera.origin.tobytes(),camera._rot.tobytes())
        if key not in self.depth_cache:
            rays=pixel_rays(camera,np.arange(640)[None,:],np.arange(480)[:,None])
            self.depth_cache[key]=np.minimum.reduce(list(shadow_depths(camera.origin,rays,robot_boxes(servo,camera)).values()))
        self.views.append(dict(t=now,odom=self.at(now),free=free,blocked=blocked,valid=valid,
            origin=camera.origin.copy(),rotation=camera._rot.copy(),self_depth=self.depth_cache[key],sha=image_sha))
        self.last_frame=now;self.stats['frames']+=1
        self.expire(now);return True

    def expire(self,now):
        while self.views and now-self.views[0]['t']>PARAMS['recent_s']+1e-8:self.views.popleft()

    def assess(self,now,profile):
        self.expire(now);points=swept_points(profile);free=np.zeros(len(points),bool);blocked=free.copy()
        current=self.at(now);world=points@rot(current[2]).T+current[:2];sources=[]
        for view in self.views:
            p=(world-view['odom'][:2])@rot(view['odom'][2]);xyz=np.c_[p,np.zeros(len(p))]
            optical=(xyz-view['origin'])@view['rotation'];z=optical[:,2]
            pixels=optical@K.T
            uv=np.rint(np.clip(pixels[:,:2]/np.maximum(z[:,None],1e-12),-10000,10000)).astype(int)
            valid=(z>0)&(uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)&(np.linalg.norm(p,axis=1)<=PARAMS['max_range_m'])
            u=uv[:,0].clip(0,639);v=uv[:,1].clip(0,479)
            valid&=view['valid'][v,u]&(view['self_depth'][v,u]>z)
            free|=valid&view['free'][v,u];blocked|=valid&view['blocked'][v,u]
            if valid.any():sources.append(view['sha'])
        known=free&~blocked
        return dict(t=now,clear=bool(len(points) and known.all()),points=len(points),
            known_free=int(known.sum()),occupied=int(blocked.sum()),unknown=int((~free&~blocked).sum()),
            coverage=float(known.mean()) if len(points) else 0.,source_images=sorted(set(sources)),
            scope='own RGB appearance and fixed ground plane; current footprint cleared; no peer truth')


def attach(runtime,*,look_before_move='off',floor_table=None):
    if look_before_move=='off':return runtime  # exact identity, no wrapper or RNG
    if look_before_move!=OPTION:raise ValueError('unknown look_before_move')
    if floor_table is None:raise ValueError('fixed floor appearance table required')
    memory=Memory(floor_table);runtime.look_memory=memory
    audit=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),checks=[],scans=[],
        denied=0,allowed=0,unconfirmed_lateral_issued=0,alternate_forward_or_turn=0,
        gt_inputs=False,communication_inputs=False,free_from_no_detection=False)
    runtime.look_before_move_audit=audit
    old_step,old_frames,old_command,old_record=runtime.step,runtime.on_frames,runtime.on_command,runtime.record
    phase=None;deadline=0.;restore=None;side=0;scanned_origin=None;last_wait=-math.inf;detour=False

    def profile_for(a):
        pf=runtime.pose.provider.loc._pf
        try:key=profile_key(a,pf.load.loaded)
        except ValueError:return None
        p=runtime.pulse_profiles.get(key)
        if p is None:return None
        calibration=getattr(runtime,'look_bias_calibration',{})
        g=calibration.get('groups',{}).get(group(runtime.servo,key))
        return scaled(p,g['gain']) if g else p

    def frames(now,values):
        old_frames(now,values)
        obs,rgb=values[runtime.robot_id];cm=None
        try:cm=runtime.pose.provider.loc._pf.column_model_for(runtime.servo)
        except (KeyError,ValueError):pass
        memory.add(now,rgb,cm,dict(runtime.servo),obs['sha256'])

    def command(rid,now,a):
        p=None
        if a['kind'] in ('drive','mecanum') and any(a.get(k,0) for k in ('forward','left','turn')):
            p=profile_for(a)
        if lateral(a):
            clear=p is not None and memory.assess(now,p)['clear']
            if not clear:
                audit['unconfirmed_lateral_issued']+=1
                raise RuntimeError('uncertified lateral command escaped own RGB guard')
        memory.command(now,a,p);return old_command(rid,now,a)

    def timing(now,a):
        p=profile_for(a)
        if p is not None:
            runtime.cal_until=now+p['duration_s'];runtime.cal_settled_at=now+p['times'][-1]

    def approach_without_strafe(now):
        nonlocal detour
        if runtime.cal_until is not None:
            if now<runtime.cal_until-1e-8:return []
            runtime.cal_until=None
            return [(runtime.robot_id,dict(kind='hold'))]
        if now<runtime.cal_settled_at-1e-8:return []
        if not runtime.path:detour=False;return []
        r=runtime.last_report
        error=rot(r.yaw_rad).T@(np.array(runtime.path[0])-[r.x_m,r.y_m])
        if np.linalg.norm(error)<=.035:
            runtime.path.pop(0)
            if not runtime.path:runtime.path_goal=None
            detour=False;return []
        if r.std_xy_m>.05 or r.std_yaw_rad>math.radians(5) or r.last_fix_t is None:
            runtime.soft('POSE_UNCERTAIN',now)
        pool={k:p for k,p in runtime.pulse_profiles.items() if p['axis']!='left'}
        heading_error=-math.atan2(error[1],error[0])
        if abs(heading_error)>math.radians(5):pool={k:p for k,p in pool.items() if p['axis']=='turn'}
        p,_=select_pulse(pool,runtime.pose.provider.loc._pf.load.loaded,error,heading_error)
        if p is None:return [(runtime.robot_id,dict(kind='hold'))]
        alt=action_of(p);timing(now,alt);audit['alternate_forward_or_turn']+=1
        audit.setdefault('detour_commands',[]).append(dict(t=now,action=alt,waypoint=list(runtime.path[0]),state=runtime.state))
        return [(runtime.robot_id,alt)]

    def step(now):
        nonlocal phase,deadline,restore,side,scanned_origin,last_wait,detour
        rid=runtime.robot_id
        if runtime.terminal:return old_step(now)
        if phase is not None:
            if now<deadline-1e-8:return []
            if phase=='observe':
                audit['scans'][-1]['observed_at']=now
                phase='restore';deadline=now+PARAMS['settle_s']
                return arm_actions(rid,restore)
            phase=None;runtime.cal_until=None;runtime.cal_settled_at=now
        if detour:return approach_without_strafe(now)
        proposals=old_step(now)
        for _,a in proposals:
            if not lateral(a):continue
            p=profile_for(a)
            row=memory.assess(now,p) if p is not None else dict(t=now,clear=False,reason='uncalibrated_pulse')
            row.update(action=copy.deepcopy(a),state=runtime.state)
            if row['clear']:
                row['issued']=True;audit['allowed']+=1;audit['checks'].append(row);return proposals
            audit['denied']+=1;row['issued']=False;audit['checks'].append(row)
            if runtime.cal_rows and abs(runtime.cal_rows[-1]['t']-now)<1e-8:
                runtime.cal_rows[-1]['look_before_move_withheld']=True
            runtime.cal_until=None;runtime.cal_settled_at=now
            sign=1 if a['left']>0 else -1;here=memory.at(now)
            changed=(scanned_origin is None or side!=sign or np.linalg.norm(here[:2]-scanned_origin[:2])>=PARAMS['grid_m']
                     or abs(here[2]-scanned_origin[2])>=math.radians(5))
            if changed:
                side=sign;scanned_origin=here;restore=dict(runtime.servo)
                target={**LOOK_P20,1:restore[1],6:2300 if sign>0 else 700}
                phase='observe';deadline=now+PARAMS['settle_s']+PARAMS['observe_s']
                audit['scans'].append(dict(t=now,target=target,restore=restore,reason='lateral corridor not visually certified'))
                # Same fixed arm/look interface as active Markov. Never open grip.
                return [(rid,dict(kind='hold'))]+arm_actions(rid,target)
            # A parked obstacle need not clear. Replan the next pulse from the
            # existing vocabulary with lateral candidates removed. No invented
            # displacement or hidden peer position, and preserve the same goal.
            if runtime.state in ('search_move','carry') and runtime.path:
                detour=True
                return approach_without_strafe(now)
            if now-last_wait>=PARAMS['wait_s']:
                runtime.soft('LATERAL_SPACE_UNKNOWN_OR_OCCUPIED',now);last_wait=now
            return [(rid,dict(kind='hold'))]
        return proposals

    runtime.on_frames,runtime.on_command,runtime.step=frames,command,step
    runtime.record=lambda:{**old_record(),'look_before_move':{**copy.deepcopy(audit),'perception':copy.deepcopy(memory.stats)}}
    return runtime
