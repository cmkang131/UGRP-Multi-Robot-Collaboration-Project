"""Local raw replay; CI skips missing raw/native dependency, never renders."""
import pytest

from scripts.verify_final_pair_fast_guard import RAW_CASES, replay


@pytest.mark.parametrize('case', RAW_CASES, ids=['unloaded', 'fine'])
def test_every_recorded_full_qpos_row_matches_old_guard(case):
    if not (case/'eval_only/trajectory.jsonl').is_file():
        pytest.skip('completed local v88 raw is absent')
    pytest.importorskip('mujoco')
    report = replay(case)
    assert report['rows'] == 7401
    assert report['mismatches'] == 0
