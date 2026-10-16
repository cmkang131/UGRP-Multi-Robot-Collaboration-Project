"""Opt-in fixed MJWarp command response, never live simulator feedback.

The calibration is exploratory, one clean start per posture/direction. A
prediction is not a measured movement. Mapping still requires visual updates.
"""
import math
import numpy as np

OPTION='mapbuild4_pulse_prediction_v1'


class PulsePrediction:
    def __init__(self,calibration,*,option='off'):
        if option!=OPTION:raise ValueError('EXPLICIT_MJWPULSE_PREDICTION_REQUIRED')
        if calibration['physics_backend']!='mjwarp':raise ValueError('MJWARP_CALIBRATION_REQUIRED')
        self.profiles=calibration['profiles'];self.active=None;self.t=0.

    def advance(self,t):
        if t<self.t:raise ValueError('NON_CAUSAL_COMMAND_TIME')
        delta=np.zeros(3)
        if self.active is not None:
            start,p=self.active;curve=np.asarray(p['curve'])
            response=lambda s:np.asarray([np.interp(s,p['times'],curve[:,i]) for i in range(3)])
            a,b=response(max(0.,self.t-start)),response(max(0.,t-start))
            d=b-a;c,s=math.cos(a[2]),math.sin(a[2]);delta=np.r_[[c*d[0]+s*d[1],-s*d[0]+c*d[1]],d[2]]
        self.t=t;return delta

    def issue(self,row):
        if row['t']!=self.t:raise ValueError('ADVANCE_BEFORE_ISSUE')
        key=f"drive:{row['axis']}:{row['value']:.2f}:{row['duration_s']:.2f}"
        if key not in self.profiles:raise ValueError('UNMEASURED_PULSE:'+key)
        self.active=(self.t,self.profiles[key])
