#!/usr/bin/env python3
"""VIS6 offline replay and evaluation (recipe #1 of the 2026-09-28 literature review, issue #216).

No simulation, render or network inference: the PF replays own commands, own
motion-profile switches, own frame JPEGs (read for the 1c stall test only; classical
image processing) and the cached segmentation column observations ``r3/obs-w6``.
Dev episodes only: any test-split episode is refused.

Subcommands
  run        PF replay of one candidate config for PF seed indices x episodes ->
             <root>/<candidate>/seed<k>/<episode>.estimates.jsonl + .meta.json (full covariance,
             VIS6 diagnostics). Refuses to overwrite.
  reproduce  T0 seed 0 must equal stored VIS3 a1 (xyyaw, both std reports, measured) frame by frame (preflight).
  evaluate   GT scoring (eval_only/frames_eval.jsonl): per candidate, seed and split: 95 % XY ellipse
             coverage, >3 sigma, ANEES (XY full covariance, yaw), NLL, door p90, door lateral p99, door
             yaw p90, sigma p90, over-confident loss events, lost frames, and the 1c detector diagnostic.
  select     pre-registered rules of experiments/2026-09-28-vis6-recipe1/plan_v6.json on an evaluate output.

PF seed index k: k = 0 is the episode seed (the VIS3/VIS4 seed), k >= 1 is episode_seed * 1000 + k.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vision_loc as vl  # noqa: E402
import vision_loc_cli_v5 as cli5  # noqa: E402
import vision_loc_io as vio  # noqa: E402
import vision_pf_v6  # noqa: E402
import vis6_metrics as vm6  # noqa: E402
from vision_loc_score import groups_of  # noqa: E402

mp = vl.mp
PLAN_DIR = vl.ROOT/'experiments'/'2026-09-28-vis6-recipe1'
DEFAULT_PLAN = PLAN_DIR/'plan_v6.json'
DEFAULTS = {'calibration': HERE/'calibration_train.json',
            'checkpoint': vio.PRIMARY_OUT/'model'/'seg-v2'/'seg_lraspp_mbv3.pt',
            'obs': vio.PRIMARY_OUT/'r3'/'obs-w6',
            'baseline_a1': vio.PRIMARY_OUT/'r3'/'dev-grid'/'a1_open'}
SOURCES = ('vision_loc.py', 'vision_pf_v5.py', 'vision_pf_v6.py', 'vision_stall_v6.py', 'vision_motion.py',
           'vision_sigma.py', 'vision_report_v5.py', 'vision_loc_cli_v5.py', 'vision_loc_io.py', 'vis6_metrics.py',
           'replay_v6.py', 'vision_loc_score.py', 'episodes.json', 'episodes_v3.json',
           '../2026-09-26-markerless-probe/markerless_probe.py')


def pf_seed(ep: str, k: int) -> int:
    s = int(vio.episode(ep)['seed'])
    if k < 0:
        raise ValueError('seed index must be >= 0')
    return s if k == 0 else s*1000 + k


def require_dev(episodes) -> None:
    bad = [e for e in episodes if vio.split_of(e) != 'dev']
    if bad:
        raise SystemExit(f'VIS6 replays dev episodes only; refused: {bad}')


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_head() -> str | None:
    try:
        return subprocess.run(['git', '-C', str(HERE), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def source_hashes() -> dict:
    files = [HERE/f for f in SOURCES] + [vl.ROOT/f for f in mp.SHARED_RUNTIME_SHA256]
    return {str(p.resolve().relative_to(vl.ROOT)): vio.sha_file(p) for p in files}


def clean_source_head() -> str:
    head = git_head()
    status = subprocess.run(['git', '-C', str(HERE), 'status', '--porcelain', '--untracked-files=normal'],
                            capture_output=True, text=True, check=True).stdout
    if not head or status.strip():
        raise SystemExit('VIS6 run requires a clean committed worktree')
    return head


def verify_config(plan: dict, name: str, path: Path) -> None:
    if plan['configs_sha256'].get(name) != vio.sha_file(path):
        raise SystemExit(f'{name}: config hash does not match the frozen plan')


def verify_unit(meta_path: Path, est_path: Path, plan: dict, plan_sha: str,
                name: str, ep: str, k: int) -> dict:
    """Fail closed before GT access; return the source identity shared by the entire cohort."""
    if not meta_path.exists():
        raise SystemExit(f'{meta_path}: missing run metadata')
    meta = vio.load_json(meta_path)
    expected = {'candidate': name, 'episode': ep, 'seed_index': k, 'pf_seed': pf_seed(ep, k),
                'plan_sha256': plan_sha, 'failure': None, 'git_dirty': False,
                'module_sha256': plan['module_sha256'], 'estimates_sha256': vio.sha_file(est_path)}
    for key, value in expected.items():
        if key not in meta or meta[key] != value:
            raise SystemExit(f'{meta_path}: {key} mismatch')
    if (meta.get('config', {}).get('sha256') != plan['configs_sha256'].get(name)
            or name not in plan['configs_sha256']):
        raise SystemExit(f'{meta_path}: config hash mismatch')
    if not meta.get('git_head') or meta.get('frames', 0) <= 0 or meta['frames'] != meta.get('frames_written'):
        raise SystemExit(f'{meta_path}: incomplete run or missing source HEAD')
    return {'git_head': meta['git_head'], 'module_sha256': meta['module_sha256']}


# ----------------------------------------------------------------------------- run
class Sink6(cli5.Sink):
    """The VIS5 vision sink; the frame image also goes to the PF (1c stall test)."""

    def frame(self, t, bgr, row):
        o = self.obs[int(row['frame'])]
        if hasattr(self.loc, 'vis6'):
            self.last = self.loc.update_obs(t, o, self.servo, image=bgr)
        else:
            self.last = self.loc.update_obs(t, o, self.servo)
        self.last['n_cols'] = int(o.informative.sum())


def frame_record(row, sink) -> dict:
    e = sink.last
    rec = {'frame': row['frame'], 't': row['t'], 'phase': row['phase'], 'skill_phase': row['skill_phase'],
           'loaded': bool(sink.loc.load.loaded), 's3': int(row['commanded_servo']['3']),
           's6': int(row['commanded_servo']['6']), 'settled': bool(sink.loc.settled(float(row['t'])))}
    rec['vision'] = None if not e.get('initialized') else {
        'xyyaw': [round(e['x'], 5), round(e['y'], 5), round(e['yaw'], 6)], 'cov': e['cov'],
        'std_xy_m': round(e['std_xy_m'], 5), 'std_yaw_rad': round(e['std_yaw_rad'], 5),
        'measured': bool(e.get('measured')), 'n_cols': e.get('n_cols'),
        'ess_pre': (e.get('diag') or {}).get('ess_pre'), 'vis6': e.get('vis6')}
    return rec


def run(args):
    import signal
    signal.signal(signal.SIGTERM, cli5._term_as_exit)
    require_dev(args.episodes)
    plan = vio.load_json(args.plan)
    name = args.candidate or Path(args.config).stem
    verify_config(plan, name, Path(args.config))
    modules, plan_sha = source_hashes(), vio.sha_file(args.plan)
    if modules != plan['module_sha256']:
        raise SystemExit('runtime module hashes do not match the frozen plan')
    head = clean_source_head()
    cfg = vio.load_json(args.config)
    unknown = set(cfg) - {'infer_size', 'obs', 'measurement', 'robust', 'pan_coupling', 'vis6'}
    if unknown:
        raise SystemExit(f'config keys not allowed in VIS6 runs: {sorted(unknown)}')
    vision_pf_v6.validate_vis6(cfg.get('vis6'))
    m1_cal, m1_prov = mp.load_m1_calibration()
    ctx = {'m1': mp.load_m1_localizer(), 'params': m1_cal['params'], 'static': vio.load_map(),
           'cal': vio.load_json(args.calibration), 'ckpt_sha': vio.sha_file(args.checkpoint)}
    obs_params = vio.config_obs_params(cfg)
    for k in args.seeds:
        out = Path(args.output)/name/f'seed{k}'
        out.mkdir(parents=True, exist_ok=True)
        for ep in args.episodes:
            if (clean_source_head() != head or source_hashes() != modules
                    or vio.sha_file(args.plan) != plan_sha):
                raise SystemExit('source/plan changed during the cohort')
            verify_config(plan, name, Path(args.config))
            if (out/f'{ep}.estimates.jsonl').exists() or (out/f'{ep}.meta.json').exists():
                raise SystemExit(f'refusing to overwrite {out}/{ep}')
            obs, _ = vio.load_obs(Path(args.obs)/f'{ep}.obs.npz', kind='vision', episode=ep, obs_params=obs_params,
                                  checkpoint_sha256=ctx['ckpt_sha'], infer_size=vio.config_infer_size(cfg))
            seed = pf_seed(ep, k)
            loc = vision_pf_v6.make_vis6_pf(
                ctx['m1'], ctx['static'], ctx['params'], cfg.get('measurement', {}), cfg.get('obs', {}),
                ctx['cal']['sag'], seed, ctx['cal'].get('pan_base_yaw') if cfg.get('pan_coupling', True) else None,
                cfg.get('robust', {}), None, None, None, cfg.get('vis6'))
            sink = Sink6(loc, 'vision', obs)
            loc.init_gaussian((cli5.DOCK_X, vio.spawn_y(ep), cli5.DOCK_YAW), cli5.DOCK_STD)
            rows, t0, failure, n = [], time.time(), None, 0
            load0 = list(os.getloadavg())
            try:
                n = vl.replay(vio.RENDER_ROOT/ep, [sink], on_frame=lambda i, row: rows.append(frame_record(row, sink)))
                if (clean_source_head() != head or source_hashes() != modules
                        or vio.sha_file(args.plan) != plan_sha):
                    raise RuntimeError('source/plan changed during the run unit')
                verify_config(plan, name, Path(args.config))
            except BaseException as exc:
                failure = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                cli5._write_estimates(out/(f'{ep}.estimates.jsonl' if failure is None else f'{ep}.estimates.partial.jsonl'),
                                      rows)
                meta = {'schema': vision_pf_v6.SCHEMA, 'candidate': name, 'episode': ep, 'seed_index': k,
                        'pf_seed': seed, 'frames': n, 'frames_written': len(rows), 'failure': failure,
                        'wall_s': round(time.time() - t0, 1), 'load_average_start': load0,
                        'load_average_end': list(os.getloadavg()), 'git_head': head, 'git_dirty': False,
                        'estimates_sha256': vio.sha_file(out/(f'{ep}.estimates.jsonl' if failure is None
                                                           else f'{ep}.estimates.partial.jsonl')),
                        'stats': dict(loc.stats), 'vis6_active': hasattr(loc, 'vis6'),
                        'dock': [cli5.DOCK_X, vio.spawn_y(ep), cli5.DOCK_YAW], 'dock_std': list(cli5.DOCK_STD),
                        'config': {'path': str(args.config), 'sha256': vio.sha_file(args.config), 'value': cfg},
                        'calibration': {'path': str(args.calibration), 'sha256': vio.sha_file(args.calibration)},
                        'checkpoint_sha256': ctx['ckpt_sha'], 'obs_dir': str(args.obs),
                        'map': {'file': str(vio.MAP_FILE.relative_to(mp.ROOT)), 'sha256': vio.sha_file(vio.MAP_FILE)},
                        'm1_calibration': m1_prov,
                        'm1_localizer': {'source': f'{mp.M1_SHA}:{mp.M1_LOCALIZER}', 'sha256': mp.M1_LOCALIZER_SHA256},
                        'module_sha256': modules, 'plan_sha256': plan_sha}
                (out/f'{ep}.meta.json').write_text(json.dumps(meta, indent=1))
            print(f'{name} seed{k} {ep}: {n} frames, {meta["wall_s"]} s, stats {meta["stats"]}', flush=True)


# ----------------------------------------------------------------------------- reproduce
def same_estimate(a, b) -> bool:
    if a['frame'] != b['frame'] or a['t'] != b['t']:
        return False
    av, bv = a['vision'], b['vision']
    if av is None or bv is None:
        return av == bv
    keys = ('xyyaw', 'std_xy_m', 'std_yaw_rad', 'measured')
    return all(k in av and k in bv and av[k] == bv[k] for k in keys)


def reproduce(args):
    """Framewise reproduction of xyyaw, both std reports and the measured flag."""
    require_dev(args.episodes)
    report, bad = {}, 0
    for ep in args.episodes:
        a = vl.read_jsonl(Path(args.baseline)/f'{ep}.estimates.jsonl')
        b = vl.read_jsonl(Path(args.root)/args.candidate/'seed0'/f'{ep}.estimates.jsonl')
        diff = sum(1 for x, y in zip(a, b) if not same_estimate(x, y))
        diff += abs(len(a) - len(b))
        report[ep] = {'frames': len(a), 'mismatches': diff}
        bad += diff
    out = {'pass': bad == 0, 'episodes': report, 'baseline': str(args.baseline)}
    _write_new(args.output, out)
    print(json.dumps(out, indent=1))
    if bad:
        raise SystemExit('T0 does not reproduce the VIS3 a1 estimates: STOP (see the VIS6 plan)')


# ----------------------------------------------------------------------------- evaluate
def _write_new(path, obj) -> None:
    p = Path(path)
    if p.exists():
        raise SystemExit(f'refusing to overwrite {p}')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1))


def episode_rows(est_path: Path, gt: dict) -> tuple[list, list]:
    """(frame rows for ``summarize``, frame pairs for ``stall_diagnostic``) of one estimates file."""
    rows, pairs, prev = [], [], None
    for rec in vl.read_jsonl(est_path):
        v = rec['vision']
        g = gt[rec['frame']]
        if v is None:
            raise SystemExit(f'{est_path}: uninitialized frame {rec["frame"]}')
        r = vm6.frame_terms(v['xyyaw'], v['cov'], g)
        r.update(frame=rec['frame'], t=float(rec['t']), groups=groups_of(rec, g))
        rows.append(r)
        st = (v.get('vis6') or {}).get('stall')
        if st and st.get('pred_m') is not None and prev is not None:
            if abs(float(st['prev_t']) - float(prev[0])) > 1e-6:
                raise SystemExit(f'{est_path}: stall pair at frame {rec["frame"]} is not the previous frame')
            pairs.append({'decision': st['decision'], 'dt': float(rec['t']) - float(prev[0]),
                          'pred_m': float(st['pred_m']), 'pred_yaw_rad': float(st['pred_yaw_rad']),
                          'gt_yaw_rad': vm6.wrap(g[2] - prev[1][2]), 'gt_m': math.hypot(g[0] - prev[1][0], g[1] - prev[1][1])})
        prev = (float(rec['t']), g)
    return rows, pairs


def evaluate(args):
    plan = json.loads(Path(args.plan).read_text())
    splits = {'fit': plan['split']['fit'], 'validation': plan['split']['validation']}
    wanted = set(args.episodes) if args.episodes else None
    require_dev([e for s in splits.values() for e in s])
    gt_cache: dict = {}
    provenance = None
    out = {'schema': 'ugrp.vision_loc.vis6.metrics.v1', 'plan_sha256': vio.sha_file(args.plan),
           'root': str(args.root), 'candidates': {}}
    for name in args.candidates:
        cand = {}
        for split, eps in splits.items():
            eps = [e for e in eps if wanted is None or e in wanted]
            if not eps:
                continue
            per_seed, pairs_all = {}, []
            for k in args.seeds:
                d = Path(args.root)/name/f'seed{k}'
                missing = [e for e in eps if not (d/f'{e}.estimates.jsonl').exists()]
                if missing:
                    if args.allow_missing:
                        continue
                    raise SystemExit(f'{d}: missing complete estimates for {missing} (partial sets are not scored)')
                episodes = {}
                for ep in eps:
                    signature = verify_unit(d/f'{ep}.meta.json', d/f'{ep}.estimates.jsonl', plan,
                                            out['plan_sha256'], name, ep, k)
                    if provenance is not None and signature != provenance:
                        raise SystemExit('mixed git_head/module_sha256 across run units')
                    provenance = signature
                    if ep not in gt_cache:
                        gt_cache[ep] = {r['frame']: r['gt']
                                        for r in vl.read_jsonl(vio.RENDER_ROOT/ep/'eval_only'/'frames_eval.jsonl')}
                    rows, pairs = episode_rows(d/f'{ep}.estimates.jsonl', gt_cache[ep])
                    if len(rows) != len(gt_cache[ep]):
                        raise SystemExit(f'{d}/{ep}: {len(rows)} rows for {len(gt_cache[ep])} frames')
                    episodes[ep] = rows
                    if k == 0:     # unique frame pairs, not three copies across PF seeds
                        pairs_all += pairs
                per_seed[f'seed{k}'] = vm6.summarize(episodes)
            if not per_seed:
                continue
            cand[split] = {'episodes': eps, 'per_seed': per_seed, 'seed_mean': vm6.seed_mean(per_seed),
                           'stall_diagnostic': vm6.stall_diagnostic(pairs_all) if pairs_all else None}
        out['candidates'][name] = cand
    out['provenance'] = provenance
    _write_new(args.output, out)
    for name, c in out['candidates'].items():
        for split, s in c.items():
            m = s['seed_mean']['mean']
            print(f"{name:28s} {split:10s} seeds={len(s['per_seed'])} cov95={m['coverage95_xy']:.4f} "
                  f"x3={m['exceed3_xy']:.4f} ANEES={m['anees_xy']:.2f} NLL={m['nll_xy']:.3f} "
                  f"door_p90={m['door_pos_p90_m']} lat_p99={m['door_lat_p99_m']} events={m['events']}")


# ----------------------------------------------------------------------------- select
def select(args):
    plan = json.loads(Path(args.plan).read_text())
    met = json.loads(Path(args.metrics).read_text())
    if met.get('plan_sha256') != vio.sha_file(args.plan):
        raise SystemExit('metrics were computed under a different plan file')
    c = met['candidates']
    split = 'validation' if args.stage == 'final' else 'fit'
    seeds = plan['seeds']['final_validation' if args.stage == 'final' else 'selection_fit']
    names = list(args.candidates)
    if args.stage in ('lowest-nll', 'final') and args.baseline not in names:
        names.append(args.baseline)
    for name in names:
        block = c.get(name, {}).get(split, {})
        if (block.get('episodes') != plan['split'][split]
                or set(block.get('per_seed', {})) != {f'seed{k}' for k in seeds}):
            raise SystemExit(f'{name}: incomplete {split} episodes/seeds for selection')
    if args.stage == 'calibration':
        stats = {n: c[n]['fit']['seed_mean']['mean'] for n in args.candidates}
        res = vm6.select_calibrated(stats, args.candidates, tuple(plan['rules']['coverage95_band']))
    elif args.stage == 'lowest-nll':
        stats = {n: c[n]['fit']['seed_mean']['mean'] for n in args.candidates}
        res = vm6.select_gating(stats, args.candidates, c[args.baseline]['fit']['seed_mean']['mean'],
                                 plan['rules']['gating_accuracy_worse_max'])
    elif args.stage == 'detector':
        d = c[args.candidates[0]]['fit']['stall_diagnostic'] or {}
        r = plan['rules']['detector_gate']
        ok = (d.get('positives', 0) >= r['min_positives'] and (d.get('precision') or 0.) >= r['min_precision']
              and (d.get('recall') or 0.) >= r['min_recall'])
        res = {'pass': ok, 'diagnostic': d, 'gate': r}
    else:   # final
        base = c[args.baseline]['validation']['seed_mean']['mean']
        res = {'baseline': args.baseline, 'results': {}}
        for n in args.candidates:
            res['results'][n] = vm6.validation_gate(c[n]['validation']['seed_mean']['mean'], base,
                                                    plan['rules']['validation'])
        passing = [n for n in args.candidates if res['results'][n]['pass']]
        res['chosen'] = (min(passing, key=lambda n: (round(c[n]['validation']['seed_mean']['mean']['nll_xy'], 9),
                                                     args.candidates.index(n))) if passing else None)
        res['decision'] = res['chosen'] or f'keep {args.baseline} (b0); no VIS6 candidate adopted'
    res['stage'] = args.stage
    res['metrics_sha256'] = vio.sha_file(args.metrics)
    _write_new(args.output, res)
    print(json.dumps({k: v for k, v in res.items() if k != 'table'}, indent=1, default=str)[:4000])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--config', required=True)
    r.add_argument('--candidate', help='name (default: the config file stem)')
    r.add_argument('--seeds', type=int, nargs='+', required=True, help='PF seed indices')
    r.add_argument('--episodes', nargs='+', required=True)
    r.add_argument('--calibration', default=str(DEFAULTS['calibration']))
    r.add_argument('--checkpoint', default=str(DEFAULTS['checkpoint']), help='hash check of the observation cache only')
    r.add_argument('--obs', default=str(DEFAULTS['obs']))
    r.add_argument('--plan', default=str(DEFAULT_PLAN))
    r.add_argument('--output', required=True)
    p = sub.add_parser('reproduce')
    p.add_argument('--root', required=True)
    p.add_argument('--candidate', default='T0')
    p.add_argument('--baseline', default=str(DEFAULTS['baseline_a1']))
    p.add_argument('--episodes', nargs='+', required=True)
    p.add_argument('--output', required=True)
    e = sub.add_parser('evaluate')
    e.add_argument('--root', required=True)
    e.add_argument('--candidates', nargs='+', required=True)
    e.add_argument('--seeds', type=int, nargs='+', required=True)
    e.add_argument('--episodes', nargs='*', help='restrict to these episodes (default: the plan splits)')
    e.add_argument('--allow-missing', action='store_true', help='skip seeds without a complete episode set')
    e.add_argument('--plan', default=str(DEFAULT_PLAN))
    e.add_argument('--output', required=True)
    s = sub.add_parser('select')
    s.add_argument('--metrics', required=True)
    s.add_argument('--stage', required=True, choices=('calibration', 'lowest-nll', 'detector', 'final'))
    s.add_argument('--candidates', nargs='+', required=True, help='in the pre-registered preference order')
    s.add_argument('--baseline', default='T0')
    s.add_argument('--plan', default=str(DEFAULT_PLAN))
    s.add_argument('--output', required=True)
    args = ap.parse_args(argv)
    {'run': run, 'reproduce': reproduce, 'evaluate': evaluate, 'select': select}[args.cmd](args)


if __name__ == '__main__':
    main()
