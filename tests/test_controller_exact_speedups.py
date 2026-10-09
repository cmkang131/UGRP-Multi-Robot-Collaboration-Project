import numpy as np
import pytest
from harness.controller_exact_speedups import ArrayRevision, PosteriorMemo, PureMemo, MethodSummaryMemo, IntegerClipNumpy, mode


def test_incremental_distance_field_matches_original_bytes_add_remove_and_owned_result():
    from scipy.ndimage import distance_transform_edt
    from harness.controller_exact_speedups import IncrementalGridFieldMemo
    class Field:
        def __init__(self, points, resolution=.05):
            self.resolution = resolution
            self.origin = np.floor((points.min(0)-1.)/resolution)*resolution
            size = np.ceil((points.max(0)+1.-self.origin)/resolution).astype(int)+1
            grid = np.ones(tuple(size), bool)
            ij = np.rint((points-self.origin)/resolution).astype(int)
            grid[ij[:,0],ij[:,1]] = False
            self.distance = distance_transform_edt(grid)*resolution
    original = Field.__init__
    cache = IncrementalGridFieldMemo(Field, maxsize=2)
    rng = np.random.default_rng(312)
    points = np.vstack([[[0.,0.],[4.,4.]], rng.integers(1,79,(35,2))*.05])
    for i in range(60):
        baseline = Field(points)
        actual = object.__new__(Field)
        cache(actual, points)
        assert actual.origin.tobytes() == baseline.origin.tobytes()
        assert actual.distance.tobytes() == baseline.distance.tobytes()
        actual.distance[:] = -1
        # Alternate additions/deletions, including deletion of a nearest witness.
        if i % 2:
            points = np.delete(points, 2+rng.integers(len(points)-2), axis=0)
        else:
            points = np.vstack([points, rng.integers(1,79,(1,2))*.05])
    assert cache.updates > 0 and cache.changed_cells > 0
    # Expanding geometry rebuilds rather than applying a finite, unsafe halo.
    points = np.vstack([points, [[9.,-7.]]])
    baseline = Field(points); actual = object.__new__(Field); cache(actual, points)
    assert actual.distance.tobytes() == baseline.distance.tobytes()
    assert Field.__init__ is original and len(cache.entries) <= 2


def test_incremental_probability_changes_only_cells_and_preserves_bits():
    import math
    from types import SimpleNamespace
    from harness.controller_exact_speedups import ProbabilityFieldMemo
    class Field:
        def __init__(self, grid):
            keys = np.array(list(grid.cells)); self.resolution = grid.resolution_m
            self.lower = keys.min(0)-2; size = keys.max(0)-self.lower+3
            self.values = np.full(tuple(size), .5)
            for k,v in grid.cells.items():
                self.values[tuple(np.array(k)-self.lower)] = 1/(1+math.exp(-v))
    cache = ProbabilityFieldMemo(Field, maxsize=2)
    grid = SimpleNamespace(resolution_m=.05, cells={(i,j):float(i-j)/10 for i in range(10) for j in range(10)})
    for change in (None, (3,4), (6,7), (3,4)):
        if change is not None: grid.cells[change] += .3
        baseline = Field(grid); actual = object.__new__(Field); cache(actual, grid)
        assert baseline.lower.tobytes() == actual.lower.tobytes()
        assert baseline.values.tobytes() == actual.values.tobytes()
        actual.values[:] = 999
    del grid.cells[(5,5)]
    baseline = Field(grid); actual = object.__new__(Field); cache(actual, grid)
    assert baseline.values.tobytes() == actual.values.tobytes()
    assert cache.updates > 0 and cache.changed_cells > 0


def test_loop_result_cache_owner_mutation_lazy_fields_and_output_isolation():
    from types import SimpleNamespace as S
    from harness.controller_exact_speedups import GraphLoopMemo
    calls=[]
    def original(submap,row,initial,options,*,prepared=None):
        calls.append(1)
        if not submap['grid'].cells: return {'reason':'empty'}
        if prepared._probability is None:
            prepared._probability=S(resolution=.05,lower=np.zeros(2),values=np.array([[.6,.8]]))
            prepared.builds += 1
        return {'score':float(prepared._probability.values.sum()),'pose':initial.tolist()}
    class Prepared:
        def __init__(self):
            self._probability=self._distance=None; self.segments=np.zeros((1,2,2))
            self.grid=S(cells={(0,0):1.}); self.builds=0
    p=Prepared(); submap={'grid':p.grid}; row={'segments':[[[0.,0.],[1.,1.]]]}; initial=np.zeros(3)
    cache=GraphLoopMemo(original,maxsize=2)
    expected=cache(submap,row,initial,None,prepared=p)
    cache(submap,row,initial,None,prepared=p)['pose'][0]=999
    assert cache(submap,row,initial,None,prepared=p)==expected and p.builds==1 and len(calls)==1
    p._probability.values[0,0] += .1
    assert cache(submap,row,initial,None,prepared=p)['score'] != expected['score']
    q=Prepared()
    cache({'grid':q.grid},row,initial,None,prepared=q)
    assert q.builds==1 and len(cache.entries)<=2
    p.grid.cells.clear()
    assert cache(submap,row,initial,None,prepared=p)=={'reason':'empty'}
    import gc, weakref
    owner=weakref.ref(p)
    del p
    gc.collect()
    assert owner() is None  # cached pairs must not keep expired submap owners alive


def test_scan_options_are_explicit_and_local_policy_defaults_off(monkeypatch):
    from harness.controller_exact_speedups import scan_options
    monkeypatch.delenv('UGRP_CONTROLLER_SCAN_SPEEDUPS',raising=False)
    monkeypatch.delenv('UGRP_CONTROLLER_LOCAL_SUBMAP_M',raising=False)
    assert scan_options()==('exact-v2',0.)
    monkeypatch.setenv('UGRP_CONTROLLER_LOCAL_SUBMAP_M','nan')
    with pytest.raises(ValueError):scan_options()


def test_snapshot_in_place_noncontiguous_signed_zero_and_nan_payloads():
    bits = np.array([0, 0x7ff8000000000001], dtype=np.uint64)
    a = bits.view(np.float64)
    revision = ArrayRevision()
    assert revision(a) == revision(a.copy()) == 1
    bits[0] = 1 << 63
    assert revision(a) == 2
    bits[1] += np.uint64(1)
    assert revision(a) == 3
    b = np.arange(12).reshape(3, 4)[:, ::2]
    assert revision(b) == revision(b.copy()) == 4
    b[0, 0] = 99
    assert revision(b) == 5


def test_posterior_interleaving_ownership_mutation_and_eviction():
    # Summaries are mutable; callers must not be able to poison future outputs.
    calls = []
    def summarize(p, w):
        calls.append(1)
        return {'mean': (w @ p).tolist()}
    cache = PosteriorMemo(summarize, maxsize=2)
    a, b, c = (np.array([[v, 1.], [2., v]]) for v in (1., 2., 3.))
    w = np.array([.5, .5])
    expected = summarize(a, w)
    cache(a, w)['mean'][0] = 999
    cache(b, w)
    assert cache(a, w) == expected
    a[0, 0] = -1
    assert cache(a, w) == summarize(a, w)
    cache(c, w)
    before = cache.misses
    cache(b, w)
    assert cache.misses == before + 1
    assert len(cache.entries) == 2


def test_geometry_cache_preserves_input_bits_and_mutable_outputs():
    memo = PureMemo(lambda x: x.copy(), maxsize=2)
    a = np.array([-0., np.nan])
    memo(a)[0] = 3.
    assert memo(a).tobytes() == a.tobytes()
    a[0] = 0.
    assert memo(a).tobytes() == a.tobytes()
    assert memo.misses == 2


def test_option_validation(monkeypatch):
    monkeypatch.delenv('UGRP_CONTROLLER_EXACT_SPEEDUPS', raising=False)
    assert mode() == 'exact-v1'
    monkeypatch.setenv('UGRP_CONTROLLER_EXACT_SPEEDUPS', 'off')
    assert mode() == 'off'
    with pytest.raises(ValueError):
        mode('typo')


def test_grid_constructor_retains_class_subclasses_and_owned_state():
    from harness.controller_exact_speedups import GridFieldMemo, Installation
    class Field:
        def __init__(self, points, resolution=.05):
            self.resolution = resolution
            self.origin = points.min(0)
            self.distance = (points-self.origin)**2
    original = Field.__init__
    cached = GridFieldMemo(Field, maxsize=2)
    installation = Installation('off')
    installation.replace(Field, '__init__', cached.bound())
    points = np.array([[0., -0.], [1., 2.]])
    try:
        a = Field(points)
        a.distance[:] = 999
        b = Field(points)
        reference = object.__new__(Field)
        original(reference, points)
        assert isinstance(b, Field) and type(b) is Field
        assert b.origin.tobytes() == reference.origin.tobytes()
        assert b.distance.tobytes() == reference.distance.tobytes()
        class Child(Field):
            def __init__(self, points):
                super().__init__(points)
                self.marker = 'subclass'
        assert Child(points).marker == 'subclass'
        assert cached.hits == cached.misses == 1
        points[1, 0] = 3.
        c = Field(points)
        assert c.distance[1, 0] == 9. and b.distance[1, 0] == 1.
        with pytest.raises(AttributeError):
            b.__init__(None, resolution=.125)
        assert b.resolution == .125
    finally:
        installation.close()
    assert Field.__init__ is original


def test_nearest_query_matches_scipy_bytes_edges_nonfinite_and_fallbacks():
    from scipy.ndimage import map_coordinates
    from harness.controller_exact_speedups import NearestCoordinates
    query = NearestCoordinates(map_coordinates)
    bits = np.array([0, 1 << 63, 0x7ff8000000000001, 0x7ff0000000000001], np.uint64)
    values = np.arange(12, dtype=float).reshape(3, 4)
    values[0, :] = bits.view(np.float64)
    edges = np.array([-np.inf, -.5, np.nextafter(0., -np.inf), -0., 0.,
                      np.nextafter(.5, 0.), .5, np.nextafter(.5, 1.), 1., 2., 3., np.inf, np.nan])
    coordinates = np.stack(np.meshgrid(edges, edges), axis=0).reshape(2, -1)
    rng = np.random.default_rng(17)
    for v, c in [(values, coordinates), (values.T, coordinates),
                 (np.ones((1, 1)), coordinates), (values, rng.uniform(-1, 4, (2, 3000))),
                 (values, np.empty((2, 0)))]:
        with np.errstate(all='raise'):
            actual = query(v, c, order=0, mode='constant', cval=.5)
        expected = map_coordinates(v, c, order=0, mode='constant', cval=.5)
        assert actual.dtype == expected.dtype and actual.tobytes() == expected.tobytes()
    before = query.fast_calls
    for order, v in [(1, np.ones((3, 4))), (0, np.ones((3, 4), np.float32))]:
        actual = query(v, coordinates, order=order, mode='constant', cval=.5)
        expected = map_coordinates(v, coordinates, order=order, mode='constant', cval=.5)
        assert actual.dtype == expected.dtype and actual.tobytes() == expected.tobytes()
    assert query.fast_calls == before == 5


def test_owncam_moments_keep_live_metadata_and_inplace_updates():
    from types import SimpleNamespace
    from harness.owncam_localizer import OwnCamLocalizer
    original = OwnCamLocalizer.estimate
    rng = np.random.default_rng(10)
    owner = SimpleNamespace(initialized=True,px=rng.normal(size=(100,3)),
                            logw=rng.normal(size=100),t=1.3,last_tag_t=None)
    cached = MethodSummaryMemo(original)
    for mutate in (lambda:None,lambda:setattr(owner,'t',2.4),
                   lambda:setattr(owner,'last_tag_t',1.5),lambda:owner.px.__setitem__((0,0),4.),
                   lambda:owner.logw.__setitem__(0,2.)):
        mutate()
        assert cached(owner) == original(owner)
    cached(owner)['cov'][0][0]=999
    assert cached(owner)==original(owner)
    owner.initialized=False
    assert cached(owner)==original(owner)
    assert cached.hits>0


def test_integer_clip_matches_numpy_bits_and_preserves_float_fallback():
    proxy = IntegerClipNumpy()
    for kind in (int,np.int64):
        for v in (-999,0,1,478,999):
            for low,high in ((1,478),(478,1),(-10,10)):
                a,b=proxy.clip(kind(v),low,high),np.clip(kind(v),low,high)
                assert type(a) is type(b) and a.tobytes()==b.tobytes()
    for value in (-0.,0.,np.nan,np.inf,np.array([-0.,np.nan,1.])):
        a,b=proxy.clip(value,-.5,.5),np.clip(value,-.5,.5)
        assert a.tobytes()==b.tobytes()


def test_s3_extract_does_not_alias_signed_zero_offsets(monkeypatch):
    import sys
    from types import ModuleType
    from harness.controller_exact_speedups import Installation, install
    s3 = ModuleType('harness.zone_s3_exact_cache')
    def attach(function, audit):
        return memo_extract(function, audit)
    monkeypatch.setitem(attach.__globals__, 'memo_extract', lambda *args: None)
    monkeypatch.setitem(attach.__globals__, 'memo_summary', lambda *args: None)
    s3.attach = attach
    monkeypatch.setitem(sys.modules, s3.__name__, s3)
    monkeypatch.setattr(Installation, 'guard', lambda *args: True)
    monkeypatch.setattr(Installation, 'optional', lambda self, name: s3 if name == s3.__name__ else None)
    installed = install('exact-v1')
    try:
        def extract(p, w, labels, old):
            offset = old['pan_yaw_offset']
            return {'pan_yaw_offset': offset, 'sign': float(np.copysign(1., offset))}
        audit = {'hits': 0, 'misses': 0}
        cached = s3.attach(extract, audit)
        a = np.zeros(1)
        assert cached(a, a, a, {'pan_yaw_offset': 0.})['sign'] == 1.
        assert cached(a, a, a, {'pan_yaw_offset': -0.})['sign'] == -1.
        assert audit == {'hits': 0, 'misses': 2}
    finally:
        installed.close()


def test_forecast_clone_keeps_append_and_particle_mutations_isolated():
    from types import SimpleNamespace
    from harness.controller_exact_speedups import ForecastCopy
    row = dict(frame_id=1, pose=[1., 2., 3.])
    history = [row]
    grid = SimpleNamespace(maps=[SimpleNamespace(cells={(0, 0): 1.})], histories=[history],
                           poses=np.ones((1, 3)), decisions=[{'reason': 'accepted'}], ledger=history)
    cloned = ForecastCopy.deepcopy(grid)
    cloned.histories[0].append(dict(frame_id=2))
    cloned.maps[0].cells[(0, 0)] = -1.
    cloned.poses[:] = 0.
    assert grid.histories == [[row]]
    assert grid.ledger is grid.histories[0] and len(grid.ledger) == 1
    assert cloned.ledger is cloned.histories[0] and len(cloned.ledger) == 2
    assert grid.maps[0].cells == {(0, 0): 1.}
    assert np.array_equal(grid.poses, np.ones((1, 3)))


def test_forecast_cells_preserve_bits_aliases_and_mutable_schema_fallback():
    import copy
    from types import SimpleNamespace
    from harness.controller_exact_speedups import ForecastCopy
    bits=np.array([0x8000000000000000,0x7ff8000000000001],np.uint64).view(np.float64)
    cells={(np.int64(1),np.int64(2)):bits[0],(3,4):bits[1]}
    value=SimpleNamespace(maps=[SimpleNamespace(cells=cells),SimpleNamespace(cells=cells)],histories=[])
    actual,reference=ForecastCopy.deepcopy(value),copy.deepcopy(value)
    assert actual.maps[0].cells is actual.maps[1].cells
    assert actual.maps[0].cells is not cells
    for k,v in reference.maps[0].cells.items():
        assert type(actual.maps[0].cells[k]) is type(v)
        assert actual.maps[0].cells[k].tobytes()==v.tobytes()
    actual.maps[0].cells[(5,6)]=7.
    assert (5,6) not in cells
    mutable=SimpleNamespace(cells={(0,0):[1.]})
    clone=ForecastCopy.deepcopy(mutable)
    clone.cells[(0,0)].append(2.)
    assert mutable.cells[(0,0)]==[1.]


def test_common_install_off_and_restore(monkeypatch):
    from harness.controller_exact_speedups import install
    from harness import zone_solo_cyan_augmented_start as start
    previous = start.belief_report
    off = install('off')
    assert start.belief_report is previous
    off.close()
    on = install('exact-v1')
    try:
        p = np.array([[1., 2., 0.], [2., 3., .1]])
        w = np.array([.5, .5])
        actual = start.belief_report(p, w)
        expected = previous(p, w)
        for a, b in zip(actual[:2], expected[:2]):
            assert a.tobytes() == b.tobytes()
        assert actual[2] == expected[2]
        assert on.snapshot()['applied'] == ['owncam_moments','markerless_integer_clip','opencv_integer_clip','posterior_summary']
        from harness.vision_loc_protocol import load_vis3
        from harness import zone_pair_highpose_opencv_exact as opencv
        vl, _ = load_vis3()
        # Regression: install()'s private np does not reach the detector's
        # nested step. Test both the frozen and subsequent cached detector.
        cached_detector = opencv.make_detect_boundaries(vl.mp, opencv.GeometryCache())
        for detector in (vl.mp.detect_boundaries, cached_detector):
            assert detector.__globals__['np'] is on.integer_clip
            assert detector.__globals__['np'].clip(np.int64(500), 1, 478) == 478
        assert on.snapshot()['integer_clip_fast_calls'] == 2
    finally:
        on.close()
    assert start.belief_report is previous
