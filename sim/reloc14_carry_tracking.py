"""Default-off AMCL tracking from authored task prior, own RGB/issued deltas.

Known initial pose is the EXISTING declared task instruction, not a scene read.
Nav2's known-initial-pose Gaussian PF initialization is followed by unchanged
.25m/.2rad motion/new-pan measurement updates. No cargo state or top input.
"""
import math
import os
import numpy as np
from harness.natural_floor_slam import compose


class CarryTracker:
    def __init__(self,static,start):
        from harness.e2e_static_rgb_localizer import create
        from harness.self_map_landmark_sensor import Sensor
        allowed={'map_id','version','frame','bounds_m','obstacles','regions','passages'}
        self.static={k:static[k] for k in allowed}
        choice=os.environ.get('UGRP_RELOC16_CARRY_WALL_FIELD','off')
        if choice not in ('off','static_walls_v1'):raise ValueError('UNKNOWN_CARRY_WALL_FIELD')
        if choice!='off':
            from harness.active_wall_vision import modules
            from harness.reloc16_floor_mask import PROFILE,ENV,OPTION
            from harness.scene_colour_boundary import RELOC16_OPTION
            state=getattr(modules()[1],'scene_colour_state',None)
            if state is None or state.profile!=PROFILE or state.option!=RELOC16_OPTION or os.environ.get(ENV,'off')!=OPTION:raise ValueError('CARRY_WALL_FIELD_REQUIRES_FIXED_V5')
        self.wall_field=choice!='off'
        self.pf=create(self.static,option='static_walls_v1' if self.wall_field else 'static_landmarks_v1',seed=5064)
        if self.wall_field:
            # Existing Nav2/Probabilistic Robotics wall likelihood field. Keep
            # the colour map for observed feature records; sensor_landmarks=off
            # means those colours are not multiplied into particle weights.
            from harness.own_map_amcl_vendor.landmarks import MapFeatures
            self.pf.landmark_map=MapFeatures(self.static)
        sigma=[start['sigma_xy_m']]*2+[start['sigma_yaw_rad']]
        self.pf.px=np.asarray(start['pose_m_rad'])+self.pf.rng.normal(size=(self.pf.n,3))*sigma
        self.sensor=Sensor(self.pf.landmark_map.hues)
        self.pending=np.zeros(3);self.servo=None;self.servo_since=None;self.last_frame=-math.inf
        self.last=dict(state='task_instruction_prior',sensor_updates=0)

    def issue(self,issued,delta):
        self.pending=compose(self.pending,delta)
        servo={int(k):int(v) for k,v in issued['pwm'].items()}
        if servo!=self.servo:self.servo_since=issued['t']
        self.servo=servo

    def observe(self,rgb,now):
        from harness.selfmap4_geometry import observe
        # Selfmap's native settle and 5Hz capture conditions, not new wall caps.
        if not self.servo or now-self.last_frame<.2-1e-8:return None
        held=self.servo.get(1,2000)<=1600
        # servo_camera_fk explicitly has no qualified loaded extrinsics.
        # Keep prediction while closed; obtain metric fixes after set-down/open.
        # Do not change the servo command or pretend an unloaded camera model.
        settled=not held and now-self.servo_since>=.25
        packet=observe(rgb,self.servo,self.sensor,reloc9_wall_height_guard_v1=True) if settled else dict(features=[],segments=[])
        from harness.self_map_csm import sample_segments
        row=self.pf.step(t=now,delta=self.pending,servo=self.servo,
            points=sample_segments(packet['segments']),features=packet['features'])
        self.pending=np.zeros(3);self.last_frame=now
        P=np.asarray(row['covariance'])
        accepted=bool(settled and row['updated'] and row['resolved'] and row['cluster']['mass']>=.9 and
            np.linalg.eigvalsh(P[:2,:2]).max()<=.15**2 and P[2,2]<=math.radians(5)**2)
        self.last=dict(**({'reloc16_wall_field':'static_walls_v1','colour_likelihood_used':False} if self.wall_field else {}),state='TRACKING' if accepted else 'prediction_or_unresolved',
            updated=row['updated'],accepted=accepted,pose=row['pose'],covariance=row['covariance'],
            cluster=row['cluster'],sensor_updates=row['updates'],feature_N=len(packet['features']),
            input='own_rgb_static_geometry_issued_commands',budget_kind='2000_particles_motion_gate',settled=settled,
            camera_admission='loaded_or_unknown_prediction_only' if held else 'unloaded_fk')
        return (np.asarray(row['pose']),P) if accepted else None
