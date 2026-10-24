"""Offline gate runner: G4 transition measurement amendment regression tests."""
import importlib.util
from pathlib import Path

from harness import pairact_r1 as p

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    'pairact_r1_offline', ROOT / 'scripts/pairact_r1_offline.py')
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


def test_transition_recall_registered_counts_one_row_ready_across_segment_split():
    # GT: alignment, ready (1 row), execute x3. The ready->execute boundary
    # starts a new segment (GO-wait control-period gap) but stays inside one
    # episode; the registered transition must still be counted (regression
    # for the 2026-10-25 gate measurement amendment: the frozen harness's
    # segment adjacency test recorded total=0 for every ready->execute).
    target = [1, 2, 3, 3, 3]
    segments = [0, 0, 1, 1, 1]
    out = runner.transition_recall_registered(list(target), target, segments, 10, [0] * 5)
    assert out['ready->execute'] == dict(hits=1, total=1, recall=1.0)
    assert out['alignment->ready']['total'] == 1
    # The frozen harness function (segment rule) still records total=0 here.
    legacy = p.transition_recall(list(target), target, segments, 10)
    assert legacy['ready->execute']['total'] == 0
    # A stage change across an episode boundary is not a transition.
    cross = runner.transition_recall_registered(list(target), target, segments, 10, [0, 0, 1, 1, 1])
    assert cross['ready->execute']['total'] == 0


def test_transition_recall_registered_episode_guard_overrides_segment_adjacency():
    # Same segment id on both sides of the boundary: the registered
    # (episode) rule must not count a cross-episode stage change.
    target = [1, 2, 3, 3, 3]
    segments = [0, 0, 0, 0, 0]
    guarded = runner.transition_recall_registered(list(target), target, segments, 10, [0, 0, 1, 1, 1])
    assert guarded['ready->execute']['total'] == 0
    same_ep = runner.transition_recall_registered(list(target), target, segments, 10, [0] * 5)
    assert same_ep['ready->execute'] == dict(hits=1, total=1, recall=1.0)
