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


def test_v6_records_current_scene_and_full_source_closure():
    from scripts.zone_pair_v6_contract import PREREG, V5H, contract
    p = json.loads(PREREG.read_text())
    assert p['scene_contract'] == dev.scene_contract()
    assert p['v6_contract'] == contract()
    assert 'grasp_contract' not in p  # old behavior/source receipt belongs to the baseline
    assert p['baseline_registration'] == {'path': str(V5H.relative_to(dev.ROOT)),
                                           'sha256': hashlib.sha256(V5H.read_bytes()).hexdigest()}
    assert p['scene_contract']['source_sha256'].items() <= p['v6_contract']['source_sha256'].items()
    for path, expected in p['v6_contract']['source_sha256'].items():
        assert hashlib.sha256((dev.ROOT/path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize('fault', ['source', 'scene', 'inherited_grasp', 'baseline'])
def test_v6_rejects_stale_or_inherited_source_contracts(tmp_path, fault):
    from scripts.zone_pair_v6_contract import PREREG, V5H
    p = json.loads(PREREG.read_text()); old = json.loads(V5H.read_text())
    if fault == 'source': p['v6_contract']['source_sha256']['harness/zone_own_team_host.py'] = '0'*64
    elif fault == 'scene': p['scene_contract'] = old['scene_contract']
    elif fault == 'inherited_grasp': p['grasp_contract'] = old['grasp_contract']
    else: p['baseline_registration']['sha256'] = '0'*64
    altered = tmp_path/'altered.json'; altered.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(altered), '--run-id', 'v6-s911-ab',
                                    '--output', str(tmp_path/'never-prepared')])
    with pytest.raises(ValueError):
        dev.load_config(args)
    assert not args.output.exists()
