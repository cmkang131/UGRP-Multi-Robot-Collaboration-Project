"""Opt-in exact validation shortcuts; never cache mutable controller state."""
from dataclasses import dataclass
from functools import lru_cache
from contextvars import ContextVar
from contextlib import contextmanager


@dataclass(frozen=True)
class Options:
    provenance_index: bool = False
    sha_validation_cache: bool = False
    omit_discarded_copy: bool = False
    scalar_cells: bool = False
    geometry_cache: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in vars(self).values()):
            raise ValueError('BOOLEAN_EXACT_SPEEDUP_REQUIRED')


OFF = Options()
_ACTIVE = ContextVar('e2e_exact_geometry_options',default=OFF)


@contextmanager
def using(options):
    token=_ACTIVE.set(options)
    try:yield
    finally:_ACTIVE.reset(token)


def cells_enabled():return _ACTIVE.get().scalar_cells
def geometry_enabled():return _ACTIVE.get().geometry_cache


def invalid_sha(value):
    return any(c not in '0123456789abcdef' for c in value)


cached_invalid_sha = lru_cache(maxsize=8192)(invalid_sha)


class ObservedIndex:
    """Local to one synchronous validation call; no stale cross-call index.

    Index only ordinary closed scalar dictionaries; unsupported values retain
    Python list equality. The underlying input is never mutated or reordered.
    """
    keys = ('robot_id', 'frame_id', 't_sim', 'sha256')

    def __init__(self, observed):
        self.observed = observed
        self.index = set()
        self.fallback = []
        for ref in observed:
            key = self.key(ref)
            if key is None:self.fallback.append(ref)
            else:self.index.add(key)

    @classmethod
    def key(cls, ref):
        if type(ref) is not dict or set(ref) != set(cls.keys):return None
        values = tuple(ref[k] for k in cls.keys)
        if any(type(v) not in (str, int, float, bool, type(None)) for v in values):return None
        return values

    def __contains__(self, ref):
        key = self.key(ref)
        if key is None:return ref in self.observed
        return key in self.index or ref in self.fallback
