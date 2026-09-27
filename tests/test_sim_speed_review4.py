"""Recording starts after scene setup, not at the first global physics step."""
import json

import pytest

from scripts import sim_equivalence as eq
from sim_speed_fixtures import (LOGS, RECORDING_START_SIM_S as START, full_run,
                                refresh_manifest, write_rows)


def set_manifest_start(run, value):
    path = run/'manifest.json'
    meta = json.loads(path.read_text())
    meta['recording_start_sim_s'] = value
    path.write_text(json.dumps(meta))


def rows(run, name):
    return [json.loads(line) for line in (run/name).read_text().splitlines()]


@pytest.mark.parametrize('source', ['first_samples', 'manifest', 'log', 'both'])
def test_post_setup_start_is_equivalent_and_explained(tmp_path, source):
    a, b = (full_run(tmp_path/s) for s in ('a', 'b'))
    for run in (a, b):
        if source in ('manifest', 'both'):
            set_manifest_start(run, START)
        if source in ('log', 'both'):
            name = 'controller_events.jsonl'
            write_rows(run/name, [{'event': 'recording_started', 't': START}] + rows(run, name))
            refresh_manifest(run)
    report = eq.compare(a, b)
    assert report['verdict'] == 'equivalent', report['evidence_errors']
    for start in report['recording_start'].values():
        assert start['sim_s'] == START
        assert start['inferred'] == (source == 'first_samples')
        assert start['sources']
        if start['inferred']:
            assert 'before the first samples' in start['limitation']


def test_manifest_start_does_not_replace_legacy_log_evidence(tmp_path):
    a, b = (full_run(tmp_path/s) for s in ('a', 'b'))
    set_manifest_start(b, START)
    report = eq.compare(a, b)
    assert report['equivalent'], report
    assert report['recording_start']['A']['inferred']
    assert not report['recording_start']['B']['inferred']


@pytest.mark.parametrize('source', ['manifest', 'log'])
@pytest.mark.parametrize('start', [0., START - .1, START + .1])
def test_explicit_start_rejects_initial_gap_or_samples_before_start(tmp_path, source, start):
    run = full_run(tmp_path/'run')
    if source == 'manifest':
        set_manifest_start(run, start)
    else:
        name = 'controller_events.jsonl'
        write_rows(run/name, [{'event': 'recording_started', 't': start}] + rows(run, name))
        refresh_manifest(run)
    report = eq.compare(run, run)
    assert report['verdict'] == 'insufficient_evidence'
    assert any('initial sample' in e for e in report['evidence_errors'])


def test_first_sample_one_step_after_explicit_start_is_allowed(tmp_path):
    run = full_run(tmp_path/'run')
    set_manifest_start(run, 1.3)  # one .00025 step, rounded to four decimals
    report = eq.compare(run, run)
    assert report['equivalent'], report['evidence_errors']


@pytest.mark.parametrize('source', ['manifest', 'log'])
@pytest.mark.parametrize('value', [None, True, '1.3003', -1., float('nan'), float('inf'), {}, []])
def test_invalid_explicit_start_cannot_fall_back_to_samples(tmp_path, source, value):
    run = full_run(tmp_path/'run')
    if source == 'manifest':
        set_manifest_start(run, value)
    else:
        name = 'controller_events.jsonl'
        write_rows(run/name, [{'event': 'recording_started', 't': value}] + rows(run, name))
        refresh_manifest(run)
    report = eq.compare(run, run)
    assert report['verdict'] == 'insufficient_evidence'
    assert any('recording start' in e for e in report['evidence_errors'])


@pytest.mark.parametrize('name', [LOGS[1], 'eval_only/gt_trajectory.jsonl'])
@pytest.mark.parametrize('case', ['missing_time', 'invalid_time', 'missing_first_sample'])
def test_fallback_requires_agreeing_first_frame_and_gt(tmp_path, name, case):
    run = full_run(tmp_path/'run')
    data = rows(run, name)
    if case == 'missing_time':
        data[0].pop('t')
    elif case == 'invalid_time':
        data[0]['t'] = float('nan')
    else:
        data.pop(0)
        if name == LOGS[1]:
            # Repair counts, indices and hashes so they cannot mask the start check.
            for i, row in enumerate(data): row['frame'] = i
            eval_rows = rows(run, 'eval_only/frames_eval.jsonl')[1:]
            for i, row in enumerate(eval_rows): row['frame'] = i
            write_rows(run/'eval_only/frames_eval.jsonl', eval_rows)
            result = json.loads((run/'result.json').read_text())
            result['frames'] = len(data)
            (run/'result.json').write_text(json.dumps(result))
    write_rows(run/name, data)
    refresh_manifest(run)
    report = eq.compare(run, run)
    assert report['verdict'] == 'insufficient_evidence'
    assert any('recording start' in e for e in report['evidence_errors'])


def test_conflicting_manifest_and_log_start_is_insufficient(tmp_path):
    run = full_run(tmp_path/'run')
    set_manifest_start(run, START)
    name = 'controller_events.jsonl'
    write_rows(run/name, [{'event': 'recording_started', 't': START + .0001}] + rows(run, name))
    refresh_manifest(run)
    report = eq.compare(run, run)
    assert report['verdict'] == 'insufficient_evidence'
    assert any('recording start' in e for e in report['evidence_errors'])


def test_duplicate_start_markers_are_insufficient(tmp_path):
    run = full_run(tmp_path/'run')
    name = 'controller_events.jsonl'
    marker = {'event': 'recording_started', 't': START}
    write_rows(run/name, [marker, marker] + rows(run, name))
    refresh_manifest(run)
    report = eq.compare(run, run)
    assert report['verdict'] == 'insufficient_evidence'
    assert any('duplicate' in e for e in report['evidence_errors'])


def test_explicit_start_detects_both_streams_missing_the_initial_interval(tmp_path):
    run = full_run(tmp_path/'run')
    set_manifest_start(run, START)
    for name in (LOGS[1], 'eval_only/frames_eval.jsonl', 'eval_only/gt_trajectory.jsonl'):
        data = [r for r in rows(run, name) if r['t'] >= START + .2]
        for i, row in enumerate(data):
            if 'frame' in row: row['frame'] = i
        write_rows(run/name, data)
    result = json.loads((run/'result.json').read_text())
    result['frames'] = len(rows(run, LOGS[1]))
    (run/'result.json').write_text(json.dumps(result))
    refresh_manifest(run)
    report = eq.compare(run, run)
    assert report['verdict'] == 'insufficient_evidence'
    assert len([e for e in report['evidence_errors'] if 'missing initial sample' in e]) == 4


@pytest.mark.parametrize('explicit', [False, True])
def test_runs_with_different_recording_starts_are_insufficient(tmp_path, explicit):
    a, b = (full_run(tmp_path/s) for s in ('a', 'b'))
    if explicit:
        # Both starts are individually within the first-step tolerance.
        set_manifest_start(a, START)
        set_manifest_start(b, START - .0001)
    else:
        # Each run is independently valid; only their start references differ.
        for name in LOGS:
            data = rows(b, name)
            for row in data:
                if 't' in row and row.get('kind') != 'initial_servo_command':
                    row['t'] = round(row['t'] + .4, 4)
            write_rows(b/name, data)
        result = json.loads((b/'result.json').read_text())
        result['sim_s'] += .4
        result['phase_times'] = {k: v + .4 for k, v in result['phase_times'].items()}
        (b/'result.json').write_text(json.dumps(result))
        refresh_manifest(b)
        assert eq.compare(b, b)['equivalent']
    report = eq.compare(a, b)
    assert report['verdict'] == 'insufficient_evidence'
    assert any('recording start' in e and 'A/B' in e for e in report['evidence_errors'])
