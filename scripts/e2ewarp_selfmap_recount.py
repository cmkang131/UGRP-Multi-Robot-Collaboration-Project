#!/usr/bin/env python3
"""Mac-side, non-physics recount of the e2ewarp self-supervised map funnel.

Reads only the raw run artifacts that the execution VM wrote (no simulator, no
model, no engine import):

* ``localization.json`` - one row per own frame per robot/world, including the
  own-map record (``fk_status``, ``self_map.scan_status``,
  ``self_map.wall_columns``, ``self_map.inserted``),
* ``runtime-applied.json`` - ``map_keyframe_admission`` policy (off or
  ``elapsed_sim_v1``), contact profile, host,
* ``result.json`` - status/nworld/source_sha/sim_s,
* ``rejections.json`` - the controller's own rejection ledger.

It rebuilds the R3-compatible frame funnel and, when the run used
``elapsed_sim_v1``, checks from the raw whether keyframe insertion actually
became > 0 and whether every accepted insertion obeys the elapsed-SIM cadence
(``tick - previous_inserted_tick >= interval_ticks``).  It also counts
insertions that would have been missed by the old ``tick % interval == 0``
gate, which is the regression the elapsed-SIM option was introduced for.

Nothing here changes a controller or a result.  GT/eval-only fields are not
read; if a caller adds them they never feed a control decision.

Usage:
``python3 scripts/e2ewarp_selfmap_recount.py --raw <run dir> --output <json>``
Exit code 1 when the run used elapsed_sim_v1 and inserted keyframes == 0 (a
failed self-map gate should fail loudly); ``--allow-zero`` suppresses that.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess


def read(root: Path, name: str, default=None):
    plain = root / name
    if plain.exists():
        return json.loads(plain.read_text())
    packed = Path(str(plain) + '.zst')
    if packed.exists():
        if shutil.which('zstd') is None:
            raise SystemExit('zstd CLI required to read ' + str(packed))
        return json.loads(subprocess.check_output(['zstd', '-dc', str(packed)]))
    return default


def funnel(values):
    previous = values[0][1]
    out = []
    for name, n in values:
        if not 0 <= n <= previous:
            raise ValueError('noncumulative funnel: ' + name)
        out.append(dict(stage=name, cumulative_pass_n=int(n),
                        rejected_n=int(previous - n)))
        previous = n
    return out


def _tick(row):
    if row.get('tick') is not None:
        return int(row['tick'])
    sim_s = row.get('sim_s')
    if sim_s is None:
        return None
    return int(round(float(sim_s) * 10))


def recount(raw: Path, *, interval_ticks=10):
    rows = read(raw, 'localization.json', []) or []
    applied = read(raw, 'runtime-applied.json', {}) or {}
    result = read(raw, 'result.json', {}) or {}
    policy = str(applied.get('map_keyframe_admission') or 'off')
    frames = funnel([
        ('own_rgb', len(rows)),
        ('qualified_unloaded_FK', sum(
            r.get('fk_status') == 'servo_fk_nominal_unloaded' for r in rows)),
        ('settled_scan', sum(
            (r.get('self_map') or {}).get('scan_status') in
            ('observed_wall_contacts', 'unknown_wall_contact') for r in rows)),
        ('observed_wall_contacts', sum(
            (r.get('self_map') or {}).get('wall_columns', 0) > 0 for r in rows)),
        ('inserted_keyframe', sum(
            bool((r.get('self_map') or {}).get('inserted')) for r in rows)),
    ])
    insert_rows = [r for r in rows if (r.get('self_map') or {}).get('inserted')]
    by_key = defaultdict(lambda: dict(inserted=0, frames=0,
                                      qualified=0, settled=0, hits=0))
    for r in rows:
        key = (r.get('world'), r.get('robot'))
        b = by_key[key]
        b['frames'] += 1
        b['qualified'] += r.get('fk_status') == 'servo_fk_nominal_unloaded'
        sm = r.get('self_map') or {}
        b['settled'] += sm.get('scan_status') in ('observed_wall_contacts',
                                                  'unknown_wall_contact')
        b['hits'] += int(sm.get('wall_columns', 0) or 0)
        b['inserted'] += bool(sm.get('inserted'))
    per_stream = []
    for key, b in sorted(by_key.items(), key=lambda kv: str(kv[0])):
        # localization rows in the R4 raw carry sim_s but not always an
        # integer tick; the 10 Hz frame clock is the declared control rate.
        ticks = sorted(_tick(r) for r in insert_rows
                       if (r.get('world'), r.get('robot')) == key
                       and _tick(r) is not None)
        ticks = [t for t in ticks if t is not None]
        gaps = [b - a for a, b in zip(ticks, ticks[1:])]
        violations = [g for g in gaps if g < interval_ticks]
        per_stream.append(dict(world=key[0], robot=key[1], **b,
                               inserted_ticks=ticks,
                               inserted_gaps_ticks=gaps,
                               elapsed_rule_violations=len(violations),
                               off_modulo_grid=sum(t % interval_ticks != 0
                                                   for t in ticks)))
    inserted_n = len(insert_rows)
    all_gaps = [b - a for s in per_stream for a, b in
                zip(s['inserted_ticks'], s['inserted_ticks'][1:])]
    off_grid = sum(int(s['off_modulo_grid']) for s in per_stream)
    violations = sum(int(s['elapsed_rule_violations']) for s in per_stream)
    elapsed_checks = dict(
        policy=policy,
        interval_ticks=interval_ticks,
        keyframe_insertions=inserted_n,
        keyframe_insertions_gt_zero=inserted_n > 0,
        inserted_off_old_modulo_grid=off_grid,
        elapsed_rule_violations=violations,
        gap_ticks=(dict(min=min(all_gaps), median=statistics.median(all_gaps),
                        max=max(all_gaps)) if all_gaps else None),
        note=('elapsed_sim_v1 keys on the last accepted frame; >0 off-grid '
              'insertions prove the old modulo gate would have missed them'),
    )
    reasons = read(raw, 'rejections.json', []) or []
    distribution = Counter(r.get('reason') for r in reasons)
    report = dict(
        schema='ugrp.e2ewarp.selfmap_recount.v1',
        raw=str(raw.resolve()),
        analysis_script_sha256=hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        status=result.get('status'),
        source_sha=result.get('source_sha'),
        nworld=result.get('nworld'),
        map_keyframe_admission=policy,
        frame_funnel=frames,
        elapsed_sim_check=elapsed_checks,
        per_stream=per_stream,
        rejection_reasons=dict(distribution),
        nonphysics=True,
        inputs=['localization.json', 'runtime-applied.json', 'result.json',
                'rejections.json'],
        not_read=['TOP camera frames', 'simulator/GT pose', 'contacts',
                  'measured joints', 'teacher phases/outcomes'],
        scope=('self-supervised map gate recount only; no transport or '
               'localization-accuracy claim'),
    )
    return report


def print_table(report):
    print('raw:', report['raw'])
    print('status:', report['status'], 'source_sha:', report['source_sha'],
          'policy:', report['map_keyframe_admission'])
    for s in report['frame_funnel']:
        print(f"  {s['stage']:<24} pass={s['cumulative_pass_n']:>5} "
              f"rejected={s['rejected_n']:>5}")
    e = report['elapsed_sim_check']
    print('keyframe insertions:', e['keyframe_insertions'],
          '| off old-modulo grid:', e['inserted_off_old_modulo_grid'],
          '| elapsed-rule violations:', e['elapsed_rule_violations'])
    for s in report['per_stream']:
        print(f"  world {s['world']} {s['robot']}: frames={s['frames']} "
              f"qualified={s['qualified']} settled={s['settled']} "
              f"inserted={s['inserted']} ticks={s['inserted_ticks']}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prior', type=Path, default=None,
                   help='optional previous rejection_table.json for comparison')
    p.add_argument('--json-only', action='store_true')
    p.add_argument('--allow-zero', action='store_true',
                   help='do not exit 1 when elapsed_sim_v1 inserts 0 keyframes')
    a = p.parse_args()
    report = recount(a.raw)
    if a.prior is not None:
        prior = json.loads(a.prior.read_text())
        report['prior_frame_funnel'] = prior.get('frame_funnel')
        report['prior_raw'] = prior.get('raw')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    (a.output.parent / (a.output.stem + '.sha256.json')).write_text(
        json.dumps({a.output.name: hashlib.sha256(a.output.read_bytes()).hexdigest()},
                   indent=2) + '\n')
    if not a.json_only:
        print_table(report)
    if (report['elapsed_sim_check']['policy'] == 'elapsed_sim_v1'
            and not report['elapsed_sim_check']['keyframe_insertions_gt_zero']
            and not a.allow_zero):
        raise SystemExit('SELFMAP_GATE_FAILED: elapsed_sim_v1 inserted 0 keyframes')


if __name__ == '__main__':
    main()
