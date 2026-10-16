"""Explicit three-seed S2 no-start-information DEV admission, v139."""
import copy
import json
from pathlib import Path

from harness.zone_pair_highpose_contract import base
from harness.python_source_closure import source_closure
from harness.idle_robot_contacts_contract import validate

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'experiments/2026-10-06-s2-realism/unknown-start-registration.json'
BUNDLE_ID = 'zone-s2-realism-v139'
VERSION = '7.32.0'
NEW_OPTIONS = dict(start_prior='none_v1', global_localization='augmented_active_v1',
                   particle_sampling='kld_global_v1')


def registration():
    return json.loads(PLAN.read_text())


def bundle(sha, seed, *, start_prior='off', global_localization='off', particle_sampling='off'):
    plan = registration()
    if seed not in plan['seeds']:
        raise ValueError('only the three preregistered fresh seeds are admitted')
    options = dict(start_prior=start_prior, global_localization=global_localization,
                   particle_sampling=particle_sampling)
    for key, value in options.items():
        if value not in ('off', NEW_OPTIONS[key]):
            raise ValueError('unknown ' + key)
    path = ROOT / plan['template']
    if base.sha(path) != plan['template_sha256']:
        raise ValueError('v133 template changed')
    b = json.loads(path.read_text())
    b['options'] = {**copy.deepcopy(plan['baseline_options']), **options}
    b['task']['seed'] = seed
    b.update(schema='ugrp.s2_realism_bundle.v139', execution_bundle_id=BUNDLE_ID,
        workflow_version=VERSION, source_sha=sha, start_proof=None,
        result_condition='S2_DEV_unknown_start_v139', pool_with_previous_s2=False,
        known_start_information=start_prior != 'none_v1', replay_admission_pass=None,
        dev_preregistration=dict(path=str(PLAN.relative_to(ROOT)), sha256=base.sha(PLAN),
            user_authorization=plan['user_decision'], seeds=plan['seeds']),
        baseline_reference=dict(bundle='zone-s2-realism-v133', sha=plan['baseline_source_sha'],
            success_not_inherited=True, prior_present=True))
    paths = set(b['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s2_unknown_start_contract.py', 'scripts/run_s2_unknown_start.py']))
    paths.update([str(PLAN.relative_to(ROOT)), plan['template'],
        'configs/simulation_workflows.d/s2_unknown_start_v139.json'])
    b['source_sha256'] = {p: base.sha(ROOT / p) for p in sorted(paths)}
    b.pop('bundle_sha256', None)
    b['bundle_sha256'] = base.digest(b)
    return b


def require_execution(b):
    validate(b)
    if b != bundle(b['source_sha'], b['task']['seed'], **NEW_OPTIONS):
        raise ValueError('exact preregistered no-prior full configuration required')
