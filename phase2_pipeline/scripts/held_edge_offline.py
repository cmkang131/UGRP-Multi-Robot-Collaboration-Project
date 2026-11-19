"""Offline replay of the held check on stored runs: old rule vs the lens-edge fix (--held-check-edge-fix).

For every 'held_check' tick of every robot folder found under the given roots (out-rK/ with commands.jsonl, eval-only.jsonl, summary.json and
rgb/rK/*.jpg) the held-look frames are found again from the carry rows the robot issued (CarryNav: arm raise 20 rows, back-off n rows + 5, pause 10
rows whose last 5 are the look, 5 trailing rows; a second look after a turn toward the pick point), PlaceMemory.box_on_floor is run on them with the
old rule and with edge_fix=True, and the verdict expression of CarryNav (more than half of the frames with a box ahead, or at least 2 frames with a box
within 0.30 m of the pick point) is applied. The recorded verdict (summary.json not_holding) must equal the replayed old verdict: that is the validity
check of the replay. The truth is read from the simulator rows (eval-only.jsonl: the target box lifted off the floor = held). The pick point of the
'at pick point' test uses the simulator pose and the box place at lift start, because the ceiling-camera pose is not stored (approximation; the old
verdict agrees with the recorded one for every row it was needed).

  python3 -B scripts/held_edge_offline.py ROOT [ROOT ...] [--json OUT.json]
"""
import argparse
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HELD_NEAR_X, HELD_NEAR_Y, HELD_AT_PICK_M, HELD_AT_PICK_FRAMES = (0.05, 0.95), 0.45, 0.30, 2     # as harness/carry_nav_v1.py
LIFTED_M = 0.10        # clearance of the target box above the floor: lifted = in the gripper


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def modules():
    gp = _load(ROOT / 'harness' / 'approach_survey_v1_parts' / 'ground_projection.py', 'ground_projection')
    pm = _load(ROOT / 'harness' / 'place_memory_v1.py', 'place_memory_v1')
    return pm.PlaceMemory(gp)


def look_ticks(commands, k):
    """Command indices of the held-look frames before the 'held_check' tick k (see the module doc), or None when the rows do not fit."""
    block, j = [], k - 1
    # robot_ahead_wait and talk_stand rows (free talk: the robot speaks, run_steps stand_hold) are pauses inside the block: wheels 0, no carry step is taken, so they are skipped
    while j >= 0 and commands[j]['source'] in ('carry_code', 'robot_ahead_wait', 'talk_stand'):
        if commands[j]['source'] == 'carry_code':
            block.append(j)
        j -= 1
    block.reverse()
    moving = lambda i: any(abs(w) > 1e-9 for w in commands[block[i]]['command']['wheels'])
    if len(block) < 30:
        return None
    n = 0
    while 20 + n < len(block) and moving(20 + n):
        n += 1
    pause = 20 + (n + 5 if n else 0)
    looks = [pause + 5 + i for i in range(5)]
    turn_at, turn = pause + 15, 0
    while turn_at + turn < len(block) and moving(turn_at + turn):
        turn += 1
    if turn:
        looks += [turn_at + turn + 10 + i for i in range(5)]
    return [block[i] for i in looks if i < len(block)]


def verdict(frames, picked_world):
    """frames: [(points in the body frame, pose (x, y, yaw) in the world or None)] -> True when the box is judged left on the floor."""
    near = [any(HELD_NEAR_X[0] < x < HELD_NEAR_X[1] and abs(y) < HELD_NEAR_Y for x, y in pts) for pts, _ in frames]
    at_pick = []
    for pts, pose in frames:
        if picked_world is None or pose is None:
            continue
        c, s = math.cos(pose[2]), math.sin(pose[2])
        at_pick.append(any(math.hypot(pose[0] + c * x - s * y - picked_world[0], pose[1] + s * x + c * y - picked_world[1]) < HELD_AT_PICK_M
                           for x, y in pts))
    return sum(near) * 2 >= max(1, len(near)) or sum(at_pick) >= HELD_AT_PICK_FRAMES


def replay(places, root):
    rows = []
    for dirpath, dirnames, filenames in os.walk(root):
        if 'commands.jsonl' not in filenames or not os.path.basename(dirpath).startswith('out-r'):
            continue
        rob = os.path.basename(dirpath)[4:]
        commands = [json.loads(line) for line in open(os.path.join(dirpath, 'commands.jsonl'))]
        evals = [json.loads(line) for line in open(os.path.join(dirpath, 'eval-only.jsonl'))]
        summary = json.load(open(os.path.join(dirpath, 'summary.json')))
        t0 = commands[0]['command']['t']
        recorded = [e['at_s'] for e in summary.get('not_holding') or [] if 'floor' in e.get('rule', '')]
        run = os.path.basename(os.path.dirname(dirpath))
        for k, row in enumerate(commands):
            if row['source'] != 'held_check':
                continue
            ticks = look_ticks(commands, k)
            t = row['command']['t']
            ev = min(range(len(evals)), key=lambda i: abs(evals[i]['t'] - t))
            e = evals[ev]
            kind = 'cyan' if e['target_object'].startswith('cyan') else 'red'
            # where the box stood when the lift began: walk back while the box is off the floor
            i = ev
            while i > 0 and evals[i]['clearance'] > 0.02:
                i -= 1
            picked = (evals[i]['object_x'], evals[i]['object_y']) if 'object_x' in evals[i] else None
            out = {'run': run, 'robot': rob, 't_s': round(t - t0, 1), 'target': e['target_object'], 'force_N': round(max(e['forces']), 1),
                   'clearance_m': round(e['clearance'], 3), 'truth': 'held' if e['clearance'] >= LIFTED_M else 'not held',
                   'recorded': 'not held' if any(abs(r - (t - t0)) < 0.35 for r in recorded) else 'held'}
            if ticks is None:
                out['error'] = 'carry rows do not fit'
                rows.append(out)
                continue
            old, new, excluded = [], [], []
            for tick in ticks:
                posture = {int(a): int(b) for a, b in commands[tick - 1]['command']['pwm'].items()}
                jpeg = open(os.path.join(dirpath, 'rgb', rob, '%06d.jpg' % tick), 'rb').read()
                ev_t = min(range(len(evals)), key=lambda i2: abs(evals[i2]['t'] - commands[tick]['command']['t']))
                pose = (evals[ev_t]['base_x'], evals[ev_t]['base_y'], evals[ev_t]['base_yaw']) if 'base_x' in evals[ev_t] else None
                old.append((places.box_on_floor(jpeg, posture, kind), pose))
                new.append((places.box_on_floor(jpeg, posture, kind, edge_fix=True), pose))
                excluded += places.last_edge_excluded
            out.update(old='not held' if verdict(old, picked) else 'held', new='not held' if verdict(new, picked) else 'held',
                       frames=len(ticks), excluded_blobs=len(excluded),
                       excluded_h=sorted({b['h'] for b in excluded}), excluded_w=sorted({b['w'] for b in excluded}))
            rows.append(out)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('roots', nargs='+', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    places = modules()
    rows = []
    for root in args.roots:
        rows += replay(places, root)
    rows.sort(key=lambda r: (r['run'], r['robot'], r['t_s']))
    print('| run | robot | t (s) | box | force N | lifted m | truth | recorded | old replay | edge fix | blobs removed (h px) |')
    print('|---|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        if 'error' in r:
            print('| %s | %s | %s | %s | | | %s | %s | %s | | |' % (r['run'], r['robot'], r['t_s'], r['target'], r['truth'], r['recorded'], r['error']))
            continue
        print('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %d (%s) |' % (
            r['run'], r['robot'], r['t_s'], r['target'], r['force_N'], r['clearance_m'], r['truth'], r['recorded'], r['old'], r['new'],
            r['excluded_blobs'], ','.join(map(str, r['excluded_h'])) or '-'))
    ok = [r for r in rows if 'error' not in r]
    print()
    print('rows %d, replay errors %d' % (len(ok), len(rows) - len(ok)))
    print('replay validity: old replay == recorded verdict in %d of %d rows' % (sum(r['old'] == r['recorded'] for r in ok), len(ok)))
    for name in ('held', 'not held'):
        sub = [r for r in ok if r['truth'] == name]
        print('truth %s: %d rows; old says not held in %d, edge fix says not held in %d' % (
            name, len(sub), sum(r['old'] == 'not held' for r in sub), sum(r['new'] == 'not held' for r in sub)))
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
