"""VIS4 opt-in command-only prediction; no observations or evaluation state.

The legacy M1 path remains in its frozen module. Here command expiry is an
integration boundary and first-order velocity is integrated analytically.
Optional delay is causal: wheel commands enter a timestamped FIFO; arm/load
commands keep their issued timestamps. Delay describes the plant, not a shift
of camera timestamps. Parameters are fitted offline, never adapted from GT.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np


def validate_motion(options):
    if options is None:
        return {"exact": False, "delay_s": {"unloaded": 0., "loaded": 0.}}
    if not isinstance(options, Mapping) or set(options) - {"exact", "delay_s"}:
        raise ValueError("motion_v4 needs only exact and delay_s")
    exact = options.get("exact", False)
    if not isinstance(exact, bool):
        raise ValueError("motion_v4.exact must be boolean")
    delays = options.get("delay_s", {})
    if not isinstance(delays, Mapping) or set(delays) - {"unloaded", "loaded"}:
        raise ValueError("delay_s needs unloaded/loaded seconds")
    result = {}
    for state in ("unloaded", "loaded"):
        value = delays.get(state, 0.)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= .5:
            raise ValueError("delay_s must be finite in [0, 0.5]")
        result[state] = float(value)
    if any(result.values()) and not exact:
        raise ValueError("delay requires exact prediction")
    return {"exact": exact, "delay_s": result}


def lag_integral(velocity, target, dt, tau):
    """Return end velocity and displacement, with stable short-interval math."""
    tau = np.maximum(np.asarray(tau, float), 1e-6)
    alpha = -np.expm1(-dt/tau)
    end = velocity + alpha*(target - velocity)
    distance = target*dt + (velocity - target)*tau*alpha
    return end, distance


def predict_exact(pf, t):
    """Integrate one command segment; caller splits delayed-command boundaries."""
    if not math.isfinite(t) or t < pf.t - 1e-9:
        raise ValueError("prediction time must be finite and monotonic")
    while pf.t < t - 1e-9:
        mp = pf._motion_params() if hasattr(pf, "_motion_params") else pf.params[
            "motion_loaded" if pf.load.loaded and "motion_loaded" in pf.params else "motion"]
        dt = min(pf.step_s, t - pf.t)
        active = pf.t < pf.cmd_expires - 1e-9
        if active:
            dt = min(dt, pf.cmd_expires - pf.t)
        u = pf.cmd if active else np.zeros(3)
        target = np.asarray(mp["gain"], float) @ u
        tau = (mp.get("tau_axis_s", mp["tau_s"]) if np.any(u)
               else mp.get("tau_stop_s", mp["tau_s"]))
        pf.vel, distance = lag_integral(pf.vel, target, dt, tau)
        if pf.initialized:
            avg = distance/dt
            std = np.asarray(mp["noise_rel"])*np.abs(avg) + np.asarray(mp["noise_abs"])
            scale = pf.scale if mp.get("use_scale", True) else 1.
            delta = distance[None, :]*scale + pf.rng.normal(size=(pf.n, 3))*std*dt
            yaw_mid = pf.px[:, 2] + .5*delta[:, 2]
            c, s = np.cos(yaw_mid), np.sin(yaw_mid)
            pf.px[:, 0] += c*delta[:, 0] - s*delta[:, 1]
            pf.px[:, 1] += s*delta[:, 0] + c*delta[:, 1]
            pf.px[:, 2] = pf.wrap(pf.px[:, 2] + delta[:, 2])
            if np.any(np.abs(pf.vel) > 1e-6) and mp.get("use_scale", True):
                pf.scale += pf.rng.normal(size=(pf.n, 3))*mp["scale_walk"]*math.sqrt(dt)
            pf.logw += pf._map_logprior(pf.px)
        pf.t += dt
