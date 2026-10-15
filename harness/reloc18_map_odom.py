"""Optional global map correction with continuous own-command odometry.

ROS REP105 and Nav2 AMCL calculateMaptoOdomTransform: global correction is
map->odom; it must not rewrite the continuous odom->base trajectory.
No simulator or evaluator input is accepted. Uses the same empirical Q/R,
nominal DOF3/alpha.01 and original correlation interval as reloc18 R2.
"""
import math
import numpy as np
from harness.natural_floor_slam import compose,_motion_covariance
from harness.selfmap4_geometry import inverse
from harness.reloc18_innovation import calibration,fuse

OPTION='reloc18_map_odom_v1'

class MapOdomFilter:
    def __init__(self,fit=None):
        self.fit=fit or calibration();self.x=None;self.P=None
        self.odom=None;self.t=None;self.last_fused_t=-math.inf;self.initial_rotation=None

    def step(self,*,t,odom,local_pose,world_pose,measurement_covariance,fresh,registered):
        odom,local_pose=np.asarray(odom,float),np.asarray(local_pose,float)
        Rfloor=np.asarray(self.fit['measurement_covariance_world'])
        if self.x is None:
            if not registered:return None,dict(status='awaiting_registered_map_pose')
            self.x=np.asarray(world_pose,float).copy();self.P=np.asarray(measurement_covariance)+Rfloor
            self.odom=odom.copy();self.t=float(t);self.last_fused_t=float(t)
            a=compose(self.x,inverse(local_pose))[2];c,s=math.cos(a),math.sin(a)
            self.initial_rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])
            decision=dict(accepted=True,reason='initialize_from_registered_RGB_once')
        else:
            if t<=self.t:raise ValueError('CAUSAL_MAP_ODOM_TIME_REQUIRED')
            delta=compose(inverse(self.odom),odom);dt=t-self.t
            qworld=self.initial_rotation@np.asarray(self.fit['command_covariance_per_sim_s'])@self.initial_rotation.T*dt
            a=self.x[2];c,s=math.cos(a),math.sin(a);body=np.array([[c,s,0],[-s,c,0],[0,0,1]])
            self.P=_motion_covariance(self.x,delta,self.P,body@qworld@body.T);self.x=compose(self.x,delta)
            decision=dict(accepted=False,reason='motion_prediction')
            if fresh and t-self.last_fused_t>=self.fit['measurement_correlation_sim_s']:
                decision=fuse(self.x,world_pose,self.P,np.asarray(measurement_covariance)+Rfloor,threshold=self.fit['chi2_threshold'])
                if decision['accepted']:
                    self.x=np.asarray(decision['posterior_pose']);self.P=np.asarray(decision['posterior_covariance']);self.last_fused_t=float(t)
            elif fresh:decision=dict(accepted=False,reason='correlated_measurement_thinned')
            self.odom,self.t=odom.copy(),float(t)
        anchor=compose(self.x,inverse(local_pose))
        return anchor,dict(option=OPTION,world_pose=self.x.tolist(),world_covariance=self.P.tolist(),
            map_from_odom=anchor.tolist(),local_pose_unchanged=True,last_fused_t=self.last_fused_t,decision=decision,
            category=decision['reason'],blocked_object='own_rgb_map_pose',minimum_gap_m=None,gap_scope='not_applicable_localization_gate')
