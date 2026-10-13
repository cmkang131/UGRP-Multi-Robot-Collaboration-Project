"""Default-off robot-private end candidates, sticky assignment and RGB occupancy.

No peer objects, referee state or common world pose enter this module. Candidate
IDs are PRIVATE track labels, not a shared frame. A model adapter must return its
choice and channel message together; only delivered channel text may be supplied.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from harness.active_wall_mapping import wrap
from harness.self_odom_grid import transform

OPTIONS=('lock_v1','rgb_rule_v1','gemma_v1')
PARAMS=dict(grip_offset_m=.27,reach_m=.2032,occupancy_radius_m=.25,
            rgb_max_age_s=.45,lock_match_max_m=.45,decision_period_s=10.)
SYSTEM='''Two robots must grasp DISTINCT OPPOSITE ends of the same beam; both at
the same end cannot carry it. Choose which beam end YOUR robot should approach using only its own RGB,
private candidate estimates, own commands, and actually delivered channel text.
Candidate end0/end1 are private labels: another robot's same label need not mean
that physical end. Ground messages in visible beam/robot relationships. Never
assume a shared B direction estimate. Choose one offered candidate or wait.
Output exactly {"choice":"end0|end1|wait","message":"...","reason":"..."}.
In no_comm message must be empty; in fixed_signal use only CLAIM or YIELD or WAIT.
Do not treat orange boxes, the floor, or your own gripper as another robot.
Occupied candidates are unavailable. Preserve a selected physical end unless
new own visual evidence or a delivered message requires reconsideration.'''


def rgb_peer_regions(jpeg):
    """Conservative compound orange/grey robot-appearance proposal, not identity.

    A single solid orange box is insufficient. No absence-of-detection is a
    clearance claim. Geometry and repeated observations must corroborate it.
    """
    import cv2
    if not jpeg:return []
    bgr=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
    if bgr is None:return []
    hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV);h,w=bgr.shape[:2]
    orange=cv2.inRange(hsv,(5,100,60),(25,255,255))
    n,labels,stats,centers=cv2.connectedComponentsWithStats(orange)
    parts=[s for s in stats[1:] if s[4]>=max(12,h*w*.00008)]
    regions=[]
    # Robot fingers/wheels have separate orange components and adjacent dark
    # mechanical texture. This rejects one-piece orange boxes in saved frames.
    for s in parts:
        x,y,bw,bh,area=map(int,s);pad=max(12,int(max(bw,bh)*.7))
        x0=max(0,x-pad);x1=min(w,x+bw+pad);y0=max(0,y-pad);y1=min(h,y+bh+pad)
        neighbors=[q for q in parts if x0<=q[0]+q[2]/2<=x1 and y0<=q[1]+q[3]/2<=y1]
        if len(neighbors)<3:continue
        grey=(hsv[y0:y1,x0:x1,1]<100)&(hsv[y0:y1,x0:x1,2]<125)
        if grey.mean()<.10:continue
        xx=min(int(q[0]) for q in neighbors);yy=min(int(q[1]) for q in neighbors)
        xe=max(int(q[0]+q[2]) for q in neighbors);ye=max(int(q[1]+q[3]) for q in neighbors)
        if ye-yy<h*.04:continue
        box=[xx,yy,xe,ye]
        if box not in [r['bbox_px'] for r in regions]:regions.append(dict(bbox_px=box,source='own_rgb_compound_robot_appearance',identity='unknown'))
    return regions


def occupied_candidates(candidates,pose,servo,regions):
    """Project candidate stance volume into the current own RGB. Hypothesis only."""
    from harness.owncam_view import project_base_points
    from harness.active_wall_mapping import inverse
    found={}
    for c in candidates:
        local=transform([c['station_own_m'][:2]],inverse(pose))[0]
        samples=np.array([[local[0]+dx,local[1]+dy,z] for dx in [-.10,0,.10]
                          for dy in [-.10,0,.10] for z in [.04,.12,.22]])
        uv=project_base_points(servo,samples);uv=uv[np.isfinite(uv).all(axis=1)]
        hits=[]
        for region in regions:
            x0,y0,x1,y1=region['bbox_px']
            if len(uv) and np.any((uv[:,0]>=x0)&(uv[:,0]<=x1)&(uv[:,1]>=y0)&(uv[:,1]<=y1)):
                hits.append(region)
        found[c['id']]=hits
    return found


class Selector:
    def __init__(self,rid,option='off',*,condition='no_comm'):
        if option not in ('off',*OPTIONS):raise ValueError('UNKNOWN_END_ASSIGNMENT')
        if rid not in ('r1','r2') or condition not in ('no_comm','fixed_signal','natural_language'):
            raise ValueError('END_ASSIGNMENT_ID_OR_CHANNEL')
        self.rid,self.option,self.condition=rid,option,condition
        self.axis=None;self.selected=None;self.rows=[];self.blocked=set();self.streak={};self.last_frame=None;self.last_occupancy_t=None

    def candidates(self,beam,target,pose,path_cost=None):
        from harness.e2e_carrier_axes import basis
        b=basis(beam,target);axis=float(b['yaw_rad'])
        if self.axis is not None and math.cos(axis-self.axis)<0:axis=wrap(axis+math.pi)
        self.axis=axis;center=np.asarray(b['center_m']);u=np.array([math.cos(axis),math.sin(axis)])
        out=[]
        for i,sign in enumerate([-1,1]):
            grip=center+sign*PARAMS['grip_offset_m']*u;yaw=wrap(axis+(math.pi if i else 0.))
            station=grip+sign*PARAMS['reach_m']*u
            cost=path_cost(station.tolist()) if path_cost is not None else None
            out.append(dict(id=f'end{i}',station_own_m=[*station.tolist(),yaw],grip_own_m=grip.tolist(),
                basis=dict(b,yaw_rad=axis),distance_m=math.dist(pose[:2],station),
                rotation_rad=abs(wrap(yaw-pose[2])),path_length_m=cost,
                path_status='unmeasured' if cost is None else 'available',
                blocked=f'end{i}' in self.blocked,source_rgb=copy.deepcopy(beam['rgb'])))
        return out

    def observe_occupancy(self,candidates,pose,servo,jpeg,frame,now,frame_t):
        if self.option not in ('rgb_rule_v1','gemma_v1'):return {}
        if frame==self.last_frame or not 0<=now-frame_t<=PARAMS['rgb_max_age_s']:return {}
        self.last_frame=frame
        if self.last_occupancy_t is not None and now-self.last_occupancy_t>1.:self.streak.clear()
        self.last_occupancy_t=now
        regions=rgb_peer_regions(jpeg);hits=occupied_candidates(candidates,pose,servo,regions)
        for c in candidates:
            cid=c['id'];self.streak[cid]=self.streak.get(cid,0)+1 if hits[cid] else 0
            if self.streak[cid]>=2:self.blocked.add(cid)
            c['blocked']=cid in self.blocked
        return dict(frame_id=frame,regions=regions,hits=hits,blocked=sorted(self.blocked),
                    source='own_RGB_and_commanded_camera',absence_means='unknown')

    def context(self,candidates,*,delivered_text=()):
        if self.condition=='no_comm' and delivered_text:raise ValueError('NO_COMM_PEER_INPUT')
        if any(not isinstance(t,str) for t in delivered_text):raise ValueError('TEXT_CHANNEL_ONLY')
        return dict(robot_id=self.rid,condition=self.condition,candidates=copy.deepcopy(candidates),
                    selected=self.selected,delivered_text=list(delivered_text))

    def choose(self,candidates,*,reply=None):
        available={c['id'] for c in candidates if not c['blocked']}
        message='';source='fixed_rule_fallback'
        if reply is not None:
            if not isinstance(reply,dict) or set(reply)!={'choice','message','reason'}:raise ValueError('END_REPLY_FORMAT')
            if not all(isinstance(reply[k],str) for k in reply):raise ValueError('END_REPLY_TEXT')
            if self.condition=='no_comm' and reply['message']:raise ValueError('NO_COMM_MESSAGE')
            if self.condition=='fixed_signal' and reply['message'] not in ('','CLAIM','YIELD','WAIT'):raise ValueError('FIXED_SIGNAL_ONLY')
            if reply['choice'] not in available|{'wait'}:raise ValueError('OCCUPIED_OR_UNKNOWN_END')
            selected=reply['choice'];message=reply['message'];source='judgment_model'
        else:
            preferred=self.selected or ('end0' if self.rid=='r1' else 'end1')
            selected=preferred if preferred in available else next((c['id'] for c in candidates if c['id'] in available),'wait')
        previous=self.selected
        self.selected=None if selected=='wait' else selected
        row=dict(choice=selected,previous=previous,source=source,message=message,blocked=sorted(self.blocked))
        self.rows.append(row)
        return next((c for c in candidates if c['id']==selected),None),row


def install(tr,option='off',*,relay_url=None):
    """Stage adapter installs robot-private state. Off does not mutate transport."""
    if option=='off':return
    if option not in OPTIONS:raise ValueError('UNKNOWN_END_ASSIGNMENT')
    tr.end_assignment=option;tr.end_selectors={rid:Selector(rid,option) for rid in ('r1','r2')}
    tr.end_clients={}
    if option=='gemma_v1':
        from harness.e2e_end_model import Client
        if relay_url is None:raise ValueError('END_MODEL_RELAY_REQUIRED')
        tr.end_clients={rid:Client(relay_url) for rid in ('r1','r2')}


def update_station(tr,rid,now,state,target):
    """Own RGB/costmap only; return hold while the finite view/model check runs."""
    if getattr(tr,'end_assignment','off')=='off' or 'station' not in state:return None
    from harness.active_wall_mapping import compose
    from harness.public_navigation_unknown import from_observed_grid
    r=tr.robots[rid];s=tr.end_selectors[rid];pose=np.asarray(r.goal.explorer.local_pose)
    b=state['basis'];beam=dict(pose_own_m=[*b['center_m'],b['yaw_rad']],rgb=b['rgb'])
    target_point=target['center_m'] if target else np.asarray(b['center_m'])+np.array([math.cos(b['yaw_rad']),math.sin(b['yaw_rad'])])
    candidates=s.candidates(beam,target_point,pose)
    frame=r.last_obs or {};f=r.frame
    occupancy=s.observe_occupancy(candidates,pose,r.servo,f.jpeg if f else None,
        frame.get('frame_id'),now,frame.get('sim_time',-math.inf))
    if occupancy.get('blocked'):
        tr.event(now,'end_occupancy_rgb',robot_id=rid,**occupancy)
    selected_before=s.selected
    if now<state.get('end_model_wait_until',-math.inf):
        r.carrier_approach=dict(t=now,status='end_model_wait')
        return False,[dict(kind='hold')]
    client=getattr(tr,'end_clients',{}).get(rid);reply=None
    if client is not None:
        response=client.poll()
        if response is not None:
            state['end_request_done']=True
            if response.get('error')=='END_MODEL_BUDGET_EXHAUSTED':
                tr.fail('END_MODEL_BUDGET_EXHAUSTED',now);return False,[dict(kind='hold')]
            reply=response.get('decision')
            if isinstance(reply,dict) and reply.get('choice')=='wait':
                state['end_model_wait_until']=now+5.;state['end_request_done']=False
            tr.event(now,'end_model_receipt',robot_id=rid,response=response)
        needs=(not state.get('end_request_done') or (s.selected in s.blocked and not state.get('end_block_decided')))
        if needs and client.future is None and response is None:
            # Path preview uses only the robot's current observed grid. It is
            # computed at decision events, not on every controller tick.
            ex=r.goal.explorer;mp=compose(ex.map_to_odom,pose)
            costmap=from_observed_grid(ex.grid,mp,ex.latest,set())
            for c in candidates:
                goal=transform([c['station_own_m'][:2]],ex.map_to_odom)[0]
                path=ex.navigator.plan_to(costmap,mp,goal)
                c['path_length_m']=sum(math.dist(a,b) for a,b in zip(path,path[1:])) if path else None
                c['path_status']='available' if path else 'unavailable'
            client.start(s.context(candidates),f);state['end_request_started']=now
            if s.selected in s.blocked:state['end_block_decided']=True
            tr.event(now,'end_model_request',robot_id=rid,context=s.context(candidates),rgb_sha256=f.sha256)
        if client.future is not None:
            r.carrier_approach=dict(t=now,status='end_model_pending')
            return False,[dict(kind='hold')]
    try:choice,event=s.choose(candidates,reply=reply)
    except ValueError as exc:
        tr.event(now,'end_model_rejected',robot_id=rid,reason=str(exc));choice,event=s.choose(candidates)
    if event['previous']!=event['choice'] or reply is not None:
        tr.event(now,'end_assignment',robot_id=rid,**event,candidates=candidates)
    if choice is None:
        r.carrier_approach=dict(t=now,status='end_both_occupied')
        return False,[dict(kind='hold')]
    state.update(station=np.array(choice['station_own_m']),grip=np.array(choice['grip_own_m']),basis=choice['basis'])
    if selected_before!=s.selected:
        for key in ('efficient_path','efficient_cruise','progress_watch','end_look'):state.pop(key,None)
        state['fine']=False
    # Before entering the stance, use the existing SEARCH camera posture and
    # a finite three-pan inspection. Camera/FOV/model geometry is unchanged.
    if s.option in ('rgb_rule_v1','gemma_v1') and choice['distance_m']<=.65:
        from harness.owncam_pair_beam_v2 import pose_of
        look=state.setdefault('end_look',dict(index=0,frame=None,until=now,done=False))
        if not look['done']:
            if look['frame'] is not None and now>=look['until'] and frame.get('frame_id')!=look['frame']:
                look['index']+=1;look['frame']=None
            if look['index']>=3:
                look['done']=True
                tr.event(now,'end_occupancy_view_complete',robot_id=rid,blocked=sorted(s.blocked),unseen_is='unknown')
            else:
                if look['frame'] is None:
                    posture=pose_of('search');posture[6]=(1200,1500,1800)[look['index']]
                    tr._poses(rid,now,[(posture,.3,.9)]);look.update(frame=frame.get('frame_id'),until=now+1.6)
                r.carrier_approach=dict(t=now,status='end_occupancy_view',view=look['index'],selected=s.selected)
                return False,[dict(kind='hold')]
    return None
