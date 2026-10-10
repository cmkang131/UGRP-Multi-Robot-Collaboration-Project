"""Next S2 DEV profile; freeze must be explicit, no probe admitted by this change."""
from harness import zone_s2_realism_contract_v117 as previous
from harness import idle_robot_contacts_contract as idle
from harness.python_source_closure import source_closure

old = previous.old
ROOT = previous.ROOT
BUNDLE_ID = 'zone-s2-realism-v118'
WORKFLOW_VERSION = '7.11.0'
WORKFLOW = 'configs/simulation_workflows.d/s2_realism_v118.json'
PLAN = 'experiments/2026-10-06-s2-realism/dev-profile-v118.json'
OPTIONS = previous.OPTIONS
NEW_OPTIONS = {**previous.NEW_OPTIONS, 'idle_robot_contacts': 'freeze_v1'}
MOTION_MODEL = previous.MOTION_MODEL


def bundle(source_sha, *, seed=None, stage_probe='pick', pickup_slot='P1-2', **options):
    unknown = options.keys()-NEW_OPTIONS.keys()
    if unknown:
        raise ValueError('unknown S2 options: '+str(sorted(unknown)))
    requested = {k: options.get(k,'off') for k in NEW_OPTIONS}
    # Reuse the frozen behavior contract and its static task vocabulary, without
    # reusing its consumed seed1042 as an execution admission.
    out = previous.bundle(source_sha,seed=1042,stage_probe='pick',pickup_slot='P1-2',
                          **{k:requested[k] for k in previous.NEW_OPTIONS})
    if seed is not None and (type(seed) is not int or seed <= 0):
        raise ValueError('seed must be a positive integer or absent in a preview')
    if stage_probe not in ('pick','place'):
        raise ValueError('unknown S2 stage')
    from harness.zone_own_contract import pickup_slots
    if pickup_slot not in pickup_slots(old.hp.resolve(old.MAP_ID)[0]):
        raise ValueError('unknown pickup slot')
    out['task'].update(seed=seed,pickup_slot=pickup_slot)
    out.update(schema='ugrp.s2_realism_bundle.v118',execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION,stage_probe=stage_probe,scenario='S2',transport='solo',
        cargo='cyan',active_robot_ids=[out['task']['robot_id']],admission='dev-pilot',
        preregistered_run=False,idle_robot_contacts_policy=idle.policy(),
        result_condition='S2_DEV_idle_contacts_'+requested['idle_robot_contacts'],
        pool_with_previous_s2=False,comparison_metrics=['wall_per_sim'])
    out['options'].update(requested)
    idle.validate(out)
    paths = set(out['source_sha256']) | set(source_closure(ROOT,[
        'harness/zone_s2_realism_contract_v118.py','scripts/run_s2_realism_v118.py','sim/s2_idle_contacts.py']))
    paths.update((WORKFLOW,PLAN,'sim/assets/masterpi_drive_friction_v7_sphere6/source.json'))
    out['source_sha256'] = {p:old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    out.pop('bundle_sha256',None)
    out['bundle_sha256'] = old.hp.base.digest(out)
    return out


def require_execution(value):
    idle.validate(value)
    if any(value['options'].get(k) != v for k,v in NEW_OPTIONS.items()):
        raise ValueError('S2 v118 DEV requires all explicit profile options, including freeze_v1')
    profile = old.hp.base.read(ROOT/PLAN)
    if value['task']['seed'] in profile['excluded_existing_seeds']:
        raise ValueError('S2_EXISTING_OR_PREREGISTERED_SEED_FORBIDDEN')
    if type(value['task']['seed']) is not int or value['task']['seed'] <= 0:
        raise ValueError('NO_S2_DEV_RUN_ADMITTED: preview has no executable seed')
    if not any(r['seed']==value['task']['seed'] and r['slot']==value['task']['pickup_slot']
               and r['stage']==value['stage_probe'] and r.get('preregistered_run') is False
               for r in profile['dev_runs']):
        raise ValueError('NO_S2_DEV_RUN_ADMITTED: next probe pending; no consumed or preregistered seed reuse')
