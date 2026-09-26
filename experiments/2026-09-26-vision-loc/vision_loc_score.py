"""GT scoring of the vision localization estimates (eval-only: reads ``eval_only/frames_eval.jsonl``).

Metrics per filter, episode and frame group (door zone, loaded, ...), lateral
error, recovery events (lost / recovered / injections), and false detections of
the learned column observations against the teacher-label ones. The registered
test set of a round is scored once, into that round's metrics file only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import vision_loc as vl
from vision_loc_io import (HERE, ROUNDS, config_infer_size, config_obs_params, load_json, load_obs, require_frozen,
                           sha_file, test_round)
import vision_loc_io as vio

DOOR_X = 2.2                                   # door_1 plane (static map)


def ang(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def pct(a, q):
    return None if len(a) == 0 else round(float(np.percentile(a, q)), 4)


def summary(errs):
    e = np.asarray([x[0] for x in errs])
    y = np.asarray([x[1] for x in errs])
    lat = np.asarray([x[2] for x in errs])
    return {'n': int(e.size), 'pos_p50_m': pct(e, 50), 'pos_p90_m': pct(e, 90), 'pos_p95_m': pct(e, 95),
            'pos_p99_m': pct(e, 99), 'pos_max_m': None if e.size == 0 else round(float(e.max()), 4),
            'lat_abs_p90_m': pct(lat, 90), 'lat_abs_p99_m': pct(lat, 99),
            'yaw_p50_deg': pct(y, 50), 'yaw_p90_deg': pct(y, 90),
            'share_pos_lt_5cm': None if e.size == 0 else round(float(np.mean(e < .05)), 4),
            'share_pos_lt_10cm': None if e.size == 0 else round(float(np.mean(e < .10)), 4)}


def near_door(gt) -> bool:
    """PR #210's door-vicinity box around door_1 (GT position)."""
    return abs(gt[0] - DOOR_X) < .6 and -.45 < gt[1] < .55


def groups_of(rec, gt) -> list[str]:
    g = ['all', 'loaded' if rec['loaded'] else 'unloaded']
    if near_door(gt):
        g += ['door_zone', 'door_loaded' if rec['loaded'] else 'door_unloaded']
    else:                                       # PR #210 groups (door zone first)
        sp = rec['skill_phase'] or ''
        g.append('carry' if sp in ('nav_preplace', 'to_carry_posture', 'pre_release') else
                 'manipulate' if sp in ('grasp', 'nav_pregrasp', 'release') else
                 'look_back' if sp == 'look_back' else 'search_approach')
    return g


def false_detections(vis: vl.ColumnObs, orc: vl.ColumnObs, tol_px: float) -> dict:
    """Column-level disagreement of the learned observations with the teacher-label ones."""
    out = {}
    for part in ('b', 't'):
        kv, ko = getattr(vis, f'{part}_kind'), getattr(orc, f'{part}_kind')
        lv = getattr(vis, f'{part}_lo')              # a sharp edge: lo == hi
        lo, ho = getattr(orc, f'{part}_lo'), getattr(orc, f'{part}_hi')
        det = kv == vl.EDGE
        with np.errstate(invalid='ignore'):
            # a learned sharp edge counts as false when the teacher interval (+- tol) does not contain it
            bad = det & ~((ko != vl.NONE) & (lv >= np.nan_to_num(lo, nan=vl.NEG_INF) - tol_px)
                          & (lv <= np.nan_to_num(ho, nan=vl.POS_INF) + tol_px))
            missed = (ko == vl.EDGE) & (kv == vl.NONE)
        out[part] = {'edges': int(det.sum()), 'false_edges': int(bad.sum()), 'teacher_edges': int((ko == vl.EDGE).sum()),
                     'missed_edges': int(missed.sum())}
    return out


LOST_M, OK_M = .30, .10


def recovery_summary(rows: list) -> dict:
    """Lost / recovered episodes of one filter from (t, position error, diag) rows in time order.

    lost: error > 0.30 m; a recovery is a return below 0.10 m after being lost;
    an injection while the error is below 0.10 m counts as a false trigger.
    """
    lost_frames = recoveries = inj = inj_ok = injected = 0
    lost, lost_since, longest = False, None, 0.
    for t, err, diag in rows:
        n = int((diag or {}).get('injected') or 0)
        if n:
            inj += 1
            injected += n
            inj_ok += int(err < OK_M)
        if err > LOST_M:
            lost_frames += 1
            if not lost:
                lost, lost_since = True, t
        elif lost and err < OK_M:
            recoveries += 1
            longest = max(longest, t - lost_since)
            lost = False
    if lost:
        longest = max(longest, rows[-1][0] - lost_since)
    return {'lost_frames': lost_frames, 'recoveries': recoveries, 'ends_lost': lost,
            'longest_lost_s': round(longest, 1), 'injection_frames': inj, 'injected_particles': injected,
            'injection_frames_while_ok': inj_ok, 'thresholds_m': {'lost': LOST_M, 'ok': OK_M}}


def _score_guard(args) -> None:
    out_path = Path(args.output)
    if out_path.exists():
        raise SystemExit(f'refusing to overwrite {out_path}')
    rnd = test_round(args.episodes)
    if rnd is not None:
        metrics = HERE/ROUNDS[rnd]['metrics']
        if metrics.exists():
            raise SystemExit(f'test refused: the registered test set was already scored ({metrics.name})')
        if out_path.resolve() != metrics.resolve():
            raise SystemExit(f'test refused: the registered test scoring writes only {metrics.relative_to(HERE)}')
        pre = json.loads((HERE/ROUNDS[rnd]['prereg']).read_text()) if (HERE/ROUNDS[rnd]['prereg']).exists() else {}
        if sorted(args.episodes) != sorted(pre.get('test_episodes', [])):
            raise SystemExit('test refused: score exactly the registered test episodes, all at once')
        require_frozen(args.episodes, config=args.config, checkpoint=args.checkpoint,
                       needs=('config', 'checkpoint') if args.obs else ())
    if bool(args.obs) != bool(args.oracle_obs):
        raise SystemExit('false-detection scoring needs both --obs and --oracle-obs (or neither)')
    if args.obs and not (args.config and args.checkpoint):
        raise SystemExit('--obs scoring needs --config and --checkpoint (observation provenance check)')


def _episode_errors(est_dir: Path, ep: str, pooled: dict) -> tuple[dict, dict]:
    est = vl.read_jsonl(est_dir/f'{ep}.estimates.jsonl')
    ev = {r['frame']: r for r in vl.read_jsonl(vio.RENDER_ROOT/ep/'eval_only'/'frames_eval.jsonl')}
    if len(est) != len(ev):
        raise SystemExit(f'{ep}: {len(est)} estimate rows for {len(ev)} frames')
    per: dict = {}
    trace: dict = {}
    for rec in est:
        gt = ev[rec['frame']]['gt']
        for fname, v in rec.items():
            if not isinstance(v, dict) or 'xyyaw' not in v:
                continue
            x, y, yaw = v['xyyaw']
            err = (math.hypot(x - gt[0], y - gt[1]), abs(math.degrees(ang(yaw - gt[2]))), abs(y - gt[1]))
            trace.setdefault(fname, []).append((float(rec['t']), err[0], v.get('diag')))
            for key in groups_of(rec, gt):
                per.setdefault(fname, {}).setdefault(key, []).append(err)
                pooled.setdefault(fname, {}).setdefault(key, []).append(err)
    return per, {f: recovery_summary(rows) for f, rows in trace.items()}


def _false_detection_totals(args, cfg, ep, fd_pool) -> dict:
    op = config_obs_params(cfg)
    vis, _ = load_obs(Path(args.obs)/f'{ep}.obs.npz', kind='vision', episode=ep, obs_params=op,
                      checkpoint_sha256=sha_file(args.checkpoint), infer_size=config_infer_size(cfg))
    orc, _ = load_obs(Path(args.oracle_obs)/f'{ep}.obs.npz', kind='oracle', episode=ep, obs_params=op)
    tot = {'b': {}, 't': {}}
    for f in vis:
        d = false_detections(vis[f], orc[f], args.tol_px)
        for part in d:
            for k, v in d[part].items():
                tot[part][k] = tot[part].get(k, 0) + v
                fd_pool[part][k] = fd_pool[part].get(k, 0) + v
    return tot


def score(args):
    """GT metrics. The registered test set is scored once: a second test scoring is refused."""
    _score_guard(args)
    cfg = load_json(args.config) if args.config else {}
    report = {'schema': 'ugrp.vision_loc.metrics.v2', 'episodes': {}, 'recovery': {}, 'pooled': {},
              'false_detections': {}}
    pooled: dict = {}
    fd_pool = {'b': {}, 't': {}}
    for ep in args.episodes:
        per, rec = _episode_errors(Path(args.estimates), ep, pooled)
        report['episodes'][ep] = {f: {g: summary(v) for g, v in d.items()} for f, d in per.items()}
        report['recovery'][ep] = rec
        if args.obs:
            report['false_detections'][ep] = _false_detection_totals(args, cfg, ep, fd_pool)
    report['pooled'] = {f: {g: summary(v) for g, v in d.items()} for f, d in pooled.items()}
    report['recovery_pooled'] = {f: {k: sum(r[f][k] for r in report['recovery'].values() if f in r)
                                     for k in ('lost_frames', 'recoveries', 'injection_frames', 'injected_particles',
                                               'injection_frames_while_ok')}
                                 for f in report['pooled']}
    if args.obs:
        report['false_detections']['pooled'] = fd_pool
        for part, d in fd_pool.items():
            d['false_edge_rate'] = round(d.get('false_edges', 0)/max(d.get('edges', 0), 1), 5)
            d['missed_edge_rate'] = round(d.get('missed_edges', 0)/max(d.get('teacher_edges', 0), 1), 5)
        report['false_detections']['tol_px'] = args.tol_px
    report['groups'] = {'door_zone': '|x - 2.2| < 0.6 and -0.45 < y < 0.55 (GT), as PR #210',
                        'loaded': 'own-command load state (LoadState of the M1 localizer)',
                        'lateral': '|y_est - y_gt| (door_1 is crossed along x)'}
    Path(args.output).write_text(json.dumps(report, indent=1))
    _print_report(report)


def _print_report(report: dict) -> None:
    for f, d in report['pooled'].items():
        a = d['all']
        print(f"{f:9s} n={a['n']:6d} p50={a['pos_p50_m']} p90={a['pos_p90_m']} p99={a['pos_p99_m']} "
              f"max={a['pos_max_m']} yaw_p90={a['yaw_p90_deg']} recovery={report['recovery_pooled'].get(f)}")
        for g in ('door_zone', 'door_loaded', 'door_unloaded', 'loaded', 'unloaded', 'search_approach', 'carry',
                  'manipulate', 'look_back'):
            if g in d:
                s = d[g]
                print(f"    {g:15s} n={s['n']:6d} p50={s['pos_p50_m']} p90={s['pos_p90_m']} p99={s['pos_p99_m']} "
                      f"lat_p99={s['lat_abs_p99_m']} yaw_p90={s['yaw_p90_deg']}")
    if report['false_detections'].get('pooled'):
        print(json.dumps(report['false_detections']['pooled']))
