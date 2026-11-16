#!/usr/bin/env python3
"""Where do the beam and the two grippers stand when the align / grasp_lift stages end? (recorded stage-probe raws only, new physics 0)

For every align and grasp_lift stage-probe raw: at the end of the stage, the true beam y and yaw relative to the coarse order sheet
(the route the carry follows), the beam lift/tilt, and both robots' grip errors (along, lateral, yaw relative to the grip frame) and
the pair's relative yaw. GT is the analysis target only. Groups: align e2e_checkpoint (staged from recorded end-to-end states),
align teacher_grid and grasp_lift teacher_grid / tolerance_boundary (designed offsets, i.e. stress).
"""
import json, math, glob, sys
from pathlib import Path
import numpy as np
OUT = Path('/Users/changmin/projects/ugrp/outputs')
groups = {}
for root in sorted(OUT.glob('pair-stage-probes-*')):
    if not (root/'cases.jsonl').exists():
        continue
    for line in open(root/'cases.jsonl'):
        r = json.loads(line)
        if r.get('stage') not in ('align', 'grasp_lift') or r.get('host_error'):
            continue
        d = root/'cases'/r['case_id'].replace('@', '_').replace(':', '_').replace('/', '_')
        try:
            res = json.load(open(d/'result.json')); case = json.load(open(d/'case.json'))
        except Exception:
            continue
        g = res.get('gt_at_end') or res.get('gt_at_stop')
        if not g or 'grip_errors_all' not in g or 'beam_xyz' not in g:
            continue
        sheet = case['coarse_order_sheet']['beam_xyyaw']
        ge = g['grip_errors_all']
        if 'r1' not in ge or 'r2' not in ge:
            continue
        row = dict(beam_y_minus_sheet=g['beam_xyz'][1] - sheet[1], beam_x_minus_sheet=g['beam_xyz'][0] - sheet[0], beam_yaw=g['beam_yaw'],
                   r1x=ge['r1']['grip_x_err_m'], r1y=ge['r1']['grip_y_err_m'], r1yaw=ge['r1']['yaw_err_rad'],
                   r2x=ge['r2']['grip_x_err_m'], r2y=ge['r2']['grip_y_err_m'], r2yaw=ge['r2']['yaw_err_rad'], beam_world_y=g['beam_xyz'][1])
        row['rel_yaw'] = row['r2yaw'] - row['r1yaw']
        groups.setdefault((r['stage'], r['source']), []).append(row)
COLS = [('beam_world_y', 'beam world y [m]', 1), ('beam_y_minus_sheet', 'beam y - sheet y [m]', 1), ('beam_yaw', 'beam yaw [deg]', 57.2958),
        ('r1x', 'r1 grip along err [m]', 1), ('r1y', 'r1 grip lateral err [m]', 1), ('r1yaw', 'r1 yaw err [deg]', 57.2958),
        ('r2x', 'r2 grip along err [m]', 1), ('r2y', 'r2 grip lateral err [m]', 1), ('r2yaw', 'r2 yaw err [deg]', 57.2958),
        ('rel_yaw', 'r2-r1 yaw [deg]', 57.2958)]
for key, rows in sorted(groups.items()):
    print(f'== {key[0]} / {key[1]}  n={len(rows)}')
    print('  %-26s %9s %9s %9s %9s %9s' % ('quantity', 'median', '|.| p90', '|.| p95', '|.| max', 'min..max'))
    for c, name, k in COLS:
        v = np.array([r[c] for r in rows])*k
        a = np.abs(v)
        print('  %-26s %9.4f %9.4f %9.4f %9.4f  %.4f..%.4f' % (name, np.median(v), np.percentile(a, 90), np.percentile(a, 95), a.max(), v.min(), v.max()))
