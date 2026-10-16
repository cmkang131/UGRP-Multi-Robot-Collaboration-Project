"""Bit identity of the shared-trace expected_rows rewrite on the registered map and calibration (no simulator)."""
import numpy as np
import pytest

from harness import vision_loc_protocol as vp
from harness import vision_pose_source_highpose as hp
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_pf_geometry_shared as g

SHA = 'aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4'
MAP = 'zone_wide_door_geometry_v3'
# candidate own-camera postures (servo id -> pulse): the most frequent ones of a recorded v98 align_to_carry
# run (frames.jsonl actuator_state) plus look pans; only those with a measured camera model are used.
_ARMS = [{1: 1500, 3: 896, 4: 2035, 5: 1894}, {1: 2000, 3: 770, 4: 1982, 5: 1876}, {1: 2000, 3: 508, 4: 2432, 5: 1320},
         {1: 1500, 3: 891, 4: 2036, 5: 2054}, {1: 2000, 3: 1269, 4: 2052, 5: 2494}, {1: 2000, 3: 1072, 4: 2400, 5: 1482}]
POSTURES = [{**a, 6: pan} for a in _ARMS for pan in (1500, 1100, 1900)]


@pytest.fixture(scope='module')
def pf():
    reg = c.registry()['dev_pilot']['admitted_source'][SHA]
    src = hp.HighPoseSource(c.resolve(MAP)[0], c.ROOT/reg['path'], SHA, seed=911)
    yield src.loc._pf
    src.close()


def _clouds(pf, rng):
    lo, hi = pf.geometry.rects[:, :2].min(0), pf.geometry.rects[:, :2].max(0)
    for n in (2000, 7, 4, 1):
        for mean in ((.23, .05, 0.), (1.77, .05, np.pi), (2.2, .05, 0.), (1., 1.1, .3)):
            yield np.asarray(mean) + rng.normal(size=(n, 3))*[.15, .15, .17]
        yield np.column_stack([rng.uniform(lo[0], hi[0], n), rng.uniform(lo[1], hi[1], n), rng.uniform(-np.pi, np.pi, n)])


def test_source_hash_is_the_frozen_one():
    vl, _ = vp.load_vis3()
    assert g.source_sha256(vl) == g.SOURCE_SHA256


@pytest.mark.parametrize('loaded', [False, True])
def test_shared_rewrite_is_bit_identical(pf, loaded):
    vl, _ = vp.load_vis3()
    fast = g.make_expected_rows(vl)
    rng = np.random.default_rng(5)
    pf.load.loaded = loaded
    try:
        from harness.vision_pose_source_final import CalibrationError
        n = models = 0
        for posture in POSTURES:
            try:
                cm = pf.column_model_for(posture)
            except CalibrationError:
                continue
            models += 1
            for poses in _clouds(pf, rng):
                a, b = vl.expected_rows(pf.geometry, poses, cm), fast(pf.geometry, poses, cm)
                assert all(x.dtype == y.dtype and x.shape == y.shape and x.tobytes() == y.tobytes() for x, y in zip(a, b))
                n += 1
        assert models >= (1 if loaded else 2) and n == models*20
    finally:
        pf.load.loaded = False


def test_install_swaps_and_restores_and_refuses_changed_source(monkeypatch):
    vl, _ = vp.load_vis3()
    original = vl.expected_rows
    rec = {}
    undo = g.install(rec)
    assert rec['pf_geometry_shared']['installed'] and vl.expected_rows is not original
    undo()
    assert vl.expected_rows is original
    monkeypatch.setattr(g, 'SOURCE_SHA256', '0'*64)
    rec = {}
    undo = g.install(rec)
    assert not rec['pf_geometry_shared']['installed'] and vl.expected_rows is original
    undo()
