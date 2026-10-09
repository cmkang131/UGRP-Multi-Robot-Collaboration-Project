"""One same-seed matched closed-loop DEV despite failed replay gates."""
from harness import zone_s2_realism_contract_v126 as previous
from harness.python_source_closure import source_closure
from harness.idle_robot_contacts_contract import validate as validate_idle

old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v128'
WORKFLOW_VERSION='7.21.0'
WORKFLOW='configs/simulation_workflows.d/s2_realism_v128.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v128.json'
EXTRINSIC,FLOOR=previous.EXTRINSIC,previous.FLOOR
PULSE_MODEL,MOTION_MODEL=previous.PULSE_MODEL,previous.MOTION_MODEL
CRITERIA='experiments/2026-10-06-s2-realism/slip-detect-criteria.json'
REPLAY='experiments/2026-10-06-s2-realism/slip-detect-summary.json'
NEW_OPTIONS={**previous.NEW_OPTIONS,'slip_detection':'slip_detect_v1','stall_recovery':'off'}


def bundle(source_sha,**kwargs):
    new={k:kwargs.pop(k,'off') for k in ('slip_detection','stall_recovery')}
    for k,v in new.items():
        if v not in ('off',NEW_OPTIONS[k]):raise ValueError('unsupported '+k)
    out=previous.bundle(source_sha,**kwargs)
    plan=old.hp.base.read(ROOT/PLAN)
    out.update(schema='ugrp.s2_realism_bundle.v128',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,result_condition='S2_DEV_slip_matched_seed1051',
        intentional_deviation=plan['intentional_deviation'],
        user_decision=plan['user_decision'],replay_admission_pass=False)
    out['options'].update(new)
    out['motion_calibration']='s1051 fixed pulse model; slip-only own RGB displacement substitution; no new fitting'
    paths=set(out['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v128.py','scripts/run_s2_realism_v128.py']))
    paths.update((WORKFLOW,PLAN,CRITERIA,REPLAY,
        'experiments/2026-10-06-s2-realism/launch_v128.zsh'))
    out['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    validate_idle(out)
    out.pop('bundle_sha256',None);out['bundle_sha256']=old.hp.base.digest(out)
    return out


def require_execution(value):
    validate_idle(value)
    if value.get('execution_bundle_id')!=BUNDLE_ID or value.get('stage_probe')!='place':
        raise ValueError('v128 full S2 DEV only')
    plan=old.hp.base.read(ROOT/PLAN)
    if value['options']!=plan['options']:raise ValueError('v128 requires exact registered options')
    deviation=plan['intentional_deviation']
    if (not deviation['approved'] or deviation['replay_admission_pass'] is not False
            or deviation['full_runs_authorized']!=1 or value.get('intentional_deviation')!=deviation
            or value.get('replay_admission_pass') is not False):
        raise ValueError('explicit administrator deviation required; replay must remain failed')
    for path,key in ((PULSE_MODEL,'pulse_model_sha256'),(EXTRINSIC,'extrinsic_sha256'),
            (FLOOR,'floor_appearance_sha256'),(CRITERIA,'criteria_sha256'),(REPLAY,'replay_summary_sha256'),
            ('harness/zone_solo_cyan_slip_detect.py','slip_source_sha256'),
            ('harness/zone_solo_cyan_pulse_cal.py','pulse_predictor_sha256')):
        if old.hp.base.sha(ROOT/path)!=plan[key]:raise ValueError('source/calibration differs from v128 registration')
    if value['extrinsic_calibration']!=old.hp.base.read(ROOT/EXTRINSIC):raise ValueError('embedded camera table changed')
    previous.approximate(value['extrinsic_calibration'])
    if value.get('floor_appearance')!=old.hp.base.read(ROOT/FLOOR):raise ValueError('embedded appearance changed')
    replay=old.hp.base.read(ROOT/REPLAY)
    if replay['admission_pass'] is not False or sorted(k for k,v in replay['gates'].items() if not v)!=sorted(deviation['failed_gates']):
        raise ValueError('original failed replay gates changed')
    baseline=old.hp.base.read(ROOT/previous.REPLAY)
    if not baseline['admission_pass'] or old.hp.base.sha(ROOT/'harness/zone_solo_cyan_floor_contact.py')!=baseline['results'][1]['candidate_sha256']:
        raise ValueError('adopted floor filter differs from passing replay')
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
               and r['stage']==value['stage_probe'] for r in plan['dev_runs']):
        raise ValueError('unregistered v128 seed/stage/slot')

    if value['task'] != plan['baseline_task']:
        raise ValueError('matched run requires identical baseline task')
    for path,digest in plan['shared_source_checks'].items():
        if old.hp.base.sha(ROOT/path)!=digest:
            raise ValueError('shared behavior changed from registered matched baseline: '+path)
