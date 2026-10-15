"""Crate12 input producers, fixed colour assignment and recording preflight.

No simulator, measured self pose, cargo world pose or partner state arguments.
The demonstration adapter's visible relative geometry remains explicitly tagged
as such; it must not be confused with a student's RGB perception accuracy.
"""
import hashlib
import math
from harness.grasp_act_input_audit import sourced
from sim.crate_rgb_lift import masks

PROFILE = 'crate12_v1'
CRATE13 = 'crate13_v1'
PROFILES = (PROFILE, CRATE13)
ASSIGNMENT = 'fixed_rgb_lugs_v1'
LOOKAROUND = 'setdown_lookaround_own_v2'
RELEASE = 'fixed_signals_v1'


def fixed_role(rid):
    return {'r1':'teal','r2':'blue'}[rid]


def own_lug(rgb, rid):
    """Fixed role is confirmed only by that robot's own colour + crate pixels.

    No distance-minimising assignment, no peer observations or claims. Pixel
    thresholds are provisional and must be checked in the fresh diagnostics.
    """
    import numpy as np
    end=fixed_role(rid)
    lug,pink=masks(rgb,end)
    y,x=np.nonzero(lug)
    visible=False
    if len(x)>=12:
        h,w=lug.shape
        # Require body colour near the lug, excluding lone blue zone markings.
        pad=max(4,round(min(h,w)*.05))
        patch=pink[max(0,y.min()-pad):min(h,y.max()+pad+1),max(0,x.min()-pad):min(w,x.max()+pad+1)]
        visible=int(patch.sum())>=12
    return {'end':end,'confirmed':visible,'lug_pixels':int(lug.sum()),
            'rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),
            'source':'own_rgb','assignment_source':ASSIGNMENT}


def tagged_world(world, *, holding=False):
    out=dict(world)
    if holding:
        out['beam']=None
        out['objects']={k:v for k,v in out['objects'].items() if k!='crate_1'}
    return {k:sourced(v,*(('clock',) if k=='t' else
              ('fixed_rule',) if k=='scope' else
              ('static_map','visible_teacher_measurement','issued_commands') if k=='walls' else
              ('issued_commands',) if k=='robots' and len(v)==1 else
              ('visible_teacher_measurement','issued_commands','known_shape')))
            for k,v in out.items()}


def validate_recording(*, mode, profile, held_object, own_pose_source, lookaround, assignment, release_channel):
    if mode not in ('success_measurement','training'):raise ValueError('unknown recording mode')
    if profile not in ('off',*PROFILES):raise ValueError('unknown crate profile')
    if profile in PROFILES or mode=='training':
        if held_object!='hidden_v1':raise ValueError('strict/recording mode requires held_object=hidden_v1')
        if own_pose_source!='commands':raise ValueError('truth pose forbidden in strict/recording mode')
        if lookaround not in ('off',LOOKAROUND):raise ValueError('truth lookaround forbidden in strict/recording mode')
        if assignment!=ASSIGNMENT:raise ValueError('GT nearest assignment forbidden in strict/recording mode')
        if release_channel!=RELEASE:raise ValueError('strict release requires explicit fixed signal channel')
    if mode=='training':
        # This runner still has no admitted student RGB writer or >=38/40 gate.
        # Never mislabel success-measurement logs as a training dataset.
        raise ValueError('training recording not implemented/admitted; success gate required first')


def local_static_landmarks(model):
    """Static wall corners in the SAME unanchored issued frame as own pose.

    No fictional map-frame pose is created from the episode spawn. Wall shape
    and the last admitted visible wall pose form this local static map. Only
    landmarks in that frame may be used until RGB map localization exists.
    """
    out=[]
    for key,m in model.memory.items():
        if m['kind']!='wall':continue
        x,y=m['xyz'][:2];hx,hy=m['half_extents'];a=m['yaw'];c,s=math.cos(a),math.sin(a)
        for i,(dx,dy) in enumerate(((-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy))):
            out.append({'id':key+'#'+str(i),'xy':(x+c*dx-s*dy,y+s*dx+c*dy)})
    return out


def look_views(pose, landmarks):
    """Directions from static map + own estimated pose; no observed bearings."""
    from sim.crate_lookaround import wrap
    bins={}
    for lm in landmarks:
        dx,dy=lm['xy'][0]-pose[0],lm['xy'][1]-pose[1]
        if math.hypot(dx,dy)>4.:continue
        angle=wrap(math.atan2(dy,dx)-pose[2])
        k=round(angle/math.radians(45))
        bins.setdefault(k,[]).append(lm['id'])
    # Still look around if localization/visible static anchors are unavailable.
    # Such a scan is explicitly unlocalized, never an EKF correction/success.
    if not bins:bins={-2:[],0:[],2:[],4:[]}
    return [{'body_yaw_deg':k*45.,'pan_deg':0.,'landmarks':v}
            for k,v in sorted(bins.items())]


class OwnLookaround:
    """Finite own-only scan. Captures real RGB; cannot manufacture a pose fix."""
    def __init__(self, model):
        self.pose=list(model.pose)
        self.landmarks=local_static_landmarks(model)
        self.rects=[(*m['xyz'][:2],*m['half_extents'],m['yaw']) for m in model.memory.values() if m['kind']=='wall']
        self.script=None;self.index=0;self.stage='start';self.until=0.;self.turn=[];self.yaw_done=0.
        self.log={'pose_frame':'issued_local','anchor_source':'admitted visible static walls',
                  'localized_in_authored_map':False,'identified_landmarks':None,'pose_updates':0,
                  'frames':[],'source':'own RGB + issued commands + local static wall map'}

    def propagate(self, dx,dy,da):
        c,s=math.cos(self.pose[2]),math.sin(self.pose[2])
        self.pose=[self.pose[0]+c*dx-s*dy,self.pose[1]+s*dx+c*dy,self.pose[2]+da]

    def step(self, now, *, apply_pan, issue_wheels, capture):
        from sim.crate_lookaround import rotation_plan,pan_pulse,DWELL_S
        if self.script is None:
            self.script=look_views(self.pose,self.landmarks)
            self.log.update(planned_views=self.script,estimate_before=list(self.pose))
        if self.index>=len(self.script):
            self.log['estimate_after']=list(self.pose)
            self.log.setdefault('outcome','complete')
            return False
        if now<self.until-1e-9:return True
        v=self.script[self.index]
        if self.stage=='start':
            self.turn=rotation_plan(math.radians(v['body_yaw_deg']-self.yaw_done))
            self.yaw_done=v['body_yaw_deg'];self.stage='turn'
        if self.stage=='turn':
            if self.turn:
                from sim.crate_approach_recovery import safe_pulse
                w,d=self.turn.pop(0)
                if not safe_pulse({'wheels':w,'duration_s':d},self.pose,[],self.rects,.13,
                                  mode='crate_no_closer_v1',wall_footprint=True):
                    self.log['outcome']='wall_blocked';self.index=len(self.script)
                    return False
                issue_wheels(w,d,now)
                return True
            apply_pan(pan_pulse(v['pan_deg']),now)
            self.stage='dwell';self.until=now+DWELL_S
            return True
        rgb=capture()
        self.log['frames'].append({'t':now,'expected_landmarks':v['landmarks'],
                                   'rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest()})
        self.index+=1;self.stage='start'
        return True
