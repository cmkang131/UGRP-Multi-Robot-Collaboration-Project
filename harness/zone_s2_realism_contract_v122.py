"""One full solo S2 DEV: unknown grasp evidence is log-only, never success."""
from harness import zone_s2_realism_contract_v118 as previous
from harness import zone_s2_realism_contract_v121 as probe
from harness import idle_robot_contacts_contract as idle
from harness.python_source_closure import source_closure
old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v122'
WORKFLOW_VERSION='7.15.0'
WORKFLOW='configs/simulation_workflows.d/s2_realism_v122.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v122.json'
OPTIONS=previous.OPTIONS
NEW_OPTIONS={**probe.NEW_OPTIONS,'pulse_motion_model':'v7_pulse_cal_v1'}
PULSE_MODEL='configs/s2_motion_v7_pulse_cal_v1.json'
MOTION_MODEL=previous.MOTION_MODEL


def bundle(source_sha,*,seed=None,stage_probe='place',pickup_slot='P1-2',**options):
    if options.keys()-NEW_OPTIONS.keys():raise ValueError('unknown S2 option')
    requested={k:options.get(k,'off') for k in NEW_OPTIONS}
    for k in ('hold_check','dev_grasp_policy','eval_camera_trace','pulse_motion_model'):
        if requested[k] not in ('off',NEW_OPTIONS[k]):raise ValueError('unsupported '+k)
    if requested['site_check']!='off':raise ValueError('full DEV uses the in-hand verifier')
    out=previous.bundle(source_sha,seed=seed,stage_probe=stage_probe,pickup_slot=pickup_slot,
        **{k:requested[k] for k in previous.NEW_OPTIONS})
    out.update(schema='ugrp.s2_realism_bundle.v122',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,preregistered_run=requested['dev_grasp_policy']!='off',
        registration_kind='s2-dev-full',user_authorization='2026-10-07-s2-full-dev-light',
        dev_confirmation=False,confirmation_sample=False,result_condition='S2_DEV_freeze_v7_pulse_cal_v1',
        grasp_claim='own RGB evidence, including unknown, is log-only; success is eval-only',
        effective_grasp_verifier=requested['hold_check'],pickup_site_comparison=False)
    out['options'].update(requested)
    out['pulse_calibration']=old.hp.base.read(ROOT/PULSE_MODEL) if requested['pulse_motion_model']!='off' else None
    out['effective_motion_model']=requested['pulse_motion_model'] if requested['pulse_motion_model']!='off' else requested['dead_reckoning']
    out['motion_calibration']='S2 finite pulse exploratory fit, selected explicitly; legacy model superseded only when pulse option ON'
    out['idle_robot_contacts_policy']={**idle.policy(),
        'dev_registration_exception':'Explicit user full-route S2 DEV, seed recorded before execution',
        'forbidden':['S3','pair_transport','research','research_preregistered_run']}
    idle.validate(out)
    paths=set(out['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v122.py','scripts/run_s2_realism_v122.py']))
    paths.update((WORKFLOW,PLAN,PULSE_MODEL,'experiments/2026-10-06-s2-realism/launch_v122.zsh'))
    out['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    out.pop('bundle_sha256',None);out['bundle_sha256']=old.hp.base.digest(out)
    return out


def require_execution(value):
    idle.validate(value)
    if any(value['options'].get(k)!=v for k,v in NEW_OPTIONS.items()):
        raise ValueError('v122 needs all explicit S2 DEV options')
    plan=old.hp.base.read(ROOT/PLAN)
    if old.hp.base.sha(ROOT/PULSE_MODEL)!=plan['pulse_model_sha256']:raise ValueError('pulse model differs from registration')
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
        and r['stage']==value['stage_probe'] for r in plan['dev_runs']):
        raise ValueError('unregistered v122 seed/stage/slot')
