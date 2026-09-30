#!/usr/bin/env python3
"""Delete D1-D5 guards in isolated in-memory modules; never edit source/raw.

Each witness passes against the real module, then must raise AssertionError
against its mutant. Import/runtime exceptions are errors, not killed mutants.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load('mutation_builders', ROOT / 'tests/test_classify_review_299.py')
review = load('mutation_review', ROOT / 'tests/test_classify_review_299c.py')
contract = load('mutation_contract', ROOT / 'tests/test_v6h_recorder_contract.py')


def d1(cp):
    data, context = contract.public_record()
    out = cp.adjudicate_attempt(data['row'], data['result'], data['trace'], recorder_context=context)
    assert out['class'] == 'PASS_CLEAN' and out['evidence_valid'], 'D1 real producer must be accepted'


def d2(cp):
    row, result, trace = base.record()
    row.update(category='HOST_ERROR:ENOSPC', host_error='ENOSPC')
    result['termination']['outcome'] = 'HOST_ERROR'
    base.record_receipt(row, result, trace)
    out = cp.adjudicate_attempt(row, result, trace)
    assert out['class'] is None, 'D2 host is not a measured task failure'
    assert cp.classify_attempt_sequence([out])['class'] is None, 'D2 unresolved host must remain unclassified'


def d3(cp):
    row, result, trace = base.record()
    review.damage_handover(row, trace, 'no_release')
    row.update(category='HOST_ERROR:ENOSPC', host_error='cleanup')
    result['termination']['outcome'] = 'HOST_ERROR'
    base.record_receipt(row, result, trace)
    first = cp.adjudicate_attempt(row, result, trace)
    r, s, t = base.record()
    r['case_id'] += ':retry1'
    base.record_receipt(r, s, t)
    second = cp.adjudicate_attempt(r, s, t)
    assert cp.classify_attempt_sequence([first, second])['class'] not in cp.PASS, 'D3 completed failure is absorbing'


def contradiction(cp, kind):
    row, result, trace = base.record()
    review.contradict(row, result, trace, kind)
    base.record_receipt(row, result, trace)
    out = cp.adjudicate_attempt(row, result, trace)
    assert out['state'] == 'INVALID' and out['class'] is None, kind + ' must be INVALID'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be new')
    path = HERE / 'classify_placements.py'
    source = path.read_text()
    before = base.cp.sha256(path)
    deletions = {
        'D1_adapter': (d1, [('if recorder_context is not None:\n            recorder = rv.adapt',
                             'if False:\n            recorder = rv.adapt')]),
        'D2_host_accounting': (d2, [('state, outcome, reason = "HOST_SAFE", None,',
                                   'state, outcome, reason = "HOST_SAFE", "FAIL",')]),
        'D3_absorbing_handover': (d3, [('if completed_handover_failure(chain, trace):', 'if False:')]),
        'D4_source_gt': (lambda cp: contradiction(cp, 'endpoint_gt'),
                        [('            validate_source_to_derived(row, result)', '            pass  # deleted source check')]),
        'D4_host_copies': (lambda cp: contradiction(cp, 'result_host_error'),
                          [('            validate_source_to_derived(row, result)', '            pass  # deleted source check')]),
        'D5_teacher_window': (lambda cp: contradiction(cp, 'missing_teacher_prefix'),
                             [('if not EVALUATION_PROTOCOL["include_teacher"]:', 'if True:')]),
        'D5_contact_window': (lambda cp: contradiction(cp, 'impossible_contact_coverage'), [(
            '            or wall["start_sim_s"] < 0 or wall["end_sim_s"] <= wall["start_sim_s"]\n'
            '            or type(count) is not int or count < 2\n'
            '            or abs((count - 1) * period - (wall["end_sim_s"] - wall["start_sim_s"])) > period + 1e-9\n'
            '            or (count - 1) * wall["max_gap_s"] < wall["end_sim_s"] - wall["start_sim_s"] - 1e-9\n',
            '            or type(count) is not int or count < 2\n')]),
    }
    results = []
    for name, (witness, replacements) in deletions.items():
        witness(base.cp)
        mutated = source
        for old, new in replacements:
            assert mutated.count(old) == 1, name
            mutated = mutated.replace(old, new)
        module = types.ModuleType(name)
        module.__file__ = str(path)
        exec(compile(mutated, str(path) + ':' + name, 'exec'), module.__dict__)
        try:
            witness(module)
        except AssertionError as error:
            results.append({'mutation': name, 'baseline_pass': True, 'mutant': 'KILLED',
                            'failure': str(error), 'changes': [{'deleted': a, 'replacement': b} for a, b in replacements]})
        else:
            raise AssertionError(name + ': mutant survived')
    assert before == base.cp.sha256(path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'source_sha256': before, 'source_unchanged': True,
        'killed': len(results), 'survived': 0, 'results': results}, indent=2) + '\n')
    print(json.dumps({'killed': len(results), 'survived': 0, 'groups': ['D1', 'D2', 'D3', 'D4', 'D5']}))


if __name__ == '__main__':
    main()
