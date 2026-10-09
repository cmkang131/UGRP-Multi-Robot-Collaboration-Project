"""Bounded pure-result caches for controller work; never touch PF/RNG state.

Input snapshots compare bits, including signed zero and NaN payloads. Returning
owned copies preserves mutable-result semantics. No observation skipping,
particle reduction, changed arithmetic or physics approximation is included.
"""
from collections import OrderedDict
import copy
from dataclasses import astuple, is_dataclass
from functools import wraps
import hashlib
import os
from pathlib import Path
import inspect
import importlib
import sys

import numpy as np

ENV = 'UGRP_CONTROLLER_EXACT_SPEEDUPS'
DEFAULT = 'exact-v1'
MODES = ('off', DEFAULT)


def mode(value=None):
    selected = os.environ.get(ENV, DEFAULT) if value is None else value
    if selected not in MODES:
        raise ValueError(f'{ENV} must be one of {MODES}, got {selected!r}')
    return selected


def array_equal(a, b):
    if a.shape != b.shape or a.dtype != b.dtype:
        return False
    if a.dtype.hasobject:
        return False
    if a.flags.c_contiguous and b.flags.c_contiguous and a.nbytes % 8 == 0:
        return np.array_equal(a.reshape(-1).view(np.uint64), b.reshape(-1).view(np.uint64))
    return a.tobytes() == b.tobytes()


class ArrayRevision:
    """An owned snapshot; in-place prediction/reweighting invalidates it."""
    def __init__(self):
        self.saved = None
        self.revision = 0

    def __call__(self, *arrays):
        if self.saved is None or len(arrays) != len(self.saved) or not all(
                array_equal(a, b) for a, b in zip(arrays, self.saved)):
            self.saved = tuple(a.copy() for a in arrays)
            self.revision += 1
        return self.revision


class PosteriorMemo:
    """Per-posterior content cache, bounded across robot/filter instances."""
    def __init__(self, function, maxsize=4):
        self.function, self.maxsize = function, maxsize
        self.entries = OrderedDict()
        self.hits = self.misses = 0

    def __call__(self, *arrays):
        if not arrays or any(type(a) is not np.ndarray or a.dtype.hasobject for a in arrays):
            return self.function(*arrays)
        owner = id(arrays[0])
        entry = self.entries.get(owner)
        if entry is None or entry[0] is not arrays[0]:
            entry = [arrays[0], ArrayRevision(), None, None]
            self.entries[owner] = entry
            if len(self.entries) > self.maxsize:
                self.entries.popitem(last=False)
        self.entries.move_to_end(owner)
        current = entry[1](*arrays)
        if current != entry[2]:
            result = self.function(*arrays)
            entry[2], entry[3] = current, copy.deepcopy(result)
            self.misses += 1
            return result
        self.hits += 1
        return copy.deepcopy(entry[3])


def key(value):
    if type(value) is np.ndarray and not value.dtype.hasobject:
        return ('array', value.dtype.str, value.shape, value.tobytes())
    if isinstance(value, np.generic) and not value.dtype.hasobject:
        return ('scalar', value.dtype.str, value.tobytes())
    if is_dataclass(value):
        return ('dataclass', type(value), key(astuple(value)))
    if isinstance(value, (tuple, list)):
        return (type(value), tuple(key(x) for x in value))
    if type(value) in (float, int, bool, str, type(None)):
        return (type(value), np.float64(value).tobytes() if type(value) is float else value)
    raise TypeError('unsupported exact cache input')


class PureMemo:
    """LRU for small geometry inputs; keep original calculation on a miss."""
    def __init__(self, function, *, maxsize=32):
        self.function, self.maxsize = function, maxsize
        self.entries = OrderedDict()
        self.hits = self.misses = 0

    def __call__(self, *args, **kwargs):
        try:
            current = (key(args), key(tuple(sorted(kwargs.items()))))
        except TypeError:
            return self.function(*args, **kwargs)
        if current in self.entries:
            self.hits += 1
            self.entries.move_to_end(current)
            return copy.deepcopy(self.entries[current])
        result = self.function(*args, **kwargs)
        self.misses += 1
        self.entries[current] = copy.deepcopy(result)
        if len(self.entries) > self.maxsize:
            self.entries.popitem(last=False)
        return result


class MethodSummaryMemo:
    """Audited OwnCam moments depend on px/logw; timestamps stay live."""
    def __init__(self, function, maxsize=4):
        self.function, self.maxsize = function, maxsize
        self.entries = OrderedDict()
        self.hits = self.misses = 0

    def __call__(self, owner):
        if not owner.initialized or any(type(a) is not np.ndarray or a.dtype.hasobject
                                        for a in (owner.px, owner.logw)):
            return self.function(owner)
        identity = id(owner)
        if identity not in self.entries:
            self.entries[identity] = [owner, ArrayRevision(), None, None]
            if len(self.entries) > self.maxsize:
                self.entries.popitem(last=False)
        self.entries.move_to_end(identity)
        entry = self.entries[identity]
        revision = entry[1](owner.px, owner.logw)
        if revision != entry[2]:
            result = self.function(owner)
            entry[2], entry[3] = revision, copy.deepcopy(result)
            self.misses += 1
        else:
            self.hits += 1
        result = copy.deepcopy(entry[3])
        result['t'] = round(owner.t, 4)
        result['since_tag_s'] = None if owner.last_tag_t is None else round(owner.t-owner.last_tag_t, 3)
        return result


class IntegerClipNumpy:
    """Exact int64 scalar clamp; arrays/floats/other signatures use NumPy."""
    def __getattr__(self, name):
        return getattr(np, name)

    @staticmethod
    def clip(value, lower, upper, *args, **kwargs):
        if (not args and not kwargs and type(value) in (int, np.int64)
                and type(lower) is int and type(upper) is int
                and all(-(1 << 63) <= x < (1 << 63) for x in (value, lower, upper))):
            return np.int64(min(max(int(value), lower), upper))
        return np.clip(value, lower, upper, *args, **kwargs)


def memo(function, *, selected=None, maxsize=4):
    if mode(selected) == 'off':
        return function
    cache = PosteriorMemo(function, maxsize)
    @wraps(function)
    def calculate(*arrays):
        return cache(*arrays)
    calculate.exact_cache = cache
    return calculate


def receipt(selected=None):
    selected = mode(selected)
    return dict(schema='ugrp.controller_exact_speedups.v1', mode=selected,
        enabled=selected != 'off', module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        distribution_changed=False, rng_changed=False, observation_skipping=False, physics_changed=False)


class ForecastCopy:
    """Share old immutable evidence rows only inside an audited virtual rollout.

    The rollout appends to copied history lists and mutates copied cell/particle
    arrays. It never modifies an existing history row, decisions or ledger.
    This avoids deep-copying ever-growing diagnostic records for every path.
    """
    @staticmethod
    def deepcopy(value, memo=None):
        memo = {} if memo is None else dict(memo)
        if hasattr(value, 'maps') and hasattr(value, 'histories'):
            if hasattr(value, 'decisions'):
                memo[id(value.decisions)] = value.decisions
            # ledger aliases the selected particle's mutable history LIST.
            # Preserve that alias in the clone, but copy the list before append.
            if hasattr(value, 'ledger'):
                memo[id(value.ledger)] = list(value.ledger)
            for history in value.histories:
                for row in history:
                    memo[id(row)] = row
        return copy.deepcopy(value, memo)


class Installation:
    """One simulation process, reversible patches, guards for optional adapters."""
    def __init__(self, selected=None):
        self.record = receipt(selected)
        self.restore = []
        self.caches = {}
        self.record.update(applied=[], fallback=[])

    def replace(self, owner, name, value):
        original = getattr(owner, name)
        self.restore.append(lambda: setattr(owner, name, original))
        setattr(owner, name, value)

    def aliases(self, original, replacement):
        for name, module in list(sys.modules.items()):
            if name.startswith(('harness.', 'scripts.')):
                for attribute, value in list(vars(module).items()):
                    if value is original:
                        self.replace(module, attribute, replacement)

    def guard(self, function, expected, name):
        actual = hashlib.sha256(inspect.getsource(function).encode()).hexdigest()
        if actual != expected:
            self.record['fallback'].append(name + ':source_changed')
            return False
        return True

    def optional(self, name):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            self.record['fallback'].append(name + ':not_in_source')
            return None

    def install(self):
        if not self.record['enabled']:
            return self
        from harness.zone_final_pair_binding import bind
        # Common S2/S3 pure posterior calculations. Sources containing the
        # existing per-runtime S3 cache retain that cache and its audit bytes.
        from harness import zone_solo_cyan_augmented_start as global_start
        from harness.owncam_localizer import OwnCamLocalizer
        if self.guard(OwnCamLocalizer.estimate,
                '9c6516fb0df8a7b5a0eb11954b87a544fcad82dc6d7d75a8af70a4a687f24327', 'owncam_moments'):
            cached = MethodSummaryMemo(OwnCamLocalizer.estimate)
            self.replace(OwnCamLocalizer, 'estimate', lambda owner, cache=cached: cache(owner))
            self.caches['owncam_moments'] = cached
            self.record['applied'].append('owncam_moments')
        from harness import zone_pair_highpose_opencv_exact as opencv
        if self.guard(opencv.install,
                '939633d488b4d2d2ceb7cec4cc30270deecd162c18dfe2a1ef3fe8b6b35f80d3', 'opencv_integer_clip'):
            self.aliases(opencv.install, bind(opencv.install, np=IntegerClipNumpy()))
            self.record['applied'].append('opencv_integer_clip')
        if self.guard(global_start.belief_report,
                '7c0acfa9ce86e0a26348a6e56f193533f87c5c89428e7ce16a4430d9c4fd0207', 'posterior_summary'):
            summary = memo(global_start.belief_report, selected=DEFAULT)
            self.aliases(global_start.belief_report, summary)
            self.caches['posterior_summary'] = summary.exact_cache
            self.record['applied'].append('posterior_summary')

        s3 = self.optional('harness.zone_s3_exact_cache')
        if s3 and self.guard(s3.attach,
                'c4d45dc3c5757ba11562c91cbc87d177e4a153495b4dc853f909c9a41e7d5a16', 's3_cache'):
            # Reuse PR416's pure-summary boundary, preserving legacy option,
            # hit/miss rows, timestamps and health. Only the exact key changes.
            def memo_summary(function, audit):
                revision = ArrayRevision()
                saved_key = saved = None
                def summarize(px, weights):
                    nonlocal saved_key, saved
                    current = revision(px, weights)
                    if current != saved_key:
                        saved = function(px, weights)
                        saved_key = current
                        audit['misses'] += 1
                    else:
                        audit['hits'] += 1
                    return copy.deepcopy(saved)
                return summarize
            def memo_extract(function, audit):
                revision = ArrayRevision()
                saved_key = saved = None
                def extract(px, weights, labels, old):
                    nonlocal saved_key, saved
                    offset = old.get('pan_yaw_offset', 0.)
                    current = (revision(px, weights, labels), key(offset))
                    if current != saved_key:
                        saved = function(px, weights, labels, {'pan_yaw_offset': offset})
                        saved.pop('pan_yaw_offset')
                        saved_key = current
                        audit['misses'] += 1
                    else:
                        audit['hits'] += 1
                    return {**old, **copy.deepcopy(saved)}
                return extract
            attach = bind(s3.attach, memo_summary=memo_summary, memo_extract=memo_extract)
            self.aliases(s3.attach, attach)
            self.record['applied'].append('s3_exact_snapshot_keys')

        rbpf = self.optional('harness.self_map_rbpf')
        if rbpf:
            for name, expected, size in (
                ('offsets_grid', '93e05a341b200d181c37a981913b7605ce5acaa3c7bf18a1cbb10afcaf047b3b', 32),
                ('sensor_sigma', '1ef3a10c8ccef3b97e01a4aac7fbfde8717f4072879b589a647d1be9dd400922', 8)):
                original = getattr(rbpf, name)
                if self.guard(original, expected, name):
                    cached = PureMemo(original, maxsize=size)
                    self.aliases(original, cached)
                    self.caches[name] = cached
                    self.record['applied'].append(name)
            field = rbpf.GridField
            if self.guard(field.__init__, 'f3c4b4f4fdd15cc68bcf2b3c953c2e0508e013588b2b8012efe8172f9607db52', 'grid_field') and self.guard(
                    field.query, '6d5691dda6f25897a3879849254bb7715fab8ab9269630662167261540a2db87', 'field_query'):
                cached = PureMemo(field, maxsize=32)
                self.aliases(field, cached)
                self.caches['grid_field'] = cached
                self.record['applied'].append('grid_field')
            information = self.optional('harness.active_information_gain')
            guards = [] if not information else [
                (information.forecast, 'cbbe99d7810a015859b0e7ec1d85b9148e88616778c86effa2ee16a81e0327b1', 'forecast_copy'),
                (information.trajectory_entropy, '45d8d24fe076c8dc6051a808e151fdb2a732bb1cddc805e1fb0b105fa0575ab8', 'trajectory_entropy'),
                (information.entropy, '3af1b4d0d27002fbf30cae46bd93d1b91cb94ec21993e985714b679348429219', 'entropy'),
                (rbpf.RaoBlackwellizedGrid.resample_if_needed, 'e66873c4b0a2406622df2e99fb1acf4ca562486b932c49ce70c0a41fd944aaa5', 'rbpf_resample'),
                (rbpf.RaoBlackwellizedGrid.propagate, '1033fbc6eb86c1dec8d8d09149140be3b67d5c7f537bf11cf18a08636d3bc70d', 'rbpf_propagate')]
            if guards and all(self.guard(function, expected, name) for function, expected, name in guards):
                self.aliases(information.forecast, bind(information.forecast, copy=ForecastCopy))
                self.record['applied'].append('forecast_evidence_copy')
        return self

    def snapshot(self):
        return {**self.record, 'caches': {name: dict(hits=c.hits, misses=c.misses,
            entries=len(c.entries), max_entries=c.maxsize) for name, c in self.caches.items()}}

    def close(self):
        for restore in reversed(self.restore):
            restore()
        self.restore.clear()


def install(selected=None):
    setup = Installation(selected)
    try:
        return setup.install()
    except BaseException:
        setup.close()
        raise
