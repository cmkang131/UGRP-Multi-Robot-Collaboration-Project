"""Read frozen release admissions on gcp3; no generation or simulator call."""
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import socket

assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
root = Path('/home/ugrp/ugrp-sim')
plan_path = root / 'ops-reviews/warp8/release-batch-plan-current.json'
plan = json.loads(plan_path.read_text())
rows, histogram = [], Counter()
for group in plan['groups']:
    if group['candidate'] != 'current_A':
        continue
    compiled = root / 'runs/warp8' / group['tag'].replace('-r1', '-c312')
    for i, seed in enumerate(group['seeds']):
        path = compiled / f'world-{i:03d}/placement-admission.json'
        admission = json.loads(path.read_text())
        assert admission['mode'] == 'placement_graspable_filter_v1'
        assert admission['setup_only'] and not admission['runtime_truth_used']
        for end, values in admission['ends'].items():
            if values['free_goal_N'] == 0:
                histogram[(end, values['blocked_object'])] += 1
        rows.append(dict(seed=seed, scenario=group['scenario'], accepted=admission['accepted'],
            ends=admission['ends'], path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
assert len(rows) == len({x['seed'] for x in rows}) == 40
accepted = sum(x['accepted'] for x in rows)
out = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), simulation_host='gcp3', analysis_host='gcp3_CPU',
    plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(), source_sha=plan['source_sha'],
    N=40, accepted_N=accepted, rejected_N=40-accepted, rows=rows,
    rejection_distribution=[dict(reason_category='placement_zero_certified_pose', end=k[0],
        blocked_object=k[1], count=v, min_gap_m=None) for k,v in histogram.most_common()],
    funnel=[dict(stage='frozen_A_plans', passed_cumulative_N=40, rejected_N=0),
        dict(stage='static_placement_admission', passed_cumulative_N=accepted, rejected_N=40-accepted)],
    reproduction=['python3', str(Path(__file__).resolve())],
    scope='compiled static admissions only; A/B have identical plans; not40 physical release outcomes or a new generated-placement population')
target = root / 'ops-reviews/warp8/warp8b-release-placement-admission.json'
assert not target.exists()
target.write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps(out))
