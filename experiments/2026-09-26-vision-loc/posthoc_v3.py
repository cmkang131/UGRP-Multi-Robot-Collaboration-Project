"""Post-hoc (written after the round-3 test was scored; not pre-registered): door-zone error along and across door_1.

door_1 is crossed along x, so |dx| is the along-track and |dy| the lateral error.
Reads the scored test estimates and eval-only GT; writes results/posthoc_v3_door_axes.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vision_loc as vl  # noqa: E402
import vision_loc_io as vio  # noqa: E402


def main():
    pre = json.loads((HERE/'prereg_v3.json').read_text())
    est_dir = vio.PRIMARY_OUT/'r3'/'test'/'estimates'
    out = HERE/'results'/'posthoc_v3_door_axes.json'
    if out.exists():
        raise SystemExit(f'refusing to overwrite {out}')
    rep = {'schema': 'ugrp.vision_loc.posthoc_door_axes.v1', 'post_hoc': True, 'episodes': pre['test_episodes'],
           'group': 'door_loaded (|x - 2.2| < 0.6, -0.45 < y < 0.55, own load state loaded)', 'filters': {}}
    for f in ('vision', 'oracle', 'boundary', 'deadreck'):
        dx, dy = [], []
        for ep in pre['test_episodes']:
            ev = {r['frame']: r for r in vl.read_jsonl(vio.RENDER_ROOT/ep/'eval_only'/'frames_eval.jsonl')}
            for r in vl.read_jsonl(est_dir/f'{ep}.estimates.jsonl'):
                g = ev[r['frame']]['gt']
                if abs(g[0] - 2.2) < .6 and -.45 < g[1] < .55 and r['loaded'] and r.get(f):
                    x, y, _ = r[f]['xyyaw']
                    dx.append(x - g[0])
                    dy.append(y - g[1])
        dx, dy = np.asarray(dx), np.asarray(dy)
        rep['filters'][f] = {'n': int(dx.size),
                             'along_abs_p50_m': round(float(np.percentile(np.abs(dx), 50)), 4),
                             'along_abs_p90_m': round(float(np.percentile(np.abs(dx), 90)), 4),
                             'along_mean_m': round(float(dx.mean()), 4),
                             'lateral_abs_p90_m': round(float(np.percentile(np.abs(dy), 90)), 4),
                             'lateral_mean_m': round(float(dy.mean()), 4)}
    out.write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps(rep['filters'], indent=1))


if __name__ == '__main__':
    main()
