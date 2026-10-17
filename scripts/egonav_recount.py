#!/usr/bin/env python3
"""Recount an egonav gate from per-world raw records (no simulator import).

Reads only the raw JSON written by ``scripts/egonav_gate.py``.  Evaluation
labels in those files are used only for the gate's success/error columns; no
value here is fed back to the controller.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slope(rows):
    if len(rows) < 2:
        return None
    ts = [float(r['t']) for r in rows]
    es = [float(r['error_m']) for r in rows]
    mt = sum(ts)/len(ts); me = sum(es)/len(es)
    den = sum((t-mt)**2 for t in ts)
    return None if den <= 1e-12 else sum((t-mt)*(e-me) for t, e in zip(ts, es))/den


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--markdown', type=Path)
    args = ap.parse_args()
    run = args.run
    summary = load(run/'summary.json')
    rejection = load(run/'rejection_table.json')
    setup = load(run/'setup.json')
    worlds = [load(p) for p in sorted(run.glob('world*.json'))]
    if not worlds:
        raise SystemExit('NO_WORLD_RECORDS')
    n = len(worlds)
    center = setup['evaluation_only']['center_m']
    half = setup['evaluation_only']['half_m']
    rows = []
    for w in worlds:
        spawn = w.get('spawn') or [None, None, None, None]
        final = w.get('final') or {}
        errs = w.get('memory_errors') or []
        unseen = [e for e in errs if not e['visible']]
        events = w.get('events') or []
        reasons = Counter(e['reason'] for e in events)
        authored_distance = None
        authored_bearing_deg = None
        if len(spawn) >= 4 and spawn[0] is not None:
            dx = center[0]-spawn[0]; dy = center[1]-spawn[1]
            authored_distance = math.hypot(dx, dy)
            if spawn[3] is not None:
                b = math.atan2(dy, dx)
                authored_bearing_deg = math.degrees((b-spawn[3]+math.pi) % (2*math.pi)-math.pi)
        rows.append(dict(
            world=w['world'], status=w['status'], seen=bool(w['seen']),
            target_losses=int(w['target_losses']), collisions=int(w['collisions']),
            done=bool(w['done']), memory_count=len(w.get('context', {}).get('items', [])),
            final_zone_distance_m=(final.get('zone_distance_m')),
            final_center_distance_m=(final.get('center_distance_m')),
            final_memory_error_m=(errs[-1]['error_m'] if errs else None),
            unseen_slope_m_per_s=slope(unseen), unseen_samples=len(unseen),
            memory_samples=len(errs),
            authored_distance_m=authored_distance,
            authored_bearing_deg=authored_bearing_deg,
            event_reason_counts=dict(reasons)))
    arrived = sum(r['status'] == 'arrived_inside_zone' for r in rows)
    claimed = sum(r['done'] for r in rows)
    seen = sum(r['seen'] for r in rows)
    lost_worlds = sum(r['target_losses'] > 0 for r in rows)
    collisions = sum(r['collisions'] for r in rows)
    collision_worlds = sum(r['collisions'] > 0 for r in rows)
    zd = [r['final_zone_distance_m'] for r in rows if r['final_zone_distance_m'] is not None]
    cdist = [r['final_center_distance_m'] for r in rows if r['final_center_distance_m'] is not None]
    slopes = [r['unseen_slope_m_per_s'] for r in rows if r['unseen_slope_m_per_s'] is not None]
    status_counts = Counter(r['status'] for r in rows)
    blocks = Counter()
    for r in rows:
        for reason, count in r['event_reason_counts'].items():
            if reason in ('turn_blocked', 'forward_blocked', 'forward_path_blocked'):
                blocks[reason] += count
    raw_files = sorted([p.name for p in run.glob('world*.json')]) + ['summary.json', 'rejection_table.json', 'setup.json']
    result = dict(
        schema='ugrp.egonav.recount.v1', raw_path=str(run),
        source_sha=summary.get('source_sha'), host=summary.get('host'),
        world_n=n, statuses=dict(status_counts),
        arrived_inside_zone_n=arrived,
        arrival_claimed_n=claimed,
        seen_at_least_once_n=seen,
        target_lost_mid_route_worlds_n=lost_worlds,
        collision_n=collisions, collision_worlds_n=collision_worlds,
        final_zone_distance_m=dict(
            n=len(zd), mean=(statistics.fmean(zd) if zd else None),
            median=(statistics.median(zd) if zd else None),
            max=(max(zd) if zd else None)),
        final_center_distance_m=dict(
            n=len(cdist), mean=(statistics.fmean(cdist) if cdist else None),
            median=(statistics.median(cdist) if cdist else None),
            max=(max(cdist) if cdist else None)),
        memory_unseen_slope_m_per_s=dict(
            n=len(slopes), median=(statistics.median(slopes) if slopes else None),
            mean=(statistics.fmean(slopes) if slopes else None)),
        blocking_event_counts=dict(blocks),
        rows=rows,
        raw_files=raw_files,
        sha256={p: sha(run/p) for p in raw_files})
    checks = []
    def check(name, raw, reported):
        checks.append(dict(name=name, raw=raw, reported=reported, match=(raw == reported)))
    check('arrived_inside_zone_n', arrived, summary.get('arrived_inside_zone_n'))
    check('arrival_claimed_n', claimed, summary.get('arrival_claimed_n'))
    check('target_lost_mid_route_n', lost_worlds, summary.get('target_lost_mid_route_n'))
    check('collision_n', collisions, summary.get('collision_n'))
    check('collision_worlds_n', collision_worlds, summary.get('collision_worlds_n'))
    check('world_n', n, summary.get('world_n'))
    check('rejection_arrived', arrived, next((f['cumulative_pass_n'] for f in rejection['funnel']
                                              if f['stage'] == 'arrived_inside_authored_zone'), None))
    result['checks'] = checks
    result['all_checks_match'] = all(c['match'] for c in checks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    if args.markdown:
        lines = ['| world | status | seen | losses | coll | final zone d (m) | final memory err (m) | unseen slope (m/s) |',
                 '|---:|---|---:|---:|---:|---:|---:|---:|']
        for r in rows:
            fmt = lambda v: '' if v is None else f'{v:.3f}'
            lines.append(f"| {r['world']:02d} | {r['status']} | {int(r['seen'])} | {r['target_losses']} | "
                         f"{r['collisions']} | {fmt(r['final_zone_distance_m'])} | "
                         f"{fmt(r['final_memory_error_m'])} | {fmt(r['unseen_slope_m_per_s'])} |")
        args.markdown.write_text('\n'.join(lines)+'\n')
    print(json.dumps({k: result[k] for k in ('world_n', 'arrived_inside_zone_n', 'arrival_claimed_n',
                                             'seen_at_least_once_n', 'target_lost_mid_route_worlds_n',
                                             'collision_n', 'all_checks_match')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
