"""Issue #366 VO feasibility: per-frame feature stats and per-pair VO on recorded own-RGB frames.

VO inputs: own RGB frames + own commanded servo (camera FK) + fixed camera intrinsics only.
GT pose (eval_only/*/pose.jsonl) is used ONLY afterwards to label and score pairs.
"""
import csv, sys, time
from vocommon import *

OUT = "/Users/changmin/projects/ugrp/outputs/vo-feasibility-20261003"
RNG = np.random.default_rng(0)
ORB = cv2.ORB_create(nfeatures=1500, fastThreshold=12)
FAST = cv2.FastFeatureDetector_create(threshold=20, nonmaxSuppression=True)
BF = cv2.BFMatcher(cv2.NORM_HAMMING)

_valid = None
def valid_mask(gray):
    global _valid
    if _valid is None:
        m = (gray > 8).astype(np.uint8) * 255
        _valid = cv2.erode(m, np.ones((15, 15), np.uint8))
    return _valid

def beam_mask(bgr):
    """Carried beam / green tape (yellow-green) and its black middle band; dilated."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (25, 90, 60), (55, 255, 255))
    black = cv2.inRange(hsv, (0, 0, 0), (180, 255, 35))
    m = cv2.dilate(cv2.bitwise_or(green, black), np.ones((9, 9), np.uint8))
    return m

_floor_cache = {}
def floor_pixels(servo, shape):
    key = json.dumps(servo, sort_keys=True)
    if key not in _floor_cache:
        h, w = shape
        ys, xs = np.mgrid[0:h:4, 0:w:4]
        pts = np.column_stack((xs.ravel(), ys.ravel())).astype(float)
        _, ok = ground(pts, servo, max_range=4.0)
        _floor_cache[key] = ok.reshape(ys.shape)
    return _floor_cache[key]

def rigid_ransac(a, b, thr=0.03, iters=300):
    """Find R,t with a ~= R b + t (2-D). Returns (yaw, t, inlier mask) or None."""
    n = len(a)
    if n < 3:
        return None
    best = None
    for _ in range(iters):
        i, j = RNG.choice(n, 2, replace=False)
        db, da = b[j] - b[i], a[j] - a[i]
        if np.linalg.norm(db) < 0.05:
            continue
        th = math.atan2(da[1], da[0]) - math.atan2(db[1], db[0])
        R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        t = a[i] - R @ b[i]
        inl = np.linalg.norm(a - (b @ R.T + t), axis=1) < thr
        if best is None or inl.sum() > best.sum():
            best = inl
    if best is None or best.sum() < 3:
        return None
    A, B = a[best], b[best]
    ca, cb = A.mean(0), B.mean(0)
    H = (B - cb).T @ (A - ca)
    th = math.atan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
    R = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    t = ca - R @ cb
    inl = np.linalg.norm(a - (b @ R.T + t), axis=1) < thr
    return th, t, inl

def gp_from_pairs(p0, p1, s0, s1):
    """Ground-plane VO: pixels in frame i (p0) and i+1 (p1) -> base motion i->i+1 in frame-i coords."""
    g0, ok0 = ground(p0, s0, 2.5)
    g1, ok1 = ground(p1, s1, 2.5)
    ok = ok0 & ok1
    if ok.sum() < 6:
        return None, int(ok.sum()), 0
    r = rigid_ransac(g0[ok], g1[ok])
    if r is None:
        return None, int(ok.sum()), 0
    th, t, inl = r
    return (t[0], t[1], th), int(ok.sum()), int(inl.sum())

def essential(p0, p1, s0, s1):
    n0, n1 = undist(p0), undist(p1)
    if len(n0) < 8:
        return None, 0
    E, m = cv2.findEssentialMat(n0, n1, np.eye(3), method=cv2.RANSAC, prob=0.999, threshold=1.0 / 620)
    if E is None or E.shape != (3, 3):
        return None, 0
    ninl, R, t, m2 = cv2.recoverPose(E, n0, n1, np.eye(3), mask=m)
    if ninl < 12:
        return None, int(ninl)
    # Camera motion: X1 = R X0 + t (optical frame). Express in base frame (same servo -> same axes).
    _, A = extr(s0)  # rows = optical axes in base frame
    Rb = A.T @ R.T @ A  # rotation of camera (base frame) from frame i to i+1
    dyaw = math.atan2(Rb[1, 0], Rb[0, 0])
    tdir = -(A.T @ (R.T @ t.ravel()))  # camera displacement direction in base frame (unit, sign-resolved by cheirality)
    return (tdir[0], tdir[1], dyaw), int(ninl)

def run(seq):
    root, rid, F, pt, pxy, pyaw = load(seq)
    beam = seq.startswith("v92")
    fstats, rows = [], []
    prev = None
    t0 = time.time()
    servo_hist = [json.dumps(f["commanded_servo"], sort_keys=True) for f in F]
    for i, f in enumerate(F):
        bgr = cv2.imread(f"{root}/{f['path']}")
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        mask = valid_mask(gray).copy()
        bm = beam_mask(bgr) if beam else np.zeros_like(mask)
        mask[bm > 0] = 0
        fl = floor_pixels(f["commanded_servo"], gray.shape)
        vsub = mask[0::4, 0::4] > 0
        floor_frac = float((fl & vsub).sum() / max((valid_mask(gray)[0::4, 0::4] > 0).sum(), 1))
        beam_frac = float(((bm[0::4, 0::4] > 0) & (valid_mask(gray)[0::4, 0::4] > 0)).sum() / max((valid_mask(gray)[0::4, 0::4] > 0).sum(), 1))
        kp_orb, des = ORB.detectAndCompute(gray, mask)
        kp_fast = FAST.detect(gray, mask)
        gf = cv2.goodFeaturesToTrack(gray, 400, 0.01, 8, mask=mask)
        gf = np.zeros((0, 2), np.float32) if gf is None else gf.reshape(-1, 2)
        if len(gf):
            _, gok = ground(gf, f["commanded_servo"], 2.5)
        else:
            gok = np.zeros(0, bool)
        fstats.append(dict(seq=seq, i=i, t=f["sim_time"], floor_frac=round(floor_frac, 3), beam_frac=round(beam_frac, 3),
                           orb=len(kp_orb), fast=len(kp_fast), gftt=len(gf), gftt_floor25=int(gok.sum()), sha=f["sha256"][:12]))
        cur = dict(gray=gray, kp=kp_orb, des=des, gf=gf, mask=mask, f=f)
        if prev is not None:
            pf, cf = prev["f"], f
            s0, s1 = pf["commanded_servo"], cf["commanded_servo"]
            settled = i >= 6 and len(set(servo_hist[i - 6:i + 1])) == 1
            g0, y0, _ = gt_at(pt, pxy, pyaw, pf["sim_time"])
            g1, y1, _ = gt_at(pt, pxy, pyaw, cf["sim_time"])
            c, s = math.cos(y0), math.sin(y0)
            d = g1 - g0
            gdx, gdy, gdyaw = c * d[0] + s * d[1], -s * d[0] + c * d[1], wrap(y1 - y0)
            row = dict(seq=seq, i=i, t=round(cf["sim_time"], 3), settled=int(settled), same_img=int(pf["sha256"] == cf["sha256"]),
                       gt_dx=gdx, gt_dy=gdy, gt_dyaw=gdyaw)
            # KLT tracks with forward-backward check
            p0 = prev["gf"]
            klt_n = 0
            if len(p0) >= 6:
                p1, st, _ = cv2.calcOpticalFlowPyrLK(prev["gray"], gray, p0.reshape(-1, 1, 2), None, winSize=(21, 21), maxLevel=3)
                pb, st2, _ = cv2.calcOpticalFlowPyrLK(gray, prev["gray"], p1, None, winSize=(21, 21), maxLevel=3)
                good = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm(pb.reshape(-1, 2) - p0, axis=1) < 1.0)
                q0, q1 = p0[good], p1.reshape(-1, 2)[good]
                inm = mask[np.clip(q1[:, 1].astype(int), 0, 479), np.clip(q1[:, 0].astype(int), 0, 639)] > 0
                q0, q1 = q0[inm], q1[inm]
                klt_n = len(q0)
            else:
                q0 = q1 = np.zeros((0, 2))
            est, nf, ni = gp_from_pairs(q0, q1, s0, s1) if klt_n >= 6 else (None, 0, 0)
            row.update(klt_tracks=klt_n, gpk_floor=nf, gpk_inl=ni, gpk_ok=int(est is not None and ni >= 8 and ni >= 0.4 * nf))
            row.update(gpk_dx=est[0] if est else np.nan, gpk_dy=est[1] if est else np.nan, gpk_dyaw=est[2] if est else np.nan)
            # ORB matches (ratio test) + ground plane; also wrong-tile match rate via GT (scoring only)
            om0 = om1 = np.zeros((0, 2))
            if prev["des"] is not None and des is not None and len(prev["des"]) >= 2 and len(des) >= 2:
                ms = BF.knnMatch(prev["des"], des, k=2)
                gm = [m[0] for m in ms if len(m) == 2 and m[0].distance < 0.8 * m[1].distance]
                om0 = np.array([prev["kp"][m.queryIdx].pt for m in gm]).reshape(-1, 2)
                om1 = np.array([kp_orb[m.trainIdx].pt for m in gm]).reshape(-1, 2)
            wrong = np.nan
            if len(om0):
                a0, k0 = ground(om0, s0, 2.5)
                a1, k1 = ground(om1, s1, 2.5)
                kk = k0 & k1
                if kk.sum():
                    R = np.array([[math.cos(gdyaw), -math.sin(gdyaw)], [math.sin(gdyaw), math.cos(gdyaw)]])
                    pred = a1[kk] @ R.T + np.array([gdx, gdy])
                    wrong = float(np.mean(np.linalg.norm(pred - a0[kk], axis=1) > 0.15))
            est2, nf2, ni2 = gp_from_pairs(om0, om1, s0, s1) if len(om0) >= 6 else (None, 0, 0)
            row.update(orb_matches=len(om0), orb_wrong_gt=wrong, gpo_inl=ni2, gpo_ok=int(est2 is not None and ni2 >= 8 and ni2 >= 0.4 * nf2))
            row.update(gpo_dx=est2[0] if est2 else np.nan, gpo_dy=est2[1] if est2 else np.nan, gpo_dyaw=est2[2] if est2 else np.nan)
            # Essential matrix on KLT tracks (needs same servo for axis mapping)
            e, ei = essential(q0, q1, s0, s1) if (klt_n >= 8 and s0 == s1) else (None, 0)
            row.update(e_inl=ei, e_ok=int(e is not None), e_tx=e[0] if e else np.nan, e_ty=e[1] if e else np.nan, e_dyaw=e[2] if e else np.nan,
                       e_pix_flow=float(np.median(np.linalg.norm(q1 - q0, axis=1))) if klt_n else np.nan)
            rows.append(row)
        prev = cur
        if i % 500 == 0:
            print(seq, i, len(F), round(time.time() - t0, 1), flush=True)
    for name, data in [("frames", fstats), ("pairs", rows)]:
        with open(f"{OUT}/{seq}_{name}.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0].keys()))
            w.writeheader(); w.writerows(data)

if __name__ == "__main__":
    for seq in sys.argv[1:]:
        run(seq)
