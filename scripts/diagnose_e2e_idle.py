"""Read-only bounded ledger audit; may be piped to remote python3 on stdin.

No imports from the controller, no writes, no image/npz reads. Evaluation
coordinates are used only in this offline report, never in a control fixture.
"""
import collections
import datetime
import hashlib
import json
import math
from pathlib import Path
import sys


def rows(path, hashes):
    size = path.stat().st_size
    digest = hashlib.sha256()
    consumed = 0
    with path.open('rb') as stream:
        while consumed < size:
            line = stream.readline(size-consumed)
            if not line.endswith(b'\n'):
                break  # a writer may be halfway through the last record
            consumed += len(line)
            digest.update(line)
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # log.txt also contains ordinary text
    hashes.append(dict(path=str(path), bytes=consumed, sha256=digest.hexdigest(),
                       scope='complete-line prefix at read; running source may grow'))


def small(path, hashes):
    data = path.read_bytes()
    hashes.append(dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return json.loads(data)


def moving(command):
    return command.get('kind') == 'mecanum' and any(command.get(k, 0) for k in ('forward', 'left', 'turn'))


def audit(run):
    hashes = []
    log = list(rows(run/'log.txt', hashes))
    log = [r for r in log if 'sim_s' in r]
    cutoff = log[-1]['sim_s']
    raw = run/'raw'
    if not raw.exists():
        raw = next(run.glob('*/raw'))
    bundle = small(raw/'bundle.json', hashes)
    setup = small(raw/'eval_only/setup.json', hashes)
    bounds = small(raw/'inputs/static_map.json', hashes)['bounds_m']
    progress = list(rows(raw/'progress.jsonl', hashes))
    origin = progress[0]['t']
    progress = [r for r in progress if r['t'] <= cutoff+origin+1e-7]
    responses = []
    for path in sorted((raw/'wire').glob('*-response.json')):
        value = small(path, hashes)
        responses.append(dict(path=str(path), choices=value.get('choices')))
    result = dict(run=run.name, raw=str(raw), source_sha=bundle['source_sha'],
                  bundle=bundle['execution_bundle_id'], options=bundle['e2e_options'],
                  cutoff_sim_s=cutoff, health=log[-1], llm_responses=responses, robots=[])
    for rid in ('r1', 'r2'):
        data = [r for r in rows(raw/f'robots/{rid}/ownmap.jsonl', hashes) if r['t'] <= cutoff]
        last = data[-1]
        last_motion = next((r['t'] for r in reversed(data) if moving(r['command'])), None)
        idle = [r for r in data if last_motion is None or r['t'] > last_motion]
        start = idle[0]['t'] if idle else None
        events = [e for r in data for e in (r.get('exploration') or {}).get('events', [])]
        finish = [e for e in events if e['reason'] == 'exploration_finished_no_frontier']
        boundary = finish[-1]['t'] if finish else start
        selected = [r for r in data if boundary is not None and boundary-1 <= r['t'] <= boundary+.4]
        at = last['pose_own_m']
        x, y, _, yaw = setup['spawns'][rid]
        world = [x+math.cos(yaw)*at[0]-math.sin(yaw)*at[1],
                 y+math.sin(yaw)*at[0]+math.cos(yaw)*at[1]]
        truth = progress[-1]['robots'][rid]['base_xyz_m'][:2]
        pc = last.get('pose_continuity') or {}
        stall_counts = collections.Counter((r.get('stall_odometry') or {}).get('status') for r in data)
        commands = [r for r in rows(raw/f'robots/{rid}/commands.jsonl', hashes)
                    if origin+cutoff-100 < r['t'] <= origin+cutoff and moving(r)]
        result['robots'].append(dict(robot=rid, idle_since_sim_s=start,
            idle_duration_s=0 if start is None else round(cutoff-start, 3),
            commands_last_100s=len(commands),
            translation_last_100s=sum(bool(c.get('forward', 0) or c.get('left', 0)) for c in commands),
            finish_event=finish[-1] if finish else None,
            last_exploration=last.get('exploration'), navigation_status=last.get('navigation_status'),
            stage=last['stage'], command=last['command'], pose_own_m=at,
            terminal_context_events=[e for e in events if boundary is not None and boundary-35 <= e['t'] <= boundary+.4],
            state_window=selected, last_state=last,
            event_counts=dict(collections.Counter(e['reason'] for e in events)),
            stall_status_counts=dict(stall_counts),
            missing_saved_state=['costmap', 'frontier count', 'complete blacklist', 'visited targets'],
            evaluation_only=dict(bounds_world_m=bounds, own_pose_transformed_world_m=world,
                actual_world_m=truth, xy_error_m=math.dist(world, truth),
                estimated_outside=not(bounds[0] <= world[0] <= bounds[1] and bounds[2] <= world[1] <= bounds[3]),
                actual_outside=not(bounds[0] <= truth[0] <= bounds[1] and bounds[2] <= truth[1] <= bounds[3]),
                map_odom_xy_difference_m=math.dist(pc['map_pose'][:2], pc['odom_pose'][:2]) if 'map_pose' in pc else None)))
    result['input_hashes'] = hashes
    return result


if __name__ == '__main__':
    base = Path.home()/'ugrp-sim/runs'
    runs = sorted(base.glob(sys.argv[1]))
    print(json.dumps(dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          runs=[audit(p) for p in runs]), ensure_ascii=False))
