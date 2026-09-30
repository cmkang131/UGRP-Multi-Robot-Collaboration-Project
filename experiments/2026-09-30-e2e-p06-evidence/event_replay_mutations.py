"""In-memory negative controls. Each mutation must cause assertion failures.

Never changes production files, raw records, installed packages or host locks.
"""
import inspect
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[variable] = '1'
for module in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
    sys.modules[module] = None

import pytest
from harness import zone_referee_replay as replay
from harness import zone_study_referee as zr
from scripts import zone_study_evidence_contract as contract
from scripts import zone_study_evidence_cohort as cohort
from scripts.tensorboard_tools import zone_study as study
from scripts.tensorboard_tools.export import Writer

D = 'tests/test_review_303d.py::'
R = 'tests/test_zone_referee_replay.py::'
O = 'tests/test_zone_referee_ownership.py::'
MUTATIONS = {
    'late_prefix': (contract, contract.verify_referee_derivations,
        "bounded = replay.replay(referee['events'], record['orders'], pin,\n                            evidence_key=evidence_key, source_key=source_key, cutoff=cutoff)",
        'bounded = full', D + 'test_late_redelivery_cannot_resurrect_a_departed_delivery'),
    'policy_pin': (replay, replay.validate_policy,
        'if not isinstance(pin, dict) or digest(pin) != digest(policy()):',
        'if False:', R + 'test_changed_loaded_policy_is_refused_not_silently_reinterpreted'),
    'code_pin': (replay, replay.validate_policy,
        'if not isinstance(pin, dict) or digest(pin) != digest(policy()):',
        'if False:', R + 'test_changed_code_hash_requires_a_new_plan'),
    'settle_window': (zr.Referee, zr.Referee.observe,
        "if t - cand['since'] >= SETTLE_S - 1e-9:",
        "if t - cand['since'] >= 0.:", R + 'test_full_settle_window_restarts_on_interruptions'),
    'summary_trust': (contract, contract.verify_referee_derivations,
        'if key not in rebuilt or digest(actual) != digest(expected):',
        'if False:', 'tests/test_review_303c.py::test_conflicting_referee_state_is_invalid[referee_verdict]'),
    'eager_tensorboard': (Writer, Writer.__init__,
        'self.path = path', 'import tensorboard\n        self.path = path',
        R + 'test_lazy_writer_needs_no_tensorboard_until_an_event'),
    'event_key': (replay, replay.replay,
        "if trial_key(row.get('evidence_key')) != expected:", 'if False:',
        O + 'test_foreign_key_cannot_replay_into_another_trial[event]'),
    'source_key': (replay, replay.replay,
        'if trial_key(source_key) != expected:', 'if False:',
        O + 'test_foreign_key_cannot_replay_into_another_trial[source]'),
    'rejected_owner': (cohort, cohort.collect,
        '# Rejection cannot erase the source\'s owners or assign it elsewhere.',
        "affected = [i for i, r in enumerate(admitted) if r['key']['run_id'] == source.name] or range(len(admitted))",
        'tests/test_review_303e.py::test_invalidating_duplicate_replay_cannot_increase_cohort_success'),
    'owner_union': (cohort, cohort.source_owners,
        'if unknown or not owners else owners', 'if unknown or not owners else {min(owners)}',
        O + 'test_key_source_disagreement_invalidates_both_trials'),
    'manifest_key': (study, study.export_study,
        "source_key = sources['eval_only/referee.json']['evidence_key']",
        'source_key = join.key_for(identity)',
        O + 'test_key_source_disagreement_invalidates_both_trials[False-manifest]'),
    'seal_rekey': (contract, contract.seal_new_evidence,
        'referee.setdefault(field, value)', 'referee[field] = value',
        O + 'test_sealing_never_rekeys_foreign_or_rejected_raw[envelope]'),
}


def main():
    import textwrap
    name = sys.argv[1]
    owner, function, old, new, selector = MUTATIONS[name]
    source = inspect.getsource(function)
    assert source.count(old) == 1, 'Mutation location drifted'
    namespace = dict(function.__globals__)
    exec(compile(textwrap.dedent(source.replace(old, new)), '<replay mutation ' + name + '>', 'exec'), namespace)
    mutated = namespace[function.__name__]
    setattr(owner, function.__name__, mutated)
    if owner is contract and function.__name__ == 'verify_referee_derivations':
        study.verify_referee_derivations = mutated
    print('Mutation:', name, 'selector:', selector, flush=True)
    return pytest.main(['-q', selector, *sys.argv[2:]])


if __name__ == '__main__':
    raise SystemExit(main())
