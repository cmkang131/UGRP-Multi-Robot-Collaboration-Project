"""S2 one-run DEV integration: real carry + RGB-PnP empty table + fixed sag.

Only immutable target calibration and own commands/RGB enter this module.
New camera, visibility, visual update and LK scope are local to this Runtime.
All options off preserves the earlier command/record path. Loaded sag and the
HIGH pulse-model transfer are explicit approximations, not new measurements.
"""
import copy
import numpy as np
from harness.zone_solo_cyan_real_carry import Runtime as CarryRuntime, CARRY, at_carry
from harness.zone_solo_cyan_likelihood_field import Runtime as MeasurementRuntime
from harness import zone_solo_cyan_camera_v3 as camera
from harness.zone_final_pair_camera import floor_camera
from harness import zone_pair_highpose as high
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D

OPTION = 'v3_unloaded_sag_v1'
SAG_DELTA_RAD = -.02711


def approximate(table):
    if (table.get('schema') != 'ugrp.s2_camera_unloaded_sag.v1' or table.get('option') != OPTION
            or table.get('fit_uses_gt') is not False or table.get('runtime_gt') is not False
            or table.get('measured_loaded') is not False or table.get('load_qualified') is not False):
        raise ValueError('unloaded RGB-PnP plus explicit unqualified sag provenance required')
    if (not np.array_equal(table['intrinsics_K'],scaled_camera_matrix(640,480))
            or not np.array_equal(table['fisheye_D'],CAMERA_FISHEYE_D)):
        raise ValueError('camera intrinsics changed')
    if table['sag_approximation']['delta_rad'] != SAG_DELTA_RAD:
        raise ValueError('fixed sag differs from registration')
    empty = table['camera_models']['unloaded']
    if '600,2200,1400,1500' not in empty:
        raise ValueError('real carry pose missing from measured empty table')
    if table['extension']['quality']['holdout']['rms_px'] > 1.:
        raise ValueError('real carry calibration holdout rejected')
    models = {state:copy.deepcopy(empty) for state in ('loaded','unloaded')}
    c,s = np.cos(SAG_DELTA_RAD),np.sin(SAG_DELTA_RAD)
    delta = np.array([[1,0,0],[0,c,-s],[0,s,c]])
    for record in models['loaded'].values():
        record['rotation'] = (np.asarray(record['rotation']) @ delta).tolist()
    for poses in models.values():
        for record in poses.values():floor_camera(record)
    return models


def apply(source,table):
    models = approximate(table)
    inner=source.provider;pf=inner.loc._pf;cal=inner.calibration
    cal['camera_models'].clear();cal['camera_models'].update(models)
    cal['pan_base_yaw'].clear();cal['pan_base_yaw'].update(copy.deepcopy(table['pan_base_yaw']))
    old_settled=pf.settled;old_command=inner.on_command
    state={'since':None}
    def command(row):
        old_command(row)
        if not at_carry(inner.servo):state['since']=None
        elif state['since'] is None:state['since']=float(row['t'])
    def settled(now):
        if pf.load.loaded and at_carry(inner.servo):
            return (type(pf).settled(pf,now) and state['since'] is not None
                    and now-state['since'] >= high.HIGH_SETTLE_S)
        return old_settled(now)
    inner.on_command=command
    # FailClosedLoc retains the callback object captured in its constructor.
    inner.loc._on_command=command
    pf.settled=settled
    receipt=dict(option=OPTION,table_sha256=camera.legacy.hp.base.digest(table),
        loaded_measured=False,sag_delta_rad=SAG_DELTA_RAD,runtime_gt=False,
        scope='S2 DEV loaded HIGH and real_delivery_v1; transit predict only',
        source='unloaded RGB-PnP; fixed optical-right-axis sag; no height adjustment')
    cal['s2_extrinsic_calibration']=receipt
    inner.runtime_contract['s2_extrinsic_calibration']=receipt
    inner.m1_calibration['s2_extrinsic_calibration']=copy.deepcopy(receipt)
    return source


class Runtime(CarryRuntime, MeasurementRuntime):
    def __init__(self,*args,camera_calibration='off',extrinsic_calibration=None,
                 provider_factory=None,**kwargs):
        if camera_calibration not in ('off',OPTION):raise ValueError('unsupported camera_calibration')
        self.camera_calibration=camera_calibration
        if camera_calibration!='off':
            if kwargs.get('camera_profile')!=camera.camera.PROFILE_ID:
                raise ValueError('real carry extrinsics require explicit camera v3')
            table=copy.deepcopy(extrinsic_calibration or {});approximate(table)
            base=provider_factory or camera.build_provider
            def factory(*a,**k):
                src=base(*a,**k)
                try:return apply(src,table)
                except Exception:src.close();raise
            factory.controller_geometry_id=base.controller_geometry_id
            factory.uses_landmark_tags=False
            kwargs['provider_factory']=factory
        elif provider_factory is not None:kwargs['provider_factory']=provider_factory
        super().__init__(*args,**kwargs)
        if camera_calibration!='off':
            inner=self.pose.provider
            inner.runtime_contract['s2_real_carry_dev']=dict(carry_pose=self.carry_pose,
                camera_calibration=camera_calibration,loaded_motion='frozen HIGH pulse profile transferred, unqualified',
                user_authorization='2026-10-07-one-full-S2-DEV',conservative_stops='log only')
            inner.identity_sha256=camera.legacy.hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_real_carry_dev:'+inner.identity_sha256[:8];self.pose.source=inner.source
            if self.measurement_model!='off':self.soft_measurement['scope']='S2 loaded HIGH or real_delivery_v1'

    def visual_pose_supported(self,servo):
        return (super().visual_pose_supported(servo) or
                (self.camera_calibration!='off' and at_carry(servo)))

    def event(self,name,now,**fields):
        if name=='real_delivery_carry_pose' and self.camera_calibration!='off':
            fields['camera_calibration']=OPTION
            fields['settle_s']=high.HIGH_SETTLE_S
            self.arm.until=now+high.HIGH_SETTLE_S
        return super().event(name,now,**fields)

    def record(self):
        out=super().record()
        if self.camera_calibration!='off':
            out['camera_calibration']=copy.deepcopy(self.pose.provider.calibration['s2_extrinsic_calibration'])
            if 'carry_pose' in out:
                out['carry_pose'].update(scope='S2 single full DEV',runtime_admitted=True,
                    loaded_camera=OPTION,visual_stall='LK log only, own real carry RGB enabled')
            if 'visual_update' in out:
                out['visual_update'].update(scope='S2 loaded HIGH and real_delivery_v1',calibration_unchanged=False,
                    measurement_isolation='AMCL+visibility replaces loaded hard gate; missing/rejected visibility is predict only')
            if 'visual_stall' in out:out['visual_stall']['scope']='S2 carry at HIGH or real_delivery_v1'
        return out
