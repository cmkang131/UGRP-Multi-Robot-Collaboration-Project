"""S2-only fixed RGB-PnP extrinsics; default off preserves the v123 path."""
import copy
import numpy as np
from harness.zone_solo_cyan_visual_fix import Runtime as Previous
from harness import zone_solo_cyan_camera_v3 as camera
from harness.zone_final_pair_camera import floor_camera
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D

OPTION='v3_extrinsic_v1'


def validate(table):
    if table.get('status')=='PARTIAL_NO_LOADED_CALIBRATION' or table.get('load_qualified') is False:
        raise ValueError('LOADED_CAMERA_CALIBRATION_UNAVAILABLE')
    if (table.get('option')!=OPTION or table.get('schema')!='ugrp.s2_camera_extrinsics.v1'
        or table.get('status')!='MEASURED_SIM_RGB_PNP_LEVEL_FIXTURE'
        or table.get('load_qualified') is not True
        or table.get('fit_uses_gt') is not False or table.get('runtime_gt') is not False):
        raise ValueError('RGB PnP calibration provenance required')
    if not np.array_equal(table['intrinsics_K'],scaled_camera_matrix(640,480)) or not np.array_equal(table['fisheye_D'],CAMERA_FISHEYE_D):
        raise ValueError('camera intrinsics differ')
    for state in ('unloaded','loaded'):
        if not table['camera_models'].get(state):raise ValueError('both load states required')
        for rec in table['camera_models'][state].values():floor_camera(rec)
    return table


def apply(source, table):
    table=copy.deepcopy(validate(table));inner=source.provider;cal=inner.calibration
    for state,poses in cal['camera_models'].items():
        if not set(poses)<=set(table['camera_models'][state]):raise ValueError('required camera pose missing')
    # PF closure, observer factory and CyanVision all retain this dictionary.
    cal['camera_models'].clear();cal['camera_models'].update(table['camera_models'])
    cal['pan_base_yaw'].clear();cal['pan_base_yaw'].update(table['pan_base_yaw'])
    receipt=dict(option=OPTION,table_sha256=camera.legacy.hp.base.digest(table),
        status=table['status'],intrinsics_changed=False,runtime_gt=False)
    cal['s2_extrinsic_calibration']=receipt
    inner.runtime_contract['s2_extrinsic_calibration']=receipt
    inner.identity_sha256=camera.legacy.hp.base.digest(inner.runtime_contract)
    inner.source='owncam_pf_s2_'+OPTION+':'+inner.identity_sha256[:8];source.source=inner.source
    return source


class Runtime(Previous):
    def __init__(self,*args,camera_calibration='off',extrinsic_calibration=None,provider_factory=None,**kwargs):
        if camera_calibration not in ('off',OPTION):raise ValueError('unsupported camera_calibration')
        self.camera_calibration=camera_calibration
        if camera_calibration=='off':
            if provider_factory is not None:kwargs['provider_factory']=provider_factory
            super().__init__(*args,**kwargs)
            return
        if kwargs.get('camera_profile')!=camera.camera.PROFILE_ID:raise ValueError('extrinsics require camera v3')
        table=copy.deepcopy(validate(extrinsic_calibration or {}))
        base=provider_factory or camera.build_provider
        def factory(*a,**kw):
            source=base(*a,**kw)
            try:return apply(source,table)
            except Exception:source.close();raise
        factory.controller_geometry_id=base.controller_geometry_id
        factory.uses_landmark_tags=False
        super().__init__(*args,provider_factory=factory,**kwargs)

    def record(self):
        out=super().record()
        if self.camera_calibration!='off':out['camera_calibration']=copy.deepcopy(self.pose.provider.calibration['s2_extrinsic_calibration'])
        return out
