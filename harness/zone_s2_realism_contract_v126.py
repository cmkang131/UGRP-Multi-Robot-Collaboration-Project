"""User-authorized one full real-carry S2 DEV; all integrations explicit."""
from harness import zone_s2_realism_contract_v125 as previous
from harness.python_source_closure import source_closure
from harness.zone_solo_cyan_real_carry_dev import approximate
old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v126'
WORKFLOW_VERSION='7.19.0'
WORKFLOW='configs/simulation_workflows.d/s2_realism_v126.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v126.json'
EXTRINSIC='configs/calibration/s2_camera_v3_unloaded_sag_v1.json'
CRITERIA='experiments/2026-10-06-s2-realism/contact-filter-criteria.json'
REPLAY='experiments/2026-10-06-s2-realism/contact-filter-summary.json'
FLOOR='configs/calibration/s2_floor_appearance_v1.json'
PULSE_MODEL=previous.PULSE_MODEL
MOTION_MODEL=previous.MOTION_MODEL
NEW_OPTIONS={**previous.NEW_OPTIONS,'carry_pose':'real_delivery_v1',
    'camera_calibration':'v3_unloaded_sag_v1','measurement_model':'amcl_likelihood_field_v1',
    'visibility_mask':'command_geometry_v1','visibility_policy':'nav2_observed_v1','contact_filter':'floor_appearance_v1'}


def bundle(source_sha,**kwargs):
    new={k:kwargs.pop(k,'off') for k in ('visibility_policy','contact_filter')}
    for k,v in new.items():
        if v not in ('off',NEW_OPTIONS[k]):raise ValueError('unsupported '+k)
    out=previous.bundle(source_sha,**kwargs)
    out.update(schema='ugrp.s2_realism_bundle.v126',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,result_condition='S2_DEV_observed_AMCL_fixed_floor_appearance',
        user_decision='2026-10-07 contact-filter RMSE replay passed before one fresh full DEV')
    out['options'].update(new)
    out['floor_appearance']=old.hp.base.read(ROOT/FLOOR) if new['contact_filter']!='off' else None
    out['extrinsic_calibration']=old.hp.base.read(ROOT/EXTRINSIC) if out['options']['camera_calibration']!='off' else None
    if out['extrinsic_calibration'] is not None:approximate(out['extrinsic_calibration'])
    out['visual_policy']='observed RGB self mask, fixed floor appearance exclusion, unchanged Nav2 cubic field/motion/resampling; no prior visibility veto or GT'
    out['motion_calibration']='frozen S2 pulse model transferred from HIGH to real carry; no new fit, unqualified transfer'
    paths=set(out['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v126.py','scripts/run_s2_realism_v126.py']))
    paths.update(('experiments/2026-10-06-s2-realism/analyze_visibility.py',WORKFLOW,PLAN,EXTRINSIC,CRITERIA,REPLAY,FLOOR,'experiments/2026-10-06-s2-realism/launch_v126.zsh'))
    out['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    previous.previous.previous.previous.idle.validate(out)
    out.pop('bundle_sha256',None);out['bundle_sha256']=old.hp.base.digest(out)
    return out


def require_execution(value):
    previous.previous.previous.previous.idle.validate(value)
    if value.get('execution_bundle_id')!=BUNDLE_ID or value.get('stage_probe')!='place':
        raise ValueError('v126 full S2 DEV only')
    if any(value['options'].get(k)!=v for k,v in NEW_OPTIONS.items()):
        raise ValueError('v126 requires every explicit requested option')
    plan=old.hp.base.read(ROOT/PLAN)
    for path,key in ((PULSE_MODEL,'pulse_model_sha256'),(EXTRINSIC,'extrinsic_sha256'),(FLOOR,'floor_appearance_sha256'),(CRITERIA,'criteria_sha256'),(REPLAY,'replay_summary_sha256')):
        if old.hp.base.sha(ROOT/path)!=plan[key]:raise ValueError('calibration differs from v126 registration')
    if value['extrinsic_calibration']!=old.hp.base.read(ROOT/EXTRINSIC):
        raise ValueError('embedded camera table changed')
    approximate(value['extrinsic_calibration'])
    if value.get('floor_appearance')!=old.hp.base.read(ROOT/FLOOR):raise ValueError('embedded appearance table changed')
    replay=old.hp.base.read(ROOT/REPLAY)
    if not replay['admission_pass'] or replay['criteria']['candidate']!=value['options']['contact_filter']:
        raise ValueError('offline contact-filter admission failed')
    if old.hp.base.sha(ROOT/'harness/zone_solo_cyan_floor_contact.py')!=replay['results'][1]['candidate_sha256']:
        raise ValueError('candidate differs from passing offline replay')
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
               and r['stage']==value['stage_probe'] for r in plan['dev_runs']):
        raise ValueError('unregistered v126 seed/stage/slot')
