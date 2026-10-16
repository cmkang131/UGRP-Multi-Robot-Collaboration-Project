"""Matched seed1051 recovery-only full DEV, admitted by own-record replay."""
import copy
from harness import zone_s2_realism_contract_v128 as previous
from harness.python_source_closure import source_closure

old, ROOT = previous.old, previous.ROOT
BUNDLE_ID = 'zone-s2-realism-v129'
WORKFLOW_VERSION = '7.22.0'
WORKFLOW = 'configs/simulation_workflows.d/s2_realism_v129.json'
PLAN = 'experiments/2026-10-06-s2-realism/registration-v129.json'
CRITERIA = 'experiments/2026-10-06-s2-realism/slip-recovery-criteria.json'
REPLAY = 'experiments/2026-10-06-s2-realism/slip-recovery-replay.json'
NEW_OPTIONS = {**previous.NEW_OPTIONS, 'slip_recovery': 'slip_recovery_v1'}


def bundle(source_sha, **kwargs):
    recovery = kwargs.pop('slip_recovery', 'off')
    if recovery not in ('off', NEW_OPTIONS['slip_recovery']):
        raise ValueError('unknown slip_recovery')
    out = previous.bundle(source_sha, **kwargs)
    out.update(schema='ugrp.s2_realism_bundle.v129', execution_bundle_id=BUNDLE_ID,
               workflow_version=WORKFLOW_VERSION, result_condition='S2_DEV_slip_recovery_matched_seed1051',
               recovery_replay_admission_pass=old.hp.base.read(ROOT/REPLAY)['admission_pass'])
    out['options']['slip_recovery'] = recovery
    paths = set(out['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s2_realism_contract_v129.py', 'scripts/run_s2_realism_v129.py']))
    paths.update((WORKFLOW, PLAN, CRITERIA, REPLAY,
                  'experiments/2026-10-06-s2-realism/launch_v129.zsh'))
    out['source_sha256'] = {p: old.hp.base.sha(ROOT/p) for p in sorted(paths)}
    out.pop('bundle_sha256', None)
    out['bundle_sha256'] = old.hp.base.digest(out)
    return out


def require_execution(value):
    previous.validate_idle(value)
    if value.get('execution_bundle_id') != BUNDLE_ID:
        raise ValueError('v129 only')
    plan = old.hp.base.read(ROOT/PLAN)
    if value['options'] != plan['options']:
        raise ValueError('v129 exact slip baseline plus recovery only')
    baseline = copy.deepcopy(value)
    baseline['execution_bundle_id'] = previous.BUNDLE_ID
    baseline['schema'] = 'ugrp.s2_realism_bundle.v128'
    baseline['options'].pop('slip_recovery')
    previous.require_execution(baseline)
    for path, key in ((CRITERIA,'recovery_criteria_sha256'), (REPLAY,'recovery_replay_sha256'),
                      ('harness/zone_solo_cyan_slip_recovery.py','recovery_source_sha256')):
        if old.hp.base.sha(ROOT/path) != plan[key]:
            raise ValueError('recovery differs from registered replay')
    replay = old.hp.base.read(ROOT/REPLAY)
    if not value['recovery_replay_admission_pass'] or not replay['admission_pass']:
        raise ValueError('recovery replay gate failed')
    if replay['candidate_sha256'] != plan['recovery_source_sha256']:
        raise ValueError('replayed recovery source changed')
