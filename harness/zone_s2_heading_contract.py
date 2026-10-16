"""Three matched DEV comparisons, not a repeat graduation or fresh cohort."""
import json

from harness import zone_s2_graduation59_contract as old
from harness.zone_solo_cyan_path_heading import OPTION, PARAMS
from harness.python_source_closure import source_closure

ROOT = old.ROOT
BUNDLE_ID = 'zone-s2-realism-v143'
VERSION = '7.36.0'
PLAN = ROOT / 'experiments/2026-10-09-s2-heading/registration.json'


def bundle(sha, seed, *, heading_mode='off'):
    if heading_mode not in ('off', OPTION):
        raise ValueError('unknown heading_mode')
    plan = json.loads(PLAN.read_text())
    if seed not in plan['seeds']:
        raise ValueError('only three matched DEV seeds admitted')
    b = old.bundle(sha, seed, **old.NEW_OPTIONS)
    if heading_mode == 'off':
        return b  # v141 bundle too is byte-identical when disabled.
    b['options']['heading_mode'] = heading_mode
    for key in ('graduation_run', 'supervised_pair_benchmark'):
        b.pop(key, None)
    b.update(schema='ugrp.s2_realism_bundle.v143', execution_bundle_id=BUNDLE_ID,
        workflow_version=VERSION, result_condition='S2_DEV_path_heading_matched_v143',
        baseline_reference=dict(bundle=old.BUNDLE_ID, sha=plan['baseline_sha'],
            prior_present=False, success_not_inherited=True, matched_seed=seed),
        heading_parameters=PARAMS,
        dev_preregistration=dict(path=str(PLAN.relative_to(ROOT)),
            sha256=old.old.base.sha(PLAN), seeds=plan['seeds'], denominator=3,
            fresh=False, graduation=False))
    paths = set(b['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s2_heading_contract.py', 'scripts/run_s2_heading.py']))
    paths.update([str(PLAN.relative_to(ROOT)), 'configs/simulation_workflows.d/s2_heading_v143.json'])
    b['source_sha256'] = {p: old.old.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256', None)
    b['bundle_sha256'] = old.old.base.digest(b)
    return b


def require_execution(b):
    old.old.validate(b)
    if b != bundle(b['source_sha'], b['task']['seed'], heading_mode=OPTION):
        raise ValueError('exact three-run heading DEV configuration required')
