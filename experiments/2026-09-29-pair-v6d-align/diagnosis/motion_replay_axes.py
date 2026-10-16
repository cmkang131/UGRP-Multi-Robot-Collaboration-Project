"""Per-axis summary of motion_replay.txt (50 histories = 25 b-v6c cells x r1/r2; 36 are distinct).

Each line: GT body displacement over the align window and the displacement that the deterministic replay of the
published commands predicts with the default and the M1 ``fine`` profile. Ratio = predicted / GT, computed only
where |GT| is large enough for a ratio to mean something (x >= 0.05 m, y >= 0.03 m, yaw >= 0.03 rad).
Error = |predicted - GT| over all histories. The replay is deterministic (no noise, no slip scale) and was
built on the same b-v6c cells that motivated the fix, so it is an in-sample check, not a held-out one.
Usage: python3 motion_replay_axes.py > motion_replay_axes.txt
"""
import os
import re
import statistics as st

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'motion_replay.txt')
NUM = r'(-?\d+\.\d+)'
LINE = re.compile(r'^(\S+) (r\d) T=.*GT body d=\[' + ' '.join([NUM] * 3) + r'\] \| default=\[' + ' '.join([NUM] * 3) +
                  r'\] \| m1_fine=\[' + ' '.join([NUM] * 3) + r'\]')
AXES = (('x', 0, 0.05, 'mm', 1000), ('y', 1, 0.03, 'mm', 1000), ('yaw', 2, 0.03, 'mrad', 1000))


def rows():
    out = []
    for line in open(PATH):
        m = LINE.match(line)
        if m:
            v = [float(x) for x in m.groups()[2:]]
            out.append({'case': m.group(1), 'rid': m.group(2), 'gt': v[0:3], 'default': v[3:6], 'fine': v[6:9]})
    return out


def report(rs, title):
    print(f'{title}: n={len(rs)}')
    for name, k, thr, unit, scale in AXES:
        big = [r for r in rs if abs(r['gt'][k]) >= thr]
        for prof in ('default', 'fine'):
            ratios = sorted(r[prof][k] / r['gt'][k] for r in big)
            errs = [abs(r[prof][k] - r['gt'][k]) * scale for r in rs]
            if not ratios:
                continue
            print(f'  {name:3s} {prof:7s} ratio median {st.median(ratios):5.2f} (min {ratios[0]:.2f}, max {ratios[-1]:.2f}, '
                  f'n={len(big)} with |GT|>={thr}) | |error| mean {st.mean(errs):7.1f} {unit}, max {max(errs):7.1f} {unit} (all n={len(rs)})')


if __name__ == '__main__':
    rs = rows()
    report(rs, 'all histories')
    distinct = {tuple(r['gt'] + r['default'] + r['fine']): r for r in rs}
    report(list(distinct.values()), 'distinct histories (identical GT/default/fine triples merged)')
    print('yaw criterion of the stage-2 alignment gate: 52 mrad')
