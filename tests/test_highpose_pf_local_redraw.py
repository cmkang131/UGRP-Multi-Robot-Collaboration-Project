"""R1 stays local next to walls (independent review #363 P1-2). PF only: no simulator, renderer, model or ground truth.

The frozen ``vision_pf._random_poses`` redraws a candidate that falls in a wall with ``_uniform_free()`` (whole map). The v98
provider binds ``harness/zone_pair_highpose_pf_local_redraw.py`` to its PF instance instead. These tests use the registered
calibration C, the registered map ``zone_wide_door_geometry_v3`` and seed 911 (the reviewer's synthetic own-belief case).
"""
from types import SimpleNamespace

import numpy as np
import pytest

from harness import vision_loc_protocol as vp
from harness import vision_pose_source_highpose as hp
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_pf_local_redraw as lr
from tests.test_zone_final_pair_v3 import MAPS

SHA = 'aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4'
MAP = 'zone_wide_door_geometry_v3'
BELIEFS = [(2.2, .05, 0.), (1., 1.1, 0.)]        # map-valid own beliefs whose local candidates hit the door frame / wall
BOX = lr.CONFIG['bound_sigma']*np.asarray([.1, .1, .2])      # literal registered scales: a PF_RECOVERY mutation must not move the bound


def _build(seed=911):
    reg = c.registry()['dev_pilot']['admitted_source'][SHA]
    return hp.HighPoseSource(c.resolve(MAP)[0], c.ROOT/reg['path'], SHA, seed=seed)


@pytest.fixture
def source():
    src = _build()
    yield src
    src.close()


def _belief(pf, pose_xyyaw, seed=911):
    mean = np.asarray(pose_xyyaw, float)
    assert pf._map_logprior(mean.reshape(1, 3))[0] == 0.        # synthetic own belief: map-valid, no simulator or truth source
    pf.px, pf.logw = np.tile(mean, (pf.n, 1)), np.zeros(pf.n)
    pf.rng = np.random.default_rng(seed)
    return mean


def _spy(pf, monkeypatch):
    calls, original = [], pf._uniform_free
    monkeypatch.setattr(pf, '_uniform_free', lambda k: (calls.append(int(k)), original(k))[1])
    return calls


def _distance(points, mean):
    return np.linalg.norm(np.asarray(points)[:, :2] - mean[:2], axis=1)


@pytest.mark.parametrize('belief', BELIEFS)
def test_random_poses_near_walls_never_draw_globally(source, monkeypatch, belief):
    pf = source.loc._pf
    mean = _belief(pf, belief)
    frozen_calls = _spy(pf, monkeypatch)
    frozen = type(pf)._random_poses(pf, pf.n)                         # control: the frozen method reproduces the reviewer's finding
    assert sum(frozen_calls) > 0 and (_distance(frozen, mean) > 1.).sum() > 0
    mean = _belief(pf, belief)
    calls = _spy(pf, monkeypatch)
    points = pf._random_poses(pf.n)
    assert points.shape == (pf.n, 3) and calls == []                  # zero global draws (not even a size-0 call)
    last = pf.local_redraw['last']
    assert last['redrawn'].sum() > 0 and not last['kept_existing'].any()   # wall candidates did occur and were redrawn locally
    assert np.all(pf._map_logprior(points) == 0.)                     # none in a wall
    assert np.all(np.abs(points - mean) <= BOX + 1e-12)               # every pose (redrawn or not) inside the stated box
    redrawn = points[last['redrawn']]
    assert len(redrawn) == last['redrawn'].sum() and np.all(np.abs(redrawn - mean) <= BOX + 1e-12)
    assert (_distance(points, mean) > 1.).sum() == 0 and _distance(points, mean).max() < np.hypot(BOX[0], BOX[1]) + 1e-9
    assert pf.stats['local_redraw_redrawn'] == int(last['redrawn'].sum()) and pf.stats['local_redraw_exhausted'] == 0


def test_installed_resampler_injects_only_local_poses(source, monkeypatch):
    """The reviewer's second check: the resampler the provider installs, with a synthetic 0.1 recovery request."""
    source.init_prior((2.2, .05, 0.), (.001, .001, .001), source='synthetic own belief for sampler audit')
    pf = source.loc._pf
    mean = _belief(pf, (2.2, .05, 0.))
    calls = _spy(pf, monkeypatch)
    pf._inject = .1
    pf._normalize_and_resample()
    injected = pf.diag['injected']
    assert injected > 0 and pf.stats['injections'] == 1 and pf.stats['local_redraw_calls'] == 1
    assert calls == []
    assert pf.px.shape == (pf.n, 3) and pf.scale.shape == (pf.n, 3) and pf.stuck.shape == (pf.n,)
    tail = pf.px[pf.n - injected:]                                    # injected poses come last
    assert np.all(pf._map_logprior(tail) == 0.) and np.all(np.abs(tail - mean) <= BOX + 1e-12)
    assert (_distance(pf.px, mean) > 1.).sum() == 0                   # reviewer: 5 particles beyond 1 m (max 3.08 m) with the frozen draw
    assert pf.stats['local_redraw_redrawn'] > 0                       # the door-side candidates were redrawn, not replaced globally


def _scan(pf, servo, shift=0.):
    """A frame whose bottom-edge rows equal particle 0's prediction, optionally shifted by ``shift`` pixels."""
    vl, _ = vp.load_vis3()
    vb, _ = pf.expected(pf.px[:1], servo)
    rows = np.asarray(vb[0], float) + shift
    n = rows.size
    kind = np.where(np.isfinite(rows), vl.EDGE, vl.NONE)
    return vl.ColumnObs(np.asarray(pf.columns), kind, rows, rows, np.full(n, vl.NONE), np.full(n, np.nan), np.full(n, np.nan))


def test_r1_is_active_through_the_real_scan_trigger(source, monkeypatch):
    """R1 on: a well-fitting view then a badly fitting new view arms the augmented-MCL injection, which is drawn locally.

    Mutation checks (run by hand, see the experiment README): PF_RECOVERY=None and max_fraction~0 must both fail this test.
    """
    source.init_prior((2.2, .05, 0.), (.1, .1, .1), source='synthetic own belief near the door')
    pf = source.loc._pf
    rec = pf.robust['recovery']
    assert rec is not None and rec['uniform_share'] == 0. and rec['max_fraction'] == 1. and list(rec['local_std']) == [.1, .1, .2]
    servo = {1: 2000, **pose.grasp_postures()[1][-1]}
    pf.apply_scan(1., _scan(pf, servo), servo)
    assert pf._inject == 0. and pf.diag['w_diff'] == 0.               # first view: running averages are seeded, no injection
    pf.command({'t': 1.01, 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .05})   # own move: a new view
    pf.apply_scan(1.05, _scan(pf, servo, shift=40.), servo)
    assert pf.diag['w_diff'] > 0. and pf._inject == pytest.approx(pf.diag['w_diff'], abs=1e-5)     # diag is rounded to 5 digits
    calls = _spy(pf, monkeypatch)
    pf._normalize_and_resample()
    injected = pf.diag['injected']
    assert injected > 0 and pf.stats['injections'] == 1 and pf.stats['injected_particles'] == injected
    assert calls == [] and pf.stats['local_redraw_calls'] == 1
    last = pf.local_redraw['last']
    tail, mean, box = pf.px[pf.n - injected:], np.asarray(last['mean']), lr.CONFIG['bound_sigma']*np.asarray(last['std'])
    assert last['k'] == injected and np.all(pf._map_logprior(tail) == 0.) and np.all(np.abs(tail - mean) <= box + 1e-12)


def test_exhausted_retries_keep_existing_particles(source, monkeypatch):
    """The belief mean sits in a blocked region: every nearby candidate fails, so each slot keeps an existing particle."""
    pf = source.loc._pf
    mean = np.array([2.2, .05, 0.])
    left, right = mean - [1.2, 0., 0.], mean + [1.2, 0., 0.]
    half = pf.n//2
    pf.px = np.concatenate([np.tile(left, (half, 1)), np.tile(right, (pf.n - half, 1))])
    pf.logw, pf.rng = np.zeros(pf.n), np.random.default_rng(911)
    real = pf._map_logprior
    assert np.all(real(pf.px) == 0.)                                  # both clusters are valid, free poses
    monkeypatch.setattr(pf, '_map_logprior', lambda px: np.where(np.linalg.norm(px[:, :2] - mean[:2], axis=1) < 1., -5., real(px)))
    calls = _spy(pf, monkeypatch)
    points = pf._random_poses(50)
    last = pf.local_redraw['last']
    assert points.shape == (50, 3) and calls == []
    assert last['kept_existing'].all() and not last['redrawn'].any() and last['rounds_used'] == lr.CONFIG['max_redraw_rounds']
    assert np.all(np.minimum(np.linalg.norm(points - left, axis=1), np.linalg.norm(points - right, axis=1)) == 0.)   # existing poses only
    assert pf.stats['local_redraw_exhausted'] == 50 and pf.stats['local_redraw_redrawn'] == 0


def test_without_wall_candidates_the_draw_is_bit_identical_to_the_frozen_method(source):
    pf = source.loc._pf
    _belief(pf, (1., 0., 0.), seed=5)
    ours = pf._random_poses(pf.n)
    assert pf.local_redraw['last']['redrawn'].sum() == 0 and not pf.local_redraw['last']['kept_existing'].any()
    state = pf.rng.bit_generator.state
    _belief(pf, (1., 0., 0.), seed=5)
    frozen = type(pf)._random_poses(pf, pf.n)
    np.testing.assert_array_equal(ours, frozen)
    assert pf.rng.bit_generator.state == state                        # same generator consumption: nothing else changed


def test_provider_installs_and_records_the_local_redraw(source):
    pf = source.loc._pf
    assert source.runtime_contract['pf_local_redraw'] == lr.record(lr.CONFIG)
    assert source.runtime_contract['pf_local_redraw']['uniform_free_calls'] == 0
    assert '_random_poses' in vars(pf) and vars(pf)['_random_poses'] is not type(pf)._random_poses    # instance override only
    assert pf.robust['recovery']['uniform_share'] == 0.
    vp.check_frozen()                                                 # the frozen PF files are byte-identical to their registered hashes
    with pytest.raises(ValueError, match='already installed'):
        lr.install(pf)
    assert lr.MODULE in c.bundle(MAPS[0], 'carry')['source_sha256']  # pulled into the bundle's source closure by the provider import


def test_install_requires_local_only_recovery_and_is_a_no_op_when_r1_is_off(monkeypatch):
    off = SimpleNamespace(robust={'recovery': None}, stats={})
    assert lr.install(off) is None and off.local_redraw is None and not hasattr(off, '_random_poses')
    for share in (.3, 1.):
        with pytest.raises(ValueError, match='uniform_share'):
            lr.install(SimpleNamespace(robust={'recovery': {'uniform_share': share}}, stats={}))
    with pytest.raises(ValueError, match='uniform_share'):             # the frozen default of a missing key is 1.0 (global)
        lr.install(SimpleNamespace(robust={'recovery': {}}, stats={}))
    monkeypatch.setattr(hp, 'PF_RECOVERY', {**hp.PF_RECOVERY, 'uniform_share': .3})
    with pytest.raises(ValueError, match='uniform_share'):
        _build()


@pytest.mark.parametrize('bad', [{'max_redraw_rounds': 0}, {'max_redraw_rounds': True}, {'max_redraw_rounds': 2.5},
                                 {'bound_sigma': .5}, {'bound_sigma': float('nan')}, {'bound_sigma': 11.}, {'schema': 'other'},
                                 {'unknown': 1}])
def test_validate_rejects_bad_configs(bad):
    assert lr.validate(None) == lr.DEFAULT
    with pytest.raises(ValueError):
        lr.validate(bad)
