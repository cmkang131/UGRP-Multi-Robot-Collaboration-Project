#!/usr/bin/env python3
"""Read-only analysis of a visgoal run: arrival geometry and search/FOV coverage.

This script never feeds control.  It reads the raw trace, eval-only pose cells
and self-camera frames of a completed run and produces two tables:

* false arrivals -- where the base and the remembered paint point were at the
  declaring tick, and the signed distance of each to the zone-B rectangle;
* cap_end / no-colour -- commanded rotation, yaw-bin coverage, whether the
  eval-only zone geometry entered the horizontal camera FOV, and an offline
  paint-band check (H 99-125, V>=30, S>=110) on sampled in-FOV frames.

Truth is used only in these analysis cells, never in a control path.

Usage:
  python3 scripts/visgoal_arrival_analysis.py <run_dir> --output <analysis2.json>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

X0, X1, Y0, Y1 = 4.3, 4.9, -2.8, -1.4
HALF_HFOV_RAD = math.radians(27.3)  # CAMERA_PINHOLE_HFOV ~= 54.5 deg
HUE_LO, HUE_HI, V_MIN, S_MIN = 99, 125, 30, 110


def margin(x, y):
    """Signed distance to zone B: positive inside, negative outside (m)."""
    return min(x - X0, X1 - x, y - Y0, Y1 - y)


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def load_episode(ep_dir):
    ep = json.loads((ep_dir / 'episode.json').read_text())
    trace = [json.loads(line) for line in (ep_dir / 'trace.jsonl').read_text().splitlines()
             if line.strip()]
    frames = json.loads((ep_dir / 'eval-only.json').read_text())['frames']
    return ep, trace, frames


def declared_geometry(ep_dir):
    ep, trace, frames = load_episode(ep_dir)
    pose = {f['frame_id']: f for f in frames}
    rows = [r for r in trace if (r.get('action') or {}).get('arrived')]
    if not rows:
        return None
    r = rows[0]
    p = pose[r['frame_id']]['pose']
    mem = [m for m in (r.get('memory') or []) if m.get('id') == 'm1']
    if not mem:
        return dict(episode=ep['episode'], declared_t=r['t'],
                    base_pose=[round(v, 4) for v in p],
                    base_margin_m=round(margin(p[0], p[1]), 4),
                    memory=None)
    m = mem[0]
    rx, ry = m['relative_xy_m']
    wx = p[0] + rx * math.cos(p[2]) - ry * math.sin(p[2])
    wy = p[1] + rx * math.sin(p[2]) + ry * math.cos(p[2])
    paint = r.get('paint') or {}
    return dict(
        episode=ep['episode'],
        declared_t=r['t'],
        base_pose=[round(v, 4) for v in p],
        base_margin_m=round(margin(p[0], p[1]), 4),
        memory_range_m=round(float(math.hypot(rx, ry)), 4),
        memory_point_world=[round(wx, 4), round(wy, 4)],
        memory_margin_m=round(margin(wx, wy), 4),
        memory_radius95_m=round(float(m.get('radius95_m', float('nan'))), 4),
        nearest_visible_paint_m=round(float(paint.get('nearest_range_m', -1)), 4),
        paint_median_relative_xy=paint.get('relative_xy_m'),
        lower_centre_pixels=int(paint.get('lower_centre_pixels', 0)))


def in_fov(pose, half=HALF_HFOV_RAD):
    x, y, yaw = pose
    nx, ny = min(max(x, X0), X1), min(max(y, Y0), Y1)
    dx, dy = nx - x, ny - y
    rng = math.hypot(dx, dy)
    bearing = wrap(math.atan2(dy, dx) - yaw) if rng > 1e-9 else 0.
    return abs(bearing) <= half, rng


def offline_paint(frame_path):
    bgr = cv2.imread(str(frame_path))
    if bgr is None:
        return None
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    band = (h >= HUE_LO) & (h <= HUE_HI) & (v >= V_MIN)
    paint = band & (s >= S_MIN)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(paint.astype(np.uint8), 8)
    largest = int(stats[1:, cv2.CC_STAT_AREA].max()) if n > 1 else 0
    return dict(band_pixels=int(band.sum()), paint_pixels=int(paint.sum()),
                largest_component_px=largest)


def cap_end_row(ep_dir, sample=16):
    ep, trace, frames = load_episode(ep_dir)
    yaw_bins = sorted({int(math.floor(((f['pose'][2] + math.pi) % (2 * math.pi))
                                     / (math.pi / 6))) for f in frames})
    fov_any = fov_close = 0
    in_fov_frames = []
    min_range = float('inf')
    for f in frames:
        hit, rng = in_fov(f['pose'])
        min_range = min(min_range, rng)
        if hit:
            fov_any += 1
            if rng <= 3.5:
                fov_close += 1
                if f.get('frame_id') is not None:
                    in_fov_frames.append(f['frame_id'])
    stages = []
    stage, t0 = None, None
    for r in trace:
        if r['stage'] != stage:
            if stage is not None:
                stages.append([stage, round(t0, 1), round(r['t'], 1)])
            stage, t0 = r['stage'], r['t']
    stages.append([stage, round(t0, 1), round(trace[-1]['t'], 1)])
    # Evenly sample the frames whose GT nearest point was inside the wedge.
    if in_fov_frames:
        idx = np.linspace(0, len(in_fov_frames) - 1,
                          min(sample, len(in_fov_frames))).astype(int)
        picks = [in_fov_frames[i] for i in idx]
    else:
        picks = []
    trace_by_frame = {r['frame_id']: r for r in trace}
    samples = []
    for fid in picks:
        row = trace_by_frame.get(fid, {})
        paint = row.get('paint') or {}
        frame_path = ep_dir / 'frames' / f'{fid:05d}.jpg'
        off = offline_paint(frame_path) if frame_path.is_file() else None
        samples.append(dict(
            frame_id=fid, t=row.get('t'),
            trace_paint_pixels=int(paint.get('pixels', 0)),
            trace_paint_reason=paint.get('reason'),
            offline=off))
    return dict(
        episode=ep['episode'], status=ep.get('status'),
        rotation_cmd_rad=round(float(ep.get('rotation_cmd_rad') or 0.), 3),
        yaw_bins_visited=len(yaw_bins), yaw_bins=yaw_bins,
        max_x=round(max(f['pose'][0] for f in frames), 3),
        reached_x_gt_1p2=any(f['pose'][0] > 1.2 for f in frames),
        min_zone_range_m=round(min_range, 3),
        fov_any_ticks=fov_any, fov_within_3p5_ticks=fov_close,
        fov_within_3p5_share=round(fov_close / len(frames), 3),
        final_pose_eval_only=ep.get('final_pose_eval_only'),
        stages=stages, samples=samples)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir')
    ap.add_argument('--output', required=True)
    a = ap.parse_args()
    run = Path(a.run_dir)
    ep_dirs = sorted((run / 'episodes').glob('e[0-9]*'))
    declared = [d for d in (declared_geometry(p) for p in ep_dirs) if d]
    # False arrivals only: declared, but the eval-only verdict (analysis cell)
    # says the base was not inside zone B.
    false_ids = {json.loads((d / 'episode.json').read_text())['episode']
                 for d in ep_dirs
                 if json.loads((d / 'episode.json').read_text()).get('arrived_declared')
                 and json.loads((d / 'episode.json').read_text())
                 .get('arrival_verdict_gt_inside_zone_B') is False}
    declared = [d for d in declared if d['episode'] in false_ids]
    cap = [cap_end_row(d) for d in ep_dirs
           if json.loads((d / 'episode.json').read_text()).get('status') == 'cap_end'
           and not json.loads((d / 'episode.json').read_text()).get('colour_seen')]
    out = dict(schema='ugrp.visgoal.arrival_analysis.v1', run=str(run),
               scope='read-only; GT used only in analysis cells, never in control',
               declared_arrivals=declared, cap_end_no_colour=cap)
    Path(a.output).write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(dict(declared_n=len(declared), cap_end_no_colour_n=len(cap)),
                     indent=1))


if __name__ == '__main__':
    raise SystemExit(main())
