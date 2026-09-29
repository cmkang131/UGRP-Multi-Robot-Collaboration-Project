"""Pure-python checks of the seg-lightfloor study (no renderer, no torch, no physics)."""
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / 'experiments' / '2026-09-29-seg-lightfloor'
sys.path.insert(0, str(S))
import floors  # noqa: E402


def test_train_looks_are_deterministic_and_avoid_held_out_floors():
    a, b = floors.train_looks(24), floors.train_looks(24)
    assert a == b and len({l['name'] for l in a}) == 24
    for look in a:
        mean = (np.array(look['rgb1']) + np.array(look['rgb2'])) / 2
        for h in floors.HELD_OUT:
            assert np.linalg.norm(mean - (np.array(h['rgb1']) + np.array(h['rgb2'])) / 2) >= .10
        assert all(0. <= c <= 1. for c in look['rgb1'] + look['rgb2'])


def test_held_out_looks_have_unique_names_and_are_not_training_names():
    names = [h['name'] for h in floors.HELD_OUT] + [floors.HELD_OUT_WALL['name']]
    assert len(set(names)) == len(names)
    assert not set(names) & {l['name'] for l in floors.train_looks(24)}


def test_look_hash_changes_with_colour():
    a = dict(floors.HELD_OUT[0])
    b = {**a, 'rgb1': [.5, .5, .5]}
    assert floors.look_sha(a) != floors.look_sha(b) and floors.look_sha(a) == floors.look_sha(dict(a))


def test_pass_criterion_constants_match_the_task():
    src = (S / 'score_b1.py').read_text()
    assert 'pos <= 0.05 and yaw <= 2.0' in src
    # station exclusion of the training renderer must cover the 18 B1 stations of the 9 route points
    text = (S / 'render_static_set.py').read_text()
    assert 'EXCL_POS_M, EXCL_YAW = 0.30, math.radians(30.)' in text and 'def eval_stations' in text
