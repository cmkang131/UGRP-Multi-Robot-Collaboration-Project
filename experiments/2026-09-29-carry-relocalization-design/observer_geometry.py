"""What could an observer robot (r3) see of the carrying pair, from the rendered poses? Map + ground-truth poses; audit only.

For every (leg, observer pose) in render_manifest.json:
  free      observer pose inside the arena, >= 0.13 m from every wall footprint, >= 0.45 m from both carriers
  points    line-of-sight (walls only; beam/robot self-occlusion ignored) AND inside the valid fisheye image for the two beam tips
            (z 0.06 m) and the two carrier bases (z 0.12 m)
  G_r3      wall/post pixel share of r3's own view (walls_v3, occlusion ignored): what r3 has for its OWN localisation
  px_per_m  pixels per metre of lateral offset at the range to the beam centre (image scale of the observer's measurement)

usage: python observer_geometry.py <render_manifest.json> <out.json>
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom_min as gm  # noqa: E402
from harness.owncam_view import HEIGHT, WIDTH, camera_extrinsics, project_base_points, valid_pixel_mask  # noqa: E402
from harness.zone_own_guards import static_boxes  # noqa: E402
from sim.masterpi_camera_profile import scaled_camera_matrix  # noqa: E402

MAP = 'zone_wide_door_geometry_v2'          # walls_v3, tag free
ROBOT_CLEAR_M = 0.13
CARRIER_CLEAR_M = 0.45
VALID = valid_pixel_mask(1)


def box_clear(static, x, y):
    for b in static_boxes(static):
        if b['height'] < 0.15:
            continue
        cx, cy = b['center']
        hx, hy = b['half']
        dx, dy = abs(x - cx) - hx, abs(y - cy) - hy
        if math.hypot(max(dx, 0.), max(dy, 0.)) < ROBOT_CLEAR_M:
            return False
    return True


def in_arena(static, x, y):
    x0, x1, y0, y1 = static['bounds_m']
    return x0 + ROBOT_CLEAR_M < x < x1 - ROBOT_CLEAR_M and y0 + ROBOT_CLEAR_M < y < y1 - ROBOT_CLEAR_M


def los(static, o, p):
    d = np.asarray(p, float) - np.asarray(o, float)
    dist = float(np.linalg.norm(d))
    d = (d / dist)[None, :]
    for b in static_boxes(static):
        t = float(gm._hit_box(np.asarray(o, float), d, b)[0])
        if t < dist - 0.02:
            return False
    return True


def analyse(row, static):
    x, y, yaw = row['robot_pose']
    servo = row['r3_servo']
    c, s = math.cos(yaw), math.sin(yaw)
    rot_inv = np.array([[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])
    origin_b, _ = camera_extrinsics(servo)
    origin_w = np.array([x, y, 0.]) + np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]]) @ np.asarray(origin_b, float)
    bx, by, bz = row['beam_xyz']
    by_yaw = row['beam_yaw']
    pts = {'beam_tip_a': [bx + 0.3 * math.cos(by_yaw), by + 0.3 * math.sin(by_yaw), 0.06],
           'beam_tip_b': [bx - 0.3 * math.cos(by_yaw), by - 0.3 * math.sin(by_yaw), 0.06],
           'r1_base': [row['carriers']['r1'][0], row['carriers']['r1'][1], 0.12],
           'r2_base': [row['carriers']['r2'][0], row['carriers']['r2'][1], 0.12]}
    seen = {}
    for k, w in pts.items():
        base = rot_inv @ (np.asarray(w) - np.array([x, y, 0.]))
        px = project_base_points(servo, base[None, :])[0]
        ok = (not np.isnan(px).any()) and 0 <= px[0] < WIDTH and 0 <= px[1] < HEIGHT and bool(VALID[int(px[1]), int(px[0])])
        seen[k] = bool(ok and los(static, origin_w, w))
    dists = {r: math.hypot(row['carriers'][r][0] - x, row['carriers'][r][1] - y) for r in ('r1', 'r2')}
    free = in_arena(static, x, y) and box_clear(static, x, y) and min(dists.values()) >= CARRIER_CLEAR_M
    g = gm.structure_share(static, servo, (x, y, yaw))
    rng = math.hypot(bx - x, by - y)
    fx = float(scaled_camera_matrix(WIDTH, HEIGHT)[0, 0])
    return {'leg': row['leg'], 'view': row['view'], 'observer_xyyaw': row['robot_pose'], 'free_space': bool(free),
            'visible': seen, 'all4_visible': all(seen.values()), 'range_to_beam_m': round(rng, 2), 'G_r3_own_structure': round(g, 3),
            'px_per_m_lateral_at_range': round(fx / rng, 1), 'mm_per_px_at_range': round(1000 * rng / fx, 2), 'fx_px': round(fx, 1)}


def main(manifest, out):
    static = gm.load_map(MAP)
    rows = [analyse(r, static) for r in json.load(open(manifest))['rows'] if r['view'].startswith('r3_')]
    json.dump(rows, open(out, 'w'), indent=1)
    by = {}
    for r in rows:
        by.setdefault(r['view'], []).append(r)
    for v, rs in by.items():
        ok = [r for r in rs if r['free_space']]
        both = [r for r in ok if r['all4_visible'] and r['G_r3_own_structure'] >= 0.03]
        print(f"{v:24s} legs {len(rs)}  free {len(ok)}  free&all4 {sum(r['all4_visible'] for r in ok)}  free&all4&G>=3% {len(both)}"
              f"  medianG {np.median([r['G_r3_own_structure'] for r in ok]) if ok else float('nan'):.3f}")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
