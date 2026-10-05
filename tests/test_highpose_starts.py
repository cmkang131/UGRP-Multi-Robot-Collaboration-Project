"""REVIEW_363 P2-1: dev replay vs frozen confirmation starts (no raw read)."""
import copy
import json

import numpy as np
import pytest

from harness import zone_pair_highpose_starts as s


def test_frozen_starts_differ_numerically_from_dev_prior_and_each_other():
    r = s.registration()
    assert len(r['confirmation_starts']) == 3 and r['dev']['seed'] == 911
    prior = [row['pose'] for row in r['prior_start_sources']]
    poses = [p for row in r['confirmation_starts'] for p in row['spawns'].values()]
    for i, pose in enumerate(poses):
        assert min(np.hypot(pose[0]-q[0], pose[1]-q[1]) for q in prior) >= s.MIN_START_SEPARATION_M
        assert all(np.hypot(pose[0]-q[0], pose[1]-q[1]) >= s.MIN_START_SEPARATION_M for q in poses[i+1:])
    for row in r['confirmation_starts']:
        assert s.require_novel_start(row)
        with pytest.raises(ValueError, match='SEED_911'):
            s.require_dev_seed(row['seed'])
    s.require_dev_seed(911)


@pytest.mark.parametrize('offset', [0., .01, .049])
def test_renamed_reseeded_or_nudged_prior_start_is_rejected(offset):
    r = s.registration()
    candidate = copy.deepcopy(r['confirmation_starts'][0])
    pose = list(r['prior_start_sources'][0]['pose'])
    pose[0] += offset
    candidate.update(map_id='different-map', seed=candidate['seed']+999)
    candidate['spawns']['r3'] = pose        # different robot id than the prior row
    with pytest.raises(ValueError, match='DUPLICATES_PRIOR'):
        s.require_novel_start(candidate, r)


def _write(path, rows):
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    return path


def _rows(t0=0., x0=0., extra=None, n=40):
    eye = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    return [{'t': t0+.05*i, 'base_position_m': [x0+.002*i, 0., .033], 'base_rotation': eye,
             **(extra or {})} for i in range(n)]


def test_motion_content_not_bytes_decides_duplicate(tmp_path):
    reg = copy.deepcopy(s.registration())
    reg['prior_trajectory_inventory_complete'] = True       # test-only corpus
    candidate = reg['confirmation_starts'][0]
    prior = s.read_trace(_write(tmp_path/'prior.jsonl', _rows(extra={'wall_clearance_lower_bound_m': .3})))
    # #219 corridor case: same t/position/rotation, other per-map field differs
    # -> different file bytes, still a duplicate. Clock shift is also free.
    same = s.read_trace(_write(tmp_path/'same.jsonl', _rows(extra={'wall_clearance_lower_bound_m': .9})))
    shifted = s.read_trace(_write(tmp_path/'shifted.jsonl', _rows(t0=100.)))
    assert (tmp_path/'prior.jsonl').read_bytes() != (tmp_path/'same.jsonl').read_bytes()
    for dup in (same, shifted):
        with pytest.raises(ValueError, match='TRAJECTORY_DUPLICATES_PRIOR'):
            s.qualify_confirmation(candidate, {'r1': dup, 'r2': dup}, [prior], reg)
    novel = s.read_trace(_write(tmp_path/'novel.jsonl', _rows(x0=.25)))
    got = s.qualify_confirmation(candidate, {'r1': novel, 'r2': novel}, [prior], reg)
    assert got['confirmation_eligible'] and got['overlap_policy']['identity_fields'] == ['t', 'base_position_m', 'base_rotation']


def test_confirmation_refused_without_prior_inventory_and_v91_raw_never_read(tmp_path):
    reg = s.registration()
    novel = s.read_trace(_write(tmp_path/'novel.jsonl', _rows(x0=.25)))
    with pytest.raises(ValueError, match='INVENTORY_REQUIRED'):
        s.qualify_confirmation(reg['confirmation_starts'][0], {'r1': novel, 'r2': novel}, [novel], reg)
    with pytest.raises(ValueError, match='forbidden'):
        s.read_trace(tmp_path/'final-pair-v91-heldout-x'/'eval_only'/'r1'/'pose.jsonl')
