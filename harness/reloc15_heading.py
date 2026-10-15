"""Relative own-RGB yaw during carry; no metric loaded FK or cargo pose.

Reuses the existing S2 homography decomposition, all cheirality-valid solutions
and its fixed feature/pixel/pitch uncertainty parameters. It is a DEV candidate,
not a qualified loaded camera model. No new acceptance/tuning constants.
"""
import math
from types import SimpleNamespace
import numpy as np
from harness.natural_floor_slam import wrap


def commanded_rotation(servo):
    # Only rotational extrinsics from the fixed v3 chain and issued PWM. This
    # never calls or weakens the unloaded-only metric camera FK admission.
    from harness.servo_camera_fk import commanded_joints,model,fixed_transform,axis_rotation
    _,joints=commanded_joints(servo);R=np.eye(3)
    for link in model()['chain']:
        R=R@fixed_transform(link)[:3,:3]
        if 'servo' in link:
            a=joints[link['servo']]
            if not link['range_rad'][0]<=a<=link['range_rad'][1]:
                raise ValueError('command target outside joint range')
            R=R@axis_rotation(link['joint_axis'],a)
    return R@fixed_transform(model()['camera'])[:3,:3]@np.diag([1.,-1.,-1.])


class Heading:
    def __init__(self, *, sample_s=.2):
        # R2 .1s = native 10Hz command clock/user recording cadence. At
        # saved failure p95/max yaw speed16.87/17.99deg/s this spans1.69/1.80deg
        # instead of3.37/3.60deg at .2s, below existing5deg task target.
        if sample_s not in (.1,.2):raise ValueError('native 10Hz/5Hz only')
        self.sample_s=sample_s
        self.previous=None;self.delta_yaw=0.;self.servo=None;self.servo_since=None
        self.last_measurement_t=None;self.accepted=0;self.last=dict(category='no_pair')

    def issue(self,issued,delta):
        pwm={int(k):int(v) for k,v in issued['pwm'].items()}
        if pwm!=self.servo:self.servo_since=issued['t']
        self.servo=pwm;self.delta_yaw+=delta[2]

    def observe(self,rgb,now,own):
        # Existing carry-tracker/VO 5Hz observation and loaded settle 2.25s.
        from harness.e2e_rgb_vo import PARAMS
        if self.previous is not None and now-self.previous['t']<self.sample_s-1e-8:return
        held=self.servo is not None and self.servo[1]<=1600
        good=held and now-self.servo_since>=PARAMS['settle_s'][1]
        old=self.previous
        self.previous=dict(rgb=rgb.copy(),t=now,pwm=self.servo,yaw=float(own.x[2]),variance=float(own.P[2,2]))
        command_yaw=self.delta_yaw;self.delta_yaw=0.
        self.last=dict(category='weak_observation',blocked_object='own_rgb_background',minimum_gap_m=None,
            gap_status='not_applicable_localization_gate',exposure_sim_t=now,sample_s=self.sample_s,
            last_measurement_t=self.last_measurement_t,command_yaw_rad=command_yaw)
        if not good or old is None or old['pwm']!=self.servo:
            self.last['category']='servo_unsettled_or_no_pair';return
        from harness.zone_solo_cyan_rotation_envelope import yaw_measurement
        cm=SimpleNamespace(_rot=commanded_rotation(self.servo))
        observation=yaw_measurement(old['rgb'],rgb,cm,self.servo,None)
        self.last.update(observation)
        if observation['status']!='measured':return
        # Replace this pair's command yaw exactly once. Preserve xy and its
        # epoch; relative yaw is not an absolute metric RGB fix.
        own.x[2]=wrap(own.x[2]+observation['delta_yaw']-command_yaw)
        own.P[2,2]=max(float(own.P[2,2]),old['variance']+observation['sigma_yaw']**2)
        self.previous['yaw']=float(own.x[2]);self.previous['variance']=float(own.P[2,2])
        self.last_measurement_t=now;self.accepted+=1
        self.last.update(category='relative_rgb_yaw',last_measurement_t=now,accepted_N=self.accepted,
            correction_rad=wrap(observation['delta_yaw']-command_yaw),
            metric_fix_refreshed=False,source='own_rgb_static_background_homography',
            camera_scope='nominal_rotation_only_loaded_unqualified',replay_count=1)
