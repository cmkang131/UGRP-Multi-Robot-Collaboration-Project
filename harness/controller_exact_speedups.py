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
import math
import weakref

import numpy as np

ENV = 'UGRP_CONTROLLER_EXACT_SPEEDUPS'
DEFAULT = 'exact-v1'
MODES = ('off', DEFAULT)
SCAN_ENV = 'UGRP_CONTROLLER_SCAN_SPEEDUPS'
LOCAL_ENV = 'UGRP_CONTROLLER_LOCAL_SUBMAP_M'


def scan_options():
    selected = os.environ.get(SCAN_ENV, 'exact-v2')
    if selected not in ('off', 'exact-v2'):
        raise ValueError(f'{SCAN_ENV}: off or exact-v2 required')
    radius = float(os.environ.get(LOCAL_ENV, '0'))
    if not math.isfinite(radius) or radius < 0 or radius > 6:
        raise ValueError(f'{LOCAL_ENV}: finite radius in [0, 6] required')
    return selected, radius


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


class GridFieldMemo:
    """Cache only audited constructor attributes; retain the public class API."""
    def __init__(self, cls, maxsize=32):
        self.cls, self.function, self.maxsize = cls, cls.__init__, maxsize
        self.entries = OrderedDict()
        self.hits = self.misses = 0

    def __call__(self, owner, *args, **kwargs):
        if type(owner) is not self.cls:
            return self.function(owner, *args, **kwargs)
        try:
            current = (key(args), key(tuple(sorted(kwargs.items()))))
        except TypeError:
            return self.function(owner, *args, **kwargs)
        if current in self.entries:
            self.hits += 1
            self.entries.move_to_end(current)
            for name, value in copy.deepcopy(self.entries[current]).items():
                setattr(owner, name, value)
            return None
        # A miss uses the actual owner, preserving exception-time side effects.
        self.function(owner, *args, **kwargs)
        self.misses += 1
        self.entries[current] = copy.deepcopy({name: getattr(owner, name)
            for name in ('resolution', 'origin', 'distance')})
        if len(self.entries) > self.maxsize:
            self.entries.popitem(last=False)

    def bound(self):
        @wraps(self.function)
        def initialize(owner, *args, **kwargs):
            return self(owner, *args, **kwargs)
        return initialize


class IncrementalGridFieldMemo(GridFieldMemo):
    """Exact integer nearest-site updates; large changes use the original EDT.

    No finite distance cutoff: deleting a witness invalidates every dependent
    cell, including distant cells. A KD-tree supplies a remaining witness;
    integer squared distances and SciPy's float64 sqrt/multiply are retained.
    """
    def __init__(self, cls, maxsize=16):
        super().__init__(cls, maxsize)
        self.updates = self.changed_cells = self.full_rebuilds = 0
        self.bytes, self.max_bytes = 0, 64*1024*1024

    def __call__(self, owner, points, resolution=.05):
        if (type(owner) is not self.cls or type(points) is not np.ndarray or
                points.dtype != np.float64 or points.ndim != 2 or points.shape[1] != 2 or
                not len(points) or not np.isfinite(points).all() or
                type(resolution) is not float or not 0 < resolution < math.inf):
            return self.function(owner, points, resolution)
        origin = np.floor((points.min(0)-1.)/resolution)*resolution
        size = np.ceil((points.max(0)+1.-origin)/resolution).astype(int)+1
        if np.any(size <= 0) or np.any(size > 4096) or np.prod(size) > 4_000_000:
            return self.function(owner, points, resolution)
        if int(np.prod(size))*25 > self.max_bytes:
            return self.function(owner, points, resolution)
        indices = np.rint((points-origin)/resolution).astype(int)
        occupied = np.zeros(tuple(size), bool)
        occupied[indices[:, 0], indices[:, 1]] = True
        geometry = key((origin, resolution, tuple(int(x) for x in size)))
        old = self.entries.get(geometry)
        if old is not None and np.array_equal(occupied, old['occupied']):
            self.hits += 1
            owner.resolution, owner.origin, owner.distance = resolution, origin, old['distance'].copy()
            self.entries.move_to_end(geometry)
            return None
        self.misses += 1
        additions = np.argwhere(occupied & ~old['occupied']) if old is not None else []
        affected = None
        if old is not None:
            removed = old['occupied'] & ~occupied
            affected = removed[old['nearest'][0], old['nearest'][1]]
        if old is not None and len(additions) <= 8 and np.count_nonzero(affected) <= occupied.size//4:
            from scipy.spatial import cKDTree
            nearest, squares = old['nearest'].copy(), old['squares'].copy()
            coordinates = np.indices(occupied.shape, dtype=np.int64)
            if affected.any():
                sites = np.argwhere(occupied)
                query = coordinates[:, affected].T
                _, index = cKDTree(sites).query(query, eps=0, workers=1)
                witnesses = sites[index].T
                nearest[:, affected] = witnesses
                squares[affected] = np.sum((query.T-witnesses)**2, axis=0)
            for site in additions:
                candidate = np.sum((coordinates-site[:, None, None])**2, axis=0)
                better = candidate < squares
                squares[better] = candidate[better]
                nearest[:, better] = site[:, None]
            changed = squares != old['squares']
            distance = old['distance'].copy()
            distance[changed] = np.sqrt(squares[changed].astype(np.float64))*resolution
            self.updates += 1
            self.changed_cells += int(changed.sum())
            owner.resolution, owner.origin, owner.distance = resolution, origin, distance.copy()
        else:
            # Preserve original construction, including original float64 bytes.
            from scipy.ndimage import distance_transform_edt
            self.function(owner, points, resolution)
            nearest = distance_transform_edt(~occupied, return_distances=False, return_indices=True)
            squares = np.sum((np.indices(occupied.shape, dtype=np.int64)-nearest)**2, axis=0)
            distance = owner.distance.copy()
            self.full_rebuilds += 1
        if old is not None:
            self.bytes -= old['bytes']
        size_bytes = sum(a.nbytes for a in (occupied,nearest,squares,distance))
        self.entries[geometry] = dict(occupied=occupied, nearest=nearest,
            squares=squares, distance=distance, bytes=size_bytes)
        self.bytes += size_bytes
        self.entries.move_to_end(geometry)
        while len(self.entries) > self.maxsize or self.bytes > self.max_bytes:
            self.bytes -= self.entries.popitem(last=False)[1]['bytes']

    def extra_stats(self):
        return dict(incremental_updates=self.updates, changed_distance_cells=self.changed_cells,
                    full_rebuilds=self.full_rebuilds, array_bytes=self.bytes,max_array_bytes=self.max_bytes)


class ProbabilityFieldMemo(GridFieldMemo):
    """Only changed log-odds cells are re-evaluated; geometry stays unchanged."""
    def __init__(self, cls, maxsize=32):
        super().__init__(cls, maxsize)
        self.updates = self.changed_cells = 0
        self.bytes, self.max_bytes = 0, 64*1024*1024

    def __call__(self, owner, grid):
        cells = grid.cells
        if (type(owner) is not self.cls or type(cells) is not dict or not cells or
                any(type(k) is not tuple or len(k)!=2 or any(type(i) not in (int,np.int64,np.int32) for i in k) for k in cells) or
                any(type(v) is not float or not math.isfinite(v) or abs(v) > 600 for v in cells.values())):
            return self.function(owner, grid)
        keys = np.array(list(cells))
        lower = keys.min(0)-2
        shape = tuple(keys.max(0)-lower+3)
        if np.prod(shape)*8+len(cells)*64 > self.max_bytes:
            return self.function(owner,grid)
        geometry = key((grid.resolution_m, lower, tuple(int(x) for x in shape)))
        old = self.entries.get(geometry)
        changed = [(k, v) for k, v in cells.items() if old is not None and
                   (k not in old['cells'] or key(v) != key(old['cells'][k]))]
        removed = [] if old is None else old['cells'].keys()-cells.keys()
        if old is not None and len(changed)+len(removed) < len(cells)//2:
            values = old['values'].copy()
            for k in removed:
                values[tuple(np.array(k)-lower)] = .5
            for k, v in changed:
                values[tuple(np.array(k)-lower)] = 1/(1+math.exp(-v))
            owner.resolution, owner.lower, owner.values = grid.resolution_m, lower, values
            self.hits += 1
            self.updates += 1
            self.changed_cells += len(changed)+len(removed)
        else:
            self.function(owner, grid)
            self.misses += 1
        if old is not None:
            self.bytes -= old['bytes']
        size_bytes = owner.values.nbytes+len(cells)*64
        self.entries[geometry] = dict(cells=dict(cells), values=owner.values.copy(), bytes=size_bytes)
        self.bytes += size_bytes
        self.entries.move_to_end(geometry)
        while len(self.entries) > self.maxsize or self.bytes > self.max_bytes:
            self.bytes -= self.entries.popitem(last=False)[1]['bytes']

    def extra_stats(self):
        return dict(incremental_updates=self.updates, changed_probability_cells=self.changed_cells,
                    estimated_bytes=self.bytes,max_estimated_bytes=self.max_bytes)


class GraphLoopMemo:
    """Retain pure loop results beyond the existing 8192-pair LRU.

    Prepared object identity and actual mutable field bytes are keys. Original
    GraphCache counters/lazy field construction remain unchanged. No candidate
    exclusion, score quantization, tie reordering or optimizer change.
    """
    def __init__(self, function, maxsize=65536):
        self.function, self.maxsize = function, maxsize
        self.entries = OrderedDict()
        self.hits = self.misses = self.bytes = 0
        self.max_bytes = 128*1024*1024

    @staticmethod
    def fields(prepared):
        def snapshot(field):
            if field is None:
                return None
            h = hashlib.sha256()
            for name in ('resolution', 'lower', 'values', 'origin', 'distance', 'segments'):
                if hasattr(field, name):
                    value = getattr(field, name)
                    h.update(name.encode())
                    if type(value) is np.ndarray and not value.dtype.hasobject:
                        h.update(repr((value.dtype.str, value.shape)).encode())
                        h.update(value.tobytes())
                    else:
                        h.update(repr(key(value)).encode())
            return h.digest()
        return (snapshot(prepared._probability), snapshot(prepared._distance),
                key(prepared.segments), bool(prepared.grid.cells))

    def __call__(self, submap, row, initial, options, *, prepared=None):
        if prepared is None:
            return self.function(submap, row, initial, options, prepared=prepared)
        try:
            # Cache keys must not retain the Prepared owner (and its grid/fields).
            signature = (weakref.ref(prepared), bool(submap['grid'].cells), key(row['segments']), key(initial), key(options))
            current = (signature, self.fields(prepared))
            hash(current)
        except (TypeError, AttributeError):
            return self.function(submap, row, initial, options, prepared=prepared)
        saved = self.entries.get(current)
        if saved is not None:
            self.hits += 1
            self.entries.move_to_end(current)
            return copy.deepcopy(saved[0])
        result = self.function(submap, row, initial, options, prepared=prepared)
        self.misses += 1
        # Lazy construction is part of the original call; key its post-state.
        current = (signature, self.fields(prepared))
        size = len(repr(signature)) + len(repr(result)) + 256
        if size <= self.max_bytes:
            if current in self.entries:
                self.bytes -= self.entries[current][1]
            self.entries[current] = (copy.deepcopy(result), size)
            self.entries.move_to_end(current)
            self.bytes += size
            while len(self.entries) > self.maxsize or self.bytes > self.max_bytes:
                _, (_, removed) = self.entries.popitem(last=False)
                self.bytes -= removed
        return result

    def extra_stats(self):
        return dict(estimated_entry_bytes=self.bytes, max_entry_bytes=self.max_bytes)


class NearestCoordinates:
    """SciPy 1.17.1's float64/order0/constant path, with owned output."""
    def __init__(self, original):
        self.original = original
        self.fast_calls = 0

    def __call__(self, values, coordinates, *args, **kwargs):
        if (args or set(kwargs) != {'order', 'mode', 'cval'}
                or type(kwargs['order']) is not int or kwargs['order'] != 0
                or kwargs['mode'] != 'constant' or kwargs['cval'] != .5
                or type(values) is not np.ndarray or values.dtype != np.dtype('float64')
                or values.ndim != 2 or min(values.shape) == 0
                or type(coordinates) is not np.ndarray or coordinates.dtype != np.dtype('float64')
                or coordinates.ndim != 2 or coordinates.shape[0] != 2):
            return self.original(values, coordinates, *args, **kwargs)
        self.fast_calls += 1
        x, y = coordinates
        inside = (x >= 0) & (x <= values.shape[0]-1) & (y >= 0) & (y <= values.shape[1]-1)
        result = np.full(x.shape, .5)
        ix = np.floor(x[inside]+.5).astype(np.intp)
        iy = np.floor(y[inside]+.5).astype(np.intp)
        # NI_GeometricTransform starts t=+0 and adds its sole order0 value.
        # Preserve signed-zero/NaN behavior rather than simply copying a cell.
        with np.errstate(invalid='ignore'):
            result[inside] = np.add(0., values[ix, iy])
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
    def __init__(self):
        self.fast_calls = 0

    def __getattr__(self, name):
        return getattr(np, name)

    def clip(self, value, lower, upper, *args, **kwargs):
        if (not args and not kwargs and type(value) in (int, np.int64)
                and type(lower) is int and type(upper) is int
                and all(-(1 << 63) <= x < (1 << 63) for x in (value, lower, upper))):
            self.fast_calls += 1
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
        maps = value.maps if hasattr(value, 'maps') else (value,) if hasattr(value, 'cells') else ()
        for grid in maps:
            cells = grid.cells
            # deepcopy already shares Python immutable keys/values. Copying
            # just this dict retains independent writes without walking every
            # coordinate tuple. Unknown/mutable cell schemas use deepcopy.
            if type(cells) is dict and all(type(k) is tuple and len(k) == 2
                    and type(k[0]) in (int, np.int64) and type(k[1]) in (int, np.int64)
                    and type(v) in (float, int, np.float64, np.int64) for k, v in cells.items()):
                if id(cells) not in memo:
                    memo[id(cells)] = dict(cells)
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
        self.scan_mode, self.local_radius = scan_options()
        self.record.update(scan_speedups=self.scan_mode,
            local_submap_requested_m=self.local_radius, local_submap_active_m=0.)
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
        from harness.vision_loc_protocol import load_vis3
        vl, _ = load_vis3()
        clip = IntegerClipNumpy()
        # The detector factory owns the nested scalar step's globals. Binding
        # install() alone does not affect it. Cover the frozen detector too,
        # when the older geometry cache declines the current observation API.
        detector_sha = hashlib.sha256(inspect.getsource(vl.mp.detect_boundaries).encode()).hexdigest()
        expected_detector = ('e63238453c1a632548a775bcf14a532a25992ae3004b925783aeb1199b2ae725'
            if detector_sha == 'e63238453c1a632548a775bcf14a532a25992ae3004b925783aeb1199b2ae725'
            else '59459639ec2b7576ef97ff06e0724b2056e6174ef135b8240cd7bb0c85aca4e6')
        if self.guard(vl.mp.detect_boundaries, expected_detector, 'markerless_integer_clip'):
            self.replace(vl.mp, 'detect_boundaries', bind(vl.mp.detect_boundaries, np=clip))
            self.record['applied'].append('markerless_integer_clip')
        if self.guard(opencv.make_detect_boundaries,
                '632ba220968ace4e2b8ba5973ee7d6048ef64e7ef8e1da402f9c68c945813e87', 'opencv_factory'):
            self.replace(opencv, 'make_detect_boundaries', bind(opencv.make_detect_boundaries, np=clip))
            self.record['applied'].append('opencv_integer_clip')
        self.integer_clip = clip
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
            if self.guard(field, '4afaf15e52fcb1894461853bbfac03d6cc103e171cd4e3d2970ea869c4f14e81', 'grid_field_class') and self.guard(field.__init__, 'f3c4b4f4fdd15cc68bcf2b3c953c2e0508e013588b2b8012efe8172f9607db52', 'grid_field') and self.guard(
                    field.query, '6d5691dda6f25897a3879849254bb7715fab8ab9269630662167261540a2db87', 'field_query'):
                cached = (IncrementalGridFieldMemo(field) if self.scan_mode == 'exact-v2'
                          else GridFieldMemo(field, maxsize=32))
                self.replace(field, '__init__', cached.bound())
                self.caches['grid_field'] = cached
                self.record['applied'].append('grid_field')
            graph = self.optional('harness.self_pose_graph')
            if graph and self.scan_mode == 'exact-v2':
                if self.guard(graph.ProbabilityField.__init__,
                        '8148fa2572196519e65aabd22a3d900665512d6d311fb0f3b36485aa12ee1e12', 'probability_incremental'):
                    cached = ProbabilityFieldMemo(graph.ProbabilityField)
                    self.replace(graph.ProbabilityField, '__init__', cached.bound())
                    self.caches['probability_field'] = cached
                    self.record['applied'].append('incremental_probability_field')
                prepared = self.optional('harness.self_graph_cache')
                if prepared and self.guard(prepared.Prepared,
                        'f4c9637df39507cfddaccf4a535cc121cd84a90df7df36380c017fbfd1dc7bfc', 'prepared_fields') and self.guard(
                        graph.match_loop, 'b8a05f32154916dbb19d719d6c79e42e829cb941e4a0c793c740521429b4c1a9', 'graph_loop_memo'):
                    cached = GraphLoopMemo(graph.match_loop)
                    self.aliases(graph.match_loop, cached)
                    self.caches['graph_loop'] = cached
                    self.record['applied'].append('exact_graph_loop_results')
            if graph and self.local_radius and self.guard(graph.apply_pose_graph,
                    'de728340f100118db9705601b2c3a09bff95c9d65e82e194ba42a11246c580d6', 'local_submap'):
                original, radius = graph.apply_pose_graph, self.local_radius
                @wraps(original)
                def local_graph(rows, poses, *, robot_id, pose_graph='off', options=None, cache=None,
                                _original=original, _radius=radius):
                    selected = options
                    if pose_graph != 'off':
                        selected = {**(options or {}), 'candidate_distance_m':min(
                            _radius, (options or {}).get('candidate_distance_m', 6.))}
                    return _original(rows, poses, robot_id=robot_id, pose_graph=pose_graph,
                                    options=selected, cache=cache)
                self.aliases(original, local_graph)
                self.record['applied'].append('local_submap_candidate_radius')
                self.record['local_submap_active_m'] = radius
            if graph and self.guard(graph.ProbabilityField.query,
                    'c53abd7fbb32e9b0d65980743e4b3503635c9c08e486ef007d42d2b3632a4526', 'probability_query'):
                import scipy
                self.record['nearest_lookup_scipy'] = scipy.__version__
                if scipy.__version__ == '1.17.1':
                    self.nearest_lookup = NearestCoordinates(graph.map_coordinates)
                    self.replace(graph.ProbabilityField, 'query', bind(graph.ProbabilityField.query,
                        map_coordinates=self.nearest_lookup))
                    self.record['applied'].append('nearest_probability_lookup')
                else:
                    self.record['fallback'].append('nearest_probability_lookup:scipy_version')
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
        return {**self.record, 'integer_clip_fast_calls': getattr(getattr(self, 'integer_clip', None), 'fast_calls', 0),
            'nearest_lookup_fast_calls': getattr(getattr(self, 'nearest_lookup', None), 'fast_calls', 0),
            'caches': {name: dict(hits=c.hits, misses=c.misses,
            entries=len(c.entries), max_entries=c.maxsize,
            **(c.extra_stats() if hasattr(c, 'extra_stats') else {})) for name, c in self.caches.items()}}

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
