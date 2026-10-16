#!/usr/bin/env python3
"""hR: carry-entry placements taken from recorded grasp_lift stage-probe raws (no new physics; GT is the staging source only).

Rule (fixed in the README before any hR carry case ran): from each of the two raws below, the cases with category PASS,
sorted by case_id, index round(i*(n-1)/4) for i = 0..4 -> 5 + 5 = 10 samples. Each sample is the end-of-grasp_lift state:
true beam x/y/yaw and both robots' base poses (gt_at_end). Neither raw was read by any fit (fits read carry raws only).
Output: hR_samples.json (read by harness.pair_stage_probe.hr_rows / run_pair_stage_probes --setup-variant hR).
"""
import json
from pathlib import Path
OUT = Path('/Users/changmin/projects/ugrp/outputs')
RAWS = ['4714263a-v6d-final-bound-e2e', 'b534a9b5-v6c-grasp-grid']
samples = []
for raw in RAWS:
    root = OUT/f'pair-stage-probes-{raw}'
    rows = [json.loads(l) for l in open(root/'cases.jsonl')]
    ok = sorted((r for r in rows if r.get('category') == 'PASS' and r['stage'] == 'grasp_lift'), key=lambda r: r['case_id'])
    n = len(ok)
    for i in range(5):
        r = ok[round(i*(n - 1)/4)]
        d = root/'cases'/r['case_id'].replace('@', '_').replace(':', '_').replace('/', '_')
        g = json.load(open(d/'result.json'))['gt_at_end']
        samples.append({'id': 'hR%02d' % (len(samples) + 1), 'raw': raw, 'case_id': r['case_id'],
                        'beam_xyyaw': [g['beam_xyz'][0], g['beam_xyz'][1], g['beam_yaw']],
                        'robots': {k: [float(v) for v in g['robots'][k]] for k in ('r1', 'r2')},
                        'grip_errors_at_end': {k: {a: float(b) for a, b in g['grip_errors_all'][k].items() if a != 'grip_base_m'} for k in ('r1', 'r2')}})
json.dump({'rule': __doc__.strip().splitlines()[2:4], 'raws': RAWS, 'samples': samples}, open(Path(__file__).with_name('hR_samples.json'), 'w'), indent=1)
for s in samples:
    print(s['id'], s['raw'][:12], s['case_id'].split(':', 2)[2], 'beam y %.4f yaw %.3f deg' % (s['beam_xyyaw'][1], s['beam_xyyaw'][2]*57.2958),
          'grip r1 %s r2 %s' % ({k: round(v, 3) for k, v in s['grip_errors_at_end']['r1'].items()}, {k: round(v, 3) for k, v in s['grip_errors_at_end']['r2'].items()}))
