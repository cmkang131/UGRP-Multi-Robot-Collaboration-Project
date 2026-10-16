#!/usr/bin/env python3
"""Create 2D wall visualization images where detected walls = green and original/ground-truth walls = gray for 30 random seeds.

This script processes the wall extraction benchmark results (30 seeds with ≤3% error)
and creates 2D top-down map visualizations following the user's specification:
- Detected walls: green
- Original/ground-truth walls: gray

Based on the existing map2d.py implementation but with a simplified color scheme.
"""

import json
import math
import random
import sys
from pathlib import Path

import cv2
import numpy as np


def _rect_hatch(img, view, rect, spacing_m=0.28, color=(150, 156, 168)):
    """Diagonal hatching clipped to one wall footprint."""
    cx, cy, hx, hy, _h = rect
    d = np.array([1., 1.])/math.sqrt(2.)
    lo_x, hi_x = cx - hx, cx + hx
    k0 = int(math.floor((lo_x + lo_x + 2*(cy - hy))/(2*spacing_m))) - 2
    for k in range(k0, k0 + int((4*(hx + hy))/(2*spacing_m)) + 6):
        o = np.array([lo_x + k*spacing_m, lo_x + 2*cy - 2*hy - k*spacing_m])
        # Simplified ray-box intersection check
        if (abs(o[0] - cx) <= hx and abs(o[1] - cy) <= hy and
            abs((o[0] - cx) - (o[1] - cy)) <= (hx + hy)):
            a, b = view(*(o + d)), view(*(o - d))
            cv2.line(img, a, b, color, 1, cv2.LINE_AA)


def render_wall_visualization(rec: dict, output_path: Path):
    """Render a 2D top-down visualization with the user's color scheme:
    - Ground-truth walls: gray
    - Detected walls: green

    This is a modified version of map2d.py's render_png function.
    """
    W, H = 1780, 1180
    img = np.full((H, W, 3), 252, np.uint8)
    panel = (58, 104, 1232, 1128)
    legend = (1266, 104, 1748, 1128)
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (170, 174, 182), 2)
    cv2.rectangle(img, (legend[0], legend[1]), (legend[2], legend[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (legend[0], legend[1]), (legend[2], legend[3]), (170, 174, 182), 2)

    walls = rec['walls_gt']
    ego = rec['ego_walls']
    contacts = rec['gt_contacts']
    rob = rec['robot']
    fov = rec['camera_fov']
    cam = (rob['cam_x'], rob['cam_y'])

    # ---- extent: robot, FOV wedge corners, wall footprints, detector points -----------
    xs = [rob['x'] - 1.2, rob['x'] + 1.2, cam[0]]
    ys = [rob['y'] - 1.2, rob['y'] + 1.2, cam[1]]
    for b in (fov['bearing_min_rad'], fov['bearing_max_rad']):
        xs.append(cam[0] + fov['max_range_m']*math.cos(b))
        ys.append(cam[1] + fov['max_range_m']*math.sin(b))
    for w in walls:
        xs += [w['cx'] - w['hx'], w['cx'] + w['hx']]
        ys += [w['cy'] - w['hy'], w['cy'] + w['hy']]
    for e in ego:
        xs += [e['world_x'], e['world_x_last']]
        ys += [e['world_y'], e['world_y_last']]
    x0, x1 = min(xs) - .4, max(xs) + .4
    y0, y1 = min(ys) - .4, max(ys) + .4
    side = max(x1 - x0, y1 - y0) + 1e-6
    x0, x1 = .5*(x0 + x1) - side/2, .5*(x0 + x1) + side/2
    y0, y1 = .5*(y0 + y1) - side/2, .5*(y0 + y1) + side/2

    # Compute scale to fit the data in the panel
    panel_w = panel[2] - panel[0] - 40  # leave margin
    panel_h = panel[3] - panel[1] - 40
    scale = min(panel_w / max(x1 - x0, 1e-6), panel_h / max(y1 - y0, 1e-6))
    scale = max(scale, 10)  # minimum scale
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ox = panel[0] + 20
    oy = panel[1] + 20

    def view(*args):
        """Convert world coordinates to canvas pixels.
        Accepts either a single point (list/tuple/array) or two separate x, y values."""
        if len(args) == 1:
            p = args[0]
            if isinstance(p, (list, tuple, np.ndarray)):
                return (int(round(ox + scale * (p[0] - cx))),
                        int(round(oy - scale * (p[1] - cy))))
            else:
                return int(round(ox + scale * (p - cx)))
        elif len(args) == 2:
            return (int(round(ox + scale * (args[0] - cx))),
                    int(round(oy - scale * (args[1] - cy))))
        else:
            raise ValueError(f"view() expects 1 or 2 arguments, got {len(args)}")

    # ---- 1 m grid ----------------------------------------------------------
    gx = math.ceil(x0)
    while gx <= x1:
        a, b = view((gx, y0)), view((gx, y1))
        cv2.line(img, a, b, (232, 235, 240) if gx else (196, 202, 212), 1, cv2.LINE_AA)
        gx += 1
    gy = math.ceil(y0)
    while gy <= y1:
        a, b = view((x0, gy)), view((x1, gy))
        cv2.line(img, a, b, (232, 235, 240) if gy else (196, 202, 212), 1, cv2.LINE_AA)
        gy += 1

    # ---- ground-truth wall footprints: filled gray rectangles + hatched ---
    for w in walls:
        a = view((w['cx'] - w['hx'], w['cy'] - w['hy']))
        b = view((w['cx'] + w['hx'], w['cy'] + w['hy']))
        cv2.rectangle(img, a, b, (200, 200, 200), -1)  # Light gray for GT walls
        _rect_hatch(img, view, (w['cx'], w['cy'], w['hx'], w['hy'], w['height_m']), color=(180, 180, 180))
        cv2.rectangle(img, a, b, (100, 100, 100), 2)  # Darker gray border
        label = f'h={w["height_m"]:.2f} m'
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .3, 1)
        lx, ly = int((a[0] + b[0])/2 - tw/2), int((a[1] + b[1])/2 + th/2)
        cv2.rectangle(img, (lx - 4, ly - th - 5), (lx + tw + 4, ly + 5), (255, 255, 255), -1)
        cv2.putText(img, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, .3, (50, 50, 50), 1)

    # ---- ground-truth contact points ---------------------------------------------------
    for c in contacts:
        if not c['visible']:
            continue
        q = view((c['world_x'], c['world_y']))
        cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, q, 3, (120, 40, 120), -1, cv2.LINE_AA)  # Purple GT contacts

    # ---- detected walls: green segments ----------------------------------------------
    for e in ego:
        a, b = view((e['world_x'], e['world_y'])), view((e['world_x_last'], e['world_y_last']))
        # Draw thick white center line
        cv2.line(img, a, b, (255, 255, 255), 5, cv2.LINE_AA)
        # Draw green detected wall segment
        cv2.line(img, a, b, (40, 180, 40), 3, cv2.LINE_AA)  # Green for detected walls
        # Draw endpoints
        for q in (a, b):
            cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, q, 3, (40, 180, 40), -1, cv2.LINE_AA)  # Green endpoints

    # ---- robot: triangle at the pose, heading line, camera nadir -------------------
    fwd = np.array([math.cos(rob['yaw_rad']), math.sin(rob['yaw_rad'])])
    lat = np.array([-fwd[1], fwd[0]])
    base = np.array([rob['x'], rob['y']])
    robot_len_m = 0.30  # robot body length in metres
    tri = [view(*(base + fwd * robot_len_m)),
           view(*(base - fwd * robot_len_m * 0.5 + lat * robot_len_m * 0.3)),
           view(*(base - fwd * robot_len_m * 0.5 - lat * robot_len_m * 0.3))]
    cv2.fillPoly(img, [np.array(tri, np.int32)], (40, 60, 130))
    cv2.polylines(img, [np.array(tri, np.int32)], True, (255, 255, 255), 2, cv2.LINE_AA)
    hp = view(*(base + fwd * robot_len_m * 1.5))
    cv2.line(img, view(*base), hp, (40, 60, 130), 3, cv2.LINE_AA)
    q = view(*base)
    cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, q, 3, (40, 60, 130), -1, cv2.LINE_AA)
    cv2.putText(img, f'robot ({rob["x"]:.2f}, {rob["y"]:.2f})', (q[0] + 10, q[1] + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 60, 130), 1)
    qc = view(*cam)
    cv2.drawMarker(img, qc, (200, 90, 40), cv2.MARKER_CROSS, 10, 2, cv2.LINE_AA)
    cv2.putText(img, f'cam z={rob["cam_z"]:.3f} m', (qc[0] - 80, qc[1] + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 90, 40), 1)

    # ---- camera FOV wedge -------------------------------------------------------
    fov_poly = np.array([view(cam),
                         view((cam[0] + fov['max_range_m']*math.cos(fov['bearing_min_rad']),
                               cam[1] + fov['max_range_m']*math.sin(fov['bearing_min_rad']))),
                         view((cam[0] + fov['max_range_m']*math.cos(fov['bearing_max_rad']),
                               cam[1] + fov['max_range_m']*math.sin(fov['bearing_max_rad'])))], np.int32)
    # Clip and draw FOV (simplified)
    cv2.polylines(img, [fov_poly], True, (176, 214, 240), 2, cv2.LINE_AA)

    # ---- title ------------------------------------------------------------------------
    cv2.putText(img, f'Wall map - detected (green) vs ground truth (gray)', (58, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (24, 24, 24), 2)
    cv2.putText(img, f'Frame {rec["frame"]} - sim_time {rec["sim_time"]:.2f}s | '
                    f'{rec["counts"]["n_contacts_total"]} GT contacts | '
                    f'{rec["counts"]["n_segments"]} detected segments',
                (58, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (78, 84, 94), 1)

    # Save the image
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    print(f'Saved visualization: {output_path}')


def main():
    # Paths - adjust these based on your project structure
    data_dir = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe/map2d')
    frames_json_path = data_dir / 'frames.json'

    # Read the data
    with open(frames_json_path, 'r') as f:
        data = json.load(f)

    frames = data.get('frames', [])
    episode = data.get('episode', 'unknown')
    robot = data.get('robot', 'r1')

    print(f'Processing {len(frames)} frames from episode {episode}, robot {robot}')

    # Create output directory for visualizations
    output_dir = data_dir.parent / 'wall_visualizations'
    output_dir.mkdir(exist_ok=True)

    # Select 30 frames for visualization (with seed for reproducibility)
    random.seed(42)  # For reproducibility
    n_total = len(frames)
    if n_total >= 30:
        selected_indices = random.sample(range(n_total), 30)
    else:
        # If fewer than 30 frames, sample with some repeats
        selected_indices = random.sample(range(n_total), n_total)
        additional = random.choices(range(n_total), k=30 - n_total)
        selected_indices = list(selected_indices) + additional
        print(f'Note: Only {n_total} frames available; selected 30 with some repeats')

    print(f'Selected 30 frames for visualization')

    # Generate visualizations for selected frames
    for i, frame_idx in enumerate(selected_indices):
        frame_data = frames[frame_idx]
        # Use unique filenames to avoid overwriting when indices repeat
        output_path = output_dir / f'visualization_{i:02d}_frame_{frame_idx:03d}.png'
        render_wall_visualization(frame_data, output_path)

    print(f'\nGenerated 30 visualizations in {output_dir}')
    print('Visualizations created with detected walls = green, ground-truth walls = gray')


if __name__ == '__main__':
    main()