"""Synthetic yaw only: no held-out raw, physics, rendering or network access."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from scripts import validate_consumer_criterion_b_v91 as v
from tests.test_consumer_criterion_b import synthetic
from tests.test_consumer_criterion_b_v91 import (
    MAPS, get, make_raw, offline_only, put, receipts,
)

b = v.frozen


@pytest.fixture(autouse=True)
def forbid_real_heldout(monkeypatch):
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert '/outputs/final-pair-v91-heldout-' not in str(path.resolve()), 'real held-out raw forbidden'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)


def serialized(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def yaw_case():
    p = get(v.ROTATION_CANDIDATE)['candidate_axes']['rotate']
    params = p['parameters']
    data, _, _ = synthetic(2, gain=params['gain'], run=params['tau_s'], stop=params['tau_stop_s'])
    return data, p['consumer_fields']


@pytest.fixture(scope='module')
def yaw_templates(tmp_path_factory):
    base = tmp_path_factory.mktemp('synthetic-v91-yaw-only')
    roots = [make_raw(base / m, m) for m in MAPS]
    profile = get(v.ROTATION_CANDIDATE)['candidate_axes']['rotate']['consumer_fields']
    for root, map_id in zip(roots, MAPS):
        folder = root/map_id
        u, _ = b.plan_arrays(get(folder/'bundle.json')['measurement'], 7400, .05)
        increments = b.c.legacy_increments({'u': u, 'dt': .05}, profile)
        yaws = np.r_[0., np.cumsum(increments[:, 2])]
        path = folder/'eval_only/r1/pose.jsonl'
        poses = b.rows(path.read_bytes())
        for row, yaw in zip(poses, yaws):
            co, si = np.cos(yaw), np.sin(yaw)
            row['base_rotation'] = [[co, -si, 0.], [si, co, 0.], [0., 0., 1.]]
        path.write_text(''.join(json.dumps(row)+'\n' for row in poses))
        receipts(root)
    return roots


@pytest.fixture
def yaw_raw(tmp_path, yaw_templates):
    return Path(shutil.copytree(yaw_templates[0], tmp_path/'raw'))


def test_public_snapshot_hashes_manifest_and_profile():
    inputs = []
    prepared = v.prepare_rotation(inputs)
    snap = prepared['snapshot']
    assert snap['created_at'] == snap['updated_at'] == '2026-10-03T05:56:19Z'
    assert snap['listed_sha256'] == v.ROTATION_HASHES
    assert '7eea9447212e3de1ffea9a61876e3234c2d348bc38de7962cca0cc169b86b216' in prepared['prior']
    profile = v.rotation_profile(prepared['addendum'], prepared['candidate'], get(b.CANDIDATE), b.criterion())
    assert profile == get(v.ROTATION_CANDIDATE)['candidate_axes']['rotate']['consumer_fields']
    assert all('/outputs/' not in i['path'] for i in inputs)


def test_two_maps_pass_separate_yaw_and_original_B_bytes_unchanged(yaw_templates):
    original = v.validate(yaw_templates)
    combined = v.validate(yaw_templates, rotation_addendum=True)
    rotation = combined.pop('rotation_addendum')
    summary = combined.pop('with_rotation_addendum')
    assert serialized(original) == serialized(combined)
    assert combined['axis_pass'] == {'forward': True, 'left': True, 'rotate': None}
    assert combined['pass'] is None
    assert rotation['pass'] is True, rotation.get('eligibility_reason')
    assert rotation['scope'] == 'HELD_OUT_VALIDATION'
    assert rotation['maps_not_supplied'] == []
    assert rotation['maps_scored'] == list(MAPS)
    assert rotation['maps_not_scored'] == []
    assert summary['rotation_scope'] == 'HELD_OUT_VALIDATION'
    assert summary['pass'] is True
    ordering = rotation['ordering_evidence']
    assert ordering['verified'] is True
    assert ordering['kind'] == 'PRE_SCORING_AND_READING_NOT_PRE_COLLECTION'
    assert ordering['pre_collection_claim'] is False
    assert v.utc(combined['ordering_evidence']['earliest']['utc']) < v.utc(ordering['commitment']['created_at'])
    assert v.utc(ordering['commitment']['created_at']) < v.utc(ordering['raw_read_started_at']) <= v.utc(ordering['scoring_started_at'])
    assert rotation['scoring_source']['sha256'] == b.sha(Path(v.__file__).read_bytes())
    assert {str(v.ROTATION_SNAPSHOT), str(v.ROTATION_MANIFEST)} <= {i['path'] for i in rotation['input_files']}


@pytest.mark.parametrize('axis', [0, 1])
@pytest.mark.parametrize('failure', [False, True])
def test_same_translation_synthetic_decisions_byte_for_byte(monkeypatch, axis, failure):
    data, candidate, _ = synthetic(axis)
    if failure:
        data['pose'][:, axis] *= 10
    # Exercise validate orchestration with the same synthetic data in both modes.
    monkeypatch.setattr(v, 'load_collection', lambda *a: ([data], [
        {'utc': '2026-10-02T19:00:00Z', 'kind': 'synthetic'}]))
    read = v.read_json
    monkeypatch.setattr(v, 'read_json', lambda path, inputs: candidate if path == b.CANDIDATE else read(path, inputs))
    before = v.validate(['synthetic'])
    after = v.validate(['synthetic'], rotation_addendum=True)
    for name in ('rotation_addendum', 'with_rotation_addendum'):
        after.pop(name)
    assert serialized(before) == serialized(after)
    assert after['axis_pass'][b.AXES[axis]] is not failure


@pytest.mark.parametrize('failure_map', [None, 0, 1])
def test_yaw_exact_frozen_metrics_and_any_map_failure(failure_map):
    data, profile = yaw_case()
    cases = [copy.deepcopy(data) for _ in MAPS]
    for i, case in enumerate(cases):
        case['map_id'] = MAPS[i]
        if failure_map == i:
            case['pose'][:, 2] *= 10
    report = v.score_rotation(cases, profile, set(), b.criterion())
    assert report['pass'] is (failure_map is None)
    for case, result in zip(cases, report['cases']):
        assert serialized(result['metrics']) == serialized(b.evaluate_axis(case, 2, profile, b.criterion()))
        assert set(result['metrics']['steps']) == {'0.2', '0.5', '1.0', '2.0', '3.0', '3.2'}
        assert all(len(row['component_pass']) == 3 for row in b.all_rows(result['metrics']))


@pytest.mark.parametrize('failure', [False, True])
def test_missing_map_cannot_pass_but_does_not_hide_failure(failure):
    data, profile = yaw_case()
    if failure:
        data['pose'][:, 2] *= 10
    report = v.score_rotation([data], profile, set(), b.criterion())
    assert report['pass'] is (False if failure else None)
    assert report['scope'] == 'PARTIAL_MAPS'
    assert len(report['maps_not_supplied']) == 1
    assert report['maps_scored'] == [data['map_id']]
    assert report['maps_not_scored'] == report['maps_not_supplied']


@pytest.mark.parametrize('excluded_index', [0, 1])
@pytest.mark.parametrize('failure', [False, True])
def test_prior_bytes_excluded_per_case_remaining_map_uses_frozen_metrics(monkeypatch, excluded_index, failure):
    data, profile = yaw_case()
    cases = [copy.deepcopy(data) for _ in MAPS]
    for i, case in enumerate(cases):
        case.update(map_id=MAPS[i], pose_sha256=f'synthetic-pose-{i}')
    remaining_index = 1-excluded_index
    if failure:
        cases[remaining_index]['pose'][:, 2] *= 10
    prior = {cases[excluded_index]['pose_sha256']}
    evaluate = b.evaluate_axis
    calls = []
    def checked(case, *args):
        assert case['pose_sha256'] not in prior, 'excluded pose must not be scored'
        calls.append(case['map_id'])
        return evaluate(case, *args)
    monkeypatch.setattr(b, 'evaluate_axis', checked)
    report = v.score_rotation(cases, profile, prior, b.criterion())
    assert calls == [MAPS[remaining_index]]
    excluded, remaining = report['cases'][excluded_index], report['cases'][remaining_index]
    assert excluded['reason'] == 'PREVIOUSLY_SEEN_POSE_BYTES'
    assert excluded['pose_sha256'] in prior
    assert excluded['metrics'] is excluded['pass'] is None
    assert 'numerical_pass' not in excluded
    assert remaining['pass'] is (not failure)
    assert serialized(remaining['metrics']) == serialized(evaluate(cases[remaining_index], 2, profile, b.criterion()))
    assert report['scope'] == 'PARTIAL_MAPS'
    assert report['maps_observed'] == list(MAPS)
    assert report['maps_not_supplied'] == []
    assert report['maps_scored'] == [MAPS[remaining_index]]
    assert report['maps_not_scored'] == [MAPS[excluded_index]]
    assert report['pass'] is (False if failure else None)


def test_all_prior_cases_are_null_without_vacuous_pass(monkeypatch):
    data, profile = yaw_case()
    cases = [dict(data, map_id=m) for m in MAPS]
    monkeypatch.setattr(b, 'evaluate_axis', lambda *a: pytest.fail('excluded pose evaluated'))
    report = v.score_rotation(cases, profile, {data['pose_sha256']}, b.criterion())
    assert report['scope'] == 'PARTIAL_MAPS'
    assert report['maps_scored'] == []
    assert report['maps_not_scored'] == list(MAPS)
    assert report['pass'] is None
    assert all(r['reason'] == 'PREVIOUSLY_SEEN_POSE_BYTES' for r in report['cases'])


@pytest.mark.parametrize('prior_bytes', [False, True])
@pytest.mark.parametrize('invalid', ['training', 'training_map', 'unknown_map', 'dt', 'duplicate_map'])
def test_rotation_hard_failures_survive_prior_exclusion(monkeypatch, prior_bytes, invalid):
    data, profile = yaw_case()
    gate = b.criterion()
    cases = [dict(data, map_id=m) for m in MAPS]
    if invalid == 'training': cases[1]['training'] = True
    elif invalid == 'training_map': cases[1]['map_id'] = gate['held_out']['training_map']
    elif invalid == 'unknown_map': cases[1]['map_id'] = 'unregistered'
    elif invalid == 'dt': cases[1]['dt'] = .1
    else: cases[1]['map_id'] = cases[0]['map_id']
    prior = {data['pose_sha256']} if prior_bytes else set()
    monkeypatch.setattr(b, 'evaluate_axis', lambda *a: pytest.fail('hard audit must finish before scoring'))
    with pytest.raises(ValueError, match='rotation training, map or sample interval|duplicate rotation map'):
        v.score_rotation(cases, profile, prior, gate)


@pytest.mark.parametrize('missing', ['candidate', 'steps', 'prbs', 'positive_step', 'negative_step',
                                    'positive_prbs', 'negative_prbs', 'horizon'])
def test_missing_yaw_support_stays_null(missing):
    data, profile = yaw_case()
    if missing == 'candidate': profile = None
    elif missing in ('steps', 'prbs'): data['segments']['rotate'][missing] = []
    elif missing == 'horizon': data['segments']['rotate']['prbs'] = [(0, 10)]
    else:
        sign, split = missing.split('_')
        for start, end in data['segments']['rotate']['steps' if split == 'step' else 'prbs']:
            u = data['u'][start:end, 2]
            u[u > 0 if sign == 'positive' else u < 0] = 0
    report = v.score_rotation([data], profile, set(), b.criterion())
    assert report['cases'][0]['pass'] is None
    assert report['scope'] == 'PARTIAL_MAPS'
    assert report['maps_scored'] == []
    assert report['maps_not_scored'] == list(MAPS)


@pytest.mark.parametrize('side', [-1, 1])
def test_yaw_threshold_just_below_and_above_p95(side):
    data, profile = yaw_case()
    gate = b.criterion()
    times = np.arange(len(data['pose']))*.05
    probe = copy.deepcopy(data)
    probe['pose'][:, 2] += times*.001
    peak = max(r['normalized_abs_error_p95'][2] for r in b.all_rows(b.evaluate_axis(probe, 2, profile, gate)))
    data['pose'][:, 2] += times*(.001*2/peak)*(1+side*1e-7)
    result = v.score_rotation([data], profile, set(), gate)['cases'][0]
    peak = max(r['normalized_abs_error_p95'][2] for r in b.all_rows(result['metrics']))
    assert abs(peak-2) < 1e-5
    assert (peak < 2) is (side < 0)
    assert result['pass'] is (side < 0)
    assert serialized(result['metrics']) == serialized(b.evaluate_axis(data, 2, profile, gate))


@pytest.mark.parametrize('outside', [9, 10, 11])
def test_yaw_coverage_boundary_is_reported_without_relaxing_p95(outside):
    # A 90% coverage group still fails p95; the frozen rules are conjunctive.
    errors = np.zeros((100, 3))
    errors[:outside, 2] = 2.000001
    covariance = np.tile(np.eye(3), (100, 1, 1))
    row = b.metrics(errors, covariance, b.criterion())
    assert row['coverage_2sigma'][2] == (100-outside)/100
    assert row['component_pass'] == [True, True, False]


@pytest.mark.parametrize('target', ['addendum', 'candidate', 'manifest', 'snapshot'])
@pytest.mark.parametrize('mode', ['tamper', 'missing'])
def test_rotation_file_tampering_fails_closed(tmp_path, monkeypatch, target, mode):
    paths = {'addendum': v.ROTATION_ADDENDUM, 'candidate': v.ROTATION_CANDIDATE,
             'manifest': v.ROTATION_MANIFEST, 'snapshot': v.ROTATION_SNAPSHOT}
    path = paths[target]
    original = b.read_input
    def changed(p, inputs):
        blob = original(p, inputs)
        if p == path:
            if mode == 'missing': raise OSError('synthetic missing evidence')
            return blob+b' '
        return blob
    monkeypatch.setattr(b, 'read_input', changed)
    with pytest.raises((ValueError, OSError), match='hash mismatch|missing evidence'):
        v.prepare_rotation([])


@pytest.mark.parametrize('mode', ['match', 'edited', 'unavailable'])
def test_rotation_refetch_matches_or_fails_closed(monkeypatch, mode):
    remote = get(v.ROTATION_SNAPSHOT)
    def fetch(argv, **kwargs):
        assert argv == ['gh', 'api', v.ROTATION_COMMENT_API]
        if mode == 'unavailable': raise subprocess.TimeoutExpired(argv, 30)
        if mode == 'edited': remote['body'] += ' edited'
        return json.dumps(remote)
    monkeypatch.setattr(v.subprocess, 'check_output', fetch)
    if mode == 'match':
        assert v.prepare_rotation([], refetch=True)['snapshot']['id'] == 5966135675
    else:
        with pytest.raises(ValueError, match='unavailable|changed'):
            v.prepare_rotation([], refetch=True)


@pytest.mark.parametrize('stamp', ['2026-10-03T05:56:18Z', '2026-10-03T05:56:19Z'])
def test_commitment_must_precede_reading_and_scoring(yaw_templates, monkeypatch, stamp):
    monkeypatch.setattr(v, 'now_utc', lambda: stamp)
    report = v.validate(yaw_templates, rotation_addendum=True)
    assert report['axis_pass']['forward'] is True
    assert report['rotation_addendum']['pass'] is None
    assert 'strictly before' in report['rotation_addendum']['eligibility_reason']


def test_clock_regression_after_reading_is_ineligible(yaw_templates, monkeypatch):
    times = iter(['2026-10-03T06:00:00Z', '2026-10-03T06:00:01Z', '2026-10-03T05:56:19Z'])
    monkeypatch.setattr(v, 'now_utc', lambda: next(times))
    report = v.validate(yaw_templates, rotation_addendum=True)
    assert report['rotation_addendum']['scope'] == 'INELIGIBLE'


def test_failed_rotation_refetch_preserves_original_B(yaw_templates, monkeypatch):
    original = v.validate(yaw_templates)
    def fetch(argv, **kwargs):
        if argv[-1] == v.COMMENT_API:
            return json.dumps(get(v.SNAPSHOT))
        raise subprocess.TimeoutExpired(argv, 30)
    monkeypatch.setattr(v.subprocess, 'check_output', fetch)
    report = v.validate(yaw_templates, rotation_addendum=True, refetch=True)
    assert report['axis_pass'] == original['axis_pass']
    assert serialized(report['cases']) == serialized(original['cases'])
    assert report['rotation_addendum']['scope'] == 'INELIGIBLE'
    assert report['rotation_addendum']['ordering_evidence']['github_check'] == 'requested'


@pytest.mark.parametrize('field,value', [('id', 1), ('html_url', 'https://example.com'),
    ('updated_at', '2026-10-03T06:00:00Z'), ('body_sha256', '0'*64), ('listed_sha256', {})])
def test_snapshot_semantic_checks_even_if_digest_is_replaced(monkeypatch, field, value):
    snapshot = get(v.ROTATION_SNAPSHOT)
    snapshot[field] = value
    blob = json.dumps(snapshot).encode()
    original = b.read_input
    monkeypatch.setattr(b, 'read_input', lambda p, inputs: blob if p == v.ROTATION_SNAPSHOT else original(p, inputs))
    monkeypatch.setattr(v, 'ROTATION_SNAPSHOT_SHA256', b.sha(blob))
    with pytest.raises(ValueError, match='identity/body/edit'):
        v.prepare_rotation([])


def test_training_pose_from_manifest_is_excluded_without_reopening_training(yaw_templates, monkeypatch):
    load = v.load_collection
    prior = get(v.ROTATION_MANIFEST)['files'][6]['sha256']
    assert prior not in get(b.CANDIDATE)['previously_seen_pose_sha256']
    def previously_seen(*args):
        cases, stamps = load(*args)
        if cases[0]['map_id'] == MAPS[1]:
            cases[0]['pose_sha256'] = prior
        return cases, stamps
    monkeypatch.setattr(v, 'load_collection', previously_seen)
    original = v.validate(yaw_templates)
    report = v.validate(yaw_templates, rotation_addendum=True)
    assert report['axis_pass']['forward'] is True
    rotation = report.pop('rotation_addendum')
    summary = report.pop('with_rotation_addendum')
    assert serialized(report) == serialized(original)
    assert rotation['scope'] == summary['rotation_scope'] == 'PARTIAL_MAPS'
    assert rotation['maps_scored'] == [MAPS[0]]
    assert rotation['maps_not_scored'] == [MAPS[1]]
    assert rotation['cases'][0]['pass'] is True
    assert rotation['cases'][1]['reason'] == 'PREVIOUSLY_SEEN_POSE_BYTES'
    assert rotation['pass'] is summary['pass'] is None


def test_duplicate_synthetic_pose_bytes_excluded_in_cli(yaw_templates, tmp_path, monkeypatch, capsys):
    # A fabricated training copy has exactly the second map's pose bytes.
    # All paths are pytest temporaries; no real training/held-out raw is opened.
    pose = yaw_templates[1]/MAPS[1]/'eval_only/r1/pose.jsonl'
    training_pose = tmp_path/'synthetic_training_pose.jsonl'
    training_pose.write_bytes(pose.read_bytes())
    prior_sha = b.sha(training_pose.read_bytes())
    assert prior_sha == b.sha(pose.read_bytes())
    assert prior_sha != b.sha((yaw_templates[0]/MAPS[0]/'eval_only/r1/pose.jsonl').read_bytes())
    prepare = v.prepare_rotation
    def with_synthetic_prior(*args, **kwargs):
        prepared = prepare(*args, **kwargs)
        prepared['prior'].add(prior_sha)
        return prepared
    monkeypatch.setattr(v, 'prepare_rotation', with_synthetic_prior)
    args = [a for root in yaw_templates for a in ('--raw', str(root))]
    output = tmp_path/'partial-duplicate.json'
    original = v.validate(yaw_templates)
    assert v.main([*args, '--rotation-addendum', '--output', str(output)]) == 2
    report = get(output)
    rotation = report.pop('rotation_addendum')
    summary = report.pop('with_rotation_addendum')
    assert serialized(report) == serialized(original)
    assert rotation['cases'][0]['pass'] is True
    assert rotation['cases'][1]['reason'] == 'PREVIOUSLY_SEEN_POSE_BYTES'
    assert rotation['cases'][1]['pose_sha256'] == prior_sha
    assert rotation['cases'][1]['metrics'] is rotation['cases'][1]['pass'] is None
    assert rotation['scope'] == summary['rotation_scope'] == 'PARTIAL_MAPS'
    assert rotation['maps_scored'] == summary['rotation_maps_scored'] == [MAPS[0]]
    assert rotation['maps_not_scored'] == summary['rotation_maps_not_scored'] == [MAPS[1]]
    assert rotation['maps_not_supplied'] == []
    assert rotation['pass'] is summary['pass'] is None
    printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert printed[1]['with_rotation_addendum'] == summary


@pytest.mark.parametrize('corruption', ['lease', 'command_clock', 'pose_clock', 'receipt'])
def test_yaw_reuses_v91_input_audit(yaw_raw, corruption):
    folder = yaw_raw/MAPS[0]
    if corruption == 'receipt':
        put(folder/'artifacts.sha256.json', {})
    else:
        pose = corruption == 'pose_clock'
        path = folder/('eval_only/r1/pose.jsonl' if pose else 'robots/r1/commands.jsonl')
        rows = b.rows(path.read_bytes())
        row = rows[1] if pose else next(r for r in rows if r['kind'] == 'mecanum')
        row['duration_s' if corruption == 'lease' else 't'] += .01
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        receipts(yaw_raw)
    report = v.validate([yaw_raw], rotation_addendum=True)
    assert report['scope'] == report['rotation_addendum']['scope'] == 'INELIGIBLE'
    assert report['with_rotation_addendum']['pass'] is None


def test_mutation_during_yaw_revokes_both_reports(yaw_raw, monkeypatch):
    score = v.score_rotation
    def changed(*args):
        report = score(*args)
        (yaw_raw/'plan.json').write_text('{}')
        return report
    monkeypatch.setattr(v, 'score_rotation', changed)
    report = v.validate([yaw_raw], rotation_addendum=True)
    assert report['scope'] == report['rotation_addendum']['scope'] == 'INELIGIBLE'
    assert report['axis_pass'] == dict.fromkeys(b.AXES)
    assert report['with_rotation_addendum']['pass'] is None


def test_yaw_evidence_mutation_revokes_only_yaw(yaw_templates, tmp_path, monkeypatch):
    snapshot = tmp_path/'commitment.json'
    snapshot.write_bytes(v.ROTATION_SNAPSHOT.read_bytes())
    monkeypatch.setattr(v, 'ROTATION_SNAPSHOT', snapshot)
    score = v.score_rotation
    def changed(*args):
        report = score(*args)
        snapshot.write_text('{}')
        return report
    monkeypatch.setattr(v, 'score_rotation', changed)
    report = v.validate(yaw_templates, rotation_addendum=True)
    assert report['axis_pass'] == {'forward': True, 'left': True, 'rotate': None}
    assert report['rotation_addendum']['scope'] == 'INELIGIBLE'
    assert report['rotation_addendum']['ordering_evidence']['verified'] is False
    assert 'changed during validation' in report['rotation_addendum']['eligibility_reason']


@pytest.mark.parametrize('component', [0, 1, 2])
def test_yaw_gates_all_three_error_components(component):
    data, profile = yaw_case()
    data['pose'][:, component] += np.arange(len(data['pose']))*.002
    report = v.score_rotation([data], profile, set(), b.criterion())
    assert report['pass'] is False
    assert any(not row['component_pass'][component] for row in b.all_rows(report['cases'][0]['metrics']))


def test_translation_failure_survives_successful_yaw(yaw_raw, yaw_templates, tmp_path):
    folder = yaw_raw/MAPS[0]
    path = folder/'eval_only/r1/pose.jsonl'
    rows = b.rows(path.read_bytes())
    for row in rows:
        row['base_position_m'][0] *= 10
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    receipts(yaw_raw)
    roots = [yaw_raw, yaw_templates[1]]
    original = v.validate(roots)
    combined = v.validate(roots, rotation_addendum=True)
    assert combined['rotation_addendum']['pass'] is True
    assert combined['with_rotation_addendum']['pass'] is False
    for name in ('rotation_addendum', 'with_rotation_addendum'):
        combined.pop(name)
    assert serialized(combined) == serialized(original)
    args = [a for root in roots for a in ('--raw', str(root))]
    assert v.main([*args, '--rotation-addendum', '--output', str(tmp_path/'failed.json')]) == 1


@pytest.mark.parametrize('field,value', [('tau_s', [1, 1, 1]), ('tau_stop_s', 0),
    ('noise_rel', [0, 0, 0]), ('noise_abs', [0, 0, 0]), ('gain', np.eye(3).tolist()),
    ('rest_noise', False), ('use_scale', True), ('scale_std', .1), ('scale_walk', .1)])
def test_profile_semantics_fail_closed_even_apart_from_hash_check(field, value):
    prepared = v.prepare_rotation([])
    candidate = prepared['candidate']
    candidate['candidate_axes']['rotate']['consumer_fields'][field] = value
    with pytest.raises(ValueError):
        v.rotation_profile(prepared['addendum'], candidate, get(b.CANDIDATE), b.criterion())


@pytest.mark.parametrize('field', ['status', 'axis_validation', 'motion', 'forward', 'command'])
def test_candidate_state_and_translation_preservation(field):
    prepared = v.prepare_rotation([])
    candidate = prepared['candidate']
    if field == 'status': candidate['status'] = 'MEASURED_SIM'
    if field == 'axis_validation': candidate['axis_validation']['rotate'] = True
    if field == 'motion': candidate['params']['motion'] = {}
    if field == 'forward': candidate['candidate_axes']['forward']['consumer_fields']['tau_s'] = 99.
    if field == 'command': candidate['candidate_axes']['rotate']['allowed_command_axis'] = 'rotate'
    with pytest.raises(ValueError):
        v.rotation_profile(prepared['addendum'], candidate, get(b.CANDIDATE), b.criterion())


def test_cli_opt_in_exit_code_and_no_overwrite(yaw_templates, tmp_path):
    args = [a for root in yaw_templates for a in ('--raw', str(root))]
    path = tmp_path/'result.json'
    assert v.main([*args, '--rotation-addendum', '--output', str(path)]) == 0
    assert get(path)['pass'] is None
    assert get(path)['with_rotation_addendum']['pass'] is True
    with pytest.raises(FileExistsError):
        v.main([*args, '--rotation-addendum', '--output', str(path)])
    assert v.main(['--raw', str(yaw_templates[0]), '--rotation-addendum',
                   '--output', str(tmp_path/'partial.json')]) == 2


def test_yaw_suite_is_collected():
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    assert collect_test_files(v.ROOT, TEST_PATTERNS).count('tests/test_consumer_criterion_b_v91_yaw.py') == 1
