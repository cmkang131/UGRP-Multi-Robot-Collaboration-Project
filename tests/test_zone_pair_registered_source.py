"""Historical provenance must survive successors without admitting old runs."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_zone_pair_dev as dev
from scripts.zone_pair_registered_source import (digest, verify_contract_sources,
                                                 verify_registered_source)


@pytest.mark.parametrize('revision', ['v3', 'v4', 'v5', 'v5b', 'v5c', 'v5d', 'v5e', 'v5f', 'v5g', 'v5h'])
def test_historical_receipts_use_git_blobs_not_worktree(revision, monkeypatch):
    registration = dev.PREREG.with_name(f'prereg_{revision}.json')
    value = json.loads(registration.read_text())
    sources = {dev.ROOT/p for key in ('scene_contract', 'grasp_contract', 'contact_profile_contract')
               for p in value.get(key, {}).get('source_sha256', {})}
    read = Path.read_bytes
    def guarded(path):
        if path in sources:
            pytest.fail(f'historical audit read current source: {path}')
        return read(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded)
    receipt = verify_registered_source(registration)
    assert receipt['contract_sha256']['scene_contract'] == value['scene_contract']['sha256']
    assert len(receipt['source_commit']) == 40
    assert 'not current-source execution admission' in receipt['qualification']


def test_resealed_bad_source_hash_and_wrong_commit_are_rejected():
    receipt = verify_registered_source(dev.PREREG_V3)
    value = copy.deepcopy(json.loads(dev.PREREG_V3.read_text())['scene_contract'])
    value['source_sha256']['harness/zone_own_team_host.py'] = '0'*64
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='registered source hash mismatch'):
        verify_contract_sources(value, receipt['source_commit'])
    with pytest.raises(ValueError, match='registered source hash mismatch'):
        verify_registered_source(dev.PREREG_V3, source_commit=verify_registered_source(dev.PREREG_V5H)['source_commit'])


def test_modified_registration_bytes_are_rejected(monkeypatch):
    read = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda p: read(p)+b'\n' if p == dev.PREREG_V3 else read(p))
    with pytest.raises(ValueError, match='registration bytes differ'):
        verify_registered_source(dev.PREREG_V3)


def test_v6_records_registered_scene_and_full_source_closure_at_its_commit():
    """v6 is historical: its receipt is checked against the registration commit, not the current tree."""
    from scripts.zone_pair_registered_source import committed_blob
    from scripts.zone_pair_v6_contract import PREREG, V5H, V6_REGISTRATION_COMMIT, verify_v6_historical
    p = json.loads(PREREG.read_text())
    assert verify_v6_historical()['sources'] == len(p['v6_contract']['source_sha256'])
    assert 'grasp_contract' not in p  # old behavior/source receipt belongs to the baseline
    assert p['baseline_registration'] == {'path': str(V5H.relative_to(dev.ROOT)),
                                           'sha256': hashlib.sha256(V5H.read_bytes()).hexdigest()}
    assert p['scene_contract']['source_sha256'].items() <= p['v6_contract']['source_sha256'].items()
    for path, expected in p['scene_contract']['source_sha256'].items():
        assert hashlib.sha256(committed_blob(str(dev.ROOT), V6_REGISTRATION_COMMIT, path)).hexdigest() == expected


def test_v6b_records_sealed_scene_and_full_source_closure_at_its_commit():
    """v6b is historical (PR #256, decision A): its DRAFT receipt is checked against its sealing commit."""
    from scripts.zone_pair_registered_source import committed_blob
    from scripts.zone_pair_v6_contract import PREREG_V6B as PREREG, V5H, V6B_DRAFT_COMMIT, verify_v6_historical
    p = json.loads(PREREG.read_text())
    assert p['registration_revision'] == 'v6b' and 'harness/owncam_bootstrap_v6b.py' in p['v6_contract']['source_sha256']
    assert verify_v6_historical(revision='v6b')['sources'] == len(p['v6_contract']['source_sha256'])
    assert 'grasp_contract' not in p  # old behavior/source receipt belongs to the baseline
    assert p['baseline_registration'] == {'path': str(V5H.relative_to(dev.ROOT)),
                                           'sha256': hashlib.sha256(V5H.read_bytes()).hexdigest()}
    assert p['scene_contract']['source_sha256'].items() <= p['v6_contract']['source_sha256'].items()
    for path, expected in p['scene_contract']['source_sha256'].items():
        assert hashlib.sha256(committed_blob(str(dev.ROOT), V6B_DRAFT_COMMIT, path)).hexdigest() == expected


def test_v6c_records_sealed_scene_and_full_source_closure_at_its_commit():
    """v6c is historical (the b-v6d fixes are the v6d revision): its DRAFT receipt is checked against its sealing commit."""
    from scripts.zone_pair_registered_source import committed_blob
    from scripts.zone_pair_v6_contract import PREREG_V6C as PREREG, V5H, V6C_DRAFT_COMMIT, verify_v6_historical
    p = json.loads(PREREG.read_text())
    assert p['registration_revision'] == 'v6c' and 'harness/owncam_recovery_v6c.py' in p['v6_contract']['source_sha256']
    assert 'harness/owncam_pair_beam_v6d.py' not in p['v6_contract']['source_sha256']   # sealed before v6d
    assert verify_v6_historical(revision='v6c')['sources'] == len(p['v6_contract']['source_sha256'])
    assert 'grasp_contract' not in p
    assert p['baseline_registration'] == {'path': str(V5H.relative_to(dev.ROOT)),
                                           'sha256': hashlib.sha256(V5H.read_bytes()).hexdigest()}
    for path, expected in p['scene_contract']['source_sha256'].items():
        assert hashlib.sha256(committed_blob(str(dev.ROOT), V6C_DRAFT_COMMIT, path)).hexdigest() == expected


def test_v6d_records_current_scene_and_full_source_closure():
    """v6d is the current v6-family revision (bundle v80): its DRAFT pins the current tree and cites the sealed v6c."""
    from scripts.zone_pair_v6_contract import CURRENT_REVISION, PREREG_V6C, PREREG_V6D, V6C_DRAFT_COMMIT, contract
    p = json.loads(PREREG_V6D.read_text())
    assert CURRENT_REVISION == p['registration_revision'] == 'v6d' and p['status'] == 'DRAFT'
    assert {'harness/owncam_pair_beam_v6d.py', 'harness/owncam_align_motion_v6d.py',
            'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'} <= set(p['v6_contract']['source_sha256'])
    assert p['scene_contract'] == dev.scene_contract() and p['v6_contract'] == contract()
    assert p['predecessor'] == {'path': str(PREREG_V6C.relative_to(dev.ROOT)),
                                'sha256': hashlib.sha256(PREREG_V6C.read_bytes()).hexdigest(),
                                'sealing_commit': V6C_DRAFT_COMMIT}
    assert sorted(r['pair_policy'] for r in p['runs']) == ['b-only', 'b-only', 'b-v6d', 'b-v6d', 'v5h', 'v5h']


def test_current_tree_v6_family_contract_closes_over_the_scene_sources():
    from scripts.zone_pair_v6_contract import contract
    for historical in ('v6', 'v6b', 'v6c'):
        with pytest.raises(ValueError, match='historical'):
            contract(historical)
    current = contract()
    assert dev.scene_contract()['source_sha256'].items() <= current['source_sha256'].items()
    for path, expected in current['source_sha256'].items():
        assert hashlib.sha256((dev.ROOT/path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize('fault', ['source', 'scene', 'inherited_grasp', 'baseline'])
def test_v6_rejects_stale_or_inherited_source_contracts(tmp_path, fault):
    """On the current v6-family registration (v6d DRAFT, as committed), each fault alone is rejected."""
    from scripts.zone_pair_v6_contract import PREREG_V6D, V5H
    p = json.loads(PREREG_V6D.read_text()); old = json.loads(V5H.read_text())
    assert p['registration_revision'] == 'v6d' and p['status'] == 'DRAFT'
    clean = tmp_path/'clean.json'; clean.write_text(json.dumps(p))
    dev.load_config(dev.parser().parse_args(['--prereg', str(clean), '--run-id', 'v6d-s911-bv6d',
                                             '--output', str(tmp_path/'clean-never')]))
    if fault == 'source': p['v6_contract']['source_sha256']['harness/zone_own_team_host.py'] = '0'*64
    elif fault == 'scene': p['scene_contract'] = old['scene_contract']
    elif fault == 'inherited_grasp': p['grasp_contract'] = old['grasp_contract']
    else: p['baseline_registration']['sha256'] = '0'*64
    altered = tmp_path/'altered.json'; altered.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(altered), '--run-id', 'v6d-s911-bv6d',
                                    '--output', str(tmp_path/'never-prepared')])
    expected = {'source': 'source contract/hash mismatch', 'scene': 'scene contract/hash mismatch',
                'inherited_grasp': 'frozen v5h baseline', 'baseline': 'frozen v5h baseline'}[fault]
    with pytest.raises(ValueError, match=expected):
        dev.load_config(args)
    assert not args.output.exists()
