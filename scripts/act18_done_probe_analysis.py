"""ACT18 done-head probe: raw vs temporal-ensemble done probability from one group.

Reads the default-off `--record-done-prob` JSONL rows (one full decoded chunk per
prediction) plus the frozen evaluation-only physics stream, then reports:
  * raw per-tick first-step probability and exact temporal-ensemble probability
  * threshold sweeps (frozen decode threshold .65 plus 0.5/0.3/0.2/0.1)
  * the physical state (finger force/lift/speed) at candidate firing ticks
Recording hook only; no policy input, command, ensemble or scoring change.
"""
import argparse
import json
from pathlib import Path

import numpy as np

COEFF = .01             # frozen ACT temporal ensemble coefficient
ACTUAL_THRESHOLD = .65  # frozen harness grasp_act_contract.decode_action
SWEEP = (.65, .5, .3, .2, .1)


def read_rows(paths):
    rows = []
    for path in paths:
        for line in Path(path).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def ensemble_series(rows):
    world = rows[0]['world']
    if any(row['world'] != world for row in rows):
        raise ValueError('mixed worlds in one series')
    chunk = rows[0]['chunk']
    if any(row['chunk'] != chunk for row in rows):
        raise ValueError('chunk size changed within a world')
    ticks = sorted(rows, key=lambda row: row['t'])
    if len({row['t'] for row in ticks}) != len(ticks):
        raise ValueError('duplicate prediction tick')
    series = [dict(t=row['t'], skill=row['skill'], sample_id=row['sample_id'],
                   raw=float(row['done_probs'][0]), logits=[float(x) for x in row['done_probs']])
              for row in ticks]
    ensemble = []
    for index in range(len(series)):
        alive = [(j, series[j]['logits'][index - j]) for j in range(index + 1)
                 if index - j < chunk]
        weights = np.exp(-COEFF * np.arange(len(alive), dtype=np.float64))
        averaged = float(np.average([value for _, value in alive], weights=weights))
        ensemble.append(dict(t=series[index]['t'], skill=series[index]['skill'], value=averaged))
    return series, ensemble


def threshold_report(series, ensemble):
    report = dict(ticks=len(series), raw_max=max(item['raw'] for item in series),
                  ensemble_max=max(item['value'] for item in ensemble), thresholds={})
    for threshold in SWEEP:
        raw_ticks = [item['t'] for item in series if item['raw'] >= threshold]
        ensemble_ticks = [item['t'] for item in ensemble if item['value'] >= threshold]
        report['thresholds'][str(threshold)] = dict(
            raw_first=raw_ticks[0] if raw_ticks else None, raw_count=len(raw_ticks),
            ensemble_first=ensemble_ticks[0] if ensemble_ticks else None,
            ensemble_count=len(ensemble_ticks))
    argmax = max(range(len(ensemble)), key=lambda i: ensemble[i]['value'])
    report['ensemble_argmax'] = dict(t=ensemble[argmax]['t'], skill=ensemble[argmax]['skill'],
                                     value=ensemble[argmax]['value'])
    argmax_raw = max(range(len(series)), key=lambda i: series[i]['raw'])
    report['raw_argmax'] = dict(t=series[argmax_raw]['t'], skill=series[argmax_raw]['skill'],
                                value=series[argmax_raw]['raw'])
    return report


def physics_state(evaluation, world):
    events = [json.loads(line) for line in (evaluation/'owner/evaluation-only.jsonl').open()]
    rows = [event for event in events
            if event.get('world') == world and event.get('speed') is not None]
    lift_ticks = [event['t'] for event in rows if event.get('lift_success')]
    grip = [(event['t'], max(event.get('finger_forces') or [0, 0])) for event in rows]
    return dict(
        physical_lift_first_t=lift_ticks[0] if lift_ticks else None,
        finger_force_max_first_t=next((t for t, force in grip if force > .5), None),
        speed_max=round(max((event.get('speed') or 0) for event in rows), 4),
        min_clearance=round(min(event.get('min_z', 0) for event in rows), 5), rows=len(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--logs', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('done probe analysis default OFF')
    plans = json.loads((args.evaluation/'initial-plans.json').read_text())['episodes']
    rows = read_rows(args.logs)
    by_world = {}
    for row in rows:
        by_world.setdefault(row['world'], []).append(row)
    results = []
    for world in sorted(by_world):
        series, ensemble = ensemble_series(by_world[world])
        table = threshold_report(series, ensemble)
        plan = plans[world]
        physics=physics_state(args.evaluation, world)
        actual=table['thresholds'][str(ACTUAL_THRESHOLD)]
        fire=actual['ensemble_first'];raw_fire=actual['raw_first']
        lift=physics['physical_lift_first_t'];force=physics['finger_force_max_first_t']
        alignment=dict(
            done_threshold_fire_t=fire,
            done_ok_after_lift=(None if fire is None or lift is None else bool(fire>=lift)),
            done_early_before_grip=(None if fire is None or force is None else bool(fire<force)),
            raw_threshold_fire_t=raw_fire,
            ensemble_fire_ticks=actual['ensemble_count'])
        results.append(dict(world=world, seed=plan['seed'], kind=plan['kind'],
                            table=table, physics=physics, alignment=alignment))
    report = dict(schema='ugrp.act18.done_probe.v1', evaluation=str(args.evaluation),
                  logs=[str(path) for path in args.logs],
                  threshold=ACTUAL_THRESHOLD, ensemble_coeff=COEFF, worlds=results,
                  note='raw=frozen single-step completion probability; ensemble=exact temporal ensemble replay')
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({str(w['world']): dict(seed=w['seed'], raw_max=round(w['table']['raw_max'], 4),
                                             ensemble_max=round(w['table']['ensemble_max'], 4),
                                             lift_t=w['physics']['physical_lift_first_t'],
                                             fire=w['alignment']['done_threshold_fire_t'],
                                             ok_after_lift=w['alignment']['done_ok_after_lift'],
                                             early=w['alignment']['done_early_before_grip'])
                      for w in results}, indent=1))


if __name__ == '__main__':
    main()
