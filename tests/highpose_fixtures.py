"""Synthetic D5 output trust is installed ONLY by test monkeypatches."""
import copy
from tests.test_final_pair_calibration_v92 import a, metadata, complete_sections, write, measurement_label
from harness import zone_pair_highpose_contract as contract


def d5_output(tmp_path):
    meta = metadata()
    manifest = {'schema': 'ugrp.v92_calibration_inputs.v1', 'files': [],
        'execution_source_sha': meta['source_sha'], 'raw_unchanged': True,
        'working_tree_dirty': False, 'qualification': 'synthetic test-only fixture'}
    write(tmp_path/'input_manifest.json', manifest)
    meta['measurement_manifest_sha256'] = contract.base.sha(tmp_path/'input_manifest.json')
    sections = complete_sections()
    # The v92 fixture camera looks straight down (no floor trace for the
    # column model); use the forward-looking v88 synthetic record instead.
    forward = measurement_label([0, 0, .033], [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [.15, 0, .2],
                                [[0., 0., -1.], [-1., 0., 0.], [0., 1., 0.]])  # MuJoCo cam frame -> optical [[0,0,1],[-1,0,0],[0,-1,0]]
    for key, row in sections.items():
        if key[0] == 'camera_models':
            row['value'] = copy.deepcopy(forward)
    cal = a.assemble(meta, sections)
    # The real output contains measured sections, not a replacement for static
    # PF options. These defaults are also what the student provider must merge.
    path = tmp_path/'calibration.json'
    write(path, cal)
    write(tmp_path/'fit_report.json', {p: {'collection_audit': 'PASS'} for p in cal['collection_sources']})
    return path, cal


def trust_fixture(monkeypatch, path, cal):
    admission, registration = contract.d5_admission()
    admission = copy.deepcopy(admission)
    admission['completed_measurements'] = [{
        'calibration_sha256': contract.base.sha(path),
        **{k: copy.deepcopy(cal[k]) for k in ('source_sha', 'measurement_manifest_sha256', 'collection_sources')},
        'fit_report_sha256': contract.base.sha(path.parent/'fit_report.json'),
        'completed_collections': {p: {'source_sha': sha, 'status': 'COLLECTED_UNQUALIFIED',
            'protocol_complete': True, 'source_unchanged': True, 'partial_data_retained': False,
            'unattempted': [], 'failure': None} for p, sha in cal['collection_sources'].items()}}]
    monkeypatch.setattr(contract, 'd5_admission', lambda: (admission, registration))
    return admission
