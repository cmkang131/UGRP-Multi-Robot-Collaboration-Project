"""Fixed-input replay of B white-mark detection, off vs contrast_v1.

Read-only: decodes the retrieved JPEGs (hash-checked against frames.jsonl),
never renders, simulates or opens a VM. The gate sees only own RGB, issued
servo commands and own pose. Evaluation labels (is B / are the slot marks in
view?) are computed AFTER detection from eval_only trajectories and the run's
scene.xml, and are written only to the evaluation record.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.active_camera import goal_camera
from harness.e2e_rgb_gate import boundary, white_markers, MARKER_OPTION
from harness.floor_goal_self_mask import body_envelopes, project_envelopes
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

OPTIONS = ('off', MARKER_OPTION)
GAINS = (1.0, .7, 1.3)


def read(path, manifests):
    data = path.read_bytes()
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else data
    manifests[str(path)] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    return raw


def jsonl(raw, name, manifests):
    path = raw/name if (raw/name).exists() else raw/(name+'.zst')
    return [json.loads(l) for l in read(path, manifests).splitlines() if l.strip()]


def components(rgb, servo, option):
    """Diagnostic only: islands inside EVERY blue component, before quad/clip tests."""
    h, w = rgb.shape[:2]
    origin, axes = goal_camera(servo, 'camera_v3')
    self_mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, w, h)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    blue = cv2.inRange(hsv, (90, 70, 35), (135, 255, 255)); blue[self_mask] = 0
    rows = []
    for contour in cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        area = float(cv2.contourArea(contour))
        if area < 100: continue
        region = np.zeros((h, w), np.uint8); cv2.drawContours(region, [contour], -1, 255, -1)
        inner = cv2.erode(region, np.ones((5, 5), np.uint8)) != 0
        mask = white_markers(rgb, hsv, inner, region_area_px2=area, option=option).astype(np.uint8)
        n, _, stats, cent = cv2.connectedComponentsWithStats(mask)
        islands = [(cent[i].tolist(), stats[i].tolist()) for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] >= 9]
        quad = cv2.approxPolyDP(contour, .02*cv2.arcLength(contour, True), True).reshape(-1, 2)
        is_quad = len(quad) == 4 and bool(cv2.isContourConvex(quad))
        clipped = bool(quad[:, 0].min() <= 2 or quad[:, 1].min() <= 2 or quad[:, 0].max() >= w-3 or quad[:, 1].max() >= h-3)
        rows.append(dict(area_px2=area, islands=islands, convex_quad=is_quad, clipped=clipped))
    return rows


def scene_B(xml):
    geoms = {m.group(1): np.array(m.group(2).split(), float) for m in re.finditer(
        r'<geom name="zone_(zone_B|slot_B\d)" type="box" pos="([^"]+)" size="([^"]+)"', xml)}
    size = np.array(re.search(r'name="zone_zone_B" type="box" pos="[^"]+" size="([^"]+)"', xml).group(1).split(), float)
    # Collision walls (0.40 m high, above the ~0.2 m camera): 2-D sight-line occluders.
    walls = []
    for m in re.finditer(r'<geom name="zone_[^"]+" type="box" pos="([^"]+)" size="([^"]+)"([^>]*)>', xml):
        if 'contype="1"' not in m.group(3): continue
        euler = re.search(r'euler="([^"]+)"', m.group(3))
        walls.append((np.array(m.group(1).split(), float)[:2], np.array(m.group(2).split(), float)[:2],
                      float(euler.group(1).split()[2]) if euler else 0.))
    return geoms['zone_B'][:2], size[:2], [geoms[f'slot_B{i}'][:2] for i in (1, 2, 3)], walls


def occluded(camera_xy, point, walls, step=.01):
    """Evaluation only: does the floor sight line cross a wall footprint?"""
    a, b = np.asarray(camera_xy, float), np.asarray(point, float)
    t = np.linspace(0., 1., max(2, int(np.linalg.norm(b-a)/step)))[1:-1, None]
    samples = a+(b-a)*t
    for center, half, yaw in walls:
        c, s = math.cos(yaw), math.sin(yaw)
        local = (samples-center)@np.array([[c, -s], [s, c]])
        if np.any((np.abs(local[:, 0]) < half[0]) & (np.abs(local[:, 1]) < half[1])): return True
    return False


def project(points, pose, servo, w, h):
    """Evaluation only: world floor points -> pixels through the own camera model."""
    x, y, yaw = pose; c, s = math.cos(yaw), math.sin(yaw)
    d = np.asarray(points, float)-[x, y]
    body = np.column_stack([c*d[:, 0]+s*d[:, 1], -s*d[:, 0]+c*d[:, 1], np.zeros(len(d))])
    origin, axes = goal_camera(servo, 'camera_v3')
    optical = (body-origin)@axes.T
    angle = np.degrees(np.arctan2(np.linalg.norm(optical[:, :2], axis=1), optical[:, 2]))
    ok = (optical[:, 2] > .02) & (angle < 80)
    uv = np.full((len(d), 2), np.nan)
    if ok.any():
        p, _ = cv2.fisheye.projectPoints(optical[ok].reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                         np.asarray(scaled_camera_matrix(w, h)), np.asarray(CAMERA_FISHEYE_D))
        uv[ok] = p.reshape(-1, 2)
    return uv, ok


def camera_world(pose, servo):
    origin, _ = goal_camera(servo, 'camera_v3')
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return np.array([pose[0]+c*origin[0]-s*origin[1], pose[1]+s*origin[0]+c*origin[1]])


def in_view(uv, ok, rgb, margin=2, *, points=None, camera_xy=None, walls=()):
    h, w = rgb.shape[:2]; out = []
    for index, ((u, v), good) in enumerate(zip(uv, ok)):
        good = bool(good) and np.isfinite(u)
        if good and walls and occluded(camera_xy, points[index], walls): good = False
        if good:
            ui, vi = int(round(u)), int(round(v))
            good = margin <= ui < w-margin and margin <= vi < h-margin and int(rgb[vi, ui].sum()) > 20
        out.append(good)
    return out


def label(rgb, B, pose, servo):
    center, half, slots, walls = B
    h, w = rgb.shape[:2]
    corners = [center+[sx*half[0], sy*half[1]] for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    grid = [center+[a*half[0], b*half[1]] for a in np.linspace(-1, 1, 9) for b in np.linspace(-1, 1, 15)]
    # Corners sit on the B edge; nudge 1 cm inward so a touching wall face is not an occluder.
    view = dict(camera_xy=camera_world(pose, servo), walls=walls)
    corner_in = in_view(*project(corners, pose, servo, w, h), rgb, points=[center+.99*(p-center) for p in corners], **view)
    slot_uv, slot_ok = project(slots, pose, servo, w, h)
    slot_in = in_view(slot_uv, slot_ok, rgb, points=slots, **view)
    area = float(np.mean(in_view(*project(grid, pose, servo, w, h), rgb, points=[center+.99*(p-center) for p in grid], **view)))
    cls = 'none' if area == 0 and not any(slot_in) else ('full' if all(corner_in) and all(slot_in) else 'partial')
    return dict(cls=cls, corners_in=int(sum(corner_in)), slots_in=int(sum(slot_in)), B_area_fraction=area,
                slot_px=[uv.tolist() for uv, good in zip(slot_uv, slot_in) if good])


def matched(islands, slot_px):
    """Evaluation only: (islands near a projected slot centre, slots with >=1 such island)."""
    near = lambda c, st, u, v: math.hypot(c[0]-u, c[1]-v) <= max(15., .75*math.hypot(st[2], st[3]))
    on = sum(any(near(c, st, u, v) for u, v in slot_px) for c, st in islands)
    marks = sum(any(near(c, st, u, v) for c, st in islands) for u, v in slot_px)
    return on, marks


def replay(outputs):
    manifests, rows = {}, []
    root = outputs/'e2e11-stall-odometry/selected-frames'
    for run_path in sorted(root.iterdir()):
        raw = outputs/'azure-runs'/run_path.name/'raw'
        B = scene_B(read(raw/'scene.xml', manifests).decode())
        for rid in ('r1', 'r2'):
            frames = jsonl(raw, f'robots/{rid}/frames.jsonl', manifests)
            poses = {r['frame_id']: r for r in jsonl(raw, f'robots/{rid}/ownmap.jsonl', manifests)}
            trajectory = jsonl(raw, f'eval_only/{rid}/trajectory.jsonl', manifests)
            times = np.array([v['t'] for v in trajectory])
            for f in frames:
                p = run_path/'raw'/f['path']
                if not p.exists(): continue
                data = read(p, manifests)
                if hashlib.sha256(data).hexdigest() != f['sha256']: raise ValueError('SAVED_RGB_HASH_MISMATCH')
                base = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                servo = {int(k): v for k, v in f['commanded_servo'].items()}
                own_pose = poses[f['frame_id']]['pose_own_m']
                row = dict(run=run_path.name, robot=rid, frame_id=f['frame_id'], sha256=f['sha256'], detect={})
                for gain in GAINS:
                    rgb = base if gain == 1. else np.clip(base.astype(np.float32)*gain, 0, 255).astype(np.uint8)
                    for option in OPTIONS:
                        diag = {}
                        accepted = boundary(rgb, servo, own_pose, diagnostics=diag, marker_detect=option) is not None
                        comps = components(rgb, servo, option)
                        row['detect'][f'{option}@{gain}'] = dict(
                            complete_boundary=accepted,
                            quad_stage_islands_max=max((c['white_islands'] for c in diag['contours'] if 'white_islands' in c), default=None),
                            any_islands_max=max((len(c['islands']) for c in comps), default=0),
                            three_island_components=[dict(convex_quad=c['convex_quad'], clipped=c['clipped'], area_px2=c['area_px2'])
                                                     for c in comps if len(c['islands']) == 3],
                            islands=[i for c in comps for i in c['islands']])
                # Evaluation labels only after all detections of this frame.
                i = int(np.argmin(np.abs(times-f['sim_time'])))
                row['time_residual_s'] = float(abs(times[i]-f['sim_time']))
                row['label'] = label(base, B, [*trajectory[i]['robot_xyz_m'][:2], trajectory[i]['robot_yaw_rad']], servo)
                for v in row['detect'].values():
                    v['islands_on_slots'], v['marks_detected'] = matched(v['islands'], row['label']['slot_px'])
                    v['islands_total'] = len(v['islands']); del v['islands']
                rows.append(row)
    return rows, manifests


def summarize(rows):
    out = dict(frames=len(rows), by_robot=dict(Counter(r['robot'] for r in rows)),
               label_classes=dict(Counter(r['label']['cls'] for r in rows)),
               label_slots_in_view=dict(Counter(r['label']['slots_in'] for r in rows)),
               label_B_corners_in_view=dict(Counter(r['label']['corners_in'] for r in rows)),
               max_time_residual_s=max(r['time_residual_s'] for r in rows), results={})
    for key in rows[0]['detect']:
        d = [r['detect'][key] for r in rows]
        lab = [r['label'] for r in rows]
        none = [x for x, l in zip(d, lab) if l['cls'] == 'none']
        seen3 = [x for x, l in zip(d, lab) if l['slots_in'] == 3]
        seen_any = [x for x, l in zip(d, lab) if l['slots_in'] >= 1]
        three = [x for x in d if x['three_island_components']]
        out['results'][key] = dict(
            complete_boundary_frames=sum(x['complete_boundary'] for x in d),
            frames_with_three_island_component=len(three),
            three_islands_but_incomplete=dict(
                total=sum(not x['complete_boundary'] for x in three),
                B_corners_in_view_lt4=sum(l['corners_in'] < 4 and not x['complete_boundary'] for x, l in zip(d, lab) if x['three_island_components']),
                component_not_convex_quad=sum(all(not c['convex_quad'] for c in x['three_island_components']) and not x['complete_boundary'] for x in three)),
            frames_with_mark_detected=dict(
                N=sum(x['marks_detected'] > 0 for x in d),
                B_corners_in_view_lt4=sum(x['marks_detected'] > 0 and l['corners_in'] < 4 for x, l in zip(d, lab))),
            all3_slots_in_view=dict(N=len(seen3), three_islands=sum(bool(x['three_island_components']) for x in seen3),
                                    complete_boundary=sum(x['complete_boundary'] for x in seen3)),
            slot_marks_in_view=dict(frames=len(seen_any), marks=sum(l['slots_in'] for l in lab),
                                    marks_detected=sum(x['marks_detected'] for x in d),
                                    islands_on_marks=sum(x['islands_on_slots'] for x, l in zip(d, lab) if l['slots_in'])),
            islands_total=sum(x['islands_total'] for x in d),
            islands_off_marks=sum(x['islands_total']-x['islands_on_slots'] for x in d),
            B_not_in_view=dict(N=len(none), frames_any_island=sum(x['islands_total'] > 0 for x in none),
                               frames_three_islands=sum(bool(x['three_island_components']) for x in none),
                               complete_boundary=sum(x['complete_boundary'] for x in none)))
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--outputs', type=Path, required=True)
    ap.add_argument('--rows-out', type=Path, required=True)
    ap.add_argument('--summary-out', type=Path, required=True)
    a = ap.parse_args()
    rows, manifests = replay(a.outputs)
    a.rows_out.write_text(json.dumps(dict(rows=rows, input_manifest=manifests), sort_keys=True))
    a.summary_out.write_text(json.dumps(summarize(rows), indent=1, sort_keys=True))
    print(json.dumps(summarize(rows)['results'], indent=1))
