"""Synthetic coverage/accuracy of b_marker_detect=cones_v1 (ground truth used ONLY here, as the evaluation output).

Robot poses on a grid around B (B centre at map (4.6,-2.1), robot heading toward B +-60 deg), cones projected through
the real fisheye model with 0.5 px Gaussian pixel noise, then detected by harness/e2e_b_cones.py from pixels only.
"""
import json, math, sys
import cv2
import numpy as np
sys.path.insert(0, '.')
from harness import e2e_b_cones as C
from harness.active_camera import SEARCH
from harness.e2e_rgb_gate import lens_valid, default_cone_layout

W, H = 640, 480
L = default_cone_layout()
rng = np.random.default_rng(1)
valid = lens_valid(W, H)


def render(robot, noise_px=.5):
    x, y, th = robot
    c, s = math.cos(th), math.sin(th)
    img = np.full((H, W, 3), 120, np.uint8)
    for loc in L['local']:  # B centre at map origin here; cone world position -> robot frame
        d = loc-[x, y]
        b = np.array([c*d[0]+s*d[1], -s*d[0]+c*d[1]])
        ang = np.linspace(0, 2*np.pi, 24, endpoint=False)
        pts = np.vstack([np.column_stack([b[0]+.09*np.cos(ang), b[1]+.09*np.sin(ang), np.zeros(24)]), [b[0], b[1], .30]])
        uv, ok = C.project_points(pts, SEARCH)
        if ok.sum() < 20: continue
        uv = uv[ok]+rng.normal(0, noise_px, (1, 2))
        cv2.fillConvexPoly(img, cv2.convexHull(np.rint(uv).astype(np.int32)), (140, 242, 13))
    img[~valid] = 0
    return img


rows = []
for rx in np.arange(-5., -1.4, .5):
    for ry in np.arange(-1.5, 1.51, .5):
        for dth in (-30, -15, 0, 15, 30):
            th = math.atan2(-ry, -rx)+math.radians(dth)  # heading relative to the bearing to B centre
            robot = (rx, ry, th)
            fit = C.detect_cones(render(robot), SEARCH, (0., 0., 0.), L)
            row = dict(robot=[float(rx), float(ry), float(th)], range_to_B_m=float(math.hypot(rx, ry)), dtheta_deg=dth, accepted=fit is not None)
            if fit:  # evaluation only: true B centre in robot frame
                c, s = math.cos(th), math.sin(th)
                true = np.array([c*(0-rx)+s*(0-ry), -s*(0-rx)+c*(0-ry)])
                row.update(pos_err_m=float(np.linalg.norm(np.array(fit['center_robot_m'])-true)), n_cones=fit['n_cones'])
            rows.append(row)
acc = [r for r in rows if r['accepted']]
by = {}
for r in rows:
    k = f"{int(r['range_to_B_m'])}-{int(r['range_to_B_m'])+1} m"
    by.setdefault(k, []).append(r)
summary = dict(poses=len(rows), accepted=len(acc), pos_err_median_m=float(np.median([r['pos_err_m'] for r in acc])) if acc else None,
               pos_err_p90_m=float(np.percentile([r['pos_err_m'] for r in acc], 90)) if acc else None,
               by_range={k: dict(n=len(v), accepted=sum(r['accepted'] for r in v),
                                 median_err_m=(float(np.median([r['pos_err_m'] for r in v if r['accepted']])) if any(r['accepted'] for r in v) else None))
                         for k, v in sorted(by.items())})
print(json.dumps(summary, indent=1))
json.dump(dict(summary=summary, rows=rows), open('experiments/2026-10-12-e2e-bcones/synthetic_coverage.json', 'w'))
