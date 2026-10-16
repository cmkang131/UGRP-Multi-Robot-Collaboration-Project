"""Batch A REPRODUCERS.md P06 probes, copied into assertions (no xfail).

Source: origin/codex/review-e2e-batch-a, review_batch_a/REPRODUCERS.md.
The four mutations are unchanged; print-only probes now require rejection.
"""
import json

import pytest

from tests.test_zone_study_evidence import (completed, export_api, no_runtime,
                                           synthetic_source, put, reseal, tb)


@pytest.mark.parametrize('case', ['foreign_identity', 'foreign_order_ids', 'missing_terminal', 'missing_image_refs'])
def test_batch_a_counterexample(tmp_path, completed, case):
    path = synthetic_source(tmp_path, 'success', completed)
    record = json.loads((path / 'study/trial_record.json').read_text())
    if case == 'foreign_identity':
        record.update(trial_id='unrelated-trial', scenario='unrelated-scenario', seed=987654)
    elif case == 'foreign_order_ids':
        for i, row in enumerate(record['orders']):
            row['order_id'] = f'unrelated-order-{i}'
    elif case == 'missing_terminal':
        result = json.loads((path / 'result.json').read_text())
        result.pop('terminal')
        put(path, 'result.json', result)
        manifest = json.loads((path / 'manifest.json').read_text())
        manifest.pop('terminal')
        put(path, 'manifest.json', manifest)
    elif case == 'missing_image_refs':
        for row in record['request_archive']:
            row['image_refs'] = []
        for image in (path / 'study/request_images').glob('*.jpg'):
            image.unlink()
    put(path, 'study/trial_record.json', record)
    reseal(path)
    out = tmp_path / 'events'
    with pytest.raises(ValueError):
        tb.convert(path, out, allow_synthetic=True, max_images=0)
    assert not list(out.glob('events*'))
