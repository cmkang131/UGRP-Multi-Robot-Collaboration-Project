"""TensorBoard snapshot of the VISW dev closed-loop check (dev closed-loop check, 연구 결과 아님).

Glue only: event files via the repo exporter's ``Writer`` (``scripts/tensorboard_tools/export.py``), percentiles
and the door box via VIS3's scorer (``experiments/2026-09-26-vision-loc/vision_loc_score.py``: ``pct``,
``near_door``) so the closed-loop numbers use the same definitions as the VIS3 offline baseline.

  <logdir>/<snapshot>/vw-s942-closed/     closed loop (errors vs eval-only GT, sigma, door, delivery, SIM, ms)
  <logdir>/<snapshot>/vis3-dev-a1/        VIS3 offline dev pooled, selected config a1_open (same config sha)
  <logdir>/<snapshot>/vis3-test-vision/   VIS3 offline independent test pooled (student)
  <logdir>/<snapshot>/collection.json     runs, sources, hashes

Existing destinations are refused. ``--verify`` re-reads every run with EventAccumulator and compares with
the sources. Scalar step for series = SIM time x 100 (centiseconds).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VIS3 = ROOT / 'experiments' / '2026-09-26-vision-loc'
sys.path[:0] = [str(ROOT), str(VIS3)]

LABEL = 'dev closed-loop check, 연구 결과 아님'
RAW = Path('/Users/changmin/projects/ugrp/outputs/vision-worker-closed-loop-20260927/vl3-dev-s942')
KEYS = ('pos_p50_m', 'pos_p90_m', 'pos_p99_m', 'yaw_p90_deg')      # shared with the VIS3 runs
NEAR_R_M = 0.5                                                  # README's near-door radius (door centre)
HP_METRICS = ['summary/all/pos_p90_m', 'summary/door_zone/pos_p90_m', 'summary/near_door_r050/pos_p90_m',
              'sigma/frac_err_gt_3sigma', 'result/door_passed', 'evaluation/reported_success', 'result/sim_time_s',
              'vision/inference_ms_p50']


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def closed_loop(raw: Path) -> tuple[dict, dict, dict]:
    """Scalars, series and provenance of the closed-loop run (evaluation-only GT, after the run)."""
    from vision_loc_score import near_door, pct
    res = json.loads((raw / 'result.json').read_text())
    rid, ev = res['robot'], res['evaluation_only_localization']
    rows = [r for r in jsonl(raw / 'eval_only' / 'frames_eval.jsonl') if r['robot_id'] == rid and 'pos_err_m' in r]
    if len(rows) != ev['pos_err_m']['n']:
        raise SystemExit(f'frames_eval rows {len(rows)} != result.json n {ev["pos_err_m"]["n"]}')
    e = np.array([r['pos_err_m'] for r in rows])
    y = np.array([r['yaw_err_deg'] for r in rows])
    s = np.array([r['std_xy_m'] for r in rows])
    t = np.array([r['t'] for r in rows])
    door = [near_door(r['gt']) for r in rows]
    man = json.loads((raw / 'manifest.json').read_text())
    map_path = VIS3 / 'maps' / 'zone_wide_door_walls_v3_notags.json'   # the run's frozen static map
    if sha(map_path) != man['code']['vision_frozen_sha256']['maps/zone_wide_door_walls_v3_notags.json']:
        raise SystemExit('static map hash differs from the run manifest')
    dx, dy = next(q for q in json.loads(map_path.read_text())['passages'] if q['kind'] == 'door')['center_m']
    near = [np.hypot(r['gt'][0] - dx, r['gt'][1] - dy) <= NEAR_R_M for r in rows]
    sc = {}
    for g, m in (('all', np.ones(len(rows), bool)), ('door_zone', np.array(door)), ('near_door_r050', np.array(near))):
        if m.any():
            sc |= {f'summary/{g}/pos_p50_m': pct(e[m], 50), f'summary/{g}/pos_p90_m': pct(e[m], 90),
                   f'summary/{g}/pos_p99_m': pct(e[m], 99), f'summary/{g}/pos_max_m': float(e[m].max()),
                   f'summary/{g}/yaw_p90_deg': pct(y[m], 90), f'summary/{g}/frames': int(m.sum())}
    ratio = e / s
    win = (t >= 90) & (t < 150)                                  # README: over-confident pick-up window
    sc |= {'sigma/std_xy_p50_m': pct(s, 50), 'sigma/err_over_sigma_p50': pct(ratio, 50),
           'sigma/err_over_sigma_p90': pct(ratio, 90), 'sigma/frac_err_gt_2sigma': round(float(np.mean(ratio > 2)), 4),
           'sigma/frac_err_gt_3sigma': round(float(np.mean(ratio > 3)), 4),
           'sigma/win090_150/pos_p50_m': pct(e[win], 50), 'sigma/win090_150/std_xy_p50_m': pct(s[win], 50)}
    rr, vp = res['robot_result'], res['vision_provider']
    sc |= {'result/sim_time_s': res['sim_s'], 'result/wall_time_s': man['wall_s'], 'result/commands': rr['commands'], 'result/llm_calls': 0,
           'result/door_passed': float(ev['door_passed']), 'result/assigned_box_in_slot': float(res['assigned_box_in_slot']),
           'evaluation/reported_success': float(res['m1_success']), 'result/false_confirmation': float(res['false_confirmation']),
           'result/pose_uncertain_events': rr['guards']['pose_uncertain_events'],
           'vision/worker_calls': vp['worker']['calls'], 'vision/inference_ms_p50': vp['inference_wall_ms']['p50'],
           'vision/inference_ms_p90': vp['inference_wall_ms']['p90'], 'vision/inference_ms_max': vp['inference_wall_ms']['max'],
           'vision/worker_startup_s': vp['worker']['startup_s']}
    step = [int(round(x * 100)) for x in t]
    timing = jsonl(raw / 'robots' / rid / 'vision_timing.jsonl')
    series = {'localization/pos_err_m': list(zip(step, e)), 'localization/std_xy_m': list(zip(step, s)),
              'localization/err_over_sigma': list(zip(step, ratio)), 'localization/yaw_err_deg': list(zip(step, y)),
              'vision/worker_ms': [(int(round(r['t'] * 100)), r['worker_ms']) for r in timing],
              'vision/pf_ms': [(int(round(r['t'] * 100)), r['pf_ms']) for r in timing]}
    files = ['result.json', 'manifest.json', 'eval_only/frames_eval.jsonl', f'robots/{rid}/vision_timing.jsonl']
    prov = {'label': LABEL, 'raw': str(raw), 'sha256': {f: sha(raw / f) for f in files},
            'deliver_outcome': res['deliver_outcome'], 'deliver_confirmation': res['deliver_confirmation'],
            'm1_failed_checks': res['m1_failed_checks'], 'door_crossings': ev['door_crossings_west_to_east'],
            'definitions': {'door_zone': 'VIS3/PR #210 box |x-2.2|<0.6, -0.45<y<0.55 (GT)',
                            'near_door_r050': f'GT within {NEAR_R_M} m of door centre ({dx}, {dy}) (README)',
                            'sigma': 'std_xy_m of the pose provider per frame; err_over_sigma = pos_err / std_xy',
                            'step': 'SIM time x 100', 'percentile': 'numpy linear (VIS3 pct)'},
            'sim_time_charge': vp['sim_time_charge'], 'llm': 'no-LLM scripted study layer; llm_calls 0'}
    hp = {'label': LABEL, 'mode': 'closed_loop', 'split': 'dev', 'episode': res['episode'], 'robot': rid,
          'provider': vp['provider'], 'config_sha8': vp['frozen_files_sha256']['selected_config_v3.json'][:8],
          'source_sha8': man['code']['sha'][:8],
          'deliver_outcome': res['deliver_outcome']}
    return sc, series, {'prov': prov, 'hp': hp}


def baselines(results_path: Path) -> list[tuple[str, dict, dict]]:
    r = json.loads(results_path.read_text())
    out = []
    for name, pooled, split, ep, cfg in (
            ('vis3-dev-a1', r['dev_variants']['a1_open']['pooled'], 'dev', 'dev pooled (offline)',
             r['dev_variants']['a1_open']['config_sha256']),
            ('vis3-test-vision', r['test']['metrics']['pooled']['vision'], 'test', 'test pooled (offline)',
             r['dev_variants']['a1_open']['config_sha256'])):
        sc = {f'summary/{g}/{k}': pooled[g][k] for g in ('all', 'door_zone') for k in KEYS
              if pooled.get(g, {}).get(k) is not None}
        sc |= {f'summary/{g}/frames': pooled[g]['n'] for g in ('all', 'door_zone') if g in pooled}
        hp = {'label': 'VIS3 offline baseline (open-loop replay of teacher renders)', 'mode': 'offline_replay',
              'split': split, 'episode': ep, 'robot': '-', 'provider': 'VIS3 a1_open', 'config_sha8': cfg[:8],
              'source_sha8': '619c0123', 'deliver_outcome': '-'}
        out.append((name, sc, {'prov': {'results': str(results_path), 'results_sha256': sha(results_path),
                                        'scope': 'offline localization only; no task, door, SIM or ms'}, 'hp': hp}))
    return out


def build(args):
    from scripts.tensorboard_tools.export import Writer
    out = args.logdir / args.snapshot
    if out.exists():
        raise SystemExit(f'{out} exists; snapshots are never overwritten')
    sc, series, meta = closed_loop(args.raw)
    runs = [('vw-s942-closed', sc, series, meta)] + [(n, s, {}, m) for n, s, m in baselines(args.results)]
    out.mkdir(parents=True)
    exported, at = [], time.time()
    for name, scal, ser, m in runs:
        (out / name).mkdir()
        w = Writer(out / name, at)
        for tag, v in scal.items():
            w.scalar(tag, float(v), 0)
        for tag, pts in ser.items():
            for step, v in pts:
                w.scalar(tag, float(v), int(step))
        w.text('provenance/source', m['prov'])
        w.hparams(m['hp'], HP_METRICS)
        w.close()
        exported.append({'name': name, 'hparams': m['hp'], 'counts': w.counts, 'scalars': scal,
                         'series_points': {k: len(v) for k, v in ser.items()}})
    (out / 'collection.json').write_text(json.dumps(
        {'schema': 'ugrp.vision_worker_dev.tensorboard_collection.v1', 'label': LABEL, 'research_result': False,
         'exported': exported, 'source_sha': args.source_sha, 'raw': str(args.raw),
         'vis3_results': str(args.results), 'vis3_results_sha256': sha(args.results), 'exported_at_s': at,
         'limits': 'one dev episode (seed 942), no-LLM, SYNC SIM; VIS3 rows are offline replays (other scope)'},
        indent=1, ensure_ascii=False) + '\n')
    print(f'{len(exported)} runs -> {out}')


def verify(args):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    out = args.logdir / args.snapshot
    col = json.loads((out / 'collection.json').read_text())
    sc, series, meta = closed_loop(args.raw)                     # recompute from raw, not from the collection
    want = {'vw-s942-closed': (sc, series)} | {n: (s, {}) for n, s, _ in baselines(args.results)}
    checked = mismatches = 0
    for item in col['exported']:
        acc = EventAccumulator(str(out / item['name']), size_guidance={'scalars': 0, 'tensors': 0})
        acc.Reload()
        tags = set(acc.Tags()['scalars'])
        scal, ser = want[item['name']]
        for tag, v in scal.items():
            checked += 1
            got = acc.Scalars(tag)[0].value if tag in tags else None
            if got is None or abs(got - float(v)) > 1e-5 * max(1., abs(float(v))):
                mismatches += 1
                print('MISMATCH', item['name'], tag, got, v)
        for tag, pts in ser.items():
            checked += 1
            got = [(s.step, s.value) for s in acc.Scalars(tag)] if tag in tags else []
            if len(got) != len(pts) or any(a[0] != b[0] or abs(a[1] - b[1]) > 1e-5 * max(1., abs(b[1]))
                                           for a, b in zip(got, pts)):
                mismatches += 1
                print('SERIES MISMATCH', item['name'], tag, len(got), len(pts))
    report = {'snapshot': str(out), 'runs': len(col['exported']), 'checked': checked, 'mismatches': mismatches,
              'raw_sha256': meta['prov']['sha256'], 'vis3_results_sha256': sha(args.results),
              'collection_sha256': sha(out / 'collection.json')}
    print(json.dumps(report, ensure_ascii=False))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    return 1 if mismatches else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--raw', type=Path, default=RAW)
    ap.add_argument('--results', type=Path, default=VIS3 / 'results' / 'results_v3.json')
    ap.add_argument('--logdir', type=Path, default=Path('/Users/changmin/projects/ugrp/outputs/tensorboard'))
    ap.add_argument('--snapshot', default='0927-vision-worker-dev')
    ap.add_argument('--source-sha', default='')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--report')
    args = ap.parse_args(argv)
    raise SystemExit(verify(args) if args.verify else build(args))


if __name__ == '__main__':
    main()
