"""S2-only look-ahead pose with measured stiff-arm RGB target extrinsics."""
import copy
from harness.zone_solo_cyan_real_carry import LOOK_AHEAD,LOOK_AHEAD_OPTION
from harness.zone_solo_cyan_slip_recovery import Runtime as Previous
from harness.s2_stiff_camera_calibration import runtime_class
from harness.zone_final_pair_camera import floor_camera
from harness.zone_pair_highpose import HIGH_SETTLE_S

Base=runtime_class(Previous)


def validate(table):
    if (table.get('schema')!='ugrp.s2.look_ahead_calibration.v1' or table.get('fit_uses_gt') is not False
            or table.get('servo_stiffness')!='real_v1' or table.get('admission_pass') is not True
            or table.get('pose_key')!='1050,2035,1894,1500'):
        raise ValueError('measured look-ahead calibration required')
    if table['pitch_difference_deg']>.5 or table['bilateral_fraction']<.99:
        raise ValueError('look-ahead physical gate failed')
    for state in ('unloaded','loaded'):
        if table['quality'][state]['holdout']['rms_px']>1:raise ValueError('look-ahead target holdout failed')
        floor_camera(table['camera_models'][state])


class Runtime(Base):
    def __init__(self,*args,carry_pose='off',look_ahead_calibration=None,**kwargs):
        if carry_pose==LOOK_AHEAD_OPTION:
            validate(look_ahead_calibration or {})
            if kwargs.get('camera_pitch')!='stiff_target_v1' or kwargs.get('servo_stiffness')!='real_v1':
                raise ValueError('look-ahead requires explicit stiff plant and calibration')
        self.look_ahead_since=None
        super().__init__(*args,carry_pose=carry_pose,**kwargs)
        if carry_pose!=LOOK_AHEAD_OPTION:return
        table=copy.deepcopy(look_ahead_calibration);inner=self.pose.provider;pf=inner.loc._pf
        for state in ('unloaded','loaded'):
            inner.calibration['camera_models'][state][table['pose_key']]=table['camera_models'][state]
        old_settled=pf.settled
        def settled(now):
            if pf.load.loaded and all(inner.servo.get(s)==v for s,v in LOOK_AHEAD.items()):
                return (type(pf).settled(pf,now) and self.look_ahead_since is not None
                        and now-self.look_ahead_since>=HIGH_SETTLE_S)
            return old_settled(now)
        pf.settled=settled
        from harness.zone_solo_cyan_v106 import hp
        receipt=dict(option=LOOK_AHEAD_OPTION,table_sha256=hp.base.digest(table),runtime_gt=False,
                     loaded_measured=True,servo_stiffness='real_v1',mount_fov_changed=False)
        inner.calibration['s2_look_ahead']=receipt;inner.runtime_contract['s2_look_ahead']=receipt
        inner.identity_sha256=hp.base.digest(inner.runtime_contract)
        inner.source='owncam_pf_s2_look_ahead:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def on_command(self,rid,now,action):
        super().on_command(rid,now,action)
        if self.carry_pose==LOOK_AHEAD_OPTION and rid==self.robot_id:
            if not all(self.servo.get(s)==v for s,v in LOOK_AHEAD.items()):self.look_ahead_since=None
            elif self.look_ahead_since is None:self.look_ahead_since=now

    def visual_pose_supported(self,servo):
        return (self.carry_pose==LOOK_AHEAD_OPTION and all(servo.get(s)==v for s,v in LOOK_AHEAD.items())) or super().visual_pose_supported(servo)

    def record(self):
        out=super().record()
        if self.carry_pose==LOOK_AHEAD_OPTION:
            out['look_ahead_calibration']=copy.deepcopy(self.pose.provider.calibration['s2_look_ahead'])
            out['carry_pose'].update(runtime_admitted=True,loaded_camera='RGB target calibrated with stiff arm, both loads',
                loaded_motion='unchanged v122; controlled ablation found free load difference below 0.55%',
                visual_stall='own look-ahead RGB; unchanged LK/slip logic',scope='S2 single-box DEV only')
        return out
