"""crate11: top-down plot of EVALUATION-ONLY ground-truth paths (data plot, not a render, not a video frame)."""
import json, math, sys
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

FAILS = [('crate-diag-77981-49d11b8e', 'r1'), ('crate-diag-77982-49d11b8e', 'r1'), ('crate-diag-77988-49d11b8e', 'r1'),
         ('crate-diag-77989-49d11b8e', 'r1'), ('crate-reproduction-77969-49d11b8e', 'r2'), ('crate-reproduction-77978-49d11b8e', 'r1'),
         ('crate-reproduction-77979-49d11b8e', 'r1'), ('crate-diag-77978-bf31840f', 'r1'), ('crate-diag-77979-bf31840f', 'r1')]


def main(trace_dir, out):
    fig, axs = plt.subplots(3, 3, figsize=(15, 14))
    for ax, (name, rid) in zip(axs.flat, FAILS):
        t = json.load(open(Path(trace_dir) / f'{name}.trace.json'))['trace'][rid]
        fin = json.load(open(Path(trace_dir) / f'{name}.final.json'))
        xs = [y['gt']['pose'][0] for y in t]; ys = [y['gt']['pose'][1] for y in t]
        cx, cy, cyaw = t[0]['gt']['crate_pose']
        c, s = math.cos(cyaw), math.sin(cyaw)
        body = [(cx + c * a - s * b, cy + s * a + c * b) for a, b in ((-.07, -.05), (.07, -.05), (.07, .05), (-.07, .05))]
        ax.add_patch(Polygon(body, color='tab:pink', alpha=.8))
        for sgn, col in ((-1, 'tab:green'), (1, 'tab:blue')):
            lug = [(cx + c * (sgn * .09 + a) - s * b, cy + s * (sgn * .09 + a) + c * b) for a, b in ((-.03, -.02), (.03, -.02), (.03, .02), (-.03, .02))]
            ax.add_patch(Polygon(lug, color=col))
        ax.axhline(-3.125, color='k'); ax.text(cx - .9, -3.115, 'south wall face y=-3.125', fontsize=7)
        sc = ax.scatter(xs, ys, c=[y['elapsed'] for y in t], s=4, cmap='viridis')
        o = max((i for i, y in enumerate(t) if any(y['wheels'])), default=0) + 1
        ax.plot(xs[min(o, len(xs) - 1)], ys[min(o, len(xs) - 1)], 'rx', ms=10, label=f'zero-run start {t[min(o,len(t)-1)]["elapsed"]:.1f}s')
        ax.set_xlim(cx - 1., cx + 1.); ax.set_ylim(cy - 1., cy + .8); ax.set_aspect('equal')
        ax.set_title(f'{name[6:]} {rid} {fin["result_outcomes"][rid]}', fontsize=8); ax.legend(fontsize=7, loc='upper left')
    fig.suptitle('crate11 eval-only GT paths (colour = elapsed s from grasp start; green=teal lug, blue=blue lug)')
    fig.savefig(out, dpi=80)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
