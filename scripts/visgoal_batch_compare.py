"""Compare two visgoal run dirs tick by tick (diagnostic only).

Used to test whether MJWarp nworld batching leaves each world's per-episode
commands, stage sequence and eval-only pose identical to the sequential
nworld=1 run.  No control input is read from here.
"""
import argparse
import json
import math
from pathlib import Path


def load(run, episode):
    out = run / 'episodes' / f'e{episode:02d}'
    ep = json.loads((out / 'episode.json').read_text())
    commands = json.loads((out / 'commands.json').read_text())
    frames = json.loads((out / 'eval-only.json').read_text())['frames']
    stages = []
    with (out / 'trace.jsonl').open() as fh:
        for line in fh:
            stages.append(json.loads(line)['stage'])
    return ep, commands, frames, stages


def compare(a, b, episode):
    ea, ca, fa, sa = load(a, episode)
    eb, cb, fb, sb = load(b, episode)
    n = min(len(ca), len(cb))
    wheel_diff = 0.
    duration_diff = 0.
    command_mismatch = 0
    for i in range(n):
        wd = max(abs(x - y) for x, y in zip(ca[i]['wheels'], cb[i]['wheels']))
        dd = max(abs(x - y) for x, y in zip(ca[i]['duration_s'],
                                            cb[i]['duration_s']))
        wheel_diff = max(wheel_diff, wd)
        duration_diff = max(duration_diff, dd)
        if wd > 1e-9 or dd > 1e-9:
            command_mismatch += 1
    m = min(len(fa), len(fb))
    pose_diff = 0.
    for i in range(m):
        pa, pb = fa[i]['pose'], fb[i]['pose']
        d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        dyaw = abs(math.atan2(math.sin(pa[2] - pb[2]),
                              math.cos(pa[2] - pb[2])))
        pose_diff = max(pose_diff, d, dyaw)
    s = min(len(sa), len(sb))
    stage_mismatch = sum(1 for i in range(s) if sa[i] != sb[i])
    keys = ('status', 'found', 'colour_seen', 'arrived_declared',
            'arrival_verdict_gt_inside_zone_B', 'entered_zone_gt_any', 'sim_s')
    return dict(
        episode=episode,
        a=dict(status=ea['status'], found=ea['found'], sim_s=ea['sim_s'],
               commands=len(ca), frames=len(fa)),
        b=dict(status=eb['status'], found=eb['found'], sim_s=eb['sim_s'],
               commands=len(cb), frames=len(fb)),
        same=dict((k, ea.get(k) == eb.get(k)) for k in keys),
        command_mismatch=command_mismatch, command_n=n,
        max_wheel_diff=wheel_diff, max_duration_diff=duration_diff,
        pose_n=m, max_pose_or_yaw_diff=pose_diff,
        stage_n=s, stage_mismatch=stage_mismatch)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('a', type=Path)
    p.add_argument('b', type=Path)
    p.add_argument('--episodes', default='0,1')
    a = p.parse_args()
    eps = [int(x) for x in a.episodes.split(',') if x != '']
    print(json.dumps([compare(a.a, a.b, e) for e in eps], indent=2))


if __name__ == '__main__':
    main()
