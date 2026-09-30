"""Independent offline counterexamples from review cfc562da, now regressions.

Run against an archive with UGRP_REVIEW_347_ROOT=/absolute/archive/root.
On main, where v89 is absent, skip explicitly. No MuJoCo, rendering or workers.
The original review had 2 passes / 6 strict xfails. No physics is exercised.
"""
from __future__ import annotations

import importlib
import math
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ("mujoco", "torch", "torchvision", "sim.multi_masterpi_production"):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("network forbidden"))


@pytest.fixture
def target(monkeypatch):
    root = Path(os.environ.get("UGRP_REVIEW_347_ROOT", Path(__file__).resolve().parents[1]))
    if not (root / "harness/final_environment_measurement_v2.py").is_file():
        pytest.skip("PR #347 source absent; set UGRP_REVIEW_347_ROOT to its archive")
    monkeypatch.syspath_prepend(str(root))
    env = importlib.import_module("harness.final_environment_measurement_v2")
    assert Path(env.__file__).resolve().is_relative_to(root.resolve())
    return env


def exact_response(segments, dt, gain, tau, stop_tau):
    """Independently derived closed form, without VIS4 or PR #347's integrator."""
    velocity = position = 0.0
    positions = [position]
    for duration, command in segments:
        steps = round(duration / dt)
        assert abs(steps * dt - duration) < 1e-9
        constant = tau if command else stop_tau
        decay = math.exp(-dt / constant)
        target_velocity = gain * command
        for _ in range(steps):
            position += target_velocity * dt + (velocity - target_velocity) * constant * (1 - decay)
            velocity = target_velocity + (velocity - target_velocity) * decay
            positions.append(position)
    return np.array(positions)


@pytest.mark.parametrize("axis,index,gain,tau,stop", [
    # #346 a5cc1402 fit_report.json, two_doors, extended_tau_sensitivity_not_selected.
    # Both fit the original data BETTER than the nominal design candidates.
    ("forward", 0, 5.529315179303428, 5.0, 0.05),
    ("left", 1, 21.774200852931983, 30.0, 0.05),
])
def test_unsafe_path_rejected_for_unexcluded_v1_models(target, tmp_path, axis, index, gain, tau, stop):
    from scripts.run_final_environment_measurement_v2 import run_case

    plan = target.protocol()  # Reading the old schedule does not admit a run.
    static = target.parent.resolve(plan["map_id"])[0]
    segments = [(plan["initial_hold_s"], 0.0)] + [
        (s["duration_s"], s["value"] if s["axis"] == axis else 0.0) for s in plan["segments"]
    ]
    displacement = exact_response(segments, plan["eval_pose_period_s"], gain, tau, stop)
    xy = np.tile(plan["spawn_xy_yaw"][:2], (len(displacement), 1))
    xy[:, index] += displacement
    other_axis = "left" if axis == "forward" else "forward"
    other_params = (2.40680, 3., .05) if other_axis == "left" else (1.78459, 1.44, .08)
    other_segments = [(plan["initial_hold_s"], 0.)] + [
        (s["duration_s"], s["value"] if s["axis"] == other_axis else 0.) for s in plan["segments"]
    ]
    xy[:, 1 - index] += exact_response(other_segments, plan["eval_pose_period_s"], *other_params)
    gaps = [target.clearance(static, point, plan["clearance"]["robot_radius_bound_m"]) for point in xy]
    # Preserve the independent counterexample. The fix rejects it; it must not
    # change the recorded commands or claim these models are safe/excluded.
    assert min(gaps) < plan["clearance"]["minimum_m"]
    receipt = target.validate(plan, for_execution=False)['full_path']
    witness = receipt['unexcluded_v1_witnesses'][axis]
    assert witness['continuous_path'] and not witness['satisfies_margin']
    assert witness['minimum_lower_bound_m'] <= min(gaps) + 1e-10
    with pytest.raises(ValueError, match='FULL_PATH_CLEARANCE_REJECTED'):
        target.validate(plan)
    with pytest.raises(ValueError, match='FULL_PATH_CLEARANCE_REJECTED'):
        run_case(target.bundle(), tmp_path / 'forbidden', seed=911,
                 backend_factory=lambda *a, **k: pytest.fail('backend must not be constructed'))
    assert not (tmp_path / 'forbidden').exists()


@pytest.mark.parametrize("bad_field", ["radius", "position"])
def test_every_geometry_must_be_finite_before_admission(target, monkeypatch, tmp_path, bad_field):
    from sim.final_environment_measurement_v2 import PhysicsBackend

    backend = PhysicsBackend.__new__(PhysicsBackend)
    backend.out, backend.plan, backend.streams = tmp_path, target.protocol(), {}
    backend._last_guard_xy = None
    static = target.parent.resolve(target.MAP_ID)[0]
    backend.scene = SimpleNamespace(config={"static_map": static})
    backend.bundle = {"map_sha256": target.digest(static)}
    base = SimpleNamespace(xpos=np.array([3.25, -.85, .032]))
    model = SimpleNamespace(ngeom=2, geom_rbound=np.array([.1, .1]))
    data = SimpleNamespace(time=0.0, body=lambda _: base,
                           geom_xpos=np.array([[3.25, -.85, .032]] * 2))
    if bad_field == "radius":
        model.geom_rbound[1] = np.nan
    else:
        data.geom_xpos[1, 0] = np.nan
    backend.world = SimpleNamespace(model=model, data=data)
    held = []
    backend.ports = {"r1": SimpleNamespace(hold=held.append)}
    monkeypatch.setitem(sys.modules, "mujoco", SimpleNamespace(
        mjtObj=SimpleNamespace(mjOBJ_GEOM=1), mj_id2name=lambda *a: "r1__geom" + str(a[-1])))
    rejected = False
    try:
        backend.guard(check_geometry=True)
    except ValueError:
        rejected = True
    finally:
        for stream in backend.streams.values():
            stream.close()
    assert rejected and held, "invalid geometry was admitted without a hold"
    import json
    abort = json.loads((tmp_path / 'eval_only/clearance_abort.jsonl').read_text())
    assert abort['reason'] == 'INVALID_ROBOT_GEOMETRY' and abort['t'] == 0.


@pytest.mark.parametrize("axis", ["forward", "left"])
def test_independent_integral_and_fisher_rederive_nominal_claim(target, axis):
    from scripts import check_measurement_v2_identifiability as ident

    gain, tau, stop = ident.CANDIDATES[axis]
    conditions = []
    for dt, segments in [(.2, [(1., .03), (3., 0.), (1., -.03), (3., 0.)]),
                         (.05, ident.design_segments())]:
        response = exact_response(segments, dt, gain, tau, stop)
        assert np.allclose(response, gain * ident.response(segments, dt, tau, stop), atol=1e-12, rtol=0)
        epsilon = 1e-5
        derivative = (exact_response(segments, dt, gain, tau * math.exp(epsilon), stop)
                      - exact_response(segments, dt, gain, tau * math.exp(-epsilon), stop)) / (2 * epsilon)
        jacobian = np.column_stack((response, derivative))
        conditions.append(np.linalg.cond(jacobian.T @ jacobian))
    assert conditions[0] > 1e3  # Ill-conditioned, not structurally rank deficient.
    assert conditions[1] < 250


@pytest.mark.parametrize("axis", ["forward", "left"])
def test_v1_fisher_matches_the_two_actual_fit_windows(target, axis):
    from scripts import check_measurement_v2_identifiability as ident

    gain, tau, stop = ident.CANDIDATES[axis]
    segment = [(1., .03), (3., 0.)]
    response = exact_response(segment, .2, gain, tau, stop)
    epsilon = 1e-5
    derivative = (exact_response(segment, .2, gain, tau * math.exp(epsilon), stop)
                  - exact_response(segment, .2, gain, tau * math.exp(-epsilon), stop)) / (2 * epsilon)
    positive = np.column_stack((response, derivative)) / ident.RESIDUAL_FLOOR_M
    independent_windows = np.vstack((positive, -positive))  # 21 + 21, each from x=v=0.
    expected = independent_windows.T @ independent_windows
    # Check the actual published report path, not a specially corrected helper
    # invocation while report() accidentally keeps the old concatenated path.
    actual = ident.report()['v1'][axis]
    assert actual['samples'] == 42 and actual['independent_windows'] == 2
    assert np.allclose(actual["fisher_log_gain_log_tau"], expected, rtol=1e-5, atol=0)
