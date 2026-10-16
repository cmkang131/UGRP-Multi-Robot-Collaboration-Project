#!/usr/bin/env python3
"""Front-ultrasonic door-frame sweep: offline sensor characterisation (no physics step, no controller).

Question (docs/ultrasonic_range_sensor.md, outputs/door-passage-lit-review-20260929.md, rank 1): can a robot that
stops in front of the 0.5 m door and strafes sideways read the door-frame edges from its own front ultrasonic
range (the range jumps from the wall to the far room when the cone fits inside the opening) and so measure its
lateral offset ``y`` and heading ``yaw`` to about 0.5-1 cm / 1 deg?

Scope: sensor characterisation. Ground truth is used only to place the robot and to score the estimate; the
estimator sees ONLY ``RangeReading``-like data (status, range) and the commanded strafe coordinate, plus the
static map (door centre / width, wall plane). No ``mj_step``: ``mj_step*`` are replaced by a failing stub.
Only model load, ``mj_forward`` and the shared ray cast (``sim.ultrasonic_range.MujocoUltrasonic.cast`` +
``harness.ultrasonic_model.first_echo``) run. The noise model is the shared one
(``harness.ultrasonic_model.noisy_reading_with_cause``), applied per reading tick with a vectorised, tested
equivalent so thousands of sweeps stay cheap.

Subcommands: ``stationary`` (a: one reading), ``sweep`` (b: strafe sweep grid), ``ablate`` (ray-count and
timing/odometry sensitivities), ``occlusion`` (carry postures from stage-probe checkpoints), ``door-frame-side``
(side-facing sensor, informational). Raw arrays go to ``--out`` (under outputs/) with sha256 in ``MANIFEST.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402


def _forbid_physics() -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError('door_ultrasonic_sweep: physics stepping is forbidden (offline characterisation)')
    for name in ('mj_step', 'mj_step1', 'mj_step2'):
        setattr(mujoco, name, forbidden)


_forbid_physics()

from harness.ultrasonic_model import (DEFAULT_SPEC, NOISE_STREAM, NO_ECHO, first_echo,  # noqa: E402
                                      noisy_reading_with_cause, reading_rng, sensor_seed)

MAP_ID = 'zone_wide_door_geometry_v2'      # final-environment single-door map (walls_v3, no tags), door_1
ROBOT = 'r1'
FLOOR_Z = .0325
FAR_ECHO = np.nan                          # 'no echo' marker in the noise-free traces

# ---- static map facts (read from maps/zones/zone_wide_door_geometry_v2.json, checked in build_world) ----------
def map_facts() -> dict:
    static = json.loads((ROOT / 'maps' / 'zones' / (MAP_ID + '.json')).read_text())
    door = static['passages'][0]
    walls = {o['id']: o for o in static['obstacles']}
    d2 = walls['wall_divider_2']
    thickness = 2 * d2['half_extents_m'][0]
    plane_x = door['center_m'][0]
    return {'map_id': static['map_id'], 'door_id': door['id'], 'door_center_y': float(door['center_m'][1]),
            'door_half_width': float(door['width_m']) / 2, 'wall_plane_x': float(plane_x),
            'wall_thickness_m': float(thickness), 'wall_face_x': float(plane_x - thickness / 2),
            'wall_height_m': float(d2['height_m']), 'wall_profile': static['wall_profile']['id'],
            'far_wall_x': float(static['bounds_m'][1]),
            'static_map_sha256': hashlib.sha256(json.dumps(static, sort_keys=True).encode()).hexdigest()}


# ---- spec variants ---------------------------------------------------------------------------------------------
def spec_for(half_angle_deg: float, **kw):
    """Same 85-ray density for any half-angle (ring step scales), everything else the shared v2 model."""
    return replace(DEFAULT_SPEC, half_angle_deg=float(half_angle_deg), ring_step_deg=float(half_angle_deg) / 6.,
                   **kw)


def exact_spec(spec):
    return replace(spec, dropout_prob=0., outlier_prob=0., noise_sigma0_m=0., noise_rel=0.)


# ---- world -----------------------------------------------------------------------------------------------------
class DoorWorld:
    """Final-environment door map (tag-free) with robot r1 only near the door; everything else parked far away."""

    def __init__(self):
        from sim.multi_masterpi_production import build_multi_robot_xml
        from sim.zone_geometry_scene import GeometryCargoZoneScene
        spec = {'map': MAP_ID, 'seed': 11, 'goal': {'A': {'cyan': 1}}, 'team_cargo': []}
        scene = GeometryCargoZoneScene.from_spec(spec, 'local_contact_fine')
        xml = scene.transform(build_multi_robot_xml(None))
        self.xml_sha256 = hashlib.sha256(xml.encode()).hexdigest()
        self.static_map = scene.config['static_map']
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        self.facts = map_facts()
        self._q = {}
        for j in range(self.model.njnt):
            name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, j) or ''
            if name.endswith('_free'):
                self._q[name] = int(self.model.jnt_qposadr[j])
        for k, name in enumerate(n for n in self._q if n != f'{ROBOT}__base_free'):
            self._set(name, -20., -20. - 2. * k, .3, 0.)         # parked outside the arena, beyond the max range
        self.sonars = {}

    def _set(self, joint, x, y, z, yaw):
        q = self._q[joint]
        self.data.qpos[q:q + 7] = [x, y, z, math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]

    def place(self, x, y, yaw):
        self._set(f'{ROBOT}__base_free', x, y, FLOOR_Z, yaw)
        mujoco.mj_forward(self.model, self.data)

    def sonar(self, spec):
        from sim.ultrasonic_range import MujocoUltrasonic
        key = (spec.half_angle_deg, spec.ring_step_deg, spec.ring_base_count)
        if key not in self.sonars:
            self.sonars[key] = MujocoUltrasonic(self.model, self.data, ROBOT, seed=sensor_seed(0, ROBOT), spec=exact_spec(spec))
        return self.sonars[key]

    def echo(self, sonar) -> float:
        c = sonar.cast()
        e = first_echo(c['dist'], sonar.alpha, c['beta'], sonar.spec)
        return FAR_ECHO if e is None else float(e)


def base_xy(facts, spec, d, y0, psi, s):
    """Base position for approach distance ``d`` (sensor face to west wall face at s=0, y0=0, yaw=0), body-lateral shift ``s``."""
    bx0 = facts['wall_face_x'] - d - spec.face_x_m
    return bx0 - s * math.sin(psi), facts['door_center_y'] + y0 + s * math.cos(psi)


def echo_trace(world: DoorWorld, spec, d, y0, psi, s_grid) -> np.ndarray:
    """Noise-free first echo (nan = none) at each strafe coordinate; the robot is only placed, never stepped."""
    sonar = world.sonar(spec)
    out = np.empty(len(s_grid))
    for i, s in enumerate(s_grid):
        x, y = base_xy(world.facts, spec, d, y0, psi, float(s))
        world.place(x, y, psi)
        out[i] = world.echo(sonar)
    return out


# ---- noise: vectorised twin of harness.ultrasonic_model.noisy_reading_with_cause ---------------------------------
def noise_draws(episode_seed: int, n_ticks: int, robot_id: str = ROBOT) -> np.ndarray:
    """(n_ticks, 4) of (u_drop, u_out, u_val, z), drawn exactly as noisy_reading_with_cause does."""
    seed = sensor_seed(episode_seed, robot_id)
    out = np.empty((n_ticks, 4))
    for tick in range(n_ticks):
        rng = reading_rng(seed, robot_id, tick, NOISE_STREAM)
        out[tick] = (rng.random(), rng.random(), rng.random(), rng.standard_normal())
    return out


def apply_noise(true_echo: np.ndarray, ticks: np.ndarray, draws: np.ndarray, spec):
    """Vector equivalent of noisy_reading_with_cause. Returns (ok, range_m) with range nan when not ok."""
    e = np.asarray(true_echo, float)
    u = draws[ticks]
    none = np.isnan(e)
    dropout = (~none) & (u[:, 0] < spec.dropout_prob)
    outlier = (~dropout) & (u[:, 1] < spec.outlier_prob)
    r = np.where(outlier, spec.min_range_m + u[:, 2] * (spec.max_range_m - spec.min_range_m),
                 e + (spec.noise_sigma0_m + spec.noise_rel * np.maximum(e, 0.)) * u[:, 3])
    valid = ~dropout & (outlier | ~none) & (r >= spec.min_range_m) & (r <= spec.max_range_m)
    r = np.minimum(np.round(r / spec.quantum_m) * spec.quantum_m, spec.sdk_clamp_m)
    return valid, np.where(valid, r, np.nan)


# ---- estimator -------------------------------------------------------------------------------------------------
def _solve_theta(target: float, d1: float, d2: float, psi: float) -> float:
    """theta with d2*tan(theta+psi) + d1*tan(theta-psi) = target (monotone); bisection."""
    lo, hi = abs(psi) + 1e-6, math.radians(50.)
    f = lambda th: d2 * math.tan(th + psi) + d1 * math.tan(th - psi)
    if target <= f(lo):
        return lo
    if target >= f(hi):
        return hi
    for _ in range(60):
        mid = .5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return .5 * (lo + hi)


def _robust_line(x, y):
    """Least squares with two 3.5-MAD clipping passes -> (intercept at x=0, slope, slope sigma) or None."""
    keep = np.ones(len(x), bool)
    for _ in range(3):
        if keep.sum() < 4:
            return None
        b, a = np.polyfit(x[keep], y[keep], 1)
        res = y - (a + b * x)
        mad = 1.4826 * np.median(np.abs(res[keep])) + 1e-4
        keep = np.abs(res) <= 3.5 * mad
    xk = x[keep]
    sxx = float(np.sum((xk - xk.mean()) ** 2))
    sig = float(np.sqrt(np.sum(res[keep] ** 2) / max(1, keep.sum() - 2)) / math.sqrt(max(sxx, 1e-12)))
    return float(a), float(b), sig


def estimate_sweep(s, ok, r, facts, *, theta_deg=None, sensor_fwd=DEFAULT_SPEC.face_x_m, min_end_near=3,
                   min_far=3, edge_margin_m=.03, near_low=.06, near_high=.15, plateau_margin_m=.03,
                   min_flat_span_m=.12, yaw_gate_deg=.6, max_mismatch_frac=.06):
    """Door-frame edges from one strafe sweep.

    ``s``: body-lateral strafe coordinate of each reading (m, from the commanded motion; + = left),
    ``ok``/``r``: reading validity and range (m). ``theta_deg``: assumed cone half-angle, or ``None`` to
    self-calibrate it from the width of the far window (the door width is on the static map).

    Always (when both frame edges are bracketed): ``aim_m``, the lateral offset of the sensor axis at the door plane,
    which needs no yaw. Only when the wall-range slope is resolved (``yaw_sigma_deg <= yaw_gate_deg``): ``yaw_deg`` and
    ``y_base_m``. ``status == 'ok'`` means both edges were bracketed; ``yaw_resolved`` says whether yaw/y are valid.
    """
    s, ok, r = np.asarray(s, float), np.asarray(ok, bool), np.asarray(r, float)
    n = len(s)
    fail = lambda why: {'status': why}
    if ok.sum() < 8:
        return fail('too_few_readings')
    order = np.sort(r[ok])
    r_ref = float(np.median(order[:max(3, len(order) // 4)]))
    if r_ref > 1.8:
        return fail('no_wall_range')
    near = ok & (r >= r_ref - near_low) & (r <= r_ref + near_high)
    n0 = np.concatenate([[0], np.cumsum(near)])
    # An optimal change point can always sit on a near/far flip (or on the end-margin bound): scan only those.
    lo, hi = min_end_near, n - min_end_near
    flips = np.flatnonzero(near[1:] != near[:-1]) + 1
    cand = np.unique(np.concatenate([flips, [lo, hi]]))
    cand = cand[(cand >= lo) & (cand <= hi)]
    ii, j = cand[:, None], cand[None, :]
    cost = (ii - n0[ii]) + (n0[j] - n0[ii]) + ((n - j) - (n0[n] - n0[j]))
    cost = np.where(j - ii >= min_far, cost, 10 ** 9)
    if cost.min() >= 10 ** 9:
        return fail('no_bracket')
    a, b = np.unravel_index(int(np.argmin(cost)), cost.shape)
    i0, j0 = int(cand[a]), int(cand[b])
    mismatches = int(cost[a, b])
    if mismatches > max_mismatch_frac * n:
        return fail('ragged_edges')
    if not (near[:i0].sum() >= min_end_near - 1 and near[j0:].sum() >= min_end_near - 1):
        return fail('no_bracket')
    s1, s2 = .5 * (s[i0 - 1] + s[i0]), .5 * (s[j0 - 1] + s[j0])
    half = facts['door_half_width']
    use = near & ((s < s1 - edge_margin_m) | (s > s2 + edge_margin_m))
    line = _robust_line(s[use], r[use]) if use.sum() >= 6 else None
    if line is None:
        return fail('no_slope')
    a0, slope, slope_sig = line

    def geometry(a0, slope):
        slope = float(np.clip(slope, -.5, .5))
        psi = math.asin(slope)
        d1, d2 = a0 + slope * s1, a0 + slope * s2
        width_y = (s2 - s1) * math.cos(psi)
        theta = _solve_theta(2. * half - width_y, d1, d2, psi) if theta_deg is None else math.radians(theta_deg)
        y_s1 = -half + d1 * math.tan(theta - psi)      # sensor lateral offset from the door centre when the right edge crosses
        y_s2 = half - d2 * math.tan(theta + psi)
        y_s0 = .5 * ((y_s1 - s1 * math.cos(psi)) + (y_s2 - s2 * math.cos(psi)))
        return psi, theta, y_s0

    psi, theta, y_s0 = geometry(a0, slope)
    # Stage 2: the shoulders next to the edges are slanted (nearest wall point is the post corner), so the plain
    # near-range slope is biased. Refit the slope on the flat part only: sensor laterally beyond the frame edge.
    flat_used = False
    for _ in range(2):
        flat = near & (np.abs(y_s0 + s * math.cos(psi)) >= half + plateau_margin_m)
        if flat.sum() >= 12 and np.ptp(s[flat]) >= min_flat_span_m:
            refit = _robust_line(s[flat], r[flat])
            if refit is not None:
                a0, slope, slope_sig = refit
                psi, theta, y_s0 = geometry(a0, slope)
                flat_used = True
    yaw_sigma = math.degrees(slope_sig / max(1e-6, math.cos(psi)))
    resolved = yaw_sigma <= yaw_gate_deg
    # Yaw-free aim point: the same edge equations with yaw 0 (uses the median near range, no slope).
    a_flat = float(np.median(r[near]))
    _, theta0, y_flat = geometry(a_flat, 0.)
    out = {'status': 'ok', 'aim_m': float(y_flat), 'theta_deg': math.degrees(theta if resolved else theta0),
           's_in_m': float(s1), 's_out_m': float(s2), 'range_at_s0_m': float(a0 if resolved else a_flat),
           'mismatches': mismatches, 'n': n, 'far_samples': j0 - i0, 'flat_slope_used': flat_used,
           'yaw_sigma_deg': yaw_sigma, 'yaw_resolved': bool(resolved)}
    if resolved:
        out.update(y_base_m=float(y_s0 - sensor_fwd * math.sin(psi)), yaw_deg=math.degrees(psi))
    return out


# ---- sweep geometry --------------------------------------------------------------------------------------------
GRID_STEP = .002
S_MAX = .50


def s_grid():
    n = int(round(S_MAX / GRID_STEP))
    return np.arange(-n, n + 1) * GRID_STEP


def sample_sweep(trace, W, v, period, t0=0., latency=0., scale=1., reverse=False):
    """Sample the fine-grid trace along one pass at speed ``v`` (m/s): -W to +W, or +W to -W with ``reverse``.

    ``latency`` (s): the position stamped on a reading lags the true position by v*latency (along the motion).
    ``scale``: the true strafe distance from the pass start is ``scale`` times the commanded one (odometry gain error).
    Returns arrays sorted by the commanded coordinate (ascending): coordinate the ESTIMATOR uses, the noise-free echo at
    the true position and the reading ticks (time order, so a reverse pass keeps its own noise stream).
    """
    n = int(math.floor(2 * W / (v * period) + 1e-9)) + 1
    k = np.arange(n)
    travelled = k * v * period
    start = W if reverse else -W
    s_cmd = start + (-travelled if reverse else travelled)
    s_true = np.clip(start + (-1. if reverse else 1.) * (travelled - v * latency) * scale, -S_MAX, S_MAX)
    idx = np.clip(np.round(s_true / GRID_STEP).astype(int) + int(round(S_MAX / GRID_STEP)), 0, len(trace) - 1)
    ticks = (k + int(round(t0 / period))).astype(int)
    order = np.argsort(s_cmd)
    return s_cmd[order], trace[idx][order], ticks[order]


def summarise(err_y, err_psi, ok_flags):
    ok_flags = np.asarray(ok_flags, bool)
    out = {'runs': int(len(ok_flags)), 'success_rate': float(ok_flags.mean()) if len(ok_flags) else float('nan')}
    for name, e in (('y_cm', 100 * np.asarray(err_y)), ('yaw_deg', np.asarray(err_psi))):
        e = e[ok_flags]
        if len(e) == 0:
            out[name] = None
            continue
        out[name] = {'bias': float(e.mean()), 'rms': float(np.sqrt(np.mean(e ** 2))), 'std': float(e.std()),
                     'p95_abs': float(np.percentile(np.abs(e), 95)), 'max_abs': float(np.abs(e).max())}
    return out


# ---- experiment grid -------------------------------------------------------------------------------------------
Y_OFFSETS_M = [k / 100 for k in range(-10, 11)]                 # base lateral offset from the door centre, 1 cm steps
YAWS_DEG = list(range(-6, 7))                                  # heading error, 1 deg steps
APPROACH_M = (.40, .50, .60, .75, .90)                         # sensor face to the door wall face
HALF_ANGLES_DEG = (15., 7.5)                                   # the two readings of "measuring angle 15 deg"
SWEEP_HALF_WIDTHS_M = (.15, .20, .30, .40, .50)
SPEEDS_MPS = (.03, .05, .08, .12)
MAX_TICKS = 1300
sha256_file = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cells():
    return [(y, math.radians(p), p) for y in Y_OFFSETS_M for p in YAWS_DEG]


def build_traces(world, half_angle, d, sg, spec=None):
    spec = spec or spec_for(half_angle)
    return np.stack([echo_trace(world, spec, d, y, psi, sg) for y, psi, _ in cells()]).astype(np.float32)


def run_cell(trace_row, spec, W, v, draws_list, facts, theta_deg, **sample_kw):
    """Estimates for one cell/design over the noise seeds -> list of dicts (status, y_base_m, yaw_deg, ...)."""
    s, e, ticks = sample_sweep(np.asarray(trace_row, float), W, v, spec.period_s, **sample_kw)
    out = []
    for dr in draws_list:
        ok, r = apply_noise(e, ticks, dr, spec)
        out.append(estimate_sweep(s, ok, r, facts, theta_deg=theta_deg))
    return out, len(s)


def truth_aim(d, y0, psi, spec=DEFAULT_SPEC):
    """Lateral offset (from the door centre) where the sensor axis meets the door plane, at strafe coordinate 0."""
    f = spec.face_x_m
    return y0 + f * math.sin(psi) + (d + f * (1 - math.cos(psi))) * math.tan(psi)


def _stat(e):
    e = np.asarray(e, float)
    e = e[~np.isnan(e)]
    if len(e) == 0:
        return None
    return {'bias': float(e.mean()), 'rms': float(np.sqrt(np.mean(e ** 2))), 'p95_abs': float(np.percentile(np.abs(e), 95)),
            'max_abs': float(np.abs(e).max()), 'n': int(len(e))}


def grid_stats(world_facts, traces, spec, d, W, v, draws_list, theta_deg, cell_list=None, **kw):
    """Score one sweep design over all (y, yaw) cells and noise seeds. Errors: y_cm, yaw_deg, aim_cm."""
    ey, epsi, eaim, cell_ey_mean, cell_ey_std = [], [], [], [], []
    n_total = n_bracket = n_resolved = 0
    n_readings = 0
    for row, (y0, psi, pd) in zip(traces, cell_list or cells()):
        ests, n_readings = run_cell(row, spec, W, v, draws_list, world_facts, theta_deg, **kw)
        cy = []
        for e in ests:
            n_total += 1
            if e['status'] != 'ok':
                continue
            n_bracket += 1
            eaim.append(e['aim_m'] - truth_aim(d, y0, psi, spec))
            if e['yaw_resolved']:
                n_resolved += 1
                ey.append(e['y_base_m'] - y0)
                epsi.append(e['yaw_deg'] - pd)
                cy.append(ey[-1])
        if len(cy) >= 2:
            cell_ey_mean.append(np.mean(cy))
            cell_ey_std.append(np.std(cy))
    out = {'runs': n_total, 'bracket_rate': n_bracket / n_total, 'resolved_rate': n_resolved / n_total,
           'y_cm': _stat(100 * np.array(ey)), 'yaw_deg': _stat(epsi), 'aim_cm': _stat(100 * np.array(eaim)),
           'y_noise_std_cm': float(100 * np.mean(cell_ey_std)) if cell_ey_std else None,
           'y_systematic_rms_cm': float(100 * np.sqrt(np.mean(np.square(cell_ey_mean)))) if cell_ey_mean else None,
           'n_readings': int(n_readings), 'duration_s': float(2 * W / v)}
    return out


def cmd_sweep(args):
    approaches = tuple(float(x) for x in args.approach.split(',')) if args.approach else APPROACH_M
    widths = tuple(float(x) for x in args.widths.split(',')) if args.widths else SWEEP_HALF_WIDTHS_M
    speeds = tuple(float(x) for x in args.speeds.split(',')) if args.speeds else SPEEDS_MPS
    world = DoorWorld()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sg = s_grid()
    draws = [noise_draws(k, MAX_TICKS) for k in range(args.seeds)]
    results, trace_store = [], {}
    t0 = time.time()
    for th in HALF_ANGLES_DEG:
        spec = spec_for(th)
        for d in approaches:
            traces = build_traces(world, th, d, sg)
            trace_store[f'th{th}_d{d}'] = traces
            print(f'traces th={th} d={d} {time.time() - t0:.0f}s', flush=True)
            for W in widths:
                for v in speeds:
                    st = grid_stats(world.facts, traces, spec, d, W, v, draws, None)
                    results.append({'half_angle_true_deg': th, 'approach_m': d, 'sweep_half_width_m': W,
                                    'speed_mps': v, 'theta_assumed': 'self_calibrated', **st})
            print(f'  graded {len(results)} designs {time.time() - t0:.0f}s', flush=True)
    np.savez_compressed(out / 'echo_traces.npz', s_m=sg, y_offsets_m=np.array(Y_OFFSETS_M), yaws_deg=np.array(YAWS_DEG),
                        **trace_store)
    (out / 'grid_results.json').write_text(json.dumps({'facts': world.facts, 'scene_xml_sha256': world.xml_sha256,
                                                       'seeds': args.seeds, 'results': results}, indent=1))
    print('done', time.time() - t0)


# ---- (a) one stationary reading ----------------------------------------------------------------------------------
def cmd_stationary(args):
    """What a single stopped reading says: range to the wall, and only one bit about y (cone inside the opening?)."""
    world = DoorWorld()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    draws = [noise_draws(k, len(cells())) for k in range(args.seeds)]
    for th in HALF_ANGLES_DEG + (10.,):
        spec = spec_for(th)
        for d in APPROACH_M:
            tr = np.array([echo_trace(world, spec, d, y, psi, np.array([0.]))[0] for y, psi, _ in cells()])
            far = np.isnan(tr) | (tr > 1.8)
            y_of = np.array([c[0] for c in cells()])
            psi_of = np.array([c[1] for c in cells()])
            d0 = d + spec.face_x_m * (1 - np.cos(psi_of))
            near = ~far
            # window half width (yaw 0): largest |y| with a far reading, refined by the 1 cm grid
            zero = np.array([c[2] == 0 for c in cells()])
            w_far = y_of[zero & far]
            noisy = []
            for dr in draws:
                ok, r = apply_noise(tr, np.arange(len(tr)), dr, spec)
                noisy.append(np.where(ok, r, np.nan))
            noisy = np.array(noisy)
            near_err = (tr - d0)[near]
            rows.append({'half_angle_true_deg': th, 'approach_m': d,
                         'cells_far_fraction': float(far.mean()),
                         'window_half_width_yaw0_cm_grid': None if len(w_far) == 0 else float(100 * np.abs(w_far).max()),
                         'analytic_half_width_cm': float(100 * max(0., world.facts['door_half_width'] - d * math.tan(math.radians(th)))),
                         'near_echo_minus_xdist_mm': None if not near.any() else {'min': float(1e3 * near_err.min()), 'max': float(1e3 * near_err.max()), 'std': float(1e3 * near_err.std())},
                         'far_echo_m_range': None if not far.any() else [float(np.nanmin(tr[far])), float(np.nanmax(tr[far]))],
                         'single_reading_range_sigma_mm_at_d': float(1e3 * spec.sigma_m(d)),
                         'valid_fraction_noisy': float(np.mean(~np.isnan(noisy)))})
    (out / 'stationary.json').write_text(json.dumps({'facts': world.facts, 'rows': rows}, indent=1))
    print(json.dumps(rows[:3], indent=1))


# ---- ablations at one chosen design --------------------------------------------------------------------------------
def _cells_subset(y_list):
    return [c for c in cells() if round(c[0], 3) in {round(v, 3) for v in y_list}]


def score(world, spec_true, d, W, v, seeds, theta_assumed, y_list=None, **kw):
    """Grid score with a custom truth spec / cell subset; returns the same summary as grid_stats."""
    sg = s_grid()
    cs = cells() if y_list is None else _cells_subset(y_list)
    traces = np.stack([echo_trace(world, spec_true, d, y, psi, sg) for y, psi, _ in cs])
    draws = [noise_draws(k, MAX_TICKS) for k in range(seeds)]
    return grid_stats(world.facts, traces, spec_true, d, W, v, draws, theta_assumed, cell_list=cs, **kw)


def cmd_ablate(args):
    world = DoorWorld()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    d, W, v, seeds = args.d, args.W, args.v, args.seeds
    res = {'design': {'approach_m': d, 'sweep_half_width_m': W, 'speed_mps': v, 'seeds': seeds}}
    ys = [-.10, -.05, 0., .05, .10]
    # 1. cone half-angle truth and assumption mismatch
    mm = []
    for th in (15., 10., 7.5):
        for assumed in (None, 15., 10., 7.5):
            mm.append({'half_angle_true_deg': th, 'theta_assumed': 'self_calibrated' if assumed is None else assumed,
                       **score(world, spec_for(th), d, W, v, seeds, assumed)})
    res['half_angle_mismatch'] = mm
    print('mismatch done', flush=True)
    # 2. ray density: the SIM cone is 85 rays; compare a ~960-ray cone
    dens = []
    for th in (15., 7.5):
        for label, sp in (('85_rays', spec_for(th)),
                          ('961_rays', replace(spec_for(th), ring_step_deg=th / 15., ring_base_count=8))):
            dens.append({'half_angle_true_deg': th, 'cone': label, **score(world, sp, d, W, v, seeds, None, y_list=ys)})
    res['ray_density'] = dens
    print('density done', flush=True)
    # 3. timing / odometry: position stamped on a reading lags (latency), strafe gain error (scale)
    tim = []
    for th in (15., 7.5):
        for latency in (0., .06, .12, .25):
            for scale in (1.0,):
                tim.append({'half_angle_true_deg': th, 'latency_s': latency, 'strafe_scale': scale,
                            **score(world, spec_for(th), d, W, v, seeds, None, y_list=ys, latency=latency, scale=scale)})
        for scale in (.90, .97, 1.03, 1.10):
            tim.append({'half_angle_true_deg': th, 'latency_s': 0., 'strafe_scale': scale,
                        **score(world, spec_for(th), d, W, v, seeds, None, y_list=ys, scale=scale)})
    res['timing_odometry'] = tim
    print('timing done', flush=True)
    # 4. out-and-back: average the forward and the return pass (latency and strafe gain error flip sign between them)
    bi = []
    for th in (15., 7.5):
        spec = spec_for(th)
        cs = _cells_subset(ys)
        traces = np.stack([echo_trace(world, spec, d, y, psi, s_grid()) for y, psi, _ in cs])
        draws = [noise_draws(k, MAX_TICKS) for k in range(seeds)]
        for latency, scale in ((0., 1.), (.12, 1.), (.25, 1.), (0., .97), (0., 1.03), (0., .90), (0., 1.10), (.12, 1.03)):
            for mode in ('forward_only', 'out_and_back'):
                ey, epsi = [], []
                nok = ntot = 0
                for row, (y0, psi, pd) in zip(traces, cs):
                    for dr in draws:
                        ests = []
                        for rev in ((False,) if mode == 'forward_only' else (False, True)):
                            s, e, ticks = sample_sweep(np.asarray(row, float), W, v, spec.period_s, latency=latency, scale=scale, reverse=rev,
                                                       t0=(0. if not rev else 40.))
                            ok, r = apply_noise(e, ticks, dr, spec)
                            ests.append(estimate_sweep(s, ok, r, world.facts, theta_deg=None))
                        ntot += 1
                        if all(x['status'] == 'ok' and x['yaw_resolved'] for x in ests):
                            nok += 1
                            ey.append(np.mean([x['y_base_m'] for x in ests]) - y0)
                            epsi.append(np.mean([x['yaw_deg'] for x in ests]) - pd)
                bi.append({'half_angle_true_deg': th, 'latency_s': latency, 'strafe_scale': scale, 'mode': mode,
                           'resolved_rate': nok / ntot, 'y_cm': _stat(100 * np.array(ey)), 'yaw_deg': _stat(epsi),
                           'duration_s': float(2 * W / v * (1 if mode == 'forward_only' else 2))})
    res['out_and_back'] = bi
    print('out-and-back done', flush=True)
    (out / 'ablate.json').write_text(json.dumps(res, indent=1))


# ---- carry-posture occlusion (stage-probe checkpoints) ----------------------------------------------------------
PROBE_ROOT_DEFAULT = ROOT / 'outputs'


def load_probe_state(case_dir: Path, label: str = 'staged_before_submit'):
    """Rebuild the stage-probe scene of ``case_dir`` and restore its mjSTATE_INTEGRATION checkpoint (no stepping)."""
    from scripts.run_pair_stage_probes import MAP_ID as PROBE_MAP
    from scripts.zone_pair_dev_runtime import make_scene
    from sim.multi_masterpi_production import build_multi_robot_xml
    case = json.loads((case_dir / 'case.json').read_text())
    spec = {'map': case.get('map', PROBE_MAP), 'seed': case['seed'], 'goal': {case.get('target', 'B'): {'cyan': 1}},
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': list(case['beam_xyyaw'])}]}
    scene = make_scene(spec)
    model = mujoco.MjModel.from_xml_string(scene.transform(build_multi_robot_xml(None)))
    data = mujoco.MjData(model)
    z = np.load(case_dir / 'checkpoints' / f'{label}.npz')
    kind = mujoco.mjtState.mjSTATE_INTEGRATION
    state = z['mj_state_integration']
    if mujoco.mj_stateSize(model, kind) != len(state):
        raise ValueError('checkpoint state size differs from the rebuilt model')
    mujoco.mj_setState(model, data, state, kind)
    mujoco.mj_forward(model, data)
    return case, scene, model, data


def _category(model, geom, rid, load_prefix):
    body = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, int(model.geom_bodyid[geom])) or ''
    gname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(geom)) or ''
    if gname.startswith(f'{rid}__') or body.startswith(f'{rid}__'):
        return 'own_arm'
    if load_prefix and (gname.startswith(load_prefix) or body.startswith(load_prefix)):
        return 'load_beam'
    if gname.startswith(('r1__', 'r2__', 'r3__')) or body.startswith(('r1__', 'r2__', 'r3__')):
        return 'partner_robot'
    if 'divider' in gname:
        return 'door_wall'
    if 'wall' in gname:
        return 'other_wall'
    return 'other'


def cone_census(model, data, rid, spec, load_prefix):
    """Noise-free look through the shared ray cast: first echo, what it is, and what the eligible rays hit."""
    from harness.ultrasonic_model import directivity, first_echo_index, incidence_gain
    from sim.ultrasonic_range import MujocoUltrasonic
    sonar = MujocoUltrasonic(model, data, rid, seed=sensor_seed(0, rid), spec=exact_spec(spec))
    c = sonar.cast()
    i = first_echo_index(c['dist'], sonar.alpha, c['beta'], sonar.spec)
    amp = directivity(sonar.alpha, sonar.spec) * incidence_gain(c['beta'], sonar.spec)
    eligible = (c['dist'] >= 0) & (c['dist'] <= sonar.spec.max_range_m) & (amp >= sonar.spec.echo_threshold)
    cats = {}
    for k in np.flatnonzero(eligible):
        cat = _category(model, c['geom'][k], rid, load_prefix)
        cats[cat] = cats.get(cat, 0) + 1
    nearest = {}
    for k in np.flatnonzero(eligible):
        cat = _category(model, c['geom'][k], rid, load_prefix)
        nearest[cat] = min(nearest.get(cat, 9.), float(c['dist'][k]))
    base = data.xpos[sonar.chassis_id]
    R = data.xmat[sonar.chassis_id].reshape(3, 3)
    row = {'base_xy': [round(float(base[0]), 3), round(float(base[1]), 3)],
           'heading_deg': round(math.degrees(math.atan2(R[1, 0], R[0, 0])), 1),
           'first_echo_m': None if i is None else round(float(c['dist'][i]), 4),
           'first_echo_is': None if i is None else _category(model, c['geom'][i], rid, load_prefix),
           'eligible_rays': int(eligible.sum()), 'n_rays': int(len(eligible)),
           'eligible_rays_by_target': cats, 'nearest_by_target_m': {k: round(v, 3) for k, v in nearest.items()}}
    row['door_wall_rays'] = int(cats.get('door_wall', 0))
    row['door_wall_share'] = round(cats.get('door_wall', 0) / max(1, int(eligible.sum())), 3)
    return row


def pick_states(root: Path, per_leg=1):
    """Choose carry/other checkpoints from the recorded stage probes (deterministic: sorted, first match)."""
    want = []
    cases = sorted(root.glob('pair-stage-probes-*/cases/*/case.json'))
    seen = set()
    for f in cases:
        try:
            c = json.loads(f.read_text())
        except Exception:
            continue
        d = f.parent
        if not (d / 'checkpoints' / 'staged_before_submit.npz').exists() or c.get('map'):
            continue
        pol = str(c.get('pair_policy', ''))
        if not pol.startswith(('b-v6c', 'b-v6e')):
            continue
        if c.get('stage') == 'carry':
            key = ('carry', c.get('leg'), round(c['beam_xyyaw'][1], 1))
            if c.get('leg') in (0, 1, 2, 3, 6) and abs(c['beam_xyyaw'][1] - .05) < .1 and key not in seen:
                seen.add(key)
                want.append(('carry_leg%s' % c['leg'], d, 'staged_before_submit'))
        elif c.get('stage') in ('align', 'grasp_lift', 'setdown'):
            key = (c['stage'],)
            if key not in seen:
                seen.add(key)
                want.append((f"{c['stage']}_entry", d, 'staged_before_submit'))
                if (d / 'checkpoints' / 'stage_stop.npz').exists():
                    want.append((f"{c['stage']}_stop", d, 'stage_stop'))
    return want


def cmd_occlusion(args):
    root = Path(args.probe_root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, d, label in pick_states(root):
        try:
            case, scene, model, data = load_probe_state(d, label)
        except Exception as exc:                      # pragma: no cover - reported, not hidden
            rows.append({'state': name, 'case_dir': str(d), 'checkpoint': label, 'error': repr(exc)})
            continue
        load_prefix = scene.cargo[0].body if getattr(scene, 'cargo', None) else None
        beam = data.body(load_prefix) if load_prefix else None
        row = {'state': name, 'case_dir': str(d), 'checkpoint': label, 'case_id': case['case_id'],
               'sim_time_s': float(data.time),
               'beam_xyz': None if beam is None else [round(float(v), 3) for v in beam.xpos]}
        for th in (15., 7.5):
            spec = spec_for(th)
            for rid in ('r1', 'r2'):
                row[f'{rid}_half{th:g}'] = cone_census(model, data, rid, spec, load_prefix)
        rows.append(row)
        print(name, row.get('r1_half15', {}).get('first_echo_is'), row.get('r2_half15', {}).get('first_echo_is'), flush=True)
    (out / 'occlusion.json').write_text(json.dumps({'probe_root': str(root), 'states': rows}, indent=1))


# ---- side-facing sensor while passing the frame (informational; needs a formation whose front faces along the wall) ---
def cmd_side(args):
    """Robot heading +y (north) drives east THROUGH the door; the front cone reads the north post's end face.

    In the recorded side-grasp formation (experiments/2026-09-28-ultrasonic-range/side_grasp_pair_analysis.json) the
    sensors face along the wall and do not see the partner or the load. Nothing here decides the formation; it
    only asks how well the range to the post end face (0.3 m north of the door centre line) fixes ``y`` while crossing.
    """
    world = DoorWorld()
    facts = world.facts
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    xs = np.arange(-.45, .45 + 1e-9, .002)                       # crossing coordinate: sensor origin x relative to the wall plane
    v, period = args.v, .06
    rows, profile = [], {}
    draws = [noise_draws(k, 600) for k in range(args.seeds)]
    north_post_y = facts['door_center_y'] + facts['door_half_width']
    for th in (15., 7.5):
        spec = spec_for(th)
        sonar = world.sonar(spec)
        errs = []
        for y0 in (-.10, -.05, 0., .05, .10):
            for pd in (-6, -3, 0, 3, 6):
                psi = math.radians(pd)
                h = math.pi / 2 + psi
                tr = np.empty(len(xs))
                for i, x in enumerate(xs):
                    bx, by = facts['wall_plane_x'] + x - spec.face_x_m * math.cos(h), facts['door_center_y'] + y0
                    world.place(bx, by, h)
                    tr[i] = world.echo(sonar)
                if (y0, pd) == (0., 0):
                    profile[f'th{th:g}'] = {'x_rel_wall_m': xs.tolist(), 'echo_m': [None if np.isnan(e) else float(e) for e in tr]}
                n = int((xs[-1] - xs[0]) / (v * period)) + 1
                k = np.arange(n)
                idx = np.clip(np.round((k * v * period) / .002).astype(int), 0, len(xs) - 1)
                e = tr[idx]
                for dr in draws:
                    ok, r = apply_noise(e, k, dr, spec)
                    rr = np.where(ok, r, np.inf)
                    med5 = np.array([np.median(rr[max(0, i - 2):i + 3]) for i in range(len(rr))])
                    r_min = float(np.min(med5))
                    # sensor origin y = base y + face_x*sin(h) ~ y_base + face_x*cos(psi); range = post_y - origin_y
                    y_est = north_post_y - r_min - spec.face_x_m
                    errs.append((y_est - (facts['door_center_y'] + y0)))
                    rows.append({'half_angle_true_deg': th, 'y0_m': y0, 'yaw_deg': pd, 'error_cm': 100 * errs[-1]})
        e = np.array(errs)
        print(th, 'rms cm', 100 * float(np.sqrt(np.mean(e ** 2))), 'bias', 100 * float(e.mean()))
    summary = {}
    for th in (15., 7.5):
        e = np.array([r['error_cm'] for r in rows if r['half_angle_true_deg'] == th])
        summary[f'th{th:g}'] = {'rms_cm': float(np.sqrt(np.mean(e ** 2))), 'bias_cm': float(e.mean()),
                                'p95_abs_cm': float(np.percentile(np.abs(e), 95)), 'max_abs_cm': float(np.abs(e).max()), 'n': int(len(e))}
    (out / 'side_facing.json').write_text(json.dumps({'speed_mps': v, 'seeds': args.seeds, 'summary': summary,
                                                      'profile_y0_yaw0': profile, 'rows': rows}, indent=1))


# ---- error versus heading, from the stored traces of a sweep run ---------------------------------------------------
def cmd_yawbias(args):
    """Bias and scatter of ``y`` and ``yaw`` per heading error at one design, from ``sweep/echo_traces.npz`` (no new casts)."""
    z = np.load(Path(args.sweep) / 'echo_traces.npz')
    facts = DoorWorld().facts
    draws = [noise_draws(k, MAX_TICKS) for k in range(args.seeds)]
    out_rows, theta_summary = [], {}
    for th in HALF_ANGLES_DEG:
        traces = z[f'th{th}_d{args.d}']
        spec = spec_for(th)
        by_yaw, theta_err = {}, []
        for row, (y0, psi, pd) in zip(traces, cells()):
            ests, _ = run_cell(row, spec, args.W, args.v, draws, facts, None)
            for e in ests:
                if e['status'] == 'ok' and e['yaw_resolved']:
                    by_yaw.setdefault(pd, []).append(((e['y_base_m'] - y0) * 100, e['yaw_deg'] - pd))
                    theta_err.append(e['theta_deg'] - th)
        te = np.array(theta_err)
        theta_summary[f'{th:g}'] = {'mean': float(te.mean()), 'std': float(te.std()), 'p95_abs': float(np.percentile(np.abs(te), 95)), 'n': int(len(te))}
        for pd in sorted(by_yaw):
            a = np.array(by_yaw[pd])
            out_rows.append({'half_angle_true_deg': th, 'yaw_deg': pd, 'y_bias_cm': float(a[:, 0].mean()),
                             'y_std_cm': float(a[:, 0].std()), 'yaw_bias_deg': float(a[:, 1].mean()), 'n': int(len(a))})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'yawbias.json').write_text(json.dumps({'design': {'d': args.d, 'W': args.W, 'v': args.v}, 'rows': out_rows,
                                                   'self_calibrated_half_angle_error_deg': theta_summary}, indent=1))
    for th in HALF_ANGLES_DEG:
        print(th, [(r['yaw_deg'], round(r['y_bias_cm'], 2)) for r in out_rows if r['half_angle_true_deg'] == th])


# ---- manifest and report -----------------------------------------------------------------------------------------
def cmd_manifest(args):
    import subprocess
    out = Path(args.out)
    files = {str(f.relative_to(out)): {'sha256': sha256_file(f), 'bytes': f.stat().st_size}
             for f in sorted(out.rglob('*')) if f.is_file() and f.name != 'MANIFEST.json'}
    git = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain', '--', 'scripts', 'harness', 'sim'],
                                capture_output=True, text=True).stdout.strip())
    (out / 'MANIFEST.json').write_text(json.dumps({'schema': 'ugrp.door_ultrasonic_sweep.manifest.v1', 'source_git_sha': git,
                                                    'source_tree_dirty': dirty, 'physics_steps': 0,
                                                    'files': files}, indent=1))
    print(f'{len(files)} files hashed, source {git[:8]} dirty={dirty}')


def _fmt(x, nd=2):
    return '-' if x is None else f'{x:.{nd}f}'


def cmd_report(args):
    """Markdown tables from grid_results.json (and ablate.json if present) for the experiment README."""
    src = Path(args.src)
    grid = json.loads((src / 'grid_results.json').read_text())['results']
    by = {}
    for r in grid:
        by.setdefault((r['approach_m'], r['sweep_half_width_m'], r['speed_mps']), {})[r['half_angle_true_deg']] = r
    lines = []
    ok = lambda r: r['resolved_rate'] >= .95 and r['y_cm'] and r['y_cm']['rms'] <= args.y_limit_cm
    lines.append(f'## Designs meeting y RMS <= {args.y_limit_cm} cm and resolved >= 95 % for BOTH cone readings (15 / 7.5 deg)\n')
    lines.append('| approach d (m) | half width W (cm) | speed (cm/s) | readings | SIM s | y RMS 15 / 7.5 (cm) | yaw RMS 15 / 7.5 (deg) | y p95 15 / 7.5 (cm) |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for k, v in sorted(by.items()):
        if 15. in v and 7.5 in v and ok(v[15.]) and ok(v[7.5]):
            a, b = v[15.], v[7.5]
            lines.append(f"| {k[0]:.2f} | {100 * k[1]:.0f} | {100 * k[2]:.0f} | {a['n_readings']} | {a['duration_s']:.0f} | "
                         f"{_fmt(a['y_cm']['rms'])} / {_fmt(b['y_cm']['rms'])} | {_fmt(a['yaw_deg']['rms'])} / {_fmt(b['yaw_deg']['rms'])} | "
                         f"{_fmt(a['y_cm']['p95_abs'])} / {_fmt(b['y_cm']['p95_abs'])} |")
    ds_ = sorted({k[0] for k in by})
    ws_ = sorted({k[1] for k in by})
    lines.append('\n## Sweep width (v = 5 cm/s): bracketed / yaw-resolved fraction, y RMS (cm), aim RMS (cm) per approach distance\n')
    lines.append('| cone | d (m) | ' + ' | '.join(f'W={100 * w:.0f} cm' for w in ws_) + ' |')
    lines.append('|---|---|' + '---|' * len(ws_))
    for th in HALF_ANGLES_DEG:
        for d in ds_:
            cols = []
            for w in ws_:
                r = by.get((d, w, .05), {}).get(th)
                cols.append('-' if r is None else f"{r['bracket_rate']:.2f}/{r['resolved_rate']:.2f}, y {_fmt(r['y_cm'] and r['y_cm']['rms'], 1)}, aim {_fmt(r['aim_cm'] and r['aim_cm']['rms'], 2)}")
            lines.append(f'| {th:g} deg | {d:.2f} | ' + ' | '.join(cols) + ' |')
    if (.5, .4, .05) in by:
        lines.append('\n## Speed (d = 0.50 m, W = 40 cm)\n')
        lines.append('| cone | speed (cm/s) | readings | SIM s | y RMS | y noise-only std | y systematic RMS | yaw RMS (deg) | y p95 | y max |')
        lines.append('|---|---|---|---|---|---|---|---|---|---|')
        for th in HALF_ANGLES_DEG:
            for v in SPEEDS_MPS:
                r = by[(.5, .4, v)][th]
                lines.append(f"| {th:g} deg | {100 * v:.0f} | {r['n_readings']} | {r['duration_s']:.0f} | {_fmt(r['y_cm']['rms'])} | "
                             f"{_fmt(r['y_noise_std_cm'])} | {_fmt(r['y_systematic_rms_cm'])} | {_fmt(r['yaw_deg']['rms'])} | "
                             f"{_fmt(r['y_cm']['p95_abs'])} | {_fmt(r['y_cm']['max_abs'])} |")
    (src / 'report_tables.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    sw = sub.add_parser('sweep')
    sw.add_argument('--out', required=True)
    sw.add_argument('--seeds', type=int, default=8)
    sw.add_argument('--approach', default='')
    sw.add_argument('--widths', default='')
    sw.add_argument('--speeds', default='')
    sw.set_defaults(fn=cmd_sweep)
    st = sub.add_parser('stationary')
    st.add_argument('--out', required=True)
    st.add_argument('--seeds', type=int, default=20)
    st.set_defaults(fn=cmd_stationary)
    ab = sub.add_parser('ablate')
    ab.add_argument('--out', required=True)
    ab.add_argument('--d', type=float, required=True)
    ab.add_argument('--W', type=float, required=True)
    ab.add_argument('--v', type=float, required=True)
    ab.add_argument('--seeds', type=int, default=12)
    ab.set_defaults(fn=cmd_ablate)
    sd = sub.add_parser('side')
    sd.add_argument('--out', required=True)
    sd.add_argument('--v', type=float, default=.05)
    sd.add_argument('--seeds', type=int, default=8)
    sd.set_defaults(fn=cmd_side)
    yb = sub.add_parser('yawbias')
    yb.add_argument('--sweep', required=True)
    yb.add_argument('--out', required=True)
    yb.add_argument('--d', type=float, default=.5)
    yb.add_argument('--W', type=float, default=.4)
    yb.add_argument('--v', type=float, default=.05)
    yb.add_argument('--seeds', type=int, default=12)
    yb.set_defaults(fn=cmd_yawbias)
    mf = sub.add_parser('manifest')
    mf.add_argument('--out', required=True)
    mf.set_defaults(fn=cmd_manifest)
    rp = sub.add_parser('report')
    rp.add_argument('--src', required=True)
    rp.add_argument('--y-limit-cm', type=float, default=1.0)
    rp.set_defaults(fn=cmd_report)
    oc = sub.add_parser('occlusion')
    oc.add_argument('--out', required=True)
    oc.add_argument('--probe-root', default=str(PROBE_ROOT_DEFAULT))
    oc.set_defaults(fn=cmd_occlusion)
    args = p.parse_args(argv)
    return args.fn(args) or 0


if __name__ == '__main__':
    raise SystemExit(main())
