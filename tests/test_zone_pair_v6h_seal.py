"""Blinded seal audits: Git blobs and synthetic classifications only; no raw."""
import copy
import importlib
import json
import os
from pathlib import Path

import pytest

PREFIX = 'experiments.2026-09-30-pair-v6h-carry.'
s = importlib.import_module(PREFIX + 'analysis.seal_registration')
b = importlib.import_module(PREFIX + 'build_prereg_v6h')


def sealed():
    return json.loads(Path(os.environ.get('V6H_SEAL_TEST_PATH', s.HERE/'prereg_v6h.json')).read_bytes())


def redigest(value):
    from scripts.zone_pair_authorization import digest, registration_payload
    value['registration_sha256'] = digest(registration_payload(value))
    return value


def test_execution_all_274_git_blobs_include_six_extras_without_worktree_reads(monkeypatch):
    value = sealed()
    execution = value['pin_sets']['execution']
    read = Path.read_bytes
    protected = {s.ROOT/p for p in execution['files']}
    def guarded(path):
        if path in protected:
            pytest.fail('execution audit read working-tree source: ' + str(path))
        return read(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded)
    assert execution['files'] == s.pins(execution['files'], s.SOURCE)
    assert len(execution['files']) == 274
    assert set(s.EXTRA) <= execution['files'].keys()
    assert {p:r['sha256'] for p,r in execution['files'].items()} == value['v6_contract']['source_sha256']


def test_complete_analysis_pins_final_classifier_adapters_definitions_and_gate():
    value = sealed()
    receipt = s.verify_seal(value)
    assert receipt['execution_files'] == 274 and receipt['outcomes_read'] is False
    commit = s.recorded_seal_commit()
    assert set(value['pin_sets']['analysis']['files']) == s.analysis_paths(commit)
    for rel in ('analysis/classify_placements.py', 'analysis/recorder_v4c6b.py', 'analysis/CLASSIFY_NOTES.md'):
        path = str((s.HERE/rel).relative_to(s.ROOT))
        raw = s.git('show', commit + ':' + path) if commit else (s.ROOT/path).read_bytes()
        assert raw == s.git('show', s.CLASSIFIER_COMMIT + ':' + path)
    assert value['analysis_gate']['primary']['minimum_pass'] == 48
    assert value['analysis_gate']['missing_rule']['HOST_ERROR'] == 'UNCLASSIFIED'


def test_builder_72_cases_match_literal_committed_blinded_plan_bytes():
    value = sealed()
    current = b.build()
    assert s.verify_cases(current['cases']) == value['case_equality']
    assert s.case_bytes(current['cases']) == s.case_bytes(value['cases'])
    current['cases'][0]['seed'] = 943
    with pytest.raises(ValueError, match='byte-for-byte'):
        s.verify_cases(current['cases'])


@pytest.mark.parametrize('fault', ['missing_execution', 'missing_extra', 'wrong_execution_sha', 'wrong_blob',
                                  'missing_classifier', 'missing_gate', 'wrong_analysis_sha', 'state', 'gate', 'case'])
def test_tampering_rejected_even_after_outer_digest_recomputed(fault):
    value = copy.deepcopy(sealed())
    execution = value['pin_sets']['execution']['files']
    analysis = value['pin_sets']['analysis']['files']
    classifier = str((s.HERE/'analysis/classify_placements.py').relative_to(s.ROOT))
    gate = str((s.HERE/'analysis/analysis_gate.json').relative_to(s.ROOT))
    if fault == 'missing_execution': execution.pop('harness/zone_pair_executor.py')
    elif fault == 'missing_extra': execution.pop(s.EXTRA[0])
    elif fault == 'wrong_execution_sha': execution[s.EXTRA[0]]['sha256'] = '0'*64
    elif fault == 'wrong_blob': execution[s.EXTRA[0]]['git_blob_sha'] = '0'*40
    elif fault == 'missing_classifier': analysis.pop(classifier)
    elif fault == 'missing_gate': analysis.pop(gate)
    elif fault == 'wrong_analysis_sha': analysis[classifier]['sha256'] = '0'*64
    elif fault == 'state': value['state'] = 'draft'
    elif fault == 'gate': value['analysis_gate']['primary']['minimum_pass'] = 47
    elif fault == 'case': value['cases'][0]['seed'] = 911
    with pytest.raises(ValueError):
        s.verify_seal(redigest(value))


def test_seal_writer_refuses_existing_seal_and_never_changes_it(tmp_path, monkeypatch):
    path = tmp_path/'prereg_v6h.json'
    raw = json.dumps(sealed()).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(b, 'HERE', tmp_path)
    with pytest.raises(FileExistsError):
        b.main(['--seal'])
    assert path.read_bytes() == raw


def test_seal_commit_verification_rejects_changed_state_with_valid_digest(monkeypatch):
    original = sealed()
    real_git = s.git
    seal_path = str((s.HERE/'prereg_v6h.json').relative_to(s.ROOT))
    def git(*args):
        if args == ('show', 'synthetic-seal:' + seal_path):
            return json.dumps(original).encode()
        return real_git(*args)
    monkeypatch.setattr(s, 'git', git)
    changed = copy.deepcopy(original)
    changed['notes']['interpretation'] = 'undisclosed prospective claim'
    with pytest.raises(ValueError, match='seal commit'):
        s.verify_seal(redigest(changed), 'synthetic-seal')


def test_sealed_registration_cannot_execute_from_seal_tree():
    from scripts.zone_pair_v6h_admission import validate_plan
    with pytest.raises(ValueError, match='source contract/hash mismatch'):
        validate_plan(sealed())


def synthetic_report(pass_primary=48, missing=None, hard=False):
    cases = []
    for seed, count in ((941, 60), (943, 12)):
        for i in range(1, count+1):
            invalid = (i, seed) == missing
            cases.append({'case_id': f'C{i:02d}-{seed}', 'placement': f'C{i:02d}', 'seed': seed,
                'class': None if invalid else 'PASS_CLEAN' if seed == 943 or i <= pass_primary else 'FAIL',
                'first_failure': None, 'unclassified_reason': 'HOST_ERROR' if invalid else None,
                'invalid_evidence': invalid, 'confirmatory_evidence_checked': not invalid,
                'hard_limit_chain': {'violated': hard and i == 1, 'evidence_issues': []},
                'sigma': {leg: {'reached': True, 'signed': {r: {'z2': [1., 1., 1.]} for r in ('r1','r2')}}
                          for leg in ('L0','L1')}})
    cls = importlib.import_module(PREFIX + 'analysis.classify_placements')
    placements, summary = cls.summarize(cases)
    summary.update(cohort_evidence_issues=[], invalid_cases=[c['case_id'] for c in cases if c['invalid_evidence']],
                   recorded_admission='unsealed_stage_probe')
    return {'placements': placements, 'attempts': cases, 'summary': summary}, cls


@pytest.mark.parametrize('count,missing,hard,expected', [
    (48, None, False, 'PASS_A_B_SAFETY'), (47, None, False, 'FAIL_A_B_SAFETY'),
    (60, (1,941), False, 'NOT_EVALUABLE'), (60, (1,943), False, 'NOT_EVALUABLE'),
    (60, None, True, 'FAIL_A_B_SAFETY')])
def test_sealed_gate_fixed_denominator_missing_and_safety(count, missing, hard, expected):
    gate = importlib.import_module(PREFIX + 'analysis.apply_sealed_analysis')
    report, cls = synthetic_report(count, missing, hard)
    summary = gate.apply_gate(report, sealed(), cls)
    assert summary['full_verdict'] == expected
    assert summary['n_placements'] == 60 and summary['n_cases'] == 72
    assert summary['pass_placements'] <= count
    assert summary['recorded_admission'] == 'unsealed_stage_probe'
    if missing == (1,941):
        assert summary['wilson95_primary_classified'] is None


def test_analysis_git_import_closure_never_reads_later_worktree(monkeypatch):
    blobs = {'analysis/entry.py': b'from harness import late\n',
             'harness/__init__.py': b'', 'harness/late.py': b'from . import leaf\n',
             'harness/leaf.py': b''}
    def git(*args):
        if args[0] == 'ls-tree':
            return '\n'.join(blobs).encode()
        assert args[0] == 'show' and args[1].startswith('seal:')
        return blobs[args[1].split(':', 1)[1]]
    monkeypatch.setattr(s, 'git', git)
    monkeypatch.setattr(Path, 'read_bytes', lambda self: pytest.fail('read later working-tree bytes'))
    assert s.source_closure(['analysis/entry.py'], 'seal') == set(blobs)


def test_analysis_pin_set_covers_main_added_transitive_admission():
    value = sealed()
    for path in ('sim/zone_study_admission.py', 'harness/zone_corridor_admission.py'):
        assert path in value['pin_sets']['analysis']['files']
        assert path not in value['pin_sets']['execution']['files']


def test_v2_audit_ignores_later_harness_bytes_but_rejects_changed_git_objects(monkeypatch):
    from tests.v6h_successor_pins import REGISTRATION, SEAL, successor_blob
    value = json.loads((s.ROOT / REGISTRATION).read_bytes())
    paths = ('harness/zone_study_eval.py', 'harness/zone_study_referee.py')
    read = Path.read_bytes

    def no_later_harness(path):
        if path in {s.ROOT / rel for rel in paths}:
            pytest.fail('historical seal audit read later main harness: ' + str(path))
        return read(path)

    monkeypatch.setattr(Path, 'read_bytes', no_later_harness)
    assert s.verify_seal(value, SEAL)['analysis_files'] == 293
    for path in paths:
        raw = successor_blob(path)
        assert s.sha(raw) == value['pin_sets']['analysis']['files'][path]['sha256']
    git = s.git
    for path in paths:
        def changed_git(*args):
            raw = git(*args)
            return raw + b'\n' if args == ('show', SEAL + ':' + path) else raw
        monkeypatch.setattr(s, 'git', changed_git)
        with pytest.raises(ValueError, match='analysis pin set incomplete or git blob/sha256 mismatch'):
            s.verify_seal(value, SEAL)


def test_all_existing_seal_records_stay_byte_identical_after_unblinding():
    from tests.v6h_successor_pins import REGISTRATION, SEAL, successor_blob
    value = json.loads(successor_blob(REGISTRATION))
    base = s.HERE.relative_to(s.ROOT).as_posix() + '/'
    records = {path for path in value['pin_sets']['analysis']['files'] if path.startswith(base)}
    records.add(base + 'prereg_v6h.json')
    records.update(s.git('ls-tree', '-r', '--name-only', SEAL, '--',
                         base + 'analysis/seal', base + 'analysis/seal_v2').decode().splitlines())
    assert base + 'REGISTRATION_PLAN.md' in records
    assert base + 'NOTE_AFTER_UNBLINDING.md' not in records
    for path in sorted(records):
        assert (s.ROOT / path).read_bytes() == successor_blob(path), path
