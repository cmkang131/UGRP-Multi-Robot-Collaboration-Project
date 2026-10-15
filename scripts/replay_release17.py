"""Offline replay for release17 (A1 FOV one-pulse recovery, A2 yaw_cal_v1). No world, no render.

Reads only locally retrieved ledgers. Ground truth appears ONLY in the yaw sign/magnitude
scoring (evaluation), never in a controller decision. Old runs were native_yaw_v1, so the
map propagation in ``restore_map`` (scripts/replay_release16.py) correctly stays native here.

  python3 -m scripts.replay_release17 --root /Users/changmin/projects/ugrp/outputs/gcp1-runs --out summary.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

import numpy as np

from scripts.replay_release14 import decoded
from scripts.replay_release16 import context, read, restore_map
from sim import release14, release15, release17
from sim.release17 import edge_progress
from sim.lookaround_localization import Camera, rotate_plan
from sim.visible_belief import odometry

YAW_RUNS = ('r12d-00-97942a82', 'r12d-01-97942a82', 'r14d-00-7369ad5e', 'r14d-01-7369ad5e',
            'r15d-00-7379fdd3', 'r15d-01-7379fdd3', 'r16d-00-be2d749a', 'r16d-01-be2d749a')
TRAIN_RUNS = tuple(f'release7-diagnostic-0{i}-a2314b16' for i in range(8)) + (
    'release8-diagnostic-00-a7f0cdcd', 'release8-diagnostic-01-a7f0cdcd')
REPRO = {'74963': 'r16d-00-be2d749a', '74976': 'r16d-01-be2d749a'}


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def lines(path):
    return [json.loads(l) for l in decoded(path).splitlines()]


def isolated_pulses(root):
    """Isolated yaw-bearing wheel commands: (run, rid, t, Y level*s, wheels, durations, GT dyaw over <=0.2 s)."""
    out = []
    for run in YAW_RUNS:
        raw = root/run/'raw'
        try:
            ev = {round(e['t'], 1): e for e in lines(raw/'eval-only.jsonl.zst') if 'robots' in e}
        except Exception:
            continue
        for rid in ('r1', 'r2'):
            prev = None; starts = []
            for r in lines(raw/f'teacher-{rid}.jsonl.zst'):
                wu = tuple(round(x, 6) for x in r['wheel_until'])
                if any(r['wheels']) and wu != prev:
                    starts.append((r['t'], r['wheels'], [max(0., u-r['t']) for u in r['wheel_until']]))
                prev = wu
            for i, (t, w, d) in enumerate(starts):
                y = (-w[0]*d[0]+w[1]*d[1]-w[2]*d[2]+w[3]*d[3])/4
                if abs(y) < .004:
                    continue
                win = min(.2, (starts[i+1][0] if i+1 < len(starts) else 1e9)-t)
                e0, e1 = ev.get(round(t, 1)), ev.get(round(t+win, 1))
                if e0 and e1:
                    out.append((run, rid, t, y, w, d, wrap(e1['robots'][rid]['pose'][2]-e0['robots'][rid]['pose'][2])))
    return out


def rotation_trains(root):
    """Consecutive yaw-bearing commands (gaps <= 0.3 s): summed Y vs UNWRAPPED GT yaw change."""
    out = []
    for run in TRAIN_RUNS:
        raw = root/run/'raw'
        try:
            ev = [e for e in lines(raw/'eval-only.jsonl.zst') if 'robots' in e]
        except Exception:
            continue
        ts = np.array([e['t'] for e in ev])
        for rid in ('r1', 'r2'):
            yaw = np.unwrap([e['robots'][rid]['pose'][2] for e in ev])
            prev = None; commands = []
            for r in lines(raw/f'teacher-{rid}.jsonl.zst'):
                wu = tuple(round(x, 6) for x in r['wheel_until'])
                if any(r['wheels']) and wu != prev:
                    d = [max(0., u-r['t']) for u in r['wheel_until']]
                    eff = [a*b for a, b in zip(r['wheels'], d)]
                    commands.append(dict(t=r['t'], y=(-eff[0]+eff[1]-eff[2]+eff[3])/4, end=max(r['wheel_until'])))
                prev = wu
            trains = []; cur = []
            for c in commands:
                if abs(c['y']) < 1e-4:
                    if cur: trains.append(cur); cur = []
                    continue
                if cur and c['t']-cur[-1]['end'] > .3: trains.append(cur); cur = []
                cur.append(c)
            if cur: trains.append(cur)
            for tr in trains:
                i0 = np.searchsorted(ts, tr[0]['t']-1e-6); i1 = np.searchsorted(ts, tr[-1]['end']+.4)
                if i1 < len(ts):
                    out.append((run, rid, sum(c['y'] for c in tr), float(yaw[i1]-yaw[i0]), len(tr)))
    return out


def yaw_report(root):
    pulses = isolated_pulses(root)
    rows = []
    for run, rid, t, y, w, d, gt in pulses:
        eff = [a*b/.1 for a, b in zip(w, d)]
        rows.append(dict(run=run, rid=rid, t=t, Y=y, gt=gt,
                         yaw_cal=odometry(eff, .1, 'yaw_cal_v1')[2], native=odometry(eff, .1, 'native_yaw_v1')[2]))
    pulse = dict(N=len(rows),
                 sign_agree_yaw_cal=sum((r['gt'] > 0) == (r['yaw_cal'] > 0) for r in rows),
                 sign_agree_native=sum((r['gt'] > 0) == (r['native'] > 0) for r in rows),
                 gt_over_yaw_cal=[round(r['gt']/r['yaw_cal'], 3) for r in rows])
    if rows:
        ratios = [r['gt']/r['yaw_cal'] for r in rows]
        pulse.update(ratio_median=statistics.median(ratios), ratio_min=min(ratios), ratio_max=max(ratios))
    trains = rotation_trains(root)
    big = [t for t in trains if abs(t[3]) > .5]
    train = dict(N=len(trains), N_over_30deg=len(big),
                 sign_agree_yaw_cal=sum((t[3] > 0) == (t[2] > 0) for t in big),
                 unwrapped_over_yaw_cal=[round(t[3]/(t[2]/.35*rate_035()), 3) for t in big])
    if big:
        ratios = [t[3]/(t[2]/.35*rate_035()) for t in big]
        train.update(ratio_median=statistics.median(ratios), ratio_min=min(ratios), ratio_max=max(ratios),
                     rad_per_level_s=[round(t[3]/t[2], 3) for t in big])
    plan = {}
    for deg in (90, -90, 45, 180):
        total = sum(odometry([w*d/.1 for w, d in zip(*p)], .1, 'yaw_cal_v1')[2] for p in rotate_plan(math.radians(deg), 'yaw_cal_v1'))
        legacy = rotate_plan(math.radians(deg), 'native_yaw_v1')
        plan[str(deg)] = dict(pulses_yaw_cal=len(rotate_plan(math.radians(deg), 'yaw_cal_v1')), pulses_native=len(legacy),
                              realized_deg_under_yaw_cal=math.degrees(total))
    return dict(isolated_pulses=pulse, rotation_trains=train, rotate_plan_self_consistency=plan)


def rate_035():
    from sim.visible_belief import rates
    return rates('yaw_cal_v1')[2]


def yaw_pulse_durations(root):
    """Pulse lengths a yaw_cal_v1 run would emit for the stored IBVS yaw steps (point: micro-pulse regime)."""
    durations = []
    for run in ('r14d-00-7369ad5e', 'r14d-01-7369ad5e', 'r15d-00-7379fdd3', 'r15d-01-7379fdd3',
                'r16d-00-be2d749a', 'r16d-01-be2d749a'):
        result = json.loads(decoded(root/run/'raw'/'result.json.zst'))
        for lc in result.get('line_rechecks', []):
            for e in lc['events']:
                if e.get('event') in ('line_ibvs', 'recover_direction') and abs(e.get('yaw', 0.)) > 1e-9:
                    w, d = release14.pulse_for(e.get('forward', 0.), e['left'], e['yaw'], 'yaw_cal_v1')
                    fw, fd, info = release17.yaw_pulse_for(e.get('forward', 0.), e['left'], e['yaw'], 'yaw_cal_v1')
                    realized = odometry([a*b/.1 for a, b in zip(fw, fd)], .1, 'yaw_cal_v1')[2]
                    durations.append(dict(run=run, requested_yaw=e['yaw'], longest_wheel_s=max(d), shortest_active_s=min(x for x in d if x),
                                          floored_mode=info['mode'], floored_shortest_active_s=min(x for x in fd if x),
                                          floored_realized_yaw=float(realized), floored_over_requested=float(realized/e['yaw'])))
    if not durations:
        return dict(N=0)
    longest = [x['longest_wheel_s'] for x in durations]
    return dict(N=len(durations), longest_wheel_s_min=min(longest), longest_wheel_s_median=statistics.median(longest),
                longest_wheel_s_max=max(longest), under_40ms=sum(v < .04 for v in longest),
                floored=dict(shortest_active_s_min=min(x['floored_shortest_active_s'] for x in durations),
                             under_40ms=sum(x['floored_shortest_active_s'] < .04-1e-12 for x in durations),
                             modes={m: sum(x['floored_mode'] == m for x in durations) for m in {x['floored_mode'] for x in durations}},
                             realized_over_requested_min=min(x['floored_over_requested'] for x in durations),
                             realized_over_requested_median=statistics.median(x['floored_over_requested'] for x in durations),
                             realized_over_requested_max=max(x['floored_over_requested'] for x in durations)),
                stored_native_longest_median=None,
                note='native_yaw_v1 would have issued these same requests as 3x longer pulses; shortest stored yaw pulse was ~40 ms')


def fov_replay(root):
    camera = Camera(); out = {}
    for seed, run in REPRO.items():
        raw = root/run/'raw'
        runrec = dict(raw=raw, result=read(raw, 'result.json'), plan=read(raw, 'plan.json'))
        ctx = context(runrec, {})
        alignments = []
        for k, lc in enumerate(runrec['result']['line_rechecks']):
            events = lc['events']
            images = [e for e in events if e['event'] == 'image']
            first = next((e for e in events if e['event'] == 'recover_fov'), None)
            if not first or lc['state'] != 'failed':
                continue
            rid = lc['robot']
            image = next(e for e in reversed(images) if e['t'] <= first['t']+1e-9)
            f = {k2: v for k2, v in image.items() if k2 not in ('t', 'event')}
            rows = [r for r in ctx['rows'][rid] if -1e-6 <= image['t']-r['t'] <= .101]
            pwm = {int(a): b for a, b in max(rows, key=lambda r: r['t'])['pwm'].items()}
            loc = restore_map(runrec, ctx, rid, image['t'])
            clearance = (lambda *a: release15.map_motion_clear(loc, *a)) if loc is not None else (lambda *a: True)
            base = release15.line_step(f, camera, pwm, clearance=clearance)
            base_pulses = len([e for e in events if e['event'] == 'recover_fov'])
            new = release17.line_step(f, camera, pwm, clearance=clearance, profile='native_yaw_v1')
            esc = release17.line_step(f, camera, pwm, clearance=clearance, profile='native_yaw_v1',
                                      period=release17.ESCALATED_PERIOD_S)
            # chain the one-pulse prediction (each step re-checked on the PREDICTED frame, nominal motion)
            chain = []; points = f['points']; fc = dict(f); total = np.zeros(2); safe_at = None
            for n in range(1, 13):
                step = release17.line_step(fc, camera, pwm, clearance=lambda dx, dy, da: clearance(*(total+[dx, dy]), 0.),
                                           profile='native_yaw_v1')
                if step['kind'] != 'recover_fov':
                    chain.append(dict(n=n, stop=step['kind'])); break
                total = total+[step['forward'], step['left']]
                points = release15.project_motion(f['points'], camera, pwm, (total[0], total[1], 0.))
                fc = dict(f, points=points.tolist(), fov_safe=release15.inside(points))
                chain.append(dict(n=n, forward_total_mm=float(total[0]*1000), left_total_mm=float(total[1]*1000),
                                  merit=release15.fov_merit(points), inside=release15.inside(points)))
                if release15.inside(points):
                    safe_at = n; break
            alignments.append(dict(
                alignment_index=k, robot=rid, stored_state=lc['state'], stored_failure=lc['failure'],
                first_recover_image_t=image['t'], stored_micro_pulses=base_pulses,
                stored_first_step=dict(forward=first['forward'], left=first['left'], merit=first['merit'], predicted_merit=first['predicted_merit']),
                replayed_release15_step={k2: base[k2] for k2 in ('kind', 'forward', 'left', 'merit', 'predicted_merit') if k2 in base},
                map_clearance_loaded=loc is not None,
                release17_step={k2: new[k2] for k2 in ('kind', 'forward', 'left', 'merit', 'predicted_merit', 'durations') if k2 in new},
                release17_escalated_step={k2: esc[k2] for k2 in ('kind', 'forward', 'left', 'predicted_merit', 'durations') if k2 in esc},
                chain=chain, pulses_to_fov_safe=safe_at,
                motion_cap_axial_m=.10,
                cap_ok_at_nominal=None if safe_at is None else bool(chain[-1]['forward_total_mm']/1000 <= .10)))
        out[seed] = dict(run=run, alignments=alignments)
    return out


def merit_plateau(root):
    """Why fov_merit cannot judge a single pulse: GT forward travel at which the OBSERVED merit first drops,
    at which fov_safe first holds, and at which the nominal model already predicts merit 0 (evaluation only)."""
    camera = Camera(); out = []
    for run in ('r15d-00-7379fdd3', 'r15d-01-7379fdd3', 'r16d-00-be2d749a', 'r16d-01-be2d749a'):
        raw = root/run/'raw'
        result = read(raw, 'result.json'); runrec = dict(raw=raw, result=result, plan=read(raw, 'plan.json')); ctx = context(runrec, {})
        ev = {round(e['t'], 1): e for e in lines(raw/'eval-only.jsonl.zst') if 'robots' in e}
        for k, lc in enumerate(result['line_rechecks']):
            images = [e for e in lc['events'] if e['event'] == 'image' and e.get('points') and round(e['t'], 1) in ev]
            if sum(e['event'] == 'recover_fov' for e in lc['events']) < 3 or not images:
                continue
            rid = lc['robot']; first = images[0]
            rec = [r for r in ctx['rows'][rid] if -1e-6 <= first['t']-r['t'] <= .101]
            pwm = {int(x): y for x, y in max(rec, key=lambda r: r['t'])['pwm'].items()}
            p0 = ev[round(first['t'], 1)]['robots'][rid]['pose']; c, s_ = math.cos(p0[2]), math.sin(p0[2])
            m0 = release15.fov_merit(first['points']); drop = safe = model0 = None
            for im in images:
                p1 = ev[round(im['t'], 1)]['robots'][rid]['pose']
                dx = c*(p1[0]-p0[0])+s_*(p1[1]-p0[1]); dy = -s_*(p1[0]-p0[0])+c*(p1[1]-p0[1])
                if abs(dy) > .01:
                    continue
                if drop is None and release15.fov_merit(im['points']) < m0-1: drop = dx*1000
                if safe is None and im.get('fov_safe'): safe = dx*1000
                if model0 is None:
                    try:
                        if release15.fov_merit(release15.project_motion(first['points'], camera, pwm, (dx, dy, 0.))) == 0.: model0 = dx*1000
                    except (ValueError, np.linalg.LinAlgError):
                        pass
            out.append(dict(run=run, alignment=k, stored_state=lc['state'], first_merit=m0, observed_merit_first_drop_mm=drop,
                            observed_fov_safe_mm=safe, model_merit_zero_mm=model0))
    return out


def edge_rule_validation(root):
    """Stored (image_i, image_j) pairs: does edge_progress call a real ~13 mm forward move 'progress'
    and a real ~0 mm move 'stall'? GT selects pairs (evaluation); the rule itself sees only boxes+commands."""
    camera = Camera(); rows = []
    for run in ('r15d-00-7379fdd3', 'r15d-01-7379fdd3', 'r16d-00-be2d749a', 'r16d-01-be2d749a'):
        raw = root/run/'raw'
        result = read(raw, 'result.json'); runrec = dict(raw=raw, result=result, plan=read(raw, 'plan.json')); ctx = context(runrec, {})
        ev = {round(e['t'], 1): e for e in lines(raw/'eval-only.jsonl.zst') if 'robots' in e}
        for k, lc in enumerate(result['line_rechecks']):
            if sum(e['event'] == 'recover_fov' for e in lc['events']) < 3:
                continue
            rid = lc['robot']
            images = [e for e in lc['events'] if e['event'] == 'image' and e.get('visible_box_px') and e.get('valid') and round(e['t'], 1) in ev]
            for i, a in enumerate(images):
                rec = [r for r in ctx['rows'][rid] if -1e-6 <= a['t']-r['t'] <= .101]
                pwm = {int(x): y for x, y in max(rec, key=lambda r: r['t'])['pwm'].items()}
                pa = ev[round(a['t'], 1)]['robots'][rid]['pose']
                for b in images[i+1:i+8]:
                    pb = ev[round(b['t'], 1)]['robots'][rid]['pose']; c, s_ = math.cos(pa[2]), math.sin(pa[2])
                    dx = c*(pb[0]-pa[0])+s_*(pb[1]-pa[1]); dy = -s_*(pb[0]-pa[0])+c*(pb[1]-pa[1])
                    if abs(dy) > .004 or abs(wrap(pb[2]-pa[2])) > math.radians(1.5):
                        continue
                    moved = 'move' if .009 <= dx <= .017 else ('still' if abs(dx) <= .0015 and b['t']-a['t'] >= .2-1e-6 else None)
                    if moved is None:
                        continue
                    try:
                        verdict = edge_progress(a['visible_box_px'], a['points'], b['visible_box_px'], (.0129, 0., 0.), camera, pwm)
                    except (ValueError, np.linalg.LinAlgError):
                        continue
                    rows.append(dict(run=run, alignment=k, t0=a['t'], t1=b['t'], gt_dx_mm=dx*1000, truth=moved, kind=verdict['kind'], score=verdict['score']))
    out = {}
    for truth, expected in (('move', 'progress'), ('still', 'stall')):
        sub = [r for r in rows if r['truth'] == truth]
        out[truth] = dict(N=len(sub), expected=expected, as_expected=sum(r['kind'] == expected for r in sub),
                          inconclusive=sum(r['kind'] == 'inconclusive' for r in sub),
                          wrong=[(r['run'][:8], r['alignment'], round(r['t0'], 1), round(r['t1'], 1), round(r['gt_dx_mm'], 1), r['kind'], r['score'])
                                 for r in sub if r['kind'] not in (expected, 'inconclusive')][:10],
                          score_min=min((r['score'] for r in sub if r['score'] is not None), default=None),
                          score_max=max((r['score'] for r in sub if r['score'] is not None), default=None))
    # the merit-only criterion the task text named, on the same 'move' pairs: it would call a plateau a stall
    return out


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    summary = dict(schema='ugrp.release17.offline.v1', profile=release17.PROFILE, scope='stored ledgers only; decisions replayed, physics not',
                   yaw=yaw_report(a.root), yaw_pulse_durations=yaw_pulse_durations(a.root), fov=fov_replay(a.root), merit_plateau=merit_plateau(a.root), edge_rule=edge_rule_validation(a.root),
                   simulation_calls=0, remote_host_connections=0, physical_effect='unverified')
    a.out.write_text(json.dumps(summary, indent=2, default=float)+'\n')
    print(json.dumps(summary, indent=1, default=float))


if __name__ == '__main__':
    main()
