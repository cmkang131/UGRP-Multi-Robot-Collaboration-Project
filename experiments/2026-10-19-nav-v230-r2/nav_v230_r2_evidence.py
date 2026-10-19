"""C height evidence + B arrival geometry audit for nav v230-r2 (analysis only).

Inputs are the *recovered raw* artifacts of the already-run 2026-10-19 sessions
(no new run, no controller, no LLM):

* Step A sweep render frames (x=1.5/2.0/2.5/3.0, tick 0/5, r1 lane y=-2.375):
  the approved 2.4 m stop point is x=1.5 (spawn x=-0.8982 + 2.4 m).
* the 45 s dev run's `localization.json` (own-navigation reports per tick) and
  `evaluation-state.npz` (raw base qpos, eval-only) for the r1 approach and the
  r2 one-tick low-quality detection.

Outputs (written into this directory):

* ``C_HEIGHT_EVIDENCE.json`` - per-frame gate-detector geometry, the r2
  low-quality sample, per-threshold "first 3-consecutive-tick confirmation"
  rows on the recorded approach, and the ground-plane camera fit from Step A.
* ``ARRIVAL_GEOMETRY_AUDIT.json`` - the ground-plane mount fit from the recorded
  approach (184 rows) and the offline replay of both B arrival candidates.

Every number is reproducible from the frozen paths below; nothing here is a
gate result and nothing is pooled with it.
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.e2ewarp_selfnav import GpuCalibZoneDetector, GATE_GROUND_PROJECTION  # noqa: E402

ZONE_CENTER = (4.6, -2.1)
ZONE_HALF = (0.3, 0.7)
ZONE_NEAR_X = ZONE_CENTER[0] - ZONE_HALF[0]
SPAWN_X = -0.8982
STEP_A_X = (1.5, 2.0, 2.5, 3.0)
THRESHOLDS = (0.02, 0.025, 0.03, 0.04)


def fisheye_theta(radius_px):
    d = GATE_GROUND_PROJECTION['fisheye_d']
    lo, hi = 0.0, math.radians(80.0)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        t2 = mid * mid
        r = mid * (1.0 + t2 * (d[0] + t2 * (d[1] + t2 * (d[2] + t2 * d[3]))))
        if r < radius_px:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def ground_forward(u, v, height_m, pitch_down_deg):
    p = GATE_GROUND_PROJECTION
    dx = (u - p['cx_px']) / p['fx_px']
    dy = (v - p['cy_px']) / p['fy_px']
    radius = math.hypot(dx, dy)
    theta = fisheye_theta(radius) if radius > 1e-12 else 0.0
    phi = math.atan2(dy, dx) if radius > 1e-12 else 0.0
    right = math.sin(theta) * math.cos(phi)
    down = math.sin(theta) * math.sin(phi)
    forward = math.cos(theta)
    pitch = math.radians(pitch_down_deg)
    fwd = math.cos(pitch) * forward - math.sin(pitch) * down
    up = -math.sin(pitch) * forward - math.cos(pitch) * down
    if up >= -1e-9:
        return None
    return height_m * fwd / (-up)


def fit_camera(rows, distances):
    rows = np.asarray(rows, float)
    dist = np.asarray(distances, float)
    d = GATE_GROUND_PROJECTION['fisheye_d']
    grid = np.linspace(0.0, math.radians(80.0), 4001)
    t2 = grid * grid
    rr = grid * (1.0 + t2 * (d[0] + t2 * (d[1] + t2 * (d[2] + t2 * d[3]))))

    dy = (rows - GATE_GROUND_PROJECTION['cy_px']) / GATE_GROUND_PROJECTION['fy_px']
    theta = np.interp(np.abs(dy), rr, grid)
    down = np.sign(dy) * np.sin(theta)
    forward = np.cos(theta)

    def resid(p):
        pr = math.radians(p[1])
        fwd = math.cos(pr) * forward - math.sin(pr) * down
        up = -math.sin(pr) * forward - math.cos(pr) * down
        with np.errstate(divide='ignore', invalid='ignore'):
            value = p[0] * fwd / (-up) + p[2]
        return np.where(up < -1e-9, value, np.nan) - dist

    best = None
    for h0 in np.arange(0.15, 0.56, 0.02):
        for p0 in np.arange(5.0, 45.0, 1.0):
            p = np.asarray([h0, p0, 0.0])
            for _ in range(40):
                r = resid(p)
                if not np.all(np.isfinite(r)):
                    break
                jac = np.empty((len(rows), 3))
                for k in range(3):
                    step = (1e-4, 1e-3, 1e-4)[k]
                    q = p.copy(); q[k] += step
                    jac[:, k] = (resid(q) - r) / step
                p = p + np.linalg.lstsq(jac, -r, rcond=None)[0]
                if np.max(np.abs(np.linalg.lstsq(jac, -r, rcond=None)[0])) < 1e-11:
                    break
            r = resid(p)
            if not np.all(np.isfinite(r)):
                continue
            sse = float(np.sum(r * r))
            if best is None or sse < best[0]:
                best = (sse, p.copy(), r)
    sse, p, r = best
    return dict(height_m=round(float(p[0]), 5), pitch_down_deg=round(float(p[1]), 4),
                camera_x_offset_m=round(float(p[2]), 5),
                rms_m=round(float(math.sqrt(sse / len(rows))), 5),
                max_abs_m=round(float(np.max(np.abs(r))), 5), n=int(len(rows)))


def step_a_rows(sweep, detector):
    measure = json.loads((sweep / 'measure.json').read_text())
    out = []
    for x in STEP_A_X:
        for tick in (0, 5):
            name = f'door_x{x:.1f}-t{tick:03d}'
            raw = (sweep / measure['frames'][name]['path']).read_bytes()
            img = np.asarray(Image.open(io.BytesIO(raw)).convert('RGB'))
            hits = detector(raw)
            row = dict(frame=name, x_m=x, tick=tick,
                       spawn_forward_m=round(x - SPAWN_X, 4), detections=len(hits))
            if hits:
                h = hits[0]
                row.update(bbox=list(h['bbox']), pixels=int(h['pixels']),
                           height_norm=round(h['height_norm'], 6),
                           width_norm=round(h['width_norm'], 6),
                           bottom_norm=round(h['bottom_norm'], 6),
                           solidity=round(h['solidity'], 6),
                           spans_center_x=bool(h['spans_center_x']),
                           touches_top=bool(h['touches_top']),
                           edge_distance_m=round(ZONE_NEAR_X - x, 4))
            out.append(row)
    return out


def recorded_rows(run):
    loc = json.loads((run / 'localization.json').read_text())
    npz = np.load(run / 'evaluation-state.npz')
    qpos = npz['qpos']
    geom = json.loads((run / 'world-00' / 'eval-geometry.json').read_text())
    adr = {r: int(v) for r, v in geom['robot_qpos_adr'].items()}
    rows = {}
    for row in loc:
        tick = int(round(row['sim_s'] * 10))
        mem = (row.get('own_navigation') or {}).get('self_centric_memory') or []
        zone = [m for m in mem if m['kind'] == 'zone_B']
        if not zone or tick >= qpos.shape[0]:
            rows.setdefault(row['robot'], []).append(None)
            continue
        item = max(zone, key=lambda m: m['last_seen_s'])
        fresh = abs(float(item['last_seen_s']) - tick / 10.0) <= 1e-6
        x, y = qpos[tick, row['world'], adr[row['robot']]:adr[row['robot']] + 2]
        rows.setdefault(row['robot'], []).append(dict(
            sim_s=round(tick / 10.0, 3), fresh=bool(fresh),
            bottom_norm=float(item['bottom_norm']), height_norm=float(item['height_norm']),
            width_norm=float(item['width_norm']), solidity=float(item['solidity']),
            bearing_deg=float(item['bearing_deg']), bbox=item.get('bbox'),
            base_xy=[round(float(x), 4), round(float(y), 4)]))
    return rows, qpos, adr


def heading(qpos, world, adr_rid, tick):
    t0, t1 = max(0, tick - 1), min(qpos.shape[0] - 1, tick + 1)
    dx = qpos[t1, world, adr_rid] - qpos[t0, world, adr_rid]
    dy = qpos[t1, world, adr_rid + 1] - qpos[t0, world, adr_rid + 1]
    return math.degrees(math.atan2(dy, dx))


def threshold_rows(series):
    """First tick at which `THRESHOLDS` values of 3 consecutive accepted hits occur."""
    out = []
    for value in THRESHOLDS:
        streak = 0
        first = None
        for row in series:
            if row is None or not row['fresh']:
                streak = 0
                continue
            if row['height_norm'] >= value:
                streak += 1
                if streak >= 3 and first is None:
                    first = row
                    break
            else:
                streak = 0
        out.append(dict(
            threshold=value,
            hits_ge=int(sum(1 for r in series if r is not None and r['fresh']
                            and r['height_norm'] >= value)),
            fresh_ticks=int(sum(1 for r in series if r is not None and r['fresh'])),
            first_confirmed_sim_s=None if first is None else first['sim_s'],
            first_confirmed_base_xy=None if first is None else first['base_xy'],
            first_confirmed_height=None if first is None else first['height_norm'],
            reachable_within_2_4m=None if first is None else
            bool(first['base_xy'][0] - SPAWN_X <= 2.4 + 1e-6)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sweep', type=Path, required=True)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out-dir', type=Path, required=True)
    a = ap.parse_args()
    detector = GpuCalibZoneDetector(profile='gpu_calib_v230',
                                    bearing_convention='positive_left')
    frames = step_a_rows(a.sweep, detector)
    heights = [r['height_norm'] for r in frames if r['detections']]
    series, qpos, adr = recorded_rows(a.run)
    r1 = [r for r in series['r1'] if r is not None and r['fresh']]
    r2 = [r for r in series['r2'] if r is not None and r['fresh']]
    # r1 approach: attach heading and the base-to-near-edge distance (eval-only)
    for row in r1:
        tick = int(round(row['sim_s'] * 10))
        row['heading_deg'] = round(heading(qpos, 0, adr['r1'], tick), 2)
        row['edge_distance_m'] = round((ZONE_NEAR_X - row['base_xy'][0])
                                       / max(1e-6, math.cos(math.radians(row['heading_deg']))), 4)
    fit_sample = [r for r in r1 if abs(r['heading_deg']) <= 6.0
                  and r['edge_distance_m'] >= 0.15 and r['solidity'] >= 0.45]
    # observed saturation of the bottom band (the occlusion boundary)
    sat = max(r['bottom_norm'] for r in r1)
    sat_rows = [r for r in r1 if r['bottom_norm'] >= sat - 1e-9]
    evidence = dict(
        schema='ugrp.e2ewarp.nav_c_height_evidence.v1', analysis_only=True,
        source=dict(step_a_sweep=str(a.sweep), recorded_run=str(a.run),
                    note='recovered raw artifacts of already-run sessions; no new run'),
        detector=dict(profile='gpu_calib_v230', band='H 110-114 / S>=100 / V 30-230',
                      min_pixels=600, bearing_convention='positive_left'),
        spawn_x_m=SPAWN_X, zone_b=dict(center_m=list(ZONE_CENTER), half_m=list(ZONE_HALF),
                                       near_edge_x_m=ZONE_NEAR_X),
        approved_stop_point=dict(x_m=1.5, spawn_forward_m=round(1.5 - SPAWN_X, 4)),
        step_a_frames=frames,
        step_a_height_norm=dict(min=min(heights), max=max(heights),
                                at_approved_stop=[r['height_norm'] for r in frames
                                                  if r['x_m'] == 1.5 and r['detections']]),
        recorded_r1_approach=dict(
            fresh_ticks=len(r1),
            height_min=min(r['height_norm'] for r in r1),
            height_max=max(r['height_norm'] for r in r1),
            height_at_1_0_1_8_m=[r['height_norm'] for r in r1
                                 if 1.0 <= r['base_xy'][0] <= 1.8],
            bottom_saturation_norm=sat,
            bottom_saturation_base_xy=list(sat_rows[0]['base_xy']),
            bottom_saturation_edge_distance_m=sat_rows[0]['edge_distance_m'],
            first_tick_ge=threshold_rows(r1)),
        recorded_r2_low_quality=[dict(sim_s=r['sim_s'], base_xy=r['base_xy'],
                                      bottom_norm=r['bottom_norm'], height_norm=r['height_norm'],
                                      width_norm=r['width_norm'], solidity=r['solidity'])
                                 for r in r2],
        camera_fit_step_a=fit_camera([r['bbox'][3] for r in frames if r['detections']],
                                     [r['edge_distance_m'] for r in frames if r['detections']]),
        camera_model=dict(source=GATE_GROUND_PROJECTION['source'],
                          intrinsics={k: GATE_GROUND_PROJECTION[k] for k in
                                      ('width', 'height', 'fx_px', 'fy_px', 'cx_px',
                                       'cy_px', 'fisheye_d')}),
    )
    audit = dict(
        schema='ugrp.e2ewarp.nav_arrival_geometry_audit.v1', analysis_only=True,
        fit_sample_n=len(fit_sample),
        camera_fit_recorded=fit_camera([r['bbox'][3] if r.get('bbox') else
                                        (r['bottom_norm'] * 480.0) for r in fit_sample],
                                       [r['edge_distance_m'] for r in fit_sample]),
        ground_distance_row_curve={str(v): round(ground_forward(320, v, 0.29983, 18.9934), 4)
                                   for v in (94, 116, 400, 430, 450, 464, 479)},
        recorded_closest_patch=None,
        odom_replay=None,
    )
    # B replays on the recorded r1 approach (design audit only)
    patch_centre_rows = [(r['bottom_norm'] - r['height_norm'] / 2.0) * 480.0 for r in r1]
    claimed = [r for r, v in zip(r1, patch_centre_rows)
               if ground_forward(320, v, 0.29983, 18.9934) is not None
               and ground_forward(320, v, 0.29983, 18.9934) + 0.0255 <= 0.25]
    audit['ground_distance_0_25_claim'] = None if not claimed else dict(
        sim_s=claimed[0]['sim_s'], base_xy=claimed[0]['base_xy'])
    audit['ground_distance_min_recorded_m'] = round(min(
        ground_forward(320, v, 0.29983, 18.9934) + 0.0255 for v in patch_centre_rows), 4)
    contact = next(r for r in r1 if r['bottom_norm'] >= 0.96)
    replays = []
    for residual in (0.25, 0.40, 0.52, 0.55, 0.68):
        travel = 0.0
        claim = None
        previous = contact['base_xy']
        for row in r1:
            if row['sim_s'] < contact['sim_s']:
                previous = row['base_xy']
                continue
            travel += math.hypot(row['base_xy'][0] - previous[0],
                                 row['base_xy'][1] - previous[1])
            previous = row['base_xy']
            if travel >= residual:
                claim = dict(sim_s=row['sim_s'], base_xy=row['base_xy'],
                             travel_m=round(travel, 3))
                break
        replays.append(dict(residual_m=residual, claim=claim,
                            inside_zone=None if claim is None else bool(
                                abs(claim['base_xy'][0] - ZONE_CENTER[0]) <= ZONE_HALF[0]
                                and abs(claim['base_xy'][1] - ZONE_CENTER[1]) <= ZONE_HALF[1])))
    audit['odom_replay'] = dict(contact_sim_s=contact['sim_s'], contact_base_xy=contact['base_xy'],
                                contact_bottom_norm=contact['bottom_norm'],
                                contact_edge_distance_m=contact['edge_distance_m'],
                                rows=replays)
    out = a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / 'C_HEIGHT_EVIDENCE.json').write_text(json.dumps(evidence, indent=1) + '\n')
    (out / 'ARRIVAL_GEOMETRY_AUDIT.json').write_text(json.dumps(audit, indent=1) + '\n')
    print(json.dumps(dict(
        step_a_heights=evidence['step_a_height_norm'],
        r2_low=evidence['recorded_r2_low_quality'],
        r1_ge=[{k: r[k] for k in ('threshold', 'first_confirmed_sim_s',
                                  'first_confirmed_base_xy', 'reachable_within_2_4m')}
               for r in evidence['recorded_r1_approach']['first_tick_ge']],
        fit_stepA=evidence['camera_fit_step_a'],
        fit_recorded=audit['camera_fit_recorded'],
        ground_min=audit['ground_distance_min_recorded_m'],
        odom=[(r['residual_m'], r['inside_zone'], r['claim']) for r in replays],
    ), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
