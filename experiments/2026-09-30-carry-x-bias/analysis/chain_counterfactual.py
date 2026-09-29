"""Offline counterfactual of the chained L0 -> regrasp -> L1 particle filter under a changed carry motion model.

Recorded inputs only: the PF posterior at the L0 start, the issued base commands, the recorded regrasp fix (as a
Gaussian information update), and GT for scoring. The estimator is replayed with the real OwnCamLocalizer (predict-only;
the carry drive is tag-blind). GT is used to SCORE, never to steer the replay.

Regrasp fix transfer: from the recorded PF prior (Sp, mp) and posterior (Sq, mq) around the fix, the measurement's
information is  L = Sq^-1 - Sp^-1  and  eta = Sq^-1 mq - Sp^-1 mp  (negative eigenvalues clipped). For a counterfactual
prior (Sp', mp') the posterior is  Sq' = (Sp'^-1 + L)^-1,  mq' = Sq' (Sp'^-1 mp' + eta). A robot whose fix carries no
information along x (r2) therefore keeps its dead-reckoned x, a robot whose fix pins x (r1) is pulled to the measurement.
"""
import sys, json, math
sys.path.insert(0, '.')
from xb_common import *
import xb_replay as R

GATE_XY = 0.07
GATE_YAW_REG = math.radians(3.0)
GATE_YAW_K1G = math.radians(5.0)

def wrap1(a):
    return (a + math.pi) % (2*math.pi) - math.pi

def pf_row(c, k, t, mode):
    p = c['pf'][k]
    if mode == 'le':
        i = int(np.searchsorted(p['t'], t + 1e-6, side='right') - 1)
    else:
        i = int(np.searchsorted(p['t'], t - 1e-6, side='left'))
    i = max(0, min(i, len(p['t']) - 1))
    return p['t'][i], p['xyyaw'][i].copy(), p['cov'][i].copy()

def fix_time(case_dir, k, t0, t1):
    reps = json.load(open(Path(case_dir)/'robots.json'))[k]['frames']
    base = None
    for f in reps:
        r = f['report']
        if r['t_est'] < t0: 
            base = r.get('last_fix_t'); continue
        if r['t_est'] > t1: break
        if r.get('last_fix_t') is not None and (base is None or r['last_fix_t'] > base + 1e-6):
            return float(r['last_fix_t'])
    return None

def fix_rows(c, k, tf):
    """Recorded PF rows bracketing the regrasp tag fix at time tf (the report's last_fix_t).

    The fix reaches the PF as a recovery update plus a final update spread over two PF rows (about tf and tf+0.2 s), and the PF row
    clock lags by up to ~0.15 s, so ``pre`` is the last row at or before tf-0.2 s and ``post`` the first row at or after tf+0.15 s.
    Returns (t_pre, m_pre, S_pre, t_post, m_post, S_post) or None when tf is None.
    """
    if tf is None:
        return None
    _, m0, S0 = pf_row(c, k, tf - 0.2, 'le'); t0 = pf_row(c, k, tf - 0.2, 'le')[0]
    t1, m1, S1 = pf_row(c, k, tf + 0.15, 'ge')
    return (t0, m0, S0, t1, m1, S1)

def gauss_fuse(pri_rec, post_rec, pri_new):
    """Linear-Gaussian transfer of the recorded regrasp fix to a changed prior.

    Gaussian fusion gives  mq = Sq (Sp^-1 mp + eta)  so  d mq / d mp = A = Sq Sp^-1  (the measurement's own term eta cancels).
    The counterfactual posterior is therefore  mq' = mq + A (mp' - mp)  and  Sq' = Sq + A (Sp' - Sp) A^T.
    (Computing eta explicitly is ill-conditioned for a fix that carries almost no information along x.)
    """
    (mp, Sp), (mq, Sq), (mn, Sn) = pri_rec, post_rec, pri_new
    A = Sq @ np.linalg.inv(Sp)
    dm = mn - mp; dm[2] = wrap1(dm[2])
    return mq + A @ dm, psd(Sq + A @ (Sn - Sp) @ A.T)

def run_leg(params, m0, S0, cmds, t0, t_end, seed, every=0.5, n=2000):
    """Feed commands in time order; record (t, mean, cov) every ``every`` s of PF clock and at t_end."""
    import copy
    prm = copy.deepcopy(params); prm['particles'] = n
    loc = R.OwnCamLocalizer(R.static_map(), prm, seed=seed)
    rng = np.random.default_rng(seed + 12345)
    px = rng.multivariate_normal(np.asarray(m0, float), np.asarray(S0, float), size=n)
    px[:, 2] = R.wrap(px[:, 2])
    loc.px = px; loc.logw = np.zeros(n); loc.initialized = True; loc.t = float(t0)
    loc.load.loaded = True; loc._init_plant_state()
    trace = []
    next_rec = t0
    def rec():
        m, S = R.moments(loc.px)
        trace.append((loc.t, m, S))
    rec()
    for (t, f, l, u, exp) in cmds:
        if t > t_end + 1e-9: break
        while next_rec + every <= t - 1e-9:
            next_rec += every; loc.predict_to(next_rec); rec()
        loc.command({'t': t, 'kind': 'mecanum' if exp > t else 'hold', 'forward': f, 'left': l, 'turn': u, 'duration_s': exp - t})
    while next_rec + every <= t_end - 1e-9:
        next_rec += every; loc.predict_to(next_rec); rec()
    loc.predict_to(t_end); rec()
    return trace

def score_state(m, S, gt):
    e = m - gt; e[2] = wrap1(e[2])
    z = e/np.sqrt(np.diag(S))
    return dict(e=e, z=z, nees=float(e @ np.linalg.solve(S, e)), sd=np.sqrt(np.diag(S)), sxy=math.sqrt(S[0, 0] + S[1, 1]))

def psd(S):
    S = (S + S.T)/2
    w, V = np.linalg.eigh(S)
    return (V*np.clip(w, 1e-12, None)) @ V.T

def analyse_case(case_dir, cid, params_by_variant, ref='V0', seeds=(1,), n=2000, every=0.5, fix_mode='fuse'):
    """Counterfactual = recorded + (variant replay - reference replay), common random numbers.

    The replay does not reproduce the recorded y/yaw exactly (the recorded PF also applies the beam-edge yaw updates and the
    pair-mean yaw coupling, which are not replayed), so every quantity is the RECORDED state plus the change the replay
    produces when the variant replaces the reference (registered) model. For the reference itself this is the recorded state.
    Returns {variant: {robot: {'L0','L1','L1start': [score dicts per seed], 'sigma_traces', 'fix_time'}}}.
    """
    c = load_case(case_dir)
    row = json.loads(next(l for l in open(Path(case_dir).parents[1]/'cases.jsonl') if json.loads(l)['case_id'] == cid))
    legs = {l['leg']: l for l in row['chain']['legs'] if l['recorded']}
    out = {v: {} for v in params_by_variant}
    for k in ROBOTS:
        b = base_cmds(c['cmds'], k)
        t0, t1 = legs[0]['start_sim_s'], legs[0]['end_sim_s']
        ta, tb = legs[1]['start_sim_s'], legs[1]['end_sim_s']
        _, m_s, S_s = pf_row(c, k, t0, 'le')
        t1, m_l0, S_l0 = pf_row(c, k, t1, 'le')          # evaluate at the PF's own clock (its estimate time), GT at that time
        tf = fix_time(case_dir, k, t1, ta)
        fr = fix_rows(c, k, tf)
        if fr is not None:
            _, m_pre, S_pre, tpost, m_post, S_post = fr
            t_start1 = tpost
        else:
            t_start1, m_post, S_post = pf_row(c, k, ta, 'le'); m_pre, S_pre = m_l0, S_l0
        tb, m_l1, S_l1 = pf_row(c, k, tb, 'le')
        cmds0 = [x for x in b if t0 - 1e-9 <= x[0] <= t1 + 3.0]
        cmds1 = [x for x in b if t_start1 - 1e-9 <= x[0] <= tb + 3.0]
        gt0 = interp_gt(c, k, [t1])[0]; gt1 = interp_gt(c, k, [tb])[0]; gts = interp_gt(c, k, [t_start1])[0]
        res = {v: {'L0': [], 'L1': [], 'L1start': [], 'tr0': [], 'tr1': []} for v in params_by_variant}
        for sd in seeds:
            tr0 = {v: run_leg(p, m_s, S_s, cmds0, t0, t1, seed=sd, every=every, n=n) for v, p in params_by_variant.items()}
            for v, p in params_by_variant.items():
                d_m0 = tr0[v][-1][1] - tr0[ref][-1][1]; d_S0 = tr0[v][-1][2] - tr0[ref][-1][2]
                m_l0v = m_l0 + d_m0; S_l0v = psd(S_l0 + d_S0)
                # variant start of L1
                if tf is not None and fix_mode == 'fuse':
                    m_new = m_pre + d_m0; S_new = psd(S_pre + d_S0)
                    m_q, S_q = gauss_fuse((m_pre, S_pre), (m_post, S_post), (m_new, S_new))
                elif tf is not None and fix_mode == 'replace':
                    m_q, S_q = m_post.copy(), S_post.copy()          # the fix re-localises: posterior as recorded
                elif tf is not None and fix_mode == 'shift':
                    m_q, S_q = m_post + d_m0, psd(S_post + d_S0)     # the fix is an additive jump: prior offset carried through
                else:
                    m_q, S_q = m_post + d_m0, psd(S_post + d_S0)
                res[v]['_start'] = (m_q, S_q)
                res[v]['L0'].append(score_state(m_l0v, S_l0v, gt0))
                res[v]['L1start'].append(score_state(m_q, S_q, gts))
                res[v]['tr0'].append([(t, math.sqrt(S[0, 0] + S[1, 1]), math.sqrt(S[2, 2])) for (t, _, S) in tr0[v]])
            tr1 = {}
            for v, p in params_by_variant.items():
                mq, Sq = res[v]['_start']
                tr1[v] = run_leg(p, mq, Sq, cmds1, t_start1, tb, seed=sd + 100, every=every, n=n)
            # reference replay from the RECORDED post-fix state (identity for the reference variant)
            tr1_ref = run_leg(params_by_variant[ref], m_post, S_post, cmds1, t_start1, tb, seed=sd + 100, every=every, n=n)
            for v in params_by_variant:
                d_m1 = tr1[v][-1][1] - tr1_ref[-1][1]; d_S1 = tr1[v][-1][2] - tr1_ref[-1][2]
                m_l1v = m_l1 + d_m1; S_l1v = psd(S_l1 + d_S1)
                res[v]['L1'].append(score_state(m_l1v, S_l1v, gt1))
                res[v]['tr1'].append([(t, math.sqrt(S[0, 0] + S[1, 1]), math.sqrt(S[2, 2])) for (t, _, S) in tr1[v]])
        for v in params_by_variant:
            res[v].pop('_start', None)
            res[v]['fix_time'] = tf
            out[v][k] = res[v]
    return out


def carry_segment(c, k):
    """(t_start, t_end) of the single carry segment of a single-leg stage-probe case."""
    segs = segments(c, k)
    return (segs[0]['t_carry'], segs[0]['t_end']) if segs else (None, None)

def analyse_leg(case_dir, cid, params_by_variant, ref='V0', seed=1, n=2000, every=0.5):
    """Single-leg stage-probe case: recorded start posterior -> leg end, counterfactual = recorded + (variant - reference)."""
    c = load_case(case_dir)
    out = {v: {} for v in params_by_variant}
    for k in ROBOTS:
        t0, t1 = carry_segment(c, k)
        if t0 is None or t1 - t0 < 3.0:
            continue
        b = base_cmds(c['cmds'], k)
        _, m_s, S_s = pf_row(c, k, t0, 'le')
        t1, m_e, S_e = pf_row(c, k, t1, 'le')
        cmds = [x for x in b if t0 - 1e-9 <= x[0] <= t1 + 3.0]
        gt = interp_gt(c, k, [t1])[0]
        tr = {v: run_leg(p, m_s, S_s, cmds, t0, t1, seed=seed, every=every, n=n) for v, p in params_by_variant.items()}
        for v in params_by_variant:
            m = m_e + (tr[v][-1][1] - tr[ref][-1][1]); S = psd(S_e + (tr[v][-1][2] - tr[ref][-1][2]))
            out[v][k] = dict(end=score_state(m, S, gt), start_sd=np.sqrt(np.diag(S_s)),
                             tr=[(t, math.sqrt(S_[0, 0] + S_[1, 1]), math.sqrt(S_[2, 2])) for (t, _, S_) in tr[v]])
    return out
