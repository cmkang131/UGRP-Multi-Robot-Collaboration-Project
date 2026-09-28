"""Summarise offline_replay.json into replay_summary.json (min/max over PF seeds and runs)."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
rows = json.loads((HERE/'offline_replay.json').read_text())['rows']
out = {'part_A_failed_runs': {}, 'part_A_v5h_runs': {}, 'part_B': []}
for group, runs in (('part_A_failed_runs', ('v6-s911-b', 'v6-s911-ab', 'v6-s912-b', 'v6-s912-ab')),
                    ('part_A_v5h_runs', ('v6-s911-v5h', 'v6-s912-v5h'))):
    agg = defaultdict(list)
    for r in rows:
        if r['part'] == 'A' and r['run'] in runs:
            agg[r['schedule']].append(r)
    for sched, rs in agg.items():
        rec = [r for r in rs if r['recorded_seed']]
        def rng(key, rows=rs):
            v = [r[key] for r in rows if r.get(key) is not None]
            return [min(v), max(v)] if v else None
        out[group][sched] = {
            'n_rows': len(rs), 'recorded_seed_rows': len(rec),
            'std_xy_m_recorded_seed': rng('std_xy_m', rec), 'std_xy_m_all_seeds': rng('std_xy_m'),
            'std_yaw_rad_all_seeds': rng('std_yaw_rad'), 'eval_err_xy_m_all_seeds': rng('eval_err_xy_m'),
            'informative_fix_rows': sum(r['v6_informative_fix'] for r in rs),
            'sigma_within_guard_cap_rows': sum(bool(r.get('sigma_within_cap')) for r in rs),
            'arm_raise_decision_counts': {d: sum(r.get('arm_raise_decision') == d for r in rs)
                                          for d in ('clear', 'wait', 'blocked')},
            'belief_pan_1230_clear_rows': sum(bool(r.get('belief_pan_1230_clear')) for r in rs)}
for r in rows:
    if r['part'] == 'B':
        out['part_B'].append({k: r.get(k) for k in ('run', 'robot', 'schedule', 'until_s', 'first_informative_fix',
                                                     'std_xy_m', 'std_yaw_rad', 'eval_err_xy_m', 'gate_class',
                                                     'arm_raise_decision')})
(HERE/'replay_summary.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
