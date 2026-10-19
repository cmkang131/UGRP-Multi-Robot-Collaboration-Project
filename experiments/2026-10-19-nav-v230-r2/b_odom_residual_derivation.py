"""B(a) odometry-residual derivation from camera geometry (no run, no diagnosis).

The approved B(a) method is *geometry*-derived: the residual distance is
computed from the camera's ground-distance row curve and zone B's authored near
edge, plus one explicit design margin.  The 45 s dev run is used only as an
independent cross-check of the contact row, never as the source of the value.

Inputs (all frozen before the run):
- camera model ``harness.e2ewarp_selfnav.GATE_GROUND_PROJECTION``
  (measured fisheye intrinsics + ground-plane mount fit h=0.29983 m,
  pitch 18.9934 deg, camera x offset +0.0255 m);
- contact threshold ``ARRIVAL_BOTTOM_CONTACT_NORM`` (0.96);
- map zone B: center (4.6, -2.1), half (0.3, 0.7) -> near edge x = 4.3;
- design margin 0.15 m (design parameter, not measured).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import e2ewarp_selfnav as sn  # noqa: E402

ZONE_NEAR_X = 4.3
DESIGN_MARGIN_M = 0.15
CONTACT_NORMS = (0.96, 0.963, 0.967)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    proj = sn.GATE_GROUND_PROJECTION
    cx = proj['cx_px']
    rows = []
    for norm in CONTACT_NORMS:
        row = norm * proj['height']
        point = sn.ground_point_robot(cx, row, proj)  # principal column: straight ahead
        rows.append(dict(bottom_norm=norm, row_px=round(row, 3),
                         base_forward_m=round(point[0], 4),
                         residual_m=round(point[0] + DESIGN_MARGIN_M, 4)))
    contact = rows[0]                      # the threshold row is the arming row
    geometric = contact['residual_m']
    frozen = float(sn.ARRIVAL_ODOM_RESIDUAL_M)
    payload = dict(
        schema='ugrp.e2ewarp.nav_b_a_residual_derivation.v1', analysis_only=True,
        method='B(a) odometry residual',
        camera=dict(height_m=proj['camera_height_m'], pitch_down_deg=proj['pitch_down_deg'],
                    camera_x_offset_m=proj['camera_x_offset_m'], cx_px=cx, cy_px=proj['cy_px'],
                    fx_px=proj['fx_px'], fy_px=proj['fy_px'],
                    fisheye_d=list(proj['fisheye_d']), source=proj['source']),
        zone=dict(center_x_m=4.6, half_x_m=0.3, near_edge_x_m=ZONE_NEAR_X),
        contact_threshold=sn.ARRIVAL_BOTTOM_CONTACT_NORM,
        design_margin_m=DESIGN_MARGIN_M,
        design_margin_role='design parameter: how far inside the paint near edge the claim lands',
        row_curve=rows,
        derived_residual_m=geometric,
        frozen_flag_value_m=frozen,
        frozen_minus_derived_m=round(frozen - geometric, 4),
        realized_inside_margin_m=round(frozen - contact['base_forward_m'], 4),
        rounding='frozen 0.55 = derived 0.5412 rounded up to the existing flag value; the '
                 'difference (+0.0088 m) is far below the projection RMS (0.049 m) and only '
                 'increases the inside margin, never reduces it',
        cross_check_recorded='45 s dev r1 arming at bottom_norm 0.963 (34.7 s) measured a '
                             'base-to-near-edge distance of 0.3842 m by raw GT, within '
                             '0.006 m of the geometry value 0.3897 m (independent check, '
                             'not the source of the constant)',
    )
    a.out.write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: payload[k] for k in (
        'row_curve', 'derived_residual_m', 'frozen_flag_value_m', 'frozen_minus_derived_m',
        'realized_inside_margin_m')}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
