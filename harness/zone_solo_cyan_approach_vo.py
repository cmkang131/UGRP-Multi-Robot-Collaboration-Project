"""Default-off S2 own-ground SE2 for unladen coarse SEARCH translations.

Seegmiller/Wettergreen 2011 II-C--F, via the existing ground_vo_v1 primitive.
No contact/pose truth, no newly fit constant, no change to loaded slip checks.
"""
import copy
import numpy as np
from harness.zone_solo_cyan_slip_detect import SlipBuffer
from harness.zone_solo_cyan_ground_vo import GroundBuffer,camera_supported
from harness.zone_solo_cyan_pulse_cal import profile_key
from harness.zone_solo_cyan_bias_tempering import closure,replace_cell

OPTION='unloaded_coarse_vo_v1'
SEARCH={3:740,4:2320,5:1320,6:1500}
PARAMS=dict(pitch_scale_bound_deg=.3,minimum_expected_m=.05,
            max_track_gap_s=.15,complete_coverage=1.)


def eligible(inner,profile,now):
    return bool(profile is not None and not inner.loc._pf.load.loaded and
        not profile['loaded'] and profile['axis'] in ('forward','left') and
        np.linalg.norm(profile['mean_delta'][:2])>=PARAMS['minimum_expected_m'] and
        all(inner.servo.get(k)==v for k,v in SEARCH.items()) and
        inner.loc._pf.settled(now) and camera_supported(inner,inner.servo))


class ApproachBuffer(SlipBuffer):
    def command(self,row):
        moving=row['kind'] in ('mecanum','drive') and any(row.get(k,0) for k in ('forward','left','turn'))
        if self.pending is not None:
            if moving or row['kind'] in ('arm','look','initial_servo_command'):self.flush(False)
            else:
                self.pending['events'].append(('command',(copy.deepcopy(row),)));return
        pf=self.inner.loc._pf
        if moving:
            key=profile_key(row,pf.load.loaded);p=self.profiles.get(key)
            if eligible(self.inner,p,row['t']):
                if self.last is not None and abs(row['t']-self.last[0])<1e-7:
                    self.pending=dict(t=float(row['t']),key=key,profile=copy.deepcopy(p),
                        command=copy.deepcopy(row),pose=dict(self.inner.servo),
                        cm=pf.column_model_for(self.inner.servo),before=self.last,
                        frames=[],events=[('command',(copy.deepcopy(row),))],unloaded_coarse_vo=True)
                    return
                self.audit['rows'].append(dict(t=float(row['t']),key=key,
                    status='missing_before_frame',prediction_replaced=False,coverage=0.,
                    source='command_prediction_fallback',unloaded_coarse_vo=True))
        return super().command(row)

    def flush(self,completed=True):
        if self.pending is not None and self.pending.get('unloaded_coarse_vo'):
            n=len(self.audit['rows'])
            # Landmark capture is outside the historical loaded buffer. For
            # this new delayed path, replay each captured image at its own t;
            # otherwise all buffered observations would see the final image.
            previous=self.frame0
            self.frame0=getattr(self,'landmark_replay',previous)
            try:GroundBuffer.flush(self,completed)
            finally:self.frame0=previous
            for row in self.audit['rows'][n:]:row['unloaded_coarse_vo']=True
        else:super().flush(completed)


def attach(runtime,*,ground_motion='off',servo_stiffness='off'):
    if ground_motion=='off':return runtime
    if ground_motion!=OPTION:raise ValueError('unknown ground_motion')
    if servo_stiffness!='real_v1':raise ValueError('requires stiff calibrated S2 camera')
    old=runtime.flow
    if type(old) is not SlipBuffer:raise ValueError('requires original S2 slip buffer, no nested VO')
    inner=runtime.pose.provider
    outer=inner.on_frame
    if closure(outer).get('previous')!=old.frame:
        raise ValueError('requires original landmark frame capture wrapper')
    inner.on_command,inner.on_frame,inner.report=old.command0,old.frame0,old.report0
    selected=ApproachBuffer(inner,old.profiles,old.supported,old.table)
    selected.landmark_replay=replace_cell(outer,'previous',old.frame0)
    inner.on_frame=replace_cell(outer,'previous',selected.frame)
    selected.calibration=dict(pitch_scale_bound_deg=PARAMS['pitch_scale_bound_deg'])
    selected.audit.update(option=OPTION,parameters=copy.deepcopy(PARAMS),
        scope='unloaded coarse SEARCH ground SE2; loaded original slip_detect_v1',
        covariance='existing complete ground-VO SE2 fit + radial pitch scale; no command double count')
    runtime.flow=selected
    from harness.zone_solo_cyan_v106 import hp
    receipt=dict(option=OPTION,parameters=copy.deepcopy(PARAMS),gt_inputs=False)
    inner.runtime_contract['s2_approach_ground_motion']=receipt
    inner.identity_sha256=hp.base.digest(inner.runtime_contract)
    inner.source='owncam_pf_s2_approach_vo:'+inner.identity_sha256[:8];runtime.pose.source=inner.source
    previous=runtime.record
    runtime.record=lambda:{**previous(),'approach_ground_motion':copy.deepcopy(receipt)}
    return runtime
