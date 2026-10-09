import numpy as np
import pytest
from harness.controller_exact_speedups import ArrayRevision, PosteriorMemo, PureMemo, MethodSummaryMemo, IntegerClipNumpy, mode


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
        assert on.snapshot()['applied'] == ['owncam_moments','opencv_integer_clip','posterior_summary']
    finally:
        on.close()
    assert start.belief_report is previous
