"""R10 coordinator policy and bundle pins; injected wire, no model or physics."""
import json
import socket

import pytest

from harness.llm_completion import ACCEPTED_UNVERIFIED_LABEL, completion_aggregate
from harness.zone_pilot_reconcile import require_preflight
from harness.zone_pilot_budget import sha
from harness.zone_study_contract import MAIN_CONDITIONS
from harness import rgb_execution_bundle as bundles
from test_zone_study_review_r9 import (PROFILE, USAGE, corrupt, run_mock_cli,
                                      trial_for)
from scripts import run_zone_study_pilot as runner


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('R10 is offline only')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('upstream', ['STOP', 'SAFETY', 'RECITATION', None, 'MAX_TOKENS'])
def test_installed_proxy_mapping_is_accepted_only_as_unverified(tmp_path, condition, upstream):
    # Audited installed mapping: it erases all reasons except MAX_TOKENS.
    # Do not modify or copy the proxy, or infer the erased reason from text.
    reason = 'length' if upstream == 'MAX_TOKENS' else 'stop'
    trial, budget = trial_for(tmp_path, condition, reason)
    result = trial.run_adapter()
    accepted = int(reason == 'stop')
    aggregate = result['model_evaluation']['completion']
    assert aggregate['successful_calls'] == aggregate['accepted_upstream_unverified_calls'] == accepted
    assert aggregate['accepted_upstream_unverified_label'] == ACCEPTED_UNVERIFIED_LABEL
    assert aggregate['upstream_finish_reason_verified_calls'] == 0
    assert bool(result['actions']) == bool(accepted)
    assert bool(result['messages']) == bool(accepted and condition != 'no_comm')
    call = result['calls'][0]
    assert call['cost_terms']['completion']['upstream_finish_verified'] is False
    assert call['cost_terms']['provider_usage'] == USAGE and call['sim_cost_s'] > 0
    assert budget.snapshot()['reserved_attempts'] == 2


@pytest.mark.parametrize('condition', MAIN_CONDITIONS)
@pytest.mark.parametrize('kind', ['missing_content', 'truncated_json', 'missing_field', 'nested_schema'])
def test_failure_is_billed_but_never_admitted_or_delivered(tmp_path, condition, kind):
    def nested_schema(response):
        message = response['choices'][0]['message']
        value = json.loads(message['content'])
        value['action'] = {'not_an_action': True}
        message['content'] = json.dumps(value)
    mutate = nested_schema if kind == 'nested_schema' else corrupt(kind)
    trial, budget = trial_for(tmp_path, condition, 'stop', mutate)
    result = trial.run_adapter()
    assert not result['actions'] and not result['messages'] and not trial.envelopes
    call = result['calls'][0]
    assert call['status'] != 'ok' and call['sim_cost_s'] > 0
    assert call['cost_terms']['provider_usage'] == USAGE
    aggregate = completion_aggregate(result['calls'])
    assert aggregate['successful_calls'] == aggregate['accepted_upstream_unverified_calls'] == 0
    assert aggregate['failed_or_unadmitted_calls'] == 1
    saved = budget.snapshot()
    assert saved['reserved_attempts'] == 2 and saved['reserved_tokens'] > 0
    assert saved['sends'][0]['provider_usage'] == USAGE


@pytest.mark.parametrize('ack', ['missing', False, None, 'true', 1])
def test_cohort_gate_requires_explicit_boolean_acknowledgement(tmp_path, monkeypatch, ack):
    budget, manifest = run_mock_cli(tmp_path, monkeypatch)
    snapshot = budget.snapshot()
    require_preflight(snapshot, {'complete': True}, manifest)
    if ack == 'missing':
        manifest.pop('upstream_finish_limitation_acknowledged')
    else:
        manifest['upstream_finish_limitation_acknowledged'] = ack
    # Rebind the hash so the new gate, not incidental byte drift, rejects it.
    snapshot['runs'][0]['manifest_sha256'] = sha(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n')
    with pytest.raises(ValueError, match='explicit upstream finish limitation acknowledgement'):
        require_preflight(snapshot, {'complete': True}, manifest)


def test_manifest_and_cli_report_separate_unverified_admissions(tmp_path, monkeypatch, capsys):
    budget, manifest = run_mock_cli(tmp_path, monkeypatch)
    printed = json.loads(capsys.readouterr().out)
    assert printed['accepted_upstream_unverified_calls'] == 4
    assert printed['accepted_upstream_unverified_label'] == ACCEPTED_UNVERIFIED_LABEL
    assert manifest['accepted_upstream_unverified_calls'] == 4
    assert manifest['upstream_finish_limitation_acknowledged'] is True
    assert [t['accepted_upstream_unverified_calls'] for t in manifest['trials']] == [1] * 4
    require_preflight(budget.snapshot(), {'complete': True}, manifest)
    contract = manifest['pilot_contract']
    assert contract['calls']['preflight_posts_per_condition'] == 1
    assert contract['calls']['client_retries'] == 0
    assert contract['calls']['upstream_attempts_reserved_per_post'] == 2
    assert contract['calls']['global_attempt_cap'] == 600
    assert contract['calls']['global_token_cap'] == 5_000_000
    assert contract['calls']['refunds'] == 0
    assert contract['physical_success'] is None
    assert len(contract['conditions']) == 4
    for row in contract['conditions']:
        assert len(row['initial_inputs']) == 1
        assert row['scenario']['order_sheet_sha256']
        assert row['scenario']['map']['map_file_sha256']
        assert row['wrist_originals']['frames']
        assert not runner.pk.verify_archived_request(row['initial_inputs'][0])
    leader = contract['conditions'][2]
    assert leader['leader_id'] == 'r3'


def test_dry_manifest_binds_full_source_bundle_inputs_without_implicit_ack(tmp_path):
    manifest = runner.dry_run(tmp_path, 'preflight', runner.load_scenario(runner.scenario_ids()[0]),
                              11, PROFILE)
    assert manifest['upstream_finish_limitation_acknowledged'] is False
    assert manifest['accepted_upstream_unverified_calls'] == 0
    assert manifest['proxy_runtime'] is None and manifest['network_calls'] == 0
    source = manifest['source_identity']
    bundle, bundle_sha = bundles.load_bundle(bundles.RUNNABLE_ID)
    assert source['rgb_execution_bundle']['id'] == 'rgb-standard-dispatch-v62'
    assert source['rgb_execution_bundle']['sha256'] == bundle_sha
    assert source['rgb_execution_bundle']['effective'] == bundle['effective']
    assert set(bundles.source_closure()) <= set(source['files'])
    assert source['files'][str(bundles.REGISTRY / (bundles.RUNNABLE_ID + '.json'))] == bundle_sha
    for name, digest in source['files'].items():
        assert sha((runner.ROOT / name).read_bytes()) == digest
    for name, digest in manifest['pilot_contract']['preprocessing_files_sha256'].items():
        assert sha((runner.ROOT / name).read_bytes()) == digest


def test_v62_retires_v61_with_identical_physics_and_immutable_bytes():
    current, _ = bundles.load_bundle(bundles.RUNNABLE_ID)
    old, old_sha = bundles.load_bundle('rgb-standard-dispatch-v61', require_runnable=False)
    assert 'rgb-standard-dispatch-v61' in bundles.RETIRED_IDS
    assert old_sha == '98b77ad6878548f21d97f4575f37fe5c0dfdbdcdf8b68087ca1f5ea2e829790b'
    assert current['parent_bundle_id'] == current['parent_bundle'] == old['id']
    assert current['effective'] == old['effective']
    assert 'harness/llm_completion.py' in current['source_files_sha256']
    assert current['status'] == 'experimental_unqualified'
    with pytest.raises(ValueError, match='original source checkout'):
        bundles.load_bundle(old['id'])
