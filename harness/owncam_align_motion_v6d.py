"""v6d: the PF predicts align pulses with the M1 ``fine`` motion profile (fitted for slow drives at the box).

Root cause (2026-09-29 stage-2 replay of the PR #263 ``b-v6c`` probe, 6 of 12 failures were
``ALIGN_RELOOK_NO_FIX``): the loop-v2 PF motion model ``motion`` (gain 1.47, spin-up tau 0.3 s) was fitted
on navigation drives. The align corrections are 0.2-0.3 s pulses of at most 0.05 m/s while the wrist
camera looks around (search/p45/inspect postures). The real chassis spins up much more slowly then: over
the align window the simulated robot moved 0.25-0.33 m forward while the default profile integrated
1.2-1.6 m. The
overconfident (std ~0.03 m) posterior then drifted 0.23-0.26 m inside the 6 s fix gap, the relook
frames had tags in view but inlier fraction 0, and three pans ended in ``ALIGN_RELOOK_NO_FIX``.

Reuse first: the repository already has the profile that fits this plant, ``motion_profiles.fine`` of
the M1 dev calibration (``experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json``, fitted on the
M1 dev seed s91 for arm-lowered fine drives at the box, not on the stage-probe cells; ``OwnCamLocalizer.
set_motion_profile`` selects it exactly as ``harness.m1_owncam_delivery._set_motion_profile`` does). This
module only makes that profile available to a tag PF whose params lack it, and names the align window that
uses it. It changes no filter code, but the profile is a whole parameter set: besides gain and tau it has
its own absolute noise (noise_abs 0.003/0.003/0.005, lower than the default 0.015/0.005/0.014, so also a
lower yaw noise) and switches the slip scale off (use_scale false). Applying it in the wrist-camera look
postures of the align states (a different arm posture than the fitted grasp drives) is checked only by the
offline replay and the stage probe, not by an independent fit. A provider whose params already carry
``fine`` (the M1/vision calibration) is used as is.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALIBRATION = 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'
PROFILE = 'fine'
# Controller states in which the wheels move by align pulses or are held while the wrist looks around.
ALIGN_STATES = ('align', 'align_relook_stop', 'align_relook', 'align_relook_return')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_profile():
    """The M1 ``fine`` profile plus where it came from (path, file sha256, profile sha256)."""
    raw = (ROOT/CALIBRATION).read_bytes()
    profile = json.loads(raw)['params']['motion_profiles'][PROFILE]
    return copy.deepcopy(profile), {'source': CALIBRATION, 'file_sha256': hashlib.sha256(raw).hexdigest(),
                                    'profile_sha256': _digest(profile)}


def _inner(provider):
    while hasattr(provider, 'provider'):
        provider = provider.provider
    return provider


def _pf(provider):
    """The particle filter that owns the motion parameters (tag PF or vision PF)."""
    inner = _inner(provider)
    loc = getattr(inner, 'loc', None)
    pf = getattr(loc, '_pf', loc)
    if pf is None or not hasattr(pf, 'set_motion_profile') or not hasattr(pf, 'params'):
        raise ValueError('align_fine_motion needs a provider whose PF selects motion profiles')
    return inner, pf


def enable_provider(provider):
    """Make ``fine`` selectable on this provider (idempotent; other providers are untouched)."""
    inner, pf = _pf(provider)
    if getattr(inner, 'align_motion_v6d', None) is not None:
        return inner.align_motion_v6d
    profiles = pf.params.get('motion_profiles', {})
    if PROFILE in profiles:
        info = {'origin': 'provider_params', 'profile_sha256': _digest(profiles[PROFILE])}
    else:
        profile, info = load_profile()
        # Rebind, never mutate: the params dict may be shared with other providers of the same run.
        pf.params = {**pf.params, 'motion_profiles': {**profiles, PROFILE: profile}}
        info = {'origin': 'injected', **info}
    inner.align_motion_v6d = info
    return info


def bound(provider):
    """True when this provider was switched to the v6d align motion (it is reused across runs)."""
    return getattr(_inner(provider), 'align_motion_v6d', None) is not None


def profile_for(state):
    return PROFILE if state in ALIGN_STATES else None
