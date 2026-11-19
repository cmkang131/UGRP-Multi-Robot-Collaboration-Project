#!/usr/bin/env python3
"""One real trial folder -> the same metrics as the simulator scoring (docs/architecture.md section 7).

    python3 scripts/real_trial_metrics.py runs/<trial>/          # writes runs/<trial>/metrics.json

Inputs in the folder (formats in real_robot/EVALUATION.md, templates in configs/real_robot/):
  trial.json     the sheet written before the trial: kind (pick1 | coop), orders, sign rectangles, cap
  events.jsonl   laptop runner log: start / handover / release_done / finished, laptop monotonic t
  overhead.jsonl scripts/real_overhead.py record output (same laptop clock)
  operator.json  what a person wrote at the end: where each box is, pick attempts, interventions

Truth for "which box is at which sign" is the operator sheet (a person looks at the floor, as the
simulator reads true coordinates). Times come from the event log. The ceiling camera gives an
independent check of each release (robot pose at release + reach -> sign) and the motion numbers;
every disagreement is listed under `checks`, never silently resolved.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
from pathlib import Path


def _jsonl(path):
    p = Path(path)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def _sign_at(signs, x, y):
    for sid, (x0, y0, x1, y1) in signs.items():
        if min(x0, x1) <= x <= max(x0, x1) and min(y0, y1) <= y <= max(y0, y1):
            return int(sid)
    return None


class Track:
    """Ceiling poses of one robot, looked up by laptop time."""

    def __init__(self, rows, rid):
        pts = [(r['t'], r['poses'][rid]) for r in rows if rid in r.get('poses', {})]
        self.t = [p[0] for p in pts]
        self.p = [p[1] for p in pts]

    def at(self, t, max_gap_s=0.3):
        if not self.t:
            return None
        i = bisect.bisect_left(self.t, t)
        best = min((j for j in (i - 1, i) if 0 <= j < len(self.t)), key=lambda j: abs(self.t[j] - t))
        return self.p[best] if abs(self.t[best] - t) <= max_gap_s else None

    def still(self, t, half_s=0.5):
        """Median pose over t +- half_s, for a robot standing still (one ceiling reading of the heading
        varies by up to about 2 deg on a ~20 px card)."""
        i, j = bisect.bisect_left(self.t, t - half_s), bisect.bisect_right(self.t, t + half_s)
        if i >= j:
            return None
        ps = self.p[i:j]
        yaw = math.atan2(sum(math.sin(p[2]) for p in ps), sum(math.cos(p[2]) for p in ps))
        xs, ys = sorted(p[0] for p in ps), sorted(p[1] for p in ps)
        return (xs[len(xs) // 2], ys[len(ys) // 2], yaw, len(ps))


def order_metrics(trial, events, operator):
    """R0, order violations, completion time. Rule text: docs/architecture.md section 7."""
    t0 = next(e['t'] for e in events if e['event'] == 'start')
    cap = float(trial['cap_s'])
    final = operator['final']                       # item -> {"kind", "sign" (None if at no sign)}
    releases = sorted((e for e in events if e['event'] == 'release_done'), key=lambda e: e['t'])
    filled_at = {}
    for o in trial['orders']:
        ok = [e['t'] - t0 for e in releases
              if final.get(e['item'], {}).get('sign') == o['sign'] and final[e['item']].get('kind') == o['kind']]
        filled_at[o['id']] = ok[o.get('count', 1) - 1] if len(ok) >= o.get('count', 1) else None
    violations, counted = [], {}
    for o in trial['orders']:
        t, before = filled_at[o['id']], o.get('after')
        bad = t is not None and before is not None and (filled_at[before] is None or filled_at[before] > t)
        if bad:
            violations.append({'order': o['id'], 'placed_s': round(t, 2), 'before_order': before,
                               'before_placed_s': None if filled_at[before] is None else round(filled_at[before], 2)})
        counted[o['id']] = t is not None and not bad and t <= cap
    finished = {e['robot']: e['t'] - t0 for e in events if e['event'] == 'finished'}
    robots = sorted({e['robot'] for e in events if 'robot' in e})
    done = robots and all(r in finished for r in robots) and max(finished.values()) <= cap
    return {'R0': sum(counted.values()) / len(trial['orders']), 'orders_filled': sum(counted.values()),
            'orders': len(trial['orders']), 'order_violations': len(violations), 'violations': violations,
            'completion_s': round(max(finished.values()), 2) if done else cap, 'all_finished': bool(done),
            'filled_at_s': {k: None if v is None else round(v, 2) for k, v in filled_at.items()}}


def release_checks(trial, events, overhead, operator):
    """Ceiling camera: robot pose at release + reach -> sign; compare with the log and the operator."""
    reach = float(trial['release_reach_m'])
    tracks, rows = {}, []
    for e in (e for e in events if e['event'] == 'release_done'):
        tr = tracks.setdefault(e['robot'], Track(overhead, e['robot']))
        p = tr.at(e['t'])
        est = None if p is None else _sign_at(trial['signs'], p[0] + reach * math.cos(p[2]), p[1] + reach * math.sin(p[2]))
        truth = operator['final'].get(e['item'], {}).get('sign')
        rows.append({'item': e['item'], 'robot': e['robot'], 'log_sign': e.get('sign'), 'ceiling_sign': est,
                     'operator_sign': truth, 'pose_seen': p is not None,
                     'agree': p is not None and est == truth == e.get('sign')})
    return rows


def motion_metrics(overhead, robots, t0, t1):
    rows = [r for r in overhead if t0 <= r['t'] <= t1]
    out = {}
    for rid in robots:
        seen = [(r['t'], r['poses'][rid]) for r in rows if rid in r.get('poses', {})]
        path = sum(math.dist(a[1][:2], b[1][:2]) for a, b in zip(seen, seen[1:])
                   if math.dist(a[1][:2], b[1][:2]) <= 0.5 * max(b[0] - a[0], 0.05))  # skip misreads (> 0.5 m/s)
        out[rid] = {'seen_fraction': round(len(seen) / len(rows), 3) if rows else 0.0, 'path_m': round(path, 3)}
    gaps = [math.dist(r['poses'][a][:2], r['poses'][b][:2]) for r in rows
            for i, a in enumerate(robots) for b in robots[i + 1:] if a in r['poses'] and b in r['poses']]
    return {'robots': out, 'min_robot_distance_m': round(min(gaps), 3) if gaps else None}


def handover_errors(trial, events, overhead):
    """pick1: robot pose at handover vs the station pose (same numbers as the sim DR: range, lateral, face)."""
    rows = []
    for e in (e for e in events if e['event'] == 'handover'):
        st = trial['stations'][e['item']]
        p = Track(overhead, e['robot']).still(e['t'])
        if p is None:
            rows.append({'item': e['item'], 'pose_seen': False})
            continue
        dx, dy = p[0] - st['x'], p[1] - st['y']
        c, s = math.cos(st['yaw']), math.sin(st['yaw'])
        dyaw = math.degrees(math.atan2(math.sin(p[2] - st['yaw']), math.cos(p[2] - st['yaw'])))
        rows.append({'item': e['item'], 'pose_seen': True, 'along_mm': round(1000 * (dx * c + dy * s), 1),
                     'lateral_mm': round(1000 * (-dx * s + dy * c), 1), 'yaw_deg': round(dyaw, 2), 'frames': p[3]})
    return rows


def score(folder):
    folder = Path(folder)
    trial = json.loads((folder / 'trial.json').read_text())
    operator = json.loads((folder / 'operator.json').read_text())
    events, overhead = _jsonl(folder / 'events.jsonl'), _jsonl(folder / 'overhead.jsonl')
    t0 = next(e['t'] for e in events if e['event'] == 'start')
    t1 = max(e['t'] for e in events)
    robots = sorted({e['robot'] for e in events if 'robot' in e})
    sync = next((r['t'] for r in overhead if r.get('sync')), None)
    out = {'trial_id': trial['trial_id'], 'kind': trial['kind'], 'robots': robots,
           'motion': motion_metrics(overhead, robots, t0, t1),
           'clock': {'start_t': t0, 'sync_card_t': sync,
                     'phone_offset_s': None if sync is None or operator.get('phone_sync_s') is None
                     else round(operator['phone_sync_s'] - (sync - t0), 2)},
           'interventions': operator.get('interventions', [])}
    if trial['kind'] == 'pick1':
        att = operator.get('attempts', [])
        out['pick'] = {'success': sum(bool(a.get('lifted') and a.get('held_3s')) for a in att), 'attempts': len(att)}
        out['handover'] = handover_errors(trial, events, overhead)
    if trial.get('orders'):
        out.update(order_metrics(trial, events, operator))
        out['checks'] = release_checks(trial, events, overhead, operator)
        out['disagreements'] = sum(not r['agree'] for r in out['checks'])
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('folder', type=Path)
    a = p.parse_args(argv)
    out = score(a.folder)
    (a.folder / 'metrics.json').write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ('trial_id', 'R0', 'completion_s', 'order_violations', 'pick', 'disagreements')
                      if k in out}, ensure_ascii=False))


if __name__ == '__main__':
    main()
