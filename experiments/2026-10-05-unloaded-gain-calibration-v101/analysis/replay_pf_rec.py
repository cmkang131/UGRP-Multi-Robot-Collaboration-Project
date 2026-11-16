#!/usr/bin/env python3
"""Offline replay of one robot's recorded own inputs (RGB frames + own issued commands) through the v98 provider.

Evaluation only. Ground truth is NOT read here (scored later by analyze_pf.py). The provider is built exactly as the
live run built it (build_provider -> DelayedPoseSource(HighPoseSource)), the event order is the live order
(frame at tick t -> commands stamped t -> relocalisation request), so the PF random stream is reproduced bit for bit.

usage: replay_pf.py RAWDIR ROBOT OUT.jsonl [--pfc JSON] [--module-dir DIR] [--until T]
  RAWDIR   case directory holding robots/<rid>/{frames,commands}.jsonl and student_record.json
  --pfc    JSON dict replacing pf_consistency.CONFIG (e.g. the NEUTRAL config) for a what-if run
  --patch  python file executed after import (monkeypatches for variants); must define patch(provider)
"""
import argparse, copy, json, os, sys, time, importlib.util
os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
sys.dont_write_bytecode = True
WT = os.environ.get('PF_REPLAY_WT', '/Users/changmin/projects/ugrp-wt/pair-carry-highpose')   # default: the #363 worktree (read only)
sys.path.insert(0, WT)
os.chdir(WT)
import numpy as np
import cv2

ap = argparse.ArgumentParser()
ap.add_argument('raw'); ap.add_argument('robot'); ap.add_argument('out')
ap.add_argument('--pfc', default=None)
ap.add_argument('--patch', default=None)
ap.add_argument('--until', type=float, default=1e9)
ap.add_argument('--probe-every', type=int, default=0, help='every Nth applied scan: likelihood-only pose probe vs truth (diagnostic, eval only)')
ap.add_argument('--profile-times', default='', help='comma list of SIM times: at the first applied scan >= each, emit a 1-D likelihood profile along x and y through the TRUE pose (diagnostic, eval only)')
ap.add_argument('--nomeasure', action='store_true', help='reject every frame: pure dead reckoning of the same PF')
ap.add_argument('--seed-offset', type=int, default=0, help='added to the recorded provider seed (ensemble over PF randomness; 0 = bit-exact live replay)')
ap.add_argument('--extra-reloc', default='', help='comma list of frame SIM times at which to ALSO call begin_relocalization (counterfactual: a rejected arrival), first frame >= t')
ap.add_argument('--cal-path', default=None, help='override the recorded calibration file (candidate calibration replay; evaluation only)')
ap.add_argument('--cal-sha', default=None, help='sha256 of --cal-path (must be admitted by the tree registry)')
ap.add_argument('--arm-reloc', action='store_true', help='every (recorded or --extra-reloc) relocalization is a REJECTED ARRIVAL: arm the one-shot belief expansion through the production helper zone_pair_highpose_arrival_confirm.request_belief_expansion before it (no-op on trees without the hook)')
ap.add_argument('--every', type=int, default=1, help='write a per-frame row every N released frames')
args = ap.parse_args()

from harness import zone_pair_highpose_contract as contract
from harness import vision_pose_source_highpose as hp
from harness import zone_pair_highpose_pf_consistency as pfc
from harness import zone_pair_highpose_arrival_confirm as arrival

raw = args.raw
rid = args.robot
rec = json.load(open(f'{raw}/student_record.json'))
prov = rec['robots'][rid]['provider']['provider']
cal_path, cal_sha = prov['m1_calibration']['path'], prov['m1_calibration']['file_sha256']
seed = prov['seed']
if args.cal_path:
    assert args.cal_sha, '--cal-path needs --cal-sha'
    cal_path, cal_sha = args.cal_path, args.cal_sha
static = json.load(open(f'{raw}/inputs/static_map.json'))
static_map, _, _ = contract.resolve(static['map_id'])
assert static_map == static, 'recorded static map differs from the registered one'

if args.pfc:
    pfc.CONFIG = json.loads(args.pfc) if args.pfc.startswith('{') else getattr(pfc, args.pfc)
    hp.pf_consistency.CONFIG = pfc.CONFIG
if args.patch:
    spec = importlib.util.spec_from_file_location('variant_patch', args.patch)
    vmod = importlib.util.module_from_spec(spec); spec.loader.exec_module(vmod)
    vmod.pre_build(hp, pfc)
else:
    vmod = None

dsrc = hp.build_provider(static_map, cal_path, cal_sha, seed + args.seed_offset)
inner = dsrc.provider
pf = inner.loc._pf
pr = prov['prior']
dsrc.init_prior(pr['mean'], pr['std'], source=pr['source'])
if vmod is not None:
    vmod.post_build(inner, pf)
if args.nomeasure:
    from harness.vision_loc_client import FrameRejected
    def _reject(bgr):
        raise FrameRejected('nomeasure')
    inner.worker.observe = _reject
runtime_contract = copy.deepcopy(inner.runtime_contract)

out = open(args.out, 'w')
def emit(kind, **row):
    row['kind'] = kind
    out.write(json.dumps(row) + '\n')

# ---- per applied scan instrumentation (outermost apply_scan = consistency view_apply)
state = pf.pf_consistency['state']
cap = {}
orig_loglik = pf.scan_loglik
def spy_loglik(obs, pose):
    ll, n = orig_loglik(obs, pose)
    cap['n_terms'] = int(n); cap['ll_min'] = float(ll.min()); cap['ll_max'] = float(ll.max())
    cap['alpha_used'] = float(state['alpha'])
    return ll, n
pf.scan_loglik = spy_loglik

def scale_stats():
    w = np.exp(pf.logw - pf.logw.max()); w /= w.sum()
    m = (w[:, None]*pf.scale).sum(0)
    sd = np.sqrt((w[:, None]*(pf.scale - m)**2).sum(0))
    return m.tolist(), sd.tolist(), np.asarray(pf.scale).std(0).tolist()

def moments():
    w = np.exp(pf.logw - pf.logw.max()); w /= w.sum()
    yaw = float(np.arctan2(np.sum(w*np.sin(pf.px[:, 2])), np.sum(w*np.cos(pf.px[:, 2]))))
    mean = np.array([float(np.sum(w*pf.px[:, 0])), float(np.sum(w*pf.px[:, 1]))])
    d = pf.px[:, :2] - mean
    cov = (w[:, None]*d).T @ d/max(1.-float(np.sum(w*w)), 1e-9)
    return mean, cov, yaw, float(1./np.sum(w*w))


# ---- diagnostic: where does ONE view's (tempered) likelihood peak relative to the recorded truth? (evaluation only)
probe_n = [0]
tr_probe = None
if args.probe_every or args.profile_times:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from analyze_pf import load_truth, truth_at, wrap as awrap
    tr_probe = load_truth(raw, rid)
    from harness import vision_loc_protocol as vp
    vl_mod, _ = vp.load_vis3()
    E0 = float(pf.measurement['effective_columns']); E1 = float(pfc.CONFIG['effective_columns'])
    DX = np.arange(-0.20, 0.2001, 0.01); DY = np.arange(-0.06, 0.0601, 0.01); DP = np.arange(-0.02, 0.0201, 0.005)

def lik_probe(t, obs, p):
    gx, gy, gyaw = truth_at(tr_probe, t)
    off = vl_mod.pan_yaw(pf.pan_table, pf.load.loaded, p)
    psi0 = awrap(gyaw - off)
    X, Y, P = np.meshgrid(DX, DY, DP, indexing='ij')
    grid = np.column_stack([gx + X.ravel(), gy + Y.ravel(), psi0 + P.ravel()])
    vb, vt = pf.expected(grid, p)
    ll, n = vl_mod.column_loglik(vb, vt, obs, {**pf.measurement, 'use_top_edge': pf.obs_params['use_top_edge']}, per_column=True)
    n = max(int(n), 1)
    ll = ll*(min(1., E1/n)/min(1., E0/n))            # alpha = 1 (first scan of a view), tempered columns
    L = ll.reshape(X.shape)
    i0 = (len(DX)//2, len(DY)//2, len(DP)//2)
    imax = np.unravel_index(int(np.argmax(L)), L.shape)
    l_true = float(L[i0]); l_max = float(L[imax])
    # curvature at the argmax (finite differences, step 1 cell) -> likelihood-implied sigma
    def d2(a, b):
        i = list(imax)
        def v(da, db):
            j = list(i); j[a] = min(max(j[a]+da, 0), L.shape[a]-1); j[b] = min(max(j[b]+db, 0), L.shape[b]-1)
            return L[tuple(j)]
        if a == b:
            return v(1, 0) - 2*L[tuple(i)] + v(-1, 0)
        return (v(1, 1) - v(1, -1) - v(-1, 1) + v(-1, -1))/4.
    h = np.array([[d2(a, b) for b in range(3)] for a in range(3)])
    steps = np.array([0.01, 0.01, 0.005])
    H = -h/np.outer(steps, steps)
    try:
        cov = np.linalg.inv(H); sig = np.sqrt(np.maximum(np.diag(cov), 0))
        pd = bool(np.all(np.linalg.eigvalsh(H) > 0))
    except np.linalg.LinAlgError:
        sig = [float('nan')]*3; pd = False
    on_edge = bool(imax[0] in (0, len(DX)-1) or imax[1] in (0, len(DY)-1))
    return dict(truth=[gx, gy, gyaw], argmax_off=[float(DX[imax[0]]), float(DY[imax[1]]), float(DP[imax[2]])],
                ll_true=l_true, ll_max=l_max, chi2_3=2*(l_max-l_true), sigma_lik=[float(v) for v in sig], pd=pd,
                edge=on_edge, n_terms=int(n), temper=float(min(1., E1/n)/min(1., E0/n)))


prof_times = sorted(float(v) for v in args.profile_times.split(',') if v.strip())
def lik_profile(t, obs, p):
    """tempered view log-likelihood along x (y, yaw at truth) and along y (x, yaw at truth), relative to the value at the true pose"""
    gx, gy, gyaw = truth_at(tr_probe, t)
    off = vl_mod.pan_yaw(pf.pan_table, pf.load.loaded, p)
    psi0 = awrap(gyaw - off)
    out = {'truth': [float(gx), float(gy), float(gyaw)]}
    for name, axis in (('x', 0), ('y', 1)):
        d = np.arange(-0.25, 0.2501, 0.005)
        g = np.column_stack([np.full_like(d, gx), np.full_like(d, gy), np.full_like(d, psi0)])
        g[:, axis] += d
        vb, vt = pf.expected(g, p)
        ll, n = vl_mod.column_loglik(vb, vt, obs, {**pf.measurement, 'use_top_edge': pf.obs_params['use_top_edge']}, per_column=True)
        n = max(int(n), 1)
        ll = ll*(min(1., E1/n)/min(1., E0/n))
        out[name] = {'d': [round(float(v), 4) for v in d], 'dll': [round(float(v), 4) for v in (ll - ll[len(d)//2])]}
    out['n_terms'] = int(n)
    return out

orig_apply = pf.apply_scan
def spy_apply(t, obs, p):
    m0, c0, y0, e0 = moments()
    k_before = state['k']
    cap.clear()
    res0 = pf.stats['resamples']
    r = orig_apply(t, obs, p)
    m1, c1, y1, e1 = moments()
    probe_row = None
    if args.probe_every:
        probe_n[0] += 1
        if probe_n[0] % args.probe_every == 0 or state['k'] == 1:
            try:
                probe_row = lik_probe(float(t), obs, p)
            except Exception as exc:   # diagnostic only
                probe_row = {'error': f'{type(exc).__name__}: {exc}'}
    if prof_times and float(t) >= prof_times[0]:
        prof_times.pop(0)
        try:
            emit('profile', t=float(t), pf_mean=m0.tolist(), **lik_profile(float(t), obs, p))
        except Exception as exc:
            emit('profile', t=float(t), error=f'{type(exc).__name__}: {exc}')
    emit('scan', t=float(t), pre_mean=m0.tolist(), pre_cov=c0.tolist(), post_mean=m1.tolist(), post_cov=c1.tolist(),
         ess_pre=e0, ess_post=e1, k=state['k'], new_view=bool(state['k'] == 1), **cap,
         loaded=bool(pf.load.loaded), vel=np.asarray(pf.vel).tolist(), odo_d=float(state['odo_d']),
         pose={str(a): b for a, b in p.items()}, n_cols=int(obs.informative.sum()),
         scale_post=scale_stats()[0:2], diag={k: v for k, v in pf.diag.items() if k in ('fit', 'gain', 'ess_pre', 'n_terms')},
         probe=probe_row)
    return r
pf.apply_scan = spy_apply

# ---- inputs
frames = [json.loads(l) for l in open(f'{raw}/robots/{rid}/frames.jsonl')]
cmds = [e['row'] for e in prov['lifecycle'] if e['event'] == 'own_command']
reloc = [e for e in prov['lifecycle'] if e['event'] == 'begin_relocalization']
reloc_now = sorted(round(e['t'] + 0.16, 2) for e in reloc)    # DelayedPoseSource: provider sees cutoff = now - .16
ci = 0
# commands after the last released frame were queued but never released; feed all port commands (harmless: held in heap)
port = [json.loads(l) for l in open(f'{raw}/robots/{rid}/commands.jsonl')]
assert port[:len(cmds)] == cmds
cmds = port
issued_servo = {}
reloc_i = 0
extra_now = sorted(float(x) for x in args.extra_reloc.split(',') if x)
extra_i = 0
t0 = time.time()
n = 0
while ci < len(cmds) and cmds[ci]['kind'] == 'initial_servo_command':      # issued at setup, before the first capture
    dsrc.on_command(cmds[ci]); ci += 1
for f in frames:
    ft = float(f['sim_time'])
    if ft > args.until:
        break
    rgb = cv2.cvtColor(cv2.imread(f'{raw}/{f["path"]}', cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    before = dict(inner.counts)
    dsrc.on_frame(ft, rgb)
    n += 1
    if n % args.every == 0 or True:
        est = inner.loc.estimate()
        emit('frame', tnow=ft, t=float(inner.loc._pf.t), initialized=bool(est.get('initialized')),
             x=est.get('x'), y=est.get('y'), yaw=est.get('yaw'), cov=est.get('cov'), std_xy=est.get('std_xy_m'),
             std_yaw=est.get('std_yaw_rad'), n_eff=est.get('n_eff'), since_scan=est.get('since_scan_s'),
             measured=inner.counts['measured'], view_k=state['k'], servo=dict(inner.servo),
             stats={k: v for k, v in pf.stats.items()}, scale=scale_stats(),
             vel=np.asarray(pf.vel).tolist(), px_std=np.asarray(pf.px).std(0).tolist())
    while ci < len(cmds) and abs(cmds[ci]['t'] - ft) < 1e-9:
        row = cmds[ci]
        dsrc.on_command(row)
        ci += 1
    while reloc_i < len(reloc_now) and abs(reloc_now[reloc_i] - ft) < 1e-6:
        if args.arm_reloc and hasattr(arrival, 'request_belief_expansion'):
            arrival.request_belief_expansion(dsrc)
        dsrc.begin_relocalization(ft, {})
        if args.arm_reloc and hasattr(arrival, 'clear_belief_expansion'):
            arrival.clear_belief_expansion(dsrc)
        emit('reloc', now=ft, **{k: v for k, v in inner.lifecycle[-1].items() if k in ('before', 'after', 'previous_fix_t', 't', 'expansion_radius', 'belief_preserved')})
        reloc_i += 1
    while extra_i < len(extra_now) and ft >= extra_now[extra_i] - 1e-9:
        if args.arm_reloc and hasattr(arrival, 'request_belief_expansion'):
            arrival.request_belief_expansion(dsrc)
        dsrc.begin_relocalization(ft, {})
        if args.arm_reloc and hasattr(arrival, 'clear_belief_expansion'):
            arrival.clear_belief_expansion(dsrc)
        emit('reloc', now=ft, extra=True, **{k: v for k, v in inner.lifecycle[-1].items() if k in ('before', 'after', 'previous_fix_t', 't', 'expansion_radius', 'belief_preserved')})
        extra_i += 1
    if n % 300 == 0:
        print(rid, 'frame', n, 'sim_t', round(ft, 2), 'wall', round(time.time()-t0, 1), flush=True)

emit('final', stats=dict(pf.stats), counts=dict(inner.counts), runtime_contract=runtime_contract,
     recorded_stats=prov['localizer_stats'], recorded_counts=prov['counts'])
out.close()
print(rid, 'done', 'wall', round(time.time()-t0, 1), 'stats', pf.stats)
print(rid, 'recorded', prov['localizer_stats'])
