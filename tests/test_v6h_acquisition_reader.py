"""Acquisition byte boundary only: synthetic files, never recorded raw."""
import importlib
import json
from pathlib import Path

import pytest

PREFIX = 'experiments.2026-09-30-pair-v6h-carry.analysis.'
gate = importlib.import_module(PREFIX + 'apply_sealed_analysis')
cp = gate.classifier


def reader_with_input(tmp_path, relative='case/result.json'):
    raw = tmp_path / 'synthetic'
    raw.mkdir()
    manifest = tmp_path / 'RUN_MANIFEST.json'
    manifest.write_text('{}\n')
    reader = gate.AcquisitionReader(raw, manifest, cp.sha256(manifest))
    path = raw / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"synthetic": true}\n')
    reader.expected[relative] = cp.sha256(path)
    return reader, path


@pytest.mark.parametrize('relative', ['cases.jsonl', 'plan.json', 'case/result.json',
    'case/eval_only/trace.jsonl', 'case/case.json', 'case/commands.json', 'future_input.json'])
@pytest.mark.parametrize('damage', ['unlisted', 'changed', 'missing'])
def test_every_consumed_input_is_checked_before_return(tmp_path, relative, damage):
    reader, path = reader_with_input(tmp_path, relative)
    if damage == 'unlisted':
        del reader.expected[relative]
        expected = 'UNLISTED_ACQUISITION_INPUT'
    elif damage == 'changed':
        path.write_text('{"synthetic": false}\n')
        expected = 'ACQUISITION_HASH_MISMATCH'
    else:
        path.unlink()
        expected = 'MISSING_EVIDENCE'
    with pytest.raises(cp.EvidenceError, match=expected):
        reader.read(path, lines=relative.endswith('.jsonl'))


def test_input_changed_during_analysis_is_still_rejected(tmp_path):
    reader, path = reader_with_input(tmp_path)
    assert reader.read(path) == ({'synthetic': True}, [])
    path.write_text('{"synthetic": false}\n')
    with pytest.raises(cp.EvidenceError, match='INPUT_CHANGED'):
        reader.verify()


def test_input_symlink_cannot_escape_acquisition_root(tmp_path):
    reader, path = reader_with_input(tmp_path)
    outside = tmp_path / 'outside.json'
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(cp.EvidenceError, match='ACQUISITION_PATH_ESCAPE'):
        reader.read(path)


def test_unlisted_future_input_is_not_even_opened(tmp_path, monkeypatch):
    reader, path = reader_with_input(tmp_path)
    del reader.expected['case/result.json']
    monkeypatch.setattr(Path, 'read_bytes', lambda _: pytest.fail('unlisted input was opened'))
    with pytest.raises(cp.EvidenceError, match='UNLISTED_ACQUISITION_INPUT'):
        reader.read(path)


@pytest.mark.parametrize('name', ['../escape.json', '/absolute.json', './case.json',
    'a//case.json', 'a/../case.json', '', 1])
def test_inventory_paths_must_be_unambiguous_relative_names(tmp_path, name):
    reader, _ = reader_with_input(tmp_path)
    with pytest.raises(cp.EvidenceError, match='INVALID_ACQUISITION_ENTRY'):
        reader.bind_inputs([(name, '0' * 64)])


def test_inventory_duplicate_paths_are_rejected(tmp_path):
    reader, _ = reader_with_input(tmp_path)
    with pytest.raises(cp.EvidenceError, match='INVALID_ACQUISITION_ENTRY'):
        reader.bind_inputs([('other.json', '0' * 64), ('other.json', '0' * 64)])


@pytest.mark.parametrize('fault', ['inventory_hash', 'schema', 'raw_path', 'file_count',
    'total_bytes', 'entry_bytes', 'duplicate_entry', 'bad_digest', 'missing_inventory_arg',
    'raw_manifest_hash'])
def test_inventory_admission_failures_have_no_gate_verdict(tmp_path, fault, monkeypatch):
    from tests.v6h_acquisition_fixtures import synthetic_acquisition
    args = list(synthetic_acquisition(tmp_path))
    raw, _, manifest, _, inventory, pin = args
    doc = json.loads(inventory.read_bytes())
    if fault == 'inventory_hash':
        inventory.write_bytes(inventory.read_bytes() + b'\n')
        reason = 'ACQUISITION_HASH_MISMATCH'
    elif fault == 'missing_inventory_arg':
        args[4] = None
        reason = 'MISSING_ACQUISITION_INVENTORY'
    elif fault == 'raw_manifest_hash':
        committed = json.loads(manifest.read_bytes())
        committed['raw']['raw_manifest_json_sha256'] = '0' * 64
        manifest.write_text(json.dumps(committed))
        args[3] = cp.sha256(manifest)
        reason = 'RAW_MANIFEST_HASH_MISMATCH'
    else:
        if fault == 'schema': doc['schema'] = 'wrong'
        elif fault == 'raw_path': doc['raw'] = str(raw.parent / 'wrong')
        elif fault == 'file_count': doc['file_count'] += 1
        elif fault == 'total_bytes': doc['total_bytes'] += 1
        elif fault == 'entry_bytes': doc['files'][0]['bytes'] += 1
        elif fault == 'duplicate_entry': doc['files'][1]['path'] = doc['files'][0]['path']
        elif fault == 'bad_digest': doc['files'][0]['sha256'] = 'wrong'
        inventory.write_text(json.dumps(doc, sort_keys=True, separators=(',', ':')))
        pin['inventory_sha256'] = cp.sha256(inventory)
        reason = ('INVALID_ACQUISITION_SCHEMA_OR_RAW_PATH' if fault in ('schema', 'raw_path') else
                  'INVALID_ACQUISITION_ENTRY' if fault in ('duplicate_entry', 'bad_digest') else
                  'ACQUISITION_TOTAL_MISMATCH')
    monkeypatch.setattr(cp, 'analyse', lambda *a, **kw: pytest.fail('classification before inventory admission'))
    monkeypatch.setattr(gate, 'apply_gate', lambda *a: pytest.fail('gate after failed inventory admission'))
    report, outcome = gate.analyse_acquisition(*args)
    assert report is None and outcome['status'] == 'INVALID' and outcome['analysis_status'] == 'NOT_ANALYSED'
    assert outcome['reason'].startswith(reason)
    assert 'summary' not in outcome and 'full_verdict' not in outcome


@pytest.mark.parametrize('relative', ['manifest.json', 'cases.jsonl', 'plan.json',
    'result.json', 'eval_only/trace.jsonl', 'case.json', 'commands.json'])
@pytest.mark.parametrize('damage', ['unlisted', 'changed', 'missing'])
def test_real_classifier_routes_all_consumed_files_through_inventory(tmp_path, monkeypatch, relative, damage):
    from tests.v6h_acquisition_fixtures import synthetic_acquisition
    args = synthetic_acquisition(tmp_path)
    raw, plan, _, _, inventory, pin = args
    path = (raw if relative in ('manifest.json', 'cases.jsonl', 'plan.json') else
            cp.ca.dra.case_dir(raw, plan['cases'][0]['case_id'])) / relative
    name = str(path.relative_to(raw))
    if damage == 'unlisted':
        doc = json.loads(inventory.read_bytes())
        removed = next(f for f in doc['files'] if f['path'] == name)
        doc['files'].remove(removed)
        doc['file_count'] -= 1
        doc['total_bytes'] -= removed['bytes']
        inventory.write_text(json.dumps(doc, sort_keys=True, separators=(',', ':')))
        pin.update(inventory_sha256=cp.sha256(inventory), file_count=doc['file_count'], total_bytes=doc['total_bytes'])
        reason = 'UNLISTED_ACQUISITION_INPUT:' + name
    elif damage == 'changed':
        # Whitespace changes preserve meaning: rejection must be byte integrity.
        path.write_bytes(path.read_bytes() + b' ')
        reason = 'ACQUISITION_HASH_MISMATCH:' + name
        if relative.endswith('.jsonl'):
            # Appending a blank JSONL record is syntactically invalid; change an
            # existing line's whitespace instead so parsing still succeeds.
            path.write_bytes(b' ' + path.read_bytes()[:-1])
    else:
        path.unlink()
        reason = 'MISSING_EVIDENCE:' + name
    monkeypatch.setattr(gate, 'apply_gate', lambda *a: pytest.fail('gate consumed damaged input'))
    report, outcome = gate.analyse_acquisition(*args)
    assert report is None and outcome['status'] == 'INVALID' and outcome['reason'].startswith(reason)
    assert 'summary' not in outcome


def test_change_after_classification_suppresses_report_and_gate(tmp_path, monkeypatch):
    from tests.v6h_acquisition_fixtures import synthetic_acquisition
    args = synthetic_acquisition(tmp_path)
    analyse = cp.analyse
    def changed(*a, **kw):
        report = analyse(*a, **kw)
        args[4].write_bytes(args[4].read_bytes() + b'\n')
        return report
    monkeypatch.setattr(cp, 'analyse', changed)
    monkeypatch.setattr(gate, 'apply_gate', lambda *a: pytest.fail('gate after mid-analysis change'))
    report, outcome = gate.analyse_acquisition(*args)
    assert report is None and outcome['reason'].startswith('INPUT_CHANGED:')
    assert 'summary' not in outcome


@pytest.mark.parametrize('damage', ['inventory', 'trace', None])
def test_cli_writes_only_invalid_status_or_verified_gate(tmp_path, monkeypatch, damage):
    from tests.v6h_acquisition_fixtures import synthetic_acquisition
    args = synthetic_acquisition(tmp_path)
    raw, plan, manifest, manifest_sha, inventory, pin = args
    seal = importlib.import_module(PREFIX + 'seal_registration')
    # Only the unrelated Git receipt boundary is stubbed. The CLI, inventory,
    # reader, classifier and gate run normally on fresh synthetic evidence.
    root = tmp_path / 'seal'
    (root / 'analysis/seal').mkdir(parents=True)
    (root / 'analysis/seal/RUN_MANIFEST.json').write_bytes(manifest.read_bytes())
    monkeypatch.setattr(seal, 'HERE', root)
    monkeypatch.setattr(seal, 'METADATA_HASHES', {'RUN_MANIFEST.json': manifest_sha})
    monkeypatch.setattr(seal, 'verify_seal', lambda *a: None)
    prereg = tmp_path / 'prereg.json'
    prereg.write_text(json.dumps({**plan, 'pin_sets': {'analysis': {'files': {}}},
                                 'registration_sha256': 'synthetic', 'acquisition_inventory': pin}))
    if damage == 'inventory': inventory.unlink()
    elif damage == 'trace':
        path = cp.ca.dra.case_dir(raw, plan['cases'][0]['case_id']) / 'eval_only/trace.jsonl'
        path.write_bytes(b' ' + path.read_bytes())
    output = tmp_path / 'report'
    rc = gate.main(['--seal-commit', 'synthetic', '--prereg', str(prereg), '--raw', str(raw),
                    '--inventory', str(inventory), '--output', str(output)])
    result = json.loads((output / 'sealed_analysis.json').read_bytes())
    if damage:
        assert rc == 2 and result['status'] == 'INVALID' and result['analysis_status'] == 'NOT_ANALYSED'
        assert 'summary' not in result and 'full_verdict' not in result and result['reason']
        assert sorted(p.name for p in output.iterdir()) == ['sealed_analysis.json']
    else:
        assert rc == 0 and result['status'] == 'ANALYSED' and result['summary']['full_verdict'] == 'PASS_A_B_SAFETY'
        report = json.loads((output / 'classifier.json').read_bytes())
        assert 'manifest.json' in report['input_sha256']
        assert str(inventory) in report['input_sha256']


def test_new_seal_has_own_analysis_pins_and_unchanged_execution():
    seal = importlib.import_module(PREFIX + 'seal_registration')
    old = json.loads(seal.registration_path().read_bytes())
    value = json.loads(seal.registration_path('v2').read_bytes())
    assert value['pin_sets']['execution'] == old['pin_sets']['execution']
    assert value['v6_contract'] == old['v6_contract']
    assert value['case_equality'] == old['case_equality']
    assert value['analysis_gate'] == old['analysis_gate']
    assert value['acquisition_inventory'] == seal.acquisition_pin()
    pin = value['acquisition_inventory']
    assert pin['inventory_sha256'] == 'd7ceca9824d4098956c7bfc5cbd7298ee5b0cfa5dacdb12586d07c2ee07ec03f'
    assert (pin['file_count'], pin['total_bytes']) == (104415, 1916385247)
    receipt = seal.verify_seal(value)
    assert receipt['execution_files'] == 274 and receipt['outcomes_read'] is False
    assert receipt['analysis_files'] == len(value['pin_sets']['analysis']['files'])
    assert value['pin_sets']['analysis'] != old['pin_sets']['analysis']


def test_new_seal_rejects_redigested_inventory_pin_change():
    seal = importlib.import_module(PREFIX + 'seal_registration')
    from scripts.zone_pair_authorization import digest, registration_payload
    value = json.loads(seal.registration_path('v2').read_bytes())
    value['acquisition_inventory']['inventory_sha256'] = '0' * 64
    value['registration_sha256'] = digest(registration_payload(value))
    with pytest.raises(ValueError, match='sealed (acquisition pin changed|state differs from seal commit)'):
        seal.verify_seal(value)


def test_v1_seal_bytes_preserved_and_v2_writer_refuses_overwrite():
    seal = importlib.import_module(PREFIX + 'seal_registration')
    builder = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h')
    original = '266118d2c2337bbf1cff507690da131c63e2db11'
    base = str(seal.HERE.relative_to(seal.ROOT))
    paths = seal.git('ls-tree', '-r', '--name-only', original, '--',
                     base + '/prereg_v6h.json', base + '/analysis/seal').decode().splitlines()
    assert paths
    for path in paths:
        assert (seal.ROOT / path).read_bytes() == seal.git('show', original + ':' + path)
    path = seal.registration_path('v2')
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        builder.main(['--seal', '--seal-revision', 'v2'])
    assert path.read_bytes() == before
