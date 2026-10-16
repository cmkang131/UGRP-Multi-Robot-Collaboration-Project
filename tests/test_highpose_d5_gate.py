"""REVIEW_363 P1-1: exact D5 output and both fail-closed entry points."""
import copy
import json
import pytest
from tests.test_zone_final_pair_v3 import offline_only, MAPS
from tests.highpose_fixtures import d5_output, trust_fixture, write
from harness import zone_pair_highpose_contract as c
from scripts import run_pair_highpose as run


def test_d5_output_fixture_accepted_only_under_test_trust(tmp_path, monkeypatch):
    path, cal = d5_output(tmp_path)
    assert c.d5.measured_calibration(path, c.base.sha(path), MAPS[0]) == cal
    with pytest.raises(ValueError, match='completed measurement not registered'):
        c.measured_calibration(path, c.base.sha(path), MAPS[0])
    trust_fixture(monkeypatch, path, cal)
    assert c.measured_calibration(path, c.base.sha(path), MAPS[0]) == cal


@pytest.mark.parametrize('fault', ['source', 'manifest', 'schedule', 'criterion', 'assembler',
                                 'PARTIAL', 'incomplete', 'dirty', 'report'])
def test_bad_provenance_or_partial_d5_rejected(tmp_path, monkeypatch, fault):
    path, cal = d5_output(tmp_path)
    trusted = trust_fixture(monkeypatch, path, cal)
    if fault in ('source', 'manifest', 'schedule', 'criterion', 'assembler'):
        name = {'source':'source_sha','manifest':'measurement_manifest_sha256',
                'schedule':'loaded_schedule_sha256','criterion':'criterion_sha256','assembler':'assembler_sha256'}[fault]
        cal[name] = 'f'*len(cal[name])
    elif fault == 'PARTIAL': cal['status'] = 'PARTIAL'
    elif fault == 'incomplete':
        trusted['completed_measurements'][0]['completed_collections']['loaded']['protocol_complete'] = False
    elif fault == 'dirty':
        p = tmp_path/'input_manifest.json'
        manifest = json.loads(p.read_text());manifest['working_tree_dirty'] = True;write(p, manifest)
    elif fault == 'report': write(tmp_path/'fit_report.json', {})
    write(path, cal)
    # Even if a fixture hash is admitted, mismatched source/assembler/evidence
    # must still fail; arbitrary caller hash alone never updates this root.
    trusted['completed_measurements'][0]['calibration_sha256'] = c.base.sha(path)
    with pytest.raises(ValueError): c.measured_calibration(path, c.base.sha(path), MAPS[0])


@pytest.mark.parametrize('trusted', [False, True])
def test_cli_and_direct_case_never_override_bundle_false(tmp_path, monkeypatch, capsys, trusted):
    path, cal = d5_output(tmp_path)
    if trusted: trust_fixture(monkeypatch, path, cal)
    out = tmp_path/'must-not-exist'
    argv = ['--check','p03','--expected-source-sha','a'*40,'--output',str(out),
            '--calibration',str(path),'--calibration-sha256',c.base.sha(path)]
    assert run.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['runnable'] is False and c.REGISTRY_BLOCK in plan['blocked_on']
    with pytest.raises(ValueError): run.main(argv+['--execute'])
    case = c.cases('p03')[0]
    bundle = {**c.bundle(case['map_id'],'p03'),'source_sha':'a'*40,'case':case}
    for runnable in (False, True):
        bundle['runnable'] = runnable
        with pytest.raises(ValueError):
            run.run_case(bundle,out,seed=911,backend_factory=lambda *a, **k: pytest.fail('backend created'),
                         calibration=path,calibration_sha=c.base.sha(path))
    assert not out.exists()
