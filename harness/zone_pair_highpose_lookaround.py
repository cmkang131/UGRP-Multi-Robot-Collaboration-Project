"""v98-only look-around: obstacle-normal position margin and one ``hold`` per tick.

Probe 7623c4dc (raise_high, 1.95-8.2 s): r2's opening look-around held 6.3 s at the dock because the arm guard
charged the isotropic radial ``std_xy`` (0.47 m at 2.0 s, almost all of it along y, which r2 cannot observe facing
east) against ``wall_west``, whose normal is x (sigma_x was 0.048 m). The held ticks also carried two ``hold``
commands, ``[hold] + [hold]``, because the guard-wait answer is already a hold.

The shared ``zone_own_executor``, ``zone_own_guards`` and ``zone_final_pair_guards`` are pinned by earlier bundles
and stay byte-identical. Everything below is v98: ``zone_pair_highpose_runtime.adopt_v98_frame_gate`` swaps each
actor's class (``sweep_steps``/``tick_sweep`` wrap two methods of ``OwnExecutor``) and its guard's class (``LookAroundGuard``) after init.

Margin. A rectangle's distance function is convex, so for a sphere centre displaced by a position error ``e`` the
distance is at least ``d + n.e`` with ``n`` the unit vector from the rectangle to the sphere. With a Gaussian
estimate ``n.e ~ N(0, n'Sigma n)``: the linear chance-constraint tightening of Blackmore, Ono and Williams (IEEE
T-RO 27(6), 2011) uses ``k * sqrt(n'Sigma n)`` instead of an isotropic radius. The shared guard charges
``std_xy = sqrt(trace Sigma)``, which is sqrt(2) times the per-axis sigma of a round estimate. That factor is kept:
``sigma_toward`` returns ``min(std_xy, sqrt(2) * sqrt(n'Sigma n))``, so a round estimate (or one elongated along
``n``) is charged exactly what the shared guard charges and only an ellipse elongated ACROSS ``n`` is charged less.
It is never larger than the shared margin. Yaw margin, base margin, residual and the 0.15 m cap are unchanged.
Chassis clearance, back-off translation checks and any pose other than the tick's own report stay isotropic.

No simulator state, measured joint or peer pose enters: the covariance is the own estimate's.
"""
from __future__ import annotations

import math

from harness import zone_own_guards as g
from harness.zone_final_pair_guards import PairArmGuard

ID = 'v98_look_around_obstacle_normal_sigma_v1'


def record() -> dict:
    return {'id': ID, 'position_margin': 'min(std_xy, sqrt(2)*sqrt(n.Sigma.n)) along the obstacle normal, arm sweeps only',
            'duplicate_leading_hold_removed': True, 'shared_sources_modified': False,
            'reference': 'Blackmore, Ono, Williams, IEEE T-RO 27(6), 2011 (linear chance constraint tightening)'}


def cov_xy(cov, std_xy):
    """(var_x, cov_xy, var_y) of a report's covariance, only when it agrees with the reported ``std_xy``."""
    try:
        vxx, vxy, vyy = float(cov[0][0]), float(cov[0][1]), float(cov[1][1])
        std = float(std_xy)
    except (TypeError, IndexError, ValueError):
        return None
    if not g._finite(vxx, vxy, vyy, std) or vxx < 0. or vyy < 0. or vxy * vxy > vxx * vyy * (1. + 1e-9) + 1e-12:
        return None
    return (vxx, vxy, vyy) if abs(math.sqrt(vxx + vyy) - std) <= 1e-3 + .01 * std else None


def sigma_toward(std_xy, cov, direction) -> float:
    """Position sigma along a world unit vector on the ``std_xy`` scale; ``std_xy`` itself without a covariance."""
    if cov is None:
        return std_xy
    vxx, vxy, vyy = cov
    nx, ny = direction
    along = math.sqrt(max(vxx * nx * nx + 2. * vxy * nx * ny + vyy * ny * ny, 0.))
    return min(std_xy, math.sqrt(2.) * along)


def rect_distance_normal(box, x, y):
    """``zone_own_guards._rect_distance`` (bit-identical) plus the world unit vector rectangle -> point (None inside)."""
    (cx, cy), (hx, hy) = box['center'], box['half']
    dx, dy = x - cx, y - cy
    c, s = (math.cos(box['yaw']), math.sin(box['yaw'])) if box['yaw'] else (1., 0.)
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    ex, ey = max(abs(lx) - hx, 0.), max(abs(ly) - hy, 0.)
    d = math.hypot(ex, ey)
    if d <= 1e-12:
        return d, None
    ux, uy = math.copysign(ex, lx) / d, math.copysign(ey, ly) / d
    return d, (c * ux - s * uy, s * ux + c * uy)


def hint_of(report):
    """(x, y, yaw, std_xy, std_yaw, cov) of one report, in the exact floats ``OwnPose.from_report`` makes."""
    if report is None or not report.initialized:
        return None
    vals = (report.x_m, report.y_m, report.yaw_rad, report.std_xy_m, report.std_yaw_rad)
    if not g._finite(*vals):
        return None
    vals = tuple(float(v) for v in vals)
    return (*vals, cov_xy(getattr(report, 'cov', None), vals[3]))


class LookAroundGuard(PairArmGuard):
    """``PairArmGuard`` (k = 1) whose arm clearance uses the obstacle-normal position sigma for the tick's own pose."""
    hint = None                                   # set by LookAroundMixin around one _sweep_steps call
    # Set by the v98 look recovery (zone_pair_highpose_relook) for the lifetime of one re-look job: the plan never
    # proposes a base back-off, so a re-look is pans only. False (the default) is the unchanged plan.
    pans_only = False

    def plan(self, current, look_pose, pans, pose, *, loaded, allow_backoff=False):
        return super().plan(current, look_pose, pans, pose, loaded=loaded,
                            allow_backoff=bool(allow_backoff) and not self.pans_only)

    def _cov_for(self, pose):
        h = self.hint
        if h is None or h[:5] != (pose.x, pose.y, pose.yaw, pose.std_xy, pose.std_yaw):
            return None                           # any other pose (moved back-off poses, nominal queries): isotropic
        return h[5]

    def _margin_toward(self, pose, cov, isotropic, toward):
        if toward is None:
            return isotropic
        iso = min(pose.std_xy, g.SIGMA_CAP_XY_M)
        return isotropic - iso + min(iso, sigma_toward(pose.std_xy, cov, toward))        # k_xy = 1 in PairArmGuard

    def arm_clearance(self, servo, pose, *, loaded):
        cov = self._cov_for(pose)
        if cov is None:
            return super().arm_clearance(servo, pose, loaded=loaded)
        best, hit = math.inf, None
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        for bx, by, bz, r in g.body_spheres(servo, loaded=loaded, mount_xyz_m=self.mount):
            mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
            lever = math.hypot(bx, by)
            margin = self.margin(pose, lever)
            for box in self.boxes:
                if bz - r >= box['height'] + margin:
                    continue                                    # passes over this wall
                d, toward = rect_distance_normal(box, mx, my)
                d -= r + self._margin_toward(pose, cov, margin, toward)
                if d < best:
                    best, hit = d, box['id']
        return best, hit

    def transition_diagnostic(self, current, target, pose, *, loaded):
        cov = None if pose is None else self._cov_for(pose)
        out = super().transition_diagnostic(current, target, pose, loaded=loaded)
        if cov is None:
            return out
        # Recompute the limiting sphere with the margin the decision used (evidence only, never consumed).
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        best, limiting = math.inf, None
        for sample in self.transition_samples(current, target):
            for i, (bx, by, bz, radius) in enumerate(g.body_spheres(sample, loaded=loaded, mount_xyz_m=self.mount)):
                mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
                lever = math.hypot(bx, by)
                for box in self.boxes:
                    margin = self.margin(pose, lever)
                    if bz - radius >= box['height'] + margin:
                        continue
                    raw, toward = rect_distance_normal(box, mx, my)
                    raw -= radius
                    margin = self._margin_toward(pose, cov, margin, toward)
                    if raw - margin < best:
                        best = raw - margin
                        part = ('yaw_bearing' if i == 0 else 'upper_arm' if i < 4 else 'forearm' if i < 6
                                else 'gripper_camera_fingers' if i < 6 + len(g.TOOL_SAMPLES_CM) else 'held_box')
                        limiting = {'sample_pwm': sample, 'sphere_index': i, 'sphere_part': part,
                                    'sphere_center_base_m': [bx, by, bz], 'sphere_radius_m': radius,
                                    'wall_id': box['id'], 'raw_clearance_mm': raw * 1000, 'margin_mm': margin * 1000,
                                    'clearance_mm': (raw - margin) * 1000, 'overlap_mm': max(0., margin - raw) * 1000}
        out['limiting'] = limiting
        out['sigma_model'] = ID
        return out


def sweep_steps(base):
    """Wrap ``ZoneOwnExecutor._sweep_steps``: hand the guard the tick's covariance for the call."""
    def _sweep_steps(self, now, target, loaded):
        guard = self.guard
        if not isinstance(guard, LookAroundGuard):
            return base(self, now, target, loaded)
        guard.hint = hint_of(self.pose.report(now))       # report(now) is idempotent for the same now
        try:
            return base(self, now, target, loaded)
        finally:
            guard.hint = None
    _sweep_steps.v98_look_around = True
    return _sweep_steps


def tick_sweep(base):
    """Wrap ``ZoneOwnExecutor._tick_sweep``: one ``hold`` per held tick (a guard wait is already the hold)."""
    def _tick_sweep(self, now, job):
        decision = base(self, now, job)
        commands = None if decision is None else decision.get('commands')
        if commands and len(commands) > 1 and commands[0]['kind'] == 'hold' and commands[1]['kind'] == 'hold':
            decision = {**decision, 'commands': commands[1:]}
        return decision
    _tick_sweep.v98_look_around = True
    return _tick_sweep


def adopt_guard(rid, actor):
    """Swap one actor's arm guard to the v98 class; fail closed on anything but the pair arm guard."""
    if type(actor.guard) is not PairArmGuard:
        raise TypeError(f'v98 look-around expects a PairArmGuard, {rid} has {type(actor.guard).__name__}')
    actor.guard.__class__ = LookAroundGuard
