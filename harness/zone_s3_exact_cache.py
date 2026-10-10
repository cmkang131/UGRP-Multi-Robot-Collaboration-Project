"""Opt-in exact posterior memoization; never changes particles, RNG or KLD.

Global scan publishes the same stationary posterior many times. Cache only
pure particle/weight summaries by content, retaining timestamps, pose offsets,
health fields and per-frame audit updates from the original call path.
"""
import copy
import hashlib
from types import SimpleNamespace
import numpy as np
from harness.zone_final_pair_binding import bind

OPTION = 'posterior_content_v1'
REVISION_OPTION = 'posterior_content_v2'


class ArrayRevision:
    """Exact owned snapshot comparison; no digest, array identity or clock key.

    Prediction/reweighting can change an array in place between RGB frames.
    Compare its bits each time, but recompute statistics only on a change.
    uint64 comparison reduces temporary memory vs byte-wise comparison; the
    fallback covers noncontiguous/odd-sized arrays. Signed zero is significant.
    """
    def __init__(self):
        self.saved = None
        self.revision = 0

    def __call__(self, *arrays):
        def equal(a, b):
            if a.shape != b.shape or a.dtype != b.dtype:
                return False
            if a.flags.c_contiguous and b.flags.c_contiguous and a.nbytes % 8 == 0:
                return np.array_equal(a.reshape(-1).view(np.uint64), b.reshape(-1).view(np.uint64))
            return a.tobytes() == b.tobytes()
        if self.saved is None or len(arrays)!=len(self.saved) or not all(equal(a,b) for a,b in zip(arrays,self.saved)):
            self.saved = tuple(a.copy() for a in arrays)
            self.revision += 1
        return self.revision


class ByteRevision:
    """Private best-cluster partition key; exact bytes equality instead of hash."""
    def __init__(self):
        self.saved = None
        self.revision = 0

    def blake2b(self, data, *, digest_size):
        if data != self.saved:
            self.saved = data
            self.revision += 1
        revision = self.revision
        return SimpleNamespace(digest=lambda: revision)


def key(*arrays):
    h = hashlib.blake2b(digest_size=32)
    for array in arrays:
        h.update(str((array.shape, array.dtype.str)).encode())
        h.update(array.tobytes())
    return h.digest()


def memo_summary(function, audit, content_key=key):
    saved_key = saved = None
    def summarize(px, weights):
        nonlocal saved_key, saved
        current = content_key(px, weights)
        if current != saved_key:
            saved = function(px, weights)
            saved_key = current
            audit['misses'] += 1
        else:
            audit['hits'] += 1
        return copy.deepcopy(saved)
    return summarize


def memo_extract(function, audit, content_key=key):
    saved_key = saved = None
    def extract(px, weights, labels, old):
        nonlocal saved_key, saved
        current = (content_key(px, weights, labels), old.get('pan_yaw_offset', 0.))
        if current != saved_key:
            saved = function(px, weights, labels, {'pan_yaw_offset': current[1]})
            saved.pop('pan_yaw_offset')
            saved_key = current
            audit['misses'] += 1
        else:
            audit['hits'] += 1
        return {**old, **copy.deepcopy(saved)}
    return extract


def attach(runtime, *, exact_cache='off'):
    if exact_cache == 'off':
        return runtime
    if exact_cache not in (OPTION, REVISION_OPTION):
        raise ValueError('unknown exact posterior cache')
    pf = runtime.pose.provider.loc._pf
    loc = runtime.pose.provider.loc
    if getattr(pf.estimate, '__name__', None) != 'report' or 'belief_report' not in pf.estimate.__globals__:
        raise ValueError('expected untouched global posterior reporting closure')
    if getattr(loc.estimate, '__name__', None) != 'estimate' or 'extract' not in loc.estimate.__globals__:
        raise ValueError('expected best-cluster reporting closure')
    audit = dict(option=exact_cache, hits=0, misses=0, distribution_changed=False)
    revision = exact_cache == REVISION_OPTION
    pf.estimate = bind(pf.estimate, belief_report=memo_summary(pf.estimate.__globals__['belief_report'], audit,
        ArrayRevision() if revision else key))
    options = dict(extract=memo_extract(loc.estimate.__globals__['extract'], audit,
        ArrayRevision() if revision else key))
    if revision:
        options['hashlib'] = ByteRevision()
    loc.estimate = bind(loc.estimate, **options)
    runtime.s3_exact_cache = audit
    previous_record = runtime.record
    def record():
        return {**previous_record(), 's3_exact_cache': copy.deepcopy(audit)}
    runtime.record = record
    return runtime
