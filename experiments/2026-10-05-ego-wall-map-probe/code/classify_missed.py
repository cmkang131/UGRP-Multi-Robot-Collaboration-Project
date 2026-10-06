"""Why does the detector return nothing on frames where a wall is in view?  (offline, no physics)

Refs #216. **Physical simulation runs: 0.** Reads a ``score_harness.py`` run (``per_frame.csv``)
and the recorded episode; writes only under ``--output``.

For every *missed* frame (ground truth says a wall contact is in view, the detector reported no
contact on any ground-truth-visible column) this evaluates, on every ground-truth-visible column,
each gate of ``height_free_wall.detect`` **at the ground-truth contact row**. The first gate that
rejects the true contact names the column's cause; the frame's cause is the majority over its
columns. Ground truth is used only to say *where to evaluate the gates*; no gate value reaches
the detector.

Causes, in the order they are tested (a column is attributed to the first that applies):

  sliver     the contact is within ``band_px`` rows of the image top, so the band window above it does
             not fit in the frame: the detector cannot test the contact at all
  horizon    ``above_is_vertical`` fails: the uniform run above the contact does not reach the horizon
             row (``horizon < 0`` means the horizon is above the image; no run can reach it)
  contrast   luminance/chroma step across the contact < ``min_contrast_below``
  band_std   the band above the contact is not uniform (std > ``max_band_std``)
  range      the contact is outside [min_range_m, max_range_m]
  self_mask  the contact is at or below the carried-object mask
  other      every gate passes at the true row: the contact was lost to candidate selection
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import height_free_wall as hfw  # noqa: E402
import wall_probe as wp  # noqa: E402
import score_harness as sh  # noqa: E402
import true_camera as tc  # noqa: E402

ORDER = ('sliver', 'horizon', 'contrast', 'band_std', 'range', 'self_mask', 'other')


def gate_values(und, cm, rows_int, params):
    """Detector gate quantities at integer row ``rows_int[j]`` of every column (NaN where invalid)."""
    p = {**hfw.PARAMS, **params}
    cols = np.asarray(cm.columns, int)
    n_c = len(cols)
    strips = hfw.ColumnStrips(und, cols, int(p['strip_half_px']))
    band_px, w = int(p['band_px']), int(p['window_px'])
    m = int(math.ceil(float(p['edge_margin_px'])))
    vb = np.asarray(rows_int, int)[None, :]
    band = strips.window(vb - band_px, vb - m)
    below = strips.window(vb + 1, vb + 1 + w)
    contrast = np.hypot(band[0] - below[0], band[1] - below[1])[0]
    std = np.sqrt(band[2])[0]
    run_top = hfw.surface_run_top(strips, float(p['run_edge_tol']))
    above = run_top[np.clip(vb - 1, 0, hfw.HEIGHT - 1)[0], np.arange(n_c)]
    horizon = hfw.horizon_rows(cm)
    t = cm.t_of_row(np.asarray(rows_int, float))
    rng, _ = cm.range_bearing(np.where(np.isfinite(t), t, 0.))
    return contrast, std, above, horizon, rng


def attribute(row, contrast, std, above, horizon, rng, self_top, p):
    """Cause name for one ground-truth-visible column."""
    if row < int(p['band_px']):
        return 'sliver'
    if not above <= horizon:
        return 'horizon'
    if not contrast >= p['min_contrast_below']:
        return 'contrast'
    if not std <= p['max_band_std']:
        return 'band_std'
    if not (p['min_range_m'] <= rng <= p['max_range_m']):
        return 'range'
    if not row <= self_top - int(p['self_margin_px']) - 1:
        return 'self_mask'
    return 'other'


def run(args):
    ep = Path(args.episode)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    static_map = json.loads((ep/'inputs'/'static_map.json').read_text())
    rects = wp.wall_rects(static_map)
    frames, _ = wp.resolve_frames(ep, args.robot)
    cam = tc.TrueCamera(ep, args.robot)
    cols = mp.column_positions(wp.FROZEN_DETECTOR['columns'], wp.FROZEN_DETECTOR['strip_half_px'])
    params = json.loads(args.params) if args.params else {}
    p = {**hfw.PARAMS, **params}

    per = list(csv.DictReader(open(args.per_frame)))
    tag = args.variant
    missed = [r for r in per if r['visible_frame'] == 'True' and int(r[f'{tag}_contacts_on_visible']) == 0]

    rows_out, by_cause = [], Counter()
    examples = defaultdict(list)
    for r in missed:
        idx = int(r['frame_index']) - 1
        servo = {int(k): int(v) for k, v in frames[idx]['commanded_servo'].items()}
        loaded = wp.loaded_for(servo, args.load_rule)
        und = mp.undistort(cv2.imread(str(ep/frames[idx]['path']), cv2.IMREAD_COLOR))
        cm = mp.column_model(servo, mp.elevation_bias(wp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo), cols)
        gt_cm, gt_pose = cam.column_model(idx, cols)
        vis, gt_row, gt_rng, _ = sh.ground_truth(gt_cm, rects, sh.world_trace(gt_cm, gt_pose), args.max_range_m)
        if not vis.any():
            continue
        row_i = np.where(vis, np.round(gt_row), 0).astype(int)
        contrast, std, above, horizon, rng = gate_values(und, cm, row_i, p)
        self_top = (hfw.self_top_mask(und, cm, loaded=loaded) if tag == 'mask_on'
                    else np.full(len(cols), hfw.HEIGHT, int))
        causes = Counter(attribute(row_i[j], contrast[j], std[j], above[j], horizon[j], rng[j], self_top[j], p)
                         for j in np.flatnonzero(vis))
        primary = max(ORDER, key=lambda c: (causes.get(c, 0), -ORDER.index(c)))
        by_cause[primary] += 1
        if len(examples[primary]) < 3:
            examples[primary].append(str(ep/frames[idx]['path']))
        rows_out.append({
            'frame_index': int(r['frame_index']), 's1': servo.get(1, 0), 's3': servo.get(3, 0),
            'visible_cols': int(vis.sum()), 'primary_cause': primary,
            'gt_row_med': float(np.median(gt_row[vis])), 'horizon_row_med': float(np.median(horizon[vis])),
            'contrast_med': float(np.median(contrast[vis])), 'band_std_med': float(np.median(std[vis])),
            **{f'cols_{c}': int(causes.get(c, 0)) for c in ORDER}})

    with open(out/'missed_frames.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)
    summary = {
        'per_frame': str(args.per_frame), 'variant': tag, 'missed_frames': len(rows_out),
        'primary_cause_frames': {c: by_cause.get(c, 0) for c in ORDER},
        'column_cause_totals': {c: int(sum(r[f'cols_{c}'] for r in rows_out)) for c in ORDER},
        'example_frames': dict(examples), 'gate_params': {k: p[k] for k in (
            'band_px', 'edge_margin_px', 'window_px', 'min_contrast_below', 'max_band_std',
            'min_range_m', 'max_range_m', 'self_margin_px', 'run_edge_tol')},
        'note': 'gates evaluated at the ground-truth contact row of every ground-truth-visible column',
    }
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--per-frame', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--variant', default='mask_off', choices=('mask_off', 'mask_on'))
    ap.add_argument('--params', default='', help='JSON overrides of height_free_wall.PARAMS (same as the scored run)')
    ap.add_argument('--max-range-m', type=float, default=6.)
    ap.add_argument('--load-rule', choices=wp.LOAD_RULES, default=wp.LOAD_RULE_DEFAULT,
                    help='must match the scored run: s3 = servo[3] >= 900 (default), gripper = commanded gripper closed')
    run(ap.parse_args())
