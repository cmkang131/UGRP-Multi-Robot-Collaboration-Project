"""Split the shape survey into stationary and in-motion frames (offline, read only).

The v6 controller only feeds settled frames to the relative track (issued
arm/look/drive commands set motion_until; a frame that precedes the issued
camera command is rejected). The saved v5 logs also contain frames captured
while the arm, pan or base was still moving; their recorded servo pulses are
the latest *issued* command, so projecting them with that FK is not a
controller input. This script labels each surveyed frame with the time since
the robot's last arm(3-6)/look/drive/mecanum command and summarizes
stationary frames (>= SETTLE_S) separately. GT is used only to score.

Usage: survey_stationary.py SURVEY_DIR [HEAD_JSON ...]
"""
import bisect, glob, hashlib, json, sys
from collections import defaultdict
from pathlib import Path

SETTLE_S = .6   # v6 relook settle after a pan/arm move (zone_pair_align / zone_pair_grasp)
OUT = Path('/Users/changmin/projects/ugrp/outputs')
ROOT_OF = {}


def moving_times(root, run):
    times = defaultdict(list)
    for line in open(OUT/root/run/'commands.jsonl'):
        c = json.loads(line)
        if c['kind'] in ('look', 'drive', 'mecanum') or (c['kind'] == 'arm' and int(c['servo_id']) in (3, 4, 5, 6)):
            times[c['robot_id']].append(c['t'])
    return {k: sorted(v) for k, v in times.items()}


def frame_times(root, run, rid):
    out = {}
    for f in glob.glob(str(OUT/root/run/'inputs'/rid/'*.json')):
        o = json.load(open(f))
        out[o['frame_id']] = o['sim_time']
    return out


def label(rows):
    cache = {}
    for r in rows:
        key = (r['root'], r['run'])
        if key not in cache:
            cache[key] = (moving_times(*key), {rid: frame_times(*key, rid) for rid in ('r1', 'r2')})
        moves, frames = cache[key]
        t = frames[r['rid']][r['frame']]
        ts = moves.get(r['rid'], [])
        i = bisect.bisect_right(ts, t+1e-6)
        r['since_motion_s'] = None if i == 0 else round(t-ts[i-1], 3)
    return rows


def summary(rows):
    fits = [r for r in rows if 'err' in r]
    viol = [r for r in fits if r['err'] > r['bound']]
    return {'frames': len(rows), 'fits': len(fits),
            'ready_fits_bound_le_5cm': sum(r['bound'] <= .05 for r in fits),
            'violations_err_gt_bound': len(viol),
            'max_err_over_bound': max((r['err']/r['bound'] for r in fits), default=None),
            'violations': [{k: r[k] for k in ('root', 'run', 'rid', 'frame', 'view', 'err', 'bound', 'since_motion_s')}
                           for r in viol]}


def main():
    survey = Path(sys.argv[1])
    rows = label(json.load(open(survey/'frames.json')))
    still = [r for r in rows if r['since_motion_s'] is None or r['since_motion_s'] >= SETTLE_S]
    look = [r for r in still if r['view'] != 'other']
    result = {'settle_s': SETTLE_S, 'survey_frames_sha256': hashlib.sha256((survey/'frames.json').read_bytes()).hexdigest(),
              'all_frames': summary(rows), 'stationary': summary(still), 'stationary_look_postures': summary(look),
              'in_motion': summary([r for r in rows if r not in still])}
    heads = []
    for path in sys.argv[2:]:
        head = json.load(open(path))
        run_root = {r['run']: r['root'] for r in rows}
        for r in head:
            r['root'] = run_root[r['run']]
        heads += head
    if heads:
        heads = label(heads)
        result['head_look_postures_all'] = summary(heads)
        result['head_look_postures_stationary'] = summary(
            [r for r in heads if r['since_motion_s'] is None or r['since_motion_s'] >= SETTLE_S])
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
