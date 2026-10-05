"""Offline replay of recorded v98 own frames + own commands through the v98 provider (HighPoseSource).

Ground truth (eval_only/<rid>/camera_labels.jsonl base pose) is read ONLY for scoring after each
update; it never enters the provider.
"""
import io, json, math, sys
from pathlib import Path

import numpy as np
from PIL import Image

WT = Path('/Users/changmin/projects/ugrp-wt/carry-ckpt')
sys.path.insert(0, str(WT))
OUT = Path('/Users/changmin/projects/ugrp/outputs')
CAL = '/Users/changmin/projects/ugrp/outputs/v92-dev-pilot-c0zero-20261003T104043Z/result/calibration_dev_pilot.json'
CAL_SHA = '398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5'

RUNS = {
    'rh-3358': 'v98-dev-probe-raise_high-3358372e',
    'rh-7623': 'v98-dev-probe-raise_high-7623c4dc',
    'al-3358': 'v98-dev-probe-raise_high_align-3358372e',
    'al-ace8': 'v98-dev-probe-raise_high_align-ace8b257',
    'rh-0865': 'v98-dev-probe-raise_high-0865a788',
    'al-0865': 'v98-dev-probe-raise_high_align-0865a788',
    'hh-0865': 'v98-dev-probe-high_hold_staged-0865a788',
    'ac-672': 'v98-dev-probe-align_to_carry-6727751b',
    'al-672': 'v98-dev-probe-raise_high_align-6727751b',
}


def rjsonl(p):
    return [json.loads(l) for l in open(p)]


def yaw_of_R(R):
    R = np.asarray(R)
    return math.atan2(R[1][0], R[0][0])


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def load_case(run, rid):
    root = OUT/RUNS[run]/'before_door'
    rec = json.load(open(root/'student_record.json'))['robots'][rid]['provider']
    prov = rec['provider']
    frames = rjsonl(root/f'robots/{rid}/frames.jsonl')
    labels = {r['frame_id']: r for r in rjsonl(root/f'eval_only/{rid}/camera_labels.jsonl')}
    static = json.load(open(root/'inputs/static_map.json'))
    sr = json.load(open(root/'student_record.json'))
    profiles = []
    for p in sr.get('pair', []):
        for e in p.get('robots', {}).get(rid, {}).get('events', []):
            if e.get('event') == 'motion_profile':
                profiles.append((float(e['sim_s']), None if e['profile'] == 'default' else e['profile']))
    return dict(root=root, prov=prov, frames=frames, labels=labels, static=static, profiles=sorted(profiles),
                rejections=rec.get('frame_rejections', []))


def build(case, patch=None, config=None):
    from harness.vision_pose_source_highpose import HighPoseSource
    from harness import zone_pair_highpose_pf_consistency as pc
    p = case['prov']
    pc.CONFIG = pc.NEUTRAL if config is None else {**pc.DEFAULT, **config}
    src = HighPoseSource(case['static'], CAL, CAL_SHA, p['seed'])
    if patch is not None:
        patch(src)
    pr = p['prior']
    src.init_prior(tuple(pr['mean']), tuple(pr['std']), source=pr['source'])
    return src


def events(case):
    """Inner-provider event stream: recorded lifecycle (commands, relocalizations) + frames by capture time.

    A frame at capture t precedes lifecycle items with t' >= t (frames are captured before commands);
    the initial servo command precedes everything. Frames dropped by the delay wrapper at a relocalization
    (capture in (cutoff, cutoff+0.16]) and frames never released (last 0.16 s) are skipped.
    """
    lc = case['prov']['lifecycle']
    items = []
    prof = list(case.get('profiles', []))
    for e in lc:
        if e['event'] == 'own_command':
            items.append(('cmd', float(e['row']['t']), e['row']))
        elif e['event'] == 'begin_relocalization':
            items.append(('reloc', float(e['t']), e))
    # motion-profile switches (own controller phase) are queued at their SIM time, after that tick's frame
    for tp, name in prof:
        k = next((n for n, it in enumerate(items) if it[1] >= tp - 1e-9 and it[0] == 'cmd'
                  and it[2].get('kind') != 'initial_servo_command'), len(items))
        items.insert(k, ('profile', tp, name))
    relocs = [t for k, t, _ in items if k == 'reloc']
    last_t = case['frames'][-1]['sim_time']
    out, i = [], 0
    if items and items[0][2].get('kind') == 'initial_servo_command':
        out.append(items[0]); i = 1
    for f in case['frames']:
        t = float(f['sim_time'])
        if t > last_t - .16 + 1e-6:
            continue
        if any(c < t <= c + .16 + 1e-9 for c in relocs):
            continue
        while i < len(items) and items[i][1] < t - 1e-9:
            out.append(items[i]); i += 1
        out.append(('frame', t, f))
    out.extend(items[i:])
    # wrapper report(now) at every frame tick releases inputs <= now-0.16 and predicts the PF to that cutoff
    ticks = [float(f['sim_time']) - .16 for f in case['frames'] if float(f['sim_time']) - .16 > 0]
    merged, j = [], 0
    for ev in out:
        while j < len(ticks) and ticks[j] < ev[1] - 1e-9:
            merged.append(('report', ticks[j], None)); j += 1
        merged.append(ev)
    return merged


def gt_pose(label):
    p = label['base_position_m']
    return np.array([p[0], p[1], yaw_of_R(label['base_rotation'])])


def replay(run, rid, patch=None, keep_obs=False, on_scan=None, config=None):
    case = load_case(run, rid)
    src = build(case, patch, config)
    pf = src.loc._pf
    rows = []
    stash = {}
    observe = src.worker.observe
    def observe_stash(bgr):
        stash['obs'] = observe(bgr)
        return stash['obs']
    src.worker.observe = observe_stash
    for kind, t, payload in events(case):
        if kind == 'report':
            if t >= pf.t - 1e-9:
                src.report(t)
            continue
        if kind == 'profile':
            src.set_motion_profile(t, payload)
            continue
        if kind == 'cmd':
            src.on_command(payload)
        elif kind == 'reloc':
            src.begin_relocalization(t, dict(src.servo))
        else:
            rgb = np.asarray(Image.open(case['root']/payload['path']).convert('RGB'))
            n_scan0 = pf.stats['scan_updates']
            meas0 = src.counts['measured']
            ess_diag = None
            src.on_frame(t, rgb)
            est = src.loc.estimate()
            if not est.get('initialized'):
                continue
            g = gt_pose(case['labels'][payload['frame_id']])
            cov = np.asarray(est['cov'])
            e = np.array([est['x'] - g[0], est['y'] - g[1]])
            P = cov[:2, :2]
            try:
                nees = float(e @ np.linalg.solve(P, e))
            except np.linalg.LinAlgError:
                nees = float('inf')
            # pan offset: estimate yaw includes the pan-induced chassis offset; PF particles are base yaw
            eyaw = wrap(est['yaw'] - est.get('pan_yaw_offset', 0.) - g[2])
            e3 = np.array([e[0], e[1], eyaw])
            try:
                nees3 = float(e3 @ np.linalg.solve(cov, e3))
            except np.linalg.LinAlgError:
                nees3 = float('inf')
            w = np.exp(pf.logw - pf.logw.max()); w /= w.sum()
            uniq = len(np.unique(pf.px.round(9), axis=0))
            row = dict(t=round(t, 3), frame_id=payload['frame_id'], scanned=pf.stats['scan_updates'] > n_scan0,
                       measured=src.counts['measured'] > meas0, ex=e[0], ey=e[1], eyaw=eyaw,
                       sx=math.sqrt(P[0, 0]), sy=math.sqrt(P[1, 1]), syaw=math.sqrt(cov[2, 2]),
                       std_xy=est['std_xy_m'], nees=nees, nees3=nees3, n_eff=est['n_eff'],
                       uniq=uniq, fix_age=est.get('fix_age_s'), loaded=bool(pf.load.loaded),
                       servo=dict(src.servo), diag=dict(pf.diag), gt=g.tolist(),
                       est=[est['x'], est['y'], est['yaw']])
            if keep_obs and src.last_obs is not None:
                row['n_cols'] = src.last_obs['n_cols'] if src.last_obs['t'] == round(t, 4) else None
            if on_scan is not None and row['scanned']:
                row['scan_info'] = on_scan(src, t, stash['obs'], g)
            rows.append(row)
    return dict(rows=rows, counts=dict(src.counts), stats=dict(pf.stats),
                recorded_counts=case['prov']['counts'], recorded_stats=case['prov']['localizer_stats'])


if __name__ == '__main__':
    run, rid = sys.argv[1], sys.argv[2]
    r = replay(run, rid)
    print('counts', r['counts'], 'recorded', r['recorded_counts'])
    print('stats', r['stats'], 'recorded', r['recorded_stats'])
    for row in r['rows'][::max(1, len(r['rows'])//40)] + r['rows'][-3:]:
        print(row['t'], 'scan' if row['scanned'] else '    ', 'M' if row['measured'] else ' ',
              f"err=({row['ex']*1000:6.1f},{row['ey']*1000:6.1f})mm s=({row['sx']*1000:5.1f},{row['sy']*1000:5.1f})"
              f" nees={row['nees']:8.1f} neff={row['n_eff']:7.1f} uniq={row['uniq']}")
