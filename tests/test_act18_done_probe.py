"""Default-off done-probability recording hook in the ACT18 evaluation path."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_evaluate import DONE_PROB_ENV, done_prob_log_path, done_prob_row


def test_done_prob_row_records_full_chunk_probabilities():
    observation = dict(sample_id='warp3-88600-0-g0:0:r1', t=12.3, skill='grasp', robot_id='r1')
    row = done_prob_row(observation, 1, [0.02, 0.125, 0.999999])
    assert row['schema'] == 'ugrp.act18.done_prob_row.v1'
    assert row['world'] == 1 and row['chunk'] == 3 and row['skill'] == 'grasp'
    assert row['t'] == 12.3 and row['sample_id'] == observation['sample_id']
    assert row['done_probs'] == [0.02, 0.125, 0.999999]


def test_done_prob_row_rejects_invalid_probabilities():
    observation = dict(sample_id='x', t=0.0, skill='grasp', robot_id='r1')
    with pytest.raises(ValueError, match='nonempty list'):
        done_prob_row(observation, 0, [])
    with pytest.raises(ValueError, match=r'\[0,1\]'):
        done_prob_row(observation, 0, [0.5, 1.5])
    with pytest.raises(ValueError, match=r'\[0,1\]'):
        done_prob_row(observation, 0, [0.5, -0.1])


def test_done_prob_recording_is_off_unless_explicitly_enabled(monkeypatch, tmp_path):
    monkeypatch.delenv(DONE_PROB_ENV, raising=False)
    assert done_prob_log_path() is None
    target = tmp_path / 'done.jsonl'
    monkeypatch.setenv(DONE_PROB_ENV, str(target))
    assert done_prob_log_path() == target
