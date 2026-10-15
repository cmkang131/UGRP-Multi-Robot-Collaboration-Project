"""crate11 analysis of the per-tick traces written by crate11_trace.py (offline, no World/render/remote I/O).

Usage: python crate11_analyze.py <trace_dir> <out.json>
Every field under 'eval_only' uses simulator ground truth and is for evaluation/audit only.
"""
import json, math, sys, subprocess
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET
from harness.static_keepouts import rect_distance

RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
# (run, failing robot, role label)
FAILS = [('crate-diag-77978-bf31840f', 'r1'), ('crate-diag-77979-bf31840f', 'r1'),
         ('crate-diag-77981-49d11b8e', 'r1'), ('crate-diag-77982-49d11b8e', 'r1'),
         ('crate-diag-77988-49d11b8e', 'r1'), ('crate-diag-77989-49d11b8e', 'r1'),
         ('crate-reproduction-77969-49d11b8e', 'r2'), ('crate-reproduction-77978-49d11b8e', 'r1'),
         ('crate-reproduction-77979-49d11b8e', 'r1'), ('crate-diag-77969-5644e3dd', 'r2')]
ALL = ([f'crate-diag-{n}-bf31840f' for n in range(77970, 77980)] +
       [f'crate-diag-{n}-49d11b8e' for n in range(77980, 77990)] +
       [f'crate-reproduction-{n}-49d11b8e' for n in (77969, 77978, 77979)])


def load(d, name):
    t = json.load(open(Path(d) / f'{name}.trace.json'))['trace']; f = json.load(open(Path(d) / f'{name}.final.json'))
    return t, f


def walls(name):
    out = []
    for g in ET.parse(RAW / name / 'raw' / 'scene.xml').getroot().findall('.//worldbody/geom'):
        n = g.get('name', '')
        if n.startswith('zone_wall_'):
            p = list(map(float, g.get('pos').split())); s = list(map(float, g.get('size').split()))
            out.append((n[10:], (p[0], p[1], s[0], s[1], 0)))
    return out


def wall_dist(W, pt):
    return min((rect_distance(pt, r), n) for n, r in W)


def onset(h):
    """Start of the last continuous zero-wheel run that ends the record (initial arm-folding/search waits excluded)."""
    last = max((i for i, x in enumerate(h) if any(x['wheels'])), default=-1)
    return min(last + 1, len(h) - 1)


def summarize(d, name, rid):
    t, f = load(d, name); h = t[rid]; fin = f['final'][rid]; t0 = h[0]['t']
    W = walls(name); o = onset(h); x = h[o]; det = x['detail']
    outcome_tick = next((i for i, y in enumerate(h) if y['outcome']), None)
    frames = Counter((tuple(y['hold'][:2]), y['phase']) for y in h[o:])
    gs = fin['goal_set_log']; last_row = gs[-1] if gs else None
    out = {'run': name, 'robot': rid, 'sha8': f['source_sha'][:8], 'ticks': len(h), 'outcome': fin['outcome'] or f['result_outcomes'][rid],
           'onset_tick': o, 'onset_elapsed_s': x['elapsed'], 'onset_ledger_t': round(x['t'], 3),
           'outcome_tick': outcome_tick, 'outcome_elapsed_s': h[outcome_tick]['elapsed'] if outcome_tick is not None else None,
           'zero_run_hold_frames': [[list(k[0]), k[1], v] for k, v in frames.most_common(4)],
           'phase_at_onset': x['phase'], 'visible_probes_at_onset': x['vis'], 'ever_align': any(y['phase'] == 'align' for y in h),
           'align_ticks': sum(y['phase'] in ('align', 'ready') for y in h), 'relooks': fin['relooks']}
    if 'pose' in det:
        obs = sorted(det['obstacles'], key=lambda q: q['base_clear_m'])
        out['controller_view'] = {'dist_goal_m': det['dist_goal_m'], 'dist_end_m': det['dist_end_m'], 'errors_axial_lat_yaw': det['errors'],
                                  'choice_offset_rad_dist_m': det['choice'], 'goal_free': det['goal_free'], 'radius_m': det['radius_m'],
                                  'nearest_obstacles': [{'id': q['id'], 'base_clear_m': q['base_clear_m'], 'goal_clear_m': q['goal_clear_m']} for q in obs[:3]],
                                  'memory_ages_s': det['mem'], 'wall_in_memory': any(k.startswith('zone_wall') for k in det['mem']),
                                  'fresh_peers': det['fresh_peers']}
    out['wall_in_memory_ticks'] = sum(any(k.startswith('zone_wall') for k in (y['detail'].get('mem') or {})) for y in h)
    out['blind_ticks_vis_lt5'] = sum(y['vis'] < 5 for y in h)
    if last_row:
        out['last_goal_set_row'] = {'elapsed_s': round(last_row['t'] - t0, 3), 'selected': bool(last_row['selected']),
                                    'candidates': [{'offset_deg': round(c['offset_deg'], 1), 'dist_m': c['distance_m'], 'reason': c['reason']}
                                                   for c in last_row['candidates'] if c['reason'] != 'grasp_geometry'],
                                    'n_grasp_geometry_rejected': sum(c['reason'] == 'grasp_geometry' for c in last_row['candidates'])}
    reasons = Counter()
    for y in h:
        p = y.get('pulse')
        if p and p['reason'] != 'ok':
            reasons[p['reason']] += 1
    out['guard_49d11b8e'] = {'unsafe_pulses': dict(reasons), 'inside_margin_unsafe': sum(1 for y in h if y.get('pulse') and y['pulse']['reason'] != 'ok' and y['pulse']['inside_margin']),
                             'first_unsafe_tick': next((y['tick'] for y in h if y.get('pulse') and y['pulse']['reason'] != 'ok'), None)}
    out['counterfactual_guard_on_older_code'] = {'would_reject': sum(1 for y in h if y.get('cf_guard') and not y['cf_guard']['safe']),
                                                 'inside_margin_ticks': sum(1 for y in h if y.get('cf_guard') and y['cf_guard']['inside_margin'])}
    # evaluation-only geometry
    gt = x['gt']; end = f['roles'][rid]
    lug = gt['ends'][end]
    wd = wall_dist(W, gt['pose'][:2]); lw = wall_dist(W, lug[:2])
    out['eval_only'] = {'robot_xy': gt['pose'][:2], 'robot_center_to_wall_face_m': wd[0], 'wall': wd[1], 'assigned_lug_xy': lug[:2],
                        'lug_center_to_wall_face_m': lw[0], 'robot_to_lug_m': math.dist(gt['pose'][:2], lug[:2])}
    mins = min((wall_dist(W, y['gt']['pose'][:2]) + (y['tick'],) for y in h), key=lambda q: q[0])
    out['eval_only']['min_robot_center_to_wall_face_m_over_run'] = {'m': mins[0], 'wall': mins[1], 'tick': mins[2]}
    return out


def pinned_yaw_drift(d, name, rid, a, b):
    """Issued dead-reckoned yaw change vs evaluation-only true yaw change between ticks a..b (audit of pose-estimate decoupling)."""
    t, _ = load(d, name); h = t[rid]
    wrap = lambda q: math.atan2(math.sin(q), math.cos(q))
    ya, yb = h[a]['detail']['pose'][2], h[b]['detail']['pose'][2]
    ga, gb = h[a]['gt']['pose'][2], h[b]['gt']['pose'][2]
    return {'ticks': [a, b], 'elapsed_s': [h[a]['elapsed'], h[b]['elapsed']], 'issued_yaw_change_rad': yb - ya,
            'eval_only_true_yaw_change_rad': wrap(gb - ga)}


def seed_stats(d):
    rows = []
    for name in ALL:
        t, f = load(d, name)
        rec = {'run': name, 'seed': f['seed'], 'sha8': f['source_sha'][:8], 'outcomes': f['result_outcomes']}
        for rid in t:
            h = t[rid]; W = walls(name)
            mn = min(wall_dist(W, y['gt']['pose'][:2])[0] for y in h)
            ins = sum(1 for y in h if y.get('cf_guard') and y['cf_guard']['inside_margin']) + sum(1 for y in h if y.get('pulse') and y['pulse']['inside_margin'])
            un = sum(1 for y in h if y.get('cf_guard') and not y['cf_guard']['safe']) + sum(1 for y in h if y.get('pulse') and y['pulse']['reason'] != 'ok')
            rec[rid] = {'min_center_to_wall_face_m': mn, 'inside_margin_ticks': ins, 'guard_unsafe_ticks': un,
                        'first_align_tick': next((y['tick'] for y in h if y['phase'] in ('align', 'ready')), None)}
        rows.append(rec)
    return rows


if __name__ == '__main__':
    d, outp = sys.argv[1], sys.argv[2]
    res = {'failures': [summarize(d, n, r) for n, r in FAILS], 'seed_stats': seed_stats(d),
           'pinned_yaw_drift_77979_bf31840f_r1': pinned_yaw_drift(d, 'crate-diag-77979-bf31840f', 'r1', 96, 144)}
    Path(outp).write_text(json.dumps(res, indent=1))
    print('ok', len(res['failures']))
