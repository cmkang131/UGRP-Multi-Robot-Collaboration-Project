"""Seeded property/adversarial equivalence; fake geometry, no renderer."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_final_pair_contract as contract
from harness.zone_final_pair_clearance import require_clearance, sphere_clearances, geometry_envelope
from harness.zone_final_pair_excitation import design, MAP_ID
from sim.final_pair_fast_guard import WallArrays, geometry_envelopes, require_envelope
from sim.final_pair_fast import PhysicsBackend as New
from scripts.verify_final_pair_fast_guard import outcome


def returned(fn):
    try:
        return fn()
    except ValueError as exc:
        return str(exc)


@pytest.mark.parametrize('map_id', [MAP_ID, 'zone_wide_corridor_final_v3', 'zone_wide_door_geometry_v3'])
def test_seeded_clearance_properties_exact(map_id):
    static = contract.resolve(map_id)[0]
    walls, plan = WallArrays(static), design('calibration-unloaded')
    rng = np.random.default_rng(911)
    for _ in range(1000):
        xyz = rng.uniform([-6, -4, -.2], [6, 4, .5], size=(17, 3))
        radii = rng.uniform(.001, .4, 17)
        assert sphere_clearances(static, xyz, radii).tobytes() == walls.sphere_clearances(xyz, radii).tobytes()
        old = returned(lambda: require_clearance(static, xyz[0, :2], plan))
        new = returned(lambda: walls.require_clearance(xyz[0, :2], plan))
        assert old == new
        if isinstance(old, float):
            assert old.hex() == new.hex()


def test_envelope_sum_order_bounded_and_decision_exact_near_threshold():
    rng = np.random.default_rng(92)
    max_ulp = 0
    for _ in range(200):
        xy = rng.uniform(-5, 5, 2)
        xyz = rng.uniform(-1, 1, (80, 3)) + np.r_[xy, 0.]
        radii = rng.uniform(0, .4, len(xyz))
        old = np.array([geometry_envelope(p, r, xy) for p, r in zip(xyz, radii)])
        new = geometry_envelopes(xyz, radii, xy)
        ulp = np.abs(old-new)/np.spacing(old)
        max_ulp = max(max_ulp, float(ulp.max()))
        # Same two squares, but BLAS dot can fuse a multiply/add whereas axis
        # reduction cannot. No gap or recorded value uses these batched norms.
        assert max_ulp <= 2
    for angle in np.linspace(-np.pi, np.pi, 101):
        for delta in (-4, -1, 0, 1, 4):
            radius = .1
            length = .4-radius+delta*np.spacing(.4)
            xyz = np.array([[length*np.cos(angle), length*np.sin(angle), .1]])
            radii, xy = np.array([radius]), np.zeros(2)
            old = geometry_envelope(xyz[0], radius, xy)
            new = returned(lambda: require_envelope(xyz, radii, xy, .4))
            assert (new == 'ROBOT_ENVELOPE_BOUND_EXCEEDED') == (old > .4)


def test_035_boundary_ulp_neighbours_exact():
    static = {'bounds_m': [-10., 10., -10., 10.], 'obstacles': [
        {'kind': 'wall', 'center_m': [0., 0.], 'half_extents_m': [.1, 9.]}]}
    walls, plan = WallArrays(static), design('calibration-unloaded')
    threshold = .35-1e-10
    for i in range(-50, 51):
        # Includes exactly/on either side of the scalar .3+.05-1e-10 check.
        x = .1+.4+threshold+i*np.spacing(1.)
        xy = np.array([x, 0.])
        assert returned(lambda: require_clearance(static, xy, plan)) == returned(lambda: walls.require_clearance(xy, plan))
        p, r = np.array([[x, 0., .2]]), np.array([.4])
        a, b = sphere_clearances(static, p, r), walls.sphere_clearances(p, r)
        assert a.tobytes() == b.tobytes()
        assert bool(a[0] < threshold) == bool(b[0] < threshold)


@pytest.mark.parametrize('fault', ['nan_x', 'nan_z', 'infinite', 'negative_radius', 'zero_radius', 'missing', 'bad_shape'])
def test_invalid_spheres_have_identical_abort_reasons(fault):
    static = contract.resolve(MAP_ID)[0]
    xyz, radii = np.array([[3.25, -.85, .1]]), np.array([.1])
    if fault == 'nan_x': xyz[0, 0] = np.nan
    if fault == 'nan_z': xyz[0, 2] = np.nan
    if fault == 'infinite': radii[0] = np.inf
    if fault == 'negative_radius': radii[0] = -.1
    if fault == 'zero_radius': radii[0] = 0.
    if fault == 'missing': xyz, radii = np.empty((0, 3)), np.empty(0)
    if fault == 'bad_shape': xyz = xyz[:, :2]
    assert returned(lambda: sphere_clearances(static, xyz, radii)) == returned(lambda: WallArrays(static).sphere_clearances(xyz, radii))


def pair(monkeypatch):
    from tests.test_zone_final_pair_review_fixes import fake_guard
    old = fake_guard(monkeypatch)
    new = New.__new__(New)
    new.__dict__ = copy.copy(old.__dict__)
    new._last_guard_xy, new.saved, new.held = {}, [], []
    new._append = lambda p, row: new.saved.append((p, row))
    new.ports = {r: SimpleNamespace(hold=lambda t, r=r: new.held.append(r), tick=lambda t: None)
                 for r in old.ports}
    return old, new


@pytest.mark.parametrize('fault', ['wall', 'nan', 'nan_z', 'missing', 'radius', 'jump', 'zero_radius'])
def test_full_guard_abort_records_holds_and_minimum_equal(monkeypatch, fault):
    old, new = pair(monkeypatch)
    assert outcome(old) == outcome(new)
    if fault == 'wall': old.world.data.geom_xpos[0, 0] = 2.4
    if fault == 'nan': old.world.data.geom_xpos[0, 0] = np.nan
    if fault == 'nan_z': old.world.data.geom_xpos[0, 2] = np.nan
    if fault == 'missing': old.world.model.ngeom = 0
    if fault == 'radius': old.world.model.geom_rbound[0] = .5
    if fault == 'jump': old.world.data.geom_xpos[0, 0] += .02
    if fault == 'zero_radius': old.world.model.geom_rbound[0] = 0.
    a, b = outcome(old), outcome(new)
    assert a['exception'] and a['abort_records']
    assert a == b


def test_displacement_bound_nextafter_neighbours(monkeypatch):
    old, new = pair(monkeypatch)
    rng = np.random.default_rng(13)
    for _ in range(1000):
        angle = rng.uniform(-np.pi, np.pi)
        length = .01+int(rng.integers(-6, 7))*np.spacing(.01)
        now = old.world.data.geom_xpos[[0], :2]
        previous = now-length*np.array([[np.cos(angle), np.sin(angle)]])
        old._last_guard_xy = {'r1': previous.copy()}
        new._last_guard_xy = {'r1': previous.copy()}
        assert outcome(old) == outcome(new)


@pytest.mark.parametrize('changed', ['time', 'qpos', 'qvel', 'geom', 'body', 'rbound', 'ngeom', 'nan', 'signed_zero'])
def test_precheck_cache_invalidates_for_every_observed_state_change(monkeypatch, changed):
    _, obj = pair(monkeypatch)
    m, d = obj.world.model, obj.world.data
    d.qpos, d.qvel, d.xpos = np.zeros(7), np.zeros(6), np.zeros((3, 3))
    snapshot = obj._post_state()
    assert obj._same_post_state(snapshot)
    if changed == 'time': d.time = np.nextafter(d.time, np.inf)
    if changed == 'qpos': d.qpos[0] = np.nextafter(0., np.inf)
    if changed == 'qvel': d.qvel[0] = .01
    if changed == 'geom': d.geom_xpos[0, 0] += .01
    if changed == 'body': d.xpos[0, 0] += .01
    if changed == 'rbound': m.geom_rbound[0] += .01
    if changed == 'ngeom': m.ngeom += 1
    if changed == 'nan': d.qpos[0] = np.nan
    if changed == 'signed_zero': d.qpos[0] = -0.
    assert not obj._same_post_state(snapshot)


def test_advance_skips_only_unchanged_precheck_and_rechecks_new_advance(monkeypatch):
    _, obj = pair(monkeypatch)
    d = obj.world.data
    d.qpos, d.qvel, d.xpos = np.zeros(7), np.zeros(6), np.zeros((3, 3))
    calls = []
    real_guard = obj.collection_guard
    def guard():
        calls.append(d.time)
        real_guard()
    obj.collection_guard = guard
    obj.world._physics_step_for = lambda _: setattr(d, 'time', d.time+obj.dt)
    obj.advance_to(.03)
    assert calls == [0., .01, .02, .03]
    obj.advance_to(.05)
    assert calls == [0., .01, .02, .03, .03, .04, .05]


def test_post_step_trip_cannot_be_hidden_by_cache(monkeypatch):
    _, obj = pair(monkeypatch)
    d = obj.world.data
    d.qpos, d.qvel, d.xpos = np.zeros(7), np.zeros(6), np.zeros((3, 3))
    def step(_):
        d.time += obj.dt
        if d.time >= .02:
            d.geom_xpos[0, 0] = 2.4
    obj.world._physics_step_for = step
    with pytest.raises(ValueError, match='CLEARANCE_ABORT'):
        obj.advance_to(.05)
    assert d.time == .02 and obj.saved
