"""Probe-only opt-in: the lag-model leg length for AXIAL carry legs too (2026-09-30, b-v6h, Refs #216; PR #286 proposal P1b).

Finding that motivates it (offline, PR #286 ``experiments/2026-09-30-l1-axial-offset``): the pair drives every carry leg for a
fixed time computed open loop from the plan (never confirmed by the estimate). For the lateral axis the registered flag
``carry_lateral_lag`` already inverts the calibrated first-order-lag loaded plant (``harness.owncam_carry_v6e.leg_duration``), but
``LAG_AXES = ('lateral',)`` leaves the axial legs on the constant ``CARRY_ODOM_SCALE['axial']`` = 0.772, which was measured on one
command length (10 s). The wheels' spin-up loss is a length-independent ~41 mm, so the axial legs travel L0 +9..+21 mm and L1 +43 mm
too far (sheet 1.0), which is most of the ~64 mm intercept of the L1 end error.

This patch (process-local, one probe case per process; the registered sources stay byte-identical,
``tests/test_zone_pair_registered_source.py``) does exactly what the proposal says:

1. ``harness.owncam_carry_v6e.LAG_AXES`` becomes ``('lateral', 'axial')``, so ``PairTeam.door_schedule`` (which reads the module
   attribute at call time and only when the policy has ``carry_lateral_lag``, true for b-v6g) also inverts the lag plant for axial legs;
2. the lag plant of an AXIAL leg uses the forward gain of the PF WITH the gain fix (``KAPPA`` x 1.4004 = 1.3281), because the
   planning time must be the inverse of the same plant the PF integrates. Without the gain fix the plan would be 43 mm too SHORT on L1
   (PR #286 P1a, replay 57 %), so this patch refuses to install unless the gain fix mode is given too. The lateral legs keep the
   registered calibration untouched; the session ``params`` are not mutated (a copy is made at the call site only).

Nothing the robot senses changes. The added quantities are the registered time constants (``tau_s``, ``tau_stop_s``), the registered
command and speed constants, and the fixed calibration multiplier ``KAPPA`` of the gain fix. No ground truth, no simulator state,
no partner information.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

MODES = {'axial': {'note': 'axial carry legs use the lag-model duration with the PF gain x KAPPA (needs --carry-gain-fix pf)'}}
LOGGED: list[dict] = []           # one entry per axial leg duration this process planned, dumped into result.json
MAX_LOGGED = 40
_installed: dict = {}


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def mode(name: str) -> dict:
    if name not in MODES:
        raise ValueError(f'unknown carry-axial-lag mode {name!r}; choose one of {sorted(MODES)}')
    return MODES[name]


def install(name: str | None, gain_fix_mode: str | None) -> dict | None:
    """Patch this process. ``None`` = registered behaviour (axial legs on CARRY_ODOM_SCALE['axial'])."""
    if name is None:
        return None
    knobs = mode(name)
    if gain_fix_mode is None:
        raise ValueError('carry axial lag needs the PF gain fix (kappa): without it the axial leg is planned 43 mm too short')
    from harness import owncam_carry_v6e as carry
    from harness import zone_pair_carry_gain_fix as gain_fix
    if getattr(carry.leg_duration, '_axial_lag_wrapped', False):
        raise RuntimeError('carry axial lag is already installed in this process')
    LOGGED.clear()
    registered_leg_duration = carry.leg_duration

    def leg_duration(distance_m, axis, command, calibration):
        if axis != 'axial':
            return registered_leg_duration(distance_m, axis, command, calibration)
        motion = calibration['motion_loaded']
        scaled = {**calibration, 'motion_loaded': {**motion, 'gain': gain_fix.scaled_gain(motion['gain'])}}   # a copy; params unchanged
        seconds = registered_leg_duration(distance_m, axis, command, scaled)
        if len(LOGGED) < MAX_LOGGED:
            LOGGED.append({'distance_m': round(float(distance_m), 4), 'duration_s': round(float(seconds), 4),
                           'forward_gain_used': round(float(scaled['motion_loaded']['gain'][0][0]), 5)})
        return seconds
    leg_duration._axial_lag_wrapped = True
    carry.leg_duration = leg_duration
    carry.LAG_AXES = ('lateral', 'axial')
    _installed.clear()
    _installed.update(describe(name))
    return dict(_installed)


def describe(name: str) -> dict:
    knobs = mode(name)
    from harness import zone_pair_carry_gain_fix as gain_fix
    return {'mode': name, **knobs, 'lag_axes': ['lateral', 'axial'], 'kappa': gain_fix.KAPPA, 'module_sha256': source_sha256(),
            'patched': ['harness.owncam_carry_v6e.LAG_AXES', 'harness.owncam_carry_v6e.leg_duration (axial: forward gain x kappa, copy)']}
