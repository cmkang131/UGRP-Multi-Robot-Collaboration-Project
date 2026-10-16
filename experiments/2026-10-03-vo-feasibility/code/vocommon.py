"""Shared helpers for issue #366 VO feasibility (offline, recorded frames only)."""
import sys, json, math
sys.path.insert(0, "/Users/changmin/projects/ugrp")
import numpy as np, cv2
from harness.visual_arm import camera_extrinsics
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

K = scaled_camera_matrix(640, 480)
D = np.asarray(CAMERA_FISHEYE_D, np.float64).reshape(4, 1)
TILE = 16.0 / 14 / 2  # floor plane 8 m half-size, texrepeat 14, 2x2 checker -> 0.5714 m

SEQS = {
    "v88_r1": ("/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded/zone_wide_two_doors_final_v3", "r1"),
    "v92_r1": ("/Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003/zone_wide_two_doors_final_v3", "r1"),
    "v92_r2": ("/Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003/zone_wide_two_doors_final_v3", "r2"),
    # older single-robot own-camera driving test run (door-tag map zone_wide_door_tags_v2, darker floor)
    "m1_s101": ("/Users/changmin/projects/ugrp/outputs/m1-owncam-20260926/test/m1test-s101", "r1"),
}

_ext_cache = {}
def extr(servo):
    key = json.dumps(servo, sort_keys=True)
    if key not in _ext_cache:
        o, a = camera_extrinsics(servo)
        _ext_cache[key] = (np.asarray(o, float), np.asarray(a, float))
    return _ext_cache[key]

def undist(pts):
    pts = np.asarray(pts, np.float64).reshape(-1, 1, 2)
    return cv2.fisheye.undistortPoints(pts, K, D).reshape(-1, 2)

def ground(pts, servo, max_range=3.0):
    """Pixels -> base-frame floor xy (own commanded servo FK only). Returns xy, valid mask."""
    o, a = extr(servo)
    n = undist(pts)
    rays = np.column_stack((n, np.ones(len(n)))) @ a
    ok = rays[:, 2] < -0.02
    s = np.where(ok, -o[2] / np.where(ok, rays[:, 2], -1), np.nan)
    xy = o[:2] + rays[:, :2] * s[:, None]
    ok &= np.isfinite(xy).all(1) & (np.linalg.norm(xy - o[:2], axis=1) < max_range)
    return xy, ok

def load(seq):
    root, rid = SEQS[seq]
    if seq.startswith("m1_"):
        F = [json.loads(l) for l in open(f"{root}/inputs/frames.jsonl")]
        for f in F:
            f["path"], f["sim_time"] = f["file"], f["t"]
            f.pop("report", None)  # PF pose report (tag-based) is NOT used
        G = [json.loads(l) for l in open(f"{root}/eval_only/gt_trajectory.jsonl")]
        return root, rid, F, np.array([g["t"] for g in G]), np.array([[g["x"], g["y"]] for g in G]), np.array([g["yaw"] for g in G])
    F = [json.loads(l) for l in open(f"{root}/robots/{rid}/frames.jsonl")]
    P = [json.loads(l) for l in open(f"{root}/eval_only/{rid}/pose.jsonl")]
    pt = np.array([p["t"] for p in P])
    pxy = np.array([p["base_position_m"][:2] for p in P])
    pyaw = np.array([math.atan2(p["base_rotation"][1][0], p["base_rotation"][0][0]) for p in P])
    return root, rid, F, pt, pxy, pyaw

def gt_at(pt, pxy, pyaw, t):
    i = int(np.argmin(abs(pt - t)))
    return pxy[i], pyaw[i], abs(pt[i] - t)

def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi

def project_base(pts_base3, servo):
    o, a = extr(servo)
    opt = (np.asarray(pts_base3, float) - o) @ np.linalg.inv(a)
    ok = opt[:, 2] > 0.05
    if len(opt) == 0:
        return np.zeros((0, 2)), np.zeros(0, bool)
    nrm = (opt[:, :2] / np.where(ok, opt[:, 2], 1)[:, None]).reshape(-1, 1, 2)
    px = cv2.fisheye.distortPoints(nrm, K, D).reshape(-1, 2)
    return px, ok
