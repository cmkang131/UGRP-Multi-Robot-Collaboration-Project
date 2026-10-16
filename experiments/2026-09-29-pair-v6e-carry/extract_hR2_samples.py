#!/usr/bin/env python3
"""hR2: carry entries = the END of the hG grasp_lift runs (GT poses + the recorded PF posterior at grasp_lift stop).

Rule (fixed in the README before any hG case ran): every hG grasp_lift case with category PASS and a stage_stop checkpoint, in hG
sample order, no selection. Usage: extract_hR2_samples.py <hG raw dir name suffix, e.g. 19c8f0b2-ghG>
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_end_samples as S

root = S.OUT/f'pair-stage-probes-{sys.argv[1]}'
rows = [json.loads(l) for l in open(root/'cases.jsonl')]
samples, skipped = [], []
for r in sorted(rows, key=lambda r: r['case_id']):
    d = S.case_dir({**r, 'raw_dir': str(root)})
    if r.get('category') == 'PASS' and d and (d/'checkpoints/stage_stop.npz').exists():
        sid = r['case_id'].split(':')[2]                      # hG01..hG10
        samples.append(S.sample('hR2_' + sid[2:], r, d, f'grasp_lift end of {sid} ({sys.argv[1]})'))
    else:
        skipped.append({'case_id': r['case_id'], 'category': r.get('category')})
json.dump({'rule': __doc__.strip(), 'source_raw': sys.argv[1], 'skipped_not_pass': skipped, 'samples': samples},
          open(Path(__file__).with_name('hR2_samples.json'), 'w'), indent=1)
S.show(samples); print('skipped (not PASS):', skipped)
