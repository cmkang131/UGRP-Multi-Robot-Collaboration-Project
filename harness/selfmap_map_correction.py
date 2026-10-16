"""Default-off Olson/Cartographer-style causal scan-to-submap correction.

Reuses existing CSM sensor model, MAP cost, observability projection, admission
and covariance rules. No new score/uniqueness thresholds. +/-1 prior sigma is
the user's requested diagnostic/candidate window, not an empirically calibrated
confidence guarantee. Floors/steps/age/count are unchanged CSMOptions.

Static initialization is a separate explicit global registration; unknown gauge
is never replaced by identity/spawn. Both matchers read the SAME motion prior;
one proposal is selected (static first), never fuse the same scan twice.
"""
import math
import numpy as np
from harness.e2e_rgb_vo import compose,between,fuse
from harness.self_map_csm import CSMOptions,CorrelativeMatcher,sample_segments
from harness.self_odom_grid import transform
from harness.mapbuild_static_registration import StaticRegistration,OPTION as STATIC

OPTION='selfmap_map_correction_v1'


def inverse(p):return between(p,np.zeros(3))


class SelfMapCorrection:
    def __init__(self,static_map,*,option='off'):
        if option not in ('off',OPTION):raise ValueError('UNKNOWN_MAP_CORRECTION')
        self.option=option;self.options=CSMOptions();self.matcher=CorrelativeMatcher(self.options)
        self.registration=StaticRegistration(static_map,option=STATIC)
        self.pose=np.zeros(3);self.covariance=np.zeros((3,3));self.frames=[];self.ledger=[]
        self.static_from_own=None;self.static_covariance=None;self.last_t=None;self.last_scan=-math.inf
        self.global_segments=[];self.global_origins=[];self.global_body_origins=[];self.global_pose_covariances=[]

    def initialize_static(self):
        result=self.registration.register(self.global_segments,camera_origins=self.global_origins,
            pose_covariances=self.global_pose_covariances,body_origins=self.global_body_origins)
        if result['status']=='accepted':
            self.static_from_own=np.asarray(result['static_from_own']);self.static_covariance=np.asarray(result['covariance'])
        return result

    def _match(self,points,camera,reference,anchor_covariance):
        # A gauge has exact zero uncertainty until motion; existing CSM floor
        # only regularizes an exactly singular algebraic prior, not a fake pose.
        P=self.covariance
        if np.linalg.eigvalsh(P).min()<=0:return dict(status='rejected',reason='singular_motion_prior',pose=self.pose.tolist(),candidates=0)
        return self.matcher.match(self.pose,P,points,camera,reference,anchor_covariance,
                                  prior_window=np.sqrt(np.diag(P)))

    def step(self,t,frame_id,command_delta,command_covariance,flow,scan):
        if self.last_t is not None and t<=self.last_t:raise ValueError('NONCAUSAL_FRAME')
        self.last_t=t;o=self.options
        if flow.get('status')=='measured':
            # The inherited command model returns EXACTLY zero Q for a zero
            # issued pulse. It has no calibration for passive body motion.
            # Do not use that singular algebraic value as perfect stationarity
            # and discard a measured visual increment. Reuse VO's existing
            # replace mode/covariance; no invented process-noise floor.
            mode='replace' if not np.any(command_covariance) else 'fused'
            delta,Q,nis,how=fuse(command_delta,command_covariance,flow['delta'],flow['covariance'],mode=mode)
        else:delta=np.asarray(command_delta);Q=np.asarray(command_covariance);nis=None;how='command_kept'
        c,s=np.cos(self.pose[2]),np.sin(self.pose[2]);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        d=R@delta;F=np.eye(3);F[:2,2]=[-d[1],d[0]]
        self.covariance=F@self.covariance@F.T+R@Q@R.T;self.pose=compose(self.pose,delta)
        event=dict(t=float(t),frame_id=int(frame_id),status='deferred',reason='no_visible_scan',
            category='map_correction',blocked_object='own_observed_wall',minimum_gap_m=None,gap_status='not_measured',
            prior_pose=self.pose.tolist(),prior_covariance=self.covariance.tolist(),motion_delta=delta.tolist(),
            motion_covariance=Q.tolist(),fusion=how,nis=nis,attempted=False,accepted=False,inserted=False,
            self_match=None,static_match=None,selected=None,truth_inputs=0,scale=1)
        self.ledger.append(event)
        local=np.asarray(scan['segments'],float).reshape(-1,2,2)
        if not len(local):return self.pose.tolist(),event
        if t-self.last_scan<o.keyframe_interval_s-1e-8:event['reason']='sim_keyframe_interval';return self.pose.tolist(),event
        self.last_scan=t
        points=sample_segments(local)
        if len(points)<o.min_points:event['reason']='insufficient_near_points';return self.pose.tolist(),event
        if self.option=='off':event['reason']='off';return self.pose.tolist(),event
        event['attempted']=True
        past=[k for k in self.frames if t-k['t']<=o.submap_age_s and np.linalg.norm(self.pose[:2]-np.asarray(k['pose'])[:2])<=o.submap_radius_m]
        chosen=None
        if past:
            reference=np.concatenate([k['world_segments'] for k in past])
            result=self._match(points,np.asarray(scan['camera']),reference,np.asarray(past[0]['anchor_covariance']))
            event['self_match']=result
            if result['status']=='accepted':chosen=('self_submap',result)
        if self.static_from_own is not None:
            reference=transform(self.registration.reference.reshape(-1,2),inverse(self.static_from_own)).reshape(-1,2,2)
            c,s=np.cos(self.static_from_own[2]),np.sin(self.static_from_own[2]);J=np.eye(3)
            J[:2,:2]=[[c,s],[-s,c]];J[:2,2]=[-self.pose[1],self.pose[0]]
            # Registration covariance is expressed in STATIC axes at the own
            # origin. Rotate it once and propagate its yaw lever arm here.
            anchor=J@self.static_covariance@J.T
            result=self._match(points,np.asarray(scan['camera']),reference,anchor)
            event['static_match']=result
            if result['status']=='accepted':chosen=('static_map',result)
        if chosen:
            event['selected'],result=chosen;self.pose=np.asarray(result['pose']);self.covariance=np.asarray(result['covariance'])
            event.update(status='accepted',reason='accepted',accepted=True)
        elif not past:event.update(status='bootstrap',reason='new_submap_motion_anchor')
        else:
            reasons=[v['reason'] for v in (event['self_match'],event['static_match']) if v]
            event.update(status='rejected',reason=';'.join(reasons) or 'no_observable_reference')
        # Grisetti motion-proposal insertion / existing mapbuild5
        # rbpf_composition.insert_selective_v1: a rejected pose correction is
        # NOT a rejected RGB observation. Insert valid scans at the unchanged
        # motion prior WITH its covariance; never shrink uncertainty on failure.
        # This fixes the observed R1 starvation (2 bootstrap maps, no further
        # reference insertion), without changing score/window constants.
        # Past frames stay immutable; this scan was absent during both matches.
        if len(local):
            world=transform(local.reshape(-1,2),self.pose).reshape(-1,2,2)
            anchor=past[0]['anchor_covariance'] if past else self.covariance.tolist()
            policy='matched' if chosen else 'bootstrap' if not past else 'motion_prior_uncorrected'
            row=dict(t=float(t),frame_id=int(frame_id),pose=self.pose.tolist(),world_segments=world.tolist(),anchor_covariance=anchor,
                     covariance=self.covariance.tolist(),insertion_policy=policy)
            self.frames=(past+[row])[-o.submap_keyframes:];event.update(inserted=True,insertion_policy=policy)
        # Separate visual-only initialization ledger, not an adopted static map.
        self.global_segments.extend(transform(local.reshape(-1,2),self.pose).reshape(-1,2,2).tolist())
        origin=transform([scan['camera']],self.pose)[0].tolist();self.global_origins.extend([origin for _ in local])
        self.global_body_origins.extend([self.pose[:2].tolist() for _ in local]);self.global_pose_covariances.extend([self.covariance.tolist() for _ in local])
        event.update(pose=self.pose.tolist(),covariance=self.covariance.tolist())
        return self.pose.tolist(),event
