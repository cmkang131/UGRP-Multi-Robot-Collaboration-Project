"""s2v58 v139 + one bounded active sensing option; four explicit DEV seeds."""
import json
from harness import zone_s2_unknown_start_contract as old
from harness.zone_solo_cyan_active_observation import OPTION
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
ROOT=old.ROOT
PLAN=ROOT/'experiments/2026-10-06-s2-realism/active-observation-registration.json'
BUNDLE_ID='zone-s2-realism-v140'
VERSION='7.33.0'
NEW_OPTIONS={**old.NEW_OPTIONS,'active_localization':OPTION}


def registration():
    active=json.loads(PLAN.read_text());plan=old.registration()
    plan.update(seeds=active['physical_seeds'],user_decision='2026-10-09 bounded active discriminating views; no prior')
    return plan


def bundle(sha,seed,*,active_localization='off'):
    if active_localization not in ('off',OPTION):raise ValueError('unknown active_localization')
    b=bind(old.bundle,registration=registration,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,PLAN=PLAN)(sha,seed,**old.NEW_OPTIONS)
    b['options']['active_localization']=active_localization
    b.update(schema='ugrp.s2_realism_bundle.v140',result_condition='S2_DEV_active_observation_v140',
        baseline_reference=dict(bundle=old.BUNDLE_ID,prior_present=False,success_not_inherited=True))
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['harness/zone_s2_active_observation_contract.py','scripts/run_s2_active_observation.py']))
    paths.add('configs/simulation_workflows.d/s2_active_observation_v140.json')
    paths.add('experiments/2026-10-06-s2-realism/active-observation-offline-result.json')
    b['source_sha256']={p:old.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256',None);b['bundle_sha256']=old.base.digest(b)
    return b


def require_execution(b):
    old.validate(b)
    result=json.loads((ROOT/'experiments/2026-10-06-s2-realism/active-observation-offline-result.json').read_text())
    if not result['passed'] or result['preregistration_sha256']!=old.base.sha(PLAN):raise ValueError('offline gate required')
    if b!=bundle(b['source_sha'],b['task']['seed'],active_localization=OPTION):raise ValueError('exact v140 configuration required')
