from types import SimpleNamespace
import pytest
from scripts.act16w_curriculum import StartCurriculum


def fixture():
    episodes = [dict(seed=s, split='train') for s in range(4)] + [dict(seed=9, split='validation')]
    data = SimpleNamespace(manifest={'episodes': episodes}, shards=[None]*4,
                           index=[(j, i) for j in range(4) for i in range(j+1)])
    starts = [dict(seed=s, object_kind='cyan' if s < 2 else 'red',
                   start_distance_m=float(s % 2 + 1), abs_start_yaw_rad=float(s % 2)) for s in range(4)]
    return data, starts


def test_easy_to_full_preserves_kind_coverage_and_excludes_validation():
    data, starts = fixture()
    cur = StartCurriculum(data, starts)
    assert set(cur.eligible(0)) == {0, 3, 4, 5}
    assert set(cur.eligible(.75)) == set(range(10))
    assert set(cur.eligible(1)) == set(range(10))


def test_validation_metadata_or_missing_train_metadata_is_rejected():
    data, starts = fixture()
    with pytest.raises(ValueError):
        StartCurriculum(data, starts[:-1])
    with pytest.raises(ValueError):
        StartCurriculum(data, starts + [{**starts[0], 'seed': 9}])
