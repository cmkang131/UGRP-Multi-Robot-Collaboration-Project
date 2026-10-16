"""Sharding must retain every seed/case, including sparse mutation seeds."""
from collections import Counter

import pytest

from tests.zone_multiturn_ci import shard_assignments


@pytest.mark.parametrize('count', [1, 3, 16])
def test_seed_ranges_cover_every_case_once_without_splitting_a_seed(count):
    cases = ([(str(n), seed) for n in (12, 100, 200, 300, 1000, 3000) for seed in range(n)]
             + [('mutation', seed) for seed in (1, 30, 479, 1235)]
             + [('extra', None)] * 431 + [('300', 287)])
    owners = shard_assignments(cases, count)
    pieces = [[i for i, owner in enumerate(owners) if owner == shard] for shard in range(count)]
    assert Counter(i for piece in pieces for i in piece) == Counter(range(len(cases)))
    assert owners[-1] == owners[cases.index(('300', 287))]
    for family in {family for family, seed in cases if seed is not None}:
        rows = sorted(set((seed, owners[i]) for i, (name, seed) in enumerate(cases) if name == family))
        assert [owner for seed, owner in rows] == sorted(owner for seed, owner in rows)
        sizes = Counter(owner for seed, owner in rows)
        assert max(sizes.get(i, 0) for i in range(count)) - min(sizes.get(i, 0) for i in range(count)) <= 1


@pytest.mark.parametrize('cases,count', [([], 0), ([('bad', True)], 16), ([('bad', '1')], 16)])
def test_invalid_shard_inputs_fail(cases, count):
    with pytest.raises(ValueError):
        shard_assignments(cases, count)
