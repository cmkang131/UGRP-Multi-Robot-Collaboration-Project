"""Direct ground-plane VO: inverse perspective mapping (bird's-eye view) of the near floor + ECC Euclidean alignment.
Inputs: own RGB + own commanded servo FK + fixed intrinsics. GT only for scoring (in summarize step)."""
import csv, sys, time
from vocommon import *
import vo_eval as V

OUT = "/Users/changmin/projects/ugrp/outputs/vo-feasibility-20261003"
RES = 0.005
X0, X1, Y0, Y1 = 0.20, 1.40, -0.60, 0.60
NU, NV = int((X1 - X0) / RES), int((Y1 - Y0) / RES)
_maps = {}

def ipm_map(servo):
    key = json.dumps(servo, sort_keys=True)
    if key not in _maps:
        u, v = np.meshgrid(np.arange(NU), np.arange(NV))  # rows = v (y), cols = u (x)
        B = np.column_stack((X0 + u.ravel() * RES, Y0 + v.ravel() * RES, np.zeros(u.size)))
        px, ok = project_base(B, servo)
        ok &= (px[:, 0] > 10) & (px[:, 0] < 630) & (px[:, 1] > 10) & (px[:, 1] < 470)
        mx = np.where(ok, px[:, 0], -1).reshape(NV, NU).astype(np.float32)
        my = np.where(ok, px[:, 1], -1).reshape(NV, NU).astype(np.float32)
        _maps[key] = (mx, my, ok.reshape(NV, NU))
    return _maps[key]

def bev(gray, mask, servo):
    mx, my, ok = ipm_map(servo)
    img = cv2.remap(gray, mx, my, cv2.INTER_LINEAR)
    m = cv2.remap(mask, mx, my, cv2.INTER_NEAREST)
    m = ((m > 0) & ok).astype(np.uint8)
    return img, m

def to_metric(W):
    R = W[:, :2]; tu = W[:, 2]
    o = np.array([X0, Y0])
    t = o - R @ o + RES * tu  # p1 = R p0 + t (base metres)
    dyaw = -math.atan2(R[1, 0], R[0, 0])
    Rd = R.T
    td = -Rd @ t
    return td[0], td[1], dyaw

def run(seq):
    root, rid, F, pt, pxy, pyaw = load(seq)
    beam = seq.startswith("v92")
    hist = [json.dumps(f["commanded_servo"], sort_keys=True) for f in F]
    rows, prev = [], None
    t0 = time.time()
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
    for i, f in enumerate(F):
        settled = i >= 6 and len(set(hist[i - 6:i + 1])) == 1
        if not settled:
            prev = None
            continue
        bgr = cv2.imread(f"{root}/{f['path']}")
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        mask = V.valid_mask(gray).copy()
        if beam:
            mask[V.beam_mask(bgr) > 0] = 0
        b, m = bev(gray, mask, f["commanded_servo"])
        b = cv2.GaussianBlur(b, (5, 5), 1.5).astype(np.float32)
        cur = (b, m)
        if prev is not None:
            (b0, m0) = prev
            both = (m0 & m)
            cov = float(both.mean())
            gx = cv2.Sobel(b0, cv2.CV_32F, 1, 0); gy = cv2.Sobel(b0, cv2.CV_32F, 0, 1)
            w = both.astype(np.float32)
            J = np.array([[np.sum(w * gx * gx), np.sum(w * gx * gy)], [np.sum(w * gx * gy), np.sum(w * gy * gy)]]) / max(w.sum(), 1)
            eig = np.linalg.eigvalsh(J)
            W = np.eye(2, 3, dtype=np.float32)
            ok, cc = 0, np.nan
            est = (np.nan, np.nan, np.nan)
            if cov > 0.15:
                try:
                    cc, W = cv2.findTransformECC(b0, b, W, cv2.MOTION_EUCLIDEAN, crit, both * 255, 1)
                    est = to_metric(W)
                    ok = 1
                except cv2.error:
                    pass
            g0, y0, _ = gt_at(pt, pxy, pyaw, F[i - 1]["sim_time"])
            g1, y1, _ = gt_at(pt, pxy, pyaw, f["sim_time"])
            c, s = math.cos(y0), math.sin(y0)
            d = g1 - g0
            rows.append(dict(seq=seq, i=i, t=round(f["sim_time"], 3), cov=round(cov, 3), eig_min=float(eig[0]), eig_max=float(eig[1]),
                             ecc_cc=cc, ipm_ok_raw=ok, ipm_dx=est[0], ipm_dy=est[1], ipm_dyaw=est[2],
                             gt_dx=c * d[0] + s * d[1], gt_dy=-s * d[0] + c * d[1], gt_dyaw=wrap(y1 - y0)))
        prev = cur
        if i % 500 == 0:
            print(seq, i, len(F), round(time.time() - t0, 1), flush=True)
    with open(f"{OUT}/{seq}_ipm.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader(); wr.writerows(rows)

if __name__ == "__main__":
    for s in sys.argv[1:]:
        run(s)
