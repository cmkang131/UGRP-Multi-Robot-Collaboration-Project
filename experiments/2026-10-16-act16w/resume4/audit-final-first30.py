"""Owned-L4 first30 issued-command statistics; no physics or policy changes."""
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import statistics
from itertools import islice

R = Path('/home/ugrp/ugrp-sim/runs/act16w-native-experiment-r1')
rows, receipts, latencies = [], [], []
prefix_root = R / 'first30-action-prefixes'
prefix_root.mkdir(exist_ok=False)
for group in sorted((R / 'final40').glob('group-*')):
    plans = json.loads((group / 'plans.json').read_text())['episodes']
    evaluation = group / 'evaluation'
    actions_path = evaluation / 'actor-actions.jsonl'
    with actions_path.open() as stream:
        prefix = ''.join(islice(stream, 300))
    actions = [json.loads(line) for line in prefix.splitlines() if line.strip()]
    complete_path = evaluation / 'summary.json'
    complete = complete_path.exists() and json.loads(complete_path.read_text()).get('complete')
    assert len(actions) >= 300 or complete, 'wait for actual30SIM or closed early group'
    saved_prefix = prefix_root / (group.name + '.jsonl')
    saved_prefix.write_text(prefix)
    receipts.append(dict(original=str(actions_path), preserved_prefix=str(saved_prefix),
                         prefix_lines=len(actions), prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest()))
    path = group / 'plans.json'
    receipts.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    first30 = evaluation / 'first30.json'
    if first30.exists():
        latency = json.loads(first30.read_text())['world_latency_wall_per_SIM']
        latencies.extend([latency] * len(plans))
    for index, plan in enumerate(plans):
        skills, signs = Counter(), Counter()
        repeated, previous, active_steps, done = 0, None, 0, False
        for step, row in enumerate(actions[:300]):
            command = row['actions'][index]['command']
            skills[row['skills'][index]] += 1
            pattern = tuple((value > 0) - (value < 0) for value in command['wheels'])
            signs[str(pattern)] += 1
            exact = json.dumps({key: value for key, value in command.items() if key != 't'}, sort_keys=True)
            repeated += int(exact == previous)
            previous = exact
            active_steps += 1
            done = bool(row['actions'][index]['done'])
            if done:
                break
        rows.append(dict(seed=plan['seed'], kind=plan['kind'], observed_SIM_s=active_steps * .1,
                         first30_active_steps=active_steps, skills=dict(skills),
                         wheel_sign_patterns=dict(signs), exact_adjacent_command_repeats=repeated,
                         issued_sequence_done_in_first30=done))
assert len(rows) == 40
out = dict(status='complete', utc=datetime.now(timezone.utc).isoformat(), N=40, rows=rows,
           skill_counts=dict(sum((Counter(row['skills']) for row in rows), Counter())),
           issued_sequence_done_first30=sum(row['issued_sequence_done_in_first30'] for row in rows),
           speed=dict(worlds_in_groups_reaching30=len(latencies), closed_group_without30_world_N=40-len(latencies),
                      group_membership_weighted_latency_median_wall_per_SIM=statistics.median(latencies),
                      min=min(latencies), max=max(latencies), speed_pass=False,
                      scope='group latency weighted by group membership, not individual early-done latency; includes startup/compilation; groups closed before30SIM excluded'),
           LLM_calls=0, prompt_tokens=0, total_LLM_tokens=0,
           ACT_forward_call_count='not separately instrumented; no estimate from command count',
           physics_steps=0, policy_changes=0, raw=receipts,
           scope='first300 issued steps or first sequence done; excludes post-terminal repeated placeholders; commands are not measured motion or success',
           period_SIM_s=.1, period_source='unchanged registered ACT period/chunk executor',
           script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
path = R / 'native-final-first30-statistics.json'
with path.open('x') as stream:
    json.dump(out, stream, indent=2)
    stream.write('\n')
print(json.dumps({key: out[key] for key in ('status', 'N', 'skill_counts', 'issued_sequence_done_first30', 'speed')}))
