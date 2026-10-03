"""Synthetic-only overlap regressions; forbidden held-out raw is never opened."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from harness.kinematic_overlap import POLICY, audit, overlap, read_trace, trace
from scripts import validate_consumer_criterion_b_v94 as validator


def rows(n=40):
    return [{'t': i*.05, 'base_position_m': [i*.003, -.8+i*.0001, .03],
             'base_rotation': np.eye(3).tolist()} for i in range(n)]


def write(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r)+'\n' for r in values))
    return path


@pytest.fixture(autouse=True)
def no_real_raw(monkeypatch):
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert '/Users/changmin/projects/ugrp/outputs/' not in str(path.resolve())
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)


def test_identical_bytes_are_previously_seen(tmp_path):
    a = write(tmp_path/'a.jsonl', rows())
    b = write(tmp_path/'b.jsonl', rows())
    assert a.read_bytes() == b.read_bytes()
    assert overlap(read_trace(a), read_trace(b))['status'] == 'PREVIOUSLY_SEEN'


def test_corridor_extra_wall_field_does_not_change_identity(tmp_path):
    a, b = rows(), rows()
    for r in a:
        r['wall_clearance_lower_bound_m'] = .5
    for r in b:
        r.update(wall_clearance_lower_bound_m=1.7, unrelated_score='DO_NOT_USE', map_id='other')
    pa, pb = write(tmp_path/'door.jsonl', a), write(tmp_path/'corridor.jsonl', b)
    assert pa.read_bytes() != pb.read_bytes()
    ta, tb = read_trace(pa), read_trace(pb)
    assert ta.sha256 == tb.sha256
    assert overlap(ta, tb)['max_position_difference_m'] == 0


@pytest.mark.parametrize('offset', [0., 700., -99.])
def test_shifted_partial_overlap_is_found_inside_both_traces(offset):
    a, b = rows(), rows(65)
    # All other points differ. Match only 9 consecutive interior points.
    for r in b:
        r['base_position_m'][0] += 100.
        r['t'] += offset
    for i in range(9):
        b[20+i]['base_position_m'] = copy.deepcopy(a[11+i]['base_position_m'])
        b[20+i]['base_rotation'] = copy.deepcopy(a[11+i]['base_rotation'])
    witness = overlap(trace(a), trace(b))
    assert witness['candidate_indices'][0] == 11
    assert witness['prior_indices'][0] == 20
    assert witness['samples'] == 5
    assert abs(witness['clock_shift_s'] - (.55-1.-offset)) < 1e-9


def test_genuinely_different_trajectory_is_disjoint():
    a, b = rows(), rows()
    for r in b:
        r['base_position_m'][1] += .001
    assert overlap(trace(a), trace(b)) is None


@pytest.mark.parametrize('delta,seen', [(0.5e-9, True), (2e-9, False)])
def test_absolute_tolerance_no_relative_scaling(delta, seen):
    a, b = rows(), rows()
    for r in b:
        r['base_position_m'][1] += delta
    assert (overlap(trace(a), trace(b)) is not None) == seen


def test_short_isolated_points_are_not_a_window():
    a, b = rows(), rows()
    for i, r in enumerate(b):
        if i % 4 == 0:
            r['base_position_m'][1] += 1.
    assert overlap(trace(a), trace(b)) is None


def test_whole_short_prior_is_conservatively_excluded():
    a = rows()
    assert overlap(trace(a), trace(a[12:16]))['samples'] == 4


def test_coarse_history_uses_actual_common_lattice():
    a = rows()
    witness = overlap(trace(a), trace(a[::4]))
    assert witness['samples'] == 2
    assert witness['matched_duration_s'] == pytest.approx(.2)


@pytest.mark.parametrize('corruption', ['nan', 'missing', 'reversed', 'rotation', 'single'])
def test_malformed_pose_fails_closed(corruption):
    a = rows()
    if corruption == 'nan': a[2]['base_position_m'][0] = float('nan')
    if corruption == 'missing': del a[3]
    if corruption == 'reversed': a[4]['t'] = a[3]['t']
    if corruption == 'rotation': a[0]['base_rotation'][0][0] = 2
    if corruption == 'single': a = a[:1]
    with pytest.raises(ValueError):
        trace(a)


def test_v91_gate_rejects_before_any_legacy_result_or_residual_reads(tmp_path, monkeypatch):
    from scripts import validate_consumer_criterion_b_v91 as old
    path = write(tmp_path/'map/eval_only/r1/pose.jsonl', rows())
    monkeypatch.setattr(validator, 'load_prior', lambda: [read_trace(path)])
    monkeypatch.setattr(old, 'validate', lambda *a, **kw: pytest.fail('scorer must not run'))
    result = validator.validate_v91([tmp_path])
    assert result['pass'] is None
    assert result['cases'] == []
    assert result['eligibility_reason'] == 'PREVIOUSLY_SEEN_KINEMATICS'


def test_all_prior_robots_are_compared_not_only_same_id():
    a, b = trace(rows(), 'r2-new'), trace(rows(), 'r1-training')
    result = audit([a], [b])
    assert result['status'] == 'PREVIOUSLY_SEEN'
    assert len(result['comparisons']) == 1


def test_frozen_hashes_unchanged_and_tests_registered():
    from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files
    frozen = validator.verify_frozen()
    assert frozen['experiments/2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json'].startswith('74c312b5')
    for name in ('tests/test_consumer_criterion_b_v94.py', 'tests/test_zone_final_pair_new_starts.py'):
        assert collect_test_files(validator.ROOT, TEST_PATTERNS).count(name) == 1
