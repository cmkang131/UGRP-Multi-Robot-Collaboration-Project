"""One fresh S2 DEV in-hand RGB probe, registered separately from exploration."""
from harness import zone_s2_realism_contract_v118 as previous
from harness import zone_s2_realism_contract_v119 as site
from harness import idle_robot_contacts_contract as idle
from harness.python_source_closure import source_closure

old,ROOT=previous.old,previous.ROOT
BUNDLE_ID='zone-s2-realism-v120'
WORKFLOW_VERSION='7.13.0'
WORKFLOW='configs/simulation_workflows.d/s2_realism_v120.json'
PLAN='experiments/2026-10-06-s2-realism/registration-v120.json'
OPTIONS=previous.OPTIONS
NEW_OPTIONS={**site.NEW_OPTIONS,'site_check':'off','hold_check':'inhand_rgb_v1'}
MOTION_MODEL=previous.MOTION_MODEL


def bundle(source_sha,*,seed=None,stage_probe='pick',pickup_slot='P1-2',**options):
    if options.keys()-NEW_OPTIONS.keys():raise ValueError('unknown S2 option')
    requested={k:options.get(k,'off') for k in NEW_OPTIONS}
    if requested['hold_check'] not in ('off','inhand_rgb_v1'):raise ValueError('unsupported hold_check')
    if requested['site_check']!='off':raise ValueError('v120 selects one verifier; site_check must be off')
    out=previous.bundle(source_sha,seed=seed,stage_probe=stage_probe,pickup_slot=pickup_slot,
        **{k:requested[k] for k in previous.NEW_OPTIONS})
    out.update(schema='ugrp.s2_realism_bundle.v120',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,preregistered_run=requested['hold_check']!='off',
        registration_kind='s2-dev-probe',user_authorization='2026-10-06-grasp-reference-probe',
        dev_confirmation=True,confirmation_sample=False,result_condition='S2_DEV_freeze_inhand_rgb_v1',
        grasp_claim='PROBABLE_HELD visual evidence only; independent eval lift required',
        effective_grasp_verifier=requested['hold_check'],pickup_site_comparison=False)
    out['options'].update(requested)
    out['idle_robot_contacts_policy']={**idle.policy(),
        'dev_registration_exception':'2026-10-06 explicit user fresh-seed reference-based S2 DEV probe',
        'forbidden':['S3','pair_transport','research','research_preregistered_run']}
    idle.validate(out)
    paths=set(out['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v120.py','scripts/run_s2_realism_v120.py',
        'harness/zone_solo_cyan_inhand.py']))
    paths.update((WORKFLOW,PLAN,'experiments/2026-10-06-s2-realism/launch_v120.zsh'))
    out['source_sha256']={p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    out.pop('bundle_sha256',None);out['bundle_sha256']=old.hp.base.digest(out)
    return out


def require_execution(value):
    idle.validate(value)
    if any(value['options'].get(k)!=v for k,v in NEW_OPTIONS.items()):
        raise ValueError('v120 needs all explicit S2 DEV options')
    plan=old.hp.base.read(ROOT/PLAN)
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
        and r['stage']==value['stage_probe'] for r in plan['dev_runs']):
        raise ValueError('unregistered v120 seed/stage/slot')
