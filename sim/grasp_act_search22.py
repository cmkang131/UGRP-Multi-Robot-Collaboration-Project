"""Default-off uncertainty inflation, visual memory clearing and targeted gaze.

Per-obstacle 2-D Gaussian confidence disc (delta=.01), not a trajectory-wide
risk guarantee. Observation floor/pixel model are design assumptions, not fitted
from evaluator truth. Mean/covariance use only visible samples + issued wheels.
"""
import math
from copy import deepcopy
from functools import lru_cache
import numpy as np
from harness.command_covariance import propagate
from harness.grasp_act_visible_world import command_delta
from sim.grasp_act_search21 import BodyNavigation as Search21Navigation, FRESH_MARGIN_M
from sim.grasp_act_search20 import ADMIT_MARGIN_M
from sim.grasp_act_search18 import body_clearance

MODES={'search22':'search22_v1'}
DELTA=.01
K=math.sqrt(-2*math.log(DELTA)) # exact chi-square(2) 99% radius


def enabled(t):return t.search15_modes.get('search22','off')!='off'


@lru_cache(maxsize=1)
def profile():
    from harness.self_odom_grid import motion_profiles
    return motion_profiles()['motion']


def measurement_uncertainty(m):
    # 2px at the existing 622.165px focal length plus 2mm quantization floor.
    # Visible adapter has no sensor covariance; do not claim calibrated coverage.
    sigma=math.hypot(.002,2*math.hypot(*m['xyz'][:2])/622.1654884818748)
    return {'observation_covariance_m2':(np.eye(2)*sigma*sigma).tolist(),
            'command_covariance':np.zeros((3,3)).tolist(),'issued_pose':[0.,0.,0.],
            'model':'CSM M1 50ms velocity + 1s correlated scale; 2px/2mm observation floor'}


def propagate_memory(memory,issued,dt,mode):
    if issued is None or dt<=0:return
    for m in memory.values():
        u=m.get('uncertainty')
        if u is None:continue
        p=np.asarray(u['issued_pose']);P=np.asarray(u['command_covariance'])
        for start in np.arange(0.,dt, .05):
            stop=min(dt,float(start)+.05);step=stop-start
            # Integrate only each wheel's live deadline, including mid-step expiry.
            a=np.array(command_delta(issued,float(start),mode=mode));b=np.array(command_delta(issued,stop,mode=mode))
            dx,dy,da=b-a;c,s=math.cos(p[2]),math.sin(p[2])
            dw=(c*dx-s*dy,s*dx+c*dy)
            P=propagate(P,p[2],dw,(b-a)/step,step,profile())
            p+=(*dw,da)
        u['command_covariance']=P.tolist();u['issued_pose']=p.tolist()


def uncertainty(m,pose):
    u=m.get('uncertainty')
    if u is None:return None
    P=np.asarray(u['command_covariance']);R=np.asarray(u['observation_covariance_m2'])
    c,s=math.cos(u.get('frame_yaw',0.)),math.sin(u.get('frame_yaw',0.))
    T=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    P=T@P@T.T
    # Relative obstacle/body displacement: shared global origin cancels. Heading
    # uncertainty still moves a remembered point through its current lever arm.
    dx,dy=m['xyz'][0]-pose[0],m['xyz'][1]-pose[1]
    J=np.array([[-1.,0.,dy],[0.,-1.,-dx]])
    covariance=R+J@P@J.T
    if not np.isfinite(covariance).all():return None
    sigma=math.sqrt(max(0.,float(np.linalg.eigvalsh(covariance)[-1])))
    return {'sigma_m':sigma,'margin_m':FRESH_MARGIN_M+K*sigma,'k':K,'delta':DELTA,
            'covariance_m2':covariance.tolist(),'seen_t':m['seen_t']}


class BodyNavigation(Search21Navigation):
    def __init__(self,t,world,*,admission=False):
        super().__init__(t,world,admission=admission)
        self.is_admission=admission
        self.admission=True # same confidence envelope also revalidates retained routes
        obs=world['visibility'][t.rid].get('observations',{})
        labels=[r for r in world['robots'] if r!=t.rid]
        labels += [k for k in world['objects'] if k!='beam_1']
        labels += ['band_'+t.end]*5 if world['beam'] else []
        self.world_observations=obs
        self.labels=labels;self.details=[];self.path_blockers=[];self.probe_cache={}
        for key in labels:
            m=obs.get(key);fresh=m is not None and m['seen_t']>=world['t']-1e-8
            info=uncertainty(m,self.pose) if m is not None else None
            # Current-frame relative geometry retains search21's exact behavior.
            row={'id':key,'fresh':fresh,**(info or {'sigma_m':None,'margin_m':ADMIT_MARGIN_M})}
            if fresh:row['margin_m']=FRESH_MARGIN_M
            self.details.append(row)
        self.disc_margins=[r['margin_m'] for r in self.details]
        for i,rect in enumerate(self.rects):
            m=next((m for m in obs.values() if m['kind']=='wall' and tuple((*m['xyz'][:2],*m['half_extents'],m['yaw']))==tuple(rect)),None)
            info=uncertainty(m,self.pose) if m else None
            if m and m['seen_t']<world['t']-1e-8 and info:self.rect_margins[i]=info['margin_m']
        # A retained route may survive a briefly lost band; new stances may not.
        if not admission:self.fresh_target=True

    def free(self,p,discs,rects,radius,*,heading=None):
        result=super().free(p,discs,rects,radius,heading=heading)
        if not result and self.fresh_target:
            yaw=self.heading(p) if heading is None else heading
            key=(*p[:2],yaw)
            if key not in self.probe_cache:self.probe_cache[key]=self.candidate_audit(p,yaw)
            checks=self.probe_cache[key]
            blockers=[d for d in checks if d['blocked']]
            # A collision-free sampled pose rejected ONLY by memory inflation
            # identifies a reobservation target, also on a connector/retreat.
            if (blockers and all(d['category']=='memory_margin' for d in blockers)
                    and body_clearance((*p[:2],yaw),[],self.rects,bounds=self.bounds,need=FRESH_MARGIN_M)>=FRESH_MARGIN_M):
                obs=self.world_observations
                for d in blockers:
                    if d['id'] not in obs:continue
                    self.teacher.search22_targets[d['id']]=deepcopy(obs[d['id']])
                    if not any(b['id']==d['id'] for b in self.path_blockers):
                        self.path_blockers.append({**d,'sample_pose':[*p[:2],yaw]})
        return result

    def plan_path(self,start,goal,bounds,discs,*,rects=(),radius=.13):
        if not self.free(start,discs,rects,radius):return None
        return super().plan_path(start,goal,bounds,discs,rects=rects,radius=radius)

    def candidate_audit(self,p,heading):
        pose=(*p[:2],heading);rows=[]
        for d,detail in zip(self.discs,self.details):
            gap=body_clearance(pose,[d],[],need=detail['margin_m'])
            rows.append({**detail,'gap_m':gap if math.isfinite(gap) else None,
                'gap_lower_bound_m':gap if math.isfinite(gap) else detail['margin_m'],
                'blocked':gap<detail['margin_m'],
                'category':'memory_margin' if not detail['fresh'] and gap>=FRESH_MARGIN_M else 'current_geometry'})
        return rows


def record_candidates(t,world,rows,now):
    """Complete per-candidate reasons, without counting IK/jaw as collisions."""
    from collections import Counter
    counts=Counter();targets={};obs=world['visibility'][t.rid].get('observations',{})
    for row in rows:
        reason=row['reason']
        blockers=[d for d in row.get('collision_audit',[]) if d['blocked']]
        if not blockers:blockers=row.get('path_memory_blockers',[])
        category=('IK' if reason=='ik_unreachable' else 'gripper_angle' if reason=='gripper_angle' else
            'memory_margin' if blockers and all(d['category']=='memory_margin' for d in blockers) else
            'current_geometry' if reason in ('blocked_goal','blocked_retreat','unsafe_body_sweep') or 'sweep' in reason else reason)
        row['rejection_category']=category;counts[category]+=1
        if t.search15_modes.get('search24_irm','off')!='off' or t.search15_modes.get('search24_budget','off')!='off':
            evidence=(row.get('failure_audit') or blockers or
                      (row.get('path_audit') or {}).get('blocked_obstacles',[]))
            gaps=[d for d in evidence if d.get('gap_m') is not None]
            nearest=min(gaps,key=lambda d:d['gap_m']) if gaps else None
            row.update(blocked_object=nearest['id'] if nearest else 'none:'+reason,
                min_gap_m=nearest['gap_m'] if nearest else None,
                gap_scope=nearest.get('gap_scope','body_surface_clearance') if nearest else
                    'no_geometric_blocker; '+reason)
        if category=='memory_margin':
            targets.update({d['id']:deepcopy(obs[d['id']]) for d in blockers if d['id'] in obs})
    t.search22_targets.update(targets)
    t.search22_log.append({'t':now,'event':'candidate_counts','counts':dict(counts),'candidates':rows})


def update_world(t,world,now):
    """Mark from fresh detections; clear only a covered, unoccluded empty region."""
    from sim.grasp_act_free_space import ghost_visible_region
    w=deepcopy(dict(world));obs=w['visibility'][t.rid].get('observations',{})
    pwm={int(k):v for k,v in t.last_command['pwm'].items()} if t.last_command else t.sink.pwm
    for key,m in list(obs.items()):
        if m['kind']!='cargo' or key=='beam_1':continue
        if m['seen_t']>=now-1e-8:
            t.search22_cleared.pop(key,None);t.search22_since.pop(key,None)
            t.reobserver.pinned.pop(key,None)
            continue
        if key not in t.search22_cleared:
            info=uncertainty(m,w['robots'][t.rid]['pose'])
            if info is None:continue
            clear,reason=ghost_visible_region(w,t.rid,m,pwm,now,
                uncertainty_m=m['radius']+K*info['sigma_m'])
            if clear:
                t.search22_since.setdefault(key,now)
                if now-t.search22_since[key]>=.3-1e-8:
                    t.search22_cleared[key]=now
                    t.search22_log.append({'t':now,'event':'raytrace_visual_clear','id':key,**info})
            else:t.search22_since.pop(key,None)
        if key in t.search22_cleared:
            w['objects'].pop(key,None);obs.pop(key,None);t.reobserver.pinned.pop(key,None)
    return w


def recovery_step(t,world,now,before):
    """Reuse search21's two finite encounters, aim once at the blocking cargo."""
    state=t.search21_recovery
    if not state.get('target'):
        from sim.grasp_act_search21 import recovery_step as previous
        return previous(t,world,now,before)
    from sim.grasp_act_visible_gaze import gaze_pose
    from sim.grasp_act_gaze import slew
    from sim.grasp_act_teacher import local
    from sim.grasp_act_pregrasp import issued_sweep_reason
    key,m=state['target'];age=now-state['start']
    fresh=world['visibility'][t.rid]['observations'].get(key)
    reacquired=fresh is not None and fresh['seen_t']>=now-1e-8 and age>=.3-1e-8
    if age>=1.4-1e-8 or reacquired:
        t.search22_log.append({'t':now,'event':'targeted_reobserve_replan','id':key,'reacquired':reacquired})
        t.search21_recovery=None;t.path=[];t.path_goal=None;t.next_plan=now;t.approach_plan_valid=False
        t.progress.reset();t.search21_progress=None
        return t._hold(now),False
    x,y=local(world['robots'][t.rid]['pose'],m['xyz'])
    # Low boxes: centre of observed vertical bound, not the beam's height.
    z=min(.20,m.get('top_z_bound_m',.04)/2)
    after=slew(t.sink.pwm,gaze_pose((x,y,z),t.sink.pwm))
    reason=issued_sweep_reason(world,t.rid,world['robots'][t.rid]['pose'],before,after,(0.,0.,0.))
    if reason:
        t.search22_log.append({'t':now,'event':'targeted_gaze_blocked','id':key,'reason':reason})
        state.pop('target')
        from sim.grasp_act_search21 import recovery_step as previous
        return previous(t,world,now,before)
    t.sink.pwm.update(after);t.arm.commanded.update(after)
    current=world['visibility'][t.rid]['observations'].get(key)
    t.search22_log.append({'t':now,'event':'targeted_gaze','id':key,'height_m':z,'pwm':dict(after),
        'fresh':current is not None and current['seen_t']>=now-1e-8,
        'uncertainty':uncertainty(current,world['robots'][t.rid]['pose']) if current else None})
    return t._hold(now),False
