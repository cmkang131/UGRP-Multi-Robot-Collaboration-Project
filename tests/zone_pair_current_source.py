"""Synthetic current-source v5h fixture for offline admission tests.

dev13/dev14 were executed at f87921dc under the committed prereg_v5h. The
2026-09-28 main merge (multi-turn scheduler, bundle v69) changed sources that
the v5h grasp receipt covers, so the committed receipt is now historical and
``run_zone_pair_dev.load_config`` refuses it with ``grasp contract/hash
mismatch``. That refusal is the correct behavior for an executed cohort and is
checked directly (``assert_executed_v5h_is_historical``).

Admission/authorization logic still needs a structurally valid registration.
``current_source_v5h`` copies the committed v5h, rebinds ONLY its source
receipts to the current checkout and reseals ``registration_sha256``. It is a
test fixture: never a registration, an authorization or an execution record,
and it is never written into the repository.
"""
import copy
import json

import pytest

from scripts import run_zone_pair_dev as dev


def committed_v5h():
    return json.loads(dev.PREREG_V5H.read_text())


def current_source_v5h():
    from scripts.zone_pair_authorization import digest, registration_payload
    from scripts.zone_pair_grasp_contract import grasp_contract
    p = committed_v5h()
    assert p.get('execution_authorization') is None
    p.update(scene_contract=dev.scene_contract(), grasp_contract=grasp_contract())
    p['registration_sha256'] = digest(registration_payload(p))
    return p


def write_current_source_v5h(path):
    path.write_text(json.dumps(current_source_v5h(), ensure_ascii=False, indent=2) + '\n')
    return path


def assert_executed_v5h_is_historical(tmp_path, run_id='dev13'):
    """Committed bytes are provenance-valid at their own commit, refused now."""
    from scripts.zone_pair_grasp_contract import grasp_contract
    from scripts.zone_pair_registered_source import verify_registered_source
    receipt = verify_registered_source(dev.PREREG_V5H)
    p = committed_v5h()
    assert receipt['contract_sha256']['grasp_contract'] == p['grasp_contract']['sha256']
    current = grasp_contract()
    assert set(current['source_sha256']) == set(p['grasp_contract']['source_sha256'])
    drift = {k for k, v in current['source_sha256'].items() if p['grasp_contract']['source_sha256'][k] != v}
    assert drift, 'v5h would be current again; revisit this fixture'
    before = copy.deepcopy(p)
    args = dev.parser().parse_args(['--prereg', str(dev.PREREG_V5H), '--run-id', run_id,
                                    '--output', str(tmp_path / f'refused-{run_id}')])
    # MasterPi v3 (PR #249) also changed the scene contract, which is checked
    # first; either refusal keeps v5h historical.
    with pytest.raises(ValueError, match='^(scene|grasp) contract/hash mismatch$'):
        dev.load_config(args)
    assert not args.output.exists() and committed_v5h() == before
    return drift
