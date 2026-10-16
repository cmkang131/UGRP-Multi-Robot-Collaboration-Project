"""Probe-only diagnostic: correct the loaded forward gain of the pair carry particle filter (2026-09-30, b-v6h gain fix, Refs #216).

Finding that motivates it (offline, ``experiments/2026-09-30-carry-x-bias``, PR #284): while the pair drives forward with the beam,
the carry PF integrates the registered loaded forward gain ``motion_loaded.gain[0][0]`` = 1.4004, but the wheels behave as if it were
about 1.328 (a 5.2 % shorter forward travel, the same for r1 and r2). The PF therefore runs ahead of the truth by ~5 % of every
forward leg (L0 +33 mm, L1 +47 mm) and its along-track sigma cannot follow. Fitted multiplier ``KAPPA`` = 0.9483 (offline fit
set = seed 911 chain + hR2 leg 0; hold-out RMS end error 4.3 mm; ``proposed_carry_fwd_gain_fit.json``).

One process-local mode ``pf`` (the registered sources stay byte-identical; ``tests/test_zone_pair_registered_source.py``): the PF
gain is multiplied by KAPPA. Nothing the robot commands changes directly (the open-loop AXIAL leg length comes from the registered
``CARRY_ODOM_SCALE['axial']`` and is not touched: recorded chain legs already travel the planned length in ground truth, L0
554 mm for 550 mm planned, so stretching the plan by the gain factor would be wrong), only what the PF believes. Commands can
still differ slightly through the closed-loop steering that reads the PF estimate.

Only the ``[0][0]`` entry (forward command -> forward velocity) is touched. The lateral row, the turn row, the time constants and
all noise terms are unchanged. The multiplier is a fixed constant of the calibration, not a runtime measurement: no ground truth,
no simulator state and no partner information reaches the controller.

The patch wraps ``harness.owncam_carry_v6e.enable_provider`` (called once per robot by ``PairSession``): after the registered
call it rebinds ``pf.params`` with a copy whose gain is scaled (rebind, never mutate: the params dict may be shared).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

KAPPA = 0.9483378899463337            # PR #284 proposed_carry_fwd_gain_fit.json (M1, kappa_M1)
REGISTERED_FORWARD_GAIN = 1.4004      # calibration_loop_v2.json params.motion_loaded.gain[0][0] (from the same file, asserted)
MODES = {'pf': {'note': 'PF loaded forward gain x KAPPA; the open-loop leg length is not changed'}}
SOURCE = {'fit': 'experiments/2026-09-30-carry-x-bias/proposed_carry_fwd_gain_fit.json (PR #284)',
          'fit_file_sha256': '02884b59026d34710473e97a154e8ffff6132dd388d36f8c893b0f2a616a2f56',
          'kappa_M1': KAPPA, 'forward_gain_M1': 1.3280523810808458}

APPLIED: list[dict] = []              # one entry per PF the patch rescaled in this process, dumped into result.json
_installed: dict = {}


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def mode(name: str) -> dict:
    if name not in MODES:
        raise ValueError(f'unknown carry-gain-fix mode {name!r}; choose one of {sorted(MODES)}')
    return MODES[name]


def scaled_gain(gain, kappa: float = KAPPA):
    """A copy of the 3x3 gain with only the forward-command -> forward-velocity entry multiplied."""
    rows = [list(map(float, row)) for row in gain]
    rows[0][0] *= kappa
    return rows


def install(name: str | None) -> dict | None:
    """Patch this process (one probe case per process). ``None`` = registered behaviour."""
    if name is None:
        return None
    knobs = mode(name)
    from harness import owncam_carry_v6e as carry
    APPLIED.clear()
    registered_enable = carry.enable_provider
    if getattr(registered_enable, '_gain_fix_wrapped', False):        # a second install in one process would double-scale
        raise RuntimeError('carry gain fix is already installed in this process')

    def enable_provider(provider, *args, **kwargs):
        info = registered_enable(provider, *args, **kwargs)
        inner, pf = carry._pf(provider)
        if getattr(inner, 'carry_gain_fix', None) is None:
            before = [list(map(float, row)) for row in pf.params['motion_loaded']['gain']]
            after = scaled_gain(before)
            pf.params = {**pf.params, 'motion_loaded': {**pf.params['motion_loaded'], 'gain': after}}
            inner.carry_gain_fix = {'kappa': KAPPA, 'gain_before': before, 'gain_after': after}
            APPLIED.append({'kappa': KAPPA, 'forward_gain_before': before[0][0], 'forward_gain_after': after[0][0]})
            if isinstance(info, dict):
                info['gain_fix'] = dict(inner.carry_gain_fix)
        return info
    enable_provider._gain_fix_wrapped = True
    carry.enable_provider = enable_provider
    _installed.clear()
    _installed.update(describe(name))
    return dict(_installed)


def describe(name: str) -> dict:
    knobs = mode(name)
    return {'mode': name, **knobs, 'kappa': KAPPA, 'source': SOURCE, 'module_sha256': source_sha256(),
            'patched': ['harness.owncam_carry_v6e.enable_provider (PF motion_loaded.gain[0][0] x kappa)']}
