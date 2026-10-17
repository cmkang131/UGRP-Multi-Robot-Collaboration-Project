"""Beamact5 round-2 opt-in modes: registration, defaults and numeric identity."""
import argparse
import numpy as np

from sim.grasp_act_search15_modes import ALL_MODES, add_arguments, validate
from sim.grasp_act_search23 import rectangle_gaps, rectangle_gaps_many


def test_new_modes_are_registered_and_default_off():
    assert ALL_MODES['search23_rects'] == 'search23_batched_rects_v1'
    assert ALL_MODES['search26_circles'] == 'search26_downfirst_circles_v1'
    assert ALL_MODES['search26_static_peer'] == 'search26_static_peer_stance_v1'
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args([])
    assert args.search23_rects == 'off'
    assert args.search26_circles == 'off'
    assert args.search26_static_peer == 'off'


def test_r2_profile_passes_the_unchanged_validator():
    values = {k: 'off' for k in ALL_MODES}
    values.update(search23_rects='search23_batched_rects_v1',
                  search26_circles='search26_downfirst_circles_v1',
                  search26_static_peer='search26_static_peer_stance_v1')
    validate(values, recovery='progress_view_recovery_v3', profile='visible_only',
             pose_source='issued', coordination='off')


def test_batched_rect_gaps_matches_per_rect_values():
    rng = np.random.default_rng(7)
    poses = rng.normal(scale=1.2, size=(37, 2))
    yaw = rng.uniform(-np.pi, np.pi, size=len(poses))
    rects = []
    for _ in range(23):
        rects.append((rng.uniform(-2, 2), rng.uniform(-2, 2),
                      rng.uniform(.01, .4), rng.uniform(.01, .4),
                      rng.uniform(-np.pi, np.pi)))
    expected = np.stack([rectangle_gaps(poses, yaw, r) for r in rects], axis=1)
    got = rectangle_gaps_many(poses, yaw, rects)
    assert got.shape == expected.shape
    assert np.array_equal(got, expected)
    # The chunk bound must not change any value.
    small = rectangle_gaps_many(poses, yaw, rects, pair_budget=8)
    assert np.array_equal(small, expected)
    empty = rectangle_gaps_many(poses, yaw, [])
    assert empty.shape == (len(poses), 0)
