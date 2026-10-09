"""Opt-in exact posterior memoization; never changes particles, RNG or KLD.

Global scan publishes the same stationary posterior many times. Cache only
pure particle/weight summaries by content, retaining timestamps, pose offsets,
health fields and per-frame audit updates from the original call path.
"""
import copy
import hashlib
from harness.zone_final_pair_binding import bind

OPTION = 'posterior_content_v1'


def key(*arrays):
    h = hashlib.blake2b(digest_size=32)
    for array in arrays:
        h.update(str((array.shape, array.dtype.str)).encode())
        h.update(array.tobytes())
    return h.digest()


def memo_summary(function, audit):
    saved_key = saved = None
    def summarize(px, weights):
        nonlocal saved_key, saved
        current = key(px, weights)
        if current != saved_key:
            saved = function(px, weights)
            saved_key = current
            audit['misses'] += 1
        else:
            audit['hits'] += 1
        return copy.deepcopy(saved)
    return summarize


def memo_extract(function, audit):
    saved_key = saved = None
    def extract(px, weights, labels, old):
        nonlocal saved_key, saved
        current = (key(px, weights, labels), old.get('pan_yaw_offset', 0.))
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
    if exact_cache != OPTION:
        raise ValueError('unknown exact posterior cache')
    pf = runtime.pose.provider.loc._pf
    loc = runtime.pose.provider.loc
    if getattr(pf.estimate, '__name__', None) != 'report' or 'belief_report' not in pf.estimate.__globals__:
        raise ValueError('expected untouched global posterior reporting closure')
    if getattr(loc.estimate, '__name__', None) != 'estimate' or 'extract' not in loc.estimate.__globals__:
        raise ValueError('expected best-cluster reporting closure')
    audit = dict(option=OPTION, hits=0, misses=0, distribution_changed=False)
    pf.estimate = bind(pf.estimate, belief_report=memo_summary(pf.estimate.__globals__['belief_report'], audit))
    loc.estimate = bind(loc.estimate, extract=memo_extract(loc.estimate.__globals__['extract'], audit))
    runtime.s3_exact_cache = audit
    return runtime
