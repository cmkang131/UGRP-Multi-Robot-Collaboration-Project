"""User-authorized one full real-carry S2 DEV; all integrations explicit."""
from harness import zone_s2_realism_contract_v123 as previous
from harness.python_source_closure import source_closure
from harness.zone_solo_cyan_real_carry_dev import approximate
old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v124'
WORKFLOW_VERSION='7.17.0'
WORKFLOW='configs/simulation_workflows.d/s2_realism_v124.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v124.json'
EXTRINSIC='configs/calibration/s2_camera_v3_unloaded_sag_v1.json'
PULSE_MODEL=previous.PULSE_MODEL
MOTION_MODEL=previous.MOTION_MODEL
NEW_OPTIONS={**previous.NEW_OPTIONS,'carry_pose':'real_delivery_v1',
    'camera_calibration':'v3_unloaded_sag_v1','measurement_model':'amcl_likelihood_field_v1',
    'visibility_mask':'command_geometry_v1'}


def bundle(source_sha,**kwargs):
    new={k:kwargs.pop(k,'off') for k in ('carry_pose','camera_calibration','measurement_model','visibility_mask')}
    for k,v in new.items():
        if v not in ('off',NEW_OPTIONS[k]):raise ValueError('unsupported '+k)
    out=previous.bundle(source_sha,**kwargs)
    out.update(schema='ugrp.s2_realism_bundle.v124',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,result_condition='S2_DEV_real_carry_v3_PnP_fixed_sag_visibility',
        user_decision='2026-10-07 run once despite failed old-trajectory geometry gate')
    out['options'].update(new)
    out['extrinsic_calibration']=old.hp.base.read(ROOT/EXTRINSIC) if new['camera_calibration']!='off' else None
    if out['extrinsic_calibration'] is not None:approximate(out['extrinsic_calibration'])
    out['visual_policy']='own RGB mask -> missing columns isolated -> AMCL soft weights; no hard residual veto in loaded admitted views; LK log only'
    out['motion_calibration']='frozen S2 pulse model transferred from HIGH to real carry; no new fit, unqualified transfer'
    paths=set(out['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v124.py','scripts/run_s2_realism_v124.py']))
    paths.update(('experiments/2026-10-06-s2-realism/analyze_visibility.py',WORKFLOW,PLAN,EXTRINSIC,'experiments/2026-10-06-s2-realism/launch_v124.zsh'))
    out['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    previous.previous.idle.validate(out)
    out.pop('bundle_sha256',None);out['bundle_sha256']=old.hp.base.digest(out)
    return out


def require_execution(value):
    previous.previous.idle.validate(value)
    if value.get('execution_bundle_id')!=BUNDLE_ID or value.get('stage_probe')!='place':
        raise ValueError('v124 full S2 DEV only')
    if any(value['options'].get(k)!=v for k,v in NEW_OPTIONS.items()):
        raise ValueError('v124 requires every explicit requested option')
    plan=old.hp.base.read(ROOT/PLAN)
    for path,key in ((PULSE_MODEL,'pulse_model_sha256'),(EXTRINSIC,'extrinsic_sha256')):
        if old.hp.base.sha(ROOT/path)!=plan[key]:raise ValueError('calibration differs from v124 registration')
    if value['extrinsic_calibration']!=old.hp.base.read(ROOT/EXTRINSIC):
        raise ValueError('embedded camera table changed')
    approximate(value['extrinsic_calibration'])
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
               and r['stage']==value['stage_probe'] for r in plan['dev_runs']):
        raise ValueError('unregistered v124 seed/stage/slot')
