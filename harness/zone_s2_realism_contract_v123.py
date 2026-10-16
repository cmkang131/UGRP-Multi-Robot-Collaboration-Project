"""Fresh S2 DEV admission for scan isolation and visual stall logging."""
from harness import zone_s2_realism_contract_v122 as previous
from harness.python_source_closure import source_closure
old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v123'
WORKFLOW_VERSION='7.16.0'
WORKFLOW='configs/simulation_workflows.d/s2_realism_v123.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v123.json'
PULSE_MODEL=previous.PULSE_MODEL
MOTION_MODEL=previous.MOTION_MODEL
NEW_OPTIONS={**previous.NEW_OPTIONS,'visual_update':'accepted_scan_v1','visual_stall':'lk_pulse_v1'}


def bundle(source_sha,**kwargs):
    options={k:kwargs.pop(k,'off') for k in ('visual_update','visual_stall')}
    for k,v in options.items():
        if v not in ('off',NEW_OPTIONS[k]):raise ValueError('unsupported '+k)
    out=previous.bundle(source_sha,**kwargs)
    out.update(schema='ugrp.s2_realism_bundle.v123',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,result_condition='S2_DEV_freeze_accepted_scan_lk_pulse_v1')
    out['options'].update(options)
    out['visual_policy']='S2 loaded HIGH only; existing gate before weights; RGB stall log only; calibration unchanged'
    paths=set(out['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v123.py','scripts/run_s2_realism_v123.py']))
    paths.update((WORKFLOW,PLAN,'experiments/2026-10-06-s2-realism/launch_v123.zsh'))
    out['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    previous.idle.validate(out)
    out.pop('bundle_sha256',None);out['bundle_sha256']=old.hp.base.digest(out)
    return out


def require_execution(value):
    previous.idle.validate(value)
    if value['options'].get('carry_pose', 'off') != 'off':
        raise ValueError('real carry pose is an offline candidate, not admitted in v123')
    if any(value['options'].get(k)!=v for k,v in NEW_OPTIONS.items()):raise ValueError('v123 requires all explicit S2 options')
    plan=old.hp.base.read(ROOT/PLAN)
    if old.hp.base.sha(ROOT/PULSE_MODEL)!=plan['pulse_model_sha256']:raise ValueError('pulse model differs from registration')
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
        and r['stage']==value['stage_probe'] for r in plan['dev_runs']):raise ValueError('unregistered v123 seed/stage/slot')
