"""Opt-in ``b-v6h``: relaxed loaded-carry collision inflation at the door (PR "door guard relax", Refs #216).

``b-v6h`` is NOT a registered policy. It is the registered ``b-v6g`` controller plus a process-local
relaxation of two loaded-carry thresholds, applied by the stage-probe worker (``scripts/run_pair_stage_probes.py
--policies b-v6h --door-relax <variant>``) before the case is built. No registered source file changes: the
sweep guard class and the loaded gate are patched in the running process, exactly like the probe's diagnostic
patches, so ``b-v6e`` / ``b-v6g`` stay byte-identical (``tests/test_zone_pair_registered_source.py``).
Folding a variant into the registered closure (``zone_own_guards.py``, ``zone_pair_v6_policy.py``, ...) is a
separate, later step that needs a new bundle number and resealing; nothing here reserves one.

What is relaxed (everything reads only the robot's own estimate, its own issued commands and the static map):

* ``SweepGuard.margin`` = ``BASE_MARGIN_M + residual + K_SIGMA*sigma_xy + K_SIGMA*sigma_yaw*lever`` (registered:
  K_SIGMA = 2 on both terms, base 0.02 m, residual 0.015 m). A variant lowers the sigma multiples ``k_xy`` and
  ``k_yaw`` (1, then 0). The fixed 0.035 m is kept in every variant, and the command-displacement pad of
  ``PairSweepGuard.motion_clear`` is unchanged.
* ``GATE_LOADED`` (own-sigma gate of the loaded pair): a variant may widen the yaw thresholds
  (registered 3.0 / 2.5 deg). The xy gate and the dwell times are unchanged.
* ``advisory`` (variant ``adv``): a base motion command that the (relaxed) guard still refuses is issued anyway
  while a per-robot budget of commanded seconds lasts (``advisory_s``); afterwards the veto stands and the job
  fails as before. This is the "tolerate contact" upper bound; every override is logged (own estimate, command).

There is deliberately NO contact-reaction (stop / back off / retry) here: during a loaded carry the robot has no
observation of a contact (no measured joints, no contact flag, a carry frame shows the beam and a dark floor, the
PF is dead reckoning), so a blind retry of the same command from the same estimate meets the same veto. See the
experiment README for the argument and for the observation that would be needed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import math
from pathlib import Path

POLICY_ID = 'b-v6h'
BASE_POLICY = 'b-v6g'      # the registered policy every b-v6h case runs (spec['pair_policy'] stays b-v6g)

# name -> knobs. k_xy / k_yaw: sigma multiples (registered 2 / 2). gate_yaw_deg: (high, low) or None (registered 3.0 / 2.5).
VARIANTS = {
    'k1': {'k_xy': 1., 'k_yaw': 1., 'gate_yaw_deg': None, 'advisory_s': 0.,
           'note': 'sigma multiples 2 -> 1 on the inflation; gate and fixed margins registered'},
    'k0': {'k_xy': 0., 'k_yaw': 0., 'gate_yaw_deg': None, 'advisory_s': 0.,
           'note': 'no sigma inflation (only the fixed 0.035 m + command pad); gate registered'},
    'k0g': {'k_xy': 0., 'k_yaw': 0., 'gate_yaw_deg': (5., 4.), 'advisory_s': 0.,
            'note': 'k0 plus the loaded yaw gate 3.0/2.5 deg -> 5.0/4.0 deg'},
    'adv': {'k_xy': 0., 'k_yaw': 0., 'gate_yaw_deg': (5., 4.), 'advisory_s': 3.,
            'note': 'k0g plus an advisory override: up to 3 commanded seconds per robot pass a residual veto'},
}
REGISTERED = {'k_xy': 2., 'k_yaw': 2., 'gate_yaw_deg': (3., 2.5), 'advisory_s': 0.}

EVENTS: list[dict] = []          # advisory overrides of this process (one case per process), dumped into result.json
_BUDGET: dict[tuple, float] = {}
MAX_LOGGED_OVERRIDES = 40
_installed: dict = {}


def source_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def variant(name: str) -> dict:
    if name not in VARIANTS:
        raise ValueError(f'unknown door-relax variant {name!r}; choose one of {sorted(VARIANTS)}')
    return VARIANTS[name]


def base_policy(policy: str) -> str:
    """The registered policy a stage-probe policy name runs (b-v6h runs b-v6g; every other name is itself)."""
    return BASE_POLICY if policy == POLICY_ID else policy


def relaxed_margin(k_xy: float, k_yaw: float):
    """A drop-in for ``SweepGuard.margin`` with the given sigma multiples (same caps, same fixed margins)."""
    from harness import zone_own_guards as g

    def margin(self, pose, lever_m: float) -> float:
        sxy, syaw = min(pose.std_xy, g.SIGMA_CAP_XY_M), min(pose.std_yaw, g.SIGMA_CAP_YAW_RAD)
        return g.BASE_MARGIN_M + self.residual + k_xy * sxy + k_yaw * syaw * lever_m
    return margin


def install(name: str | None) -> dict | None:
    """Patch this process for one variant (the probe worker runs one case per process). ``None`` = registered."""
    if name is None:
        return None
    knobs = variant(name)
    from harness import zone_own_guards as g
    from harness import zone_pair_geometry as geo
    EVENTS.clear()
    _BUDGET.clear()
    g.SweepGuard.margin = relaxed_margin(knobs['k_xy'], knobs['k_yaw'])
    if knobs['gate_yaw_deg'] is not None:
        high, low = knobs['gate_yaw_deg']
        wide = dataclasses.replace(g.GATE_LOADED, high_yaw_rad=math.radians(high), low_yaw_rad=math.radians(low))
        # GATE_LOADED is imported by name; rebind it in every module that holds it (as the probe's loaded_yaw_gate_wide).
        for mod in ('harness.zone_own_guards', 'harness.zone_own_driver', 'harness.zone_own_sweep',
                    'harness.zone_pair_guards'):
            module = importlib.import_module(mod)
            if not hasattr(module, 'GATE_LOADED'):
                raise RuntimeError(f'{mod} has no GATE_LOADED to patch')
            module.GATE_LOADED = wide
    if knobs['advisory_s'] > 0:
        registered = geo.PairSweepGuard.motion_clear
        cap = float(knobs['advisory_s'])

        def motion_clear(self, servo, pose, cmd, *, loaded):
            ok = registered(self, servo, pose, cmd, loaded=loaded)
            if ok or not loaded or pose is None:
                return ok
            duration = cmd.get('duration_s')
            if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 <= duration <= 1.:
                return False
            role = (round(float(self.grasp['yaw_rad']), 4), tuple(round(float(v), 4) for v in self.grasp['xyz_m']))
            used = _BUDGET.get(role, 0.)
            if used + duration > cap + 1e-9:
                return False
            _BUDGET[role] = used + duration
            if len(EVENTS) < MAX_LOGGED_OVERRIDES:
                EVENTS.append({'role': role[0], 'used_s': round(_BUDGET[role], 3),
                               'own_estimate': [round(pose.x, 4), round(pose.y, 4), round(pose.yaw, 4)],
                               'std_xy_m': round(pose.std_xy, 4), 'std_yaw_rad': round(pose.std_yaw, 4),
                               'cmd': {k: cmd.get(k) for k in ('forward', 'left', 'turn', 'duration_s')}})
            return True
        geo.PairSweepGuard.motion_clear = motion_clear
    _installed.clear()
    _installed.update(describe(name))
    return dict(_installed)


def describe(name: str) -> dict:
    knobs = variant(name)
    return {'policy_id': POLICY_ID, 'base_policy': BASE_POLICY, 'variant': name, **knobs,
            'registered': REGISTERED, 'module_sha256': source_sha256(),
            'patched': ['harness.zone_own_guards.SweepGuard.margin']
                       + (['GATE_LOADED (yaw) in zone_own_guards/zone_own_driver/zone_own_sweep/zone_pair_guards']
                          if knobs['gate_yaw_deg'] else [])
                       + (['harness.zone_pair_geometry.PairSweepGuard.motion_clear (advisory budget)']
                          if knobs['advisory_s'] else [])}


def needed_clearance_m(k_xy: float, std_xy: float, k_yaw: float, std_yaw: float, lever_m: float = .18,
                       base_m: float = .02, residual_m: float = .015) -> float:
    """The analysis formula of hR_analysis.py (door clearance the guard demands) for any multiples."""
    return base_m + residual_m + k_xy * std_xy + k_yaw * std_yaw * lever_m
