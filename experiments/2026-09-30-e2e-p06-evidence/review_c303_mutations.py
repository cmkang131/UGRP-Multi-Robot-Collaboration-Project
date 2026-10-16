"""Run one production mutation in memory; the selected regression MUST fail.

Usage: python experiments/2026-09-30-e2e-p06-evidence/review_c303_mutations.py
       <name> --junitxml=<output.xml>
No source/raw file is overwritten; no world, network or inference is loaded.
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

import pytest  # noqa: E402
from scripts import zone_study_evidence_contract as contract  # noqa: E402
from scripts import zone_study_evidence_join as join  # noqa: E402
from scripts.tensorboard_tools import zone_study as study  # noqa: E402

PREFIX = 'tests/test_review_303c.py::'
MUTATIONS = {
    'optional_count_bypass': (
        contract.verify_referee_derivations,
        "    if not isinstance(referee, dict):",
        "    if 'departures' not in evaluation and 'departed_unsettled_items' not in evaluation:\n"
        "        return ev.efficiency_metrics(record)\n    if not isinstance(referee, dict):",
        PREFIX + 'test_failed_referee_cannot_back_a_success_when_counts_are_missing'),
    'dispatch_content_bypass': (
        join.validate_internal,
        "if (row_key(row, identity, oid or TRIAL_SCOPE) != dispatch_key",
        "if False and (row_key(row, identity, oid or TRIAL_SCOPE) != dispatch_key",
        PREFIX + 'test_raw_action_and_camera_receipts_must_match_the_call[dispatch_order]'),
    'input_content_bypass': (
        join.validate_internal,
        "if (digest(refs) != digest([frame]) or not images",
        "if False and (digest(refs) != digest([frame]) or not images",
        PREFIX + 'test_raw_action_and_camera_receipts_must_match_the_call[input_frame]'),
    'missing_table_bypass': (
        join.validate_internal,
        "if (consumers or complete_relations) and name not in auxiliary:",
        "if False and (consumers or complete_relations) and name not in auxiliary:",
        PREFIX + 'test_raw_action_and_camera_receipts_must_match_the_call[missing_dispatch]'),
    'canonical_sort_bypass': (
        join.canonical_referee_rows,
        "return sorted(rows, key=sort_key)",
        "for row in rows:\n        sort_key(row)\n    return list(rows)",
        PREFIX + 'test_reordered_simultaneous_referee_rows_preserve_valid_success'),
}


def main():
    name = sys.argv[1]
    function, old, new, selector = MUTATIONS[name]
    source = inspect.getsource(function)
    assert source.count(old) == 1, 'Mutation location drifted; no test was run'
    namespace = dict(function.__globals__)
    exec(compile(source.replace(old, new), f'<C303 mutation {name}>', 'exec'), namespace)
    mutated = namespace[function.__name__]
    owner = contract if function is contract.verify_referee_derivations else join
    setattr(owner, function.__name__, mutated)
    if owner is contract:
        study.verify_referee_derivations = mutated
    print(f'Mutation {name}: only {function.__module__}.{function.__name__}', flush=True)
    return pytest.main(['-q', selector, *sys.argv[2:]])


if __name__ == '__main__':
    raise SystemExit(main())
