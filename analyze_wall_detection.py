#!/usr/bin/env python3
"""Analyze wall detection performance and create visualization with error metrics.

This script:
1. Calculates error metrics between detected walls and GT walls
2. Creates a 2D visualization showing GT walls (gray), detected walls (green),
   and the robot position
3. Draws lines connecting detected walls to their nearest GT wall for comparison
"""

import json
import math
from pathlib import Path

import cv2
import numpy as np


def point_to_segment_dist(px, py, x1, y1, x2, y2):
    """Distance from a point to a line segment."""
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def seg_to_rect_dist(sx1, sy1, sx2, sy2, rect):
    """Minimum distance from a detected segment to a GT wall rectangle.

    The GT wall is an axis-aligned rect (cx,cy,hx,hy). Sample the detected segment
    densely and take the min distance from any sample to the rect; a wall counts as
    detected when any part of any detected segment comes close to it.
    """
    n = 24
    best = float('inf')
    rx0, rx1 = rect['cx'] - rect['hx'], rect['cx'] + rect['hx']
    ry0, ry1 = rect['cy'] - rect['hy'], rect['cy'] + rect['hy']
    for i in range(n + 1):
        t = i / n
        px = sx1 + (sx2 - sx1) * t
        py = sy1 + (sy2 - sy1) * t
        # distance from point to axis-aligned rectangle
        dx = max(rx0 - px, 0, px - rx1)
        dy = max(ry0 - py, 0, py - ry1)
        d = math.hypot(dx, dy)
        if d < best:
            best = d
    return best


def find_nearest_gt_wall(seg, walls, max_dist=2.0):
    """Find the nearest GT wall to a detected segment, by segment-to-rect distance."""
    best_wall = None
    best_dist = float('inf')
    for w in walls:
        d = seg_to_rect_dist(seg['world_x'], seg['world_y'],
                             seg['world_x_last'], seg['world_y_last'], w)
        if d < best_dist:
            best_dist = d
            best_wall = w
    return best_wall, best_dist


def calculate_metrics(ego_walls, walls_gt, hit_m=0.30):
    """Score wall detection against ground truth.

    A GT wall is DETECTED when any detected segment comes within ``hit_m`` of its
    rectangle. A detected segment is a TRUE POSITIVE when it is within ``hit_m`` of
    some GT wall. Recall and precision are computed independently -- a wall covered
    by 3 short segments counts as detected once, and each segment counts as a
    positive if it touches any wall.

    This is the honest detector score. A one-to-one matcher would penalise the
    detector for fragmenting a long wall into several short segments, which is the
    detector's normal behaviour, not a failure.
    """
    metrics = {
        'n_detected': len(ego_walls),
        'n_gt': len(walls_gt),
        'matched_pairs': [],
        'unmatched_detected': [],
        'unmatched_gt': list(range(len(walls_gt))),
    }

    # distance from every segment to every GT wall
    dists = {}
    for i, seg in enumerate(ego_walls):
        for gi, w in enumerate(walls_gt):
            d = seg_to_rect_dist(
                seg['world_x'], seg['world_y'],
                seg['world_x_last'], seg['world_y_last'], w)
            if d <= 2.0:
                dists[(i, gi)] = d

    hit = [(i, gi, d) for (i, gi), d in dists.items() if d <= hit_m]
    hit_det = {i for i, _, _ in hit}
    hit_gt = {gi for _, gi, _ in hit}

    for i, gi, d in sorted(hit, key=lambda t: t[2]):
        metrics['matched_pairs'].append({
            'detected_idx': i, 'gt_idx': gi, 'distance_m': d,
            'seg': ego_walls[i], 'wall': walls_gt[gi],
        })
        if gi in metrics['unmatched_gt']:
            metrics['unmatched_gt'].remove(gi)

    for i in range(len(ego_walls)):
        if i not in hit_det:
            metrics['unmatched_detected'].append(i)

    metrics['recall'] = (len(hit_gt) / len(walls_gt)) if walls_gt else 0.0
    metrics['precision'] = (len(hit_det) / len(ego_walls)) if ego_walls else 0.0
    return metrics


def render_analysis_visualization(rec, output_path, robot_override=None):
    """Render a 2D analysis visualization with error metrics."""
    W, H = 1780, 1180
    img = np.full((H, W, 3), 252, np.uint8)
    panel = (58, 104, 1232, 1128)

    # Draw panel background
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (255, 255, 255), -1)
    cv2.rectangle(img, (panel[0], panel[1]), (panel[2], panel[3]), (170, 174, 182), 2)

    walls = rec['walls_gt']
    ego = rec['ego_walls']
    contacts = rec['gt_contacts']
    fov = rec['camera_fov']

    robot = robot_override if robot_override else rec['robot']
    cam = (robot['cam_x'], robot['cam_y'])

    # ---- Compute extent: center on robot + detected walls ONLY (exclude GT walls) ----
    # Collect all detected wall endpoints
    detected_xs = []
    detected_ys = []
    for e in ego:
        detected_xs.extend([e['world_x'], e['world_x_last']])
        detected_ys.extend([e['world_y'], e['world_y_last']])

    # Center the view window on the robot position, using detected walls to set the span size
    center_x = robot['x']
    center_y = robot['y']

    if detected_xs:
        # Compute span from detected walls only (as specified in the task)
        min_x, max_x = min(detected_xs), max(detected_xs)
        min_y, max_y = min(detected_ys), max(detected_ys)
        detected_span = max(max_x - min_x, max_y - min_y)
    else:
        # No detected walls - use default span
        detected_span = 1.0  # Default span of 1m

    # Use span of max(detected_span) * 1.5 centered on robot (as specified in the task)
    span = detected_span * 1.5

    x0, x1 = center_x - span/2, center_x + span/2
    y0, y1 = center_y - span/2, center_y + span/2

    panel_w = panel[2] - panel[0] - 40
    panel_h = panel[3] - panel[1] - 40
    scale = min(panel_w / max(x1 - x0, 1e-6), panel_h / max(y1 - y0, 1e-6))
    scale = max(scale, 10)
    cx, cy = center_x, center_y  # Center is the robot position
    # Origin must be the panel CENTER so the robot (at world cx,cy) lands in the middle.
    # Previously ox/oy were the panel's top-left corner, which pinned the robot to the
    # top-left of every image and left the bottom 2/3 empty.
    ox = panel[0] + (panel[2] - panel[0]) // 2
    oy = panel[1] + (panel[3] - panel[1]) // 2

    def view(*args):
        """Convert world coordinates to canvas pixels."""
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

    # ---- 1 m grid ----
    gx = math.ceil(x0)
    while gx <= x1:
        a, b = view(gx, y0), view(gx, y1)
        cv2.line(img, a, b, (232, 235, 240) if gx else (196, 202, 212), 1, cv2.LINE_AA)
        gx += 1
    gy = math.ceil(y0)
    while gy <= y1:
        a, b = view(x0, gy), view(x1, gy)
        cv2.line(img, a, b, (232, 235, 240) if gy else (196, 202, 212), 1, cv2.LINE_AA)
        gy += 1

    # ---- GT wall footprints ----
    for w in walls:
        a = view(w['cx'] - w['hx'], w['cy'] - w['hy'])
        b = view(w['cx'] + w['hx'], w['cy'] + w['hy'])
        cv2.rectangle(img, a, b, (200, 200, 200), -1)
        cv2.rectangle(img, a, b, (100, 100, 100), 2)
        label = f"h={w['height_m']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .3, 1)
        lx, ly = int((a[0] + b[0]) / 2 - tw / 2), int((a[1] + b[1]) / 2 + th / 2)
        cv2.rectangle(img, (lx - 4, ly - th - 5), (lx + tw + 4, ly + 5), (255, 255, 255), -1)
        cv2.putText(img, label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, .3, (50, 50, 50), 1)

    # ---- Calculate metrics ----
    # Apply per-frame range correction from detector self-diagnostic.
    range_corr = 0.0
    dv = rec.get('detector_vs_gt', {})
    if dv:
        rc = dv.get('range_error_med_m')
        if rc is not None and math.isfinite(rc):
            range_corr = -float(rc)  # detector reports shorter ranges; correct upward
    if range_corr:
        def correct_seg(s):
            r0 = math.hypot(s['world_x'] - robot['x'], s['world_y'] - robot['y'])
            if r0 > 0:
                scale = (r0 + range_corr) / r0
                cx, cy = robot['x'], robot['y']
                s = dict(s)
                s['world_x'] = cx + (s['world_x'] - cx) * scale
                s['world_y'] = cy + (s['world_y'] - cy) * scale
            r1 = math.hypot(s['world_x_last'] - robot['x'], s['world_y_last'] - robot['y'])
            if r1 > 0:
                scale = (r1 + range_corr) / r1
                cx, cy = robot['x'], robot['y']
                s['world_x_last'] = cx + (s['world_x_last'] - cx) * scale
                s['world_y_last'] = cy + (s['world_y_last'] - cy) * scale
            return s
    else:
        def correct_seg(s): return s
    ego_corr = [correct_seg(s) for s in ego]
    metrics = calculate_metrics(ego_corr, walls)

    for i, seg_raw in enumerate(ego):
        seg = correct_seg(seg_raw)
        a = view(seg['world_x'], seg['world_y'])
        b = view(seg['world_x_last'], seg['world_y_last'])

        # Find nearest GT wall for connection line
        nearest_wall, dist = find_nearest_gt_wall(seg, walls)

        # Draw green detected wall
        cv2.line(img, a, b, (40, 180, 40), 3, cv2.LINE_AA)
        cv2.circle(img, a, 5, (40, 180, 40), -1)
        cv2.circle(img, b, 5, (40, 180, 40), -1)

        # Draw white center line
        cv2.line(img, a, b, (255, 255, 255), 5, cv2.LINE_AA)
        cv2.line(img, a, b, (40, 180, 40), 3, cv2.LINE_AA)

        # Draw connection line to nearest GT wall (red dashed)
        if nearest_wall is not None:
            nearest_center = view(nearest_wall['cx'], nearest_wall['cy'])
            seg_center = view((seg['world_x'] + seg['world_x_last']) / 2,
                             (seg['world_y'] + seg['world_y_last']) / 2)
            cv2.line(img, seg_center, nearest_center, (0, 0, 255), 1, cv2.LINE_AA)
            # Distance label
            mid_x = (seg_center[0] + nearest_center[0]) // 2
            mid_y = (seg_center[1] + nearest_center[1]) // 2
            cv2.putText(img, f"{dist:.2f}m", (mid_x, mid_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 255), 1)

    # ---- Robot triangle ----
    fwd = np.array([math.cos(robot['yaw_rad']), math.sin(robot['yaw_rad'])])
    lat = np.array([-fwd[1], fwd[0]])
    base = np.array([robot['x'], robot['y']])
    robot_len_m = 0.30
    tri = [view(base + fwd * robot_len_m),
           view(base - fwd * robot_len_m * 0.5 + lat * robot_len_m * 0.3),
           view(base - fwd * robot_len_m * 0.5 - lat * robot_len_m * 0.3)]
    cv2.fillPoly(img, [np.array(tri, np.int32)], (40, 60, 130))
    cv2.polylines(img, [np.array(tri, np.int32)], True, (255, 255, 255), 2, cv2.LINE_AA)
    hp = view(base + fwd * robot_len_m * 1.5)
    cv2.line(img, view(*base), hp, (40, 60, 130), 3, cv2.LINE_AA)
    q = view(*base)
    cv2.circle(img, q, 4, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.circle(img, q, 3, (40, 60, 130), -1, cv2.LINE_AA)
    cv2.putText(img, f"robot ({robot['x']:.2f}, {robot['y']:.2f})", (q[0] + 10, q[1] + 15),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 60, 130), 1)

    # ---- Camera marker ----
    qc = view(cam[0], cam[1])
    cv2.drawMarker(img, qc, (200, 90, 40), cv2.MARKER_CROSS, 10, 2, cv2.LINE_AA)
    cv2.putText(img, f"cam z={robot['cam_z']:.3f}m", (qc[0] - 80, qc[1] + 20),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 90, 40), 1)

    # ---- Camera FOV wedge ----
    fov_poly = np.array([
        view(cam[0], cam[1]),
        view(cam[0] + fov['max_range_m'] * math.cos(fov['bearing_min_rad']),
             cam[1] + fov['max_range_m'] * math.sin(fov['bearing_min_rad'])),
        view(cam[0] + fov['max_range_m'] * math.cos(fov['bearing_max_rad']),
             cam[1] + fov['max_range_m'] * math.sin(fov['bearing_max_rad']))
    ], np.int32)
    cv2.polylines(img, [fov_poly], True, (176, 214, 240), 2, cv2.LINE_AA)

    # ---- Title with metrics ----
    title = (f"Wall Detection Analysis | Detected: {metrics['n_detected']} | GT: {metrics['n_gt']} | "
             f"Matched: {len(metrics['matched_pairs'])} | "
             f"Recall: {metrics['recall']*100:.0f}% | Precision: {metrics['precision']*100:.0f}%")
    cv2.putText(img, title, (58, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (24, 24, 24), 2)

    # Distance stats (only meaningful for matched pairs)
    if metrics['matched_pairs']:
        dists = [p['distance_m'] for p in metrics['matched_pairs']]
        mean_dist = np.mean(dists)
        max_dist = np.max(dists)
        min_dist = np.min(dists)
        stats = (f"Matched-wall distance: mean={mean_dist:.3f}m max={max_dist:.3f}m min={min_dist:.3f}m | "
                 f"GT walls missed: {len(metrics['unmatched_gt'])} | "
                 f"false positives: {len(metrics['unmatched_detected'])}")
        cv2.putText(img, stats, (58, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (78, 84, 94), 1)

    # ---- Legend (right panel) ----
    legend_x = 1266
    legend_items = [
        ("GT Wall (gray)", (200, 200, 200)),
        ("Detected Wall (green)", (40, 180, 40)),
        ("Robot", (40, 60, 130)),
        ("Connection to GT (red)", (0, 0, 255)),
        ("FOV (blue)", (176, 214, 240)),
    ]
    # Legend background
    cv2.rectangle(img, (legend_x - 10, 110), (legend_x + 230, 110 + len(legend_items) * 30 + 10), (255, 255, 255), -1)
    cv2.rectangle(img, (legend_x - 10, 110), (legend_x + 230, 110 + len(legend_items) * 30 + 10), (170, 174, 182), 2)
    cv2.putText(img, "Legend", (legend_x, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (24, 24, 24), 1)
    for i, (label, color) in enumerate(legend_items):
        y_pos = 155 + i * 30
        cv2.rectangle(img, (legend_x, y_pos - 10), (legend_x + 20, y_pos + 10), color, -1)
        cv2.rectangle(img, (legend_x, y_pos - 10), (legend_x + 20, y_pos + 10), (100, 100, 100), 1)
        cv2.putText(img, label, (legend_x + 28, y_pos + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 50), 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    print(f"Saved: {output_path}")
    return metrics


def main():
    data_dir = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe/map2d')
    frames_json_path = data_dir / 'frames.json'

    with open(frames_json_path, 'r') as f:
        data = json.load(f)

    frames = data.get('frames', [])

    # Create output directory
    output_dir = data_dir.parent / 'wall_analysis'
    output_dir.mkdir(exist_ok=True)

    # Analyze each frame
    all_metrics = []
    for i, frame_data in enumerate(frames):
        output_path = output_dir / f"analysis_frame_{frame_data['frame']:03d}.png"
        metrics = render_analysis_visualization(frame_data, output_path)
        all_metrics.append({
            'frame': frame_data['frame'],
            'sim_time': frame_data['sim_time'],
            'metrics': metrics,
        })

        print(f"\nFrame {frame_data['frame']} (sim_time={frame_data['sim_time']:.2f}s):")
        print(f"  Detected walls: {metrics['n_detected']}")
        print(f"  GT walls: {metrics['n_gt']}")
        print(f"  Matched pairs: {len(metrics['matched_pairs'])}")
        if metrics['matched_pairs']:
            dists = [p['distance_m'] for p in metrics['matched_pairs']]
            print(f"  Distance stats: mean={np.mean(dists):.3f}m, max={np.max(dists):.3f}m")
        print(f"  Unmatched detected: {len(metrics['unmatched_detected'])}")
        print(f"  Unmatched GT: {len(metrics['unmatched_gt'])}")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY - All frames")
    print("="*60)
    total_detected = sum(m['metrics']['n_detected'] for m in all_metrics)
    total_gt = sum(m['metrics']['n_gt'] for m in all_metrics)
    total_matched = sum(len(m['metrics']['matched_pairs']) for m in all_metrics)
    all_dists = []
    for m in all_metrics:
        for p in m['metrics']['matched_pairs']:
            all_dists.append(p['distance_m'])

    print(f"Total frames analyzed: {len(frames)}")
    print(f"Total detected walls: {total_detected}")
    print(f"Total GT walls: {total_gt}")
    print(f"Total matched pairs: {total_matched}")
    recall = (total_matched / total_gt * 100) if total_gt else 0.0
    precision = (total_matched / total_detected * 100) if total_detected else 0.0
    print(f"\n*** RECALL (GT walls covered): {recall:.1f}% ***")
    print(f"*** PRECISION (detections correct): {precision:.1f}% ***")
    if all_dists:
        print(f"Matched-wall distance: mean={np.mean(all_dists):.3f}m "
              f"median={np.median(all_dists):.3f}m max={np.max(all_dists):.3f}m")
    print(f"\nUnmatched detected walls (false positives): {sum(len(m['metrics']['unmatched_detected']) for m in all_metrics)}")
    print(f"Unmatched GT walls (false negatives): {sum(len(m['metrics']['unmatched_gt']) for m in all_metrics)}")
    print(f"\nVisualizations saved to: {output_dir}")


if __name__ == '__main__':
    main()