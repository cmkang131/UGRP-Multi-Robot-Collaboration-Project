#!/usr/bin/env python3
"""Apply the v101 (#376) rest_noise rule, unchanged, to the v104 loaded rest collection raw. Offline, read-only.

Rule (scripts/fit_unloaded_gain_calibration.py ``rest_rms`` + ``ACCEPT['rest_noise_rms_m'] = .001``): over fit-split
blocks, windows start ``ceil(5 * tau_stop / DT)`` samples after the step end, last 1 s (20 samples) and slide by one
sample; value = norm of the model-free xy displacement (eval-only truth pose) over the window; rest = RMS over all
windows; rest_noise = rest >= 1 mm. tau_stop = the selected v102 loaded stop lag (form A, 0.10035 s).
Usage: rest_rule_v104.py <raw_dir> <out.json>
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, '/Users/changmin/projects/ugrp-wt/loaded-rest-v104')
from harness import final_pair_loaded_rest_v104 as env  # noqa: E402  (static plan only)

DT = .05
TAU_STOP = 0.10035335696344526       # v102 selected form A stop lag (calibration_dev_pilot_loaded_v102.json tau_stop_s)
THRESHOLD_M = .001
WINDOW_S = 1.

raw = Path(sys.argv[1])
plan = env.protocol()
res = {'schema': 'ugrp.loaded_rest_rule.v104', 'raw': str(raw), 'rule': __doc__.split('\n\n')[1].replace('\n', ' '),
       'tau_stop_s': TAU_STOP, 'threshold_m': THRESHOLD_M, 'runs': {}}
allv = {'r1': [], 'r2': []}
for run in plan['runs']:
    rid = run['id']
    tpath = raw/rid/rid/'eval_only'/'trajectory.jsonl'
    rows = [json.loads(line) for line in open(tpath)]
    t = np.array([r['t'] for r in rows])
    q = np.array([r['qpos'] for r in rows])
    t0 = t[0]                                  # first eval sample = case start (elapsed 0)
    n = round(WINDOW_S/DT)
    seg_t = 0.
    rec = {'trajectory_sha256': hashlib.sha256(tpath.read_bytes()).hexdigest(), 'rows': len(rows), 't0': float(t0)}
    for seg in run['segments']:
        if seg['phase'] == 'step' and seg['role'] == 'fit':
            step_end = env.PREP_END_S + seg_t + seg['duration_s']
            block_end = step_end + run['segments'][run['segments'].index(seg) + 1]['duration_s']
            i_step = int(np.argmin(np.abs(t - (t0 + step_end))))
            i_end = int(np.argmin(np.abs(t - (t0 + block_end))))
            j0 = i_step + math.ceil(5*TAU_STOP/DT)
            for k, who in ((0, 'r1'), (1, 'r2')):
                xy = q[:, 17*k:17*k + 2]
                v = [float(np.linalg.norm(xy[j + n] - xy[j])) for j in range(j0, i_end - n + 1)]
                allv[who] += v
                rec[who] = {'n_windows': len(v), 'rms_m': float(np.sqrt(np.mean(np.square(v)))) if v else None,
                            'max_m': max(v) if v else None,
                            'step_end_t': float(t[i_step]), 'block_end_t': float(t[i_end])}
        seg_t += seg['duration_s']
    res['runs'][rid] = rec
for who, v in allv.items():
    rms = float(np.sqrt(np.mean(np.square(v)))) if v else None
    res[who] = {'n_windows': len(v), 'rms_m': rms, 'rest_noise': None if rms is None else bool(rms >= THRESHOLD_M)}
both = [res['r1']['rest_noise'], res['r2']['rest_noise']]
res['decision'] = {'rest_noise': None if None in both else any(both),
                   'note': 'rest_noise true if either carrier reaches the 1 mm RMS (one shared motion_loaded profile)'}
Path(sys.argv[2]).write_text(json.dumps(res, indent=1))
print(json.dumps({k: res[k] for k in ('r1', 'r2', 'decision')}, indent=1))
for rid, rec in res['runs'].items():
    print(rid, {w: rec.get(w) for w in ('r1', 'r2')})
