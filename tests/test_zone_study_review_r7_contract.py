"""Seventh review of PR 194, P2: a record is audited against ITS OWN contract version.

Codex ``codex-194-r7``: a normal tags_v2 record whose trial and call provenance
were relabelled with the v1 registry hash parsed and audited ``clean``, because
``parse_trial``/the input audit never looked at the registry hash, and an
unregistered hash passed as well. Now the version comes from the record's own
registry hash (``zone_study_contract.contract_version_for_registry``), an
unknown hash is refused, and every stored request body is re-validated against
THAT version, pinned to the call's provenance digests. The frozen v1-v5 records
keep their hashes and still parse (v1: f1ff6a49..., v2: c9bb5556...).
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from harness import zone_study_contract as c
from harness import zone_study_eval as ev
from harness import zone_study_offline as off
from harness.zone_study_scenarios import bundle_for, load as load_scenario
from scripts import zone_study_report as report

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / 'experiments' / '2026-09-26-zone-study-offline-smoke'
V1_REGISTRY = 'f1ff6a49'
V2_REGISTRY = 'c9bb55567a82eef535e7b296ae69f35d5a08e8372479a56ef14c1ac76f08037c'
PLACEMENT_V2_ONLY = ('near_door_spacing_m', 'near_door_radius_m', 'door_posts')


def _record(map_id='zone_wide_door_tags_v2', condition='peer_ko', seed=601, horizon_s=20.0):
    scenario = copy.deepcopy(load_scenario('s1_normal_mixed'))
    scenario['map_id'] = map_id
    trial = off.OfflineTrial(scenario, condition=condition, seed=seed, map_bundle=bundle_for(scenario),
                             horizon_s=horizon_s)
    return json.loads(json.dumps(trial.trial_record(trial.run())))


def _relabel(record, registry):
    out = copy.deepcopy(record)
    out['provenance']['registry_sha256'] = registry
    for row in out['calls']:
        row['provenance']['registry_sha256'] = registry
    return out


def _audit(record):
    trial = ev.parse_trial(record)
    return trial, ev.audit_input_boundary(trial)


def test_r7_p2_every_registry_hash_names_one_contract_version():
    versions = c.registry_versions()
    assert versions == {c.registry_sha256(c.CONTRACT_VERSION_V1): c.CONTRACT_VERSION_V1,
                        V2_REGISTRY: c.CONTRACT_VERSION}
    assert c.registry_sha256(c.CONTRACT_VERSION_V1).startswith(V1_REGISTRY)
    for registry, version in versions.items():
        assert c.contract_version_for_registry(registry) == version


@pytest.mark.parametrize('value', ['a' * 64, V2_REGISTRY.upper(), V2_REGISTRY[:-1], '', None, 5, 1.5,
                                   float('nan'), [V2_REGISTRY], {'sha': V2_REGISTRY}, True])
def test_r7_p2_boundary_an_unknown_registry_hash_is_refused(value):
    with pytest.raises(c.ContractViolation, match='registry'):
        c.contract_version_for_registry(value)


def test_r7_p2_codex_counterexample_a_tags_v2_record_labelled_v1_fails_the_audit():
    record = _record()
    trial, boundary = _audit(record)
    assert trial['contract_version'] == c.CONTRACT_VERSION and ev.boundary_status(boundary) == 'clean'
    relabelled = _relabel(record, c.registry_sha256(c.CONTRACT_VERSION_V1))
    trial, boundary = _audit(relabelled)
    assert trial['contract_version'] == c.CONTRACT_VERSION_V1
    assert ev.boundary_status(boundary) == 'violation' and boundary['clean'] is False
    rows = boundary['payload_contract_violations']
    assert len(rows) == len(record['calls']) and ev.boundary_failures(boundary) == {
        'payload_contract_violations': len(record['calls'])}
    assert all(any(key in problem for key in PLACEMENT_V2_ONLY for problem in row['problems'])
               for row in rows)


def test_r7_p2_the_violation_reaches_the_cohort_summary_and_the_report(tmp_path):
    trials = tmp_path / 'trials'
    trials.mkdir()
    bad = _relabel(_record(), c.registry_sha256(c.CONTRACT_VERSION_V1))
    (trials / f'{bad["trial_id"]}.json').write_text(json.dumps(bad, ensure_ascii=False))
    report.build([trials], tmp_path / 'report', resamples=20, now=0.0)
    text = (tmp_path / 'report' / 'summary.md').read_text()
    assert '계약 버전 위반' in text and '입력 경계 감사에 실패한 시행이 있다' in text
    row = ev.summarise([ev.parse_trial(bad)])['conditions']['peer_ko']
    assert row['boundary_violation_trials'] == 1 and row['boundary_clean_trials'] == 0


def test_r7_p2_an_unregistered_hash_in_the_record_is_refused():
    record = _record(map_id='zone_wide_door_tags_v1')
    with pytest.raises(c.ContractViolation, match='known contract version'):
        ev.parse_trial(_relabel(record, 'a' * 64))
    top_only = copy.deepcopy(record)
    top_only['provenance']['registry_sha256'] = 'b' * 64
    with pytest.raises(ev.TrialError, match='mixes'):
        ev.parse_trial(top_only)


def test_r7_p2_one_record_is_one_contract_version():
    record = _record(map_id='zone_wide_door_tags_v1')
    mixed = copy.deepcopy(record)
    mixed['calls'][0]['provenance']['registry_sha256'] = c.registry_sha256(c.CONTRACT_VERSION_V1)
    with pytest.raises(ev.TrialError, match='mixes'):
        ev.parse_trial(mixed)
    authored = copy.deepcopy(record)
    authored['contract_version'] = c.CONTRACT_VERSION_V1
    with pytest.raises(ev.TrialError, match='differs from the version'):
        ev.parse_trial(authored)
    authored['contract_version'] = c.CONTRACT_VERSION
    assert ev.parse_trial(authored)['contract_version'] == c.CONTRACT_VERSION


def test_r7_p2_control_a_tags_v1_record_is_clean_under_either_version():
    record = _record(map_id='zone_wide_door_tags_v1')
    for registry in (V2_REGISTRY, c.registry_sha256(c.CONTRACT_VERSION_V1)):
        _, boundary = _audit(_relabel(record, registry))
        assert ev.boundary_status(boundary) == 'clean', boundary['payload_contract_violations'][:1]


def test_r7_p2_a_stored_body_must_match_the_provenance_it_is_filed_under():
    """The re-validation is pinned to the call's own order sheet and map digests."""
    record = _record(map_id='zone_wide_door_tags_v1')
    for key, match in (('order_sheet_sha256', 'order sheet'), ('public_map_sha256', 'map projection'),
                       ('map_file_sha256', 'map bundle')):
        bad = copy.deepcopy(record)
        for row in bad['calls']:
            row['provenance'][key] = 'e' * 64
        _, boundary = _audit(bad)
        assert ev.boundary_status(boundary) == 'violation'
        assert all(any(match in p for p in row['problems']) for row in boundary['payload_contract_violations'])


def test_r7_p2_a_request_whose_body_was_edited_consistently_is_still_caught():
    """A forbidden key added to the stored body AND re-hashed passes the digest
    checks; the version re-validation still refuses it."""
    from harness import zone_study_prompts_ko as pk

    record = _record(map_id='zone_wide_door_tags_v1')
    row = record['request_archive'][0]
    body = json.loads(row['user'])
    body['own_pose_m'] = [1.0, 2.0]
    row['user'] = json.dumps(body, sort_keys=True, ensure_ascii=False)
    window = body.pop(pk.WINDOW_KEY, None)
    row['input_sha256'] = pk.payload_sha256(body)
    row['request_sha256'] = pk.request_digest_from_refs(row['system'], row['user'], row['image_refs'])
    row['tokens'].update(pk.request_tokens(row['system'], row['user'], row['image_refs']))
    row['billed_tokens'].update(user=row['tokens']['user'],
                                total_text_billed=row['billed_tokens']['system_billed'] + row['tokens']['user'])
    call = next(r for r in record['calls'] if r['request_id'] == row['request_id'])
    call['input_sha256'] = row['input_sha256']
    assert window is not None                       # peer_ko: the dialogue window is outside the digest
    _, boundary = _audit(record)
    (bad,) = boundary['payload_contract_violations']
    assert bad['request_id'] == row['request_id'] and any('own_pose_m' in p for p in bad['problems'])


FROZEN = [('v3', 'example_trial_record.json.gz', c.CONTRACT_VERSION_V1, 'clean'),
          ('v4', 'example_trial_record.json.gz', c.CONTRACT_VERSION_V1, 'clean'),
          ('v5', 'example_trial_record.json.gz', c.CONTRACT_VERSION, 'clean')]


@pytest.mark.parametrize('folder, name, version, status', FROZEN)
def test_r7_p2_frozen_records_keep_their_hashes_and_audit_under_their_own_version(folder, name, version,
                                                                                  status):
    path = SMOKE / folder / name
    index = json.loads((SMOKE / folder / 'raw_index.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == index['committed'][name]
    record = json.loads(gzip.decompress(path.read_bytes()))
    trial, boundary = _audit(record)
    assert trial['contract_version'] == version and ev.boundary_status(boundary) == status
    assert boundary['payload_contract_violations'] == []
