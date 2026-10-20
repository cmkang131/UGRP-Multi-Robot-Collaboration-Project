"""Unit tests for the ACT18 C4c kind aggregation helpers (CPU only, no data needed)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from act18_c4c_kind import episode_summary, sort_counts, summarize  # noqa: E402


def row(t, skill, pwm1, pe=0.0, se=0.0, servo4=1830):
    return dict(t=t, skill=skill, skill_elapsed_s=se, pwm_elapsed_s=pe,
                teacher_pwm={'1': pwm1, '3': 740, '4': servo4, '5': 2210, '6': 1500})


def release_rows(pose_shift=0):
    rows = [row(0.0, 'release', 1500, pe=11.3, se=0.0),
            row(0.1, 'release', 1500, pe=11.4, se=0.1)]
    rows += [row(0.2 + 0.1 * i, 'release', 1500, pe=0.0, se=round(0.2 + 0.1 * i, 6)) for i in range(3)]
    # pose move onset at 0.6: servo4 jumps by >= 3 (the open ramp starts after it)
    rows.append(row(0.6, 'release', 1500, pe=0.0, se=0.6, servo4=1830 + pose_shift))
    rows += [row(0.7, 'release', 1552, pe=0.0, se=0.7),
             row(0.8, 'release', 1676, pe=0.0, se=0.8),
             row(0.9, 'release', 1900, pe=0.0, se=0.9)]
    return rows


def test_episode_summary_finds_open_and_pose_onset():
    summary = episode_summary(release_rows(pose_shift=4))
    assert summary['release_ticks'] == 9
    assert summary['open_skill_elapsed_s'] == pytest.approx(0.9)
    assert summary['entry_pwm_elapsed_s'] == 11.3
    assert summary['pose_pwm_elapsed_s'] == pytest.approx(0.0)
    assert summary['pose_pwm']['4'] == 1834


def test_episode_summary_requires_release_rows():
    with pytest.raises(ValueError):
        episode_summary([row(0.0, 'grasp', 2000)])


def test_episode_summary_without_open():
    rows = [row(0.0, 'release', 1500, pe=11.3, se=0.0),
            row(0.1, 'release', 1500, pe=0.0, se=0.1)]
    summary = episode_summary(rows)
    assert summary['open_skill_elapsed_s'] is None
    assert summary['pose_pwm_elapsed_s'] is None


def test_sort_counts_rounds_and_sorts():
    assert sort_counts([4.40000000001, 4.4, 4.5, None]) == {4.4: 2, 4.5: 1}


def test_summarize_aggregates_by_kind():
    first = episode_summary(release_rows(pose_shift=4))
    first.update(seed=1, kind='cyan')
    second = episode_summary(release_rows(pose_shift=7))
    second.update(seed=2, kind='cyan')
    report = summarize([first, second])
    assert set(report) == {'cyan'}
    assert report['cyan']['demos'] == 2
    assert report['cyan']['opens'] == 2
    assert report['cyan']['open_skill_elapsed_s'] == {0.9: 2}
    assert report['cyan']['pose_pwm']['4']['spread'] == 3
