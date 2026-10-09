"""v145: default-on driving for new DEV runs; completed v143 stays historical."""
import copy

from harness import zone_s2_heading_contract as previous
from harness.path_heading_policy import DEFAULT, VISUAL_LOCK, mode_for_bundle
from harness.python_source_closure import source_closure

ROOT = previous.ROOT
BUNDLE_ID = 'zone-s2-realism-v145'
VERSION = '7.38.0'
WORKFLOW = 'configs/simulation_workflows.d/path_heading_v145.json'
PLAN = 'experiments/2026-10-09-s2-heading/default-on/registration.json'


def bundle(sha, seed, *, heading_mode=DEFAULT, heading_visual_lock='off'):
    mode_for_bundle(dict(options=dict(heading_mode=heading_mode)))
    if heading_visual_lock not in ('off', VISUAL_LOCK):
        raise ValueError('unknown heading_visual_lock')
    if heading_mode == 'off' and heading_visual_lock != 'off':
        raise ValueError('visual lock requires heading')
    b = copy.deepcopy(previous.bundle(sha, seed, heading_mode=DEFAULT))
    b['options'].update(heading_mode=heading_mode, heading_visual_lock=heading_visual_lock)
    b.update(schema='ugrp.s2_realism_bundle.v145', execution_bundle_id=BUNDLE_ID,
        workflow_version=VERSION, result_condition='DEV_shared_heading_default_v145',
        heading_mode=heading_mode, heading_visual_lock=heading_visual_lock,
        dev_preregistration=dict(path=PLAN, sha256=previous.old.old.base.sha(ROOT/PLAN),
            fresh=False, graduation=False, automatic_physical_runs=0),
        default_decision='user 2026-10-09: heading default on for new runs',
        prior_physical_results_inherited=False)
    paths = set(b['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_path_heading_contract.py', 'scripts/run_path_heading.py']))
    paths.update((WORKFLOW, PLAN))
    b['source_sha256'] = {p: previous.old.old.base.sha(ROOT/p) for p in sorted(paths)}
    b.pop('bundle_sha256', None)
    b['bundle_sha256'] = previous.old.old.base.digest(b)
    return b


def require_execution(b):
    previous.old.old.validate(b)
    if b != bundle(b['source_sha'], b['task']['seed'],
                   heading_mode=b['options']['heading_mode'],
                   heading_visual_lock=b['options']['heading_visual_lock']):
        raise ValueError('v145 source/options mismatch')
