"""Default-off S3 command ownership and bounded last-visible approach.

No simulator/evaluation imports. All geometry comes from own RGB, fixed camera
calibration and the exact issued pulse profile. Legacy defaults are untouched.
"""
import copy
from dataclasses import dataclass, asdict
import math
from types import SimpleNamespace
import numpy as np
from harness.zone_final_pair_binding import bind
from harness.zone_s3_visual_pose_servo import transform
from harness.zone_solo_cyan_pulse_cal import profile_key


@dataclass(frozen=True)
class Options:
    endpoint_memory: bool = False
    band_border: bool = False
    posture_ownership: bool = False
    coarse_axis_ownership: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):raise ValueError('boolean options required')

    @property
    def enabled(self):return any(asdict(self).values())


ALL=Options(True,True,True,True)
LIMITS=dict(anchor_age_s=8.,max_pulses=3,max_travel_m=.06,max_turn_rad=.32,
    band_border_px=1,hysteresis_exit_multiplier=1.25,gt_inputs=False)


def band_vision(vision):
    """Full-band support test at real valid-image boundary, 1px sampling margin.

    Leave the v1 body/end detector and all band length/identity tests unchanged.
    The previous 14px erosion was a conservative clipping proxy, not visibility.
    """
    import cv2
    from harness.owncam_view import valid_pixel_mask
    old=vision.v2_observe.__globals__['v1']
    mask=cv2.erode(valid_pixel_mask(1).astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
    own=SimpleNamespace(**{**vars(old),'_INNER':mask})
    vision.v2_observe=bind(vision.v2_observe,v1=own)
    return vision


class LastVisible:
    def __init__(self,profiles):
        self.profiles=profiles;self.anchor=None;self.pending=[];self.pulses=0
        self.travel=0.;self.turn=0.;self.invalid=None

    def capture(self,beam,obs,pulses,segment):
        self.anchor=copy.deepcopy(beam)
        self.anchor.update(anchor_time_s=obs['sim_time'],anchor_frame_id=obs['frame_id'],
            anchor_sha256=obs['sha256'],anchor_servo=dict(pulses),prediction_time_s=obs['sim_time'],
            source='last visible own RGB + calibrated issued commands')
        self.segment=segment;self.pending=[];self.pulses=0;self.travel=self.turn=0.;self.invalid=None

    def command(self,row,servo):
        if self.anchor is None:return
        if row['kind'] in ('drive','mecanum') and any(row.get(k,0.) for k in ('forward','left','turn')):
            p=self.profiles.get(profile_key(row,False))
            if p is None or p['axis'] not in ('forward','turn') or p['duration_s']!=.1:
                self.invalid='unregistered_motion';return
            self.pending.append((row['t']+max(.5,p['times'][-1]),copy.deepcopy(p)))
            self.pulses+=1;self.travel+=math.hypot(*p['mean_delta'][:2]);self.turn+=abs(p['mean_delta'][2])
        if row['kind']=='arm' and int(row['servo_id'])==1 and row['pulse']>=2000>servo.get(1,2000):
            self.invalid='release'

    def estimate(self,now,segment):
        if self.anchor is None or self.invalid or segment!=self.segment:return None
        if not 0<=now-self.anchor['anchor_time_s']<=LIMITS['anchor_age_s']:return None
        if self.pulses>3 or self.travel>.06 or self.turn>.32:return None
        if any(t>now+1e-8 for t,p in self.pending):return None
        for t,p in self.pending:
            g,h=transform(self.anchor['grip_base_m'],self.anchor['axis_heading_rad'],p['mean_delta'])
            self.anchor.update(grip_base_m=g.tolist(),axis_heading_rad=h,prediction_time_s=t)
            var=np.asarray(p['prediction_variance'])
            self.anchor['std_xy_m']=math.sqrt(self.anchor['std_xy_m']**2+max(var[:2]))
            self.anchor['std_yaw_rad']=math.sqrt(self.anchor['std_yaw_rad']**2+var[2])
        self.pending=[]
        return copy.deepcopy(self.anchor)


def owns_posture(ctl):
    s=getattr(ctl,'s3_coarse_fine',None)
    return bool(s and s.refinements.posture_ownership and ctl.state=='align'
        and not ctl.beam_grasp_confirmed and ctl.port.own.servo.get(1)==2000)


def install_posture_owner(ctl):
    # Explicit resource handover; don't add private pan poses to PF calibration.
    from harness.zone_pair_highpose_posture_defer import DeferRelook
    from harness.zone_pair_align import PairAlignRelook
    tick,restore,relook=ctl.tick,ctl._v98_restore,ctl._begin_align_relook
    def owned_tick(now):
        if not owns_posture(ctl):return tick(now)
        ctl.v98_relook_pending=None
        # Skip only the competing posture/relook owners. Original status,
        # partner-abort and arm tick live in the normal align tick below.
        return super(PairAlignRelook,ctl).tick(now)
    def owned_restore(now,st):
        if owns_posture(ctl):
            ctl.log(ctl.rid,'fine_posture_restore_deferred',now,owner='own_rgb_align')
            return None
        return restore(now,st)
    def owned_relook(now,reason):
        if owns_posture(ctl):
            ctl.log(ctl.rid,'fine_posture_relook_deferred',now,reason=reason,owner='own_rgb_align')
            return None
        return relook(now,reason)
    ctl.tick,ctl._v98_restore,ctl._begin_align_relook=owned_tick,owned_restore,owned_relook


def one_step(servo,grip,heading,plan):
    """Quantized coordinate descent; no future sequence can justify a bad first move.

    Keep acceptance widths fixed. An axis that enters its band remains latched
    until 1.25x departure while another axis needs work. If only a latched residual
    prevents acceptance, re-enable that axis; a latch never fabricates alignment.
    """
    q=plan(grip,heading,servo.rid)
    if q['ready']:return None,q
    e,t=np.array(q['errors']),np.array(q['halfwidths'])
    if not hasattr(servo,'axis_latched'):servo.axis_latched=[False]*3
    for i in range(3):
        if abs(e[i])<=t[i]:servo.axis_latched[i]=True
        elif abs(e[i])>1.25*t[i]:servo.axis_latched[i]=False
    active=[i for i in range(3) if abs(e[i])>t[i] and not servo.axis_latched[i]]
    if not active:active=[i for i in range(3) if abs(e[i])>t[i]]
    def cost(p):return sum(max(abs(a)/b-1,0)**2 for a,b in zip(p['errors'],p['halfwidths']))
    before=cost(q);candidates=[]
    # The arm lever couples base yaw and lateral error. Test each single axis
    # against the complete fixed envelope, never a future multi-pulse benefit.
    for profile in servo.pool:
        g,h=transform(grip,heading,profile['mean_delta']);after=plan(g,h,servo.rid)
        if any(servo.axis_latched[i] and i not in active and
            abs(after['errors'][i])>1.25*after['halfwidths'][i] for i in range(3)):continue
        if cost(after)<before-1e-9:candidates.append((cost(after),profile))
    return (min(candidates,key=lambda x:x[0])[1] if candidates else None),q


def install_solo_owner(own,servo):
    from harness.zone_solo_cyan_align_pulse import Runtime as FineRuntime, alignment_primitive
    def primitive(action,option='off'):
        claimed=(own.state=='align' and servo.audit and
            servo.audit[-1].get('issued')==action and
            servo.audit[-1]['frame_id']==own.last_obs['frame_id'])
        # Copy preserves the legacy timing/stop receipt while retaining the
        # exact calibrated 100ms values; no shared factory/source mutation.
        return dict(action) if claimed else alignment_primitive(action,option)
    class FineOwner(FineRuntime):
        step=bind(FineRuntime.step,alignment_primitive=primitive)
    own.__class__=type('S3FineOwner',(own.__class__,FineOwner),{})
