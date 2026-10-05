"""Targeted in-memory mutations for the D1 review; no physics or model calls.

Run with the existing Python environment through run_ci_tests.run_locked.
Only test helpers and generated modules are loaded; production files stay intact.
"""
import importlib.util
from pathlib import Path
import sys
import types
import pytest

root = Path(__file__).resolve().parents[2]
def module_from(name, source):
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, name, 'exec'), module.__dict__)
    return module
spec = importlib.util.spec_from_file_location('d1_review_tests', root/'tests/test_stall_detector_d1.py')
tests = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tests
spec.loader.exec_module(tests)
source = (tests.HERE/'d1_evaluation.py').read_text()
mutants = [
 ('relax_30_to_24_and_drop_start_kind', source.replace('len(kinds) == 30 and all(kinds.count(k) == 6 for k in STALL_KINDS)', 'len(kinds) >= 24 and sum(kinds.count(k) > 0 for k in STALL_KINDS) >= 4'), lambda: tests.test_cohort_count_gate_requires_all_five_kinds_and_exact_30((6,6,6,6,0), 'INCOMPLETE')),
 ('onset_only_matching_ignores_recovery', source.replace('    return IntervalScore(tuple(events)', '    events = [EventScore(e.start_s, e.end_s, next((t for t in sorted(alarms) if t >= e.start_s), None), None) for e in events]\n    return IntervalScore(tuple(events)'), tests.test_alarm_after_recovery_is_false_alarm_not_detection),
]
for name, mutated, test in mutants:
    assert mutated != source
    module = module_from(name, mutated)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tests, 'evaluation', lambda: module)
        try:
            test()
        except AssertionError:
            print('KILLED', name)
        else:
            raise RuntimeError('SURVIVED '+name)
source = (tests.HERE/'d1_detector.py').read_text()
mutant = module_from('relax_95_to_80', source.replace('>= 19 * len(checks)', '>= 16 * len(checks)'))
with pytest.MonkeyPatch.context() as patch:
    patch.setattr(tests, 'd1', mutant)
    try:
        tests.test_exact_95_percent_boundary_keeps_all_scheduled_checks(patch, 3, 'INSUFFICIENT_COVERAGE')
    except AssertionError:
        print('KILLED relax_95_to_80')
    else:
        raise RuntimeError('SURVIVED relax_95_to_80')
original_read = Path.read_text
for name, token in [('omit_incomplete', 'INCOMPLETE'), ('omit_posthoc_freeze', '사후 선택 금지')]:
    with pytest.MonkeyPatch.context() as patch:
        def read(path, *args, **kwargs):
            text = original_read(path, *args, **kwargs)
            return text.replace(token, 'REMOVED') if path == tests.HERE/'PREREG_DRAFT.md' else text
        patch.setattr(Path, 'read_text', read)
        try:
            tests.test_preregistration_requires_exact_30_and_predata_freeze()
        except AssertionError:
            print('KILLED', name)
        else:
            raise RuntimeError('SURVIVED '+name)
print('5/5 targeted mutants killed; no production files changed')
