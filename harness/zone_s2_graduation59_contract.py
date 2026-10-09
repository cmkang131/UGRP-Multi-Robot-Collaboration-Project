"""s2v59 six fresh no-prior S2 DEV graduation samples; defaults remain off."""
import json
from harness import zone_s2_unknown_start_contract as old
from harness.zone_solo_cyan_active_observation import OPTION as ACTIVE
from harness.zone_solo_cyan_rotation_envelope import OPTION as GUARD
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

ROOT=old.ROOT
PLAN=ROOT/'experiments/2026-10-06-s2-realism/graduation59-registration.json'
PROOF='experiments/2026-10-06-s2-realism/rotation-envelope-offline-result.json'
BUNDLE_ID='zone-s2-realism-v141'
VERSION='7.34.0'
NEW_OPTIONS=dict(active_localization=ACTIVE,active_rotation_guard=GUARD)


def registration():
    result=old.registration();plan=json.loads(PLAN.read_text())
    result.update(seeds=plan['seeds'],user_decision=plan['user_decision'])
    return result


def bundle(sha,seed,*,active_localization='off',active_rotation_guard='off'):
    options=dict(active_localization=active_localization,active_rotation_guard=active_rotation_guard)
    if any(v not in ('off',NEW_OPTIONS[k]) for k,v in options.items()):
        raise ValueError('unknown v141 option')
    plan=json.loads(PLAN.read_text())
    b=bind(old.bundle,registration=registration,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,PLAN=PLAN)(sha,seed,**old.NEW_OPTIONS)
    slot=next(q['slot'] for q in plan['runs'] if q['seed']==seed)
    b['task']['pickup_slot']=slot
    b['options'].update(options)
    b.update(schema='ugrp.s2_realism_bundle.v141',result_condition='S2_DEV_graduation_v141',
        graduation_run=dict(seed=seed,slot=slot,stage='place',fresh=True),
        baseline_reference=dict(bundle='zone-s2-realism-v140',sha='e532f52e3df512e5fac8cef7654dc2ba06fa61b1',
            prior_present=False,success_not_inherited=True),
        timing_sensitive=False,supervised_pair_benchmark=plan['concurrency'])
    paths=set(b['source_sha256'])|set(source_closure(ROOT,[
        'harness/zone_s2_graduation59_contract.py','scripts/run_s2_graduation59.py']))
    paths.update([PROOF,'configs/simulation_workflows.d/s2_graduation_v141.json'])
    b['source_sha256']={p:old.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256',None);b['bundle_sha256']=old.base.digest(b)
    return b


def require_execution(b):
    old.validate(b)
    proof=json.loads((ROOT/PROOF).read_text())
    if not proof['passed'] or proof['parameters']['max_abs_deg']!=90:
        raise ValueError('unchanged 90deg offline gate required')
    if b!=bundle(b['source_sha'],b['task']['seed'],**NEW_OPTIONS):
        raise ValueError('exact preregistered v141 required')
