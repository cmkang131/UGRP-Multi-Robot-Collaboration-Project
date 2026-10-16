"""Summarize per-pair VO CSVs: class metrics, drift windows, command dead-reckoning baseline (GT used only for scoring/fitting the baseline gain)."""
import json, math, sys
import numpy as np, pandas as pd

OUT = "/Users/changmin/projects/ugrp/outputs/vo-feasibility-20261003"
SEQ_ROOT = {
    "v88_r1": ("/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded/zone_wide_two_doors_final_v3", "r1"),
    "v92_r1": ("/Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003/zone_wide_two_doors_final_v3", "r1"),
    "v92_r2": ("/Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003/zone_wide_two_doors_final_v3", "r2"),
    "m1_s101": ("/Users/changmin/projects/ugrp/outputs/m1-owncam-20260926/test/m1test-s101", "r1"),
}

def classify(p):
    tr = np.hypot(p.gt_dx, p.gt_dy); rot = np.degrees(np.abs(p.gt_dyaw))
    c = np.full(len(p), "mixed_small", object)
    c[(tr < 0.0005) & (rot < 0.02)] = "static"
    c[(tr >= 0.002) & (rot < 0.05)] = "translation"
    c[(rot >= 0.1) & (tr < 0.002)] = "rotation"
    c[(rot >= 0.1) & (tr >= 0.002)] = "rot+trans"
    c[p.settled.values == 0] = "arm_moving"
    return c

def cmd_features(seq, p):
    root, rid = SEQ_ROOT[seq]
    cp = f"{root}/inputs/commands.jsonl" if seq.startswith("m1_") else f"{root}/robots/{rid}/commands.jsonl"
    C = [json.loads(l) for l in open(cp)]
    m = [c for c in C if c["kind"] in ("mecanum", "drive")]
    t1 = p.t.values; t0 = t1 - 0.2
    out = np.zeros((len(p), 3))
    for c in m:
        rate = np.array([c.get("forward", 0.0), c.get("left", 0.0), c.get("turn", 0.0)])
        a, b = c["t"], c["t"] + c["duration_s"]
        lo, hi = np.searchsorted(t1, a), np.searchsorted(t0, b)
        for k in range(max(lo - 1, 0), min(hi + 1, len(p))):
            ov = max(0.0, min(b, t1[k]) - max(a, t0[k]))
            if ov > 0:
                out[k] += rate * ov
    return out

def fit_gain(F, y):
    k = np.linalg.lstsq(F, y, rcond=None)[0]
    return k

def method_cols(p, m):
    if m == "cmd":
        return p.cmd_dx, p.cmd_dy, p.cmd_dyaw, pd.Series(np.ones(len(p), bool), index=p.index)
    return p[f"{m}_dx"], p[f"{m}_dy"], p[f"{m}_dyaw"], p[f"{m}_ok"] == 1

def class_table(seq, p):
    rows = []
    for cls in ["static", "translation", "rotation", "rot+trans", "mixed_small", "arm_moving"]:
        q = p[p.cls == cls]
        if not len(q):
            continue
        gtr = np.hypot(q.gt_dx, q.gt_dy)
        for m in ["gpk", "gpo", "ipm", "cmd"]:
            dx, dy, dyaw, ok = method_cols(q, m)
            err_t = np.hypot(dx - q.gt_dx, dy - q.gt_dy)[ok]
            err_r = pd.Series(np.degrees(np.abs(np.angle(np.exp(1j * (dyaw - q.gt_dyaw).values)))), index=q.index)[ok]
            rel = (err_t / gtr[ok]).replace([np.inf], np.nan) if cls in ("translation", "rot+trans") else pd.Series(dtype=float)
            rows.append(dict(seq=seq, cls=cls, n=len(q), method=m, ok_rate=round(ok.mean(), 3),
                             gt_tr_med_mm=round(1000 * gtr.median(), 2), gt_rot_med_deg=round(np.degrees(np.abs(q.gt_dyaw)).median(), 3),
                             err_t_med_mm=round(1000 * err_t.median(), 2) if len(err_t) else np.nan,
                             err_t_p90_mm=round(1000 * err_t.quantile(.9), 2) if len(err_t) else np.nan,
                             rel_t_med=round(rel.median(), 3) if len(rel.dropna()) else np.nan,
                             err_rot_med_deg=round(err_r.median(), 3) if len(err_r) else np.nan,
                             err_rot_p90_deg=round(err_r.quantile(.9), 3) if len(err_r) else np.nan))
        # essential matrix: rotation error, translation-direction error (scale-free)
        ok = q.e_ok == 1
        er = pd.Series(np.degrees(np.abs(np.angle(np.exp(1j * (q.e_dyaw - q.gt_dyaw).values)))), index=q.index)[ok]
        ang = np.nan
        if cls == "translation" and ok.sum():
            g = np.column_stack((q.gt_dx, q.gt_dy))[ok.values]; e = np.column_stack((q.e_tx, q.e_ty))[ok.values]
            cosv = np.sum(g * e, 1) / (np.linalg.norm(g, axis=1) * np.linalg.norm(e, axis=1) + 1e-12)
            ang = round(float(np.median(np.degrees(np.arccos(np.clip(cosv, -1, 1))))), 1)
        rows.append(dict(seq=seq, cls=cls, n=len(q), method="essential", ok_rate=round(ok.mean(), 3),
                         err_rot_med_deg=round(er.median(), 3) if len(er) else np.nan,
                         err_rot_p90_deg=round(er.quantile(.9), 3) if len(er) else np.nan, e_tdir_med_deg=ang))
    return rows

def integrate(dx, dy, dyaw):
    x = y = th = 0.0
    for a, b, c in zip(dx, dy, dyaw):
        x += math.cos(th) * a - math.sin(th) * b
        y += math.sin(th) * a + math.cos(th) * b
        th += c
    return x, y, th

def drift(seq, p):
    rows = []
    usable = {}
    valid_frac = {}
    for m in ["gpk", "gpo", "ipm", "cmd", "zero"]:
        if m == "zero":
            usable[m] = (np.zeros(len(p)),) * 3
            continue
        dx, dy, dyaw, ok = method_cols(p, m)
        use = ok.values & (p.settled.values == 1) if m != "cmd" else np.ones(len(p), bool)
        usable[m] = (np.where(use, dx, 0.0), np.where(use, dy, 0.0), np.where(use, dyaw, 0.0))
        valid_frac[m] = use
    for win_s in [5, 10, 30]:
        n = int(win_s / 0.2)
        for start in range(0, len(p) - n, 5):
            sl = slice(start, start + n)
            g = integrate(p.gt_dx.values[sl], p.gt_dy.values[sl], p.gt_dyaw.values[sl])
            path = float(np.sum(np.hypot(p.gt_dx.values[sl], p.gt_dy.values[sl])))
            rotp = float(np.degrees(np.sum(np.abs(p.gt_dyaw.values[sl]))))
            arm = float(np.mean(p.settled.values[sl] == 0))
            r = dict(seq=seq, win_s=win_s, start_t=float(p.t.values[start]), gt_path_m=path, gt_rot_deg=rotp, arm_frac=arm,
                     gt_net_m=math.hypot(g[0], g[1]))
            for m in valid_frac:
                r[f"{m}_valid_frac"] = float(np.mean(valid_frac[m][sl]))
            for m, (a, b, c) in usable.items():
                e = integrate(a[sl], b[sl], c[sl])
                r[f"{m}_pos_err_m"] = math.hypot(e[0] - g[0], e[1] - g[1])
                r[f"{m}_yaw_err_deg"] = abs(math.degrees(math.atan2(math.sin(e[2] - g[2]), math.cos(e[2] - g[2]))))
            rows.append(r)
    return rows

if __name__ == "__main__":
    seqs = sys.argv[1:] or list(SEQ_ROOT)
    P = {}
    for s in seqs:
        p = pd.read_csv(f"{OUT}/{s}_pairs.csv")
        import os
        ip = f"{OUT}/{s}_ipm.csv"
        if os.path.exists(ip):
            q = pd.read_csv(ip)[["i", "ipm_ok_raw", "eig_min", "ecc_cc", "ipm_dx", "ipm_dy", "ipm_dyaw"]]
            p = p.merge(q, on="i", how="left")
        else:
            for c in ["ipm_ok_raw", "eig_min", "ipm_dx", "ipm_dy", "ipm_dyaw"]:
                p[c] = np.nan
        # IPM valid: ECC converged and the bird's-eye patch has gradient energy in both directions
        p["ipm_ok"] = ((p.ipm_ok_raw == 1) & (p.eig_min > 50)).astype(int)
        p["cls"] = classify(p)
        p[["cf", "cl", "ct"]] = cmd_features(s, p)
        P[s] = p
    # dead-reckoning gain: fitted on v88_r1 only (calibration run), applied to all
    q = P["v88_r1"]
    q = q[q.settled == 1]
    gains = {"dx": fit_gain(q[["cf", "cl", "ct"]].values, q.gt_dx.values), "dy": fit_gain(q[["cf", "cl", "ct"]].values, q.gt_dy.values),
             "dyaw": fit_gain(q[["cf", "cl", "ct"]].values, q.gt_dyaw.values)}
    json.dump({k: v.tolist() for k, v in gains.items()}, open(f"{OUT}/cmd_gain_fit_v88.json", "w"), indent=1)
    for s, p in P.items():
        F = p[["cf", "cl", "ct"]].values
        p["cmd_dx"], p["cmd_dy"], p["cmd_dyaw"] = F @ gains["dx"], F @ gains["dy"], F @ gains["dyaw"]
    ct = pd.DataFrame([r for s, p in P.items() for r in class_table(s, p)])
    ct.to_csv(f"{OUT}/summary_by_class.csv", index=False)
    dr = pd.DataFrame([r for s, p in P.items() for r in drift(s, p)])
    dr.to_csv(f"{OUT}/drift_windows.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(ct.to_string())
    agg = []
    for (s, w), g in dr.groupby(["seq", "win_s"]):
        mv = g[(g.gt_path_m >= 0.01 * w) & (g.arm_frac == 0)]  # moving >=1 cm/s average, arm still
        r = dict(seq=s, win_s=w, n_all=len(g), n_moving=len(mv), gt_path_med_m=round(mv.gt_path_m.median(), 3) if len(mv) else np.nan,
                 gt_net_med_m=round(mv.gt_net_m.median(), 3) if len(mv) else np.nan,
                 gpk_valid_med=round(mv.gpk_valid_frac.median(), 2) if len(mv) else np.nan)
        for m in ["gpk", "gpo", "ipm", "cmd", "zero"]:
            r[f"{m}_pos_med_m"] = round(mv[f"{m}_pos_err_m"].median(), 3) if len(mv) else np.nan
            r[f"{m}_pos_p90_m"] = round(mv[f"{m}_pos_err_m"].quantile(.9), 3) if len(mv) else np.nan
            r[f"{m}_yaw_med_deg"] = round(mv[f"{m}_yaw_err_deg"].median(), 2) if len(mv) else np.nan
        agg.append(r)
    agg = pd.DataFrame(agg)
    agg.to_csv(f"{OUT}/drift_summary.csv", index=False)
    print(agg.to_string())
    for s, p in P.items():
        print(s, "class counts", p.cls.value_counts().to_dict())
