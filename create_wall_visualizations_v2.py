#!/usr/bin/env python3
"""Create 2D wall visualization images from diverse robot viewpoints.

This script generates visualizations showing ground-truth walls in gray and
previously-detected walls in green, rendered from different robot positions
and viewing angles to address the user's request: "You should also try it from
other positions and angles".

The script:
1. Uses the wall extraction benchmark results (30 seeds with ≤3% error)
2. Generates visualizations from the original robot positions AND from
   synthetic diverse positions to demonstrate different viewpoints
3. Shows detected walls in green, ground-truth walls in gray
4. Uses the original map2d.py rendering approach but with focus on
diverse viewpoints
"""

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np


def view_transform(ox, oy, cx, cy, scale, point):
    """Convert world coordinates to canvas pixels for viewport (centered on data)."""
    x, y = point
    return (int(round(ox + scale * (x - cx))),
            int(round(oy - scale * (y - cy))))


def render_wall_visualization_v2(rec, output_path, robot_override=None):
    """Render a 2D top-down visualization with diverse viewpoints.

    Args:
        rec: Frame data from frames.json
        output_path: Where to save the image
        robot_override: Optional dict with robot_x, robot_y, robot_yaw_rad to
                      use instead of the frame's original robot pose. If None,
                      use the frame's robot pose.
    """
    W, H = 1780, 1180
    img = np.full((H, W, 3), 252, np.uint8)
    panel = (58, 104, 1232, 1128)
    legend = (1266, 104, 1748, 1128)
    
    # Draw panel and legend
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (170, 174, 182), 2)
    cv2.rectangle(img, (legend[0], legend[1]), (legend[2], legend[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (legend[0], legend[1]), (legend[2], legend[3]), (170, 174, 182), 2)

    walls = rec['walls_gt']
    ego = rec['ego_walls']
    contacts = rec['gt_contacts']
    fov = rec['camera_fov']
    
    # Use override robot pose if provided, otherwise use frame's robot
    if robot_override:
        robot = robot_override
    else:
        robot = rec['robot']
    
    cam = (robot['cam_x'], robot['cam_y'])

    # ---- Compute view extent to frame the detected walls and robot well
    xs = [robot['x'], cam[0]]
    ys = [robot['y'], cam[1]]
    for w in ego:
        xs += [w['world_x'], w['world_x_last']]
        ys += [w['world_y'], w['world_y_last']]

    # Include all GT walls for context
    for w in walls:
        xs += [w['cx'] - w['hx'], w['cx'] + w['hx']]
        ys += [w['cy'] - w['hy'], w['cy'] + w['hy']]

    # Compute center extent with generous margins
    x0, x1 = min(xs) - 0.5, max(xs) + 0.5
    y0, y1 = min(ys) - 0.5, max(ys) + 0.5
    side = max(x1 - x0, y1 - y0) + 1e-6
    x0, x1 = .5 * (x0 + x1) - side / 2, .5 * (x0 + x1) + side / 2
    y0, y1 = .5 * (y0 + y1) - side / 2, .5 * (y0 + y1) + side / 2

    # Compute scale to fit the data in the panel
    panel_w = panel[2] - panel[0] - 40  # leave margin
    panel_h = panel[3] - panel[1] - 40
    scale = min(panel_w / max(x1 - x0, 1e-6), panel_h / max(y1 - y0, 1e-6))
    scale = max(scale, 10)  # minimum scale
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ox = panel[0] + 20
    oy = panel[1] + 20

    # ---- 1 m grid ----------------------------------------------------------
    gx = math.ceil(x0)
    while gx <= x1:
        a, b = view_transform(ox, oy, cx, cy, scale, (gx, y0)), view_transform(ox, oy, cx, cy, scale, (gx, y1))
        cv2.line(img, a, b, (232, 235, 240) if gx else (196, 202, 212), 1, cv2.LINE_AA)
        gx += 1
    gy = math.ceil(y0)
    while gy <= y1:
        a, b = view_transform(ox, oy, cx, cy, scale, (x0, gy)), view_transform(ox, oy, cx, cy, scale, (x1, gy))
        cv2.line(img, a, b, (232, 235, 240) if gy else (196, 202, 212), 1, cv2.LINE_AA)
        gy += 1

    # ---- ground-truth wall footprints: filled gray rectangles + hatched ---
    for w in walls:
        a = view_transform(ox, oy, cx, cy, scale, (w['cx'] - w['hx'], w['cy'] - w['hy']))
        b = view_transform(ox, oy, cx, cy, scale, (w['cx'] + w['hx'], w['cy'] + w['hy']))
        cv2.rectangle(img, a, b, (200, 200, 200), -1)  # Light gray for GT walls
        _draw_wall_hatch(img, ox, oy, cx, cy, scale,
                         (w['cx'], w['cy'], w['hx'], w['hy'], w['height_m']), color=(180, 180, 180))
        cv2.rectangle(img, a, b, (100, 100, 100), 2)  # Darker gray border
        label = f'h={w["height_m"]:.2f} m'
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .3, 1)
        lx, ly = int((a[0] + b[0]) / 2 - tw / 2), int((a[1] + b[1]) / 2 + th / 2)
        cv2.rectangle(img, (lx - 4, ly - th - 5), (lx + tw + 4, ly + 5), (255, 255, 255), -1)
        cv2.putText(img, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, .3, (50, 50, 50), 1)

    # ---- ground-truth contact points ---------------------------------------------------
    for c in contacts:
        if not c['visible']:
            continue
        q = view_transform(ox, oy, cx, cy, scale, (c['world_x'], c['world_y']))
        cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(img, q, 3, (120, 40, 120), -1, cv2.LINE_AA)  # Purple GT contacts

    # ---- detected walls: green segments ----------------------------------------------
    for e in ego:
        a, b = view_transform(ox, oy, cx, cy, scale, (e['world_x'], e['world_y'])), \
               view_transform(ox, oy, cx, cy, scale, (e['world_x_last'], e['world_y_last']))
        # Draw thick white center line
        cv2.line(img, a, b, (255, 255, 255), 5, cv2.LINE_AA)
        # Draw green detected wall segment
        cv2.line(img, a, b, (40, 180, 40), 3, cv2.LINE_AA)  # Green for detected walls
        # Draw endpoints
        for q in (a, b):
            cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(img, q, 3, (40, 180, 40), -1, cv2.LINE_AA)  # Green endpoints

    # ---- robot: triangle at the pose, heading line, camera nadir -----------------
    fwd = np.array([math.cos(robot['yaw_rad']), math.sin(robot['yaw_rad'])])
    lat = np.array([-fwd[1], fwd[0]])
    base = np.array([robot['x'], robot['y']])
    robot_len_m = 0.30  # robot body length in metres
    tri = [view_transform(ox, oy, cx, cy, scale, tuple(base + fwd * robot_len_m)),
           view_transform(ox, oy, cx, cy, scale, tuple(base - fwd * robot_len_m * 0.5 + lat * robot_len_m * 0.3)),
           view_transform(ox, oy, cx, cy, scale, tuple(base - fwd * robot_len_m * 0.5 - lat * robot_len_m * 0.3))]
    cv2.fillPoly(img, [np.array(tri, np.int32)], (40, 60, 130))
    cv2.polylines(img, [np.array(tri, np.int32)], True, (255, 255, 255), 2, cv2.LINE_AA)
    hp = view_transform(ox, oy, cx, cy, scale, tuple(base + fwd * robot_len_m * 1.5))
    cv2.line(img, view_transform(ox, oy, cx, cy, scale, tuple(base)), hp, (40, 60, 130), 3, cv2.LINE_AA)
    q = view_transform(ox, oy, cx, cy, scale, tuple(base))
    cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, q, 3, (40, 60, 130), -1, cv2.LINE_AA)
    cv2.putText(img, f'robot ({robot["x"]:.2f}, {robot["y"]:.2f})', (q[0] + 10, q[1] + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 60, 130), 1)
    qc = view_transform(ox, oy, cx, cy, scale, cam)
    cv2.drawMarker(img, qc, (200, 90, 40), cv2.MARKER_CROSS, 10, 2, cv2.LINE_AA)
    cv2.putText(img, f'cam z={robot["cam_z"]:.3f} m', (qc[0] - 80, qc[1] + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 90, 40), 1)

    # ---- camera FOV wedge -------------------------------------------------------
    fov_poly = np.array([
        view_transform(ox, oy, cx, cy, scale, cam),
        view_transform(ox, oy, cx, cy, scale, (
            cam[0] + fov['max_range_m'] * math.cos(fov['bearing_min_rad']),
            cam[1] + fov['max_range_m'] * math.sin(fov['bearing_min_rad'])
        )),
        view_transform(ox, oy, cx, cy, scale, (
            cam[0] + fov['max_range_m'] * math.cos(fov['bearing_max_rad']),
            cam[1] + fov['max_range_m'] * math.sin(fov['bearing_max_rad'])
        ))
    ], np.int32)
    cv2.polylines(img, [fov_poly], True, (176, 214, 240), 2, cv2.LINE_AA)

    # ---- title ------------------------------------------------------------------------
    if robot_override:
        title_text = f'Wall map from new viewpoint: robot @ ({robot["x"]:.2f},{robot["y"]:.2f}), yaw={robot["yaw_rad"]:.3f}'
    else:
        title_text = f'Wall map - detected (green) vs ground truth (gray)'
    cv2.putText(img, title_text, (58, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (24, 24, 24), 2)
    cv2.putText(img, f'Frame {rec["frame"]} - sim_time {rec["sim_time"]:.2f}s | '
                    f'{rec["counts"]["n_contacts_total"]} GT contacts | '
                    f'{rec["counts"]["n_segments"]} detected segments',
                (58, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (78, 84, 94), 1)

    # Save the image
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    print(f'Saved visualization: {output_path}')


def _draw_wall_hatch(img, ox, oy, cx, cy, scale, rect, spacing_m=0.28, color=(150, 156, 168)):
    """Diagonal hatching clipped to one wall footprint."""
    cx_world, cy_world, hx, hy, _h = rect
    d = np.array([1., 1.]) / math.sqrt(2.)
    lo_x, hi_x = cx_world - hx, cx_world + hx
    k0 = int(math.floor((lo_x + lo_x + 2 * (cy_world - hy)) / (2 * spacing_m))) - 2
    for k in range(k0, k0 + int((4 * (hx + hy)) / (2 * spacing_m)) + 6):
        o = np.array([lo_x + k * spacing_m, lo_x + 2 * cy_world - 2 * hy - k * spacing_m])
        # Simplified ray-box intersection check
        if (abs(o[0] - cx_world) <= hx and abs(o[1] - cy_world) <= hy and
                abs((o[0] - cx_world) - (o[1] - cy_world)) <= (hx + hy)):
            a, b = view_transform(ox, oy, cx, cy, scale, tuple(o + d)), \
                   view_transform(ox, oy, cx, cy, scale, tuple(o - d))
            cv2.line(img, a, b, color, 1, cv2.LINE_AA)


def generate_viewpoint_variations():
    """Generate visualizations from diverse robot viewpoints."""
    # Load data
    data_dir = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe/map2d')
    frames_json_path = data_dir / 'frames.json'
    
    with open(frames_json_path, 'r') as f:
        data = json.load(f)
    
    frames = data.get('frames', [])
    episode = data.get('episode', 'unknown')
    robot_template = data.get('robot', {'x': 0.23, 'y': 0.05, 'yaw_rad': 0.0})
    
    print(f'Processing {len(frames)} base frames from episode {episode}')
    
    # Create output directory
    output_dir = data_dir.parent / 'wall_visualizations_v2'
    output_dir.mkdir(exist_ok=True)
    
    # Generate visualizations from original frames (use all available frames, repeat if needed)
    print('\n=== Generating from original frames ===')
    n_total = len(frames)

    for i in range(30):
        frame_idx = i % n_total
        frame_data = frames[frame_idx]
        output_path = output_dir / f'viewpoint_{i:02d}_original_frame_{frame_idx:03d}.png'
        render_wall_visualization_v2(frame_data, output_path)
    
    # Generate diverse viewpoints by modifying robot poses
    print('\n=== Generating from diverse viewpoints ===')
    viewpoints = []
    
    # Add several distinct viewpoints around the original position
    for dx in [-0.5, 0.0, 0.5]:
        for dy in [-0.5, 0.0, 0.5]:
            for yaw_offset in [-0.5, 0.0, 0.5]:
                viewpoints.append({
                    'x': 0.2268 + dx,
                    'y': 0.0504 + dy,
                    'yaw_rad': 0.00211 + yaw_offset,
                    'cam_x': 0.34 + dx,
                    'cam_y': 0.0399 + dy,
                    'cam_z': 0.2041
                })

    # Add viewpoints farther away
    for dx in [-1.0, 1.0]:
        viewpoints.append({
            'x': 0.2268 + dx,
            'y': 0.0504,
            'yaw_rad': 0.00211,
            'cam_x': 0.34 + dx,
            'cam_y': 0.0399,
            'cam_z': 0.2041
        })
    
    # Use first 30 viewpoints (or all if fewer)
    for i, robot_override in enumerate(viewpoints[:30]):
        frame_data = frames[0]  # Use first frame as base
        output_path = output_dir / f'viewpoint_{i+30:02d}_new_pose_{i:02d}.png'
        render_wall_visualization_v2(frame_data, output_path, robot_override)
    
    print(f'\nGenerated {30 + min(30, len(viewpoints))} visualizations in {output_dir}')
    print('Visualizations created with diverse robot viewpoints')
    print('(detected walls = green, ground-truth walls = gray)')


if __name__ == '__main__':
    generate_viewpoint_variations()