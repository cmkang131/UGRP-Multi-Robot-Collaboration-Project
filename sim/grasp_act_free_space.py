"""Negative visual evidence for stale peers; never TTL-based authorization.

Uses the same conservative 18-degree optical cone as the teacher's band-view
check, issued camera FK, fresh visible anchors and known occluders. No renderer,
scene handle, segmentation IDs, hidden poses or evaluation fields are accepted.
"""
import math
from copy import deepcopy
import numpy as np
from sim.grasp_act_gaze import camera_extrinsics
from sim.grasp_act_teacher import local
from sim.grasp_act_visible_route import segment_free

RANGE_M=2.0
UNCERTAINTY_M=.065
DWELL_S=.3


def ghost_visible_region(world,rid,ghost,pwm,now,*,uncertainty_m=UNCERTAINTY_M):
    vis=world['visibility'][rid];obs=vis.get('observations',{})
    key=ghost['id']
    if key in vis['peers'] or obs.get(key,{}).get('seen_t',-math.inf)>=now-1e-8:
        return False,'peer_seen'
    # An empty/missing frame is not a negative detection. A fresh admitted
    # landmark establishes that the current observation pipeline is alive.
    if not any(k!=key and m['seen_t']>=now-1e-8 for k,m in obs.items()):
        return False,'no_fresh_frame_anchor'
    pose=world['robots'][rid]['pose'];origin,axes=camera_extrinsics(pwm)
    c,s=math.cos(pose[2]),math.sin(pose[2])
    eye=(pose[0]+c*origin[0]-s*origin[1],pose[1]+s*origin[0]+c*origin[1],origin[2])
    x,y=ghost['xyz'][:2];z=min(.16,ghost.get('top_z_bound_m',.32)/2)
    # Cover the whole position-error square, not just a centre ray near an edge.
    for dx in (-uncertainty_m,0.,uncertainty_m):
        for dy in (-uncertainty_m,0.,uncertainty_m):
            q=(x+dx,y+dy,z);lx,ly=local(pose,q)
            optical=np.asarray(axes)@(np.array([lx,ly,z])-origin)
            if (optical[2]<=0 or np.linalg.norm(optical)>RANGE_M or
                    np.linalg.norm(optical[:2])>optical[2]*math.tan(math.radians(18))):
                return False,'outside_view_or_range'
            obstacles=[(k,o['xy'],o['radius'],o['top_z_bound_m']) for k,o in world['objects'].items() if k not in ('beam_1',key)]
            obstacles += [(k,r['pose'][:2],r.get('radius',.17),r.get('top_z_bound_m',.32))
                          for k,r in world['robots'].items() if k not in (rid,key)]
            if world['beam'] is not None:
                bx,by,a=world['beam']['pose'];bz=next(iter(world['beam']['ends'].values()))[2]+.02
                obstacles += [('beam_1',(bx+d*math.cos(a),by+d*math.sin(a)),.025,bz) for d in (-.27,-.135,0.,.135,.27)]
            vx,vy=q[0]-eye[0],q[1]-eye[1];norm=vx*vx+vy*vy
            for _,xy,radius,top in obstacles:
                u=max(0.,min(1.,((xy[0]-eye[0])*vx+(xy[1]-eye[1])*vy)/max(norm,1e-12)))
                if (0.<u<1. and math.dist((eye[0]+u*vx,eye[1]+u*vy),xy)<radius+UNCERTAINTY_M
                        and eye[2]+u*(z-eye[2])<=top+UNCERTAINTY_M):return False,'occluded'
            # Walls may not be relaxed just because the camera starts near one.
            from sim.grasp_act_search17 import segment_free as strict_segment
            if not strict_segment(eye[:2],q[:2],[],world.get('walls',[]),UNCERTAINTY_M):
                return False,'wall_occluded'
    return True,'covered_empty'


class FreeSpace:
    def __init__(self):
        self.ghosts={};self.since={};self.cleared={};self.events=[];self.last_status={}

    def update(self,world,teacher,now):
        rid=teacher.rid;vis=world['visibility'][rid];obs=vis.get('observations',{})
        for k,m in obs.items():
            if m['kind']=='robot' and m['seen_t']>=now-1e-8:
                self.ghosts[k]=deepcopy(m);self.cleared.pop(k,None);self.since.pop(k,None)
        # The last issued posture formed this frame; the next gaze command did not.
        pwm=({int(k):v for k,v in teacher.last_command['pwm'].items()}
             if teacher.last_command else teacher.sink.pwm)
        w=deepcopy(dict(world))
        for k,m in self.ghosts.items():
            if k in vis['peers']:continue
            if k not in self.cleared:
                clear,reason=ghost_visible_region(world,rid,m,pwm,now)
                self.last_status[k]=reason
                if clear:
                    self.since.setdefault(k,now)
                    if now-self.since[k]>=DWELL_S-1e-8:
                        self.cleared[k]=now
                        self.events.append({'t':now,'event':'peer_free_space_clear','peer':k,
                            'last_seen_t':m['seen_t'],'dwell_s':now-self.since[k],
                            'input':'current visible anchors + issued camera FK + last visible peer; no GT'})
                else:self.since.pop(k,None)
            if k in self.cleared:
                w['robots'].pop(k,None);w['visibility'][rid]['observations'].pop(k,None)
            else:
                # 기억 만료는 목표가 비었다는 증거가 아니다.
                # Expiry of a remembered peer is not evidence that the goal cleared.
                w['robots'][k]={'pose':[*m['xyz'][:2],m.get('yaw',0.)],
                    'radius':m.get('radius',.17),'top_z_bound_m':m.get('top_z_bound_m',.32)}
        if teacher.peer_wait_ids and teacher.peer_wait_ids<=self.cleared.keys():
            if teacher.reobserver.active and teacher.reobserver.active['kind']=='peer':
                teacher.reobserver.finish(teacher,now,'observed_free_space_replan')
        return w
