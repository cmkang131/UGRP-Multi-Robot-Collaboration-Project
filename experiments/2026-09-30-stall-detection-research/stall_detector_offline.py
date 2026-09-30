"""Offline replay of a minimal image-only stall detector on recorded carry frames (no simulation, no model calls).

Statistic (own wrist frames only): f(t) = mean | blockmean16(I(t) - I(t-1s)) - its mean |, over the dark central ROI.
Rule per 'command run' (own issued command magnitude >= 0.03 m/s, carry posture, >= 5 s long):
  reference  f_ref = median f over windows ending in [t_on+1, t_on+3] s (the robot has just been told to go, ramp is over);
  flag       f < RATIO * f_ref for K consecutive windows (stride 0.2 s), only for windows ending after t_on+3 s.
GT is used ONLY for labels: a window is STALL when GT displacement <= 0.3 x issued, MOVING when >= 0.6 x issued.
Two sensor conditions: clean render, and synthetic noise (read noise 1.0 gray levels + 0.3 % exposure jitter per frame).
Outputs results/stall_detector_offline.{json,txt}. This is an exploratory replay, NOT a pre-registered result.
"""
import json, math, sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).parent))
from caseio import OUT, load_case, interp_pose, cmd_forward_distance
from flow_feasibility import dark_roi, STALL_SETS, MOVE_SETS
cv2.setNumThreads(1)
HERE = Path(__file__).parent
LAG, STRIDE_S = 1.0, 0.2
RATIO = float(sys.argv[1]) if len(sys.argv) > 1 else 0.4
K = int(sys.argv[2]) if len(sys.argv) > 2 else 2
rng = np.random.default_rng(7)


def nz(x):
    return np.clip(np.round(x * (1 + rng.normal(0, 0.003)) + rng.normal(0, 1.0, x.shape)), 0, 255)


def stat(a, b, noise):
    if noise:
        a, b = nz(a), nz(b)
    d = b - a
    h, w = (d.shape[0] // 16) * 16, (d.shape[1] // 16) * 16
    bm = d[:h, :w].reshape(h // 16, 16, w // 16, 16).mean((1, 3))
    return float(np.abs(bm - bm.mean()).mean())


def runs_for(c, rid):
    """maximal command runs (t_on, t_off) with issued magnitude >= 0.03 in carry posture, length >= 5 s."""
    ts, v, _ = c['mec'][rid]
    on = np.hypot(v[:, 0], v[:, 1]) >= 0.03
    idx = np.flatnonzero(on)
    runs = []
    if len(idx) == 0:
        return runs
    s = idx[0]; p = idx[0]
    for i in idx[1:]:
        if ts[i] - ts[p] > 0.35:
            runs.append((ts[s], ts[p] + 0.1)); s = i
        p = i
    runs.append((ts[s], ts[p] + 0.1))
    return [r for r in runs if r[1] - r[0] >= 5.0]


def process(cd, kind):
    c = load_case(cd)
    out = []
    for rid in ('r1', 'r2'):
        fidx, ft = c['frames'][rid]
        for (t_on, t_off) in runs_for(c, rid):
            wins = []
            t = t_on + 1.0
            while t + 0 <= t_off - 0.05:
                ta = t - LAG
                ia, ib = np.searchsorted(ft, [ta, t])
                if ib >= len(ft) or ia >= len(ft) or abs(ft[ib] - t) > 0.11 or abs(ft[ia] - ta) > 0.11:
                    t += STRIDE_S; continue
                ii = np.searchsorted(c['t'], [ft[ia], ft[ib]]); ii = np.minimum(ii, len(c['t']) - 1)
                if not (c['lift'][ii] > 0.04).all() or not c['jaws'][rid][ii].all():
                    t += STRIDE_S; continue
                xa, ya, _ = interp_pose(c, rid, ft[ia]); xb, yb, _ = interp_pose(c, rid, ft[ib])
                d = math.hypot(xb - xa, yb - ya); cf = cmd_forward_distance(c, rid, ft[ia], ft[ib]); m = math.hypot(cf[0], cf[1])
                lab = 'STALL' if (m >= 0.025 and d <= 0.3 * m) else 'MOVING' if (m >= 0.025 and d >= 0.6 * m) else 'OTHER'
                pa = cd / 'frames' / rid / f'{int(fidx[ia]):05d}.jpg'; pb = cd / 'frames' / rid / f'{int(fidx[ib]):05d}.jpg'
                ga = cv2.imread(str(pa), cv2.IMREAD_GRAYSCALE); gb = cv2.imread(str(pb), cv2.IMREAD_GRAYSCALE)
                roi = dark_roi(ga, gb)
                if roi is None:
                    t += STRIDE_S; continue
                r0, r1 = roi
                A = ga[r0:r1, 100:540].astype(np.float32); B = gb[r0:r1, 100:540].astype(np.float32)
                # noise-floor estimate: last two frames (0.1 s apart, motion <= 4 mm) share the same noise level as the 1 s pair
                gp = cv2.imread(str(cd / 'frames' / rid / f'{int(fidx[ib]) - 1:05d}.jpg'), cv2.IMREAD_GRAYSCALE)
                P = gp[r0:r1, 100:540].astype(np.float32)
                na, nb, npv = nz(A), nz(B), nz(P)
                f_long = stat(na, nb, False); f_short = stat(npv, nb, False)
                f_corr = math.sqrt(max(f_long ** 2 - f_short ** 2, 0.0))
                wins.append(dict(t=float(ft[ib]), label=lab, f_clean=stat(A, B, False), f_noisy=f_long, f_noisy_corr=f_corr))
                t += STRIDE_S
            if len(wins) < 20:
                continue
            out.append(dict(case=cd.name, rid=rid, kind=kind, t_on=float(t_on), t_off=float(t_off), wins=wins))
    return out


def evaluate(runs, key):
    res = []
    for r in runs:
        w = r['wins']
        ref_w = [x[key] for x in w if r['t_on'] + 1.0 <= x['t'] <= r['t_on'] + 3.0]
        if len(ref_w) < 5:
            continue
        ref = float(np.median(ref_w))
        test = [x for x in w if x['t'] > r['t_on'] + 3.0]
        flags = []; cnt = 0
        for x in test:
            cnt = cnt + 1 if x[key] < RATIO * ref else 0
            if cnt >= K:
                flags.append(x['t'])
        stall_w = [x for x in w if x['label'] == 'STALL']
        onset = None
        if stall_w:
            # window ends at t; window START = t-1s: onset = first stalled window's start (GT displacement small over that whole second)
            onset = stall_w[0]['t'] - LAG
        move_test = [x for x in test if x['label'] == 'MOVING']
        false_flags = [t for t in flags if not any(abs(t - x['t']) < 1e-6 and x['label'] == 'STALL' for x in test) and
                       (onset is None or t < onset)]
        res.append(dict(case=r['case'], rid=r['rid'], kind=r['kind'], ref=ref, n_test=len(test), n_flags=len(flags),
                        stall_onset=onset, first_flag=(flags[0] if flags else None),
                        latency_s=(flags[0] - onset if (flags and onset is not None and flags[0] >= onset - 1e-6) else None),
                        flag_before_onset=(bool(flags) and onset is not None and flags[0] < onset) or (onset is None and bool(flags)),
                        n_moving_windows=len(move_test)))
    return res


def main():
    runs = []
    for sets, kind in ((STALL_SETS, 'stallset'), (MOVE_SETS, 'moveset')):
        for s in sets:
            for cd in sorted((OUT / s / 'cases').iterdir()):
                if cd.is_dir() and (cd / 'eval_only' / 'trace.jsonl').exists():
                    runs += process(cd, kind)
        print(kind, len(runs), flush=True)
    summary = {'ratio': RATIO, 'K': K, 'n_runs': len(runs)}
    lines = [f'ratio={RATIO} K={K} lag={LAG}s stride={STRIDE_S}s  runs={len(runs)}']
    for key in ('f_clean', 'f_noisy', 'f_noisy_corr'):
        ev = evaluate(runs, key)
        st = [e for e in ev if e['stall_onset'] is not None]
        mv = [e for e in ev if e['stall_onset'] is None]
        det = [e for e in st if e['latency_s'] is not None]
        early = [e for e in ev if e['flag_before_onset']]
        lat = [e['latency_s'] for e in det]
        s = dict(stall_runs=len(st), stall_detected=len(det), stall_cases=len({e['case'] for e in st}),
                 latency_median_s=float(np.median(lat)) if lat else None, latency_max_s=float(max(lat)) if lat else None,
                 nonstall_runs=len(mv), nonstall_runs_with_flag=sum(1 for e in mv if e['n_flags'] > 0),
                 nonstall_cases=len({e['case'] for e in mv}), flag_before_true_onset=len(early),
                 moving_windows_tested=int(sum(e['n_moving_windows'] for e in ev)),
                 flagged_windows_total_nonstall=int(sum(e['n_flags'] for e in mv)),
                 test_windows_nonstall=int(sum(e['n_test'] for e in mv)))
        summary[key] = s
        lines.append(f'[{key}] ' + json.dumps(s))
    (HERE / f'results/stall_detector_offline_r{RATIO}_k{K}.json').write_text(json.dumps(dict(summary=summary, per_run=evaluate(runs, 'f_clean')), indent=1))
    txt = '\n'.join(lines)
    (HERE / f'results/stall_detector_offline_r{RATIO}_k{K}.txt').write_text(txt + '\n')
    print(txt)


if __name__ == '__main__':
    main()
