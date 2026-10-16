import copy
import numpy as np
import pytest
from tests.test_e2e_acquire_standoff import _pan_parent


def _boxes(rng, n=40):
    out = []
    for i in range(n):
        q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        out.append((('gripper', 'arm', 'chassis')[i % 3], rng.uniform(-.3, .5, 3) + [0, 0, .2], q, rng.uniform(.01, .12, 3)))
    return out


def test_shadow_depths_axes_exact_vs_original():
    from harness.e2e_perception_fast import shadow_depths_axes
    from harness.own_map_amcl_vendor.visibility import shadow_depths
    rng = np.random.default_rng(3)
    u, v = np.meshgrid(np.linspace(-.9, .9, 40), np.linspace(-.7, .7, 30))
    rays = np.stack([u, v, np.ones_like(u)], -1)
    rays[0, 0] = [0., 0., 1.]; rays[0, 1] = [1., 0., 0.]   # axis-parallel rays hit the parallel branch
    for origin in (np.array([0., 0., .05]), np.array([.1, .0, .4])):
        boxes = _boxes(rng) + [('arm', origin + [0., 0., .02], np.eye(3), np.array([.05, .05, .05]))]  # origin inside a box
        a, b = shadow_depths(origin, rays, boxes), shadow_depths_axes(origin, rays, boxes)
        for k in a:
            assert np.array_equal(a[k], b[k]) and a[k].shape == b[k].shape
        assert any(np.isfinite(a[k]).any() for k in a)


def test_v316_v317_v318_compose_and_validate(monkeypatch):
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    base = dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_v1')
    assert bundle(*args, **base)['execution_bundle_id'] == 'e2e18-v303'
    for fast, timing, v in (('shadow_axes_v1', 'phase_v1', 316), ('off', 'phase_v1', 317), ('shadow_axes_v1', 'off', 318)):
        b = bundle(*args, **dict(base, perception_fast=fast, controller_timing=timing))
        assert b['execution_bundle_id'] == f'e2e18-v{v}' and b['perception_speed_parent'] == 'e2e18-v303'
        assert b['e2e_options']['perception_fast'] == fast and b['e2e_options']['controller_timing'] == timing
        require_current(b, ROOT)
        bad = copy.deepcopy(b); bad['e2e_options']['perception_fast'] = 'off' if fast != 'off' else 'shadow_axes_v1'
        with pytest.raises(ValueError):
            require_current(bad, ROOT)
    with pytest.raises(ValueError):       # needs the v303 parent
        bundle(*args, **dict(kw, perception_fast='shadow_axes_v1'))
    assert 'perception_fast' not in bundle(*args, **base)['e2e_options']


def test_controller_timing_install_wraps_only_when_on():
    from types import SimpleNamespace as NS
    from harness import e2e_speed_phase as sp
    assert sp.install('off', {}, None, None, None) is None
    calls = []
    goal = NS(receive=lambda **k: calls.append('g') or 1)
    robot = NS(_receive=lambda *a: calls.append('r') or 2, goal=goal, observe_beam=lambda *a: 3)
    transport = NS(step=lambda now: 4); host = NS(step_to=lambda now: 5); backend = NS(capture=lambda: 6)
    g = {'ownmap_record': lambda *a: 7, 'health': lambda *a: 8}
    t = sp.install('phase_v1', {'r1': robot}, transport, host, backend, g)
    t.phase = 'relook'
    assert robot._receive() == 2 and transport.step(0) == 4 and g['health']() == 8
    assert t.stats['relook']['robot._receive']['calls'] == 1 and t.stats['relook']['health']['calls'] == 1
